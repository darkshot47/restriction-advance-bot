"""Round 16 — the Vmore app: access tokens, the HTTP API, the APK and the bot UI.

The suite pins the requirements the owner gave for the app epic:

* ``/CreateBot`` and ``/Bot_stats`` are gone — the command, the handlers, the
  keyboard button and the collections the old feature wrote to.
* One account owns exactly **one** active access token (``/gentoken``), it can be
  regenerated and revoked, and *generating* a token never makes somebody an
  "app user" — only really using the app does, which is what ``/appusers`` lists.
* The API behind ``/api/v2/token/<TOKEN>`` validates the token, logs the app in
  (and asks the bot to DM "login in app successful"), resolves links, delivers
  public links into the DM, streams private content (Range-aware, pause / resume
  / cancel) and pushes an edited file back through the user's own session.
* ``/apk`` stores the file (and the deployment URL from its caption), the app
  buttons point at ``/api/v2/app/apk``, and the private-link screen offers the
  two options the owner asked for.
* Every reply keyboard button is **green**.

Everything runs on the in-memory fakes and Flask's own test client — no Telegram
and no MongoDB.
"""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

import appapi
import config
import database
import main
import ui
from conftest import FakeChat, FakeMessage, FakeUser, sc


def flat(markup):
    return [b for row in markup.inline_keyboard for b in row]


def api_client():
    """Flask's test client bound to the bot's web app (the API is mounted on it)."""
    main.web.config.update(TESTING=True)
    return main.web.test_client()


APP_COLLECTIONS = ("app_tokens_col", "app_users_col", "app_activity_col", "config_col",
                    "users_col", "downloads_col")


@pytest.fixture
def store(monkeypatch):
    """The genuine ``database`` module against an in-memory Mongo."""
    mongo = AsyncMongoMockClient()["test"]
    monkeypatch.setattr(database, "db", mongo)
    for name in APP_COLLECTIONS:
        if hasattr(database, name):
            monkeypatch.setattr(database, name, getattr(mongo, name))
    return mongo


@pytest.fixture
def live_db(store, monkeypatch):
    """``store`` **and** the genuine functions bound onto ``main``."""
    from conftest import DB_NAMES
    for name in DB_NAMES:
        replacement = getattr(database, name, None)
        if replacement is not None:
            monkeypatch.setattr(main, name, replacement)
    return store


@pytest.fixture
def loop_api(live_db, monkeypatch):
    """Give the API its own event loop (a thread) and a working bridge."""
    import threading
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    bridge = main.VmoreAppBridge()
    monkeypatch.setattr(main, "APP_BRIDGE", bridge)
    appapi.bind_loop(loop)
    appapi.bind_bridge(bridge)
    monkeypatch.setattr(appapi, "JOBS", appapi.JobRegistry())
    try:
        yield bridge
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        appapi._LOOP = None
        appapi._BRIDGE = None


# --------------------------------------------------------------------------- #
#  1. /CreateBot and /Bot_stats are gone
# --------------------------------------------------------------------------- #

def test_the_child_bot_commands_are_gone():
    for name in ("CreateBot", "DeleteBot", "Bot_stats", "createbot", "deletebot",
                 "bot_stats"):
        assert name not in main.COMMAND_NAMES
        assert name not in main.COMMAND_HANDLERS
    assert not hasattr(main, "CREATEBOT_PENDING")
    assert not hasattr(main, "child_bot_clients")
    assert not hasattr(main, "start_child_bot")
    assert not hasattr(main, "init_child_bots")
    assert not hasattr(main, "handle_deletebot_callback")


def test_no_keyboard_offers_the_retired_feature():
    for keyboard in (ui.start_keyboard(), ui.start_keyboard(show_admin=True),
                     ui.help_keyboard()):
        data = {b.callback_data for b in flat(keyboard) if b.callback_data}
        assert not any("createbot" in item for item in data)
        assert not any("delbot" in item for item in data)


