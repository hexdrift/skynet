"""Centralized configuration management via pydantic-settings.

Replaces scattered os.getenv() calls with a single Settings class that
validates environment variables at startup and provides typed access.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env file relative to backend/ directory (parent of core/)
_BACKEND_DIR = Path(__file__).parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.
    
    All settings have sensible defaults for local development.
    Production deployments should override via .env file or environment.
    """
    
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars
    )
    
    # ── Database ──
    remote_db_url: SecretStr | None = Field(
        default=None,
        description="PostgreSQL connection string for remote storage"
    )
    
    # ── API Keys ──
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key for model access"
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key for Claude models"
    )
    
    # ── Worker Configuration ──
    worker_threads: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Number of concurrent worker threads",
        alias="WORKER_CONCURRENCY"
    )
    worker_poll_interval: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Seconds between queue polling cycles"
    )
    worker_stale_threshold: float = Field(
        default=600.0,
        ge=60.0,
        description="Seconds of inactivity before worker flagged as stuck"
    )
    cancel_poll_interval: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Seconds between cancel signal checks"
    )
    job_run_start_method: Literal["fork", "spawn", "forkserver"] = Field(
        default="fork",
        description="Multiprocessing start method for job execution"
    )
    
    # ── Paths ──
    artifacts_dir: str = Field(
        default="artifacts",
        description="Directory for storing optimized program artifacts"
    )
    logs_dir: str = Field(
        default="logs",
        description="Directory for job execution logs"
    )
    
    # ── Timeouts ──
    default_timeout: float = Field(
        default=30.0,
        ge=1.0,
        description="Standard request timeout in seconds"
    )
    long_running_timeout: float = Field(
        default=120.0,
        ge=10.0,
        description="Extended timeout for complex operations in seconds"
    )
    subprocess_timeout: float = Field(
        default=300.0,
        ge=30.0,
        description="Timeout for subprocess execution in seconds"
    )
    
    # ── Server ──
    host: str = Field(
        default="0.0.0.0",
        description="Server bind address"
    )
    port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="Server port"
    )
    reload: bool = Field(
        default=False,
        description="Enable auto-reload on code changes (dev only)"
    )
    
    # ── CORS ──
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Comma-separated list of allowed CORS origins",
        alias="ALLOWED_ORIGINS"
    )
    
    # ── Logging ──
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Global settings instance
settings = Settings()
