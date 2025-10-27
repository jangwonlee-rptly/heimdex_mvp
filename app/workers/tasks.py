from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.core.logging import configure_logging
from app.core.storage import get_storage
from app.db.models import JobType
from app.services.ingest_service import IngestService, process_sidecar_job, process_thumbnails_job


def run_job(job_id: str) -> None:
    """Entry-point executed by the job backend (RQ or inline)."""

    settings = get_settings()
    configure_logging()
    storage = get_storage(settings)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async def _runner() -> None:
        async with session_factory() as session:
            service = IngestService(settings, storage, session)
            job = await service.get_job(job_id)
            if not job:
                return
            if job.job_type == JobType.thumbnails:
                await process_thumbnails_job(job_id, session, settings, storage)
            elif job.job_type == JobType.sidecar:
                await process_sidecar_job(job_id, session, settings, storage)

    asyncio.run(_runner())
    asyncio.run(engine.dispose())


__all__ = ["run_job"]
