"""Every /start inline button must run its action directly.

Regression guard for the old behaviour where pressing a button only answered
"Send /login", "Send /help", …
"""

from __future__ import annotations

import pytest

import main
import ui
from conftest import FakeMessage, FakeUser, sc


class FakeEvent:
    """Minimal asyncio.Event stand-in for download jobs."""

    def __init__(self):
        self.set_called = False
        self.cleared = False

    def set(self):
        self.set_called = True

    def clear(self):
        self.cleared = True


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def test_every_menu_button_is_wired_to_a_handler():
    menus = [
        ui.start_keyboard(),
        ui.settings_keyboard(True, False),
        ui.language_keyboard("en"),
        ui.login_keyboard(),
        ui.logout_keyboard(),
        ui.feedback_keyboard(),
        ui.stats_keyboard(),
        ui.premium_keyboard(False, owner_id=1),
        ui.refer_keyboard("https://t.me/TestRestrictBot?start=1"),
        ui.help_keyboard(),
        ui.fsub_keyboard("@channel"),
        ui.back_keyboard(),
        ui.close_keyboard(),
    ]
    missing = [
        b.callback_data
        for markup in menus
        for b in flat(markup)
        if b.callback_data and b.callback_data not in main.CALLBACK_ACTIONS
    ]
    assert missing == [], f"buttons without an action: {missing}"


@pytest.mark.asyncio
async def test_start_menu_buttons_never_ask_for_a_command(db, press):
    """Pressing each menu button must perform the action, not print a hint."""
    for data in sorted({b.callback_data for b in flat(ui.start_keyboard())}):
        message = FakeMessage()
        query = await press(message, data)
        answers = " ".join(query.answer.texts)
        assert sc("Send /") not in answers, f"{data} still asks for a command"
        assert message.shown_text, f"{data} did nothing"


@pytest.mark.asyncio
async def test_login_button_starts_login_flow(db, press):
    message = FakeMessage()
    query = await press(message, "cmd_login")

    assert query.answer.calls, "the callback was not acknowledged"
    assert main.login_pending[message.from_user.id]["step"] == "waiting_phone"
    assert sc("+91 9876543210") in message.shown_text
    assert message.button("cancel_login").text  # cancel button is offered


@pytest.mark.asyncio
async def test_login_button_with_existing_session(db, press, monkeypatch):
    async def fake_client(user_id):
        return object()

    monkeypatch.setattr(main, "get_user_client", fake_client)
    message = FakeMessage()
    await press(message, "cmd_login")
    assert sc("Already logged in") in message.shown_text
    assert message.from_user.id not in main.login_pending


@pytest.mark.asyncio
async def test_cancel_login_clears_state(db, press):
    message = FakeMessage()
    await press(message, "cmd_login")
    assert main.login_pending

    query = await press(message, "cancel_login")
    assert main.login_pending == {}
    assert sc("cancelled") in message.shown_text.lower()
    assert query.answer.texts


@pytest.mark.asyncio
async def test_logout_button_logs_out(db, press, monkeypatch):
    user_id = 1001
    db.users[user_id] = db._new_user(user_id, "Tester", "tester")
    await db.save_session(user_id, "session-string", "919999999999")

    class FakeUserClient:
        async def get_me(self):
            class Me:
                phone_number = "919999999999"
            return Me()

        async def log_out(self):
            self.logged_out = True

    client = FakeUserClient()

    async def fake_client(uid):
        return client

    monkeypatch.setattr(main, "get_user_client", fake_client)
    monkeypatch.setattr(main, "user_clients", {user_id: client})

    message = FakeMessage()
    await press(message, "cmd_logout")

    assert client.logged_out is True
    assert db.sessions == {}
    assert sc("Logged out") in message.shown_text
    assert message.button("cmd_login").text == sc("🔐 Login")


@pytest.mark.asyncio
async def test_logout_button_without_session(db, press, monkeypatch):
    async def fake_client(uid):
        return None

    monkeypatch.setattr(main, "get_user_client", fake_client)
    message = FakeMessage()
    await press(message, "cmd_logout")
    assert sc("not logged in") in message.shown_text.lower()


@pytest.mark.asyncio
async def test_settings_button_shows_toggles(db, press):
    message = FakeMessage()
    await press(message, "cmd_settings")

    assert sc("SETTINGS") in message.shown_text
    assert message.button("toggle_notif").text.endswith(sc("ON"))
    assert message.button("toggle_silent").text.endswith(sc("OFF"))


@pytest.mark.asyncio
async def test_toggle_notifications_updates_db_and_menu(db, press):
    message = FakeMessage()
    await press(message, "cmd_settings")
    query = await press(message, "toggle_notif")

    assert db.users[message.from_user.id]["notifications"] is False
    assert sc("OFF") in message.button("toggle_notif").text
    assert sc("Notifications OFF") in " ".join(query.answer.texts)


@pytest.mark.asyncio
async def test_toggle_silent_updates_db_and_menu(db, press):
    message = FakeMessage()
    await press(message, "cmd_settings")
    await press(message, "toggle_silent")

    assert db.users[message.from_user.id]["silent_mode"] is True
    assert sc("ON") in message.button("toggle_silent").text


