"""Expo push notifications — best-effort delivery for waitlist promotion."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

log = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
PUSH_CHANNEL_ID = "booking-updates"

VALID_TOKEN_PREFIXES = ("ExponentPushToken[", "ExpoPushToken[")


def is_valid_expo_push_token(token: str) -> bool:
    token = (token or "").strip()
    return any(token.startswith(prefix) for prefix in VALID_TOKEN_PREFIXES)


async def upsert_push_token(
    conn: Any,
    *,
    user_id: UUID,
    expo_push_token: str,
    platform: str | None,
) -> None:
    """Register or refresh an Expo push token for a user."""
    now = datetime.now(timezone.utc)
    await conn.execute(
        """INSERT INTO user_push_tokens
               (user_id, expo_push_token, platform, is_active, created_at, updated_at)
           VALUES ($1, $2, $3, TRUE, $4, $4)
           ON CONFLICT (user_id, expo_push_token) DO UPDATE SET
               platform   = EXCLUDED.platform,
               is_active  = TRUE,
               updated_at = EXCLUDED.updated_at""",
        user_id,
        expo_push_token.strip(),
        platform,
        now,
    )


async def _deactivate_token(conn: Any, token_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    await conn.execute(
        "UPDATE user_push_tokens SET is_active = FALSE, updated_at = $2 WHERE id = $1",
        token_id,
        now,
    )


async def send_push_to_user(
    conn: Any,
    *,
    user_id: UUID,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Send push to all active Expo tokens for a user. Never raises."""
    try:
        rows = await conn.fetch(
            """SELECT id, expo_push_token
               FROM user_push_tokens
               WHERE user_id = $1 AND is_active = TRUE""",
            user_id,
        )
        if not rows:
            log.debug("[PUSH] no active tokens for user_id=%s", user_id)
            return

        messages = [
            {
                "to": row["expo_push_token"],
                "title": title,
                "body": body,
                "data": data or {},
                "channelId": PUSH_CHANNEL_ID,
                "sound": "default",
            }
            for row in rows
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            payload = resp.json()

        tickets = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(tickets, list):
            log.warning("[PUSH] unexpected Expo response for user_id=%s: %s", user_id, payload)
            return

        for row, ticket in zip(rows, tickets, strict=False):
            if not isinstance(ticket, dict):
                continue
            if ticket.get("status") == "ok":
                continue
            details = ticket.get("details") or {}
            err = details.get("error") or ticket.get("message") or ""
            if err == "DeviceNotRegistered":
                log.info("[PUSH] deactivating stale token id=%s user_id=%s", row["id"], user_id)
                await _deactivate_token(conn, row["id"])
            else:
                log.warning(
                    "[PUSH] send failed user_id=%s token_id=%s error=%s",
                    user_id,
                    row["id"],
                    err or ticket,
                )
    except Exception:
        log.exception("[PUSH] send_push_to_user failed user_id=%s (non-fatal)", user_id)


async def notify_waitlist_promoted(
    conn: Any,
    *,
    user_id: UUID,
    booking_id: UUID,
    booking_date: Any,
    slot_template_id: UUID,
) -> None:
    """Push notification when a waitlisted user is promoted. Best-effort."""
    bdate = booking_date.isoformat() if hasattr(booking_date, "isoformat") else str(booking_date)
    await send_push_to_user(
        conn,
        user_id=user_id,
        title="Slot confirmed",
        body="Your waitlisted turf slot is now confirmed.",
        data={
            "type": "waitlist.promoted",
            "booking_id": str(booking_id),
            "date": bdate[:10] if len(bdate) >= 10 else bdate,
            "slot_template_id": str(slot_template_id),
        },
    )
