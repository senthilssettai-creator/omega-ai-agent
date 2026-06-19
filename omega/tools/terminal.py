"""Terminal Tool"""
import asyncio
import os
from typing import Optional
from omega.tools.registry import BaseTool, ToolResult
from omega.tools.process_utils import run_shell_with_timeout


class TerminalTool(BaseTool):
    name = "terminal"
    description = "Execute shell commands and scripts"

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "run":
            return await self._run(**kwargs)
        return ToolResult(success=False, error=f"Unknown action: {action}")

    async def _run(self, command: str, cwd: Optional[str] = None,
                   timeout: int = 60, env: Optional[dict] = None) -> ToolResult:
        """Run a shell command"""
        result = await run_shell_with_timeout(command, cwd=cwd, timeout=timeout, env=env)

        if result["returncode"] == -1:
            # Timed out or failed to even start - report as a tool-level error
            return ToolResult(success=False, error=result["error"])

        return ToolResult(
            success=result["success"],
            output={
                "stdout": result["output"],
                "stderr": result["error"],
                "returncode": result["returncode"],
            },
        )
