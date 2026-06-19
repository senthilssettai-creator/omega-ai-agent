"""Browser Agent - Full browser automation via Playwright"""

import json
import asyncio
import base64
from typing import Any, Dict, List, Optional
from pathlib import Path
import structlog

from omega.agents.base import BaseAgent, AgentResult
from omega.models.router import TaskType
from omega.config import config

logger = structlog.get_logger(__name__)


class BrowserAgent(BaseAgent):
    name = "browser"
    description = "Automates browser interactions, web scraping, form filling, and web app usage"
    task_type = TaskType.GENERAL

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._browser = None
        self._page = None
        self._playwright = None

    @property
    def system_prompt(self) -> str:
        return """You are the Browser Agent for OMEGA.

You control a web browser to:
- Navigate websites
- Login to services
- Fill and submit forms
- Extract information
- Download and upload files
- Interact with web apps

Given a task, determine the sequence of browser actions needed.
Output JSON with the action sequence.

Available actions:
- navigate: go to URL
- click: click element (css selector or text)
- type: type text into input
- extract: get text/data from page
- screenshot: take screenshot
- wait: wait for element or time
- scroll: scroll page
- hover: hover over element
- select: select dropdown option
- check: check checkbox
- upload: upload file
- download: trigger download"""

    async def _get_browser(self):
        """Get or create browser instance"""
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=config.browser_headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )

        if self._page is None or self._page.is_closed():
            context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            self._page = await context.new_page()

        return self._page

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        """Execute a browser automation task"""
        messages = [
            {
                "role": "user",
                "content": f"""Browser automation task: {task}

Current URL: {context.get('url', 'none')}
Context: {json.dumps(context, indent=2) if context else 'None'}

Create a sequence of browser actions to complete this task.
Output JSON:
{{
  "actions": [
    {{"type": "navigate", "url": "https://..."}},
    {{"type": "click", "selector": "css selector or text", "text": "optional button text"}},
    {{"type": "type", "selector": "input selector", "text": "text to type"}},
    {{"type": "extract", "selector": "selector", "attribute": "text/href/src"}},
    {{"type": "wait", "selector": "optional selector", "ms": 1000}},
    {{"type": "screenshot"}}
  ],
  "goal": "what we're trying to achieve"
}}"""
            }
        ]

        plan_result = await self.think(messages)

        try:
            plan_str = plan_result.strip()
            if "```json" in plan_str:
                plan_str = plan_str.split("```json")[1].split("```")[0].strip()
            plan = json.loads(plan_str)
        except Exception:
            return AgentResult(success=False, error="Could not parse browser action plan")

        # Execute browser actions
        try:
            page = await self._get_browser()
            results = []
            extracted_data = {}

            for action in plan.get("actions", []):
                action_type = action.get("type", "")

                try:
                    if action_type == "navigate":
                        await page.goto(action["url"], timeout=config.browser_timeout)
                        results.append({"action": "navigate", "url": action["url"], "success": True})

                    elif action_type == "click":
                        if action.get("text"):
                            await page.click(f"text={action['text']}", timeout=10000)
                        else:
                            await page.click(action.get("selector", ""), timeout=10000)
                        results.append({"action": "click", "success": True})

                    elif action_type == "type":
                        await page.fill(action.get("selector", ""), action.get("text", ""))
                        results.append({"action": "type", "success": True})

                    elif action_type == "extract":
                        selector = action.get("selector", "body")
                        attribute = action.get("attribute", "text")
                        if attribute == "text":
                            elements = await page.query_selector_all(selector)
                            texts = [await el.inner_text() for el in elements[:10]]
                            extracted_data[selector] = texts
                        else:
                            elements = await page.query_selector_all(selector)
                            attrs = [await el.get_attribute(attribute) for el in elements[:10]]
                            extracted_data[selector] = attrs
                        results.append({"action": "extract", "data": extracted_data, "success": True})

                    elif action_type == "screenshot":
                        screenshot_path = str(config.omega_home / "screenshot.png")
                        await page.screenshot(path=screenshot_path)
                        results.append({"action": "screenshot", "path": screenshot_path, "success": True})

                    elif action_type == "wait":
                        if action.get("selector"):
                            await page.wait_for_selector(action["selector"], timeout=action.get("ms", 5000))
                        else:
                            await asyncio.sleep(action.get("ms", 1000) / 1000)
                        results.append({"action": "wait", "success": True})

                    elif action_type == "scroll":
                        await page.evaluate("window.scrollBy(0, 500)")
                        results.append({"action": "scroll", "success": True})

                    elif action_type == "select":
                        await page.select_option(action.get("selector", ""), action.get("value", ""))
                        results.append({"action": "select", "success": True})

                except Exception as e:
                    results.append({"action": action_type, "success": False, "error": str(e)})
                    logger.warning("browser_action_failed", action=action_type, error=str(e))

            # Get final page content for context
            try:
                current_url = page.url
                page_title = await page.title()
            except Exception:
                current_url = ""
                page_title = ""

            return AgentResult(
                success=True,
                output={
                    "actions_executed": results,
                    "extracted_data": extracted_data,
                    "final_url": current_url,
                    "page_title": page_title,
                }
            )

        except Exception as e:
            logger.error("browser_execute_error", error=str(e))
            return AgentResult(success=False, error=str(e))

    async def get_text(self, url: str) -> str:
        """Simple URL text extraction"""
        try:
            page = await self._get_browser()
            await page.goto(url, timeout=config.browser_timeout)
            content = await page.inner_text("body")
            return content[:10000]
        except Exception as e:
            return f"Error fetching {url}: {e}"

    async def close(self):
        """Close browser"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._page = None
