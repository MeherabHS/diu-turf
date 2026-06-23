"""Booking access roles + access request queue.

Revision ID: 008
Revises: 007
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE users
    ADD CONSTRAINT users_role_check
    CHECK (role IN ('viewer', 'booker', 'student', 'admin', 'super_admin'));

UPDATE users SET role = 'viewer' WHERE role = 'student';

UPDATE users SET role = 'booker'
 WHERE role = 'viewer'
   AND id IN (SELECT DISTINCT user_id FROM bookings);

CREATE TABLE IF NOT EXISTS booking_access_requests (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name        TEXT        NOT NULL,
    email       TEXT        NOT NULL,
    student_id  TEXT,
    reason      TEXT,
    status      TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by UUID        REFERENCES users (id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_booking_access_requests_user
    ON booking_access_requests (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_booking_access_requests_status
    ON booking_access_requests (status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_booking_access_requests_one_pending
    ON booking_access_requests (user_id)
    WHERE status = 'pending';
"""

_DOWNGRADE_SQL = """
DROP INDEX IF EXISTS idx_booking_access_requests_one_pending;
DROP INDEX IF EXISTS idx_booking_access_requests_status;
DROP INDEX IF EXISTS idx_booking_access_requests_user;
DROP TABLE IF EXISTS booking_access_requests;

UPDATE users SET role = 'student' WHERE role IN ('viewer', 'booker');

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE users
    ADD CONSTRAINT users_role_check
    CHECK (role IN ('student', 'admin', 'super_admin'));
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
