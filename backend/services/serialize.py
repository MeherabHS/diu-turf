"""Centralized datetime utilities — works for both PostgreSQL (datetime objects)
and SQLite dev mode (ISO string values, including legacy malformed ones).

Public API
──────────
  utc_now()         → datetime (tz-aware UTC)
  utc_now_iso()     → str  "YYYY-MM-DDTHH:MM:SS.ffffffZ"
  parse_dt(value)   → datetime | None
  serialize_dt(v)   → str | None  (always valid ISO, safe for JSON + Pydantic)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Pattern: 2026-06-22T15:35:349485Z
#   HH:MM: prefix, then two-digit seconds, then extra digits (microseconds smashed in)
_BAD_SMASHED = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:)"   # up to and including the last colon
    r"(\d{2})"                               # two-digit seconds
    r"(\d+)Z$",                              # extra digits (no dot separator)
)
# Pattern: 2026-06-22T16:00:09.09.794Z
#   seconds.junk.usecZ (double dot, the first decimal part is junk)
_BAD_DOUBLE_DOT = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"   # up to full seconds
    r"\.\d{1,6}"                                   # junk first decimal (dots)
    r"\.(\d+)Z$",                                  # real microseconds after second dot
)


def _repair(text: str) -> str:
    """Try to fix known malformed SQLite timestamp strings."""
    # Double-dot: 2026-06-22T16:00:09.09.794Z
    m = _BAD_DOUBLE_DOT.match(text)
    if m:
        usec = m.group(2).ljust(6, "0")[:6]
        return f"{m.group(1)}.{usec}Z"

    # Smashed: 2026-06-22T15:35:349485Z  (seconds=34, usec=9485)
    m = _BAD_SMASHED.match(text)
    if m:
        usec = m.group(3).ljust(6, "0")[:6]
        return f"{m.group(1)}{m.group(2)}.{usec}Z"

    return text


def utc_now() -> datetime:
    """Current time as a tz-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Current UTC as a canonical ISO string: YYYY-MM-DDTHH:MM:SS.ffffffZ"""
    now = utc_now()
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{now.microsecond:06d}Z"


def parse_dt(value: Any) -> datetime | None:
    """Parse any DB timestamp value to a tz-aware datetime or None.

    Handles:
      - None → None
      - datetime (with or without tzinfo) → normalized to UTC
      - valid ISO str with Z or +00:00
      - legacy malformed strings like 2026-06-22T16:00:09.09.794Z
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        text = _repair(text)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def serialize_dt(value: Any) -> str | None:
    """Return an API-safe ISO-8601 UTC string, or None.

    Accepts datetime objects (PostgreSQL) or ISO strings (SQLite).
    Always returns a clean, Pydantic-parseable string.
    """
    dt = parse_dt(value)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{dt.microsecond:06d}Z"
