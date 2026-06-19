"""Research Agent - Web search, analysis, and report generation"""

import json
import asyncio
from typing import Any, Dict, List, Optional
import structlog
import httpx

from omega.agents.base import BaseAgent, AgentResult
from omega.models.router import TaskType

logger = structlog.get_logger(__name__)


class ResearchAgent(BaseAgent):
    name = "researcher"
    description = "Searches the web, analyzes sources, and builds comprehensive research reports"
    task_type = TaskType.RESEARCH

    @property
    def system_prompt(self) -> str:
        return """You are the Research Agent for OMEGA.

Your capabilities:
- Search the web for information
- Analyze and compare sources
- Synthesize findings into clear reports
- Identify key facts, trends, and insights
- Cite sources accurately

When researching:
1. Break down the topic into specific search queries
2. Search multiple angles
3. Synthesize findings coherently
4. Note confidence level and source quality
5. Flag conflicting information

Output research as structured markdown reports."""

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        """Execute a research task"""

        # Generate search strategy
        strategy_messages = [
            {
                "role": "user",
                "content": f"""I need to research: {task}

Generate a search strategy with 3-5 specific search queries.
Output as JSON: {{"queries": ["query1", "query2", ...], "focus_areas": ["area1", "area2"]}}"""
            }
        ]

        strategy_result = await self.think(strategy_messages)

        try:
            strategy_str = strategy_result.strip()
            if "```json" in strategy_str:
                strategy_str = strategy_str.split("```json")[1].split("```")[0].strip()
            strategy = json.loads(strategy_str)
            queries = strategy.get("queries", [task])
        except Exception:
            queries = [task]

        # Perform searches
        search_results = []
        for query in queries[:5]:
            results = await self._web_search(query)
            if results:
                search_results.append({
                    "query": query,
                    "results": results,
                })

        # Synthesize findings
        synthesis_messages = [
            {
                "role": "user",
                "content": f"""Research task: {task}

Search results:
{json.dumps(search_results, indent=2)}

Please synthesize these findings into a comprehensive research report.
Include:
- Executive Summary
- Key Findings
- Detailed Analysis
- Sources & Confidence
- Recommendations (if applicable)

Format as clean markdown."""
            }
        ]

        report = await self.think(synthesis_messages)

        # Store in memory
        try:
            from omega.memory.store import memory
            memory.remember(
                content=f"Research on '{task}': {report[:500]}",
                type_="research",
                key=task[:100],
                importance=0.7,
                metadata={"task": task, "queries": queries},
            )
        except Exception:
            pass

        return AgentResult(
            success=True,
            output={
                "report": report,
                "queries": queries,
                "sources_count": sum(len(r["results"]) for r in search_results),
            }
        )

    async def _web_search(self, query: str) -> List[Dict]:
        """Perform a web search using DuckDuckGo (no API key needed)"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Use DuckDuckGo Instant Answer API (free, no auth)
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_redirect": "1",
                        "no_html": "1",
                    },
                    headers={"User-Agent": "OMEGA-Agent/1.0"},
                )
                if response.status_code == 200:
                    data = response.json()
                    results = []

                    # Abstract
                    if data.get("AbstractText"):
                        results.append({
                            "title": data.get("Heading", ""),
                            "content": data["AbstractText"],
                            "url": data.get("AbstractURL", ""),
                            "type": "abstract",
                        })

                    # Related topics
                    for topic in data.get("RelatedTopics", [])[:3]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append({
                                "title": topic.get("Text", "")[:100],
                                "content": topic.get("Text", ""),
                                "url": topic.get("FirstURL", ""),
                                "type": "related",
                            })

                    return results
        except Exception as e:
            logger.warning("web_search_error", query=query, error=str(e))

        # Fallback: return empty and let LLM use its knowledge
        return []

    async def analyze_url(self, url: str) -> str:
        """Fetch and analyze a URL"""
        try:
            from omega.tools.browser import BrowserTool
            browser = BrowserTool()
            content = await browser.get_text(url)
            return content[:5000]
        except Exception:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, headers={"User-Agent": "OMEGA-Agent/1.0"})
                    return response.text[:5000]
            except Exception as e:
                return f"Could not fetch {url}: {e}"
