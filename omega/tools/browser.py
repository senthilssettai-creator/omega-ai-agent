"""Browser Tool - Playwright-based web browser automation"""
from typing import Optional
from omega.tools.registry import BaseTool, ToolResult
from omega.config import config


class BrowserTool(BaseTool):
    name = "browser"
    description = "Navigate websites, extract content, fill forms"

    def __init__(self):
        super().__init__()
        self._browser = None
        self._page = None
        self._pw = None

    async def setup(self) -> bool:
        return True  # Lazy init

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=config.browser_headless)
        if self._page is None or self._page.is_closed():
            ctx = await self._browser.new_context()
            self._page = await ctx.new_page()
        return self._page

    async def execute(self, action: str, **kwargs) -> ToolResult:
        try:
            page = await self._ensure_browser()
            if action == "navigate":
                await page.goto(kwargs["url"], timeout=config.browser_timeout)
                return ToolResult(success=True, output=page.url)
            elif action == "get_text":
                url = kwargs.get("url")
                if url:
                    await page.goto(url, timeout=config.browser_timeout)
                text = await page.inner_text("body")
                return ToolResult(success=True, output=text[:8000])
            elif action == "click":
                sel = kwargs.get("selector") or f"text={kwargs.get('text', '')}"
                await page.click(sel, timeout=10000)
                return ToolResult(success=True, output="clicked")
            elif action == "type":
                await page.fill(kwargs["selector"], kwargs["text"])
                return ToolResult(success=True, output="typed")
            elif action == "screenshot":
                path = kwargs.get("path", str(config.omega_home / "screenshot.png"))
                await page.screenshot(path=path)
                return ToolResult(success=True, output=path)
            elif action == "evaluate":
                result = await page.evaluate(kwargs["script"])
                return ToolResult(success=True, output=result)
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def get_text(self, url: str) -> str:
        """Convenience: get text from URL"""
        result = await self.execute("get_text", url=url)
        return result.output if result.success else f"Error: {result.error}"

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
