"""Prove Core org membership via GET /context (with process-local TTL cache)."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import HTTPException, status

# ponytail: process-local TTL cache — ceiling ~N workers × entries; upgrade to Redis if multi-replica.
_DEFAULT_TTL_SECONDS = 45.0
_cache: dict[tuple[str, str], tuple[float, str]] = {}
_lock = asyncio.Lock()

FetchContext = Callable[[str, uuid.UUID, str], Awaitable[dict[str, Any]]]


def clear_membership_cache() -> None:
    """Test helper — drop all cached memberships."""
    _cache.clear()


def _cache_key(user_id: uuid.UUID, org_id: uuid.UUID) -> tuple[str, str]:
    return (str(user_id), str(org_id))


def _get_cached(user_id: uuid.UUID, org_id: uuid.UUID) -> str | None:
    key = _cache_key(user_id, org_id)
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, role = entry
    if time.monotonic() >= expires_at:
        _cache.pop(key, None)
        return None
    return role


def _set_cached(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    *,
    ttl_seconds: float,
) -> None:
    _cache[_cache_key(user_id, org_id)] = (time.monotonic() + ttl_seconds, role)


async def _default_fetch_context(
    token: str,
    org_id: uuid.UUID,
    core_api_url: str,
) -> dict[str, Any]:
    url = f"{core_api_url.rstrip('/')}/context"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Org-Id": str(org_id),
            },
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text or "Core membership check failed",
        )
    return response.json()


async def verify_org_membership(
    token: str,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    core_api_url: str | None = None,
    ttl_seconds: float | None = None,
    fetch_context: FetchContext | None = None,
) -> str:
    """
    Return the member's role if Core confirms membership.

    Uses GET /context with the same Bearer + X-Org-Id the product received.
    """
    cached = _get_cached(user_id, org_id)
    if cached is not None:
        return cached

    ttl = (
        ttl_seconds
        if ttl_seconds is not None
        else float(os.environ.get("CORE_MEMBERSHIP_CACHE_TTL", _DEFAULT_TTL_SECONDS))
    )
    base_url = core_api_url or os.environ.get("CORE_API_URL", "").rstrip("/")
    fetcher = fetch_context

    async with _lock:
        cached = _get_cached(user_id, org_id)
        if cached is not None:
            return cached

        if fetcher is None:
            if not base_url:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="CORE_API_URL is not configured",
                )

            async def _fetch(
                t: str, oid: uuid.UUID, _url: str = base_url
            ) -> dict[str, Any]:
                return await _default_fetch_context(t, oid, _url)

            fetcher = _fetch

        body = await fetcher(token, org_id, base_url or "")
        membership = body.get("membership") or {}
        role = membership.get("role")
        if not role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Core context missing membership.role",
            )
        org = body.get("organization") or {}
        ctx_org = org.get("id")
        if ctx_org is not None and str(ctx_org) != str(org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Core context organization does not match X-Org-Id",
            )
        _set_cached(user_id, org_id, str(role), ttl_seconds=ttl)
        return str(role)
