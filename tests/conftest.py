"""Shared pytest fixtures for OMEGA tests"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-pytest")

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_home(monkeypatch, tmp_path):
    """Provide an isolated OMEGA home directory for tests"""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def mock_router_response():
    """Factory for creating mock LLM responses"""
    def _make(content: str, model: str = "test-model"):
        return {
            "content": content,
            "model": model,
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            "task_type": None,
        }
    return _make
