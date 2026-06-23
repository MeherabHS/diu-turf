"""Phase 2 backend regression — Booking Engine + WebSocket.

Targets:
  - GET /api/health, /api/bookings/date/{date}, /api/bookings/me
  - POST /api/bookings  (rules, duplicates, race, analytics fields)
  - DELETE /api/bookings/{id}  (owner / admin / completed / cancelled / 404)
  - WebSocket /api/ws/bookings  (auth, hello, broadcast on create/cancel)
  - MongoDB indexes (uniq_active_slot_per_date, uniq_active_booking_per_user_per_date)
  - analytics_events appended on every create/cancel
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import uuid
from datetime import date as date_cls, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import requests
import websockets
import websockets.exceptions as ws_exc

# ---------------------------------------------------------------------------
# Helpers / module-scope state
# ---------------------------------------------------------------------------
TURF_TZ = ZoneInfo("Asia/Dhaka")
SLOT_TIMES = {"A": (16, 17), "B": (17, 18), "C": (18, 19)}


def _tomorrow_dhaka() -> str:
    return (datetime.now(TURF_TZ) + timedelta(days=1)).date().isoformat()


def _yesterday_dhaka() -> str:
    return (datetime.now(TURF_TZ) - timedelta(days=1)).date().isoformat()


def _future_date(offset_days: int) -> str:
    return (datetime.now(TURF_TZ) + timedelta(days=offset_days)).date().isoformat()


@pytest.fixture(scope="module")
def ws_base_url() -> str:
    # WS via internal port — preview ingress upgrades are not guaranteed.
    return "ws://localhost:8001"


@pytest.fixture(scope="module")
def http_base_url(base_url) -> str:
    return base_url


# ---------------------------------------------------------------------------
# User factory — directly inserts TEST_ users into Mongo and mints JWTs.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def user_factory(mongo_db, mint_jwt):
    created: list[str] = []

    def _make(*, profile_completed: bool = True, role: str = "student",
              department: str = "CSE", batch: str = "60") -> dict:
        uid = f"u_test_{uuid.uuid4().hex[:10]}"
        email = f"TEST_{uid}@diu.edu.bd"
        now = datetime.now(timezone.utc)
        doc = {
            "user_id": uid,
            "email": email,
            "name": f"Test {uid[-4:]}",
            "picture": None,
            "role": role,
            "student_id": f"TEST{uid[-6:]}" if profile_completed else None,
            "department": department if profile_completed else None,
            "batch": batch if profile_completed else None,
            "profile_completed": profile_completed,
            "created_at": now,
            "last_login": now,
            "updated_at": now,
        }
        mongo_db.users.insert_one(doc)
        created.append(uid)
        token = mint_jwt(uid, email, role)
        return {"user_id": uid, "email": email, "token": token, "headers": {
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"}, "doc": doc}

    yield _make

    # Teardown — purge created TEST_ users and any bookings they made.
    if created:
        mongo_db.bookings.delete_many({"user_id": {"$in": created}})
        mongo_db.users.delete_many({"user_id": {"$in": created}})


@pytest.fixture(scope="module", autouse=True)
def _clean_bookings(mongo_db):
    """Clear bookings + analytics for the next 30 days at module start."""
    cutoff_dates = [_future_date(i) for i in range(-2, 30)]
    mongo_db.bookings.delete_many({"booking_date": {"$in": cutoff_dates}})
    yield
    mongo_db.bookings.delete_many({"booking_date": {"$in": cutoff_dates}})


# ---------------------------------------------------------------------------
# Health + Auth gating
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_200(self, api_client, http_base_url):
        r = api_client.get(f"{http_base_url}/api/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


class TestAuthGating:
    def test_date_overview_requires_auth(self, api_client, http_base_url):
        r = api_client.get(f"{http_base_url}/api/bookings/date/{_tomorrow_dhaka()}")
        assert r.status_code == 401

    def test_create_requires_auth(self, api_client, http_base_url):
        r = api_client.post(
            f"{http_base_url}/api/bookings",
            json={"booking_date": _tomorrow_dhaka(), "slot_id": "A"},
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Date overview — 3 fixed slots
# ---------------------------------------------------------------------------
class TestDateOverview:
    def test_empty_date_returns_three_available_slots(self, api_client, http_base_url, user_factory):
        u = user_factory()
        d = _future_date(7)
        r = api_client.get(f"{http_base_url}/api/bookings/date/{d}", headers=u["headers"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["booking_date"] == d
        slots = body["slots"]
        assert [s["slot_id"] for s in slots] == ["A", "B", "C"]
        for s in slots:
            assert s["status"] == "available"
            assert s["booking"] is None
            assert s["is_mine"] is False

    def test_past_date_slots_marked_completed(self, api_client, http_base_url, user_factory):
        u = user_factory()
        r = api_client.get(f"{http_base_url}/api/bookings/date/{_yesterday_dhaka()}", headers=u["headers"])
        assert r.status_code == 200
        for s in r.json()["slots"]:
            assert s["status"] == "completed"

    def test_invalid_date_format_400(self, api_client, http_base_url, user_factory):
        u = user_factory()
        r = api_client.get(f"{http_base_url}/api/bookings/date/not-a-date", headers=u["headers"])
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Create booking — happy + validation paths
# ---------------------------------------------------------------------------
class TestCreateBooking:
    def test_create_success_and_analytics(self, api_client, http_base_url, user_factory, mongo_db):
        u = user_factory(department="CSE", batch="60")
        d = _future_date(2)
        r = api_client.post(
            f"{http_base_url}/api/bookings",
            json={"booking_date": d, "slot_id": "A"},
            headers=u["headers"],
        )
        assert r.status_code == 201, r.text
        b = r.json()
        assert b["booking_date"] == d
        assert b["slot_id"] == "A"
        assert b["status"] == "booked"
        assert b["start_time"] == "16:00" and b["end_time"] == "17:00"
        # analytics fields
        assert isinstance(b["day_of_week"], int) and 0 <= b["day_of_week"] <= 6
        assert b["hour"] == 16
        assert isinstance(b["booking_lead_time"], int) and b["booking_lead_time"] > 0
        assert b["department"] == "CSE"
        assert b["batch"] == "60"
        assert b["user_id"] == u["user_id"]

        # analytics_events row exists
        ev = mongo_db.analytics_events.find_one(
            {"event_type": "booking.created", "user_id": u["user_id"], "booking_date": d, "slot_id": "A"}
        )
        assert ev is not None

    def test_past_date_returns_400(self, api_client, http_base_url, user_factory):
        u = user_factory()
        r = api_client.post(
            f"{http_base_url}/api/bookings",
            json={"booking_date": _yesterday_dhaka(), "slot_id": "A"},
            headers=u["headers"],
        )
        assert r.status_code == 400
        assert "past" in r.json()["detail"].lower()

    def test_invalid_date_format_400(self, api_client, http_base_url, user_factory):
        u = user_factory()
        r = api_client.post(
            f"{http_base_url}/api/bookings",
            json={"booking_date": "06-14-2026", "slot_id": "A"},
            headers=u["headers"],
        )
        assert r.status_code == 400

    def test_unknown_slot_id_422(self, api_client, http_base_url, user_factory):
        u = user_factory()
        r = api_client.post(
            f"{http_base_url}/api/bookings",
            json={"booking_date": _future_date(3), "slot_id": "Z"},
            headers=u["headers"],
        )
        # Pydantic Literal["A","B","C"] rejects -> 422
        assert r.status_code in (400, 422)

    def test_profile_incomplete_400(self, api_client, http_base_url, user_factory):
        u = user_factory(profile_completed=False)
        r = api_client.post(
            f"{http_base_url}/api/bookings",
            json={"booking_date": _future_date(4), "slot_id": "A"},
            headers=u["headers"],
        )
        assert r.status_code == 400
        assert "profile" in r.json()["detail"].lower()

    def test_double_booking_same_slot_409(self, api_client, http_base_url, user_factory):
        u1, u2 = user_factory(), user_factory()
        d = _future_date(5)
        r1 = api_client.post(f"{http_base_url}/api/bookings",
                             json={"booking_date": d, "slot_id": "B"}, headers=u1["headers"])
        assert r1.status_code == 201
        r2 = api_client.post(f"{http_base_url}/api/bookings",
                             json={"booking_date": d, "slot_id": "B"}, headers=u2["headers"])
        assert r2.status_code == 409
        assert "already booked" in r2.json()["detail"].lower()

    def test_same_user_two_slots_same_day_409(self, api_client, http_base_url, user_factory):
        u = user_factory()
        d = _future_date(6)
        r1 = api_client.post(f"{http_base_url}/api/bookings",
                             json={"booking_date": d, "slot_id": "A"}, headers=u["headers"])
        assert r1.status_code == 201
        r2 = api_client.post(f"{http_base_url}/api/bookings",
                             json={"booking_date": d, "slot_id": "C"}, headers=u["headers"])
        assert r2.status_code == 409
        assert "active booking" in r2.json()["detail"].lower()

    def test_race_two_parallel_creates_one_wins(self, api_client, http_base_url, user_factory):
        u1, u2 = user_factory(), user_factory()
        d = _future_date(8)

        def _post(headers):
            return requests.post(
                f"{http_base_url}/api/bookings",
                json={"booking_date": d, "slot_id": "C"},
                headers=headers, timeout=15,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(_post, u1["headers"])
            f2 = ex.submit(_post, u2["headers"])
            r1, r2 = f1.result(), f2.result()

        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [201, 409], f"Expected [201,409], got {statuses}: {r1.text} | {r2.text}"


# ---------------------------------------------------------------------------
# /me listing
# ---------------------------------------------------------------------------
class TestMyBookings:
    def test_me_lists_sorted_desc(self, api_client, http_base_url, user_factory):
        u = user_factory()
        d1, d2 = _future_date(10), _future_date(11)
        for d, slot in [(d1, "A"), (d2, "B")]:
            r = api_client.post(f"{http_base_url}/api/bookings",
                                json={"booking_date": d, "slot_id": slot}, headers=u["headers"])
            assert r.status_code == 201, r.text

        r = api_client.get(f"{http_base_url}/api/bookings/me", headers=u["headers"])
        assert r.status_code == 200
        bookings = r.json()
        assert len(bookings) == 2
        # sorted by booking_date DESC
        assert bookings[0]["booking_date"] >= bookings[1]["booking_date"]

    def test_me_derives_completed_for_past(self, api_client, http_base_url, user_factory, mongo_db):
        u = user_factory()
        # Insert a directly-past booking with status='booked' to test derived 'completed'
        past_date = _yesterday_dhaka()
        booking_id = f"bk_test_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)
        mongo_db.bookings.insert_one({
            "booking_id": booking_id,
            "user_id": u["user_id"],
            "student_name": u["doc"]["name"],
            "student_id": u["doc"]["student_id"],
            "email": u["email"],
            "booking_date": past_date,
            "slot_id": "A",
            "slot_label": "Slot A",
            "start_time": "16:00",
            "end_time": "17:00",
            "status": "booked",
            "created_at": now,
            "updated_at": now,
            "day_of_week": 0, "hour": 16, "booking_lead_time": -1,
            "department": "CSE", "batch": "60",
        })
        r = api_client.get(f"{http_base_url}/api/bookings/me", headers=u["headers"])
        assert r.status_code == 200
        found = [b for b in r.json() if b["booking_id"] == booking_id]
        assert found and found[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------
class TestCancelBooking:
    def test_owner_can_cancel_and_slot_rebookable(self, api_client, http_base_url, user_factory, mongo_db):
        u1, u2 = user_factory(), user_factory()
        d = _future_date(12)
        r = api_client.post(f"{http_base_url}/api/bookings",
                            json={"booking_date": d, "slot_id": "A"}, headers=u1["headers"])
        assert r.status_code == 201
        bid = r.json()["booking_id"]

        r = api_client.delete(f"{http_base_url}/api/bookings/{bid}", headers=u1["headers"])
        assert r.status_code == 200, r.text
        # status flipped
        doc = mongo_db.bookings.find_one({"booking_id": bid}, {"_id": 0})
        assert doc["status"] == "cancelled"

        # another user can now book the same slot
        r2 = api_client.post(f"{http_base_url}/api/bookings",
                             json={"booking_date": d, "slot_id": "A"}, headers=u2["headers"])
        assert r2.status_code == 201, r2.text

        # analytics row for cancellation appended
        ev = mongo_db.analytics_events.find_one({"event_type": "booking.cancelled",
                                                 "booking_date": d, "slot_id": "A",
                                                 "user_id": u1["user_id"]})
        assert ev is not None

    def test_non_owner_403(self, api_client, http_base_url, user_factory):
        u1, u2 = user_factory(), user_factory()
        d = _future_date(13)
        r = api_client.post(f"{http_base_url}/api/bookings",
                            json={"booking_date": d, "slot_id": "B"}, headers=u1["headers"])
        bid = r.json()["booking_id"]
        r2 = api_client.delete(f"{http_base_url}/api/bookings/{bid}", headers=u2["headers"])
        assert r2.status_code == 403

    def test_admin_can_cancel(self, api_client, http_base_url, user_factory, admin_headers):
        u = user_factory()
        d = _future_date(14)
        r = api_client.post(f"{http_base_url}/api/bookings",
                            json={"booking_date": d, "slot_id": "C"}, headers=u["headers"])
        bid = r.json()["booking_id"]
        r2 = api_client.delete(f"{http_base_url}/api/bookings/{bid}", headers=admin_headers)
        assert r2.status_code == 200

    def test_unknown_id_404(self, api_client, http_base_url, admin_headers):
        r = api_client.delete(f"{http_base_url}/api/bookings/bk_doesnotexist", headers=admin_headers)
        assert r.status_code == 404

    def test_already_cancelled_400(self, api_client, http_base_url, user_factory):
        u = user_factory()
        d = _future_date(15)
        r = api_client.post(f"{http_base_url}/api/bookings",
                            json={"booking_date": d, "slot_id": "A"}, headers=u["headers"])
        bid = r.json()["booking_id"]
        api_client.delete(f"{http_base_url}/api/bookings/{bid}", headers=u["headers"])
        r2 = api_client.delete(f"{http_base_url}/api/bookings/{bid}", headers=u["headers"])
        assert r2.status_code == 400

    def test_completed_booking_cannot_cancel(self, api_client, http_base_url, user_factory, mongo_db):
        u = user_factory()
        past_date = _future_date(-3)  # 3 days ago, avoid collision with other past-date inserts
        bid = f"bk_test_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)
        mongo_db.bookings.insert_one({
            "booking_id": bid, "user_id": u["user_id"],
            "student_name": u["doc"]["name"], "student_id": u["doc"]["student_id"],
            "email": u["email"], "booking_date": past_date, "slot_id": "A",
            "slot_label": "Slot A", "start_time": "16:00", "end_time": "17:00",
            "status": "booked", "created_at": now, "updated_at": now,
            "day_of_week": 0, "hour": 16, "booking_lead_time": -1,
            "department": "CSE", "batch": "60",
        })
        r = api_client.delete(f"{http_base_url}/api/bookings/{bid}", headers=u["headers"])
        assert r.status_code == 400
        assert "completed" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Mongo indexes
# ---------------------------------------------------------------------------
class TestIndexes:
    def test_bookings_partial_unique_indexes_present(self, mongo_db):
        idx = mongo_db.bookings.index_information()
        assert "uniq_active_slot_per_date" in idx
        assert "uniq_active_booking_per_user_per_date" in idx
        for name in ("uniq_active_slot_per_date", "uniq_active_booking_per_user_per_date"):
            spec = idx[name]
            assert spec.get("unique") is True, f"{name} must be unique"
            pfe = spec.get("partialFilterExpression") or {}
            assert pfe == {"status": "booked"}, f"{name} partialFilterExpression mismatch: {pfe}"


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
class TestWebSocket:
    @pytest.mark.asyncio
    async def test_ws_no_token_closes_1008(self, ws_base_url):
        # Acceptable rejection forms: pre-accept HTTP 403 (Starlette default when
        # close() is called before accept()) OR post-accept WS close 1008.
        with pytest.raises((ws_exc.WebSocketException, ws_exc.ConnectionClosed)) as exc:
            async with websockets.connect(f"{ws_base_url}/api/ws/bookings") as ws:
                await ws.recv()
        msg = str(exc.value)
        assert ("1008" in msg) or ("403" in msg) or getattr(exc.value, "code", None) == 1008, msg

    @pytest.mark.asyncio
    async def test_ws_invalid_token_closes_1008(self, ws_base_url):
        with pytest.raises((ws_exc.WebSocketException, ws_exc.ConnectionClosed)) as exc:
            async with websockets.connect(f"{ws_base_url}/api/ws/bookings?token=bogus.jwt.value") as ws:
                await ws.recv()
        msg = str(exc.value)
        assert ("1008" in msg) or ("403" in msg) or getattr(exc.value, "code", None) == 1008, msg

    @pytest.mark.asyncio
    async def test_ws_valid_token_hello_and_broadcast(self, ws_base_url, http_base_url, user_factory):
        u_listener = user_factory()
        u_actor = user_factory()
        url = f"{ws_base_url}/api/ws/bookings?token={u_listener['token']}"
        async with websockets.connect(url) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert hello["type"] == "hello"
            assert hello["user_id"] == u_listener["user_id"]

            # Trigger booking from another user
            d = _future_date(20)

            def _create():
                return requests.post(
                    f"{http_base_url}/api/bookings",
                    json={"booking_date": d, "slot_id": "A"},
                    headers=u_actor["headers"], timeout=10,
                )

            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(None, _create)
            assert r.status_code == 201, r.text
            bid = r.json()["booking_id"]

            # Listen for booking.created
            created = None
            for _ in range(5):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if msg.get("type") == "booking.created":
                    created = msg
                    break
            assert created is not None, "Did not receive booking.created"
            assert created["booking_date"] == d
            assert created["slot_id"] == "A"
            assert created["booking_id"] == bid

            # Cancel and listen for booking.cancelled
            def _cancel():
                return requests.delete(f"{http_base_url}/api/bookings/{bid}",
                                       headers=u_actor["headers"], timeout=10)

            r = await loop.run_in_executor(None, _cancel)
            assert r.status_code == 200

            cancelled = None
            for _ in range(5):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if msg.get("type") == "booking.cancelled":
                    cancelled = msg
                    break
            assert cancelled is not None, "Did not receive booking.cancelled"
            assert cancelled["booking_id"] == bid
