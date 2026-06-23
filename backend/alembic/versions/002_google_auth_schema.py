"""Google OAuth auth schema — Phase 4 additions.

Revision ID: 002
Revises: 001
Create Date: 2026-06-22 UTC

Changes
───────
1. users.google_sub      TEXT UNIQUE — Google account identifier (sub claim).
2. users.last_login      TIMESTAMPTZ — updated on every successful login.
3. users.password_hash   → made nullable (Google is the identity provider;
                           the admin seed row keeps its existing hash).
4. users.role CHECK      → extended to include 'super_admin'.
5. token_revocations     — new table for JWT jti-based logout/revocation.

Downgrade
─────────
Reverses all changes. Data in token_revocations is lost.
"""
from __future__ import annotations

from database.migration_sql import execute_sql_script

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

_UPGRADE_SQL = """
-- ── 1. google_sub ────────────────────────────────────────────────────────────
-- The Google account "sub" claim — globally unique per Google account.
-- Nullable so the admin seed row (created with password only) is unaffected.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS google_sub TEXT;

-- Partial unique index: allows NULL (multiple rows), but unique when set.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub
    ON users (google_sub)
    WHERE google_sub IS NOT NULL;


-- ── 2. last_login ─────────────────────────────────────────────────────────────
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;


-- ── 3. Make password_hash nullable ────────────────────────────────────────────
-- Google is the identity provider from Phase 4 onwards.
-- Existing rows (admin seed) keep their hash; new Google-auth rows have NULL.
ALTER TABLE users
    ALTER COLUMN password_hash DROP NOT NULL;


-- ── 4. Extend role CHECK ──────────────────────────────────────────────────────
-- Add 'super_admin' for future multi-tenant / multi-campus expansion.
-- PostgreSQL requires dropping then re-adding inline CHECK constraints.
ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE users
    ADD CONSTRAINT users_role_check
    CHECK (role IN ('student', 'admin', 'super_admin'));


-- ── 5. token_revocations ─────────────────────────────────────────────────────
-- Stores revoked JWT jti values.
-- Used for logout (Phase 4) and forced session invalidation (Phase 6+).
-- Rows whose expires_at is in the past can be deleted by a maintenance job.
CREATE TABLE IF NOT EXISTS token_revocations (
    jti        UUID        PRIMARY KEY,
    user_id    UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL   -- mirrors the JWT exp claim
);

-- Fast lookup during request authentication.
CREATE INDEX IF NOT EXISTS idx_token_revocations_user
    ON token_revocations (user_id);

-- For a periodic cleanup job: DELETE FROM token_revocations WHERE expires_at < NOW().
CREATE INDEX IF NOT EXISTS idx_token_revocations_expires
    ON token_revocations (expires_at);
"""

_DOWNGRADE_SQL = """
DROP TABLE  IF EXISTS token_revocations;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD  CONSTRAINT users_role_check
    CHECK (role IN ('student', 'admin'));

ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;

DROP INDEX  IF EXISTS idx_users_google_sub;
ALTER TABLE users DROP COLUMN IF EXISTS google_sub;
ALTER TABLE users DROP COLUMN IF EXISTS last_login;
"""


def upgrade() -> None:
    execute_sql_script(_UPGRADE_SQL)


def downgrade() -> None:
    execute_sql_script(_DOWNGRADE_SQL)
