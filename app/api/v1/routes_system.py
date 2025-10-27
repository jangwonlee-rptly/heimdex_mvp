from __future__ import annotations

from fastapi import APIRouter

from .schemas import HealthResponse


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse()


__all__ = ["router"]

