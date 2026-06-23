"""Add waitlists(status) index for status-filtered queries.

Revision ID: 005
Revises: 004
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
CREATE INDEX IF NOT EXISTS idx_waitlists_status
    ON waitlists (status);
"""

_DOWNGRADE_SQL = """
DROP INDEX IF EXISTS idx_waitlists_status;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
