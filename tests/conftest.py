"""Shared test fixtures.

The bot module reads its credentials from the environment at import time, so we
set harmless dummy values first and then replace every database function with an
in-memory fake — the tests never touch MongoDB or Telegram.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys
from pathlib import Path
from types import SimpleNamespace

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
import engines  # noqa: E402
import telemetry  # noqa: E402
from pyrogram.types import (  # noqa: E402
    CallbackQuery, ChatMember, ChatAdministratorRights, ChatJoiner,
)
from pyrogram.enums import ChatMemberStatus  # noqa: E402
from pyrogram.errors import UserNotParticipant  # noqa: E402


# --------------------------------------------------------------------------- #
#  Fakes
# --------------------------------------------------------------------------- #

class FakeUser:
    def __init__(self, user_id: int = 1001, first_name: str = "Tester", username: str = "tester"):
        self.id = user_id
        self.first_name = first_name
        self.username = username


class FakeChat:
    def __init__(self, chat_id: int = 1001, chat_type: str | None = None, title: str | None = None):
        self.id = chat_id
        self.type = chat_type
        self.title = title or f"chat{chat_id}"


class FakeMessage:
    """Records everything the bot replies / edits with."""

    def __init__(self, text: str = "", user: FakeUser | None = None, message_id: int = 1):
        self.id = message_id
        self.text = text
        self.from_user = user or FakeUser()
        self.chat = FakeChat(self.from_user.id)
        self.caption = None
        self.photo = None
        self.reply_to_message = None
        self.replies: list[dict] = []
        self.edits: list[dict] = []
        self.markups: list = []
        self.captions: list = []
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

    async def edit_caption(self, caption, **kwargs):
        self.captions.append({"caption": caption, **kwargs})
        self.caption = caption
        return self

    @property
    def last_caption(self) -> str:
        assert self.captions, "the bot did not edit the caption"
        return self.captions[-1]["caption"]

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
        self.fsub_items: list[dict] = []
        self.fsub_verify_label = None
        self.join_requests: dict = {}
        self.admins: set[int] = set()
        self.profile_syncs: list[tuple] = []
        self.payments: list[dict] = []
        #: Global engine controller mode (None → config.DEFAULT_ENGINE_MODE).
        self.engine_mode = None
        #: Persisted per-engine extraction counters.
        self.engine_stats: dict[str, int] = {}
        #: chat_id -> files extracted into that dump channel.
        self.channel_files: dict[int, int] = {}
        #: The owner dump channel (one document, like the real config row).
        self.dump_channel: dict | None = None
        #: The single active giveaway and its participant rows.
        self.giveaway: dict | None = None
        self.giveaway_participants: list[dict] = []
        self.indexes: list = []

    # owner dump channel ------------------------------------------------------
    async def set_dump_channel(self, chat_id, title=None, username=None, kind=None):
        self.dump_channel = {"chat_id": int(chat_id), "title": title,
                             "username": username, "kind": kind}
        return True

    async def get_dump_channel(self):
        return dict(self.dump_channel) if self.dump_channel else None

    async def delete_dump_channel(self):
        existed = self.dump_channel is not None
        self.dump_channel = None
        return existed

    # giveaways ---------------------------------------------------------------
    async def ensure_giveaway_indexes(self):
        self.indexes.append("giveaway_participants")
        return True

    async def create_giveaway(self, doc: dict):
        from config import GIVEAWAY_SINGLE_ACTIVE
        if GIVEAWAY_SINGLE_ACTIVE and self.giveaway and self.giveaway.get("status") == "running":
            return False
        payload = dict(doc)
        payload["_id"] = "active"
        payload.setdefault("status", "running")
        payload.setdefault("participant_count", 0)
        self.giveaway = payload
        self.giveaway_participants.clear()
        return True

    async def get_active_giveaway(self):
        if self.giveaway and self.giveaway.get("status") == "running":
            return dict(self.giveaway)
        return None

    async def get_last_giveaway(self):
        return dict(self.giveaway) if self.giveaway else None

    async def update_giveaway(self, updates: dict):
        if not self.giveaway:
            return False
        self.giveaway.update(updates)
        return True

    async def finish_giveaway(self, winner=None, *, status="finished"):
        if not self.giveaway:
            return False
        self.giveaway["status"] = status
        if winner is not None:
            self.giveaway["winner"] = dict(winner)
        return True

    async def add_giveaway_participant(self, giveaway_id, user_id, name=None, username=None):
        if any(row["user_id"] == int(user_id) for row in self.giveaway_participants):
            return False
        self.giveaway_participants.append({
            "giveaway_id": str(giveaway_id), "user_id": int(user_id),
            "name": name, "username": username, "joined_at": _dt.datetime.now(),
        })
        if self.giveaway:
            self.giveaway["participant_count"] = len(self.giveaway_participants)
        return True

    async def count_giveaway_participants(self, giveaway_id):
        return len([row for row in self.giveaway_participants
                    if row["giveaway_id"] == str(giveaway_id)])

    async def is_giveaway_participant(self, giveaway_id, user_id):
        return any(row["giveaway_id"] == str(giveaway_id) and row["user_id"] == int(user_id)
                   for row in self.giveaway_participants)

    async def list_giveaway_participants(self, giveaway_id, skip: int = 0, limit: int = 10):
        rows = [row for row in self.giveaway_participants
                if row["giveaway_id"] == str(giveaway_id)]
        return rows[int(skip):int(skip) + int(limit)]

    async def all_giveaway_participants(self, giveaway_id):
        return [row for row in self.giveaway_participants
                if row["giveaway_id"] == str(giveaway_id)]

    async def clear_giveaway_participants(self, giveaway_id):
        before = len(self.giveaway_participants)
        self.giveaway_participants = [row for row in self.giveaway_participants
                                      if row["giveaway_id"] != str(giveaway_id)]
        return before - len(self.giveaway_participants)

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
            "has_private_access": False,
            "has_models_access": False,
            "engine_preference": None,
            "premium_tier": None,
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

    async def sync_user_profile(self, user_id, name=None, username=None):
        """Mirror of database.sync_user_profile — records every change."""
        user = self.users.get(user_id)
        if not user:
            return False
        changed = False
        if name and name != user.get("name"):
            user["name"] = name
            changed = True
        if username is not None and username != user.get("username"):
            user["username"] = username
            changed = True
        self.profile_syncs.append((user_id, name, username))
        return changed

    async def get_display_name(self, user_id, fallback="User"):
        return (self.users.get(user_id) or {}).get("name") or fallback

    async def add_premium(self, user_id, days=30, source="manual", *, tier=None,
                          has_private_access=None, has_models_access=None,
                          premium_expiry=None):
        """Mirror of database.add_premium — tier decides flags *and* source."""
        from config import GRANT_TIERS
        user = self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))
        definition = GRANT_TIERS.get(str(tier or "").strip().lower()) if tier else None
        if definition:
            source = definition.get("source", source)
            if has_private_access is None:
                has_private_access = definition["has_private_access"]
            if has_models_access is None:
                has_models_access = definition["has_models_access"]
            user["premium_tier"] = str(tier).strip().lower()
        user["is_premium"] = True
        user["premium_source"] = source
        if premium_expiry is not None:
            user["premium_expiry"] = premium_expiry
        elif days is not None:
            user["premium_expiry"] = _dt.datetime.now() + _dt.timedelta(days=int(days))
        else:
            user["premium_expiry"] = None        # lifetime
        if has_private_access is not None:
            user["has_private_access"] = bool(has_private_access)
        if has_models_access is not None:
            user["has_models_access"] = bool(has_models_access)
        return user

    async def remove_premium(self, user_id):
        user = self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))
        user["is_premium"] = False
        user["premium_expiry"] = None
        user["premium_source"] = None
        user["has_private_access"] = False
        user["has_models_access"] = False
        user["premium_tier"] = None

    async def get_premium_tier(self, user_id):
        return (self.users.get(user_id) or {}).get("premium_tier")

    # granular feature flags -------------------------------------------------
    async def has_private_access(self, user_id):
        return bool((self.users.get(user_id) or {}).get("has_private_access"))

    async def has_models_access(self, user_id):
        user = self.users.get(user_id) or {}
        if not user.get("has_models_access"):
            return False
        expiry = user.get("premium_expiry")
        return not (expiry and expiry < _dt.datetime.now())

    async def set_models_access(self, user_id, enabled):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))[
            "has_models_access"] = bool(enabled)

    async def set_private_access(self, user_id, enabled):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))[
            "has_private_access"] = bool(enabled)

    # engines ----------------------------------------------------------------
    async def set_user_engine(self, user_id, engine):
        from engines import normalize_engine
        value = normalize_engine(engine)
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))[
            "engine_preference"] = value
        return value

    async def get_user_engine(self, user_id):
        return (self.users.get(user_id) or {}).get("engine_preference") or None

    async def get_engine_preference(self, user_id):
        return await self.get_user_engine(user_id)

    async def set_engine_mode(self, mode):
        from engines import normalize_mode
        self.engine_mode = normalize_mode(mode)
        return self.engine_mode

    async def get_engine_mode(self):
        from config import DEFAULT_ENGINE_MODE
        return self.engine_mode or DEFAULT_ENGINE_MODE

    async def record_engine_use(self, engine, count=1):
        from engines import normalize_engine
        key = normalize_engine(engine)
        self.engine_stats[key] = self.engine_stats.get(key, 0) + int(count)

    async def get_engine_stats(self):
        from config import ENGINES
        return {engine: int(self.engine_stats.get(engine, 0)) for engine in ENGINES}

    # per-channel counters (/mychannels) -------------------------------------
    async def increment_channel_files(self, chat_id, count=1):
        self.channel_files[int(chat_id)] = self.channel_files.get(int(chat_id), 0) + int(count)

    async def get_channel_files(self, chat_id):
        return int(self.channel_files.get(int(chat_id), 0))

    async def set_channel_files(self, chat_id, count):
        self.channel_files[int(chat_id)] = int(count)

    async def get_bot_stats(self):
        users = list(self.users.values())
        return {
            "total": len(users),
            "active_today": 0,
            "new_today": 0,
            "premium": sum(1 for u in users if u.get("is_premium")),
            "banned": sum(1 for u in users if u.get("is_banned")),
            "admins": len(self.admins),
            "total_downloads": sum(int(u.get("downloads", 0)) for u in users),
            "models_access": sum(1 for u in users if u.get("has_models_access")),
            "private_access": sum(1 for u in users if u.get("has_private_access")),
        }

    async def ban_user(self, user_id):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))["is_banned"] = True

    async def unban_user(self, user_id):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))["is_banned"] = False

    # channel dump (/setchat) — up to config.MAX_USER_CHANNELS per user --------
    #: The fake stores documents in the *real* shape and normalizes them through
    #: the real pure helpers in database.py, so the on-read migration of legacy
    #: single-channel documents is exercised by the tests rather than faked.
    async def set_user_chat(self, user_id, chat_id, title=None, username=None):
        return await self.add_user_channel(user_id, chat_id, title, username)

    async def add_user_channel(self, user_id, chat_id, title=None, username=None,
                               chat_type=None):
        import database as _database
        user = self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))
        entries = _database.channels_from_document(user)
        chat_id = int(chat_id)
        for entry in entries:
            if entry["chat_id"] == chat_id:
                entry["title"] = title or entry["title"]
                entry["username"] = username if username is not None else entry["username"]
                entry["type"] = chat_type or entry["type"]
                reason = "updated"
                break
        else:
            if len(entries) >= max(1, int(_database.MAX_USER_CHANNELS)):
                return False, "full"
            entries.append({"chat_id": chat_id, "title": title or str(chat_id),
                            "username": username, "type": chat_type or "channel"})
            reason = "added"
        first = entries[0]
        user.update({
            "channels": entries,
            # Mirror of the primary channel: legacy readers keep working.
            "channel_chat_id": first["chat_id"], "channel_title": first["title"],
            "channel_username": first["username"], "channel_type": first["type"],
        })
        return True, reason

    async def get_user_channels(self, user_id):
        import database as _database
        return _database.channels_from_document(self.users.get(user_id) or {})

    async def remove_user_channel(self, user_id, chat_id):
        import database as _database
        user = self.users.get(user_id)
        if not user:
            return False
        entries = _database.channels_from_document(user)
        wanted = int(chat_id) if chat_id is not None else None
        remaining = [e for e in entries if e["chat_id"] != wanted]
        if len(remaining) == len(entries):
            return False
        first = remaining[0] if remaining else None
        user.update({
            "channels": remaining,
            "channel_chat_id": first["chat_id"] if first else None,
            "channel_title": first["title"] if first else None,
            "channel_username": first["username"] if first else None,
            "channel_type": first["type"] if first else None,
        })
        return True

    async def get_user_chat(self, user_id):
        """The **primary** channel, byte-compatible with the single-channel era."""
        entries = await self.get_user_channels(user_id)
        if not entries:
            return None
        first = entries[0]
        return {
            "chat_id": first["chat_id"],
            "title": first["title"] or str(first["chat_id"]),
            "username": first["username"],
        }

    async def find_user_chat_owner(self, chat_id):
        import database as _database
        wanted = int(chat_id)
        for user in self.users.values():
            if _database.pick_channel_entry(user, wanted):
                return user
        return None

    async def clear_user_chat(self, user_id):
        user = self.users.get(user_id)
        if user:
            user.update({"channels": [], "channel_chat_id": None, "channel_title": None,
                         "channel_username": None, "channel_type": None})

    # payments ----------------------------------------------------------------
    async def mark_payment(self, user_id, status, reviewer=None, plan=None):
        for row in reversed(self.payments):
            if row.get("user_id") == user_id and row.get("status", "pending_review") == "pending_review":
                row["status"] = status
                row["reviewed_by"] = reviewer
                if plan:
                    row["approved_plan"] = plan
                return row
        return None

    async def get_user(self, user_id):
        return self.users.get(user_id)

    async def update_user(self, user_id, data):
        if user_id in self.users:
            self.users[user_id].update(data)

    async def is_premium(self, user_id):
        user = self.users.get(user_id)
        return bool(user and user.get("is_premium"))

    async def is_banned(self, user_id):
        user = self.users.get(user_id)
        return bool(user and user.get("is_banned"))

    async def is_admin(self, user_id):
        return user_id in self.admins

    async def get_admins_list(self):
        return [{"user_id": uid, "name": f"Admin {uid}"} for uid in sorted(self.admins)]

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

    async def del_caption(self, user_id):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))["caption"] = None

    async def get_caption(self, user_id):
        return (self.users.get(user_id) or {}).get("caption")

    async def set_prefix(self, user_id, prefix):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))["prefix"] = prefix

    async def get_prefix(self, user_id):
        return (self.users.get(user_id) or {}).get("prefix")

    async def set_suffix(self, user_id, suffix):
        self.users.setdefault(user_id, self._new_user(user_id, "Tester", None))["suffix"] = suffix

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

    def utcnow(self):
        return _dt.datetime.utcnow()

    async def set_qr(self, file_id): self.qr = file_id
    async def get_qr(self): return getattr(self, "qr", None)
    async def delete_qr(self): self.qr = None
    async def add_payment(self, user_id, proof, note=None):
        self.payments.append({"user_id": user_id, "proof": proof, "note": note,
                              "status": "pending_review"})
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
        return 0

    # force-sub list (mirror of database.get_fsub_list and friends) --------
    async def get_fsub_list(self):
        return [dict(item) for item in self.fsub_items]

    async def add_fsub_item(self, item):
        entry = {
            "chat_id": int(item.get("chat_id") or 0),
            "title": (item.get("title") or "").strip() or f"Chat {item.get('chat_id')}",
            "username": (item.get("username") or "").strip().lstrip("@") or None,
            "invite_link": (item.get("invite_link") or "").strip() or None,
            "button_text": (item.get("button_text") or "").strip()
                           or f"✅ Join {item.get('title') or 'Chat'}",
            "kind": "group" if str(item.get("kind") or "").lower().startswith("group") else "channel",
            "auto_approve": bool(item.get("auto_approve")),
            "order": len(self.fsub_items),
        }
        self.fsub_items.append(entry)
        return len(self.fsub_items)

    async def remove_fsub_item(self, number):
        index = int(number) - 1
        if not 0 <= index < len(self.fsub_items):
            return None
        removed = self.fsub_items.pop(index)
        for position, entry in enumerate(self.fsub_items):
            entry["order"] = position
        return removed

    async def update_fsub_item(self, number, **fields):
        index = int(number) - 1
        if not 0 <= index < len(self.fsub_items):
            return False
        allowed = {"chat_id", "title", "username", "invite_link",
                   "button_text", "kind", "auto_approve", "order"}
        self.fsub_items[index].update({k: v for k, v in fields.items() if k in allowed})
        return True

    async def clear_fsub_list(self):
        count = len(self.fsub_items)
        self.fsub_items = []
        return count

    async def get_fsub_verify_label(self):
        return self.fsub_verify_label

    async def set_fsub_verify_label(self, label):
        self.fsub_verify_label = (label or "").strip() or None

    # join requests ---------------------------------------------------------
    async def record_join_request(self, chat_id, user_id, date=None, status="pending"):
        self.join_requests[(int(chat_id), int(user_id))] = {
            "chat_id": int(chat_id), "user_id": int(user_id), "status": status,
        }

    async def set_join_request_status(self, chat_id, user_id, status):
        row = self.join_requests.setdefault(
            (int(chat_id), int(user_id)), {"chat_id": int(chat_id), "user_id": int(user_id)})
        row["status"] = status

    async def get_join_request(self, chat_id, user_id):
        return self.join_requests.get((int(chat_id), int(user_id)))

    async def add_download(self, user_id, link, file_type):
        self.downloads.append({"user_id": user_id, "link": link, "type": file_type})

    async def add_bookmark(self, user_id, link, tag=None):
        self.bookmarks.setdefault(user_id, []).append(link)

    async def get_bookmarks(self, user_id):
        return [{"link": link} for link in self.bookmarks.get(user_id, [])]


#: every database symbol main.py imports
DB_NAMES = [
    "add_user", "get_user", "update_user", "is_premium", "is_banned", "check_daily_limit",
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
    "get_fsub_channel", "delete_fsub", "get_fsub_list", "add_fsub_item",
    "remove_fsub_item", "update_fsub_item", "clear_fsub_list",
    "get_fsub_verify_label", "set_fsub_verify_label", "record_join_request",
    "set_join_request_status", "get_join_request",
    "add_admin", "remove_admin", "is_admin",
    "get_admins_list", "clear_all_logs", "get_bot_stats", "add_premium",
    "remove_premium", "ban_user", "unban_user", "get_points", "award_referral",
    "redeem_points", "set_qr", "get_qr", "delete_qr", "add_payment", "get_payments",
    "reserve_daily", "refund_daily", "utcnow", "sync_user_profile", "get_display_name",
    "set_user_chat", "get_user_chat", "find_user_chat_owner", "clear_user_chat", "mark_payment",
    # Round 4: two dump channels per user, migrated on read.
    "get_user_channels", "add_user_channel", "remove_user_channel",
    # Dual engines, granular VIP flags and the /mychannels counters.
    "set_engine_mode", "get_engine_mode", "set_user_engine", "get_user_engine",
    "get_engine_preference", "has_models_access", "has_private_access",
    "set_models_access", "set_private_access", "record_engine_use", "get_engine_stats",
    "get_premium_tier", "increment_channel_files", "get_channel_files",
    # Round 12: the owner dump channel and the giveaway engine.
    "set_dump_channel", "get_dump_channel", "delete_dump_channel",
    "create_giveaway", "get_active_giveaway", "get_last_giveaway", "update_giveaway",
    "finish_giveaway", "add_giveaway_participant", "count_giveaway_participants",
    "is_giveaway_participant", "list_giveaway_participants",
    "all_giveaway_participants", "clear_giveaway_participants",
    "ensure_giveaway_indexes",
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


class FakeHost:
    """Deterministic CPU / RAM / ping readings for the telemetry tests.

    The probes return fixed values, so no test ever reads ``/proc`` or opens a
    socket — the HUD still renders exactly what a real host would produce.
    """

    def __init__(self, cpu_percent: float = 19.2, memory_percent: float = 41.8,
                 ping_ms: float = 11.0):
        self.cpu_percent = cpu_percent
        self.memory_percent = memory_percent
        self.ping_ms = ping_ms
        self.cpu_calls = 0
        self.ping_calls = 0

    def cpu(self):
        """``(idle, total)`` deltas that encode exactly ``cpu_percent`` busy."""
        self.cpu_calls += 1
        total = 1000.0 * self.cpu_calls
        return total * (1.0 - self.cpu_percent / 100.0), total

    def memory(self):
        return self.memory_percent

    async def ping(self, host=None, port=None):
        self.ping_calls += 1
        return self.ping_ms


@pytest.fixture
def fake_host(monkeypatch) -> FakeHost:
    """Install the deterministic host probes on the bot's telemetry monitor."""
    host = FakeHost()
    monkeypatch.setattr(main, "HOST_MONITOR", telemetry.HostMonitor(
        cpu_probe=host.cpu, memory_probe=host.memory, ping_probe=host.ping,
        sample_ttl=0.0, ping_ttl=0.0))
    return host


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Make sure no test leaks in-memory bot state into the next one."""
    monkeypatch.setattr(main, "PROFILE_REFRESH_TASKS", {})
    monkeypatch.setattr(main, "BACKGROUND_TASKS", set())
    monkeypatch.setattr(main, "CAMPAIGN_LOCK", asyncio.Lock())
    monkeypatch.setattr(main, "BROADCAST_PAUSED_UNTIL", 0.0)
    monkeypatch.setattr(main, "COMMAND_REGISTRATION_TASK", None)
    monkeypatch.setattr(main, "user_clients", {})
    monkeypatch.setattr(main, "login_pending", {})
    monkeypatch.setattr(main, "pending_action", {})
    monkeypatch.setattr(main, "admin_pending", {})
    monkeypatch.setattr(main, "active_downloads", {})
    monkeypatch.setattr(main, "payment_pending", {})
    monkeypatch.setattr(main, "premium_tier_pending", {})
    monkeypatch.setattr(main, "setchat_pending", {})
    monkeypatch.setattr(main, "fsub_pending", {})
    monkeypatch.setattr(main, "channel_locks", {})
    monkeypatch.setattr(main, "channel_last_request", {})
    #: Round 12 state: share tokens, the button wizard, the giveaway wizard, the
    #: dump mirror and the background pump must be born fresh in every test.
    monkeypatch.setattr(main, "SHARE_TOKENS", {})
    monkeypatch.setattr(main, "BUTTON_WIZARD", {})
    monkeypatch.setattr(main, "BUTTON_DRAFT", {})
    monkeypatch.setattr(main, "GIVEAWAY_WIZARD", {})
    monkeypatch.setattr(main, "DUMP_MIRROR", main.DumpMirror())
    monkeypatch.setattr(main, "GIVEAWAY_TASK", None)
    monkeypatch.setattr(main, "GIVEAWAY_INDEXES_READY", False)
    #: Round 14 state: the echo guard for a native copy made with the user's
    #: own session, and the giveaway DM fan-out, must both be born fresh.
    monkeypatch.setattr(main, "ECHO_GUARD", {})
    monkeypatch.setattr(main, "GIVEAWAY_BROADCAST_TASK", None)
    #: Round 15 state: the chats that show a picker reply keyboard and the users
    #: already swept for a keyboard an older build left behind.
    monkeypatch.setattr(main, "PICKER_KEYBOARD_SHOWN", set())
    monkeypatch.setattr(main, "PICKER_SWEPT", set())
    # A fresh engine controller per test: the mode, the autoscaler counters and
    # the analytics must never leak from one test into the next.  The provider is
    # re-wired so it still reads whatever the FakeDB fixture installs.
    monkeypatch.setattr(main, "ENGINE_CONTROLLER",
                        engines.EngineController(mode_provider=main._stored_engine_mode))
    # Telemetry defaults to the deterministic fake host (no /proc, no sockets).
    host = FakeHost()
    monkeypatch.setattr(main, "HOST_MONITOR", telemetry.HostMonitor(
        cpu_probe=host.cpu, memory_probe=host.memory, ping_probe=host.ping,
        sample_ttl=0.0, ping_ttl=0.0))
    yield


@pytest.fixture
def staged_campaigns(monkeypatch):
    """Opt in to staging the owner's campaigns through the dump channel.

    The default is direct delivery (``config.DUMP_STAGE_CAMPAIGNS`` is off): the
    dump only carries users' downloads and messages.  The staging code is still
    there behind the switch, and the tests that cover it ask for this fixture.
    """
    monkeypatch.setattr(main, "DUMP_STAGE_CAMPAIGNS", True)


#: The bot's own user id inside FakeBot (used by every admin check).
FAKE_BOT_ID = 999
#: The user id every FakeUser() defaults to — see ``FakeUser.__init__``.
DEFAULT_USER_ID = 1001
#: Raw channel id FakeBot reports for a private invite link.
FAKE_RAW_CHANNEL_ID = 4242
#: High-level id of that private channel (what the bot stores and checks).
FAKE_PRIVATE_CHAT_ID = -1000000000000 - FAKE_RAW_CHANNEL_ID

_UNSET = object()


def make_member(status=ChatMemberStatus.MEMBER, *, can_post_messages=None,
                can_delete_messages=None, privileges=_UNSET, user=None):
    """A **real** :class:`pyrogram.types.ChatMember`.

    ``can_post_messages`` deliberately lives in ``privileges``
    (:class:`pyrogram.types.ChatAdministratorRights`) — the very place Kurigram
    parses it into — because ``ChatMember`` has no such attribute at all.
    Pass ``privileges=None`` for the chats where Telegram reports no rights.
    """
    if privileges is _UNSET:
        privileges = ChatAdministratorRights(
            can_post_messages=bool(can_post_messages),
            can_delete_messages=bool(can_delete_messages), can_manage_chat=True,
        ) if (can_post_messages is not None or can_delete_messages is not None
              or status == ChatMemberStatus.ADMINISTRATOR) else None
    return ChatMember(status=status, user=user, privileges=privileges)


def make_joiner(user_id, *, pending=True):
    """A **real** :class:`pyrogram.types.ChatJoiner` for the approve list."""
    return ChatJoiner(client=None, user=SimpleNamespace(id=user_id), date=None, bio=None,
                      pending=pending)


class FakeBot:
    """Stands in for the pyrogram bot client so no test can reach the network."""

    def __init__(self):
        self.sent: list[dict] = []
        #: user_id or (chat_id, user_id) -> real ChatMember
        self.members: dict = {}
        #: (chat_id, user_id) pairs that must raise UserNotParticipant
        self.not_members: set = set()
        self.messages: dict = {}
        self.chats: dict = {}
        self.channel_id = -100777
        self.me = SimpleNamespace(id=FAKE_BOT_ID, is_self=True, username="TestRestrictBot")
        #: invite hash -> "already" | "join" | "approval" | "expired" | "invalid"
        self.invites: dict = {}
        #: chat_id -> list of ChatJoiner (the approve list)
        self.join_requests: dict = {}
        self.approved: list = []
        self.declined: list = []
        self.joined_chats: list = []
        self.invoked: list = []
        #: Round 12 bookkeeping: mirror copies, deletes, pins and edits.
        self.copies: list = []
        self.deleted: list = []
        self.pinned: list = []
        self.unpinned: list = []
        self.registered_commands = []
        self.command_scopes = []
        #: Every ``set_bot_commands`` call as ``(scope, [BotCommand, ...])``, so a
        #: test can read the menu of each scope (all private chats, one chat).
        self.command_registry: list = []
        #: Scopes whose list was deleted with ``delete_bot_commands(scope=...)``.
        self.deleted_command_scopes: list = []
        self.edited: list = []

    async def delete_bot_commands(self, **kwargs):
        self.registered_commands.clear()
        self.deleted_command_scopes.append(kwargs.get("scope"))

    async def set_bot_commands(self, commands, **kwargs):
        self.registered_commands = commands
        self.command_scopes.append(kwargs.get("scope"))
        self.command_registry.append((kwargs.get("scope"), list(commands)))

    def menu_for(self, scope_name, chat_id=None):
        """The command names last published for a scope (``None`` if never set).

        ``scope_name`` is the class name, e.g. ``"BotCommandScopeAllPrivateChats"``
        or ``"BotCommandScopeChat"`` (then pass the ``chat_id``).
        """
        found = None
        for scope, commands in self.command_registry:
            if scope.__class__.__name__ != scope_name:
                continue
            if chat_id is not None and getattr(scope, "chat_id", None) != chat_id:
                continue
            found = commands
        return found

    async def send_message(self, chat_id, text, **kwargs):
        msg = FakeMessage(text=text, message_id=len(self.sent) + 1000)
        msg.chat = FakeChat(chat_id)
        if "reply_markup" in kwargs:
            msg.markups.append(kwargs["reply_markup"])
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return msg

    async def send_photo(self, chat_id, photo, **kwargs):
        self.sent.append({"chat_id": chat_id, "photo": photo, **kwargs})

    async def get_chat_member(self, chat_id, user_id):
        if (int(chat_id), user_id) in self.not_members:
            raise UserNotParticipant()
        if (chat_id, user_id) in self.members:
            return self.members[(chat_id, user_id)]
        return self.members.get(user_id, make_member())

    async def get_me(self):
        return SimpleNamespace(id=FAKE_BOT_ID, username="TestRestrictBot", is_self=True)

    # ---- round 12: copy / pin / delete / edit ------------------------------ #
    #: These verbs are what the dump mirror, /pin and the giveaway poster use.
    #: They are separate from ``send_message`` so a test can assert exactly
    #: which of them ran.
    async def copy_message(self, chat_id, from_chat_id, message_id, **kwargs):
        copy = FakeMessage(text=f"copy:{from_chat_id}:{message_id}",
                           message_id=len(self.sent) + 5000)
        copy.chat = FakeChat(chat_id, chat_type="channel")
        self.sent.append({"chat_id": chat_id, "copy_from": from_chat_id,
                          "message_id": message_id, **kwargs})
        self.copies.append((chat_id, from_chat_id, int(message_id)))
        return copy

    async def delete_messages(self, chat_id, message_ids):
        if isinstance(message_ids, (list, tuple, set)):
            for message_id in message_ids:
                self.deleted.append((chat_id, int(message_id)))
        else:
            self.deleted.append((chat_id, int(message_ids)))
        return True

    async def pin_chat_message(self, chat_id, message_id, **kwargs):
        self.pinned.append((chat_id, int(message_id)))
        return True

    async def unpin_chat_message(self, chat_id, message_id=None, **kwargs):
        self.unpinned.append((chat_id, message_id))
        return True

    async def edit_message_text(self, chat_id, message_id, text, **kwargs):
        self.edited.append((chat_id, int(message_id), text))
        edited = FakeMessage(text=text, message_id=int(message_id))
        edited.chat = FakeChat(chat_id, chat_type="channel")
        return edited

    async def get_chat(self, chat_id):
        from types import SimpleNamespace
        if chat_id in self.chats:
            return self.chats[chat_id]
        if isinstance(chat_id, int):
            return SimpleNamespace(id=chat_id, title=f"chat{chat_id}", username=None,
                                   type="channel")
        handle = str(chat_id).rstrip("/").split("/")[-1].lstrip("@") or "channel"
        return SimpleNamespace(id=self.channel_id, title=handle, username=handle,
                               type="channel")

    async def get_messages(self, chat_id, message_ids):
        """Mirror Kurigram: one id returns a message, a list returns a list.

        A list answer keeps the requested order and puts ``None`` where the
        message does not exist, which is exactly what the range pre-flight
        relies on to tell "missing" from "unreadable".
        """
        if isinstance(message_ids, (list, tuple, set, range)):
            return [self.messages.get(int(mid)) for mid in message_ids]
        return self.messages.get(message_ids)

    async def download_media(self, *args, **kwargs):
        return None

    # private invite links ---------------------------------------------------
    async def invoke(self, query, *args, **kwargs):
        """Answer ``messages.CheckChatInvite`` from the ``invites`` mapping."""
        from pyrogram import raw
        from pyrogram.errors import (InviteRequestSent, InviteHashExpired,
                                     InviteHashInvalid)
        self.invoked.append(query)
        if not isinstance(query, raw.functions.messages.CheckChatInvite):
            raise AssertionError(f"unexpected raw call: {query!r}")
        behaviour = self.invites.get(query.hash, "expired")
        if behaviour == "expired":
            raise InviteHashExpired()
        if behaviour == "invalid":
            raise InviteHashInvalid()
        if behaviour == "approval":
            raise InviteRequestSent()
        if behaviour == "join":
            return raw.types.ChatInvite(
                title="Private Channel", photo=raw.types.ChatPhoto(photo_id=1, dc_id=2),
                participants_count=1, color=0, channel=True, request_needed=False,
            )
        return raw.types.ChatInviteAlready(chat=raw.types.Channel(
            id=FAKE_RAW_CHANNEL_ID, title="Private Channel",
            photo=raw.types.ChatPhoto(photo_id=1, dc_id=2), date=1,
            access_hash=1, username=None,
        ))

    async def join_chat(self, chat_id):
        from types import SimpleNamespace
        from pyrogram.errors import UserAlreadyParticipant
        self.joined_chats.append(chat_id)
        invite_hash = str(chat_id).rstrip("/").split("/")[-1].lstrip("+")
        if self.invites.get(invite_hash) == "approval":
            raise UserAlreadyParticipant()
        return SimpleNamespace(id=FAKE_PRIVATE_CHAT_ID, title="Private Channel",
                               username=None, type="channel")

    async def export_chat_invite_link(self, chat_id):
        return SimpleNamespace(invite_link=f"https://t.me/+export{chat_id}")

    async def resolve_peer(self, chat_id):
        return f"peer:{chat_id}"

    # join requests ----------------------------------------------------------
    async def get_chat_join_requests(self, chat_id, limit=0, query=""):
        for joiner in list(self.join_requests.get(chat_id, [])):
            yield joiner

    async def approve_chat_join_request(self, chat_id, user_id):
        self.approved.append((chat_id, user_id))
        return True

    async def decline_chat_join_request(self, chat_id, user_id):
        self.declined.append((chat_id, user_id))
        return True


@pytest.fixture(autouse=True)
def fake_bot(monkeypatch) -> FakeBot:
    bot = FakeBot()
    #: Round 5 verifies the **person** adding a channel before it verifies the
    #: bot, so the default test user is an administrator by default.  A test
    #: that needs a plain member, a non-member or an error overrides this
    #: explicitly (``bot.members[...]`` / ``bot.not_members``).  The bot's own
    #: membership (id 999) is deliberately left at the plain-member default, so
    #: every existing "make the bot an admin" test still has to say so.
    bot.members[DEFAULT_USER_ID] = make_member(ChatMemberStatus.ADMINISTRATOR,
                                               can_post_messages=True)
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


def sc(text):
    """Render *text* the way the bot does (Unicode small caps)."""
    import ui as _ui
    return _ui.smallcaps(text)


@pytest.fixture
def press():
    """Press a button (run the router) and return the touched message."""

    async def _press(message: FakeMessage, data: str):
        query = make_query(message, data)
        await main.callback_handler(None, query)
        return query

    return _press


async def drain_background():
    """Wait for finite command jobs, not TTL/giveaway schedulers."""
    while main.BACKGROUND_TASKS:
        await asyncio.gather(*list(main.BACKGROUND_TASKS))
