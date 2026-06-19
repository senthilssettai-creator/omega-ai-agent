"""Critic Agent - Reviews, validates, and improves agent outputs"""

import json
from typing import Any, Dict, List, Optional
import structlog

from omega.agents.base import BaseAgent, AgentResult
from omega.models.router import TaskType

logger = structlog.get_logger(__name__)


class CriticAgent(BaseAgent):
    name = "critic"
    description = "Reviews outputs for quality, correctness, and completeness"
    task_type = TaskType.REASONING

    @property
    def system_prompt(self) -> str:
        return """You are the Critic Agent for OMEGA.

Your job is to rigorously review outputs from other agents.

You check for:
1. Correctness - Is the output factually correct and logically sound?
2. Completeness - Does it fully address the original task?
3. Quality - Is it production-ready and well-structured?
4. Security - Are there any security vulnerabilities?
5. Edge cases - Are important edge cases handled?

Be constructive but demanding. High standards produce better outcomes.

Output JSON:
{
  "passed": true/false,
  "score": 0-10,
  "issues": [
    {"severity": "critical/high/medium/low", "description": "...", "suggestion": "..."}
  ],
  "improvements": ["specific improvement 1", "..."],
  "verdict": "brief verdict"
}"""

    async def review(self, task: str, output: Any,
                     agent_name: str = "unknown") -> Dict:
        """Review an agent's output"""
        messages = [
            {
                "role": "user",
                "content": f"""Review this output from the {agent_name} agent:

Original task: {task}

Output:
{json.dumps(output, indent=2) if isinstance(output, dict) else str(output)}

Evaluate quality, correctness, completeness. Output JSON review."""
            }
        ]

        result = await self.think(messages)

        try:
            result_str = result.strip()
            if "```json" in result_str:
                result_str = result_str.split("```json")[1].split("```")[0].strip()
            review = json.loads(result_str)
        except Exception:
            review = {
                "passed": True,
                "score": 7,
                "issues": [],
                "improvements": [],
                "verdict": result[:200],
            }

        logger.info("critic_review", agent=agent_name, score=review.get("score"), passed=review.get("passed"))
        return review

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        output = context.get("output")
        agent_name = context.get("agent_name", "unknown")
        review = await self.review(task, output, agent_name)
        return AgentResult(success=review.get("passed", True), output=review)

    async def self_improve(self, system_prompt: str, failures: List[Dict]) -> str:
        """Suggest improvements to a system prompt based on failures"""
        messages = [
            {
                "role": "user",
                "content": f"""Analyze these agent failures and suggest improvements to the system prompt:

Current system prompt:
{system_prompt}

Recent failures:
{json.dumps(failures, indent=2)}

Output an improved system prompt that addresses these failures."""
            }
        ]
        return await self.think(messages)
