"""Shared test fixtures — PostgreSQL-only (MongoDB removed)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt
import pytest
from dotenv import load_dotenv

# Load .env if present (CI may inject vars directly)
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001").rstrip("/")
JWT_SECRET    = os.environ.get("JWT_SECRET", "test-secret")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_DAYS = int(os.environ.get("JWT_EXPIRES_DAYS", "7"))


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


def _mint(
    user_id: str,
    email: str,
    role: str,
    *,
    secret: str = JWT_SECRET,
    exp_delta: timedelta = timedelta(days=7),
) -> str:
    import uuid
    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {
            "sub":   user_id,
            "email": email,
            "role":  role,
            "iat":   int(now.timestamp()),
            "exp":   int((now + exp_delta).timestamp()),
            "jti":   str(uuid.uuid4()),
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )


@pytest.fixture(scope="session")
def mint_jwt():
    return _mint


@pytest.fixture
def student_jwt() -> str:
    return _mint("00000000-0000-0000-0000-000000000001", "student@diu.edu.bd", "student")


@pytest.fixture
def admin_jwt() -> str:
    return _mint("00000000-0000-0000-0000-000000000002", "admin@diu.edu.bd", "admin")


@pytest.fixture
def student_headers(student_jwt) -> dict:
    return {"Authorization": f"Bearer {student_jwt}", "Content-Type": "application/json"}


@pytest.fixture
def admin_headers(admin_jwt) -> dict:
    return {"Authorization": f"Bearer {admin_jwt}", "Content-Type": "application/json"}
