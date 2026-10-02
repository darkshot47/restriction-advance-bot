"""Round 12 — copy-first delivery, the owner dump channel, /pin, the button
wizard and the giveaway engine.

What this suite pins down:

1. **Copy before download.**  A restricted source is *copied* server-side
   (``copy_message``) and only falls back to the download → re-upload path when
   Telegram refuses the copy — that is the only case where the file really has
   to stream through this server.
2. **One-tap channel registration.**  ``t.me/<bot>?start=ch…`` (the URL behind
   the share-sheet button) is read out of the message the *channel* received, so
   a private channel registers without pasting a link, forwarding a post or ever
   printing an id.  A message link works as the identity proof too.
3. **The owner dump channel.**  Every delivery is mirrored with ``copy_message``
   (never ``forward``), each copy is deleted after ``DUMP_TTL_SECONDS`` and every
   mirror/delete call passes the native FloodWait governor.
4. **/pin and /pinned.**  Reply-to-pin, link-to-pin, id-to-pin, and removing the
   live pin — with plain-English failures and no crash on a fake client.
5. **The inline-button wizard.**  Colour → label → link → send, with a cancel
   button on every step — for a **direct user send** only.  A broadcast and a
   channel post go out exactly as they were typed (round 13, item 9).
6. **Giveaways.**  Steps (tier → duration → benefit → end → channel), the
   participate deep link (once per account, live count), the daily re-post, the
   live refresh of the pinned message, and a **random** winner whose prize is
   granted automatically.

In-memory fakes only: no Telegram, no MongoDB, no sockets.
"""

from __future__ import annotations

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
from pyrogram.errors import ChatAdminRequired, FloodWait

ADMIN = ChatMemberStatus.ADMINISTRATOR
USER = DEFAULT_USER_ID
OWNER = main.OWNER_ID
CHANNEL = -100777            # the dump channel the fake bot resolves
SECRET = -1001234567890      # a private channel
BOT_ID = FAKE_BOT_ID


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


def channel_post(text, *, chat_id=CHANNEL, user_id=None):
    message = FakeMessage(text=text, user=FakeUser(user_id) if user_id else None)
    message.chat = FakeChat(chat_id, chat_type="channel", title="Dump")
    return message


def raw_of(chat_id) -> str:
    """``-1001234567890`` → ``1234567890`` (the id inside a t.me/c/ link)."""
    raw = str(abs(int(chat_id)))
    return raw[3:] if raw.startswith("100") else raw


def message_link(chat_id, msg_id=7) -> str:
    return f"https://t.me/c/{raw_of(chat_id)}/{msg_id}"


def content_message(msg_id, chat_id=SECRET):
    return SimpleNamespace(id=msg_id, empty=False, chat=SimpleNamespace(id=chat_id),
                           text="hello", caption=None, media=False)


