"""Centralized configuration management via pydantic-settings.

Replaces scattered os.getenv() calls with a single Settings class that
validates environment variables at startup and provides typed access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"
_VENDORED_EMBEDDER = _BACKEND_DIR / "vendor" / "models" / "jina-code-embeddings-0.5b"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    All settings have sensible defaults for local development.
    Production deployments should override via .env file or environment.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    remote_db_url: SecretStr | None = Field(default=None, description="PostgreSQL connection string for remote storage")

    openai_api_key: SecretStr | None = Field(default=None, description="OpenAI API key for model access")
    anthropic_api_key: SecretStr | None = Field(default=None, description="Anthropic API key for Claude models")

    worker_threads: int = Field(
        default=4, ge=1, le=32, description="Number of concurrent worker threads", alias="WORKER_CONCURRENCY"
    )
    worker_poll_interval: float = Field(
        default=1.0, ge=0.1, le=60.0, description="Seconds between queue polling cycles"
    )
    worker_stale_threshold: float = Field(
        default=600.0, ge=60.0, description="Seconds of inactivity before worker flagged as stuck"
    )
    cancel_poll_interval: float = Field(
        default=1.0, ge=0.1, le=10.0, description="Seconds between cancel signal checks"
    )
    job_run_start_method: Literal["fork", "spawn", "forkserver"] = Field(
        default="fork", description="Multiprocessing start method for job execution"
    )

    artifacts_dir: str = Field(default="artifacts", description="Directory for storing optimized program artifacts")
    logs_dir: str = Field(default="logs", description="Directory for job execution logs")

    default_timeout: float = Field(default=30.0, ge=1.0, description="Standard request timeout in seconds")
    long_running_timeout: float = Field(
        default=120.0, ge=10.0, description="Extended timeout for complex operations in seconds"
    )
    subprocess_timeout: float = Field(default=300.0, ge=30.0, description="Timeout for subprocess execution in seconds")

    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(default=8000, ge=1024, le=65535, description="Server port")
    reload: bool = Field(default=False, description="Enable auto-reload on code changes (dev only)")

    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Comma-separated list of allowed CORS origins",
        alias="ALLOWED_ORIGINS",
    )

    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

    code_agent_model: str = Field(
        default="openai/gpt-4o-mini",
        description="LiteLLM model id used by the submit-wizard code agent (default: openai/gpt-4o-mini)",
    )
    code_agent_base_url: str = Field(
        default="",
        description="Optional custom base URL for the code agent LM (e.g. internal OpenAI-compatible gateway)",
    )

    generalist_agent_mcp_url: str = Field(
        default="http://localhost:8000/mcp/",
        description="URL of the MCP server the generalist agent connects to (usually the same app's /mcp mount)",
    )
    generalist_agent_model: str = Field(
        default="fireworks_ai/accounts/fireworks/models/minimax-m2p7",
        description=(
            "LiteLLM model id used by the generalist agent (default: "
            "Fireworks-hosted MiniMax M2p7 — exposes <think> reasoning "
            "for streaming)"
        ),
    )
    generalist_agent_base_url: str = Field(
        default="",
        description="Optional custom base URL for the generalist agent LM (e.g. internal OpenAI-compatible gateway)",
    )

    recommendations_embedding_model: str = Field(
        default=str(_VENDORED_EMBEDDER),
        description=(
            "Path or HF model id for the recommendation embedder. Defaults to "
            "the snapshot vendored under backend/vendor/models/ (tracked via "
            "git-lfs) so air-gapped deployments work out of the box. Override "
            "with a HF id (e.g. 'jinaai/jina-code-embeddings-0.5b') to fetch "
            "from Hugging Face when the host has internet, or with another "
            "absolute path to use a different snapshot. Must support MRL / "
            "head-truncated dimensions."
        ),
    )
    recommendations_embedding_dim: int = Field(
        default=512,
        ge=64,
        le=2048,
        description=(
            "MRL-truncated dimension stored in job_embeddings.embedding_*. "
            "Must match the schema; changing requires a migration."
        ),
    )
    recommendations_summary_model: str = Field(
        default="",
        description=(
            "LiteLLM model id used to summarise a finished job for the "
            "'summary' embedding aspect. Falls back to code_agent_model when empty."
        ),
    )
    recommendations_enabled: bool = Field(
        default=True,
        description=(
            "Master switch for the recommendation ingest + search pipeline. "
            "Off = the endpoint still returns [] and no embeddings are written."
        ),
    )
    recommendations_quality_min_absolute: float = Field(
        default=50.0,
        ge=0.0,
        description=(
            "Minimum optimized_test_metric required for a job to be "
            "flagged is_recommendable. Metrics live on a 0-100 scale in "
            "this codebase, so 50.0 is 'beats random for a two-class task.'"
        ),
    )
    recommendations_quality_min_gain_absolute: float = Field(
        default=5.0,
        ge=0.0,
        description=(
            "Minimum absolute lift (optimized - baseline) in percentage "
            "points for a job to be flagged is_recommendable."
        ),
    )
    recommendations_quality_min_gain_relative: float = Field(
        default=0.10,
        ge=0.0,
        description=(
            "Minimum relative lift (optimized - baseline) / baseline for a "
            "job to be flagged is_recommendable. Used in tandem with the "
            "absolute gain threshold via max(); whichever is larger applies."
        ),
    )

    max_jobs_per_user: int = Field(default=100, ge=1, description="Default per-user job cap")
    admin_usernames: str = Field(
        default="",
        description="Comma-separated usernames that bypass job quota entirely",
    )
    quota_overrides_json: str = Field(
        default="{}",
        description='Per-user quota overrides as JSON, e.g. \'{"power_user": 500, "researcher": null}\'',
        alias="QUOTA_OVERRIDES",
    )

    @field_validator("quota_overrides_json")
    @classmethod
    def _validate_quota_overrides_json(cls, v: str) -> str:
        """Reject QUOTA_OVERRIDES values that are not valid JSON."""
        if not v.strip():
            return "{}"
        try:
            json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"QUOTA_OVERRIDES is not valid JSON: {exc}") from exc
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Return ``cors_origins`` parsed into a list of trimmed, non-empty origins."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def admin_usernames_set(self) -> frozenset[str]:
        """Return admin usernames as a lowercase frozenset for O(1) membership tests."""
        return frozenset(s.strip().lower() for s in self.admin_usernames.split(",") if s.strip())

    def get_user_quota(self, username: str) -> int | None:
        """Return the effective job quota for a user.

        Admin users and users with a ``null`` override receive ``None`` (unlimited).
        Per-user overrides in ``quota_overrides_json`` take precedence over
        ``max_jobs_per_user`` for non-admin users.

        Args:
            username: The username to look up.

        Returns:
            Maximum number of allowed jobs, or ``None`` for unlimited access.
        """
        if username and username.lower() in self.admin_usernames_set:
            return None
        overrides: dict[str, int | None] = json.loads(self.quota_overrides_json)
        if username in overrides:
            return overrides[username]
        return self.max_jobs_per_user


settings = Settings()
