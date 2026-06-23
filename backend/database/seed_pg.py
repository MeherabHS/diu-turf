"""Database seed — default turf, slot templates, and admin user.

Works with PostgreSQL (asyncpg) and SQLite (local dev adapter).
Idempotent — safe to run on every startup.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, time, timezone
from typing import Any

import bcrypt
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

TURF_NAME = "Main Turf"
TURF_LOCATION = "DIU Hostel Grounds, Daffodil International University"

SLOT_DEFINITIONS: list[tuple[str, time, time]] = [
    ("A", time(16, 0), time(17, 0)),
    ("B", time(17, 0), time(18, 0)),
    ("C", time(18, 0), time(19, 0)),
]

# Permanent dev accounts — ensured on every startup (idempotent).
DEV_ADMIN_EMAIL = "261-35-113@diu.edu.bd"
DEV_ADMIN_STUDENT_ID = "261-35-113"
DEV_ADMIN_NAME = "Admin User"

DEV_TEST_STUDENT_EMAIL = "252-35-166@diu.edu.bd"
DEV_TEST_STUDENT_ID = "252-35-166"
DEV_TEST_STUDENT_NAME = "Test Student"
DEV_TEST_STUDENT_DEPARTMENT = "SWE"
DEV_TEST_STUDENT_BATCH = "47"
DEV_TEST_STUDENT_ROOM = "402"
DEV_TEST_STUDENT_HOSTEL = "DIU Boys Hostel"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", DEV_ADMIN_EMAIL).strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_DEFAULT_PASSWORD", "Admin@DIU2025!")
ADMIN_NAME = DEV_ADMIN_NAME
ADMIN_STUDENT_ID = DEV_ADMIN_STUDENT_ID


def _hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _id_str(value: Any) -> str:
    return str(value).replace("-", "").lower()


async def _commit_if_needed(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if commit is not None:
        await commit()


async def _ensure_user(
    conn: Any,
    *,
    email: str,
    name: str,
    role: str,
    student_id: str,
    password_hash: str | None = None,
    department: str | None = None,
    batch: str | None = None,
    room_number: str | None = None,
    hostel_name: str | None = None,
    phone: str | None = None,
) -> str:
    """Create user if missing; otherwise refresh profile fields (idempotent)."""
    email = email.strip().lower()
    now = datetime.now(timezone.utc)
    existing_id = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
    if not existing_id:
        user_id = await conn.fetchval(
            """INSERT INTO users
                   (name, email, password_hash, student_id, department, batch,
                    room_number, hostel_name, phone,
                    role, is_active, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, TRUE, $11, $11)
               RETURNING id""",
            name,
            email,
            password_hash,
            student_id,
            department,
            batch,
            room_number,
            hostel_name,
            phone or None,
            role,
            now,
        )
        await _commit_if_needed(conn)
        log.info("Created user  : %s  role=%s  (id=%s)", email, role, user_id)
        return str(user_id)

    await conn.execute(
        """UPDATE users SET
               name = $2,
               student_id = $3,
               role = $4,
               is_active = TRUE,
               suspension_until = NULL,
               suspension_reason = NULL,
               department = $5,
               batch = $6,
               room_number = $7,
               hostel_name = $8,
               phone = $9,
               updated_at = $10
           WHERE id = $1""",
        existing_id,
        name,
        student_id,
        role,
        department,
        batch,
        room_number,
        hostel_name,
        phone or None,
        now,
    )
    await _commit_if_needed(conn)
    log.info("User exists   : %s  role=%s profile ensured  (id=%s)", email, role, existing_id)
    return str(existing_id)


async def seed(conn: Any) -> None:
    """Insert missing seed rows. All operations are idempotent."""
    for col in ("room_number", "hostel_name", "phone", "auth_provider"):
        try:
            if col == "auth_provider":
                await conn.execute(
                    "ALTER TABLE users ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'password'"
                )
            else:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            await _commit_if_needed(conn)
        except Exception:
            pass

    # 1. Turf ─────────────────────────────────────────────────────────────────
    turf_id = await conn.fetchval(
        "SELECT id FROM turfs WHERE name = $1 AND is_active = TRUE LIMIT 1",
        TURF_NAME,
    )
    if not turf_id:
        turf_id = await conn.fetchval(
            """INSERT INTO turfs (name, location)
               VALUES ($1, $2)
               RETURNING id""",
            TURF_NAME,
            TURF_LOCATION,
        )
        await _commit_if_needed(conn)
        log.info("Created turf  : %s  (id=%s)", TURF_NAME, turf_id)
    else:
        log.info("Turf exists   : %s  (id=%s)", TURF_NAME, turf_id)

    turf_id = _id_str(turf_id)
    turf_row = await conn.fetchrow(
        "SELECT id, name FROM turfs WHERE id = $1",
        turf_id,
    )
    if turf_row is None:
        raise RuntimeError(
            f"Seed failed: turf '{TURF_NAME}' not found after insert (turf_id={turf_id})"
        )
    turf_id = _id_str(turf_row["id"])
    log.info("Verified turf row: id=%s name=%s", turf_id, turf_row["name"])

    # 2. Slot templates ───────────────────────────────────────────────────────
    for slot_key, start, end in SLOT_DEFINITIONS:
        existing = await conn.fetchval(
            """SELECT id FROM slot_templates
               WHERE turf_id = $1 AND slot_key = $2""",
            turf_id,
            slot_key,
        )
        if not existing:
            log.info(
                "Inserting slot: turf_id=%s slot_key=%s start=%s end=%s",
                turf_id,
                slot_key,
                start.strftime("%H:%M:%S"),
                end.strftime("%H:%M:%S"),
            )
            slot_id = await conn.fetchval(
                """INSERT INTO slot_templates (turf_id, slot_key, start_time, end_time)
                   VALUES ($1, $2, $3, $4)
                   RETURNING id""",
                turf_id,
                slot_key,
                start,
                end,
            )
            await _commit_if_needed(conn)
            log.info(
                "Created slot  : %s  %s–%s  turf_id=%s  id=%s",
                slot_key,
                start.strftime("%H:%M"),
                end.strftime("%H:%M"),
                turf_id,
                slot_id,
            )
        else:
            log.info("Slot exists   : %s  (id=%s)", slot_key, existing)

    # 3. Dev admin user ────────────────────────────────────────────────────────
    admin_email = DEV_ADMIN_EMAIL
    existing_admin = await conn.fetchval(
        "SELECT id FROM users WHERE email = $1",
        admin_email,
    )
    admin_password_hash = None if existing_admin else _hash(ADMIN_PASSWORD)
    await _ensure_user(
        conn,
        email=admin_email,
        name=DEV_ADMIN_NAME,
        role="admin",
        student_id=DEV_ADMIN_STUDENT_ID,
        password_hash=admin_password_hash,
        department="SWE",
        batch="47",
    )

    # 4. Dev test student ───────────────────────────────────────────────────────
    await _ensure_user(
        conn,
        email=DEV_TEST_STUDENT_EMAIL,
        name=DEV_TEST_STUDENT_NAME,
        role="student",
        student_id=DEV_TEST_STUDENT_ID,
        password_hash=None,
        department=DEV_TEST_STUDENT_DEPARTMENT,
        batch=DEV_TEST_STUDENT_BATCH,
        room_number=DEV_TEST_STUDENT_ROOM,
        hostel_name=DEV_TEST_STUDENT_HOSTEL,
        phone="",
    )

    log.info("Seed complete.")

    # Ensure push token table exists on older SQLite dev databases.
    try:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS user_push_tokens (
                   id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
                   user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                   expo_push_token TEXT NOT NULL,
                   platform TEXT,
                   is_active INTEGER NOT NULL DEFAULT 1,
                   created_at TEXT NOT NULL DEFAULT (datetime('now')),
                   updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                   UNIQUE (user_id, expo_push_token)
               )"""
        )
        await _commit_if_needed(conn)
    except Exception:
        pass


async def _main() -> None:
    raw_dsn = os.environ["DATABASE_URL"]
    if raw_dsn.startswith("sqlite:///"):
        from database.db_config import BACKEND_DIR
        from database.sqlite_adapter import create_sqlite_pool, close_sqlite_pool
        from pathlib import Path

        path_str = raw_dsn.replace("sqlite:///", "", 1)
        path = Path(path_str)
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        pool = await create_sqlite_pool(path)
        try:
            async with pool.acquire() as conn:
                await seed(conn)
        finally:
            await close_sqlite_pool(pool)
    else:
        import asyncpg

        dsn = raw_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncpg.connect(dsn)
        try:
            await seed(conn)
        finally:
            await conn.close()
    log.info("Seed script finished.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    asyncio.run(_main())
