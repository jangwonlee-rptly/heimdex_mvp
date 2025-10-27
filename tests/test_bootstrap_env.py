from __future__ import annotations

import asyncio
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.db import Base
from app.main import create_app

DEV_SECRET = "dev-secret"
DEV_AUDIENCE = "heimdex"
DEV_ISSUER = "heimdex-local"


pytestmark = pytest.mark.no_default_env


def _write_env(target_dir: Path, *, environment: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    env_text = f"""
HEIMDEX_ENV={environment}
HEIMDEX_LOG_LEVEL=debug
HEIMDEX_AUTH_PROVIDER=local
HEIMDEX_JWT_SECRET={DEV_SECRET}
HEIMDEX_JWT_ISSUER={DEV_ISSUER}
HEIMDEX_JWT_AUDIENCE={DEV_AUDIENCE}
HEIMDEX_STORAGE_BACKEND=local
HEIMDEX_DERIVED_ROOT=derived
HEIMDEX_ALLOWED_SOURCE_URI_SCHEMES=file
HEIMDEX_DB_URL=sqlite+aiosqlite:///./heimdex.db
HEIMDEX_JOB_BACKEND=inline
HEIMDEX_JOB_MAX_RETRIES=1
HEIMDEX_REDIS_URL=redis://localhost:6379/0
HEIMDEX_ENABLE_LEGACY=false
""".strip()
    env_path = target_dir / ".env"
    env_path.write_text(env_text)
    return env_path


async def _initialise_sqlite(database_url: str) -> None:
    engine = create_async_engine(database_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


def _prepare_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, environment: str) -> TestClient:
    _write_env(tmp_path, environment=environment)
    for key in list(os.environ.keys()):
        if key.startswith("HEIMDEX_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    derived = tmp_path / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    asyncio.run(_initialise_sqlite("sqlite+aiosqlite:///./heimdex.db"))
    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    return client


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_env_boots_without_shell_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _prepare_app(tmp_path, monkeypatch, environment="development")
    try:
        response = client.get("/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        client.close()


def test_dev_token_endpoint_only_in_dev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _prepare_app(tmp_path, monkeypatch, environment="development")
    try:
        payload = {"org_id": "org-demo", "scopes": ["admin"], "user_id": "user-1"}
        response = client.post("/v1/admin/dev-token", json=payload)
        assert response.status_code == 200
        token = response.json()["token"]
        decoded = jwt.decode(
            token,
            DEV_SECRET,
            algorithms=["HS256"],
            audience=DEV_AUDIENCE,
            issuer=DEV_ISSUER,
        )
        assert decoded["org_id"] == payload["org_id"]
        assert decoded.get("sub") == payload["user_id"]
    finally:
        client.close()

    prod_client = _prepare_app(tmp_path / "prod", monkeypatch, environment="production")
    try:
        response = prod_client.post("/v1/admin/dev-token", json={"org_id": "org-prod"})
        assert response.status_code == 403
    finally:
        prod_client.close()


def test_request_with_dev_token_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _prepare_app(tmp_path, monkeypatch, environment="development")
    media_path = tmp_path / "sample.bin"
    media_path.write_bytes(b"sample-data")
    try:
        token_resp = client.post("/v1/admin/dev-token", json={"org_id": "org-demo"})
        assert token_resp.status_code == 200
        token = token_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        commit_resp = client.post(
            "/v1/ingest/commit",
            json={
                "org_id": "org-demo",
                "upload_id": "upload-1",
                "source_uri": media_path.resolve().as_uri(),
            },
            headers=headers,
        )
        assert commit_resp.status_code == 200
    finally:
        client.close()
