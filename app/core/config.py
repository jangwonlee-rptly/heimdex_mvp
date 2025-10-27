from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised runtime configuration for the Heimdex API."""

    model_config = SettingsConfigDict(env_prefix="HEIMDEX_", env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Heimdex API"
    environment: str = Field(default="local", description="Deployment environment label.")
    version: str = Field(default="0.1.0", description="API version for metadata and OpenAPI.")

    database_url: str = Field(default="sqlite+aiosqlite:///./heimdex.db", description="SQLAlchemy compatible DSN.")
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL for background jobs.")

    derived_root: Path = Field(default_factory=lambda: Path("derived"), description="Root for derived artefacts.")
    storage_backend: Literal["local", "s3"] = Field(default="local", description="Active storage implementation.")
    local_storage_base_path: Path | None = Field(
        default=None,
        description="Override base path for local storage (defaults to derived_root).",
    )

    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024, description="Soft limit for ingest uploads.")

    jwt_secret: str = Field(default="change-me", description="Signing secret for stub JWT validation.")
    jwt_algorithm: str = Field(default="HS256", description="Algorithm used for JWT tokens.")

    idempotency_ttl_seconds: int = Field(default=24 * 3600, description="TTL for stored idempotency keys.")

    job_queue_backend: Literal["immediate", "rq"] = Field(
        default="immediate",
        description="Backend for async jobs (immediate executes inline; rq schedules via Redis).",
    )
    job_max_retries: int = Field(default=3, description="Maximum retry attempts for failed jobs.")
    job_retry_backoff_base: float = Field(default=2.0, description="Backoff multiplier between retries.")
    job_retry_initial_delay_s: float = Field(default=1.0, description="Initial delay before the first retry.")

    allow_http_source_schemes: tuple[str, ...] = Field(
        default=("file", "s3", "gs"),
        description="Allowed URI schemes for source media references.")

    metrics_endpoint: HttpUrl | None = Field(
        default=None,
        description="Optional push endpoint for metrics exporters.",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]

