"""Simple rate limiting for auth and sensitive endpoints."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request, status

from database.db_config import DbBackend

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


def _enforce_in_memory(key: str, max_attempts: int, window_seconds: int) -> None:
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


async def _enforce_db(conn: Any, key: str, max_attempts: int, window_seconds: int) -> None:
    now = time.time()
    window_epoch = int(now // window_seconds) * window_seconds
    row = await conn.fetchrow(
        """SELECT attempt_count FROM rate_limit_buckets
           WHERE bucket_key = $1 AND window_start = $2""",
        key,
        window_epoch,
    )
    if row and row["attempt_count"] >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )
    await conn.execute(
        """INSERT INTO rate_limit_buckets (bucket_key, window_start, attempt_count)
           VALUES ($1, $2, 1)
           ON CONFLICT (bucket_key, window_start)
           DO UPDATE SET attempt_count = rate_limit_buckets.attempt_count + 1""",
        key,
        window_epoch,
    )


def _backend_from_request(request: Request | None) -> DbBackend | None:
    if request is None:
        return None
    db_config = getattr(request.app.state, "db_config", None)
    return db_config.backend if db_config else None


async def enforce_auth_rate_limit(
    request: Request,
    scope: str,
    conn: Any | None = None,
) -> None:
    max_attempts, window_seconds = _limits()
    key = f"{scope}:{_client_key(request)}"
    backend = _backend_from_request(request)
    if backend == DbBackend.POSTGRESQL and conn is not None:
        await _enforce_db(conn, key, max_attempts, window_seconds)
        return
    _enforce_in_memory(key, max_attempts, window_seconds)
