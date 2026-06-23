"""Verify MVP performance indexes exist in Alembic migration SQL."""
from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

MIGRATION_FILES = sorted(MIGRATIONS_DIR.glob("*.py"))

# Each entry: (table, index DDL fragment that must appear in combined migration SQL)
REQUIRED_INDEX_FRAGMENTS = [
    ("bookings", "on bookings (user_id)"),
    ("bookings", "on bookings (booking_date)"),
    ("bookings", "on bookings (status)"),
    ("bookings", "on bookings (user_id, booking_date)"),
    ("bookings", "on bookings (turf_id, booking_date)"),
    ("bookings", "on bookings (slot_template_id)"),
    ("waitlists", "on waitlists (user_id, booking_date)"),
    ("waitlists", "on waitlists (turf_id, slot_template_id, booking_date"),
    ("waitlists", "on waitlists (status)"),
    ("notifications", "on notifications (user_id, created_at desc)"),
    ("activity_logs", "on activity_logs (created_at desc)"),
    ("activity_logs", "on activity_logs (actor_user_id)"),
    ("users", "unique (email)"),
    ("users", "unique (student_id)"),
    ("users", "on users (role)"),
    ("users", "on users (is_active)"),
]


def _migration_sql() -> str:
    parts: list[str] = []
    for path in MIGRATION_FILES:
        if path.name == "__init__.py":
            continue
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts).lower()


def test_required_mvp_indexes_present_in_migrations() -> None:
    sql = _migration_sql()
    for table, fragment in REQUIRED_INDEX_FRAGMENTS:
        assert fragment.lower() in sql, (
            f"Missing index for {table!r}: expected fragment {fragment!r}"
        )
