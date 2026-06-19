"""Tests for omega.agents.orchestrator"""

import json
import pytest

from omega.agents.orchestrator import Orchestrator, Task, TaskStatus


def make_fake_complete(plan_tasks, on_task_run=None):
    """Build a fake router.complete that returns a plan, then generic task responses"""
    async def fake_complete(messages, system=None, task_type=None, model=None,
                             max_tokens=4096, temperature=0.7, stream=False):
        content = messages[-1]["content"] if messages else ""
        if "Create a detailed execution plan" in content:
            return {
                "content": json.dumps({
                    "goal": "test", "summary": "s",
                    "tasks": plan_tasks,
                    "risks": [], "estimated_total_minutes": len(plan_tasks),
                }),
                "model": "fake", "usage": {}, "task_type": task_type,
            }
        if on_task_run:
            on_task_run(content)
        return {
            "content": json.dumps({"approach": "done", "commands": [], "file_operations": []}),
            "model": "fake", "usage": {}, "task_type": task_type,
        }
    return fake_complete


class TestOrchestratorTaskGraph:
    @pytest.mark.asyncio
    async def test_parallel_independent_tasks_both_complete(self, monkeypatch):
        from omega.models import router as router_module

        tasks = [
            {"id": "t1", "name": "A", "description": "task a", "agent": "executor",
             "depends_on": [], "priority": 1, "estimated_minutes": 1, "tools_needed": [], "success_criteria": "x"},
            {"id": "t2", "name": "B", "description": "task b", "agent": "executor",
             "depends_on": [], "priority": 1, "estimated_minutes": 1, "tools_needed": [], "success_criteria": "x"},
        ]
        monkeypatch.setattr(router_module.router, "complete", make_fake_complete(tasks))

        orch = Orchestrator()
        result = await orch.execute_goal("test goal")

        assert result["success"] is True
        assert result["completed_tasks"] == 2
        assert result["total_tasks"] == 2

    @pytest.mark.asyncio
    async def test_dependent_task_waits_for_dependency(self, monkeypatch):
        from omega.models import router as router_module

        run_order = []

        def track(content):
            # The executor's prompt starts with "Task: <description>" on its own line;
            # match against that specific line rather than the full context blob (which
            # includes the whole original plan, so naive substring checks would false-positive).
            first_line = content.splitlines()[0] if content else ""
            if first_line == "Task: do step 1":
                run_order.append("t1")
            elif first_line == "Task: do step 2":
                run_order.append("t2")

        tasks = [
            {"id": "t1", "name": "Step1", "description": "do step 1", "agent": "executor",
             "depends_on": [], "priority": 1, "estimated_minutes": 1, "tools_needed": [], "success_criteria": "x"},
            {"id": "t2", "name": "Step2", "description": "do step 2", "agent": "executor",
             "depends_on": ["t1"], "priority": 2, "estimated_minutes": 1, "tools_needed": [], "success_criteria": "x"},
        ]
        monkeypatch.setattr(router_module.router, "complete", make_fake_complete(tasks, on_task_run=track))

        orch = Orchestrator()
        result = await orch.execute_goal("test goal")

        assert result["success"] is True
        assert run_order == ["t1", "t2"]  # t1 must run before t2

    @pytest.mark.asyncio
    async def test_failed_dependency_blocks_dependent_task(self, monkeypatch):
        from omega.models import router as router_module

        async def fake_complete(messages, system=None, task_type=None, model=None,
                                 max_tokens=4096, temperature=0.7, stream=False):
            content = messages[-1]["content"] if messages else ""
            if "Create a detailed execution plan" in content:
                return {
                    "content": json.dumps({
                        "goal": "test", "summary": "s",
                        "tasks": [
                            {"id": "t1", "name": "WillFail", "description": "FAIL_MARKER",
                             "agent": "executor", "depends_on": [], "priority": 1,
                             "estimated_minutes": 1, "tools_needed": [], "success_criteria": "x"},
                            {"id": "t2", "name": "Blocked", "description": "do step 2",
                             "agent": "executor", "depends_on": ["t1"], "priority": 2,
                             "estimated_minutes": 1, "tools_needed": [], "success_criteria": "x"},
                        ],
                        "risks": [], "estimated_total_minutes": 2,
                    }),
                    "model": "fake", "usage": {}, "task_type": task_type,
                }
            if "FAIL_MARKER" in content:
                raise RuntimeError("Simulated failure")
            return {
                "content": json.dumps({"approach": "done", "commands": [], "file_operations": []}),
                "model": "fake", "usage": {}, "task_type": task_type,
            }

        monkeypatch.setattr(router_module.router, "complete", fake_complete)

        orch = Orchestrator()
        result = await orch.execute_goal("test goal")

        assert result["success"] is False
        statuses = {t["name"]: t["status"] for t in result["tasks"]}
        assert statuses["WillFail"] == "failed"
        assert statuses["Blocked"] == "failed"  # deadlocked, never became ready

    @pytest.mark.asyncio
    async def test_planning_failure_returns_error(self, monkeypatch):
        from omega.models import router as router_module

        async def failing_plan(messages, system=None, task_type=None, model=None,
                                max_tokens=4096, temperature=0.7, stream=False):
            return {"content": "not valid json at all {{{", "model": "fake", "usage": {}, "task_type": task_type}

        monkeypatch.setattr(router_module.router, "complete", failing_plan)

        orch = Orchestrator()
        result = await orch.execute_goal("test goal")

        # Planner has a fallback plan for unparseable JSON, so this should still produce
        # a minimal single-task plan rather than crash
        assert "plan" in result
        assert result["plan"]["tasks"][0]["name"] == "Execute Goal"
