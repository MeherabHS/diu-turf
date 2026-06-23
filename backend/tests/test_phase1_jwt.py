"""DIU Hostel Turf Booking — Phase 1 (JWT) backend regression suite.

Replaces the obsolete `test_phase1.py` which targeted /api/auth/session.
The live endpoint is POST /api/auth/google → {token, user}; auth is now a
stateless JWT (HS256) signed with backend/.env::JWT_SECRET.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from services.domain import ALLOWED_DOMAIN, is_diu_email
from services.jwt_util import (
    JWT_ALGORITHM,
    JWT_EXPIRES_DAYS,
    JWT_SECRET,
    decode_token,
    issue_token,
)


# ---------- Health & banner ----------
class TestHealthAndBanner:
    def test_health_ok(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_root_banner(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/")
        assert r.status_code == 200
        body = r.json()
        assert body.get("service") == "DIU Hostel Turf Booking"
        assert body.get("status") == "ok"


# ---------- Domain enforcement (unit + source inspection) ----------
class TestDomainEnforcement:
    def test_allowed_domain_constant(self):
        assert ALLOWED_DOMAIN == "@diu.edu.bd"

    def test_diu_email_accepted(self):
        assert is_diu_email("x@diu.edu.bd") is True
        assert is_diu_email("Mixed.Case@DIU.edu.bd") is True

    def test_non_diu_email_rejected(self):
        assert is_diu_email("u@gmail.com") is False
        assert is_diu_email("u@diu.edu.bd.evil.com") is False
        assert is_diu_email(None) is False
        assert is_diu_email("") is False

    def test_auth_route_403_message_is_exact(self):
        """Verify the EXACT 403 message used when email isn't @diu.edu.bd."""
        src = open("/app/backend/routes/auth.py", encoding="utf-8").read()
        assert "if not is_diu_email(email):" in src
        assert "HTTP_403_FORBIDDEN" in src
        assert (
            "Access restricted to Daffodil International University students."
            in src
        ), "403 message text drifted from spec"


# ---------- POST /api/auth/google ----------
class TestGoogleLoginEndpoint:
    def test_empty_session_token_returns_400(self, api_client, base_url):
        r = api_client.post(
            f"{base_url}/api/auth/google", json={"session_token": ""}
        )
        # Empty string passes Pydantic (str type, no min_length) → handler returns 400
        assert r.status_code == 400, r.text

    def test_missing_field_returns_422(self, api_client, base_url):
        r = api_client.post(f"{base_url}/api/auth/google", json={})
        assert r.status_code == 422

    def test_invalid_session_token_returns_401(self, api_client, base_url):
        r = api_client.post(
            f"{base_url}/api/auth/google",
            json={"session_token": "definitely-not-a-real-session-id"},
        )
        assert r.status_code == 401, r.text
        assert r.json().get("detail") == "Invalid or expired OAuth session"


