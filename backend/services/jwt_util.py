"""JWT helpers — sign + verify HS256 tokens.

Phase 4 changes:
  - Added 'jti' (JWT ID) claim: a unique UUID per token.
    Used with the token_revocations table for logout revocation.
  - All other behaviour unchanged.

Stateless sessions: the JWT is the session.  Expiry is enforced by 'exp'.
True logout (before exp) requires recording the jti in token_revocations
and checking it on every authenticated request (Phase 6 enhancement).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_DAYS = int(os.environ.get("JWT_EXPIRES_DAYS", "7"))


def issue_token(user_id: str, email: str, role: str) -> tuple[str, datetime]:
    """Sign and return a JWT plus its expiry datetime.

    Claims:
      sub   — user UUID (string)
      email — verified email address
      role  — 'student' | 'admin' | 'super_admin'
      iat   — issued-at (Unix timestamp)
      exp   — expiry (Unix timestamp, JWT_EXPIRES_DAYS from now)
      jti   — unique token ID (UUID4) for revocation support
    """
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=JWT_EXPIRES_DAYS)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4()),   # unique per-token ID for revocation
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), exp


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT.  Raises HTTP 401 on any failure."""
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please sign in again",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        ) from exc
