"""Booking routes — PostgreSQL + SQLite dev compatible."""
from __future__ import annotations

import logging
import uuid
from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from database.booking_tx import (
    WEEKLY_BOOKING_LIMIT,
    WEEKLY_CANCELLATION_LIMIT,
    BookingError,
    cancel_booking,
    create_booking,
    promote_from_waitlist,
)
from database.connection import get_conn
from services.auth_dep import get_current_user
from services.serialize import parse_dt
from services.models import (
    Booking,
    BookingCreate,
    CalendarDay,
    CalendarResponse,
    DateOverview,
    OccupancyResponse,
    SlotView,
    WaitlistEntry,
    WaitlistJoin,
    WeeklyUsage,
)
from services.uuid_util import uuid_same
from services.push import notify_waitlist_promoted
from services.turf_schedule import (
    active_slot_count,
    coerce_db_time,
    is_completed,
    is_future_slot,
    now_turf,
    ordered_active_slots,
    parse_booking_date,
    resolve_slot,
    slot_datetimes,
    SlotTemplate,
)
from services.ws_manager import ws_manager

router = APIRouter(prefix="/api/bookings", tags=["bookings"])
log = logging.getLogger(__name__)


# ── Row → Pydantic helpers ────────────────────────────────────────────────────

def _row_to_booking(row: dict) -> Booking:
    """Map a JOINed bookings row to the Booking response model.

    Normalizes timestamps before passing to Pydantic so that both PostgreSQL
    datetime objects and SQLite ISO strings (including legacy malformed ones)
    are accepted without validation errors.
    """
    bdate = row["booking_date"]
    if isinstance(bdate, str):
        try:
            bdate = date.fromisoformat(bdate[:10])
        except ValueError:
            pass

    start = row["start_time"]
    end   = row["end_time"]

    created_at = parse_dt(row["created_at"])
    cancelled_at = parse_dt(row.get("cancelled_at"))
    updated_at = cancelled_at or created_at

    return Booking(
        booking_id       = str(row["id"]),
        user_id          = str(row["user_id"]),
        student_name     = row.get("student_name") or row.get("name") or "",
        student_id       = row.get("student_id") or "",
        email            = row.get("email") or "",
        booking_date     = str(bdate)[:10],
        slot_id          = row["slot_key"],
        slot_label       = f"Slot {row['slot_key']}",
        start_time       = start.strftime("%H:%M") if hasattr(start, "strftime") else str(start)[:5],
        end_time         = end.strftime("%H:%M")   if hasattr(end, "strftime")   else str(end)[:5],
        status           = row["status"],
        created_at       = created_at,
        updated_at       = updated_at,
        day_of_week      = bdate.weekday() if isinstance(bdate, date) else 0,
        hour             = start.hour if hasattr(start, "hour") else 0,
        booking_lead_time= 0,
        department       = row.get("department"),
        batch            = row.get("batch"),
    )


_BOOKING_SELECT = """
    SELECT b.id, b.user_id, b.turf_id, b.slot_template_id,
           b.booking_date, b.status, b.created_at, b.cancelled_at,
           u.name        AS student_name,
           u.student_id  AS student_id,
           u.email       AS email,
           u.department  AS department,
           u.batch       AS batch,
           s.slot_key    AS slot_key,
           s.start_time  AS start_time,
           s.end_time    AS end_time
    FROM bookings b
    JOIN users          u ON u.id = b.user_id
    JOIN slot_templates s ON s.id = b.slot_template_id
"""


def _get_turf_state(request: Request) -> tuple:
    """Return (default_turf_id, slot_template_ids, slot_templates) from app.state."""
    turf_id = getattr(request.app.state, "default_turf_id", None)
    if turf_id is None:
        raise HTTPException(status_code=503, detail="Turf not configured. Run migrations + seed.")
    return (
        turf_id,
        request.app.state.slot_template_ids,
        request.app.state.slot_templates,
    )


