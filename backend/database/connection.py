"""Database connection layer — PostgreSQL (production) or SQLite (local dev)."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Union

import asyncpg
from fastapi import Request

from database.db_config import (
    DEFAULT_SQLITE_PATH,
    DbBackend,
    DatabaseConfig,
    prepare_postgres_connection,
    resolve_database_config,
    sqlite_allowed,
)
from database.sqlite_adapter import SQLitePool, close_sqlite_pool, create_sqlite_pool

log = logging.getLogger(__name__)

DbPool = Union[asyncpg.Pool, SQLitePool]

POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
POOL_COMMAND_TIMEOUT = float(os.getenv("DB_POOL_COMMAND_TIMEOUT", "30"))
POOL_ACQUIRE_TIMEOUT = float(os.getenv("DB_POOL_ACQUIRE_TIMEOUT", "5"))


async def _try_postgres_pool(dsn: str, timeout: float = 3.0) -> asyncpg.Pool | None:
    pg = prepare_postgres_connection(dsn)
    pool_kwargs: dict[str, Any] = {
        "dsn": pg.dsn,
        "min_size": POOL_MIN_SIZE,
        "max_size": POOL_MAX_SIZE,
        "command_timeout": POOL_COMMAND_TIMEOUT,
        "timeout": POOL_ACQUIRE_TIMEOUT,
    }
    if pg.ssl is True:
        pool_kwargs["ssl"] = True
    elif pg.ssl is False:
        pool_kwargs["ssl"] = False
    try:
        pool = await asyncio.wait_for(asyncpg.create_pool(**pool_kwargs), timeout=timeout)
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return pool
    except Exception as exc:
        log.warning("PostgreSQL unavailable (%s)", exc)
        return None


async def create_pool(dsn: str | None = None) -> tuple[DbPool, DatabaseConfig]:
    if dsn and dsn.startswith("sqlite:///"):
        path_str = dsn.replace("sqlite:///", "", 1)
        sqlite_path = Path(path_str)
        if not sqlite_path.is_absolute():
            from database.db_config import BACKEND_DIR
            sqlite_path = (BACKEND_DIR / sqlite_path).resolve()
        config = DatabaseConfig(backend=DbBackend.SQLITE, dsn=dsn, sqlite_path=sqlite_path)
    elif dsn and dsn.startswith("postgresql"):
        config = DatabaseConfig(
            backend=DbBackend.POSTGRESQL,
            dsn=dsn.replace("postgresql+asyncpg://", "postgresql://", 1),
        )
    else:
        config = resolve_database_config()

    if config.backend == DbBackend.SQLITE:
        if not sqlite_allowed():
            raise RuntimeError("SQLite is not allowed when ENVIRONMENT=production")
        path = config.sqlite_path or DEFAULT_SQLITE_PATH
        pool = await create_sqlite_pool(path)
        return pool, config

    pool = await _try_postgres_pool(config.dsn)
    if pool is not None:
        return pool, config

    if sqlite_allowed():
        fallback_config = DatabaseConfig(
            backend=DbBackend.SQLITE,
            dsn=f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}",
            sqlite_path=DEFAULT_SQLITE_PATH,
            fallback_used=True,
        )
        sqlite_pool = await create_sqlite_pool(DEFAULT_SQLITE_PATH)
        return sqlite_pool, fallback_config

    raise RuntimeError(f"Could not connect to PostgreSQL at {config.dsn}.")


async def close_pool(pool: DbPool) -> None:
    if isinstance(pool, SQLitePool):
        await close_sqlite_pool(pool)
    else:
        await pool.close()


def get_pool(request: Request) -> DbPool:
    return request.app.state.db_pool


async def get_conn(request: Request) -> AsyncGenerator[Any, None]:
    pool: DbPool = request.app.state.db_pool
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def acquire_conn(pool: DbPool) -> AsyncGenerator[Any, None]:
    async with pool.acquire() as conn:
        yield conn
