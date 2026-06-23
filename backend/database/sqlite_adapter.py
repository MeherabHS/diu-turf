"""SQLite development adapter — asyncpg-compatible API for local dev."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import aiosqlite

from database.exceptions import UniqueViolationError
from database.schema_sqlite import SCHEMA_SQL
from services.serialize import parse_dt, utc_now_iso

log = logging.getLogger(__name__)

_PG_ADVISORY_LOCK = re.compile(
    r"SELECT\s+pg_advisory_xact_lock\s*\([^;]+\)",
    re.IGNORECASE,
)
_FOR_UPDATE = re.compile(r"\s+FOR UPDATE\b", re.IGNORECASE)
_CAST_SUFFIX = re.compile(r"::\w+(\[\])?", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\$\d+")
_ANY_PATTERN = re.compile(r"=\s*ANY\s*\(\$\d+\)", re.IGNORECASE)
_WRITE_VERBS = frozenset({"INSERT", "UPDATE", "DELETE", "REPLACE"})

_DATETIME_COLS = frozenset({
    "created_at", "updated_at", "last_login", "cancelled_at",
    "suspension_until", "promoted_at", "marked_at", "revoked_at", "expires_at",
})
_DATE_COLS = frozenset({"booking_date", "date"})
_TIME_COLS = frozenset({"start_time", "end_time"})
_JSON_COLS = frozenset({"metadata", "event_payload"})


class SQLiteRecord(dict):
    """Dict-like row — compatible with asyncpg.Record bracket access."""


def _is_write_sql(sql: str) -> bool:
    verb = sql.strip().split()[0].upper()
    return verb in _WRITE_VERBS


def _format_ts(value: datetime) -> str:
    """Write a canonical ISO UTC string for storage — delegates to serialize.py."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S") + f".{value.microsecond:06d}Z"


def _parse_timestamp(value: Any) -> Any:
    """Parse any DB timestamp value — delegates to serialize.parse_dt."""
    return parse_dt(value)


def _parse_date(value: Any) -> Any:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value


def _parse_time(value: Any) -> Any:
    if value is None or isinstance(value, time):
        return value
    if isinstance(value, str):
        parts = value.split(":")
        try:
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
        except (ValueError, IndexError):
            return value
    return value


def _id_param(value: Any) -> Any:
    """Store IDs exactly as TEXT in SQLite (32-char hex, no dashes)."""
    if isinstance(value, UUID):
        return value.hex
    if isinstance(value, str):
        cleaned = value.replace("-", "").lower()
        if len(cleaned) == 32 and all(c in "0123456789abcdef" for c in cleaned):
            return cleaned
    return value


