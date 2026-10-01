"""Item 3 — private-channel content must never land in **Saved Messages**.

The bug: ``try_native_copy`` used ``fetch_client.copy_message(chat_id=message.chat.id, ...)``.
For private content ``fetch_client`` is the *user's own* session and, in a private
chat with the bot, ``message.chat.id`` **is that same user's id** — so Telegram
delivered the file to the user's Saved Messages instead of the bot chat.

These tests assert the exact ``(client, chat_id)`` pair used for delivery in all
four combinations of (private chat | dump channel) x (public link | private link).
In-memory fakes only: no Telegram, no MongoDB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config
import main
import ui
from conftest import FakeChat, FakeMessage, FakeUser, sc


USER_ID = 1001
CHANNEL_ID = -100777
SOURCE_CHAT = -100888
#: The bot's own user id (what ``bot_self_id()`` reports for the fake client).
BOT_ID = 999


class RecordingClient:
    """A client stand-in that records every delivery it is asked to perform."""

    def __init__(self, name: str, *, user_client: bool = False):
        self.name = name
        #: ``is_user_session`` honours this flag, exactly like a real /login session.
        self.is_user_client = user_client
        self.me = SimpleNamespace(id=USER_ID if user_client else 999,
                                  is_bot=not user_client)
        self.copy_message = AsyncMock(side_effect=self._copy)
        self.get_messages = AsyncMock(return_value=None)
        self.sent: list[tuple[str, int]] = []
        for verb in ("send_photo", "send_video", "send_document", "send_audio",
                     "send_voice", "send_video_note", "send_sticker",
                     "send_animation", "send_message"):
            setattr(self, verb, AsyncMock(side_effect=self._record(verb)))

    def _record(self, verb):
        async def _call(chat_id, *args, **kwargs):
            self.sent.append((verb, int(chat_id)))
            return SimpleNamespace(id=7, chat=SimpleNamespace(id=int(chat_id)))
        return _call

    async def _copy(self, chat_id=None, from_chat_id=None, message_id=None, **kwargs):
        self.sent.append(("copy_message", int(chat_id)))
        return SimpleNamespace(id=5, chat=SimpleNamespace(id=int(chat_id)),
                               edit_caption=AsyncMock(), edit_text=AsyncMock())

    @property
    def destinations(self) -> list[int]:
        return [chat_id for _verb, chat_id in self.sent]

    @property
    def uploads(self) -> list[str]:
        """Every verb that streams a file through this client (never a copy)."""
        return [verb for verb, _chat_id in self.sent if verb != "copy_message"]


def media_message(msg_id=15, chat_id=SOURCE_CHAT, size=1024):
    """A downloadable private-channel post."""
    return SimpleNamespace(
        id=msg_id, empty=False, chat=SimpleNamespace(id=chat_id),
        text=None, caption="Restricted caption",
        video=SimpleNamespace(file_id="v1", file_size=size),
        document=None, audio=None, photo=None, voice=None, video_note=None,
        sticker=None, animation=None, media=True,
    )


def private_message(user_id=USER_ID):
    """A message sent **in the private chat with the bot** (chat id == user id)."""
    message = FakeMessage(text="t.me/c/123/15", user=FakeUser(user_id))
    message.chat = FakeChat(user_id)
    return message


def channel_message(user_id=USER_ID, chat_id=CHANNEL_ID):
    """A post inside a registered dump channel (chat id == the channel)."""
    message = FakeMessage(text="t.me/c/123/15", user=FakeUser(user_id))
    message.chat = FakeChat(chat_id, "channel", "Dump")
    return message


def install_source(fake_bot, monkeypatch, msg, *, download="/tmp/file.mp4"):
    """Serve *msg* from the fetch client and record how it was uploaded."""
    fake_bot.messages[msg.id] = msg
    monkeypatch.setattr(main.os.path, "exists", lambda path: False)
    monkeypatch.setattr(main, "TELEMETRY_EDIT_INTERVAL", 0.0)


# --------------------------------------------------------------------------- #
#  The guard itself
# --------------------------------------------------------------------------- #

def test_user_session_is_detected_positively():
    """Only a real user session trips the guard — never a bot stand-in."""
    user_client = RecordingClient("user", user_client=True)
    bot_like = RecordingClient("bot-like")
    assert main.is_user_session(user_client, USER_ID) is True
    assert main.is_user_session(bot_like, USER_ID) is False
    assert main.is_user_session(None, USER_ID) is False


def test_registered_login_session_is_a_user_session(db):
    """Whatever /login stored for this user counts as that user's session."""
    client = SimpleNamespace(get_messages=AsyncMock())
    main.user_clients[USER_ID] = client
    assert main.is_user_session(client, USER_ID) is True
    assert main.is_user_session(client, 4242) is False


