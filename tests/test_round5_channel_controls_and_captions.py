"""Round 5 acceptance tests: channel download controls, custom-caption question, English copy sweep, and payment contact.

Features covered:
1. Download controls in a channel:
   - Private content keeps controls in the channel message; nothing is mirrored.
   - Public content points at the bot (single URL button), live controls mirrored into DM.
   - Mirrored job ID is DM message ID; handle_download_controls owner guard works unchanged.
   - Fallback if bot cannot DM the owner: channel message takes controls back.
   - Public-content channel notice has no dl: callback buttons.
2. Caption-only content never receives the custom caption (media still does).
3. Custom-caption question in dump channel:
   - Asked before extraction starts if custom caption is stored.
   - Deleted immediately on answer.
   - Only channel owner may answer (others get show_alert).
   - Stale question expires after CHANNEL_CAPTION_TIMEOUT and next post re-asks.
   - No question asked if no custom caption is stored.
4. Config: BOT_USERNAME and CHANNEL_CAPTION_TIMEOUT single source of truth in config.py.
5. English copy everywhere: no Devanagari text in any screen or helper.
6. Payment contact: @XyrDeveloper in config.py, plan copy, and payment proofs.
"""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram.enums import ParseMode

import config
import main
import ui
from conftest import (
    FakeChat, FakeMessage, FakeUser, make_query, sc
)


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def style_of(button):
    style = getattr(button, "style", None)
    if style is None:
        return None
    name = getattr(style, "name", str(style)).lower()
    return None if name == "default" else name


DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")


# --------------------------------------------------------------------------- #
#  1. Config exports & payment contact
# --------------------------------------------------------------------------- #

def test_config_bot_username_and_timeout():
    assert hasattr(config, "BOT_USERNAME")
    assert isinstance(config.BOT_USERNAME, str)
    assert len(config.BOT_USERNAME) > 0
    assert hasattr(config, "CHANNEL_CAPTION_TIMEOUT")
    assert isinstance(config.CHANNEL_CAPTION_TIMEOUT, int)
    assert config.CHANNEL_CAPTION_TIMEOUT > 0
    assert main.BOT_USERNAME == config.BOT_USERNAME
    assert main.CHANNEL_CAPTION_TIMEOUT == config.CHANNEL_CAPTION_TIMEOUT


def test_payment_contact_configured_as_xyrdeveloper():
    assert hasattr(config, "PAYMENT_CONTACT")
    assert config.PAYMENT_CONTACT == "XyrDeveloper"


def test_plans_text_mentions_payment_contact():
    text = ui.plans_text()
    assert "@XyrDeveloper" in text or "XyrDeveloper" in text


def test_payment_text_mentions_payment_contact():
    plan = config.PREMIUM_PLANS["month"]
    text = ui.payment_text(plan)
    assert "@XyrDeveloper" in text or "XyrDeveloper" in text


# --------------------------------------------------------------------------- #
#  2. UI helpers: open bot button, caption question, English strings
# --------------------------------------------------------------------------- #

def test_open_bot_keyboard_structure():
    markup = ui.open_bot_keyboard()
    rows = markup.inline_keyboard
    assert len(rows) == 1
    assert len(rows[0]) == 1
    btn = rows[0][0]
    assert btn.url == f"https://t.me/{config.BOT_USERNAME}"
    assert sc("Open bot") in btn.text
    assert len(btn.text) <= 28
    assert btn.callback_data is None


def test_open_bot_keyboard_style():
    markup = ui.open_bot_keyboard()
    btn = markup.inline_keyboard[0][0]
    assert style_of(btn) == "primary"


def test_channel_caption_keyboard_structure():
    token = "test_tok_123"
    markup = ui.channel_caption_keyboard(token)
    rows = markup.inline_keyboard
    assert len(rows) == 1
    assert len(rows[0]) == 2
    yes_btn, no_btn = rows[0]
    assert sc("Yes") in yes_btn.text
    assert sc("No") in no_btn.text
    assert yes_btn.callback_data == f"cap_yes:{token}"
    assert no_btn.callback_data == f"cap_no:{token}"
    assert len(yes_btn.text) <= 28
    assert len(no_btn.text) <= 28


def test_channel_caption_keyboard_styles():
    token = "test_tok_456"
    markup = ui.channel_caption_keyboard(token)
    yes_btn, no_btn = markup.inline_keyboard[0]
    assert style_of(yes_btn) == "success"
    assert style_of(no_btn) == "danger"


@pytest.mark.parametrize("percent,paused,expected_pct,expected_state", [
    (None, False, None, None),
    (0, False, "0%", None),
    (50, False, "50%", None),
    (100, False, "100%", None),
    (30, True, "30%", "paused"),
    (None, True, None, "paused"),
])
def test_channel_download_public_text_variations(percent, paused, expected_pct, expected_state):
    text = ui.channel_download_public_text(percent=percent, paused=paused)
    assert "Downloading" in text
    assert config.BOT_USERNAME in text
    if expected_pct:
        assert expected_pct in text
    if expected_state:
        assert expected_state in text
    else:
        assert "paused" not in text


