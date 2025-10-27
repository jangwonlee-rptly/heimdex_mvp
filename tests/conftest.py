import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import jwt
import pytest
import subprocess
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import Base, create_engine
from app.core.jobs import get_job_backend
from app.main import create_app


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "no_default_env: disable the default Heimdex environment bootstrap fixture for tests that manage their own .env",
    )


@pytest.fixture(autouse=True)
def configure_environment(request, monkeypatch, tmp_path):
    if request.node.get_closest_marker("no_default_env"):
        get_settings.cache_clear()
        get_job_backend.cache_clear()
        yield
        get_job_backend.cache_clear()
        get_settings.cache_clear()
        return
    db_path = tmp_path / "heimdex_test.db"
    derived_root = tmp_path / "derived"

    monkeypatch.setenv("HEIMDEX_ENV", "test")
    monkeypatch.setenv("HEIMDEX_LOG_LEVEL", "debug")
    monkeypatch.setenv("HEIMDEX_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("HEIMDEX_DERIVED_ROOT", str(derived_root))
    monkeypatch.setenv("HEIMDEX_STORAGE_BACKEND", "local")
    monkeypatch.setenv("HEIMDEX_JOB_BACKEND", "inline")
    monkeypatch.setenv("HEIMDEX_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("HEIMDEX_JWT_SECRET", "test-secret")
    monkeypatch.setenv("HEIMDEX_JWT_ISSUER", "heimdex-test")
    monkeypatch.setenv("HEIMDEX_JWT_AUDIENCE", "heimdex")
    monkeypatch.setenv("HEIMDEX_ENABLE_LEGACY", "false")

    get_settings.cache_clear()
    get_job_backend.cache_clear()
    settings = get_settings()
    engine = create_engine(settings)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_setup())

    yield

    async def _teardown() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_teardown())
    get_job_backend.cache_clear()
    get_settings.cache_clear()


@pytest.fixture()
def client(configure_environment):
    app = create_app()
    with TestClient(app) as client:
        yield client


def build_token(org_id: str, *, scopes: list[str] | None = None, user_id: str | None = None) -> str:
    payload = {"org_id": org_id}
    if scopes:
        payload["scopes"] = scopes
    if user_id:
        payload["sub"] = user_id
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture()
def org_headers() -> dict[str, str]:
    token = build_token("org-test")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    token = build_token("org-test", scopes=["admin"])
    return {"Authorization": f"Bearer {token}"}


def uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError("Unsupported URI in tests")
    return Path(parsed.path)


@pytest.fixture(scope="session")
def generated_video_file(tmp_path_factory) -> Path:
    """
    Generates a small, valid MP4 video file for testing in a temporary directory.
    """
    video_path = tmp_path_factory.mktemp("data") / "test_video.mp4"

    # Generate a 1-second video with a solid color
    command = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "color=c=black:s=128x72:r=30",
        "-t", "1",
        "-pix_fmt", "yuv420p",
        str(video_path)
    ]
    subprocess.run(command, check=True, capture_output=True)
    return video_path
