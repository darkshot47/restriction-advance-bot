"""Tests for new requirements:
1. Copy-first extraction and custom captions (free and premium)
2. Redemption limitation text
3. Feedback handling with URLs, safe escaping, clickable names
4. /loggedusers command with pagination (5 per page)
5. /users command with pagination (30 per page)
6. Login success notification for OTP and 2FA
"""

import html
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config
import main
from conftest import FakeMessage, FakeUser, make_query, sc


# --------------------------------------------------------------------------- #
# 1. Copy-first extraction and custom captions
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_free_user_with_custom_caption_copies_and_edits_without_download(db, fake_bot):
    await db.add_user(1001, "Freebie")
    await db.set_caption(1001, "My Custom Caption")

    source = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=55,
        caption="Original Caption",
        photo=object(),
        video=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
        text=None,
        empty=False,
    )
    copied = SimpleNamespace(edit_caption=AsyncMock())
    fake_bot.get_messages = AsyncMock(return_value=source)
    fake_bot.copy_message = AsyncMock(return_value=copied)
    fake_bot.download_media = AsyncMock()

    message = FakeMessage(user=FakeUser(1001))
    status = FakeMessage(user=FakeUser(1001))

    result = await main.fetch_and_send(message, status, fake_bot, "channel", 55)
    assert result is True
    fake_bot.copy_message.assert_awaited_once()
    fake_bot.download_media.assert_not_called()
    copied.edit_caption.assert_awaited_once_with(
        caption="My Custom Caption\nExtracted by @wantedkar99bot",
        parse_mode=main.ParseMode.DISABLED,
    )


@pytest.mark.asyncio
async def test_premium_user_with_custom_caption_copies_without_attribution(db, fake_bot):
    await db.add_user(2002, "VIP")
    db.users[2002]["is_premium"] = True
    await db.set_caption(2002, "VIP Caption")

    source = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=66,
        caption="Original Caption",
        photo=object(),
        video=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
        text=None,
        empty=False,
    )
    copied = SimpleNamespace(edit_caption=AsyncMock())
    fake_bot.get_messages = AsyncMock(return_value=source)
    fake_bot.copy_message = AsyncMock(return_value=copied)
    fake_bot.download_media = AsyncMock()

    message = FakeMessage(user=FakeUser(2002))
    status = FakeMessage(user=FakeUser(2002))

    result = await main.fetch_and_send(message, status, fake_bot, "channel", 66)
    assert result is True
    fake_bot.copy_message.assert_awaited_once()
    fake_bot.download_media.assert_not_called()
    copied.edit_caption.assert_awaited_once_with(
        caption="VIP Caption",
        parse_mode=main.ParseMode.DISABLED,
    )


@pytest.mark.asyncio
async def test_copy_fails_falls_back_to_download(db, fake_bot, tmp_path):
    await db.add_user(1001, "Tester")
    media = SimpleNamespace(
        empty=False, media=True, text=None, caption="Orig Caption",
        photo=True, video=None, document=None, audio=None, voice=None,
        sticker=None, animation=None, video_note=None,
        chat=SimpleNamespace(id=-100123), id=77,
    )
    path = tmp_path / "file.jpg"
    path.write_bytes(b"data")

    fake_bot.get_messages = AsyncMock(return_value=media)
    fake_bot.copy_message = AsyncMock(side_effect=RuntimeError("Copy rejected by Telegram"))
    fake_bot.download_media = AsyncMock(return_value=str(path))

    message = FakeMessage(user=FakeUser(1001))
    status = FakeMessage(user=FakeUser(1001))

    result = await main.fetch_and_send(message, status, fake_bot, "channel", 77)
    assert result is True
    fake_bot.copy_message.assert_awaited_once()
    fake_bot.download_media.assert_awaited_once()
    assert fake_bot.sent
    assert "Extracted by @wantedkar99bot" in fake_bot.sent[-1]["caption"]  # watermark stays verbatim


@pytest.mark.asyncio
async def test_copy_sticker_and_video_note_sends_separate_attribution_for_free_user(db):
    source = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=88,
        caption=None,
        photo=None,
        video=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
        text=None,
        sticker=object(),
        video_note=None,
        empty=False,
    )
    copied = SimpleNamespace()
    fetch_client = SimpleNamespace(
        get_messages=AsyncMock(return_value=source),
        copy_message=AsyncMock(return_value=copied),
    )
    message = FakeMessage(user=FakeUser(1001))
    assert await main.try_native_copy(message, fetch_client, "channel", 88)
    assert message.replies
    assert "Extracted by @wantedkar99bot" in message.replies[-1]["text"]  # watermark stays verbatim


