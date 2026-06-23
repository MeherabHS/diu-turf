"""Password auth — auth_provider column.

Revision ID: 006
Revises: 005
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'password';

UPDATE users
   SET auth_provider = 'password'
 WHERE auth_provider IS NULL OR TRIM(auth_provider) = '';
"""

_DOWNGRADE_SQL = """
ALTER TABLE users DROP COLUMN IF EXISTS auth_provider;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
