"""SQLite schema for local development — mirrors PostgreSQL migrations 001 + 002."""
from __future__ import annotations

_SQLITE_NOW = (
    "(strftime('%Y-%m-%dT%H:%M:%S', 'now') || '.' || "
    "substr('000000' || strftime('%f', 'now'), -6) || 'Z')"
)

_SCHEMA_TEMPLATE = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id                TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name              TEXT NOT NULL,
    email             TEXT NOT NULL COLLATE NOCASE,
    password_hash     TEXT,
    student_id        TEXT,
    department        TEXT,
    batch             TEXT,
    room_number       TEXT,
    hostel_name       TEXT,
    phone             TEXT,
    avatar_url        TEXT,
    google_sub        TEXT,
    auth_provider     TEXT NOT NULL DEFAULT 'password',
    role              TEXT NOT NULL DEFAULT 'student'
                      CHECK (role IN ('student', 'admin', 'super_admin')),
    is_active         INTEGER NOT NULL DEFAULT 1,
    suspension_until  TEXT,
    suspension_reason TEXT,
    last_login        TEXT,
    created_at        TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    updated_at        TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    UNIQUE (email)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student_id
    ON users (student_id) WHERE student_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub
    ON users (google_sub) WHERE google_sub IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users (is_active);

CREATE TABLE IF NOT EXISTS turfs (
    id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name       TEXT NOT NULL,
    location   TEXT,
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT __SQLITE_NOW__
);

CREATE TABLE IF NOT EXISTS slot_templates (
    id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    turf_id    TEXT NOT NULL REFERENCES turfs (id) ON DELETE CASCADE,
    slot_key   TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1,
    UNIQUE (turf_id, slot_key)
);

CREATE INDEX IF NOT EXISTS idx_slot_templates_turf ON slot_templates (turf_id);

CREATE TABLE IF NOT EXISTS bookings (
    id                  TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id             TEXT NOT NULL REFERENCES users (id),
    turf_id             TEXT NOT NULL REFERENCES turfs (id),
    slot_template_id    TEXT NOT NULL REFERENCES slot_templates (id),
    booking_date        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'booked'
                        CHECK (status IN ('booked', 'cancelled', 'completed', 'no_show')),
    created_at          TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    cancelled_at        TEXT,
    cancellation_reason TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_slot_per_day
    ON bookings (turf_id, slot_template_id, booking_date)
    WHERE status = 'booked';
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_booking_per_user_per_day
    ON bookings (user_id, booking_date)
    WHERE status = 'booked';
CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings (user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_turf_id ON bookings (turf_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings (booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings (status);
CREATE INDEX IF NOT EXISTS idx_bookings_user_created ON bookings (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bookings_date_status
    ON bookings (booking_date, status) WHERE status = 'booked';
CREATE INDEX IF NOT EXISTS idx_bookings_turf_date
    ON bookings (turf_id, booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_user_date
    ON bookings (user_id, booking_date);

CREATE TABLE IF NOT EXISTS waitlists (
    id               TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id          TEXT NOT NULL REFERENCES users (id),
    turf_id          TEXT NOT NULL REFERENCES turfs (id),
    slot_template_id TEXT NOT NULL REFERENCES slot_templates (id),
    booking_date     TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'waiting'
                     CHECK (status IN ('waiting', 'promoted', 'cancelled', 'expired')),
    position         INTEGER NOT NULL,
    created_at       TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    promoted_at      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_waitlist_per_user
    ON waitlists (user_id, turf_id, slot_template_id, booking_date)
    WHERE status = 'waiting';
CREATE INDEX IF NOT EXISTS idx_waitlists_position
    ON waitlists (turf_id, slot_template_id, booking_date, position)
    WHERE status = 'waiting';
CREATE INDEX IF NOT EXISTS idx_waitlists_user_id ON waitlists (user_id, booking_date);

CREATE TABLE IF NOT EXISTS maintenance_days (
    id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    turf_id    TEXT NOT NULL REFERENCES turfs (id),
    date       TEXT NOT NULL,
    reason     TEXT,
    created_by TEXT REFERENCES users (id),
    created_at TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    UNIQUE (turf_id, date)
);

CREATE INDEX IF NOT EXISTS idx_maintenance_date ON maintenance_days (date);

CREATE TABLE IF NOT EXISTS attendance (
    id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    booking_id TEXT NOT NULL UNIQUE REFERENCES bookings (id),
    status     TEXT NOT NULL CHECK (status IN ('present', 'absent', 'late')),
    marked_by  TEXT REFERENCES users (id),
    marked_at  TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    note       TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id    TEXT NOT NULL REFERENCES users (id),
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    type       TEXT,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT __SQLITE_NOW__
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_created
    ON notifications (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS activity_logs (
    id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    actor_user_id TEXT REFERENCES users (id),
    event_type    TEXT NOT NULL,
    message       TEXT NOT NULL,
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT __SQLITE_NOW__
);

CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_logs (created_at DESC);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    admin_id    TEXT NOT NULL REFERENCES users (id),
    action      TEXT NOT NULL,
    target_type TEXT,
    target_id   TEXT,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT __SQLITE_NOW__
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at DESC);

CREATE TABLE IF NOT EXISTS analytics_events (
    id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id       TEXT REFERENCES users (id),
    event_name    TEXT NOT NULL,
    event_payload TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT __SQLITE_NOW__
);

CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics_events (created_at);

CREATE TABLE IF NOT EXISTS token_revocations (
    jti        TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    revoked_at TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_token_revocations_user ON token_revocations (user_id);
CREATE INDEX IF NOT EXISTS idx_token_revocations_expires ON token_revocations (expires_at);

CREATE TABLE IF NOT EXISTS user_push_tokens (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id         TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expo_push_token TEXT NOT NULL,
    platform        TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    updated_at      TEXT NOT NULL DEFAULT __SQLITE_NOW__,
    UNIQUE (user_id, expo_push_token)
);

CREATE INDEX IF NOT EXISTS idx_user_push_tokens_user_active
    ON user_push_tokens (user_id)
    WHERE is_active = 1;
"""

SCHEMA_SQL = _SCHEMA_TEMPLATE.replace("__SQLITE_NOW__", _SQLITE_NOW)
