import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import calendar
from pymongo.errors import DuplicateKeyError
from config import (FREE_DAILY_LIMIT, MAX_USER_CHANNELS, REDEEM_PREMIUM_MONTHS,
                    PREMIUM_SOURCE_MANUAL, PREMIUM_SOURCE_REDEEM,
                    DEFAULT_ENGINE_MODE, ENGINE_PYTHON, ENGINES, GRANT_TIERS,
                    GIVEAWAY_SINGLE_ACTIVE)

MONGO_URL = os.environ.get("MONGO_URL")

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["restricted_bot"]

users_col = db["users"]
downloads_col = db["downloads"]
bookmarks_col = db["bookmarks"]
feedback_col = db["feedback"]
config_col = db["config"]
created_bots_col = db["created_bots"]  # /CreateBot feature
stars_payments_col = db["stars_payments"]  # Telegram Stars payments


#: User-document flag: "no picker reply keyboard from an older build can still be
#: on this user's screen".  New users are born with it set; for everybody else
#: the bot clears the keyboard once and sets it (see ``main.sweep_stale_picker_keyboard``).
PICKER_SWEEP_FIELD = "reply_keyboard_cleared"


def utcnow():
    """Naive UTC clock — the free daily quota resets at midnight UTC.

    Keeping the counters on UTC makes the user facing "resets at 00:00 UTC"
    wording in ``ui.daily_limit_text`` literally true.
    """
    return datetime.utcnow()


async def add_user(user_id, name, username=None):
    existing = await users_col.find_one({"user_id": user_id})
    if not existing:
        user_data = {
            "_id": user_id,
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
            "last_download_date": None,
            "joined_date": datetime.now(),
            "last_active": datetime.now(),
            "referred_by": None,
            "referral_count": 0,
            "points": 0,
            "premium_source": None,
            # Granular VIP flags (/addpremium tiers) — see config.GRANT_TIERS.
            "has_private_access": False,
            "has_models_access": False,
            # Engine the user picked in /models (models holders only).
            "engine_preference": None,
            "notifications": True,
            "silent_mode": False,
            "favorites": [],
            # Channel dump (/setchat): up to config.MAX_USER_CHANNELS channels.
            # ``channels`` is the source of truth; the three scalars below are a
            # mirror of its first entry so pre-round-4 readers keep working.
            "channels": [],
            "channel_chat_id": None,
            "channel_title": None,
            "channel_username": None,
            "channel_type": None,
            # A brand-new chat can never carry a leftover picker keyboard.
            PICKER_SWEEP_FIELD: True,
        }
        try:
            await users_col.insert_one(user_data)
        except DuplicateKeyError:
            return False
        return True
    return False


async def get_user(user_id):
    return await users_col.find_one({"user_id": user_id})


async def update_user(user_id, data):
    await users_col.update_one({"user_id": user_id}, {"$set": data})


async def total_users():
    return await users_col.count_documents({})


async def get_all_users():
    users = []
    async for user in users_col.find({}):
        users.append(user)
    return users


async def get_all_users_list():
    return await get_all_users()


async def get_banned_users_list():
    users = []
    async for user in users_col.find({"is_banned": True}):
        users.append(user)
    return users


async def get_premium_users_list():
    users = []
    async for user in users_col.find({"is_premium": True}):
        users.append(user)
    return users


async def get_logged_users_list():
    users = []
    # ``$nin`` is the correct filter here: a duplicated ``$ne`` key would be
    # silently collapsed by Python, dropping one of the two checks.
    async for user in users_col.find({"session_string": {"$exists": True, "$nin": [None, ""]}}):
        users.append(user)
    return users


async def is_premium(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if not user or not user.get("is_premium"):
        return False
    expiry = user.get("premium_expiry")
    if expiry and expiry < datetime.now():
        # Expiry revokes the granular feature flags too, so an expired grant
        # can never keep private-channel or C++ Turbo access alive.
        await users_col.update_one(
            {"user_id": user_id, "premium_expiry": expiry},
            {"$set": {"is_premium": False, "premium_expiry": None,
                      "has_private_access": False, "has_models_access": False,
                      "premium_tier": None}}
        )
        return False
    return True


async def add_premium(user_id, days=30, source=PREMIUM_SOURCE_MANUAL, *, tier=None,
                      has_private_access=None, has_models_access=None,
                      premium_expiry=None):
    """Grant premium plus the granular feature flags of a tier.

    ``tier`` is a key of ``config.GRANT_TIERS`` (``public`` / ``models`` /
    ``private`` / ``all``): it fills in the flags *and* the matching
    ``premium_source`` so a models-only grant can never inherit the legacy
    "manual means private" meaning.

    ``days=None`` means **lifetime**: no expiry is stored, and :func:`is_premium`
    treats a missing expiry as "still valid".  The explicit
    ``has_private_access`` / ``has_models_access`` arguments default to ``None``
    = *leave the stored flag alone*, so renewing one feature never silently
    downgrades the other.  Returns the updates that were written.
    """
    definition = GRANT_TIERS.get(str(tier or "").strip().lower()) if tier else None
    if definition:
        source = definition.get("source", source)
        if has_private_access is None:
            has_private_access = definition["has_private_access"]
        if has_models_access is None:
            has_models_access = definition["has_models_access"]
    updates = {"is_premium": True, "premium_source": source}
    if premium_expiry is not None:
        updates["premium_expiry"] = premium_expiry
    elif days is not None:
        updates["premium_expiry"] = datetime.now() + timedelta(days=int(days))
    else:
        updates["premium_expiry"] = None          # lifetime — no expiry
    if has_private_access is not None:
        updates["has_private_access"] = bool(has_private_access)
    if has_models_access is not None:
        updates["has_models_access"] = bool(has_models_access)
    if definition:
        updates["premium_tier"] = str(tier).strip().lower()
    await users_col.update_one({"user_id": user_id}, {"$set": updates})
    return updates


async def get_premium_tier(user_id):
    """The granular tier key stored by the last :func:`add_premium` call."""
    return (await get_user(user_id) or {}).get("premium_tier")


async def remove_premium(user_id):
    """Revoke VIP: premium, both feature flags, the tier and the expiry."""
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": False, "premium_expiry": None, "premium_source": None,
                  "has_private_access": False, "has_models_access": False,
                  "premium_tier": None}},
    )