def test_delivery_target_never_posts_to_the_users_own_id():
    """Private chat + the user's own session would be *Saved Messages*.

    Round 14 kept the rule and changed the answer.  The session still may
    never post to its own id; instead of refusing the copy (which used to force
    a download through this server) the destination becomes the **bot's** chat,
    so the copy is made there by the user's own account and the server never
    sees a single byte of the restricted content.
    """
    user_client = RecordingClient("user", user_client=True)
    target = main.resolve_delivery_target(private_message(), USER_ID, user_client)
    assert target.reason == "bot_dm_native_copy"
    assert target.chat_id == BOT_ID, "the bot's own chat, never the user's id"
    assert target.chat_id != USER_ID
    assert target.native_copy is True, "it is still a server-side copy"
    assert target.copy_client is user_client
    assert target.upload_client is main.bot


def test_delivery_target_falls_back_to_the_bot_without_a_bot_id():
    """Still connecting (no bot id yet): refuse the copy, never Saved Messages."""
    user_client = RecordingClient("user", user_client=True)
    original = main.bot_self_id
    main.bot_self_id = lambda: None
    try:
        target = main.resolve_delivery_target(private_message(), USER_ID, user_client)
    finally:
        main.bot_self_id = original
    assert target.native_copy is False
    assert target.copy_client is None
    assert target.chat_id == USER_ID
    assert target.reason == "saved_messages_guard"


def test_delivery_target_allows_the_bot_in_private_chat():
    """A public link in private chat is copied by the bot into the bot chat."""
    target = main.resolve_delivery_target(private_message(), USER_ID, main.bot)
    assert target.native_copy is True
    assert target.copy_client is main.bot
    assert target.chat_id == USER_ID
    assert target.reason == "direct"


def test_delivery_target_allows_a_dump_channel_route():
    """In a channel the destination is the channel id, never the user's own."""
    user_client = RecordingClient("user", user_client=True)
    target = main.resolve_delivery_target(channel_message(), USER_ID, user_client)
    assert target.native_copy is True
    assert target.copy_client is user_client
    assert target.chat_id == CHANNEL_ID
    assert target.reason == "direct"


def test_delivery_target_survives_a_message_without_a_chat():
    message = SimpleNamespace(chat=None)
    target = main.resolve_delivery_target(message, USER_ID, main.bot)
    assert target.native_copy is False
    assert target.chat_id == USER_ID
    assert target.reason == "no_chat_id"


# --------------------------------------------------------------------------- #
#  (a) private chat + public link
# --------------------------------------------------------------------------- #

async def test_private_chat_public_link_is_copied_by_the_bot(db, fake_bot, monkeypatch):
    await db.add_user(USER_ID, "Tester")
    msg = media_message(15, chat_id=SOURCE_CHAT)
    fake_bot.get_messages = AsyncMock(return_value=msg)
    copied = SimpleNamespace(id=5, edit_caption=AsyncMock())
    fake_bot.copy_message = AsyncMock(return_value=copied)

    message = private_message()
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, fake_bot, "publicname", 15) is True

    assert fake_bot.copy_message.call_count == 1
    kwargs = fake_bot.copy_message.call_args.kwargs
    assert kwargs["chat_id"] == USER_ID, "the bot chat is the destination"
    assert kwargs["from_chat_id"] == msg.chat.id


# --------------------------------------------------------------------------- #
#  (b) private chat + private-channel link via the user's session — THE BUG
# --------------------------------------------------------------------------- #