# ---------- JWT utility (issue + decode) ----------
class TestJwtUtility:
    def test_issue_token_claims(self):
        token, exp = issue_token(user_id="user_abc", email="x@diu.edu.bd", role="student")
        decoded = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert decoded["sub"] == "user_abc"
        assert decoded["email"] == "x@diu.edu.bd"
        assert decoded["role"] == "student"
        assert "iat" in decoded and "exp" in decoded
        # exp ~ JWT_EXPIRES_DAYS away
        now = datetime.now(timezone.utc)
        delta_days = (exp - now).days
        assert JWT_EXPIRES_DAYS - 1 <= delta_days <= JWT_EXPIRES_DAYS
        assert decoded["exp"] - decoded["iat"] == JWT_EXPIRES_DAYS * 86400

    def test_issue_token_uses_hs256(self):
        token, _ = issue_token("u", "x@diu.edu.bd", "student")
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_decode_rejects_wrong_secret(self):
        bad = pyjwt.encode(
            {"sub": "u", "email": "x@diu.edu.bd", "role": "student",
             "iat": int(datetime.now(timezone.utc).timestamp()),
             "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
            "wrong-secret", algorithm="HS256",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            decode_token(bad)
        assert exc.value.status_code == 401


# ---------- GET /api/auth/me ----------
class TestAuthMe:
    def test_missing_authorization_returns_401(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/auth/me")
        assert r.status_code == 401
        assert r.json().get("detail") == "Missing bearer token"

    def test_malformed_bearer_returns_401(self, api_client, base_url):
        r = api_client.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert r.status_code == 401
        assert r.json().get("detail") == "Invalid session"

    def test_non_bearer_scheme_returns_401(self, api_client, base_url):
        r = api_client.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": "Basic abc"},
        )
        assert r.status_code == 401
        assert r.json().get("detail") == "Missing bearer token"

    def test_valid_admin_jwt_returns_200_with_admin_payload(
        self, api_client, base_url, admin_headers
    ):
        r = api_client.get(f"{base_url}/api/auth/me", headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        u = body["user"]
        assert u["email"] == "admin@diu.edu.bd"
        assert u["role"] == "admin"
        assert u["profile_completed"] is True
        # phase 1 spec: department/batch are part of the user payload
        assert "department" in u
        assert "batch" in u

    def test_expired_jwt_returns_401_session_expired(
        self, api_client, base_url, mint_jwt, admin_user
    ):
        token = mint_jwt(
            admin_user["user_id"], admin_user["email"], admin_user["role"],
            exp_delta=timedelta(seconds=-10),
        )
        r = api_client.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
        assert r.json().get("detail") == "Session expired"

    def test_jwt_signed_with_wrong_secret_returns_401(
        self, api_client, base_url, mint_jwt, admin_user
    ):
        token = mint_jwt(
            admin_user["user_id"], admin_user["email"], admin_user["role"],
            secret="totally-wrong-secret",
        )
        r = api_client.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
        assert r.json().get("detail") == "Invalid session"

    def test_jwt_for_unknown_user_returns_401(
        self, api_client, base_url, mint_jwt
    ):
        token = mint_jwt("user_doesnotexist", "ghost@diu.edu.bd", "student")
        r = api_client.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
        assert r.json().get("detail") == "User not found"


# ---------- Seed data assertion ----------
class TestSeededAdmin:
    def test_admin_seeded_with_expected_fields(self, admin_user):
        assert admin_user is not None
        assert admin_user["email"] == "admin@diu.edu.bd"
        assert admin_user["role"] == "admin"
        assert admin_user["student_id"] == "ADMIN-0001"
        assert admin_user["department"] == "Administration"
        assert admin_user["profile_completed"] is True


# ---------- PUT /api/users/profile (and /api/users/me alias) ----------
class TestProfileUpdate:
    def test_profile_update_without_auth_returns_401(self, api_client, base_url):
        r = api_client.put(
            f"{base_url}/api/users/profile",
            json={"student_id": "ABC-123"},
        )
        assert r.status_code == 401

    def test_profile_update_alias_me_without_auth_returns_401(self, api_client, base_url):
        r = api_client.put(
            f"{base_url}/api/users/me",
            json={"student_id": "ABC-123"},
        )
        assert r.status_code == 401

    @pytest.mark.parametrize("bad_sid,expected", [
        ("ab", (400, 422)),       # too short — pydantic min_length=3
        ("@@@@", (400, 422)),     # invalid chars — route regex 400
        ("a" * 33, (400, 422)),  # too long — pydantic max_length=32
    ])
    def test_profile_update_rejects_invalid_student_id(
        self, api_client, base_url, admin_headers, bad_sid, expected
    ):
        r = api_client.put(
            f"{base_url}/api/users/profile",
            headers=admin_headers,
            json={"student_id": bad_sid},
        )
        assert r.status_code in expected, f"{bad_sid!r} → {r.status_code}: {r.text}"

    def test_profile_update_accepts_valid_payload_and_persists(
        self, api_client, base_url, admin_headers, mongo_db, admin_user
    ):
        original = {
            "name": admin_user.get("name"),
            "student_id": admin_user.get("student_id"),
            "department": admin_user.get("department"),
            "batch": admin_user.get("batch"),
        }
        try:
            payload = {
                "name": "TEST DIU Admin",
                "student_id": "TEST-PROFILE-001",
                "department": "TEST-CSE",
                "batch": "TEST-61",
            }
            r = api_client.put(
                f"{base_url}/api/users/profile",
                headers=admin_headers,
                json=payload,
            )
            assert r.status_code == 200, r.text
            u = r.json()["user"]
            assert u["name"] == "TEST DIU Admin"
            assert u["student_id"] == "TEST-PROFILE-001"
            assert u["department"] == "TEST-CSE"
            assert u["batch"] == "TEST-61"
            assert u["profile_completed"] is True

            # GET to confirm persistence via /api/auth/me
            r2 = api_client.get(f"{base_url}/api/auth/me", headers=admin_headers)
            assert r2.status_code == 200
            u2 = r2.json()["user"]
            assert u2["student_id"] == "TEST-PROFILE-001"
            assert u2["department"] == "TEST-CSE"
            assert u2["batch"] == "TEST-61"
        finally:
            mongo_db.users.update_one(
                {"user_id": admin_user["user_id"]},
                {"$set": {**original, "profile_completed": True}},
            )

    def test_profile_update_alias_me_persists_identically(
        self, api_client, base_url, admin_headers, mongo_db, admin_user
    ):
        original_sid = admin_user["student_id"]
        try:
            r = api_client.put(
                f"{base_url}/api/users/me",
                headers=admin_headers,
                json={"student_id": "TEST-ALIAS-001"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["user"]["student_id"] == "TEST-ALIAS-001"
            r2 = api_client.get(f"{base_url}/api/auth/me", headers=admin_headers)
            assert r2.json()["user"]["student_id"] == "TEST-ALIAS-001"
        finally:
            mongo_db.users.update_one(
                {"user_id": admin_user["user_id"]},
                {"$set": {"student_id": original_sid}},
            )


# ---------- POST /api/auth/logout ----------
class TestLogout:
    def test_logout_returns_ok_and_user_id(self, api_client, base_url, admin_headers, admin_user):
        r = api_client.post(f"{base_url}/api/auth/logout", headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("user_id") == admin_user["user_id"]

    def test_token_still_valid_after_logout_stateless_jwt(
        self, api_client, base_url, admin_headers
    ):
        """JWTs are stateless — server cannot invalidate without a denylist.
        Same token MUST continue to authenticate /api/auth/me after logout.
        Documented in test_credentials notes; the client is responsible for
        discarding the token. This test pins the intended behaviour."""
        r1 = api_client.post(f"{base_url}/api/auth/logout", headers=admin_headers)
        assert r1.status_code == 200
        r2 = api_client.get(f"{base_url}/api/auth/me", headers=admin_headers)
        assert r2.status_code == 200, r2.text

    def test_logout_without_auth_returns_401(self, api_client, base_url):
        r = api_client.post(f"{base_url}/api/auth/logout")
        assert r.status_code == 401


# ---------- MongoDB indexes (phase-1 carried over) ----------
class TestIndexes:
    def test_users_email_unique(self, mongo_db):
        idx = mongo_db.users.index_information()
        match = [v for v in idx.values() if v["key"] == [("email", 1)]]
        assert match and match[0].get("unique") is True

    def test_users_user_id_unique(self, mongo_db):
        idx = mongo_db.users.index_information()
        match = [v for v in idx.values() if v["key"] == [("user_id", 1)]]
        assert match and match[0].get("unique") is True

    def test_bookings_user_date_partial_unique_active(self, mongo_db):
        idx = mongo_db.bookings.index_information()
        target = [v for v in idx.values() if v["key"] == [("user_id", 1), ("date", 1)]]
        assert target, "bookings (user_id,date) index missing"
        assert target[0].get("unique") is True
        assert target[0].get("partialFilterExpression", {}).get("status") == "active"

    def test_bookings_date_slot_partial_unique_active(self, mongo_db):
        idx = mongo_db.bookings.index_information()
        target = [v for v in idx.values() if v["key"] == [("date", 1), ("slot_key", 1)]]
        assert target, "bookings (date,slot_key) index missing"
        assert target[0].get("unique") is True
        assert target[0].get("partialFilterExpression", {}).get("status") == "active"

    def test_bookings_expires_at_ttl(self, mongo_db):
        idx = mongo_db.bookings.index_information()
        ttl = [v for v in idx.values() if v["key"] == [("expires_at", 1)]]
        assert ttl and ttl[0].get("expireAfterSeconds") == 0
