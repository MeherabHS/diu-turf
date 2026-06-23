"""Initial PostgreSQL schema — all 11 tables.

Revision ID: 001
Revises: (none — this is the first migration)
Create Date: 2026-06-22 UTC

Tables created
──────────────
  users, turfs, slot_templates, bookings, waitlists,
  maintenance_days, attendance, notifications,
  activity_logs, audit_logs, analytics_events

Design decisions
────────────────
UUID primary keys
  All PKs use gen_random_uuid() (requires pgcrypto extension).
  No sequential integers that leak row counts to clients.

citext for email
  Provides case-insensitive unique constraint at DB level.
  Eliminates the need for lower() in every query.

Partial unique indexes for bookings / waitlists
  PostgreSQL lets us enforce "one active booking per slot/day" with
  a WHERE status = 'booked' clause.  Cancelled rows are ignored by
  the unique index, so a slot can be re-booked after cancellation.

Transaction safety (TODO for Phase 5/6)
  The unique indexes are the final safety net, but booking creation
  and waitlist promotion MUST run inside explicit transactions with
  SELECT ... FOR UPDATE to avoid race conditions under high concurrency.
  See TODO comments in routes/bookings.py (Phase 5) and routes/admin.py
  (Phase 6) for the exact patterns.

Downgrade
  Drops all tables in reverse dependency order (CASCADE).
  Irreversible data loss — only use on a dev/test database.
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Full schema SQL
# ---------------------------------------------------------------------------
# Written as a single op.execute() block for readability and portability.
# Raw SQL is preferred here over SQLAlchemy column definitions because:
#   1. We use asyncpg (not SQLAlchemy ORM) at runtime — no model drift.
#   2. PostgreSQL-specific features (citext, partial indexes, JSONB default)
#      are easier to express in SQL than in SA constructs.
#   3. The migration is self-documenting as valid PostgreSQL DDL.
# ---------------------------------------------------------------------------

_UPGRADE_SQL = """
-- ── Extensions ────────────────────────────────────────────────────────────────
-- pgcrypto  → gen_random_uuid()
-- citext    → case-insensitive text type (email uniqueness without lower())
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;


-- ── users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name              TEXT        NOT NULL,
    email             CITEXT      NOT NULL,
    password_hash     TEXT        NOT NULL,
    student_id        TEXT        NOT NULL,
    department        TEXT,
    batch             TEXT,
    avatar_url        TEXT,
    role              TEXT        NOT NULL DEFAULT 'student'
                                  CHECK (role IN ('student', 'admin')),
    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
    suspension_until  TIMESTAMPTZ,
    suspension_reason TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT users_email_unique      UNIQUE (email),
    CONSTRAINT users_student_id_unique UNIQUE (student_id)
);

