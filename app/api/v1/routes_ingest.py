from __future__ import annotations

import subprocess

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.core.auth import AuthContext
from app.core.config import Settings

from . import schemas


router = APIRouter(prefix="/ingest", tags=["ingest"])


def _verify_org(request_org: str, context: AuthContext) -> None:
    if request_org != context.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="org_scope_mismatch")


@router.post("/init", response_model=schemas.IngestInitResponse, status_code=status.HTTP_201_CREATED)
async def init_ingest(
    payload: schemas.IngestInitRequest,
    service: deps.AuthenticatedService,
    context: deps.AuthDependency,
    settings: Settings = Depends(deps.get_app_settings),
) -> schemas.IngestInitResponse:
    _verify_org(payload.org_id, context)

    if payload.content_length > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="upload_too_large")

    result = await service.init_upload(
        org_id=payload.org_id,
        source_name=payload.source_name,
        content_type=payload.content_type,
    )
    return schemas.IngestInitResponse(**result)


@router.post("/commit", response_model=schemas.IngestCommitResponse)
async def commit_ingest(
    payload: schemas.IngestCommitRequest,
    service: deps.AuthenticatedService,
    context: deps.AuthDependency,
) -> schemas.IngestCommitResponse:
    _verify_org(payload.org_id, context)
    try:
        result = await service.commit_upload(
            org_id=payload.org_id,
            source_uri=str(payload.source_uri),
            upload_id=payload.upload_id,
            weak_threshold_bytes=payload.weak_threshold_bytes,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source_not_found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return schemas.IngestCommitResponse(**result)


@router.post("/probe", response_model=schemas.SidecarModel)
async def probe_source(
    payload: schemas.ProbeRequest,
    service: deps.AuthenticatedService,
    context: deps.AuthDependency,
) -> schemas.SidecarModel:
    _verify_org(payload.org_id, context)
    try:
        result = await service.probe(
            org_id=payload.org_id,
            source_uri=str(payload.source_uri),
            weak_threshold_bytes=payload.weak_threshold_bytes,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source_not_found")
    except subprocess.CalledProcessError as exc:  # type: ignore[name-defined]
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.stderr) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return schemas.SidecarModel(**result)


__all__ = ["router"]
