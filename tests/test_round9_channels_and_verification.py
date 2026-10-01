"""Round 9 — items 4, 5, 7 and 8: two channels per user and real verification.

Item 4  Every account may keep ``config.MAX_USER_CHANNELS`` (2) dump channels
        connected.  A third is refused in plain English ("disconnect one
        first").  Legacy single-channel documents migrate **on read** — no
        migration script, no data loss.  Extraction resolves the owner from the
        *posting* chat id and uses that channel's own counter, ``/mychannels``
        lists both with per-channel actions, and ``/delchat`` offers a choice
        only when two are connected.

Item 5  The bot verifies that the **person** adding a channel administers it
        (owner/creator/administrator).  A plain member, a non-member or an
        inconclusive Telegram answer cancels the wizard and stores nothing.
        This fails **safe**, unlike force-sub which fails open.  The existing
        bot-admin + Post-Messages check stays a separate step: both must pass.

Item 7  A private channel is registered by **sharing** it: the bot reads the
        chat id and title off the forward, stores a pending registration and
        runs both verifications.  No invite link or raw chat id is ever printed
        into the conversation.

Item 8  The "send message number e.g. 15" step is gone.  Verification resolves
        a real **content link**, reads the message and confirms it belongs to
        the channel being registered; a private channel accepts a shared post
        instead.  Every failure keeps the wizard alive for a retry.

In-memory fakes only: no Telegram, no MongoDB, no /proc, no sockets.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config
import database
import main
import ui
from conftest import (DEFAULT_USER_ID, FAKE_BOT_ID, FakeChat, FakeMessage,
                      FakeUser, make_member, make_query, sc)
from pyrogram.enums import ChatMemberStatus

CREATOR = ChatMemberStatus.OWNER
ADMIN = ChatMemberStatus.ADMINISTRATOR
MEMBER = ChatMemberStatus.MEMBER

USER = DEFAULT_USER_ID
CHANNEL = -100777          # what FakeBot.get_chat resolves a public handle to
SECOND = -100888


def grant(status, *, chat_id=CHANNEL, user_id=USER, can_post_messages=True,
          privileges="__unset"):
    """Give one (chat, user) pair a specific membership in the fake bot."""
    if privileges == "__unset":
        main.bot.members[(chat_id, user_id)] = make_member(
            status, can_post_messages=can_post_messages)
    else:
        #: A channel creator carries no ``privileges`` object at all.
        main.bot.members[(chat_id, user_id)] = make_member(status, privileges=privileges)


def bot_is_admin(chat_id=CHANNEL, can_post_messages=True):
    """The bot itself must be an admin with posting rights for step 2 to pass."""
    main.bot.members[(chat_id, FAKE_BOT_ID)] = make_member(
        ADMIN, can_post_messages=can_post_messages)


def shared_post(chat_id=CHANNEL, title="Shared Channel", *, username=None,
                kind="channel", user_id=USER, text="a post from the channel"):
    """A message forwarded out of *chat_id* — how a private channel is shared."""
    message = FakeMessage(text=text, user=FakeUser(user_id))
    message.forward_from_chat = SimpleNamespace(
        id=chat_id, title=title, username=username, type=kind)
    return message


def content_message(msg_id, chat_id=CHANNEL):
    """A readable message living in *chat_id*, served by ``FakeBot.messages``."""
    return SimpleNamespace(id=msg_id, empty=False, chat=SimpleNamespace(id=chat_id),
                           text="hello", caption=None, media=False)


async def open_wizard(link="t.me/mychannel"):
    """Start /setchat and return the message the wizard is talking through."""
    message = FakeMessage(text=f"/setchat {link}", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    return message


# --------------------------------------------------------------------------- #
#  4a. Two channels per user — the storage layer
# --------------------------------------------------------------------------- #

def test_the_channel_cap_is_a_documented_config_knob():
    assert config.MAX_USER_CHANNELS == 2


async def test_adding_the_first_and_second_channel_both_succeed(db):
    await db.add_user(USER, "Tester")
    assert await db.add_user_channel(USER, CHANNEL, "First", "first") == (True, "added")
    assert await db.add_user_channel(USER, SECOND, "Second", None) == (True, "added")

    entries = await db.get_user_channels(USER)
    assert [entry["chat_id"] for entry in entries] == [CHANNEL, SECOND]
    assert [entry["title"] for entry in entries] == ["First", "Second"]


async def test_the_third_channel_is_refused(db):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")
    ok, reason = await db.add_user_channel(USER, -100999, "Third")
    assert (ok, reason) == (False, "full")
    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [CHANNEL, SECOND]


async def test_re_registering_a_known_channel_updates_instead_of_refusing(db):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")
    #: Refreshing an already-connected channel is never blocked by the cap.
    assert await db.add_user_channel(USER, CHANNEL, "Renamed", "renamed") == (True, "updated")
    entries = await db.get_user_channels(USER)
    assert len(entries) == 2
    assert entries[0]["title"] == "Renamed" and entries[0]["username"] == "renamed"


async def test_a_legacy_single_channel_document_migrates_on_read():
    """No migration script: the old scalar fields are read as one channel."""
    legacy = {"user_id": USER, "channel_chat_id": CHANNEL,
              "channel_title": "Old Channel", "channel_username": "oldchan"}
    entries = database.channels_from_document(legacy)
    assert entries == [{"chat_id": CHANNEL, "title": "Old Channel",
                        "username": "oldchan", "type": "channel"}]
    #: And a document with neither shape is simply empty.
    assert database.channels_from_document({"user_id": USER}) == []
    assert database.channels_from_document(None) == []


async def test_the_legacy_mirror_is_kept_in_step(db):
    """Old readers keep working: entry 0 is mirrored into the scalar fields."""
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First", "first")
    row = db.users[USER]
    assert row["channel_chat_id"] == CHANNEL and row["channel_title"] == "First"
    assert await db.get_user_chat(USER) == {
        "chat_id": CHANNEL, "title": "First", "username": "first"}

    #: Disconnecting the primary promotes the second one into the mirror.
    await db.add_user_channel(USER, SECOND, "Second")
    assert await db.remove_user_channel(USER, CHANNEL) is True
    assert await db.get_user_chat(USER) == {
        "chat_id": SECOND, "title": "Second", "username": None}


async def test_disconnecting_one_of_two_keeps_the_other(db):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")
    assert await db.remove_user_channel(USER, SECOND) is True
    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [CHANNEL]
    assert await db.remove_user_channel(USER, SECOND) is False, "already gone"


async def test_the_owner_lookup_matches_either_channel(db):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")
    assert (await db.find_user_chat_owner(SECOND))["user_id"] == USER
    assert (await db.find_user_chat_owner(CHANNEL))["user_id"] == USER
    assert await db.find_user_chat_owner(-100555) is None


def test_pick_channel_entry_only_matches_the_requested_chat():
    row = {"channels": [{"chat_id": CHANNEL, "title": "A"},
                        {"chat_id": SECOND, "title": "B"}]}
    assert database.pick_channel_entry(row, SECOND)["title"] == "B"
    assert database.pick_channel_entry(row, -100555) is None
    assert database.pick_channel_entry(row, None) is None


# --------------------------------------------------------------------------- #
#  4b. Two channels per user — the wizard and the dashboard
# --------------------------------------------------------------------------- #

async def test_the_wizard_refuses_a_third_channel_in_plain_english(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")
    fake_bot.chats["thirdchan"] = SimpleNamespace(
        id=-100999, title="Third", username="thirdchan", type="channel")

    message = FakeMessage(text="/setchat t.me/thirdchan", user=FakeUser(USER))
    await main.setchat_handler(None, message)

    assert sc("Channel limit reached") in message.shown_text
    assert sc("Disconnect one of them first") in message.shown_text
    assert USER not in main.setchat_pending, "nothing was queued for a refused channel"
    #: Both connected channels are named so the user can pick one to drop.
    assert sc("First") in message.shown_text and sc("Second") in message.shown_text
    assert "http" not in message.shown_text


async def test_the_wizard_still_refuses_at_the_final_step(db, fake_bot, press):
    """A wizard left open while the slots filled up cannot push past the cap."""
    await db.add_user(USER, "Tester")
    bot_is_admin()
    message = await open_wizard()
    await press(message, "setchat:check")
    assert main.setchat_pending[USER]["step"] == "await_sample"

    #: The two slots fill up while step 3 is still open.
    await db.add_user_channel(USER, SECOND, "Second")
    await db.add_user_channel(USER, -100999, "Third")

    sample = FakeMessage(text="https://t.me/mychannel/15", user=FakeUser(USER))
    fake_bot.messages[15] = content_message(15)
    await main.text_handler(None, sample)
    assert sc("Channel limit reached") in sample.shown_text
    #: The pending channel was NOT squeezed in — the two existing ones are intact.
    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [SECOND, -100999]
    assert USER in main.setchat_pending, "the wizard is still open for a retry"


async def test_mychannels_lists_both_channels_with_their_own_counters(db, fake_bot):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First", "first")
    await db.add_user_channel(USER, SECOND, "Second", None)
    await db.increment_channel_files(CHANNEL, 4)
    await db.increment_channel_files(SECOND, 9)

    message = FakeMessage(text="/mychannels", user=FakeUser(USER))
    await main.mychannels_handler(None, message)

    text = message.shown_text
    assert sc("First") in text and sc("Second") in text
    assert f"`{CHANNEL}`" in text and f"`{SECOND}`" in text
    #: Each counter stays separate — no shared total.
    assert sc("Files extracted here: **4**") in text
    assert sc("Files extracted here: **9**") in text
    assert sc(f"Connected: **2/{config.MAX_USER_CHANNELS}**") in text
    assert sc("MY CHANNELS") in text


async def test_mychannels_offers_per_channel_actions(db, fake_bot):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")

    message = FakeMessage(text="/mychannels", user=FakeUser(USER))
    await main.mychannels_handler(None, message)
    data = message.callback_data()
    for chat_id in (CHANNEL, SECOND):
        assert f"mych_test:{chat_id}" in data
        assert f"mych_verify:{chat_id}" in data
        assert f"mych_del:{chat_id}" in data
    #: The mobile budget still holds with two channels on screen.
    rows = message.shown_markup.inline_keyboard
    assert 1 <= len(rows) <= 7
    assert all(1 <= len(row) <= 2 for row in rows)
    #: Labels are measured after the small-caps renderer, exactly as Telegram
    #: shows them, and never carry a raw link.
    assert all(len(ui.plain_caps(b.text)) <= 28 for row in rows for b in row)
    assert all(b.url is None or b.url.startswith("https://") for row in rows for b in row)


async def test_disconnecting_one_channel_leaves_the_other_dashboard_ready(
        db, fake_bot, press):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")

    message = FakeMessage(text="/mychannels", user=FakeUser(USER))
    await main.mychannels_handler(None, message)
    await press(message, f"mych_del:{SECOND}")

    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [CHANNEL]
    assert sc("Channel disconnected") in message.shown_text
    assert f"mych_test:{CHANNEL}" in message.callback_data()
    assert f"mych_test:{SECOND}" not in message.callback_data()


async def test_a_forged_channel_id_cannot_touch_another_channel(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")

    message = FakeMessage(text="/mychannels", user=FakeUser(USER))
    await main.mychannels_handler(None, message)
    query = await press(message, "mych_del:-100555")

    assert query.answer.calls[-1]["show_alert"] is True
    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [CHANNEL]


async def test_delchat_offers_a_choice_only_when_two_are_connected(db, fake_bot):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")

    one = FakeMessage(text="/delchat", user=FakeUser(USER))
    await main.delchat_handler(None, one)
    #: Unchanged single-channel behaviour: it just goes, no question asked.
    assert sc("Channel link removed") in one.shown_text
    assert await db.get_user_channels(USER) == []

    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")
    two = FakeMessage(text="/delchat", user=FakeUser(USER))
    await main.delchat_handler(None, two)
    assert sc("Disconnect a channel") in two.shown_text
    assert f"delchat_pick:{CHANNEL}" in two.callback_data()
    assert f"delchat_pick:{SECOND}" in two.callback_data()
    #: Nothing was removed yet — the user still has to choose.
    assert len(await db.get_user_channels(USER)) == 2


async def test_the_delchat_choice_disconnects_exactly_the_tapped_channel(
        db, fake_bot, press):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")

    message = FakeMessage(text="/delchat", user=FakeUser(USER))
    await main.delchat_handler(None, message)
    await press(message, f"delchat_pick:{SECOND}")

    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [CHANNEL]
    assert sc("Channel disconnected") in message.shown_text


async def test_extraction_is_routed_by_the_posting_chat_id(db, fake_bot, monkeypatch):
    """A post in channel 2 uses channel 2's owner, settings and counter."""
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")
    await db.add_user_channel(USER, SECOND, "Second")
    seen = {}

    async def fake_fetch(requester, status, client, target, mid, **kwargs):
        seen["owner"] = requester.from_user.id
        seen["chat"] = requester.chat.id
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "get_caption", AsyncMock(return_value=None))

    post = FakeMessage(text="https://t.me/publicchannel/10", user=FakeUser(USER))
    post.chat = FakeChat(SECOND, chat_type="channel")
    await main.channel_dump_handler(None, post)

    assert seen == {"owner": USER, "chat": SECOND}
    assert await db.get_channel_files(SECOND) == 1
    assert await db.get_channel_files(CHANNEL) == 0, "the other counter is untouched"


