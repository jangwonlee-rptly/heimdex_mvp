from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
for candidate in (ROOT_DIR, APP_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from app.core.config import get_settings
from app.core.db import Base, create_engine
import app.db.models  # noqa: F401 - ensure models are imported for metadata


config = context.config

if config.config_file_name is not None:  # pragma: no cover - alembic runtime
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = get_settings()
    url = settings.database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_settings()
    connectable = create_engine(settings)

    async def run() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(run_migrations)
        await connectable.dispose()

    asyncio.run(run())


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():  # pragma: no cover - executed via alembic CLI
    run_migrations_offline()
else:  # pragma: no cover - executed via alembic CLI
    run_migrations_online()