@pytest.mark.asyncio
async def test_copy_overflow_caption_sends_separate_attribution_for_free_user(db):
    long_caption = "A" * 1020
    source = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=99,
        caption=long_caption,
        photo=object(),
        video=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
        text=None,
        empty=False,
    )
    copied = SimpleNamespace(edit_caption=AsyncMock())
    fetch_client = SimpleNamespace(
        get_messages=AsyncMock(return_value=source),
        copy_message=AsyncMock(return_value=copied),
    )
    message = FakeMessage(user=FakeUser(1001))
    assert await main.try_native_copy(message, fetch_client, "channel", 99)
    assert message.replies
    assert "Extracted by @wantedkar99bot" in message.replies[-1]["text"]  # watermark stays verbatim


# --------------------------------------------------------------------------- #
# 2. Redemption limitation text
# --------------------------------------------------------------------------- #

def test_limitation_wording_updated():
    expected = "This bot extracts restricted content from public channels only."
    assert config.REDEEM_LIMITATION == expected
    assert sc("Private-channel links do not work with redemption points") not in config.REDEEM_LIMITATION
    assert sc("Only premium manually granted by the owner") not in config.REDEEM_LIMITATION


# --------------------------------------------------------------------------- #
# 3. Feedback handling
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_feedback_with_links_is_rejected(db, fake_bot):
    """Security rule: feedback containing a URL is rejected, nothing is stored."""
    user = FakeUser(user_id=3003, first_name="Linker", username="linker")
    feedback_text = "Check this URL: https://example.com/item and t.me/c/123/45 😊"
    message = FakeMessage(text=f"/feedback {feedback_text}", user=user)

    await main.feedback_handler(None, message)

    assert db.feedback == []
    assert not fake_bot.sent
    assert sc(config.FEEDBACK_LINK_WARNING) in message.shown_text


@pytest.mark.asyncio
async def test_feedback_with_mentions_is_forwarded_exactly(db, fake_bot):
    """Plain text, @mentions, @username mentions and emojis stay allowed."""
    user = FakeUser(user_id=3003, first_name="Linker", username="linker")
    feedback_text = "Thanks @XyrDeveloper and @wantedkar99bot, great work 😊 #feedback"
    message = FakeMessage(text=f"/feedback {feedback_text}", user=user)

    await main.feedback_handler(None, message)

    assert db.feedback == [(3003, feedback_text)]
    assert fake_bot.sent
    sent_to_owner = fake_bot.sent[-1]
    assert sent_to_owner["chat_id"] == main.OWNER_ID
    assert feedback_text in html.unescape(sent_to_owner["text"])  # user words verbatim
    assert "tg://user?id=3003" in sent_to_owner["text"]
    assert "Linker" in sent_to_owner["text"]  # Telegram name stays verbatim


@pytest.mark.asyncio
async def test_feedback_sender_without_username_clickable(db, fake_bot):
    user = FakeUser(user_id=4004, first_name="<Dan & Dave>", username=None)
    feedback_text = "Everything looks great!"
    message = FakeMessage(text=f"/feedback {feedback_text}", user=user)

    await main.feedback_handler(None, message)

    assert db.feedback == [(4004, feedback_text)]
    sent_to_owner = fake_bot.sent[-1]
    assert 'href="tg://user?id=4004"' in sent_to_owner["text"]
    assert "&lt;Dan &amp; Dave&gt;" in sent_to_owner["text"]  # escaped name verbatim
    assert sc("💬 Feedback from 4004:") not in sent_to_owner["text"]


@pytest.mark.asyncio
async def test_feedback_via_button_rejects_links(db, fake_bot):
    user = FakeUser(user_id=5005, first_name="Elena", username="elena")
    start_msg = FakeMessage(user=user)
    await main.start_feedback(start_msg)
    assert main.pending_action[5005] == "feedback"

    text_msg = FakeMessage(text="https://t.me/publicchannel/10 is nice", user=user)
    await main.text_handler(None, text_msg)

    assert db.feedback == []
    assert not fake_bot.sent
    assert sc(config.FEEDBACK_LINK_WARNING) in text_msg.shown_text
    # the feedback session stays open so the user can retry without a link
    assert main.pending_action[5005] == "feedback"

    good = FakeMessage(text="Great bot, thanks @XyrDeveloper!", user=user)
    await main.text_handler(None, good)
    assert db.feedback == [(5005, "Great bot, thanks @XyrDeveloper!")]
    assert 5005 not in main.pending_action


