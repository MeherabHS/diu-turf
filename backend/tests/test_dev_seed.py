"""Tests for permanent dev admin + test student seed accounts."""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

from database.seed_pg import (
    DEV_ADMIN_EMAIL,
    DEV_TEST_STUDENT_EMAIL,
    DEV_TEST_STUDENT_ID,
    DEV_TEST_STUDENT_NAME,
)

_RUN_ID = uuid.uuid4().hex[:8]
_TEST_DB = f"dev_seed_test_{_RUN_ID}.db"


@pytest.fixture(scope="module", autouse=True)
def sqlite_dev_env():
    os.environ["DATABASE_URL"] = f"sqlite:///./{_TEST_DB}"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEV_AUTH_ENABLED"] = "true"
    os.environ["JWT_SECRET"] = "test_" + "x" * 60
    yield
    Path(_TEST_DB).unlink(missing_ok=True)


async def _seed_pool():
    from database.connection import close_pool, create_pool
    from database.seed_pg import seed

    pool, _ = await create_pool()
    async with pool.acquire() as conn:
        await seed(conn)
    return pool


def test_seed_creates_dev_accounts():
    async def _run():
        pool = await _seed_pool()
        try:
            async with pool.acquire() as conn:
                admin = await conn.fetchrow(
                    "SELECT email, role, student_id, is_active FROM users WHERE email = $1",
                    DEV_ADMIN_EMAIL,
                )
                student = await conn.fetchrow(
                    "SELECT email, role, student_id, name, is_active FROM users WHERE email = $1",
                    DEV_TEST_STUDENT_EMAIL,
                )
            assert admin is not None
            assert admin["role"] == "admin"
            assert admin["is_active"] is True
            assert student is not None
            assert student["role"] == "student"
            assert student["student_id"] == DEV_TEST_STUDENT_ID
            assert student["name"] == DEV_TEST_STUDENT_NAME
            assert student["is_active"] is True
        finally:
            from database.connection import close_pool

            await close_pool(pool)

    asyncio.run(_run())


def test_seed_is_idempotent():
    async def _run():
        from database.seed_pg import seed

        pool = await _seed_pool()
        try:
            async with pool.acquire() as conn:
                await seed(conn)
                student = await conn.fetchrow(
                    "SELECT student_id, role, is_active FROM users WHERE email = $1",
                    DEV_TEST_STUDENT_EMAIL,
                )
            assert student["student_id"] == DEV_TEST_STUDENT_ID
            assert student["role"] == "student"
            assert student["is_active"] is True
        finally:
            from database.connection import close_pool

            await close_pool(pool)

    asyncio.run(_run())


def test_dev_login_test_student():
    async def _run():
        from routes.auth import dev_login
        from services.models import DevLoginRequest

        pool = await _seed_pool()
        try:
            async with pool.acquire() as conn:
                auth = await dev_login(DevLoginRequest(email=DEV_TEST_STUDENT_EMAIL), conn)
            assert auth.access_token
            assert auth.user.email == DEV_TEST_STUDENT_EMAIL
            assert auth.user.role == "student"
            assert auth.user.profile_completed is True
            assert auth.user.student_id == DEV_TEST_STUDENT_ID
        finally:
            from database.connection import close_pool

            await close_pool(pool)

    asyncio.run(_run())


def test_dev_login_admin():
    async def _run():
        from routes.auth import dev_login
        from services.models import DevLoginRequest

        pool = await _seed_pool()
        try:
            async with pool.acquire() as conn:
                auth = await dev_login(DevLoginRequest(email=DEV_ADMIN_EMAIL), conn)
            assert auth.access_token
            assert auth.user.role == "admin"
        finally:
            from database.connection import close_pool

            await close_pool(pool)

    asyncio.run(_run())
