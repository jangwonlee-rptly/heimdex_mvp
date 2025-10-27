from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from .config import Settings


@dataclass(slots=True)
class StorageStat:
    size_bytes: int | None
    etag: str | None = None


@dataclass(slots=True)
class PresignedURL:
    url: str
    method: str = "PUT"
    headers: dict[str, str] | None = None


class Storage(ABC):
    @abstractmethod
    def exists(self, uri: str) -> bool: ...

    @abstractmethod
    def stat(self, uri: str) -> StorageStat: ...

    @abstractmethod
    def read_text(self, uri: str) -> str: ...

    @abstractmethod
    def write_text(self, uri: str, payload: str) -> str: ...

    @abstractmethod
    def write_bytes(self, uri: str, payload: bytes) -> str: ...

    @abstractmethod
    def list(self, prefix: str) -> Iterable[str]: ...

    @abstractmethod
    def presign_put(self, key: str, *, content_type: str | None, expires_s: int = 3600) -> PresignedURL: ...

    @abstractmethod
    def presign_get(self, key: str, *, expires_s: int = 3600) -> PresignedURL: ...


class LocalStorage(Storage):
    """Filesystem-backed storage abstraction suitable for development."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, uri_or_key: str) -> Path:
        parsed = urlparse(uri_or_key)
        if parsed.scheme in {"", "file"}:
            if parsed.scheme == "file":
                return Path(os.path.abspath(os.path.join(parsed.netloc, parsed.path))).resolve()
            return (self.base_path / uri_or_key).resolve()
        raise ValueError(f"Unsupported URI scheme for local storage: {uri_or_key}")

    def exists(self, uri: str) -> bool:
        return self._resolve(uri).exists()

    def stat(self, uri: str) -> StorageStat:
        path = self._resolve(uri)
        if not path.exists():
            raise FileNotFoundError(uri)
        return StorageStat(size_bytes=path.stat().st_size)

    def read_text(self, uri: str) -> str:
        return self._resolve(uri).read_text(encoding="utf-8")

    def write_text(self, uri: str, payload: str) -> str:
        path = self._resolve(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        return path.as_uri()

    def write_bytes(self, uri: str, payload: bytes) -> str:
        path = self._resolve(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path.as_uri()

    def list(self, prefix: str) -> Iterable[str]:
        base = self._resolve(prefix)
        if not base.exists():
            return []
        if base.is_file():
            return [base.as_uri()]
        return [p.as_uri() for p in base.rglob("*") if p.is_file()]

    def presign_put(self, key: str, *, content_type: str | None, expires_s: int = 3600) -> PresignedURL:
        target = self.base_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        return PresignedURL(url=target.as_uri(), method="PUT", headers={"Content-Type": content_type or "application/octet-stream"})

    def presign_get(self, key: str, *, expires_s: int = 3600) -> PresignedURL:
        target = self.base_path / key
        return PresignedURL(url=target.as_uri(), method="GET", headers=None)


class S3Storage(Storage):
    """Placeholder S3 implementation. Real integration pending secrets/bootstrap."""

    def __init__(self, *_: object, **__: object) -> None:  # pragma: no cover - stub
        raise NotImplementedError("S3 storage backend is not yet implemented.")


def get_storage(settings: Settings) -> Storage:
    base_path = settings.local_storage_base_path or settings.derived_root
    if settings.storage_backend == "local":
        return LocalStorage(base_path=Path(base_path))
    if settings.storage_backend == "s3":  # pragma: no cover - waiting for integration
        return S3Storage()
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")


__all__ = [
    "Storage",
    "LocalStorage",
    "S3Storage",
    "StorageStat",
    "PresignedURL",
    "get_storage",
]