async def has_private_access(user_id):
    """True when the ``has_private_access`` flag is set on a live premium."""
    user = await users_col.find_one({"user_id": user_id})
    return bool(user and user.get("has_private_access"))


async def has_models_access(user_id):
    """True when the user may switch to the C++ Turbo engine (/models).

    The permission is only meaningful while premium is active, so an expired
    grant stops advertising the switcher immediately.
    """
    user = await users_col.find_one({"user_id": user_id})
    if not user or not user.get("has_models_access"):
        return False
    expiry = user.get("premium_expiry")
    if expiry and expiry < datetime.now():
        return False
    return True


async def set_models_access(user_id, enabled: bool):
    await users_col.update_one({"user_id": user_id},
                               {"$set": {"has_models_access": bool(enabled)}})


async def set_private_access(user_id, enabled: bool):
    await users_col.update_one({"user_id": user_id},
                               {"$set": {"has_private_access": bool(enabled)}})


# --------------------------------------------------------------------------- #
#  Engine preference (per user) and engine mode (global)
# --------------------------------------------------------------------------- #

async def set_user_engine(user_id, engine):
    """Persist the engine a models holder picked in /models or /engine."""
    from engines import normalize_engine
    value = normalize_engine(engine)
    await users_col.update_one({"user_id": user_id}, {"$set": {"engine_preference": value}})
    return value


async def get_user_engine(user_id):
    """The stored preference (``None`` when the user never chose one)."""
    user = await users_col.find_one({"user_id": user_id}, {"engine_preference": 1})
    value = (user or {}).get("engine_preference")
    return value or None


async def get_engine_preference(user_id):
    """Alias of :func:`get_user_engine` used by the extraction pipeline."""
    return await get_user_engine(user_id)


async def set_engine_mode(mode):
    """Persist the global engine controller mode (AUTO / LOCK C++ / LOCK PYTHON)."""
    from engines import normalize_mode
    value = normalize_mode(mode)
    await config_col.update_one(
        {"type": "engine_mode"},
        {"$set": {"mode": value, "updated_at": datetime.now()}},
        upsert=True,
    )
    return value


async def get_engine_mode():
    """The stored global mode, defaulting to ``config.DEFAULT_ENGINE_MODE``."""
    row = await config_col.find_one({"type": "engine_mode"})
    if not row or not row.get("mode"):
        return DEFAULT_ENGINE_MODE
    from engines import normalize_mode
    return normalize_mode(row.get("mode"))


async def record_engine_use(engine, count: int = 1):
    """Persist how many extractions each engine has served (analytics)."""
    from engines import normalize_engine
    value = normalize_engine(engine)
    if value not in ENGINES:
        value = ENGINE_PYTHON
    await config_col.update_one(
        {"type": "engine_stats"},
        {"$inc": {f"counts.{value}": int(count)},
         "$set": {"updated_at": datetime.now()}},
        upsert=True,
    )


async def get_engine_stats():
    """Persisted per-engine extraction counters (``0`` for untouched engines)."""
    row = await config_col.find_one({"type": "engine_stats"})
    counts = (row or {}).get("counts") or {}
    return {engine: int(counts.get(engine, 0) or 0) for engine in ENGINES}


# --------------------------------------------------------------------------- #
#  Per-channel extraction counter (/mychannels dashboard)
# --------------------------------------------------------------------------- #

async def increment_channel_files(chat_id, count: int = 1):
    """Count files delivered into a dump channel (shown by /mychannels)."""
    await config_col.update_one(
        {"type": "channel_stats", "chat_id": int(chat_id)},
        {"$inc": {"files": int(count)}, "$set": {"updated_at": datetime.now()}},
        upsert=True,
    )


async def get_channel_files(chat_id):
    row = await config_col.find_one({"type": "channel_stats", "chat_id": int(chat_id)})
    return int((row or {}).get("files", 0) or 0)


async def set_channel_files(chat_id, count: int):
    await config_col.update_one(
        {"type": "channel_stats", "chat_id": int(chat_id)},
        {"$set": {"files": int(count), "updated_at": datetime.now()}},
        upsert=True,
    )



async def is_banned(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("is_banned", False) if user else False


async def ban_user(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_banned": True}})


async def unban_user(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_banned": False}})


async def check_daily_limit(user_id, limit=FREE_DAILY_LIMIT):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        return True, 0
    today = utcnow().date()
    last_date = user.get("last_download_date")
    if last_date and last_date.date() == today:
        current = user.get("daily_downloads", 0)
        if current >= limit:
            return False, current
        return True, current
    return True, 0


async def increment_daily(user_id, count_daily=True):
    await users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {"downloads": 1, "daily_downloads": int(count_daily)},
            "$set": {"last_active": datetime.now(), **({"last_download_date": datetime.now()} if count_daily else {})}
        }
    )


async def save_session(user_id, session_string, phone):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": session_string, "phone": phone}}
    )


async def get_session(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("session_string") if user else None


async def delete_session(user_id):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": None, "phone": None}}
    )


async def set_caption(user_id, caption):
    await users_col.update_one({"user_id": user_id}, {"$set": {"caption": caption}})


async def get_caption(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("caption") if user else None


async def del_caption(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"caption": None}})


async def set_thumbnail(user_id, file_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"thumbnail_id": file_id}})


async def get_thumbnail(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("thumbnail_id") if user else None


async def del_thumbnail(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"thumbnail_id": None}})


async def set_prefix(user_id, prefix):
    await users_col.update_one({"user_id": user_id}, {"$set": {"prefix": prefix}})


