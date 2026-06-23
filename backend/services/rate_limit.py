"""Simple in-memory rate limiting for auth endpoints."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

_lock = Lock()
_attempts: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _limits() -> tuple[int, int]:
    max_attempts = int(os.getenv("AUTH_RATE_LIMIT_MAX", "10"))
    window_seconds = int(os.getenv("AUTH_RATE_LIMIT_WINDOW", "900"))
    return max(1, max_attempts), max(60, window_seconds)


def enforce_auth_rate_limit(request: Request, scope: str) -> None:
    """Raise HTTP 429 when too many auth attempts from the same client."""
    max_attempts, window_seconds = _limits()
    key = f"{scope}:{_client_key(request)}"
    now = time.time()
    window_start = now - window_seconds

    with _lock:
        recent = [t for t in _attempts[key] if t > window_start]
        if len(recent) >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
            )
        recent.append(now)
        _attempts[key] = recent