async def test_a_channel_nobody_registered_is_still_ignored(db, fake_bot, monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "First")

    post = FakeMessage(text="https://t.me/publicchannel/10", user=FakeUser(USER))
    post.chat = FakeChat(-100555, chat_type="channel")
    await main.channel_dump_handler(None, post)
    fetch.assert_not_called()


# --------------------------------------------------------------------------- #
#  5. The person adding the channel must administer it
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status,expected", [
    (CREATOR, (True, "ok")),
    (ADMIN, (True, "ok")),
    (MEMBER, (False, "not_admin")),
])
async def test_requester_admin_probe_reads_the_real_membership(status, expected,
                                                               db, fake_bot):
    grant(status, can_post_messages=status == ADMIN)
    assert await main.describe_requester_admin(CHANNEL, USER) == expected


async def test_a_non_member_is_reported_as_such(db, fake_bot):
    fake_bot.members.pop(USER, None)
    fake_bot.not_members.add((CHANNEL, USER))
    assert await main.describe_requester_admin(CHANNEL, USER) == (False, "not_member")


async def test_an_inconclusive_answer_fails_safe(db, fake_bot):
    """A Telegram hiccup must never register a channel on an uncertain answer."""
    fake_bot.get_chat_member = AsyncMock(side_effect=RuntimeError("telegram hiccup"))
    assert await main.describe_requester_admin(CHANNEL, USER) == (False, "error")


