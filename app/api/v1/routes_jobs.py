from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api import deps
from app.db.models import Job

from . import schemas


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=schemas.JobResponse)
async def get_job(job_id: str, service: deps.AuthenticatedService, context: deps.AuthDependency) -> schemas.JobResponse:
    job = await service.get_job(job_id)
    if not job or job.org_id != context.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")

    result = job.result or {}
    error = job.error or {}

    return schemas.JobResponse(
        job_id=job.job_id,
        type=job.job_type.value,
        asset_id=job.asset_id,
        status=job.status.value,
        started_at=job.started_at,
        finished_at=job.finished_at,
        result=schemas.JobResultSidecar(**result) if result else None,
        error=schemas.JobError(**error) if error else None,
    )


__all__ = ["router"]

