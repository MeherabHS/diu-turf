"""UUID normalization helpers — compare IDs across PG/SQLite representations."""
from __future__ import annotations

from typing import Any
from uuid import UUID


def uuid_hex(value: Any) -> str:
    """Return canonical 32-char lowercase hex for any UUID representation."""
    if isinstance(value, UUID):
        return value.hex
    if isinstance(value, str):
        cleaned = value.replace("-", "").lower()
        if len(cleaned) == 32 and all(c in "0123456789abcdef" for c in cleaned):
            return cleaned
        return UUID(value).hex
    return UUID(str(value)).hex


def uuid_same(a: Any, b: Any) -> bool:
    """True when *a* and *b* refer to the same UUID (object, dashed, or hex)."""
    return uuid_hex(a) == uuid_hex(b)
