"""Docker Tool"""
import asyncio
from omega.tools.registry import BaseTool, ToolResult
from omega.tools.process_utils import run_shell_with_timeout


class DockerTool(BaseTool):
    name = "docker"
    description = "Docker container and image management"

    async def _docker(self, args: str) -> dict:
        result = await run_shell_with_timeout(f"docker {args}", timeout=120)
        return {
            "success": result["success"],
            "output": result["output"].strip(),
            "error": result["error"].strip(),
        }

    async def execute(self, action: str, **kwargs) -> ToolResult:
        try:
            if action == "ps":
                r = await self._docker("ps --format json")
            elif action == "build":
                tag = kwargs.get("tag", "omega-app")
                path = kwargs.get("path", ".")
                r = await self._docker(f"build -t {tag} {path}")
            elif action == "run":
                image = kwargs["image"]
                name = kwargs.get("name", "")
                ports = " ".join(f"-p {h}:{c}" for h, c in kwargs.get("ports", {}).items())
                env = " ".join(f"-e {k}={v}" for k, v in kwargs.get("env", {}).items())
                detach = "-d" if kwargs.get("detach", True) else ""
                name_flag = f"--name {name}" if name else ""
                r = await self._docker(f"run {detach} {name_flag} {ports} {env} {image}")
            elif action == "stop":
                r = await self._docker(f"stop {kwargs['container']}")
            elif action == "logs":
                r = await self._docker(f"logs {kwargs['container']}")
            elif action == "pull":
                r = await self._docker(f"pull {kwargs['image']}")
            elif action == "images":
                r = await self._docker("images")
            elif action == "exec":
                r = await self._docker(f"exec {kwargs['container']} {kwargs['command']}")
            else:
                r = await self._docker(kwargs.get("args", ""))
            return ToolResult(success=r["success"], output=r["output"] or r["error"])
        except Exception as e:
            return ToolResult(success=False, error=str(e))
