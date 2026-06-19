"""Tests for omega.tools"""

import pytest
from pathlib import Path

from omega.tools.registry import ToolRegistry
from omega.tools.filesystem import FilesystemTool
from omega.tools.terminal import TerminalTool


class TestFilesystemTool:
    @pytest.fixture
    def fs_tool(self):
        return FilesystemTool()

    @pytest.mark.asyncio
    async def test_write_and_read(self, fs_tool, tmp_path):
        file_path = str(tmp_path / "test.txt")
        write_result = await fs_tool.execute("write", path=file_path, content="hello world")
        assert write_result.success

        read_result = await fs_tool.execute("read", path=file_path)
        assert read_result.success
        assert read_result.output == "hello world"

    @pytest.mark.asyncio
    async def test_append(self, fs_tool, tmp_path):
        file_path = str(tmp_path / "test.txt")
        await fs_tool.execute("write", path=file_path, content="line1\n")
        await fs_tool.execute("append", path=file_path, content="line2\n")
        result = await fs_tool.execute("read", path=file_path)
        assert result.output == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_exists(self, fs_tool, tmp_path):
        file_path = str(tmp_path / "exists_test.txt")
        result = await fs_tool.execute("exists", path=file_path)
        assert result.output is False

        await fs_tool.execute("write", path=file_path, content="x")
        result = await fs_tool.execute("exists", path=file_path)
        assert result.output is True

    @pytest.mark.asyncio
    async def test_delete(self, fs_tool, tmp_path):
        file_path = str(tmp_path / "to_delete.txt")
        await fs_tool.execute("write", path=file_path, content="x")
        result = await fs_tool.execute("delete", path=file_path)
        assert result.success
        assert not Path(file_path).exists()

    @pytest.mark.asyncio
    async def test_list_directory(self, fs_tool, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = await fs_tool.execute("list", path=str(tmp_path))
        assert result.success
        names = [item["name"] for item in result.output]
        assert "a.txt" in names
        assert "b.txt" in names

    @pytest.mark.asyncio
    async def test_unknown_action_fails_gracefully(self, fs_tool):
        result = await fs_tool.execute("nonexistent_action")
        assert not result.success
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_read_nonexistent_file_fails_gracefully(self, fs_tool, tmp_path):
        result = await fs_tool.execute("read", path=str(tmp_path / "does_not_exist.txt"))
        assert not result.success
        assert result.error is not None


class TestTerminalTool:
    @pytest.fixture
    def term_tool(self):
        return TerminalTool()

    @pytest.mark.asyncio
    async def test_run_simple_command(self, term_tool):
        result = await term_tool.execute("run", command="echo hello")
        assert result.success
        assert "hello" in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_run_failing_command(self, term_tool):
        result = await term_tool.execute("run", command="exit 1")
        assert not result.success
        assert result.output["returncode"] == 1

    @pytest.mark.asyncio
    async def test_timeout(self, term_tool):
        result = await term_tool.execute("run", command="sleep 5", timeout=1)
        assert not result.success
        assert "Timed out" in result.error


class TestToolRegistry:
    @pytest.mark.asyncio
    async def test_register_and_get(self):
        registry = ToolRegistry()
        tool = FilesystemTool()
        registry.register(tool)
        assert registry.get("filesystem") is tool

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_fails_gracefully(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent_tool", "action")
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_load_builtin_tools(self):
        registry = ToolRegistry()
        await registry.load_builtin_tools()
        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "filesystem" in tool_names
        assert "terminal" in tool_names
        assert "git" in tool_names
