"""Round 22 — one price per plan, the Turbo add-on removed, and /testmode.

The owner asked for three things:

* the C++ Turbo / "models" upsell is useless — delete it from premium;
* **one price per plan**, no Standard vs with-Turbo variant and no add-on;
* an owner-only ``/testmode`` that walks the whole flow screen by screen, lets
  the owner type **any** amount, and shows exactly what happens after payment —
  with no charge and no real user affected.

This module pins all three, including the promise that the dry run writes
nothing anywhere.
"""

from __future__ import annotations

import pytest

import config
import main
import testmode
import ui


def plain(text) -> str:
    return ui.plain_caps(text or "").lower()


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def callbacks(message):
    return [b.callback_data for row in message.shown_markup.inline_keyboard
            for b in row if b.callback_data]


def owner_message(text=""):
    from conftest import FakeMessage, FakeUser
    return FakeMessage(text=text, user=FakeUser(main.OWNER_ID))


def user_message(user_id, text=""):
    from conftest import FakeMessage, FakeUser
    return FakeMessage(text=text, user=FakeUser(user_id))


# --------------------------------------------------------------------------- #
#  1. One price per plan
# --------------------------------------------------------------------------- #

def test_every_plan_has_exactly_one_price():
    plans = config.PREMIUM_PLANS
    assert sorted(config.plan_base_price(p) for p in plans.values()) == [99, 249, 700]
    for plan in plans.values():
        assert config.plan_total_price(plan) == config.plan_base_price(plan)
        assert config.plan_addon_price(plan) == 0
        assert "addon_price" not in plan
        assert "turbo_price" not in plan
        assert "variants" not in plan


def test_no_turbo_benefit_list_survives_in_config():
    assert not hasattr(config, "TURBO_BENEFITS")
    for text in config.GIVEAWAY_BENEFIT_SUGGESTIONS:
        assert "turbo" not in str(text).lower()


def test_the_plan_chooser_sells_one_button_per_duration():
    data = [b.callback_data for b in flat(ui.plans_keyboard())]
    for key in config.PREMIUM_PLANS:
        assert f"buy:{key}" in data
        assert f"buy:{key}:turbo" not in data
    buys = [d for d in data if d and d.startswith("buy:")]
    assert len(buys) == len(config.PREMIUM_PLANS)


def test_the_premium_page_promises_one_price_and_nothing_else():
    text = plain(ui.premium_overview(False, {"premium_source": None}))
    assert "one price" in text
    assert "c++ turbo" not in text
    assert "add-on" in text and "no add-ons" in text
    for gone in ("turbo_cpp", "cmd_models", "buy:month:turbo"):
        assert gone not in " ".join(
            b.callback_data or "" for b in flat(ui.premium_overview_keyboard()))


def test_the_payment_screen_shows_the_plan_price_only():
    month = config.PREMIUM_PLANS["month"]
    text = plain(ui.payment_text(month))
    assert "99" in text
    assert "149" not in text
    #: A legacy caller that still passes ``turbo=True`` renders the same screen.
    assert text == plain(ui.payment_text(month, turbo=True))


def test_the_grant_has_two_tiers_and_legacy_names_still_map():
    assert config.GRANT_TIER_KEYS == ("public", "private")
    assert config.GRANT_TIERS["public"]["has_private_access"] is False
    assert config.GRANT_TIERS["private"]["has_private_access"] is True
    for legacy, expected in config.LEGACY_TIER_ALIASES.items():
        assert main.normalize_tier(legacy) == expected
    assert main.normalize_tier("models") == "public"


# --------------------------------------------------------------------------- #
#  2. /testmode — the walkthrough data
# --------------------------------------------------------------------------- #

def test_every_step_renders_a_banner_and_a_next_line():
    assert len(testmode.STEPS) >= 8
    for key, label in testmode.STEPS:
        text, rows = testmode.screen(key)
        assert label in text
        assert testmode.TEST_BANNER.split(" — ")[0] in text
        assert "NEXT" in plain(text).upper()
        assert rows, key
        labels = [label for row in rows for label, _data in row]
        assert any("Exit" in each for each in labels), key


def test_the_steps_run_in_journey_order():
    keys = [key for key, _label in testmode.STEPS]
    assert keys[0] == "start"
    assert keys.index("payment") < keys.index("proof")
    assert keys.index("proof") < keys.index("approved")
    assert testmode.next_key("start") == keys[1]
    assert testmode.prev_key(keys[1]) == "start"
    assert testmode.next_key(keys[-1]) == keys[-1]
    assert testmode.prev_key(keys[0]) == keys[0]


def test_the_payment_step_really_renders_the_plan_price():
    text = plain(testmode.screen("payment", plan_key="year")[0])
    assert "700" in text
    assert "payment details" in text


@pytest.mark.parametrize("amount,kind,plan,days", [
    (99, "exact", "month", 30),
    (249, "exact", "quarter", 90),
    (700, "exact", "year", 365),
    (40, "underpaid", None, 0),
    (150, "partial", "month", 30),
    (900, "overpaid", "year", 365),
    (0, "invalid", None, 0),
    ("nonsense", "invalid", None, 0),
])
def test_a_custom_amount_is_classified_honestly(amount, kind, plan, days):
    outcome = testmode.amount_outcome(amount)
    assert outcome["kind"] == kind
    assert outcome["plan"] == plan
    assert outcome["days"] == days


def test_a_custom_amount_reaches_the_payment_screen_verbatim():
    text, _rows = testmode.screen("custom", amount=149)
    body = plain(text)
    assert "149" in body
    assert "between two plans" in body
    assert "nothing is activated" in body


