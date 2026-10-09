"""Round 18 — TDLib direct mode: the server becomes bandwidth-free.

The owner's hard requirement: *when a user downloads or uploads, their own
phone data carries the bytes, never the Render host's bandwidth.*  The
zero-transfer round (17) already made the upload leg disappear; this round
pins the remaining piece — the phone's own Telegram session (TDLib) needs
the application's api_id/api_hash and the bot's username, and the
``GET /api/v2/app`` payload is where the app learns them.

Everything runs on the in-memory fakes and Flask's own test client — no
Telegram and no MongoDB, exactly like rounds 16 and 17.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

import appapi
import database
import main


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
#  The TDLib handshake payload
# --------------------------------------------------------------------------- #

def test_td_config_hands_the_app_the_same_app_credentials():
    """The phone logs into Telegram with the *same* api_id/api_hash the bot's
    server-side sessions use — so the two sessions coexist on one Telegram app."""
    config = main.APP_BRIDGE.td_config()
    assert config["td_api_id"] == int(main.API_ID)
    assert config["td_api_hash"] == main.API_HASH
    assert config["bot_username"] == main.BOT_USERNAME


def test_td_config_copes_with_missing_credentials(monkeypatch):
    """A deployment without the env pair must answer sanely, never crash the
    app-info endpoint that everything else also reads."""
    monkeypatch.setattr(main, "API_ID", 0)
    monkeypatch.setattr(main, "API_HASH", None)
    monkeypatch.setattr(main, "BOT_USERNAME", "")
    config = main.APP_BRIDGE.td_config()
    assert config == {"td_api_id": 0, "td_api_hash": "", "bot_username": ""}


@pytest.mark.asyncio
async def test_the_app_info_endpoint_carries_the_td_config(store, live_db, loop_api,
                                                           monkeypatch):
    """The app fetches ``/api/v2/app`` once at startup — TDLib creds ride it."""
    await database.create_app_token(1001)
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())
    with api_client() as http:
        response = http.get("/api/v2/app")
    body = response.get_json()
    assert response.status_code == 200 and body["ok"] is True
    assert body["td_api_id"] == int(main.API_ID)
    assert body["td_api_hash"] == main.API_HASH
    assert body["bot_username"] == main.BOT_USERNAME
    #: Nothing else was lost along the way.
    assert body["name"] == appapi.APP_NAME and "howto" in body and "owner" in body
