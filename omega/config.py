"""OMEGA Configuration System"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class OmegaConfig(BaseSettings):
    """Central configuration for OMEGA"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    omega_home: Path = Field(default_factory=lambda: Path.home() / ".omega")
    plugins_dir: Path = Field(default_factory=lambda: Path.home() / ".omega" / "plugins")
    memory_dir: Path = Field(default_factory=lambda: Path.home() / ".omega" / "memory")
    logs_dir: Path = Field(default_factory=lambda: Path.home() / ".omega" / "logs")
    sandbox_dir: Path = Field(default_factory=lambda: Path.home() / ".omega" / "sandbox")
    workflows_dir: Path = Field(default_factory=lambda: Path.home() / ".omega" / "workflows")

    # OpenRouter
    openrouter_api_key: str = Field(default="")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str = "https://omega-agent.ai"
    openrouter_app_name: str = "OMEGA Agent"

    # Model routing (free models)
    models: Dict[str, str] = Field(default_factory=lambda: {
        "reasoning": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "coding": "qwen/qwen3-coder-480b-a35b:free",
        "fast": "google/gemma-4-31b-it:free",
        "long_context": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "research": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "planning": "nex-agi/nex-n2-pro:free",
        "general": "nousresearch/hermes-3-405b-instruct:free",
        "vision": "nvidia/nemotron-nano-12b-v2-vl:free",
    })
    fallback_model: str = "google/gemma-4-31b-it:free"

    # Memory
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    sqlite_path: str = Field(default_factory=lambda: str(Path.home() / ".omega" / "omega.db"))
    duckdb_path: str = Field(default_factory=lambda: str(Path.home() / ".omega" / "analytics.duckdb"))
    max_short_term_messages: int = 50
    max_context_tokens: int = 32000

    # Redis / Task Queue
    redis_url: str = "redis://localhost:6379/0"
    celery_broker: str = "redis://localhost:6379/0"
    celery_backend: str = "redis://localhost:6379/1"

    # Security
    require_approval_for: List[str] = Field(default_factory=lambda: [
        "delete", "rm -rf", "push", "deploy", "publish", "payment",
        "format", "sudo", "chmod 777", "drop table", "truncate"
    ])
    sandbox_enabled: bool = True
    docker_sandbox_image: str = "python:3.12-slim"

    # Performance
    max_parallel_agents: int = 8
    agent_timeout_seconds: int = 300
    tool_timeout_seconds: int = 60

    # Observability
    log_level: str = "INFO"
    otel_endpoint: Optional[str] = None
    enable_metrics: bool = True

    # Browser
    browser_headless: bool = True
    browser_timeout: int = 30000

    # API Server
    api_host: str = "127.0.0.1"
    api_port: int = 8888

    def ensure_dirs(self):
        """Create all required directories"""
        for attr in ["omega_home", "plugins_dir", "memory_dir", "logs_dir",
                     "sandbox_dir", "workflows_dir"]:
            path = getattr(self, attr)
            path.mkdir(parents=True, exist_ok=True)


# Global config instance
config = OmegaConfig()
