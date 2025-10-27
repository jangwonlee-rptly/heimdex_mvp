from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Protocol

from redis import Redis
from rq import Queue

from app.db.models import JobType

from .config import Settings, get_settings


class BaseJobBackend(ABC):
    @abstractmethod
    async def enqueue(self, job_id: str, job_type: JobType) -> None: ...


class ImmediateJobBackend(BaseJobBackend):
    async def enqueue(self, job_id: str, job_type: JobType) -> None:
        from app.workers.tasks import run_job

        await asyncio.to_thread(run_job, job_id)


class RQJobBackend(BaseJobBackend):
    def __init__(self, queue: Queue):
        self.queue = queue

    async def enqueue(self, job_id: str, job_type: JobType) -> None:  # pragma: no cover - exercised via worker
        from app.workers.tasks import run_job

        self.queue.enqueue(run_job, job_id)


@lru_cache()
def get_job_backend() -> BaseJobBackend:
    settings = get_settings()
    if settings.job_queue_backend == "immediate":
        return ImmediateJobBackend()
    if settings.job_queue_backend == "rq":  # pragma: no cover - requires redis
        connection = Redis.from_url(settings.redis_url)
        return RQJobBackend(Queue("heimdex-jobs", connection=connection))
    raise ValueError(f"Unsupported job backend: {settings.job_queue_backend}")


__all__ = ["BaseJobBackend", "ImmediateJobBackend", "RQJobBackend", "get_job_backend"]
