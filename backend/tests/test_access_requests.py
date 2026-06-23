"""Booking access request tests."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-access-requests")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("AUTH_RATE_LIMIT_MAX", "1000")

_TEST_DB = Path(__file__).parent / f"test_access_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"


@pytest.fixture
def mock_request():
    return MagicMock()


@pytest.fixture(scope="module")
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def conn():
    from database.connection import create_pool, close_pool
    from database.seed_pg import seed

    pool, _ = await create_pool()
    async with pool.acquire() as c:
        await seed(c)
    yield pool
    await close_pool(pool)
    if _TEST_DB.exists():
        _TEST_DB.unlink(missing_ok=True)


@pytest_asyncio.fixture
async def viewer_user(conn, mock_request):
    from routes.auth import register
    from services.models import RegisterRequest

    sid = f"1{uuid.uuid4().int % 10**2:02d}-35-{uuid.uuid4().int % 1000:03d}"
    email = f"{sid}@diu.edu.bd"
    async with conn.acquire() as c:
        resp = await register(
            RegisterRequest(
                email=email,
                password="ViewerPass1",
                full_name="Viewer Test",
                student_id=sid,
                department="SWE",
                batch="47",
            ),
            mock_request,
            c,
        )
    return resp.user


@pytest.mark.asyncio
async def test_viewer_cannot_create_booking(viewer_user):
    from services.permissions import can_book, require_booking_access

    user = {
        "user_id": viewer_user.user_id,
        "role": viewer_user.role,
        "profile_completed": True,
    }
    assert viewer_user.role == "viewer"
    assert can_book(user) is False

    with pytest.raises(HTTPException) as exc:
        await require_booking_access(user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_access_request_flow(conn, viewer_user, mock_request):
    from routes.access_requests import (
        AccessRequestCreate,
        approve_access_request,
        create_access_request,
        my_access_request,
    )

    user_dict = {
        "user_id": viewer_user.user_id,
        "name": viewer_user.name,
        "email": viewer_user.email,
        "student_id": viewer_user.student_id,
        "role": viewer_user.role,
    }
    assert viewer_user.role == "viewer"

    async with conn.acquire() as c:
        created = await create_access_request(AccessRequestCreate(reason="Need turf"), user_dict, c)
        assert created["status"] == "pending"
        assert created["email"] == viewer_user.email

        with pytest.raises(HTTPException) as dup:
            await create_access_request(AccessRequestCreate(reason="Again"), user_dict, c)
        assert dup.value.status_code == 409

        mine = await my_access_request(user_dict, c)
        assert mine["status"] == "pending"

        admin_row = await c.fetchrow(
            "SELECT id FROM users WHERE role IN ('admin', 'super_admin') LIMIT 1",
        )
        admin = {"user_id": str(admin_row["id"]), "role": "admin"}
        approved = await approve_access_request(created["id"], admin, c)
        assert approved["status"] == "approved"

        row = await c.fetchrow("SELECT role FROM users WHERE id = $1", uuid.UUID(viewer_user.user_id))
        assert row["role"] == "booker"
