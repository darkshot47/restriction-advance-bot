"""Round 15 — a temporary picker keyboard, a working /setdump, a dump that only
carries users' custom-caption downloads, and the official Telegram menu.

What this suite pins down:

1. **/setdump works.**  Telegram requires the bot rights of a chat chooser to be
   a *subset* of the user rights.  The dump chooser asked the bot for Post +
   Delete Messages but the user only for Post Messages, so Telegram refused the
   whole keyboard and ``/setdump`` answered with nothing.  Both sides now come
   from one object, the prompt survives a refused keyboard, and a failed typed
   reference no longer disarms the picker.
2. **The picker keyboard is temporary.**  A reply keyboard stays on the screen
   until the bot removes it.  Every way out of a picker flow — a finished
   setup, ``/cancel``, any other command, any other button — now takes it away,
   and a keyboard an older build left behind is cleared once per user.
3. **The dump only carries users' downloads and messages, and only those of a
   user with a custom caption.**  Everybody else is delivered directly, and so
   are the owner's own campaigns.
4. **The Telegram menu (setMyCommands)** is published by the bot itself: /start
   first, every description an emoji followed by what the command does, user
   commands for everybody and the admin commands only in staff chats.

In-memory fakes only: no Telegram, no MongoDB, no sockets.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import BadRequest, FloodWait, ReplyMarkupInvalid
from pyrogram.types import ChatShared, ReplyKeyboardMarkup, ReplyKeyboardRemove

import config
import database
import main
import ui
from conftest import (DEFAULT_USER_ID, FAKE_BOT_ID, FakeChat, FakeMessage,
                      FakeUser, drain_background, make_member, sc)

ADMIN = ChatMemberStatus.ADMINISTRATOR
USER = DEFAULT_USER_ID
OWNER = main.OWNER_ID
DUMP = -100777              # the dump channel (also FakeBot.channel_id)
PICKED = -100999888777      # a channel picked in the chooser
SOURCE = -100123            # where a user's link points
BOT_ID = FAKE_BOT_ID


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

@pytest.fixture
def bot(fake_bot):
    """The fake bot with the memberships the two pickers need."""
    fake_bot.members[(PICKED, BOT_ID)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.members[(PICKED, USER)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.members[(DUMP, BOT_ID)] = make_member(
        ADMIN, can_post_messages=True, can_delete_messages=True)
    fake_bot.members[(DUMP, OWNER)] = make_member(ADMIN, can_post_messages=True)
    fake_bot.chats[PICKED] = SimpleNamespace(id=PICKED, title="Picked Channel",
                                             username=None, type="channel")
    fake_bot.chats[DUMP] = SimpleNamespace(id=DUMP, title="Dump", username="dump",
                                           type="channel")
    return fake_bot


def granted(rights) -> set:
    """The rights that are switched on in a ChatAdministratorRights."""
    return {name for name, value in vars(rights).items() if value is True}


def kind(markup) -> str:
    return markup.__class__.__name__


def removals(bot) -> list:
    """Every message the bot *sent* only to carry ``ReplyKeyboardRemove``."""
    return [entry for entry in bot.sent
            if isinstance(entry.get("reply_markup"), ReplyKeyboardRemove)]


def pick_message(user_id=USER, chat_id=PICKED, *, button_id=None):
    message = FakeMessage(text="", user=FakeUser(user_id))
    message.chat_shared = ChatShared(
        button_id=config.CHANNEL_PICKER_BUTTON_ID if button_id is None else button_id,
        chat=SimpleNamespace(id=chat_id, title="Picked Channel", username=None,
                             type="channel"))
    return message


def dump_pick_message(chat_id=DUMP):
    message = FakeMessage(text="", user=FakeUser(OWNER))
    message.chat_shared = ChatShared(
        button_id=config.DUMP_PICKER_BUTTON_ID,
        chat=SimpleNamespace(id=chat_id, title="Dump", username="dump", type="channel"))
    return message


async def open_channel_picker(press, user_id=USER):
    """/setchat → "Share the channel": the picker keyboard is now on screen."""
    message = FakeMessage(text="/setchat", user=FakeUser(user_id))
    await main.setchat_handler(None, message)
    await press(message, "setchat:share")
    assert user_id in main.PICKER_KEYBOARD_SHOWN
    return message


async def open_dump_picker():
    message = FakeMessage(text="/setdump", user=FakeUser(OWNER))
    await main.setdump_handler(None, message)
    assert OWNER in main.PICKER_KEYBOARD_SHOWN
    return message


# --------------------------------------------------------------------------- #
#  1. /setdump
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("factory", [ui.setchat_picker_keyboard, ui.setdump_picker_keyboard],
                         ids=["channel", "dump"])
def test_the_bot_rights_of_a_picker_are_a_subset_of_the_user_rights(factory):
    request = factory().keyboard[0][0].request_chat
    assert granted(request.bot_administrator_rights) <= granted(request.user_administrator_rights)


def test_the_dump_picker_still_asks_for_post_and_delete():
    request = ui.setdump_picker_keyboard().keyboard[0][0].request_chat
    for rights in (request.bot_administrator_rights, request.user_administrator_rights):
        assert rights.can_post_messages is True
        assert rights.can_delete_messages is True


@pytest.mark.parametrize("factory", [ui.setchat_picker_keyboard, ui.setdump_picker_keyboard],
                         ids=["channel", "dump"])
async def test_the_picker_goes_out_on_the_wire_with_valid_rights(factory):
    """The raw MTProto button — what Telegram actually validates."""
    wire = factory().write(None)
    if inspect.isawaitable(wire):
        wire = await wire
    peer_type = wire.rows[0].buttons[0].type.peer_type
    flags = lambda rights: {name for name in rights.__slots__ if getattr(rights, name) is True}
    assert flags(peer_type.bot_admin_rights) <= flags(peer_type.user_admin_rights)
    assert peer_type.bot_admin_rights.post_messages is True


async def test_setdump_answers_the_owner_with_the_picker(db, bot):
    message = FakeMessage(text="/setdump", user=FakeUser(OWNER))

    await main.setdump_handler(None, message)

    assert main.pending_action[OWNER] == "setdump_share"
    assert sc("DUMP CHANNEL SETUP") in message.shown_text
    assert kind(message.shown_markup) == "ReplyKeyboardMarkup"
    assert message.shown_markup.keyboard[0][0].text == "🗄 Pick my dump"


async def test_setdump_still_answers_when_telegram_refuses_the_keyboard(db, bot):
    """A refused reply markup must never leave the owner with a silent bot."""
    message = FakeMessage(text="/setdump", user=FakeUser(OWNER))
    delivered = []

    async def reply(text, reply_markup=None, **kwargs):
        if isinstance(reply_markup, ReplyKeyboardMarkup):
            raise ReplyMarkupInvalid()
        delivered.append((text, reply_markup))
        return message

    message.reply = reply

    await main.setdump_handler(None, message)

    assert len(delivered) == 1
    text, markup = delivered[0]
    assert sc("DUMP CHANNEL SETUP") in text
    assert kind(markup) == "InlineKeyboardMarkup", "the inline Cancel button replaces it"
    assert main.pending_action[OWNER] == "setdump_share", "typing a link still works"
    assert OWNER not in main.PICKER_KEYBOARD_SHOWN


async def test_the_channel_picker_also_survives_a_refused_keyboard(db, bot, press):
    message = FakeMessage(text="/setchat", user=FakeUser(USER))
    await main.setchat_handler(None, message)
    delivered = []

    async def reply(text, reply_markup=None, **kwargs):
        if isinstance(reply_markup, ReplyKeyboardMarkup):
            raise ReplyMarkupInvalid()
        delivered.append(text)
        return message

    message.reply = reply
    await press(message, "setchat:share")

    assert delivered and sc("PICK YOUR CHANNEL") in delivered[0]
    assert main.pending_action[USER] == "setchat_share"


async def test_the_dump_pick_registers_the_channel(db, bot):
    await open_dump_picker()
    message = dump_pick_message()

    await main.chat_shared_handler(None, message)

    entry = await db.get_dump_channel()
    assert entry and entry["chat_id"] == DUMP
    assert OWNER not in main.pending_action
    assert sc("Dump channel connected") in message.shown_text


async def test_a_failed_typed_reference_keeps_the_picker_working(db, bot, monkeypatch):
    """The typed path disarms the flow; a recoverable failure must re-arm it."""
    await open_dump_picker()
    monkeypatch.setattr(main, "resolve_chat_target",
                        AsyncMock(side_effect=main.InviteLinkError("unresolved")))
    typed = FakeMessage(text="not-a-channel", user=FakeUser(OWNER))

    await main.text_handler(None, typed)

    assert main.pending_action[OWNER] == "setdump_share"
    assert kind(typed.shown_markup) == "ReplyKeyboardMarkup", "the picker is offered again"
    #: ...and a pick made right after that really registers.
    await main.chat_shared_handler(None, dump_pick_message())
    assert (await db.get_dump_channel())["chat_id"] == DUMP


async def test_a_typed_dump_that_is_not_a_channel_keeps_the_flow_armed(db, bot, monkeypatch):
    monkeypatch.setattr(main, "resolve_chat_target", AsyncMock(return_value={
        "chat_id": -1009, "type": "supergroup", "title": "A group"}))
    main.pending_action[OWNER] = "setdump_share"
    typed = FakeMessage(text="@agroup", user=FakeUser(OWNER))

    await main.text_handler(None, typed)

    assert main.pending_action[OWNER] == "setdump_share"
    assert await db.get_dump_channel() is None


# --------------------------------------------------------------------------- #
#  2. The picker keyboard is temporary
# --------------------------------------------------------------------------- #

async def test_say_notes_which_chats_show_a_reply_keyboard(db, bot):
    message = FakeMessage(text="x", user=FakeUser(USER))

    await main.say(message, "inline only", reply_markup=ui.back_keyboard())
    assert USER not in main.PICKER_KEYBOARD_SHOWN

    await main.say(message, "picker", reply_markup=ui.setchat_picker_keyboard())
    assert USER in main.PICKER_KEYBOARD_SHOWN

    await main.say(message, "inline again", reply_markup=ui.back_keyboard())
    assert USER in main.PICKER_KEYBOARD_SHOWN, "an inline keyboard does not touch it"

    await main.say(message, "gone", reply_markup=ui.remove_keyboard())
    assert USER not in main.PICKER_KEYBOARD_SHOWN


async def test_say_message_notes_the_keyboard_too(db, bot):
    await main.say_message(bot, USER, "picker", reply_markup=ui.setdump_picker_keyboard())
    assert USER in main.PICKER_KEYBOARD_SHOWN
    await main.say_message(bot, USER, "gone", reply_markup=ui.remove_keyboard())
    assert USER not in main.PICKER_KEYBOARD_SHOWN


async def test_cancel_takes_the_picker_keyboard_off_the_screen(db, bot, press):
    await open_channel_picker(press)
    cancel = FakeMessage(text="/cancel", user=FakeUser(USER))

    await main.cancel_handler(None, cancel)

    assert USER not in main.PICKER_KEYBOARD_SHOWN
    sent = removals(bot)
    assert [entry["chat_id"] for entry in sent] == [USER]
    assert sent[0].get("disable_notification") is True, "no buzz for a clean-up"
    assert [chat for chat, _id in bot.deleted] == [USER], "the throw-away message is deleted"
    assert USER not in main.pending_action
    assert sc("Action cancelled") in cancel.shown_text


async def test_the_inline_cancel_button_takes_the_keyboard_off_too(db, bot, press):
    message = await open_channel_picker(press)

    await press(message, "cancel_action")

    assert USER not in main.PICKER_KEYBOARD_SHOWN
    assert len(removals(bot)) == 1


async def test_any_other_command_takes_the_keyboard_off(db, bot, press):
    await open_channel_picker(press)

    await main.abort_pending_on_command(None, FakeMessage(text="/help", user=FakeUser(USER)))

    assert USER not in main.PICKER_KEYBOARD_SHOWN
    assert len(removals(bot)) == 1


async def test_a_navigation_button_takes_the_keyboard_off(db, bot, press):
    message = await open_channel_picker(press)

    await press(message, "home")

    assert USER not in main.PICKER_KEYBOARD_SHOWN
    assert len(removals(bot)) == 1


async def test_the_buttons_of_the_flow_itself_keep_the_keyboard(db, bot, press):
    """Pressing *Share the channel* again must not blink the keyboard away."""
    message = await open_channel_picker(press)

    await press(message, "setchat:share")

    assert USER in main.PICKER_KEYBOARD_SHOWN
    assert removals(bot) == []


async def test_a_typed_channel_takes_the_keyboard_off_after_the_setup(db, bot, press):
    await db.add_user(USER, "Tester")
    bot.chats[PICKED] = SimpleNamespace(id=PICKED, title="Picked Channel",
                                        username="picked", type="channel")
    await open_channel_picker(press)
    typed = FakeMessage(text="@picked", user=FakeUser(USER))

    await main.text_handler(None, typed)

    assert [e["chat_id"] for e in await db.get_user_channels(USER)] == [bot.channel_id]
    assert sc("Channel dump enabled") in typed.shown_text
    assert USER not in main.PICKER_KEYBOARD_SHOWN
    assert len(removals(bot)) == 1


async def test_a_picked_channel_removes_the_keyboard_in_its_own_reply(db, bot, press):
    """No second message: the confirmation itself carries the removal."""
    await db.add_user(USER, "Tester")
    await open_channel_picker(press)
    pick = pick_message()

    await main.chat_shared_handler(None, pick)

    assert kind(pick.replies[-1]["reply_markup"]) == "ReplyKeyboardRemove"
    assert USER not in main.PICKER_KEYBOARD_SHOWN
    assert removals(bot) == []


async def test_a_finished_dump_setup_takes_the_keyboard_off(db, bot):
    await open_dump_picker()

    await main.chat_shared_handler(None, dump_pick_message())

    assert OWNER not in main.PICKER_KEYBOARD_SHOWN
    assert [entry["chat_id"] for entry in removals(bot)] == [OWNER]


async def test_a_typed_dump_setup_takes_the_keyboard_off(db, bot, monkeypatch):
    await open_dump_picker()
    monkeypatch.setattr(main, "resolve_chat_target", AsyncMock(return_value={
        "chat_id": DUMP, "type": "channel", "title": "Dump", "username": "dump"}))

    await main.text_handler(None, FakeMessage(text="@dump", user=FakeUser(OWNER)))

    assert (await db.get_dump_channel())["chat_id"] == DUMP
    assert OWNER not in main.PICKER_KEYBOARD_SHOWN
    assert len(removals(bot)) == 1


async def test_a_refused_requester_ends_the_setup_and_the_keyboard(db, bot, press):
    """"Setup cancelled" means cancelled — typed reference or not."""
    await db.add_user(USER, "Tester")
    bot.members[(bot.channel_id, USER)] = make_member(ChatMemberStatus.MEMBER)
    await open_channel_picker(press)
    typed = FakeMessage(text="@picked", user=FakeUser(USER))

    await main.text_handler(None, typed)

    assert sc("Setup cancelled") in typed.shown_text
    assert await db.get_user_channels(USER) == []
    assert USER not in main.pending_action
    assert USER not in main.PICKER_KEYBOARD_SHOWN
    assert len(removals(bot)) == 1


async def test_a_failed_pick_keeps_the_keyboard_for_the_retry(db, bot):
    """Not a way out: the bot still waits for a (better) pick."""
    bot.members[(DUMP, BOT_ID)] = make_member(ADMIN, can_post_messages=True,
                                              can_delete_messages=False)
    await open_dump_picker()
    message = dump_pick_message()

    await main.chat_shared_handler(None, message)

    assert await db.get_dump_channel() is None
    assert main.pending_action[OWNER] == "setdump_share"
    assert OWNER in main.PICKER_KEYBOARD_SHOWN
    assert kind(message.shown_markup) == "ReplyKeyboardMarkup"
    assert removals(bot) == []


async def test_a_full_channel_list_takes_the_keyboard_off(db, bot, press):
    await db.add_user(USER, "Tester")
    await open_channel_picker(press)
    #: The slots fill up while the picker is open (e.g. a second device).
    for index in range(max(1, int(config.MAX_USER_CHANNELS))):
        await db.add_user_channel(USER, -100500 - index, f"Spare {index}")
    pick = pick_message()

    await main.chat_shared_handler(None, pick)

    assert sc("Channel limit") in pick.shown_text
    assert PICKED not in {e["chat_id"] for e in await db.get_user_channels(USER)}
    assert USER not in main.PICKER_KEYBOARD_SHOWN
    assert len(removals(bot)) == 1


async def test_a_tap_on_a_leftover_keyboard_removes_it_and_saves_nothing(db, bot):
    await db.add_user(USER, "Tester")
    message = pick_message()          # no flow is armed

    await main.chat_shared_handler(None, message)

    assert kind(message.replies[-1]["reply_markup"]) == "ReplyKeyboardRemove"
    assert sc("Pick your channel") in message.shown_text
    assert not any(isinstance(r["reply_markup"], ReplyKeyboardMarkup) for r in message.replies)
    assert await db.get_user_channels(USER) == []


async def test_a_leftover_pick_from_an_older_client_is_handled_the_same_way(db, bot):
    """Older clients may omit the button id; the leftover is still taken away."""
    message = FakeMessage(text="", user=FakeUser(USER))
    message.chat_shared = SimpleNamespace(chat=SimpleNamespace(
        id=PICKED, title="Picked Channel", username=None, type="channel"))

    await main.chat_shared_handler(None, message)

    assert kind(message.replies[-1]["reply_markup"]) == "ReplyKeyboardRemove"
    assert await db.get_user_channels(USER) == []


async def test_a_leftover_dump_keyboard_is_removed_not_offered_again(db, bot):
    message = dump_pick_message()     # the owner, but no /setdump is running

    await main.chat_shared_handler(None, message)

    assert kind(message.replies[-1]["reply_markup"]) == "ReplyKeyboardRemove"
    assert await db.get_dump_channel() is None


async def test_nothing_is_sent_when_no_keyboard_is_on_screen(db, bot):
    await main.cancel_handler(None, FakeMessage(text="/cancel", user=FakeUser(USER)))
    await main.abort_pending_on_command(None, FakeMessage(text="/help", user=FakeUser(USER)))

    assert bot.sent == [] and bot.deleted == []


async def test_a_refused_removal_never_raises_and_is_retried_later(db, bot):
    main.PICKER_KEYBOARD_SHOWN.add(USER)
    bot.send_message = AsyncMock(side_effect=RuntimeError("blocked"))

    assert await main.dismiss_picker_keyboard(USER) is False
    assert USER in main.PICKER_KEYBOARD_SHOWN, "the record stays so the next exit retries"


async def test_a_floodwait_does_not_stall_the_cleanup(db, bot, monkeypatch):
    main.PICKER_KEYBOARD_SHOWN.add(USER)
    bot.send_message = AsyncMock(side_effect=FloodWait(30))
    slept = []

    async def sleeper(seconds):
        slept.append(seconds)

    original = main.floodwait_guard

    async def guard(call, *args, **kwargs):
        return await original(call, *args, sleeper=sleeper, **kwargs)

    monkeypatch.setattr(main, "floodwait_guard", guard)

    assert await main.dismiss_picker_keyboard(USER) is False

    assert slept == [], "cosmetic clean-up must not sleep out a FloodWait"
    assert USER in main.PICKER_KEYBOARD_SHOWN


async def test_two_exits_at_once_send_a_single_removal(db, bot):
    import asyncio
    main.PICKER_KEYBOARD_SHOWN.add(USER)

    results = await asyncio.gather(main.dismiss_picker_keyboard(USER),
                                   main.dismiss_picker_keyboard(USER))

    assert sorted(results) == [False, True]
    assert len(removals(bot)) == 1


async def test_dm_user_still_delivers_when_the_picker_is_refused(db, bot):
    original = bot.send_message
    tries = []

    async def send(chat_id, text, **kwargs):
        tries.append(kwargs.get("reply_markup"))
        if isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup):
            raise ReplyMarkupInvalid()
        return await original(chat_id, text, **kwargs)

    bot.send_message = send

    sent = await main.dm_user(USER, "pick a channel", ui.setchat_picker_keyboard())

    assert sent is not None and len(tries) == 2
    assert USER not in main.PICKER_KEYBOARD_SHOWN


# ---- every door into a picker flow really shows the keyboard --------------- #

async def test_a_deep_link_sent_to_the_bot_really_shows_the_picker(db, bot, monkeypatch):
    """The copy says "on the keyboard below" — the keyboard must be there."""
    monkeypatch.setattr(main, "SHARE_TOKENS", {})
    await db.add_user(USER, "Tester")
    sent = FakeMessage(text=main.share_deep_link(USER, "setchat"), user=FakeUser(USER))

    await main.text_handler(None, sent)

    assert kind(sent.shown_markup) == "ReplyKeyboardMarkup"
    assert USER in main.PICKER_KEYBOARD_SHOWN
    assert main.pending_action[USER] == "setchat_share"


async def test_the_start_deep_links_open_their_picker(db, bot, monkeypatch):
    monkeypatch.setattr(main, "SHARE_TOKENS", {})
    await db.add_user(USER, "Tester")
    link = main.share_deep_link(USER, "setchat")
    start = FakeMessage(text="/start ch" + link.rsplit("ch", 1)[1], user=FakeUser(USER))
    await main.start_handler(None, start)
    assert kind(start.shown_markup) == "ReplyKeyboardMarkup"

    owner_link = main.share_deep_link(OWNER, "setdump")
    owner_start = FakeMessage(text="/start dp" + owner_link.rsplit("dp", 1)[1],
                              user=FakeUser(OWNER))
    await main.start_handler(None, owner_start)
    assert kind(owner_start.shown_markup) == "ReplyKeyboardMarkup"
    assert main.pending_action[OWNER] == "setdump_share"


async def test_a_setchat_link_posted_in_a_channel_dms_the_picker_and_tracks_it(db, bot, monkeypatch):
    monkeypatch.setattr(main, "SHARE_TOKENS", {})
    await main.guide_channel_link_in_channel(FakeMessage(text="x"), USER,
                                             FakeChat(PICKED, "channel"))

    assert main.pending_action[USER] == "setchat_share"
    assert USER in main.PICKER_KEYBOARD_SHOWN
    assert kind(bot.sent[-1]["reply_markup"]) == "ReplyKeyboardMarkup"


# ---- keyboards an older build left behind ---------------------------------- #

async def test_a_leftover_keyboard_is_swept_once_per_user(db, bot):
    await db.add_user(USER, "Tester")          # an old account: no flag stored

    assert await main.sweep_stale_picker_keyboard(USER) is True

    assert [entry["chat_id"] for entry in removals(bot)] == [USER]
    assert len(bot.deleted) == 1
    assert (await db.get_user(USER))[database.PICKER_SWEEP_FIELD] is True
    #: ...a second look — even after a restart — finds the flag and stays quiet.
    main.PICKER_SWEPT.clear()
    assert await main.sweep_stale_picker_keyboard(USER) is False
    assert len(removals(bot)) == 1


async def test_the_sweep_is_cached_within_a_process(db, bot):
    await db.add_user(USER, "Tester")
    await main.sweep_stale_picker_keyboard(USER)
    db.users[USER].pop(database.PICKER_SWEEP_FIELD)

    assert await main.sweep_stale_picker_keyboard(USER) is False
    assert len(removals(bot)) == 1


async def test_the_sweep_never_pulls_a_live_picker_away(db, bot, press):
    await db.add_user(USER, "Tester")
    await open_channel_picker(press)

    assert await main.sweep_stale_picker_keyboard(USER) is False

    assert removals(bot) == [] and USER in main.PICKER_KEYBOARD_SHOWN


async def test_the_sweep_ignores_an_unknown_user(db, bot):
    assert await main.sweep_stale_picker_keyboard(424242) is False
    assert bot.sent == []


async def test_a_refused_sweep_is_tried_again_on_the_next_update(db, bot):
    await db.add_user(USER, "Tester")
    original = bot.send_message
    bot.send_message = AsyncMock(side_effect=RuntimeError("offline"))
    assert await main.sweep_stale_picker_keyboard(USER) is False
    assert database.PICKER_SWEEP_FIELD not in db.users[USER]

    bot.send_message = original
    assert await main.sweep_stale_picker_keyboard(USER) is True


async def test_the_sweep_runs_ahead_of_every_other_handler(db, bot):
    await db.add_user(USER, "Tester")

    await main.sweep_picker_keyboard_on_message(None, FakeMessage(text="hi", user=FakeUser(USER)))

    assert len(removals(bot)) == 1


async def test_a_button_press_in_the_private_chat_sweeps_too(db, bot, press):
    await db.add_user(USER, "Tester")
    menu = FakeMessage(text="menu", user=FakeUser(FAKE_BOT_ID))
    menu.chat = FakeChat(USER, "private")
    from conftest import make_query
    await main.sweep_picker_keyboard_on_callback(None, make_query(menu, "home", FakeUser(USER)))

    assert len(removals(bot)) == 1


async def test_a_new_account_is_born_without_anything_to_sweep(monkeypatch):
    store = AsyncMongoMockClient()["test"]
    monkeypatch.setattr(database, "db", store)
    monkeypatch.setattr(database, "users_col", store.users)

    await database.add_user(77, "Fresh")

    assert (await store.users.find_one({"user_id": 77}))[database.PICKER_SWEEP_FIELD] is True


# --------------------------------------------------------------------------- #
#  3. The dump carries only users' downloads — and only with a custom caption
# --------------------------------------------------------------------------- #

async def connect_dump(db, bot):
    await db.add_user(USER, "Reader")
    await db.set_dump_channel(DUMP, "Workspace", None, "channel")


def source_message(*, media: bool, message_id: int = 77):
    return SimpleNamespace(
        id=message_id, empty=False, chat=FakeChat(SOURCE),
        text=None if media else "Body", caption="Body" if media else None,
        media=media, video=SimpleNamespace(file_id="v", file_size=100) if media else None,
        photo=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None)


async def test_a_user_without_a_custom_caption_is_not_in_use(db):
    await db.add_user(USER, "Reader")
    assert await main.custom_caption_in_use(USER) is False


@pytest.mark.parametrize("setter", ["set_caption", "set_prefix", "set_suffix"])
async def test_a_caption_a_prefix_or_a_suffix_counts_as_in_use(db, setter):
    await db.add_user(USER, "Reader")
    await getattr(db, setter)(USER, "Mine")
    assert await main.custom_caption_in_use(USER) is True


async def test_the_dump_is_only_offered_for_a_custom_caption(db, bot):
    await connect_dump(db, bot)
    assert await main.staging_entry_for(USER) is None, "no custom caption"

    await db.set_prefix(USER, "Mine")
    entry = await main.staging_entry_for(USER)
    assert entry and entry["chat_id"] == DUMP

    assert await main.staging_entry_for(USER, use_custom_caption=False) is None, \
        "the batch chose not to use the caption"


async def test_without_a_dump_nothing_is_ever_staged(db, bot):
    await db.add_user(USER, "Reader")
    await db.set_caption(USER, "Mine")
    assert await main.staging_entry_for(USER) is None


async def test_a_link_without_a_custom_caption_never_touches_the_dump(db, bot):
    await connect_dump(db, bot)
    bot.messages[77] = source_message(media=False)
    request = FakeMessage("link", FakeUser(USER))
    request.chat = FakeChat(USER, "private")

    result = await main.try_native_copy(request, bot, SOURCE, 77)

    assert result is True, "delivered directly"
    assert bot.copies == [(USER, SOURCE, 77)]
    assert all(destination != DUMP for destination, *_ in bot.copies)
    assert bot.deleted == [] and not main.DUMP_MIRROR.pending
    assert main.DUMP_MIRROR.mirrored == 0


async def test_a_link_with_a_custom_caption_goes_through_the_dump(db, bot):
    await connect_dump(db, bot)
    await db.set_suffix(USER, "Mine")
    bot.messages[77] = source_message(media=False)
    request = FakeMessage("link", FakeUser(USER))
    request.chat = FakeChat(USER, "private")

    result = await main.try_native_copy(request, bot, SOURCE, 77)

    assert result == main.DUMP_STAGED_COPY
    stage_id = 5000  # FakeBot gives the first staged copy this id
    assert bot.copies == [(DUMP, SOURCE, 77),        # first into the dump...
                          (USER, DUMP, stage_id)]    # ...then from the dump to the user
    assert bot.deleted == [(DUMP, stage_id)], "and the staged copy is cleaned"


async def test_a_batch_that_declined_the_caption_is_delivered_directly(db, bot):
    await connect_dump(db, bot)
    await db.set_caption(USER, "Mine")
    bot.messages[77] = source_message(media=False)

    request = FakeMessage("link", FakeUser(USER))
    request.chat = FakeChat(USER, "private")

    result = await main.try_native_copy(request, bot, SOURCE, 77, use_custom_caption=False)

    assert result is True
    assert bot.copies == [(USER, SOURCE, 77)]


@pytest.mark.parametrize("custom", [False, True])
async def test_a_text_download_is_staged_only_for_a_custom_caption(db, bot, custom):
    await connect_dump(db, bot)
    if custom:
        await db.set_prefix(USER, "Mine")
    bot.messages[77] = source_message(media=False)
    original_copy = bot.copy_message

    async def copy(chat_id, from_chat_id, message_id, **kwargs):
        if from_chat_id == SOURCE:
            raise RuntimeError("the source cannot be copied")
        return await original_copy(chat_id, from_chat_id, message_id, **kwargs)

    bot.copy_message = copy
    request = FakeMessage("link", FakeUser(USER))
    request.chat = FakeChat(USER, "private")

    assert await main.fetch_and_send(request, FakeMessage(), bot, "example", 77,
                                     enforce_fsub=False)

    staged_in_dump = [entry for entry in bot.sent if entry["chat_id"] == DUMP]
    if custom:
        assert staged_in_dump and "Mine" in staged_in_dump[0]["text"]
        assert any(copy[:2] == (USER, DUMP) for copy in bot.copies)
    else:
        assert staged_in_dump == [], "the dump saw nothing"
        assert request.replies and "Body" in request.replies[0]["text"]
        assert bot.copies == []


@pytest.mark.parametrize("custom", [False, True])
async def test_a_media_download_is_staged_only_for_a_custom_caption(db, bot, tmp_path, custom):
    await connect_dump(db, bot)
    if custom:
        await db.set_caption(USER, "Mine")
    bot.messages[77] = source_message(media=True)
    original_copy = bot.copy_message

    async def copy(chat_id, from_chat_id, message_id, **kwargs):
        if from_chat_id == SOURCE:
            raise RuntimeError("the source cannot be copied")
        return await original_copy(chat_id, from_chat_id, message_id, **kwargs)

    bot.copy_message = copy
    file = tmp_path / "clip.mp4"
    file.write_bytes(b"clip")
    bot.download_media = AsyncMock(return_value=str(file))
    uploads = []

    async def upload(chat_id, path, **kwargs):
        uploads.append(chat_id)
        return SimpleNamespace(id=900)

    bot.send_video = upload
    request = FakeMessage("link", FakeUser(USER))
    request.chat = FakeChat(USER, "private")

    assert await main.fetch_and_send(request, FakeMessage(), bot, "example", 77,
                                     enforce_fsub=False)

    if custom:
        assert uploads == [DUMP], "uploaded to the dump first"
        assert (USER, DUMP, 900) in bot.copies and (DUMP, 900) in bot.deleted
    else:
        assert uploads == [USER], "uploaded straight to the user"
        assert bot.copies == [] and bot.deleted == []
    assert main.DUMP_MIRROR.mirrored == 0, "a delivery is never mirrored into the dump"


async def test_a_direct_copy_is_not_mirrored_into_the_dump(db, bot):
    """Mirroring every delivery into the dump is gone — the dump stays clean."""
    await connect_dump(db, bot)
    bot.messages[77] = source_message(media=False)
    status = FakeMessage()
    request = FakeMessage("link", FakeUser(USER))
    request.chat = FakeChat(USER, "private")

    assert await main.fetch_and_send(request, status, bot, "example", 77, enforce_fsub=False)

    assert [dest for dest, *_ in bot.copies] == [USER]
    assert not main.DUMP_MIRROR.tasks


# ---- the owner's own campaigns --------------------------------------------- #

async def test_a_campaign_is_delivered_directly_by_default(db, bot):
    await connect_dump(db, bot)
    payload = {"source_chat_id": OWNER, "source_message_id": 9}

    report = await main.deliver_campaign_payload(payload, users_only=True)

    assert report["users_sent"] == 1
    assert bot.copies == [(USER, OWNER, 9)], "source → user, no stop in the dump"
    assert bot.deleted == []
    assert all(entry["chat_id"] != DUMP for entry in bot.sent)


async def test_a_typed_campaign_text_is_sent_directly_by_default(db, bot):
    await connect_dump(db, bot)

    report = await main.run_text_broadcast("Hello everyone", users_only=True)

    assert report["users_sent"] == 1
    assert [entry["chat_id"] for entry in bot.sent] == [USER]
    assert bot.deleted == []


async def test_a_staged_text_dm_is_sent_directly_by_default(db, bot):
    await connect_dump(db, bot)

    await main.deliver_staged_text_to_chat(24680, "Your note")

    assert [entry["chat_id"] for entry in bot.sent] == [24680]
    assert bot.sent[0]["text"] == "Your note"
    assert bot.deleted == [] and bot.copies == []


async def test_a_campaign_with_a_keyboard_stays_unedited(db, bot):
    await connect_dump(db, bot)
    payload = {"source_chat_id": OWNER, "source_message_id": 9}
    buttons = [{"label": "Join", "url": "https://example.com", "style": "success"}]

    await main.deliver_campaign_payload(payload, buttons, users_only=True)

    assert bot.copies == [(USER, OWNER, 9)]
    assert bot.sent[0]["reply_markup"] is not None, "the keyboard rides on the copy"
    assert bot.edited == []


async def test_a_telegram_client_without_copy_keyboards_still_delivers_directly(db, bot):
    """The refusal belongs to copies *out of the dump*, not to every campaign."""
    await connect_dump(db, bot)
    original = bot.copy_message

    async def copy(chat_id, from_chat_id, message_id, **kwargs):
        if "reply_markup" in kwargs:
            raise TypeError("copy_message() got an unexpected keyword argument")
        return await original(chat_id, from_chat_id, message_id, **kwargs)

    bot.copy_message = copy
    bot.edit_message_reply_markup = AsyncMock()
    keyboard = ui.custom_buttons_keyboard([{"label": "Join", "url": "https://example.com",
                                            "style": "success"}])

    sent = await main.copy_message_with_markup(USER, OWNER, 9, reply_markup=keyboard)

    assert sent is not None
    bot.edit_message_reply_markup.assert_awaited_once()


async def test_a_copy_out_of_the_dump_still_refuses_to_edit_the_recipient(db, bot):
    await connect_dump(db, bot)

    async def copy(chat_id, from_chat_id, message_id, **kwargs):
        if "reply_markup" in kwargs:
            raise TypeError("old client")
        raise AssertionError("no destination copy may be sent")

    bot.copy_message = copy
    with pytest.raises(main.DumpWorkspaceError):
        await main.copy_message_with_markup(USER, DUMP, 5, reply_markup=object())


async def test_the_campaign_switch_brings_the_staging_back(db, bot, staged_campaigns):
    await connect_dump(db, bot)
    payload = {"source_chat_id": OWNER, "source_message_id": 9}

    await main.deliver_campaign_payload(payload, users_only=True)

    assert (DUMP, OWNER, 9) in bot.copies
    assert any(copy[:2] == (USER, DUMP) for copy in bot.copies)


def test_campaign_staging_is_off_unless_the_operator_turns_it_on():
    assert config.DUMP_STAGE_CAMPAIGNS is False


def test_the_dump_screens_describe_the_new_rule():
    prompt = ui.setdump_prompt_text()
    for phrase in ("users' downloads and messages", "custom caption", "directly"):
        assert phrase in prompt, phrase
    assert "custom caption" in ui.setdump_done_text("Dump", DUMP)
    assert "custom caption" in ui.dump_status_text(None)
    assert "never used" in ui.message_menu_text()
    for text in (prompt, ui.setdump_done_text("Dump", DUMP), ui.dump_status_text(None),
                 ui.message_menu_text(), ui.custom_message_prompt_text()):
        assert "t.me/" not in text and "https://" not in text


# --------------------------------------------------------------------------- #
#  4. The Telegram command menu
# --------------------------------------------------------------------------- #

def described(commands):
    return {command.command: command.description for command in commands}


def split_emoji(description: str):
    """``("🚀", "Start the bot")`` — the emoji, then what the command does."""
    emoji, _space, rest = description.partition(" ")
    return emoji, rest


@pytest.mark.parametrize("role", main.MENU_ROLES)
def test_every_menu_description_is_an_emoji_then_what_the_command_does(role):
    for name, description in described(main.telegram_commands(role)).items():
        emoji, rest = split_emoji(description)
        assert emoji, name
        assert not any(char.isascii() and char.isalnum() for char in emoji), (name, description)
        assert rest[:1].isalpha(), (name, description)
        assert 1 <= len(description) <= 256, name


@pytest.mark.parametrize("role", main.MENU_ROLES)
def test_a_menu_respects_telegrams_limits(role):
    commands = main.telegram_commands(role)
    names = [command.command for command in commands]
    assert len(names) == len(set(names)) <= 100
    assert all(re.fullmatch(r"[a-z0-9_]{1,32}", name) for name in names)


def test_start_comes_first_in_every_menu():
    for role in main.MENU_ROLES:
        assert main.telegram_commands(role)[0].command == "start"
    assert main.telegram_commands("user")[0].description.startswith("🚀 ")


def test_the_default_menu_is_the_user_menu():
    assert [c.command for c in main.telegram_commands()] == \
        [c.command for c in main.telegram_commands("user")]


def test_an_unknown_menu_role_is_refused():
    with pytest.raises(ValueError):
        main.telegram_commands("nobody")


def test_users_see_user_commands_only():
    names = {c.command for c in main.telegram_commands("user")}
    assert {"start", "help", "login", "setcaption", "setchat", "mychannels",
            "models", "premium", "history", "feedback"} <= names
    for hidden in ("setdump", "deldump", "dump", "broadcast", "botcast", "ban", "addadmin",
                   "addpremium", "setfsub", "maintenance", "giveaway", "pin", "admin",
                   "users", "stats", "clearlogs", "payments"):
        assert hidden not in names, hidden


def test_admins_add_the_admin_commands_but_not_the_owner_ones():
    names = {c.command for c in main.telegram_commands("admin")}
    assert {"admin", "admins", "ban", "unban", "broadcast", "stats", "users", "payments"} <= names
    for owner_only in ("addadmin", "removeadmin", "setdump", "maintenance", "addpremium"):
        assert owner_only not in names, owner_only


def test_the_owner_menu_has_every_command():
    assert {c.command for c in main.telegram_commands("owner")} == set(main.COMMAND_NAMES)


def test_no_command_is_lost_between_the_user_and_the_staff_lists():
    user = {c.command for c in main.telegram_commands("user")}
    owner = {c.command for c in main.telegram_commands("owner")}
    assert user < owner
    assert user | (owner - user) == set(main.COMMAND_NAMES)
    assert all(name in main.COMMAND_NAMES for name in user)
    assert all(name in main.COMMAND_HANDLERS for name in user)


def test_menu_lines_are_short_enough_for_a_phone():
    assert max(len(c.description) for c in main.telegram_commands("user")) <= 45


async def test_registration_publishes_the_user_menu_for_every_private_chat(db, bot):
    await main.register_telegram_commands()

    menu = bot.menu_for("BotCommandScopeAllPrivateChats")
    assert [c.command for c in menu] == [c.command for c in main.telegram_commands("user")]
    assert menu[0].command == "start" and menu[0].description.startswith("🚀")


async def test_registration_clears_the_legacy_default_list_first(db, bot):
    await main.register_telegram_commands()

    assert bot.deleted_command_scopes[0] is None, "the default scope is cleared"
    assert bot.command_scopes[0].__class__.__name__ == "BotCommandScopeAllPrivateChats"


async def test_the_owner_gets_every_command_in_their_own_chat(db, bot):
    await main.register_telegram_commands()

    menu = bot.menu_for("BotCommandScopeChat", OWNER)
    assert {c.command for c in menu} == set(main.COMMAND_NAMES)
    assert menu[0].command == "start"


async def test_stored_admins_get_the_admin_menu_in_their_own_chat(db, bot):
    db.admins.add(555)

    await main.register_telegram_commands()

    menu = bot.menu_for("BotCommandScopeChat", 555)
    assert menu is not None
    names = {c.command for c in menu}
    assert "ban" in names and "setdump" not in names and "start" in names
    assert bot.menu_for("BotCommandScopeChat", USER) is None, "a normal user gets nothing extra"


async def test_a_chat_the_bot_cannot_reach_does_not_stop_the_others(db, bot):
    db.admins.add(555)
    db.admins.add(666)
    original = bot.set_bot_commands

    async def flaky(commands, **kwargs):
        scope = kwargs.get("scope")
        if getattr(scope, "chat_id", None) == 555:
            raise BadRequest("chat not found")
        return await original(commands, **kwargs)

    bot.set_bot_commands = flaky

    await main.register_telegram_commands()

    assert bot.menu_for("BotCommandScopeChat", 666) is not None
    assert bot.menu_for("BotCommandScopeChat", OWNER) is not None


async def test_a_new_admin_gets_the_admin_menu_at_once(db, bot):
    request = FakeMessage(text="/addadmin 555", user=FakeUser(OWNER))

    await main.addadmin_handler(None, request)

    menu = bot.menu_for("BotCommandScopeChat", 555)
    assert menu and "ban" in {c.command for c in menu}


async def test_a_removed_admin_falls_back_to_the_user_menu(db, bot):
    db.admins.add(555)
    request = FakeMessage(text="/removeadmin 555", user=FakeUser(OWNER))

    await main.removeadmin_handler(None, request)

    assert any(getattr(scope, "chat_id", None) == 555 for scope in bot.deleted_command_scopes)


async def test_an_admin_who_starts_the_bot_gets_the_menu_even_if_added_earlier(db, bot):
    db.admins.add(555)
    start = FakeMessage(text="/start", user=FakeUser(555))

    await main.start_handler(None, start)

    assert bot.menu_for("BotCommandScopeChat", 555) is not None


async def test_an_ordinary_user_who_starts_the_bot_gets_no_extra_menu(db, bot):
    await main.start_handler(None, FakeMessage(text="/start", user=FakeUser(USER)))

    assert bot.command_registry == []


async def test_the_menu_is_published_when_the_client_starts(db, bot):
    """No first update needed: the start hook publishes it."""
    await main.publish_menu_on_start(None)
    await drain_background()

    assert bot.menu_for("BotCommandScopeAllPrivateChats") is not None
    assert bot.menu_for("BotCommandScopeChat", OWNER) is not None


def test_the_start_hook_is_registered_on_the_client():
    """``@bot.on_start()`` — the one lifecycle hook this library offers."""
    import ast
    from pathlib import Path
    module = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    hook = next(node for node in module.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "publish_menu_on_start")
    assert [ast.unparse(decorator) for decorator in hook.decorator_list] == ["bot.on_start()"]