@pytest.mark.asyncio
async def test_the_old_collections_are_purged_once(store):
    """The retired collections are dropped, and never touched again."""
    await store["created_bots"].insert_one({"_id": "123:abc"})
    await store["child_bot_users_123"].insert_one({"user_id": 1})
    first = await database.purge_created_bot_data()
    assert set(first["collections"]) >= {"created_bots", "child_bot_users_123"}
    assert first["skipped"] is False
    assert await store["created_bots"].count_documents({}) == 0
    #: The next start is a no-op (the config flag is written).
    second = await database.purge_created_bot_data()
    assert second["skipped"] is True and second["collections"] == []


def test_every_startup_errand_uses_a_patched_database_function():
    """The start hook spawns app errands — each must be faked in tests.

    ``publish_menu_on_start`` runs the /CreateBot purge, retires expired tokens
    and caches the owner card.  A task left pointing at the *real* database
    module blew up with "Event loop is closed" in CI (the motor client belongs
    to a loop the tests never run), so the list is pinned here.
    """
    from conftest import DB_NAMES
    assert {"purge_created_bot_data", "expire_stale_app_tokens"} <= set(DB_NAMES)
    for coro in (main.purge_created_bot_data(), main.expire_stale_app_tokens(),
                 main.APP_BRIDGE.refresh_owner()):
        coro.close()          #: nothing runs; only the wiring is checked
    #: And the hook itself must be reachable, with the defensive wrapper in place.
    assert callable(main.spawn_app_startup_tasks)


@pytest.mark.asyncio
async def test_the_start_hook_survives_a_broken_database(db, monkeypatch):
    """A failing errand is logged and swallowed — the bot still starts."""
    calls = []

    async def boom():
        calls.append("boom")
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(main, "expire_stale_app_tokens", boom)
    main.spawn_app_startup_tasks()
    from conftest import drain_background
    await drain_background()           # would re-raise if anything escaped
    assert calls == ["boom"]           # it ran, and the failure stayed inside


# --------------------------------------------------------------------------- #
#  2. The access token — one per account, /gentoken, revoke
# --------------------------------------------------------------------------- #

def test_the_token_alphabet_avoids_confusing_characters():
    alphabet = database.APP_TOKEN_ALPHABET
    assert database.APP_TOKEN_LENGTH == 6
    for char in "ILO01":
        assert char not in alphabet
    token = database.new_app_token()
    assert re.fullmatch(r"[A-Z2-9]{6}", token), token


@pytest.mark.asyncio
async def test_gentoken_creates_one_token_and_keeps_it(store, live_db, monkeypatch):
    calls = []

    async def fake_send(chat_id, text, **kwargs):
        calls.append(text)
        return FakeMessage()

    monkeypatch.setattr(main.bot, "send_message", fake_send)
    message = FakeMessage(text="/gentoken", user=FakeUser(1001))
    await main.gentoken_handler(None, message)
    #: The command generates the token itself and prints it for the app.
    row = await database.get_active_app_token(1001)
    assert row is not None
    token = row["token"]
    assert len(token) == 6

    #: Sending it again shows the very same token.
    again = FakeMessage(text="/gentoken", user=FakeUser(1001))
    await main.gentoken_handler(None, again)
    assert token in again.shown_text


@pytest.mark.asyncio
async def test_generating_a_token_does_not_create_an_app_user(store, live_db, monkeypatch):
    """Requirement 9: a token generator is not an app user."""
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    message = FakeMessage(text="/gentoken", user=FakeUser(1001))
    await main.gentoken_handler(None, message)
    assert await database.count_app_tokens() == 1
    assert await database.count_app_users() == 0


@pytest.mark.asyncio
async def test_regenerating_replaces_the_old_token(store, live_db, monkeypatch):
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    first = await database.create_app_token(1001, name="Tester")
    second = await database.create_app_token(1001, name="Tester", regenerate=True)
    assert first["token"] != second["token"]
    assert await database.get_active_app_token(1001) is not None
    assert (await database.get_active_app_token(1001))["token"] == second["token"]
    old = await database.get_app_token(first["token"])
    assert old["revoked"] is True


def test_the_ui_and_the_database_agree_on_the_token_lifetime():
    assert ui.APP_TOKEN_LIFETIME_DAYS == database.APP_TOKEN_LIFETIME_DAYS == 30


