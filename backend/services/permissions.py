"""Role-based booking permissions."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from services.auth_dep import get_current_user

BOOKING_ROLES = frozenset({"booker", "admin", "super_admin"})
VIEW_ONLY_ROLES = frozenset({"viewer", "student"})


def can_book(user: dict) -> bool:
    """True when the user may create/cancel bookings or join waitlists."""
    return user.get("role") in BOOKING_ROLES


def is_view_only(user: dict) -> bool:
    role = user.get("role")
    return role in VIEW_ONLY_ROLES or (role not in BOOKING_ROLES and role not in ("admin", "super_admin"))


def booking_denied_detail() -> str:
    return "You need booking access to reserve or cancel slots."


async def require_booking_access(user: dict = Depends(get_current_user)) -> dict:
    if not can_book(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=booking_denied_detail(),
        )
    return user
