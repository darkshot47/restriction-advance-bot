"""Round 19 — the Vmore App page (/app) and the APK hand-over (/apk).

The number is the next free one: the rounds numbered 16 to 18 tested the retired
app server (`appapi.py`, ``/api/v2``) and are gone with it.

The rule this round exists for: **no screen asks for a server address, an
access token or anything else**.  ``/app`` explains the app, ``/apk`` either
publishes the owner's file or hands exactly that file over, and the private-link
prompt offers the app next to premium.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

import pytest

import main
import ui
from config import OWNER_CONTACT_URL, VMORE_APK_URL
from conftest import FakeMessage, FakeUser, sc

OWNER = main.OWNER_ID
USER = 1001


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def apk_document(file_id="BQACAgAPK1", file_name="Vmore-2.2.12.apk", size=15_728_640):
    """A Telegram document, the way Kurigram hands one to a bot."""
    return SimpleNamespace(file_id=file_id, file_name=file_name, file_size=size)


#: Words that would mean the retired deployment wizard had come back.  The
#: screens are free to *say* there is no server and no token; they must never
#: ask for one, and never print a raw link.
BANNED_WORDS = ("gentoken", "revoketoken", "access token", "server url", "base url",
                "api endpoint", "mongodb", "http://", "https://")


def prose(text: str) -> str:
    """Body copy with ``code`` spans removed — the way every round checks links."""
    return re.sub(r"`[^`]*`", "", text)


# --------------------------------------------------------------------------- #
#  1. The buttons are back
# --------------------------------------------------------------------------- #

def test_start_menu_ends_with_the_app_button():
    rows = ui.start_keyboard().inline_keyboard
    assert len(rows[-1]) == 1, "the app button is full width"
    assert rows[-1][0].callback_data == "cmd_app"
    assert rows[-1][0].text == sc("📱 Vmore App")
    assert rows[-1][0].url is None


def test_the_app_button_is_last_for_users_and_admins_alike():
    for markup in (ui.start_keyboard(), ui.start_keyboard(show_admin=True)):
        rows = markup.inline_keyboard
        assert len(rows) <= 7
        assert [b.callback_data for b in rows[-1]] == ["cmd_app"]


def test_help_menu_offers_the_app():
    by_data = {b.callback_data: b for b in flat(ui.help_keyboard())}
    assert by_data["cmd_app"].text == sc("📱 Vmore App")


def test_every_app_button_is_wired():
    for data in ("cmd_app", "app:apk", "app:howto", "home"):
        assert data in main.CALLBACK_ACTIONS, data


# --------------------------------------------------------------------------- #
#  2. /app — the app page
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_app_command_shows_the_app_page(db):
    message = FakeMessage(text="/app", user=FakeUser(USER))
    await main.app_handler(None, message)

    text = message.shown_text
    assert sc("VMORE APP") in text
    assert "unlimited" in ui.plain_caps(text).lower()

    buttons = flat(message.shown_markup)
    by_data = {b.callback_data: b for b in buttons}
    assert by_data["app:apk"].text == sc("📩 Send APK in chat")
    assert by_data["app:howto"].text == sc("❓ How to use?")
    assert by_data["home"].text == sc("🏠 Main Menu")
    urls = [b.url for b in buttons if b.url]
    assert VMORE_APK_URL in urls
    assert OWNER_CONTACT_URL in urls

    #: One message, and the page fits a phone.
    assert len(message.replies) == 1
    rows = message.shown_markup.inline_keyboard
    assert 1 <= len(rows) <= 7
    assert all(1 <= len(row) <= 2 for row in rows)


@pytest.mark.asyncio
async def test_app_button_press_opens_the_same_page(db, press):
    message = FakeMessage(user=FakeUser(USER))
    await press(message, "cmd_app")
    assert sc("VMORE APP") in message.shown_text
    assert "app:apk" in message.callback_data()


@pytest.mark.asyncio
async def test_app_page_names_the_published_build(db):
    await main.set_app_apk(file_id="F1", file_name="Vmore-2.2.12.apk", size=15_728_640,
                           version="2.2.12", uploaded_by=OWNER)
    text = ui.app_details_text(await main.app_build())
    assert "Current build" in text
    assert "2.2.12" in text
    assert "15.0 MB" in text


@pytest.mark.asyncio
async def test_app_page_without_an_upload_still_offers_the_link(db):
    text = ui.app_details_text(await main.app_build())
    assert "Latest build" in text
    assert "2.2.12" not in text


# --------------------------------------------------------------------------- #
#  3. No server, no token — anywhere on these screens
# --------------------------------------------------------------------------- #

APP_TEXTS = [
    ("app_page", lambda: ui.app_details_text()),
    ("app_howto", ui.app_howto_text),
    ("app_sent", lambda: ui.app_sent_text(None)),
    ("app_saved", lambda: ui.app_saved_text(None)),
    ("app_missing", ui.app_missing_text),
    ("app_private_link", ui.app_private_link_text),
    ("apk", ui.apk_text),
]


@pytest.mark.parametrize("name,build", APP_TEXTS, ids=[n for n, _ in APP_TEXTS])
def test_no_app_screen_asks_for_a_server_or_a_token(name, build):
    text = build()
    assert text.strip(), name
    lowered = text.lower()
    for word in BANNED_WORDS:
        assert word not in lowered, (name, word)
    #: A link belongs in a ``url=`` button, never in the body.
    assert "t.me/" not in prose(text), name
    assert not any("\u0900" <= char <= "\u097f" for char in text), name
    #: And the copy says out loud that there is nothing to fill in.
    assert "no server" in lowered, name


@pytest.mark.parametrize("name,build", [
    ("details", ui.app_details_keyboard),
    ("howto", ui.app_howto_keyboard),
    ("sent", ui.app_sent_keyboard),
], ids=["details", "howto", "sent"])
def test_app_keyboards_fit_the_mobile_budget(name, build):
    rows = build().inline_keyboard
    assert 1 <= len(rows) <= 7, name
    for row in rows:
        assert 1 <= len(row) <= 2, name
        for button in row:
            assert len(ui.plain_caps(button.text)) <= 28, (name, button.text)
            if button.callback_data is not None:
                assert button.callback_data.isascii()
                assert button.url is None, "a button is either a callback or a link"
            if button.url is not None:
                assert button.url.startswith("https://")


# --------------------------------------------------------------------------- #
#  4. /apk — the owner publishes
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_owner_apk_with_document_is_connected(db):
    message = FakeMessage(text="/apk", user=FakeUser(OWNER))
    message.document = apk_document()
    await main.apk_handler(None, message)

    record = await main.get_app_apk()
    assert record["file_id"] == "BQACAgAPK1"
    assert record["file_name"] == "Vmore-2.2.12.apk"
    assert record["size"] == 15_728_640
    assert record["version"] == "2.2.12"
    assert record["uploaded_by"] == OWNER
    #: The reply confirms the connection and asks for nothing — the only
    #: mention of a server or a token is the sentence saying there is neither.
    lowered = ui.plain_caps(message.shown_text).lower()
    assert sc("APK CONNECTED") in message.shown_text
    assert "no server address and no token" in lowered
    for banned in BANNED_WORDS:
        assert banned not in lowered, banned


@pytest.mark.asyncio
async def test_owner_apk_reply_to_a_document_is_connected(db):
    message = FakeMessage(text="/apk", user=FakeUser(OWNER))
    message.reply_to_message = SimpleNamespace(document=apk_document(file_id="REPLY-ID"))
    await main.apk_handler(None, message)
    assert (await main.get_app_apk())["file_id"] == "REPLY-ID"


@pytest.mark.asyncio
async def test_owner_version_is_read_from_the_file_name(db):
    message = FakeMessage(text="/apk", user=FakeUser(OWNER))
    message.document = apk_document(file_name="vmore-3.1.apk", file_id="V31")
    await main.apk_handler(None, message)
    assert (await main.get_app_apk())["version"] == "3.1"


@pytest.mark.asyncio
async def test_a_non_apk_document_is_not_connected(db):
    message = FakeMessage(text="/apk", user=FakeUser(OWNER))
    message.document = apk_document(file_name="notes.zip", file_id="ZIP")
    await main.apk_handler(None, message)
    assert await main.get_app_apk() is None
    #: No false success: the ordinary link screen, unchanged.
    assert sc("VMORE FOR ANDROID") in message.shown_text


@pytest.mark.asyncio
async def test_a_user_cannot_replace_the_published_apk(db):
    await main.set_app_apk(file_id="OWNER-FILE", file_name="Vmore-2.2.12.apk",
                           size=1, version="2.2.12", uploaded_by=OWNER)
    message = FakeMessage(text="/apk", user=FakeUser(USER))
    message.document = apk_document(file_id="ATTACKER-FILE")
    await main.apk_handler(None, message)
    assert (await main.get_app_apk())["file_id"] == "OWNER-FILE"
    assert sc("APK CONNECTED") not in message.shown_text


# --------------------------------------------------------------------------- #
#  5. /apk and app:apk — everybody receives the file
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_apk_sends_the_published_file_into_the_chat(db, fake_bot):
    await main.set_app_apk(file_id="BQACAgAPK1", file_name="Vmore-2.2.12.apk",
                           size=15_728_640, version="2.2.12", uploaded_by=OWNER)
    message = FakeMessage(text="/apk", user=FakeUser(USER))
    await main.apk_handler(None, message)

    chat_id, file_id, kwargs = fake_bot.documents[-1]
    assert (chat_id, file_id) == (USER, "BQACAgAPK1")
    caption = kwargs["caption"]
    assert sc("VMORE APK") in caption
    assert "2.2.12" in caption
    buttons = flat(kwargs["reply_markup"])
    assert VMORE_APK_URL in [b.url for b in buttons]
    assert "app:howto" in [b.callback_data for b in buttons]


@pytest.mark.asyncio
async def test_apk_falls_back_to_the_link_when_nothing_is_published(db, fake_bot):
    message = FakeMessage(text="/apk", user=FakeUser(USER))
    await main.apk_handler(None, message)
    assert not fake_bot.documents
    assert len(message.replies) == 1
    buttons = flat(message.shown_markup)
    assert len(buttons) == 1, "one download button, nothing to fill in"
    assert buttons[0].url == VMORE_APK_URL


@pytest.mark.asyncio
async def test_apk_still_offers_the_link_when_the_file_cannot_be_sent(db, fake_bot, monkeypatch):
    await main.set_app_apk(file_id="DEAD-ID", file_name="Vmore.apk", size=10,
                           version="1.0", uploaded_by=OWNER)

    async def refuse(*args, **kwargs):
        raise RuntimeError("that file id belongs to another bot")

    monkeypatch.setattr(fake_bot, "send_document", refuse)
    message = FakeMessage(text="/apk", user=FakeUser(USER))
    await main.apk_handler(None, message)
    assert sc("VMORE FOR ANDROID") in message.shown_text
    assert [b.url for b in flat(message.shown_markup) if b.url] == [VMORE_APK_URL]


@pytest.mark.asyncio
async def test_app_apk_button_sends_the_file(db, fake_bot, press):
    await main.set_app_apk(file_id="BQACAgAPK1", file_name="Vmore-2.2.12.apk",
                           size=15_728_640, version="2.2.12", uploaded_by=OWNER)
    message = FakeMessage(user=FakeUser(USER))
    query = await press(message, "app:apk")
    assert fake_bot.documents[-1][1] == "BQACAgAPK1"
    assert query.answer.texts, "the press was not acknowledged"


@pytest.mark.asyncio
async def test_app_apk_button_without_an_upload_shows_the_link(db, fake_bot, press):
    message = FakeMessage(user=FakeUser(USER))
    await press(message, "app:apk")
    assert not fake_bot.documents
    assert [b.url for b in flat(message.shown_markup) if b.url] == [VMORE_APK_URL]


@pytest.mark.asyncio
async def test_the_owner_is_told_how_to_publish_one(db, press):
    """The owner pressing **Send APK in chat** first learns the missing step."""
    message = FakeMessage(user=FakeUser(OWNER))
    await press(message, "app:apk")
    assert sc("NO APK PUBLISHED YET") in message.shown_text
    assert sc("/apk") in message.shown_text or "/apk" in message.shown_text


@pytest.mark.asyncio
async def test_howto_button_explains_the_phone_login(db, press):
    message = FakeMessage(user=FakeUser(USER))
    await press(message, "cmd_app")
    await press(message, "app:howto")
    text = message.shown_text
    plain = ui.plain_caps(text).lower()
    assert sc("HOW TO USE VMORE") in text
    assert "my.telegram.org" in plain
    assert "api_id" in plain
    assert "install unknown apps" in plain
    for banned in BANNED_WORDS:
        assert banned not in plain, banned


# --------------------------------------------------------------------------- #
#  6. The private-link prompt now offers the app too
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_private_link_prompt_offers_the_app(db):
    message = FakeMessage(user=FakeUser(USER))
    await main.reply_private_access(message)

    rows = message.shown_markup.inline_keyboard
    assert [b.callback_data for b in rows[0]] == ["cmd_premium", "cmd_refer"]
    assert [b.callback_data for b in rows[1]] == ["app:apk"]
    assert rows[1][0].text == sc("♾️ Unlimited Download (App)")
    assert sc("Private Channel Access (Premium Only)") in message.shown_text
    assert "unlimited" in ui.plain_caps(message.shown_text).lower()


@pytest.mark.asyncio
async def test_a_private_link_still_offers_the_app_before_anything_is_fetched(db, monkeypatch):
    from unittest.mock import AsyncMock

    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    message = FakeMessage(text="https://t.me/c/12345/10", user=FakeUser(USER))
    await main.text_handler(None, message)
    fetch.assert_not_called()
    assert "app:apk" in message.callback_data()


def test_the_daily_limit_screen_keeps_its_own_keyboard():
    """The app row belongs to the private-link pitch, not to the quota screen."""
    assert [b.callback_data for b in flat(ui.daily_limit_keyboard())] == \
        ["cmd_premium", "cmd_refer"]


# --------------------------------------------------------------------------- #
#  7. Registration: commands, menus and the admin panel
# --------------------------------------------------------------------------- #

def test_app_and_apk_are_registered_everywhere():
    for command in ("app", "apk"):
        assert command in main.COMMAND_NAMES
        assert callable(main.COMMAND_HANDLERS[command])
        assert command in main.ADMIN_PANEL_COMMANDS
        assert main.ADMIN_INLINE_HANDLERS[command] is main.COMMAND_HANDLERS[command]
        assert f"/{command}" in main.admin_help_text()
        assert command in ui.ADMIN_COMMAND_LABELS
        assert command in ui.ADMIN_COMMAND_ICONS
        assert command not in main.ADMIN_VALUE_EXAMPLES, "these two ask for no argument"


def test_app_and_apk_are_in_the_user_menu():
    described = {c.command: c.description for c in main.telegram_commands("user")}
    assert {"app", "apk"} <= set(described)
    assert described["app"].startswith("📱")
    assert all(len(line) <= 45 for line in described.values())
    assert {"app", "apk"} <= {name for name, _emoji, _text in ui.USER_MENU}


def test_the_admin_and_owner_menus_include_the_app_commands():
    for role in ("admin", "owner"):
        names = {c.command for c in main.telegram_commands(role)}
        assert {"app", "apk"} <= names


@pytest.mark.asyncio
async def test_the_admin_panel_button_opens_the_app_page(db, press):
    """The panel runs the very same handler, editing the panel message."""
    message = FakeMessage(user=FakeUser(OWNER))
    await press(message, "admin:app")
    assert sc("VMORE APP") in message.shown_text


@pytest.mark.asyncio
async def test_the_admin_panel_button_sends_the_apk(db, fake_bot, press):
    await main.set_app_apk(file_id="PANEL-FILE", file_name="Vmore.apk", size=1,
                           version="1.0", uploaded_by=OWNER)
    message = FakeMessage(user=FakeUser(OWNER))
    await press(message, "admin:apk")
    assert fake_bot.documents[-1][1] == "PANEL-FILE"


def test_the_only_published_state_is_a_file_id():
    """The stored record is the file and its description: no URL, no token."""
    signature = inspect.signature(main.set_app_apk)
    assert list(signature.parameters) == ["file_id", "file_name", "size", "version",
                                          "apk_hash", "uploaded_by"]


@pytest.mark.asyncio
async def test_a_dead_database_never_eats_the_download_link(db, fake_bot, monkeypatch):
    async def broken():
        raise RuntimeError("mongo is down")

    monkeypatch.setattr(main, "get_app_apk", broken)
    message = FakeMessage(text="/apk", user=FakeUser(USER))
    await main.apk_handler(None, message)
    assert not fake_bot.documents
    assert [b.url for b in flat(message.shown_markup) if b.url] == [VMORE_APK_URL]
