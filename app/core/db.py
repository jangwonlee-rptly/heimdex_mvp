from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import Settings


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, echo=False, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(settings: Settings) -> AsyncIterator[dict[str, object]]:
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    state: dict[str, object] = {"engine": engine, "session_factory": session_factory}
    try:
        yield state
    finally:
        await engine.dispose()


async def get_session(state: dict[str, object]) -> AsyncIterator[AsyncSession]:
    session_factory = state["session_factory"]
    assert isinstance(session_factory, async_sessionmaker)
    async with session_factory() as session:
        yield session


__all__ = ["Base", "create_engine", "create_session_factory", "lifespan", "get_session"]