@pytest.mark.asyncio
async def test_reset_settings_restores_defaults(db, press):
    message = FakeMessage()
    await press(message, "cmd_settings")
    await press(message, "toggle_notif")
    await press(message, "reset_settings")

    user = db.users[message.from_user.id]
    assert user["notifications"] is True
    assert user["silent_mode"] is False
    assert sc("SETTINGS") in message.shown_text


@pytest.mark.asyncio
async def test_stats_button_shows_personal_stats(db, press):
    message = FakeMessage()
    await press(message, "cmd_settings")  # create the user row
    db.users[message.from_user.id]["downloads"] = 7
    db.users[message.from_user.id]["referral_count"] = 3

    await press(message, "cmd_stats")
    assert sc("YOUR STATS") in message.shown_text
    assert sc("7") in message.shown_text
    assert sc("3") in message.shown_text
    assert message.button("home").callback_data == "home"


@pytest.mark.asyncio
async def test_premium_button_shows_benefits(db, press):
    message = FakeMessage()
    await press(message, "cmd_premium")
    assert sc("PREMIUM") in message.shown_text
    assert sc("Unlimited downloads") in message.shown_text
    # owner contact button only when an owner id is configured
    texts = message.button_texts()
    assert any("owner" in ui.plain_caps(t).lower() for t in texts) is bool(main.OWNER_ID)


@pytest.mark.asyncio
async def test_refer_button_shows_referral_link(db, press):
    message = FakeMessage()
    await press(message, "cmd_refer")
    assert f"https://t.me/{main.BOT_USERNAME}?start={message.from_user.id}" in message.shown_text


@pytest.mark.asyncio
async def test_help_button_shows_help(db, press):
    message = FakeMessage()
    await press(message, "cmd_help")
    assert sc("HELP MENU") in message.shown_text
    assert message.button("home")


@pytest.mark.asyncio
async def test_feedback_button_waits_for_text_and_saves_it(db, press):
    message = FakeMessage(user=FakeUser(5001))
    await press(message, "cmd_feedback")
    assert main.pending_action[5001] == "feedback"
    assert sc("FEEDBACK") in message.shown_text
    assert message.button("cancel_action")

    # the user now types the feedback
    text_message = FakeMessage(text="Great bot!", user=FakeUser(5001))
    await main.text_handler(None, text_message)
    assert db.feedback == [(5001, "Great bot!")]
    assert sc("Feedback sent") in text_message.shown_text
    assert 5001 not in main.pending_action


@pytest.mark.asyncio
async def test_cancel_feedback(db, press):
    message = FakeMessage(user=FakeUser(5002))
    await press(message, "cmd_feedback")
    await press(message, "cancel_action")
    assert main.pending_action == {}


@pytest.mark.asyncio
async def test_language_button_and_selection(db, press):
    message = FakeMessage()
    await press(message, "cmd_language")

    assert sc("LANGUAGE") in message.shown_text
    assert message.button("lang_en").text.startswith("✅")

    query = await press(message, "lang_hi")
    assert db.users[message.from_user.id]["language"] == "hi"
    assert message.button("lang_hi").text.startswith("✅")
    assert not message.button("lang_en").text.startswith("✅")
    assert query.answer.texts


@pytest.mark.asyncio
async def test_home_button_returns_to_main_menu(db, press):
    message = FakeMessage()
    await press(message, "cmd_help")
    await press(message, "home")
    assert sc("Hello") in message.shown_text
    assert {b.callback_data for b in flat(ui.start_keyboard())} <= set(message.callback_data())


@pytest.mark.asyncio
async def test_close_button_deletes_the_message(db, press):
    message = FakeMessage()
    query = await press(message, "close")
    assert message.deleted is True
    assert sc("closed") in " ".join(query.answer.texts).lower()


@pytest.mark.asyncio
async def test_check_fsub_button_without_required_channel(db, press):
    message = FakeMessage()
    query = await press(message, "check_fsub")
    assert sc("verify") in " ".join(query.answer.texts).lower() or query.answer.calls


@pytest.mark.asyncio
async def test_unknown_button_gets_a_friendly_alert(db, press):
    message = FakeMessage()
    query = await press(message, "totally-unknown-data")
    assert query.answer.calls[0]["show_alert"] is True
    assert sc("/start") in query.answer.calls[0]["text"]


@pytest.mark.asyncio
async def test_download_controls_pause_resume_stop(db, press):
    job_id = "job-1"
    main.active_downloads[job_id] = {
        "user_id": 1001,
        "paused": False,
        "cancelled": False,
        "event": FakeEvent(),
        "task": None,
    }
    message = FakeMessage()

    query = await press(message, f"dl:p:{job_id}")
    assert main.active_downloads[job_id]["paused"] is True
    assert message.markups[-1].inline_keyboard[0][0].callback_data == f"dl:r:{job_id}"
    assert sc("paused") in " ".join(query.answer.texts).lower()

    await press(message, f"dl:r:{job_id}")
    assert main.active_downloads[job_id]["paused"] is False

    await press(message, f"dl:s:{job_id}")
    assert main.active_downloads[job_id]["cancelled"] is True


@pytest.mark.asyncio
async def test_download_controls_reject_foreign_jobs(db, press):
    main.active_downloads["other"] = {
        "user_id": 999, "paused": False, "cancelled": False,
        "event": FakeEvent(), "task": None,
    }
    message = FakeMessage(user=FakeUser(1001))
    query = await press(message, "dl:p:other")
    assert sc("no longer active") in " ".join(query.answer.texts).lower()