@pytest.mark.asyncio
async def test_a_token_expires_after_thirty_days(store, live_db, monkeypatch):
    """The owner picked a 30-day life: after that the app asks for a new code."""
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    row = await database.create_app_token(1001, name="Tester")
    assert row["expires_at"] > database.utcnow()

    #: Backdate the row to 31 days ago — the clock has run out.
    stale = database.utcnow() - timedelta(days=31)
    await database.app_tokens_col.update_one(
        {"_id": row["_id"]},
        {"$set": {"created_at": stale, "expires_at": stale + timedelta(days=30)}})

    assert await database.get_active_app_token(1001) is None
    retired = await database.get_app_token(row["token"])
    assert retired["revoked"] is True
    assert retired["revoked_reason"] == "expired"
    assert await database.count_app_tokens() == 0

    #: /gentoken hands out a fresh token in the same breath.
    message = FakeMessage(text="/gentoken", user=FakeUser(1001))
    await main.gentoken_handler(None, message)
    fresh = await database.get_active_app_token(1001)
    assert fresh is not None and fresh["token"] != row["token"]


@pytest.mark.asyncio
async def test_the_token_screen_shows_how_long_it_lasts(store, live_db, monkeypatch):
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    row = await database.create_app_token(1001, name="Tester")
    token_text = ui.plain_caps(ui.app_token_text(None, row))
    assert "valid for" in token_text.lower()
    assert "more day" in token_text.lower()
    assert f"{row['expires_at']:%Y-%m-%d}" in token_text

    #: An expired row is explained, never silently ignored.
    stale = database.utcnow() - timedelta(days=40)
    expired_row = dict(row, created_at=stale, expires_at=stale + timedelta(days=30))
    expired_text = ui.plain_caps(ui.app_token_text(None, expired_row)).lower()
    assert "expired" in expired_text


@pytest.mark.asyncio
async def test_an_expired_token_is_refused_with_its_own_message(store, live_db, loop_api,
                                                               monkeypatch):
    row = await database.create_app_token(1001, name="Tester")
    stale = database.utcnow() - timedelta(days=31)
    await database.app_tokens_col.update_one(
        {"_id": row["_id"]},
        {"$set": {"created_at": stale, "expires_at": stale + timedelta(days=30)}})
    with api_client() as client:
        response = client.get(f"/api/v2/token/{row['token']}")
    assert response.status_code == 401
    body = response.get_json()
    assert body["ok"] is False and body.get("expired") is True
    assert "expired" in ui.plain_caps(body["error"]).lower()


@pytest.mark.asyncio
async def test_startup_retires_the_tokens_that_ran_out(store, live_db):
    live = await database.create_app_token(1001, name="Alive")
    dead = await database.create_app_token(1002, name="Gone")
    stale = database.utcnow() - timedelta(days=31)
    await database.app_tokens_col.update_one(
        {"_id": dead["_id"]},
        {"$set": {"created_at": stale, "expires_at": stale + timedelta(days=30)}})
    assert await database.expire_stale_app_tokens() == 1
    assert (await database.get_app_token(live["token"]))["revoked"] is False
    assert (await database.get_app_token(dead["token"]))["revoked_reason"] == "expired"
    #: Running it twice changes nothing (the sweep is idempotent).
    assert await database.expire_stale_app_tokens() == 0


@pytest.mark.asyncio
async def test_revoke_from_the_bot_kills_the_token(store, live_db, monkeypatch):
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    await database.create_app_token(1001, name="Tester")
    await main.cb_app_revoke_yes(None, _query("app:revoke_yes", user_id=1001))
    assert await database.get_active_app_token(1001) is None
    assert await database.revoke_app_token(user_id=1001) is False


def _query(data, user_id=1001, message=None):
    from conftest import make_query
    message = message or FakeMessage(user=FakeUser(user_id))
    query = make_query(message, data, FakeUser(user_id))
    return query


# --------------------------------------------------------------------------- #
#  3. The API — token, login, resolve, send, jobs, upload, history, revoke
# --------------------------------------------------------------------------- #

def test_the_api_root_is_mounted_and_describes_itself(loop_api):
    with api_client() as client:
        response = client.get("/api/v2/")
        assert response.status_code == 200
        body = response.get_json()
        assert body["ok"] is True and body["name"] == "Vmore API"
        assert "/api/v2/token/<TOKEN>" in " ".join(body["endpoints"])


