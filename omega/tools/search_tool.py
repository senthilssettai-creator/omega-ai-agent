"""Search Tool"""
import httpx
from typing import List, Dict
from omega.tools.registry import BaseTool, ToolResult


class SearchTool(BaseTool):
    name = "search"
    description = "Web search using DuckDuckGo"

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "search":
            return await self._search(**kwargs)
        return ToolResult(success=False, error=f"Unknown: {action}")

    async def _search(self, query: str, n: int = 5) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": "1"},
                    headers={"User-Agent": "OMEGA/1.0"},
                )
                data = r.json()
                results = []
                if data.get("AbstractText"):
                    results.append({"title": data.get("Heading"), "content": data["AbstractText"], "url": data.get("AbstractURL")})
                for t in data.get("RelatedTopics", [])[:n]:
                    if isinstance(t, dict) and t.get("Text"):
                        results.append({"title": t["Text"][:80], "content": t["Text"], "url": t.get("FirstURL")})
                return ToolResult(success=True, output=results)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
