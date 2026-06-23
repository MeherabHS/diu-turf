"""Notification routes — Expo push token registration."""
from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from database.connection import get_conn
from services.auth_dep import get_current_user
from services.push import is_valid_expo_push_token, upsert_push_token

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
log = logging.getLogger(__name__)


class PushTokenRequest(BaseModel):
    expo_push_token: str = Field(..., min_length=20)
    platform: str | None = Field(default=None, max_length=20)


@router.post("/push-token", status_code=status.HTTP_200_OK)
async def register_push_token(
    payload: PushTokenRequest,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
) -> dict:
    """Register the current user's Expo push token (upsert)."""
    token = payload.expo_push_token.strip()
    if not is_valid_expo_push_token(token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Expo push token format.",
        )

    user_id = UUID(user["user_id"])
    platform = (payload.platform or "").strip().lower() or None

    await upsert_push_token(
        conn,
        user_id=user_id,
        expo_push_token=token,
        platform=platform,
    )
    log.info("[PUSH] token registered user_id=%s platform=%s", user_id, platform)
    return {"ok": True}
