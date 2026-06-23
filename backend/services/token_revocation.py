"""JWT revocation helpers — token_revocations table."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status


async def is_token_revoked(conn: Any, jti: str) -> bool:
    """Return True when jti is present in token_revocations and not yet expired."""
    if not jti:
        return False
    try:
        jti_val: str | uuid.UUID = uuid.UUID(jti)
    except ValueError:
        jti_val = jti
    row = await conn.fetchval(
        """SELECT 1 FROM token_revocations
           WHERE jti = $1 AND expires_at > $2
           LIMIT 1""",
        jti_val,
        datetime.now(timezone.utc),
    )
    return row is not None


async def assert_token_not_revoked(conn: Any, jti: str) -> None:
    if await is_token_revoked(conn, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked — please sign in again",
        )


async def revoke_token(
    conn: Any,
    *,
    jti: str,
    user_id: str | uuid.UUID,
    expires_at: datetime,
) -> None:
    """Record a revoked JWT jti (idempotent)."""
    try:
        jti_val: str | uuid.UUID = uuid.UUID(jti)
    except ValueError:
        jti_val = jti
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    await conn.execute(
        """INSERT INTO token_revocations (jti, user_id, expires_at)
           VALUES ($1, $2, $3)
           ON CONFLICT (jti) DO NOTHING""",
        jti_val,
        uid,
        expires_at,
    )
