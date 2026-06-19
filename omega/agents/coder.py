"""Coder Agent - Code generation, debugging, testing, and review"""

import json
import asyncio
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import structlog

from omega.agents.base import BaseAgent, AgentResult
from omega.models.router import TaskType

logger = structlog.get_logger(__name__)


class CoderAgent(BaseAgent):
    name = "coder"
    description = "Writes, debugs, tests, and reviews code in any language"
    task_type = TaskType.CODING

    @property
    def system_prompt(self) -> str:
        return """You are the Coder Agent for OMEGA - an expert software engineer.

Capabilities:
- Write production-quality code in any language
- Debug and fix complex bugs
- Refactor and optimize code
- Generate comprehensive tests
- Code review and security analysis
- Architect software systems

Standards:
- Write clean, documented, production-ready code
- Follow language-specific best practices
- Include error handling
- Write tests for critical paths
- Security-first mindset

When creating files, output JSON:
{
  "files": [
    {"path": "relative/path/file.py", "content": "full file content"},
    ...
  ],
  "commands": ["pip install x", "python -m pytest"],
  "explanation": "what was done",
  "tests": "how to test"
}"""

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        """Execute a coding task"""

        # Get relevant context
        project_path = context.get("project_path", ".")
        language = context.get("language", "python")
        existing_code = context.get("existing_code", "")

        messages = [
            {
                "role": "user",
                "content": f"""Coding task: {task}

Language: {language}
Project path: {project_path}
{f'Existing code:{chr(10)}{existing_code}' if existing_code else ''}

Please implement this. Output JSON with files, commands, and explanation.
All file content must be complete and production-ready."""
            }
        ]

        result = await self.think(messages)

        try:
            result_str = result.strip()
            if "```json" in result_str:
                result_str = result_str.split("```json")[1].split("```")[0].strip()
            elif "```" in result_str:
                result_str = result_str.split("```")[1].split("```")[0].strip()

            code_result = json.loads(result_str)
        except Exception:
            # Return raw code if JSON parse fails
            code_result = {
                "files": [],
                "explanation": result,
                "commands": [],
            }

        # Write files if project path exists and files specified
        files_written = []
        if code_result.get("files") and os.path.exists(project_path):
            for file_spec in code_result["files"]:
                file_path = Path(project_path) / file_spec["path"]
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(file_spec["content"])
                files_written.append(str(file_path))
                logger.info("file_written", path=str(file_path))

        return AgentResult(
            success=True,
            output={
                "files_written": files_written,
                "code_result": code_result,
                "explanation": code_result.get("explanation", ""),
            }
        )

    async def debug(self, code: str, error: str, language: str = "python") -> AgentResult:
        """Debug code given an error"""
        messages = [
            {
                "role": "user",
                "content": f"""Debug this {language} code:

Code:
```{language}
{code}
```

Error:
```
{error}
```

Identify the root cause and provide a fixed version.
Output JSON: {{"root_cause": "...", "fixed_code": "...", "explanation": "..."}}"""
            }
        ]

        result = await self.think(messages)
        try:
            result_str = result.strip()
            if "```json" in result_str:
                result_str = result_str.split("```json")[1].split("```")[0].strip()
            fix = json.loads(result_str)
            return AgentResult(success=True, output=fix)
        except Exception:
            return AgentResult(success=True, output={"explanation": result, "fixed_code": ""})

    async def generate_tests(self, code: str, language: str = "python") -> AgentResult:
        """Generate tests for code"""
        messages = [
            {
                "role": "user",
                "content": f"""Generate comprehensive tests for this {language} code:

```{language}
{code}
```

Include:
- Unit tests
- Edge cases
- Integration tests where appropriate

Output the complete test file content."""
            }
        ]
        result = await self.think(messages)
        return AgentResult(success=True, output={"tests": result})

    async def review(self, code: str, language: str = "python") -> AgentResult:
        """Code review"""
        messages = [
            {
                "role": "user",
                "content": f"""Review this {language} code for:
1. Bugs and logic errors
2. Security vulnerabilities
3. Performance issues
4. Code quality and maintainability
5. Best practice violations

Code:
```{language}
{code}
```

Output JSON: {{"issues": [{{"severity": "high/medium/low", "line": N, "description": "...", "fix": "..."}}], "score": 0-10, "summary": "..."}}"""
            }
        ]
        result = await self.think(messages)
        try:
            result_str = result.strip()
            if "```json" in result_str:
                result_str = result_str.split("```json")[1].split("```")[0].strip()
            review = json.loads(result_str)
            return AgentResult(success=True, output=review)
        except Exception:
            return AgentResult(success=True, output={"summary": result})

    async def run_code(self, code: str, language: str = "python",
                       timeout: int = 30) -> Dict:
        """Execute code in a safe subprocess"""
        with tempfile.TemporaryDirectory() as tmpdir:
            if language == "python":
                code_file = Path(tmpdir) / "code.py"
                code_file.write_text(code)
                try:
                    proc = subprocess.run(
                        ["python3", str(code_file)],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=tmpdir,
                    )
                    return {
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                        "returncode": proc.returncode,
                        "success": proc.returncode == 0,
                    }
                except subprocess.TimeoutExpired:
                    return {"stdout": "", "stderr": "Timeout", "returncode": -1, "success": False}
            elif language in ("javascript", "js", "node"):
                code_file = Path(tmpdir) / "code.js"
                code_file.write_text(code)
                try:
                    proc = subprocess.run(
                        ["node", str(code_file)],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=tmpdir,
                    )
                    return {
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                        "returncode": proc.returncode,
                        "success": proc.returncode == 0,
                    }
                except Exception as e:
                    return {"stdout": "", "stderr": str(e), "returncode": -1, "success": False}
            else:
                return {"stdout": "", "stderr": f"Language {language} not supported for direct execution", "returncode": -1, "success": False}
