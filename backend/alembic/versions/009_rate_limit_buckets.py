"""DB-backed rate limit buckets for multi-instance deployments.

Revision ID: 009
Revises: 008
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    bucket_key     TEXT    NOT NULL,
    window_start   BIGINT  NOT NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (bucket_key, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_buckets_window
    ON rate_limit_buckets (window_start);
"""

_DOWNGRADE_SQL = """
DROP TABLE IF EXISTS rate_limit_buckets;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