async def get_prefix(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("prefix") if user else None


async def set_suffix(user_id, suffix):
    await users_col.update_one({"user_id": user_id}, {"$set": {"suffix": suffix}})


async def get_suffix(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("suffix") if user else None


async def add_download(user_id, link, file_type):
    await downloads_col.insert_one({
        "user_id": user_id,
        "link": link,
        "type": file_type,
        "date": datetime.now()
    })


async def get_history(user_id, limit=10):
    history = []
    async for item in downloads_col.find({"user_id": user_id}).sort("date", -1).limit(limit):
        history.append(item)
    return history


async def clear_history(user_id):
    await downloads_col.delete_many({"user_id": user_id})


async def add_bookmark(user_id, link, tag=None):
    await bookmarks_col.insert_one({
        "user_id": user_id,
        "link": link,
        "tag": tag,
        "date": datetime.now()
    })


async def get_bookmarks(user_id):
    bookmarks = []
    async for item in bookmarks_col.find({"user_id": user_id}).sort("date", -1):
        bookmarks.append(item)
    return bookmarks


async def delete_bookmark(user_id, link):
    await bookmarks_col.delete_one({"user_id": user_id, "link": link})


async def add_favorite(user_id, channel):
    await users_col.update_one(
        {"user_id": user_id},
        {"$addToSet": {"favorites": channel}}
    )


async def get_favorites(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("favorites", []) if user else []


async def remove_favorite(user_id, channel):
    await users_col.update_one(
        {"user_id": user_id},
        {"$pull": {"favorites": channel}}
    )


async def set_language(user_id, lang):
    await users_col.update_one({"user_id": user_id}, {"$set": {"language": lang}})


async def toggle_notifications(user_id):
    user = await get_user(user_id)
    new_val = not user.get("notifications", True) if user else True
    await users_col.update_one({"user_id": user_id}, {"$set": {"notifications": new_val}})
    return new_val


async def toggle_silent(user_id):
    user = await get_user(user_id)
    new_val = not user.get("silent_mode", False) if user else False
    await users_col.update_one({"user_id": user_id}, {"$set": {"silent_mode": new_val}})
    return new_val


async def reset_settings(user_id):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "caption": None,
            "thumbnail_id": None,
            "prefix": None,
            "suffix": None,
            "language": "en",
            "notifications": True,
            "silent_mode": False
        }}
    )


async def add_referral(referrer_id, new_user_id):
    await users_col.update_one(
        {"user_id": new_user_id},
        {"$set": {"referred_by": referrer_id}}
    )
    await users_col.update_one(
        {"user_id": referrer_id},
        {"$inc": {"referral_count": 1}}
    )


async def add_feedback(user_id, message):
    await feedback_col.insert_one({
        "user_id": user_id,
        "message": message,
        "date": datetime.now()
    })


async def get_all_feedback():
    feedbacks = []
    async for fb in feedback_col.find({}).sort("date", -1):
        feedbacks.append(fb)
    return feedbacks


async def get_active_users_today():
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return await users_col.count_documents({"last_active": {"$gte": today_start}})


async def get_new_users_today():
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return await users_col.count_documents({"joined_date": {"$gte": today_start}})


async def get_top_users(limit=10):
    users = []
    async for user in users_col.find({}).sort("downloads", -1).limit(limit):
        users.append(user)
    return users


async def total_downloads_count():
    return await downloads_col.count_documents({})


async def total_bookmarks_count():
    return await bookmarks_col.count_documents({})


async def sync_user_profile(user_id, name=None, username=None):
    """Keep the stored name/username in sync with Telegram.

    Users can rename themselves at any time, so every interaction refreshes the
    stored profile instead of trusting the value captured at first /start.  Only
    real changes are written.
    """
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        return False
    updates = {}
    if name and name != user.get("name"):
        updates["name"] = name
        history = list(user.get("previous_names") or [])
        old_name = user.get("name")
        if old_name and old_name != name and len(history) < 5:
            history.append(old_name)
        updates["previous_names"] = history
    if username is not None and username != user.get("username"):
        updates["username"] = username
    if not updates:
        return False
    updates["last_active"] = datetime.now()
    await users_col.update_one({"user_id": user_id}, {"$set": updates})
    return True


async def get_display_name(user_id, fallback="User"):
    """Always read the freshest stored name (used by lists and notifications)."""
    user = await users_col.find_one({"user_id": user_id}, {"name": 1})
    return (user or {}).get("name") or fallback


# --------------------------------------------------------------------------- #
#  Dump channels — up to config.MAX_USER_CHANNELS per user
#
#  Storage: a ``channels`` list of small documents plus a mirror of the first
#  entry in the legacy single-channel fields (``channel_chat_id`` /
#  ``channel_title`` / ``channel_username``).  The mirror is what keeps every
#  pre-multi-channel document, query and reader working unchanged, so there is
#  no migration script and no window where a legacy user loses their channel.
#  Legacy rows are migrated *on read* by :func:`channels_from_document`.
# --------------------------------------------------------------------------- #

def channels_from_document(user) -> list[dict]:
    """Normalize any stored shape into the canonical ``channels`` list.

    A document written before multi-channel support only has the three legacy
    scalar fields; one written after has the list.  Reading through this
    function migrates on the fly, so no data is ever lost or rewritten.
    """
    if not user:
        return []
    entries = []
    seen = set()
    for raw in (user.get("channels") or []):
        if not isinstance(raw, dict):
            continue
        chat_id = raw.get("chat_id")
        if chat_id is None or int(chat_id) in seen:
            continue
        chat_id = int(chat_id)
        seen.add(chat_id)
        entries.append({
            "chat_id": chat_id,
            "title": raw.get("title") or str(chat_id),
            "username": raw.get("username"),
            "type": raw.get("type") or "channel",
        })
    legacy_id = user.get("channel_chat_id")
    if legacy_id is not None and int(legacy_id) not in seen:
        entries.insert(0, {
            "chat_id": int(legacy_id),
            "title": user.get("channel_title") or str(int(legacy_id)),
            "username": user.get("channel_username"),
            "type": user.get("channel_type") or "channel",
        })
    return entries