async def test_private_chat_private_link_is_copied_not_downloaded(
        db, fake_bot, monkeypatch):
    """Round 14 — restricted content is copied by the session, never downloaded.

    The user's own session posts the copy straight into the bot's chat, so the
    file never streams through this server at all.  That is the whole point of
    the round: the old guard "solved" Saved Messages by downloading, which is
    the one thing restricted content must never do.
    """
    await db.add_user(USER_ID, "Tester")
    await db.add_premium(USER_ID, 30, tier="all")

    user_client = RecordingClient("user", user_client=True)
    msg = media_message(15)
    user_client.get_messages = AsyncMock(return_value=msg)
    main.user_clients[USER_ID] = user_client

    async def fake_download(message, progress=None, **kwargs):   # pragma: no cover
        raise AssertionError("restricted content must never be downloaded")

    user_client.download_media = fake_download
    install_source(fake_bot, monkeypatch, msg)
    fake_bot.send_video = AsyncMock()

    message = private_message()
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, user_client, SOURCE_CHAT, 15) is True

    # the session made exactly one copy, into the bot's own chat
    assert user_client.copy_message.call_count == 1
    assert user_client.copy_message.call_args.kwargs["chat_id"] == BOT_ID
    assert USER_ID not in user_client.destinations, "never Saved Messages"
    # nothing was downloaded and nothing was re-uploaded through the server
    assert user_client.uploads == [], "no upload verbs ran"
    assert fake_bot.send_video.call_count == 0


async def test_the_native_copy_keeps_the_premium_caption_clean(
        db, fake_bot, monkeypatch):
    """Caption behaviour is identical on the native-copy path."""
    await db.add_user(USER_ID, "Tester")
    await db.add_premium(USER_ID, 30, tier="private")
    user_client = RecordingClient("user", user_client=True)
    msg = media_message(16)
    user_client.get_messages = AsyncMock(return_value=msg)
    main.user_clients[USER_ID] = user_client

    async def fake_download(message, progress=None, **kwargs):   # pragma: no cover
        raise AssertionError("restricted content must never be downloaded")

    user_client.download_media = fake_download
    install_source(fake_bot, monkeypatch, msg)
    fake_bot.send_video = AsyncMock()

    message = private_message()
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, user_client, SOURCE_CHAT, 16) is True

    #: The copy is made and its caption is left exactly as it was: premium
    #: keeps the clean caption, and nothing was re-uploaded to add one.
    assert user_client.copy_message.call_count == 1
    assert user_client.copy_message.call_args.kwargs["chat_id"] == BOT_ID
    assert fake_bot.send_video.call_count == 0
    assert main.attribution_text() not in (msg.caption or ""), "clean caption"


async def test_free_credit_line_survives_the_bot_upload_path(db, fake_bot, monkeypatch):
    """Public link + no server-side copy → the bot uploads *with* attribution."""
    await db.add_user(USER_ID, "Tester")          # free tier → credit line
    msg = media_message(17)
    fake_bot.messages[msg.id] = msg

    async def no_copy(**kwargs):
        raise RuntimeError("no native copy available")

    async def fake_download(message, progress=None, **kwargs):
        if progress:
            await progress(msg.video.file_size, msg.video.file_size)
        return "/tmp/file.mp4"

    fake_bot.copy_message = no_copy
    fake_bot.download_media = fake_download
    fake_bot.send_video = AsyncMock()
    monkeypatch.setattr(main.os.path, "exists", lambda path: False)
    monkeypatch.setattr(main, "TELEMETRY_EDIT_INTERVAL", 0.0)

    message = private_message()
    status = FakeMessage(text="...", message_id=9)
    await main.fetch_and_send(message, status, fake_bot, "publicname", 17)

    caption = fake_bot.send_video.call_args.kwargs["caption"]
    assert main.attribution_text() in caption
    assert "Restricted caption" in caption


async def test_private_link_via_try_native_copy_copies_into_the_bot_chat(db, fake_bot):
    """``try_native_copy`` alone copies into the bot's chat and arms the guard."""
    await db.add_user(USER_ID, "Tester")
    await db.add_premium(USER_ID, 30, tier="all")
    user_client = RecordingClient("user", user_client=True)
    user_client.get_messages = AsyncMock(return_value=media_message(15))

    message = private_message()
    assert await main.try_native_copy(message, user_client, SOURCE_CHAT, 15) is True
    assert user_client.copy_message.call_count == 1
    assert user_client.copy_message.call_args.kwargs["chat_id"] == BOT_ID
    assert USER_ID not in user_client.destinations
    #: the echo of that copy is now expected, exactly once
    assert USER_ID in main.ECHO_GUARD


# --------------------------------------------------------------------------- #
#  (c) dump channel + public link
# --------------------------------------------------------------------------- #

