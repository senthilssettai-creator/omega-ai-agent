"""DevOps Agent - Docker, Git, GitHub, CI/CD, and deployment"""

import json
import asyncio
import subprocess
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import structlog

from omega.agents.base import BaseAgent, AgentResult
from omega.models.router import TaskType

logger = structlog.get_logger(__name__)


class DevOpsAgent(BaseAgent):
    name = "devops"
    description = "Manages Docker, Git, GitHub, CI/CD pipelines, and deployments"
    task_type = TaskType.CODING

    @property
    def system_prompt(self) -> str:
        return """You are the DevOps Agent for OMEGA.

Capabilities:
- Docker container management
- Git operations
- GitHub integration
- CI/CD pipeline creation
- Infrastructure management
- Deployment automation

Always output executable commands and configurations.
Include rollback procedures for critical operations."""

    async def _run(self, cmd: str, cwd: Optional[str] = None) -> Dict:
        """Run a command and return result"""
        from omega.tools.process_utils import run_shell_with_timeout
        result = await run_shell_with_timeout(cmd, cwd=cwd, timeout=120)
        return {
            "success": result["success"],
            "output": result["output"].strip(),
            "error": result["error"].strip(),
            "returncode": result["returncode"],
        }

    async def git_init(self, path: str, remote_url: Optional[str] = None) -> AgentResult:
        """Initialize a git repository"""
        results = []
        results.append(await self._run("git init", cwd=path))
        results.append(await self._run('git config user.email "omega@agent.ai"', cwd=path))
        results.append(await self._run('git config user.name "OMEGA Agent"', cwd=path))

        if remote_url:
            results.append(await self._run(f"git remote add origin {remote_url}", cwd=path))

        return AgentResult(success=all(r["success"] for r in results), output=results)

    async def git_commit(self, path: str, message: str,
                          add_all: bool = True) -> AgentResult:
        """Create a git commit"""
        results = []
        if add_all:
            results.append(await self._run("git add -A", cwd=path))
        results.append(await self._run(f'git commit -m "{message}"', cwd=path))
        return AgentResult(success=results[-1]["success"], output=results)

    async def git_status(self, path: str) -> Dict:
        """Get git status"""
        status = await self._run("git status --porcelain", cwd=path)
        log = await self._run("git log --oneline -10", cwd=path)
        branch = await self._run("git branch --show-current", cwd=path)
        return {
            "status": status["output"],
            "recent_commits": log["output"],
            "branch": branch["output"],
        }

    async def docker_build(self, path: str, tag: str,
                            dockerfile: str = "Dockerfile") -> AgentResult:
        """Build a Docker image"""
        result = await self._run(
            f"docker build -f {dockerfile} -t {tag} .",
            cwd=path
        )
        return AgentResult(success=result["success"], output=result)

    async def docker_run(self, image: str, name: str, ports: Optional[Dict] = None,
                          env: Optional[Dict] = None, detach: bool = True) -> AgentResult:
        """Run a Docker container"""
        cmd_parts = ["docker run"]
        if detach:
            cmd_parts.append("-d")
        cmd_parts.extend(["--name", name])
        if ports:
            for host_port, container_port in ports.items():
                cmd_parts.extend(["-p", f"{host_port}:{container_port}"])
        if env:
            for key, value in env.items():
                cmd_parts.extend(["-e", f"{key}={value}"])
        cmd_parts.append(image)

        result = await self._run(" ".join(cmd_parts))
        return AgentResult(success=result["success"], output=result)

    async def generate_dockerfile(self, project_path: str,
                                   project_type: str) -> AgentResult:
        """Generate an optimized Dockerfile for a project"""
        messages = [
            {
                "role": "user",
                "content": f"""Generate an optimized, production-ready Dockerfile for a {project_type} project.

Project path: {project_path}

Requirements:
- Multi-stage build where appropriate
- Minimal final image size
- Security best practices (non-root user)
- Proper layer caching
- Health check

Also generate docker-compose.yml if appropriate.

Output JSON:
{{
  "dockerfile": "full Dockerfile content",
  "docker_compose": "optional docker-compose.yml content",
  "dockerignore": ".dockerignore content",
  "build_command": "docker build command",
  "run_command": "docker run command"
}}"""
            }
        ]

        result = await self.think(messages)
        try:
            result_str = result.strip()
            if "```json" in result_str:
                result_str = result_str.split("```json")[1].split("```")[0].strip()
            docker_config = json.loads(result_str)
        except Exception:
            return AgentResult(success=False, error="Could not parse Docker config")

        # Write files
        project = Path(project_path)
        if docker_config.get("dockerfile"):
            (project / "Dockerfile").write_text(docker_config["dockerfile"])
        if docker_config.get("docker_compose"):
            (project / "docker-compose.yml").write_text(docker_config["docker_compose"])
        if docker_config.get("dockerignore"):
            (project / ".dockerignore").write_text(docker_config["dockerignore"])

        return AgentResult(success=True, output=docker_config)

    async def generate_cicd(self, project_path: str, platform: str = "github") -> AgentResult:
        """Generate CI/CD pipeline configuration"""
        messages = [
            {
                "role": "user",
                "content": f"""Generate a complete CI/CD pipeline for {platform} Actions.

Project path: {project_path}

Include:
- Build and test stages
- Docker build and push
- Deployment stages (staging + production)
- Security scanning
- Dependency caching

Output the workflow YAML file content."""
            }
        ]

        result = await self.think(messages)

        if platform == "github":
            workflow_dir = Path(project_path) / ".github" / "workflows"
            workflow_dir.mkdir(parents=True, exist_ok=True)

            # Clean up the result (remove markdown fencing)
            yaml_content = result.strip()
            if "```yaml" in yaml_content:
                yaml_content = yaml_content.split("```yaml")[1].split("```")[0].strip()
            elif "```" in yaml_content:
                yaml_content = yaml_content.split("```")[1].split("```")[0].strip()

            (workflow_dir / "ci.yml").write_text(yaml_content)

        return AgentResult(success=True, output={"pipeline": result, "platform": platform})

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        """Execute a DevOps task"""
        messages = [
            {
                "role": "user",
                "content": f"""DevOps task: {task}

Context: {json.dumps(context, indent=2) if context else 'None'}

Determine the commands and configurations needed.
Output JSON:
{{
  "approach": "description",
  "commands": [{{"cmd": "...", "cwd": "optional"}}],
  "files": [{{"path": "...", "content": "..."}}]
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
            return AgentResult(success=False, error="Could not parse DevOps plan")

        results = []
        for cmd_spec in plan.get("commands", []):
            result = await self._run(cmd_spec.get("cmd", ""), cwd=cmd_spec.get("cwd"))
            results.append(result)

        for file_spec in plan.get("files", []):
            path = Path(file_spec.get("path", ""))
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(file_spec.get("content", ""))
                results.append({"file": str(path), "success": True})
            except Exception as e:
                results.append({"file": str(path), "success": False, "error": str(e)})

        success = all(r.get("success", True) for r in results)
        return AgentResult(success=success, output={
            "approach": plan.get("approach", ""),
            "results": results,
        })
