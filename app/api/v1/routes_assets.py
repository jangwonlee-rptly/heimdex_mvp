from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api import deps
from app.core.auth import AuthContext
from app.core.storage import Storage
from app.db.models import JobType

from . import schemas


router = APIRouter(prefix="/assets", tags=["assets"])


def _verify_org(org_id: str, context: AuthContext) -> None:
    if org_id != context.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="org_scope_mismatch")


@router.post("/{asset_id}/thumbnails", response_model=schemas.JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_thumbnails(
    asset_id: str,
    payload: schemas.ThumbnailJobRequest,
    service: deps.AuthenticatedService,
    context: deps.AuthDependency,
    response: Response,
    idempotency_key: str | None = Depends(deps.get_idempotency_key),
) -> schemas.JobAcceptedResponse:
    _verify_org(payload.org_id, context)

    snapshot = await service.get_asset_snapshot(org_id=context.org_id, asset_id=asset_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="asset_not_found")

    try:
        job = await service.enqueue_job(
            org_id=context.org_id,
            asset_id=asset_id,
            job_type=JobType.thumbnails,
            payload={
                "org_id": context.org_id,
                "asset_id": asset_id,
                "source_uri": str(payload.source_uri),
                "weak_threshold_bytes": payload.weak_threshold_bytes,
                "policy": payload.policy.model_dump() if payload.policy else None,
            },
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        if str(exc) == "idempotency_conflict":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency_conflict") from exc
        raise

    location = f"/v1/jobs/{job.job_id}"
    response.headers["Location"] = location
    return schemas.JobAcceptedResponse(job_id=job.job_id, location=location)


@router.post("/{asset_id}/sidecar", response_model=schemas.JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_sidecar(
    asset_id: str,
    payload: schemas.SidecarJobRequest,
    service: deps.AuthenticatedService,
    context: deps.AuthDependency,
    response: Response,
    idempotency_key: str | None = Depends(deps.get_idempotency_key),
) -> schemas.JobAcceptedResponse:
    _verify_org(payload.org_id, context)

    snapshot = await service.get_asset_snapshot(org_id=context.org_id, asset_id=asset_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="asset_not_found")

    try:
        job = await service.enqueue_job(
            org_id=context.org_id,
            asset_id=asset_id,
            job_type=JobType.sidecar,
            payload={
                "org_id": context.org_id,
                "asset_id": asset_id,
                "source_uri": str(payload.source_uri),
                "weak_threshold_bytes": payload.weak_threshold_bytes,
            },
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        if str(exc) == "idempotency_conflict":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency_conflict") from exc
        raise

    location = f"/v1/jobs/{job.job_id}"
    response.headers["Location"] = location
    return schemas.JobAcceptedResponse(job_id=job.job_id, location=location)


@router.get("/{asset_id}", response_model=schemas.AssetResponse)
async def get_asset(
    asset_id: str,
    service: deps.AuthenticatedService,
    context: deps.AuthDependency,
) -> schemas.AssetResponse:
    snapshot = await service.get_asset_snapshot(org_id=context.org_id, asset_id=asset_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="asset_not_found")
    return schemas.AssetResponse(**snapshot)


@router.get("/{asset_id}/sidecar", response_model=schemas.SidecarModel)
async def fetch_sidecar(
    asset_id: str,
    service: deps.AuthenticatedService,
    context: deps.AuthDependency,
    storage: Storage = Depends(deps.get_storage),
) -> schemas.SidecarModel:
    snapshot = await service.get_asset_snapshot(org_id=context.org_id, asset_id=asset_id)
    pointer = snapshot.get("sidecar") if snapshot else None
    if not snapshot or not pointer or not pointer.get("storage_key"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sidecar_not_found")

    storage_key = f"{context.org_id}/{pointer['storage_key']}"
    try:
        payload = storage.read_text(storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sidecar_not_found")
    return schemas.SidecarModel(**json.loads(payload))


__all__ = ["router"]
