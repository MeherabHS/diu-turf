"""Production startup validation — fail fast on unsafe configuration."""
from __future__ import annotations

import os

from database.db_config import DbBackend, DatabaseConfig

_WEAK_JWT_SECRETS = frozenset({
    "",
    "change_me_to_a_long_random_secret",
    "test-secret",
    "test-secret-phase4",
    "test-secret-password-auth",
    "secret",
    "dev-secret",
})


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def validate_production_config(db_config: DatabaseConfig) -> None:
    """Raise RuntimeError when production env has unsafe settings."""
    env = os.getenv("ENVIRONMENT", "production").strip().lower()
    if env != "production":
        return

    errors: list[str] = []

    jwt_secret = os.getenv("JWT_SECRET", "").strip()
    if len(jwt_secret) < 32 or jwt_secret in _WEAK_JWT_SECRETS:
        errors.append("JWT_SECRET must be a strong random secret (≥32 chars, not a default)")

    if _is_truthy(os.getenv("DEV_AUTH_ENABLED")):
        errors.append("DEV_AUTH_ENABLED must be false in production")

    if db_config.backend == DbBackend.SQLITE:
        errors.append("DATABASE_URL must be PostgreSQL in production (SQLite is not allowed)")

    allowed = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not allowed or allowed == "*":
        errors.append("ALLOWED_ORIGINS must list explicit origins in production")

    if errors:
        raise RuntimeError("Production configuration invalid: " + "; ".join(errors))
