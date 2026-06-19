"""Git Tool"""
from omega.tools.registry import BaseTool, ToolResult
from omega.tools.process_utils import run_shell_with_timeout


class GitTool(BaseTool):
    name = "git"
    description = "Git version control operations"

    async def _git(self, args: str, cwd: str = ".", timeout: int = 60) -> dict:
        result = await run_shell_with_timeout(f"git {args}", cwd=cwd, timeout=timeout)
        return {
            "success": result["success"],
            "output": result["output"].strip(),
            "error": result["error"].strip(),
        }

    async def execute(self, action: str, **kwargs) -> ToolResult:
        try:
            if action == "init":
                r = await self._git("init", kwargs.get("path", "."))
            elif action == "clone":
                r = await self._git(f"clone {kwargs['url']} {kwargs.get('dest', '')}")
            elif action == "status":
                r = await self._git("status --short", kwargs.get("path", "."))
            elif action == "add":
                files = kwargs.get("files", ".")
                r = await self._git(f"add {files}", kwargs.get("path", "."))
            elif action == "commit":
                msg = kwargs.get("message", "Auto commit by OMEGA")
                r = await self._git(f'commit -m "{msg}"', kwargs.get("path", "."))
            elif action == "push":
                remote = kwargs.get("remote", "origin")
                branch = kwargs.get("branch", "main")
                r = await self._git(f"push {remote} {branch}", kwargs.get("path", "."))
            elif action == "pull":
                r = await self._git("pull", kwargs.get("path", "."))
            elif action == "log":
                n = kwargs.get("n", 10)
                r = await self._git(f"log --oneline -{n}", kwargs.get("path", "."))
            elif action == "branch":
                name = kwargs.get("name", "")
                r = await self._git(f"checkout -b {name}" if name else "branch -a",
                                     kwargs.get("path", "."))
            elif action == "diff":
                r = await self._git("diff", kwargs.get("path", "."))
            elif action == "stash":
                r = await self._git("stash", kwargs.get("path", "."))
            else:
                # Pass through raw git command
                r = await self._git(kwargs.get("args", ""), kwargs.get("path", "."))

            return ToolResult(success=r["success"], output=r["output"] or r["error"])
        except Exception as e:
            return ToolResult(success=False, error=str(e))
