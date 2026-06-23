"""services/seed.py — DEPRECATED.

MongoDB-based seed replaced by database/seed_pg.py (asyncpg).
This shim delegates to the PostgreSQL seed so existing imports still work.
"""
from database.seed_pg import (  # noqa: F401
    seed,
    ADMIN_EMAIL,
    DEV_ADMIN_EMAIL,
    DEV_TEST_STUDENT_EMAIL,
    DEV_TEST_STUDENT_ID,
)

async def seed_admin(pool) -> None:
    """Thin wrapper kept for any legacy call sites."""
    async with pool.acquire() as conn:
        await seed(conn)
