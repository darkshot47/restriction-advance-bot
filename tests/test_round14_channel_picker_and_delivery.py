"""Round 14 — the channel chooser, the giveaway fan-out, the server-free copy
and honest /pin errors.

What this suite pins down:

1. **The channel picker.**  A channel is handed over with Telegram's *own*
   chat chooser: a reply-keyboard button carrying ``request_chat``, whose
   choice arrives back in ``message.chat_shared``.  Nothing is posted inside
   the channel, and the screens spell out — step by step — how to select one.
   Typing a link, an ``@username`` or a numeric id remains the fallback.
2. **The giveaway fan-out.**  Going live pins the message *and* DMs every user
   in a background task: FloodWait answers are slept out and retried, users who
   never started the bot are reported apart from real failures, and the owner
   receives a delivery report when the last message lands.
3. **A copy that never touches this server.**  Restricted content is copied by
   the user's own session straight into the bot's chat — never downloaded and
   re-uploaded — and the echo of that copy is swallowed exactly once so the
   bot never extracts it a second time.
4. **Honest /pin errors.**  Reply, link and bare id each land in their own
   chat, and every refusal (already pinned, no rights, no access, FloodWait,
   not found) has its own plain-English screen instead of one useless
   "pin failed".

In-memory fakes only: no Telegram, no MongoDB, no sockets.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config
import main
import ui
from conftest import (DEFAULT_USER_ID, FAKE_BOT_ID, FakeChat, FakeMessage,
                      FakeUser, make_member, make_query, sc)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatAdminRequired, ChannelPrivate, FloodWait
from pyrogram.types import ChatShared

ADMIN = ChatMemberStatus.ADMINISTRATOR
USER = DEFAULT_USER_ID
OWNER = main.OWNER_ID
CHANNEL = -100777            # the dump channel the fake bot resolves
SECRET = -1001234567890      # a private channel
BOT_ID = FAKE_BOT_ID
PICKED = -100999888777       # the channel the owner picks in the chooser


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def texts(message) -> str:
    """Every reply/edit the fake message received, joined (order preserved)."""
    chunks = [entry["text"] for entry in message.replies]
    chunks += [entry["text"] for entry in message.edits]
    return "\n".join(chunks)


def owner_message(text="", *, message_id=1):
    return FakeMessage(text=text, user=FakeUser(OWNER), message_id=message_id)


def private_message(text="x", user_id=USER):
    """A message in the private chat with the bot (chat id == the user's id)."""
    message = FakeMessage(text=text, user=FakeUser(user_id))
    message.chat = FakeChat(user_id)
    return message


def picker_buttons(markup):
    """The reply-keyboard buttons of a picker screen."""
    return [b for row in markup.keyboard for b in row]


def pick_message(chat_id=PICKED, *, button_id=None, title="Picked Channel",
                 username=None):
    """A message carrying the chat Telegram's chooser handed back."""
    if button_id is None:
        button_id = config.CHANNEL_PICKER_BUTTON_ID
    message = FakeMessage(text="", user=FakeUser(USER))
    message.chat_shared = ChatShared(
        button_id=button_id,
        chat=SimpleNamespace(id=chat_id, title=title, username=username,
                             type="channel"))
    return message


@pytest.fixture
def bot(fake_bot):
    """The fake bot with the memberships the picker and the pin need."""
    fake_bot.members[(PICKED, BOT_ID)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.members[(PICKED, USER)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.members[(CHANNEL, BOT_ID)] = make_member(
        ADMIN, can_post_messages=True, can_delete_messages=True)
    fake_bot.members[(CHANNEL, OWNER)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.chats[PICKED] = SimpleNamespace(id=PICKED, title="Picked Channel",
                                             username=None, type="channel")
    fake_bot.chats[CHANNEL] = SimpleNamespace(id=CHANNEL, title="Dump",
                                              username="dump", type="channel")
    return fake_bot


def seed_giveaway(db, **overrides):
    """One running giveaway, stored exactly the way the Database layer does."""
    gw = {
        "token": "abc12345", "status": "running", "prize_tier": "all",
        "prize_days": 30, "benefit": "Full VIP for a month",
        "ends_at": dt.datetime.utcnow() + dt.timedelta(days=1),
        "created_at": dt.datetime.utcnow(), "created_by": OWNER,
        "channel_id": CHANNEL, "message_id": 500, "participant_count": 0,
    }
    gw.update(overrides)
    db.giveaway = gw
    db.giveaway["_id"] = "active"
    return db.giveaway


# --------------------------------------------------------------------------- #
#  1. The channel chooser — Telegram's own picker, nothing posted inside
# --------------------------------------------------------------------------- #

def test_the_picker_button_opens_telegrams_own_chooser():
    """One reply-keyboard button, carrying ``request_chat``."""
    markup = ui.setchat_picker_keyboard()
    assert markup.__class__.__name__ == "ReplyKeyboardMarkup"
    buttons = picker_buttons(markup)
    assert len(buttons) == 1, "one chooser button, nothing to mis-tap"
    request = buttons[0].request_chat
    assert request is not None, "the button must open the chooser"
    assert request.button_id == config.CHANNEL_PICKER_BUTTON_ID
    assert request.chat_is_channel is True, "channels only, never a group chat"
    assert request.bot_is_member is True, "only chats the bot is already in"
    assert request.max_quantity == 1, "exactly one channel per pick"
    #: The rights are declared up front, so the chooser only lists chats where
    #: the bot may be promoted to a posting admin.
    assert request.bot_administrator_rights.can_post_messages is True
    assert request.user_administrator_rights.can_post_messages is True


def test_the_dump_picker_uses_its_own_channel_chooser_id():
    markup = ui.setdump_picker_keyboard()
    assert markup.__class__.__name__ == "ReplyKeyboardMarkup"
    button = markup.keyboard[0][0]
    request = button.request_chat
    assert request.button_id == config.DUMP_PICKER_BUTTON_ID
    assert request.button_id != config.CHANNEL_PICKER_BUTTON_ID
    assert request.bot_administrator_rights.can_post_messages is True
    assert request.bot_administrator_rights.can_delete_messages is True
    assert request.user_administrator_rights.can_post_messages is True


async def test_the_dump_picker_registers_only_after_admin_checks(db, bot):
    message = FakeMessage(text="", user=FakeUser(OWNER))
    message.chat_shared = ChatShared(
        button_id=config.DUMP_PICKER_BUTTON_ID,
        chat=SimpleNamespace(id=CHANNEL, title="Dump", username="dump", type="channel"),
    )
    main.pending_action[OWNER] = "setdump_share"

    await main.chat_shared_handler(None, message)

    entry = await db.get_dump_channel()
    assert entry and entry["chat_id"] == CHANNEL and entry["username"] == "dump"
    assert OWNER not in main.pending_action
    assert sc("Dump channel connected") in texts(message)


async def test_the_dump_picker_requires_the_bot_delete_right(db, bot):
    bot.members[(CHANNEL, BOT_ID)] = make_member(ADMIN, can_post_messages=True,
                                                  can_delete_messages=False)
    message = FakeMessage(text="", user=FakeUser(OWNER))
    message.chat_shared = ChatShared(
        button_id=config.DUMP_PICKER_BUTTON_ID,
        chat=SimpleNamespace(id=CHANNEL, title="Dump", username="dump", type="channel"),
    )
    main.pending_action[OWNER] = "setdump_share"

    await main.chat_shared_handler(None, message)

    assert await db.get_dump_channel() is None
    assert sc("Delete Messages") in texts(message)


def test_the_picker_button_respects_the_mobile_budget():
    markup = ui.setchat_picker_keyboard()
    for button in picker_buttons(markup):
        assert len(ui.plain_caps(button.text)) <= 28, button.text
    assert markup.resize_keyboard is True and markup.one_time_keyboard is True


def test_the_picker_screen_explains_how_to_select_a_channel():
    """Round 14 requirement: the owner never has to guess how the chooser works."""
    text = ui.setchat_picker_text()
    for phrase in ("Administrators", "Add Admin", "Post Messages",
                   "Pick my channel", "tap it once", "channel list opens"):
        assert phrase in text, phrase
    assert "Only channels where I am already an admin" in text


def test_the_picker_screen_names_the_typed_fallback():
    text = ui.setchat_picker_text()
    assert "message link" in text and "@username" in text
    assert "numeric" in text and "/cancel" in text


def test_no_picker_screen_carries_a_raw_link():
    """Standing constraint: links live only in url= buttons, never in body copy."""
    for text in (ui.setchat_picker_text(), ui.setchat_share_prompt_text(),
                 ui.setchat_share_link_in_channel_text(),
                 ui.setchat_deep_link_private_text()):
        assert "t.me/" not in text, text
        assert "https://" not in text, text


async def test_pressing_share_shows_the_picker_and_arms_the_fallback(db, bot, press):
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")

    assert main.pending_action[USER] == "setchat_share"
    assert sc("Pick your channel") in message.shown_text
    #: The chooser arrived as a **reply** keyboard, not an inline one.
    sent = message.replies[-1]["reply_markup"]
    assert sent.__class__.__name__ == "ReplyKeyboardMarkup"
    assert picker_buttons(sent)[0].request_chat is not None


def test_no_setchat_screen_offers_a_share_url():
    """Round 14 — the share sheet posted a link *into* the channel; it is gone."""
    for markup in (ui.setchat_prompt_keyboard(), ui.setchat_share_prompt_keyboard("x"),
                   ui.setchat_picker_keyboard()):
        rows = getattr(markup, "inline_keyboard", None)
        if rows is None:
            continue
        for button in (b for row in rows for b in row):
            assert not getattr(button, "url", None), button


async def test_a_pick_we_never_asked_for_is_ignored(db, bot):
    """A stale or forged chooser answer is not ours and is dropped."""
    message = FakeMessage(text="", user=FakeUser(USER))
    message.chat_shared = ChatShared(button_id=424242,
                                      chat=SimpleNamespace(id=PICKED, title="X",
                                                           type="channel"))
    assert main.shared_chat_of(message) is None
    await main.chat_shared_handler(None, message)
    assert message.replies == [] and await db.get_user_channels(USER) == []


async def test_the_picked_channel_is_registered(db, bot):
    await db.add_user(USER, "Tester")
    message = pick_message()
    main.pending_action[USER] = "setchat_share"

    await main.chat_shared_handler(None, message)

    stored = await db.get_user_channels(USER)
    assert [entry["chat_id"] for entry in stored] == [PICKED]
    assert [entry["title"] for entry in stored] == ["Picked Channel"]
    assert USER not in main.setchat_pending
    assert USER not in main.pending_action
    assert sc("Channel dump enabled") in texts(message)


async def test_the_picker_verifies_the_person_and_the_bot(db, bot):
    """Both checks run on a pick, exactly as they do on the link path."""
    await db.add_user(USER, "Tester")
    seen = []
    original = main.describe_requester_admin

    async def spy(chat_id, user_id):
        seen.append(("person", chat_id, user_id))
        return await original(chat_id, user_id)

    main.describe_requester_admin = spy
    main.pending_action[USER] = "setchat_share"
    try:
        await main.chat_shared_handler(None, pick_message())
    finally:
        main.describe_requester_admin = original
    assert seen == [("person", PICKED, USER)]
    assert [entry["chat_id"] for entry in await db.get_user_channels(USER)] == [PICKED]


async def test_a_pick_of_a_channel_you_do_not_administer_is_refused(db, bot):
    await db.add_user(USER, "Tester")
    bot.members[(PICKED, USER)] = make_member(ChatMemberStatus.MEMBER)
    main.pending_action[USER] = "setchat_share"
    message = pick_message()

    await main.chat_shared_handler(None, message)

    assert sc("Setup cancelled") in texts(message)
    assert sc("not an administrator") in texts(message)
    assert await db.get_user_channels(USER) == []
    assert USER not in main.setchat_pending


async def test_a_pick_without_posting_rights_keeps_the_wizard_alive(db, bot):
    await db.add_user(USER, "Tester")
    bot.members[(PICKED, BOT_ID)] = make_member(ADMIN, can_post_messages=False)
    main.pending_action[USER] = "setchat_share"
    message = pick_message()

    await main.chat_shared_handler(None, message)

    assert sc("Admin check failed") in texts(message)
    assert main.setchat_pending[USER]["step"] == "await_check"
    assert "setchat:check" in message.callback_data()
    assert await db.get_user_channels(USER) == []


async def test_a_pick_is_capped_at_the_channel_limit(db, bot):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    limit = max(1, int(config.MAX_USER_CHANNELS))
    for index in range(limit - 1):
        await db.add_user_channel(USER, -100500 - index, f"Spare {index}")
    main.pending_action[USER] = "setchat_share"
    message = pick_message()

    await main.chat_shared_handler(None, message)

    assert sc("Channel limit") in texts(message)
    assert PICKED not in {e["chat_id"] for e in await db.get_user_channels(USER)}


async def test_the_picker_completion_removes_the_reply_keyboard(db, bot):
    await db.add_user(USER, "Tester")
    main.pending_action[USER] = "setchat_share"
    message = pick_message()

    await main.chat_shared_handler(None, message)

    assert message.replies[-1]["reply_markup"].__class__.__name__ == "ReplyKeyboardRemove"


async def test_a_stray_pick_outside_the_wizard_is_guided(db, bot):
    """The chooser can be opened from anywhere, so a stray pick is explained."""
    await db.add_user(USER, "Tester")
    message = pick_message()

    await main.chat_shared_handler(None, message)

    assert sc("Pick your channel") in texts(message)
    assert await db.get_user_channels(USER) == []


async def test_typing_a_username_still_registers_the_channel(db, bot):
    """The link/username path is the fallback, and it still works."""
    await db.add_user(USER, "Tester")
    bot.chats[PICKED] = SimpleNamespace(id=PICKED, title="Picked Channel",
                                        username="picked", type="channel")
    main.pending_action[USER] = "setchat_share"

    message = FakeMessage(text="@picked", user=FakeUser(USER))
    await main.text_handler(None, message)

    #: The fake client resolves any handle to its own channel id; the point is
    #: that the typed reference went through the same verification and landed.
    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [bot.channel_id]
    assert sc("Channel dump enabled") in texts(message)
    assert USER not in main.pending_action


# --------------------------------------------------------------------------- #
#  2. The giveaway fan-out — pinned, then DMed to everyone, safely
# --------------------------------------------------------------------------- #

async def test_going_live_pins_the_message_and_starts_the_fan_out(db, bot):
    await db.add_user(OWNER, "Owner")
    await db.add_user(USER, "Tester")
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.chats[CHANNEL] = SimpleNamespace(id=CHANNEL, title="Dump", username="dump",
                                         type="channel", pinned_message=None)
    main.GIVEAWAY_WIZARD[OWNER] = {
        "tier": "all", "days": 30, "benefit": "Full VIP",
        "ends_at": dt.datetime.utcnow() + dt.timedelta(days=1), "step": "channel",
    }

    created = await main.create_giveaway_from_wizard(OWNER, main.GIVEAWAY_WIZARD[OWNER],
                                                     CHANNEL, "Dump")

    assert created is not None
    assert bot.pinned and bot.pinned[-1][0] == CHANNEL, "the message is pinned"
    assert main.GIVEAWAY_BROADCAST_TASK is not None, "the fan-out is running"
    task = main.GIVEAWAY_BROADCAST_TASK
    await asyncio.wait_for(task, timeout=5)

    #: the announcement reached the user, and never the owner as a recipient
    dmed = [sent["chat_id"] for sent in bot.sent]
    assert USER in dmed
    announcements = [s for s in bot.sent
                     if sc("A giveaway just started") in s["text"]]
    assert {s["chat_id"] for s in announcements} == {USER}, "the owner is skipped"
    assert any(sent["chat_id"] == USER
               and sc("A giveaway just started") in sent["text"]
               for sent in bot.sent)


async def test_the_fan_out_delivers_to_every_user_except_the_owner(db, bot):
    await db.add_user(OWNER, "Owner")
    for uid in (2001, 2002, 2003):
        await db.add_user(uid, f"User {uid}")
    seed_giveaway(db)

    report = await main.run_giveaway_broadcast(await db.get_active_giveaway())

    assert report["total"] == 3 and report["sent"] == 3
    assert report["pin_attempted"] == report["pin_succeeded"] == 3
    assert {sent["chat_id"] for sent in bot.sent} == {2001, 2002, 2003}


async def test_the_fan_out_is_paced_between_two_sends(db, bot, monkeypatch):
    """A burst of sends is what earns a FloodWait, so there is a real gap."""
    await db.add_user(2001, "A")
    await db.add_user(2002, "B")
    seed_giveaway(db)
    gaps = []

    async def fake_gap():
        gaps.append(config.GIVEAWAY_BROADCAST_DELAY)

    monkeypatch.setattr(main, "broadcast_gap", fake_gap)

    await main.run_giveaway_broadcast(await db.get_active_giveaway())

    assert gaps == [config.GIVEAWAY_BROADCAST_DELAY], "one gap between two sends"
    assert config.GIVEAWAY_BROADCAST_DELAY > 0


async def test_a_floodwait_is_slept_out_and_retried(db, bot, monkeypatch):
    await db.add_user(2001, "A")
    seed_giveaway(db)
    monkeypatch.setattr(main, "floodwait_sleep", AsyncMock())
    calls = {"n": 0}
    real_send = bot.send_message

    async def flaky(chat_id, text, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FloodWait(value=7)
        return await real_send(chat_id, text, **kwargs)

    bot.send_message = flaky

    report = await main.run_giveaway_broadcast(await db.get_active_giveaway())

    assert report["sent"] == 1, "the retry delivered it"
    assert report["pauses"] == 1
    assert report["wait_seconds"] == main.floodwait_seconds(FloodWait(value=7))
    main.floodwait_sleep.assert_awaited_once()


async def test_a_user_who_never_started_the_bot_is_reported_as_blocked(db, bot):
    from pyrogram.errors import PeerIdInvalid
    await db.add_user(2001, "A")
    await db.add_user(2002, "B")
    seed_giveaway(db)

    async def picky(chat_id, text, **kwargs):
        if chat_id == 2002:
            raise PeerIdInvalid()
        return await bot.__class__.send_message(bot, chat_id, text, **kwargs)

    bot.send_message = picky

    report = await main.run_giveaway_broadcast(await db.get_active_giveaway())

    assert report["sent"] == 1 and report["blocked"] == 1 and report["failed"] == 0


async def test_a_real_failure_is_counted_apart_from_a_blocked_user(db, bot):
    await db.add_user(2001, "A")
    await db.add_user(2002, "B")
    seed_giveaway(db)

    async def picky(chat_id, text, **kwargs):
        if chat_id == 2002:
            raise RuntimeError("telegram is on fire")
        return await bot.__class__.send_message(bot, chat_id, text, **kwargs)

    bot.send_message = picky

    report = await main.run_giveaway_broadcast(await db.get_active_giveaway())

    assert report["sent"] == 1 and report["failed"] == 1 and report["blocked"] == 0


async def test_the_owner_gets_a_delivery_report_when_the_fan_out_ends(db, bot):
    await db.add_user(OWNER, "Owner")
    await db.add_user(2001, "A")
    seed_giveaway(db)

    await main._giveaway_broadcast_task(await db.get_active_giveaway())

    reports = [s for s in bot.sent if s["chat_id"] == OWNER]
    assert reports, "the owner was told how it went"
    assert sc("delivery report") in reports[-1]["text"]
    assert sc("Delivered") in reports[-1]["text"]
    assert sc("Users on the list") in reports[-1]["text"]


async def test_the_report_names_every_outcome_it_counts(db, bot):
    report = {"total": 10, "sent": 6, "failed": 1, "blocked": 2, "paused": 1,
              "pauses": 3, "wait_seconds": 42.0}
    text = ui.giveaway_broadcast_report_text(report)
    assert "**10**" in text and "**6**" in text
    assert "Could not deliver" in text and "Never started the bot" in text
    assert "Skipped after rate limits" in text and "42s" in text


def test_the_announcement_copy_names_the_prize_and_the_draw():
    gw = {"prize_tier": "all", "prize_days": 30, "benefit": "Full VIP",
          "ends_at": dt.datetime(2026, 5, 1, 12, 0), "token": "abc12345"}
    text = ui.giveaway_broadcast_text(gw)
    assert "giveaway just started" in text
    assert "Prize" in text and "Draw" in text and "Full VIP" in text
    assert "Participate" in text
    assert "t.me/" not in text, "no raw link in body copy"


def test_the_announcement_keyboard_carries_the_participate_link():
    gw = {"token": "abc12345"}
    markup = ui.giveaway_broadcast_keyboard(main.giveaway_link("abc12345"))
    urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
    assert urls == [main.giveaway_link("abc12345")]


# --------------------------------------------------------------------------- #
#  3. A copy that never touches this server — and its echo, swallowed once
# --------------------------------------------------------------------------- #

def test_a_private_chat_copy_lands_in_the_bots_own_chat():
    from conftest import FakeUser as _FakeUser  # noqa: F401  (documentation)
    session = SimpleNamespace(name="user-session")
    main.user_clients[USER] = session
    target = main.resolve_delivery_target(private_message(), USER, session)
    assert target.reason == "bot_dm_native_copy"
    assert target.chat_id == BOT_ID and target.chat_id != USER
    assert target.copy_client is session


async def test_restricted_content_is_copied_and_never_downloaded(db, bot):
    await db.add_user(USER, "Tester")
    await db.add_premium(USER, 30, tier="all")
    source = SimpleNamespace(
        id=15, empty=False, chat=SimpleNamespace(id=SECRET),
        text=None, caption="Restricted caption",
        video=SimpleNamespace(file_id="v1", file_size=1024),
        document=None, audio=None, photo=None, voice=None, video_note=None,
        sticker=None, animation=None, media=True,
    )
    session = SimpleNamespace(
        name="user-session", is_user_client=True,
        me=SimpleNamespace(id=USER, is_bot=False),
        get_messages=AsyncMock(return_value=source),
        copy_message=AsyncMock(return_value=SimpleNamespace(
            id=5, chat=SimpleNamespace(id=BOT_ID),
            edit_caption=AsyncMock(), edit_text=AsyncMock())),
        download_media=AsyncMock(side_effect=AssertionError("never download")),
    )
    main.user_clients[USER] = session

    message = private_message("t.me/c/123456789/15")
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, session, SECRET, 15) is True

    assert session.copy_message.call_count == 1
    assert session.copy_message.call_args.kwargs["chat_id"] == BOT_ID
    session.download_media.assert_not_awaited()
    assert USER not in [c.kwargs["chat_id"] for c in session.copy_message.call_args_list]


def test_a_successful_copy_arms_the_echo_guard():
    main.ECHO_GUARD.clear()
    main.arm_echo_guard(USER, BOT_ID, 5)
    guard = main.ECHO_GUARD[USER]
    assert guard["chat_id"] == BOT_ID and guard["message_id"] == 5
    assert guard["expires"] > 0


def test_the_echo_of_a_copy_is_swallowed_exactly_once():
    main.ECHO_GUARD.clear()
    main.arm_echo_guard(USER, BOT_ID, 5)
    first = FakeMessage(text="t.me/c/123456789/15", user=FakeUser(USER))
    second = FakeMessage(text="t.me/c/123456789/16", user=FakeUser(USER))
    assert main.consume_echo_guard(USER, first) is True
    assert USER not in main.ECHO_GUARD, "the guard is single-use"
    assert main.consume_echo_guard(USER, second) is False


def test_an_expired_guard_does_not_swallow_anything():
    main.ECHO_GUARD.clear()
    main.arm_echo_guard(USER, BOT_ID, 5)
    main.ECHO_GUARD[USER]["expires"] = main.time.monotonic() - 1
    assert main.consume_echo_guard(USER, FakeMessage(user=FakeUser(USER))) is False
    assert USER not in main.ECHO_GUARD, "an expired guard is dropped, not honoured"


def test_a_user_without_a_guard_is_never_swallowed():
    main.ECHO_GUARD.clear()
    assert main.consume_echo_guard(USER, FakeMessage(user=FakeUser(USER))) is False


async def test_the_text_echo_is_swallowed_and_not_extracted_again(db, bot):
    await db.add_user(USER, "Tester")
    await db.add_premium(USER, 30, tier="all")
    main.arm_echo_guard(USER, BOT_ID, 5)

    echo = FakeMessage(text="https://t.me/c/123456789/15", user=FakeUser(USER))
    await main.text_handler(None, echo)

    assert echo.replies == [] and echo.edits == [], "the echo was swallowed"
    assert USER not in main.ECHO_GUARD


async def test_a_fresh_request_after_the_swallow_is_processed_normally(db, bot):
    await db.add_user(USER, "Tester")
    await db.add_premium(USER, 30, tier="all")
    main.arm_echo_guard(USER, BOT_ID, 5)
    await main.text_handler(None, FakeMessage(text="t.me/c/1/1", user=FakeUser(USER)))

    #: the very next message is an ordinary request again
    fresh = FakeMessage(text="not a link at all", user=FakeUser(USER))
    await main.text_handler(None, fresh)
    assert sc("Send valid Telegram link") in texts(fresh)


async def test_a_photo_echo_is_swallowed_too(db, bot):
    await db.add_user(USER, "Tester")
    main.arm_echo_guard(USER, BOT_ID, 5)
    photo = FakeMessage(text="", user=FakeUser(USER))
    photo.photo = SimpleNamespace(file_id="p1")

    await main.photo_handler(None, photo)

    assert photo.replies == [] and photo.edits == []
    assert USER not in main.ECHO_GUARD


def test_the_echo_window_is_long_enough_for_a_slow_connection():
    assert config.ECHO_SWALLOW_WINDOW_SECONDS >= 30


# --------------------------------------------------------------------------- #
#  4. /pin — three targets, and a distinct screen for every refusal
# --------------------------------------------------------------------------- #

async def test_a_reply_is_broadcast_and_pinned_in_the_configured_channel(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    message = FakeMessage(text="/pin", user=FakeUser(OWNER))
    message.chat = FakeChat(PICKED, "channel", "Picked Channel")
    message.reply_to_message = FakeMessage(message_id=31, user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert bot.pinned[-1][0] == CHANNEL
    assert bot.pinned[-1][1] != 31
    assert sc("BROADCAST COMPLETE") in texts(message)


async def test_a_link_pins_in_the_chat_the_link_names(db, bot):
    """A link is a destination: it must not be re-pointed at the dump channel."""
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.chats[PICKED] = SimpleNamespace(id=PICKED, title="Picked Channel",
                                        username="picked", type="channel")
    message = FakeMessage(text="/pin https://t.me/c/999888777/44",
                          user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert bot.pinned[-1] == (PICKED, 44), "the link's own chat, not the dump"


async def test_a_bare_id_pins_in_the_dump_channel(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    message = FakeMessage(text="/pin 77", user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert bot.pinned[-1] == (CHANNEL, 77)


async def test_a_bare_id_without_a_dump_channel_pins_in_this_chat(db, bot):
    message = FakeMessage(text="/pin 77", user=FakeUser(OWNER))
    message.chat = FakeChat(OWNER)

    await main.pin_handler(None, message)

    assert bot.pinned[-1] == (OWNER, 77)


async def test_an_already_pinned_message_is_reported_as_such(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.chats[CHANNEL] = SimpleNamespace(id=CHANNEL, title="Dump", username="dump",
                                         type="channel",
                                         pinned_message=SimpleNamespace(id=77))
    message = FakeMessage(text="/pin 77", user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert sc("Already pinned") in texts(message)
    assert bot.pinned == [], "nothing was pinned a second time"


async def test_missing_pin_rights_are_reported(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.pin_chat_message = AsyncMock(side_effect=ChatAdminRequired())
    message = FakeMessage(text="/pin 77", user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert sc("I cannot pin here") in texts(message)
    assert sc("Pin Messages") in texts(message)


async def test_no_access_to_the_chat_is_reported(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.get_chat = AsyncMock(side_effect=ChannelPrivate())
    message = FakeMessage(text="/pin 77", user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert sc("I cannot reach that chat") in texts(message)
    assert bot.pinned == []


async def test_a_floodwait_pause_is_reported(db, bot, monkeypatch):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    monkeypatch.setattr(main, "floodwait_sleep", AsyncMock())
    bot.get_chat = AsyncMock(side_effect=FloodWait(value=33))
    message = FakeMessage(text="/pin 77", user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert sc("Telegram asked me to slow down") in texts(message)
    assert bot.pinned == []


async def test_a_missing_message_is_reported(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.pin_chat_message = AsyncMock(side_effect=RuntimeError("MESSAGE_ID_INVALID"))
    message = FakeMessage(text="/pin 77", user=FakeUser(OWNER))

    await main.pin_handler(None, message)

    assert sc("I could not find that message") in texts(message)


async def test_a_link_to_a_chat_that_cannot_be_resolved_is_explained(db, bot):
    """The link names a chat the bot cannot open: that is its own message."""
    message = FakeMessage(text="/pin https://t.me/somesecret/44", user=FakeUser(OWNER))
    bot.get_chat = AsyncMock(side_effect=ChannelPrivate())

    await main.pin_handler(None, message)

    assert sc("I cannot reach that chat") in texts(message)
    assert bot.pinned == []


async def test_pinned_reports_no_access_and_a_floodwait(db, bot, monkeypatch):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    monkeypatch.setattr(main, "floodwait_sleep", AsyncMock())
    message = FakeMessage(text="/pinned", user=FakeUser(OWNER))

    bot.get_chat = AsyncMock(side_effect=ChannelPrivate())
    await main.pinned_handler(None, message)
    assert sc("I cannot reach that chat") in texts(message)

    bot.get_chat = AsyncMock(side_effect=FloodWait(value=12))
    await main.pinned_handler(None, message)
    assert sc("Telegram asked me to slow down") in texts(message)


def test_every_pin_reason_renders_its_own_screen():
    """No two failures may share a screen — that is what "pin failed" was."""
    reasons = ["already_pinned", "no_rights", "no_access", "floodwait",
               "not_found", "no_target"]
    rendered = {reason: ui.pin_failed_text(reason) for reason in reasons}
    assert len(set(rendered.values())) == len(reasons), "one screen per reason"
    for reason, text in rendered.items():
        assert text.strip(), reason
        assert "pin" in text.lower(), (reason, text)


def test_the_pin_usage_screen_names_all_three_targets():
    text = ui.pin_usage_text()
    assert "Reply" in text and "message link" in text and "message id" in text
    assert "dump channel" in text
    assert "t.me/" not in text, "no raw link in body copy"
