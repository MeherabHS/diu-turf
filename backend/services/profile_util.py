"""Shared profile completion rules."""
from __future__ import annotations

from typing import Any


def compute_profile_completed(data: dict[str, Any]) -> bool:
    """Profile is complete when core student fields are filled."""
    return all(
        str(data.get(field) or "").strip()
        for field in ("name", "student_id", "department", "batch")
    )
