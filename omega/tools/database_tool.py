"""Database Tool - SQLite and DuckDB"""
import json
import sqlite3
from typing import List, Dict, Any, Optional
from omega.tools.registry import BaseTool, ToolResult


class DatabaseTool(BaseTool):
    name = "database"
    description = "Query and manage SQLite and DuckDB databases"

    async def execute(self, action: str, **kwargs) -> ToolResult:
        db_type = kwargs.get("type", "sqlite")
        path = kwargs.get("path", ":memory:")

        try:
            if db_type == "sqlite":
                return await self._sqlite(action, path, **kwargs)
            elif db_type == "duckdb":
                return await self._duckdb(action, path, **kwargs)
            else:
                return ToolResult(success=False, error=f"Unknown db type: {db_type}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _sqlite(self, action: str, path: str, **kwargs) -> ToolResult:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            if action == "query":
                cursor = conn.execute(kwargs["sql"], kwargs.get("params", []))
                rows = [dict(r) for r in cursor.fetchall()]
                return ToolResult(success=True, output=rows)
            elif action == "execute":
                conn.execute(kwargs["sql"], kwargs.get("params", []))
                conn.commit()
                return ToolResult(success=True, output="OK")
            elif action == "schema":
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                schema = {}
                for (table,) in tables:
                    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
                    schema[table] = [dict(c) for c in cols]
                return ToolResult(success=True, output=schema)
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        finally:
            conn.close()

    async def _duckdb(self, action: str, path: str, **kwargs) -> ToolResult:
        try:
            import duckdb
            conn = duckdb.connect(path)
            if action in ("query", "execute"):
                result = conn.execute(kwargs["sql"], kwargs.get("params", [])).fetchdf()
                return ToolResult(success=True, output=result.to_dict(orient="records"))
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except ImportError:
            return ToolResult(success=False, error="duckdb not installed")