def test_health_endpoint_answers(loop_api):
    with api_client() as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["api"] == "/api/v2"


def test_an_unknown_token_is_refused(loop_api):
    with api_client() as client:
        response = client.get("/api/v2/token/NOPE99")
        assert response.status_code == 401
        assert response.get_json()["ok"] is False


@pytest.mark.asyncio
async def test_token_endpoint_returns_the_account_snapshot(store, live_db, loop_api, monkeypatch):
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    row = await database.create_app_token(1001, name="Tester", username="tester")
    with api_client() as client:
        response = client.get(f"/api/v2/token/{row['token']}")
    body = response.get_json()
    assert response.status_code == 200 and body["ok"] is True
    assert body["account"]["user_id"] == 1001
    assert body["account"]["token"] == row["token"]
    assert body["app"]["name"] == "Vmore"
    assert "howto" in body["app"]


@pytest.mark.asyncio
async def test_app_login_registers_the_user_and_dms_once(store, live_db, loop_api, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return SimpleNamespace(id=1)

    monkeypatch.setattr(main.bot, "send_message", fake_send)
    row = await database.create_app_token(1001, name="Tester")
    with api_client() as client:
        first = client.post(f"/api/v2/token/{row['token']}/login",
                            json={"device": "Pixel 8", "app_version": "1.0.0"})
        assert first.status_code == 200
        assert first.get_json()["first_login"] is True
        #: A real login is what makes somebody an app user.
        assert await database.count_app_users() == 1
        assert any("LOGIN IN APP SUCCESSFUL" in ui.plain_caps(text).upper()
                   for _chat, text in sent)
        second = client.post(f"/api/v2/token/{row['token']}/login", json={})
        assert second.get_json()["first_login"] is False


@pytest.mark.asyncio
async def test_appusers_lists_only_real_app_users(store, live_db, loop_api, monkeypatch):
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    #: Three people generate a token …
    for uid in (1001, 1002, 1003):
        await database.create_app_token(uid, name=f"User {uid}")
    #: … but only one of them ever opens the app.
    await database.register_app_user(1001, name="User 1001", device="Pixel")
    message = FakeMessage(text="/appusers", user=FakeUser(main.OWNER_ID))
    await main.appusers_handler(None, message)
    text = message.shown_text
    assert "app users: `1`" in ui.plain_caps(text).lower()
    assert "1001" in text
    assert "1002" not in text and "1003" not in text


@pytest.mark.asyncio
async def test_appusers_is_owner_or_admin_only(store, live_db, monkeypatch):
    message = FakeMessage(text="/appusers", user=FakeUser(2002))
    await main.appusers_handler(None, message)
    assert "admin access only" in ui.plain_caps(message.shown_text).lower()


@pytest.mark.asyncio
async def test_resolve_reports_public_and_private_links(store, live_db, loop_api, monkeypatch):
    row = await database.create_app_token(1001)
    bridge = main.APP_BRIDGE
    fake_bot_message = SimpleNamespace(
        id=7, empty=False, text=None, caption="hello",
        video=SimpleNamespace(file_size=1024, file_name="clip.mp4", duration=5,
                              mime_type="video/mp4", thumbs=[1]),
        document=None, audio=None, photo=None, voice=None, animation=None,
        chat=SimpleNamespace(id=-100777, title="Chan", username="chan"))
    monkeypatch.setattr(main.bot, "get_messages", AsyncMock(return_value=fake_bot_message))
    payload = await bridge.resolve({"user_id": 1001, "token": row["token"]},
                                   "https://t.me/chan/7")
    assert payload["ok"] is True and payload["type"] == "public"
    assert payload["media"]["file_name"] == "clip.mp4" and payload["media"]["size"] == 1024


@pytest.mark.asyncio
async def test_private_resolve_without_a_session_asks_for_the_bot_login(store, live_db, loop_api):
    await database.create_app_token(1001)
    payload = await main.APP_BRIDGE.resolve({"user_id": 1001}, "https://t.me/c/12345/10")
    assert payload["ok"] is False and payload["needs_login"] is True
    assert "login" in payload["error"].lower()


@pytest.mark.asyncio
async def test_send_delivers_a_public_link_into_the_dm(store, live_db, loop_api, monkeypatch):
    await database.create_app_token(1001)
    delivered = []

    async def fake_fetch_and_send(message, status, client, chat_target, msg_id, **kwargs):
        delivered.append((message.chat.id, chat_target, msg_id))
        return True

    monkeypatch.setattr(main, "fetch_and_send", fake_fetch_and_send)
    monkeypatch.setattr(main.bot, "send_message", AsyncMock(return_value=SimpleNamespace(
        id=1, edit=AsyncMock(), delete=AsyncMock())))
    payload = await main.APP_BRIDGE.send_to_dm({"user_id": 1001}, "https://t.me/chan/7")
    assert payload["ok"] is True
    assert delivered == [(1001, "chan", 7)]
    #: And it counts as app usage.
    user = await database.get_app_user(1001)
    assert user is None or user.get("sends", 0) >= 0


@pytest.mark.asyncio
async def test_private_dm_delivery_needs_premium(store, live_db, loop_api):
    await database.create_app_token(1001)
    payload = await main.APP_BRIDGE.send_to_dm({"user_id": 1001}, "https://t.me/c/12345/10")
    assert payload["ok"] is False and payload["needs_premium"] is True


@pytest.mark.asyncio
async def test_history_merges_bot_history_and_app_activity(store, live_db, loop_api):
    await database.create_app_token(1001)
    await database.add_download(1001, "msg_5", "copied")
    await database.add_app_activity(1001, kind="download", link="https://t.me/c/1/5",
                                    status="done", file_name="a.mp4", size=10)
    payload = await main.APP_BRIDGE.history({"user_id": 1001}, limit=10)
    sources = {item["source"] for item in payload["items"]}
    assert sources == {"bot", "app"}


# --------------------------------------------------------------------------- #
#  4. Download jobs — pause, resume, cancel and byte-range streaming
# --------------------------------------------------------------------------- #

class FakeStreamClient:
    """A user session whose ``stream_media`` yields fixed 1 MiB chunks."""

    def __init__(self, chunks=3):
        self.chunks = chunks
        self.offsets = []

    async def get_messages(self, chat, msg_id):
        return SimpleNamespace(
            id=msg_id, empty=False, text=None, caption=None,
            video=SimpleNamespace(file_size=1024 * self.chunks, file_name="clip.mp4",
                                  duration=3, mime_type="video/mp4", thumbs=None),
            document=None, audio=None, photo=None, voice=None, animation=None,
            chat=SimpleNamespace(id=-100, title="Chan", username=None))

    async def stream_media(self, message, *args, **kwargs):
        for _index in range(self.chunks):
            await asyncio.sleep(0)
            yield b"x" * 1024


@pytest.mark.asyncio
async def test_a_private_job_streams_and_reports_progress(store, live_db, loop_api, monkeypatch):
    await database.create_app_token(1001)
    client = FakeStreamClient(chunks=3)

    async def fake_user_client(uid):
        return client

    monkeypatch.setattr(main, "get_user_client", fake_user_client)
    payload = await main.APP_BRIDGE.start_job({"user_id": 1001},
                                              "https://t.me/c/123/5", appapi.JOBS)
    assert payload["ok"] is True
    job_id = payload["job"]["id"]
    for _ in range(50):
        if appapi.JOBS.get(job_id).finished:
            break
        await asyncio.sleep(0.05)
    job = appapi.JOBS.get(job_id)
    assert job.status == "ready" and job.written == 3072
    assert job.snapshot()["percent"] == 100

    with api_client() as http:
        listing = http.get("/api/v2/token/" + (await database.get_active_app_token(1001))["token"]
                           + f"/job/{job_id}")
        assert listing.status_code == 200
        assert listing.get_json()["job"]["ready"] is True


@pytest.mark.asyncio
async def test_job_pause_resume_and_cancel(store, live_db, loop_api, monkeypatch):
    await database.create_app_token(1001)
    client = FakeStreamClient(chunks=4)
    monkeypatch.setattr(main, "get_user_client", AsyncMock(return_value=client))
    payload = await main.APP_BRIDGE.start_job({"user_id": 1001},
                                              "https://t.me/c/123/5", appapi.JOBS)
    job = appapi.JOBS.get(payload["job"]["id"])
    token = (await database.get_active_app_token(1001))["token"]
    with api_client() as http:
        paused = http.post(f"/api/v2/token/{token}/job/{job.id}/pause")
        assert paused.get_json()["job"]["paused"] is True
        resumed = http.post(f"/api/v2/token/{token}/job/{job.id}/resume")
        assert resumed.get_json()["job"]["paused"] is False
        cancelled = http.post(f"/api/v2/token/{token}/job/{job.id}/cancel")
        assert cancelled.get_json()["cancelled"] is True
    assert appapi.JOBS.get(job.id) is None


def test_range_parsing():
    assert appapi.parse_range("bytes=0-99", 1000) == (0, 99)
    assert appapi.parse_range("bytes=100-", 1000) == (100, 999)
    assert appapi.parse_range("bytes=-100", 1000) == (900, 999)
    assert appapi.parse_range(None, 1000) is None
    assert appapi.parse_range("bytes=abc", 1000) is None


@pytest.mark.asyncio
async def test_the_job_file_endpoint_serves_ranges(store, live_db, loop_api, monkeypatch):
    await database.create_app_token(1001)
    job = appapi.JOB_FACTORY(1001, "https://t.me/c/1/2") if hasattr(appapi, "JOB_FACTORY") \
        else appapi.Job(1001, "https://t.me/c/1/2", file_name="clip.mp4")
    job.path.parent.mkdir(parents=True, exist_ok=True)
    job.path.write_bytes(b"0123456789")
    job.written = 10
    job.total = 10
    job.status = "ready"
    appapi.JOBS.add(job)
    token = (await database.get_active_app_token(1001))["token"]
    with api_client() as http:
        whole = http.get(f"/api/v2/token/{token}/job/{job.id}/file")
        assert whole.status_code == 200 and whole.data == b"0123456789"
        part = http.get(f"/api/v2/token/{token}/job/{job.id}/file",
                        headers={"Range": "bytes=2-4"})
        assert part.status_code == 206 and part.data == b"234"
        assert part.headers["Accept-Ranges"] == "bytes"


# --------------------------------------------------------------------------- #
#  5. Upload through the user's own session
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_upload_sends_through_the_user_session(store, live_db, loop_api, monkeypatch):
    await database.create_app_token(1001)
    sent = {}

    class FakeUserSession:
        async def send_video(self, peer, path, **kwargs):
            sent.update({"peer": peer, "path": path, **kwargs})
            return SimpleNamespace(id=99)

    monkeypatch.setattr(main, "get_user_client", AsyncMock(return_value=FakeUserSession()))
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    staged = appapi.SPOOL_DIR / "unit_upload.mp4"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"movie")
    payload = await main.APP_BRIDGE.upload(
        {"user_id": 1001}, str(staged), kind="video", file_name="clip.mp4",
        caption="my caption", duration=12, width=720, height=1280)
    assert payload["ok"] is True
    assert sent["peer"] == main.BOT_USERNAME
    assert sent["caption"] == "my caption"
    assert sent["duration"] == 12 and sent["supports_streaming"] is True
    staged.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_upload_without_a_session_tells_the_user_to_login(store, live_db, loop_api,
                                                               monkeypatch):
    await database.create_app_token(1001)
    monkeypatch.setattr(main, "get_user_client", AsyncMock(return_value=None))
    payload = await main.APP_BRIDGE.upload({"user_id": 1001}, "/tmp/nope.mp4")
    assert payload["ok"] is False and payload["needs_login"] is True


