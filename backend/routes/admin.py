"""Admin routes (PostgreSQL-only)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from database.booking_tx import BookingError, cancel_booking, promote_from_waitlist
from services.push import notify_waitlist_promoted
from database.connection import get_conn
from database.exceptions import UniqueViolationError
from services.activity import add_notification, fan_out_notification, log_activity
from services.auth_dep import get_current_user, require_admin
from services.serialize import parse_dt, serialize_dt
from services.models import BookingCreate, WaitlistEntry, WaitlistJoin
from services.uuid_util import uuid_same
from services.slot_cache import load_slot_cache
from services.turf_schedule import (
    MAIN_TURF_NAME,
    active_slot_count,
    coerce_db_time,
    is_future_slot,
    now_turf,
    parse_booking_date,
    parse_hhmm,
    resolve_slot,
    time_ranges_overlap,
)
from services.ws_manager import ws_manager

router = APIRouter(prefix="/api", tags=["admin"])
log = logging.getLogger(__name__)


# ── Shared helpers ─────────────────────────────────────────────────────────────

async def _audit(
    conn: asyncpg.Connection,
    *,
    admin: dict,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict | None = None,
) -> None:
    admin_uuid = uuid.UUID(admin["user_id"])
    try:
        tid = uuid.UUID(target_id) if target_id else None
    except ValueError:
        tid = None
    await conn.execute(
        """INSERT INTO audit_logs (admin_id, action, target_type, target_id, metadata)
           VALUES ($1, $2, $3, $4, $5::jsonb)""",
        admin_uuid, action, target_type, tid, json.dumps(metadata or {}),
    )


def _get_turf_state(request: Request):
    turf_id = getattr(request.app.state, "default_turf_id", None)
    if turf_id is None:
        raise HTTPException(503, "Turf not configured")
    return (
        turf_id,
        request.app.state.slot_template_ids,
        request.app.state.slot_templates,
    )


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/admin/kpis")
async def admin_kpis(
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    turf_id, _, slot_templates = _get_turf_state(request)
    today = now_turf().date()
    now = datetime.now(timezone.utc)
    total_slots = active_slot_count(slot_templates)

    bookings_today = await conn.fetchval(
        "SELECT COUNT(*) FROM bookings WHERE booking_date=$1 AND turf_id=$2 AND status='booked'",
        today, turf_id,
    )
    util_pct = int(round(bookings_today / total_slots * 100)) if total_slots else 0

    active_students = await conn.fetchval(
        """SELECT COUNT(*) FROM users
           WHERE role = 'student' AND is_active = TRUE
             AND (suspension_until IS NULL OR suspension_until <= $1)""",
        now,
    )
    maint_days = await conn.fetchval(
        "SELECT COUNT(*) FROM maintenance_days WHERE date >= $1 AND turf_id=$2",
        today, turf_id,
    )
    waitlist_pending = await conn.fetchval(
        "SELECT COUNT(*) FROM waitlists WHERE status='waiting'",
    )
    upcoming = await conn.fetchval(
        "SELECT COUNT(*) FROM bookings WHERE status='booked' AND booking_date >= $1 AND turf_id=$2",
        today, turf_id,
    )
    att_total   = await conn.fetchval("SELECT COUNT(*) FROM attendance")
    att_present = await conn.fetchval("SELECT COUNT(*) FROM attendance WHERE status='present'")
    att_rate    = int(round(att_present / att_total * 100)) if att_total else 0

    total_bk   = await conn.fetchval("SELECT COUNT(*) FROM bookings")
    cancelled  = await conn.fetchval("SELECT COUNT(*) FROM bookings WHERE status='cancelled'")
    cancel_rate = int(round(cancelled / total_bk * 100)) if total_bk else 0

    return {
        "bookings_today":        bookings_today,
        "utilization_today_pct": util_pct,
        "available_slots_today": max(0, total_slots - bookings_today),
        "active_students":       active_students,
        "maintenance_days":      maint_days,
        "waitlist_pending":      waitlist_pending,
        "upcoming_reservations": upcoming,
        "attendance_rate_pct":   att_rate,
        "cancellation_rate_pct": cancel_rate,
    }


@router.get("/admin/bookings")
async def admin_list_bookings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    total = await conn.fetchval("SELECT COUNT(*) FROM bookings")
    offset = (page - 1) * page_size
    rows = await conn.fetch(
        """SELECT b.id AS booking_id, b.booking_date, b.status, b.created_at,
                  u.name AS student_name, u.email AS student_email, u.student_id,
                  s.slot_key, s.start_time, s.end_time
           FROM bookings b
           JOIN users u ON u.id = b.user_id
           JOIN slot_templates s ON s.id = b.slot_template_id
           ORDER BY b.booking_date DESC, s.start_time DESC
           LIMIT $1 OFFSET $2""",
        page_size,
        offset,
    )
    items = [
        _serialize_booking_row({
            **dict(r),
            "booking_id": r["booking_id"],
            "cancellation_reason": None,
            "cancelled_at": None,
        }) | {
            "student_name": r["student_name"],
            "student_email": r["student_email"],
            "student_id": r["student_id"],
        }
        for r in rows
    ]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
    }


# ── Student management ────────────────────────────────────────────────────────

def _suspension_active(until: Any, now: datetime) -> bool:
    if until is None:
        return False
    if isinstance(until, str):
        until = parse_dt(until)
    if until is None:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until > now


def _student_status(row: dict, now: datetime) -> str:
    if not row.get("is_active", True):
        return "inactive"
    if _suspension_active(row.get("suspension_until"), now):
        return "suspended"
    return "active"


async def _student_aggregate_stats(conn: asyncpg.Connection, now: datetime) -> dict:
    total = await conn.fetchval("SELECT COUNT(*) FROM users")
    suspended = await conn.fetchval(
        """SELECT COUNT(*) FROM users
           WHERE suspension_until IS NOT NULL AND suspension_until > $1""",
        now,
    )
    active = await conn.fetchval(
        """SELECT COUNT(*) FROM users
           WHERE is_active = TRUE
             AND (suspension_until IS NULL OR suspension_until <= $1)""",
        now,
    )
    return {"total": int(total or 0), "active": int(active or 0), "suspended": int(suspended or 0)}


def _audit_description(
    action: str,
    *,
    metadata: Any = None,
    message: str | None = None,
    actor_email: str | None = None,
) -> str:
    meta = metadata if isinstance(metadata, dict) else {}
    if message:
        return message
    if action == "BOOKING_CREATED":
        slot = meta.get("slot_key")
        bdate = meta.get("booking_date")
        if slot and bdate:
            return f"Booking created — Slot {slot} on {bdate}"
        return "Booking created"
    if action in ("BOOKING_CANCELLED", "BOOKING_FORCE_CANCELLED"):
        bdate = meta.get("booking_date")
        if bdate:
            return f"Booking cancelled on {bdate}"
        return "Booking cancelled"
    if action == "STUDENT_SUSPENDED":
        reason = meta.get("reason") or "No reason given"
        return f"User suspended — {reason}"
    if action == "STUDENT_DEACTIVATED":
        return "User deactivated"
    if action == "STUDENT_DELETED":
        reason = meta.get("reason") or "No reason given"
        return f"User deleted — {reason}"
    if action == "STUDENT_PROFILE_UPDATED":
        return "User profile updated by admin"
    if action in ("STUDENT_ACTIVATED", "STUDENT_UNSUSPENDED"):
        return "User activated"
    return action.replace("_", " ").title()


def _booking_history_sql(status_filter: str) -> str:
    return f"""
        SELECT b.id AS booking_id, b.booking_date, b.status, b.created_at, b.cancelled_at,
               b.cancellation_reason, s.slot_key, s.start_time, s.end_time
        FROM bookings b
        JOIN slot_templates s ON s.id = b.slot_template_id
        WHERE b.user_id = $1 AND b.status = '{status_filter}'
        ORDER BY b.booking_date DESC, s.start_time DESC
        LIMIT 100
    """


def _serialize_booking_row(r: dict) -> dict:
    bdate = r["booking_date"]
    if hasattr(bdate, "isoformat"):
        bdate = bdate.isoformat()[:10]
    start = r["start_time"]
    end = r["end_time"]
    if hasattr(start, "strftime"):
        start = start.strftime("%H:%M")
    if hasattr(end, "strftime"):
        end = end.strftime("%H:%M")
    return {
        "booking_id":           str(r["booking_id"]),
        "booking_date":         str(bdate),
        "slot_id":              r["slot_key"],
        "slot_label":           f"Slot {r['slot_key']}",
        "time_range":           f"{start}–{end}",
        "status":               r["status"],
        "created_at":           serialize_dt(r["created_at"]),
        "cancelled_at":         serialize_dt(r.get("cancelled_at")),
        "cancellation_reason":  r.get("cancellation_reason"),
    }


@router.get("/admin/students")
async def admin_students(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    department: str | None = Query(default=None),
    batch: str | None = Query(default=None),
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    now = datetime.now(timezone.utc)
    conditions: list[str] = []
    params: list = []

    if q:
        term = q.strip()
        params.append(f"%{term}%")
        idx = len(params)
        id_clause = ""
        try:
            uid = uuid.UUID(term)
            params.append(uid)
            id_clause = f" OR id = ${len(params)}"
        except ValueError:
            pass
        conditions.append(
            f"(LOWER(name) LIKE LOWER(${idx}) "
            f"OR LOWER(COALESCE(student_id, '')) LIKE LOWER(${idx}) "
            f"OR LOWER(email) LIKE LOWER(${idx}){id_clause})"
        )
    if department:
        params.append(department)
        conditions.append(f"department = ${len(params)}")
    if batch:
        params.append(batch)
        conditions.append(f"batch = ${len(params)}")

    where = " AND ".join(conditions) if conditions else "TRUE"
    total = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE {where}", *params)
    offset = (page - 1) * page_size
    params.extend([page_size, offset])
    limit_idx = len(params) - 1
    offset_idx = len(params)

    rows = await conn.fetch(
        f"""SELECT u.id, u.name, u.email, u.student_id, u.role, u.is_active, u.suspension_until,
                   u.department, u.batch, u.room_number, u.created_at,
                   (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) AS booking_count
            FROM users u WHERE {where}
            ORDER BY u.created_at DESC
            LIMIT ${limit_idx} OFFSET ${offset_idx}""",
        *params,
    )
    items = []
    for r in rows:
        suspended = _suspension_active(r["suspension_until"], now)
        items.append({
            "user_id":        str(r["id"]),
            "student_id":     r["student_id"],
            "name":           r["name"],
            "email":          r["email"],
            "department":     r["department"],
            "batch":          r["batch"],
            "room_number":    r["room_number"],
            "created_at":     serialize_dt(r["created_at"]),
            "role":           r["role"],
            "booking_count":  int(r["booking_count"] or 0),
            "status":         _student_status(r, now),
            "suspended":      suspended,
        })

    stats = await _student_aggregate_stats(conn, now)
    return {
        "items":     items,
        "page":      page,
        "page_size": page_size,
        "total":     int(total or 0),
        "stats":     stats,
    }


@router.get("/admin/students/{user_id}")
async def admin_student_detail(
    user_id: str,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(404, "Student not found")

    row = await conn.fetchrow(
        """SELECT id, name, email, student_id, role, department, batch, is_active,
                  suspension_until, suspension_reason, last_login, created_at
           FROM users WHERE id=$1""",
        uid,
    )
    if not row:
        raise HTTPException(404, "User not found")

    now = datetime.now(timezone.utc)
    suspended = _suspension_active(row["suspension_until"], now)
    profile = {
        "user_id":           str(row["id"]),
        "name":              row["name"],
        "email":             row["email"],
        "student_id":        row["student_id"],
        "role":              row["role"],
        "department":        row["department"],
        "batch":             row["batch"],
        "status":            _student_status(row, now),
        "suspended":         suspended,
        "suspension_until":  serialize_dt(row["suspension_until"]),
        "suspension_reason": row["suspension_reason"],
        "last_login":        serialize_dt(row["last_login"]),
        "created_at":        serialize_dt(row["created_at"]),
    }

    booking_count = await conn.fetchval(
        "SELECT COUNT(*) FROM bookings WHERE user_id=$1", uid,
    )
    profile["booking_count"] = int(booking_count or 0)

    booking_rows = await conn.fetch(_booking_history_sql("booked"), uid)
    cancel_rows = await conn.fetch(_booking_history_sql("cancelled"), uid)
    attendance_rows = await conn.fetch(
        """SELECT a.status, a.marked_at, a.note,
                  b.booking_date, s.slot_key, s.start_time, s.end_time
           FROM attendance a
           JOIN bookings b ON b.id = a.booking_id
           JOIN slot_templates s ON s.id = b.slot_template_id
           WHERE b.user_id = $1
           ORDER BY a.marked_at DESC
           LIMIT 100""",
        uid,
    )

    attendance = []
    for r in attendance_rows:
        bdate = r["booking_date"]
        if hasattr(bdate, "isoformat"):
            bdate = bdate.isoformat()[:10]
        start = r["start_time"]
        end = r["end_time"]
        if hasattr(start, "strftime"):
            start = start.strftime("%H:%M")
        if hasattr(end, "strftime"):
            end = end.strftime("%H:%M")
        attendance.append({
            "status":       r["status"],
            "marked_at":    serialize_dt(r["marked_at"]),
            "note":         r["note"],
            "booking_date": str(bdate),
            "slot_id":      r["slot_key"],
            "slot_label":   f"Slot {r['slot_key']}",
            "time_range":   f"{start}–{end}",
        })

    return {
        "profile":       profile,
        "bookings":      [_serialize_booking_row(dict(b)) for b in booking_rows],
        "cancellations": [_serialize_booking_row(dict(b)) for b in cancel_rows],
        "attendance":    attendance,
    }


class SuspendRequest(BaseModel):
    duration: Literal["1d", "7d", "30d", "permanent"]
    reason: str = Field(min_length=3, max_length=500)


@router.post("/admin/students/{user_id}/suspend")
async def admin_suspend(
    user_id: str,
    payload: SuspendRequest,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(404, "Student not found")

    now = datetime.now(timezone.utc)
    until = {
        "1d":  now + timedelta(days=1),
        "7d":  now + timedelta(days=7),
        "30d": now + timedelta(days=30),
    }.get(payload.duration)  # None → permanent

    result = await conn.execute(
        """UPDATE users SET suspension_until=$2, suspension_reason=$3, updated_at=$4
           WHERE id=$1 AND role NOT IN ('admin', 'super_admin')""",
        uid, until, payload.reason, now,
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "User not found or cannot be suspended")

    await _audit(conn, admin=admin, action="STUDENT_SUSPENDED", target_type="user",
                 target_id=user_id, metadata={"duration": payload.duration, "reason": payload.reason})
    return {"ok": True, "until": until.isoformat() if until else "permanent"}


@router.post("/admin/students/{user_id}/unsuspend")
async def admin_unsuspend(
    user_id: str,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await _activate_user(user_id, admin, conn)


@router.post("/admin/students/{user_id}/activate")
async def admin_activate(
    user_id: str,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await _activate_user(user_id, admin, conn)


async def _activate_user(user_id: str, admin: dict, conn: asyncpg.Connection) -> dict:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(404, "User not found")

    now = datetime.now(timezone.utc)
    result = await conn.execute(
        """UPDATE users SET is_active=TRUE, suspension_until=NULL, suspension_reason=NULL,
                  updated_at=$2
           WHERE id=$1 AND role NOT IN ('admin', 'super_admin')""",
        uid, now,
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "User not found or cannot be activated")

    await _audit(conn, admin=admin, action="STUDENT_ACTIVATED", target_type="user", target_id=user_id)
    return {"ok": True}


class AdminStudentProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    email: Optional[str] = Field(default=None, min_length=10)
    student_id: Optional[str] = Field(default=None, min_length=10, max_length=10)
    department: Optional[str] = Field(default=None, min_length=1, max_length=100)
    batch: Optional[str] = Field(default=None, min_length=1, max_length=50)
    room_number: Optional[str] = Field(default=None, max_length=20)
    hostel_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)


class DeleteStudentRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/admin/students/{user_id}/deactivate")
async def admin_deactivate(
    user_id: str,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Deactivate a student account (is_active=false)."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(404, "User not found")

    row = await conn.fetchrow("SELECT email, role FROM users WHERE id=$1", uid)
    if not row or row["role"] in ("admin", "super_admin"):
        raise HTTPException(404, "User not found or cannot be deactivated")

    now = datetime.now(timezone.utc)
    result = await conn.execute(
        """UPDATE users SET is_active=FALSE, updated_at=$2
           WHERE id=$1 AND role NOT IN ('admin', 'super_admin')""",
        uid, now,
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "User not found or cannot be deactivated")

    await _audit(
        conn,
        admin=admin,
        action="STUDENT_DEACTIVATED",
        target_type="user",
        target_id=user_id,
        metadata={"email": str(row["email"])},
    )
    return {"ok": True}


@router.patch("/admin/students/{user_id}/profile")
async def admin_update_student_profile(
    user_id: str,
    payload: AdminStudentProfileUpdate,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Edit a student's profile fields (admin recovery)."""
    from services.registration_util import (
        normalize_email,
        normalize_student_id,
        validate_registration_identity,
        validate_student_id_format,
    )

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(404, "User not found")

    row = await conn.fetchrow("SELECT * FROM users WHERE id=$1", uid)
    if not row:
        raise HTTPException(404, "User not found")
    if row["role"] in ("admin", "super_admin"):
        raise HTTPException(403, "Cannot edit admin accounts via this endpoint")

    updates: dict[str, Any] = {}
    audit_before = {
        "email": str(row["email"]),
        "student_id": row.get("student_id"),
    }

    if payload.name is not None:
        updates["name"] = payload.name.strip()

    final_student_id = (
        normalize_student_id(payload.student_id)
        if payload.student_id is not None
        else (row.get("student_id") or "")
    )
    if payload.student_id is not None:
        sid_err = validate_student_id_format(final_student_id)
        if sid_err:
            raise HTTPException(400, sid_err)
        existing_sid = await conn.fetchval(
            "SELECT id FROM users WHERE student_id = $1 AND id <> $2",
            final_student_id,
            uid,
        )
        if existing_sid:
            raise HTTPException(409, "An account with this student ID already exists.")
        updates["student_id"] = final_student_id

    if payload.email is not None:
        final_email = normalize_email(payload.email)
    elif payload.student_id is not None:
        final_email = f"{final_student_id}@diu.edu.bd"
    else:
        final_email = str(row["email"])

    if payload.email is not None or payload.student_id is not None:
        identity_err = validate_registration_identity(final_email, final_student_id)
        if identity_err:
            raise HTTPException(400, identity_err)
        if final_email != str(row["email"]):
            existing_email = await conn.fetchval(
                "SELECT id FROM users WHERE email = $1 AND id <> $2",
                final_email,
                uid,
            )
            if existing_email:
                raise HTTPException(409, "An account with this email already exists.")
            updates["email"] = final_email

    if payload.department is not None:
        updates["department"] = payload.department.strip()
    if payload.batch is not None:
        updates["batch"] = payload.batch.strip()
    if payload.room_number is not None:
        updates["room_number"] = payload.room_number.strip() or None
    if payload.hostel_name is not None:
        updates["hostel_name"] = payload.hostel_name.strip() or None
    if payload.phone is not None:
        updates["phone"] = payload.phone.strip() or None

    if not updates:
        raise HTTPException(400, "No profile fields to update")

    now = datetime.now(timezone.utc)
    set_clauses = [f"{col} = ${idx + 2}" for idx, col in enumerate(updates)]
    set_clauses.append(f"updated_at = ${len(updates) + 2}")
    params: list[Any] = [uid, *updates.values(), now]

    try:
        await conn.execute(
            f"UPDATE users SET {', '.join(set_clauses)} WHERE id = $1",
            *params,
        )
    except UniqueViolationError as exc:
        constraint = getattr(exc, "constraint_name", "") or ""
        if "email" in constraint:
            raise HTTPException(409, "An account with this email already exists.") from exc
        if "student_id" in constraint:
            raise HTTPException(409, "An account with this student ID already exists.") from exc
        raise HTTPException(409, "An account with these details already exists.") from exc

    await _audit(
        conn,
        admin=admin,
        action="STUDENT_PROFILE_UPDATED",
        target_type="user",
        target_id=user_id,
        metadata={
            "fields": list(updates.keys()),
            "before": audit_before,
            "after": {
                "email": updates.get("email", audit_before["email"]),
                "student_id": updates.get("student_id", audit_before["student_id"]),
            },
        },
    )
    return {"ok": True}