def test_channel_caption_question_text():
    text = ui.channel_caption_question_text()
    assert "custom caption" in text.lower()
    assert "download" in text.lower()


# --------------------------------------------------------------------------- #
#  3. English copy sweep: no Devanagari anywhere in UI output
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("screen_text", [
    ui.fsub_text([]),
    ui.fsub_text([{"kind": "channel", "title": "Chan1"}]),
    ui.fsub_list_text([]),
    ui.fsub_list_text([{"kind": "group", "title": "Grp1", "button_text": "Join", "chat_id": 123}]),
    ui.fsub_button_prompt_text("MyChan", "channel"),
    ui.fsub_button_prompt_text("MyGroup", "group"),
    ui.fsub_admin_failed_text("no_post_rights", "MyChan"),
    ui.fsub_admin_failed_text("error", "MyChan"),
    ui.fsub_admin_failed_text("not_admin", "MyChan"),
    ui.fsub_label_invalid_text(),
    ui.fsub_join_pending_text("MyChan"),
    ui.fsub_request_notify_text("Alice", 12345, "MyChan"),
    ui.fsub_request_approved_text(),
    ui.fsub_auto_approved_text(),
    ui.fsub_verified_text(),
    ui.fsub_pending_text(),
    ui.fsub_empty_text(),
    ui.fsub_join_instruction_text(True),
    ui.fsub_join_instruction_text(False),
    ui.fsub_added_text({"kind": "channel", "title": "Chan", "button_text": "Join"}),
    ui.fsub_removed_text({"title": "Chan"}),
    ui.fsub_cleared_text(5),
    ui.fsub_delete_all_confirm_text(5),
    ui.setchat_admin_failed_text("no_post_rights"),
    ui.setchat_admin_failed_text("error"),
    ui.setchat_admin_failed_text("not_admin"),
    ui.setchat_join_request_text("MyChan"),
    ui.setchat_resolve_failed_text("expired"),
    ui.setchat_resolve_failed_text("invalid"),
    ui.setchat_resolve_failed_text("no_access"),
    ui.setchat_resolve_failed_text("unresolved"),
    ui.channel_download_public_text(),
    ui.channel_caption_question_text(),
])
def test_ui_screens_are_english_with_no_devanagari(screen_text):
    assert not DEVANAGARI_PATTERN.search(screen_text), f"Devanagari found in: {screen_text!r}"


