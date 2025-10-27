from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    """Secrets configuration, loaded from the environment or a secrets management service."""

    model_config = SettingsConfigDict(
        env_prefix="HEIMDEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret: str = Field(default="change-me", description="Signing secret for stub JWT validation.")

    @classmethod
    def from_settings(cls, settings: "Settings") -> "Secrets":
        return cls()


class Settings(BaseSettings):
    """Centralised runtime configuration for the Heimdex API."""

    model_config = SettingsConfigDict(
        env_prefix="HEIMDEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Heimdex API"
    environment: str = Field(default="development", description="Deployment environment label.")
    version: str = Field(default="0.1.0", description="API version for metadata and OpenAPI.")
    log_level: str = Field(default="info")

    auth_provider: str = Field(default="local")
    firebase_project_id: Optional[str] = None

    database_url: str = Field(
        default="sqlite+aiosqlite:///./heimdex.db",
        description="SQLAlchemy compatible DSN.",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for background jobs.",
    )

    derived_root: Path = Field(default_factory=lambda: Path("derived"), description="Root for derived artefacts.")
    storage_backend: Literal["local", "gcs"] = Field(default="local", description="Active storage implementation.")
    local_storage_base_path: Path | None = Field(
        default=None,
        description="Override base path for local storage (defaults to derived_root).",
    )

    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024, description="Soft limit for ingest uploads.")
    enable_legacy: bool = Field(default=False, description="Enable legacy /metadata endpoints temporarily.")

    jwt_algorithm: str = Field(default="HS256", description="Algorithm used for JWT tokens.")
    jwt_issuer: Optional[str] = None
    jwt_audience: Optional[str] = None

    idempotency_ttl_seconds: int = Field(default=24 * 3600, description="TTL for stored idempotency keys.")

    job_queue_backend: Literal["immediate", "inline", "rq", "gcp_tasks"] = Field(
        default="immediate",
        description="Backend for async jobs (inline executes inline; rq schedules via Redis).",
    )
    job_max_retries: int = Field(default=3, description="Maximum retry attempts for failed jobs.")
    job_retry_backoff_base: float = Field(default=2.0, description="Backoff multiplier between retries.")
    job_retry_initial_delay_s: float = Field(default=1.0, description="Initial delay before the first retry.")

    allow_http_source_schemes: tuple[str, ...] = Field(
        default=("file", "s3", "gs"),
        description="Allowed URI schemes for source media references.")

    secrets: Secrets = Field(default_factory=Secrets, description="Holds sensitive configuration.")

    metrics_endpoint: HttpUrl | None = Field(
        default=None,
        description="Optional push endpoint for metrics exporters.",
    )
    gcp_project_id: Optional[str] = None
    gcs_bucket: Optional[str] = None
    gcp_signing_service_account: Optional[str] = None
    gcp_signing_key_path: Optional[Path] = None

    @property
    def environment_lower(self) -> str:
        return self.environment.lower()

    @property
    def normalized_job_backend(self) -> str:
        if self.job_queue_backend == "inline":
            return "immediate"
        return self.job_queue_backend

    @property
    def allowed_source_uri_schemes(self) -> tuple[str, ...]:
        override = os.getenv("HEIMDEX_ALLOWED_SOURCE_URI_SCHEMES")
        if override:
            values = [item.strip() for item in override.split(",") if item.strip()]
            if values:
                return tuple(values)
        if self.storage_backend == "gcs":
            return ("gs", "file")
        return ("file",)


@lru_cache()
def get_settings() -> Settings:
    load_dotenv(".env", override=False)

    _ENV_ALIAS_MAP = {
        "HEIMDEX_ENV": "HEIMDEX_ENVIRONMENT",
        "HEIMDEX_DB_URL": "HEIMDEX_DATABASE_URL",
        "HEIMDEX_JOB_BACKEND": "HEIMDEX_JOB_QUEUE_BACKEND",
    }

    for source, target in _ENV_ALIAS_MAP.items():
        value = os.getenv(source)
        if value:
            os.environ[target] = value

    settings = Settings()

    # In a real application, you would fetch secrets from a secure vault
    # instead of just loading them from the environment.
    secrets = Secrets.from_settings(settings)

    if settings.environment == "production" and secrets.jwt_secret == "change-me":
        raise ValueError("Production environment must have a non-default JWT secret.")

    settings.secrets = secrets
    return settings


__all__ = ["Settings", "get_settings"]