@pytest.mark.parametrize("status,reason", [
    (MEMBER, "not_admin"),
    (ChatMemberStatus.RESTRICTED, "not_admin"),
])
async def test_the_wizard_is_cancelled_for_a_plain_member(db, fake_bot, press,
                                                          status, reason):
    await db.add_user(USER, "Tester")
    bot_is_admin()                       # the bot's rights are fine
    grant(status, can_post_messages=False)   # …but the person adding it is not an admin

    message = await open_wizard()
    await press(message, "setchat:check")

    assert sc("Setup cancelled") in message.shown_text
    assert sc("not an administrator") in message.shown_text
    assert USER not in main.setchat_pending, "the wizard is closed, not left hanging"
    assert await db.get_user_channels(USER) == [], "nothing was stored"
    #: No stack trace, no invite link, no raw chat id in the refusal.
    assert "Traceback" not in message.shown_text
    assert str(CHANNEL) not in message.shown_text
    assert "t.me/" not in message.shown_text


async def test_a_non_member_cannot_register_the_channel(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    bot_is_admin()
    fake_bot.members.pop(USER, None)
    fake_bot.not_members.add((CHANNEL, USER))

    message = await open_wizard()
    await press(message, "setchat:check")

    assert sc("Setup cancelled") in message.shown_text
    assert sc("not a member") in message.shown_text
    assert await db.get_user_channels(USER) == []


async def test_an_inconclusive_probe_cancels_rather_than_guessing(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    bot_is_admin()
    real = fake_bot.get_chat_member

    async def flaky(chat_id, user_id):
        if user_id == USER:
            raise RuntimeError("telegram hiccup")
        return await real(chat_id, user_id)

    fake_bot.get_chat_member = flaky
    message = await open_wizard()
    await press(message, "setchat:check")

    assert sc("Setup cancelled") in message.shown_text
    assert sc("never register a channel on an uncertain answer") in message.shown_text
    assert await db.get_user_channels(USER) == []


async def test_the_channel_owner_may_register_it(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    bot_is_admin()
    grant(CREATOR, privileges=None)

    message = await open_wizard()
    await press(message, "setchat:check")
    assert sc("Admin verified") in message.shown_text
    assert main.setchat_pending[USER]["step"] == "await_sample"


async def test_both_checks_must_pass(db, fake_bot, press):
    """The person is an admin, but the bot has no posting rights."""
    await db.add_user(USER, "Tester")
    grant(ADMIN)
    bot_is_admin(can_post_messages=False)

    message = await open_wizard()
    await press(message, "setchat:check")

    assert sc("Admin check failed") in message.shown_text
    assert sc("Post Messages") in message.shown_text
    assert USER in main.setchat_pending, "the wizard stays alive for a retry"
    assert await db.get_user_channels(USER) == []


# --------------------------------------------------------------------------- #
#  7. Registering a channel with a message link — never a forward
# --------------------------------------------------------------------------- #

async def test_the_prompt_offers_the_share_path(db, fake_bot):
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    assert "setchat:share" in message.callback_data()
    assert sc("Private channel?") in message.shown_text
    assert main.pending_action[USER] == "setchat"


def test_no_screen_ever_asks_the_user_to_forward_a_post():
    """Round 12: verification is a **message link**, never a forward."""
    source = open("main.py", encoding="utf-8").read()
    assert "forwarded_chat_of" not in source
    for text in (ui.setchat_share_prompt_text(),
                 ui.setchat_share_failed_text("not_received"),
                 ui.setchat_share_failed_text("not_a_channel"),
                 ui.setchat_admin_ok_text("A Channel", private=True),
                 ui.setchat_sample_failed_text("not_a_link")):
        assert "forward" not in text.lower(), text


def message_link(chat_id, msg_id=7):
    """The link Telegram's *Copy Link* action produces for a private channel.

    A supergroup id is ``-100<raw>`` and the ``t.me/c/`` link carries ``<raw>``,
    so the helper turns ``-1001234567890`` back into ``1234567890``.
    """
    raw = str(abs(int(chat_id)))
    if raw.startswith("100"):
        raw = raw[3:]
    return f"https://t.me/c/{raw}/{msg_id}"


async def test_a_message_link_registers_a_private_channel(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    private_id = -1001234567890
    bot_is_admin(private_id)
    grant(ADMIN, chat_id=private_id)
    fake_bot.chats[private_id] = SimpleNamespace(
        id=private_id, title="Secret Channel", username=None, type="channel")
    fake_bot.messages[7] = content_message(7, private_id)

    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")
    assert main.pending_action[USER] == "setchat_share"
    #: Round 14 — the share button is gone; the chooser screen took its place.
    assert sc("Pick your channel") in message.shown_text
    assert sc("Pick my channel") in message.shown_text

    link = FakeMessage(text=message_link(private_id), user=FakeUser(USER))
    await main.text_handler(None, link)

    assert sc("Channel dump enabled") in link.shown_text
    stored = await db.get_user_channels(USER)
    assert [entry["chat_id"] for entry in stored] == [private_id]
    assert USER not in main.setchat_pending
    assert USER not in main.pending_action
    #: The step itself never prints the link it received or the raw chat id —
    #: the confirmation screen is the only place the id may appear.
    ack = link.replies[0]["text"]
    assert "t.me/" not in ack
    assert str(private_id) not in ack


async def test_a_message_that_is_not_a_link_keeps_the_step_open(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")

    share = FakeMessage(text="just some text", user=FakeUser(USER))
    await main.text_handler(None, share)

    assert sc("That was not a message link") in share.shown_text
    assert sc("Copy Link") in share.shown_text
    assert main.pending_action[USER] == "setchat_share", "the step stays open"
    assert USER not in main.setchat_pending
    assert await db.get_user_channels(USER) == []


async def test_a_link_the_bot_is_not_in_is_explained(db, fake_bot, press):
    from pyrogram.errors import ChannelPrivate
    await db.add_user(USER, "Tester")
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")
    fake_bot.get_chat = AsyncMock(side_effect=ChannelPrivate())

    share = FakeMessage(text=message_link(-100444), user=FakeUser(USER))
    await main.text_handler(None, share)

    assert sc("I am not in that channel") in share.shown_text
    assert sc("Add Admin") in share.shown_text
    assert main.pending_action[USER] == "setchat_share", "send the link again once added"
    assert USER not in main.setchat_pending
    assert await db.get_user_channels(USER) == []


async def test_a_channel_the_bot_cannot_see_is_explained(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")
    fake_bot.get_chat = AsyncMock(side_effect=RuntimeError("no route to telegram"))

    share = FakeMessage(text=message_link(-100444), user=FakeUser(USER))
    await main.text_handler(None, share)

    assert sc("I cannot see that channel") in share.shown_text
    assert await db.get_user_channels(USER) == []


async def test_a_channel_you_do_not_administer_is_refused(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    bot_is_admin(-100444)
    grant(MEMBER, chat_id=-100444, can_post_messages=False)
    fake_bot.chats[-100444] = SimpleNamespace(
        id=-100444, title="Someone Elses Channel", username=None, type="channel")
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")

    share = FakeMessage(text=message_link(-100444), user=FakeUser(USER))
    await main.text_handler(None, share)

    assert sc("Setup cancelled") in share.shown_text
    assert sc("not an administrator") in share.shown_text
    assert USER not in main.setchat_pending
    assert await db.get_user_channels(USER) == []


async def test_no_posting_rights_keeps_the_wizard_alive(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    grant(ADMIN, chat_id=-100444)
    bot_is_admin(-100444, can_post_messages=False)
    fake_bot.chats[-100444] = SimpleNamespace(
        id=-100444, title="Muted Channel", username=None, type="channel")
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")

    share = FakeMessage(text=message_link(-100444), user=FakeUser(USER))
    await main.text_handler(None, share)

    assert sc("Admin check failed") in share.shown_text
    assert main.setchat_pending[USER]["step"] == "await_check"
    assert "setchat:check" in share.callback_data()
    assert await db.get_user_channels(USER) == []


async def test_a_link_the_bot_cannot_read_never_registers_the_channel(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    grant(ADMIN, chat_id=-100444)
    bot_is_admin(-100444)
    fake_bot.chats[-100444] = SimpleNamespace(
        id=-100444, title="Empty Channel", username=None, type="channel")
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")

    #: The chat resolves, but that post cannot be read back.
    share = FakeMessage(text=message_link(-100444, 999), user=FakeUser(USER))
    await main.text_handler(None, share)

    assert sc("cannot see that channel") in share.shown_text
    assert main.pending_action[USER] == "setchat_share"
    assert await db.get_user_channels(USER) == []


async def test_a_share_link_inside_a_channel_registers_nothing(db, fake_bot, monkeypatch):
    """Round 14 — a setchat link posted *inside* a channel is no longer a proof.

    That link used to be read off the message it landed in, which is precisely
    the "post something into the channel" behaviour the picker replaced.  It is
    now only a hint: nothing is registered, the channel is not answered in, and
    the owner is sent the chooser in their private chat instead.
    """
    await db.add_user(USER, "Tester")
    private_id = -1001234567890
    bot_is_admin(private_id)
    grant(ADMIN, chat_id=private_id)
    fake_bot.chats[private_id] = SimpleNamespace(
        id=private_id, title="Secret Channel", username=None, type="channel")

    link = main.share_deep_link(USER, "setchat")
    post = FakeMessage(text=f"Check this channel: {link}", user=FakeUser(USER))
    post.chat = FakeChat(private_id, chat_type="channel", title="Secret Channel")

    await main.channel_dump_handler(None, post)

    assert await db.get_user_channels(USER) == [], "nothing is registered from it"
    #: The channel stays clean — the answer goes to the user's private chat.
    assert post.replies == [] and post.edits == []
    assert any(sent["chat_id"] == USER for sent in fake_bot.sent), "the owner was told"
    assert main.pending_action[USER] == "setchat_share", "the chooser is armed"


async def test_cancel_leaves_the_share_step(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")
    assert main.pending_action[USER] == "setchat_share"

    #: /cancel is its own handler (the text handler never sees a command).
    await main.cancel_handler(None, FakeMessage(text="/cancel", user=FakeUser(USER)))
    assert USER not in main.pending_action
    assert USER not in main.setchat_pending
    assert await db.get_user_channels(USER) == []


# --------------------------------------------------------------------------- #
#  8. Verification with a real content link, never a bare number
# --------------------------------------------------------------------------- #

def test_the_bare_number_prompt_is_gone_from_the_ui():
    source = open("ui.py", encoding="utf-8").read()
    assert "just the message number" not in source
    assert "message number (for example" not in source
    #: The wizard asks for a content link — private channels included, and never
    #: for a forwarded post.
    assert "one content link from this channel" in ui.setchat_admin_ok_text("Chan")
    assert "bare message number is no longer accepted" in ui.setchat_admin_ok_text("Chan")
    private_copy = ui.setchat_admin_ok_text("Chan", private=True)
    assert "one message link from this channel" in private_copy
    assert "copy link" in private_copy.lower()
    assert "forward" not in private_copy.lower()


async def test_a_valid_content_link_completes_the_wizard(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    bot_is_admin()
    fake_bot.messages[15] = content_message(15)

    message = await open_wizard()
    await press(message, "setchat:check")
    sample = FakeMessage(text="https://t.me/mychannel/15", user=FakeUser(USER))
    await main.text_handler(None, sample)

    assert sc("Channel dump enabled") in sample.shown_text
    assert await db.get_user_chat(USER) == {
        "chat_id": CHANNEL, "title": "mychannel", "username": "mychannel"}
    assert USER not in main.setchat_pending


async def test_a_link_from_another_channel_is_refused(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    bot_is_admin()
    #: The message is readable, but it lives somewhere else.
    fake_bot.messages[15] = content_message(15, chat_id=-100555)

    message = await open_wizard()
    await press(message, "setchat:check")
    sample = FakeMessage(text="https://t.me/otherchannel/15", user=FakeUser(USER))
    await main.text_handler(None, sample)

    assert sc("different chat") in sample.shown_text
    assert USER in main.setchat_pending, "the wizard stays alive for a retry"
    assert main.setchat_pending[USER]["step"] == "await_sample"
    assert await db.get_user_channels(USER) == []
    #: The link the user sent is never echoed back.
    assert "otherchannel" not in sample.shown_text


async def test_a_bare_message_number_is_refused_with_its_own_next_step(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    bot_is_admin()
    fake_bot.messages[15] = content_message(15)

    message = await open_wizard()
    await press(message, "setchat:check")
    sample = FakeMessage(text="15", user=FakeUser(USER))
    await main.text_handler(None, sample)

    assert sc("not a message number") in sample.shown_text
    assert sc("Copy Message Link") in sample.shown_text
    assert USER in main.setchat_pending
    assert await db.get_user_channels(USER) == []


@pytest.mark.parametrize("reason,expected", [
    ("unreadable", "could not be read"),
    ("deleted", "could not be read"),
])
async def test_an_unreadable_or_deleted_post_keeps_the_wizard_alive(
        db, fake_bot, press, reason, expected):
    await db.add_user(USER, "Tester")
    bot_is_admin()
    if reason == "deleted":
        fake_bot.messages[15] = SimpleNamespace(id=15, empty=True, chat=None)
    #: "unreadable": nothing in the store at all.

    message = await open_wizard()
    await press(message, "setchat:check")
    sample = FakeMessage(text="https://t.me/mychannel/15", user=FakeUser(USER))
    await main.text_handler(None, sample)

    assert sc("Verification failed") in sample.shown_text
    assert sc(expected) in sample.shown_text
    assert USER in main.setchat_pending
    assert await db.get_user_channels(USER) == []


async def test_a_channel_the_bot_lost_access_to_is_reported_as_such(db, fake_bot, press):
    from pyrogram.errors import ChannelPrivate
    await db.add_user(USER, "Tester")
    bot_is_admin()

    message = await open_wizard()
    await press(message, "setchat:check")
    real = fake_bot.get_messages

    async def blind(chat_id, message_ids):
        raise ChannelPrivate()

    fake_bot.get_messages = blind
    sample = FakeMessage(text="https://t.me/mychannel/15", user=FakeUser(USER))
    await main.text_handler(None, sample)
    fake_bot.get_messages = real

    assert sc("cannot see") in sample.shown_text
    assert USER in main.setchat_pending
    assert await db.get_user_channels(USER) == []


async def test_a_message_link_verifies_a_private_channel(db, fake_bot, press):
    """Step 3 for a private channel: paste its *Copy Link*, never a forward."""
    await db.add_user(USER, "Tester")
    private_id = -1001234567890
    bot_is_admin(private_id)
    grant(ADMIN, chat_id=private_id)
    fake_bot.chats[private_id] = SimpleNamespace(
        id=private_id, title="Secret", username=None, type="channel")

    message = FakeMessage(text=f"/setchat {private_id}", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:check")
    assert sc("message link") in message.shown_text.lower()

    fake_bot.messages[7] = content_message(7, private_id)
    link = FakeMessage(text=message_link(private_id), user=FakeUser(USER))
    await main.text_handler(None, link)
    assert sc("Channel dump enabled") in link.shown_text
    assert await db.get_user_chat(USER) == {
        "chat_id": private_id, "title": "Secret", "username": None}


async def test_a_message_link_from_another_channel_is_refused(db, fake_bot, press):
    await db.add_user(USER, "Tester")
    private_id = -1001234567890
    bot_is_admin(private_id)
    grant(ADMIN, chat_id=private_id)
    fake_bot.chats[private_id] = SimpleNamespace(
        id=private_id, title="Secret", username=None, type="channel")

    message = FakeMessage(text=f"/setchat {private_id}", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    await press(message, "setchat:check")

    fake_bot.messages[7] = content_message(7, -100555)
    link = FakeMessage(text=message_link(-100555), user=FakeUser(USER))
    await main.text_handler(None, link)
    assert sc("different chat") in link.shown_text
    assert USER in main.setchat_pending
    assert await db.get_user_channels(USER) == []