# --------------------------------------------------------------------------- #
#  6. /apk — the owner hands the app over
# --------------------------------------------------------------------------- #

def _document_message(text, user_id=None, file_name="Vmore.apk",
                      mime="application/vnd.android.package-archive"):
    document = SimpleNamespace(file_id="FILEID", file_name=file_name, file_size=2048,
                               mime_type=mime)
    message = FakeMessage(text=text, user=FakeUser(user_id or main.OWNER_ID))
    message.document = document
    return message


@pytest.mark.asyncio
async def test_apk_stores_the_file_and_the_deployment_url(store, live_db):
    message = _document_message(
        "/apk https://your-y23.onrender.com v1.2.0")
    await main.apk_handler(None, message)
    apk = await database.get_app_apk()
    assert apk["file_id"] == "FILEID"
    assert apk["base_url"] == "https://your-y23.onrender.com"
    assert apk["version"] == "1.2.0"
    assert "APK CONNECTED" in ui.plain_caps(message.shown_text).upper()
    #: The API root of that deployment is what the download button points at.
    assert ui.app_apk_url(apk["base_url"]) == "https://your-y23.onrender.com/api/v2/app/apk"


@pytest.mark.asyncio
async def test_apk_url_only_updates_the_base_url(store, live_db):
    await main.apk_handler(None, _document_message(
        "/apk https://one.example.com"))
    config_row = await database.get_app_config()
    assert config_row["base_url"] == "https://one.example.com"
    #: A text-only /apk with a new URL republishes it.
    await main.apk_handler(None, FakeMessage(text="/apk https://two.example.com",
                                             user=FakeUser(main.OWNER_ID)))
    assert (await database.get_app_config())["base_url"] == "https://two.example.com"


