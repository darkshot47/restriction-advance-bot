"""Shared test fixtures.

The bot module reads its credentials from the environment at import time, so we
set harmless dummy values first and then replace every database function with an
in-memory fake — the tests never touch MongoDB or Telegram.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:AAH-test-token")
os.environ.setdefault("OWNER_ID", "1")
os.environ.setdefault("BOT_USERNAME", "TestRestrictBot")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import main  # noqa: E402  (import after the environment is ready)
from pyrogram.types import CallbackQuery  # noqa: E402


# --------------------------------------------------------------------------- #
#  Fakes
# --------------------------------------------------------------------------- #

class FakeUser:
    def __init__(self, user_id: int = 1001, first_name: str = "Tester", username: str = "tester"):
        self.id = user_id
        self.first_name = first_name
        self.username = username


class FakeChat:
    def __init__(self, chat_id: int = 1001):
        self.id = chat_id


class FakeMessage:
    """Records everything the bot replies / edits with."""

    def __init__(self, text: str = "", user: FakeUser | None = None, message_id: int = 1):
        self.id = message_id
        self.text = text
        self.from_user = user or FakeUser()
        self.chat = FakeChat(self.from_user.id)
        self.replies: list[dict] = []
        self.edits: list[dict] = []
        self.markups: list = []
        self.deleted = False

    async def reply(self, text, reply_markup=None, **kwargs):
        self.replies.append({"text": text, "reply_markup": reply_markup})
        return self

    async def edit(self, text, reply_markup=None, **kwargs):
        return await self.edit_text(text, reply_markup, **kwargs)

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.edits.append({"text": text, "reply_markup": reply_markup})
        return self

    async def edit_reply_markup(self, reply_markup=None):
        self.markups.append(reply_markup)
        return self

    async def delete(self):
        self.deleted = True

    # assertions helpers -----------------------------------------------------
    @property
    def last_reply(self) -> dict:
        assert self.replies, "the bot did not reply"
        return self.replies[-1]

    @property
    def last_edit(self) -> dict:
        assert self.edits, "the bot did not edit the message"
        return self.edits[-1]

    @property
    def shown_text(self) -> str:
        if self.edits:
            return self.edits[-1]["text"]
        return self.replies[-1]["text"] if self.replies else ""

    @property
    def shown_markup(self):
        if self.edits:
            return self.edits[-1]["reply_markup"]
        return self.replies[-1]["reply_markup"] if self.replies else None

    def callback_data(self) -> list[str]:
        markup = self.shown_markup
        if markup is None:
            return []
        return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]

    def button_texts(self) -> list[str]:
        markup = self.shown_markup
        if markup is None:
            return []
        return [b.text for row in markup.inline_keyboard for b in row]

    def button(self, callback_data: str):
        markup = self.shown_markup
        for row in markup.inline_keyboard:
            for b in row:
                if b.callback_data == callback_data:
                    return b
        raise AssertionError(f"button {callback_data!r} not found in {self.callback_data()}")


class RecordingAnswer:
    """Stands in for CallbackQuery.answer()."""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, text=None, show_alert=None, url=None, cache_time=0):
        self.calls.append({"text": text, "show_alert": show_alert})

    @property
    def texts(self) -> list[str]:
        return [c["text"] for c in self.calls if c["text"]]


class FakeDB:
    """In-memory replacement for every database function used by main.py."""

    def __init__(self):
        self.users: dict[int, dict] = {}
        self.downloads: list[dict] = []
        self.feedback: list[tuple[int, str]] = []
        self.bookmarks: dict[int, list[str]] = {}
        self.sessions: dict[int, str] = {}
        self.maintenance = False
        self.fsub = None
        self.admins: set[int] = set()

    # users -----------------------------------------------------------------
    def _new_user(self, user_id, name, username):
        now = _dt.datetime.now()
        return {
            "user_id": user_id,
            "name": name,
            "username": username,
            "phone": None,
            "session_string": None,
            "caption": None,
            "thumbnail_id": None,
            "prefix": None,
            "suffix": None,
            "language": "en",
            "is_banned": False,
            "is_premium": False,
            "is_admin": False,
            "premium_expiry": None,
            "downloads": 0,
            "daily_downloads": 0,
            "joined_date": now,
            "last_active": now,
            "referral_count": 0,
            "points": 0,
            "premium_source": None,
            "referred_by": None,
            "notifications": True,
            "silent_mode": False,
            "favorites": [],
        }

    async def add_user(self, user_id, name, username=None):
        if user_id in self.users:
            return False
        self.users[user_id] = self._new_user(user_id, name, username)
        return True

    async def get_user(self, user_id):
        return self.users.get(user_id)

    async def is_premium(self, user_id):
        user = self.users.get(user_id)
        return bool(user and user.get("is_premium"))

    async def is_banned(self, user_id):
        user = self.users.get(user_id)
        return bool(user and user.get("is_banned"))

    async def is_admin(self, user_id):
        return user_id in self.admins

    async def check_daily_limit(self, user_id, limit=10):
        user = self.users.get(user_id) or {}
        return (user.get("daily_downloads", 0) < limit, user.get("daily_downloads", 0))

    async def increment_daily(self, user_id, count_daily=True):
        user = self.users.get(user_id)
        if user:
            user["daily_downloads"] = user.get("daily_downloads", 0) + int(count_daily)
            user["downloads"] = user.get("downloads", 0) + 1

    # sessions --------------------------------------------------------------
    async def save_session(self, user_id, session_string, phone=None):
        self.sessions[user_id] = session_string
        user = self.users.get(user_id)
        if user:
            user["phone"] = phone
            user["session_string"] = session_string

    async def get_session(self, user_id):
        return self.sessions.get(user_id)

    async def delete_session(self, user_id):
        self.sessions.pop(user_id, None)
        user = self.users.get(user_id)
        if user:
            user["phone"] = None
            user["session_string"] = None

    async def get_all_users(self):
        return list(self.users.values())

    async def get_logged_users_list(self):
        result = []
        for uid, user in self.users.items():
            session = self.sessions.get(uid) or user.get("session_string")
            if session:
                u = dict(user)
                u["session_string"] = session
                result.append(u)
        return result

    # settings --------------------------------------------------------------
    async def set_language(self, user_id, lang):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))["language"] = lang

    async def toggle_notifications(self, user_id):
        user = self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))
        user["notifications"] = not user.get("notifications", True)
        return user["notifications"]

    async def toggle_silent(self, user_id):
        user = self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))
        user["silent_mode"] = not user.get("silent_mode", False)
        return user["silent_mode"]

    async def reset_settings(self, user_id):
        user = self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))
        user.update({
            "caption": None, "thumbnail_id": None, "prefix": None, "suffix": None,
            "language": "en", "notifications": True, "silent_mode": False,
        })

    async def set_caption(self, user_id, caption):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))["caption"] = caption

    async def get_caption(self, user_id):
        return (self.users.get(user_id) or {}).get("caption")

    async def get_prefix(self, user_id):
        return (self.users.get(user_id) or {}).get("prefix")

    async def get_suffix(self, user_id):
        return (self.users.get(user_id) or {}).get("suffix")

    async def get_thumbnail(self, user_id):
        return (self.users.get(user_id) or {}).get("thumbnail_id")

    # feedback / referrals --------------------------------------------------
    async def add_feedback(self, user_id, message):
        self.feedback.append((user_id, message))

    async def add_referral(self, referrer_id, new_user_id):
        user = self.users.setdefault(referrer_id, self._new_user(referrer_id, "Tester", None))
        user["referral_count"] = user.get("referral_count", 0) + 1

    async def get_points(self, user_id):
        return (self.users.get(user_id) or {}).get("points", 0)

    async def award_referral(self, referrer_id, new_user_id, points=10):
        if referrer_id == new_user_id:
            return False
        ref = self.users.setdefault(referrer_id, self._new_user(referrer_id, "Tester", None))
        new = self.users.setdefault(new_user_id, self._new_user(new_user_id, "Tester", None))
        if new.get("referred_by") is not None:
            return False
        new["referred_by"] = referrer_id
        ref["referral_count"] += 1
        ref["points"] += points
        return True

    async def redeem_points(self, user_id, points=100, days=None, *, months=1):
        user = self.users.get(user_id)
        if not user or user.get("points", 0) < points or (user.get("is_premium") and user.get("premium_source") != "redeem"):
            return False
        user["points"] -= points
        user["is_premium"] = True
        user["premium_source"] = "redeem"
        from database import add_months
        user["premium_expiry"] = (_dt.datetime.now() + _dt.timedelta(days=days) if days is not None
                                  else add_months(_dt.datetime.now(), months))
        return True

    async def reserve_daily(self, user_id, limit=3, now=None):
        allowed, _ = await self.check_daily_limit(user_id, limit)
        if allowed:
            self.users[user_id]["daily_downloads"] += 1
        return allowed

    async def refund_daily(self, user_id, reservation_date):
        self.users[user_id]["daily_downloads"] -= 1

    async def set_qr(self, file_id): self.qr = file_id
    async def get_qr(self): return getattr(self, "qr", None)
    async def delete_qr(self): self.qr = None
    async def add_payment(self, user_id, proof, note=None):
        self.payments = getattr(self, "payments", [])
        self.payments.append({"user_id": user_id, "proof": proof, "note": note})
        return True
    async def get_payments(self): return getattr(self, "payments", [])

    # config ---------------------------------------------------------------
    async def get_maintenance(self):
        return self.maintenance

    async def set_maintenance(self, status):
        self.maintenance = status

    async def get_fsub_channel(self):
        return self.fsub

    async def set_fsub_channel(self, channel):
        self.fsub = channel

    async def delete_fsub(self):
        self.fsub = None

    async def add_download(self, user_id, link, file_type):
        self.downloads.append({"user_id": user_id, "link": link, "type": file_type})

    async def add_bookmark(self, user_id, link, tag=None):
        self.bookmarks.setdefault(user_id, []).append(link)

    async def get_bookmarks(self, user_id):
        return [{"link": link} for link in self.bookmarks.get(user_id, [])]


#: every database symbol main.py imports
DB_NAMES = [
    "add_user", "get_user", "is_premium", "is_banned", "check_daily_limit",
    "increment_daily", "save_session", "get_session", "delete_session",
    "set_caption", "get_caption", "del_caption", "set_thumbnail", "get_thumbnail",
    "del_thumbnail", "set_prefix", "get_prefix", "set_suffix", "get_suffix",
    "add_download", "get_history", "clear_history", "add_bookmark", "get_bookmarks",
    "delete_bookmark", "add_favorite", "get_favorites", "remove_favorite",
    "set_language", "toggle_notifications", "toggle_silent", "reset_settings",
    "add_referral", "add_feedback", "test_connection", "total_users",
    "get_all_users", "get_banned_users_list", "get_premium_users_list", "get_logged_users_list",
    "get_active_users_today", "get_new_users_today", "get_top_users",
    "total_downloads_count", "total_bookmarks_count", "get_all_feedback",
    "search_user", "set_maintenance", "get_maintenance", "set_fsub_channel",
    "get_fsub_channel", "delete_fsub", "add_admin", "remove_admin", "is_admin",
    "get_admins_list", "clear_all_logs", "get_bot_stats", "add_premium",
    "remove_premium", "ban_user", "unban_user", "get_points", "award_referral",
    "redeem_points", "set_qr", "get_qr", "delete_qr", "add_payment", "get_payments",
    "reserve_daily", "refund_daily",
]


def _noop(value=None):
    async def _stub(*args, **kwargs):
        return value
    return _stub


@pytest.fixture
def db(monkeypatch) -> FakeDB:
    """Install the in-memory database on main.py."""
    fake = FakeDB()
    for name in DB_NAMES:
        replacement = getattr(fake, name, None)
        if replacement is None:
            default = {
                "check_daily_limit": (True, 0),
                "get_history": [],
                "get_bookmarks": [],
                "get_favorites": [],
                "get_top_users": [],
                "get_all_feedback": [],
                "daily_downloads": 0,
            }.get(name)
            replacement = _noop(default)
        monkeypatch.setattr(main, name, replacement)
    return fake


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Make sure no test leaks in-memory bot state into the next one."""
    monkeypatch.setattr(main, "user_clients", {})
    monkeypatch.setattr(main, "login_pending", {})
    monkeypatch.setattr(main, "pending_action", {})
    monkeypatch.setattr(main, "admin_pending", {})
    monkeypatch.setattr(main, "active_downloads", {})
    monkeypatch.setattr(main, "payment_pending", {})
    yield


