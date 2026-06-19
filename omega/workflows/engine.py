"""OMEGA Workflow Engine - User-defined and scheduled workflows"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import structlog

from omega.config import config
from omega.memory.store import memory

logger = structlog.get_logger(__name__)


class WorkflowStep:
    """A single step in a workflow"""

    def __init__(self, name: str, agent: str, task: str,
                 depends_on: Optional[List[str]] = None,
                 config: Optional[Dict] = None):
        self.name = name
        self.agent = agent
        self.task = task
        self.depends_on = depends_on or []
        self.config = config or {}
        self.result: Optional[Any] = None
        self.status: str = "pending"


class Workflow:
    """A named, reusable workflow"""

    def __init__(self, name: str, description: str = "",
                 steps: Optional[List[Dict]] = None,
                 schedule: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self.steps = steps or []
        self.schedule = schedule  # cron-like string
        self.created_at = time.time()
        self.last_run: Optional[float] = None
        self.run_count: int = 0
        self.success_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "schedule": self.schedule,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "success_count": self.success_count,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Workflow":
        wf = cls(
            name=data["name"],
            description=data.get("description", ""),
            steps=data.get("steps", []),
            schedule=data.get("schedule"),
        )
        wf.id = data.get("id", wf.id)
        wf.created_at = data.get("created_at", wf.created_at)
        wf.last_run = data.get("last_run")
        wf.run_count = data.get("run_count", 0)
        wf.success_count = data.get("success_count", 0)
        return wf


class WorkflowEngine:
    """Executes and manages workflows"""

    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}
        self._workflows_dir = config.workflows_dir
        self._running: Dict[str, asyncio.Task] = {}
        self._scheduler_task: Optional[asyncio.Task] = None
        self._load_workflows()

    def _load_workflows(self):
        """Load workflows from disk"""
        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        for wf_file in self._workflows_dir.glob("*.json"):
            try:
                with open(wf_file) as f:
                    data = json.load(f)
                wf = Workflow.from_dict(data)
                self._workflows[wf.name] = wf
            except Exception as e:
                logger.warning("workflow_load_failed", file=str(wf_file), error=str(e))

    def _save_workflow(self, workflow: Workflow):
        """Persist a workflow to disk"""
        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        wf_file = self._workflows_dir / f"{workflow.name}.json"
        with open(wf_file, "w") as f:
            json.dump(workflow.to_dict(), f, indent=2)

    def create_workflow(self, name: str, steps: List[Dict],
                         description: str = "",
                         schedule: Optional[str] = None) -> Workflow:
        """Create and save a new workflow"""
        wf = Workflow(name=name, description=description, steps=steps, schedule=schedule)
        self._workflows[name] = wf
        self._save_workflow(wf)
        memory.long_term.save_workflow(name, steps, description)
        logger.info("workflow_created", name=name, steps=len(steps))
        return wf

    async def run(self, name: str, context: Optional[Dict] = None,
                  on_progress: Optional[Callable] = None) -> Dict:
        """Execute a workflow by name"""
        wf = self._workflows.get(name)
        if not wf:
            return {"success": False, "error": f"Workflow not found: {name}"}

        from omega.agents.orchestrator import Orchestrator
        orchestrator = Orchestrator()

        results = []
        context = context or {}
        start = time.time()

        logger.info("workflow_start", name=name)
        if on_progress:
            await on_progress("start", f"Starting workflow: {name}")

        for step_def in wf.steps:
            step = WorkflowStep(
                name=step_def.get("name", "step"),
                agent=step_def.get("agent", "executor"),
                task=step_def.get("task", ""),
                depends_on=step_def.get("depends_on", []),
                config=step_def.get("config", {}),
            )

            # Merge previous results into context
            step_context = {**context, "previous_results": results, **step.config}

            if on_progress:
                await on_progress("step", f"Running: {step.name}")

            agent = orchestrator.get_agent(step.agent)
            result = await agent.run(step.task, step_context)

            step.result = result.output if result else None
            step.status = "done" if (result and result.success) else "failed"

            results.append({
                "step": step.name,
                "agent": step.agent,
                "status": step.status,
                "output": str(step.result)[:500] if step.result else None,
            })

            if on_progress:
                await on_progress("step_done", f"{'✓' if step.status == 'done' else '✗'} {step.name}")

        duration = time.time() - start
        success = all(r["status"] == "done" for r in results)

        # Update workflow stats
        wf.last_run = time.time()
        wf.run_count += 1
        if success:
            wf.success_count += 1
        self._save_workflow(wf)

        logger.info("workflow_complete", name=name, success=success, duration=duration)
        return {
            "workflow": name,
            "success": success,
            "steps": results,
            "duration": duration,
        }

    async def run_from_nl(self, description: str,
                           on_progress: Optional[Callable] = None) -> Dict:
        """Create and run a workflow from natural language description"""
        from omega.models.router import router, TaskType

        messages = [
            {
                "role": "user",
                "content": f"""Convert this workflow description into executable steps:

{description}

Output JSON:
{{
  "name": "workflow_name",
  "description": "brief description",
  "steps": [
    {{
      "name": "step name",
      "agent": "researcher/coder/executor/browser/devops",
      "task": "specific task for this agent",
      "config": {{}}
    }}
  ]
}}"""
            }
        ]

        result = await router.complete(messages=messages, task_type=TaskType.PLANNING)
        content = result["content"].strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()

        try:
            wf_spec = json.loads(content)
        except Exception:
            return {"success": False, "error": "Could not parse workflow"}

        wf = self.create_workflow(
            name=wf_spec.get("name", "generated_workflow"),
            steps=wf_spec.get("steps", []),
            description=wf_spec.get("description", description),
        )

        return await self.run(wf.name, on_progress=on_progress)

    def list_workflows(self) -> List[Dict]:
        return [wf.to_dict() for wf in self._workflows.values()]

    def delete_workflow(self, name: str) -> bool:
        if name in self._workflows:
            wf_file = self._workflows_dir / f"{name}.json"
            if wf_file.exists():
                wf_file.unlink()
            del self._workflows[name]
            return True
        return False

    async def start_scheduler(self):
        """Start the workflow scheduler (runs scheduled workflows)"""
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def _scheduler_loop(self):
        """Background scheduler loop"""
        while True:
            try:
                now = datetime.now()
                for name, wf in self._workflows.items():
                    if wf.schedule and self._should_run(wf, now):
                        logger.info("scheduled_workflow_start", name=name)
                        asyncio.create_task(self.run(name))
            except Exception as e:
                logger.error("scheduler_error", error=str(e))
            await asyncio.sleep(60)  # Check every minute

    def _should_run(self, wf: Workflow, now: datetime) -> bool:
        """Simple schedule check (hourly/daily/weekly)"""
        if not wf.last_run:
            return True
        elapsed = time.time() - wf.last_run
        schedule = wf.schedule.lower()
        if "hourly" in schedule:
            return elapsed >= 3600
        if "daily" in schedule:
            return elapsed >= 86400
        if "weekly" in schedule:
            return elapsed >= 604800
        return False


# Global workflow engine
workflow_engine = WorkflowEngine()