def _normalize_param(value: Any) -> Any:
    if isinstance(value, UUID):
        return value.hex
    if isinstance(value, datetime):
        return _format_ts(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return _id_param(value)
    return value


def _normalize_row(row: aiosqlite.Row | None) -> SQLiteRecord | None:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for key in row.keys():
        val = row[key]
        if key in _DATETIME_COLS:
            val = _parse_timestamp(val)
        elif key in _DATE_COLS:
            val = _parse_date(val)
        elif key in _TIME_COLS:
            val = _parse_time(val)
        elif key in _JSON_COLS and isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                pass
        elif key in {"is_active", "is_read"} and isinstance(val, int):
            val = bool(val)
        out[key] = val
    return SQLiteRecord(out)


def _translate_sql(sql: str, args: tuple[Any, ...]) -> tuple[str, tuple[Any, ...]]:
    original = sql
    sql = _PG_ADVISORY_LOCK.sub("SELECT 1", sql)
    sql = _FOR_UPDATE.sub("", sql)
    sql = _CAST_SUFFIX.sub("", sql)

    any_match = _ANY_PATTERN.search(sql)
    if any_match and args:
        idx_match = re.search(r"\$(\d+)", any_match.group(0))
        if idx_match:
            pos = int(idx_match.group(1)) - 1
            if 0 <= pos < len(args) and isinstance(args[pos], (list, tuple)):
                values = list(args[pos])
                placeholders = ", ".join("?" * len(values))
                sql = _ANY_PATTERN.sub(f"IN ({placeholders})", sql, count=1)
                new_args: list[Any] = []
                for i, arg in enumerate(args):
                    if i == pos:
                        new_args.extend(_normalize_param(v) for v in values)
                    else:
                        new_args.append(_normalize_param(arg))
                sql = _PLACEHOLDER.sub("?", sql)
                return sql, tuple(new_args)

    new_args: list[Any] = []
    out_parts: list[str] = []
    last = 0
    for match in _PLACEHOLDER.finditer(sql):
        out_parts.append(sql[last : match.start()])
        idx = int(match.group(0)[1:]) - 1
        if idx < 0 or idx >= len(args):
            raise ValueError(f"Missing SQL bind parameter {match.group(0)}")
        new_args.append(_normalize_param(args[idx]))
        out_parts.append("?")
        last = match.end()
    out_parts.append(sql[last:])
    final_sql = "".join(out_parts)
    final_params = tuple(new_args)
    if "bookings" in original.lower() or "pg_advisory" in original.lower():
        log.info("[BOOKING] SQL: %s", final_sql)
        log.info("[BOOKING] PARAMS: %s", final_params)
    return final_sql, final_params


def _constraint_from_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "uniq_active_slot_per_day" in msg or "slot_per_day" in msg:
        return "uniq_active_slot_per_day"
    if "uniq_active_booking_per_user_per_day" in msg or "user_per_day" in msg:
        return "uniq_active_booking_per_user_per_day"
    if "uniq_active_waitlist_per_user" in msg:
        return "uniq_active_waitlist_per_user"
    if "users.email" in msg or "users_email" in msg:
        return "users_email_unique"
    if "users.student_id" in msg or "users_student_id" in msg:
        return "users_student_id_unique"
    if "slot_templates.turf_id" in msg or "slot_templates" in msg and "unique" in msg:
        return "slot_templates_turf_key_unique"
    return ""


def _raise_integrity_error(exc: aiosqlite.IntegrityError, sql: str, params: tuple[Any, ...]) -> None:
    msg = str(exc).lower()
    log.error("SQLite integrity error: %s | SQL: %s | params: %s", exc, sql, params)
    if "unique constraint failed" in msg:
        raise UniqueViolationError(str(exc), _constraint_from_error(exc)) from exc
    raise exc


class _SQLiteTransaction:
    def __init__(self, conn: "SQLiteConnection") -> None:
        self._conn = conn
        self._savepoint: str | None = None

    async def __aenter__(self) -> "SQLiteConnection":
        self._conn._txn_depth += 1
        if self._conn._txn_depth == 1:
            await self._conn._raw.execute("BEGIN IMMEDIATE")
        else:
            self._savepoint = f"sp_{self._conn._txn_depth}"
            await self._conn._raw.execute(f"SAVEPOINT {self._savepoint}")
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._conn._txn_depth == 1:
                if exc_type:
                    await self._conn._raw.execute("ROLLBACK")
                else:
                    await self._conn._raw.execute("COMMIT")
            elif self._savepoint:
                if exc_type:
                    await self._conn._raw.execute(f"ROLLBACK TO {self._savepoint}")
                await self._conn._raw.execute(f"RELEASE {self._savepoint}")
        finally:
            self._conn._txn_depth = max(0, self._conn._txn_depth - 1)


class SQLiteConnection:
    """Single SQLite connection with asyncpg-like query methods."""

    def __init__(self, raw: aiosqlite.Connection) -> None:
        self._raw = raw
        self._txn_depth = 0

    def transaction(self) -> _SQLiteTransaction:
        return _SQLiteTransaction(self)

    async def commit(self) -> None:
        if self._txn_depth == 0:
            await self._raw.commit()

    async def _maybe_commit(self, sql: str) -> None:
        if self._txn_depth == 0 and _is_write_sql(sql):
            await self._raw.commit()

    async def execute(self, sql: str, *args: Any) -> str:
        sql, params = _translate_sql(sql, args)
        try:
            cursor = await self._raw.execute(sql, params)
            rowcount = cursor.rowcount if cursor.rowcount is not None else 0
            await cursor.close()
            await self._maybe_commit(sql)
            verb = sql.strip().split()[0].upper()
            if verb == "UPDATE":
                return f"UPDATE {rowcount}"
            if verb == "DELETE":
                return f"DELETE {rowcount}"
            if verb == "INSERT":
                return f"INSERT {rowcount}"
            return f"OK {rowcount}"
        except aiosqlite.IntegrityError as exc:
            if self._txn_depth == 0:
                await self._raw.rollback()
            _raise_integrity_error(exc, sql, params)
        except aiosqlite.OperationalError as exc:
            if "bookings" in sql.lower():
                log.error("[BOOKING] SQL: %s", sql)
                log.error("[BOOKING] PARAMS: %s", params)
            raise exc

    async def fetchval(self, sql: str, *args: Any) -> Any:
        row = await self.fetchrow(sql, *args)
        if row is None:
            return None
        return next(iter(row.values()))

    async def fetchrow(self, sql: str, *args: Any) -> SQLiteRecord | None:
        sql, params = _translate_sql(sql, args)
        try:
            cursor = await self._raw.execute(sql, params)
            row = await cursor.fetchone()
            await cursor.close()
            await self._maybe_commit(sql)
            return _normalize_row(row)
        except aiosqlite.IntegrityError as exc:
            if self._txn_depth == 0:
                await self._raw.rollback()
            _raise_integrity_error(exc, sql, params)
        except aiosqlite.OperationalError as exc:
            if "bookings" in sql.lower():
                log.error("[BOOKING] SQL: %s", sql)
                log.error("[BOOKING] PARAMS: %s", params)
            raise exc

    async def fetch(self, sql: str, *args: Any) -> list[SQLiteRecord]:
        sql, params = _translate_sql(sql, args)
        try:
            cursor = await self._raw.execute(sql, params)
            rows = await cursor.fetchall()
            await cursor.close()
            await self._maybe_commit(sql)
            return [_normalize_row(r) for r in rows if r is not None]
        except aiosqlite.IntegrityError as exc:
            if self._txn_depth == 0:
                await self._raw.rollback()
            _raise_integrity_error(exc, sql, params)


class _AcquireCtx:
    def __init__(self, pool: "SQLitePool") -> None:
        self._pool = pool

    async def __aenter__(self) -> SQLiteConnection:
        return self._pool._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class SQLitePool:
    """Minimal pool wrapper — one shared connection for local dev."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: SQLiteConnection | None = None
        self._raw: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._raw = await aiosqlite.connect(self.path, timeout=30)
        self._raw.row_factory = aiosqlite.Row
        await self._raw.execute("PRAGMA foreign_keys = ON")
        await self._raw.execute("PRAGMA busy_timeout = 5000")
        await self._raw.execute("PRAGMA journal_mode = WAL")
        for stmt in SCHEMA_SQL.split(";"):
            chunk = stmt.strip()
            if chunk and not chunk.upper().startswith("PRAGMA"):
                await self._raw.execute(chunk)
        await self._raw.commit()
        self._conn = SQLiteConnection(self._raw)
        log.info("SQLite schema ready at %s", self.path)

    def acquire(self) -> _AcquireCtx:
        if self._conn is None:
            raise RuntimeError("SQLite pool not initialized")
        return _AcquireCtx(self)

    async def close(self) -> None:
        if self._raw:
            await self._raw.close()
            self._raw = None
            self._conn = None


async def create_sqlite_pool(path: Path) -> SQLitePool:
    pool = SQLitePool(path)
    await pool.initialize()
    return pool


async def close_sqlite_pool(pool: SQLitePool) -> None:
    await pool.close()
