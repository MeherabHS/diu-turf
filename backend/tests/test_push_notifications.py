"""Push notification tests — token registration and waitlist promotion."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

os.environ.setdefault("JWT_SECRET", "test-secret-push")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEV_AUTH_ENABLED", "false")
os.environ.setdefault("AUTH_RATE_LIMIT_MAX", "1000")

_TEST_DB = Path(__file__).parent / f"test_push_{uuid.uuid4().hex[:8]}.db"
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


@pytest.fixture
def mock_request():
    from unittest.mock import MagicMock

    request = MagicMock()
    request.client.host = f"push-test-{uuid.uuid4().hex[:6]}"
    request.headers.get.return_value = None
    return request


def test_valid_expo_push_token_prefix():
    from services.push import is_valid_expo_push_token

    assert is_valid_expo_push_token("ExponentPushToken[abc123]")
    assert is_valid_expo_push_token("ExpoPushToken[xyz]")
    assert not is_valid_expo_push_token("invalid-token")


@pytest.mark.asyncio
async def test_register_push_token_upsert(conn, mock_request):
    from routes.auth import register
    from routes.notifications import PushTokenRequest, register_push_token
    from services.models import RegisterRequest

    sid = f"252-35-{uuid.uuid4().int % 1000:03d}"
    email = f"{sid}@diu.edu.bd"

    resp = await register(
        RegisterRequest(
            email=email,
            password="SecurePass1",
            full_name="Push Test",
            student_id=sid,
            department="SWE",
            batch="47",
        ),
        mock_request,
        conn,
    )
    user_id = resp.user.user_id

    token = "ExponentPushToken[test-token-12345]"
    result = await register_push_token(
        PushTokenRequest(expo_push_token=token, platform="android"),
        {"user_id": user_id, "role": "student"},
        conn,
    )
    assert result["ok"] is True

    row = await conn.fetchrow(
        "SELECT expo_push_token, platform, is_active FROM user_push_tokens WHERE user_id = $1",
        user_id,
    )
    assert row is not None
    assert row["expo_push_token"] == token
    assert row["platform"] == "android"
    assert row["is_active"] in (True, 1)


@pytest.mark.asyncio
async def test_register_push_token_rejects_invalid(conn):
    from fastapi import HTTPException
    from routes.notifications import PushTokenRequest, register_push_token

    with pytest.raises(HTTPException) as exc:
        await register_push_token(
            PushTokenRequest(expo_push_token="this-is-not-an-expo-push-token", platform="android"),
            {"user_id": str(uuid.uuid4()), "role": "student"},
            conn,
        )
    assert exc.value.status_code == 400


async def _create_test_user(conn, mock_request):
    from routes.auth import register
    from services.models import RegisterRequest

    sid = f"252-35-{uuid.uuid4().int % 1000:03d}"
    email = f"{sid}@diu.edu.bd"
    resp = await register(
        RegisterRequest(
            email=email,
            password="SecurePass1",
            full_name="Push Test",
            student_id=sid,
            department="SWE",
            batch="47",
        ),
        mock_request,
        conn,
    )
    return uuid.UUID(resp.user.user_id)


@pytest.mark.asyncio
async def test_notify_waitlist_promoted_calls_expo(conn, mock_request):
    from services.push import notify_waitlist_promoted, upsert_push_token

    user_id = await _create_test_user(conn, mock_request)
    token = "ExponentPushToken[promote-test]"
    await upsert_push_token(conn, user_id=user_id, expo_push_token=token, platform="android")

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"data": [{"status": "ok", "id": "ticket-1"}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as post:
        await notify_waitlist_promoted(
            conn,
            user_id=user_id,
            booking_id=uuid.uuid4(),
            booking_date=datetime.now(timezone.utc).date(),
            slot_template_id=uuid.uuid4(),
        )

    assert post.called
    payload = post.call_args.kwargs.get("json") or post.call_args[0][1]
    assert payload[0]["title"] == "Slot confirmed"
    assert payload[0]["body"] == "Your waitlisted turf slot is now confirmed."
    assert payload[0]["data"]["type"] == "waitlist.promoted"


@pytest.mark.asyncio
async def test_push_send_failure_does_not_raise(conn, mock_request):
    from services.push import send_push_to_user, upsert_push_token

    user_id = await _create_test_user(conn, mock_request)
    await upsert_push_token(
        conn,
        user_id=user_id,
        expo_push_token="ExponentPushToken[fail-test]",
        platform="android",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=RuntimeError("network down")):
        await send_push_to_user(
            conn,
            user_id=user_id,
            title="Test",
            body="Body",
        )
