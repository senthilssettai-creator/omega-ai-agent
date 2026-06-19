"""Tests for omega.tools.process_utils

These guard against a real bug found during testing: timing out a subprocess
via asyncio.wait_for(proc.communicate(), ...) does NOT kill the underlying
process. Left unfixed, this leaks an orphaned OS process per timeout, which
later surfaces as "Event loop is closed" warnings (or worse, lingering
processes) when the abandoned transport is garbage-collected.
"""

import asyncio
import os
import signal
import time

import pytest

from omega.tools.process_utils import run_shell_with_timeout


class TestRunShellWithTimeout:
    @pytest.mark.asyncio
    async def test_successful_command(self):
        result = await run_shell_with_timeout("echo hello", timeout=5)
        assert result["success"] is True
        assert "hello" in result["output"]
        assert result["returncode"] == 0

    @pytest.mark.asyncio
    async def test_failing_command(self):
        result = await run_shell_with_timeout("exit 1", timeout=5)
        assert result["success"] is False
        assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_timeout_reports_failure(self):
        result = await run_shell_with_timeout("sleep 5", timeout=1)
        assert result["success"] is False
        assert result["returncode"] == -1
        assert "Timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_timeout_actually_kills_the_process(self):
        """Regression test: verify the spawned process is actually terminated
        after timeout, not left running (consuming CPU/resources) in the
        background.

        Note: on Linux, a killed grandchild process (e.g. the 'sleep' spawned
        by 'sh -c sleep 5') is reparented to init and may briefly appear as a
        harmless <defunct>/zombie table entry until init reaps it -- this
        holds no real resources and is not a leak. What we actually must
        verify is that the process is no longer *alive and running* (i.e. its
        state is not anything but a zombie)."""
        marker = f"OMEGA_LEAK_TEST_{int(time.time() * 1000)}"
        command = f"sleep 5 # {marker}"

        result = await run_shell_with_timeout(command, timeout=1)
        assert result["success"] is False

        # Give the OS a brief moment, then verify no LIVE (non-zombie) process
        # matching our marker remains. ps state codes: Z = zombie (harmless,
        # pending reap by init); anything else means it's genuinely still running.
        await asyncio.sleep(0.3)
        proc = await asyncio.create_subprocess_shell(
            f"ps -eo pid,stat,cmd | grep '{marker}' | grep -v grep",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        lines = [l for l in stdout.decode().strip().splitlines() if l.strip()]
        live_processes = [l for l in lines if "Z" not in l.split()[1]] if lines else []
        assert live_processes == [], (
            f"Process leaked after timeout (still alive, not just a zombie)! "
            f"Found: {live_processes}"
        )

    @pytest.mark.asyncio
    async def test_custom_cwd(self, tmp_path):
        (tmp_path / "marker.txt").write_text("present")
        result = await run_shell_with_timeout("ls", cwd=str(tmp_path), timeout=5)
        assert "marker.txt" in result["output"]

    @pytest.mark.asyncio
    async def test_custom_env(self):
        result = await run_shell_with_timeout(
            "echo $OMEGA_TEST_VAR", env={"OMEGA_TEST_VAR": "test_value_123"}, timeout=5
        )
        assert "test_value_123" in result["output"]
