"""Round 11 — the standing presentation constraints over every new surface.

The bot's non-negotiable rules, re-checked for everything rounds 7-10 added:

* **Mobile keyboard budget** — at most 7 rows, at most 2 buttons per row, and
  every label at most 28 visible characters.
* **ASCII ``callback_data``** — never a stray non-ASCII byte, never both a
  ``callback_data`` and a ``url`` on the same button, and every ``url`` is
  ``https://``.
* **Links only inside ``url=`` buttons** — no raw link anywhere in body copy.
* **100% English** — zero Devanagari in any string, label or helper.

Each helper is rendered with the arguments the bot really passes it, so a
regression shows up as a named failure rather than a mystery in production.
"""

from __future__ import annotations

import re

import pytest

import config
import ui

ONE_CHANNEL = [{"chat_id": -100777, "title": "Dump", "username": "dump",
                "type": "channel"}]
TWO_CHANNELS = [
    {"chat_id": -100777, "title": "First Channel", "username": "first",
     "type": "channel"},
    {"chat_id": -100888, "title": "Second Supergroup", "username": None,
     "type": "supergroup"},
]
LONG_CHANNELS = [
    {"chat_id": -100777, "title": "A very long channel title indeed",
     "username": None, "type": "channel"},
    {"chat_id": -100888, "title": "Another extremely long title here",
     "username": None, "type": "supergroup"},
]

#: Devanagari block — nothing in the bot's copy may use it.
DEVANAGARI = tuple(chr(code) for code in range(0x0900, 0x0980))


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


NEW_KEYBOARDS = [
    ("open_bot", ui.open_bot_keyboard),
    ("setchat_prompt", ui.setchat_prompt_keyboard),
    ("setchat_check", ui.setchat_check_keyboard),
    ("delchat_choice_one", lambda: ui.delchat_choice_keyboard(ONE_CHANNEL)),
    ("delchat_choice_two", lambda: ui.delchat_choice_keyboard(TWO_CHANNELS)),
    ("delchat_choice_long_titles", lambda: ui.delchat_choice_keyboard(LONG_CHANNELS)),
    ("mychannels_one_entry", lambda: ui.mychannels_keyboard(ONE_CHANNEL)),
    ("mychannels_two_entries", lambda: ui.mychannels_keyboard(TWO_CHANNELS)),
    ("mychannels_bare_id", lambda: ui.mychannels_keyboard(-100777)),
    ("mychannels_empty", lambda: ui.mychannels_keyboard(None, connected=False)),
]

