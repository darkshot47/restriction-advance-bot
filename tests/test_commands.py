"""The /commands must show the same screens as the buttons."""

from __future__ import annotations

import pytest

import main
from conftest import FakeMessage, FakeUser


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


@pytest.mark.asyncio
async def test_start_command_shows_working_menu(db):
    message = FakeMessage(text="/start")
    await main.start_handler(None, message)

    text = message.shown_text
    assert "Restricted Content Saver Bot" in text
    assert "Status:" in text
    # the old menu told users to type /login — that is gone
    assert "/login first" not in text

    data = message.callback_data()
    assert {
        "cmd_login", "cmd_logout", "cmd_settings", "cmd_stats",
        "cmd_premium", "cmd_refer", "cmd_help", "cmd_feedback", "cmd_language",
    } <= set(data)
    assert all(d in main.CALLBACK_ACTIONS for d in data)


@pytest.mark.asyncio
async def test_start_command_registers_referral_once(db):
    new_user = FakeUser(2002, "Newbie")
    message = FakeMessage(text="/start 1001", user=new_user)
    await main.start_handler(None, message)

    assert db.users[1001]["referral_count"] == 1

    # pressing /start again must not double count
    again = FakeMessage(text="/start 1001", user=new_user)
    await main.start_handler(None, again)
    assert db.users[1001]["referral_count"] == 1


@pytest.mark.asyncio
async def test_start_command_ignores_self_referral(db):
    message = FakeMessage(text="/start 1001", user=FakeUser(1001))
    await main.start_handler(None, message)
    assert db.users[1001]["referral_count"] == 0


@pytest.mark.asyncio
async def test_help_command(db):
    message = FakeMessage(text="/help")
    await main.help_handler(None, message)
    assert "HELP MENU" in message.shown_text
    assert "home" in message.callback_data()


@pytest.mark.asyncio
async def test_settings_command(db):
    message = FakeMessage(text="/settings")
    await main.settings_handler(None, message)
    assert "SETTINGS" in message.shown_text
    assert {"toggle_notif", "toggle_silent", "cmd_language", "reset_settings"} <= set(
        message.callback_data()
    )


@pytest.mark.asyncio
async def test_language_command(db):
    message = FakeMessage(text="/language")
    await main.language_handler(None, message)
    assert {"lang_en", "lang_hi"} <= set(message.callback_data())


@pytest.mark.asyncio
async def test_stats_command(db):
    message = FakeMessage(text="/mystats")
    await main.mystats_handler(None, message)
    assert "YOUR STATS" in message.shown_text


@pytest.mark.asyncio
async def test_premium_command_for_free_user(db):
    message = FakeMessage(text="/premium")
    await main.premium_handler(None, message)
    assert "PREMIUM BENEFITS" in message.shown_text


@pytest.mark.asyncio
async def test_premium_command_for_premium_user(db):
    user = FakeUser(3003)
    await db.add_user(user.id, user.first_name, user.username)
    db.users[user.id]["is_premium"] = True

    message = FakeMessage(text="/premium", user=user)
    await main.premium_handler(None, message)
    assert "PREMIUM ACTIVE" in message.shown_text


@pytest.mark.asyncio
async def test_refer_command(db):
    message = FakeMessage(text="/refer")
    await main.refer_handler(None, message)
    assert f"?start={message.from_user.id}" in message.shown_text


@pytest.mark.asyncio
async def test_feedback_command_with_text(db, fake_bot):
    message = FakeMessage(text="/feedback nice work", user=FakeUser(4004))
    await main.feedback_handler(None, message)

    assert db.feedback == [(4004, "nice work")]
    assert "Feedback sent" in message.shown_text
    assert fake_bot.sent and fake_bot.sent[0]["chat_id"] == main.OWNER_ID


@pytest.mark.asyncio
async def test_feedback_command_without_text_waits(db):
    message = FakeMessage(text="/feedback", user=FakeUser(4005))
    await main.feedback_handler(None, message)
    assert main.pending_action[4005] == "feedback"
    assert "cancel_action" in message.callback_data()


@pytest.mark.asyncio
async def test_myinfo_command(db):
    message = FakeMessage(text="/myinfo")
    await main.myinfo_handler(None, message)
    assert "MY INFO" in message.shown_text


@pytest.mark.asyncio
async def test_logout_command_without_session(db, monkeypatch):
    async def no_client(uid):
        return None

    monkeypatch.setattr(main, "get_user_client", no_client)
    message = FakeMessage(text="/logout")
    await main.logout_handler(None, message)
    assert "not logged in" in message.shown_text.lower()


@pytest.mark.asyncio
async def test_text_handler_ignores_plain_chatter_but_asks_for_a_link(db):
    message = FakeMessage(text="hello there")
    await main.text_handler(None, message)
    assert "t.me/" in message.shown_text


@pytest.mark.asyncio
async def test_button_menu_and_command_menu_are_identical(db):
    """The /start screen and the 🏠 Main Menu button render the same keyboard."""
    command_message = FakeMessage(text="/start")
    await main.start_handler(None, command_message)

    from conftest import make_query
    button_message = FakeMessage()
    query = make_query(button_message, "home")
    await main.callback_handler(None, query)

    assert command_message.shown_text == button_message.shown_text
    assert command_message.callback_data() == button_message.callback_data()
