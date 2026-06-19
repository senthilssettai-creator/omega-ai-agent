"""OMEGA Multi-Tier Memory System

Implements:
- Short-term memory (session context)
- Long-term memory (SQLite)
- Semantic memory (ChromaDB vector store)
- Episodic memory (action history)
- Procedural memory (learned workflows)
- User memory (preferences)
"""

import json
import time
import uuid
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import sqlite3
import structlog

from omega.config import config

logger = structlog.get_logger(__name__)


class ShortTermMemory:
    """In-session conversation context"""

    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages
        self._messages: List[Dict] = []
        self._context: Dict[str, Any] = {}

    def add(self, role: str, content: str, metadata: Optional[Dict] = None):
        self._messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {},
        })
        if len(self._messages) > self.max_messages:
            # Keep system messages, trim oldest user/assistant
            system = [m for m in self._messages if m["role"] == "system"]
            non_system = [m for m in self._messages if m["role"] != "system"]
            self._messages = system + non_system[-self.max_messages:]

    def get_messages(self, include_metadata: bool = False) -> List[Dict]:
        if include_metadata:
            return self._messages.copy()
        return [{"role": m["role"], "content": m["content"]} for m in self._messages]

    def set_context(self, key: str, value: Any):
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def clear(self):
        self._messages.clear()
        self._context.clear()

    def summary(self) -> str:
        return f"{len(self._messages)} messages in context"


class LongTermMemory:
    """Persistent SQLite-backed memory"""

    def __init__(self):
        self.db_path = config.sqlite_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    key TEXT,
                    content TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    importance REAL DEFAULT 0.5,
                    access_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    input TEXT,
                    output TEXT,
                    success INTEGER DEFAULT 1,
                    duration_ms INTEGER,
                    agent TEXT,
                    metadata TEXT DEFAULT '{}',
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    steps TEXT NOT NULL,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    avg_duration_ms REAL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'active',
                    metadata TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    metadata TEXT DEFAULT '{}',
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
                CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
                CREATE INDEX IF NOT EXISTS idx_episodes_agent ON episodes(agent);
                CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp);
                CREATE INDEX IF NOT EXISTS idx_knowledge_entity ON knowledge_graph(entity_type, entity_id);
            """)

    def store(self, type_: str, content: Any, key: Optional[str] = None,
              importance: float = 0.5, metadata: Optional[Dict] = None,
              expires_at: Optional[float] = None) -> str:
        id_ = str(uuid.uuid4())
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO memories
                   (id, type, key, content, metadata, importance, created_at, updated_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id_, type_, key, json.dumps(content), json.dumps(metadata or {}),
                 importance, now, now, expires_at)
            )
        return id_

    def retrieve(self, type_: Optional[str] = None, key: Optional[str] = None,
                 limit: int = 10) -> List[Dict]:
        query = "SELECT * FROM memories WHERE (expires_at IS NULL OR expires_at > ?)"
        params: List[Any] = [time.time()]

        if type_:
            query += " AND type = ?"
            params.append(type_)
        if key:
            query += " AND key = ?"
            params.append(key)

        query += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["content"] = json.loads(d["content"])
                d["metadata"] = json.loads(d["metadata"])
                results.append(d)
                # Update access count
                conn.execute("UPDATE memories SET access_count = access_count + 1 WHERE id = ?", (d["id"],))
        return results

    def log_episode(self, action: str, input_: Any = None, output: Any = None,
                    success: bool = True, duration_ms: int = 0,
                    agent: str = "", metadata: Optional[Dict] = None) -> str:
        id_ = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO episodes (id, action, input, output, success, duration_ms, agent, metadata, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id_, action, json.dumps(input_), json.dumps(output),
                 1 if success else 0, duration_ms, agent,
                 json.dumps(metadata or {}), time.time())
            )
        return id_

    def get_episodes(self, agent: Optional[str] = None, limit: int = 20) -> List[Dict]:
        query = "SELECT * FROM episodes"
        params: List[Any] = []
        if agent:
            query += " WHERE agent = ?"
            params.append(agent)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def set_user_pref(self, key: str, value: Any):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time())
            )

    def get_user_pref(self, key: str, default: Any = None) -> Any:
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM user_profile WHERE key = ?", (key,)).fetchone()
        if row:
            return json.loads(row[0])
        return default

    def save_workflow(self, name: str, steps: List[Dict], description: str = "") -> str:
        id_ = str(uuid.uuid4())
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO workflows
                   (id, name, description, steps, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (id_, name, description, json.dumps(steps), now, now)
            )
        return id_

    def get_workflow(self, name: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE name = ?", (name,)).fetchone()
        if row:
            d = dict(row)
            d["steps"] = json.loads(d["steps"])
            return d
        return None

    def add_knowledge_edge(self, entity_type: str, entity_id: str, relation: str,
                            target_type: str, target_id: str, weight: float = 1.0):
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO knowledge_graph
                   (id, entity_type, entity_id, relation, target_type, target_id, weight, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)""",
                (str(uuid.uuid4()), entity_type, entity_id, relation,
                 target_type, target_id, weight, time.time())
            )

    def get_related(self, entity_type: str, entity_id: str) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_graph WHERE entity_type = ? AND entity_id = ? ORDER BY weight DESC",
                (entity_type, entity_id)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        with self._get_conn() as conn:
            return {
                "memories": conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                "episodes": conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0],
                "workflows": conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0],
                "knowledge_edges": conn.execute("SELECT COUNT(*) FROM knowledge_graph").fetchone()[0],
            }


