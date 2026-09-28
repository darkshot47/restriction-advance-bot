"""Exercise production database functions with Mongo query semantics, not FakeDB."""
import asyncio
from datetime import datetime, timedelta

import pytest
from mongomock_motor import AsyncMongoMockClient

import database


@pytest.fixture
def store(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(database, "users_col", db.users)
    monkeypatch.setattr(database, "config_col", db.config)
    return db


@pytest.mark.asyncio
async def test_new_user_created_once_under_concurrent_starts(store):
    results = await asyncio.gather(*[database.add_user(10, "User") for _ in range(10)])
    assert results.count(True) == 1
    assert await store.users.count_documents({"user_id": 10}) == 1


@pytest.mark.asyncio
async def test_referrals_are_real_distinct_once_and_ten_points(store):
    await database.add_user(10, "Referrer")
    await database.add_user(20, "Invitee")
    assert not await database.award_referral(999, 20)
    assert not await database.award_referral(10, 10)
    results = await asyncio.gather(*[database.award_referral(10, 20) for _ in range(10)])
    assert results.count(True) == 1
    user = await database.get_user(10)
    assert user["points"] == 10 and user["referral_count"] == 1
    assert (await database.get_user(20))["referred_by"] == 10


@pytest.mark.asyncio
async def test_threshold_and_one_calendar_month(store):
    await database.add_user(10, "Referrer")
    for uid in range(20, 29):
        await database.add_user(uid, "Friend")
        await database.award_referral(10, uid)
    assert not await database.redeem_points(10)
    await database.add_user(29, "Last friend")
    await database.award_referral(10, 29)
    before = datetime.now()
    results = await asyncio.gather(*[database.redeem_points(10) for _ in range(5)])
    assert results.count(True) == 1
    user = await database.get_user(10)
    assert user["points"] == 0 and user["premium_source"] == "redeem"
    assert database.add_months(before, 1) - timedelta(milliseconds=1) <= user["premium_expiry"] <= database.add_months(datetime.now(), 1)


@pytest.mark.asyncio
async def test_redemption_extends_points_but_never_downgrades_manual(store):
    await database.add_user(10, "User")
    await store.users.update_one({"user_id": 10}, {"$set": {"points": 300}})
    assert await database.redeem_points(10)
    first = (await database.get_user(10))["premium_expiry"]
    assert await database.redeem_points(10)
    assert (await database.get_user(10))["premium_expiry"] == database.add_months(first, 1)
    await database.add_premium(10, 30)
    assert not await database.redeem_points(10)
    user = await database.get_user(10)
    assert user["points"] == 100 and user["premium_source"] == "manual"


def test_calendar_month_end_and_leap_year():
    assert database.add_months(datetime(2024, 8, 31), 30) == datetime(2027, 2, 28)
    assert database.add_months(datetime(2023, 8, 31), 6) == datetime(2024, 2, 29)


@pytest.mark.asyncio
async def test_atomic_daily_slots_and_next_day_reset(store):
    await database.add_user(10, "User")
    now = datetime(2026, 9, 28, 12)
    results = await asyncio.gather(*[database.reserve_daily(10, now=now) for _ in range(10)])
    assert results.count(True) == 3
    await database.refund_daily(10, now)
    assert await database.reserve_daily(10, now=now)
    assert not await database.reserve_daily(10, now=now)
    assert await database.reserve_daily(10, now=now + timedelta(days=1))
    # An old download failure cannot refund tomorrow's quota.
    await database.refund_daily(10, now)
    assert (await database.get_user(10))["daily_downloads"] == 1


@pytest.mark.asyncio
async def test_qr_and_payment_metadata_are_persisted(store):
    await database.set_qr("file")
    assert await database.get_qr() == "file"
    await database.delete_qr()
    assert await database.get_qr() is None
    note = {"plan": "year", "price": 700, "days": 365}
    await database.add_payment(10, "receipt", note)
    payments = await database.get_payments()
    assert payments[0]["note"] == note
    assert payments[0]["status"] == "pending_review"


@pytest.mark.asyncio
async def test_duplicate_payment_for_same_checkout_is_recorded_once(store):
    note = {"checkout": "order-123", "plan": "month", "price": 99}
    assert await database.add_payment(10, "receipt", note) is not None
    assert await database.add_payment(10, "receipt", note) is None
    assert len(await database.get_payments()) == 1


@pytest.mark.asyncio
async def test_expired_manual_premium_can_redeem_but_loses_private_source(store):
    await database.add_user(10, "User")
    await store.users.update_one({"user_id": 10}, {"$set": {
        "points": 100, "is_premium": True, "premium_source": "manual",
        "premium_expiry": datetime.now() - timedelta(days=1),
    }})
    assert await database.redeem_points(10)
    assert (await database.get_user(10))["premium_source"] == "redeem"


@pytest.mark.asyncio
async def test_expired_premium_is_not_active(store):
    await database.add_user(10, "User")
    await store.users.update_one({"user_id": 10}, {"$set": {
        "is_premium": True, "premium_source": "redeem",
        "premium_expiry": datetime.now() - timedelta(days=1),
    }})
    assert not await database.is_premium(10)
