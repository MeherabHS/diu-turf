"""Pydantic models — Phase 4 update.

Changes from Phase 1-3:
  GoogleAuthRequest   — now carries 'id_token' (Google ID token), not session_token.
  AuthResponse        — renamed field: token → access_token.
  User                — added google_sub, last_login; role extended to super_admin.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, EmailStr, Field

from services.profile_util import compute_profile_completed
from services.serialize import parse_dt as _parse_dt


def _coerce_dt(v: Any) -> Any:
    """Accept datetime objects or ISO strings (PostgreSQL + SQLite)."""
    if v is None or isinstance(v, datetime):
        return v
    if isinstance(v, str):
        parsed = _parse_dt(v)
        return parsed if parsed is not None else v
    return v


FlexDatetime = Annotated[datetime, BeforeValidator(_coerce_dt)]
OptFlexDatetime = Annotated[Optional[datetime], BeforeValidator(_coerce_dt)]

Role = Literal["viewer", "booker", "student", "admin", "super_admin"]
SlotId = str  # slot_key from slot_templates (A/B/C seed + admin-defined slots)
SlotStatus = Literal["available", "booked", "completed", "maintenance"]
BookingStatus = Literal["booked", "completed", "cancelled"]
ActivityAction = Literal["BOOKED", "CANCELLED", "COMPLETED", "EXPIRED"]


# ── Auth models ───────────────────────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    """Phase 4: accepts a Google ID token from expo-auth-session."""
    id_token: str = Field(..., min_length=10, description="Google ID token from the client")


class DevLoginRequest(BaseModel):
    """Development-only login bypass — rejected in production."""
    email: str = Field(..., min_length=6, description="@diu.edu.bd email for dev login")


class RegisterRequest(BaseModel):
    """POST /api/auth/register — DIU email + password registration."""
    email: str = Field(..., min_length=10)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=80)
    student_id: str = Field(..., min_length=10, max_length=12)
    department: str = Field(..., min_length=1, max_length=100)
    batch: str = Field(..., min_length=1, max_length=50)
    room_number: Optional[str] = Field(default=None, max_length=20)
    hostel_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    """POST /api/auth/login — email + password."""
    email: str = Field(..., min_length=10)
    password: str = Field(..., min_length=1, max_length=128)


class User(BaseModel):
    """Normalised user object returned in every auth response.

    user_id maps from the PostgreSQL 'id' (UUID as string) or the MongoDB
    'user_id' field — both routes use this same model.
    """
    user_id: str
    email: EmailStr
    name: str
    picture: Optional[str] = None           # avatar_url alias
    google_sub: Optional[str] = None        # Google sub claim (Phase 4)
    role: str = "viewer"
    student_id: Optional[str] = None
    department: Optional[str] = None
    batch: Optional[str] = None
    room_number: Optional[str] = None
    hostel_name: Optional[str] = None
    phone: Optional[str] = None
    profile_completed: bool = False
    created_at: FlexDatetime
    last_login: OptFlexDatetime = None
    updated_at: FlexDatetime


class AuthResponse(BaseModel):
    """Returned by POST /api/auth/google on successful authentication."""
    access_token: str       # JWT issued by this application
    user: User


class AuthMeResponse(BaseModel):
    user: User


# ── Profile ───────────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    student_id: str = Field(min_length=3, max_length=32)
    department: str = Field(min_length=1, max_length=100)
    batch: str = Field(min_length=1, max_length=50)
    room_number: Optional[str] = Field(default=None, max_length=20)
    hostel_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)


# ── Bookings ──────────────────────────────────────────────────────────────────

class Booking(BaseModel):
    booking_id: str
    user_id: str
    student_name: str
    student_id: str
    email: EmailStr
    booking_date: str
    slot_id: SlotId
    slot_label: str
    start_time: str
    end_time: str
    status: BookingStatus
    created_at: FlexDatetime
    updated_at: FlexDatetime
    day_of_week: int
    hour: int
    booking_lead_time: int
    department: Optional[str] = None
    batch: Optional[str] = None


class BookingCreate(BaseModel):
    booking_date: str
    slot_id: SlotId


class SlotView(BaseModel):
    slot_id: SlotId
    slot_label: str
    start_time: str
    end_time: str
    booking_date: str
    status: SlotStatus
    booking: Optional[Booking] = None
    is_mine: bool = False
    is_waitlisted: bool = False
    waitlist_position: Optional[int] = None
    waitlist_id: Optional[str] = None
    booker_name: Optional[str] = None
    booker_student_id: Optional[str] = None


class WaitlistEntry(BaseModel):
    waitlist_id: str
    booking_date: str
    slot_id: SlotId
    slot_label: str
    start_time: str
    end_time: str
    position: int
    status: str
    created_at: FlexDatetime


class DateOverview(BaseModel):
    booking_date: str
    slots: list[SlotView]


class OccupancyResponse(BaseModel):
    booking_date: str
    total_slots: int
    filled_slots: int
    percentage: int


class CalendarDay(BaseModel):
    date: str
    total: int
    mine: int
    fully_booked: bool


class CalendarResponse(BaseModel):
    year: int
    month: int
    days: list[CalendarDay]


class WaitlistJoin(BaseModel):
    booking_date: str
    slot_id: SlotId


class WeeklyUsage(BaseModel):
    week_start: str
    bookings_made: int
    bookings_limit: int
    cancellations_made: int
    cancellations_limit: int


# ── Activity / Notifications ──────────────────────────────────────────────────

class ActivityItem(BaseModel):
    activity_id: str
    action: ActivityAction
    user_id: str
    student_name: str
    student_id: Optional[str] = None
    booking_id: Optional[str] = None
    booking_date: Optional[str] = None
    slot_id: Optional[SlotId] = None
    slot_label: Optional[str] = None
    created_at: FlexDatetime


class Notification(BaseModel):
    notification_id: str
    user_id: str
    title: str
    message: str
    kind: str
    read: bool = False
    created_at: FlexDatetime
    booking_id: Optional[str] = None
