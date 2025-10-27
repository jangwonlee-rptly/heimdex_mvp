from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import AuthDependency
from app.core.config import Settings, get_settings

from .schemas import EnvCheckResponse


router = APIRouter(prefix="/admin", tags=["admin"])


class DevTokenRequest(BaseModel):
    org_id: str = Field(..., examples=["demo-org"])
    scopes: list[str] = Field(default_factory=lambda: ["admin"])
    user_id: str | None = Field(default=None, examples=["user-123"])


class DevTokenResponse(BaseModel):
    token: str


def _probe_binary(command: list[str]) -> bool:
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:  # pragma: no cover - defensive
        return False


@router.get("/env-check", response_model=EnvCheckResponse, summary="Validate ffmpeg toolchain")
async def env_check(context: AuthDependency) -> EnvCheckResponse:
    if "admin" not in context.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_scope_required")

    results = {
        "ffmpeg": _probe_binary(["ffmpeg", "-version"]),
        "ffprobe": _probe_binary(["ffprobe", "-version"]),
        "pyscenedetect": _probe_binary(["python", "-m", "scenedetect", "--version"]),
    }
    return EnvCheckResponse(**results)


@router.post("/dev-token", response_model=DevTokenResponse, summary="Mint development JWT")
async def mint_dev_token(payload: DevTokenRequest, settings: Settings = Depends(get_settings)) -> DevTokenResponse:
    if settings.environment_lower not in {"development", "dev"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="dev_token_disabled")

    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(hours=1)
    claims: dict[str, object] = {
        "org_id": payload.org_id,
        "scopes": payload.scopes,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if payload.user_id:
        claims["sub"] = payload.user_id
    if settings.jwt_issuer:
        claims["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        claims["aud"] = settings.jwt_audience

    token = jwt.encode(claims, settings.secrets.jwt_secret, algorithm=settings.jwt_algorithm)
    return DevTokenResponse(token=token)


__all__ = ["router"]
