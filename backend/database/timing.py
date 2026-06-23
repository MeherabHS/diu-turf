"""Request-scoped query timing helpers for performance investigation."""
from __future__ import annotations

import logging
import time
from typing import Any

import asyncpg

log = logging.getLogger(__name__)


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


async def timed_fetchrow(
    conn: asyncpg.Connection,
    tag: str,
    query: str,
    *args: Any,
) -> asyncpg.Record | None:
    start = time.perf_counter()
    try:
        return await conn.fetchrow(query, *args)
    finally:
        log.info("[TIMING] query=%s duration=%.1fms", tag, _elapsed_ms(start))


async def timed_fetchval(
    conn: asyncpg.Connection,
    tag: str,
    query: str,
    *args: Any,
) -> Any:
    start = time.perf_counter()
    try:
        return await conn.fetchval(query, *args)
    finally:
        log.info("[TIMING] query=%s duration=%.1fms", tag, _elapsed_ms(start))


async def timed_execute(
    conn: asyncpg.Connection,
    tag: str,
    query: str,
    *args: Any,
) -> str:
    start = time.perf_counter()
    try:
        return await conn.execute(query, *args)
    finally:
        log.info("[TIMING] query=%s duration=%.1fms", tag, _elapsed_ms(start))


async def timed_fetch(
    conn: asyncpg.Connection,
    tag: str,
    query: str,
    *args: Any,
) -> list[asyncpg.Record]:
    start = time.perf_counter()
    try:
        return await conn.fetch(query, *args)
    finally:
        log.info("[TIMING] query=%s duration=%.1fms", tag, _elapsed_ms(start))


async def log_ungranted_locks(conn: asyncpg.Connection) -> None:
    """Log any ungranted PostgreSQL locks (helps spot pool/lock contention)."""
    try:
        rows = await conn.fetch(
            """SELECT locktype, relation::regclass AS relation, mode, granted, pid
               FROM pg_locks
               WHERE NOT granted
               LIMIT 20"""
        )
        if rows:
            log.warning(
                "[TIMING] ungranted_locks count=%d sample=%s",
                len(rows),
                [dict(r) for r in rows[:5]],
            )
        else:
            log.info("[TIMING] ungranted_locks=0")
    except Exception:
        log.exception("[TIMING] failed to inspect pg_locks")
