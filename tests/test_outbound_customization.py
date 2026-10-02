"""Reply-scoped broadcasts, dump-first custom messages, and pin actions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import main
import ui
from conftest import DEFAULT_USER_ID, FAKE_BOT_ID, FakeChat, FakeMessage, FakeUser, sc, make_member, drain_background
from pyrogram.enums import ChatMemberStatus

OWNER = main.OWNER_ID
USER = DEFAULT_USER_ID
CHANNEL = -100777


@pytest.fixture(autouse=True)
def staging_permissions(fake_bot):
    fake_bot.members[(CHANNEL, FAKE_BOT_ID)] = make_member(
        ChatMemberStatus.ADMINISTRATOR, can_post_messages=True, can_delete_messages=True)


def texts(message):
    return "\n".join([entry["text"] for entry in message.replies]
                     + [entry["text"] for entry in message.edits])


def owner_message(text, *, message_id=1):
    return FakeMessage(text=text, user=FakeUser(OWNER), message_id=message_id)


def source_message(text="Reusable announcement", *, message_id=77, chat_id=None):
    source = FakeMessage(text=text, user=FakeUser(OWNER), message_id=message_id)
    source.chat = FakeChat(OWNER if chat_id is None else chat_id)
    return source


async def test_broadcast_replies_are_staged_then_copied_to_channel_and_users(
        db, fake_bot, press):
    await db.add_user(OWNER, "Owner")
    await db.add_user(USER, "Reader")
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    request = owner_message("/broadcast")
    request.reply_to_message = source_message()

    await main.broadcast_handler(None, request)
    await drain_background()

    assert {item[0] for item in fake_bot.copies} == {CHANNEL, USER}
    assert (CHANNEL, OWNER, 77) in fake_bot.copies
    stage_id = 5000  # FakeBot assigns this ID to the temporary staged copy.
    assert (CHANNEL, CHANNEL, stage_id) not in fake_bot.copies
    assert (USER, CHANNEL, stage_id) in fake_bot.copies
    assert (CHANNEL, stage_id) in fake_bot.deleted
    assert sc("BROADCAST COMPLETE") in texts(request)


async def test_botcast_sends_only_to_bot_users(db, fake_bot):
    await db.add_user(OWNER, "Owner")
    await db.add_user(USER, "Reader")
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    request = owner_message("/botcast Hello bot users")

    await main.botcast_handler(None, request)
    await drain_background()

    destinations = {entry["chat_id"] for entry in fake_bot.sent}
    assert USER in destinations
    assert CHANNEL not in destinations
    assert sc("Bot users: 1/1") in texts(request)


async def test_broadcast_posts_typed_text_to_channel_and_bot_users(db, fake_bot):
    await db.add_user(OWNER, "Owner")
    await db.add_user(USER, "Reader")
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    request = owner_message("/broadcast New release")

    await main.broadcast_handler(None, request)
    await drain_background()

    destinations = {entry["chat_id"] for entry in fake_bot.sent}
    assert destinations == {USER}
    assert sc("Channels: 0/0") in texts(request)
    assert sc("Bot users: 1/1") in texts(request)


async def test_menu_offers_reply_actions_and_pin_broadcasts_then_pins(
        db, fake_bot, press):
    await db.add_user(OWNER, "Owner")
    await db.add_user(USER, "Reader")
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    request = owner_message("/menu")
    request.reply_to_message = source_message("Keep this post")

    await main.message_menu_handler(None, request)

    assert {"msgmenu:pin", "msgmenu:unpin", "msgmenu:broadcast",
            "msgmenu:botcast", "msgmenu:cmsg"} <= set(request.callback_data())
    await press(request, "msgmenu:pin")
    await drain_background()

    assert {USER} == {chat_id for chat_id, _message_id in fake_bot.pinned}
    assert sc("Private-chat pins are best-effort") in texts(request)
    stage_id = 5000  # FakeBot assigns this ID to the temporary staged copy.
    assert (CHANNEL, stage_id) in fake_bot.deleted


async def test_cmsg_stages_a_custom_message_with_coloured_buttons(db, fake_bot, press):
    await db.add_user(OWNER, "Owner")
    await db.add_user(USER, "Reader")
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    request = owner_message("/cMSG Join the launch")

    await main.cmsg_handler(None, request)
    await press(request, "btnwiz:yes")
    await press(request, "btnwiz:color:green")
    await main.text_handler(None, FakeMessage(text="Join now", user=FakeUser(OWNER)))
    await main.text_handler(None, FakeMessage(text="example.com", user=FakeUser(OWNER)))
    await press(request, "btnwiz:send")
    await drain_background()

    assert {USER} == {chat_id for chat_id, _from_chat, _message in fake_bot.copies}
    staged = fake_bot.sent[0]
    assert staged["chat_id"] == CHANNEL and staged["text"] == "Join the launch"
    assert staged["reply_markup"].inline_keyboard[0][0].style is ui.BUTTON_SUCCESS
    assert (CHANNEL, 1000) in fake_bot.deleted
    final_copies = [entry for entry in fake_bot.sent if "copy_from" in entry]
    assert final_copies and all(entry["reply_markup"] is not None for entry in final_copies)
    assert fake_bot.edited == [], "the delivered text/caption is never edited"
    assert sc("BROADCAST COMPLETE") in texts(request)


async def test_media_download_is_uploaded_to_dump_copied_to_user_and_cleaned(
        db, fake_bot, tmp_path):
    source_chat = -100888
    await db.add_user(USER, "Reader")
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    local_file = tmp_path / "staged-video.mp4"
    local_file.write_bytes(b"video")
    message = FakeMessage(text="t.me/example/77", user=FakeUser(USER))
    message.chat = FakeChat(USER)
    source = SimpleNamespace(
        id=77, empty=False, chat=FakeChat(source_chat), text=None,
        caption="Original caption", media=True,
        video=SimpleNamespace(file_id="v1", file_size=4096),
        photo=None, document=None, audio=None, voice=None, video_note=None,
        sticker=None, animation=None,
    )
    fake_bot.messages[77] = source
    uploads = []

    async def download(_message, **kwargs):
        return str(local_file)

    async def upload(chat_id, _file, **kwargs):
        uploads.append(chat_id)
        return SimpleNamespace(id=7000)

    original_copy = fake_bot.copy_message

    async def fail_source_copy_then_copy_stage(chat_id, from_chat_id, message_id, **kwargs):
        if from_chat_id == source_chat:
            raise RuntimeError("source copy is unavailable")
        return await original_copy(chat_id, from_chat_id, message_id, **kwargs)

    fake_bot.download_media = download
    fake_bot.send_video = upload
    fake_bot.copy_message = fail_source_copy_then_copy_stage

    result = await main.fetch_and_send(
        message, FakeMessage(text="Working"), fake_bot, "example", 77,
        enforce_fsub=False,
    )

    assert result is True
    assert uploads == [CHANNEL], "the edited media is uploaded to the dump first"
    assert (USER, CHANNEL, 7000) in fake_bot.copies
    assert (CHANNEL, 7000) in fake_bot.deleted
    assert not local_file.exists(), "the downloaded file is cleaned after delivery"


async def test_direct_sendmsg_custom_message_uses_dump_before_the_dm(db, fake_bot, press):
    target = 24680
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    request = owner_message(f"/sendmsg {target} Your custom note")

    await main.sendmsg_handler(None, request)
    await press(request, "btnwiz:skip")

    stage = fake_bot.sent[0]
    assert stage["chat_id"] == CHANNEL and "Your custom note" in stage["text"]
    assert (target, CHANNEL, 1000) in fake_bot.copies
    assert (CHANNEL, 1000) in fake_bot.deleted
    assert fake_bot.edited == []


def test_giveaway_template_replaces_each_empty_bracket_pair():
    template = "🎁 Join now: [] participants. Count: []!"
    assert ui.giveaway_public_text({"custom_message": template}, 17) == (
        "🎁 Join now: 17 participants. Count: 17!")


async def test_custom_giveaway_announcement_is_sent_and_pinned_in_bot_users_chats(
        db, fake_bot):
    await db.add_user(OWNER, "Owner")
    await db.add_user(USER, "Reader")
    await db.add_user(2002, "Another reader")
    await db.create_giveaway({
        "token": "abc12345", "status": "running", "created_by": OWNER,
        "custom_message": "🎁 We have [] participants; you could be number [].",
    })
    await db.add_giveaway_participant("active", 3001)
    await db.add_giveaway_participant("active", 3002)

    report = await main.run_giveaway_broadcast(await db.get_active_giveaway())

    messages = [entry for entry in fake_bot.sent
                if entry["chat_id"] in {USER, 2002}]
    assert [entry["text"] for entry in messages] == [
        "🎁 We have 2 participants; you could be number 2.",
        "🎁 We have 2 participants; you could be number 2.",
    ]
    assert report["total"] == report["sent"] == 2
    assert report["pin_attempted"] == report["pin_succeeded"] == 2
    assert {chat_id for chat_id, _message_id in fake_bot.pinned} == {USER, 2002}
    report_text = ui.giveaway_broadcast_report_text(report)
    assert "Telegram may not allow bots to pin messages in private chats." in report_text


async def test_giveaway_custom_template_cancel_clears_the_wizard(db, fake_bot, press):
    main.GIVEAWAY_WIZARD[OWNER] = {"step": "custom"}
    main.pending_action[OWNER] = "gw_custom_message"
    message = owner_message("Choose a custom announcement")

    await press(message, "gw:cancel")

    assert OWNER not in main.GIVEAWAY_WIZARD
    assert OWNER not in main.pending_action
    assert sc("Action cancelled") in texts(message)


async def test_unpin_command_removes_the_configured_channel_pin(db, fake_bot):
    await db.set_dump_channel(CHANNEL, "Dump", "dump", "channel")
    fake_bot.chats[CHANNEL] = SimpleNamespace(
        id=CHANNEL, title="Dump", username="dump", type="channel",
        pinned_message=SimpleNamespace(id=900),
    )
    request = owner_message("/unpin")

    await main.unpin_handler(None, request)

    assert fake_bot.unpinned == [(CHANNEL, 900)]
    assert sc("Pins removed: 1") in texts(request)
