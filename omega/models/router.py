"""Intelligent OpenRouter Model Router - Auto-selects best free model per task"""

import asyncio
import time
from typing import Optional, AsyncIterator, Dict, Any, List
from enum import Enum
import httpx
import structlog

from omega.config import config

logger = structlog.get_logger(__name__)


class TaskType(str, Enum):
    REASONING = "reasoning"
    CODING = "coding"
    FAST = "fast"
    LONG_CONTEXT = "long_context"
    RESEARCH = "research"
    PLANNING = "planning"
    GENERAL = "general"
    VISION = "vision"


class ModelRouter:
    """Automatically routes requests to the best free model for the task"""

    def __init__(self):
        self.base_url = config.openrouter_base_url
        self.api_key = config.openrouter_api_key
        self.models = config.models
        self.fallback = config.fallback_model
        self._model_health: Dict[str, bool] = {}
        self._request_counts: Dict[str, int] = {}
        self._last_reset = time.time()

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": config.openrouter_site_url,
            "X-Title": config.openrouter_app_name,
            "Content-Type": "application/json",
        }

    def select_model(self, task_type: TaskType, context_length: int = 0) -> str:
        """Select the optimal model for a given task"""
        if context_length > 64000:
            return self.models.get("long_context", self.fallback)

        model = self.models.get(task_type.value, self.fallback)
        if self._model_health.get(model) is False:
            logger.warning("model_unhealthy_falling_back", model=model)
            return self.fallback
        return model

    def infer_task_type(self, messages: List[Dict], system: Optional[str] = None) -> TaskType:
        """Infer the best task type from message content"""
        import re

        content = " ".join(
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        ).lower()
        if system:
            content += " " + system.lower()

        def has_any(keywords: List[str]) -> bool:
            return any(re.search(rf"\b{re.escape(kw)}\b", content) for kw in keywords)

        if has_any(["code", "python", "javascript", "function", "class", "debug", "bug", "test", "implement", "refactor"]):
            return TaskType.CODING
        if has_any(["search", "research", "find", "analyze", "compare", "summarize", "report"]):
            return TaskType.RESEARCH
        if has_any(["plan", "roadmap", "strategy", "breakdown", "steps", "tasks"]):
            return TaskType.PLANNING
        if has_any(["reason", "reasoning", "think through", "logic", "solve", "explain why", "figure out", "deduce", "root cause"]):
            return TaskType.REASONING
        if has_any(["image", "screenshot", "visual", "picture", "photo"]):
            return TaskType.VISION
        return TaskType.GENERAL

    async def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Send a completion request to OpenRouter"""
        if not task_type:
            task_type = self.infer_task_type(messages, system)

        selected_model = model or self.select_model(task_type)
        logger.info("model_selected", model=selected_model, task_type=task_type)

        payload = {
            "model": selected_model,
            "messages": messages if not system else [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                self._model_health[selected_model] = True
                return {
                    "content": data["choices"][0]["message"]["content"],
                    "model": data.get("model", selected_model),
                    "usage": data.get("usage", {}),
                    "task_type": task_type,
                }
            except httpx.HTTPStatusError as e:
                self._model_health[selected_model] = False
                logger.error("openrouter_error", status=e.response.status_code, model=selected_model)
                if selected_model != self.fallback:
                    return await self.complete(
                        messages, system, task_type, self.fallback,
                        max_tokens, temperature, stream
                    )
                raise

    async def stream_complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream a completion response token by token"""
        if not task_type:
            task_type = self.infer_task_type(messages, system)

        selected_model = model or self.select_model(task_type)

        payload = {
            "model": selected_model,
            "messages": messages if not system else [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            import json
                            data = json.loads(data_str)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue

    async def list_free_models(self) -> List[Dict]:
        """Fetch available free models from OpenRouter"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/models",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            models = response.json().get("data", [])
            return [m for m in models if m.get("pricing", {}).get("prompt", "0") == "0"]


# Global router instance
router = ModelRouter()