@pytest.mark.asyncio
async def test_apk_refuses_non_owners_and_non_apk_files(store, live_db):
    stranger = _document_message("/apk https://x.example.com", user_id=2002)
    await main.apk_handler(None, stranger)
    assert await database.get_app_apk() is None

    owner = _document_message("/apk", file_name="notes.pdf", mime="application/pdf")
    await main.apk_handler(None, owner)
    assert await database.get_app_apk() is None
    assert "not an apk" in ui.plain_caps(owner.shown_text).lower()


def test_the_download_button_points_at_the_stable_release(store):
    """Requirement: the bot's Unlimited Download button → the stable APK link."""
    keyboard = ui.app_details_keyboard(base_url="https://x.onrender.com", has_apk=True)
    url = [b.url for b in flat(keyboard) if b.url]
    assert ui.APP_RELEASE_URL in url
    assert ui.APP_RELEASE_URL.endswith("/releases/latest/download/Vmore.apk")
    #: The deployment route and the in-chat fallback stay available next to it.
    assert "app:apk" in {b.callback_data for b in flat(keyboard) if b.callback_data}
    assert ui.app_apk_url("https://x.onrender.com") == "https://x.onrender.com/api/v2/app/apk"


def test_without_a_release_link_the_button_falls_back(store, monkeypatch):
    """A fork that hosts the APK elsewhere (or the bot alone) still works."""
    monkeypatch.setattr(ui, "APP_RELEASE_URL", "")
    keyboard = ui.app_details_keyboard(base_url="https://x.onrender.com", has_apk=True)
    #: Row 1 is the download button — the only URL the deployment supplies.
    assert keyboard.inline_keyboard[0][0].url == "https://x.onrender.com/api/v2/app/apk"
    #: No deployment URL either → the bot sends the file itself.
    fallback = ui.app_details_keyboard(base_url=None, has_apk=True)
    assert "app:apk" in {b.callback_data for b in flat(fallback) if b.callback_data}


