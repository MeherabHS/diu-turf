"""Regression test for SQLite local dev mode.

Tests:
  1. Backend starts with SQLite
  2. Seed completes (turf + 3 slots + admin)
  3. Dev login returns access_token
  4. Profile completion works
  5. POST /api/bookings succeeds for slot A tomorrow
  6. GET /api/bookings/me returns that booking
  7. GET /api/bookings/date/{date} shows slot A booked
  8. Booking same date again returns BookingError (HTTP 409)
  9. Booking different date (day+2) succeeds
  10. Malformed legacy timestamp row still serializes without error

Run from backend/ directory:
    python _regression_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
import uuid
from datetime import date, timedelta

_RUN_ID = uuid.uuid4().hex[:8]
_TEST_DB = f"dev_turf_test_{_RUN_ID}.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{_TEST_DB}"
os.environ["ENVIRONMENT"] = "development"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["JWT_SECRET"] = "test_" + "x" * 60

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    sym = PASS if passed else FAIL
    print(f"  {sym} {name}" + (f": {detail}" if detail else ""))


async def main() -> None:
    from pathlib import Path
    p = Path(_TEST_DB)

    print("\n=== SQLite Regression Test ===\n")

    # ── 1. Pool + seed ────────────────────────────────────────────────────────
    print("[1] Startup — pool + seed")
    try:
        from database.connection import close_pool, create_pool
        from database.seed_pg import seed

        pool, cfg = await create_pool()
        check("pool backend=sqlite", cfg.backend.value == "sqlite")
        async with pool.acquire() as c:
            await seed(c)
        check("seed completed", True)

        async with pool.acquire() as c:
            n_turfs = await c.fetchval("SELECT COUNT(*) FROM turfs")
            n_slots = await c.fetchval("SELECT COUNT(*) FROM slot_templates")
            n_admin = await c.fetchval("SELECT COUNT(*) FROM users WHERE role='admin'")
            n_dev_student = await c.fetchval(
                "SELECT COUNT(*) FROM users WHERE email = $1",
                "252-35-166@diu.edu.bd",
            )
        check("1 turf seeded", n_turfs == 1)
        check("3 slots seeded", n_slots == 3)
        check("admin seeded", n_admin >= 1)
        check("dev test student seeded", n_dev_student == 1)
    except Exception:
        check("startup", False, traceback.format_exc().splitlines()[-1])
        await close_pool(pool)
        _print_summary()
        sys.exit(1)

    # ── 2. Dev login ──────────────────────────────────────────────────────────
    print("\n[2] Dev login")
    email = f"test-{uuid.uuid4().hex[:8]}@diu.edu.bd"
    try:
        from routes.auth import dev_login
        from services.models import DevLoginRequest

        async with pool.acquire() as c:
            auth = await dev_login(DevLoginRequest(email=email), c)
        check("access_token issued", bool(auth.access_token))
        check("user.email matches", auth.user.email == email)
        check("profile_completed=False", auth.user.profile_completed is False)
        token = auth.access_token
        raw_user_id = auth.user.user_id
    except Exception:
        check("dev login", False, traceback.format_exc().splitlines()[-1])
        await close_pool(pool)
        _print_summary()
        sys.exit(1)

    # ── 2b. Admin + dev test student ───────────────────────────────────────────
    print("\n[2b] Dev admin + test student accounts")
    try:
        from config.admin_emails import role_for_email
        from database.seed_pg import DEV_TEST_STUDENT_EMAIL, DEV_TEST_STUDENT_ID

        check("role_for_email admin", role_for_email("261-35-113@diu.edu.bd") == "admin")
        check("role_for_email student", role_for_email("other@diu.edu.bd") == "student")

        async with pool.acquire() as c:
            admin_auth = await dev_login(DevLoginRequest(email="261-35-113@diu.edu.bd"), c)
            student_auth = await dev_login(DevLoginRequest(email=DEV_TEST_STUDENT_EMAIL), c)
        check("admin dev-login role", admin_auth.user.role == "admin")
        check("admin JWT role in response", admin_auth.user.role == "admin")
        check("test student dev-login role", student_auth.user.role == "student")
        check("test student profile_completed", student_auth.user.profile_completed is True)
        check("test student_id", student_auth.user.student_id == DEV_TEST_STUDENT_ID)
    except Exception:
        check("dev accounts", False, traceback.format_exc().splitlines()[-1])

    # ── 3. Profile completion ─────────────────────────────────────────────────
    print("\n[3] Profile completion")
    test_student_id = f"261-{uuid.uuid4().hex[:8]}"
    try:
        async with pool.acquire() as c:
            uid_hex = raw_user_id.replace("-", "")
            await c.execute(
                "UPDATE users SET student_id = $1, name = $2 WHERE id = $3",
                test_student_id,
                "Test User",
                uid_hex,
            )
            row = await c.fetchrow("SELECT student_id FROM users WHERE id = $1", uid_hex)
        check("student_id set", row["student_id"] == test_student_id)
    except Exception:
        check("profile completion", False, traceback.format_exc().splitlines()[-1])

    # ── 4. Booking slot A tomorrow ────────────────────────────────────────────
    print("\n[4] Create booking (slot A, tomorrow)")
    tomorrow = date.today() + timedelta(days=1)
    day_after = date.today() + timedelta(days=2)
    booking1_id = None
    try:
        from database.booking_tx import BookingError, create_booking
        from services.models import Booking

        async with pool.acquire() as c:
            turf = await c.fetchrow("SELECT id FROM turfs WHERE name = $1", "Main Turf")
            slot = await c.fetchrow(
                "SELECT id, start_time, end_time FROM slot_templates WHERE turf_id = $1 AND slot_key = $2",
                turf["id"], "A",
            )
            from datetime import time
            row = await create_booking(
                c,
                user_id=uuid.UUID(raw_user_id),
                turf_id=turf["id"],
                slot_template_id=slot["id"],
                booking_date=tomorrow,
                slot_key="A",
                slot_start=slot["start_time"] if isinstance(slot["start_time"], time) else time(16, 0),
                slot_end=slot["end_time"] if isinstance(slot["end_time"], time) else time(17, 0),
            )
        booking1_id = str(row["id"])
        check("booking created", row["status"] == "booked")
        check("booking_id returned", bool(booking1_id))

        # Serialize through Pydantic to catch timestamp issues
        from routes.bookings import _row_to_booking
        bobj = _row_to_booking(row)
        check("Booking Pydantic valid", isinstance(bobj, Booking))
        check("created_at is datetime", hasattr(bobj.created_at, "year"))
    except Exception:
        check("create booking", False, traceback.format_exc().splitlines()[-1])

    # ── 5. My bookings ────────────────────────────────────────────────────────
    print("\n[5] GET /api/bookings/me (via query)")
    try:
        from routes.bookings import _row_to_booking, _BOOKING_SELECT

        async with pool.acquire() as c:
            uid_obj = uuid.UUID(raw_user_id)
            rows = await c.fetch(
                _BOOKING_SELECT + " WHERE b.user_id = $1",
                uid_obj,
            )
        check("rows returned", len(rows) >= 1)
        bookings = [_row_to_booking(dict(r)) for r in rows]
        check("all rows serialize without error", len(bookings) == len(rows))
    except Exception:
        check("my bookings", False, traceback.format_exc().splitlines()[-1])

    # ── 6. Slot board for tomorrow ────────────────────────────────────────────
    print("\n[6] GET /api/bookings/date/{date}")
    try:
        from routes.bookings import _row_to_booking, _BOOKING_SELECT

        async with pool.acquire() as c:
            turf = await c.fetchrow("SELECT id FROM turfs WHERE name = $1", "Main Turf")
            rows = await c.fetch(
                _BOOKING_SELECT + " WHERE b.booking_date = $1 AND b.turf_id = $2 AND b.status = 'booked'",
                tomorrow, turf["id"],
            )
        booked_keys = [r["slot_key"] for r in rows]
        check("slot A shows as booked", "A" in booked_keys)
        for r in rows:
            _row_to_booking(dict(r))  # must not raise
        check("slot board serializes OK", True)
    except Exception:
        check("slot board", False, traceback.format_exc().splitlines()[-1])

    # ── 7. Duplicate same-date → 409 ──────────────────────────────────────────
    print("\n[7] Duplicate booking same date -> BookingError 409")
    try:
        from database.booking_tx import BookingError, create_booking

        async with pool.acquire() as c:
            turf = await c.fetchrow("SELECT id FROM turfs WHERE name = $1", "Main Turf")
            slot_b = await c.fetchrow(
                "SELECT id, start_time, end_time FROM slot_templates WHERE turf_id = $1 AND slot_key = $2",
                turf["id"], "B",
            )
            from datetime import time
            try:
                await create_booking(
                    c,
                    user_id=uuid.UUID(raw_user_id),
                    turf_id=turf["id"],
                    slot_template_id=slot_b["id"],
                    booking_date=tomorrow,
                    slot_key="B",
                    slot_start=slot_b["start_time"] if isinstance(slot_b["start_time"], time) else time(17, 0),
                    slot_end=slot_b["end_time"] if isinstance(slot_b["end_time"], time) else time(18, 0),
                )
                check("duplicate rejected as BookingError", False, "no error raised")
            except BookingError as e:
                check("duplicate rejected as BookingError", e.http_status == 409)
    except Exception:
        check("duplicate booking check", False, traceback.format_exc().splitlines()[-1])

    # ── 8. Different date → succeeds ──────────────────────────────────────────
    print("\n[8] Booking different date (day+2) succeeds")
    try:
        from database.booking_tx import create_booking
        from routes.bookings import _row_to_booking

        async with pool.acquire() as c:
            turf = await c.fetchrow("SELECT id FROM turfs WHERE name = $1", "Main Turf")
            slot = await c.fetchrow(
                "SELECT id, start_time, end_time FROM slot_templates WHERE turf_id = $1 AND slot_key = $2",
                turf["id"], "A",
            )
            from datetime import time
            row = await create_booking(
                c,
                user_id=uuid.UUID(raw_user_id),
                turf_id=turf["id"],
                slot_template_id=slot["id"],
                booking_date=day_after,
                slot_key="A",
                slot_start=slot["start_time"] if isinstance(slot["start_time"], time) else time(16, 0),
                slot_end=slot["end_time"] if isinstance(slot["end_time"], time) else time(17, 0),
            )
        check("second booking (day+2) created", row["status"] == "booked")
        bobj = _row_to_booking(row)
        check("second booking serializes OK", hasattr(bobj.created_at, "year"))
    except Exception:
        check("different date booking", False, traceback.format_exc().splitlines()[-1])

    # ── 9. Cancel booking ownership ───────────────────────────────────────────
    print("\n[9] Cancel booking ownership")
    try:
        from database.booking_tx import BookingError, cancel_booking
        from services.uuid_util import uuid_hex, uuid_same

        sample = uuid.uuid4()
        hex_id = sample.hex
        dashed = str(sample)
        check("uuid_same hex vs UUID", uuid_same(hex_id, sample))
        check("uuid_same dashed vs hex", uuid_same(dashed, hex_id))
        check("uuid_hex normalizes dashed", uuid_hex(dashed) == hex_id)

        async with pool.acquire() as c:
            result = await cancel_booking(
                c,
                booking_id=uuid.UUID(booking1_id),
                cancelled_by_user_id=uuid.UUID(raw_user_id),
            )
        check("own booking cancel succeeds", result["status"] == "cancelled")

        # Second user must not cancel the day+2 booking owned by the first user.
        other_email = f"other-{uuid.uuid4().hex[:8]}@diu.edu.bd"
        from services.serialize import utc_now_iso
        now = utc_now_iso()
        async with pool.acquire() as c:
            other_id = await c.fetchval(
                """INSERT INTO users (name, email, role, is_active, created_at, updated_at)
                   VALUES ($1, $2, 'student', TRUE, $3, $3)
                   RETURNING id""",
                "Other User",
                other_email,
                now,
            )
            other_booking = await c.fetchrow(
                "SELECT id FROM bookings WHERE user_id = $1 AND status = 'booked' LIMIT 1",
                uuid.UUID(raw_user_id),
            )
            try:
                await cancel_booking(
                    c,
                    booking_id=uuid.UUID(str(other_booking["id"])),
                    cancelled_by_user_id=uuid.UUID(str(other_id)),
                )
                check("other user cancel rejected", False, "no error raised")
            except BookingError as e:
                check("other user cancel rejected", e.http_status == 403)
    except Exception:
        check("cancel booking ownership", False, traceback.format_exc().splitlines()[-1])

    # ── 10. Malformed legacy timestamp round-trip ─────────────────────────────
    print("\n[10] Malformed legacy timestamp parse+serialize")
    try:
        from services.serialize import parse_dt, serialize_dt
        cases = [
            "2026-06-22T16:00:09.09.794Z",
            "2026-06-22T16:03:39.39.613Z",
            "2026-06-22T15:35:349485Z",
            "2026-06-22T16:00:09.794000Z",
        ]
        for ts in cases:
            dt = parse_dt(ts)
            out = serialize_dt(ts)
            ok = dt is not None and out is not None and "T" in out and out.endswith("Z")
            check(f"  parse '{ts[:30]}...'", ok)
    except Exception:
        check("timestamp parse", False, traceback.format_exc().splitlines()[-1])

    # ── Teardown ──────────────────────────────────────────────────────────────
    await close_pool(pool)
    try:
        p.unlink(missing_ok=True)
    except PermissionError:
        pass

    _print_summary()


def _print_summary() -> None:
    print("\n=== Summary ===")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  {PASS} {passed} passed   {FAIL} {failed} failed")
    if failed:
        print("\nFailed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  {FAIL} {name}: {detail}")
        sys.exit(1)
    else:
        print("\nAll checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
