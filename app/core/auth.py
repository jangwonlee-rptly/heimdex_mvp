from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings


security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    org_id: str
    user_id: Optional[str] = None
    scopes: tuple[str, ...] = ()


def _decode_token(token: str, settings: Settings) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - library handles message
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token") from exc
    return payload


async def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_authorization")

    payload = _decode_token(credentials.credentials, settings)
    org_id = payload.get("org_id") or payload.get("tenant")
    if not org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="org_scope_required")

    user_id = payload.get("sub") or payload.get("user_id")
    scopes = tuple(payload.get("scopes") or [])

    context = AuthContext(org_id=str(org_id), user_id=user_id, scopes=scopes)
    request.state.auth = context
    return context


__all__ = ["AuthContext", "get_auth_context"]