class FakeBot:
    """Stands in for the pyrogram bot client so no test can reach the network."""

    def __init__(self):
        self.sent: list[dict] = []
        self.members: dict = {}

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text})
        return None

    async def send_photo(self, chat_id, photo, **kwargs):
        self.sent.append({"chat_id": chat_id, "photo": photo, **kwargs})

    async def get_chat_member(self, chat_id, user_id):
        from types import SimpleNamespace
        return self.members.get(user_id, SimpleNamespace(status="member"))

    async def download_media(self, *args, **kwargs):
        return None


@pytest.fixture(autouse=True)
def fake_bot(monkeypatch) -> FakeBot:
    bot = FakeBot()
    monkeypatch.setattr(main, "bot", bot)
    return bot


@pytest.fixture
def bot_client():
    """A stand-in for the pyrogram client (handlers never use it directly)."""
    return None


@pytest.fixture
def user():
    return FakeUser()


def make_query(message: FakeMessage, data: str, user_obj: FakeUser | None = None) -> CallbackQuery:
    """Build a real CallbackQuery wired to a fake message."""
    query = CallbackQuery(
        client=None,
        id="query-1",
        from_user=user_obj or message.from_user,
        chat_instance="chat-instance",
        message=message,
        data=data,
    )
    query.answer = RecordingAnswer()
    return query


@pytest.fixture
def press():
    """Press a button (run the router) and return the touched message."""

    async def _press(message: FakeMessage, data: str):
        query = make_query(message, data)
        await main.callback_handler(None, query)
        return query

    return _press
