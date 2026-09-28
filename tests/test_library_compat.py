"""The bot depends on a fairly wide pyrogram surface — keep it verified.

Kurigram installs the `pyrogram` package, so a dependency bump can silently
remove a method the bot calls.  These cheap assertions catch that before a
deploy does.
"""

from __future__ import annotations

import inspect

import pyrogram
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, Message

CLIENT_METHODS = [
    "start", "stop", "run", "get_me",
    "send_code", "sign_in", "check_password", "export_session_string", "log_out",
    "get_messages", "copy_message", "download_media",
    "send_message", "send_photo", "send_video", "send_document", "send_audio",
    "send_voice", "send_video_note", "send_sticker", "send_animation",
    "get_chat_member",
]

MESSAGE_MEMBERS = [
    "reply", "edit_text", "edit_reply_markup", "delete",
    "photo", "video", "document", "audio", "voice", "video_note", "sticker",
    "animation", "caption", "text", "empty", "media",
]


def test_client_surface():
    missing = [name for name in CLIENT_METHODS if not hasattr(Client, name)]
    assert missing == [], f"pyrogram client is missing {missing}"


def test_client_constructor_kwargs():
    params = inspect.signature(Client.__init__).parameters
    for name in ("api_id", "api_hash", "bot_token", "session_string", "in_memory"):
        assert name in params, f"Client(..., {name}=...) is not supported anymore"


def test_message_and_callback_surface():
    missing = [name for name in MESSAGE_MEMBERS if not hasattr(Message, name)]
    # data fields (photo, video, …) live in __init__, methods on the class
    fields = inspect.signature(Message.__init__).parameters
    missing = [name for name in missing if name not in fields]
    assert missing == [], f"Message is missing {missing}"

    assert hasattr(CallbackQuery, "answer")
    assert "message" in inspect.signature(CallbackQuery.__init__).parameters


def test_filters_used_by_the_bot():
    for name in ("command", "photo", "private", "text"):
        assert hasattr(filters, name), f"filters.{name} is missing"


def test_button_style_api():
    """The blue/green/red styles are the reason this bot needs kurigram."""
    from pyrogram.enums import ButtonStyle

    assert {"PRIMARY", "SUCCESS", "DANGER"} <= {s.name for s in ButtonStyle}
    assert "style" in inspect.signature(InlineKeyboardButton.__init__).parameters


def test_layer_supports_button_styles():
    """Styles only exist from layer 222 on — pyrofork 2.3.69 (layer 220) cannot."""
    from pyrogram.raw.all import layer

    assert layer >= 222, f"MTProto layer {layer} predates styled buttons"


def test_library_version_is_known():
    assert getattr(pyrogram, "__version__", "")
