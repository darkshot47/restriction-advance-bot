"""Round 3 acceptance tests.

Covers the nine requested items end to end, with Telegram and MongoDB replaced
by the in-memory fakes from ``conftest``:

1. Private-channel access message + [Buy Premium][Earn Points] row
2. Daily-limit explanation + the same dual button row
3. Feedback link rejection (mentions stay allowed)
4. /addpremium public-only vs full tier selection
5. Payment review: approve / fake / ban (owner only)
6. Channel dump via /setchat with admin verification, auto-cleanup and the
   FloodWait / rate-limit guard
7. Every admin command in /admins and in the inline panel
8. Unicode small-caps font engine
9. Profile (name/username) sync so renames show up everywhere
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config
import main
import ui
from conftest import (FakeChat, FakeMessage, FakeUser, make_member, make_query, sc)
from pyrogram.enums import ChatMemberStatus


# --------------------------------------------------------------------------- #
# 8. Unicode small-caps font engine
# --------------------------------------------------------------------------- #

def test_small_caps_letter_mapping_is_exact():
    expected = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
    assert ui.smallcaps("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == expected
    assert ui.smallcaps("abcdefghijklmnopqrstuvwxyz") == expected
    assert ui.SMALL_CAPS_MAP["S"] == "s"
    assert ui.SMALL_CAPS_MAP["X"] == "x"
    assert ui.SMALL_CAPS_MAP["I"] == "ɪ"


def test_small_caps_keeps_numbers_and_punctuation():
    assert ui.smallcaps("Free 3/day • 00:00 UTC → 50%") == "ғʀᴇᴇ 3/ᴅᴀʏ • 00:00 ᴜᴛᴄ → 50%"
    assert ui.smallcaps("₹249 · 365 days") == "₹249 · 365 ᴅᴀʏs"


def test_small_caps_protects_urls_mentions_commands_and_markup():
    sample = (
        "Open /premium or @XyrDeveloper — https://t.me/TestRestrictBot?start=42 "
        "and t.me/mychannel/15 · <a href=\"tg://user?id=7\">x</a> · `code`"
    )
    converted = ui.smallcaps(sample)
    assert "/premium" in converted
    assert "@XyrDeveloper" in converted
    assert "https://t.me/TestRestrictBot?start=42" in converted
    assert "t.me/mychannel/15" in converted
    assert '<a href="tg://user?id=7">' in converted
    assert "`code`" in converted
    assert "ᴏᴘᴇɴ" in converted


def test_small_caps_protects_html_entities():
    converted = ui.smallcaps("&lt;Dan &amp; Dave&gt; &#39;ok&#39;")
    for entity in ("&lt;", "&amp;", "&gt;", "&#39;"):
        assert entity in converted
    assert "ᴅᴀɴ" in converted  # the words themselves may still be styled


def test_small_caps_is_idempotent_and_reversible():
    once = ui.smallcaps("Daily Free Limit Reached")
    assert ui.smallcaps(once) == once
    assert ui.plain_caps(once) == "daily free limit reached"


def test_small_caps_can_be_disabled(monkeypatch):
    monkeypatch.setenv("SMALL_CAPS", "off")
    assert ui.smallcaps("Hello") == "Hello"
    monkeypatch.setenv("SMALL_CAPS", "auto")
    assert ui.smallcaps("Hello") == "ʜᴇʟʟᴏ"


def test_button_labels_are_small_caps_but_callback_data_is_not():
    markup = ui.premium_upsell_keyboard()
    buy, earn = markup.inline_keyboard[0]
    assert buy.text == sc("💎 Buy Premium")
    assert earn.text == sc("🎁 Earn Points")
    assert [buy.callback_data, earn.callback_data] == ["cmd_premium", "cmd_refer"]


@pytest.mark.asyncio
async def test_every_rendered_screen_uses_the_font_engine(db):
    message = FakeMessage(text="/help")
    await main.help_handler(None, message)
    assert sc("HELP MENU") in message.shown_text
    # commands inside the copy survive untouched
    assert "/setcaption" in message.shown_text

    start = FakeMessage(text="/start")
    await main.start_handler(None, start)
    assert sc("Restricted Content Saver Bot") in start.shown_text


def test_admin_help_and_panel_text_are_converted():
    text = main.admin_help_text()
    assert ui.plain_caps(text) != text          # letters were converted
    assert "/addpremium" in text                # commands untouched


# --------------------------------------------------------------------------- #
# 1. Private channel access message + dual buttons
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_private_link_single_message_and_buttons(db, monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    message = FakeMessage(text="https://t.me/c/12345/10")

    await main.text_handler(None, message)

    fetch.assert_not_called()
    assert sc("Private Channel Access (Premium Only)") in message.shown_text
    assert sc("Private channel and restricted group extraction is available exclusively "
              "for Premium users.") in message.shown_text
    assert sc("Upgrade to Premium or refer friends to earn points!") in message.shown_text
    row = message.shown_markup.inline_keyboard[0]
    assert [b.callback_data for b in row] == ["cmd_premium", "cmd_refer"]
    assert [b.text for b in row] == [sc("💎 Buy Premium"), sc("🎁 Earn Points")]


@pytest.mark.asyncio
async def test_private_links_inside_bulk_and_range_get_the_same_screen(db, monkeypatch):
    """Requirement 1: single, bulk and range inputs all show the premium pitch."""
    monkeypatch.setattr(main, "fetch_and_send", AsyncMock(return_value=True))

    for text in ("https://t.me/c/12345/10\nhttps://t.me/publicname/11",
                 "https://t.me/c/12345/10-12"):
        message = FakeMessage(text=text)
        await main.text_handler(None, message)
        assert sc("Private Channel Access (Premium Only)") in message.shown_text, text
        assert sc("available exclusively for Premium users") in message.shown_text
        row = message.shown_markup.inline_keyboard[0]
        assert [b.callback_data for b in row] == ["cmd_premium", "cmd_refer"]


@pytest.mark.asyncio
async def test_fetch_and_send_private_gate_shows_upsell(db):
    status = FakeMessage()
    message = FakeMessage(user=FakeUser(1001))
    result = await main.fetch_and_send(message, status, main.bot, -1001234, 5)
    assert result is False
    assert sc("Private Channel Access (Premium Only)") in status.shown_text
    assert status.shown_markup.inline_keyboard[0][0].callback_data == "cmd_premium"


# --------------------------------------------------------------------------- #
# 2. Daily limit explanation + dual buttons
# --------------------------------------------------------------------------- #

def test_daily_limit_text_explains_the_reason():
    text = ui.daily_limit_text()   # screen copy; the sender applies the font
    assert f"Free accounts get **{main.FREE_DAILY_LIMIT} public extractions per day**" in text
    assert "00:00 UTC" in text
    assert "Buy Premium" in text and "Earn Points" in text


@pytest.mark.asyncio
async def test_daily_limit_reached_single_link(db):
    await db.add_user(1001, "Tester")
    db.users[1001]["daily_downloads"] = main.FREE_DAILY_LIMIT

    message = FakeMessage(text="https://t.me/publicname/10")
    await main.text_handler(None, message)

    assert sc("Daily Free Limit Reached") in message.shown_text
    assert sc(f"**{main.FREE_DAILY_LIMIT} public extractions per day**") in message.shown_text
    assert sc(f"(**{main.FREE_DAILY_LIMIT}/{main.FREE_DAILY_LIMIT}** used today)") in message.shown_text
    assert sc("resets every day at **00:00 UTC**") in message.shown_text
    row = message.shown_markup.inline_keyboard[0]
    assert [b.callback_data for b in row] == ["cmd_premium", "cmd_refer"]


@pytest.mark.asyncio
async def test_daily_limit_reached_bulk_and_range(db):
    await db.add_user(1001, "Tester")
    db.users[1001]["daily_downloads"] = 2  # only one slot left

    bulk = FakeMessage(text="https://t.me/publicname/1\nhttps://t.me/publicname/2")
    await main.text_handler(None, bulk)
    assert sc("Daily Free Limit Reached") in bulk.shown_text
    assert bulk.button("cmd_premium") and bulk.button("cmd_refer")

    db.users[1001]["daily_downloads"] = 2
    range_msg = FakeMessage(text="https://t.me/publicname/1-20")
    await main.text_handler(None, range_msg)
    assert sc("Daily Free Limit Reached") in range_msg.shown_text
    assert range_msg.button("cmd_premium") and range_msg.button("cmd_refer")


@pytest.mark.asyncio
async def test_daily_limit_from_atomic_reservation_shows_reason_and_buttons(db, monkeypatch):
    await db.add_user(1001, "Tester")
    db.users[1001]["daily_downloads"] = main.FREE_DAILY_LIMIT
    monkeypatch.setattr(main, "_fetch_and_send", AsyncMock(return_value=True))

    status = FakeMessage()
    result = await main.fetch_and_send(FakeMessage(), status, main.bot, "publicname", 1)

    assert result is False
    assert sc("Daily Free Limit Reached") in status.shown_text
    assert sc("00:00 UTC") in status.shown_text
    assert status.shown_markup.inline_keyboard[0][0].callback_data == "cmd_premium"


def test_daily_quota_uses_the_utc_clock():
    """The message promises a 00:00 UTC reset, so the counters must use UTC."""
    import database
    assert database.utcnow().tzinfo is None
    assert abs((database.utcnow() - database.datetime.utcnow()).total_seconds()) < 5
    assert (database.utcnow() - database.datetime.now()).total_seconds() < 86400


# --------------------------------------------------------------------------- #
# 3. Feedback security: no links, mentions allowed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("linked", [
    "Check https://example.com/item",
    "go to http://spam.example",
    "t.me/spamchannel/1 is cool",
    "telegram.me/spamchannel",
    "www.spam.example",
    "join here spam.example.com",
    "tg://user?id=1",
    "write to me@example.com",
])
def test_feedback_link_detection(linked):
    assert main.feedback_has_link(linked) is True


@pytest.mark.parametrize("plain", [
    "Everything works great!",
    "Thanks @XyrDeveloper and @wantedkar99bot 😊",
    "@channel please add 4K support",
    "Yes @user, the bot saved 3 files at 10:30",
    "join the channel @mychannel",
])
def test_feedback_mentions_are_plain_text(plain):
    assert main.feedback_has_link(plain) is False


@pytest.mark.asyncio
async def test_feedback_with_link_is_rejected_and_warned(db, fake_bot):
    user = FakeUser(3003, "Linker", "linker")
    message = FakeMessage(text="/feedback please check https://spam.example now", user=user)

    await main.feedback_handler(None, message)

    assert db.feedback == []
    assert not fake_bot.sent
    assert message.shown_text == sc(config.FEEDBACK_LINK_WARNING)


@pytest.mark.asyncio
async def test_feedback_with_mentions_reaches_the_owner(db, fake_bot):
    user = FakeUser(3004, "Mentioner", "mentioner")
    message = FakeMessage(text="/feedback shoutout to @XyrDeveloper 👏", user=user)

    await main.feedback_handler(None, message)

    assert db.feedback == [(3004, "shoutout to @XyrDeveloper 👏")]
    assert fake_bot.sent and fake_bot.sent[-1]["chat_id"] == main.OWNER_ID
    # the mention survives verbatim in the copy the owner receives
    assert "@XyrDeveloper" in fake_bot.sent[-1]["text"]


# --------------------------------------------------------------------------- #
# 4. /addpremium two-tier selection
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_addpremium_asks_for_the_tier_first(db, monkeypatch):
    grant = AsyncMock()
    monkeypatch.setattr(main, "add_premium", grant)
    await db.add_user(2002, "Recipient")

    message = FakeMessage(text="/addpremium 2002 45", user=FakeUser(main.OWNER_ID))
    await main.addpremium_handler(None, message)

    assert sc("Select Premium Access Tier for User `2002` (45 days):") in message.shown_text
    assert message.button("premium_tier:public").text == sc("🌐 Public Only")
    assert message.button("premium_tier:full").text == sc("🔓 Full (Public + Private)")
    assert message.button("cancel_action").callback_data == "cancel_action"
    grant.assert_not_called()
    assert main.premium_tier_pending[main.OWNER_ID] == {"user_id": 2002, "days": 45}


@pytest.mark.asyncio
async def test_addpremium_public_only_tier(db, press, fake_bot):
    await db.add_user(2002, "Recipient")
    message = FakeMessage(text="/addpremium 2002 30", user=FakeUser(main.OWNER_ID))
    await main.addpremium_handler(None, message)

    await press(message, "premium_tier:public")

    user = db.users[2002]
    assert user["is_premium"] is True
    assert user["premium_source"] == config.PREMIUM_SOURCE_PUBLIC
    assert not await main.private_access(2002)          # private links stay blocked
    assert sc("Public Only") in message.shown_text
    notification = [m for m in fake_bot.sent if m["chat_id"] == 2002][-1]["text"]
    assert sc("PREMIUM ACTIVATED") in notification
    assert sc("Private channels are **not** included") in notification
    assert not main.premium_tier_pending


@pytest.mark.asyncio
async def test_addpremium_full_tier(db, press, fake_bot):
    await db.add_user(2002, "Recipient")
    message = FakeMessage(text="/addpremium 2002 90", user=FakeUser(main.OWNER_ID))
    await main.addpremium_handler(None, message)

    await press(message, "premium_tier:full")

    assert db.users[2002]["premium_source"] == "manual"
    assert await main.private_access(2002)              # private extraction unlocked
    assert sc("Full (Public + Private)") in message.shown_text
    notification = [m for m in fake_bot.sent if m["chat_id"] == 2002][-1]["text"]
    assert "private links are now enabled" in ui.plain_caps(notification)


@pytest.mark.asyncio
async def test_addpremium_selection_is_owner_only(db, press, fake_bot):
    await db.add_user(2002, "Recipient")
    owner_msg = FakeMessage(text="/addpremium 2002 30", user=FakeUser(main.OWNER_ID))
    await main.addpremium_handler(None, owner_msg)

    intruder = make_query(FakeMessage(user=FakeUser(5005)), "premium_tier:full", FakeUser(5005))
    await main.callback_handler(None, intruder)

    assert not db.users[2002]["is_premium"]
    assert intruder.answer.calls[-1]["show_alert"] is True


@pytest.mark.asyncio
async def test_addpremium_cancel_clears_the_selection(db, press):
    await db.add_user(2002, "Recipient")
    message = FakeMessage(text="/addpremium 2002 30", user=FakeUser(main.OWNER_ID))
    await main.addpremium_handler(None, message)

    await press(message, "cancel_action")

    assert not main.premium_tier_pending
    assert not db.users[2002]["is_premium"]


# --------------------------------------------------------------------------- #
# 5. Owner payment review: approve / fake / ban
# --------------------------------------------------------------------------- #

async def submit_proof(db, uid=1001, plan="month"):
    main.payment_pending[uid] = {"plan": plan, "token": "tok"}
    main.pending_action[uid] = "payment_proof"
    message = FakeMessage(user=FakeUser(uid))
    message.photo = SimpleNamespace(file_id="screenshot-file-id")
    await main.photo_handler(None, message)
    return message


@pytest.mark.asyncio
async def test_payment_proof_carries_the_three_review_buttons(db, fake_bot):
    await submit_proof(db)

    owner_photo = [m for m in fake_bot.sent if m["chat_id"] == main.OWNER_ID][-1]
    rows = owner_photo["reply_markup"].inline_keyboard
    assert [b.callback_data for b in rows[0]] == ["payok:1001:month", "payfake:1001"]
    assert [b.callback_data for b in rows[1]] == ["payban:1001"]
    assert rows[0][0].text == sc("✅ Approve")
    assert rows[0][1].text == sc("⚠️ Fake")
    assert rows[1][0].text == sc("🚫 Ban User")
    assert db.payments[0]["status"] == "pending_review"


@pytest.mark.asyncio
async def test_payment_review_is_owner_only(db, fake_bot):
    await submit_proof(db)
    review_msg = FakeMessage(user=FakeUser(main.OWNER_ID))
    review_msg.caption = "💳 PAYMENT REVIEW"

    query = make_query(review_msg, "payok:1001:month", FakeUser(4242))
    await main.callback_handler(None, query)

    assert not db.users.get(1001, {}).get("is_premium")
    assert query.answer.calls[-1]["show_alert"] is True
    assert db.payments[0]["status"] == "pending_review"


@pytest.mark.asyncio
async def test_payment_approve_activates_plan(db, fake_bot):
    await submit_proof(db, plan="quarter")
    review_msg = FakeMessage(user=FakeUser(main.OWNER_ID))
    review_msg.caption = "💳 PAYMENT REVIEW"

    query = make_query(review_msg, "payok:1001:quarter")
    await main.callback_handler(None, query)

    assert db.users[1001]["is_premium"] is True
    assert db.payments[0]["status"] == "approved"
    assert db.payments[0]["reviewed_by"] == main.OWNER_ID
    assert sc("✅ Approved by Owner") in review_msg.last_caption
    notification = [m for m in fake_bot.sent if m["chat_id"] == 1001][-1]["text"]
    assert "🎉 payment approved! your premium has been activated." in ui.plain_caps(notification)


@pytest.mark.asyncio
async def test_payment_fake_rejects_without_activating(db, fake_bot):
    await submit_proof(db)
    review_msg = FakeMessage(user=FakeUser(main.OWNER_ID))
    review_msg.caption = "💳 PAYMENT REVIEW"

    query = make_query(review_msg, "payfake:1001")
    await main.callback_handler(None, query)

    assert not db.users.get(1001, {}).get("is_premium")
    assert db.payments[0]["status"] == "rejected"
    assert sc("marked as fake/invalid") in review_msg.last_caption
    notification = [m for m in fake_bot.sent if m["chat_id"] == 1001][-1]["text"]
    assert "❌ payment rejected! your payment screenshot was marked as fake/invalid." \
        in ui.plain_caps(notification)


@pytest.mark.asyncio
async def test_payment_ban_bans_the_user(db, fake_bot):
    await submit_proof(db)
    review_msg = FakeMessage(user=FakeUser(main.OWNER_ID))
    review_msg.caption = "💳 PAYMENT REVIEW"

    query = make_query(review_msg, "payban:1001")
    await main.callback_handler(None, query)

    assert db.users[1001]["is_banned"] is True
    assert db.payments[0]["status"] == "banned"
    assert sc("Banned") in review_msg.last_caption
    notification = [m for m in fake_bot.sent if m["chat_id"] == 1001][-1]["text"]
    assert "submitting fraudulent payment proof" in ui.plain_caps(notification)


@pytest.mark.asyncio
async def test_payment_approve_falls_back_to_the_stored_plan(db, fake_bot):
    """Older proofs have no plan inside the callback data."""
    await submit_proof(db, plan="year")
    review_msg = FakeMessage(user=FakeUser(main.OWNER_ID))

    query = make_query(review_msg, "payok:1001")
    await main.callback_handler(None, query)

    assert db.users[1001]["is_premium"] is True
    assert db.payments[0]["status"] == "approved"


# --------------------------------------------------------------------------- #
# 6. Channel dump (/setchat) + anti-ban guard
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_setchat_asks_for_a_channel(db):
    message = FakeMessage(text="/setchat", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    assert main.pending_action[1001] == "setchat"
    assert sc("CHANNEL DUMP SETUP") in message.shown_text
    assert message.button("cancel_action")


@pytest.mark.asyncio
async def test_setchat_resolves_link_and_offers_admin_check(db, fake_bot):
    message = FakeMessage(text="/setchat", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    reply = FakeMessage(text="https://t.me/mychannel", user=FakeUser(1001))
    await main.text_handler(None, reply)

    pending = main.setchat_pending[1001]
    assert pending["chat_id"] == fake_bot.channel_id
    assert pending["step"] == "await_check"
    assert sc("Tap **🔍 Check Admin Status**") in reply.shown_text
    assert reply.button("setchat:check").text == sc("🔍 Check Admin Status")
    assert 1001 not in main.pending_action


@pytest.mark.asyncio
async def test_setchat_accepts_a_username_and_a_numeric_id(db, fake_bot, press):
    for ref in ("@mychannel", "-100777"):
        main.setchat_pending.pop(1001, None)
        message = FakeMessage(text=f"/setchat {ref}", user=FakeUser(1001))
        await main.setchat_handler(None, message)
        assert main.setchat_pending[1001]["chat_id"] == fake_bot.channel_id, ref
        assert sc("Set Channel") in message.shown_text or message.shown_text
        assert message.button("setchat:check")


@pytest.mark.asyncio
async def test_setchat_rejects_an_unresolvable_reference(db, fake_bot):
    fake_bot.get_chat = AsyncMock(side_effect=ValueError("no such chat"))
    message = FakeMessage(text="/setchat not..a..ref", user=FakeUser(1001))

    await main.setchat_handler(None, message)

    assert sc("Could not resolve") in message.shown_text
    assert 1001 not in main.setchat_pending


@pytest.mark.asyncio
async def test_delchat_requires_admin_to_target_another_user(db, fake_bot):
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")
    intruder = FakeMessage(text="/delchat 1001", user=FakeUser(4242))
    await main.delchat_handler(None, intruder)
    assert await db.get_user_chat(1001) is not None

    admin = FakeMessage(text="/delchat 1001", user=FakeUser(main.OWNER_ID))
    await main.delchat_handler(None, admin)
    assert await db.get_user_chat(1001) is None


@pytest.mark.asyncio
async def test_setchat_admin_check_fails_with_instructions(db, fake_bot, press):
    fake_bot.members[999] = make_member(ChatMemberStatus.MEMBER)
    message = FakeMessage(text="/setchat t.me/mychannel", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    await press(message, "setchat:check")

    assert sc("Admin check failed") in message.shown_text
    assert sc("Post Messages") in message.shown_text
    assert message.button("setchat:check")          # retry button available
    assert main.setchat_pending[1001]["step"] == "await_check"


@pytest.mark.asyncio
async def test_setchat_admin_check_requires_post_permission(db, fake_bot, press):
    fake_bot.members[999] = make_member(ChatMemberStatus.ADMINISTRATOR, can_post_messages=False)
    message = FakeMessage(text="/setchat t.me/mychannel", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    await press(message, "setchat:check")

    assert sc("Admin check failed") in message.shown_text


@pytest.mark.asyncio
async def test_setchat_full_flow_verifies_a_sample_message(db, fake_bot, press):
    fake_bot.members[999] = make_member(ChatMemberStatus.ADMINISTRATOR, can_post_messages=True)
    fake_bot.messages[15] = SimpleNamespace(empty=False, id=15)

    message = FakeMessage(text="/setchat t.me/mychannel", user=FakeUser(1001))
    await main.setchat_handler(None, message)

    await press(message, "setchat:check")
    assert sc("Admin verified") in message.shown_text
    assert sc("send a sample message") in message.shown_text
    assert sc("just the message number") in message.shown_text
    assert main.setchat_pending[1001]["step"] == "await_sample"

    sample = FakeMessage(text="https://t.me/mychannel/15", user=FakeUser(1001))
    await main.text_handler(None, sample)

    assert sc("Channel dump enabled") in sample.shown_text
    assert 1001 not in main.setchat_pending
    assert await db.get_user_chat(1001) == {
        "chat_id": fake_bot.channel_id, "title": "mychannel", "username": "mychannel",
    }


@pytest.mark.asyncio
async def test_setchat_sample_must_be_readable(db, fake_bot, press):
    fake_bot.members[999] = make_member(ChatMemberStatus.ADMINISTRATOR, can_post_messages=True)
    message = FakeMessage(text="/setchat t.me/mychannel", user=FakeUser(1001))
    await main.setchat_handler(None, message)
    await press(message, "setchat:check")

    fake_bot.messages.clear()
    sample = FakeMessage(text="https://t.me/mychannel/99", user=FakeUser(1001))
    await main.text_handler(None, sample)

    assert sc("Verification failed") in sample.shown_text
    assert 1001 in main.setchat_pending
    assert await db.get_user_chat(1001) is None


@pytest.mark.asyncio
async def test_setchat_from_inside_the_channel(db, fake_bot):
    message = FakeMessage(text="/setchat", user=FakeUser(1001))
    message.chat = FakeChat(fake_bot.channel_id, chat_type="channel", title="My Channel")

    await main.setchat_handler(None, message)

    assert main.setchat_pending[1001]["chat_id"] == fake_bot.channel_id
    assert main.setchat_pending[1001]["title"] == "My Channel"


@pytest.mark.asyncio
async def test_delchat_unlinks_the_channel(db, fake_bot):
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")

    message = FakeMessage(text="/delchat", user=FakeUser(1001))
    await main.delchat_handler(None, message)

    assert await db.get_user_chat(1001) is None
    assert sc("Channel link removed") in message.shown_text


@pytest.mark.asyncio
async def test_channel_post_extracts_into_the_channel(db, fake_bot, monkeypatch):
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")
    captured = {}

    async def fake_fetch(requester, status, client, chat_target, msg_id, **kwargs):
        captured["user"] = requester.from_user.id
        captured["chat"] = requester.chat.id
        captured["target"] = chat_target
        captured["kwargs"] = kwargs
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)

    post = FakeMessage(text="https://t.me/publicchannel/10", user=FakeUser(1001))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    await main.channel_dump_handler(None, post)

    assert captured["user"] == 1001
    assert captured["chat"] == fake_bot.channel_id      # posts back into the channel
    assert captured["target"] == "publicchannel"
    assert captured["kwargs"]["enforce_fsub"] is False
    assert captured["kwargs"]["cleanup_errors"] is True


@pytest.mark.asyncio
async def test_channel_post_from_unregistered_channel_is_ignored(db, fake_bot, monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)

    post = FakeMessage(text="https://t.me/publicchannel/10", user=FakeUser(1001))
    post.chat = FakeChat(-100999, chat_type="channel")
    await main.channel_dump_handler(None, post)

    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_channel_dump_ignores_the_bots_own_posts(db, fake_bot, monkeypatch):
    """The bot must never answer its own status messages (update loop)."""
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)

    outgoing = FakeMessage(text="https://t.me/publicchannel/10", user=FakeUser(1001))
    outgoing.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    outgoing.outgoing = True
    await main.channel_dump_handler(None, outgoing)

    self_post = FakeMessage(text="https://t.me/publicchannel/10",
                            user=SimpleNamespace(id=999, is_self=True, first_name="Bot"))
    self_post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    await main.channel_dump_handler(None, self_post)

    fetch.assert_not_called()
    assert main.is_own_message(outgoing) is True
    assert main.is_own_message(self_post) is True
    assert main.is_own_message(FakeMessage()) is False


@pytest.mark.asyncio
async def test_channel_extraction_applies_the_private_channel_rules(db, fake_bot, monkeypatch):
    """Private links inside a dump channel show the same premium pitch."""
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")
    fetch = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    monkeypatch.setattr(main, "try_native_copy", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "get_user_client", AsyncMock(return_value=None))

    post = FakeMessage(text="https://t.me/c/12345/10", user=FakeUser(1001))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    await main.extract_channel_links(post, db.users[1001])

    fetch.assert_not_called()
    assert sc("Private Channel Access (Premium Only)") in post.shown_text
    assert post.button("cmd_premium")


@pytest.mark.asyncio
async def test_channel_message_not_found_is_cleaned_up_in_five_seconds(db, fake_bot, monkeypatch):
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")
    cleaned = []
    monkeypatch.setattr(main, "schedule_cleanup", lambda message, delay=None: cleaned.append(
        (message, main.CHANNEL_CLEANUP_SECONDS if delay is None else delay)))
    monkeypatch.setattr(main, "try_native_copy", AsyncMock(return_value=False))
    monkeypatch.setattr(fake_bot, "get_messages", AsyncMock(return_value=None), raising=False)

    post = FakeMessage(text="https://t.me/publicchannel/404", user=FakeUser(1001))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    await main.channel_dump_handler(None, post)

    assert main.CHANNEL_CLEANUP_SECONDS == 5
    assert cleaned, "the not-found notice was not scheduled for deletion"
    status_message, delay = cleaned[-1]
    assert delay == 5
    assert sc("Message not found") in status_message.shown_text


@pytest.mark.asyncio
async def test_cleanup_message_later_deletes_after_the_delay():
    message = FakeMessage()
    slept = []

    async def sleeper(seconds):
        slept.append(seconds)

    await main.cleanup_message_later(message, 5, sleeper=sleeper)

    assert slept == [5]
    assert message.deleted is True


@pytest.mark.asyncio
async def test_channel_requests_are_rate_limited():
    slept = []

    async def sleeper(seconds):
        slept.append(seconds)

    main.channel_last_request.clear()
    async with main.channel_rate_limit(-1001, sleeper=sleeper):
        pass
    assert slept == []                       # first request never waits

    async with main.channel_rate_limit(-1001, sleeper=sleeper):
        pass
    assert slept and 0 < slept[-1] <= main.CHANNEL_EXTRACT_COOLDOWN


@pytest.mark.asyncio
async def test_channel_extraction_sleeps_between_requests(db, fake_bot, monkeypatch):
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")
    slept = []

    async def sleeper(seconds):
        slept.append(seconds)

    monkeypatch.setattr(main, "fetch_and_send", AsyncMock(return_value=True))
    post = FakeMessage(text="https://t.me/publicchannel/1\nhttps://t.me/publicchannel/2",
                       user=FakeUser(1001))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    await main.extract_channel_links(post, db.users[1001], sleeper=sleeper)

    assert slept.count(main.CHANNEL_EXTRACT_COOLDOWN) >= 2


@pytest.mark.asyncio
async def test_floodwait_guard_pauses_then_retries():
    calls = {"n": 0}
    slept = []

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise main.FloodWait(value=7)
        return "ok"

    async def sleeper(seconds):
        slept.append(seconds)

    assert await main.floodwait_guard(flaky, sleeper=sleeper) == "ok"
    assert calls["n"] == 2
    assert slept == [8]                      # value + 1 safety second
    assert main.floodwait_seconds(main.FloodWait(value=0)) == 1


@pytest.mark.asyncio
async def test_fetch_and_send_survives_floodwait_without_crashing(db, monkeypatch):
    slept = []

    async def sleeper(seconds):
        slept.append(seconds)

    monkeypatch.setattr(main, "floodwait_sleep", sleeper)
    attempts = {"n": 0}
    status = FakeMessage()

    async def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise main.FloodWait(value=3)
        return True

    monkeypatch.setattr(main, "_fetch_and_send", flaky)

    result = await main.fetch_and_send(FakeMessage(), status, main.bot, "publicname", 1)

    assert result is True
    assert attempts["n"] == 2
    assert slept == [4]                      # paused once, then continued
    assert db.users[1001]["daily_downloads"] == 1


@pytest.mark.asyncio
async def test_channel_floodwait_is_absorbed(db, fake_bot, monkeypatch):
    await db.set_user_chat(1001, fake_bot.channel_id, "My Channel")

    async def flaky(*args, **kwargs):
        raise main.FloodWait(value=2)

    monkeypatch.setattr(main, "fetch_and_send", flaky)

    post = FakeMessage(text="https://t.me/publicchannel/1", user=FakeUser(1001))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    # No exception may escape the handler.
    await main.channel_dump_handler(None, post)


# --------------------------------------------------------------------------- #
# 7. Every admin command in /admins and the inline panel
# --------------------------------------------------------------------------- #

def test_admin_panel_lists_every_command():
    listed = main.admin_help_text()
    for command in main.ADMIN_PANEL_COMMANDS:
        assert f"/{command}" in listed
    for required in ("loggedusers", "setchat", "delchat", "userinfo", "addpremium",
                     "payments", "addqr", "removeqr", "feedbacks", "export"):
        assert required in main.ADMIN_PANEL_COMMANDS


def test_every_panel_command_has_an_inline_handler():
    missing = [c for c in main.ADMIN_PANEL_COMMANDS if c not in main.ADMIN_INLINE_HANDLERS]
    assert missing == []
    assert set(main.ADMIN_PANEL_COMMANDS) <= set(main.COMMAND_NAMES)


def test_every_admin_page_button_is_dispatchable():
    seen = set()
    for page, (_, commands) in enumerate(main.ADMIN_PAGES):
        rows = main.admin_panel_keyboard(page).inline_keyboard
        assert len(rows) <= 7
        for row in rows:
            assert len(row) <= 2
            for btn in row:
                data = btn.callback_data
                seen.add(data)
                assert len(ui.smallcaps(btn.text)) <= 28
                if data.startswith("admin:") and not data.startswith("admin_page:"):
                    assert data.split(":", 1)[1] in main.ADMIN_INLINE_HANDLERS
                else:
                    assert data.startswith("admin_page:") or data == "home"
    for command in main.ADMIN_PANEL_COMMANDS:
        assert f"admin:{command}" in seen
    assert len(main.ADMIN_PAGES) >= 5


@pytest.mark.asyncio
async def test_admin_pages_are_reachable_and_permission_checked(db, press, fake_bot):
    for page in range(len(main.ADMIN_PAGES)):
        message = FakeMessage(user=FakeUser(main.OWNER_ID))
        await press(message, f"admin_page:{page}")
        assert sc("ADMIN PANEL") in message.shown_text
        assert f"{page + 1}/{len(main.ADMIN_PAGES)}" in message.shown_text

    outsider = make_query(FakeMessage(user=FakeUser(4242)), "admin_page:0", FakeUser(4242))
    await main.callback_handler(None, outsider)
    assert outsider.answer.calls[-1]["show_alert"] is True
    assert sc("Admin access only") in outsider.answer.calls[-1]["text"]


@pytest.mark.asyncio
async def test_admins_command_shows_list_and_panel(db):
    message = FakeMessage(text="/admins", user=FakeUser(main.OWNER_ID))
    await main.admin_handler(None, message)

    assert sc("ADMIN COMMANDS") in message.shown_text
    assert "/loggedusers" in message.shown_text
    assert "/setchat" in message.shown_text
    assert "admin:stats" in message.callback_data()
    assert "admin_page:1" in message.callback_data()


@pytest.mark.asyncio
async def test_setchat_is_reachable_from_the_inline_panel(db, press):
    message = FakeMessage(user=FakeUser(main.OWNER_ID))
    await press(message, "admin:setchat")

    assert main.admin_pending[main.OWNER_ID] == "setchat"
    assert sc("Send the details") in message.shown_text


@pytest.mark.asyncio
async def test_loggedusers_is_reachable_from_the_inline_panel(db, press):
    await db.add_user(2001, "LoggedIn")
    await db.save_session(2001, "session-token", "+919999999999")
    message = FakeMessage(user=FakeUser(main.OWNER_ID))

    await press(message, "admin:loggedusers")

    assert sc("LOGGED-IN USERS (1)") in message.shown_text


# --------------------------------------------------------------------------- #
# 8b. Single source of truth — a renamed price/limit/contact updates the copy
# --------------------------------------------------------------------------- #

def test_plan_prices_come_from_config(monkeypatch):
    import config
    monkeypatch.setattr(config, "PREMIUM_PLANS", {
        "week": {"title": "1 week", "price": 49, "days": 7},
    }, raising=False)
    text = ui.plans_text()
    assert "1 week" in text and "₹49" in text
    assert "₹99" not in text and "3 months" not in text

    monkeypatch.setattr(config, "PAYMENT_CONTACT", "NewOwner", raising=False)
    assert "@NewOwner" in ui.plans_text()
    assert "@NewOwner" in ui.payment_text({"title": "1 week", "price": 49, "days": 7})


def test_refer_copy_follows_config(monkeypatch):
    import config
    monkeypatch.setattr(config, "REFER_POINTS", 25, raising=False)
    monkeypatch.setattr(config, "REDEEM_POINTS", 250, raising=False)
    text = ui.refer_text("https://t.me/x?start=1", 3)
    assert "25" in text and "**Points: 75 / 250**" in text
    assert "https://t.me/x?start=1" in text


def test_limits_match_between_main_and_config():
    import config
    assert main.FREE_DAILY_LIMIT == config.FREE_DAILY_LIMIT
    assert ui.daily_limit_text().find(str(config.FREE_DAILY_LIMIT)) != -1
    assert config.DAILY_RESET_LABEL == "00:00 UTC"


def test_premium_tier_names_come_from_config():
    import config
    assert config.PURCHASE_PREMIUM_SOURCE == config.PREMIUM_SOURCE_MANUAL
    assert {config.PREMIUM_SOURCE_MANUAL, config.PREMIUM_SOURCE_PUBLIC,
            config.PREMIUM_SOURCE_REDEEM} == {"manual", "public", "redeem"}


# --------------------------------------------------------------------------- #
# 9. Renames propagate (name/username checked on every interaction)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_rename_is_synced_on_every_interaction(db):
    user = FakeUser(777, "Old Name", "oldhandle")
    await main.start_handler(None, FakeMessage(text="/start", user=user))
    assert db.users[777]["name"] == "Old Name"

    user.first_name = "New Name"
    user.username = "newhandle"
    await main.start_handler(None, FakeMessage(text="/start", user=user))

    assert db.users[777]["name"] == "New Name"
    assert db.users[777]["username"] == "newhandle"
    assert db.profile_syncs, "the profile was never refreshed"


@pytest.mark.asyncio
async def test_rename_appears_in_lists_and_userinfo(db):
    await db.add_user(888, "First Name", "first")
    user = FakeUser(888, "Brand New Name", "brandnew")
    await main.text_handler(None, FakeMessage(text="hello", user=user))
    assert db.users[888]["name"] == "Brand New Name"

    listing = FakeMessage(text="/users", user=FakeUser(main.OWNER_ID))
    await main.users_handler(None, listing)
    assert sc("Brand New Name") in listing.shown_text
    assert sc("First Name") not in listing.shown_text

    info = FakeMessage(text="/userinfo 888", user=FakeUser(main.OWNER_ID))
    await main.userinfo_handler(None, info)
    assert sc("Brand New Name") in info.shown_text
    assert "@brandnew" in info.shown_text


@pytest.mark.asyncio
async def test_addpremium_screens_show_the_current_stored_name(db):
    await db.add_user(2002, "Old Name")
    first = FakeMessage(text="/addpremium 2002 30", user=FakeUser(main.OWNER_ID))
    await main.addpremium_handler(None, first)
    assert sc("Old Name") in first.shown_text

    await db.sync_user_profile(2002, name="New Name")
    second = FakeMessage(text="/addpremium 2002 30", user=FakeUser(main.OWNER_ID))
    await main.addpremium_handler(None, second)
    assert sc("New Name") in second.shown_text
    assert sc("Old Name") not in second.shown_text


@pytest.mark.asyncio
async def test_ban_confirmation_reads_the_fresh_name(db):
    await db.add_user(3002, "Before Ban")
    await db.sync_user_profile(3002, name="After Rename")

    message = FakeMessage(text="/ban 3002", user=FakeUser(main.OWNER_ID))
    await main.ban_handler(None, message)

    assert sc("After Rename") in message.shown_text
    assert db.users[3002]["is_banned"] is True


@pytest.mark.asyncio
async def test_rename_is_synced_from_button_presses(db):
    await db.add_user(999, "Before", "before")
    query = make_query(FakeMessage(user=FakeUser(999, "After", "after")), "cmd_stats")
    await main.callback_handler(None, query)

    assert db.users[999]["name"] == "After"
    assert db.users[999]["username"] == "after"


@pytest.mark.asyncio
async def test_sync_user_profile_only_writes_on_change(db):
    await db.add_user(1001, "Same")
    assert await db.sync_user_profile(1001, name="Same") is False
    assert await db.sync_user_profile(1001, name="Changed") is True
    assert await db.sync_user_profile(424242, name="Ghost") is False


def test_profile_sync_is_wired_into_the_handlers():
    """Guard against a refactor dropping the refresh calls."""
    import inspect
    for func in (main.start_handler, main.show_start, main.text_handler,
                 main.callback_handler, main.setchat_handler):
        assert "refresh_profile" in inspect.getsource(func), func.__name__


# --------------------------------------------------------------------------- #
# Internationalisation of the copy stays intact (no lost emoji/labels)
# --------------------------------------------------------------------------- #

def test_ui_copy_is_converted_once_and_keeps_links(db):
    text = ui.start_text("Tester", False)
    converted = ui.smallcaps(text)
    assert converted == ui.smallcaps(converted)
    assert "ᴛᴇsᴛᴇʀ" in converted
    assert "🔐" in converted


def _plain_letters_left(text: str) -> list[str]:
    """ASCII letters that survived outside protected regions (links, /cmds).

    ``S`` and ``X`` are excluded: their small-caps glyphs *are* the ASCII
    letters "s" and "x", so those are legitimate font-engine output.
    """
    import re
    stripped = ui.PROTECTED_RE.sub("", text)
    return [ch for ch in re.findall(r"[A-Za-z]", stripped) if ch not in "SsXx"]


@pytest.mark.asyncio
async def test_no_screen_leaks_plain_ascii_letters(db, fake_bot, press):
    """Requirement 8: every visible heading/copy is rendered in the font."""
    screens: list[str] = []

    for command in ("/start", "/help", "/settings", "/premium", "/refer", "/stats",
                    "/myinfo", "/language", "/feedback", "/mystats", "/status"):
        message = FakeMessage(text=command, user=FakeUser(1001, "Tester", "tester"))
        handler = main.text_handler
        await handler(None, message)
        screens.append(message.shown_text or "")

    # Screens that live behind callbacks / admin gating.
    for data in ("cmd_premium", "premium_plans", "cmd_refer", "cmd_help", "cmd_language"):
        query = make_query(FakeMessage(user=FakeUser(1001, "Tester", "tester")), data)
        await main.callback_handler(None, query)
        screens.append(query.message.shown_text or "")

    admin = FakeMessage(user=FakeUser(main.OWNER_ID))
    query = make_query(admin, "admin:adminhelp")
    await main.callback_handler(None, query)
    screens.append(query.message.shown_text or "")

    setchat = FakeMessage(text="/setchat", user=FakeUser(1001))
    await main.setchat_handler(None, setchat)
    screens.append(setchat.shown_text or "")

    # ui.* helpers return plain copy; the sender applies the font. Render them
    # the same way main.say() does.
    for raw in (ui.private_access_text(), ui.daily_limit_text(),
                ui.setchat_admin_failed_text("no_post_rights"), ui.feedback_link_warning(),
                ui.premium_tier_text(2002, 30), ui.premium_activated_user_text(30, "public"),
                ui.payment_approved_user_text("Monthly", 30), ui.payment_rejected_user_text(),
                ui.payment_banned_user_text(), ui.setchat_prompt_text(),
                ui.setchat_admin_hint_text("My Channel"), ui.setchat_done_text("My Channel", -100777),
                ui.setchat_usage_text(), ui.channel_not_found_text(),
                main.admin_help_text()):
        screens.append(ui.smallcaps(raw))

    for screen in screens:
        leftovers = _plain_letters_left(screen)
        # ``/commands`` and URLs are protection regions, so any leftover letter
        # means a heading or button label skipped the font engine.
        assert not leftovers, f"plain ASCII letters in: {leftovers!r} <- {screen[:120]!r}"


def test_smallcaps_protection_keeps_commands_and_links_verbatim():
    text = ui.smallcaps("/admins lists every command — see t.me/mychannel/15 and @Xyr")
    assert "/admins" in text
    assert "t.me/mychannel/15" in text
    assert "@Xyr" in text


def test_no_button_is_a_dead_end(db):
    """Every callback_data a keyboard can emit is routed by callback_handler."""
    prefix_routes = ("dl:", "payok:", "payfake:", "payban:", "admin_page:", "admin:",
                     "buy:", "paid:", "users_page:", "loggedusers:",
                     "fsub:", "fsub_page:", "fsub_list_page:", "fsub_del:", "fsub_rename:",
                     "fsub_del_all")
    direct_routes = {"home", "close", "cancel_login", "cancel_action", "redeem_points"}
    keyboards = [
        ui.start_keyboard(), ui.start_keyboard(show_admin=True), ui.settings_keyboard(True, False),
        ui.language_keyboard(), ui.login_keyboard(), ui.logout_keyboard(), ui.feedback_keyboard(),
        ui.stats_keyboard(), ui.premium_keyboard(False), ui.premium_keyboard(True),
        ui.refer_keyboard("https://t.me/x?start=1"), ui.help_keyboard(),
        ui.fsub_keyboard([{"chat_id": -1001, "title": "Chan", "username": "chan",
                          "invite_link": None, "button_text": "✅ Join Chan",
                          "kind": "channel", "auto_approve": False, "order": 0}]),
        ui.download_controls("job"),         ui.plans_keyboard(), ui.payment_keyboard("tok"), ui.admin_back_keyboard(),
        main.admin_panel_keyboard(0), ui.admin_back_keyboard(),
        ui.premium_upsell_keyboard(), ui.private_access_keyboard(), ui.daily_limit_keyboard(),
        ui.setchat_check_keyboard(), ui.premium_tier_keyboard(),
        ui.payment_review_keyboard(7, "month"), ui.payment_review_keyboard(7),
        ui.admin_back_keyboard(),
    ]
    seen = set()
    for markup in keyboards:
        rows = markup.inline_keyboard
        assert len(rows) <= 7, rows
        for row in rows:
            assert 1 <= len(row) <= 2, row
            for btn in row:
                if btn.callback_data:
                    seen.add(btn.callback_data)
    assert seen, "no callbacks collected"
    for data in seen:
        if data in direct_routes or data.startswith(prefix_routes):
            continue
        assert data in main.CALLBACK_ACTIONS, f"dead button: {data}"


def test_smallcaps_never_touches_callback_data():
    for markup in (ui.start_keyboard(), ui.premium_upsell_keyboard(),
                   ui.payment_review_keyboard(7, "month"), ui.premium_tier_keyboard(),
                   ui.setchat_check_keyboard(), ui.admin_back_keyboard()):
        for row in markup.inline_keyboard:
            for button in row:
                data = button.callback_data or ""
                assert data == ui.plain_caps(data) or data.isascii()
                assert data.isascii()