async def _broadcast(message: dict) -> None:
    try:
        await ws_manager.broadcast(message)
    except Exception:
        log.exception("ws broadcast failed")


async def _promote_waitlist_after_cancel(
    conn: asyncpg.Connection,
    request: Request,
    cancel_result: dict,
) -> dict | None:
    """Promote first waitlisted user after a cancellation; send push if promoted."""
    _, slot_template_ids, slot_templates = _get_turf_state(request)
    bdate = cancel_result.get("booking_date")
    slot_key = cancel_result.get("slot_key") or cancel_result.get("slot_id")
    if not bdate or not slot_key or slot_key not in slot_template_ids:
        return None

    slot = resolve_slot(slot_key, slot_templates)
    if not slot:
        return None
    parsed_date = bdate if isinstance(bdate, date) else parse_booking_date(str(bdate))
    if not is_future_slot(parsed_date, slot):
        return None

    turf_id, _, _ = _get_turf_state(request)
    try:
        promoted = await promote_from_waitlist(
            conn,
            turf_id=turf_id,
            slot_template_id=slot_template_ids[slot_key],
            booking_date=parsed_date,
            slot_key=slot_key,
            slot_start=slot.start_time,
            slot_end=slot.end_time,
        )
    except Exception:
        log.exception("waitlist promotion failed after cancellation")
        return None

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

    return promoted


# ── POST /api/bookings ────────────────────────────────────────────────────────

@router.post("", response_model=Booking, status_code=status.HTTP_201_CREATED)
async def create_booking_route(
    payload: BookingCreate,
    request: Request,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
) -> Booking:
    if not user.get("profile_completed"):
        raise HTTPException(400, "Complete your profile before booking")

    turf_id, slot_template_ids, slot_templates = _get_turf_state(request)

    slot_key = payload.slot_id
    slot = resolve_slot(slot_key, slot_templates)
    if not slot:
        raise HTTPException(400, f"Unknown slot_id: {slot_key}")

    try:
        bdate = parse_booking_date(payload.booking_date)
    except ValueError as e:
        raise HTTPException(400, "Invalid booking_date (YYYY-MM-DD)") from e

    if not is_future_slot(bdate, slot):
        raise HTTPException(400, "Cannot book a slot that is already in the past")

    slot_template_id = slot_template_ids.get(slot_key)
    if not slot_template_id:
        raise HTTPException(503, f"Slot template '{slot_key}' not found. Re-seed the database.")

    uid = uuid.UUID(user["user_id"])

    try:
        row = await create_booking(
            conn,
            user_id          = uid,
            turf_id          = turf_id,
            slot_template_id = slot_template_id,
            booking_date     = bdate,
            slot_key         = slot_key,
            slot_start       = slot.start_time,
            slot_end         = slot.end_time,
        )
    except BookingError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

    await _broadcast({
        "type":         "booking.created",
        "booking_date": payload.booking_date,
        "slot_id":      slot_key,
        "booking_id":   str(row["id"]),
    })
    return _row_to_booking(row)


# ── GET /api/bookings/date/{date} ─────────────────────────────────────────────