NEW_SCREENS = [
    # Round 9 — the range pre-flight report and its neighbours.
    ("range_scan", lambda: ui.range_scan_text(1, 500)),
    ("range_preflight", lambda: ui.range_preflight_text(1, 500, 412, 31, 57)),
    ("range_preflight_unreadable",
     lambda: ui.range_preflight_text(1, 500, 412, 31, 57, unreadable=4)),
    ("range_nothing", lambda: ui.range_nothing_to_extract_text(1, 500, 500)),
    ("range_preflight_floodwait", lambda: ui.range_preflight_floodwait_text(23)),
    ("range_too_large", lambda: ui.range_too_large_text(40, 20)),
    # Round 8 — the shared batch copy.
    ("batch_heading", lambda: ui.batch_heading_text(6)),
    ("range_heading", lambda: ui.range_heading_text(412)),
    ("batch_item", lambda: ui.batch_item_text(3)),
    ("batch_progress", lambda: ui.batch_progress_text(2, 6)),
    ("batch_done", lambda: ui.batch_done_text(5, 1)),
    ("private_login", ui.private_login_text),
    # Round 6 — limits hit inside a dump channel.
    ("channel_limit_daily", lambda: ui.channel_limit_text("daily", used=3)),
    ("channel_limit_links", lambda: ui.channel_limit_text("links", sent=9)),
    ("channel_limit_range", lambda: ui.channel_limit_text("range", requested=40)),
    ("channel_limit_size", lambda: ui.channel_limit_text("size", size_mb=900.0)),
    ("channel_limit_unknown_kind", lambda: ui.channel_limit_text("nonsense")),
    # Round 4 — two channels per user.
    ("channel_slots_full", lambda: ui.channel_slots_full_text(TWO_CHANNELS)),
    ("channel_slots_full_empty", lambda: ui.channel_slots_full_text([])),
    ("delchat_choice", lambda: ui.delchat_choice_text(TWO_CHANNELS)),
    ("mychannels_two", lambda: ui.mychannels_text(TWO_CHANNELS, files=[4, 9],
                                                  engine=config.ENGINE_CPP)),
    ("mychannels_one", lambda: ui.mychannels_text(ONE_CHANNEL[0], admin_ok=True,
                                                  files=4, engine=config.ENGINE_CPP)),
    # Round 5 — the person adding the channel must administer it.
    ("requester_not_admin", lambda: ui.setchat_requester_failed_text("not_admin", "Dump")),
    ("requester_not_member", lambda: ui.setchat_requester_failed_text("not_member")),
    ("requester_error", lambda: ui.setchat_requester_failed_text("error", "Dump")),
    # Round 7 — registering a private channel by sharing it.
    ("share_prompt", ui.setchat_share_prompt_text),
    ("share_resolved", lambda: ui.setchat_share_resolved_text("Secret")),
    ("share_not_received", lambda: ui.setchat_share_failed_text("not_received")),
    ("share_cancelled", lambda: ui.setchat_share_failed_text("cancelled")),
    ("share_not_a_channel", lambda: ui.setchat_share_failed_text("not_a_channel")),
    ("share_bot_not_in_chat", lambda: ui.setchat_share_failed_text("bot_not_in_chat")),
    ("share_cannot_see", lambda: ui.setchat_share_failed_text("cannot_see")),
    ("share_not_admin", lambda: ui.setchat_share_failed_text("not_admin")),
    ("share_unknown", lambda: ui.setchat_share_failed_text("something-else")),
    # Round 8 — verification with a real content link.
    ("admin_ok_public", lambda: ui.setchat_admin_ok_text("Dump")),
    ("admin_ok_private", lambda: ui.setchat_admin_ok_text("Dump", private=True)),
    ("sample_wrong_chat", lambda: ui.setchat_sample_failed_text("wrong_chat")),
    ("sample_deleted", lambda: ui.setchat_sample_failed_text("deleted")),
    ("sample_no_access", lambda: ui.setchat_sample_failed_text("no_access")),
    ("sample_not_a_link", lambda: ui.setchat_sample_failed_text("not_a_link")),
    ("sample_unreadable", lambda: ui.setchat_sample_failed_text()),
    ("setchat_prompt", ui.setchat_prompt_text),
    # Rounds 2 and 10 — the corrected engine claims.
    ("speed_cap", ui.speed_cap_label),
    ("speed_cap_disabled", lambda: ui.speed_cap_label(0)),
    ("models_upsell", ui.models_upsell_text),
    ("models_architecture", lambda: ui.models_architecture_text(config.ENGINE_CPP)),
]


@pytest.mark.parametrize("name,build", NEW_KEYBOARDS, ids=[n for n, _ in NEW_KEYBOARDS])
def test_mobile_budget_holds_for_every_new_keyboard(name, build):
    rows = build().inline_keyboard
    assert 1 <= len(rows) <= 7, f"{name}: {len(rows)} rows"
    for row in rows:
        assert 1 <= len(row) <= 2, f"{name}: a row of {len(row)} buttons"
        for each in row:
            label = ui.plain_caps(each.text)
            assert len(label) <= 28, f"{name}: {label!r} is {len(label)} characters"


@pytest.mark.parametrize("name,build", NEW_KEYBOARDS, ids=[n for n, _ in NEW_KEYBOARDS])
def test_callback_data_is_ascii_and_links_only_live_in_url_buttons(name, build):
    for each in flat(build()):
        if each.callback_data is not None:
            assert each.callback_data.isascii(), each.callback_data
            assert each.callback_data == each.callback_data.strip()
            assert each.url is None, "a button is either a callback or a link"
        if each.url is not None:
            assert each.url.startswith("https://"), each.url
            assert each.callback_data is None


