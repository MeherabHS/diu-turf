"""Password auth acceptance tests — register + login with DIU email/student ID rules.

Run:
    cd backend
    pytest tests/test_password_auth.py -v
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

os.environ.setdefault("JWT_SECRET", "test-secret-password-auth")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRES_DAYS", "7")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEV_AUTH_ENABLED", "false")
os.environ.setdefault("AUTH_RATE_LIMIT_MAX", "1000")
os.environ.setdefault("AUTH_RATE_LIMIT_WINDOW", "60")

_TEST_DB = Path(__file__).parent / f"test_password_auth_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"

SEED_EMAIL = "252-35-166@diu.edu.bd"
SEED_STUDENT_ID = "252-35-166"
MISMATCH_MSG = "Student ID must match the part before @ in your DIU email."


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


@pytest.fixture
def mock_request():
    from unittest.mock import MagicMock

    request = MagicMock()
    request.client.host = f"test-{uuid.uuid4().hex[:8]}"
    request.headers.get.return_value = None
    return request


def _unique_student_id() -> str:
    n = uuid.uuid4().int % 1000
    return f"252-35-{n:03d}"


def _register_payload(**overrides):
    sid = _unique_student_id()
    base = {
        "email": f"{sid}@diu.edu.bd",
        "password": "SecurePass1",
        "full_name": "Test Student",
        "student_id": sid,
        "department": "SWE",
        "batch": "47",
        "room_number": "402",
        "hostel_name": "DIU Boys Hostel",
        "phone": "01700000000",
    }
    base.update(overrides)
    return base


async def _clear_seed_student(conn) -> None:
    """Remove seeded dev test student so 252-35-166 can be registered in tests."""
    await conn.execute(
        "DELETE FROM users WHERE email = $1 OR student_id = $2",
        SEED_EMAIL,
        SEED_STUDENT_ID,
    )


@pytest.mark.asyncio
async def test_register_252_35_166_succeeds(conn, mock_request):
    from routes.auth import register
    from services.models import RegisterRequest

    await _clear_seed_student(conn)
    resp = await register(
        RegisterRequest(**_register_payload(
            email=SEED_EMAIL,
            student_id=SEED_STUDENT_ID,
        )),
        mock_request,
        conn,
    )
    assert resp.access_token
    assert resp.user.email == SEED_EMAIL
    assert resp.user.student_id == SEED_STUDENT_ID


@pytest.mark.asyncio
async def test_register_valid_email_student_id_match(conn, mock_request):
    from routes.auth import register
    from services.models import RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    resp = await register(RegisterRequest(**_register_payload(
        email=email,
        student_id=sid,
    )), mock_request, conn)
    assert resp.access_token
    assert resp.user.email == email
    assert resp.user.student_id == sid
    assert resp.user.profile_completed is True


@pytest.mark.asyncio
async def test_register_email_student_id_mismatch(conn, mock_request):
    from fastapi import HTTPException
    from routes.auth import register
    from services.models import RegisterRequest

    with pytest.raises(HTTPException) as exc:
        await register(
            RegisterRequest(**_register_payload(
                email="252-35-999@diu.edu.bd",
                student_id="252-35-166",
            )),
            mock_request,
            conn,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == MISMATCH_MSG


@pytest.mark.asyncio
async def test_register_shafin_email_mismatch(conn, mock_request):
    from fastapi import HTTPException
    from routes.auth import register
    from services.models import RegisterRequest

    with pytest.raises(HTTPException) as exc:
        await register(
            RegisterRequest(**_register_payload(
                email="shafin@diu.edu.bd",
                student_id="252-35-166",
            )),
            mock_request,
            conn,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == MISMATCH_MSG


@pytest.mark.asyncio
async def test_register_duplicate_email(conn, mock_request):
    from fastapi import HTTPException
    from routes.auth import register
    from services.models import RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    await register(RegisterRequest(**_register_payload(email=email, student_id=sid)), mock_request, conn)

    with pytest.raises(HTTPException) as exc:
        await register(RegisterRequest(**_register_payload(email=email, student_id=sid)), mock_request, conn)
    assert exc.value.status_code == 409
    assert "email" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_register_duplicate_student_id(conn, mock_request):
    from fastapi import HTTPException
    from routes.auth import register
    from services.models import RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    await register(RegisterRequest(**_register_payload(email=email, student_id=sid)), mock_request, conn)

    # Email changed in DB but student_id kept — registration hits student_id duplicate.
    await conn.execute(
        "UPDATE users SET email = $1 WHERE student_id = $2",
        f"orphan-{sid}@diu.edu.bd",
        sid,
    )

    with pytest.raises(HTTPException) as exc:
        await register(RegisterRequest(**_register_payload(email=email, student_id=sid)), mock_request, conn)
    assert exc.value.status_code == 409
    assert "student ID" in exc.value.detail


@pytest.mark.asyncio
async def test_login_correct_password(conn, mock_request):
    from routes.auth import login, register
    from services.models import LoginRequest, RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    password = "CorrectPass99"
    await register(RegisterRequest(**_register_payload(
        email=email,
        student_id=sid,
        password=password,
    )), mock_request, conn)

    resp = await login(LoginRequest(email=email, password=password), mock_request, conn)
    assert resp.access_token
    assert resp.user.email == email


@pytest.mark.asyncio
async def test_login_wrong_password(conn, mock_request):
    from fastapi import HTTPException
    from routes.auth import login, register
    from services.models import LoginRequest, RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    await register(RegisterRequest(**_register_payload(
        email=email,
        student_id=sid,
        password="GoodPassword1",
    )), mock_request, conn)

    with pytest.raises(HTTPException) as exc:
        await login(LoginRequest(email=email, password="WrongPassword1"), mock_request, conn)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid email or password."


@pytest.mark.asyncio
async def test_suspended_user_cannot_login(conn, mock_request):
    from fastapi import HTTPException
    from routes.auth import login, register
    from services.models import LoginRequest, RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    password = "SecurePass1"
    await register(RegisterRequest(**_register_payload(
        email=email,
        student_id=sid,
        password=password,
    )), mock_request, conn)

    until = datetime.now(timezone.utc) + timedelta(days=7)
    await conn.execute(
        """UPDATE users SET suspension_until = $1, suspension_reason = $2
           WHERE email = $3""",
        until,
        "Test suspension",
        email,
    )

    with pytest.raises(HTTPException) as exc:
        await login(LoginRequest(email=email, password=password), mock_request, conn)
    assert exc.value.status_code == 403
    assert "suspended" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_deactivated_user_cannot_login(conn, mock_request):
    from fastapi import HTTPException
    from routes.auth import login, register
    from services.models import LoginRequest, RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    password = "SecurePass1"
    await register(RegisterRequest(**_register_payload(
        email=email,
        student_id=sid,
        password=password,
    )), mock_request, conn)

    await conn.execute(
        "UPDATE users SET is_active = FALSE WHERE email = $1",
        email,
    )

    with pytest.raises(HTTPException) as exc:
        await login(LoginRequest(email=email, password=password), mock_request, conn)
    assert exc.value.status_code == 403
    assert "deactivated" in exc.value.detail.lower()


def test_registration_util_validation():
    from services.registration_util import validate_registration_identity

    assert validate_registration_identity("252-35-166@diu.edu.bd", "252-35-166") is None
    assert validate_registration_identity("252-35-999@diu.edu.bd", "252-35-166") == MISMATCH_MSG
    assert validate_registration_identity("shafin@diu.edu.bd", "252-35-166") == MISMATCH_MSG
    assert validate_registration_identity("tahrim35-1137@ds.diu.edu.bd", "123-35-1137") is None
    assert validate_registration_identity("261-35-113@diu.edu.bd", "261-35-113") is None
    assert validate_registration_identity("tahrim35-1137@ds.diu.edu.bd", "261-35-113") is None


def test_student_id_formats():
    from services.registration_util import validate_student_id_format

    assert validate_student_id_format("261-35-113") is None
    assert validate_student_id_format("123-35-1137") is None
    assert validate_student_id_format("12-35-113") is not None


def test_is_diu_email_subdomains():
    from services.google_auth import is_diu_email

    assert is_diu_email("tahrim35-1137@ds.diu.edu.bd") is True
    assert is_diu_email("261-35-113@diu.edu.bd") is True
    assert is_diu_email("notdiu@gmail.com") is False


def test_password_hash_never_stores_plain():
    from services.password_util import hash_password, verify_password

    plain = "MySecretPass123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrong", hashed)


@pytest.mark.asyncio
async def test_password_not_stored_plain_in_db(conn, mock_request):
    from routes.auth import register
    from services.models import RegisterRequest

    sid = _unique_student_id()
    email = f"{sid}@diu.edu.bd"
    password = "PlainTextCheck1"
    await register(RegisterRequest(**_register_payload(
        email=email,
        student_id=sid,
        password=password,
    )), mock_request, conn)

    stored = await conn.fetchval("SELECT password_hash FROM users WHERE email = $1", email)
    assert stored is not None
    assert stored != password
    assert stored.startswith("$2")


def test_auth_rate_limit(monkeypatch):
    from unittest.mock import MagicMock

    from fastapi import HTTPException
    from services.rate_limit import enforce_auth_rate_limit

    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX", "2")
    monkeypatch.setenv("AUTH_RATE_LIMIT_WINDOW", "60")

    request = MagicMock()
    request.client.host = "test-client"
    request.headers.get.return_value = None

    enforce_auth_rate_limit(request, "auth:login")
    enforce_auth_rate_limit(request, "auth:login")
    with pytest.raises(HTTPException) as exc:
        enforce_auth_rate_limit(request, "auth:login")
    assert exc.value.status_code == 429
