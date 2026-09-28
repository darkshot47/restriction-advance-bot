"""Focused acceptance tests for the Round 2 tier and rewards behavior."""
import datetime as dt
import pytest

import main
from conftest import FakeMessage, FakeUser


@pytest.mark.asyncio
async def test_referral_awards_ten_points_only_once(db):
    await db.add_user(10, "Referrer")
    await db.add_user(20, "Invitee")
    assert await main.award_referral(10, 20, main.REFER_POINTS)
    assert not await main.award_referral(10, 20, main.REFER_POINTS)
    assert db.users[10]["points"] == 10
    assert db.users[10]["referral_count"] == 1


@pytest.mark.asyncio
async def test_no_self_referral(db):
    await db.add_user(10, "User")
    assert not await main.award_referral(10, 10, main.REFER_POINTS)
    assert db.users[10]["points"] == 0


@pytest.mark.asyncio
async def test_redeem_locked_below_threshold(db):
    await db.add_user(10, "User")
    db.users[10]["points"] = 99
    assert not await main.redeem_points(10, 100, 30)
    assert not db.users[10]["is_premium"]


@pytest.mark.asyncio
async def test_redeem_grants_thirty_day_redeem_premium(db):
    await db.add_user(10, "User")
    db.users[10]["points"] = 100
    before = dt.datetime.now()
    assert await main.redeem_points(10, 100, 30)
    user = db.users[10]
    assert user["points"] == 0
    assert user["premium_source"] == "redeem"
    assert before + dt.timedelta(days=29) < user["premium_expiry"] < before + dt.timedelta(days=31)


@pytest.mark.asyncio
async def test_free_referral_page_shows_points_and_private_warning(db):
    message = FakeMessage(user=FakeUser(42))
    await main.show_refer(message)
    assert "points" in message.shown_text.lower()
    assert "public channels only" in message.shown_text.lower()
    assert "https://t.me/" in message.shown_text
    assert any("🔒" in label for label in message.button_texts())


@pytest.mark.asyncio
async def test_add_qr_is_owner_prompt(db):
    message = FakeMessage(text="/addqr", user=FakeUser(main.OWNER_ID))
    await main.addqr_handler(None, message)
    assert main.pending_action[main.OWNER_ID] == "qr_upload"
    assert "photo" in message.shown_text.lower()