@router.get("/date/{date_str}", response_model=DateOverview)
async def list_for_date(
    date_str: str = Path(..., alias="date_str"),
    request: Request = None,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
) -> DateOverview:
    try:
        bdate = parse_booking_date(date_str)
    except ValueError as e:
        raise HTTPException(400, "Invalid date (YYYY-MM-DD)") from e

    turf_id, _, slot_templates_map = _get_turf_state(request)

    rows = await conn.fetch(
        _BOOKING_SELECT + " WHERE b.booking_date = $1 AND b.status = 'booked' AND b.turf_id = $2",
        bdate, turf_id,
    )
    bookings_by_key = {r["slot_key"]: r for r in rows}
    uid = uuid.UUID(user["user_id"])

    wl_rows = await conn.fetch(
        """SELECT w.id, w.position, s.slot_key
           FROM waitlists w
           JOIN slot_templates s ON s.id = w.slot_template_id
           WHERE w.user_id = $1 AND w.booking_date = $2 AND w.status = 'waiting'""",
        uid,
        bdate,
    )
    wl_by_key = {r["slot_key"]: r for r in wl_rows}

    slots: list[SlotView] = []
    for tmpl in ordered_active_slots(slot_templates_map):
        bk_row = bookings_by_key.get(tmpl.slot_id)
        wl_row = wl_by_key.get(tmpl.slot_id)
        completed = is_completed(bdate, tmpl)
        if bk_row:
            bk = _row_to_booking(dict(bk_row))
            is_mine = uuid_same(bk_row["user_id"], uid)
            slots.append(SlotView(
                slot_id     = tmpl.slot_id,
                slot_label  = tmpl.slot_label,
                start_time  = tmpl.start_time.strftime("%H:%M"),
                end_time    = tmpl.end_time.strftime("%H:%M"),
                booking_date= date_str,
                status      = "completed" if completed else "booked",
                booking     = bk,
                is_mine     = is_mine,
                is_waitlisted = wl_row is not None,
                waitlist_position = wl_row["position"] if wl_row else None,
                waitlist_id = str(wl_row["id"]) if wl_row else None,
                booker_name = None if is_mine else (bk_row.get("student_name") or bk.student_name),
                booker_student_id = None if is_mine else (bk_row.get("student_id") or bk.student_id),
            ))
        else:
            slots.append(SlotView(
                slot_id     = tmpl.slot_id,
                slot_label  = tmpl.slot_label,
                start_time  = tmpl.start_time.strftime("%H:%M"),
                end_time    = tmpl.end_time.strftime("%H:%M"),
                booking_date= date_str,
                status      = "completed" if completed else "available",
                booking     = None,
                is_mine     = False,
                is_waitlisted = wl_row is not None,
                waitlist_position = wl_row["position"] if wl_row else None,
                waitlist_id = str(wl_row["id"]) if wl_row else None,
            ))
    return DateOverview(booking_date=date_str, slots=slots)


# ── GET /api/bookings/occupancy/{date} ────────────────────────────────────────

