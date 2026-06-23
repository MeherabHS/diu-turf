"""Fast database health probe — bounded time, never blocks the root endpoint."""
from __future__ import annotations

import asyncio
import logging
import os
import time

import asyncpg

from database.connection import DbPool

log = logging.getLogger(__name__)

ROOT_DB_CHECK_TIMEOUT = float(os.getenv("ROOT_DB_CHECK_TIMEOUT", "0.8"))


async def ping_database(
    pool: DbPool,
    timeout_sec: float = ROOT_DB_CHECK_TIMEOUT,
) -> bool:
    """Return True if SELECT 1 succeeds within timeout_sec."""

    async def _ping() -> None:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    start = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_sec):
            await _ping()
        ms = (time.perf_counter() - start) * 1000
        log.info("[ROOT] db ping ok in %.1fms", ms)
        return True
    except Exception as exc:
        ms = (time.perf_counter() - start) * 1000
        log.warning("[ROOT] db ping failed in %.1fms: %s", ms, exc)
        return False
