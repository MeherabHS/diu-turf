"""Role-based booking permissions."""
from __future__ import annotations

from services.auth_dep import get_current_user, require_booking_access

BOOKING_ROLES = frozenset({"booker", "admin", "super_admin"})
VIEW_ONLY_ROLES = frozenset({"viewer", "student"})


def can_book(user: dict) -> bool:
    """True when the user may create/cancel bookings or join waitlists."""
    return user.get("role") in BOOKING_ROLES


def is_view_only(user: dict) -> bool:
    role = user.get("role")
    return role in VIEW_ONLY_ROLES or (role not in BOOKING_ROLES and role not in ("admin", "super_admin"))


def booking_denied_detail() -> str:
    return "Booking access required"
