from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

import config
import main
import ui
from conftest import FakeMessage, FakeUser, make_query
from pyrogram.raw import types as raw_types


class FakePreCheckoutQuery:
    def __init__(self, *, payload, user_id=1001, currency="XTR", total_amount=49):
        self.invoice_payload = payload
        self.from_user = SimpleNamespace(id=user_id)
        self.currency = currency
        self.total_amount = total_amount
        self.answers: list[dict] = []

    async def answer(self, ok=None, error_message=None):
        self.answers.append({"ok": ok, "error_message": error_message})
        return True


@pytest.mark.asyncio
async def test_kurigram_invoice_constructor_matches_pinned_version():
    signature = inspect.signature(raw_types.InputMediaInvoice.__init__)

    assert "title_param" not in signature.parameters
    assert {"title", "description", "invoice", "payload", "provider_data"} <= set(signature.parameters)

    invoice = raw_types.InputMediaInvoice(
        title="1 month Premium",
        description="Premium 1 month",
        invoice=raw_types.Invoice(
            currency="XTR",
            prices=[raw_types.LabeledPrice(label="1 month", amount=49)],
        ),
        payload=b"stars_month_1001_test",
        provider_data=raw_types.DataJSON(data="{}"),
    )
    assert invoice.invoice.currency == "XTR"
    assert invoice.invoice.prices[0].amount == 49
    assert invoice.provider is None
    assert invoice.provider_data.data == "{}"
    assert not hasattr(invoice, "title_param")


def test_existing_stars_prices_and_callbacks_are_unchanged():
    assert main.stars_amount_for_plan(config.PREMIUM_PLANS["month"]) == 49
    assert main.stars_amount_for_plan(config.PREMIUM_PLANS["quarter"]) == 124
    assert main.stars_amount_for_plan(config.PREMIUM_PLANS["year"]) == 350

    keyboard_data = [
        button.callback_data
        for row in ui.stars_plans_keyboard().inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "stars_buy:month" in keyboard_data
    assert "stars_buy:quarter" in keyboard_data
    assert "stars_buy:year" in keyboard_data
    assert len(keyboard_data) == len(set(keyboard_data))
    assert main.CALLBACK_ACTIONS["stars_buy:month"] is main.cb_stars_buy_month
    assert main.CALLBACK_ACTIONS["stars_buy:quarter"] is main.cb_stars_buy_quarter
    assert main.CALLBACK_ACTIONS["stars_buy:year"] is main.cb_stars_buy_year
    assert main.CALLBACK_ACTIONS["stars_plans"] is main.cb_stars_plans


@pytest.mark.asyncio
async def test_stars_buy_builds_kurigram_xtr_invoice_without_title_param(db, fake_bot, monkeypatch):
    invoked = []

    async def record_invoke(query, *args, **kwargs):
        invoked.append(query)
        return True

    monkeypatch.setattr(fake_bot, "invoke", record_invoke)
    monkeypatch.setattr(fake_bot, "rnd_id", lambda: 123456, raising=False)

    message = FakeMessage(user=FakeUser(1001))
    query = make_query(message, "stars_buy:month")
    await main.handle_stars_buy(None, query, "month")

    assert invoked, "the invoice was not sent through raw SendMedia"
    sent = invoked[0]
    media = sent.media
    assert isinstance(media, raw_types.InputMediaInvoice)
    assert not hasattr(media, "title_param")
    assert media.provider is None
    assert media.provider_data.data == "{}"
    assert media.invoice.currency == "XTR"
    assert media.invoice.prices[0].label == "1 month"
    assert media.invoice.prices[0].amount == 49

    payload = media.payload.decode()
    parsed = main.parse_stars_payload(payload)
    assert parsed == {"plan_key": "month", "user_id": 1001, "nonce": parsed["nonce"]}
    row = await db.get_stars_payment(payload)
    assert row["status"] == "pending"
    assert row["stars_amount"] == 49
    assert query.answer.calls[-1]["show_alert"] is None


@pytest.mark.asyncio
async def test_pre_checkout_validates_payload_currency_amount_and_pending_record(db):
    payload = "stars_quarter_1001_deadbeef"
    await db.add_stars_payment(1001, "quarter", 124, 249, payload)

    ok_query = FakePreCheckoutQuery(payload=payload, total_amount=124)
    await main.pre_checkout_handler(None, ok_query)
    assert ok_query.answers == [{"ok": True, "error_message": None}]

    wrong_amount = FakePreCheckoutQuery(payload=payload, total_amount=125)
    await main.pre_checkout_handler(None, wrong_amount)
    assert wrong_amount.answers[-1]["ok"] is False
    assert "amount" in wrong_amount.answers[-1]["error_message"].lower()

    wrong_currency = FakePreCheckoutQuery(payload=payload, currency="USD", total_amount=124)
    await main.pre_checkout_handler(None, wrong_currency)
    assert wrong_currency.answers[-1]["ok"] is False
    assert "currency" in wrong_currency.answers[-1]["error_message"].lower()

    wrong_user = FakePreCheckoutQuery(payload=payload, user_id=2002, total_amount=124)
    await main.pre_checkout_handler(None, wrong_user)
    assert wrong_user.answers[-1]["ok"] is False
    assert "user" in wrong_user.answers[-1]["error_message"].lower()


@pytest.mark.asyncio
async def test_successful_payment_activates_once_and_stores_charge_id(db, fake_bot):
    payload = "stars_year_1001_deadbeef"
    await db.add_stars_payment(1001, "year", 350, 700, payload)

    message = FakeMessage(user=FakeUser(1001))
    message.successful_payment = SimpleNamespace(
        currency="XTR",
        total_amount=350,
        invoice_payload=payload,
        telegram_payment_charge_id="tg-charge-1",
        provider_payment_charge_id="",
    )

    await main.successful_payment_handler(None, message)

    row = await db.get_stars_payment(payload)
    assert row["status"] == "completed"
    assert row["telegram_payment_charge_id"] == "tg-charge-1"
    user = db.users[1001]
    assert user["is_premium"] is True
    assert user["premium_tier"] == "private"
    assert user["has_private_access"] is True
    assert user["has_models_access"] is False
    first_expiry = user["premium_expiry"]
    assert message.replies, "the user should get a clean success confirmation"

    duplicate = FakeMessage(user=FakeUser(1001))
    duplicate.successful_payment = message.successful_payment
    await main.successful_payment_handler(None, duplicate)

    assert db.users[1001]["premium_expiry"] == first_expiry
    assert not duplicate.replies
    assert len([row for row in db.stars_payments if row["invoice_payload"] == payload]) == 1