CREATE INDEX IF NOT EXISTS idx_users_role      ON users (role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users (is_active);


-- ── turfs ─────────────────────────────────────────────────────────────────────
-- Designed for multiple turfs in future. Phase 3–6 seeds one default turf.
CREATE TABLE IF NOT EXISTS turfs (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    location   TEXT,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── slot_templates ────────────────────────────────────────────────────────────
-- Each row = one bookable slot definition for a turf.
-- Phase 3 seeds: Slot A 16:00-17:00, Slot B 17:00-18:00, Slot C 18:00-19:00.
-- Future: add rows here to support more turfs or flexible time windows.
CREATE TABLE IF NOT EXISTS slot_templates (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    turf_id    UUID        NOT NULL REFERENCES turfs (id) ON DELETE CASCADE,
    slot_key   TEXT        NOT NULL,   -- 'A' | 'B' | 'C' (or more in future)
    start_time TIME        NOT NULL,
    end_time   TIME        NOT NULL,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,

    CONSTRAINT slot_templates_turf_key_unique UNIQUE (turf_id, slot_key)
);

CREATE INDEX IF NOT EXISTS idx_slot_templates_turf ON slot_templates (turf_id);


-- ── bookings ──────────────────────────────────────────────────────────────────
-- TODO(phase5): booking creation MUST use SELECT ... FOR UPDATE inside a
-- transaction to prevent race conditions between the cap check and INSERT.
-- The partial unique indexes below are the last-resort safety net.
CREATE TABLE IF NOT EXISTS bookings (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES users (id),
    turf_id             UUID        NOT NULL REFERENCES turfs (id),
    slot_template_id    UUID        NOT NULL REFERENCES slot_templates (id),
    booking_date        DATE        NOT NULL,
    status              TEXT        NOT NULL DEFAULT 'booked'
                                    CHECK (status IN (
                                        'booked', 'cancelled', 'completed', 'no_show'
                                    )),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at        TIMESTAMPTZ,
    cancellation_reason TEXT
);

-- One active booking per slot per day (double-booking the same slot prevented).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_slot_per_day
    ON bookings (turf_id, slot_template_id, booking_date)
    WHERE status = 'booked';

-- One active booking per user per day (one-slot-per-day rule).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_booking_per_user_per_day
    ON bookings (user_id, booking_date)
    WHERE status = 'booked';

-- Single-column indexes covering all queried dimensions.
CREATE INDEX IF NOT EXISTS idx_bookings_user_id          ON bookings (user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_turf_id          ON bookings (turf_id);
CREATE INDEX IF NOT EXISTS idx_bookings_slot_template_id ON bookings (slot_template_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date             ON bookings (booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_status           ON bookings (status);
CREATE INDEX IF NOT EXISTS idx_bookings_created          ON bookings (created_at DESC);

-- Composite indexes for the two hottest query paths.
-- Weekly usage cap check: "how many bookings did user X make this week?"
CREATE INDEX IF NOT EXISTS idx_bookings_user_created
    ON bookings (user_id, created_at DESC);

-- Date + status board: "all booked slots on date D" (home screen, date overview).
CREATE INDEX IF NOT EXISTS idx_bookings_date_status
    ON bookings (booking_date, status)
    WHERE status = 'booked';


-- ── waitlists ─────────────────────────────────────────────────────────────────
-- TODO(phase6): waitlist promotion MUST run inside a transaction that verifies
-- the slot is still empty before creating the promoted booking row.
CREATE TABLE IF NOT EXISTS waitlists (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL REFERENCES users (id),
    turf_id          UUID        NOT NULL REFERENCES turfs (id),
    slot_template_id UUID        NOT NULL REFERENCES slot_templates (id),
    booking_date     DATE        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'waiting'
                                 CHECK (status IN (
                                     'waiting', 'promoted', 'cancelled', 'expired'
                                 )),
    position         INTEGER     NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promoted_at      TIMESTAMPTZ
);

-- One active waitlist entry per user per slot per day.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_waitlist_per_user
    ON waitlists (user_id, turf_id, slot_template_id, booking_date)
    WHERE status = 'waiting';

-- Fast lookup of next-in-queue for promotion (ordered by join time).
CREATE INDEX IF NOT EXISTS idx_waitlists_position
    ON waitlists (turf_id, slot_template_id, booking_date, position)
    WHERE status = 'waiting';

-- For "show my waitlist entries" (user-facing screen).
CREATE INDEX IF NOT EXISTS idx_waitlists_user_id
    ON waitlists (user_id, booking_date);

-- For date-scoped admin or slot queries.
CREATE INDEX IF NOT EXISTS idx_waitlists_date
    ON waitlists (booking_date);


-- ── maintenance_days ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maintenance_days (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    turf_id    UUID        NOT NULL REFERENCES turfs (id),
    date       DATE        NOT NULL,
    reason     TEXT,
    created_by UUID        REFERENCES users (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT maintenance_days_turf_date_unique UNIQUE (turf_id, date)
);

CREATE INDEX IF NOT EXISTS idx_maintenance_date ON maintenance_days (date);


-- ── attendance ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID        NOT NULL UNIQUE REFERENCES bookings (id),
    status     TEXT        NOT NULL
               CHECK (status IN ('present', 'absent', 'late')),
    marked_by  UUID        REFERENCES users (id),
    marked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note       TEXT
);


-- ── notifications ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users (id),
    title      TEXT        NOT NULL,
    body       TEXT        NOT NULL,
    type       TEXT,
    is_read    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_created
    ON notifications (user_id, created_at DESC);


-- ── activity_logs ─────────────────────────────────────────────────────────────
-- Public event feed (bookings, cancellations, etc.).
CREATE TABLE IF NOT EXISTS activity_logs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID        REFERENCES users (id),
    event_type    TEXT        NOT NULL,
    message       TEXT        NOT NULL,
    metadata      JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_user    ON activity_logs (actor_user_id);


-- ── audit_logs ────────────────────────────────────────────────────────────────
-- Admin mutations only — every write action by an admin is recorded here.
-- IMMUTABILITY: rows are INSERT-only.  No UPDATE or DELETE is ever issued by
-- application code.  In production, enforce with:
--   REVOKE UPDATE, DELETE ON audit_logs FROM <app_db_role>;
-- A future migration can add this REVOKE once a restricted DB role is set up.
CREATE TABLE IF NOT EXISTS audit_logs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id    UUID        NOT NULL REFERENCES users (id),
    action      TEXT        NOT NULL,
    target_type TEXT,
    target_id   UUID,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_admin   ON audit_logs (admin_id);


-- ── analytics_events ──────────────────────────────────────────────────────────
-- Append-only ML telemetry. Never update rows; only insert.
-- Cancellation cap check needs: WHERE user_id=$1 AND cancelled_at >= week_start.
-- Covered by idx_bookings_user_created + status filter; no extra index needed.
CREATE TABLE IF NOT EXISTS analytics_events (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        REFERENCES users (id),
    event_name    TEXT        NOT NULL,
    event_payload JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_created    ON analytics_events (created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_event_name ON analytics_events (event_name);
"""

_DOWNGRADE_SQL = """
-- Drops all tables in reverse dependency order.
-- WARNING: destroys all data. Dev/test only.
DROP TABLE IF EXISTS analytics_events    CASCADE;
DROP TABLE IF EXISTS audit_logs          CASCADE;
DROP TABLE IF EXISTS activity_logs       CASCADE;
DROP TABLE IF EXISTS notifications       CASCADE;
DROP TABLE IF EXISTS attendance          CASCADE;
DROP TABLE IF EXISTS maintenance_days    CASCADE;
DROP TABLE IF EXISTS waitlists           CASCADE;
DROP TABLE IF EXISTS bookings            CASCADE;
DROP TABLE IF EXISTS slot_templates      CASCADE;
DROP TABLE IF EXISTS turfs               CASCADE;
DROP TABLE IF EXISTS users               CASCADE;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
