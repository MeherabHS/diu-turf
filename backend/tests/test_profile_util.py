"""Profile completion rules."""
from services.profile_util import compute_profile_completed


def test_profile_complete_when_core_fields_present():
    assert compute_profile_completed({
        "name": "Test Student",
        "student_id": "252-35-166",
        "department": "SWE",
        "batch": "47",
    }) is True


def test_profile_incomplete_when_department_missing():
    assert compute_profile_completed({
        "name": "Test Student",
        "student_id": "252-35-166",
        "department": "",
        "batch": "47",
    }) is False
