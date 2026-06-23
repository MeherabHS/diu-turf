"""Database mode detection — PostgreSQL (production) vs SQLite (local dev)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BACKEND_DIR / "dev_turf.db"


class DbBackend(str, Enum):
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


@dataclass(frozen=True)
class DatabaseConfig:
    backend: DbBackend
    dsn: str
    sqlite_path: Path | None = None
    fallback_used: bool = False


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def resolve_database_config() -> DatabaseConfig:
    """Resolve which database backend to use from environment variables."""
    raw_url = os.getenv("DATABASE_URL", "").strip()
    environment = os.getenv("ENVIRONMENT", "production").strip().lower()

    if raw_url.startswith("sqlite:///"):
        path_str = raw_url.replace("sqlite:///", "", 1)
        sqlite_path = Path(path_str)
        if not sqlite_path.is_absolute():
            sqlite_path = BACKEND_DIR / sqlite_path
        return DatabaseConfig(
            backend=DbBackend.SQLITE,
            dsn=f"sqlite:///{sqlite_path.as_posix()}",
            sqlite_path=sqlite_path,
        )

    if raw_url.startswith("postgresql://") or raw_url.startswith("postgresql+asyncpg://"):
        return DatabaseConfig(
            backend=DbBackend.POSTGRESQL,
            dsn=raw_url.replace("postgresql+asyncpg://", "postgresql://", 1),
        )

    # No DATABASE_URL — default to SQLite in development, otherwise require PostgreSQL.
    if environment != "production":
        return DatabaseConfig(
            backend=DbBackend.SQLITE,
            dsn=f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}",
            sqlite_path=DEFAULT_SQLITE_PATH,
            fallback_used=True,
        )

    raise RuntimeError(
        "DATABASE_URL is required in production. "
        "Set postgresql://… or use ENVIRONMENT=development for SQLite."
    )


def sqlite_allowed() -> bool:
    """SQLite is never allowed when ENVIRONMENT=production."""
    environment = os.getenv("ENVIRONMENT", "production").strip().lower()
    return environment != "production"
