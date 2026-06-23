"""Performance indexes — composite booking lookups.

Revision ID: 003
Revises: 002
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
CREATE INDEX IF NOT EXISTS idx_bookings_turf_date
    ON bookings (turf_id, booking_date);

CREATE INDEX IF NOT EXISTS idx_bookings_user_date
    ON bookings (user_id, booking_date);
"""

_DOWNGRADE_SQL = """
DROP INDEX IF EXISTS idx_bookings_turf_date;
DROP INDEX IF EXISTS idx_bookings_user_date;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