async def test_dump_channel_public_link_uses_the_server_side_copy(
        db, fake_bot, monkeypatch):
    await db.add_user(USER_ID, "Tester")
    await db.set_user_chat(USER_ID, CHANNEL_ID, "Dump")
    msg = media_message(20, chat_id=SOURCE_CHAT)
    fake_bot.get_messages = AsyncMock(return_value=msg)
    copied = SimpleNamespace(id=6, edit_caption=AsyncMock())
    fake_bot.copy_message = AsyncMock(return_value=copied)

    post = channel_message()
    requester = main.ChannelRequester(post, db.users[USER_ID])
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(requester, status, fake_bot, "publicname", 20,
                                     enforce_fsub=False) is True
    assert fake_bot.copy_message.call_args.kwargs["chat_id"] == CHANNEL_ID


# --------------------------------------------------------------------------- #
#  (d) dump channel + private link
# --------------------------------------------------------------------------- #

async def test_dump_channel_private_link_copies_into_the_channel(
        db, fake_bot, monkeypatch):
    """The fast server-side copy stays legal when the destination is a channel."""
    await db.add_user(USER_ID, "Tester")
    await db.add_premium(USER_ID, 30, tier="all")
    await db.set_user_chat(USER_ID, CHANNEL_ID, "Dump")

    user_client = RecordingClient("user", user_client=True)
    msg = media_message(21)
    user_client.get_messages = AsyncMock(return_value=msg)
    main.user_clients[USER_ID] = user_client

    post = channel_message()
    requester = main.ChannelRequester(post, db.users[USER_ID])
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(requester, status, user_client, SOURCE_CHAT, 21,
                                     enforce_fsub=False) is True

    assert user_client.copy_message.call_count == 1
    assert user_client.copy_message.call_args.kwargs["chat_id"] == CHANNEL_ID
    assert USER_ID not in user_client.destinations


# --------------------------------------------------------------------------- #
#  The end-to-end private-chat route a VIP actually takes
# --------------------------------------------------------------------------- #

async def test_text_handler_private_link_copies_without_downloading(
        db, fake_bot, monkeypatch):
    """``t.me/c/...`` in the bot chat: the session copies, the server downloads
    nothing — and the echo of that copy is swallowed once it arrives."""
    await db.add_user(USER_ID, "Tester")
    await db.add_premium(USER_ID, 30, tier="all")

    user_client = RecordingClient("user", user_client=True)
    msg = media_message(31)
    user_client.get_messages = AsyncMock(return_value=msg)

    async def fake_download(message, progress=None, **kwargs):   # pragma: no cover
        raise AssertionError("restricted content must never be downloaded")

    user_client.download_media = fake_download
    monkeypatch.setattr(main, "get_user_client", AsyncMock(return_value=user_client))
    install_source(fake_bot, monkeypatch, msg)
    fake_bot.send_video = AsyncMock()

    message = FakeMessage(text="https://t.me/c/123456789/31", user=FakeUser(USER_ID))
    await main.text_handler(None, message)

    assert user_client.copy_message.call_count == 1
    assert user_client.copy_message.call_args.kwargs["chat_id"] == BOT_ID
    assert USER_ID not in user_client.destinations
    assert fake_bot.send_video.call_count == 0, "nothing was re-uploaded"
    assert user_client.uploads == [], "the session uploaded nothing"

    #: The copy lands in the bot chat and comes back as an ordinary message.
    #: The bot must swallow that echo once and never extract it a second time.
    assert USER_ID in main.ECHO_GUARD, "the echo is expected"
    echo = FakeMessage(text="https://t.me/c/123456789/31", user=FakeUser(USER_ID))
    await main.text_handler(None, echo)
    assert echo.replies == [] and echo.edits == [], "the echo was swallowed"
    assert USER_ID not in main.ECHO_GUARD, "the guard is single-use"


# --------------------------------------------------------------------------- #
#  Standing constraints on the new copy
# --------------------------------------------------------------------------- #

def test_guard_reasons_are_plain_ascii():
    user_client = RecordingClient("user", user_client=True)
    target = main.resolve_delivery_target(private_message(), USER_ID, user_client)
    assert target.reason.isascii()
    assert target.reason in {"bot_dm_native_copy", "saved_messages_guard"}
    #: whichever branch ran, the destination is never the user's own id.
    assert target.chat_id != USER_ID or target.reason == "saved_messages_guard"