@router.get("/occupancy/{date_str}", response_model=OccupancyResponse)
async def occupancy(
    date_str: str,
    request: Request = None,
    user: dict = Depends(get_current_user),  # noqa: ARG001
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        bdate = parse_booking_date(date_str)
    except ValueError as e:
        raise HTTPException(400, "Invalid date") from e

    turf_id, _, slot_templates_map = _get_turf_state(request)
    filled = await conn.fetchval(
        "SELECT COUNT(*) FROM bookings WHERE booking_date=$1 AND turf_id=$2 AND status='booked'",
        bdate, turf_id,
    )
    total = active_slot_count(slot_templates_map)
    pct   = int(round(filled / total * 100)) if total else 0
    return OccupancyResponse(booking_date=date_str, total_slots=total, filled_slots=filled, percentage=pct)


# ── GET /api/bookings/calendar/{year}/{month} ─────────────────────────────────

@router.get("/calendar/{year}/{month}", response_model=CalendarResponse)
async def calendar(
    year: int,
    month: int,
    request: Request = None,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    if not (1 <= month <= 12) or not (2024 <= year <= 2100):
        raise HTTPException(400, "Invalid year/month")

    turf_id, _, slot_templates_map = _get_turf_state(request)
    uid = uuid.UUID(user["user_id"])

    from datetime import date as date_cls
    start = date_cls(year, month, 1)
    if month == 12:
        end = date_cls(year + 1, 1, 1)
    else:
        end = date_cls(year, month + 1, 1)

    rows = await conn.fetch(
        """SELECT booking_date,
                  COUNT(*) AS total,
                  SUM(CASE WHEN user_id = $1 THEN 1 ELSE 0 END) AS mine
           FROM bookings
           WHERE turf_id = $2 AND booking_date >= $3 AND booking_date < $4
             AND status = 'booked'
           GROUP BY booking_date
           ORDER BY booking_date""",
        uid, turf_id, start, end,
    )
    total_active = active_slot_count(slot_templates_map)
    days = [
        CalendarDay(
            date        = str(r["booking_date"]),
            total       = r["total"],
            mine        = r["mine"],
            fully_booked= r["total"] >= total_active,
        )
        for r in rows
    ]
    return CalendarResponse(year=year, month=month, days=days)


# ── GET /api/bookings/usage/weekly ────────────────────────────────────────────

@router.get("/usage/weekly", response_model=WeeklyUsage)
async def weekly_usage_route(
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    from services.limits import weekly_usage
    return WeeklyUsage(**(await weekly_usage(conn, user["user_id"])))


# ── GET /api/bookings/me ──────────────────────────────────────────────────────

@router.get("/me", response_model=list[Booking])
async def my_bookings(
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
) -> list[Booking]:
    try:
        uid = uuid.UUID(user["user_id"])
    except ValueError:
        log.error("my_bookings: bad user_id=%r", user.get("user_id"))
        raise HTTPException(400, "Invalid user session")

    try:
        rows = await conn.fetch(
            _BOOKING_SELECT + " WHERE b.user_id = $1 ORDER BY b.booking_date DESC, s.start_time DESC",
            uid,
        )
    except Exception:
        log.exception("my_bookings: DB fetch failed for user_id=%s", uid)
        raise

    now = now_turf()
    out: list[Booking] = []
    for r in rows:
        d = dict(r)
        if d["status"] == "booked":
            try:
                bdate = d["booking_date"]
                # coerce string to date if needed (SQLite returns str for booking_date)
                if isinstance(bdate, str):
                    from datetime import date as _date
                    bdate = _date.fromisoformat(bdate[:10])
                slot = SlotTemplate(
                    slot_id=d["slot_key"],
                    slot_label=f"Slot {d['slot_key']}",
                    start_time=coerce_db_time(d["start_time"]),
                    end_time=coerce_db_time(d["end_time"]),
                )
                if slot:
                    _, end = slot_datetimes(bdate, slot)
                    if end <= now:
                        d["status"] = "completed"
            except Exception:
                log.debug("my_bookings: completed-check skipped for row id=%s", d.get("id"))
        try:
            out.append(_row_to_booking(d))
        except Exception:
            log.exception("my_bookings: _row_to_booking failed for row id=%s", d.get("id"))
            raise
    return out


# ── DELETE /api/bookings/{booking_id} ─────────────────────────────────────────

@router.delete("/{booking_id}", status_code=status.HTTP_200_OK)
async def cancel_booking_route(
    booking_id: str,
    request: Request = None,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
) -> dict:
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(404, "Booking not found")

    uid = uuid.UUID(user["user_id"])
    is_admin = user.get("role") in ("admin", "super_admin")

    try:
        result = await cancel_booking(conn, booking_id=bid, cancelled_by_user_id=uid, is_admin=is_admin)
    except BookingError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

    # Auto-promote first waitlisted user (separate transaction — acceptable).
    promoted = await _promote_waitlist_after_cancel(conn, request, result)

    bdate = result.get("booking_date")
    slot_key = result.get("slot_key") or result.get("slot_id")

    await _broadcast({
        "type":         "booking.cancelled",
        "booking_date": str(bdate),
        "slot_id":      slot_key,
        "booking_id":   booking_id,
    })

    if promoted:
        await _broadcast({
            "type":         "waitlist.promoted",
            "booking_id":   str(promoted.get("id")),
            "user_id":      str(promoted.get("user_id")),
            "booking_date": str(bdate),
            "slot_id":      slot_key,
        })
    return {"ok": True, "booking_id": booking_id}
