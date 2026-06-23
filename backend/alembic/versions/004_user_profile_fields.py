"""User profile fields — room, hostel, phone.

Revision ID: 004
Revises: 003
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS room_number TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hostel_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;
"""

_DOWNGRADE_SQL = """
ALTER TABLE users DROP COLUMN IF EXISTS phone;
ALTER TABLE users DROP COLUMN IF EXISTS hostel_name;
ALTER TABLE users DROP COLUMN IF EXISTS room_number;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
