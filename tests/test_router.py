"""Tests for omega.models.router"""

import pytest
from omega.models.router import ModelRouter, TaskType


class TestTaskInference:
    """Verify task type inference uses word-boundary matching, not naive substrings"""

    def setup_method(self):
        self.router = ModelRouter()

    def test_coding_task_detected(self):
        msgs = [{"role": "user", "content": "write a python function to sort a list"}]
        assert self.router.infer_task_type(msgs) == TaskType.CODING

    def test_research_task_detected(self):
        msgs = [{"role": "user", "content": "research the latest AI trends"}]
        assert self.router.infer_task_type(msgs) == TaskType.RESEARCH

    def test_latest_does_not_false_positive_as_coding(self):
        """Regression test: 'latest' contains substring 'test' but is not a coding task"""
        msgs = [{"role": "user", "content": "what are the latest news headlines today"}]
        assert self.router.infer_task_type(msgs) != TaskType.CODING

    def test_planning_task_detected(self):
        msgs = [{"role": "user", "content": "create a project plan with steps"}]
        assert self.router.infer_task_type(msgs) == TaskType.PLANNING

    def test_reasoning_task_detected(self):
        msgs = [{"role": "user", "content": "why does this happen, explain the reasoning"}]
        assert self.router.infer_task_type(msgs) == TaskType.REASONING

    def test_vision_task_detected(self):
        msgs = [{"role": "user", "content": "analyze this screenshot of the dashboard"}]
        # contains both "analyze" (research) and "screenshot" (vision) - research checked first
        result = self.router.infer_task_type(msgs)
        assert result in (TaskType.RESEARCH, TaskType.VISION)

    def test_default_general(self):
        msgs = [{"role": "user", "content": "hello how are you"}]
        assert self.router.infer_task_type(msgs) == TaskType.GENERAL


class TestModelSelection:
    def setup_method(self):
        self.router = ModelRouter()

    def test_select_coding_model(self):
        model = self.router.select_model(TaskType.CODING)
        assert model == self.router.models["coding"]

    def test_long_context_overrides_task_type(self):
        model = self.router.select_model(TaskType.GENERAL, context_length=100_000)
        assert model == self.router.models["long_context"]

    def test_unhealthy_model_falls_back(self):
        model_name = self.router.models["coding"]
        self.router._model_health[model_name] = False
        model = self.router.select_model(TaskType.CODING)
        assert model == self.router.fallback
