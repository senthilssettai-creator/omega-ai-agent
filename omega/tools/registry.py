"""OMEGA Plugin/Tool System - Dynamic loading of tools and plugins"""

import importlib
import importlib.util
import inspect
import json
import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type
import structlog

from omega.config import config

logger = structlog.get_logger(__name__)


class ToolResult:
    """Result from a tool execution"""
    def __init__(self, success: bool, output: Any = None, error: Optional[str] = None):
        self.success = success
        self.output = output
        self.error = error

    def __str__(self):
        return str(self.output) if self.success else f"Error: {self.error}"


class BaseTool(ABC):
    """Base class for all OMEGA tools/plugins"""
    name: str = "base"
    description: str = "Base tool"
    version: str = "1.0.0"
    requires: List[str] = []  # pip packages required

    def __init__(self):
        self._initialized = False

    async def setup(self) -> bool:
        """Initialize the tool - install deps, set up connections, etc."""
        self._initialized = True
        return True

    @abstractmethod
    async def execute(self, action: str, **kwargs) -> ToolResult:
        """Execute a tool action"""
        ...

    def get_schema(self) -> Dict:
        """Return the tool's action schema for LLM function calling"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "actions": self._get_actions(),
        }

    def _get_actions(self) -> List[Dict]:
        """Introspect available actions from methods"""
        actions = []
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if name.startswith("action_"):
                action_name = name[7:]  # Remove "action_" prefix
                doc = inspect.getdoc(method) or ""
                sig = inspect.signature(method)
                params = {
                    k: str(v.annotation) for k, v in sig.parameters.items()
                    if k != "self"
                }
                actions.append({
                    "name": action_name,
                    "description": doc,
                    "parameters": params,
                })
        return actions


class ToolRegistry:
    """Central registry for all OMEGA tools"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._loaded = False

    def register(self, tool: BaseTool):
        """Register a tool"""
        self._tools[tool.name] = tool
        logger.info("tool_registered", tool=tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict]:
        return [t.get_schema() for t in self._tools.values()]

    async def load_builtin_tools(self):
        """Load all built-in tools"""
        from omega.tools.filesystem import FilesystemTool
        from omega.tools.terminal import TerminalTool
        from omega.tools.git_tool import GitTool
        from omega.tools.search_tool import SearchTool
        from omega.tools.browser import BrowserTool
        from omega.tools.docker_tool import DockerTool
        from omega.tools.api_tool import ApiTool
        from omega.tools.database_tool import DatabaseTool

        builtin_tools = [
            FilesystemTool(),
            TerminalTool(),
            GitTool(),
            SearchTool(),
            BrowserTool(),
            DockerTool(),
            ApiTool(),
            DatabaseTool(),
        ]

        for tool in builtin_tools:
            try:
                await tool.setup()
                self.register(tool)
            except Exception as e:
                logger.warning("tool_setup_failed", tool=tool.name, error=str(e))

        self._loaded = True

    async def load_plugins(self):
        """Dynamically load plugins from plugins directory"""
        plugins_dir = config.plugins_dir
        if not plugins_dir.exists():
            return

        for plugin_file in plugins_dir.glob("*.py"):
            if plugin_file.stem.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"omega_plugin_{plugin_file.stem}", plugin_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find all BaseTool subclasses in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseTool) and obj is not BaseTool:
                        tool = obj()
                        await tool.setup()
                        self.register(tool)
                        logger.info("plugin_loaded", plugin=plugin_file.stem, tool=tool.name)
            except Exception as e:
                logger.error("plugin_load_failed", plugin=plugin_file.stem, error=str(e))

    async def execute(self, tool_name: str, action: str, **kwargs) -> ToolResult:
        """Execute a tool action"""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Tool '{tool_name}' not found")
        try:
            return await tool.execute(action, **kwargs)
        except Exception as e:
            logger.error("tool_execute_error", tool=tool_name, action=action, error=str(e))
            return ToolResult(success=False, error=str(e))


# Global registry
registry = ToolRegistry()
