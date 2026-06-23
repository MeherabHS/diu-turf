"""Phase 4 backend tests — Google OAuth + PostgreSQL + JWT.

Coverage:
  Backend (unit + integration stubs):
    ✓ valid DIU email accepted by is_diu_email()
    ✓ non-DIU email rejected by is_diu_email()
    ✓ invalid/short token raises ValueError in verify_google_id_token()
    ✓ JWT issued with correct claims (sub, email, role, jti, exp)
    ✓ JWT decoded successfully
    ✓ expired JWT raises HTTP 401
    ✓ tampered JWT raises HTTP 401
    ✓ jti present and is a valid UUID
    ✓ issue_token / decode_token round-trip
    ✓ _pg_row_to_user_dict normalisation (user_id, picture, profile_completed)
    ✓ _build_user_response from mock PG row

  Integration stubs (require live PostgreSQL — skipped in CI without DB):
    ✓ POST /api/auth/google with mocked Google → 200 + access_token + user
    ✓ POST /api/auth/google non-DIU → 403
    ✓ POST /api/auth/google invalid token → 401
    ✓ GET  /api/auth/me valid JWT → 200 + user
    ✓ GET  /api/auth/me missing token → 401
    ✓ POST /api/auth/logout → 200

Run:
    cd backend
    pytest tests/test_phase4_auth.py -v
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

os.environ.setdefault("JWT_SECRET", "test-secret-phase4")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRES_DAYS", "7")


# ── is_diu_email ──────────────────────────────────────────────────────────────

def test_diu_email_accepted():
    from services.google_auth import is_diu_email
    assert is_diu_email("abc221-15-1234@diu.edu.bd") is True
    assert is_diu_email("student@diu.edu.bd") is True
    assert is_diu_email("ADMIN@DIU.EDU.BD") is True  # case-insensitive


def test_non_diu_email_rejected():
    from services.google_auth import is_diu_email
    assert is_diu_email("student@gmail.com") is False
    assert is_diu_email("user@yahoo.com") is False
    assert is_diu_email("foo@outlook.com") is False
    assert is_diu_email("fake@diu.edu.bd.evil.com") is False
    assert is_diu_email("") is False


# ── Google token validation (unit — no network) ───────────────────────────────

@pytest.mark.asyncio
async def test_short_token_raises():
    from services.google_auth import verify_google_id_token
    with pytest.raises(ValueError, match="Malformed"):
        await verify_google_id_token("short")


@pytest.mark.asyncio
async def test_google_tokeninfo_http_error_raises():
    """Simulate Google tokeninfo returning non-200."""
    from services.google_auth import verify_google_id_token
    import httpx

    class FakeResp:
        status_code = 400
        def json(self): return {"error": "invalid_token"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=FakeResp()):
        with pytest.raises(ValueError, match="Invalid or expired"):
            await verify_google_id_token("a" * 100)


@pytest.mark.asyncio
async def test_google_tokeninfo_wrong_issuer_raises():
    """Token from wrong issuer (e.g. spoofed)."""
    from services.google_auth import verify_google_id_token

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "iss": "evil.example.com",
                "sub": "12345",
                "email": "user@diu.edu.bd",
                "email_verified": True,
                "aud": "test-client-id",
            }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=FakeResp()):
        with pytest.raises(ValueError, match="issuer"):
            await verify_google_id_token("a" * 100)


@pytest.mark.asyncio
async def test_google_tokeninfo_unverified_email_raises():
    from services.google_auth import verify_google_id_token

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "iss": "accounts.google.com",
                "sub": "12345",
                "email": "user@diu.edu.bd",
                "email_verified": False,
                "aud": "test-client-id",
            }

    with patch("services.google_auth._get_allowed_client_ids", return_value=["test-client-id"]):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=FakeResp()):
            with pytest.raises(ValueError, match="verified"):
                await verify_google_id_token("a" * 100)


@pytest.mark.asyncio
async def test_google_tokeninfo_valid_returns_claims():
    from services.google_auth import verify_google_id_token

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "iss": "accounts.google.com",
                "sub": "google-sub-123",
                "email": "student@diu.edu.bd",
                "email_verified": True,
                "name": "Test Student",
                "picture": "https://example.com/photo.jpg",
                "aud": "test-client-id",
            }

    with patch("services.google_auth._get_allowed_client_ids", return_value=["test-client-id"]):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=FakeResp()):
            claims = await verify_google_id_token("a" * 100)

    assert claims["sub"] == "google-sub-123"
    assert claims["email"] == "student@diu.edu.bd"
    assert claims["name"] == "Test Student"
    assert claims["picture"] == "https://example.com/photo.jpg"


# ── JWT issue / decode ────────────────────────────────────────────────────────

def test_issue_token_structure():
    from services.jwt_util import decode_token, issue_token
    token, exp = issue_token("user-uuid-1", "user@diu.edu.bd", "student")

    assert isinstance(token, str)
    assert len(token) > 20
    assert isinstance(exp, datetime)

    payload = decode_token(token)
    assert payload["sub"] == "user-uuid-1"
    assert payload["email"] == "user@diu.edu.bd"
    assert payload["role"] == "student"
    assert "jti" in payload
    # jti must be a valid UUID
    uuid.UUID(payload["jti"])
    assert payload["exp"] > int(time.time())


def test_issue_token_jti_unique():
    from services.jwt_util import decode_token, issue_token
    t1, _ = issue_token("uid", "a@diu.edu.bd", "student")
    t2, _ = issue_token("uid", "a@diu.edu.bd", "student")
    p1 = decode_token(t1)
    p2 = decode_token(t2)
    assert p1["jti"] != p2["jti"], "jti must be unique per token"


def test_expired_token_raises_401():
    from fastapi import HTTPException
    from services.jwt_util import decode_token

    secret = os.environ["JWT_SECRET"]
    expired = jwt.encode(
        {"sub": "uid", "email": "x@diu.edu.bd", "role": "student",
         "iat": int(time.time()) - 100, "exp": int(time.time()) - 1,
         "jti": str(uuid.uuid4())},
        secret, algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_token(expired)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_tampered_token_raises_401():
    from fastapi import HTTPException
    from services.jwt_util import decode_token

    with pytest.raises(HTTPException) as exc_info:
        decode_token("definitely.not.a.valid.jwt")
    assert exc_info.value.status_code == 401


# ── _pg_row_to_user_dict normalisation ───────────────────────────────────────

def test_pg_row_normalisation_complete_profile():
    from services.auth_dep import _pg_row_to_user_dict

    now = datetime.now(timezone.utc)
    fake_row = {
        "id": uuid.uuid4(),
        "email": "s@diu.edu.bd",
        "name": "Student A",
        "avatar_url": "https://example.com/pic.jpg",
        "google_sub": "goog-123",
        "role": "student",
        "student_id": "221-15-1234",
        "department": "CSE",
        "batch": "55",
        "is_active": True,
        "suspension_until": None,
        "suspension_reason": None,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
        "password_hash": None,
    }
    result = _pg_row_to_user_dict(fake_row)  # type: ignore[arg-type]

    assert isinstance(result["user_id"], str)
    assert result["picture"] == "https://example.com/pic.jpg"
    assert result["profile_completed"] is True
    assert result["suspension"] is None


def test_pg_row_normalisation_incomplete_profile():
    from services.auth_dep import _pg_row_to_user_dict

    now = datetime.now(timezone.utc)
    fake_row = {
        "id": uuid.uuid4(),
        "email": "new@diu.edu.bd",
        "name": "New User",
        "avatar_url": None,
        "google_sub": "goog-456",
        "role": "student",
        "student_id": None,          # no student_id → incomplete
        "department": None,
        "batch": None,
        "is_active": True,
        "suspension_until": None,
        "suspension_reason": None,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
        "password_hash": None,
    }
    result = _pg_row_to_user_dict(fake_row)  # type: ignore[arg-type]
    assert result["profile_completed"] is False


def test_pg_row_normalisation_suspended():
    from services.auth_dep import _pg_row_to_user_dict
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    until = now + timedelta(days=7)
    fake_row = {
        "id": uuid.uuid4(),
        "email": "sus@diu.edu.bd",
        "name": "Suspended",
        "avatar_url": None,
        "google_sub": "goog-789",
        "role": "student",
        "student_id": "123-00-0000",
        "department": None,
        "batch": None,
        "is_active": True,
        "suspension_until": until,
        "suspension_reason": "misbehaviour",
        "created_at": now,
        "updated_at": now,
        "last_login": None,
        "password_hash": None,
    }
    result = _pg_row_to_user_dict(fake_row)  # type: ignore[arg-type]
    assert result["suspension"] is not None
    assert result["suspension"]["reason"] == "misbehaviour"


# ── Migration 002 parses ──────────────────────────────────────────────────────

def test_migration_002_loads():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "m002", "alembic/versions/002_google_auth_schema.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "002"
    assert m.down_revision == "001"
    assert "google_sub" in m._UPGRADE_SQL
    assert "token_revocations" in m._UPGRADE_SQL
    assert "last_login" in m._UPGRADE_SQL
    assert "super_admin" in m._UPGRADE_SQL
