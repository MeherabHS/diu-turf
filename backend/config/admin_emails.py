"""Admin access — assign role=admin by email at login (server-side only).

Add addresses here to grant admin without code changes elsewhere.
"""
from __future__ import annotations

ADMIN_EMAILS: list[str] = [
    "261-35-113@diu.edu.bd",
]

_ADMIN_SET = frozenset(e.strip().lower() for e in ADMIN_EMAILS)


def role_for_email(email: str) -> str:
    """Return 'admin' for configured emails, otherwise 'student'."""
    return "admin" if email.strip().lower() in _ADMIN_SET else "student"