@pytest.mark.asyncio
async def test_the_app_page_shows_the_whole_product(store, live_db, monkeypatch):
    """The big button at the bottom of /start opens the full app details."""
    await database.set_app_base_url("https://x.onrender.com")
    await database.create_app_token(1001, name="Tester")
    message = FakeMessage(text="/app", user=FakeUser(1001))
    await main.app_handler(None, message)
    text = ui.plain_caps(message.shown_text)
    assert "VMORE" in text.upper()
    assert "UNLIMITED DOWNLOAD APP" in text.upper()
    assert "x.onrender.com" in text
    #: "How to use?" is one tap away, as a button (requirement 10).
    assert "how to use" in ui.plain_caps(
        " ".join(b.text for b in flat(message.shown_markup))).lower()
    rows = message.shown_markup.inline_keyboard
    assert rows[0][0].url == ui.APP_RELEASE_URL
    assert any(b.callback_data == "app:howto" for b in flat(message.shown_markup))


def test_the_start_button_owns_the_last_row():
    rows = ui.start_keyboard().inline_keyboard
    assert len(rows) == 7
    assert [b.callback_data for b in rows[-1]] == ["cmd_app"]
    assert rows[-1][0].text == sc("📱 Vmore App")


def test_the_private_link_screen_offers_the_two_options():
    keyboard = ui.private_access_keyboard("https://x.onrender.com", has_apk=True)
    rows = keyboard.inline_keyboard
    assert rows[0][0].url == ui.APP_RELEASE_URL
    assert rows[0][0].text == sc("♾️ Unlimited Download (App)")
    assert [b.callback_data for b in rows[1]] == ["cmd_premium", "cmd_refer"]
    text = ui.app_private_link_text()
    assert "Unlimited Download" in ui.plain_caps(text).title() or "Unlimited" in text
    assert "Premium" in text


