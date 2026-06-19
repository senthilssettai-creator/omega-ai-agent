"""Executor Agent - Orchestrates plans and executes system operations"""

import json
import asyncio
import subprocess
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import structlog

from omega.agents.base import BaseAgent, AgentResult
from omega.models.router import TaskType
from omega.config import config

logger = structlog.get_logger(__name__)


class ExecutorAgent(BaseAgent):
    name = "executor"
    description = "Executes terminal commands, manages files, and coordinates agent workflows"
    task_type = TaskType.GENERAL

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pending_approvals: List[Dict] = []

    @property
    def system_prompt(self) -> str:
        return """You are the Executor Agent for OMEGA.

You execute plans by:
1. Running terminal commands
2. Managing files and directories
3. Coordinating between agents
4. Tracking progress
5. Handling errors and retries

You have access to the full filesystem and terminal.
Always check if an action is safe before executing.
Dangerous operations require user approval."""

    def _needs_approval(self, command: str) -> bool:
        """Check if a command requires user approval"""
        command_lower = command.lower()
        return any(danger in command_lower for danger in config.require_approval_for)

    async def run_command(self, command: str, cwd: Optional[str] = None,
                          timeout: int = 60, require_approval: bool = False) -> Dict:
        """Execute a shell command"""
        if require_approval or self._needs_approval(command):
            return {
                "success": False,
                "output": "",
                "error": f"Command requires approval: {command}",
                "needs_approval": True,
                "command": command,
            }

        from omega.tools.process_utils import run_shell_with_timeout
        return await run_shell_with_timeout(command, cwd=cwd, timeout=timeout)

    async def create_project(self, name: str, project_type: str,
                              path: Optional[str] = None) -> AgentResult:
        """Create a new project structure"""
        project_path = Path(path or os.getcwd()) / name

        messages = [
            {
                "role": "user",
                "content": f"""Create the directory structure and initial files for a {project_type} project named '{name}'.

Output JSON:
{{
  "directories": ["dir1", "dir2/subdir"],
  "files": [
    {{"path": "relative/path", "content": "file content"}}
  ],
  "setup_commands": ["command1", "command2"]
}}

Be comprehensive - include all necessary files for a production-ready project."""
            }
        ]

        result = await self.think(messages)
        try:
            result_str = result.strip()
            if "```json" in result_str:
                result_str = result_str.split("```json")[1].split("```")[0].strip()
            structure = json.loads(result_str)
        except Exception:
            return AgentResult(success=False, error="Could not parse project structure")

        # Create directories
        project_path.mkdir(parents=True, exist_ok=True)
        for dir_ in structure.get("directories", []):
            (project_path / dir_).mkdir(parents=True, exist_ok=True)

        # Create files
        for file_spec in structure.get("files", []):
            file_path = project_path / file_spec["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(file_spec.get("content", ""))

        # Run setup commands (safe ones only)
        setup_results = []
        for cmd in structure.get("setup_commands", []):
            if not self._needs_approval(cmd):
                result = await self.run_command(cmd, cwd=str(project_path))
                setup_results.append(result)

        return AgentResult(
            success=True,
            output={
                "project_path": str(project_path),
                "structure": structure,
                "setup_results": setup_results,
            }
        )

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        """Execute a task using the LLM to determine approach"""
        messages = [
            {
                "role": "user",
                "content": f"""Task: {task}

Context: {json.dumps(context, indent=2) if context else 'None'}

Determine the best way to execute this task.
Output JSON:
{{
  "approach": "description of approach",
  "commands": [
    {{"cmd": "shell command", "cwd": "optional working dir", "description": "why"}}
  ],
  "file_operations": [
    {{"op": "create/read/delete/move", "path": "path", "content": "for create"}}
  ]
}}"""
            }
        ]

        plan_result = await self.think(messages)

        try:
            plan_str = plan_result.strip()
            if "```json" in plan_str:
                plan_str = plan_str.split("```json")[1].split("```")[0].strip()
            plan = json.loads(plan_str)
        except Exception:
            return AgentResult(success=False, error=f"Could not parse execution plan: {plan_result[:200]}")

        results = []
        # Execute commands
        for cmd_spec in plan.get("commands", []):
            cmd = cmd_spec.get("cmd", "")
            if not cmd:
                continue
            result = await self.run_command(
                cmd,
                cwd=cmd_spec.get("cwd"),
            )
            results.append(result)
            if not result["success"] and not result.get("needs_approval"):
                logger.warning("command_failed", cmd=cmd, error=result["error"])

        # File operations
        for op_spec in plan.get("file_operations", []):
            op = op_spec.get("op", "")
            path = Path(op_spec.get("path", ""))
            try:
                if op == "create":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(op_spec.get("content", ""))
                    results.append({"op": "create", "path": str(path), "success": True})
                elif op == "delete":
                    if path.exists():
                        if path.is_dir():
                            shutil.rmtree(path)
                        else:
                            path.unlink()
                    results.append({"op": "delete", "path": str(path), "success": True})
                elif op == "move":
                    dest = Path(op_spec.get("destination", ""))
                    shutil.move(str(path), str(dest))
                    results.append({"op": "move", "path": str(path), "dest": str(dest), "success": True})
                elif op == "read":
                    content = path.read_text() if path.exists() else ""
                    results.append({"op": "read", "path": str(path), "content": content, "success": True})
            except Exception as e:
                results.append({"op": op, "path": str(path), "success": False, "error": str(e)})

        success = all(r.get("success", True) for r in results)
        return AgentResult(
            success=success,
            output={
                "approach": plan.get("approach", ""),
                "results": results,
            }
        )