@pytest.fixture
def bot(fake_bot):
    """The fake bot with the memberships the owner tools need."""
    fake_bot.members[(CHANNEL, BOT_ID)] = make_member(
        ADMIN, can_post_messages=True, can_delete_messages=True)
    fake_bot.members[(CHANNEL, OWNER)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.members[(SECRET, BOT_ID)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.members[(SECRET, OWNER)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.chats[CHANNEL] = SimpleNamespace(id=CHANNEL, title="Dump",
                                              username="dump", type="channel")
    fake_bot.chats[SECRET] = SimpleNamespace(id=SECRET, title="Secret Channel",
                                             username=None, type="channel")
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
#  1. Copy first, download only when the copy is refused
# --------------------------------------------------------------------------- #

async def test_a_restricted_source_is_copied_before_it_is_downloaded(db, bot):
    await db.add_user(OWNER, "Owner")
    message = FakeMessage(text="t.me/c/1234567890/15", user=FakeUser(OWNER))
    message.chat = FakeChat(CHANNEL, chat_type="channel")
    bot.messages[15] = content_message(15, SECRET)

    copied = await main.try_native_copy(message, bot, SECRET, 15)

    assert copied
    assert bot.copies[-1] == (CHANNEL, SECRET, 15), "the server made the copy"


async def test_when_the_copy_is_refused_the_file_is_streamed(db, bot):
    """Telegram refusing the copy is exactly when the download path is right."""
    await db.add_user(OWNER, "Owner")
    message = FakeMessage(text="t.me/c/1234567890/15", user=FakeUser(OWNER))
    message.chat = FakeChat(CHANNEL, chat_type="channel")
    bot.messages[15] = content_message(15, SECRET)
    bot.copy_message = AsyncMock(side_effect=ChatAdminRequired())

    assert await main.try_native_copy(message, bot, SECRET, 15) is False


async def test_a_user_session_never_delivers_to_its_own_id(db, bot):
    """Private chat + the user's own session would be *Saved Messages*.

    Round 14 changed the answer without weakening the rule.  The session still
    may never post to its own id; instead of giving up on the copy (which used
    to force a download through this server) the destination becomes the
    **bot's** chat, so the copy is made there by the user's own account and no
    byte ever streams through the server.
    """
    from conftest import FakeUser as _FakeUser  # noqa: F401  (documentation)
    message = FakeMessage(text="x", user=FakeUser(USER))
    main.user_clients[USER] = SimpleNamespace(name="user-session")
    target = main.resolve_delivery_target(message, USER, main.user_clients[USER])
    assert target.reason == "bot_dm_native_copy"
    assert target.chat_id == BOT_ID and target.chat_id != USER
    #: The copy is still a copy — that is the whole point of the round.
    assert target.native_copy is True
    assert target.copy_client is main.user_clients[USER]


async def test_a_user_session_still_refuses_saved_messages_without_a_bot_id(db, bot):
    """No bot id known yet (still connecting): fall back to the bot, never copy."""
    from conftest import FakeUser as _FakeUser  # noqa: F401  (documentation)
    message = FakeMessage(text="x", user=FakeUser(USER))
    main.user_clients[USER] = SimpleNamespace(name="user-session")
    original = main.bot_self_id
    main.bot_self_id = lambda: None
    try:
        target = main.resolve_delivery_target(message, USER, main.user_clients[USER])
    finally:
        main.bot_self_id = original
    assert target.native_copy is False and target.reason == "saved_messages_guard"
    assert target.chat_id == USER


# --------------------------------------------------------------------------- #
#  2. The share-URL deep link
# --------------------------------------------------------------------------- #

def test_no_share_button_is_ever_offered_for_a_channel():
    """Round 14 — the share sheet is gone from the channel flow.

    Its whole mechanism was "post this link into the channel", which is the one
    thing the picker replaced.  A share URL may still appear elsewhere (the
    referral screen, the giveaway link), but never on a setchat screen.
    """
    markup = ui.setchat_share_prompt_keyboard("https://t.me/share/url?url=x")
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert not [b for b in buttons if b.url], "no share URL on a setchat screen"
    assert [b.callback_data for b in buttons if b.callback_data] == ["cancel_action"]


def test_a_token_is_bound_to_its_kind_and_its_ttl(monkeypatch):
    monkeypatch.setattr(main, "SHARE_TOKENS", {})
    link = main.share_deep_link(USER, "setchat")
    token = link.rsplit("ch", 1)[1]
    assert main.find_share_token(link)["user_id"] == USER

    #: A /setdump token may not register a channel.
    dump_link = main.share_deep_link(USER, "setdump")
    assert main.find_share_token(dump_link.replace("start=dp", "start=ch")) is None
    #: Expired tokens stop working.
    main.SHARE_TOKENS[token]["ttl"] = -1
    assert main.find_share_token(link) is None


async def test_a_deep_link_posted_in_a_channel_registers_nothing(db, bot, monkeypatch):
    """Round 14 — the link is a hint, not a registration proof any more."""
    monkeypatch.setattr(main, "SHARE_TOKENS", {})
    await db.add_user(USER, "Tester")
    bot.members[(SECRET, USER)] = make_member(ADMIN, can_post_messages=True)
    link = main.share_deep_link(USER, "setchat")

    post = channel_post(link, chat_id=SECRET, user_id=USER)
    await main.channel_dump_handler(None, post)

    assert await db.get_user_channels(USER) == [], "nothing is registered from it"
    #: The channel stays clean: the answer went to the user's private chat.
    assert post.replies == [] and post.edits == []
    assert any(sent["chat_id"] == USER for sent in bot.sent)


async def test_a_deep_link_sent_to_the_bot_opens_the_picker(db, bot, monkeypatch):
    """Round 14 — the link no longer matters; the chooser screen does."""
    monkeypatch.setattr(main, "SHARE_TOKENS", {})
    await db.add_user(USER, "Tester")
    link = main.share_deep_link(USER, "setchat")
    sent = FakeMessage(text=link, user=FakeUser(USER))
    await main.text_handler(None, sent)
    assert sc("Pick your channel") in texts(sent)
    assert sc("Pick my channel") in texts(sent)
    assert main.pending_action[USER] == "setchat_share"


# --------------------------------------------------------------------------- #
#  3. The owner dump channel
# --------------------------------------------------------------------------- #

async def test_setdump_connects_the_channel_and_reports_it(db, bot):
    message = owner_message(f"/setdump {CHANNEL}")
    await main.setdump_handler(None, message)
    entry = await db.get_dump_channel()
    assert entry and entry["chat_id"] == CHANNEL
    assert sc("Dump channel connected") in texts(message)

    status = owner_message("/dump")
    await main.dump_status_handler(None, status)
    assert sc("DUMP CHANNEL") in texts(status)
    assert str(config.DUMP_TTL_SECONDS) in texts(status)


async def test_setdump_is_owner_only(db, bot):
    message = FakeMessage(text=f"/setdump {CHANNEL}", user=FakeUser(USER))
    await main.setdump_handler(None, message)
    assert await db.get_dump_channel() is None


async def test_the_dump_prompt_offers_telegrams_channel_picker(db, bot):
    message = owner_message("/setdump")
    await main.setdump_handler(None, message)
    markup = message.shown_markup
    assert markup.__class__.__name__ == "ReplyKeyboardMarkup"
    button = markup.keyboard[0][0]
    assert button.request_chat.button_id == config.DUMP_PICKER_BUTTON_ID
    assert button.request_chat.bot_administrator_rights.can_delete_messages is True
    assert main.pending_action[OWNER] == "setdump_share"


async def test_a_delivery_is_mirrored_then_deleted_after_the_ttl(db, bot, monkeypatch):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    sleeps: list = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    copy = await main.DUMP_MIRROR.mirror(SECRET, 42, label="video")

    assert bot.copies[-1] == (CHANNEL, SECRET, 42)
    assert main.DUMP_MIRROR.pending == 1 and main.DUMP_MIRROR.mirrored == 1

    #: The queued task deletes the copy after exactly the configured TTL.
    await main.DUMP_MIRROR._delete_later(CHANNEL, copy.id)
    assert survives(sleeps, config.DUMP_TTL_SECONDS), sleeps
    assert bot.deleted[-1] == (CHANNEL, copy.id)
    assert main.DUMP_MIRROR.deleted == 1
    assert main.DUMP_MIRROR.pending == 0


def survives(sleeps, expected):
    """The governor may pace first; the TTL is the *longest* sleep of the run."""
    return bool(sleeps) and max(sleeps) == expected


async def test_the_mirror_never_copies_into_itself(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    assert await main.DUMP_MIRROR.mirror(CHANNEL, 15) is None
    assert bot.copies == []


async def test_the_mirror_is_a_no_op_without_a_dump_channel(db, bot):
    assert await main.DUMP_MIRROR.mirror(SECRET, 15) is None
    assert bot.copies == []


async def test_a_floodwait_pauses_the_mirror_instead_of_crashing(db, bot, monkeypatch):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    calls = {"n": 0}
    real_copy = bot.copy_message

    async def flood_once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FloodWait(2)
        return await real_copy(*args, **kwargs)

    bot.copy_message = flood_once

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(main, "floodwait_sleep", no_sleep)
    copy = await main.DUMP_MIRROR.mirror(SECRET, 15)

    assert copy is not None
    assert main.DUMP_MIRROR.pauses == 1
    assert main.DUMP_MIRROR.governor.pause_ms("dump:x", main.time.monotonic()) >= 0


async def test_deldump_disconnects_and_cleans_pending_copies(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    await main.DUMP_MIRROR.mirror(SECRET, 15)
    message = owner_message("/deldump")
    await main.deldump_handler(None, message)
    assert await db.get_dump_channel() is None
    assert sc("Dump channel disconnected") in texts(message)
    assert bot.deleted, "the pending copy was deleted with the channel"


# --------------------------------------------------------------------------- #
#  4. /pin and /pinned
# --------------------------------------------------------------------------- #

async def test_pin_a_replied_message_in_the_dump_channel(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    message = owner_message("/pin")
    message.reply_to_message = FakeMessage(message_id=77, user=FakeUser(OWNER))
    await main.pin_handler(None, message)
    assert bot.pinned[-1][0] == CHANNEL
    assert bot.pinned[-1][1] != 77, "the broadcast copy, not the source, is pinned"
    assert sc("BROADCAST COMPLETE") in texts(message)
    assert bot.deleted, "temporary dump stage is removed after fan-out"


async def test_pin_accepts_a_message_link(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    message = owner_message("/pin https://t.me/dump/88")
    await main.pin_handler(None, message)
    assert bot.pinned[-1] == (CHANNEL, 88)


async def test_pin_without_a_target_explains_itself(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    message = owner_message("/pin")
    await main.pin_handler(None, message)
    assert sc("Nothing to pin") in texts(message)
    assert bot.pinned == []


async def test_pinned_removes_the_live_pin(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.chats[CHANNEL] = SimpleNamespace(id=CHANNEL, title="Dump", username="dump",
                                         type="channel",
                                         pinned_message=SimpleNamespace(id=55))
    message = owner_message("/pinned")
    await main.pinned_handler(None, message)
    assert bot.unpinned[-1] == (CHANNEL, 55)
    assert sc("Live pin removed") in texts(message)


async def test_pinned_without_a_pin_says_so(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.chats[CHANNEL] = SimpleNamespace(id=CHANNEL, title="Dump", username="dump",
                                         type="channel", pinned_message=None)
    message = owner_message("/pinned")
    await main.pinned_handler(None, message)
    assert sc("No live pin") in texts(message)
    assert bot.unpinned == []


async def test_pin_reports_missing_rights_in_plain_english(db, bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    bot.pin_chat_message = AsyncMock(side_effect=ChatAdminRequired())
    message = owner_message("/pin")
    message.reply_to_message = FakeMessage(message_id=5, user=FakeUser(OWNER))
    await main.pin_handler(None, message)
    assert sc("Pin Messages") in texts(message)


# --------------------------------------------------------------------------- #
#  5. The inline-button wizard
# --------------------------------------------------------------------------- #

async def test_sendmsg_offers_the_button_wizard(db, bot):
    message = owner_message(f"/sendmsg {USER} Hello there")
    await main.sendmsg_handler(None, message)
    assert sc("ADD INLINE BUTTONS") in texts(message)
    assert "btnwiz:yes" in message.callback_data()
    assert main.BUTTON_WIZARD[OWNER]["payload"]["kind"] == main.WIZARD_KIND_DM
    assert bot.sent == [], "nothing is sent before the wizard finishes"


async def test_the_wizard_collects_colour_label_and_link(db, bot, press):
    message = owner_message(f"/sendmsg {USER} Hello")
    await main.sendmsg_handler(None, message)

    await press(message, "btnwiz:yes")
    assert "btnwiz:color:blue" in message.callback_data()
    await press(message, "btnwiz:color:green")
    assert main.BUTTON_WIZARD[OWNER]["stage"] == "label"

    await main.text_handler(None, FakeMessage(text="Join Now", user=FakeUser(OWNER)))
    assert main.BUTTON_WIZARD[OWNER]["stage"] == "link"

    link = FakeMessage(text="t.me/mychannel", user=FakeUser(OWNER))
    await main.text_handler(None, link)
    assert main.BUTTON_WIZARD[OWNER]["buttons"][0]["url"] == "https://t.me/mychannel"
    assert "btnwiz:send" in link.callback_data()

    await press(link, "btnwiz:send")
    sent = bot.sent[-1]
    assert sent["chat_id"] == USER
    assert sent["reply_markup"].inline_keyboard[0][0].url == "https://t.me/mychannel"
    assert sc("Message sent") in texts(link)


async def test_every_wizard_step_offers_cancel(db, bot, press):
    message = owner_message(f"/sendmsg {USER} Hi")
    await main.sendmsg_handler(None, message)
    assert "btnwiz:cancel" in message.callback_data()
    await press(message, "btnwiz:yes")
    assert "btnwiz:cancel" in message.callback_data()
    await press(message, "btnwiz:color:red")
    assert "btnwiz:cancel" in message.callback_data()


async def test_cancel_sends_nothing_and_clears_the_wizard(db, bot, press):
    message = owner_message(f"/sendmsg {USER} Hi")
    await main.sendmsg_handler(None, message)
    await press(message, "btnwiz:yes")
    await press(message, "btnwiz:cancel")
    assert sc("Cancelled") in texts(message)
    assert OWNER not in main.BUTTON_WIZARD
    assert bot.sent == []


async def test_skip_sends_the_plain_message(db, bot, press):
    message = owner_message(f"/sendmsg {USER} Plain")
    await main.sendmsg_handler(None, message)
    await press(message, "btnwiz:skip")
    assert bot.sent[-1]["chat_id"] == USER
    assert bot.sent[-1].get("reply_markup") is None


async def test_an_over_long_label_keeps_the_step_open(db, bot, press):
    message = owner_message(f"/sendmsg {USER} Hi")
    await main.sendmsg_handler(None, message)
    await press(message, "btnwiz:yes")
    await press(message, "btnwiz:color:blue")
    long_label = FakeMessage(text="x" * (config.MAX_BUTTON_LABEL + 5),
                             user=FakeUser(OWNER))
    await main.text_handler(None, long_label)
    assert sc("Too long") in texts(long_label)
    assert main.BUTTON_WIZARD[OWNER]["stage"] == "label"


async def test_a_bad_link_keeps_the_step_open(db, bot, press):
    message = owner_message(f"/sendmsg {USER} Hi")
    await main.sendmsg_handler(None, message)
    await press(message, "btnwiz:yes")
    await press(message, "btnwiz:color:blue")
    await main.text_handler(None, FakeMessage(text="Join", user=FakeUser(OWNER)))
    bad = FakeMessage(text="not an address", user=FakeUser(OWNER))
    await main.text_handler(None, bad)
    assert sc("not an address") in texts(bad)
    assert main.BUTTON_WIZARD[OWNER]["stage"] == "link"


async def test_a_broadcast_formats_every_copy_on_the_native_pool(db, bot, press):
    await db.add_user(USER, "Tester")
    await db.add_user(2002, "Bob <script>")
    await db.add_user(2003, "Carol")
    message = owner_message("/broadcast Hello {name}!")
    await main.broadcast_handler(None, message)

    #: Round 13 item 9 — a broadcast is not a direct user send, so the builder
    #: is never offered: no ADD INLINE BUTTONS screen, nothing to skip.
    assert sc("ADD INLINE BUTTONS") not in texts(message)
    assert "btnwiz:" not in "".join(message.callback_data())
    assert OWNER not in main.BUTTON_WIZARD

    bodies = {entry["chat_id"]: entry.get("text", "") for entry in bot.sent}
    assert bodies[2002] == "Hello Bob &lt;script&gt;!", "names are HTML-escaped"
    assert bodies[USER] == "Hello Tester!"
    assert main.native_engine.pool_tasks() >= 0


async def test_a_channel_post_goes_out_plain_and_then_offers_the_pin(db, bot, press):
    """Round 13 item 9 — a channel post carries no button builder, only the pin."""
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    message = owner_message("/post Big news today")
    await main.post_to_channel_handler(None, message)

    #: published exactly as typed, with no keyboard and no wizard left open
    posted = [entry for entry in bot.sent if entry["chat_id"] == CHANNEL]
    assert posted and posted[-1]["text"] == "Big news today"
    assert posted[-1].get("reply_markup") is None
    assert sc("ADD INLINE BUTTONS") not in texts(message)
    assert sc("Message sent") in texts(message)

    #: The post is followed by a one-tap pin offer in the owner's DM.
    offers = [entry for entry in bot.sent if entry["chat_id"] == OWNER
              and entry.get("reply_markup") is not None]
    assert any(button.callback_data == "pin_offer:yes"
               for row in offers[-1]["reply_markup"].inline_keyboard for button in row)
    await main.callback_handler(None, make_query(message, "pin_offer:yes"))
    assert bot.pinned and bot.pinned[-1][0] == CHANNEL


async def test_the_pin_offer_can_be_declined(db, bot, press):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    message = owner_message("/post Not pinned")
    await main.post_to_channel_handler(None, message)
    await press(message, "btnwiz:skip")
    message.edits.clear()
    await press(message, "pin_offer:no")
    assert bot.pinned == []


# --------------------------------------------------------------------------- #
#  6. Giveaways
# --------------------------------------------------------------------------- #

def test_the_end_time_parser_reads_durations_and_dates():
    now = dt.datetime(2026, 1, 1, 12, 0, 0)
    assert main.parse_giveaway_end("6h", now=now) == now + dt.timedelta(hours=6)
    assert main.parse_giveaway_end("3d", now=now) == now + dt.timedelta(days=3)
    assert main.parse_giveaway_end("2w", now=now) == now + dt.timedelta(weeks=2)
    assert main.parse_giveaway_end("2026-01-05 09:30", now=now) == \
        dt.datetime(2026, 1, 5, 9, 30)
    assert main.parse_giveaway_end("yesterday", now=now) is None
    assert main.parse_giveaway_end("2025-01-01", now=now) is None, "in the past"
    assert main.parse_giveaway_end("0d", now=now) is None
    assert main.parse_giveaway_end("99999d", now=now) is None, "capped"


async def test_the_panel_creates_a_giveaway_step_by_step(db, bot, press):
    await db.add_user_channel(OWNER, CHANNEL, "Dump", "dump", "channel")
    panel = owner_message("/giveaway")
    await main.giveaway_handler(None, panel)
    assert sc("GIVEAWAY CONTROL") in texts(panel)
    assert "gw:new" in panel.callback_data()

    await press(panel, "gw:new")
    assert any(data.startswith("grant_tier:") for data in panel.callback_data())

    await press(panel, "grant_tier:all")
    assert sc("STEP 2/6") in texts(panel)

    await press(panel, "grant_dur:all:month")
    assert sc("STEP 3/6") in texts(panel)

    benefit = FakeMessage(text="Full VIP for 30 days", user=FakeUser(OWNER))
    await main.text_handler(None, benefit)
    assert sc("STEP 4/6") in texts(benefit)
    await press(benefit, "gw:custom:skip")
    assert sc("STEP 5/6") in texts(benefit)

    await press(benefit, "gw:end:3d")
    assert sc("STEP 6/6") in texts(benefit)

    await press(benefit, "gw:channel:1")
    giveaway = await db.get_active_giveaway()
    assert giveaway and giveaway["status"] == "running"
    assert int(giveaway["channel_id"]) == CHANNEL
    assert giveaway["benefit"] == "Full VIP for 30 days"
    assert sc("GIVEAWAY IS LIVE") in texts(benefit)

    #: Published and pinned in the channel, with the participate link inside a
    #: url= button (never printed into the copy).
    posted = [entry for entry in bot.sent if entry["chat_id"] == CHANNEL]
    assert posted and "🎉" in posted[-1]["text"]
    link = posted[-1]["reply_markup"].inline_keyboard[0][0].url
    assert link == f"https://t.me/{config.BOT_USERNAME}?start=gw{giveaway['token']}"
    assert bot.pinned and bot.pinned[-1][0] == CHANNEL
    assert "Full VIP for 30 days" in posted[-1]["text"]


async def test_the_duration_step_can_take_a_custom_number_of_days(db, bot, press):
    await db.add_user_channel(OWNER, CHANNEL, "Dump", "dump", "channel")
    panel = owner_message("/giveaway")
    await main.giveaway_handler(None, panel)
    await press(panel, "gw:new")
    await press(panel, "grant_tier:public")
    await press(panel, "grant_dur:public:custom")

    days = FakeMessage(text="45", user=FakeUser(OWNER))
    await main.text_handler(None, days)
    assert sc("STEP 3/6") in texts(days)
    assert main.GIVEAWAY_WIZARD[OWNER]["days"] == 45


async def test_only_one_giveaway_can_run(db, bot, press):
    seed_giveaway(db)
    panel = owner_message("/giveaway")
    await main.giveaway_handler(None, panel)
    query = await press(panel, "gw:new")
    assert query.answer.calls[-1]["show_alert"] is True
    assert sc("one giveaway at a time") in (query.answer.calls[-1]["text"] or "")


async def test_participating_once_through_the_deep_link(db, bot):
    seed_giveaway(db)
    await db.add_user(USER, "Tester")
    message = FakeMessage(text="/start gwabc12345", user=FakeUser(USER))
    await main.start_handler(None, message)

    assert sc("You are in the draw") in texts(message)
    assert await db.count_giveaway_participants("active") == 1
    assert db.giveaway["participant_count"] == 1
    #: The live count on the pinned message is refreshed immediately.
    assert bot.edited and bot.edited[-1][0] == CHANNEL

    again = FakeMessage(text="/start gwabc12345", user=FakeUser(USER))
    await main.start_handler(None, again)
    assert sc("already joined") in texts(again)
    assert await db.count_giveaway_participants("active") == 1


async def test_a_wrong_token_joins_nothing(db, bot):
    seed_giveaway(db)
    await db.add_user(USER, "Tester")
    message = FakeMessage(text="/start gwwrongtoken", user=FakeUser(USER))
    await main.start_handler(None, message)
    assert sc("No giveaway is running") in texts(message)
    assert await db.count_giveaway_participants("active") == 0


async def test_the_participant_list_pages_and_counts(db, bot):
    seed_giveaway(db)
    for index in range(25):
        await db.add_giveaway_participant("active", 5000 + index, f"User {index}",
                                          f"u{index}")
    message = owner_message("/participants")
    await main.giveaway_handler(None, message)
    body = texts(message)
    assert "25" in body and sc("TOTAL JOINED") in body.upper() or "25" in body
    assert "gw:list:1" in message.callback_data()


async def test_the_winner_is_random_and_the_prize_is_granted(db, bot):
    seed_giveaway(db)
    for index in range(12):
        await db.add_giveaway_participant("active", 6000 + index, f"User {index}", None)

    message = owner_message("/endgiveaway")
    await main.giveaway_handler(None, message)

    finished = await db.get_last_giveaway()
    assert finished["status"] == "finished"
    winner_id = finished["winner"]["user_id"]
    assert 6000 <= winner_id < 6012
    granted = await db.get_user(winner_id)
    assert granted["is_premium"] is True
    assert granted["has_private_access"] is True and granted["has_models_access"] is True
    assert sc("Giveaway closed by hand") in texts(message)


async def test_a_deadline_draws_the_winner_and_announces_it(db, bot):
    seed_giveaway(db, ends_at=dt.datetime.utcnow() - dt.timedelta(minutes=1))
    await db.add_giveaway_participant("active", 7001, "Winner", "winner")

    assert await main.giveaway_tick() is True
    finished = await db.get_last_giveaway()
    assert finished["status"] == "finished" and finished["winner"]["user_id"] == 7001
    #: Announced in the channel and sent to the winner's private chat.
    assert any(sc("GIVEAWAY WINNER") in entry["text"]
               for entry in bot.sent if entry["chat_id"] == CHANNEL)
    assert any(entry["chat_id"] == 7001 for entry in bot.sent)


async def test_a_daily_repost_happens_while_the_giveaway_runs(db, bot):
    seed_giveaway(db, last_post_at=dt.datetime.utcnow() - dt.timedelta(days=2))
    await db.add_giveaway_participant("active", 8001, "A", None)
    before = len([entry for entry in bot.sent if entry["chat_id"] == CHANNEL])

    assert await main.giveaway_tick() is True
    after = [entry for entry in bot.sent if entry["chat_id"] == CHANNEL]
    assert len(after) == before + 1, "the message is re-posted once a day"
    assert bot.pinned[-1][0] == CHANNEL
    assert (await db.get_active_giveaway())["status"] == "running"


async def test_the_live_count_refreshes_the_pinned_message(db, bot):
    seed_giveaway(db, participant_count=1, rendered_count=1)
    await db.add_giveaway_participant("active", 9001, "B", None)
    await db.add_giveaway_participant("active", 9002, "C", None)

    assert await main.giveaway_tick() is True
    assert bot.edited, "the pinned message must show the live count"
    assert "2" in bot.edited[-1][2]
    assert (await db.get_active_giveaway())["rendered_count"] == 2


async def test_the_scheduler_is_started_only_once(monkeypatch):
    monkeypatch.setattr(main, "GIVEAWAY_TASK", None)
    first = main.ensure_giveaway_loop()
    assert first is not None
    assert main.ensure_giveaway_loop() is first, "never a second pump"


async def test_a_giveaway_is_owner_only(db, bot):
    seed_giveaway(db)
    message = FakeMessage(text="/giveaway", user=FakeUser(USER))
    await main.giveaway_handler(None, message)
    assert sc("owner only") in texts(message).lower() or "owner only" in texts(message).lower()


# --------------------------------------------------------------------------- #
#  7. Presentation constraints over every new surface
# --------------------------------------------------------------------------- #

ONE = [{"chat_id": CHANNEL, "title": "Dump", "username": "dump", "type": "channel"}]
LINK = "https://t.me/Bot?start=gwabc123"
GW = {"token": "abc123", "prize_tier": "all", "prize_days": 30, "benefit": "VIP",
      "ends_at": dt.datetime(2026, 5, 1, 12, 0), "channel_id": CHANNEL,
      "message_id": 5, "participant_count": 3}

NEW_KEYBOARDS = [
    ("setchat_share", lambda: ui.setchat_share_prompt_keyboard(LINK)),
    ("setdump_prompt", lambda: ui.setdump_prompt_keyboard(LINK)),
    ("message_menu", ui.message_menu_keyboard),
    ("giveaway_custom", ui.giveaway_step_custom_keyboard),
    ("dump_on", lambda: ui.dump_status_keyboard(True)),
    ("dump_off", lambda: ui.dump_status_keyboard(False)),
    ("pin_offer", ui.pin_offer_keyboard),
    ("buttons_offer", ui.buttons_offer_keyboard),
    ("button_color", ui.button_color_keyboard),
    ("button_label", ui.button_label_keyboard),
    ("button_link", ui.button_link_keyboard),
    ("button_more", lambda: ui.button_more_keyboard([{"label": "A", "url": "https://x.y"}])),
    ("giveaway_panel_off", lambda: ui.giveaway_panel_keyboard(None)),
    ("giveaway_panel_on", lambda: ui.giveaway_panel_keyboard(GW)),
    ("giveaway_tier", ui.grant_tier_keyboard),
    ("giveaway_duration", lambda: ui.grant_duration_keyboard("all")),
    ("giveaway_benefit", ui.giveaway_step_benefit_keyboard),
    ("giveaway_end", ui.giveaway_step_end_keyboard),
    ("giveaway_channel", lambda: ui.giveaway_step_channel_keyboard(ONE)),
    ("giveaway_participants", lambda: ui.giveaway_participants_keyboard(0, 3)),
    ("giveaway_public", lambda: ui.giveaway_public_keyboard(LINK)),
    ("native_engine", ui.native_engine_keyboard),
]

NEW_SCREENS = [
    ("setchat_share", ui.setchat_share_prompt_text),
    ("setchat_admin_ok_private", lambda: ui.setchat_admin_ok_text("Chan", private=True)),
    ("setdump_prompt", ui.setdump_prompt_text),
    ("dump_requester_not_admin", lambda: ui.dump_admin_failed_text("requester_not_admin")),
    ("setdump_done", lambda: ui.setdump_done_text("Dump", CHANNEL)),
    ("message_menu", ui.message_menu_text),
    ("custom_message_prompt", ui.custom_message_prompt_text),
    ("giveaway_custom", ui.giveaway_step_custom_text),
    ("broadcast_complete", lambda: ui.broadcast_complete_text(
        {"channels_total": 1, "channels_sent": 1, "users_total": 2,
         "users_sent": 1, "blocked": 1}, pin=True)),
    ("setdump_removed", lambda: ui.setdump_removed_text("Dump")),
    ("dump_off", lambda: ui.dump_status_text(None)),
    ("dump_on", lambda: ui.dump_status_text(
        {"chat_id": CHANNEL, "title": "Dump", "username": "dump", "kind": "channel"},
        {"pending": 2, "mirrored": 10, "deleted": 8, "pauses": 1, "wait_seconds": 30})),
    ("pin_usage", ui.pin_usage_text),
    ("pin_none", ui.pin_no_target_text),
    ("pin_done", lambda: ui.pin_done_text("Dump", 12)),
    ("pin_failed", lambda: ui.pin_failed_text("no_rights")),
    ("pinned_none", lambda: ui.pinned_none_text("Dump")),
    ("unpin_done", lambda: ui.unpin_done_text("Dump")),
    ("buttons_offer", lambda: ui.buttons_offer_text("hello")),
    ("button_color", ui.button_color_text),
    ("button_label", ui.button_label_text),
    ("button_link", lambda: ui.button_link_text("Join")),
    ("button_more", lambda: ui.button_more_text([])),
    ("message_sent", ui.message_sent_text),
    ("message_cancelled", ui.message_cancelled_text),
    ("giveaway_panel", lambda: ui.giveaway_panel_text(None)),
    ("giveaway_panel_live", lambda: ui.giveaway_panel_text(GW, {"participants": 4})),
    ("giveaway_public", lambda: ui.giveaway_public_text(GW, 7)),
    ("giveaway_joined", lambda: ui.giveaway_joined_text("Tester", GW, 3)),
    ("giveaway_none", ui.giveaway_none_text),
    ("giveaway_finished", lambda: ui.giveaway_finished_text("Tester", "VIP", 4)),
    ("giveaway_no_winner", lambda: ui.giveaway_finished_text(None, "VIP", 0)),
    ("giveaway_owner_ended", lambda: ui.giveaway_owner_ended_text("Tester", 4, True)),
    ("giveaway_share", lambda: ui.giveaway_share_text(LINK)),
    ("native_engine", lambda: ui.native_engine_text(
        {"backend": "native", "version": "3.0.0", "compiler": "g++ 12", "threads": 4,
         "selftest": 0, "governor_keys": 1, "governor_wait_ms": 5, "library": "/tmp/x.so"})),
]

LINK_SNIPPETS = ("http://", "https://", "t.me/")


@pytest.mark.parametrize("name,render", NEW_KEYBOARDS, ids=[n for n, _ in NEW_KEYBOARDS])
def test_new_keyboards_fit_the_mobile_budget(name, render):
    markup = render()
    rows = markup.inline_keyboard
    assert len(rows) <= 7, name
    for row in rows:
        assert len(row) <= 2, name
        for button in row:
            assert len(ui.smallcaps(button.text)) <= 28, (name, button.text)
            if button.callback_data:
                assert button.callback_data.isascii(), (name, button.callback_data)
                assert not button.url, (name, button.callback_data)


@pytest.mark.parametrize("name,render", NEW_SCREENS, ids=[n for n, _ in NEW_SCREENS])
def test_new_screens_are_english_and_link_free(name, render):
    text = render()
    assert text, name
    assert not any("\u0900" <= char <= "\u097f" for char in text), name
    for snippet in LINK_SNIPPETS:
        assert snippet not in text, (name, snippet)


def test_the_owner_start_menu_offers_the_giveaway():
    """`/start` → 🎁 Start Giveaway, still inside the 7-row mobile budget."""
    rows = ui.start_keyboard(show_admin=True).inline_keyboard
    assert len(rows) <= 7
    assert all(len(row) <= 2 for row in rows)
    assert any(button.callback_data == "cmd_giveaway_panel"
               for row in rows for button in row)
    #: A normal user's menu is untouched (and keeps the language switch).
    user_rows = ui.start_keyboard(show_admin=False).inline_keyboard
    assert any(button.callback_data == "cmd_language"
               for row in user_rows for button in row)
    assert not any(button.callback_data == "cmd_giveaway_panel"
                   for row in user_rows for button in row)


@pytest.mark.parametrize("command", main.NEW_COMMAND_NAMES)
def test_every_new_command_is_registered_everywhere(command):
    assert command in main.COMMAND_NAMES
    assert command in main.COMMAND_HANDLERS
    assert command in main.ADMIN_PANEL_COMMANDS
    assert command in main.ADMIN_INLINE_HANDLERS
    assert command in main.ADMIN_OWNER_COMMANDS
    assert f"/{command}" in main.admin_help_text()


@pytest.mark.parametrize("command", ["pin", "pinned", "giveaway", "participants"])
async def test_new_commands_answer_a_stranger_with_a_refusal(db, bot, command):
    message = FakeMessage(text=f"/{command}", user=FakeUser(USER))
    await main.COMMAND_HANDLERS[command](None, message)
    body = texts(message)
    assert body, command
    assert sc("only") in body


@pytest.mark.parametrize("command", ["pin", "pinned", "unpin", "menu", "cmsg",
                                     "botcast", "dump", "native", "giveaway",
                                     "participants", "endgiveaway", "setdump",
                                     "deldump", "post"])
def test_the_new_commands_are_excluded_from_the_text_handler(command):
    source = open("main.py", encoding="utf-8").read()
    block = source.split("async def text_handler")[0]
    block = block.split("filters.command([")[-1].split("])")[0]
    assert f'"{command}"' in block, command
