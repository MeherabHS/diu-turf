"""Database mode detection — PostgreSQL (production) vs SQLite (local dev)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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


@dataclass(frozen=True)
class PostgresConnectionParams:
    """Normalized PostgreSQL DSN + SSL flag for asyncpg / SQLAlchemy async."""

    dsn: str
    ssl: bool | None = None


def prepare_postgres_connection(raw_dsn: str) -> PostgresConnectionParams:
    """Normalize a PostgreSQL URL for asyncpg and resolve SSL settings."""
    clean = raw_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)

    ssl_override = os.getenv("DATABASE_SSL", "").strip().lower()
    if ssl_override in ("1", "true", "yes", "require"):
        ssl: bool | None = True
    elif ssl_override in ("0", "false", "no", "disable"):
        ssl = False
    else:
        ssl = None

    parsed = urlparse(clean)
    query = parse_qs(parsed.query, keep_blank_values=False)

    sslmode_vals = query.pop("sslmode", [])
    sslmode = (sslmode_vals[0] if sslmode_vals else "").lower()
    ssl_vals = query.pop("ssl", [])
    ssl_param = (ssl_vals[0] if ssl_vals else "").lower()

    if ssl is None:
        if sslmode in ("require", "verify-ca", "verify-full", "prefer"):
            ssl = True
        elif sslmode == "disable":
            ssl = False
        elif ssl_param in ("true", "1", "require"):
            ssl = True
        elif ssl_param in ("false", "0", "disable"):
            ssl = False

    flat_query: list[tuple[str, str]] = []
    for key, values in sorted(query.items()):
        for value in values:
            flat_query.append((key, value))
    new_query = urlencode(flat_query)
    clean_dsn = urlunparse(parsed._replace(query=new_query))

    return PostgresConnectionParams(dsn=clean_dsn, ssl=ssl)


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
    environment = os.getenv("ENVIRONMENT", "production").strip().lower()
    return environment != "production"
