"""Shared subprocess execution helpers for OMEGA

Centralizes the run-with-timeout pattern used across tools/agents so that a
timeout always kills and reaps the underlying process instead of abandoning
it (which leaks an orphaned OS process and triggers "Event loop is closed"
warnings later when its transport is garbage-collected).

Important: `asyncio.create_subprocess_shell` spawns `/bin/sh -c "<command>"`.
Killing that shell process does NOT kill its children (e.g. `sleep 5` started
by the shell survives as an orphan) because signals aren't automatically
propagated to child processes. To actually terminate the whole command,
including anything it spawns, we start the subprocess in its own process
group (via os.setsid) and send the kill signal to the entire group with
os.killpg instead of proc.kill().
"""

import asyncio
import os
import signal
from typing import Dict, Optional


async def run_shell_with_timeout(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
    env: Optional[Dict[str, str]] = None,
) -> Dict:
    """Run a shell command, killing and reaping its entire process group if it
    exceeds timeout.

    Returns a dict with: success, output (stdout), error (stderr or error message),
    returncode, command.
    """
    proc = None
    try:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or os.getcwd(),
            env=run_env,
            preexec_fn=os.setsid,  # new process group so we can kill all descendants
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "success": proc.returncode == 0,
            "output": stdout.decode("utf-8", errors="replace"),
            "error": stderr.decode("utf-8", errors="replace"),
            "returncode": proc.returncode,
            "command": command,
        }
    except asyncio.TimeoutError:
        await _kill_and_reap(proc)
        return {
            "success": False,
            "output": "",
            "error": f"Timed out after {timeout}s",
            "returncode": -1,
            "command": command,
        }
    except Exception as e:
        await _kill_and_reap(proc)
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "returncode": -1,
            "command": command,
        }


async def _kill_and_reap(proc: Optional[asyncio.subprocess.Process]):
    """Kill a subprocess and its whole process group (so spawned children like
    a 'sleep' started by 'sh -c' don't survive as live orphans), then reap our
    direct child.

    Note: killpg terminates all processes in the group, including
    grandchildren the shell spawned. Those grandchildren aren't our direct
    children, so proc.wait() won't reap them -- after being killed they
    become harmless zombies reaped by init. That's standard, acceptable Unix
    behavior and holds no real resources; what matters is that nothing is
    left *running*.
    """
    if proc is None or proc.returncode is not None:
        return

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception:
        try:
            proc.kill()
        except ProcessLookupError:
            pass

    try:
        await proc.wait()
    except Exception:
        pass