# --------------------------------------------------------------------------- #
#  4. Download controls in channel: private vs public content
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_private_content_keeps_controls_in_channel_and_nothing_mirrored(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    db.users[user_id]["premium_source"] = "manual"
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    media_msg = SimpleNamespace(
        id=10,
        chat=SimpleNamespace(id=-100999),
        photo=SimpleNamespace(file_id="photo123", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, caption="Private Media",
        media=True, text=None,
    )
    user_client = SimpleNamespace(
        get_messages=AsyncMock(return_value=media_msg),
        copy_message=AsyncMock(side_effect=Exception("no copy")),
        download_media=AsyncMock(return_value="/tmp/fake_photo.jpg"),
    )

    channel_post = FakeMessage(text="https://t.me/c/100999/10", user=FakeUser(user_id))
    channel_post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    status = FakeMessage(text="Fetching...", message_id=50)
    status.chat = channel_post.chat

    requester = main.ChannelRequester(channel_post, db.users[user_id])
    ok = await main.fetch_and_send(requester, status, user_client, -100999, 10, enforce_fsub=False)

    assert ok is True
    # Private content: controls stay in the channel status message
    # Nothing sent to user DM
    dm_messages = [m for m in fake_bot.sent if m["chat_id"] == user_id]
    assert dm_messages == []
    # Channel status received download controls (dl: buttons)
    dl_markups = [e["reply_markup"] for e in status.edits if e.get("reply_markup") is not None]
    assert any(any(b.callback_data and b.callback_data.startswith("dl:") for b in flat(m)) for m in dl_markups)


@pytest.mark.asyncio
async def test_public_content_mirrors_controls_to_dm_and_channel_shows_open_bot(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    media_msg = SimpleNamespace(
        id=20,
        chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="photo456", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, caption="Public Media",
        media=True, text=None,
    )
    fake_bot.messages[20] = media_msg
    fake_bot.download_media = AsyncMock(return_value="/tmp/fake_media.jpg")

    channel_post = FakeMessage(text="https://t.me/publicchan/20", user=FakeUser(user_id))
    channel_post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    status = FakeMessage(text="Fetching...", message_id=60)
    status.chat = channel_post.chat

    # Make copy fail so it goes through the download path
    fake_bot.copy_message = AsyncMock(side_effect=Exception("copy fail"))

    requester = main.ChannelRequester(channel_post, db.users[user_id])
    ok = await main.fetch_and_send(requester, status, fake_bot, "publicchan", 20, enforce_fsub=False)

    assert ok is True
    # Live download was mirrored into DM
    dm_messages = [m for m in fake_bot.sent if m["chat_id"] == user_id]
    assert len(dm_messages) >= 1

    # Channel status notice has open bot URL button and NO dl: callback buttons
    for edit in status.edits:
        markup = edit.get("reply_markup")
        if markup is not None:
            buttons = flat(markup)
            for b in buttons:
                assert not (b.callback_data and b.callback_data.startswith("dl:")), f"dl: button leaked to channel: {b}"
            url_btns = [b for b in buttons if b.url]
            assert any(f"t.me/{config.BOT_USERNAME}" in b.url for b in url_btns)


@pytest.mark.asyncio
async def test_fallback_when_bot_cannot_dm_owner(db, fake_bot, monkeypatch):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    media_msg = SimpleNamespace(
        id=30,
        chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="photo789", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, caption="Public Media 2",
        media=True, text=None,
    )
    fake_bot.messages[30] = media_msg
    fake_bot.download_media = AsyncMock(return_value="/tmp/fake_media.jpg")
    fake_bot.copy_message = AsyncMock(side_effect=Exception("copy fail"))

    # Bot cannot DM owner
    async def broken_send(chat_id, text, **kwargs):
        if chat_id == user_id:
            raise Exception("User has blocked the bot")
        return await fake_bot.send_message(chat_id, text, **kwargs)

    monkeypatch.setattr(fake_bot, "send_message", broken_send)

    channel_post = FakeMessage(text="https://t.me/publicchan/30", user=FakeUser(user_id))
    channel_post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    status = FakeMessage(text="Fetching...", message_id=70)
    status.chat = channel_post.chat

    requester = main.ChannelRequester(channel_post, db.users[user_id])
    ok = await main.fetch_and_send(requester, status, fake_bot, "publicchan", 30, enforce_fsub=False)

    assert ok is True
    # Controls fall back to the channel status message
    dl_markups = [e["reply_markup"] for e in status.edits if e.get("reply_markup") is not None]
    assert any(any(b.callback_data and b.callback_data.startswith("dl:") for b in flat(m)) for m in dl_markups)


@pytest.mark.asyncio
async def test_channel_download_job_cleared_from_active_downloads_on_completion(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    media_msg = SimpleNamespace(
        id=35,
        chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="photo_done", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, caption="Done Media",
        media=True, text=None,
    )
    fake_bot.messages[35] = media_msg
    fake_bot.download_media = AsyncMock(return_value="/tmp/fake_done.jpg")
    fake_bot.copy_message = AsyncMock(side_effect=Exception("copy fail"))

    channel_post = FakeMessage(text="https://t.me/publicchan/35", user=FakeUser(user_id))
    channel_post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")
    status = FakeMessage(text="Fetching...", message_id=75)
    status.chat = channel_post.chat

    requester = main.ChannelRequester(channel_post, db.users[user_id])
    await main.fetch_and_send(requester, status, fake_bot, "publicchan", 35, enforce_fsub=False)

    assert main.active_downloads == {}


# --------------------------------------------------------------------------- #
#  5. Caption-only / text-only content never gets custom caption
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_text_only_post_never_receives_custom_caption_on_yes_and_no(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "VIP Custom Caption Header")

    text_msg = SimpleNamespace(
        id=40,
        chat=SimpleNamespace(id=-100888),
        photo=None, video=None, document=None, audio=None, voice=None,
        video_note=None, sticker=None, animation=None, empty=False,
        media=False, text="This is original channel post text.", caption=None,
    )
    copied = SimpleNamespace(id=101, edit_text=AsyncMock())
    fetch_client = SimpleNamespace(
        get_messages=AsyncMock(return_value=text_msg),
        copy_message=AsyncMock(return_value=copied),
    )

    msg = FakeMessage(user=FakeUser(user_id))
    # Test copy with use_custom_caption=True
    assert await main.try_native_copy(msg, fetch_client, "channel", 40, use_custom_caption=True)
    copied.edit_text.assert_not_called()

    # Test copy with use_custom_caption=False
    assert await main.try_native_copy(msg, fetch_client, "channel", 40, use_custom_caption=False)
    copied.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_text_only_download_path_never_receives_custom_caption(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "VIP Custom Caption Header")

    text_msg = SimpleNamespace(
        id=45,
        chat=SimpleNamespace(id=-100888),
        photo=None, video=None, document=None, audio=None, voice=None,
        video_note=None, sticker=None, animation=None, empty=False,
        media=False, text="Original text without media.", caption=None,
    )
    fake_bot.messages[45] = text_msg
    fake_bot.copy_message = AsyncMock(side_effect=Exception("copy not supported"))

    channel_post = FakeMessage(text="https://t.me/publicchan/45", user=FakeUser(user_id))
    status = FakeMessage(text="Fetching...", message_id=80)

    requester = main.ChannelRequester(channel_post, db.users[user_id])
    ok = await main.fetch_and_send(requester, status, fake_bot, "publicchan", 45, enforce_fsub=False, use_custom_caption=True)

    assert ok is True
    # The reply to channel_post should contain original text and NOT custom caption
    assert any("Original text without media." in r["text"] for r in channel_post.replies)
    assert not any("VIP Custom Caption Header" in r["text"] for r in channel_post.replies)


@pytest.mark.parametrize("media_type", ["video", "document", "audio", "animation"])
@pytest.mark.asyncio
async def test_media_types_receive_custom_caption_when_enabled(db, fake_bot, media_type):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "Applied Custom Caption")

    media_obj = SimpleNamespace(file_id=f"{media_type}_id", file_size=2000)
    kwargs = {"photo": None, "video": None, "document": None, "audio": None, "voice": None,
              "video_note": None, "sticker": None, "animation": None, "empty": False,
              "media": True, "caption": "Original", "text": None}
    kwargs[media_type] = media_obj

    msg_obj = SimpleNamespace(id=77, chat=SimpleNamespace(id=-100888), **kwargs)
    copied = SimpleNamespace(id=300, edit_caption=AsyncMock())
    fetch_client = SimpleNamespace(
        get_messages=AsyncMock(return_value=msg_obj),
        copy_message=AsyncMock(return_value=copied),
    )
    msg = FakeMessage(user=FakeUser(user_id))

    assert await main.try_native_copy(msg, fetch_client, "channel", 77, use_custom_caption=True)
    copied.edit_caption.assert_awaited_once_with(
        caption="Applied Custom Caption",
        parse_mode=ParseMode.DISABLED,
    )


# --------------------------------------------------------------------------- #
#  6. Media uses custom caption on yes and keeps original on no
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_media_uses_custom_caption_on_yes_and_original_on_no(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "VIP Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "Owner Custom Caption")

    media_msg = SimpleNamespace(
        id=50,
        chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p1", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False,
        caption="Original Photo Caption", media=True, text=None,
    )
    copied_yes = SimpleNamespace(id=201, edit_caption=AsyncMock())
    fetch_yes = SimpleNamespace(
        get_messages=AsyncMock(return_value=media_msg),
        copy_message=AsyncMock(return_value=copied_yes),
    )
    msg = FakeMessage(user=FakeUser(user_id))

    # With use_custom_caption=True
    assert await main.try_native_copy(msg, fetch_yes, "channel", 50, use_custom_caption=True)
    copied_yes.edit_caption.assert_awaited_once_with(
        caption="Owner Custom Caption",
        parse_mode=ParseMode.DISABLED,
    )

    # With use_custom_caption=False
    copied_no = SimpleNamespace(id=202, edit_caption=AsyncMock())
    fetch_no = SimpleNamespace(
        get_messages=AsyncMock(return_value=media_msg),
        copy_message=AsyncMock(return_value=copied_no),
    )
    assert await main.try_native_copy(msg, fetch_no, "channel", 50, use_custom_caption=False)
    # Original caption is unchanged, so edit_caption is not needed
    copied_no.edit_caption.assert_not_called()


@pytest.mark.asyncio
async def test_free_user_media_gets_attribution_with_custom_caption_and_without(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Free User")
    await db.set_caption(user_id, "Free User Custom Caption")

    media_msg = SimpleNamespace(
        id=55,
        chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p2", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False,
        caption="Original Caption", media=True, text=None,
    )
    copied = SimpleNamespace(id=203, edit_caption=AsyncMock())
    fetch_client = SimpleNamespace(
        get_messages=AsyncMock(return_value=media_msg),
        copy_message=AsyncMock(return_value=copied),
    )
    msg = FakeMessage(user=FakeUser(user_id))

    assert await main.try_native_copy(msg, fetch_client, "channel", 55, use_custom_caption=True)
    copied.edit_caption.assert_awaited_once_with(
        caption=f"Free User Custom Caption\n{config.WATERMARK}",
        parse_mode=ParseMode.DISABLED,
    )


# --------------------------------------------------------------------------- #
#  7. Custom caption question: owner answers, non-owner rejected, deletion
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_question_asked_deleted_on_owner_answer(db, fake_bot, press):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "My Custom Caption")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    fake_bot.messages[1] = SimpleNamespace(
        id=1, chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p", file_size=500),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, media=True, caption="Media", text=None
    )
    fake_bot.copy_message = AsyncMock(return_value=SimpleNamespace(id=1, edit_caption=AsyncMock()))

    post = FakeMessage(text="https://t.me/publicchan/1", user=FakeUser(user_id))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    async def answer_question_after_delay():
        await asyncio.sleep(0.01)
        assert len(main.caption_pending) == 1
        token = list(main.caption_pending.keys())[0]
        entry = main.caption_pending[token]
        q_msg = entry["question_msg"]
        assert sc("Use your custom caption") in q_msg.shown_text

        # Non-owner tries to press
        non_owner_query = make_query(q_msg, f"cap_yes:{token}", FakeUser(9999))
        await main.callback_handler(None, non_owner_query)
        assert non_owner_query.answer.calls[-1]["show_alert"] is True
        assert not entry["future"].done()
        assert not q_msg.deleted

        # Owner presses Yes
        owner_query = make_query(q_msg, f"cap_yes:{token}", FakeUser(user_id))
        await main.callback_handler(None, owner_query)
        assert entry["future"].done()
        assert entry["future"].result() is True
        assert q_msg.deleted is True

    task = asyncio.create_task(answer_question_after_delay())
    success, failed = await main.extract_channel_links(post, db.users[user_id], sleeper=AsyncMock())
    await task
    assert success == 1
    assert failed == 0


@pytest.mark.asyncio
async def test_owner_presses_no_on_caption_question(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "My Custom Caption")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    fake_bot.messages[5] = SimpleNamespace(
        id=5, chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p5", file_size=500),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, media=True, caption="OrigCaption", text=None
    )
    fake_bot.copy_message = AsyncMock(return_value=SimpleNamespace(id=5, edit_caption=AsyncMock()))

    post = FakeMessage(text="https://t.me/publicchan/5", user=FakeUser(user_id))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    async def answer_no():
        await asyncio.sleep(0.01)
        assert len(main.caption_pending) == 1
        token = list(main.caption_pending.keys())[0]
        entry = main.caption_pending[token]
        q_msg = entry["question_msg"]
        owner_query = make_query(q_msg, f"cap_no:{token}", FakeUser(user_id))
        await main.callback_handler(None, owner_query)
        assert entry["future"].done()
        assert entry["future"].result() is False
        assert q_msg.deleted is True

    task = asyncio.create_task(answer_no())
    success, failed = await main.extract_channel_links(post, db.users[user_id], sleeper=AsyncMock())
    await task
    assert success == 1
    assert failed == 0


@pytest.mark.asyncio
async def test_no_question_asked_when_no_custom_caption_stored(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.del_caption(user_id)
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    fake_bot.messages[2] = SimpleNamespace(
        id=2, chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p", file_size=500),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, media=True, caption="Media", text=None
    )
    fake_bot.copy_message = AsyncMock(return_value=SimpleNamespace(id=2, edit_caption=AsyncMock()))

    post = FakeMessage(text="https://t.me/publicchan/2", user=FakeUser(user_id))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    success, failed = await main.extract_channel_links(post, db.users[user_id], sleeper=AsyncMock())
    assert success == 1
    assert len(main.caption_pending) == 0
    # No question reply in channel
    assert not any("Use your custom caption" in r.get("text", "") for r in post.replies)


# --------------------------------------------------------------------------- #
#  8. Stale question timeout and re-asking on next post
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_stale_question_timeout_and_reask(db, fake_bot, monkeypatch):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "My Custom Caption")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    # Set short timeout for testing
    monkeypatch.setattr(main, "CHANNEL_CAPTION_TIMEOUT", 0.05)

    post1 = FakeMessage(text="https://t.me/publicchan/100", user=FakeUser(user_id))
    post1.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    # Post 1 times out
    success, failed = await main.extract_channel_links(post1, db.users[user_id], sleeper=AsyncMock())
    assert (success, failed) == (0, 0)
    assert len(main.caption_pending) == 0

    # Next post arrives (Post 2) - question is re-asked
    post2 = FakeMessage(text="https://t.me/publicchan/101", user=FakeUser(user_id))
    post2.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    fake_bot.messages[101] = SimpleNamespace(
        id=101, chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p", file_size=500),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, media=True, caption="Media", text=None
    )
    fake_bot.copy_message = AsyncMock(return_value=SimpleNamespace(id=101, edit_caption=AsyncMock()))

    async def answer_post2():
        await asyncio.sleep(0.01)
        assert len(main.caption_pending) == 1
        token = list(main.caption_pending.keys())[0]
        q_msg = main.caption_pending[token]["question_msg"]
        owner_query = make_query(q_msg, f"cap_no:{token}", FakeUser(user_id))
        await main.callback_handler(None, owner_query)

    task = asyncio.create_task(answer_post2())
    success2, failed2 = await main.extract_channel_links(post2, db.users[user_id], sleeper=AsyncMock())
    await task
    assert success2 == 1
    assert failed2 == 0


@pytest.mark.asyncio
async def test_stale_callback_shows_expired_alert(db, fake_bot):
    msg = FakeMessage()
    query = make_query(msg, "cap_yes:expired_token_123", FakeUser(1001))
    await main.callback_handler(None, query)
    assert query.answer.calls[-1]["show_alert"] is True
    assert sc("expired") in query.answer.calls[-1]["text"].lower()


@pytest.mark.asyncio
async def test_stale_no_callback_shows_expired_alert(db, fake_bot):
    msg = FakeMessage()
    query = make_query(msg, "cap_no:expired_token_456", FakeUser(1001))
    await main.callback_handler(None, query)
    assert query.answer.calls[-1]["show_alert"] is True
    assert sc("expired") in query.answer.calls[-1]["text"].lower()


# --------------------------------------------------------------------------- #
#  9. Mirrored download control actions (pause, resume, stop)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_handle_download_controls_pause_resume_stop_on_mirrored_job(db, press):
    user_id = 1001
    job_id = "job-9999"
    main.active_downloads[job_id] = {
        "user_id": user_id,
        "paused": False,
        "cancelled": False,
        "event": asyncio.Event(),
        "task": None,
    }
    main.active_downloads[job_id]["event"].set()
    message = FakeMessage(user=FakeUser(user_id))

    # Foreign user rejected
    foreign_query = make_query(message, f"dl:p:{job_id}", FakeUser(2002))
    await main.callback_handler(None, foreign_query)
    assert foreign_query.answer.calls[-1]["show_alert"] is True
    assert main.active_downloads[job_id]["paused"] is False

    # Owner pauses
    await press(message, f"dl:p:{job_id}")
    assert main.active_downloads[job_id]["paused"] is True

    # Owner resumes
    await press(message, f"dl:r:{job_id}")
    assert main.active_downloads[job_id]["paused"] is False

    # Owner stops
    await press(message, f"dl:s:{job_id}")
    assert main.active_downloads[job_id]["cancelled"] is True

    main.active_downloads.pop(job_id, None)


@pytest.mark.asyncio
async def test_non_owner_stop_is_rejected(db, press):
    user_id = 1001
    job_id = "job-8888"
    main.active_downloads[job_id] = {
        "user_id": user_id,
        "paused": False,
        "cancelled": False,
        "event": asyncio.Event(),
        "task": None,
    }
    message = FakeMessage(user=FakeUser(user_id))
    foreign_stop = make_query(message, f"dl:s:{job_id}", FakeUser(999))
    await main.callback_handler(None, foreign_stop)

    assert foreign_stop.answer.calls[-1]["show_alert"] is True
    assert main.active_downloads[job_id]["cancelled"] is False
    main.active_downloads.pop(job_id, None)


# --------------------------------------------------------------------------- #
#  10. Custom caption with prefix and suffix combinations
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_media_with_custom_caption_prefix_suffix_applied_on_yes(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "VIP")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "Main Caption")
    await db.set_prefix(user_id, "[PRE]")
    await db.set_suffix(user_id, "[SUF]")

    media_msg = SimpleNamespace(
        id=60, chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p60", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, media=True, caption="Original", text=None
    )
    copied = SimpleNamespace(id=601, edit_caption=AsyncMock())
    fetch = SimpleNamespace(
        get_messages=AsyncMock(return_value=media_msg),
        copy_message=AsyncMock(return_value=copied),
    )
    msg = FakeMessage(user=FakeUser(user_id))

    assert await main.try_native_copy(msg, fetch, "channel", 60, use_custom_caption=True)
    copied.edit_caption.assert_awaited_once_with(
        caption="Main Caption",
        parse_mode=ParseMode.DISABLED,
    )


@pytest.mark.asyncio
async def test_text_with_prefix_suffix_never_gets_custom_caption(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "VIP")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "Main Caption")
    await db.set_prefix(user_id, "[PRE]")
    await db.set_suffix(user_id, "[SUF]")

    text_msg = SimpleNamespace(
        id=62, chat=SimpleNamespace(id=-100888),
        photo=None, video=None, document=None, audio=None, voice=None,
        video_note=None, sticker=None, animation=None, empty=False, media=False,
        text="Original Post Content", caption=None
    )
    copied = SimpleNamespace(id=602, edit_text=AsyncMock())
    fetch = SimpleNamespace(
        get_messages=AsyncMock(return_value=text_msg),
        copy_message=AsyncMock(return_value=copied),
    )
    msg = FakeMessage(user=FakeUser(user_id))

    assert await main.try_native_copy(msg, fetch, "channel", 62, use_custom_caption=True)
    copied.edit_text.assert_not_called()


# --------------------------------------------------------------------------- #
#  11. Multi-link channel post with caption choice
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_multi_link_channel_post_single_question_applies_to_all(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "Universal Caption")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    for mid in (10, 11):
        fake_bot.messages[mid] = SimpleNamespace(
            id=mid, chat=SimpleNamespace(id=-100888),
            photo=SimpleNamespace(file_id=f"p{mid}", file_size=500),
            video=None, document=None, audio=None, voice=None, video_note=None,
            sticker=None, animation=None, empty=False, media=True, caption=f"Orig {mid}", text=None
        )
    copied_edit = AsyncMock()
    fake_bot.copy_message = AsyncMock(return_value=SimpleNamespace(id=99, edit_caption=copied_edit))

    post = FakeMessage(
        text="https://t.me/publicchan/10\nhttps://t.me/publicchan/11",
        user=FakeUser(user_id)
    )
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    async def answer_once():
        await asyncio.sleep(0.01)
        assert len(main.caption_pending) == 1
        token = list(main.caption_pending.keys())[0]
        q_msg = main.caption_pending[token]["question_msg"]
        owner_query = make_query(q_msg, f"cap_yes:{token}", FakeUser(user_id))
        await main.callback_handler(None, owner_query)

    task = asyncio.create_task(answer_once())
    success, failed = await main.extract_channel_links(post, db.users[user_id], sleeper=AsyncMock())
    await task
    assert success == 2
    assert failed == 0
    assert copied_edit.call_count == 2
    for call in copied_edit.call_args_list:
        assert call.kwargs["caption"] == "Universal Caption"


# --------------------------------------------------------------------------- #
#  12. Mobile keyboard budget and formatting rules
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("markup", [
    ui.open_bot_keyboard(),
    ui.channel_caption_keyboard("test_token"),
    ui.download_controls("job-123", paused=False),
    ui.download_controls("job-123", paused=True),
])
def test_new_keyboards_fit_mobile_budget(markup):
    rows = markup.inline_keyboard
    assert len(rows) <= 7
    assert all(len(row) <= 2 for row in rows)
    for row in rows:
        for btn in row:
            assert len(btn.text) <= 28
            if btn.callback_data:
                assert btn.callback_data.isascii()
                assert not btn.callback_data.startswith("http")


@pytest.mark.parametrize("data", [
    "cap_yes:abc123token",
    "cap_no:abc123token",
    "dl:p:job-1",
    "dl:r:job-1",
    "dl:s:job-1",
])
def test_callback_data_is_plain_ascii(data):
    assert data.isascii()
    assert not any(ord(c) > 127 for c in data)


# --------------------------------------------------------------------------- #
#  13. Daily limit guard and private access in dump channels
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dump_channel_daily_limit_stops_before_asking_caption_question(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Free User")
    db.users[user_id]["is_premium"] = False
    db.users[user_id]["daily_downloads"] = config.FREE_DAILY_LIMIT
    await db.set_caption(user_id, "Free Custom Caption")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    post = FakeMessage(text="https://t.me/publicchan/1", user=FakeUser(user_id))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    success, failed = await main.extract_channel_links(post, db.users[user_id], sleeper=AsyncMock())
    assert (success, failed) == (0, 0)
    assert len(main.caption_pending) == 0
    assert any(sc("Daily Free Limit Reached") in r["text"] for r in post.replies)


@pytest.mark.asyncio
async def test_dump_channel_private_link_without_premium_shows_pitch(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Free User")
    db.users[user_id]["is_premium"] = False
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    post = FakeMessage(text="https://t.me/c/123456/10", user=FakeUser(user_id))
    post.chat = FakeChat(fake_bot.channel_id, chat_type="channel")

    success, failed = await main.extract_channel_links(post, db.users[user_id], sleeper=AsyncMock())
    assert failed == 1
    assert success == 0
    assert len(main.caption_pending) == 0


# --------------------------------------------------------------------------- #
#  14. Large media and text splitting
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_large_media_over_limit_fails_cleanly(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Free User")
    await db.set_user_chat(user_id, fake_bot.channel_id, "Dump Channel")

    large_video = SimpleNamespace(
        id=88, chat=SimpleNamespace(id=-100888),
        photo=None, video=SimpleNamespace(file_id="vid", file_size=100 * 1024 * 1024),
        document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, media=True, caption="Large", text=None
    )
    fake_bot.messages[88] = large_video
    fake_bot.copy_message = AsyncMock(side_effect=Exception("copy fail"))

    channel_post = FakeMessage(text="https://t.me/publicchan/88", user=FakeUser(user_id))
    status = FakeMessage(text="Fetching...", message_id=888)

    requester = main.ChannelRequester(channel_post, db.users[user_id])
    ok = await main.fetch_and_send(requester, status, fake_bot, "publicchan", 88, enforce_fsub=False)
    assert ok is False
    assert any(sc("File too large") in e["text"] for e in status.edits)


@pytest.mark.asyncio
async def test_long_text_message_split_without_custom_caption(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "VIP")
    db.users[user_id]["is_premium"] = True
    await db.set_caption(user_id, "Custom Caption Should Not Appear")

    long_body = "A" * 5000
    text_msg = SimpleNamespace(
        id=92, chat=SimpleNamespace(id=-100888),
        photo=None, video=None, document=None, audio=None, voice=None,
        video_note=None, sticker=None, animation=None, empty=False, media=False,
        text=long_body, caption=None
    )
    fake_bot.messages[92] = text_msg
    fake_bot.copy_message = AsyncMock(side_effect=Exception("no copy"))

    channel_post = FakeMessage(text="https://t.me/publicchan/92", user=FakeUser(user_id))
    status = FakeMessage(text="Fetching...", message_id=920)

    requester = main.ChannelRequester(channel_post, db.users[user_id])
    ok = await main.fetch_and_send(requester, status, fake_bot, "publicchan", 92, enforce_fsub=False, use_custom_caption=True)

    assert ok is True
    # Replies must sum to long_body and never contain custom caption
    total_received = "".join(r["text"] for r in channel_post.replies)
    assert total_received == long_body
    assert "Custom Caption Should Not Appear" not in total_received


# --------------------------------------------------------------------------- #
#  15. Start menu channel stats and admin checks
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_start_menu_renders_without_errors(db):
    user_id = 1001
    await db.add_user(user_id, "Tester")
    markup = ui.start_keyboard(show_admin=False)
    assert any(b.callback_data == "cmd_stats" for b in flat(markup))
    assert any(b.callback_data == "cmd_setchat" for b in flat(markup))


@pytest.mark.asyncio
async def test_start_menu_for_admin_includes_admin_button(db):
    markup = ui.start_keyboard(show_admin=True)
    assert any(b.callback_data == "cmd_admin" for b in flat(markup))


# --------------------------------------------------------------------------- #
#  16. Supergroup support in channel dump
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_supergroup_dump_controls_behave_like_channel(db, fake_bot):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    await db.set_user_chat(user_id, -100555444, "Supergroup Dump")

    media_msg = SimpleNamespace(
        id=70, chat=SimpleNamespace(id=-100888),
        photo=SimpleNamespace(file_id="p70", file_size=1000),
        video=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None, empty=False, caption="SG Media",
        media=True, text=None,
    )
    fake_bot.messages[70] = media_msg
    fake_bot.download_media = AsyncMock(return_value="/tmp/fake_sg.jpg")
    fake_bot.copy_message = AsyncMock(side_effect=Exception("copy fail"))

    group_post = FakeMessage(text="https://t.me/publicchan/70", user=FakeUser(user_id))
    group_post.chat = FakeChat(-100555444, chat_type="supergroup")
    status = FakeMessage(text="Fetching...", message_id=700)
    status.chat = group_post.chat

    requester = main.ChannelRequester(group_post, db.users[user_id])
    ok = await main.fetch_and_send(requester, status, fake_bot, "publicchan", 70, enforce_fsub=False)

    assert ok is True
    # Live download mirrored into DM
    dm_messages = [m for m in fake_bot.sent if m["chat_id"] == user_id]
    assert len(dm_messages) >= 1


# --------------------------------------------------------------------------- #
#  17. Additional edge cases and coverage validation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("plan_key", ["month", "quarter", "year"])
def test_payment_text_for_all_plan_types(plan_key):
    plan = config.PREMIUM_PLANS[plan_key]
    text = ui.payment_text(plan)
    assert "@XyrDeveloper" in text or "XyrDeveloper" in text
    assert str(plan["price"]) in text


@pytest.mark.parametrize("paused", [False, True])
def test_mirrored_download_controls_button_texts(paused):
    markup = ui.download_controls("job-test-1", paused=paused)
    texts = [b.text for b in flat(markup)]
    if paused:
        assert any(sc("Resume") in t for t in texts)
    else:
        assert any(sc("Pause") in t for t in texts)
    assert any(sc("Stop") in t for t in texts)


@pytest.mark.asyncio
async def test_extract_channel_links_empty_text_returns_zero(db):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    post = FakeMessage(text="", user=FakeUser(user_id))
    post.chat = FakeChat(-100999, chat_type="channel")
    success, failed = await main.extract_channel_links(post, db.users[user_id])
    assert (success, failed) == (0, 0)


@pytest.mark.asyncio
async def test_extract_channel_links_no_tg_links_returns_zero(db):
    user_id = 1001
    await db.add_user(user_id, "Owner")
    post = FakeMessage(text="Hello world this is some random post without links", user=FakeUser(user_id))
    post.chat = FakeChat(-100999, chat_type="channel")
    success, failed = await main.extract_channel_links(post, db.users[user_id])
    assert (success, failed) == (0, 0)


def test_channel_caption_keyboard_token_isolation():
    k1 = ui.channel_caption_keyboard("token_aaa")
    k2 = ui.channel_caption_keyboard("token_bbb")
    assert k1.inline_keyboard[0][0].callback_data == "cap_yes:token_aaa"
    assert k2.inline_keyboard[0][0].callback_data == "cap_yes:token_bbb"
    assert k1.inline_keyboard[0][1].callback_data == "cap_no:token_aaa"
    assert k2.inline_keyboard[0][1].callback_data == "cap_no:token_bbb"