# --------------------------------------------------------------------------- #
# 4. /loggedusers command
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_loggedusers_pagination(db):
    for i in range(1, 13):
        await db.add_user(i * 10, f"User{i}", f"user{i}")
        await db.save_session(i * 10, f"session_secret_{i}", f"+9198765432{i:02d}")

    # Admin opens page 0
    msg = FakeMessage(text="/loggedusers", user=FakeUser(main.OWNER_ID))
    await main.loggedusers_handler(None, msg)

    text = msg.shown_text
    assert sc("LOGGED-IN USERS (12)") in text
    assert sc("Page 1/3") in text
    assert sc("session_secret") not in text
    for i in range(1, 6):
        assert sc(f"User{i}") in text
    assert sc("User6") not in text

    # Navigation buttons: Previous absent, Next present
    buttons = msg.button_texts()
    assert sc("⬅️ Previous") not in buttons
    assert sc("Next ➡️") in buttons

    # Callback to page 1
    query = make_query(msg, "loggedusers:1", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, query)
    text1 = msg.shown_text
    assert sc("Page 2/3") in text1
    assert sc("User6") in text1
    assert sc("User10") in text1
    assert sc("User1<") not in text1
    buttons1 = msg.button_texts()
    assert sc("⬅️ Previous") in buttons1
    assert sc("Next ➡️") in buttons1

    # Callback to page 2 (last page)
    query2 = make_query(msg, "loggedusers:2", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, query2)
    text2 = msg.shown_text
    assert sc("Page 3/3") in text2
    assert sc("User11") in text2
    assert sc("User12") in text2
    buttons2 = msg.button_texts()
    assert sc("⬅️ Previous") in buttons2
    assert sc("Next ➡️") not in buttons2


@pytest.mark.asyncio
async def test_loggedusers_unauthorized_user_blocked(db):
    user = FakeUser(9999, "Regular")
    msg = FakeMessage(text="/loggedusers", user=user)
    await main.loggedusers_handler(None, msg)
    assert sc("Admin only") in msg.shown_text

    query = make_query(msg, "loggedusers:0", user)
    await main.callback_handler(None, query)
    assert any(sc("Admin access only") in (t or "") for t in query.answer.texts)


@pytest.mark.asyncio
async def test_loggedusers_no_users(db):
    msg = FakeMessage(text="/loggedusers", user=FakeUser(main.OWNER_ID))
    await main.loggedusers_handler(None, msg)
    assert sc("No logged-in users") in msg.shown_text


# --------------------------------------------------------------------------- #
# 5. /users pagination
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_users_command_pagination(db):
    for i in range(1, 36):
        await db.add_user(i * 100, f"Name{i}")

    msg = FakeMessage(text="/users", user=FakeUser(main.OWNER_ID))
    await main.users_handler(None, msg)

    text = msg.shown_text
    assert sc("ALL USERS (35)") in text
    assert sc("Page 1/2") in text
    assert sc("1. `100` - Name1") in text
    assert sc("30. `3000` - Name30") in text
    assert sc("Name31") not in text

    buttons = msg.button_texts()
    assert sc("⬅️ Previous") not in buttons
    assert sc("Next ➡️") in buttons

    query = make_query(msg, "users_page:1", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, query)
    text2 = msg.shown_text
    assert sc("Page 2/2") in text2
    assert sc("31. `3100` - Name31") in text2
    assert sc("35. `3500` - Name35") in text2
    buttons2 = msg.button_texts()
    assert sc("⬅️ Previous") in buttons2
    assert sc("Next ➡️") not in buttons2


@pytest.mark.asyncio
async def test_users_out_of_range_page(db):
    for i in range(1, 5):
        await db.add_user(i * 10, f"User{i}")

    msg = FakeMessage(text="/users", user=FakeUser(main.OWNER_ID))
    query = make_query(msg, "users_page:999", FakeUser(main.OWNER_ID))
    await main.callback_handler(None, query)
    assert sc("Page 1/1") in msg.shown_text


