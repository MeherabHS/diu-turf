"""Fair-use limit helpers — PostgreSQL + SQLite dev compatible."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

WEEKLY_BOOKING_LIMIT      = 5
WEEKLY_CANCELLATION_LIMIT = 3


def week_start_utc(now: datetime | None = None) -> datetime:
    """Monday 00:00:00 UTC for the week containing *now*."""
    n = (now or datetime.now(timezone.utc)).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    return n - timedelta(days=n.weekday())


def _week_start_param(conn: Any) -> Any:
    """Return week-start in the right type for the current DB backend.

    asyncpg (PostgreSQL) → datetime object
    SQLiteConnection      → ISO string (SQLite stores timestamps as TEXT)
    """
    from database.sqlite_adapter import SQLiteConnection
    ws = week_start_utc()
    if isinstance(conn, SQLiteConnection):
        return ws.strftime("%Y-%m-%dT%H:%M:%S") + ".000000Z"
    return ws


async def weekly_usage(conn: Any, user_id: str | UUID) -> dict:
    """Return booking and cancellation counts for the current week."""
    if isinstance(user_id, str):
        uid = UUID(user_id)
    else:
        uid = user_id

    start = week_start_utc()
    start_param = _week_start_param(conn)

    bookings_made: int = await conn.fetchval(
        "SELECT COUNT(*) FROM bookings WHERE user_id = $1 AND created_at >= $2",
        uid, start_param,
    )
    cancellations_made: int = await conn.fetchval(
        """SELECT COUNT(*) FROM bookings
           WHERE user_id = $1 AND status = 'cancelled' AND cancelled_at >= $2""",
        uid, start_param,
    )
    return {
        "week_start":          start.date().isoformat(),
        "bookings_made":       bookings_made,
        "bookings_limit":      WEEKLY_BOOKING_LIMIT,
        "cancellations_made":  cancellations_made,
        "cancellations_limit": WEEKLY_CANCELLATION_LIMIT,
    }
