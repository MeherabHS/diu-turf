"""Auth routes — DIU email/password + Google OAuth (paused) + JWT.

Endpoints:
  POST /api/auth/register  DIU email + password registration → JWT.
  POST /api/auth/login     Email + password login → JWT.
  POST /api/auth/google     Verify Google ID token → upsert PG user → issue JWT.
  POST /api/auth/dev-login  Dev-only bypass (DEV_AUTH_ENABLED=true, non-production).
  GET  /api/auth/me         Return current authenticated user.
  POST /api/auth/logout     Revoke JWT jti + clear client token.

Security model:
  - Google ID token verified server-side via Google's tokeninfo endpoint.
  - Email domain restricted to @diu.edu.bd at this layer (not trusted from client).
  - JWT issued by this application (HS256, JWT_SECRET).
  - JWT carries jti claim; stored in token_revocations on logout.
  - Role assigned server-side; never read from the Google token.
  - Frontend email/role claims are NEVER trusted for access decisions.
  - dev-login is disabled when ENVIRONMENT=production or DEV_AUTH_ENABLED!=true.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from database.connection import get_conn
from database.exceptions import UniqueViolationError
from database.timing import (
    log_ungranted_locks,
    timed_execute,
    timed_fetchrow,
)
from config.admin_emails import role_for_email
from services.auth_dep import get_current_user_pg
from services.google_auth import GoogleClaims, is_diu_email, verify_google_id_token
from services.jwt_util import decode_token, issue_token
from services.models import (
    AuthMeResponse,
    AuthResponse,
    DevLoginRequest,
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    User,
)
from services.password_util import hash_password, verify_password
from services.profile_util import compute_profile_completed
from services.rate_limit import enforce_auth_rate_limit
from services.registration_util import normalize_email, normalize_student_id, validate_registration_identity
from services.token_revocation import revoke_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)
_indexes_logged = False


async def _log_users_indexes_once(conn: asyncpg.Connection) -> None:
    """Log users-table indexes once per process (PostgreSQL only)."""
    global _indexes_logged
    if _indexes_logged:
        return
    try:
        rows = await conn.fetch(
            """SELECT indexname, indexdef
               FROM pg_indexes
               WHERE schemaname = 'public' AND tablename = 'users'
               ORDER BY indexname"""
        )
        if rows:
            for row in rows:
                log.info("[INDEX] users.%s → %s", row["indexname"], row["indexdef"])
        else:
            log.warning("[INDEX] no indexes found on public.users")
        _indexes_logged = True
    except Exception:
        log.exception("[INDEX] failed to read pg_indexes for users")


def _timing(step: str, started: float) -> float:
    """Log a dev-login step and return elapsed ms since `started`."""
    elapsed = (time.perf_counter() - started) * 1000
    log.info("[TIMING] step=%s elapsed=%.1fms", step, elapsed)
    return elapsed


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_response(row: asyncpg.Record) -> User:
    """Convert a PostgreSQL users row to the User Pydantic model."""
    d = dict(row)
    return User(
        user_id=str(d["id"]),
        email=d["email"],
        name=d["name"],
        picture=d.get("avatar_url"),
        google_sub=d.get("google_sub"),
        role=d["role"],
        student_id=d.get("student_id"),
        department=d.get("department"),
        batch=d.get("batch"),
        room_number=d.get("room_number"),
        hostel_name=d.get("hostel_name"),
        phone=d.get("phone"),
        profile_completed=compute_profile_completed(d),
        created_at=d["created_at"],
        last_login=d.get("last_login"),
        updated_at=d["updated_at"],
    )


async def _upsert_user(
    conn: asyncpg.Connection,
    claims: GoogleClaims,
    now: datetime,
) -> tuple[asyncpg.Record, str]:
    """Insert or update the user row.  Returns (row, event_type)."""

    existing = await conn.fetchrow(
        "SELECT * FROM users WHERE email = $1",
        claims["email"],
    )

    if existing:
        assigned_role = role_for_email(claims["email"])
        # Update: refresh Google sub (if first PG login), name, avatar, last_login, role.
        await conn.execute(
            """UPDATE users
               SET google_sub = COALESCE(google_sub, $2),
                   name       = CASE
                                  WHEN TRIM(COALESCE($3, '')) = '' THEN name
                                  ELSE $3
                                END,
                   avatar_url = COALESCE($4, avatar_url),
                   role       = $5,
                   last_login = $6,
                   updated_at = $6
               WHERE id = $1""",
            existing["id"],
            claims["sub"],
            claims["name"],
            claims["picture"],
            assigned_role,
            now,
        )
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", existing["id"])
        return row, "auth.login"

    # Create new account — role assigned from admin email list.
    assigned_role = role_for_email(claims["email"])
    student_id = claims["email"].split("@", 1)[0]
    user_id = await conn.fetchval(
        """INSERT INTO users
               (name, email, google_sub, avatar_url, student_id, role, is_active, last_login)
           VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
           RETURNING id""",
        claims["name"],
        claims["email"],
        claims["sub"],
        claims["picture"],
        student_id,
        assigned_role,
        now,
    )
    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return row, "auth.register"


async def _write_audit(
    conn: asyncpg.Connection,
    user_id,
    event_type: str,
    message: str,
    metadata: dict,
) -> None:
    """Insert one row into activity_logs (fire-and-forget, never raises)."""
    try:
        await conn.execute(
            """INSERT INTO activity_logs (actor_user_id, event_type, message, metadata)
               VALUES ($1, $2, $3, $4::jsonb)""",
            user_id,
            event_type,
            message,
            json.dumps(metadata),
        )
    except Exception:
        log.exception("audit log write failed for event_type=%s", event_type)


def _assert_account_allowed(row: asyncpg.Record, now: datetime) -> None:
    """Raise HTTP 403 if the account is deactivated or suspended."""
    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )
    sus_until = row["suspension_until"]
    if sus_until is not None:
        if sus_until.tzinfo is None:
            sus_until = sus_until.replace(tzinfo=timezone.utc)
        if sus_until > now:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account suspended until {sus_until.isoformat()}. "
                       f"Reason: {row['suspension_reason'] or 'policy violation'}.",
            )


async def _issue_auth_response(
    conn: asyncpg.Connection,
    row: asyncpg.Record,
    *,
    event_type: str,
    method: str,
    now: datetime,
    audit_message: str,
    audit_metadata: dict | None = None,
) -> AuthResponse:
    """Issue JWT, write audit log, return AuthResponse."""
    token, _exp = issue_token(
        user_id=str(row["id"]),
        email=row["email"],
        role=row["role"],
    )
    await _write_audit(
        conn,
        row["id"],
        event_type,
        audit_message,
        {"method": method, **(audit_metadata or {})},
    )
    log.info("[AUTH] jwt issued email=%s role=%s event=%s", row["email"], row["role"], event_type)
    return AuthResponse(access_token=token, user=_build_user_response(row))


# ── POST /api/auth/register ───────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
) -> AuthResponse:
    """Register a new student with DIU email + password."""
    enforce_auth_rate_limit(request, "auth:register")
    email = normalize_email(payload.email)
    student_id = normalize_student_id(payload.student_id)
    full_name = payload.full_name.strip()

    identity_err = validate_registration_identity(email, student_id)
    if identity_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=identity_err)

    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )

    existing_email = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    existing_sid = await conn.fetchval("SELECT id FROM users WHERE student_id = $1", student_id)
    if existing_sid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this student ID already exists.",
        )

    now = datetime.now(timezone.utc)
    password_hash = hash_password(payload.password)
    room_number = (payload.room_number or "").strip() or None
    hostel_name = (payload.hostel_name or "").strip() or None
    phone = (payload.phone or "").strip() or None

    try:
        async with conn.transaction():
            user_id = await conn.fetchval(
                """INSERT INTO users
                       (name, email, password_hash, student_id, department, batch,
                        room_number, hostel_name, phone,
                        role, is_active, auth_provider, last_login, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                           'viewer', TRUE, 'password', $10, $10, $10)
                   RETURNING id""",
                full_name,
                email,
                password_hash,
                student_id,
                payload.department.strip(),
                payload.batch.strip(),
                room_number,
                hostel_name,
                phone,
                now,
            )
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Registration failed — user row missing after insert.",
                )
            return await _issue_auth_response(
                conn,
                row,
                event_type="auth.register",
                method="password",
                now=now,
                audit_message=f"New account: {email}",
            )
    except UniqueViolationError as exc:
        constraint = getattr(exc, "constraint_name", "") or ""
        if "email" in constraint:
            detail = "An account with this email already exists."
        elif "student_id" in constraint:
            detail = "An account with this student ID already exists."
        else:
            detail = "An account with these details already exists."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc


# ── POST /api/auth/login ──────────────────────────────────────────────────────

@router.post("/login", response_model=AuthResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
) -> AuthResponse:
    """Authenticate with DIU email + password."""
    enforce_auth_rate_limit(request, "auth:login")
    email = normalize_email(payload.email)
    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        "SELECT * FROM users WHERE email = $1",
        email,
    )
    if row is None or not verify_password(payload.password, row.get("password_hash")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    _assert_account_allowed(row, now)

    async with conn.transaction():
        await conn.execute(
            "UPDATE users SET last_login = $1, updated_at = $1 WHERE id = $2",
            now,
            row["id"],
        )
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", row["id"])
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed — user row missing after update.",
            )
        return await _issue_auth_response(
            conn,
            row,
            event_type="auth.login",
            method="password",
            now=now,
            audit_message=f"Login: {email}",
        )


# ── POST /api/auth/google ─────────────────────────────────────────────────────

@router.post("/google", response_model=AuthResponse, status_code=status.HTTP_200_OK)
async def google_login(
    payload: GoogleAuthRequest,
    conn: asyncpg.Connection = Depends(get_conn),
) -> AuthResponse:
    """Exchange a Google ID token for an application JWT.

    10-step flow:
      1. Verify Google ID token (signature + expiry + issuer via Google tokeninfo).
      2. Verify token audience matches configured client ID(s).
      3. Verify email is @diu.edu.bd — backend is authoritative.
      4. Upsert user in PostgreSQL (INSERT on first login, UPDATE thereafter).
      5. Check account is active / not suspended.
      6. Issue application JWT (HS256, 7-day, with jti).
      7. Write audit log (login or first registration).
      8. Return { access_token, user }.
    """
    log.info("[GOOGLE_AUTH] id_token received len=%d", len(payload.id_token))

    # Step 1 & 2: Google verification (raises ValueError on failure).
    try:
        claims = await verify_google_id_token(payload.id_token)
    except ValueError as exc:
        log.warning("[GOOGLE_AUTH] verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google authentication failed: {exc}",
        ) from exc

    log.info(
        "[GOOGLE_AUTH] claims verified email=%s sub=%s",
        claims["email"],
        claims["sub"][:8] + "...",
    )

    # Step 3: Domain restriction — authoritative.
    if not is_diu_email(claims["email"]):
        log.warning("[GOOGLE_AUTH] rejected non-DIU email=%s", claims["email"])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only DIU institutional accounts (@diu.edu.bd) are allowed.",
        )

    now = datetime.now(timezone.utc)

    # Steps 4 & 5: Upsert + active check.
    async with conn.transaction():
        row, event_type = await _upsert_user(conn, claims, now)
        _assert_account_allowed(row, now)

        # Step 6: Issue application JWT.
        token, _exp = issue_token(
            user_id=str(row["id"]),
            email=row["email"],
            role=row["role"],
        )

        # Step 7: Audit log (inside transaction so it rolls back with user upsert).
        await _write_audit(
            conn,
            row["id"],
            event_type,
            f"{'New account' if event_type == 'auth.register' else 'Login'}: {claims['email']}",
            {"method": "google", "google_sub": claims["sub"]},
        )

    log.info(
        "[GOOGLE_AUTH] user upserted id=%s event=%s role=%s",
        row["id"],
        event_type,
        row["role"],
    )

    # Step 8: Return response.
    log.info("[GOOGLE_AUTH] jwt issued email=%s role=%s", row["email"], row["role"])
    return AuthResponse(access_token=token, user=_build_user_response(row))


# ── POST /api/auth/dev-login ──────────────────────────────────────────────────

def _dev_auth_enabled() -> bool:
    """Return True only when both guards pass: flag set AND not production."""
    flag = os.getenv("DEV_AUTH_ENABLED", "false").lower() in ("1", "true", "yes")
    env  = os.getenv("ENVIRONMENT", "production").lower()
    return flag and env != "production"


def _dev_identity_from_email(email: str) -> tuple[str, str]:
    """Derive display name and student_id from a DIU email local-part."""
    student_id = email.split("@", 1)[0]
    name = student_id or "Dev User"
    return name, student_id


@router.post("/dev-login", response_model=AuthResponse, status_code=status.HTTP_200_OK)
async def dev_login(
    payload: DevLoginRequest,
    conn: asyncpg.Connection = Depends(get_conn),
) -> AuthResponse:
    """Development-only login bypass.

    Disabled at runtime when ENVIRONMENT=production or DEV_AUTH_ENABLED!=true.
    Accepts any @diu.edu.bd email — creates the account if it does not exist.
    Returns the same { access_token, user } shape as /api/auth/google.
    """
    request_start = time.perf_counter()
    log.info("[TIMING] step=start")

    if not _dev_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login is disabled in this environment.",
        )

    email = payload.email.strip().lower()
    if not is_diu_email(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only DIU institutional accounts (@diu.edu.bd) are allowed.",
        )

    try:
        await _log_users_indexes_once(conn)
        await log_ungranted_locks(conn)

        now = datetime.now(timezone.utc)
        name, student_id = _dev_identity_from_email(email)
        _timing("validate", request_start)

        assigned_role = role_for_email(email)
        row: asyncpg.Record | None = None
        event_type: str

        async with conn.transaction():
            tx_start = time.perf_counter()
            log.info("[TIMING] step=transaction_begin")

            find_start = time.perf_counter()
            existing = await timed_fetchrow(
                conn,
                "find_user",
                "SELECT * FROM users WHERE email = $1",
                email,
            )
            _timing("find_user", find_start)

            if existing:
                update_start = time.perf_counter()
                row = await timed_fetchrow(
                    conn,
                    "update_user",
                    """UPDATE users
                       SET last_login = $1,
                           updated_at = $1,
                           role       = $2,
                           student_id = COALESCE(student_id, $4),
                           name       = CASE
                                          WHEN TRIM(COALESCE(name, '')) = '' THEN $5
                                          ELSE name
                                        END
                       WHERE id = $3
                       RETURNING *""",
                    now,
                    assigned_role,
                    existing["id"],
                    student_id,
                    name,
                )
                _timing("update_user", update_start)
                event_type = "auth.login"
                log.info("[TIMING] step=create_user skipped (user_exists id=%s)", existing["id"])
            else:
                create_start = time.perf_counter()
                row = await timed_fetchrow(
                    conn,
                    "create_user",
                    """INSERT INTO users
                           (name, email, student_id, role, is_active,
                            last_login, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, TRUE, $5, $5, $5)
                       RETURNING *""",
                    name,
                    email,
                    student_id,
                    assigned_role,
                    now,
                )
                _timing("create_user", create_start)
                event_type = "auth.register"

            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Dev login failed — user row missing after upsert.",
                )

            if not row["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This account has been deactivated.",
                )

            token_start = time.perf_counter()
            token, _exp = issue_token(
                user_id=str(row["id"]),
                email=row["email"],
                role=row["role"],
            )
            _timing("generate_token", token_start)

            audit_start = time.perf_counter()
            await timed_execute(
                conn,
                "audit_log",
                """INSERT INTO activity_logs (actor_user_id, event_type, message, metadata)
                   VALUES ($1, $2, $3, $4::jsonb)""",
                row["id"],
                event_type,
                f"[DEV] {'New account' if event_type == 'auth.register' else 'Login'}: {email}",
                json.dumps({"method": "dev_login"}),
            )
            _timing("audit_log", audit_start)

            _timing("transaction_commit", tx_start)
            log.info("[TIMING] step=transaction_end (committed)")

        response_start = time.perf_counter()
        result = AuthResponse(access_token=token, user=_build_user_response(row))
        _timing("response", response_start)

        total_ms = (time.perf_counter() - request_start) * 1000
        log.info(
            "[TIMING] dev-login completed in %.0fms email=%s event=%s",
            total_ms,
            email,
            event_type,
        )
        return result
    except HTTPException:
        total_ms = (time.perf_counter() - request_start) * 1000
        log.info("[TIMING] dev-login failed (HTTP) in %.0fms email=%s", total_ms, email)
        raise
    except Exception:
        total_ms = (time.perf_counter() - request_start) * 1000
        log.exception(
            "[TIMING] dev-login failed in %.0fms email=%s — see traceback",
            total_ms,
            email,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dev login failed — see server logs for traceback.",
        ) from None


# ── GET /api/auth/me ──────────────────────────────────────────────────────────

@router.get("/me", response_model=AuthMeResponse)
async def me(
    user: dict = Depends(get_current_user_pg),
) -> AuthMeResponse:
    """Return the currently authenticated user.

    Uses get_current_user_pg — requires a PostgreSQL account (Phase 4+).
    Legacy MongoDB accounts should re-authenticate via /google.
    """
    return AuthMeResponse(
        user=User(
            user_id=user["user_id"],
            email=user["email"],
            name=user["name"],
            picture=user.get("picture"),
            google_sub=user.get("google_sub"),
            role=user["role"],
            student_id=user.get("student_id"),
            department=user.get("department"),
            batch=user.get("batch"),
            room_number=user.get("room_number"),
            hostel_name=user.get("hostel_name"),
            phone=user.get("phone"),
            profile_completed=user.get("profile_completed", False),
            created_at=user["created_at"],
            last_login=user.get("last_login"),
            updated_at=user["updated_at"],
        )
    )


# ── POST /api/auth/logout ─────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    user: dict = Depends(get_current_user_pg),
    authorization: str | None = Header(default=None),
    conn: asyncpg.Connection = Depends(get_conn),
) -> dict:
    """Revoke the current JWT by storing its jti in token_revocations."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            expires_at = datetime.fromtimestamp(int(exp), tz=timezone.utc)
            await revoke_token(
                conn,
                jti=jti,
                user_id=user["user_id"],
                expires_at=expires_at,
            )

    await _write_audit(
        conn,
        None,
        "auth.logout",
        f"Logout: {user['email']}",
        {"user_id": user["user_id"]},
    )

    return {"ok": True, "user_id": user["user_id"]}