# --------------------------------------------------------------------------- #
# 6. Successful login notification (OTP and 2FA)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_login_notification_otp(db, fake_bot):
    user_id = 7777
    user = FakeUser(user_id=user_id, first_name="LoginGuy", username="loginguy")
    temp_client = SimpleNamespace(
        sign_in=AsyncMock(),
        export_session_string=AsyncMock(return_value="secret_session_token_12345"),
        get_me=AsyncMock(return_value=SimpleNamespace(first_name="LoginGuy", last_name="OTP", username="loginguy", phone_number="919876543210")),
    )
    main.login_pending[user_id] = {
        "step": "waiting_otp",
        "phone": "+919876543210",
        "phone_code_hash": "hash123",
        "client": temp_client,
    }

    message = FakeMessage(text="1 2 3 4 5", user=user)
    await main.text_handler(None, message)

    assert sc("Login Successful") in message.shown_text
    # Verify owner notification was sent
    notify = [m for m in fake_bot.sent if m["chat_id"] == main.OWNER_ID]
    assert notify
    owner_text = notify[-1]["text"]
    assert sc("User Login Successful") in owner_text
    assert f"tg://user?id={user_id}" in owner_text
    assert "LoginGuy" in owner_text  # Telegram name stays verbatim
    assert sc("secret_session_token") not in owner_text


@pytest.mark.asyncio
async def test_login_notification_2fa(db, fake_bot):
    user_id = 8888
    user = FakeUser(user_id=user_id, first_name="TwoFactorUser", username=None)
    temp_client = SimpleNamespace(
        check_password=AsyncMock(),
        export_session_string=AsyncMock(return_value="secret_2fa_session_token"),
        get_me=AsyncMock(return_value=SimpleNamespace(first_name="TwoFactorUser", last_name=None, username=None, phone_number="919876543211")),
    )
    main.login_pending[user_id] = {
        "step": "waiting_2fa",
        "phone": "+919876543211",
        "client": temp_client,
    }

    message = FakeMessage(text="mysecret2fapass", user=user)
    await main.text_handler(None, message)

    assert sc("Login Successful") in message.shown_text
    notify = [m for m in fake_bot.sent if m["chat_id"] == main.OWNER_ID]
    assert notify
    owner_text = notify[-1]["text"]
    assert sc("User Login Successful") in owner_text
    assert f"tg://user?id={user_id}" in owner_text
    assert "TwoFactorUser" in owner_text  # Telegram name stays verbatim
    assert sc("secret_2fa_session_token") not in owner_text


@pytest.mark.asyncio
async def test_user_with_thumbnail_copies_and_does_not_download(db, fake_bot):
    await db.add_user(1001, "ThumbUser")
    db.users[1001]["thumbnail_id"] = "photo_file_id_thumb"

    source = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=56,
        caption="Original Caption",
        photo=object(),
        video=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
        text=None,
        empty=False,
    )
    copied = SimpleNamespace(edit_caption=AsyncMock())
    fake_bot.get_messages = AsyncMock(return_value=source)
    fake_bot.copy_message = AsyncMock(return_value=copied)
    fake_bot.download_media = AsyncMock()

    message = FakeMessage(user=FakeUser(1001))
    status = FakeMessage(user=FakeUser(1001))

    result = await main.fetch_and_send(message, status, fake_bot, "channel", 56)
    assert result is True
    fake_bot.copy_message.assert_awaited_once()
    fake_bot.download_media.assert_not_called()


