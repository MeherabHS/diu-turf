"""Tests for slot overlap validation and admin slot helpers."""
from __future__ import annotations

from datetime import time

import pytest

from services.turf_schedule import parse_hhmm, time_ranges_overlap


def test_parse_hhmm():
    assert parse_hhmm("19:00") == time(19, 0)
    assert parse_hhmm("16:30:00") == time(16, 30)


def test_time_ranges_overlap_touching_endpoints_do_not_overlap():
    assert not time_ranges_overlap(time(16, 0), time(17, 0), time(17, 0), time(18, 0))
    assert not time_ranges_overlap(time(17, 0), time(18, 0), time(16, 0), time(17, 0))


def test_time_ranges_overlap_partial_overlap():
    assert time_ranges_overlap(time(16, 0), time(17, 0), time(16, 30), time(17, 30))
    assert time_ranges_overlap(time(16, 30), time(17, 30), time(16, 0), time(17, 0))


def test_parse_hhmm_invalid():
    with pytest.raises(ValueError):
        parse_hhmm("25:00")
