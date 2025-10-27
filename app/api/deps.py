from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.storage import Storage
from app.services.ingest_service import IngestService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    if not isinstance(session_factory, async_sessionmaker):  # pragma: no cover - defensive
        raise RuntimeError("session_factory_not_configured")
    async with session_factory() as session:
        yield session


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def get_app_settings() -> Settings:
    return get_settings()


async def get_ingest_service(
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_app_settings),
) -> AsyncIterator[IngestService]:
    service = IngestService(settings, storage, session)
    yield service


AuthenticatedService = Annotated[IngestService, Depends(get_ingest_service)]
AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


def get_idempotency_key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")


__all__ = [
    "get_session",
    "get_storage",
    "get_app_settings",
    "get_ingest_service",
    "AuthenticatedService",
    "AuthDependency",
    "get_idempotency_key",
]

