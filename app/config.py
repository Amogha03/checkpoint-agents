"""
Configuration management for the Clone & Scan system.
Loads settings from .env file and provides access to LLM configuration.
"""

import os
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str = "") -> str:
    """Read an environment value and remove optional surrounding quotes."""
    return os.getenv(name, default).strip().strip('"').strip("'")


class Config:
    """Application configuration loaded from environment variables."""

    # LLM Provider
    LLM_PROVIDER: Literal["openai", "anthropic"] = _get_env("LLM_PROVIDER", "openai")

    # OpenAI
    OPENAI_API_KEY: str = _get_env("OPENAI_API_KEY")
    OPENAI_MODEL: str = _get_env("OPENAI_MODEL", "gpt-4o-mini")

    # Anthropic
    ANTHROPIC_API_KEY: str = _get_env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL: str = _get_env("ANTHROPIC_MODEL", "claude-haiku-4-5")

    # LangSmith
    LANGSMITH_API_KEY: str = _get_env("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT: str = _get_env("LANGSMITH_PROJECT", "codebase-analyzer")
    LANGSMITH_TRACING_V2: str = _get_env("LANGSMITH_TRACING_V2", "true")
    LANGCHAIN_PROJECT: str = _get_env("LANGCHAIN_PROJECT", LANGSMITH_PROJECT)
    LANGCHAIN_TRACING_V2: str = _get_env(
        "LANGCHAIN_TRACING_V2", LANGSMITH_TRACING_V2
    )
    LANGCHAIN_API_KEY: str = _get_env("LANGCHAIN_API_KEY", LANGSMITH_API_KEY)

    # Service
    SERVICE_PORT: int = int(os.getenv("SERVICE_PORT", "8000"))
    SERVICE_HOST: str = _get_env("SERVICE_HOST", "0.0.0.0")

    # Workspace
    WORKSPACE_ROOT: str = _get_env("WORKSPACE_ROOT", "/tmp/workspaces")
    WORKSPACE_CLEANUP: bool = _get_env("WORKSPACE_CLEANUP", "true").lower() == "true"

    # Logging
    LOG_LEVEL: str = _get_env("LOG_LEVEL", "INFO")

    @classmethod
    def configure_tracing(cls) -> None:
        """Export LangSmith settings under the names consumed by LangChain."""
        os.environ["LANGCHAIN_TRACING_V2"] = cls.LANGCHAIN_TRACING_V2.lower()
        os.environ["LANGCHAIN_PROJECT"] = cls.LANGCHAIN_PROJECT
        if cls.LANGCHAIN_API_KEY:
            os.environ["LANGCHAIN_API_KEY"] = cls.LANGCHAIN_API_KEY

    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is present."""
        if cls.LLM_PROVIDER not in ("openai", "anthropic"):
            raise ValueError(f"Invalid LLM_PROVIDER: {cls.LLM_PROVIDER}. Must be 'openai' or 'anthropic'")

        if cls.LLM_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        if cls.LLM_PROVIDER == "anthropic" and not cls.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")

    @classmethod
    def get_llm_model_name(cls) -> str:
        """Get the configured LLM model name."""
        if cls.LLM_PROVIDER == "openai":
            return cls.OPENAI_MODEL
        else:
            return cls.ANTHROPIC_MODEL

    @classmethod
    def get_llm_provider(cls) -> Literal["openai", "anthropic"]:
        """Get the configured LLM provider."""
        return cls.LLM_PROVIDER


Config.configure_tracing()
