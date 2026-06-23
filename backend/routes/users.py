"""User profile routes (PostgreSQL)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from database.connection import get_conn
from services.auth_dep import _pg_row_to_user_dict, get_current_user
from services.models import AuthMeResponse, ProfileUpdate, User
from services.profile_util import compute_profile_completed

router = APIRouter(prefix="/api/users", tags=["users"])

STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9\-]{3,32}$")


def _row_to_user(row: asyncpg.Record) -> User:
    d = _pg_row_to_user_dict(row)
    return User(
        user_id           = d["user_id"],
        email             = d["email"],
        name              = d["name"],
        picture           = d.get("picture"),
        google_sub        = d.get("google_sub"),
        role              = d["role"],
        student_id        = d.get("student_id"),
        department        = d.get("department"),
        batch             = d.get("batch"),
        room_number       = d.get("room_number"),
        hostel_name       = d.get("hostel_name"),
        phone             = d.get("phone"),
        profile_completed = d["profile_completed"],
        created_at        = d["created_at"],
        last_login        = d.get("last_login"),
        updated_at        = d["updated_at"],
    )


async def _apply_profile_update(
    payload: ProfileUpdate,
    user: dict,
    conn: asyncpg.Connection,
) -> AuthMeResponse:
    name = payload.name.strip()
    sid = payload.student_id.strip()
    department = payload.department.strip()
    batch = payload.batch.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Full name is required")
    if not STUDENT_ID_RE.match(sid):
        raise HTTPException(status_code=400, detail="Invalid student_id format (3-32 alphanumeric)")
    if not department:
        raise HTTPException(status_code=400, detail="Department is required")
    if not batch:
        raise HTTPException(status_code=400, detail="Batch is required")

    uid = uuid.UUID(user["user_id"])
    clash = await conn.fetchval(
        "SELECT id FROM users WHERE student_id = $1 AND id != $2",
        sid, uid,
    )
    if clash:
        raise HTTPException(status_code=409, detail="This student ID is already registered")

    room_number = payload.room_number.strip() if payload.room_number else None
    hostel_name = payload.hostel_name.strip() if payload.hostel_name else None
    phone = payload.phone.strip() if payload.phone else None
    now = datetime.now(timezone.utc)

    await conn.execute(
        """UPDATE users SET
               name = $2,
               student_id = $3,
               department = $4,
               batch = $5,
               room_number = $6,
               hostel_name = $7,
               phone = $8,
               updated_at = $9
           WHERE id = $1""",
        uid,
        name,
        sid,
        department,
        batch,
        room_number,
        hostel_name,
        phone,
        now,
    )
    fresh = await conn.fetchrow("SELECT * FROM users WHERE id = $1", uid)
    return AuthMeResponse(user=_row_to_user(fresh))


@router.put("/profile", response_model=AuthMeResponse)
async def update_profile(
    payload: ProfileUpdate,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await _apply_profile_update(payload, user, conn)


@router.put("/me", response_model=AuthMeResponse, include_in_schema=False)
async def update_profile_me(
    payload: ProfileUpdate,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await _apply_profile_update(payload, user, conn)
