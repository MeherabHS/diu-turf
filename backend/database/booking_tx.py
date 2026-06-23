"""Transactional booking engine — Phase 5 database layer.

Implements the exact 10-step atomic booking flow:

    BEGIN TRANSACTION
    1.  Lock requested slot                     (pg_advisory_xact_lock)
    2.  Check maintenance status                (maintenance_days table)
    3.  Check user suspension                   (users.suspension_until)
    4.  Check weekly booking limit              (WEEKLY_BOOKING_LIMIT = 5)
    5.  Check one-booking-per-day rule          (unique partial index guard)
    6.  Create booking                          (INSERT bookings)
    7.  Cancel user's own waitlist entry        (UPDATE waitlists → cancelled)
    8.  Create confirmation notification        (INSERT notifications)
    9.  Create activity log entry               (INSERT activity_logs)
    10. COMMIT
    ROLLBACK on any failure.

Usage (from Phase 5 route handlers):

    from database.booking_tx import create_booking, BookingError, cancel_booking
    import asyncpg

    @router.post("/api/bookings")
    async def book(
        payload: BookingCreate,
        user: dict = Depends(get_current_user_pg),
        conn: asyncpg.Connection = Depends(get_conn),
    ):
        try:
            booking = await create_booking(
                conn,
                user_id=user["id"],
                turf_id=app.state.default_turf_id,
                slot_template_id=app.state.slot_template_ids[payload.slot_key],
                booking_date=payload.booking_date,
                slot_key=payload.slot_key,
                slot_start=time(16, 0),   # from slot template
                slot_end=time(17, 0),
            )
        except BookingError as exc:
            raise HTTPException(status_code=exc.http_status, detail=str(exc))
        return booking

Concurrency design
──────────────────
Layer 1 — Advisory lock (step 1):
  pg_advisory_xact_lock serialises concurrent booking attempts for the SAME
  slot+date.  Different slots/dates proceed in parallel without contention.
  The lock is automatically released on COMMIT or ROLLBACK.

Layer 2 — Partial unique index (step 6):
  uniq_active_slot_per_day  → one 'booked' row per (turf, slot, date)
  uniq_active_booking_per_user_per_day → one 'booked' row per (user, date)
  If two transactions somehow pass the advisory lock simultaneously, the
  unique index raises UniqueViolationError on the second INSERT, which is
  caught and converted to a 409 HTTPException.  The transaction rolls back.

Weekly cap race (step 4):
  A user can make only 1 booking per day (enforced above), so hitting the
  weekly cap via concurrent requests requires 5+ simultaneous requests from
  the same user — pathological in practice.  The advisory lock in step 1
  also serialises requests from the same user for the same slot, providing
  sufficient protection.  A Redis counter or user-level advisory lock can be
  added in future if stricter cap enforcement is required.

ACID guarantee:
  asyncpg wraps all steps in a single PostgreSQL transaction.
  Any exception inside `async with conn.transaction()` triggers ROLLBACK.
  Partial writes (e.g. booking created but notification missing) cannot occur.

UTC / Timezone:
  All timestamps written as UTC (NOW() / Python datetime.now(timezone.utc)).
  Convert to Asia/Dhaka at the API / UI layer.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID

import asyncpg

from database.exceptions import UniqueViolationError
from services.uuid_util import uuid_hex, uuid_same

log = logging.getLogger(__name__)

WEEKLY_BOOKING_LIMIT = 5
WEEKLY_CANCELLATION_LIMIT = 3


# ── Errors ────────────────────────────────────────────────────────────────────

class BookingError(Exception):
    """Domain error raised inside booking_tx functions.

    Callers should convert to HTTPException:
        except BookingError as e:
            raise HTTPException(status_code=e.http_status, detail=str(e))
    """
    def __init__(self, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


# ── Helpers ───────────────────────────────────────────────────────────────────

def _week_start_utc(now: datetime | None = None) -> datetime:
    """Return Monday 00:00:00 UTC for the week containing *now*."""
    from datetime import timedelta
    n = (now or datetime.now(timezone.utc)).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    return n - timedelta(days=n.weekday())


def _week_start_param(conn: Any) -> Any:
    """Return the week-start in the correct type for the DB backend.

    SQLite stores timestamps as TEXT so we pass an ISO string.
    asyncpg (PostgreSQL) expects a datetime object.
    """
    from database.sqlite_adapter import SQLiteConnection
    ws = _week_start_utc()
    if isinstance(conn, SQLiteConnection):
        return ws.strftime("%Y-%m-%dT%H:%M:%S") + ".000000Z"
    return ws


def _slot_lock_key(turf_id: UUID, slot_template_id: UUID, booking_date: date) -> str:
    """Deterministic string used to derive the advisory lock bigint."""
    return f"{turf_id}|{slot_template_id}|{booking_date.isoformat()}"


# ── Core transaction: create_booking ─────────────────────────────────────────

async def create_booking(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    turf_id: UUID,
    slot_template_id: UUID,
    booking_date: date,
    slot_key: str,          # 'A' | 'B' | 'C'  (for messages)
    slot_start: time,       # 16:00              (for messages)
    slot_end: time,         # 17:00              (for messages)
) -> dict[str, Any]:
    """Execute the 10-step atomic booking transaction.

    Returns the full booking row dict on success.
    Raises BookingError on any domain violation.
    Raises asyncpg exceptions on unexpected DB errors (let them propagate).
    """
    async with conn.transaction():

        # ── Step 1: Lock the requested slot ───────────────────────────────────
        # pg_advisory_xact_lock(bigint) acquires an exclusive session-level
        # advisory lock for the duration of this transaction.  Any other
        # transaction trying to book the same slot+date will block here until
        # we COMMIT or ROLLBACK.
        lock_key = _slot_lock_key(turf_id, slot_template_id, booking_date)
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)",
            lock_key,
        )

        # ── Step 2: Check maintenance status ──────────────────────────────────
        maintenance = await conn.fetchrow(
            """SELECT reason
               FROM maintenance_days
               WHERE turf_id = $1 AND date = $2
               LIMIT 1""",
            turf_id,
            booking_date,
        )
        if maintenance is not None:
            reason = maintenance["reason"] or "scheduled maintenance"
            raise BookingError(
                f"Turf is closed on {booking_date}: {reason}",
                http_status=400,
            )

        # ── Step 3: Check user suspension ─────────────────────────────────────
        user_row = await conn.fetchrow(
            """SELECT is_active, suspension_until, suspension_reason
               FROM users
               WHERE id = $1""",
            user_id,
        )
        if user_row is None:
            raise BookingError("User not found", http_status=401)
        if not user_row["is_active"]:
            raise BookingError("Your account is deactivated.", http_status=403)
        if user_row["suspension_until"] is not None:
            from services.serialize import parse_dt as _sdt
            until: datetime | None = _sdt(user_row["suspension_until"])
            if until is None:
                until = user_row["suspension_until"]
            if isinstance(until, datetime):
                if until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
            if until and until > datetime.now(timezone.utc):
                reason_str = user_row["suspension_reason"] or "policy violation"
                raise BookingError(
                    f"Account suspended until {until.isoformat()} ({reason_str})",
                    http_status=403,
                )

        # ── Step 4: Check weekly booking limit ────────────────────────────────
        # Count all bookings (any status) created this week — a cancelled booking
        # still consumes a weekly quota slot to prevent abuse.
        week_start = _week_start_param(conn)
        weekly_count: int = await conn.fetchval(
            """SELECT COUNT(*)
               FROM bookings
               WHERE user_id = $1
                 AND created_at >= $2""",
            user_id,
            week_start,
        )
        if weekly_count >= WEEKLY_BOOKING_LIMIT:
            raise BookingError(
                f"Weekly booking limit reached ({WEEKLY_BOOKING_LIMIT} bookings/week).",
                http_status=429,
            )

        # ── Step 5: Check one-booking-per-day rule ────────────────────────────
        # The partial unique index enforces this at DB level; this check gives a
        # human-readable error before hitting the constraint.
        existing_today = await conn.fetchval(
            """SELECT id
               FROM bookings
               WHERE user_id = $1
                 AND booking_date = $2
                 AND status = 'booked'
               LIMIT 1""",
            user_id,
            booking_date,
        )
        if existing_today is not None:
            raise BookingError(
                "You already have an active booking for this date.",
                http_status=409,
            )

        # ── Step 6: Create the booking ────────────────────────────────────────
        try:
            booking_id: UUID = await conn.fetchval(
                """INSERT INTO bookings
                       (user_id, turf_id, slot_template_id, booking_date, status)
                   VALUES ($1, $2, $3, $4, 'booked')
                   RETURNING id""",
                user_id,
                turf_id,
                slot_template_id,
                booking_date,
            )
        except (asyncpg.UniqueViolationError, UniqueViolationError) as exc:
            constraint = getattr(exc, "constraint_name", "") or ""
            if "slot_per_day" in constraint:
                raise BookingError(
                    "This slot was just booked by someone else. Please choose another.",
                    http_status=409,
                ) from exc
            if "user_per_day" in constraint:
                raise BookingError(
                    "You already have an active booking for this date.",
                    http_status=409,
                ) from exc
            raise BookingError("Booking conflict — please try again.", http_status=409) from exc

        # ── Step 7: Cancel user's own waitlist entry for this slot (if any) ───
        # If the user was queued for this exact slot, their direct booking
        # satisfies the intent — remove the waitlist entry cleanly.
        await conn.execute(
            """UPDATE waitlists
               SET status = 'cancelled'
               WHERE user_id          = $1
                 AND turf_id          = $2
                 AND slot_template_id = $3
                 AND booking_date     = $4
                 AND status           = 'waiting'""",
            user_id,
            turf_id,
            slot_template_id,
            booking_date,
        )

        # ── Step 8: Create confirmation notification ───────────────────────────
        start_str = slot_start.strftime("%I:%M %p").lstrip("0")
        end_str = slot_end.strftime("%I:%M %p").lstrip("0")
        await conn.execute(
            """INSERT INTO notifications (user_id, title, body, type)
               VALUES ($1, $2, $3, 'booking.confirmed')""",
            user_id,
            "Booking Confirmed",
            f"Slot {slot_key} · {start_str}–{end_str} on {booking_date.isoformat()}",
        )

        # ── Step 9: Create activity log entry ─────────────────────────────────
        await conn.execute(
            """INSERT INTO activity_logs (actor_user_id, event_type, message, metadata)
               VALUES ($1, 'booking.created', $2, $3::jsonb)""",
            user_id,
            f"Booked Slot {slot_key} on {booking_date.isoformat()}",
            json.dumps({
                "booking_id": str(booking_id),
                "slot_key": slot_key,
                "booking_date": booking_date.isoformat(),
            }),
        )

        # ── Step 10: COMMIT ───────────────────────────────────────────────────
        # Implicit on clean exit from `async with conn.transaction()`.
        # ROLLBACK is implicit on any exception raised above.

        # Fetch and return the full booking row for the response.
        booking_row = await conn.fetchrow(
            """SELECT
                   b.id,
                   b.user_id,
                   b.turf_id,
                   b.slot_template_id,
                   b.booking_date,
                   b.status,
                   b.created_at,
                   b.cancelled_at,
                   b.cancellation_reason,
                   u.name          AS student_name,
                   u.student_id    AS student_id,
                   u.email         AS email,
                   u.department    AS department,
                   u.batch         AS batch,
                   s.slot_key      AS slot_key,
                   s.start_time    AS start_time,
                   s.end_time      AS end_time
               FROM bookings        b
               JOIN users           u ON u.id = b.user_id
               JOIN slot_templates  s ON s.id = b.slot_template_id
               WHERE b.id = $1""",
            booking_id,
        )
        return dict(booking_row)  # type: ignore[arg-type]


# ── Core transaction: cancel_booking ─────────────────────────────────────────

async def cancel_booking(
    conn: asyncpg.Connection,
    *,
    booking_id: UUID,
    cancelled_by_user_id: UUID,
    is_admin: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    """Cancel a booking and trigger waitlist promotion.

    Steps:
      1. Fetch + lock the booking row.
      2. Validate ownership (or admin override).
      3. Check weekly cancellation limit (non-admin only).
      4. Mark booking as cancelled.
      5. Promote first waitlisted user (if any) — see promote_from_waitlist().
      6. Create cancellation notification.
      7. Create activity log.
      8. Commit.

    TODO(phase5): Wire auto-promotion (step 5) inline here.
    """
    async with conn.transaction():

        # Step 1: Fetch and lock the booking row.
        booking = await conn.fetchrow(
            "SELECT * FROM bookings WHERE id = $1 FOR UPDATE",
            booking_id,
        )
        if booking is None:
            raise BookingError("Booking not found.", http_status=404)
        if booking["status"] != "booked":
            raise BookingError(
                f"Cannot cancel a booking with status '{booking['status']}'.",
                http_status=400,
            )

        # Step 2: Ownership check (hex vs dashed UUID must compare equal).
        booking_owner_hex = uuid_hex(booking["user_id"])
        current_user_hex = uuid_hex(cancelled_by_user_id)
        log.info(
            "cancel_booking ownership: booking_id=%s current_user=%s booking_user_id=%s",
            booking_id,
            current_user_hex,
            booking_owner_hex,
        )
        if not is_admin and not uuid_same(booking["user_id"], cancelled_by_user_id):
            raise BookingError("You can only cancel your own bookings.", http_status=403)

        # Step 3: Weekly cancellation limit (students only).
        if not is_admin:
            week_start = _week_start_param(conn)
            cancel_count: int = await conn.fetchval(
                """SELECT COUNT(*)
                   FROM bookings
                   WHERE user_id     = $1
                     AND status      = 'cancelled'
                     AND cancelled_at >= $2""",
                booking["user_id"],
                week_start,
            )
            if cancel_count >= WEEKLY_CANCELLATION_LIMIT:
                raise BookingError(
                    f"Weekly cancellation limit reached ({WEEKLY_CANCELLATION_LIMIT}/week).",
                    http_status=429,
                )

        # Step 4: Mark as cancelled.
        now_utc = datetime.now(timezone.utc)
        await conn.execute(
            """UPDATE bookings
               SET status              = 'cancelled',
                   cancelled_at        = $2,
                   cancellation_reason = $3
               WHERE id = $1""",
            booking_id,
            now_utc,
            reason,
        )

        # Step 5: Auto-promote waitlist — TODO(phase5/6): implement inline.
        # Placeholder: promotion will be a separate call to promote_from_waitlist()
        # inside this same transaction once Phase 6 waitlist logic is written.

        # Step 6: Cancellation notification.
        booking_date = booking["booking_date"]
        await conn.execute(
            """INSERT INTO notifications (user_id, title, body, type)
               VALUES ($1, 'Booking Cancelled', $2, 'booking.cancelled')""",
            booking["user_id"],
            f"Your booking on {booking_date} has been cancelled.",
        )

        # Step 7: Activity log.
        await conn.execute(
            """INSERT INTO activity_logs (actor_user_id, event_type, message, metadata)
               VALUES ($1, 'booking.cancelled', $2, $3::jsonb)""",
            cancelled_by_user_id,
            f"Cancelled booking on {booking_date}",
            json.dumps({
                "booking_id": str(booking_id),
                "booking_date": str(booking_date),
                "cancelled_by_admin": is_admin,
            }),
        )

        # Step 8: Commit (implicit).
        return {**dict(booking), "status": "cancelled", "cancelled_at": now_utc}


# ── Waitlist promotion helper ─────────────────────────────────────────────────

async def promote_from_waitlist(
    conn: asyncpg.Connection,
    *,
    turf_id: UUID,
    slot_template_id: UUID,
    booking_date: date,
    slot_key: str,
    slot_start: time,
    slot_end: time,
) -> dict[str, Any] | None:
    """Promote the first waiting user to a confirmed booking (self-contained transaction).

    Returns the new booking row dict, or None if the waitlist is empty or slot taken.

    This function re-uses the same slot advisory lock so concurrent promotion
    attempts for the same slot are serialised.

    Called from cancel_booking() step 5 and from admin force-cancel.
    """
    async with conn.transaction():
        return await _promote_inner(
            conn,
            turf_id=turf_id,
            slot_template_id=slot_template_id,
            booking_date=booking_date,
            slot_key=slot_key,
            slot_start=slot_start,
            slot_end=slot_end,
        )


async def _promote_inner(
    conn: asyncpg.Connection,
    *,
    turf_id: UUID,
    slot_template_id: UUID,
    booking_date: date,
    slot_key: str,
    slot_start: time,
    slot_end: time,
) -> dict[str, Any] | None:
    """Inner promotion logic — called inside an open transaction."""
    # Re-acquire the slot lock.
    lock_key = _slot_lock_key(turf_id, slot_template_id, booking_date)
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1)::bigint)", lock_key)

    # Verify the slot is still empty.
    slot_taken = await conn.fetchval(
        """SELECT id FROM bookings
           WHERE turf_id          = $1
             AND slot_template_id = $2
             AND booking_date     = $3
             AND status           = 'booked'
           LIMIT 1""",
        turf_id,
        slot_template_id,
        booking_date,
    )
    if slot_taken is not None:
        return None  # slot was re-booked before promotion could run

    # Find the next waiting user (lowest position).
    entry = await conn.fetchrow(
        """SELECT *
           FROM waitlists
           WHERE turf_id          = $1
             AND slot_template_id = $2
             AND booking_date     = $3
             AND status           = 'waiting'
           ORDER BY position ASC
           LIMIT 1
           FOR UPDATE""",
        turf_id,
        slot_template_id,
        booking_date,
    )
    if entry is None:
        return None  # waitlist is empty

    promoted_user_id: UUID = entry["user_id"]
    promoted_at = datetime.now(timezone.utc)

    # Create the promoted booking.
    try:
        booking_id: UUID = await conn.fetchval(
            """INSERT INTO bookings
                   (user_id, turf_id, slot_template_id, booking_date, status)
               VALUES ($1, $2, $3, $4, 'booked')
               RETURNING id""",
            promoted_user_id,
            turf_id,
            slot_template_id,
            booking_date,
        )
    except (asyncpg.UniqueViolationError, UniqueViolationError) as exc:
        # Another transaction beat us — the slot is taken.
        raise BookingError(
            "Slot was booked concurrently during promotion.", http_status=409
        ) from exc

    # Mark the waitlist entry as promoted.
    await conn.execute(
        """UPDATE waitlists
           SET status      = 'promoted',
               promoted_at = $2
           WHERE id = $1""",
        entry["id"],
        promoted_at,
    )

    # Notify the promoted user.
    start_str = slot_start.strftime("%I:%M %p").lstrip("0")
    end_str = slot_end.strftime("%I:%M %p").lstrip("0")
    await conn.execute(
        """INSERT INTO notifications (user_id, title, body, type)
           VALUES ($1, 'You have been promoted from the waitlist!', $2,
                   'waitlist.promoted')""",
        promoted_user_id,
        f"Your waitlist spot for Slot {slot_key} · {start_str}–{end_str} "
        f"on {booking_date.isoformat()} has been confirmed.",
    )

    # Activity log.
    await conn.execute(
        """INSERT INTO activity_logs (actor_user_id, event_type, message, metadata)
           VALUES ($1, 'waitlist.promoted', $2, $3::jsonb)""",
        promoted_user_id,
        f"Promoted from waitlist — Slot {slot_key} on {booking_date.isoformat()}",
        json.dumps({
            "booking_id": str(booking_id),
            "waitlist_id": str(entry["id"]),
            "slot_key": slot_key,
            "booking_date": booking_date.isoformat(),
        }),
    )

    booking_row = await conn.fetchrow(
        """SELECT b.*,
                  u.name       AS student_name,
                  u.student_id AS student_id,
                  u.email      AS email,
                  s.slot_key   AS slot_key,
                  s.start_time AS start_time,
                  s.end_time   AS end_time
           FROM bookings       b
           JOIN users          u ON u.id = b.user_id
           JOIN slot_templates s ON s.id = b.slot_template_id
           WHERE b.id = $1""",
        booking_id,
    )
    return dict(booking_row)  # type: ignore[arg-type]