def pick_channel_entry(user_row, chat_id):
    """The stored entry for *chat_id* inside *user_row*, or ``None``."""
    if chat_id is None:
        return None
    try:
        wanted = int(chat_id)
    except (TypeError, ValueError):
        return None
    for entry in channels_from_document(user_row):
        if entry["chat_id"] == wanted:
            return entry
    return None


async def get_user_channels(user_id) -> list[dict]:
    """Every dump channel of *user_id*, oldest registration first."""
    user = await users_col.find_one({"user_id": int(user_id)})
    return channels_from_document(user)


async def add_user_channel(user_id, chat_id, title=None, username=None,
                           chat_type=None):
    """Register (or refresh) one dump channel, honouring ``MAX_USER_CHANNELS``.

    Returns ``(ok, reason)`` where *reason* is ``"added"``, ``"updated"`` or
    ``"full"`` — the caller turns that into plain English, so a user who already
    has two channels is told to disconnect one first instead of getting a
    silent failure.
    """
    user_id, chat_id = int(user_id), int(chat_id)
    user = await users_col.find_one({"user_id": user_id}) or {}
    entries = channels_from_document(user)
    for entry in entries:
        if entry["chat_id"] == chat_id:
            entry["title"] = title or entry["title"]
            entry["username"] = username if username is not None else entry["username"]
            entry["type"] = chat_type or entry["type"]
            reason = "updated"
            break
    else:
        if len(entries) >= max(1, int(MAX_USER_CHANNELS)):
            return False, "full"
        entries.append({
            "chat_id": chat_id,
            "title": title or str(chat_id),
            "username": username,
            "type": chat_type or "channel",
        })
        reason = "added"

    first = entries[0]
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "channels": entries,
            # Mirror of the primary channel: legacy readers keep working.
            "channel_chat_id": first["chat_id"],
            "channel_title": first["title"],
            "channel_username": first["username"],
            "channel_type": first["type"],
        }},
        upsert=True,
    )
    return True, reason


async def remove_user_channel(user_id, chat_id) -> bool:
    """Disconnect one dump channel.  ``True`` when something was removed."""
    user_id = int(user_id)
    user = await users_col.find_one({"user_id": user_id}) or {}
    entries = channels_from_document(user)
    wanted = int(chat_id) if chat_id is not None else None
    remaining = [e for e in entries if e["chat_id"] != wanted]
    if len(remaining) == len(entries):
        return False
    first = remaining[0] if remaining else None
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "channels": remaining,
            "channel_chat_id": first["chat_id"] if first else None,
            "channel_title": first["title"] if first else None,
            "channel_username": first["username"] if first else None,
            "channel_type": first["type"] if first else None,
        }},
    )
    return True


async def set_user_chat(user_id, chat_id, title=None, username=None):
    """Remember a channel where this user enabled the bot dump (/setchat).

    Thin wrapper kept for every existing caller: it registers the channel and
    reports whether the per-user limit refused it.
    """
    return await add_user_channel(user_id, chat_id, title=title, username=username)


async def get_user_chat(user_id):
    """The **primary** channel-dump target of *user_id* (``None`` if unset).

    Kept byte-compatible with the single-channel era: exactly the three legacy
    keys, describing the first registered channel.
    """
    user = await users_col.find_one({"user_id": int(user_id)})
    entries = channels_from_document(user)
    if not entries:
        return None
    first = entries[0]
    return {
        "chat_id": first["chat_id"],
        "title": first["title"] or str(first["chat_id"]),
        "username": first["username"],
    }


async def find_user_chat_owner(chat_id):
    """Which user configured *chat_id* as one of their dump channels?"""
    return await users_col.find_one({
        "$or": [
            {"channel_chat_id": int(chat_id)},
            {"channels.chat_id": int(chat_id)},
        ],
    })


async def clear_user_chat(user_id):
    """Disconnect **every** dump channel of *user_id*."""
    await users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {"channels": [], "channel_chat_id": None, "channel_title": None,
                  "channel_username": None, "channel_type": None}},
    )


async def mark_payment(user_id, status, reviewer=None, plan=None):
    """Move the newest pending proof of *user_id* to *status*.

    Returns the updated row (or ``None`` when there was nothing pending), so the
    caller can build the review caption from the stored plan details.
    """
    row = await db["payments"].find_one(
        {"user_id": user_id, "status": "pending_review"}, sort=[("date", -1)]
    )
    if not row:
        return None
    updates = {"status": status, "reviewed_by": reviewer, "reviewed_at": datetime.now()}
    if plan:
        updates["approved_plan"] = plan
    await db["payments"].update_one({"_id": row["_id"]}, {"$set": updates})
    row.update(updates)
    return row


async def search_user(query):
    try:
        q_int = int(query)
        res = await users_col.find_one({"user_id": q_int})
        if res:
            return [res]
    except:
        pass
    results = []
    async for u in users_col.find({"$or": [{"name": {"$regex": query, "$options": "i"}}, {"username": {"$regex": query, "$options": "i"}}]}).limit(10):
        results.append(u)
    return results


async def set_maintenance(status: bool):
    await config_col.update_one({"type": "maintenance"}, {"$set": {"status": status}}, upsert=True)


async def get_maintenance():
    res = await config_col.find_one({"type": "maintenance"})
    return res.get("status", False) if res else False


async def set_fsub_channel(channel: str):
    """Back-compat single-entry writer: stores the legacy document.

    ``get_fsub_list()`` migrates that document into ``items[0]`` on its first
    read, so old deployments keep working without any manual migration.
    """
    await config_col.update_one({"type": "fsub"}, {"$set": {"channel": str(channel)}}, upsert=True)


async def get_fsub_channel():
    """Back-compat accessor: public reference of the required chat, if any."""
    row = await config_col.find_one({"type": "fsub"})
    if row and row.get("channel"):
        return row["channel"]
    items = await get_fsub_list()
    if not items:
        return None
    first = items[0]
    return "@" + first["username"] if first.get("username") else str(first["chat_id"])


