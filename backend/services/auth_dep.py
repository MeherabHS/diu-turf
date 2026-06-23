"""Auth dependencies — JWT Bearer + RBAC (PostgreSQL-only).

MongoDB fallback removed. All user lookups go through asyncpg.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

import asyncpg
from fastapi import Depends, Header, HTTPException, status

from database.connection import get_conn
from services.jwt_util import decode_token
from services.profile_util import compute_profile_completed

log = logging.getLogger(__name__)


def _pg_row_to_user_dict(row: asyncpg.Record) -> dict:
    """Normalise a PostgreSQL users row to the common dict shape used by routes."""
    d = dict(row)
    d["user_id"]         = str(d["id"])
    d["picture"]         = d.pop("avatar_url", None)
    d["profile_completed"] = compute_profile_completed(d)

    sus_until  = d.get("suspension_until")
    sus_reason = d.get("suspension_reason")
    d["suspension"] = (
        {"until": sus_until, "reason": sus_reason}
        if sus_until is not None else None
    )
    return d


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    conn: asyncpg.Connection = Depends(get_conn),
) -> dict:
    """Authenticate against PostgreSQL. Used by all routes."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)

    user_id_str = payload.get("sub", "")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session format")

    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_uuid)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    return _pg_row_to_user_dict(row)


# Alias kept so Phase 4 routes that already import get_current_user_pg still compile.
get_current_user_pg = get_current_user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


require_admin_pg = require_admin
