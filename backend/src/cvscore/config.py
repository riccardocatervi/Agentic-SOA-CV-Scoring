from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",  # looked up in the current working directory first
        env_file_depth=2,  # then in the parent directory (the repo root)
        extra="ignore",  # unknown lines in .env are discarded instead of failing
    )

    # LLM backend (any OpenAI-compatible endpoint: local Ollama, FBK server, OpenAI)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str  # no default: it is required, startup fails if it is missing
    llm_model: str  # no default: depends on what the server exposes
    llm_timeout_seconds: float = 60.0

    # Job processing
    k_consumers: int = 2
    max_agent_steps: int = 10
    job_ttl_seconds: int = 3600

    # Files and services
    storage_dir: Path = Path("data")
    mcp_gateway_url: str = "http://127.0.0.1:8765/mcp"


@lru_cache
def get_settings() -> Settings:
    """Single shared instance, built on first use (not at import time)."""
    return Settings()