@pytest.mark.parametrize("name,build", NEW_SCREENS, ids=[n for n, _ in NEW_SCREENS])
def test_new_copy_is_english_only_and_link_free(name, build):
    text = build()
    assert text.strip(), f"{name} rendered nothing"
    assert not any(char in text for char in DEVANAGARI), f"{name} contains Devanagari"
    assert "http://" not in text and "https://" not in text, \
        f"{name} prints a raw link — links belong in url= buttons"
    #: An inline-code span documents a link *format*; it is not clickable, so
    #: only the prose is checked.
    prose = re.sub(r"`[^`]*`", "", text)
    assert "t.me/" not in prose.replace(f"t.me/{config.BOT_USERNAME}", ""), \
        f"{name} prints a Telegram link outside a button"


def test_the_open_bot_button_is_the_only_way_out_of_a_channel_limit():
    """The channel escape hatch is a url= button, never a pasted link."""
    buttons = flat(ui.open_bot_keyboard())
    assert len(buttons) == 1
    assert buttons[0].url == f"https://t.me/{config.BOT_USERNAME}"
    assert buttons[0].callback_data is None
    for kind in ("daily", "links", "range", "size"):
        assert "button below" in ui.channel_limit_text(kind).lower()


def test_no_channel_limit_advertises_a_personal_command():
    """A dump channel is not a dashboard: no /premium, /refer or /models pitch."""
    for kind in ("daily", "links", "range", "size"):
        lowered = ui.channel_limit_text(kind).lower()
        for command in ("/premium", "/refer", "/models", "/mychannels", "/start"):
            assert command not in lowered
        #: The buttons offered are the open-bot url button only.
        assert all(b.callback_data is None for b in flat(ui.open_bot_keyboard()))


def test_the_share_flow_never_prints_a_chat_id_or_an_invite_link():
    for reason in ("not_received", "cancelled", "not_a_channel", "bot_not_in_chat",
                   "cannot_see", "not_admin", "unknown"):
        text = ui.setchat_share_failed_text(reason)
        assert "t.me/+" not in text and "joinchat" not in text
        assert not re.search(r"-100\d{6,}", text), f"{reason} leaked a raw chat id"


def test_the_requester_refusal_never_leaks_a_link_or_an_id():
    for reason in ("not_admin", "not_member", "error"):
        text = ui.setchat_requester_failed_text(reason, "Some Channel")
        assert "t.me/" not in text
        assert "Traceback" not in text
        assert not re.search(r"-100\d{6,}", text)
        #: Every refusal tells the user the concrete next step.
        assert "/setchat" in text


def test_the_content_link_step_names_the_next_action_for_every_failure():
    for reason in ("wrong_chat", "deleted", "no_access", "not_a_link", "unreadable"):
        text = ui.setchat_sample_failed_text(reason)
        assert "👉" in text, f"{reason} has no next step"
        assert "still running" in text, f"{reason} must say the wizard stays alive"
        assert not re.search(r"\bt\.me/\w+/\d+\b", text), "no echoed link"


def test_the_bare_number_prompt_is_gone_from_the_whole_ui_module():
    source = open("ui.py", encoding="utf-8").read()
    assert "just the message number" not in source
    assert "message number (for example" not in source
    assert "for example `15`" not in source


def test_engine_pages_never_claim_a_native_cipher_as_a_turbo_feature():
    for text in (ui.models_architecture_text(config.ENGINE_CPP),
                 ui.models_upsell_text()):
        lowered = text.lower()
        assert "tgcrypto" not in lowered
        assert "native c cipher" not in lowered


def test_the_two_channel_dashboard_stays_inside_the_mobile_budget():
    rows = ui.mychannels_keyboard(TWO_CHANNELS).inline_keyboard
    #: 2 channels x 3 actions = 6 buttons -> 3 rows, plus the footer row.
    assert len(rows) == 4
    assert sum(len(row) for row in rows) == 8