class SemanticMemory:
    """Vector-based semantic search using ChromaDB"""

    def __init__(self):
        self._client = None
        self._collection = None
        self._initialized = False
        self._init_failed = False

    def _init(self):
        if self._initialized or self._init_failed:
            return
        try:
            import concurrent.futures
            import chromadb

            def _do_init():
                client = chromadb.PersistentClient(
                    path=str(config.memory_dir / "chroma")
                )
                collection = client.get_or_create_collection(
                    name="omega_memory",
                    metadata={"hnsw:space": "cosine"},
                )
                return client, collection

            # Bound init time so a restricted network (e.g. blocked huggingface.co
            # for the default embedding model download) can't stall every caller.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_do_init)
                self._client, self._collection = future.result(timeout=8)
            self._initialized = True
        except Exception as e:
            logger.warning("chromadb_unavailable", error=str(e))
            self._initialized = False
            self._init_failed = True

    def store(self, text: str, metadata: Optional[Dict] = None, id_: Optional[str] = None) -> Optional[str]:
        self._init()
        if not self._initialized:
            return None
        try:
            id_ = id_ or str(uuid.uuid4())
            self._collection.add(
                documents=[text],
                metadatas=[metadata or {}],
                ids=[id_],
            )
            return id_
        except Exception as e:
            logger.error("semantic_store_error", error=str(e))
            self._init_failed = True
            self._initialized = False
            return None

    def search(self, query: str, n_results: int = 5, where: Optional[Dict] = None) -> List[Dict]:
        self._init()
        if not self._initialized:
            return []
        try:
            kwargs: Dict[str, Any] = {"query_texts": [query], "n_results": n_results}
            if where:
                kwargs["where"] = where
            results = self._collection.query(**kwargs)
            items = []
            for i, doc in enumerate(results["documents"][0]):
                items.append({
                    "text": doc,
                    "metadata": results["metadatas"][0][i],
                    "id": results["ids"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                })
            return items
        except Exception as e:
            logger.error("semantic_search_error", error=str(e))
            self._init_failed = True
            self._initialized = False
            return []


class MemorySystem:
    """Unified memory interface"""

    def __init__(self):
        config.ensure_dirs()
        self.short_term = ShortTermMemory(config.max_short_term_messages)
        self.long_term = LongTermMemory()
        self.semantic = SemanticMemory()

    def remember(self, content: str, type_: str = "fact", key: Optional[str] = None,
                 importance: float = 0.5, metadata: Optional[Dict] = None):
        """Store something in both long-term and semantic memory"""
        id_ = self.long_term.store(type_, content, key=key, importance=importance, metadata=metadata)
        self.semantic.store(content, metadata={"type": type_, "key": key or "", "lt_id": id_})
        return id_

    def recall(self, query: str, n: int = 5) -> List[Dict]:
        """Semantically recall relevant memories"""
        return self.semantic.search(query, n_results=n)

    def chat(self, role: str, content: str):
        """Add to short-term conversation"""
        self.short_term.add(role, content)

    def get_context(self) -> List[Dict]:
        return self.short_term.get_messages()

    def log_action(self, action: str, input_: Any = None, output: Any = None,
                   success: bool = True, duration_ms: int = 0, agent: str = ""):
        self.long_term.log_episode(action, input_, output, success, duration_ms, agent)

    def stats(self) -> Dict:
        lt_stats = self.long_term.stats()
        return {
            "short_term_messages": len(self.short_term._messages),
            **lt_stats,
        }


# Global memory instance
memory = MemorySystem()