# --------------------------------------------------------------------------- #
#  Force subscription — an unlimited list of channels and groups
#
#  Everything lives on one config document so a read/write is atomic:
#      {"type": "fsub_list", "items": [item, ...]}
# --------------------------------------------------------------------------- #

#: Fields an item may carry; anything else is dropped on write.
FSUB_ITEM_FIELDS = (
    "chat_id", "title", "username", "invite_link",
    "button_text", "kind", "auto_approve", "order",
)


def normalize_fsub_item(item: dict, order: int = 0) -> dict:
    """Return a sanitized copy of *item* (never trust caller-supplied keys)."""
    chat_id = item.get("chat_id")
    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        chat_id = 0
    title = (item.get("title") or "").strip() or f"Chat {chat_id}"
    username = (item.get("username") or "").strip().lstrip("@") or None
    invite_link = (item.get("invite_link") or "").strip() or None
    button_text = (item.get("button_text") or "").strip() or f"✅ Join {title}"
    kind = "group" if str(item.get("kind") or "").lower().startswith("group") else "channel"
    return {
        "chat_id": chat_id,
        "title": title,
        "username": username,
        "invite_link": invite_link,
        "button_text": button_text,
        "kind": kind,
        "auto_approve": bool(item.get("auto_approve")),
        "order": int(order),
    }


async def _read_fsub_doc():
    return await config_col.find_one({"type": "fsub_list"})


async def _write_fsub_items(items):
    await config_col.update_one(
        {"type": "fsub_list"}, {"$set": {"items": items}}, upsert=True
    )


async def _migrate_legacy_fsub() -> list:
    """Move the old single ``{"type": "fsub"}`` document into items[0]."""
    legacy = await config_col.find_one({"type": "fsub"})
    if not legacy or not legacy.get("channel"):
        return []
    channel = str(legacy["channel"]).lstrip("@")
    items = [normalize_fsub_item({
        "chat_id": 0, "title": channel, "username": channel,
        "invite_link": None, "button_text": "✅ I Joined",
        "kind": "channel", "auto_approve": False,
    }, order=0)]
    await _write_fsub_items(items)
    await config_col.delete_one({"type": "fsub"})
    return items


async def get_fsub_list() -> list:
    """Every required chat, in the order the owner added them."""
    doc = await _read_fsub_doc()
    if not doc:
        return await _migrate_legacy_fsub()
    items = [normalize_fsub_item(item, order=index)
             for index, item in enumerate(doc.get("items") or [])]
    if items != (doc.get("items") or []):
        # keep stored documents tidy (legacy rows lacked fields)
        await _write_fsub_items(items)
    return items


async def add_fsub_item(item: dict) -> int:
    """Append *item* and return its 1-based number."""
    items = await get_fsub_list()
    items.append(normalize_fsub_item(item, order=len(items)))
    await _write_fsub_items(items)
    return len(items)


async def remove_fsub_item(number: int):
    """Remove the *number*-th (1-based) entry; returns it or ``None``."""
    items = await get_fsub_list()
    index = int(number) - 1
    if not 0 <= index < len(items):
        return None
    removed = items.pop(index)
    for position, item in enumerate(items):
        item["order"] = position
    await _write_fsub_items(items)
    return removed


async def update_fsub_item(number: int, **fields) -> bool:
    """Patch the *number*-th (1-based) entry; ``False`` when it is missing."""
    items = await get_fsub_list()
    index = int(number) - 1
    if not 0 <= index < len(items):
        return False
    patch = {key: value for key, value in fields.items() if key in FSUB_ITEM_FIELDS}
    if not patch:
        return True
    items[index].update(patch)
    items[index] = normalize_fsub_item(items[index], order=index)
    await _write_fsub_items(items)
    return True


async def clear_fsub_list() -> int:
    """Remove every entry; returns how many were removed."""
    items = await get_fsub_list()
    await config_col.delete_one({"type": "fsub_list"})
    return len(items)


async def delete_fsub() -> int:
    """Back-compat alias of :func:`clear_fsub_list`."""
    return await clear_fsub_list()


async def set_fsub_verify_label(label: str | None):
    await config_col.update_one(
        {"type": "fsub_verify_label"}, {"$set": {"label": (label or "").strip() or None}},
        upsert=True,
    )


async def get_fsub_verify_label():
    row = await config_col.find_one({"type": "fsub_verify_label"})
    return (row or {}).get("label")


# --------------------------------------------------------------------------- #
#  Join requests of the force-sub chats (approve list bookkeeping)
# --------------------------------------------------------------------------- #

async def record_join_request(chat_id, user_id, date=None, status: str = "pending"):
    await db["join_requests"].update_one(
        {"chat_id": int(chat_id), "user_id": int(user_id)},
        {"$set": {
            "chat_id": int(chat_id), "user_id": int(user_id),
            "date": date or datetime.now(), "status": status,
        }},
        upsert=True,
    )


async def set_join_request_status(chat_id, user_id, status: str):
    await db["join_requests"].update_one(
        {"chat_id": int(chat_id), "user_id": int(user_id)},
        {"$set": {"status": status}},
    )


async def get_join_request(chat_id, user_id):
    return await db["join_requests"].find_one(
        {"chat_id": int(chat_id), "user_id": int(user_id)}
    )


