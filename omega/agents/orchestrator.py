"""OMEGA Agent Orchestrator - Multi-agent coordination and execution"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import structlog

from omega.agents.base import AgentResult
from omega.config import config

logger = structlog.get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


@dataclass
class Task:
    id: str
    name: str
    description: str
    agent_name: str
    depends_on: List[str] = field(default_factory=list)
    priority: int = 1
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[AgentResult] = None
    context: Dict = field(default_factory=dict)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    retries: int = 0
    max_retries: int = 2


class Orchestrator:
    """Coordinates multiple agents to execute complex plans"""

    def __init__(self, progress_callback: Optional[Callable] = None):
        self._agents: Dict[str, Any] = {}
        self._tasks: Dict[str, Task] = {}
        self._progress_callback = progress_callback
        self._running = False
        self._session_id = str(uuid.uuid4())

    def _load_agents(self):
        """Lazy-load all agents"""
        if self._agents:
            return

        from omega.agents.planner import PlannerAgent
        from omega.agents.researcher import ResearchAgent
        from omega.agents.coder import CoderAgent
        from omega.agents.executor import ExecutorAgent
        from omega.agents.browser import BrowserAgent
        from omega.agents.devops import DevOpsAgent
        from omega.agents.critic import CriticAgent
        from omega.agents.mcp import MCPAgent

        self._agents = {
            "planner": PlannerAgent(),
            "researcher": ResearchAgent(),
            "coder": CoderAgent(),
            "executor": ExecutorAgent(),
            "browser": BrowserAgent(),
            "devops": DevOpsAgent(),
            "critic": CriticAgent(),
            "mcp": MCPAgent(),
        }

    def get_agent(self, name: str):
        self._load_agents()
        return self._agents.get(name, self._agents["executor"])

    async def execute_goal(self, goal: str, context: Optional[Dict] = None,
                           on_progress=None) -> Dict:
        """Execute a high-level goal through full agent pipeline"""
        self._load_agents()
        context = context or {}
        session_result = {
            "goal": goal,
            "session_id": self._session_id,
            "started_at": time.time(),
            "tasks": [],
            "success": False,
        }

        # Step 1: Plan
        if on_progress:
            await on_progress("planning", f"Creating execution plan for: {goal}")

        planner = self.get_agent("planner")
        plan_result = await planner.run(goal, context)

        if not plan_result.success:
            session_result["error"] = plan_result.error
            return session_result

        plan = plan_result.output
        session_result["plan"] = plan

        if on_progress:
            tasks = plan.get("tasks", [])
            await on_progress("planned", f"Plan created: {len(tasks)} tasks")

        # Step 2: Convert plan tasks to Task objects
        for task_spec in plan.get("tasks", []):
            task = Task(
                id=task_spec["id"],
                name=task_spec["name"],
                description=task_spec["description"],
                agent_name=task_spec.get("agent", "executor"),
                depends_on=task_spec.get("depends_on", []),
                priority=task_spec.get("priority", 1),
                context={**context, "goal": goal, "plan": plan},
            )
            self._tasks[task.id] = task

        # Step 3: Execute tasks respecting dependencies
        results = await self._execute_task_graph(on_progress)
        session_result["tasks"] = [
            {
                "id": t.id,
                "name": t.name,
                "agent": t.agent_name,
                "status": t.status.value,
                "result": str(t.result.output)[:500] if t.result else None,
                "duration": (t.finished_at - t.started_at) if t.started_at and t.finished_at else None,
            }
            for t in self._tasks.values()
        ]

        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.DONE)
        total = len(self._tasks)
        session_result["success"] = completed >= total * 0.8  # 80% success threshold
        session_result["completed_tasks"] = completed
        session_result["total_tasks"] = total
        session_result["finished_at"] = time.time()
        session_result["duration"] = session_result["finished_at"] - session_result["started_at"]

        return session_result

    async def _execute_task_graph(self, on_progress=None) -> List[AgentResult]:
        """Execute tasks in dependency order with parallel execution"""
        results = []
        max_iterations = len(self._tasks) * 2

        for _ in range(max_iterations):
            # Find ready tasks (deps completed, status pending)
            ready = [
                t for t in self._tasks.values()
                if t.status == TaskStatus.PENDING
                and all(
                    self._tasks.get(dep_id, Task(id=dep_id, name="", description="", agent_name="executor")).status == TaskStatus.DONE
                    for dep_id in t.depends_on
                )
            ]

            if not ready:
                # Check if all done
                pending = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
                if not pending:
                    break
                # Stuck in dependency deadlock - fail remaining
                for t in pending:
                    t.status = TaskStatus.FAILED
                break

            # Sort by priority and execute up to max_parallel
            ready.sort(key=lambda t: t.priority)
            batch = ready[:config.max_parallel_agents]

            # Execute batch in parallel
            coros = [self._execute_task(task, on_progress) for task in batch]
            batch_results = await asyncio.gather(*coros, return_exceptions=True)

            for result in batch_results:
                if not isinstance(result, Exception):
                    results.append(result)

        return results

    async def _execute_task(self, task: Task, on_progress=None) -> Optional[AgentResult]:
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        if on_progress:
            await on_progress("executing", f"[{task.agent_name}] {task.name}")

        agent = self.get_agent(task.agent_name)

        try:
            result = await asyncio.wait_for(
                agent.run(task.description, task.context),
                timeout=config.agent_timeout_seconds,
            )
            task.result = result
            task.status = TaskStatus.DONE if result.success else TaskStatus.FAILED
            task.finished_at = time.time()

            if on_progress:
                status_str = "✓" if result.success else "✗"
                await on_progress(
                    "task_done",
                    f"{status_str} {task.name} ({int(task.finished_at - task.started_at)}s)"
                )

            return result

        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.finished_at = time.time()
            task.result = AgentResult(success=False, error=f"Task timed out after {config.agent_timeout_seconds}s")
            if on_progress:
                await on_progress("task_timeout", f"⏱ {task.name} timed out")
            return task.result

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.finished_at = time.time()
            task.result = AgentResult(success=False, error=str(e))
            logger.error("task_execution_error", task=task.name, error=str(e))
            return task.result

    def status_summary(self) -> Dict:
        """Get current execution status"""
        statuses = {}
        for status in TaskStatus:
            statuses[status.value] = sum(1 for t in self._tasks.values() if t.status == status)
        return {
            "session_id": self._session_id,
            "task_counts": statuses,
            "agents": {name: agent.to_dict() for name, agent in self._agents.items()},
        }