@router.delete("/admin/students/{user_id}")
async def admin_delete_student(
    user_id: str,
    payload: DeleteStudentRequest,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Permanently delete a student account and related rows."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(404, "User not found")

    row = await conn.fetchrow(
        "SELECT id, email, student_id, role, name FROM users WHERE id=$1",
        uid,
    )
    if not row:
        raise HTTPException(404, "User not found")
    if row["role"] in ("admin", "super_admin"):
        raise HTTPException(403, "Cannot delete admin accounts")

    active_booking = await conn.fetchval(
        "SELECT id FROM bookings WHERE user_id=$1 AND status='booked' LIMIT 1",
        uid,
    )
    if active_booking:
        raise HTTPException(
            400,
            "Cannot delete a user with active bookings. Cancel bookings first or suspend the account.",
        )

    async with conn.transaction():
        await conn.execute(
            "UPDATE activity_logs SET actor_user_id = NULL WHERE actor_user_id = $1",
            uid,
        )
        await conn.execute(
            """DELETE FROM attendance
               WHERE booking_id IN (SELECT id FROM bookings WHERE user_id = $1)""",
            uid,
        )
        await conn.execute("DELETE FROM waitlists WHERE user_id = $1", uid)
        await conn.execute("DELETE FROM notifications WHERE user_id = $1", uid)
        await conn.execute("DELETE FROM analytics_events WHERE user_id = $1", uid)
        await conn.execute("DELETE FROM token_revocations WHERE user_id = $1", uid)
        await conn.execute("DELETE FROM bookings WHERE user_id = $1", uid)
        result = await conn.execute("DELETE FROM users WHERE id = $1", uid)
        if result == "DELETE 0":
            raise HTTPException(404, "User not found")

        await _audit(
            conn,
            admin=admin,
            action="STUDENT_DELETED",
            target_type="user",
            target_id=user_id,
            metadata={
                "reason": payload.reason,
                "email": str(row["email"]),
                "student_id": row.get("student_id"),
                "name": row["name"],
            },
        )

    return {"ok": True}


# ── Waitlist (student-facing) ─────────────────────────────────────────────────

def _waitlist_row_to_entry(row: dict) -> WaitlistEntry:
    bdate = row["booking_date"]
    if not isinstance(bdate, str):
        bdate = str(bdate)[:10]
    start = row["start_time"]
    end = row["end_time"]
    if hasattr(start, "strftime"):
        start = start.strftime("%H:%M")
    if hasattr(end, "strftime"):
        end = end.strftime("%H:%M")
    slot_key = row["slot_key"]
    return WaitlistEntry(
        waitlist_id=str(row["id"]),
        booking_date=bdate,
        slot_id=slot_key,
        slot_label=f"Slot {slot_key}",
        start_time=start,
        end_time=end,
        position=row["position"],
        status=row["status"],
        created_at=row["created_at"],
    )


@router.post("/waitlists")
async def join_waitlist(
    payload: WaitlistJoin,
    request: Request,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    if not user.get("profile_completed"):
        raise HTTPException(400, "Complete your profile first")

    sus_until = user.get("suspension", {}) or {}
    if sus_until and sus_until.get("until") and sus_until["until"] > datetime.now(timezone.utc):
        raise HTTPException(403, "Account suspended")

    try:
        bdate = parse_booking_date(payload.booking_date)
    except ValueError as e:
        raise HTTPException(400, "Invalid date") from e

    turf_id, slot_template_ids, slot_templates = _get_turf_state(request)
    slot = resolve_slot(payload.slot_id, slot_templates)
    if not slot or not is_future_slot(bdate, slot):
        raise HTTPException(400, "Slot is in the past or unknown")

    uid = uuid.UUID(user["user_id"])
    stid = slot_template_ids.get(payload.slot_id)
    if not stid:
        raise HTTPException(400, f"Unknown slot_id: {payload.slot_id}")

    # Maintenance check
    maint = await conn.fetchval("SELECT id FROM maintenance_days WHERE turf_id=$1 AND date=$2", turf_id, bdate)
    if maint:
        raise HTTPException(400, "Turf closed for maintenance on this date")

    # Slot must be actively booked by someone else
    active = await conn.fetchrow(
        "SELECT user_id FROM bookings WHERE turf_id=$1 AND slot_template_id=$2 AND booking_date=$3 AND status='booked'",
        turf_id, stid, bdate,
    )
    if not active:
        raise HTTPException(400, "Slot is available — book it instead")
    if uuid_same(active["user_id"], uid):
        raise HTTPException(400, "You already hold this booking")

    # User can't have another booking that day
    existing_booking = await conn.fetchval(
        "SELECT id FROM bookings WHERE user_id=$1 AND booking_date=$2 AND status='booked'",
        uid, bdate,
    )
    if existing_booking:
        raise HTTPException(400, "You already have a booking that day")

    # Position = current waiting count + 1
    pos = await conn.fetchval(
        "SELECT COUNT(*) FROM waitlists WHERE turf_id=$1 AND slot_template_id=$2 AND booking_date=$3 AND status='waiting'",
        turf_id, stid, bdate,
    )
    pos = (pos or 0) + 1

    try:
        wl_id = await conn.fetchval(
            """INSERT INTO waitlists (user_id, turf_id, slot_template_id, booking_date, position)
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            uid, turf_id, stid, bdate, pos,
        )
    except (asyncpg.UniqueViolationError, UniqueViolationError) as e:
        raise HTTPException(409, "Already on this waitlist") from e

    await ws_manager.broadcast({"type": "waitlist.joined", "booking_date": payload.booking_date, "slot_id": payload.slot_id})
    return {"waitlist_id": str(wl_id), "position": pos, "status": "waiting"}


@router.get("/waitlists/me", response_model=list[WaitlistEntry])
async def my_waitlists(
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    uid = uuid.UUID(user["user_id"])
    rows = await conn.fetch(
        """SELECT w.id, w.booking_date, w.position, w.status, w.created_at,
                  s.slot_key, s.start_time, s.end_time
           FROM waitlists w
           JOIN slot_templates s ON s.id = w.slot_template_id
           WHERE w.user_id = $1
           ORDER BY w.created_at DESC
           LIMIT 100""",
        uid,
    )
    return [_waitlist_row_to_entry(dict(r)) for r in rows]


@router.delete("/waitlists/{waitlist_id}")
async def leave_waitlist(
    waitlist_id: str,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        wid = uuid.UUID(waitlist_id)
    except ValueError:
        raise HTTPException(404, "Not found")

    uid = uuid.UUID(user["user_id"])
    row = await conn.fetchrow("SELECT user_id FROM waitlists WHERE id=$1", wid)
    if not row:
        raise HTTPException(404, "Not found")
    if row["user_id"] != uid and user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(403, "Not yours")

    await conn.execute("UPDATE waitlists SET status='cancelled' WHERE id=$1", wid)
    return {"ok": True}


# ── Maintenance ────────────────────────────────────────────────────────────────

class MaintenanceCreate(BaseModel):
    date: str
    reason: str = Field(min_length=3, max_length=200)


@router.get("/maintenance")
async def list_maintenance(
    request: Request,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    turf_id, _, _ = _get_turf_state(request)
    today = datetime.now(timezone.utc).date()
    rows = await conn.fetch(
        "SELECT * FROM maintenance_days WHERE turf_id=$1 AND date >= $2 ORDER BY date",
        turf_id, today,
    )
    return [dict(r) for r in rows]


@router.post("/admin/maintenance")
async def create_maintenance(
    payload: MaintenanceCreate,
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        d = parse_booking_date(payload.date)
    except ValueError as e:
        raise HTTPException(400, "Invalid date") from e

    turf_id, _, _ = _get_turf_state(request)
    admin_uuid = uuid.UUID(admin["user_id"])
    try:
        maint_id = await conn.fetchval(
            """INSERT INTO maintenance_days (turf_id, date, reason, created_by)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            turf_id, d, payload.reason, admin_uuid,
        )
    except (asyncpg.UniqueViolationError, UniqueViolationError) as e:
        raise HTTPException(409, "Maintenance already scheduled for this date") from e

    await _audit(conn, admin=admin, action="MAINTENANCE_CREATED", target_type="date",
                 target_id=str(maint_id), metadata={"date": payload.date, "reason": payload.reason})
    await ws_manager.broadcast({"type": "maintenance.scheduled", "date": payload.date})
    return {"maintenance_id": str(maint_id), "date": payload.date, "reason": payload.reason}


@router.delete("/admin/maintenance/{maintenance_id}")
async def remove_maintenance(
    maintenance_id: str,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        mid = uuid.UUID(maintenance_id)
    except ValueError:
        raise HTTPException(404, "Not found")

    result = await conn.execute("DELETE FROM maintenance_days WHERE id=$1", mid)
    if result == "DELETE 0":
        raise HTTPException(404, "Not found")

    await _audit(conn, admin=admin, action="MAINTENANCE_REMOVED", target_type="maintenance",
                 target_id=maintenance_id)
    return {"ok": True}


# ── Attendance ─────────────────────────────────────────────────────────────────

class AttendanceMark(BaseModel):
    status: Literal["present", "absent", "late"]
    note: Optional[str] = None


@router.put("/admin/attendance/{booking_id}")
async def mark_attendance(
    booking_id: str,
    payload: AttendanceMark,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(404, "Booking not found")

    booking = await conn.fetchrow("SELECT id FROM bookings WHERE id=$1", bid)
    if not booking:
        raise HTTPException(404, "Booking not found")

    admin_uuid = uuid.UUID(admin["user_id"])
    await conn.execute(
        """INSERT INTO attendance (booking_id, status, marked_by, note)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (booking_id) DO UPDATE
             SET status=$2, marked_by=$3, marked_at=NOW(), note=$4""",
        bid, payload.status, admin_uuid, payload.note,
    )
    await _audit(conn, admin=admin, action="ATTENDANCE_MARKED", target_type="booking",
                 target_id=booking_id, metadata={"status": payload.status})
    return {"ok": True}


# ── Announcements ──────────────────────────────────────────────────────────────

class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=3, max_length=1000)


@router.post("/admin/announcements")
async def broadcast_announcement(
    payload: AnnouncementCreate,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    admin_uuid = uuid.UUID(admin["user_id"])
    await log_activity(
        conn,
        event_type="announcement",
        actor_user_id=admin_uuid,
        message=payload.title,
        metadata={"body": payload.message},
    )
    count = await fan_out_notification(
        conn, title=payload.title, body=payload.message, type_="announcement",
    )
    await _audit(conn, admin=admin, action="ANNOUNCEMENT_PUBLISHED", target_type="announcement",
                 target_id=None, metadata={"title": payload.title})
    await ws_manager.broadcast({"type": "announcement", "title": payload.title})
    return {"ok": True, "sent_to": count}


# ── Force-cancel booking ───────────────────────────────────────────────────────

@router.delete("/admin/bookings/{booking_id}/force-cancel")
async def admin_force_cancel(
    booking_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(404, "Booking not found")

    admin_uuid = uuid.UUID(admin["user_id"])

    try:
        result = await cancel_booking(
            conn,
            booking_id           = bid,
            cancelled_by_user_id = admin_uuid,
            is_admin             = True,
            reason               = "Admin force-cancelled",
        )
    except BookingError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

    # Promote waitlist
    _, slot_template_ids, slot_templates = _get_turf_state(request)
    bdate    = result.get("booking_date")
    slot_key = result.get("slot_key") or result.get("slot_id")
    if bdate and slot_key and slot_key in slot_template_ids:
        slot = resolve_slot(slot_key, slot_templates)
        if slot:
            turf_id, _, _ = _get_turf_state(request)
            promoted = None
            try:
                promoted = await promote_from_waitlist(
                    conn,
                    turf_id          = turf_id,
                    slot_template_id = slot_template_ids[slot_key],
                    booking_date     = bdate if isinstance(bdate, datetime) else parse_booking_date(str(bdate)),
                    slot_key         = slot_key,
                    slot_start       = slot.start_time,
                    slot_end         = slot.end_time,
                )
            except Exception:
                log.exception("waitlist promotion failed after force-cancel")
            if promoted:
                try:
                    await notify_waitlist_promoted(
                        conn,
                        user_id=promoted["user_id"],
                        booking_id=promoted["id"],
                        booking_date=promoted["booking_date"],
                        slot_template_id=promoted["slot_template_id"],
                    )
                except Exception:
                    log.exception("push notification failed after waitlist promotion")

    await _audit(conn, admin=admin, action="BOOKING_FORCE_CANCELLED", target_type="booking",
                 target_id=booking_id)
    return {"ok": True, "booking_id": booking_id}


# ── Audit log ──────────────────────────────────────────────────────────────────

@router.get("/admin/audit")
async def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    rows = await conn.fetch(
        """SELECT * FROM (
               SELECT al.id, al.created_at, al.action, al.target_id, al.metadata,
                      u.email AS actor_email, NULL::text AS message, 'audit' AS source
               FROM audit_logs al
               JOIN users u ON u.id = al.admin_id
               UNION ALL
               SELECT al.id, al.created_at,
                      CASE al.event_type
                          WHEN 'booking.created' THEN 'BOOKING_CREATED'
                          WHEN 'booking.cancelled' THEN 'BOOKING_CANCELLED'
                          ELSE UPPER(REPLACE(al.event_type, '.', '_'))
                      END AS action,
                      NULLIF(al.metadata->>'booking_id', '')::uuid AS target_id,
                      al.metadata,
                      u.email AS actor_email,
                      al.message,
                      'activity' AS source
               FROM activity_logs al
               LEFT JOIN users u ON u.id = al.actor_user_id
               WHERE al.event_type IN ('booking.created', 'booking.cancelled')
           ) combined
           ORDER BY created_at DESC
           LIMIT $1""",
        limit,
    )
    return [
        {
            "audit_id":    str(r["id"]),
            "admin_email": r["actor_email"] or "system",
            "action":      r["action"],
            "target_type": "booking" if r["action"].startswith("BOOKING") else "user",
            "target_id":   str(r["target_id"]) if r["target_id"] else None,
            "metadata":    r["metadata"],
            "description": _audit_description(
                r["action"],
                metadata=r["metadata"],
                message=r["message"],
                actor_email=r["actor_email"],
            ),
            "timestamp":   serialize_dt(r["created_at"]),
        }
        for r in rows
    ]


# ── Slot management ───────────────────────────────────────────────────────────

class SlotCreateRequest(BaseModel):
    slot_key: str = Field(min_length=1, max_length=10)
    start_time: str
    end_time: str


class SlotUpdateRequest(BaseModel):
    slot_key: str = Field(min_length=1, max_length=10)
    start_time: str
    end_time: str
    is_active: bool = True


def _normalize_slot_key(value: str) -> str:
    return value.strip().upper()


def _serialize_slot_row(row: dict) -> dict:
    return {
        "id":         str(row["id"]),
        "turf_id":    str(row["turf_id"]),
        "slot_key":   row["slot_key"],
        "start_time": coerce_db_time(row["start_time"]).strftime("%H:%M"),
        "end_time":   coerce_db_time(row["end_time"]).strftime("%H:%M"),
        "is_active":  bool(row["is_active"]),
    }


def _parse_slot_times(start_raw: str, end_raw: str) -> tuple[time, time]:
    try:
        start = parse_hhmm(start_raw)
        end = parse_hhmm(end_raw)
    except ValueError as exc:
        raise HTTPException(400, "Invalid time format (use HH:MM)") from exc
    if start >= end:
        raise HTTPException(400, "Start time must be before end time.")
    return start, end


async def _slot_overlap_key(
    conn: asyncpg.Connection,
    *,
    turf_id: str,
    start: time,
    end: time,
    exclude_id: uuid.UUID | None = None,
) -> str | None:
    rows = await conn.fetch(
        """SELECT id, slot_key, start_time, end_time
           FROM slot_templates
           WHERE turf_id = $1 AND is_active = TRUE
             AND ($2::uuid IS NULL OR id != $2)""",
        turf_id,
        exclude_id,
    )
    for row in rows:
        other_start = coerce_db_time(row["start_time"])
        other_end = coerce_db_time(row["end_time"])
        if time_ranges_overlap(start, end, other_start, other_end):
            return row["slot_key"]
    return None


async def _refresh_slot_cache(request: Request) -> None:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is not None:
        await load_slot_cache(request.app, pool)


async def _log_slot_activity(
    conn: asyncpg.Connection,
    *,
    admin: dict,
    event_type: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    await log_activity(
        conn,
        event_type=event_type,
        actor_user_id=admin["user_id"],
        message=message,
        metadata=metadata,
    )


@router.get("/admin/slots")
async def admin_list_slots(
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    turf_id, _, _ = _get_turf_state(request)
    rows = await conn.fetch(
        """SELECT id, turf_id, slot_key, start_time, end_time, is_active
           FROM slot_templates
           WHERE turf_id = $1
           ORDER BY start_time, slot_key""",
        turf_id,
    )
    return [_serialize_slot_row(dict(r)) for r in rows]


@router.post("/admin/slots", status_code=201)
async def admin_create_slot(
    payload: SlotCreateRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    turf_id, _, _ = _get_turf_state(request)
    slot_key = _normalize_slot_key(payload.slot_key)
    start, end = _parse_slot_times(payload.start_time, payload.end_time)

    existing_key = await conn.fetchval(
        "SELECT id FROM slot_templates WHERE turf_id = $1 AND slot_key = $2",
        turf_id,
        slot_key,
    )
    if existing_key:
        raise HTTPException(409, "Slot key already exists.")

    overlap = await _slot_overlap_key(conn, turf_id=turf_id, start=start, end=end)
    if overlap:
        raise HTTPException(409, f"Slot overlaps existing slot {overlap}.")

    try:
        row = await conn.fetchrow(
            """INSERT INTO slot_templates (turf_id, slot_key, start_time, end_time, is_active)
               VALUES ($1, $2, $3, $4, TRUE)
               RETURNING id, turf_id, slot_key, start_time, end_time, is_active""",
            turf_id,
            slot_key,
            start,
            end,
        )
    except UniqueViolationError as exc:
        raise HTTPException(409, "Slot key already exists.") from exc

    slot_id = str(row["id"])
    meta = {
        "slot_id": slot_id,
        "slot_key": slot_key,
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
    }
    await _log_slot_activity(
        conn,
        admin=admin,
        event_type="slot.created",
        message=f"Created Slot {slot_key} ({start.strftime('%H:%M')}–{end.strftime('%H:%M')})",
        metadata=meta,
    )
    await _audit(conn, admin=admin, action="SLOT_CREATED", target_type="slot", target_id=slot_id, metadata=meta)
    await _refresh_slot_cache(request)
    return _serialize_slot_row(dict(row))


@router.put("/admin/slots/{slot_id}")
async def admin_update_slot(
    slot_id: str,
    payload: SlotUpdateRequest,
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        sid = uuid.UUID(slot_id)
    except ValueError:
        raise HTTPException(404, "Slot not found")

    turf_id, _, _ = _get_turf_state(request)
    row = await conn.fetchrow(
        """SELECT id, turf_id, slot_key, start_time, end_time, is_active
           FROM slot_templates WHERE id = $1 AND turf_id = $2""",
        sid,
        turf_id,
    )
    if not row:
        raise HTTPException(404, "Slot not found")

    slot_key = _normalize_slot_key(payload.slot_key)
    start, end = _parse_slot_times(payload.start_time, payload.end_time)
    booking_count = int(await conn.fetchval(
        "SELECT COUNT(*) FROM bookings WHERE slot_template_id = $1", sid,
    ) or 0)

    changing_identity = (
        slot_key != row["slot_key"]
        or start != coerce_db_time(row["start_time"])
        or end != coerce_db_time(row["end_time"])
    )
    if booking_count and changing_identity:
        raise HTTPException(
            409,
            "Slot has bookings; disable instead of deleting or changing times.",
        )

    if slot_key != row["slot_key"]:
        dup = await conn.fetchval(
            "SELECT id FROM slot_templates WHERE turf_id = $1 AND slot_key = $2 AND id != $3",
            turf_id,
            slot_key,
            sid,
        )
        if dup:
            raise HTTPException(409, "Slot key already exists.")

    if payload.is_active:
        overlap = await _slot_overlap_key(
            conn, turf_id=turf_id, start=start, end=end, exclude_id=sid,
        )
        if overlap:
            raise HTTPException(409, f"Slot overlaps existing slot {overlap}.")

    try:
        updated = await conn.fetchrow(
            """UPDATE slot_templates
               SET slot_key = $2, start_time = $3, end_time = $4, is_active = $5
               WHERE id = $1
               RETURNING id, turf_id, slot_key, start_time, end_time, is_active""",
            sid,
            slot_key,
            start,
            end,
            payload.is_active,
        )
    except UniqueViolationError as exc:
        raise HTTPException(409, "Slot key already exists.") from exc

    meta = {
        "slot_id": slot_id,
        "slot_key": slot_key,
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
        "is_active": payload.is_active,
    }
    await _log_slot_activity(
        conn,
        admin=admin,
        event_type="slot.updated",
        message=f"Updated Slot {slot_key}",
        metadata=meta,
    )
    await _audit(conn, admin=admin, action="SLOT_UPDATED", target_type="slot", target_id=slot_id, metadata=meta)
    await _refresh_slot_cache(request)
    return _serialize_slot_row(dict(updated))


@router.patch("/admin/slots/{slot_id}/disable")
async def admin_disable_slot(
    slot_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        sid = uuid.UUID(slot_id)
    except ValueError:
        raise HTTPException(404, "Slot not found")

    turf_id, _, _ = _get_turf_state(request)
    row = await conn.fetchrow(
        """UPDATE slot_templates SET is_active = FALSE
           WHERE id = $1 AND turf_id = $2
           RETURNING id, turf_id, slot_key, start_time, end_time, is_active""",
        sid,
        turf_id,
    )
    if not row:
        raise HTTPException(404, "Slot not found")

    meta = {"slot_id": slot_id, "slot_key": row["slot_key"]}
    await _log_slot_activity(
        conn,
        admin=admin,
        event_type="slot.disabled",
        message=f"Disabled Slot {row['slot_key']}",
        metadata=meta,
    )
    await _audit(conn, admin=admin, action="SLOT_DISABLED", target_type="slot", target_id=slot_id, metadata=meta)
    await _refresh_slot_cache(request)
    return _serialize_slot_row(dict(row))


@router.patch("/admin/slots/{slot_id}/enable")
async def admin_enable_slot(
    slot_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        sid = uuid.UUID(slot_id)
    except ValueError:
        raise HTTPException(404, "Slot not found")

    turf_id, _, _ = _get_turf_state(request)
    row = await conn.fetchrow(
        """SELECT id, turf_id, slot_key, start_time, end_time, is_active
           FROM slot_templates WHERE id = $1 AND turf_id = $2""",
        sid,
        turf_id,
    )
    if not row:
        raise HTTPException(404, "Slot not found")

    start = coerce_db_time(row["start_time"])
    end = coerce_db_time(row["end_time"])
    overlap = await _slot_overlap_key(conn, turf_id=turf_id, start=start, end=end, exclude_id=sid)
    if overlap:
        raise HTTPException(409, f"Slot overlaps existing slot {overlap}.")

    updated = await conn.fetchrow(
        """UPDATE slot_templates SET is_active = TRUE
           WHERE id = $1
           RETURNING id, turf_id, slot_key, start_time, end_time, is_active""",
        sid,
    )
    meta = {"slot_id": slot_id, "slot_key": updated["slot_key"]}
    await _log_slot_activity(
        conn,
        admin=admin,
        event_type="slot.enabled",
        message=f"Enabled Slot {updated['slot_key']}",
        metadata=meta,
    )
    await _audit(conn, admin=admin, action="SLOT_ENABLED", target_type="slot", target_id=slot_id, metadata=meta)
    await _refresh_slot_cache(request)
    return _serialize_slot_row(dict(updated))


# ── Analytics preview ──────────────────────────────────────────────────────────

@router.get("/admin/analytics/preview")
async def analytics_preview(
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    popular = await conn.fetchrow(
        """SELECT s.slot_key, COUNT(*) AS n
           FROM bookings b
           JOIN slot_templates s ON s.id = b.slot_template_id
           WHERE b.status = 'booked'
           GROUP BY s.slot_key ORDER BY n DESC LIMIT 1""",
    )
    top_dept = await conn.fetchrow(
        """SELECT u.department, COUNT(*) AS n
           FROM bookings b
           JOIN users u ON u.id = b.user_id
           WHERE b.status = 'booked' AND u.department IS NOT NULL
           GROUP BY u.department ORDER BY n DESC LIMIT 1""",
    )
    waitlist_demand = await conn.fetchval("SELECT COUNT(*) FROM waitlists WHERE status='waiting'")

    return {
        "most_popular_slot": popular["slot_key"] if popular else None,
        "top_department":    top_dept["department"] if top_dept else None,
        "waitlist_demand":   waitlist_demand,
    }
