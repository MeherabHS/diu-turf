"""Booking access request routes — viewer → booker approval flow."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database.connection import get_conn
from services.auth_dep import get_current_user, require_admin
from services.permissions import can_book
from services.serialize import serialize_dt

router = APIRouter(tags=["access-requests"])

AccessRequestStatus = Literal["pending", "approved", "rejected"]


class AccessRequestCreate(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


def _row_to_dict(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "name": row["name"],
        "email": row["email"],
        "student_id": row["student_id"],
        "reason": row["reason"],
        "status": row["status"],
        "reviewed_by": str(row["reviewed_by"]) if row["reviewed_by"] else None,
        "reviewed_at": serialize_dt(row["reviewed_at"]) if row["reviewed_at"] else None,
        "created_at": serialize_dt(row["created_at"]),
        "updated_at": serialize_dt(row["updated_at"]),
    }


@router.post("/api/access-requests", status_code=201)
async def create_access_request(
    payload: AccessRequestCreate,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    if can_book(user):
        raise HTTPException(400, "Your account already has booking access.")

    uid = uuid.UUID(user["user_id"])
    pending = await conn.fetchval(
        "SELECT id FROM booking_access_requests WHERE user_id = $1 AND status = 'pending'",
        uid,
    )
    if pending:
        raise HTTPException(409, "You already have a pending booking access request.")

    reason = (payload.reason or "").strip() or None
    now = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        """INSERT INTO booking_access_requests
               (user_id, name, email, student_id, reason, status, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, 'pending', $6, $6)
           RETURNING *""",
        uid,
        user.get("name") or "",
        user.get("email") or "",
        user.get("student_id"),
        reason,
        now,
    )
    return _row_to_dict(row)


@router.get("/api/access-requests/me")
async def my_access_request(
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    uid = uuid.UUID(user["user_id"])
    row = await conn.fetchrow(
        """SELECT * FROM booking_access_requests
           WHERE user_id = $1
           ORDER BY created_at DESC
           LIMIT 1""",
        uid,
    )
    if not row:
        return None
    return _row_to_dict(row)


@router.get("/api/admin/access-requests")
async def list_access_requests(
    status: Optional[AccessRequestStatus] = Query(default=None),
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    if status:
        rows = await conn.fetch(
            """SELECT * FROM booking_access_requests
               WHERE status = $1
               ORDER BY created_at DESC
               LIMIT 200""",
            status,
        )
    else:
        rows = await conn.fetch(
            """SELECT * FROM booking_access_requests
               ORDER BY created_at DESC
               LIMIT 200""",
        )
    return [_row_to_dict(r) for r in rows]


@router.post("/api/admin/access-requests/{request_id}/approve")
async def approve_access_request(
    request_id: str,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(404, "Request not found")

    admin_id = uuid.UUID(admin["user_id"])
    now = datetime.now(timezone.utc)

    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM booking_access_requests WHERE id = $1 FOR UPDATE",
            rid,
        )
        if not row:
            raise HTTPException(404, "Request not found")
        if row["status"] != "pending":
            raise HTTPException(409, f"Request is already {row['status']}.")

        await conn.execute(
            """UPDATE booking_access_requests
               SET status = 'approved', reviewed_by = $2, reviewed_at = $3, updated_at = $3
               WHERE id = $1""",
            rid,
            admin_id,
            now,
        )
        await conn.execute(
            """UPDATE users SET role = 'booker', updated_at = $2
               WHERE id = $1 AND role NOT IN ('admin', 'super_admin')""",
            row["user_id"],
            now,
        )
        updated = await conn.fetchrow(
            "SELECT * FROM booking_access_requests WHERE id = $1",
            rid,
        )

    return _row_to_dict(updated)


@router.post("/api/admin/access-requests/{request_id}/reject")
async def reject_access_request(
    request_id: str,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(404, "Request not found")

    admin_id = uuid.UUID(admin["user_id"])
    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        "SELECT status FROM booking_access_requests WHERE id = $1",
        rid,
    )
    if not row:
        raise HTTPException(404, "Request not found")
    if row["status"] != "pending":
        raise HTTPException(409, f"Request is already {row['status']}.")

    updated = await conn.fetchrow(
        """UPDATE booking_access_requests
           SET status = 'rejected', reviewed_by = $2, reviewed_at = $3, updated_at = $3
           WHERE id = $1
           RETURNING *""",
        rid,
        admin_id,
        now,
    )
    return _row_to_dict(updated)
