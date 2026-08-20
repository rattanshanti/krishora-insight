"""Core JWT + org membership (Shared Hosted Core)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import settings
from .membership import verify_org_membership

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CorePrincipal:
    user_id: uuid.UUID
    email: str | None
    org_id: uuid.UUID
    role: str
    raw: dict[str, Any]


def decode_core_token(token: str) -> dict[str, Any]:
    if not settings.CORE_AUTH_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CORE_AUTH_SECRET_KEY is not configured",
        )
    try:
        return jwt.decode(
            token,
            settings.CORE_AUTH_SECRET_KEY,
            algorithms=[settings.CORE_JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Core token: {exc}",
        ) from exc


def require_org_id(
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> uuid.UUID:
    if not x_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Org-Id header is required",
        )
    try:
        return uuid.UUID(x_org_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Org-Id format",
        ) from exc


async def get_core_principal(
    org_id: Annotated[uuid.UUID, Depends(require_org_id)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> CorePrincipal:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    token = credentials.credentials
    payload = decode_core_token(token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Core token missing sub",
        )
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Core token sub must be a user UUID",
        ) from exc

    role = await verify_org_membership(
        token,
        user_id,
        org_id,
        core_api_url=settings.CORE_API_URL,
        ttl_seconds=settings.CORE_MEMBERSHIP_CACHE_TTL,
    )
    return CorePrincipal(
        user_id=user_id,
        email=payload.get("email"),
        org_id=org_id,
        role=role,
        raw=payload,
    )
