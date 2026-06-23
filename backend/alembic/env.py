"""Alembic migration environment.

Runs migrations asynchronously using SQLAlchemy's async engine + asyncpg.

The DATABASE_URL environment variable always takes precedence over the
placeholder URL in alembic.ini, so you never need to edit alembic.ini.

Usage
─────
    cd backend
    alembic upgrade head          # apply all pending migrations
    alembic downgrade -1          # roll back one step
    alembic current               # show applied revision
    alembic revision --autogenerate -m "add column foo"  # new migration
    alembic upgrade head --sql    # dry-run: print SQL without executing
"""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Alembic config object ────────────────────────────────────────────────────
alembic_cfg = context.config

if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

# ── Override URL from DATABASE_URL env var (12-factor) ───────────────────────
_raw_url = os.environ.get("DATABASE_URL", "")
if _raw_url:
    # Normalise: asyncpg dialect prefix expected by SQLAlchemy async engine.
    if not _raw_url.startswith("postgresql+asyncpg://"):
        _raw_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    alembic_cfg.set_main_option("sqlalchemy.url", _raw_url)

# No ORM metadata — all migrations are written as raw SQL via op.execute().
target_metadata = None


# ── Migration runners ─────────────────────────────────────────────────────────

def _do_run_migrations(sync_conn) -> None:
    """Configure and run migrations against a synchronous connection wrapper."""
    context.configure(
        connection=sync_conn,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_online() -> None:
    """Connect to the live database and apply migrations."""
    connectable = async_engine_from_config(
        alembic_cfg.get_section(alembic_cfg.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # single-use connection for migrations
    )
    async with connectable.connect() as async_conn:
        await async_conn.run_sync(_do_run_migrations)
    await connectable.dispose()


def _run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (dry-run / CI)."""
    url = alembic_cfg.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Entry point ───────────────────────────────────────────────────────────────
if context.is_offline_mode():
    _run_migrations_offline()
else:
    asyncio.run(_run_migrations_online())
