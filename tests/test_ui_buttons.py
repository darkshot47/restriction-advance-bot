"""Button styles + keyboard layout tests (no bot/DB involved)."""

from __future__ import annotations

import pytest

import ui
from conftest import make_member  # noqa: F401  (real library types only)


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def fsub_item(**overrides):
    """A force-sub entry the way database.normalize_fsub_item stores it."""
    item = {"chat_id": -100555, "title": "My Channel", "username": "mychannel",
            "invite_link": None, "button_text": "✅ Join My Channel",
            "kind": "channel", "auto_approve": False, "order": 0}
    item.update(overrides)
    return item


def style_of(button):
    """Colour name of a button ("primary"/"success"/"danger"/None)."""
    style = getattr(button, "style", None)
    if style is None:
        return None
    name = getattr(style, "name", str(style)).lower()
    return None if name == "default" else name


def is_plain(button) -> bool:
    return style_of(button) is None


def test_library_supports_native_styles():
    """Kurigram (requirements.txt) ships ButtonStyle; the bot must use it."""
    assert ui.native_style_support() is True
    assert ui.styles_enabled() is True


def test_button_styles_are_blue_green_red():
    assert ui.STYLE_COLORS == {"primary": "blue", "success": "green", "danger": "red"}

    primary = ui.button("p", callback_data="x", style="primary")
    success = ui.button("s", callback_data="x", style="success")
    danger = ui.button("d", callback_data="x", style="danger")

    assert style_of(primary) == "primary"
    assert style_of(success) == "success"
    assert style_of(danger) == "danger"


def test_invalid_style_is_rejected_loudly():
    with pytest.raises(ValueError):
        ui.button("x", callback_data="x", style="neon-pink")


def test_button_without_action_is_rejected():
    with pytest.raises(ValueError):
        ui.button("nowhere")


def test_start_menu_has_every_requested_button():
    markup = ui.start_keyboard()
    by_data = {b.callback_data: b for b in flat(markup) if b.callback_data}

    expected = {
        "cmd_login": "Login",
        "cmd_logout": "Logout",
        "cmd_settings": "Settings",
        "cmd_stats": "Stats",
        "cmd_premium": "Premium",
        "cmd_refer": "Refer",
        "cmd_help": "Help",
        "cmd_feedback": "Feedback",
        "cmd_language": "Language",
    }
    for data, label in expected.items():
        assert data in by_data, f"{label} button missing"
        # labels are rendered in small caps, the wording itself stays identical
        assert label.lower() in ui.plain_caps(by_data[data].text).lower()

    # every row is at most two buttons (fits on a phone screen)
    assert all(1 <= len(row) <= 2 for row in markup.inline_keyboard)


def test_start_menu_colours():
    by_data = {b.callback_data: b for b in ui.start_keyboard().inline_keyboard[0]}
    assert style_of(by_data["cmd_login"]) == "success"   # green
    assert style_of(by_data["cmd_logout"]) == "danger"   # red

    rest = {b.callback_data: b for b in flat(ui.start_keyboard()) if b.callback_data}
    assert style_of(rest["cmd_settings"]) == "primary"   # blue
    assert style_of(rest["cmd_stats"]) == "primary"


def test_language_menu_marks_current_language():
    markup = ui.language_keyboard("hi")
    by_data = {b.callback_data: b for b in flat(markup)}
    assert by_data["lang_hi"].text.startswith("✅")
    assert style_of(by_data["lang_hi"]) == "success"
    assert not by_data["lang_en"].text.startswith("✅")
    assert style_of(by_data["lang_en"]) == "primary"


def test_settings_menu_labels_follow_state():
    on = {b.callback_data: b.text for b in flat(ui.settings_keyboard(True, False))}
    off = {b.callback_data: b.text for b in flat(ui.settings_keyboard(False, True))}
    on_labels = {k: ui.plain_caps(v) for k, v in on.items()}
    off_labels = {k: ui.plain_caps(v) for k, v in off.items()}
    assert "on" in on_labels["toggle_notif"].lower()
    assert "off" in on_labels["toggle_silent"].lower()
    assert "off" in off_labels["toggle_notif"].lower()
    assert "on" in off_labels["toggle_silent"].lower()


def test_download_controls_colours():
    markup = ui.download_controls("job1", paused=False)
    pause, stop = markup.inline_keyboard[0]
    assert pause.callback_data == "dl:p:job1" and style_of(pause) == "primary"
    assert stop.callback_data == "dl:s:job1" and style_of(stop) == "danger"

    resume = ui.download_controls("job1", paused=True).inline_keyboard[0][0]
    assert resume.callback_data == "dl:r:job1" and style_of(resume) == "success"


def test_refer_keyboard_share_and_copy():
    link = "https://t.me/TestRestrictBot?start=42"
    by_data = {ui.plain_caps(b.text): b for b in flat(ui.refer_keyboard(link))}
    share = next(b for t, b in by_data.items() if "share" in t.lower())
    copy = next(b for t, b in by_data.items() if "copy" in t.lower())
    assert share.url.startswith("https://t.me/share/url?url=")
    assert link in share.url
    assert copy.copy_text.text == link


def test_styles_degrade_gracefully_without_library_support(monkeypatch):
    """Old pyrofork builds have no ButtonStyle — buttons must still be built."""
    monkeypatch.setattr(ui, "native_style_support", lambda: False)
    markup = ui.start_keyboard()
    buttons = flat(markup)
    # Login/Logout, Premium/Refer, Stats/Set channel, My Channels/Help,
    # Settings/Feedback, Language/Share, and the Vmore app footer button.
    assert len(buttons) == 13
    assert all(is_plain(b) for b in buttons)
    # callback data is untouched, so the actions keep working
    assert {b.callback_data for b in buttons} >= {
        "cmd_login", "cmd_language", "cmd_setchat", "cmd_mychannels", "cmd_app",
    }


def test_styles_can_be_forced_off(monkeypatch):
    monkeypatch.setenv("BUTTON_STYLES", "off")
    assert ui.styles_enabled() is False
    assert all(is_plain(b) for b in flat(ui.start_keyboard()))
    monkeypatch.setenv("BUTTON_STYLES", "auto")
    assert ui.styles_enabled() is True


def test_colours_reach_the_wire_format():
    """Build the real MTProto payload and check the colour flags are set."""
    from pyrogram.raw.types import KeyboardButtonStyle, KeyboardInlineButton

    raw = ui.start_keyboard().write(None)  # kurigram builds this synchronously
    buttons = [b for row in raw.rows for b in row.buttons]
    assert all(isinstance(b, KeyboardInlineButton) for b in buttons)

    by_data = {b.type.data.decode(): b for b in buttons}
    assert isinstance(by_data["cmd_login"].style, KeyboardButtonStyle)
    assert by_data["cmd_login"].style.bg_success is True     # green
    assert by_data["cmd_logout"].style.bg_danger is True     # red
    assert by_data["cmd_settings"].style.bg_primary is True  # blue
    assert by_data["cmd_stats"].style.bg_primary is True


def test_every_button_has_exactly_one_action():
    keys = {
        "callback_data", "url", "web_app", "login_url", "user_id",
        "switch_inline_query", "switch_inline_query_current_chat",
        "callback_game", "copy_text", "requires_password",
    }
    for markup in (
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
        ui.fsub_keyboard([fsub_item()]),
        ui.back_keyboard(),
        ui.close_keyboard(),
        ui.download_controls("job", False),
    ):
        for b in flat(markup):
            used = [k for k in keys if getattr(b, k, None) is not None]
            assert len(used) == 1, f"{b.text!r} has {used}"
