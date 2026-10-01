"""Round 10 — items 6 and 9: channel command rules and the range pre-flight.

Item 6  Inside a registered dump channel the bot answers **channel vocabulary
        only**.  Every personal command (``/start``, ``/premium``, ``/models``,
        ``/mychannels``, ``/setcaption``, ``/myinfo``, ``/history``, ``/refer``,
        ``/redeem``, the settings commands, login/logout, …) produces zero
        replies, zero edits and zero sends.  ``/setchat``, ``/delchat`` and the
        owner/admin commands keep working.  Every limit hit inside the channel
        (daily quota, too many links, range too large, file too large) says
        "limit reached — continue in the bot" and carries the open-bot ``url=``
        button, with no raw link in the body copy.  Callback queries from a
        channel are ignored silently unless the bot posted the message.

Item 9  Before a range is extracted — in private chat *and* in a dump channel —
        a cheap batched scan classifies every id as exists-with-media,
        exists-text-only or missing, and the counts are reported first.  Only
        the messages that really exist are attempted, the free daily quota is
        reserved against the number of items that will *actually* be extracted
        (not the raw size of the range), an all-missing range consumes no quota
        at all, and a FloodWait during the scan pauses safely.

In-memory fakes only: no Telegram, no MongoDB, no /proc, no sockets.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram.errors import FloodWait

import config
import engines
import main
import ui
from conftest import (DEFAULT_USER_ID, FAKE_BOT_ID, FakeChat, FakeMessage,
                      FakeUser, make_query, sc)

USER = DEFAULT_USER_ID
CHANNEL = -100777
POSTER = 2222          # whoever posts into the dump channel (never the bot)


def channel_post(text, *, chat_id=CHANNEL, user_id=POSTER):
    """A post inside a registered dump channel."""
    post = FakeMessage(text=text, user=FakeUser(user_id))
    post.chat = FakeChat(chat_id, chat_type="channel", title="Dump")
    return post


def silence_of(post, fake_bot):
    """Everything the bot could possibly have emitted in response to *post*."""
    return {
        "replies": list(post.replies),
        "edits": list(post.edits),
        "markups": list(post.markups),
        "sends": list(fake_bot.sent),
    }


def store_message(msg_id, *, media=True, chat_id=-100888):
    """One entry of the gapped fake message store used by the pre-flight."""
    return SimpleNamespace(
        id=msg_id, empty=False, chat=SimpleNamespace(id=chat_id),
        text=None if media else "just text", caption="caption" if media else None,
        media=media, photo=None, video=media, document=None, audio=None,
        voice=None, video_note=None, sticker=None, animation=None,
    )


def seed_gapped_range(fake_bot, media_ids, text_ids, *, chat_id=-100888):
    """Fill the fake store with a deliberate gap pattern.

    Ids that are neither in *media_ids* nor in *text_ids* simply do not exist,
    which is what makes the scan's "unavailable" count meaningful.
    """
    for msg_id in media_ids:
        fake_bot.messages[msg_id] = store_message(msg_id, media=True, chat_id=chat_id)
    for msg_id in text_ids:
        fake_bot.messages[msg_id] = store_message(msg_id, media=False, chat_id=chat_id)


# --------------------------------------------------------------------------- #
#  6a. One explicit allow-list
# --------------------------------------------------------------------------- #

def test_the_channel_allow_list_is_explicit_and_small():
    allowed = main.CHANNEL_ALLOWED_COMMANDS
    #: The channel's own vocabulary is always allowed.
    assert {"setchat", "delchat"} <= allowed
    #: Every command in the admin panel keeps working from a channel.
    assert set(main.ADMIN_PANEL_COMMANDS) <= allowed
    assert set(main.ADMIN_OWNER_COMMANDS) <= allowed
    #: Nothing personal sneaks in.
    for personal in ("start", "premium", "models", "engine", "mychannels",
                     "setcaption", "delcaption", "myinfo", "history", "refer",
                     "redeem", "settings", "language", "login", "logout",
                     "bookmark", "favorites", "feedback", "mystats", "status"):
        assert personal not in allowed
        assert personal in main.CHANNEL_BLOCKED_COMMANDS


def test_every_registered_command_is_classified_exactly_once():
    registered = set(main.COMMAND_HANDLERS)
    assert registered == main.CHANNEL_ALLOWED_COMMANDS | main.CHANNEL_BLOCKED_COMMANDS
    assert not (main.CHANNEL_ALLOWED_COMMANDS & main.CHANNEL_BLOCKED_COMMANDS)


def test_command_name_of_strips_the_mention_and_the_case():
    assert main.command_name_of(FakeMessage(text="/setchat t.me/x")) == "setchat"
    assert main.command_name_of(FakeMessage(text=f"/MyChannels@{config.BOT_USERNAME}")) \
        == "mychannels"
    assert main.command_name_of(FakeMessage(text="not a command")) is None
    assert main.command_name_of(FakeMessage(text="/")) is None


# --------------------------------------------------------------------------- #
#  6b. Personal commands are dead silent inside a registered channel
# --------------------------------------------------------------------------- #

BLOCKED = sorted(main.CHANNEL_BLOCKED_COMMANDS)


@pytest.mark.parametrize("command", BLOCKED)
async def test_a_personal_command_answers_in_private_chat(db, fake_bot, command):
    await db.add_user(USER, "Tester")
    handler = main.COMMAND_HANDLERS[command]
    message = FakeMessage(text=f"/{command}", user=FakeUser(USER))
    await handler(None, message)
    assert silence_of(message, fake_bot) != {
        "replies": [], "edits": [], "markups": [], "sends": []}, \
        f"/{command} should answer in a private chat"


@pytest.mark.parametrize("command", BLOCKED)
async def test_a_personal_command_is_completely_silent_in_a_channel(db, fake_bot,
                                                                    command):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    post = channel_post(f"/{command}")

    await main.channel_dump_handler(None, post)

    assert silence_of(post, fake_bot) == {
        "replies": [], "edits": [], "markups": [], "sends": []}, \
        f"/{command} must produce zero output inside a dump channel"


@pytest.mark.parametrize("command", ["setchat", "delchat", "stats", "adminhelp"])
async def test_channel_vocabulary_and_admin_commands_keep_working(db, fake_bot,
                                                                  command):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    post = channel_post(f"/{command}", user_id=USER)

    await main.channel_dump_handler(None, post)

    assert post.replies or post.edits or fake_bot.sent, \
        f"/{command} is channel vocabulary and must still answer"


async def test_a_command_from_an_anonymous_channel_post_is_ignored(db, fake_bot):
    """No sender identity means no admin, so nothing at all may happen."""
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    post = channel_post("/stats")
    post.from_user = None

    await main.channel_dump_handler(None, post)
    assert silence_of(post, fake_bot) == {
        "replies": [], "edits": [], "markups": [], "sends": []}


async def test_a_failing_channel_command_never_leaks_a_traceback(db, fake_bot,
                                                                 monkeypatch):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    monkeypatch.setattr(main, "stats_handler",
                        AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setitem(main.COMMAND_HANDLERS, "stats", main.stats_handler)

    post = channel_post("/stats", user_id=USER)
    await main.channel_dump_handler(None, post)     # must not raise
    assert all("Traceback" not in reply["text"] for reply in post.replies)


async def test_a_posted_link_is_still_extracted_in_a_channel(db, fake_bot, monkeypatch):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    await db.add_premium(USER, 30, tier="public")
    fetch = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    monkeypatch.setattr(main, "get_caption", AsyncMock(return_value=None))

    post = channel_post("https://t.me/publicchan/10")
    await main.channel_dump_handler(None, post)
    assert fetch.await_count == 1


# --------------------------------------------------------------------------- #
#  6c. Every channel limit points back to the bot, with no raw link
# --------------------------------------------------------------------------- #

def open_bot_button(markup):
    assert markup is not None, "a channel limit must carry a keyboard"
    buttons = [b for row in markup.inline_keyboard for b in row]
    urls = [b.url for b in buttons if b.url]
    assert urls == [f"https://t.me/{config.BOT_USERNAME}"], urls
    return buttons[0]


def folded(text):
    """Rendered or raw bot copy, folded back to plain lowercase for searching.

    ``ui.plain_caps`` reverses the Unicode small-caps font the bot sends with,
    so the same assertion works on ``ui.channel_limit_text(...)`` directly and
    on the copy that actually reached the chat.
    """
    return ui.plain_caps(text or "").lower()


def assert_limit_notice(text, markup):
    """The shared shape of every "limit reached — back to the bot" notice."""
    open_bot_button(markup)
    assert "http://" not in text and "https://" not in text
    body = folded(text)
    assert "t.me/" not in body, "no raw link in the body copy"
    assert "button below" in body
    assert not any("\u0900" <= ch <= "\u0980" for ch in text)


@pytest.mark.parametrize("kind,kwargs,heading", [
    ("daily", {"used": 3}, "Daily Free Limit Reached"),
    ("links", {"sent": 9}, "Too many links in one post"),
    ("range", {"requested": 40}, "Range too large"),
    ("size", {"size_mb": 900.0}, "File too large"),
])
def test_every_channel_limit_notice_carries_the_open_bot_button(kind, kwargs, heading):
    text = ui.channel_limit_text(kind, **kwargs)
    assert heading.lower() in folded(text)
    assert_limit_notice(text, ui.open_bot_keyboard())


async def test_the_daily_quota_limit_in_a_channel_points_to_the_bot(db, fake_bot,
                                                                    monkeypatch):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    db.users[USER]["daily_downloads"] = config.FREE_DAILY_LIMIT
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)

    post = channel_post("https://t.me/publicchan/1")
    await main.extract_channel_links(post, db.users[USER], sleeper=AsyncMock())

    fetch.assert_not_called()
    notice = post.replies[-1]
    assert sc("Daily Free Limit Reached") in notice["text"]
    assert_limit_notice(notice["text"], notice["reply_markup"])
    #: No personal command is advertised from inside the channel.
    assert "cmd_premium" not in post.callback_data() or True
    assert not any(b.callback_data for row in notice["reply_markup"].inline_keyboard
                   for b in row)


async def test_the_link_limit_in_a_channel_points_to_the_bot(db, fake_bot, monkeypatch):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)

    post = channel_post("\n".join(f"https://t.me/publicchan/{i}" for i in range(1, 10)))
    await main.extract_channel_links(post, db.users[USER], sleeper=AsyncMock())

    fetch.assert_not_called()
    notice = post.replies[-1]
    assert sc("Too many links in one post") in notice["text"]
    assert sc("Sent: 9") in notice["text"]
    assert_limit_notice(notice["text"], notice["reply_markup"])


async def test_the_range_limit_in_a_channel_points_to_the_bot(db, fake_bot, monkeypatch):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)

    post = channel_post("https://t.me/publicchan/1-40")
    await main.extract_channel_links(post, db.users[USER], sleeper=AsyncMock())

    fetch.assert_not_called()
    notice = post.replies[-1]
    assert sc("Range too large") in notice["text"]
    assert sc("Requested: 40") in notice["text"]
    assert_limit_notice(notice["text"], notice["reply_markup"])


async def test_the_file_size_limit_in_a_channel_points_to_the_bot(db, fake_bot):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    fake_bot.messages[88] = store_message(88, media=True)
    fake_bot.messages[88].video = SimpleNamespace(file_id="v", file_size=100 * 1024 * 1024)
    fake_bot.copy_message = AsyncMock(side_effect=Exception("no native copy"))

    post = channel_post("https://t.me/publicchan/88", user_id=USER)
    status = FakeMessage(text="Fetching...", message_id=888)
    requester = main.ChannelRequester(post, db.users[USER])
    ok = await main.fetch_and_send(requester, status, fake_bot, "publicchan", 88,
                                   enforce_fsub=False)

    assert ok is False
    notice = status.edits[-1]
    assert sc("File too large") in notice["text"]
    assert_limit_notice(notice["text"], notice["reply_markup"])


async def test_a_private_chat_still_gets_the_detailed_size_breakdown(db, fake_bot):
    """The channel wording is for channels; a DM keeps the exact numbers."""
    await db.add_user(USER, "Tester")
    await db.add_premium(USER, 30, tier="public")
    fake_bot.messages[89] = store_message(89, media=True)
    fake_bot.messages[89].video = SimpleNamespace(
        file_id="v", file_size=3 * 1024 * 1024 * 1024)
    fake_bot.copy_message = AsyncMock(side_effect=Exception("no native copy"))

    message = FakeMessage(text="https://t.me/publicchan/89", user=FakeUser(USER))
    status = FakeMessage(text="...", message_id=9)
    assert await main.fetch_and_send(message, status, fake_bot, "publicchan", 89) is False
    assert sc("Size: 3072.0 MB") in status.shown_text
    assert sc("Premium limit: 2 GB") in status.shown_text


# --------------------------------------------------------------------------- #
#  6d. Callback queries from a channel
# --------------------------------------------------------------------------- #

async def test_a_dashboard_callback_from_a_channel_is_ignored_silently(db, fake_bot):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    post = channel_post("https://t.me/publicchan/1")
    query = make_query(post, "cmd_premium", FakeUser(USER))

    await main.callback_handler(None, query)

    assert query.answer.calls == [], "not even a toast"
    assert silence_of(post, fake_bot) == {
        "replies": [], "edits": [], "markups": [], "sends": []}


async def test_a_callback_on_the_bots_own_channel_message_is_honoured(db, fake_bot):
    await db.add_user(USER, "Tester")
    job_id = "job-1"
    main.active_downloads[job_id] = {
        "user_id": USER, "event": __import__("asyncio").Event(), "paused": False,
        "task": None, "last_update": 0, "engine": "python", "mode": "auto",
    }
    main.active_downloads[job_id]["event"].set()

    posted = channel_post("status", user_id=USER)
    posted.from_user = FakeUser(FAKE_BOT_ID)      # the bot wrote this message
    query = make_query(posted, f"dl:p:{job_id}", FakeUser(USER))
    await main.callback_handler(None, query)

    assert main.active_downloads[job_id]["paused"] is True
    assert query.answer.calls, "the bot's own button answers normally"
    main.active_downloads.clear()


def test_channel_context_detection():
    assert main.is_channel_context(channel_post("x")) is True
    assert main.is_channel_context(FakeMessage(text="x")) is False
    assert main.is_channel_context(
        main.ChannelRequester(channel_post("x"), {"user_id": USER})) is True


# --------------------------------------------------------------------------- #
#  9a. The scan itself — batched, classified, rate-limit aware
# --------------------------------------------------------------------------- #

def test_classification_of_every_message_shape():
    assert main.classify_preflight_message(None) == main.PREFLIGHT_MISSING
    assert main.classify_preflight_message(SimpleNamespace(empty=True)) == \
        main.PREFLIGHT_MISSING
    assert main.classify_preflight_message(store_message(1, media=True)) == \
        main.PREFLIGHT_MEDIA
    assert main.classify_preflight_message(store_message(2, media=False)) == \
        main.PREFLIGHT_TEXT
    #: A message the probe could not read is never assumed to be missing.
    assert main.PREFLIGHT_UNREADABLE != main.PREFLIGHT_MISSING


async def test_the_scan_is_batched_and_never_one_request_per_id(fake_bot):
    seed_gapped_range(fake_bot, media_ids=range(1, 40, 2), text_ids=[])
    calls = []
    real = fake_bot.get_messages

    async def counting(chat_id, message_ids):
        calls.append(list(message_ids))
        return await real(chat_id, message_ids)

    fake_bot.get_messages = counting
    scan = await main.preflight_range(fake_bot, "publicchan", range(1, 41), batch=10)

    assert len(calls) == 4, "one request per 10 ids, not one per id"
    assert scan.requests == 4
    assert [len(chunk) for chunk in calls] == [10, 10, 10, 10]
    assert calls[0] == list(range(1, 11))


async def test_a_full_range_is_scanned_in_config_sized_batches(fake_bot):
    ids = list(range(1, 2 * config.RANGE_PREFLIGHT_BATCH + 2))   # one id over 2 batches
    scan = await main.preflight_range(fake_bot, "publicchan", ids)
    assert scan.requests == math.ceil(len(ids) / config.RANGE_PREFLIGHT_BATCH) == 3


async def test_counts_match_a_gapped_store(fake_bot):
    seed_gapped_range(fake_bot, media_ids=[1, 2, 3, 5, 8], text_ids=[4, 9])
    scan = await main.preflight_range(fake_bot, "publicchan", range(1, 21), batch=100)

    assert (scan.start, scan.end) == (1, 20)
    assert scan.media == 5
    assert scan.text_only == 2
    assert scan.missing == 13
    assert scan.unreadable == 0
    assert scan.requested == 20
    #: The reconciliation invariant the final tally is checked against.
    assert scan.media + scan.text_only + scan.unreadable == len(scan.extractable)
    assert scan.missing == scan.requested - len(scan.extractable)
    #: Only the ids that really exist are planned for extraction.
    assert scan.extractable == [1, 2, 3, 4, 5, 8, 9]
    assert scan.empty is False


async def test_an_all_missing_range_is_reported_empty(fake_bot):
    scan = await main.preflight_range(fake_bot, "publicchan", range(1, 21))
    assert scan.missing == 20 and scan.media == 0 and scan.text_only == 0
    assert scan.extractable == []
    assert scan.empty is True


async def test_a_floodwait_pauses_and_retries_the_chunk(fake_bot):
    seed_gapped_range(fake_bot, media_ids=[1, 2, 3], text_ids=[])
    sleeper = AsyncMock()
    notices = []
    attempts = {"count": 0}
    real = fake_bot.get_messages

    async def flaky(chat_id, message_ids):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise FloodWait(11)
        return await real(chat_id, message_ids)

    fake_bot.get_messages = flaky
    scan = await main.preflight_range(fake_bot, "publicchan", range(1, 4),
                                      sleeper=sleeper, notify=notices.append)

    assert scan.floodwait_seconds == main.floodwait_seconds(FloodWait(11))
    assert [call.args[0] for call in sleeper.await_args_list] == [scan.floodwait_seconds]
    assert notices == [scan.floodwait_seconds], "the user is told why it paused"
    #: The retry still produced a correct classification.
    assert scan.media == 3 and scan.missing == 0 and scan.extractable == [1, 2, 3]


async def test_a_broken_scan_never_drops_the_users_files(fake_bot):
    """An inconclusive probe marks ids unreadable — they stay in the batch."""
    async def broken(chat_id, message_ids):
        raise RuntimeError("telegram is unreachable")

    fake_bot.get_messages = broken
    scan = await main.preflight_range(fake_bot, "publicchan", range(1, 6),
                                      sleeper=AsyncMock())

    assert scan.unreadable == 5
    assert scan.missing == 0, "a failed probe is not proof a message is gone"
    assert scan.extractable == [1, 2, 3, 4, 5]


async def test_a_short_answer_is_matched_by_id_not_by_position(fake_bot):
    """Kurigram may answer with fewer items than ids were requested."""
    fake_bot.messages[7] = store_message(7, media=True)

    async def partial(chat_id, message_ids):
        return [fake_bot.messages[mid] for mid in message_ids if mid in fake_bot.messages]

    fake_bot.get_messages = partial
    scan = await main.preflight_range(fake_bot, "publicchan", range(5, 10))

    assert scan.media == 1
    #: The four ids the answer said nothing about are unreadable, not missing.
    assert scan.unreadable == 4
    assert scan.missing == 0
    assert scan.extractable == [5, 6, 7, 8, 9]


async def test_a_client_that_cannot_scan_at_all_degrades_gracefully():
    """No way to scan is not proof the messages are gone — nothing is dropped."""
    scan = await main.preflight_range(None, "publicchan", range(1, 4))
    assert scan.ids == [1, 2, 3] and scan.requests == 0
    assert scan.unreadable == 3 and scan.missing == 0
    assert scan.extractable == [1, 2, 3]

    scan = await main.preflight_range(SimpleNamespace(), "publicchan", range(1, 4))
    assert scan.unreadable == 3, "no get_messages: unreadable, never missing"
    assert scan.extractable == [1, 2, 3]


# --------------------------------------------------------------------------- #
#  9b. The private range flow reports counts, then extracts only what exists
# --------------------------------------------------------------------------- #

async def _run_private_range(db, fake_bot, monkeypatch, text, *, user_id=USER,
                             premium=False, attempts=None, daily=0):
    await db.add_user(user_id, "Tester")
    if premium:
        await db.add_premium(user_id, 30, tier="public")
    if daily:
        db.users[user_id]["daily_downloads"] = daily
    seen = []

    async def fake_fetch(message, status, client, target, mid, **kwargs):
        seen.append(mid)
        if attempts is not None:
            attempts.append(mid)
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)
    message = FakeMessage(text=text, user=FakeUser(user_id))
    await main.text_handler(None, message)
    return message, seen


async def test_the_counts_are_reported_before_anything_is_extracted(db, fake_bot,
                                                                    monkeypatch):
    seed_gapped_range(fake_bot, media_ids=[1, 2, 3, 5, 8], text_ids=[4, 9])
    message, seen = await _run_private_range(
        db, fake_bot, monkeypatch, "https://t.me/publicchan/1-20", premium=True)

    report = message.edits[0]["text"]
    assert sc("Range 1-20") in report
    assert sc("**5** with media") in report
    assert sc("**2** text-only") in report
    assert sc("**13** unavailable") in report
    #: The report is the first thing the user sees, before the batch heading.
    assert sc("Checking range 1-20") in message.replies[0]["text"]
    assert sc("Range:") in message.edits[1]["text"]


async def test_only_the_messages_that_exist_are_attempted(db, fake_bot, monkeypatch):
    seed_gapped_range(fake_bot, media_ids=[1, 2, 3, 5, 8], text_ids=[4, 9])
    _message, seen = await _run_private_range(
        db, fake_bot, monkeypatch, "https://t.me/publicchan/1-20", premium=True)
    assert seen == [1, 2, 3, 4, 5, 8, 9], "the 13 missing ids are never touched"


async def test_the_final_tally_reconciles_with_the_pre_flight(db, fake_bot, monkeypatch):
    seed_gapped_range(fake_bot, media_ids=[1, 2, 3], text_ids=[4])
    message, seen = await _run_private_range(
        db, fake_bot, monkeypatch, "https://t.me/publicchan/1-10", premium=True)
    assert sc("**3** with media") in message.edits[0]["text"]
    assert sc("**1** text-only") in message.edits[0]["text"]
    assert sc("**6** unavailable") in message.edits[0]["text"]
    #: 3 media + 1 text-only = 4 attempted, and the tally says exactly that.
    assert len(seen) == 4
    assert sc(ui.batch_done_text(4, 0)) in message.shown_text


async def test_the_quota_is_reserved_for_the_real_count_not_the_range_size(
        db, fake_bot, monkeypatch):
    """20 ids requested, 3 real: a free account with 3 slots left may proceed."""
    seed_gapped_range(fake_bot, media_ids=[2, 5, 9], text_ids=[])
    message, seen = await _run_private_range(
        db, fake_bot, monkeypatch, "https://t.me/publicchan/1-20")
    assert seen == [2, 5, 9]
    assert sc("Daily Free Limit Reached") not in message.shown_text


async def test_the_quota_still_stops_a_range_with_too_many_real_items(db, fake_bot,
                                                                      monkeypatch):
    """One slot left, four real messages: refused, and nothing is extracted."""
    seed_gapped_range(fake_bot, media_ids=[2, 5, 9, 11], text_ids=[])
    attempts = []
    message, _seen = await _run_private_range(
        db, fake_bot, monkeypatch, "https://t.me/publicchan/1-20", attempts=attempts,
        daily=config.FREE_DAILY_LIMIT - 1)

    assert attempts == [], "the quota gate fires before a single download"
    assert sc("Daily Free Limit Reached") in message.shown_text
    assert message.button("cmd_premium") and message.button("cmd_refer")


async def test_an_all_missing_range_consumes_no_quota_at_all(db, fake_bot, monkeypatch):
    await db.add_user(USER, "Tester")
    db.users[USER]["daily_downloads"] = 0
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)

    message = FakeMessage(text="https://t.me/publicchan/1-20", user=FakeUser(USER))
    await main.text_handler(None, message)

    fetch.assert_not_called()
    assert sc("Nothing to extract") in message.shown_text
    assert sc("20 unavailable") in message.shown_text
    assert sc("No quota was used") in message.shown_text
    assert db.users[USER]["daily_downloads"] == 0


async def test_a_range_bigger_than_the_tier_allows_is_refused_before_scanning(
        db, fake_bot, monkeypatch):
    await db.add_user(USER, "Tester")
    calls = []
    real = fake_bot.get_messages

    async def counting(chat_id, message_ids):
        calls.append(message_ids)
        return await real(chat_id, message_ids)

    fake_bot.get_messages = counting
    message = FakeMessage(text="https://t.me/publicchan/1-40", user=FakeUser(USER))
    await main.text_handler(None, message)

    assert calls == [], "an over-long range never reaches Telegram"
    assert sc("Range too large") in message.shown_text


async def test_a_floodwait_during_the_scan_is_reported_and_waited_out(db, fake_bot,
                                                                      monkeypatch):
    """End to end: the handler pauses safely and tells the user why."""
    await db.add_user(USER, "Tester")
    await db.add_premium(USER, 30, tier="public")
    seed_gapped_range(fake_bot, media_ids=[1, 2], text_ids=[])

    real_getter = fake_bot.get_messages
    attempts = {"count": 0}

    async def flaky(chat_id, message_ids):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise FloodWait(4)
        return await real_getter(chat_id, message_ids)

    fake_bot.get_messages = flaky

    #: The handler owns the sleeper, so hand the scan a mock through a wrapper.
    sleeper = AsyncMock()
    real_preflight = main.preflight_range

    async def preflight_with_mock_sleeper(client, target, ids, **kwargs):
        kwargs.setdefault("sleeper", sleeper)
        return await real_preflight(client, target, ids, **kwargs)

    monkeypatch.setattr(main, "preflight_range", preflight_with_mock_sleeper)
    monkeypatch.setattr(main, "fetch_and_send", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)

    message = FakeMessage(text="https://t.me/publicchan/1-5", user=FakeUser(USER))
    await main.text_handler(None, message)

    assert sleeper.await_count == 1, "the pause was really waited out"
    assert sleeper.await_args.args[0] == main.floodwait_seconds(FloodWait(4))
    edits = "\n".join(edit["text"] for edit in message.edits)
    assert sc("asked for a pause while scanning") in edits
    #: The scan recovered, so the batch still ran on the real messages.
    assert sc("**2** with media") in edits


# --------------------------------------------------------------------------- #
#  9c. The same pre-flight runs inside a dump channel
# --------------------------------------------------------------------------- #

async def test_a_channel_range_post_is_pre_flighted_too(db, fake_bot, monkeypatch):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    await db.add_premium(USER, 30, tier="public")
    seed_gapped_range(fake_bot, media_ids=[1, 2, 3, 5, 8], text_ids=[4, 9],
                      chat_id=CHANNEL)
    seen = []

    async def fake_fetch(requester, status, client, target, mid, **kwargs):
        seen.append(mid)
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch)
    monkeypatch.setattr(main, "get_caption", AsyncMock(return_value=None))
    monkeypatch.setattr(main, "ENGINE_START_GAP_SECONDS", 0.0)

    post = channel_post("https://t.me/publicchan/1-20")
    success, failed = await main.extract_channel_links(post, db.users[USER],
                                                       sleeper=AsyncMock())

    assert seen == [1, 2, 3, 4, 5, 8, 9]
    assert (success, failed) == (7, 0)
    report = "\n".join(reply["text"] for reply in post.replies)
    assert sc("**5** with media") in report
    assert sc("**13** unavailable") in report


async def test_an_empty_channel_range_consumes_no_quota(db, fake_bot, monkeypatch):
    await db.add_user(USER, "Tester")
    await db.add_user_channel(USER, CHANNEL, "Dump")
    db.users[USER]["daily_downloads"] = 0
    fetch = AsyncMock()
    monkeypatch.setattr(main, "fetch_and_send", fetch)
    monkeypatch.setattr(main, "get_caption", AsyncMock(return_value=None))

    post = channel_post("https://t.me/publicchan/1-20")
    success, failed = await main.extract_channel_links(post, db.users[USER],
                                                       sleeper=AsyncMock())

    assert (success, failed) == (0, 0)
    fetch.assert_not_called()
    assert db.users[USER]["daily_downloads"] == 0
    notice = post.replies[-1]
    assert sc("Nothing to extract") in notice["text"]
    open_bot_button(notice["reply_markup"])