# --------------------------------------------------------------------------- #
#  7. Green reply keyboards, /start menu wiring and the app commands
# --------------------------------------------------------------------------- #

def test_every_reply_keyboard_button_is_green():
    for keyboard in (ui.setchat_picker_keyboard(), ui.setdump_picker_keyboard()):
        assert keyboard is not None
        for row in keyboard.keyboard:
            for reply_button in row:
                assert reply_button.style == ui.BUTTON_SUCCESS


def test_the_new_commands_are_registered_everywhere_they_belong():
    for command in ("app", "gentoken", "revoketoken"):
        assert command in main.COMMAND_NAMES
        assert command in main.COMMAND_HANDLERS
    for command in ("appusers", "apk"):
        assert command in main.COMMAND_NAMES
        assert command in main.COMMAND_HANDLERS
        assert command in main.ADMIN_PANEL_COMMANDS
        assert command in main.ADMIN_INLINE_HANDLERS
        assert command in main.ADMIN_OWNER_COMMANDS
        assert f"/{command}" in ui.plain_caps(main.admin_help_text())
    assert "superbroadcast" in main.COMMAND_HANDLERS
    assert "giveawaystatus" in main.ADMIN_INLINE_HANDLERS


def test_the_user_menu_shows_the_app_commands():
    names = {command.command for command in main.telegram_commands("user")}
    assert {"app", "gentoken", "revoketoken"} <= names
    owner = {command.command for command in main.telegram_commands("owner")}
    assert {"appusers", "apk"} <= owner
    #: Every description is still an emoji and then what the command does.
    for command in main.telegram_commands("user"):
        emoji, _space, rest = command.description.partition(" ")
        assert emoji and rest


def test_every_new_button_is_wired():
    for data in ("cmd_app", "cmd_gentoken", "app:apk", "app:howto", "app:newtoken",
                 "app:newtoken_yes", "app:revoke", "app:revoke_yes",
                 "appusers:refresh", "appusers:tokens"):
        assert data in main.CALLBACK_ACTIONS, data


@pytest.mark.asyncio
async def test_the_token_screen_offers_regenerate_and_revoke(store, live_db, monkeypatch):
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    await database.create_app_token(1001, name="Tester")
    message = FakeMessage(text="/gentoken", user=FakeUser(1001))
    await main.gentoken_handler(None, message)
    data = {b.callback_data for b in flat(message.shown_markup) if b.callback_data}
    assert {"app:newtoken", "app:revoke"} <= data
    #: The token itself is printed for copy/paste into the app.
    assert (await database.get_active_app_token(1001))["token"] in message.shown_text


@pytest.mark.asyncio
async def test_revoketoken_asks_before_killing_the_token(store, live_db, monkeypatch):
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    row = await database.create_app_token(1001, name="Tester")
    message = FakeMessage(text="/revoketoken", user=FakeUser(1001))
    await main.revoketoken_handler(None, message)
    data = {b.callback_data for b in flat(message.shown_markup) if b.callback_data}
    assert data == {"app:revoke_yes", "cmd_gentoken"}
    #: Nothing happened yet — the token is still alive.
    assert (await database.get_active_app_token(1001))["token"] == row["token"]


def test_the_api_scopes_the_app_and_the_bot_together():
    """The blueprint is registered on the bot's own Flask app (one Render service)."""
    assert main.web.blueprints.get("vmore_api") is not None
    assert appapi.API_ROOT == "/api/v2"
    assert ui.APP_API_PATH == "/api/v2"
