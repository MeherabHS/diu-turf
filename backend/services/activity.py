"""Activity-feed + notification helpers — PostgreSQL (asyncpg)."""
from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

import asyncpg

log = logging.getLogger(__name__)


async def log_activity(
    conn: asyncpg.Connection,
    *,
    event_type: str,
    actor_user_id: UUID | str | None,
    message: str,
    metadata: dict | None = None,
) -> None:
    """Insert one row into activity_logs (fire-and-forget, never raises)."""
    uid = UUID(str(actor_user_id)) if actor_user_id else None
    try:
        await conn.execute(
            """INSERT INTO activity_logs (actor_user_id, event_type, message, metadata)
               VALUES ($1, $2, $3, $4::jsonb)""",
            uid,
            event_type,
            message,
            json.dumps(metadata or {}),
        )
    except Exception:
        log.exception("activity_log write failed: event_type=%s", event_type)


async def add_notification(
    conn: asyncpg.Connection,
    *,
    user_id: UUID | str,
    title: str,
    body: str,
    type_: str = "system",
) -> None:
    """Insert one notification row (fire-and-forget, never raises)."""
    uid = UUID(str(user_id)) if isinstance(user_id, str) else user_id
    try:
        await conn.execute(
            """INSERT INTO notifications (user_id, title, body, type)
               VALUES ($1, $2, $3, $4)""",
            uid, title, body, type_,
        )
    except Exception:
        log.exception("notification write failed for user_id=%s", user_id)


async def fan_out_notification(
    conn: asyncpg.Connection,
    *,
    title: str,
    body: str,
    type_: str = "announcement",
    roles: tuple[str, ...] = ("student",),
) -> int:
    """Insert a notification for every active user with a matching role.

    Returns the number of rows inserted.
    Used by admin announcements.
    """
    rows = await conn.fetch(
        "SELECT id FROM users WHERE role = ANY($1::text[]) AND is_active = TRUE",
        list(roles),
    )
    count = 0
    for r in rows:
        try:
            await conn.execute(
                """INSERT INTO notifications (user_id, title, body, type)
                   VALUES ($1, $2, $3, $4)""",
                r["id"], title, body, type_,
            )
            count += 1
        except Exception:
            log.exception("fan_out notification failed for user_id=%s", r["id"])
    return count
