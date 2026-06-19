"""Tests for omega.memory.store"""

import pytest
from omega.memory.store import LongTermMemory, ShortTermMemory


class TestShortTermMemory:
    def test_add_and_retrieve_messages(self):
        stm = ShortTermMemory(max_messages=10)
        stm.add("user", "hello")
        stm.add("assistant", "hi there")
        messages = stm.get_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"

    def test_trims_to_max_messages_keeping_system(self):
        stm = ShortTermMemory(max_messages=3)
        stm.add("system", "you are a bot")
        for i in range(10):
            stm.add("user", f"message {i}")
        messages = stm.get_messages()
        # system message preserved + most recent non-system messages
        assert any(m["role"] == "system" for m in messages)
        assert len(messages) <= 4  # system + max_messages

    def test_context_storage(self):
        stm = ShortTermMemory()
        stm.set_context("project_path", "/home/user/app")
        assert stm.get_context("project_path") == "/home/user/app"
        assert stm.get_context("missing_key", "default") == "default"

    def test_clear(self):
        stm = ShortTermMemory()
        stm.add("user", "test")
        stm.set_context("key", "value")
        stm.clear()
        assert len(stm.get_messages()) == 0
        assert stm.get_context("key") is None


class TestLongTermMemory:
    @pytest.fixture
    def ltm(self, tmp_path, monkeypatch):
        from omega.config import config
        monkeypatch.setattr(config, "sqlite_path", str(tmp_path / "test.db"))
        return LongTermMemory()

    def test_store_and_retrieve(self, ltm):
        ltm.store("fact", "The sky is blue", key="sky_color", importance=0.7)
        results = ltm.retrieve(type_="fact")
        assert len(results) == 1
        assert results[0]["content"] == "The sky is blue"

    def test_retrieve_by_key(self, ltm):
        ltm.store("fact", "fact A", key="key_a")
        ltm.store("fact", "fact B", key="key_b")
        results = ltm.retrieve(key="key_a")
        assert len(results) == 1
        assert results[0]["content"] == "fact A"

    def test_importance_ordering(self, ltm):
        ltm.store("fact", "low importance", importance=0.1)
        ltm.store("fact", "high importance", importance=0.9)
        results = ltm.retrieve(type_="fact", limit=10)
        assert results[0]["content"] == "high importance"

    def test_log_and_get_episodes(self, ltm):
        ltm.log_episode("test_action", input_={"x": 1}, output={"y": 2},
                        success=True, duration_ms=150, agent="test_agent")
        episodes = ltm.get_episodes(agent="test_agent")
        assert len(episodes) == 1
        assert episodes[0]["action"] == "test_action"
        assert episodes[0]["success"] == 1

    def test_user_preferences(self, ltm):
        ltm.set_user_pref("theme", "dark")
        assert ltm.get_user_pref("theme") == "dark"
        assert ltm.get_user_pref("nonexistent", "fallback") == "fallback"

    def test_workflow_save_and_get(self, ltm):
        steps = [{"name": "step1", "agent": "researcher", "task": "do research"}]
        ltm.save_workflow("my_workflow", steps, "test workflow")
        wf = ltm.get_workflow("my_workflow")
        assert wf is not None
        assert wf["name"] == "my_workflow"
        assert len(wf["steps"]) == 1

    def test_workflow_not_found_returns_none(self, ltm):
        assert ltm.get_workflow("nonexistent_workflow") is None

    def test_knowledge_graph(self, ltm):
        ltm.add_knowledge_edge("project", "omega", "uses", "language", "python")
        related = ltm.get_related("project", "omega")
        assert len(related) == 1
        assert related[0]["relation"] == "uses"

    def test_stats(self, ltm):
        ltm.store("fact", "test fact")
        ltm.log_episode("action", agent="test")
        stats = ltm.stats()
        assert stats["memories"] == 1
        assert stats["episodes"] == 1

    def test_expired_memories_not_retrieved(self, ltm):
        import time
        ltm.store("fact", "expired fact", expires_at=time.time() - 100)
        ltm.store("fact", "valid fact", expires_at=time.time() + 1000)
        results = ltm.retrieve(type_="fact")
        contents = [r["content"] for r in results]
        assert "expired fact" not in contents
        assert "valid fact" in contents
