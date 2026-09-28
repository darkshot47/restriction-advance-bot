"""End-to-end handler regressions; Telegram is replaced, not contacted."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram.enums import ChatMemberStatus

import main
import ui
from conftest import FakeMessage, FakeUser


@pytest.mark.asyncio
async def test_purchase_is_benefits_then_plans_then_qr_then_photo(db, press, fake_bot):
    message = FakeMessage(text="/premium")
    uid = message.from_user.id
    await main.premium_handler(None, message)
    assert all(f"₹{price}" in message.shown_text for price in [99, 249, 700])
    assert "premium_plans" in message.callback_data()
    assert not any(x.startswith("buy:") for x in message.callback_data())
    assert not fake_bot.sent

    await press(message, "premium_plans")
    assert {"buy:month", "buy:quarter", "buy:year"} <= set(message.callback_data())
    await db.set_qr("owner-qr")
    await press(message, "buy:quarter")
    qr = fake_bot.sent[-1]
    assert qr["photo"] == "owner-qr"
    assert "₹249" in qr["caption"]
    assert uid not in main.pending_action
    paid = qr["reply_markup"].inline_keyboard[0][0].callback_data
    await press(message, paid)
    assert main.pending_action[uid] == "payment_proof"
    assert "screenshot" in message.shown_text.lower()
    message.photo = SimpleNamespace(file_id="receipt")
    await main.photo_handler(None, message)
    assert db.payments[0]["note"]["plan"] == "quarter"
    assert db.payments[0]["note"]["price"] == 249
    assert db.payments[0]["note"]["days"] == 90
    assert not db.users[uid]["is_premium"]
    assert any(x.get("photo") == "receipt" and x["chat_id"] == main.OWNER_ID for x in fake_bot.sent)
    assert any(x.get("photo") == "receipt" and x["chat_id"] == "XyrDeveloper" for x in fake_bot.sent)
    assert uid not in main.pending_action and uid not in main.payment_pending
    # Duplicate receipt is not recorded again.
    await main.photo_handler(None, message)
    assert len(db.payments) == 1


@pytest.mark.asyncio
async def test_missing_qr_does_not_request_or_accept_proof(db, press, fake_bot):
    message = FakeMessage()
    await press(message, "buy:month")
    assert "temporarily unavailable" in message.shown_text
    assert not main.payment_pending and not main.pending_action and not fake_bot.sent


@pytest.mark.asyncio
async def test_expired_checkout_and_text_proof(db, press):
    message = FakeMessage()
    query = await press(message, "paid:old-token")
    assert "expired" in query.answer.texts[-1]
    await db.set_qr("qr")
    await press(message, "buy:month")
    await press(message, "paid:" + main.payment_pending[1001]["token"])
    message.text = "Paid successfully"
    await main.text_handler(None, message)
    assert "Screenshot required" in message.replies[-1]["text"]
    assert main.pending_action[1001] == "payment_proof"
    assert not getattr(db, "payments", [])


@pytest.mark.asyncio
async def test_undeliverable_proof_is_saved_and_not_falsely_marked_sent(db, fake_bot, monkeypatch):
    uid = 1001
    main.payment_pending[uid] = {"plan": "year", "token": "abc"}
    main.pending_action[uid] = "payment_proof"
    message = FakeMessage()
    message.photo = SimpleNamespace(file_id="proof")
    monkeypatch.setattr(fake_bot, "send_photo", AsyncMock(side_effect=RuntimeError("blocked")))
    await main.photo_handler(None, message)
    assert len(db.payments) == 1
    assert "delivery unavailable" in message.shown_text
    assert "@XyrDeveloper" in message.shown_text


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/premium", "/new_unknown", "/help@TestRestrictBot"])
async def test_any_slash_command_aborts_feedback(db, command):
    message = FakeMessage(text=command)
    main.pending_action[1001] = "feedback"
    await main.abort_pending_on_command(None, message)
    assert not main.pending_action
    assert not db.feedback


@pytest.mark.asyncio
async def test_unknown_command_is_never_saved_as_feedback(db):
    main.pending_action[1001] = "feedback"
    await main.text_handler(None, FakeMessage(text="/newcommand"))
    assert not db.feedback
    assert not main.pending_action


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cmd_premium", "home", "close"])
async def test_navigation_aborts_feedback(db, press, action):
    main.pending_action[1001] = "feedback"
    await press(FakeMessage(), action)
    assert not main.pending_action


@pytest.mark.asyncio
async def test_cancel_clears_checkout(db, press):
    main.payment_pending[1001] = {"plan": "year", "token": "abc"}
    await press(FakeMessage(), "cancel_action")
    assert not main.payment_pending


@pytest.mark.asyncio
@pytest.mark.parametrize("premium,source", [(False, None), (True, "redeem"), (True, None)])
@pytest.mark.parametrize("link", ["https://t.me/c/12345/10", "https://t.me/c/12345/10-12", "https://t.me/publicname/1\nhttps://t.me/c/12345/10"])
async def test_private_links_blocked_before_fetch_for_nonmanual_users(db, monkeypatch, premium, source, link):
    await db.add_user(1001, "Tester")
    db.users[1001].update(is_premium=premium, premium_source=source)
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    message = FakeMessage(text=link)
    await main.text_handler(None, message)
    fetch.assert_not_called()
    assert "This bot extracts restricted content from public channels only." in message.shown_text


@pytest.mark.asyncio
async def test_only_owner_can_grant_private_access(db, press, monkeypatch):
    grant = AsyncMock()
    monkeypatch.setattr(main, "add_premium", grant)
    db.admins.add(1001)
    await main.addpremium_handler(None, FakeMessage(text="/addpremium 2002 30"))
    grant.assert_not_called()
    await press(FakeMessage(), "admin:addpremium")
    assert not main.admin_pending
    await db.add_user(2002, "Recipient")
    await main.addpremium_handler(None, FakeMessage(text="/addpremium 2002 30", user=FakeUser(main.OWNER_ID)))
    grant.assert_awaited_once_with(2002, 30)


@pytest.mark.asyncio
async def test_forged_admin_broadcast_cannot_establish_prompt(db, press):
    await press(FakeMessage(), "admin:broadcast")
    assert not main.admin_pending


@pytest.mark.asyncio
async def test_free_quota_and_refunds_on_actual_extraction_entry(db, monkeypatch):
    fetch = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "_fetch_and_send", fetch)
    message = FakeMessage()
    results = await asyncio.gather(*[
        main.fetch_and_send(message, FakeMessage(), main.bot, "publicname", i)
        for i in range(8)
    ])
    assert results.count(True) == 3
    assert db.users[1001]["daily_downloads"] == 3
    assert db.users[1001]["downloads"] == 3
    assert fetch.await_count == 3
    db.users[1001]["daily_downloads"] = 0
    fetch.return_value = False
    assert not await main.fetch_and_send(message, FakeMessage(), main.bot, "publicname", 1)
    assert db.users[1001]["daily_downloads"] == 0


@pytest.mark.asyncio
async def test_manual_and_points_premium_have_no_daily_limit(db, monkeypatch):
    await db.add_user(1001, "Tester")
    db.users[1001].update(is_premium=True, premium_source="redeem", daily_downloads=100)
    monkeypatch.setattr(main, "_fetch_and_send", AsyncMock(return_value=True))
    assert await main.fetch_and_send(FakeMessage(), FakeMessage(), main.bot, "publicname", 1)
    assert not await main.private_access(1001)
    db.users[1001]["premium_source"] = "manual"
    assert await main.private_access(1001)
    assert await main.fetch_and_send(FakeMessage(), FakeMessage(), main.bot, -1001234, 1)


@pytest.mark.asyncio
async def test_membership_is_checked_again_on_each_extraction(db, fake_bot, monkeypatch):
    db.fsub = "@channel"
    fake_bot.members[1001] = SimpleNamespace(status=ChatMemberStatus.LEFT)
    fetch = AsyncMock()
    monkeypatch.setattr(main, "_fetch_and_send", fetch)
    message = FakeMessage()
    assert not await main.fetch_and_send(message, FakeMessage(), main.bot, "publicname", 1)
    assert "remain joined" in message.shown_text
    fetch.assert_not_called()


@pytest.mark.parametrize("member,expected", [
    (SimpleNamespace(status=ChatMemberStatus.MEMBER), True),
    (SimpleNamespace(status=ChatMemberStatus.BANNED), False),
    (SimpleNamespace(status=ChatMemberStatus.RESTRICTED, is_member=False), False),
    (SimpleNamespace(status=ChatMemberStatus.RESTRICTED, is_member=True), True),
])
def test_membership_enum_handling(member, expected):
    assert main.joined_channel(member) is expected


@pytest.mark.asyncio
async def test_free_native_copy_edits_caption_after_copy(db):
    source = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=44,
        caption="Original caption",
        photo=object(),
        video=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
        text=None,
    )
    copied = SimpleNamespace(edit_caption=AsyncMock())
    fetch_client = SimpleNamespace(
        get_messages=AsyncMock(return_value=source),
        copy_message=AsyncMock(return_value=copied),
    )
    message = FakeMessage()

    assert await main.try_native_copy(message, fetch_client, "publicname", source.id)
    fetch_client.copy_message.assert_awaited_once_with(
        chat_id=message.chat.id,
        from_chat_id=source.chat.id,
        message_id=source.id,
    )
    copied.edit_caption.assert_awaited_once_with(
        caption="Original caption\nExtracted by @wantedkar99bot",
        parse_mode=main.ParseMode.DISABLED,
    )
    assert not message.replies


@pytest.mark.asyncio
@pytest.mark.parametrize("premium", [False, True])
async def test_watermark_preserves_original_caption_and_is_free_only(db, monkeypatch, fake_bot, tmp_path, premium):
    await db.add_user(1001, "Tester")
    db.users[1001].update(is_premium=premium, caption="custom replacement" if not premium else None)
    media = SimpleNamespace(empty=False, media=True, text=None, caption="Original **caption** <text>",
                            photo=True, video=None, document=None, audio=None, voice=None,
                            sticker=None, animation=None, video_note=None)
    path = tmp_path / "download.jpg"
    path.write_bytes(b"image")
    monkeypatch.setattr(main, "try_native_copy", AsyncMock(return_value=False))
    monkeypatch.setattr(fake_bot, "get_messages", AsyncMock(return_value=media), raising=False)
    monkeypatch.setattr(fake_bot, "download_media", AsyncMock(return_value=str(path)))
    assert await main.fetch_and_send(FakeMessage(), FakeMessage(), fake_bot, "publicname", 1)
    caption = fake_bot.sent[-1]["caption"]
    assert caption.startswith(media.caption)
    assert ("Extracted by @wantedkar99bot" in caption) is not premium


def test_mobile_button_labels_and_complete_admin_pages():
    pages = [main.admin_panel_keyboard(i) for i in range(len(main.ADMIN_PAGES))]
    names = {b.callback_data for page in pages for row in page.inline_keyboard for b in row}
    assert {"admin:addpremium", "admin:payments", "admin:addqr", "admin:removeqr", "admin:export", "admin:setfsub"} <= names
    for markup in pages + [ui.premium_overview_keyboard(), ui.plans_keyboard(), ui.payment_keyboard("x")]:
        assert len(markup.inline_keyboard) <= 6
        assert all(len(row) <= 2 for row in markup.inline_keyboard)
        assert all(len(button.text) <= 24 for row in markup.inline_keyboard for button in row)


def test_text_splitting_is_lossless_and_telegram_safe():
    text = "😀" * 4096 + "\nExtracted by @wantedkar99bot"
    chunks = list(ui.split_text(text, 4096))
    assert "".join(chunks) == text
    assert all(ui.utf16_length(x) <= 4096 for x in chunks)


@pytest.mark.asyncio
async def test_redeem_command_requests_one_calendar_month(db, monkeypatch):
    redeem = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "redeem_points", redeem)
    message = FakeMessage(text="/redeem")
    await main.redeem_handler(None, message)
    redeem.assert_awaited_once_with(1001, 100, months=1)
    assert "1 month" in message.shown_text


@pytest.mark.asyncio
async def test_qr_delivery_failure_does_not_leave_active_checkout(db, press, fake_bot, monkeypatch):
    await db.set_qr("invalid-file-id")
    monkeypatch.setattr(fake_bot, "send_photo", AsyncMock(side_effect=RuntimeError("invalid file")))
    message = FakeMessage()
    await press(message, "buy:year")
    assert not main.payment_pending
    assert "Could not display" in message.shown_text


@pytest.mark.asyncio
async def test_long_free_caption_keeps_original_on_media(db, monkeypatch, fake_bot, tmp_path):
    original = "A" * 1024
    media = SimpleNamespace(empty=False, media=True, text=None, caption=original,
                            photo=True, video=None, document=None, audio=None, voice=None,
                            sticker=None, animation=None, video_note=None)
    path = tmp_path / "download.jpg"
    path.write_bytes(b"image")
    monkeypatch.setattr(main, "try_native_copy", AsyncMock(return_value=False))
    monkeypatch.setattr(fake_bot, "get_messages", AsyncMock(return_value=media), raising=False)
    monkeypatch.setattr(fake_bot, "download_media", AsyncMock(return_value=str(path)))
    message = FakeMessage()
    assert await main.fetch_and_send(message, FakeMessage(), fake_bot, "publicname", 1)
    assert fake_bot.sent[-1]["caption"] == original
    assert message.replies[-1]["text"] == "Extracted by @wantedkar99bot"


@pytest.mark.asyncio
@pytest.mark.parametrize("premium", [False, True])
async def test_text_only_content_keeps_original_and_free_attribution(db, monkeypatch, fake_bot, premium):
    await db.add_user(1001, "Tester")
    db.users[1001]["is_premium"] = premium
    original = "Original <text> **not to be removed**"
    media = SimpleNamespace(empty=False, media=False, text=original)
    monkeypatch.setattr(main, "try_native_copy", AsyncMock(return_value=False))
    monkeypatch.setattr(fake_bot, "get_messages", AsyncMock(return_value=media), raising=False)
    message = FakeMessage()
    assert await main.fetch_and_send(message, FakeMessage(), fake_bot, "publicname", 1)
    expected = original if premium else original + "\nExtracted by @wantedkar99bot"
    assert message.replies[-1]["text"] == expected


@pytest.mark.parametrize("link,expected", [
    ("https://t.me/c/1234/5?single", (-1001234, 5, True)),
    ("https://t.me/c/1234/8/5", (-1001234, 5, True)),
    ("t.me/s/publicname/12", ("publicname", 12, False)),
    ("https://t.me/c/bad/5", (None, None, None)),
    ("https://evil.test/publicname/12", (None, None, None)),
])
def test_link_parser(link, expected):
    assert main.parse_link(link) == expected


@pytest.mark.asyncio
async def test_slash_and_inline_admin_panel_match(db, press):
    owner = FakeUser(main.OWNER_ID)
    command = FakeMessage(text="/admins", user=owner)
    inline = FakeMessage(user=owner)
    await main.admin_handler(None, command)
    await press(inline, "cmd_admin")
    assert command.shown_text == inline.shown_text
    assert command.callback_data() == inline.callback_data()
    await press(inline, "admin_page:1")
    assert "admin:addpremium" in inline.callback_data()


@pytest.mark.asyncio
async def test_redeem_callback_uses_one_calendar_month(db, press, monkeypatch):
    redeem = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "redeem_points", redeem)
    await press(FakeMessage(), "redeem_points")
    redeem.assert_awaited_once_with(1001, 100, months=1)


@pytest.mark.asyncio
async def test_status_cleanup_failure_does_not_refund_delivered_content(db, monkeypatch, fake_bot):
    media = SimpleNamespace(empty=False, media=False, text="delivered content")
    monkeypatch.setattr(main, "try_native_copy", AsyncMock(return_value=False))
    monkeypatch.setattr(fake_bot, "get_messages", AsyncMock(return_value=media), raising=False)
    status = FakeMessage()
    status.delete = AsyncMock(side_effect=RuntimeError("already deleted"))
    status.edit = AsyncMock(side_effect=RuntimeError("already deleted"))
    assert await main.fetch_and_send(FakeMessage(), status, fake_bot, "publicname", 1)
    assert db.users[1001]["daily_downloads"] == 1


@pytest.mark.asyncio
async def test_cancel_command_clears_every_pending_flow_with_one_confirmation(db):
    main.pending_action[1001] = "payment_proof"
    main.payment_pending[1001] = {"plan": "year", "token": "123"}
    main.admin_pending[1001] = "broadcast"
    message = FakeMessage(text="/cancel@TestRestrictBot")
    await main.abort_pending_on_command(None, message)
    await main.cancel_handler(None, message)
    assert not main.pending_action and not main.payment_pending and not main.admin_pending
    assert len(message.replies) == 1
    assert "cancelled" in message.shown_text
