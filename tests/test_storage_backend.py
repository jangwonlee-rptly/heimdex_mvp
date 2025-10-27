from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.storage import GCSStorage, LocalStorage, get_storage


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_backend_is_local(monkeypatch):
    monkeypatch.delenv("HEIMDEX_STORAGE_BACKEND", raising=False)
    settings = get_settings()
    storage = get_storage(settings)
    assert isinstance(storage, LocalStorage)
    assert "file" in settings.allowed_source_uri_schemes
    assert "gs" not in settings.allowed_source_uri_schemes


def test_selecting_gcs_returns_gcs_storage(monkeypatch):
    monkeypatch.setenv("HEIMDEX_STORAGE_BACKEND", "gcs")
    settings = get_settings()
    storage = get_storage(settings)
    assert isinstance(storage, GCSStorage)


def test_allowed_schemes_reflect_backend(monkeypatch):
    monkeypatch.delenv("HEIMDEX_STORAGE_BACKEND", raising=False)
    settings_local = get_settings()
    assert settings_local.storage_backend == "local"
    assert "gs" not in settings_local.allowed_source_uri_schemes

    monkeypatch.setenv("HEIMDEX_STORAGE_BACKEND", "gcs")
    get_settings.cache_clear()
    settings_gcs = get_settings()
    assert settings_gcs.storage_backend == "gcs"
    assert "gs" in settings_gcs.allowed_source_uri_schemes


def test_parse_gs_uri_success(monkeypatch):
    monkeypatch.setenv("HEIMDEX_STORAGE_BACKEND", "gcs")
    settings = get_settings()
    storage = get_storage(settings)
    assert isinstance(storage, GCSStorage)
    bucket, key = storage._parse_gs_uri("gs://bucket/a/b/c.mp4")
    assert bucket == "bucket"
    assert key == "a/b/c.mp4"


@pytest.mark.parametrize(
    "uri",
    [
        "gs:///missing-bucket",
        "gs://",
        "gs://bucket",
        "file:///not-allowed",
    ],
)
def test_parse_gs_uri_errors(monkeypatch, uri):
    monkeypatch.setenv("HEIMDEX_STORAGE_BACKEND", "gcs")
    settings = get_settings()
    storage = get_storage(settings)
    assert isinstance(storage, GCSStorage)
    with pytest.raises(ValueError):
        storage._parse_gs_uri(uri)