@pytest.mark.asyncio
async def test_text_message_copy_edits_text_for_free_and_premium(db):
    # Free user
    source_free = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=60,
        text="Hello free world",
        caption=None, photo=None, video=None, document=None, audio=None, voice=None,
        animation=None, sticker=None, video_note=None, empty=False,
    )
    copied_free = SimpleNamespace(edit_text=AsyncMock())
    fetch_client_free = SimpleNamespace(
        get_messages=AsyncMock(return_value=source_free),
        copy_message=AsyncMock(return_value=copied_free),
    )
    msg_free = FakeMessage(user=FakeUser(1001))
    assert await main.try_native_copy(msg_free, fetch_client_free, "channel", 60)
    copied_free.edit_text.assert_awaited_once_with(
        "Hello free world\nExtracted by @wantedkar99bot",
        parse_mode=main.ParseMode.DISABLED,
    )

    # Premium user with custom caption
    await db.add_user(2002, "VIP")
    db.users[2002]["is_premium"] = True
    await db.set_caption(2002, "VIP Text Replacement")
    source_prem = SimpleNamespace(
        chat=SimpleNamespace(id=-100123),
        id=61,
        text="Original VIP text",
        caption=None, photo=None, video=None, document=None, audio=None, voice=None,
        animation=None, sticker=None, video_note=None, empty=False,
    )
    copied_prem = SimpleNamespace(edit_text=AsyncMock())
    fetch_client_prem = SimpleNamespace(
        get_messages=AsyncMock(return_value=source_prem),
        copy_message=AsyncMock(return_value=copied_prem),
    )
    msg_prem = FakeMessage(user=FakeUser(2002))
    assert await main.try_native_copy(msg_prem, fetch_client_prem, "channel", 61)
    copied_prem.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_failed_otp_no_notification(db, fake_bot):
    user_id = 9001
    user = FakeUser(user_id=user_id, first_name="BadOTP", username="badotp")
    temp_client = SimpleNamespace(
        sign_in=AsyncMock(side_effect=main.PhoneCodeInvalid()),
    )
    main.login_pending[user_id] = {
        "step": "waiting_otp",
        "phone": "+919876543299",
        "phone_code_hash": "hash_bad",
        "client": temp_client,
    }
    message = FakeMessage(text="0 0 0 0 0", user=user)
    await main.text_handler(None, message)
    assert sc("Wrong OTP") in message.shown_text
    # No login notification sent
    assert not any("User Login Successful" in m.get("text", "") for m in fake_bot.sent)


@pytest.mark.asyncio
async def test_failed_2fa_no_notification(db, fake_bot):
    user_id = 9002
    user = FakeUser(user_id=user_id, first_name="Bad2FA", username="bad2fa")
    temp_client = SimpleNamespace(
        check_password=AsyncMock(side_effect=main.PasswordHashInvalid()),
    )
    main.login_pending[user_id] = {
        "step": "waiting_2fa",
        "phone": "+919876543298",
        "client": temp_client,
    }
    message = FakeMessage(text="wrongpass", user=user)
    await main.text_handler(None, message)
    assert sc("Wrong password") in message.shown_text
    assert not any("User Login Successful" in m.get("text", "") for m in fake_bot.sent)


@pytest.mark.asyncio
async def test_login_notification_failure_does_not_break_login_flow(db, monkeypatch):
    user_id = 9003
    user = FakeUser(user_id=user_id, first_name="RobustUser", username="robust")
    temp_client = SimpleNamespace(
        sign_in=AsyncMock(),
        export_session_string=AsyncMock(return_value="valid_session"),
        get_me=AsyncMock(return_value=SimpleNamespace(first_name="RobustUser", last_name=None, username="robust", phone_number="919876543297")),
    )
    main.login_pending[user_id] = {
        "step": "waiting_otp",
        "phone": "+919876543297",
        "phone_code_hash": "hash_ok",
        "client": temp_client,
    }
    # Simulate send_message throwing an exception
    broken_send = AsyncMock(side_effect=RuntimeError("Telegram network outage"))
    monkeypatch.setattr(main.bot, "send_message", broken_send)

    message = FakeMessage(text="1 2 3 4 5", user=user)
    await main.text_handler(None, message)
    assert sc("Login Successful") in message.shown_text
    assert await db.get_session(user_id) == "valid_session"


@pytest.mark.asyncio
async def test_owner_self_login_no_notification(db, fake_bot):
    owner_id = main.OWNER_ID
    user = FakeUser(user_id=owner_id, first_name="Boss", username="boss")
    temp_client = SimpleNamespace(
        sign_in=AsyncMock(),
        export_session_string=AsyncMock(return_value="owner_session"),
        get_me=AsyncMock(return_value=SimpleNamespace(first_name="Boss", last_name=None, username="boss", phone_number="1234567890")),
    )
    main.login_pending[owner_id] = {
        "step": "waiting_otp",
        "phone": "+1234567890",
        "phone_code_hash": "hash123",
        "client": temp_client,
    }

    message = FakeMessage(text="1 2 3 4 5", user=user)
    await main.text_handler(None, message)

    owner_notifies = [m for m in fake_bot.sent if m["chat_id"] == owner_id and "User Login Successful" in m.get("text", "")]
    assert not owner_notifies