# --------------------------------------------------------------------------- #
#  3. /testmode — the owner-only bot flow
# --------------------------------------------------------------------------- #

async def test_a_normal_user_is_refused(db):
    await db.add_user(1001, "Tester")
    message = user_message(1001, "/testmode")
    await main.testmode_handler(None, message)
    assert "owner only" in plain(message.shown_text)
    assert 1001 not in main.TESTMODE


async def test_the_owner_starts_on_step_one(db):
    await db.add_user(main.OWNER_ID, "Owner")
    message = owner_message("/testmode")
    await main.testmode_handler(None, message)
    assert main.TESTMODE[main.OWNER_ID]["step"] == "start"
    assert "TEST MODE" in message.shown_text.upper() or "test mode" in plain(
        message.shown_text)
    data = callbacks(message)
    for control in ("tm:next", "tm:prev", "tm:amount", "tm:list", "tm:exit"):
        assert control in data


async def test_next_walks_every_step_and_never_writes_anything(db, press):
    await db.add_user(main.OWNER_ID, "Owner")
    before = dict(db.users[main.OWNER_ID])
    message = owner_message("/testmode")
    await main.testmode_handler(None, message)

    seen = [main.TESTMODE[main.OWNER_ID]["step"]]
    for _ in range(len(testmode.STEPS) - 1):
        await press(message, "tm:next")
        seen.append(main.TESTMODE[main.OWNER_ID]["step"])
    assert seen == [key for key, _label in testmode.STEPS]

    #: The dry run must leave the account exactly as it was.
    assert db.users[main.OWNER_ID] == before
    assert main.payment_pending == {}
    assert db.users[main.OWNER_ID]["is_premium"] is False


async def test_the_step_list_jumps_straight_to_a_screen(db, press):
    await db.add_user(main.OWNER_ID, "Owner")
    message = owner_message("/testmode")
    await main.testmode_handler(None, message)
    await press(message, "tm:list")
    data = callbacks(message)
    for key, _label in testmode.STEPS:
        assert f"tm:s:{key}" in data
    await press(message, "tm:s:approved")
    assert main.TESTMODE[main.OWNER_ID]["step"] == "approved"
    assert "after approval" in plain(message.shown_text)


async def test_a_typed_amount_shows_its_own_payment_screen(db):
    await db.add_user(main.OWNER_ID, "Owner")
    message = owner_message("/testmode")
    await main.testmode_handler(None, message)
    from conftest import FakeUser, make_query
    await main.handle_testmode_callback(
        None, make_query(message, "tm:amount", FakeUser(main.OWNER_ID)), "tm:amount")
    assert main.TESTMODE[main.OWNER_ID]["await"] == "amount"

    typed = owner_message("199")
    await main.text_handler(None, typed)
    state = main.TESTMODE[main.OWNER_ID]
    assert state["amount"] == 199 and state["step"] == "custom"
    body = plain(typed.shown_text)
    assert "199" in body
    assert "payment details" in body
    #: Nothing charged, nothing stored on the account.
    assert db.users[main.OWNER_ID]["is_premium"] is False


async def test_a_bad_amount_reasks_instead_of_crashing(db):
    await db.add_user(main.OWNER_ID, "Owner")
    message = owner_message("/testmode")
    await main.testmode_handler(None, message)
    main.TESTMODE[main.OWNER_ID]["await"] = "amount"

    typed = owner_message("not a number")
    await main.text_handler(None, typed)
    assert "plain number" in plain(typed.shown_text)
    assert main.TESTMODE[main.OWNER_ID].get("amount") is None

    zero = owner_message("0")
    await main.text_handler(None, zero)
    assert "more than zero" in plain(zero.shown_text)


async def test_an_amount_can_be_passed_straight_into_the_command(db):
    await db.add_user(main.OWNER_ID, "Owner")
    message = owner_message("/testmode 249")
    await main.testmode_handler(None, message)
    assert main.TESTMODE[main.OWNER_ID]["amount"] == 249
    assert main.TESTMODE[main.OWNER_ID]["step"] == "custom"
    assert "249" in plain(message.shown_text)


async def test_exit_clears_the_dry_run_and_returns_the_real_menu(db, press):
    await db.add_user(main.OWNER_ID, "Owner")
    message = owner_message("/testmode")
    await main.testmode_handler(None, message)
    await press(message, "tm:exit")
    assert main.OWNER_ID not in main.TESTMODE
    assert "test mode closed" in plain(message.shown_text)
    assert "cmd_premium" in callbacks(message)


async def test_testmode_callbacks_are_owner_only(db, press):
    await db.add_user(1001, "Tester")
    message = user_message(1001, "/start")
    await press(message, "tm:next")
    assert 1001 not in main.TESTMODE


async def test_cancel_drops_the_dry_run_state(db):
    await db.add_user(main.OWNER_ID, "Owner")
    main.TESTMODE[main.OWNER_ID] = {"step": "payment", "amount": None, "await": None}
    await main.clear_pending_inputs(main.OWNER_ID)
    assert main.OWNER_ID not in main.TESTMODE


def test_the_dry_run_is_registered_as_an_owner_command():
    assert "testmode" in main.COMMAND_NAMES
    assert "testmode" in main.COMMAND_HANDLERS
    assert "testmode" in main.MENU_OWNER_ONLY, "admins never see the dry run"
    assert "testmode" not in {c.command for c in main.telegram_commands("user")}
    assert "testmode" not in {c.command for c in main.telegram_commands("admin")}
