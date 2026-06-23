"""Activity-feed + notifications HTTP routes (PostgreSQL)."""
from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from database.connection import get_conn
from services.auth_dep import get_current_user
from services.serialize import serialize_dt

router = APIRouter(tags=["activity"])

_ACTION_MAP = {
    "booking.created": "BOOKED",
    "booking.cancelled": "CANCELLED",
}


def _meta_dict(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_action(event_type: str) -> str:
    if event_type in _ACTION_MAP:
        return _ACTION_MAP[event_type]
    upper = event_type.upper().replace(".", "_")
    if upper in ("BOOKED", "CANCELLED", "COMPLETED", "EXPIRED"):
        return upper
    return upper


@router.get("/api/activity")
async def recent_activity(
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    is_admin = user.get("role") in ("admin", "super_admin")
    if is_admin:
        rows = await conn.fetch(
            """SELECT al.id, al.actor_user_id, al.event_type, al.message,
                      al.metadata, al.created_at,
                      u.name  AS student_name,
                      u.student_id
               FROM activity_logs al
               LEFT JOIN users u ON u.id = al.actor_user_id
               ORDER BY al.created_at DESC
               LIMIT $1""",
            limit,
        )
    else:
        uid = uuid.UUID(user["user_id"])
        rows = await conn.fetch(
            """SELECT al.id, al.actor_user_id, al.event_type, al.message,
                      al.metadata, al.created_at,
                      u.name  AS student_name,
                      u.student_id
               FROM activity_logs al
               LEFT JOIN users u ON u.id = al.actor_user_id
               WHERE al.actor_user_id = $1
                 AND al.event_type IN ('booking.created', 'booking.cancelled', 'booking.completed')
               ORDER BY al.created_at DESC
               LIMIT $2""",
            uid,
            limit,
        )
    items = []
    for r in rows:
        meta = _meta_dict(r["metadata"])
        slot_key = meta.get("slot_key")
        booking_date = meta.get("booking_date")
        message = (r["message"] or "").strip()
        action = _normalize_action(r["event_type"])
        items.append({
            "activity_id":  str(r["id"]),
            "event_type":   r["event_type"],
            "action":       action,
            "user_id":      str(r["actor_user_id"]) if r["actor_user_id"] else None,
            "student_name": r["student_name"] or "",
            "student_id":   r["student_id"],
            "message":      message,
            "slot_id":      slot_key,
            "slot_label":   f"Slot {slot_key}" if slot_key else None,
            "booking_date": str(booking_date)[:10] if booking_date else None,
            "metadata":     meta,
            "created_at":   serialize_dt(r["created_at"]),
        })
    return items


@router.get("/api/notifications/me")
async def my_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    uid = uuid.UUID(user["user_id"])
    rows = await conn.fetch(
        """SELECT id, user_id, title, body, type, is_read, created_at
           FROM notifications
           WHERE user_id = $1
           ORDER BY created_at DESC
           LIMIT $2""",
        uid, limit,
    )
    return [
        {
            "notification_id": str(r["id"]),
            "user_id":         str(r["user_id"]),
            "title":           r["title"],
            "message":         r["body"],
            "body":            r["body"],
            "kind":            r["type"],
            "type":            r["type"],
            "read":            r["is_read"],
            "is_read":         r["is_read"],
            "created_at":      serialize_dt(r["created_at"]),
        }
        for r in rows
    ]


@router.put("/api/notifications/{notification_id}/read")
async def mark_read(
    notification_id: str,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Notification not found")

    uid = uuid.UUID(user["user_id"])
    result = await conn.execute(
        "UPDATE notifications SET is_read = TRUE WHERE id = $1 AND user_id = $2",
        nid, uid,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.put("/api/notifications/read-all")
async def mark_all_read(
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    uid = uuid.UUID(user["user_id"])
    result = await conn.execute(
        "UPDATE notifications SET is_read = TRUE WHERE user_id = $1 AND is_read = FALSE",
        uid,
    )
    updated = int(result.split()[-1]) if result else 0
    return {"ok": True, "updated": updated}