async def add_admin(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_admin": True}})


async def remove_admin(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_admin": False}})


async def is_admin(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("is_admin", False) if user else False


async def get_admins_list():
    admins = []
    async for u in users_col.find({"is_admin": True}):
        admins.append(u)
    return admins


async def clear_all_logs():
    await downloads_col.delete_many({})


async def get_bot_stats():
    total = await total_users()
    active_today = await get_active_users_today()
    new_today = await get_new_users_today()
    premium = await users_col.count_documents({"is_premium": True})
    banned = await users_col.count_documents({"is_banned": True})
    admins = await users_col.count_documents({"is_admin": True})
    downloads = await total_downloads_count()
    return {
        "total": total,
        "active_today": active_today,
        "new_today": new_today,
        "premium": premium,
        "banned": banned,
        "admins": admins,
        "total_downloads": downloads,
        # Granular VIP flags — how many users hold each feature.
        "models_access": await users_col.count_documents({"has_models_access": True}),
        "private_access": await users_col.count_documents({"has_private_access": True}),
    }


async def test_connection():
    try:
        await mongo_client.admin.command('ping')
        print("✅ MongoDB Connected!")
        return True
    except Exception as e:
        print(f"❌ MongoDB Failed: {e}")
        return False
    


async def get_points(user_id):
    user = await get_user(user_id)
    return int((user or {}).get("points", 0))


async def award_referral(referrer_id, new_user_id, points=10):
    """Claim an invitee once and credit the referrer idempotently.

    credited_referrals also makes retrying a partially completed award safe.
    The /start handler only calls this for a newly registered account.
    """
    if int(referrer_id) == int(new_user_id):
        return False
    if not await users_col.find_one({"user_id": referrer_id}):
        return False
    invitee = await users_col.find_one_and_update(
        {"user_id": new_user_id, "$or": [{"referred_by": None}, {"referred_by": referrer_id}]},
        {"$set": {"referred_by": referrer_id}}, return_document=True,
    )
    if not invitee:
        return False
    result = await users_col.update_one(
        {"user_id": referrer_id, "credited_referrals": {"$ne": new_user_id}},
        {"$inc": {"referral_count": 1, "points": points},
         "$addToSet": {"credited_referrals": new_user_id}},
    )
    return bool(result.modified_count)


def add_months(date, months):
    month = date.month - 1 + months
    year = date.year + month // 12
    month = month % 12 + 1
    return date.replace(year=year, month=month,
                        day=min(date.day, calendar.monthrange(year, month)[1]))


async def redeem_points(user_id, points=100, days=None, *, months=REDEEM_PREMIUM_MONTHS):
    """Spend once with optimistic concurrency; never downgrade manual access.

    Existing points premium is extended, not replaced. ``days`` is retained
    for callers of the older API; the bot always requests calendar months.
    """
    for _ in range(5):
        user = await get_user(user_id)
        now = datetime.now()
        if not user or user.get("points", 0) < points:
            return False
        expiry = user.get("premium_expiry")
        active = user.get("is_premium") and (not expiry or expiry > now)
        if active and user.get("premium_source") != PREMIUM_SOURCE_REDEEM:
            return False
        base = max(now, expiry) if active and expiry else now
        new_expiry = base + timedelta(days=days) if days is not None else add_months(base, months)
        result = await users_col.update_one(
            {"user_id": user_id, "points": user["points"],
             "premium_expiry": expiry, "premium_source": user.get("premium_source"),
             "is_premium": user.get("is_premium", False)},
            {"$inc": {"points": -points}, "$set": {
                "is_premium": True, "premium_source": PREMIUM_SOURCE_REDEEM,
                "premium_expiry": new_expiry,
            }},
        )
        if result.modified_count:
            return True
    return False


async def reserve_daily(user_id, limit=FREE_DAILY_LIMIT, now=None):
    """Reserve before sending, so concurrent requests cannot exceed the quota."""
    now = now or utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    await users_col.update_one(
        {"user_id": user_id, "last_download_date": {"$not": {"$gte": today}}},
        {"$set": {"daily_downloads": 0, "last_download_date": now}},
    )
    result = await users_col.update_one(
        {"user_id": user_id, "daily_downloads": {"$lt": limit}},
        {"$inc": {"daily_downloads": 1}, "$set": {"last_download_date": now}},
    )
    return bool(result.modified_count)


async def refund_daily(user_id, reservation_date):
    today = reservation_date.replace(hour=0, minute=0, second=0, microsecond=0)
    await users_col.update_one(
        {"user_id": user_id, "daily_downloads": {"$gt": 0},
         "last_download_date": {"$gte": today, "$lt": today + timedelta(days=1)}},
        {"$inc": {"daily_downloads": -1}},
    )


async def set_qr(file_id):
    await config_col.update_one({"type": "payment_qr"}, {"$set": {"file_id": file_id}}, upsert=True)


async def get_qr():
    row = await config_col.find_one({"type": "payment_qr"})
    return row.get("file_id") if row else None


async def delete_qr():
    await config_col.delete_one({"type": "payment_qr"})


async def add_payment(user_id, proof, note=None):
    row = {"user_id": user_id, "proof": proof, "note": note,
           "status": "pending_review", "date": datetime.now()}
    if isinstance(note, dict) and note.get("checkout"):
        row["_id"] = f"{user_id}:{note['checkout']}"
    try:
        return await db["payments"].insert_one(row)
    except DuplicateKeyError:
        return None


async def get_payments():
    rows = []
    async for row in db["payments"].find({}).sort("date", -1):
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
#  Owner dump channel — one global mirror for everything the bot delivers
#
#  It lives on a single ``config`` document (``{"type": "dump_channel"}``) so a
#  read is one query and there is no second source of truth.  The mirror itself
#  is implemented in main.py: the bot *copies* every delivered message there
#  (never forwards it, so nothing shows a "Forwarded from" header) and deletes
#  the copy again after ``config.DUMP_TTL_SECONDS``.
# --------------------------------------------------------------------------- #

async def set_dump_channel(chat_id, title=None, username=None, kind=None):
    """Connect (or move) the owner's dump channel."""
    await config_col.update_one(
        {"type": "dump_channel"},
        {"$set": {
            "chat_id": int(chat_id),
            "title": title,
            "username": username,
            "kind": kind,
            "added_at": utcnow(),
        }},
        upsert=True,
    )
    return True


async def get_dump_channel():
    """The connected dump channel as a dict, or ``None``."""
    row = await config_col.find_one({"type": "dump_channel"})
    if not row or row.get("chat_id") is None:
        return None
    return {
        "chat_id": int(row["chat_id"]),
        "title": row.get("title"),
        "username": row.get("username"),
        "kind": row.get("kind"),
        "added_at": row.get("added_at"),
    }


async def delete_dump_channel():
    result = await config_col.delete_one({"type": "dump_channel"})
    return bool(getattr(result, "deleted_count", 0))


# --------------------------------------------------------------------------- #
#  Giveaways
#
#  One active giveaway at a time (``config.GIVEAWAY_SINGLE_ACTIVE``):
#      db["giveaway"]             {"_id": "active", ...}   — the giveaway itself
#      db["giveaway_participants"] {"giveaway_id", "user_id", ...} — one per user
#
#  Participants live in their own collection because the count has to stay
#  cheap (it is refreshed on the pinned message while the giveaway runs) and a
#  unique index on (giveaway_id, user_id) makes a double tap impossible.
# --------------------------------------------------------------------------- #

#: Fields a giveaway document may carry; anything else is dropped on write.
GIVEAWAY_FIELDS = (
    "token", "status", "prize_tier", "prize_days", "benefit", "ends_at",
    "created_at", "created_by", "channel_id", "message_id", "last_post_at",
    "winner", "winner_at", "ended_at", "participant_count", "custom_message",
    "rendered_count",
)


def _clean_giveaway(doc: dict) -> dict:
    return {key: doc[key] for key in GIVEAWAY_FIELDS if key in doc}


async def create_giveaway(doc: dict):
    """Start the single active giveaway (refuses when one is already running)."""
    if GIVEAWAY_SINGLE_ACTIVE:
        existing = await get_active_giveaway()
        if existing:
            return False
    payload = _clean_giveaway(doc)
    payload["_id"] = "active"
    payload.setdefault("status", "running")
    payload.setdefault("created_at", utcnow())
    payload.setdefault("participant_count", 0)
    await db["giveaway"].replace_one({"_id": "active"}, payload, upsert=True)
    return True


async def get_active_giveaway():
    """The running giveaway, or ``None`` when none is live."""
    row = await db["giveaway"].find_one({"_id": "active"})
    if not row or row.get("status") != "running":
        return None
    return row


async def get_last_giveaway():
    """The most recent giveaway whatever its status (used by /end and history)."""
    return await db["giveaway"].find_one({"_id": "active"})


async def update_giveaway(updates: dict):
    if not updates:
        return False
    result = await db["giveaway"].update_one({"_id": "active"}, {"$set": dict(updates)})
    return bool(getattr(result, "matched_count", 0))


async def finish_giveaway(winner=None, *, status="finished"):
    """Close the active giveaway, recording the winner when there is one."""
    updates = {
        "status": status,
        "ended_at": utcnow(),
    }
    if winner is not None:
        updates["winner"] = winner
        updates["winner_at"] = utcnow()
    result = await db["giveaway"].update_one({"_id": "active"}, {"$set": updates})
    return bool(getattr(result, "matched_count", 0))


async def ensure_giveaway_indexes():
    """Best-effort unique index so one account can never join twice.

    The explicit existence check in :func:`add_giveaway_participant` is what
    actually guarantees the rule (it also works on a Mongo-compatible mock that
    has no indexes); the index only makes the concurrent double-tap cheap.
    """
    try:
        await db["giveaway_participants"].create_index(
            [("giveaway_id", 1), ("user_id", 1)], unique=True, background=True)
    except Exception as exc:  # pragma: no cover - depends on the server
        print(f"[GIVEAWAY INDEX] {exc}", flush=True)
        return False
    return True


async def add_giveaway_participant(giveaway_id, user_id, name=None, username=None):
    """Join a giveaway.  ``False`` when this user already joined."""
    if await is_giveaway_participant(giveaway_id, user_id):
        return False
    row = {
        "giveaway_id": str(giveaway_id),
        "user_id": int(user_id),
        "name": name,
        "username": username,
        "joined_at": utcnow(),
    }
    try:
        await db["giveaway_participants"].insert_one(row)
    except DuplicateKeyError:
        return False
    await db["giveaway"].update_one({"_id": "active"}, {"$inc": {"participant_count": 1}})
    return True


async def count_giveaway_participants(giveaway_id) -> int:
    return int(await db["giveaway_participants"].count_documents(
        {"giveaway_id": str(giveaway_id)}))


async def is_giveaway_participant(giveaway_id, user_id) -> bool:
    row = await db["giveaway_participants"].find_one(
        {"giveaway_id": str(giveaway_id), "user_id": int(user_id)})
    return row is not None


async def list_giveaway_participants(giveaway_id, skip: int = 0, limit: int = 10):
    cursor = (db["giveaway_participants"]
              .find({"giveaway_id": str(giveaway_id)})
              .sort("joined_at", 1).skip(max(0, int(skip))).limit(max(1, int(limit))))
    return [row async for row in cursor]


async def all_giveaway_participants(giveaway_id):
    """Every participant — the pool the random draw picks the winner from."""
    cursor = (db["giveaway_participants"]
              .find({"giveaway_id": str(giveaway_id)}).sort("joined_at", 1))
    return [row async for row in cursor]


async def clear_giveaway_participants(giveaway_id) -> int:
    result = await db["giveaway_participants"].delete_many({"giveaway_id": str(giveaway_id)})
    return int(getattr(result, "deleted_count", 0))


# --------------------------------------------------------------------------- #
#  Auto-delete history and payments older than 30 days
# --------------------------------------------------------------------------- #

async def cleanup_old_records(days: int = 30):
    """Delete download history, bookmarks, feedback and payment records older than *days*.

    Called periodically by a background task in main.py.
    """
    cutoff = datetime.now() - timedelta(days=days)
    dl_result = await downloads_col.delete_many({"date": {"$lt": cutoff}})
    pay_result = await db["payments"].delete_many({"date": {"$lt": cutoff}})
    fb_result = await feedback_col.delete_many({"date": {"$lt": cutoff}})
    bm_result = await bookmarks_col.delete_many({"date": {"$lt": cutoff}})
    stars_result = await stars_payments_col.delete_many({"date": {"$lt": cutoff}})
    return {
        "downloads": int(getattr(dl_result, "deleted_count", 0)),
        "payments": int(getattr(pay_result, "deleted_count", 0)),
        "feedback": int(getattr(fb_result, "deleted_count", 0)),
        "bookmarks": int(getattr(bm_result, "deleted_count", 0)),
        "stars_payments": int(getattr(stars_result, "deleted_count", 0)),
    }


# --------------------------------------------------------------------------- #
#  Telegram Stars payments
# --------------------------------------------------------------------------- #

async def add_stars_payment(user_id, plan_key, stars_amount, inr_amount, invoice_payload):
    """Record a Telegram Stars payment."""
    row = {
        "user_id": int(user_id),
        "plan": plan_key,
        "stars_amount": int(stars_amount),
        "inr_amount": int(inr_amount),
        "invoice_payload": invoice_payload,
        "status": "pending",
        "date": datetime.now(),
    }
    return await stars_payments_col.insert_one(row)


async def complete_stars_payment(invoice_payload, status="completed"):
    """Mark a Stars payment as completed or refunded."""
    result = await stars_payments_col.update_one(
        {"invoice_payload": invoice_payload, "status": "pending"},
        {"$set": {"status": status, "completed_at": datetime.now()}},
    )
    return bool(result.modified_count)


async def get_stars_payments(limit=50):
    """All Stars payments, newest first."""
    rows = []
    async for row in stars_payments_col.find({}).sort("date", -1).limit(limit):
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
#  /CreateBot — user-created child bots
# --------------------------------------------------------------------------- #

async def register_created_bot(creator_id, bot_token, bot_username=None, bot_id=None):
    """Register a new child bot created via /CreateBot."""
    row = {
        "_id": str(bot_token.split(":")[0]) if ":" in str(bot_token) else str(bot_token),
        "creator_id": int(creator_id),
        "bot_token": str(bot_token),
        "bot_username": bot_username,
        "bot_id": int(bot_id) if bot_id else None,
        "status": "active",
        "users_count": 0,
        "total_extractions": 0,
        "created_at": datetime.now(),
        "last_active": datetime.now(),
    }
    try:
        await created_bots_col.insert_one(row)
    except DuplicateKeyError:
        await created_bots_col.update_one(
            {"_id": row["_id"]},
            {"$set": {"bot_token": str(bot_token), "bot_username": bot_username,
                      "bot_id": int(bot_id) if bot_id else None,
                      "status": "active", "last_active": datetime.now()}},
        )
    return row


async def get_created_bot(bot_token_prefix):
    """Get a created bot by its token prefix (bot id part)."""
    prefix = str(bot_token_prefix).split(":")[0] if ":" in str(bot_token_prefix) else str(bot_token_prefix)
    return await created_bots_col.find_one({"_id": prefix})


async def get_created_bots_by_creator(creator_id):
    """All bots created by a specific user."""
    rows = []
    async for row in created_bots_col.find({"creator_id": int(creator_id)}):
        rows.append(row)
    return rows


async def get_all_created_bots():
    """Every registered child bot."""
    rows = []
    async for row in created_bots_col.find({}):
        rows.append(row)
    return rows


async def update_created_bot_stats(bot_token_prefix, *, users_count=None, total_extractions=None):
    """Update usage stats of a child bot."""
    prefix = str(bot_token_prefix).split(":")[0] if ":" in str(bot_token_prefix) else str(bot_token_prefix)
    updates = {"last_active": datetime.now()}
    if users_count is not None:
        updates["users_count"] = int(users_count)
    if total_extractions is not None:
        updates["total_extractions"] = int(total_extractions)
    await created_bots_col.update_one({"_id": prefix}, {"$set": updates})


async def delete_created_bot(bot_token_prefix):
    """Remove a child bot registration."""
    prefix = str(bot_token_prefix).split(":")[0] if ":" in str(bot_token_prefix) else str(bot_token_prefix)
    result = await created_bots_col.delete_one({"_id": prefix})
    return bool(result.deleted_count)


async def is_created_bot_admin(user_id, bot_token_prefix):
    """Check if a user is the creator/admin of a specific child bot."""
    bot = await get_created_bot(bot_token_prefix)
    return bot and int(bot.get("creator_id", 0)) == int(user_id)


async def get_child_bot_users_col(bot_token_prefix):
    """Get the users collection for a specific child bot's users."""
    prefix = str(bot_token_prefix).split(":")[0] if ":" in str(bot_token_prefix) else str(bot_token_prefix)
    return db[f"child_bot_users_{prefix}"]


async def add_child_bot_user(bot_token_prefix, user_id, name=None, username=None):
    """Track a user of a child bot."""
    col = await get_child_bot_users_col(bot_token_prefix)
    try:
        await col.update_one(
            {"user_id": int(user_id)},
            {"$set": {"user_id": int(user_id), "name": name, "username": username,
                      "last_active": datetime.now()},
             "$setOnInsert": {"joined_at": datetime.now(), "extractions": 0}},
            upsert=True,
        )
    except Exception:
        pass


async def get_child_bot_user_count(bot_token_prefix):
    """How many users a child bot has."""
    col = await get_child_bot_users_col(bot_token_prefix)
    return await col.count_documents({})


async def get_child_bot_users(bot_token_prefix, limit=50):
    """List users of a child bot."""
    col = await get_child_bot_users_col(bot_token_prefix)
    rows = []
    async for row in col.find({}).sort("last_active", -1).limit(limit):
        rows.append(row)
    return rows


async def increment_child_bot_extractions(bot_token_prefix):
    """Increment extraction count for a child bot."""
    prefix = str(bot_token_prefix).split(":")[0] if ":" in str(bot_token_prefix) else str(bot_token_prefix)
    await created_bots_col.update_one(
        {"_id": prefix},
        {"$inc": {"total_extractions": 1}, "$set": {"last_active": datetime.now()}},
    )
