"""Planner Agent - Decomposes goals into structured task trees"""

import json
from typing import Any, Dict, List, Optional
import structlog

from omega.agents.base import BaseAgent, AgentResult
from omega.models.router import TaskType

logger = structlog.get_logger(__name__)


PLANNER_SYSTEM = """You are the Planner Agent for OMEGA - an autonomous AI agent system.

Your job is to break down high-level goals into structured, executable task trees.

You must output ONLY valid JSON in this exact format:
{
  "goal": "the original goal",
  "summary": "brief description of the plan",
  "tasks": [
    {
      "id": "task_1",
      "name": "Task name",
      "description": "Detailed description",
      "agent": "which agent handles this (planner/researcher/coder/browser/devops/executor)",
      "depends_on": [],
      "priority": 1,
      "estimated_minutes": 5,
      "tools_needed": ["tool1", "tool2"],
      "success_criteria": "how to know this task succeeded"
    }
  ],
  "risks": ["potential risk 1", "potential risk 2"],
  "estimated_total_minutes": 30
}

Available agents:
- researcher: web search, data gathering, analysis
- coder: writing code, debugging, testing
- browser: browser automation, web scraping
- devops: docker, git, deployment
- executor: terminal commands, file operations
- memory: storing/retrieving knowledge

Make tasks specific, actionable, and appropriately scoped.
Tasks should be parallelizable where possible.
Always include dependency chains correctly."""


class PlannerAgent(BaseAgent):
    name = "planner"
    description = "Breaks goals into structured task plans with dependencies"
    task_type = TaskType.PLANNING

    @property
    def system_prompt(self) -> str:
        return PLANNER_SYSTEM

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        """Create an execution plan for a goal"""

        # Enrich with memory context
        relevant_memories = []
        try:
            from omega.memory.store import memory
            relevant_memories = memory.recall(task, n=3)
        except Exception:
            pass

        memory_context = ""
        if relevant_memories:
            memory_context = "\n\nRelevant past context:\n" + "\n".join(
                f"- {m['text']}" for m in relevant_memories
            )

        messages = [
            {
                "role": "user",
                "content": f"""Create a detailed execution plan for this goal:

Goal: {task}
{memory_context}

Context: {json.dumps(context, indent=2) if context else 'None'}

Output only valid JSON."""
            }
        ]

        result = await self.think(messages)

        # Parse the JSON plan
        try:
            # Handle markdown code blocks
            plan_str = result.strip()
            if "```json" in plan_str:
                plan_str = plan_str.split("```json")[1].split("```")[0].strip()
            elif "```" in plan_str:
                plan_str = plan_str.split("```")[1].split("```")[0].strip()

            plan = json.loads(plan_str)
            return AgentResult(success=True, output=plan)
        except json.JSONDecodeError as e:
            logger.error("plan_parse_error", error=str(e), raw=result[:200])
            # Return a simple fallback plan
            fallback_plan = {
                "goal": task,
                "summary": f"Execute: {task}",
                "tasks": [
                    {
                        "id": "task_1",
                        "name": "Execute Goal",
                        "description": task,
                        "agent": "executor",
                        "depends_on": [],
                        "priority": 1,
                        "estimated_minutes": 10,
                        "tools_needed": [],
                        "success_criteria": "Task completed successfully",
                    }
                ],
                "risks": [],
                "estimated_total_minutes": 10,
            }
            return AgentResult(success=True, output=fallback_plan)

    async def replan(self, original_plan: Dict, failure: str, context: Dict) -> AgentResult:
        """Replan after a failure"""
        messages = [
            {
                "role": "user",
                "content": f"""The following plan failed:

Original Plan: {json.dumps(original_plan, indent=2)}

Failure: {failure}

Context: {json.dumps(context, indent=2)}

Please create a revised plan that addresses the failure.
Output only valid JSON in the same format."""
            }
        ]
        result = await self.think(messages)
        try:
            plan_str = result.strip()
            if "```json" in plan_str:
                plan_str = plan_str.split("```json")[1].split("```")[0].strip()
            plan = json.loads(plan_str)
            return AgentResult(success=True, output=plan)
        except Exception as e:
            return AgentResult(success=False, error=f"Replan failed: {e}")
