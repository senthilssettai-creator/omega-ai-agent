"""Base Agent - Foundation for all OMEGA agents"""

import time
import uuid
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncIterator
from enum import Enum
import structlog

from omega.models.router import router, TaskType
from omega.memory.store import memory
from omega.config import config

logger = structlog.get_logger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"


class AgentResult:
    """Result of an agent execution"""

    def __init__(self, success: bool, output: Any = None, error: Optional[str] = None,
                 metadata: Optional[Dict] = None):
        self.success = success
        self.output = output
        self.error = error
        self.metadata = metadata or {}
        self.timestamp = time.time()

    def __str__(self):
        if self.success:
            return str(self.output)
        return f"Error: {self.error}"


class BaseAgent(ABC):
    """Foundation for all OMEGA agents"""

    name: str = "base"
    description: str = "Base agent"
    task_type: TaskType = TaskType.GENERAL

    def __init__(self, agent_id: Optional[str] = None):
        self.agent_id = agent_id or f"{self.name}_{str(uuid.uuid4())[:8]}"
        self.status = AgentStatus.IDLE
        self.current_task: Optional[str] = None
        self._children: List["BaseAgent"] = []
        self._parent: Optional["BaseAgent"] = None
        self.tools: Dict[str, Any] = {}
        self._start_time: Optional[float] = None
        self.log = structlog.get_logger(f"agent.{self.name}").bind(agent_id=self.agent_id)

    @property
    def system_prompt(self) -> str:
        return f"""You are {self.name}, a specialized AI agent that is part of OMEGA - an autonomous AI agent system.

{self.description}

Rules:
- Be precise, efficient, and goal-oriented
- Always output structured, actionable results
- If you cannot complete a task, explain why clearly
- Use tools when available and appropriate
- Think step by step for complex tasks
- Always verify your work before declaring success"""

    async def think(self, messages: List[Dict]) -> str:
        """Query the LLM with appropriate model selection (streaming for live view)"""
        self.status = AgentStatus.THINKING
        from omega.ui.terminal import ui
        
        # We print a header indicating the agent is thinking live
        header = f"\n[dim][{self.name.upper()} thinking][/dim] "
        ui.console.print(header, end="")
        
        full_content = []
        try:
            async for chunk in router.stream_complete(
                messages=messages,
                system=self.system_prompt,
                task_type=self.task_type,
            ):
                ui.console.print(chunk, end="", style="dim white")
                full_content.append(chunk)
            ui.console.print("\n")
            return "".join(full_content)
        finally:
            self.status = AgentStatus.IDLE

    async def think_stream(self, messages: List[Dict]) -> AsyncIterator[str]:
        """Query the LLM with streaming output and show live thinking"""
        self.status = AgentStatus.THINKING
        from omega.ui.terminal import ui
        header = f"\n[dim][{self.name.upper()} thinking][/dim] "
        ui.console.print(header, end="")
        try:
            async for chunk in router.stream_complete(
                messages=messages,
                system=self.system_prompt,
                task_type=self.task_type,
            ):
                ui.console.print(chunk, end="", style="dim white")
                yield chunk
            ui.console.print("\n")
        finally:
            self.status = AgentStatus.IDLE

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentResult:
        """Execute a task - main entry point"""
        self._start_time = time.time()
        self.current_task = task
        self.status = AgentStatus.EXECUTING
        self.log.info("agent_start", task=task[:100])

        try:
            result = await self._execute(task, context or {})
            duration_ms = int((time.time() - self._start_time) * 1000)
            memory.log_action(
                action=task[:200],
                output=str(result.output)[:500] if result else None,
                success=result.success if result else False,
                duration_ms=duration_ms,
                agent=self.name,
            )
            self.status = AgentStatus.DONE
            self.log.info("agent_done", duration_ms=duration_ms, success=result.success)
            return result
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.log.error("agent_error", error=str(e))
            memory.log_action(
                action=task[:200],
                success=False,
                agent=self.name,
            )
            return AgentResult(success=False, error=str(e))

    @abstractmethod
    async def _execute(self, task: str, context: Dict) -> AgentResult:
        """Implement task execution logic"""
        ...

    def spawn_child(self, agent_cls, **kwargs) -> "BaseAgent":
        """Spawn a child agent"""
        child = agent_cls(**kwargs)
        child._parent = self
        self._children.append(child)
        return child

    def register_tool(self, name: str, tool):
        """Register a tool with this agent"""
        self.tools[name] = tool

    def get_tool(self, name: str):
        return self.tools.get(name)

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "current_task": self.current_task,
            "children": len(self._children),
        }
