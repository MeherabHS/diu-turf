"""CORS configuration from ALLOWED_ORIGINS env."""
from __future__ import annotations

import os


def parse_allowed_origins() -> tuple[list[str], bool]:
    """Return (origins, allow_credentials).

    In development, ``*`` is allowed with credentials disabled.
    In production, explicit origins are required; ``*`` is rejected.
    """
    env = os.getenv("ENVIRONMENT", "production").strip().lower()
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()

    if not raw:
        if env == "development":
            return ["*"], False
        raise RuntimeError(
            "ALLOWED_ORIGINS must be set in production (comma-separated origins)."
        )

    if raw == "*":
        if env == "development":
            return ["*"], False
        raise RuntimeError("ALLOWED_ORIGINS=* is not allowed when ENVIRONMENT=production.")

    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        raise RuntimeError("ALLOWED_ORIGINS is empty after parsing.")
    return origins, True
