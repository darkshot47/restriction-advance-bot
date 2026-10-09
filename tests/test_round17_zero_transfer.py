"""Round 17 — zero-transfer uploads: the phone (and the host) stop paying twice.

The owner ran out of hosting bandwidth because every private-link round trip
crossed the server **four** times (Telegram → server → phone → server →
Telegram).  This round pins the fix: when the app changed nothing but the
caption (and at most the thumbnail), the phone ships **no bytes at all** —

* the still-warm spool of the finished download job is pushed out as-is
  (``via == "spool"``),
* else Telegram itself re-sends the message (``copy_message`` / cached media:
  ``via == "copy"`` / ``"reference"`` — zero bytes on the host),
* else the host re-downloads once and the user's own session pushes it back
  (``via == "download"`` — the phone is *still* out of it),
* and only when none of that can work does the reply carry ``needs_bytes`` so
  the app falls back to the classic byte upload on its own.

Everything runs on the in-memory fakes and Flask's own test client — no
Telegram and no MongoDB, exactly like round 16.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

import appapi
import database
import main


PRIVATE_LINK = "https://t.me/c/123/55"


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


def _media_message(caption="the original words", file_id="FILEID"):
    """A private message with one video — the thing there is to re-send."""
    media = SimpleNamespace(file_id=file_id, file_size=4096, file_name="clip.mp4",
                            duration=12, mime_type="video/mp4")
    return SimpleNamespace(
        id=55, empty=False, caption=caption, text=None,
        video=media, document=None, audio=None, photo=None, voice=None,
        animation=None, sticker=None, video_note=None,
        chat=SimpleNamespace(id=-1000000000123, title="Private chan"))


class ZeroTransferSession:
    """A user session that records every re-send attempt the bridge makes."""

    def __init__(self, message, *, copy_fails=False, cached_fails=False):
        self.message = message
        self.copy_fails = copy_fails
        self.cached_fails = cached_fails
        self.copied = None
        self.cached = None
        self.downloaded_to = None
        self.sent = None

    async def get_messages(self, chat, msg_id):
        return self.message

    async def copy_message(self, target, from_chat, msg_id, caption=None, **kwargs):
        if self.copy_fails:
            raise RuntimeError("CHAT_FORBIDDEN")
        self.copied = {"target": target, "from": from_chat, "msg_id": msg_id,
                       "caption": caption}
        return SimpleNamespace(id=77)

    async def send_cached_media(self, target, file_id, caption=None, **kwargs):
        if self.cached_fails:
            raise RuntimeError("MEDIA_EMPTY")
        self.cached = {"target": target, "file_id": file_id, "caption": caption}
        return SimpleNamespace(id=78)

    async def download_media(self, message, file_name=None, **kwargs):
        self.downloaded_to = file_name
        with open(file_name, "wb") as handle:
            handle.write(b"pulled down on the server")
        return file_name

    async def send_video(self, peer, path, **kwargs):
        self.sent = {"peer": peer, "path": path, **kwargs}
        return SimpleNamespace(id=79)

    async def send_photo(self, peer, path, **kwargs):
        self.sent = {"peer": peer, "path": path, **kwargs}
        return SimpleNamespace(id=79)

    async def send_audio(self, peer, path, **kwargs):
        self.sent = {"peer": peer, "path": path, **kwargs}
        return SimpleNamespace(id=79)

    async def send_document(self, peer, path, **kwargs):
        self.sent = {"peer": peer, "path": path, **kwargs}
        return SimpleNamespace(id=79)


def _bind_session(monkeypatch, session):
    monkeypatch.setattr(main, "get_user_client", AsyncMock(return_value=session))
    monkeypatch.setattr(main.bot, "send_message", AsyncMock())


# --------------------------------------------------------------------------- #
#  1. The bridge: zero-transfer re-sends
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_reference_upload_copies_without_moving_a_byte(store, live_db, loop_api,
                                                             monkeypatch):
    """The headline fix: Telegram re-sends — the host moves literally nothing."""
    await database.create_app_token(1001)
    session = ZeroTransferSession(_media_message())
    _bind_session(monkeypatch, session)
    payload = await main.APP_BRIDGE.upload_reference({"user_id": 1001}, PRIVATE_LINK,
                                                     caption="new words")
    assert payload["ok"] is True and payload["via"] == "copy"
    assert session.copied["target"] == main.BOT_USERNAME
    assert session.copied["from"] == -1000000000123
    assert session.copied["msg_id"] == 55
    assert session.copied["caption"] == "new words"
    #: Nothing was downloaded and nothing was re-uploaded: zero transfer.
    assert session.downloaded_to is None and session.sent is None


@pytest.mark.asyncio
async def test_an_empty_caption_keeps_the_original_words(store, live_db, loop_api,
                                                         monkeypatch):
    """The app sends an empty caption to mean "don't touch the words"."""
    await database.create_app_token(1001)
    session = ZeroTransferSession(_media_message(caption="keep me"))
    _bind_session(monkeypatch, session)
    payload = await main.APP_BRIDGE.upload_reference({"user_id": 1001}, PRIVATE_LINK,
                                                     caption="")
    assert payload["ok"] is True
    assert session.copied["caption"] == "keep me"


@pytest.mark.asyncio
async def test_a_refused_copy_falls_back_to_the_cached_media(store, live_db, loop_api,
                                                             monkeypatch):
    """Restricted chats refuse copies: the file_id re-send costs zero too."""
    await database.create_app_token(1001)
    session = ZeroTransferSession(_media_message(file_id="RESTRICTED_ID"),
                                  copy_fails=True)
    _bind_session(monkeypatch, session)
    payload = await main.APP_BRIDGE.upload_reference({"user_id": 1001}, PRIVATE_LINK,
                                                     caption="again")
    assert payload["ok"] is True and payload["via"] == "reference"
    assert session.cached == {"target": main.BOT_USERNAME,
                              "file_id": "RESTRICTED_ID", "caption": "again"}
    assert session.downloaded_to is None and session.sent is None


@pytest.mark.asyncio
async def test_a_new_thumbnail_forces_the_server_side_re_upload(store, live_db, loop_api,
                                                                monkeypatch):
    """Telegram cannot swap a thumbnail inside a copy — so the bytes move once
    on the host (download + user-session upload) and never on the phone."""
    await database.create_app_token(1001)
    session = ZeroTransferSession(_media_message())
    _bind_session(monkeypatch, session)
    thumb = appapi.SPOOL_DIR / "unit_thumb_ref.jpg"
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"\xff\xd8\xff")
    payload = await main.APP_BRIDGE.upload_reference(
        {"user_id": 1001}, PRIVATE_LINK, caption="c", thumbnail=str(thumb))
    #: The zero-byte paths were never even tried.
    assert session.copied is None and session.cached is None
    assert payload["ok"] is True and payload["via"] == "download"
    assert session.downloaded_to is not None
    assert session.sent["peer"] == main.BOT_USERNAME
    assert session.sent["thumb"] == str(thumb)
    #: The staged re-download is cleaned up behind the bridge's back?  No: it
    #: is the bridge itself that unlinks it once the session has the file.
    import os
    assert not os.path.exists(session.downloaded_to)
    thumb.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_every_reference_refusal_still_spares_the_phone(store, live_db, loop_api,
                                                              monkeypatch):
    """Copy and cached re-send both fail: the host pulls the media once, the
    user's session pushes it back — the phone's bill is untouched."""
    await database.create_app_token(1001)
    session = ZeroTransferSession(_media_message(), copy_fails=True, cached_fails=True)
    _bind_session(monkeypatch, session)
    payload = await main.APP_BRIDGE.upload_reference({"user_id": 1001}, PRIVATE_LINK,
                                                     caption="last resort")
    assert payload["ok"] is True and payload["via"] == "download"
    assert session.sent is not None and session.sent["caption"] == "last resort"
    import os
    assert not os.path.exists(session.downloaded_to)


@pytest.mark.asyncio
async def test_reference_upload_without_a_session_asks_for_login(store, live_db, loop_api,
                                                                 monkeypatch):
    await database.create_app_token(1001)
    monkeypatch.setattr(main, "get_user_client", AsyncMock(return_value=None))
    payload = await main.APP_BRIDGE.upload_reference({"user_id": 1001}, PRIVATE_LINK)
    assert payload["ok"] is False and payload["needs_login"] is True


@pytest.mark.asyncio
async def test_a_missing_message_says_the_bytes_are_needed(store, live_db, loop_api,
                                                           monkeypatch):
    await database.create_app_token(1001)
    session = ZeroTransferSession(None)
    _bind_session(monkeypatch, session)
    payload = await main.APP_BRIDGE.upload_reference({"user_id": 1001}, PRIVATE_LINK)
    assert payload["ok"] is False and payload["needs_bytes"] is True


@pytest.mark.asyncio
async def test_a_media_less_message_refuses_with_needs_bytes(store, live_db, loop_api,
                                                             monkeypatch):
    await database.create_app_token(1001)
    text_only = _media_message()
    text_only.video = None
    session = ZeroTransferSession(text_only)
    _bind_session(monkeypatch, session)
    payload = await main.APP_BRIDGE.upload_reference({"user_id": 1001}, PRIVATE_LINK)
    assert payload["ok"] is False and payload["needs_bytes"] is True


# --------------------------------------------------------------------------- #
#  2. The endpoint: no file attached ⇒ server-side re-send
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_the_upload_endpoint_replays_the_spooled_job(store, live_db, loop_api,
                                                           monkeypatch):
    """Warmest path: the bytes the phone downloaded are still on the server,
    so the commit only ships the caption and nothing else moves."""
    row = await database.create_app_token(1001)
    session = ZeroTransferSession(_media_message())
    _bind_session(monkeypatch, session)
    job = appapi.Job(1001, PRIVATE_LINK, kind="video", file_name="clip.mp4")
    job.path = appapi.SPOOL_DIR / "unit_spooled.mp4"
    job.path.parent.mkdir(parents=True, exist_ok=True)
    job.path.write_bytes(b"already here")
    job.status = "ready"
    appapi.JOBS.add(job)
    with api_client() as http:
        response = http.post(f"/api/v2/token/{row['token']}/upload", data={
            "job_id": job.id, "caption": "fresh caption", "kind": "video"})
    body = response.get_json()
    assert response.status_code == 200 and body["ok"] is True
    assert body["via"] == "spool"
    assert session.sent["path"] == str(job.path)
    assert session.sent["caption"] == "fresh caption"
    #: The job owns its spooled file — the commit must not eat it.
    assert job.path.exists()
    job.path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_the_upload_endpoint_re_sends_by_reference_when_no_job_is_known(
        store, live_db, loop_api, monkeypatch):
    """The job went stale but the link stands: Telegram does the work."""
    row = await database.create_app_token(1001)
    session = ZeroTransferSession(_media_message())
    _bind_session(monkeypatch, session)
    with api_client() as http:
        response = http.post(f"/api/v2/token/{row['token']}/upload", data={
            "link": PRIVATE_LINK, "caption": "", "kind": "video"})
    body = response.get_json()
    assert response.status_code == 200 and body["ok"] is True
    assert body["via"] == "copy"
    assert session.copied is not None and session.downloaded_to is None


@pytest.mark.asyncio
async def test_the_upload_endpoint_flags_a_byte_fallback(store, live_db, loop_api,
                                                         monkeypatch):
    """No reachable message ⇒ the reply tells the app to send the bytes."""
    row = await database.create_app_token(1001)
    session = ZeroTransferSession(None)
    _bind_session(monkeypatch, session)
    with api_client() as http:
        response = http.post(f"/api/v2/token/{row['token']}/upload", data={
            "link": PRIVATE_LINK, "caption": ""})
    body = response.get_json()
    assert response.status_code == 400
    assert body["ok"] is False and body["needs_bytes"] is True


@pytest.mark.asyncio
async def test_the_upload_endpoint_still_demands_a_file_without_any_reference(
        store, live_db, loop_api, monkeypatch):
    """Neither file, job nor link is a 400 — the contract from round 16."""
    row = await database.create_app_token(1001)
    _bind_session(monkeypatch, ZeroTransferSession(_media_message()))
    with api_client() as http:
        response = http.post(f"/api/v2/token/{row['token']}/upload", data={})
    body = response.get_json()
    assert response.status_code == 400
    assert body["ok"] is False and "'file'" in body["error"]
