"""Static turf slot definitions for Phase 2.

Centralised so future phases can swap to a DB-backed schedule without touching
booking logic. All times interpreted in `TURF_TZ` (Asia/Dhaka).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls, datetime, time, timedelta
from typing import Final, Optional
from zoneinfo import ZoneInfo

TURF_TZ: Final = ZoneInfo("Asia/Dhaka")
MAIN_TURF_NAME: Final = "Main Turf"


@dataclass(frozen=True)
class SlotTemplate:
    slot_id: str
    slot_label: str
    start_time: time
    end_time: time

    @property
    def display_range(self) -> str:
        # %-I is Linux-only (strips leading zero); use lstrip("0") for cross-platform compat.
        start = self.start_time.strftime("%I:%M %p").lstrip("0")
        end = self.end_time.strftime("%I:%M %p").lstrip("0")
        return f"{start} - {end}"


SLOT_TEMPLATES: Final[tuple[SlotTemplate, ...]] = (
    SlotTemplate("A", "Slot A", time(16, 0), time(17, 0)),
    SlotTemplate("B", "Slot B", time(17, 0), time(18, 0)),
    SlotTemplate("C", "Slot C", time(18, 0), time(19, 0)),
)


def get_slot(slot_id: str) -> Optional[SlotTemplate]:
    return next((s for s in SLOT_TEMPLATES if s.slot_id == slot_id), None)


def parse_hhmm(value: str) -> time:
    """Parse HH:MM or HH:MM:SS into a time."""
    raw = value.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time '{value}' (expected HH:MM)")


def coerce_db_time(value: time | str) -> time:
    if isinstance(value, time):
        return value
    return parse_hhmm(str(value))


def time_ranges_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """True when two same-day intervals overlap (touching endpoints do not overlap)."""
    return a_start < b_end and b_start < a_end


def slot_template_from_row(row: dict) -> SlotTemplate:
    key = row["slot_key"]
    return SlotTemplate(
        slot_id=key,
        slot_label=f"Slot {key}",
        start_time=coerce_db_time(row["start_time"]),
        end_time=coerce_db_time(row["end_time"]),
    )


def ordered_active_slots(slot_templates: dict[str, dict]) -> list[SlotTemplate]:
    slots = [slot_template_from_row(v) for v in slot_templates.values()]
    slots.sort(key=lambda s: (s.start_time, s.slot_id))
    return slots


def resolve_slot(slot_key: str, slot_templates: dict[str, dict]) -> Optional[SlotTemplate]:
    row = slot_templates.get(slot_key)
    if row:
        return slot_template_from_row(row)
    return get_slot(slot_key)


def active_slot_count(slot_templates: dict[str, dict]) -> int:
    return len(slot_templates)


def parse_booking_date(value: str) -> date_cls:
    """Parse YYYY-MM-DD into a date (raises ValueError on bad input)."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def slot_datetimes(booking_date: date_cls, slot: SlotTemplate) -> tuple[datetime, datetime]:
    start = datetime.combine(booking_date, slot.start_time, tzinfo=TURF_TZ)
    end = datetime.combine(booking_date, slot.end_time, tzinfo=TURF_TZ)
    return start, end


def now_turf() -> datetime:
    return datetime.now(TURF_TZ)


def is_future_slot(booking_date: date_cls, slot: SlotTemplate) -> bool:
    """A slot is bookable only while its start is still in the future."""
    start, _ = slot_datetimes(booking_date, slot)
    return start > now_turf()


def is_completed(booking_date: date_cls, slot: SlotTemplate) -> bool:
    """A slot is 'completed' once its end time has passed."""
    _, end = slot_datetimes(booking_date, slot)
    return end <= now_turf()


def booking_lead_time_minutes(booking_date: date_cls, slot: SlotTemplate, created_at: datetime) -> int:
    start, _ = slot_datetimes(booking_date, slot)
    delta: timedelta = start - created_at
    return int(delta.total_seconds() // 60)
