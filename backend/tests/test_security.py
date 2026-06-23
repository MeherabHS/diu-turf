"""Security hardening tests — revocation, suspension, CORS config."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

os.environ.setdefault("JWT_SECRET", "test-secret-security-hardening-32chars!")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRES_DAYS", "7")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEV_AUTH_ENABLED", "false")
os.environ.setdefault("AUTH_RATE_LIMIT_MAX", "1000")
os.environ.setdefault("AUTH_RATE_LIMIT_WINDOW", "60")
os.environ.setdefault("ALLOWED_ORIGINS", "*")

_TEST_DB = Path(__file__).parent / f"test_security_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"


@pytest.fixture(scope="module")
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def pool():
    from database.connection import close_pool, create_pool
    from database.seed_pg import seed

    pool, _cfg = await create_pool()
    async with pool.acquire() as conn:
        await seed(conn)
    yield pool
    await close_pool(pool)
    if _TEST_DB.exists():
        _TEST_DB.unlink()


@pytest_asyncio.fixture
async def conn(pool):
    async with pool.acquire() as c:
        yield c


@pytest.mark.asyncio
async def test_logout_revokes_token(conn):
    from fastapi import HTTPException
    from routes.auth import logout, register
    from services.auth_dep import get_current_user
    from services.models import RegisterRequest

    sid = f"252-35-{uuid.uuid4().int % 900 + 100:03d}"
    email = f"{sid}@diu.edu.bd"
    password = "SecurePass1"

    mock_request = MagicMock()
    mock_request.client.host = "test-logout"
    mock_request.headers.get.return_value = None

    await conn.execute(
        "DELETE FROM users WHERE email = $1 OR student_id = $2",
        email,
        sid,
    )

    resp = await register(
        RegisterRequest(
            email=email,
            password=password,
            full_name="Logout Test",
            student_id=sid,
            department="SWE",
            batch="47",
            room_number="101",
            hostel_name="DIU Boys Hostel",
            phone="01700000000",
        ),
        mock_request,
        conn,
    )
    token = resp.access_token

    await logout(
        user={"user_id": resp.user.user_id, "email": email},
        authorization=f"Bearer {token}",
        conn=conn,
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            authorization=f"Bearer {token}",
            conn=conn,
        )
    assert exc.value.status_code == 401
    assert "revoked" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_suspended_user_rejected_by_get_current_user(conn):
    from fastapi import HTTPException
    from services.auth_dep import get_current_user
    from services.jwt_util import issue_token

    row = await conn.fetchrow(
        "SELECT id, email, role FROM users WHERE email = $1",
        "252-35-166@diu.edu.bd",
    )
    assert row is not None
    token, _ = issue_token(str(row["id"]), row["email"], row["role"])

    until = datetime.now(timezone.utc) + timedelta(days=3)
    await conn.execute(
        """UPDATE users SET suspension_until = $1, suspension_reason = $2
           WHERE id = $3""",
        until,
        "Security test suspension",
        row["id"],
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=f"Bearer {token}", conn=conn)
    assert exc.value.status_code == 403
    assert "suspended" in exc.value.detail.lower()

    await conn.execute(
        "UPDATE users SET suspension_until = NULL, suspension_reason = NULL WHERE id = $1",
        row["id"],
    )


def test_cors_dev_allows_wildcard_without_credentials(monkeypatch):
    from services.cors_config import parse_allowed_origins

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    origins, credentials = parse_allowed_origins()
    assert origins == ["*"]
    assert credentials is False


def test_cors_production_rejects_wildcard(monkeypatch):
    from services.cors_config import parse_allowed_origins

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="not allowed"):
        parse_allowed_origins()


def test_cors_production_requires_explicit_origins(monkeypatch):
    from services.cors_config import parse_allowed_origins

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://diu-turf.onrender.com")
    origins, credentials = parse_allowed_origins()
    assert origins == ["https://diu-turf.onrender.com"]
    assert credentials is True


def test_production_startup_validation_rejects_weak_config(monkeypatch):
    from database.db_config import DatabaseConfig, DbBackend
    from services.startup_validation import validate_production_config

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "short")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")

    cfg = DatabaseConfig(
        backend=DbBackend.SQLITE,
        dsn="sqlite:///./dev_turf.db",
    )
    with pytest.raises(RuntimeError, match="Production configuration invalid"):
        validate_production_config(cfg)
