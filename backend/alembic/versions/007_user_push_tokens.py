"""User Expo push tokens for waitlist promotion notifications.

Revision ID: 007
Revises: 006
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
CREATE TABLE IF NOT EXISTS user_push_tokens (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expo_push_token TEXT        NOT NULL,
    platform        TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT user_push_tokens_user_token_unique UNIQUE (user_id, expo_push_token)
);

CREATE INDEX IF NOT EXISTS idx_user_push_tokens_user_active
    ON user_push_tokens (user_id)
    WHERE is_active = TRUE;
"""

_DOWNGRADE_SQL = """
DROP TABLE IF EXISTS user_push_tokens;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
