from __future__ import annotations

import subprocess

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthDependency

from .schemas import EnvCheckResponse


router = APIRouter(prefix="/admin", tags=["admin"])


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


__all__ = ["router"]
