import os
import re
import html
import math
import time
import random
import secrets
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
from pyrogram import Client, filters, raw, utils
from pyrogram.types import (
    CallbackQuery, BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid,
    PasswordHashInvalid, FloodWait, ChannelPrivate, MessageNotModified,  # noqa: F401
    InviteHashExpired, InviteHashInvalid, InviteSlugExpired, InviteRequestSent,
    UserAlreadyParticipant, ChatAdminRequired, PeerIdInvalid, UserNotParticipant
)

import ui
import database
import appapi
import engines
import telemetry
import native_engine
from config import (BOT_USERNAME, FREE_DAILY_LIMIT, FREE_PRIVATE_LINKS, WATERMARK, REFER_POINTS,
                    REDEEM_POINTS, REDEEM_PREMIUM_DAYS, REDEEM_PREMIUM_MONTHS, PAYMENT_CONTACT,
                    PREMIUM_PLANS, PREMIUM_BENEFITS, REDEEM_LIMITATION, RUPEE,
                    PREMIUM_SOURCE_MANUAL, PREMIUM_SOURCE_PUBLIC, PREMIUM_SOURCE_MODELS,
                    PURCHASE_PREMIUM_SOURCE, CHANNEL_CLEANUP_SECONDS, CHANNEL_EXTRACT_COOLDOWN,
                    CHANNEL_CAPTION_TIMEOUT, MAX_USER_CHANNELS, RANGE_PREFLIGHT_BATCH,
                    FSUB_MAX_BUTTON_CHARS, FSUB_ITEMS_PER_PAGE, FSUB_JOINER_SCAN_LIMIT,
                    FSUB_VERIFY_LABEL, CHANNEL_TITLE_FALLBACK,
                    OWNER_CONTACT_URL, plan_addon_price, plan_base_price, plan_total_price,
                    STAR_EXCHANGE_RATE, HISTORY_RETENTION_DAYS, OWNER_TELEGRAM_ID,
                    ENGINE_PYTHON, ENGINE_CPP, ENGINE_PEAK_THRESHOLD, ENGINE_TURBO_WORKERS,
                    ENGINE_ZERO_COPY_MAX_BYTES, ENGINE_START_GAP_SECONDS,
                    ENGINE_PYTHON_SPEED_LIMIT_MBPS, ENGINE_PYTHON_SPEED_BURST_SECONDS,
                    DUMP_TTL_SECONDS, DUMP_QUEUE_LIMIT, DUMP_COOLDOWN_SECONDS,
                    DUMP_STAGE_CAMPAIGNS,
                    MAX_MESSAGE_BUTTONS, MAX_BUTTON_LABEL, BUTTON_COLORS,
                    GIVEAWAY_SINGLE_ACTIVE, GIVEAWAY_LIVE_REFRESH_SECONDS,
                    GIVEAWAY_DAILY_INTERVAL_SECONDS, GIVEAWAY_PARTICIPANTS_PER_PAGE,
                    GIVEAWAY_MAX_BENEFIT_CHARS, GIVEAWAY_MAX_DAYS,
                    GIVEAWAY_BENEFIT_SUGGESTIONS, CHANNEL_SHARE_TOKEN_TTL,
                    GIVEAWAY_BROADCAST_DELAY, GIVEAWAY_BROADCAST_FLOOD_RETRIES,
                    CHANNEL_PICKER_BUTTON_ID, DUMP_PICKER_BUTTON_ID,
                    ECHO_SWALLOW_WINDOW_SECONDS,
                    ENGINE_MODE_AUTO, ENGINE_MODE_LOCK_CPP, ENGINE_MODE_LOCK_PYTHON,
                    DEFAULT_ENGINE_MODE, GRANT_TIERS, GRANT_TIER_KEYS, GRANT_DURATIONS,
                    GRANT_CUSTOM_DAYS_KEY, GRANT_MAX_DAYS, LEGACY_TIER_ALIASES,
                    TELEMETRY_EDIT_INTERVAL)  # noqa: F401
from database import (
    add_user, get_user, update_user, is_premium, is_banned, check_daily_limit,
    increment_daily, save_session, get_session, delete_session,
    set_caption, get_caption, del_caption, set_thumbnail, get_thumbnail,
    del_thumbnail, set_prefix, get_prefix, set_suffix, get_suffix,
    add_download, get_history, clear_history, add_bookmark, get_bookmarks,
    delete_bookmark, add_favorite, get_favorites, remove_favorite,
    set_language, toggle_notifications, toggle_silent, reset_settings,
    add_referral, add_feedback, test_connection, total_users,
    get_all_users, get_banned_users_list, get_premium_users_list,
    get_logged_users_list,
    get_active_users_today, get_new_users_today, get_top_users,
    total_downloads_count, total_bookmarks_count, get_all_feedback,
    search_user, set_maintenance, get_maintenance, set_fsub_channel,
    get_fsub_channel, delete_fsub, get_fsub_list, add_fsub_item,
    remove_fsub_item, update_fsub_item, clear_fsub_list,
    get_fsub_verify_label, set_fsub_verify_label,
    record_join_request, set_join_request_status, get_join_request,
    add_admin, remove_admin, is_admin,
    get_admins_list, clear_all_logs, get_bot_stats, add_premium,
    remove_premium, ban_user, unban_user, get_points, award_referral,
    redeem_points, set_qr, get_qr, delete_qr, add_payment, get_payments,
    reserve_daily, refund_daily, utcnow, sync_user_profile, get_display_name,
    set_user_chat, get_user_chat, find_user_chat_owner, clear_user_chat, mark_payment,
    get_user_channels, add_user_channel, remove_user_channel, channels_from_document,
    pick_channel_entry,
    set_engine_mode, get_engine_mode, set_user_engine, get_user_engine,
    get_engine_preference, has_models_access, has_private_access,
    set_models_access, set_private_access, record_engine_use, get_engine_stats,
    get_premium_tier, increment_channel_files, get_channel_files,
    set_dump_channel, get_dump_channel, delete_dump_channel,
    create_giveaway, get_active_giveaway, get_last_giveaway, update_giveaway,
    finish_giveaway, add_giveaway_participant, count_giveaway_participants,
    is_giveaway_participant, list_giveaway_participants,
    all_giveaway_participants, clear_giveaway_participants,
    ensure_giveaway_indexes, PICKER_SWEEP_FIELD,
    cleanup_old_records, add_stars_payment, get_stars_payment, complete_stars_payment,
    get_stars_payments,
    purge_created_bot_data,
    app_token_expired, app_token_days_left, expire_stale_app_tokens,
    create_app_token, get_app_token, get_active_app_token, revoke_app_token,
    list_app_tokens, count_app_tokens, mark_app_token_login, touch_app_token,
    register_app_user, increment_app_user_usage, get_app_user, list_app_users,
    count_app_users, add_app_activity, update_app_activity, get_app_activity,
    count_app_activity, cleanup_app_activity,
    set_app_apk, get_app_apk, get_app_config, set_app_base_url,
)  # noqa: F401

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_clients = {}
login_pending = {}
pending_action = {}
admin_pending = {}
#: user_id -> source message descriptor behind the reply-scoped /menu.
MESSAGE_MENU_PENDING = {}
active_downloads = {}
payment_pending = {}
#: token -> {"future", "owner_id", "question_msg", "token"} for channel custom caption questions.
caption_pending = {}
#: owner_id -> {"user_id": int, "days": int} while /addpremium waits for a tier.
premium_tier_pending = {}
#: user_id -> {"chat_id", "title", "username", "step"} for the /setchat wizard.
setchat_pending = {}
#: user_id -> wizard state of the /setfsub flow (owner adds a chat to the list).
fsub_pending = {}
#: chat_id -> asyncio.Lock() — one extraction at a time per dump channel.
channel_locks = {}
#: chat_id -> loop time of the last channel extraction (anti-ban rate limiting).
channel_last_request = {}


# --------------------------------------------------------------------------- #
#  Unicode small-caps font plumbing
#
#  Every user-visible string the bot sends goes through :func:`ui_text`, which
#  renders it in the small-caps font while leaving URLs, @mentions, /commands,
#  HTML tags and ``code`` spans untouched.  Extracted *content* (media captions,
#  copied text and the attribution watermark) is sent with plain ``.reply`` and
#  is never converted.
# --------------------------------------------------------------------------- #

def ui_text(text):
    return ui.smallcaps(text)


async def say(target, text, **kwargs):
    """Reply with small-caps UI copy (raw payload sends use ``target.reply``)."""
    sent = await target.reply(ui_text(text), **kwargs)
    track_reply_keyboard(reply_chat_id(target), kwargs.get("reply_markup"))
    return sent


async def say_edit(target, text, **kwargs):
    """Edit a message with small-caps UI copy."""
    return await target.edit(ui_text(text), **kwargs)


async def say_message(client, chat_id, text, **kwargs):
    sent = await client.send_message(chat_id, ui_text(text), **kwargs)
    track_reply_keyboard(chat_id, kwargs.get("reply_markup"))
    return sent


async def refresh_profile(user) -> None:
    """Re-check the Telegram name/username on every interaction.

    A user who renames themselves is therefore updated everywhere — lists,
    /userinfo, owner notifications and feedback all read the stored document,
    which this call keeps fresh.
    """
    if user is None or getattr(user, "id", None) is None:
        return
    username = getattr(user, "username", None)
    name = get_user_display_name(user, default=None)
    try:
        await sync_user_profile(user.id, name=name, username=username)
    except Exception as exc:  # never block a handler because of a rename
        print(f"[PROFILE SYNC FAILED] {exc}", flush=True)


# --------------------------------------------------------------------------- #
#  FloodWait / anti-ban guard
#
#  Every channel-dump request is rate limited, and whenever Telegram answers
#  with FloodWait the bot pauses for the requested amount of seconds instead of
#  crashing (or getting itself restricted).
# --------------------------------------------------------------------------- #

FLOODWAIT_MAX_RETRIES = 3


class FloodWaitPause(Exception):
    """Internal signal: Telegram asked us to pause before continuing."""

    def __init__(self, seconds: int, original: Exception | None = None):
        super().__init__(f"FloodWait: pausing {seconds}s")
        self.seconds = int(seconds)
        self.original = original


def floodwait_seconds(error) -> int:
    """Seconds to sleep for a FloodWait error (always at least 1)."""
    try:
        value = int(getattr(error, "value", 0) or 0)
    except (TypeError, ValueError):
        value = 0
    return max(1, value + 1)


async def floodwait_sleep(seconds, *, sleeper=asyncio.sleep):
    await sleeper(seconds)


async def floodwait_guard(call, *args, attempts: int = FLOODWAIT_MAX_RETRIES,
                          sleeper=asyncio.sleep, **kwargs):
    """Await ``call(*args, **kwargs)``, sleeping through FloodWait answers."""
    global BROADCAST_PAUSED_UNTIL
    for attempt in range(attempts + 1):
        try:
            return await call(*args, **kwargs)
        except FloodWait as error:
            BROADCAST_PAUSED_UNTIL = max(BROADCAST_PAUSED_UNTIL, time.monotonic() + floodwait_seconds(error))
            if attempt >= attempts:
                raise
            await sleeper(floodwait_seconds(error))


async def cleanup_message_later(message, delay=None, *, sleeper=asyncio.sleep):
    """Delete *message* after *delay* seconds (keeps dump channels tidy)."""
    delay = CHANNEL_CLEANUP_SECONDS if delay is None else delay
    await sleeper(delay)
    try:
        await message.delete()
    except Exception:
        pass


def schedule_cleanup(message, delay=None):
    """Fire-and-forget version of :func:`cleanup_message_later`."""
    try:
        return asyncio.get_running_loop().create_task(cleanup_message_later(message, delay))
    except RuntimeError:  # pragma: no cover - no running loop (sync callers)
        return None


# --------------------------------------------------------------------------- #
#  The picker keyboard is temporary
#
#  /setchat and /setdump hand Telegram's native chat chooser over through a
#  *reply* keyboard (a ``request_chat`` button).  A reply keyboard is chat
#  state, not message state: it stays on the screen until the bot sends a
#  message whose reply_markup is ``ReplyKeyboardRemove`` — deleting or editing
#  the message that carried it does nothing and ``one_time_keyboard`` merely
#  collapses it, leaving the button one tap away forever.
#
#  So the bot (1) remembers every chat it put a picker keyboard in, because
#  ``say`` / ``say_message`` watch the reply_markup of everything they send,
#  and (2) takes the keyboard off again on **every** way out of the flow — a
#  finished setup, /cancel, any other command, any other button.  A reply that
#  already carries ``ReplyKeyboardRemove`` clears the record by itself; a reply
#  that has to carry an inline menu instead (one message, one reply_markup)
#  gets a tiny silent message with the removal, deleted again at once.
# --------------------------------------------------------------------------- #

#: ``pending_action`` values for which a picker keyboard is what the bot awaits.
PICKER_ACTIONS = frozenset({"setchat_share", "setdump_share"})
#: Buttons that continue a picker flow instead of leaving it.
PICKER_FLOW_CALLBACKS = frozenset({"setchat:share", "setchat:check"})
#: Private chats (chat id == user id) that may still show a picker keyboard.
PICKER_KEYBOARD_SHOWN: set = set()
#: The one character of the throw-away message that carries the removal.
PICKER_DISMISS_TEXT = "⌨️"
#: Users already checked for a picker keyboard that an older build left behind.
PICKER_SWEPT: set = set()


def reply_chat_id(target):
    """Chat a reply goes to — in a private chat that is the user's own id."""
    chat_id = getattr(getattr(target, "chat", None), "id", None)
    if chat_id is None:
        chat_id = getattr(getattr(target, "from_user", None), "id", None)
    return chat_id


def track_reply_keyboard(chat_id, markup) -> None:
    """Note whether *chat_id* now shows, or no longer shows, a reply keyboard.

    Pure bookkeeping on the way out of ``say`` — it must never be the reason a
    reply fails, so an odd chat id is simply ignored.
    """
    if not isinstance(markup, (ReplyKeyboardMarkup, ReplyKeyboardRemove)):
        return
    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        return
    if isinstance(markup, ReplyKeyboardMarkup):
        PICKER_KEYBOARD_SHOWN.add(chat_id)
    else:
        PICKER_KEYBOARD_SHOWN.discard(chat_id)


def picker_flow_active(uid) -> bool:
    """True while a picker keyboard is what this user's flow is waiting on."""
    return pending_action.get(uid) in PICKER_ACTIONS or uid in setchat_pending


async def dismiss_picker_keyboard(chat_id, *, force: bool = False) -> bool:
    """Take a picker keyboard off *chat_id*'s screen; ``True`` when it was sent.

    Does nothing unless the chat is recorded as showing one (``force`` skips
    that check — used for keyboards an older build left behind).  The removal
    is a silent one-character message whose only job is to carry
    ``ReplyKeyboardRemove``; it is deleted again straight away.  Cosmetic by
    nature, so it never retries a FloodWait and never raises.
    """
    if chat_id is None:
        return False
    chat_id = int(chat_id)
    if not force and chat_id not in PICKER_KEYBOARD_SHOWN:
        return False
    #: Claim the record first: two exits in the same instant send one removal.
    was_recorded = chat_id in PICKER_KEYBOARD_SHOWN
    PICKER_KEYBOARD_SHOWN.discard(chat_id)
    try:
        sent = await floodwait_guard(
            bot.send_message, chat_id, PICKER_DISMISS_TEXT,
            reply_markup=ReplyKeyboardRemove(), disable_notification=True, attempts=0)
    except Exception as exc:
        if was_recorded:
            PICKER_KEYBOARD_SHOWN.add(chat_id)     # still there: the next exit retries
        print(f"[PICKER] could not remove the keyboard in chat={chat_id}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return False
    message_id = getattr(sent, "id", None)
    if message_id is not None:
        try:
            await floodwait_guard(bot.delete_messages, chat_id, message_id, attempts=0)
        except Exception as exc:
            print(f"[PICKER] left the one-character message in chat={chat_id}: "
                  f"{type(exc).__name__}: {exc}", flush=True)
    return True


async def say_with_picker(target, text, keyboard, *, fallback=None):
    """Send a picker prompt; if Telegram refuses the keyboard, send it without.

    A picker button is a ``request_chat`` reply keyboard.  Should Telegram ever
    reject that markup, the person must not be left with a silent bot: the
    prompt still goes out (with *fallback*, normally the inline Cancel button)
    and the typed link / @username / id keeps working.
    """
    try:
        return await say(target, text, reply_markup=keyboard)
    except FloodWait:
        raise
    except Exception as exc:
        print(f"[PICKER] keyboard refused ({type(exc).__name__}: {exc}); "
              "sending the prompt without it", flush=True)
        return await say(target, text, reply_markup=fallback)


async def sweep_stale_picker_keyboard(uid) -> bool:
    """Once per user: clear a picker keyboard an older build left on the screen.

    Earlier builds never removed the keyboard after a typed link, ``/cancel``,
    another command or ``/setdump`` — it stayed pinned under the chat for good.
    Nothing remembers who has one, so the first time a user is seen after this
    fix the bot sends the silent removal once and stores that fact in the user
    document (``PICKER_SWEEP_FIELD``).  Users created after the fix are born
    with the flag set, so the check costs them nothing.
    """
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return False
    if uid in PICKER_SWEPT:
        return False
    PICKER_SWEPT.add(uid)
    try:
        row = await get_user(uid)
        if not row or row.get(PICKER_SWEEP_FIELD):
            return False
        if picker_flow_active(uid) or uid in PICKER_KEYBOARD_SHOWN:
            #: A live picker owns its keyboard; the flow's own exits remove it.
            sent, done = False, True
        else:
            sent = await dismiss_picker_keyboard(uid, force=True)
            done = sent
        if done:
            await update_user(uid, {PICKER_SWEEP_FIELD: True})
        else:
            PICKER_SWEPT.discard(uid)      # Telegram refused: try again next time
        return sent
    except Exception as exc:
        PICKER_SWEPT.discard(uid)
        print(f"[PICKER] sweep failed for user={uid}: {type(exc).__name__}: {exc}", flush=True)
        return False


def parse_link(link):
    """Accept Telegram message URLs only, including /s/ previews and topics.

    The grammar lives in the **native C++ engine** (``native/restriction_engine``)
    which answers every message that reaches the bot; :func:`native_engine.parse_link`
    falls back to an equivalent Python implementation when no compiler is
    available, so the result never depends on the backend.
    """
    return native_engine.parse_link(link)


async def private_access(user_id):
    """True when this user may extract private/restricted links.

    ``has_private_access`` — the granular flag written by /addpremium — is
    authoritative, and it is only honoured while premium is actually live.
    Documents granted before the flag existed fall back to ``premium_source``,
    which is where "full/manual means private" used to be recorded.
    """
    if user_id == OWNER_ID:
        return True
    if not await is_premium(user_id):
        return False
    row = await get_user(user_id) or {}
    if row.get("has_private_access"):
        return True
    # Legacy grants: only a full (manual) tier unlocked private links; a
    # public-only grant or a points redemption never did.
    return row.get("premium_source") in {PREMIUM_SOURCE_MANUAL, PURCHASE_PREMIUM_SOURCE}


# --------------------------------------------------------------------------- #
#  Dual execution engines — Python Standard ⚙️ / C++ Turbo 🚀
#
#  engines.py owns the routing matrix (AUTO autoscaler + the two global locks),
#  telemetry.py samples the host, ui.py renders every string.  This section is
#  the glue: it reads the persisted mode and the user's ``models`` permission,
#  asks the controller for a decision and keeps the concurrency counter honest
#  while an extraction is in flight.
# --------------------------------------------------------------------------- #

#: The process-wide engine controller (autoscaler + global lock modes).
ENGINE_CONTROLLER = engines.CONTROLLER
#: The host sampler behind the live download HUD.
HOST_MONITOR = telemetry.MONITOR


async def _stored_engine_mode():
    """Read the persisted mode through the module global.

    Going through the global (instead of binding ``database.get_engine_mode``
    directly) is what lets the test fakes replace it.
    """
    return await get_engine_mode()


ENGINE_CONTROLLER.mode_provider = _stored_engine_mode
ENGINE_CONTROLLER.monitor.peak_threshold = ENGINE_PEAK_THRESHOLD


async def models_access(user_id) -> bool:
    """True when the user holds the ``models`` (C++ Turbo) permission."""
    if user_id == OWNER_ID:
        return True
    return bool(await has_models_access(user_id))


async def engine_preference_of(user_id, *, models: bool | None = None) -> str | None:
    """The engine this user picked in /models (``None`` when they never did)."""
    if models is None:
        models = await models_access(user_id)
    if not models:
        # Without the permission a stored preference must never take effect.
        return None
    return await get_user_engine(user_id)


async def resolve_engine_for(user_id, *, record: bool = True) -> engines.EngineDecision:
    """Which engine runs the next extraction for *user_id*.

    Reads the global controller mode, the user's ``models`` permission and
    their stored preference, then lets the controller apply the autoscaler.
    """
    await ENGINE_CONTROLLER.load_mode()
    models = await models_access(user_id)
    preference = await engine_preference_of(user_id, models=models)
    return ENGINE_CONTROLLER.decide(has_models=models, preference=preference,
                                    record=record)


async def engine_status_snapshot() -> dict:
    """Live controller state + the persisted per-engine counters, for /stats."""
    snapshot = ENGINE_CONTROLLER.snapshot()
    try:
        snapshot["stored"] = await get_engine_stats()
    except Exception as exc:  # analytics must never break a command
        print(f"[ENGINE STATS FAILED] {exc}", flush=True)
        snapshot["stored"] = {}
    return snapshot


async def record_engine_routing(decision) -> None:
    """Persist one routed extraction (best effort — never blocks a download)."""
    try:
        await record_engine_use(decision.engine)
    except Exception as exc:
        print(f"[ENGINE STATS FAILED] {exc}", flush=True)


async def set_engine_preference(user_id, engine):
    """Store the engine picked in /models and return the normalised id."""
    value = engines.normalize_engine(engine)
    await set_user_engine(user_id, value)
    return value


#: Injectable clock/sleeper for the transfer maths and the Python Standard speed
#: cap.  A test replaces both with a fake clock, which is what makes the ~3 MB/s
#: pacing provable without ever really waiting.
TRANSFER_CLOCK = time.monotonic
TRANSFER_SLEEPER = asyncio.sleep


def engine_speed_limit(decision) -> float:
    """MB/s cap of the resolved engine — ``0.0`` means "uncapped".

    ⚙️ Python Standard is throttled to ``config.ENGINE_PYTHON_SPEED_LIMIT_MBPS``
    (default 3 MB/s); 🚀 C++ Turbo is never capped.  Setting the constant to
    ``0`` disables the cap for Python Standard too.
    """
    engine = getattr(decision, "engine", None) or decision
    if engines.normalize_engine(engine) != ENGINE_PYTHON:
        return 0.0
    try:
        return max(0.0, float(ENGINE_PYTHON_SPEED_LIMIT_MBPS or 0.0))
    except (TypeError, ValueError):  # pragma: no cover - a bad env value
        return 0.0


def joined_channel(member):
    status = getattr(member.status, "value", member.status)
    return status in {"member", "administrator", "owner", "creator"} or (
        status == "restricted" and bool(getattr(member, "is_member", False)))


async def chat_membership_state(chat_id, user_id):
    """Membership probe that distinguishes "not a member" from "unknown".

    Returns ``("member"|"not_member"|"error", detail)``.  A network hiccup or a
    permission problem must never be reported as "not a member", otherwise a
    transient Telegram error would lock a perfectly fine user out.
    """
    try:
        member = await floodwait_guard(bot.get_chat_member, chat_id, user_id)
    except UserNotParticipant:
        return "not_member", "user is not a participant"
    except Exception as exc:
        return "error", f"{type(exc).__name__}: {exc}"
    if joined_channel(member):
        return "member", ""
    return "not_member", f"status={getattr(member, 'status', None)!r}"


async def fetch_join_requests(chat_id, limit: int = FSUB_JOINER_SCAN_LIMIT):
    """Every pending/approved joiner of *chat_id* (empty list when unsupported)."""
    getter = getattr(bot, "get_chat_join_requests", None)
    if getter is None:  # pragma: no cover - fork without the high-level helper
        return await raw_join_request_importers(chat_id)
    joiners = []
    async for joiner in getter(chat_id, limit=limit):
        joiners.append(joiner)
    return joiners


async def raw_join_request_importers(chat_id, limit: int = FSUB_JOINER_SCAN_LIMIT):
    """Raw MTProto fallback for forks without ``get_chat_join_requests``.

    Kept as documentation of the underlying call as well as a working path.
    Returns joiner-shaped objects so callers need no special casing.
    """
    peer = await bot.resolve_peer(chat_id)
    result = await bot.invoke(raw.functions.messages.GetChatInviteImporters(
        peer=peer,
        offset_date=0,
        offset_user=raw.types.InputUser(user_id=0, access_hash=0),
        limit=limit,
        requested=True,
    ))
    joiners = []
    for importer in getattr(result, "importers", None) or []:
        raw_user = getattr(importer, "user_id", None)
        user_id = getattr(raw_user, "user_id", None)
        if user_id is None:
            user_id = getattr(raw_user, "id", None)
        joiners.append(SimpleNamespace(
            user=SimpleNamespace(id=user_id),
            pending=True,
            date=getattr(importer, "date", None),
        ))
    return joiners


async def join_request_state(chat_id, user_id, *, skip_membership: bool = False) -> str:
    """``'member' | 'pending' | 'approved' | 'none'`` for a force-sub chat.

    Membership wins.  Otherwise the approve list is scanned: a request that is
    still waiting is ``pending``, one that was already approved is ``approved``.
    Any Telegram error (the bot not being an admin there, network problems)
    degrades to ``"none"`` after being logged — it is never raised.
    """
    if not skip_membership:
        state, detail = await chat_membership_state(chat_id, user_id)
        if state == "member":
            return "member"
        if state == "error":
            print(f"[FSUB] membership unknown for {chat_id}: {detail}", flush=True)
            return "none"
    try:
        joiners = await floodwait_guard(fetch_join_requests, chat_id)
    except ChatAdminRequired as exc:
        print(f"[FSUB] not an admin in {chat_id}: {exc}", flush=True)
        return "none"
    except Exception as exc:
        print(f"[FSUB] join-request scan failed for {chat_id}: {exc}", flush=True)
        return "none"
    for joiner in joiners or []:
        joiner_user = getattr(joiner, "user", None)
        if joiner_user is not None and getattr(joiner_user, "id", None) == user_id:
            return "pending" if getattr(joiner, "pending", False) else "approved"
    return "none"


async def get_user_client(user_id):
    if user_id in user_clients:
        client = user_clients[user_id]
        try:
            if await client.get_me():
                return client
        except:
            pass
        try:
            await client.stop()
        except:
            pass
        del user_clients[user_id]
    session = await get_session(user_id)
    if session:
        try:
            client = Client(
                f"user_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session,
                in_memory=True
            )
            await client.start()
            user_clients[user_id] = client
            return client
        except:
            await delete_session(user_id)
    return None


async def apply_custom_caption(user_id, original):
    custom = await get_caption(user_id)
    prefix = await get_prefix(user_id)
    suffix = await get_suffix(user_id)
    if custom:
        return custom
    result = original or ""
    if prefix:
        result = f"{prefix}\n{result}"
    if suffix:
        result = f"{result}\n{suffix}"
    if not prefix and not suffix:
        return original or ""
    return result.strip()


def attribution_text():
    return WATERMARK.format(bot_username=BOT_USERNAME)


async def apply_copy_caption_and_attribution(message, fetch_client, copied, source, premium, user_id, *, use_custom_caption: bool = True, copied_chat_id=None, overflow_target_chat_id=None):
    """Apply caption and attribution to a copied message.

    Free extractions add attribution at the end. Premium and owner extractions
    do not include attribution. Edits the copied message when feasible, or
    falls back to a separate attribution reply without re-downloading media.
    """
    credit = attribution_text() if not premium else None

    caption_media = any(
        getattr(source, kind, None)
        for kind in ("photo", "video", "document", "audio", "voice", "animation")
    )

    if caption_media:
        source_caption = getattr(source, "caption", None) or ""
        base_caption = await apply_custom_caption(user_id, source_caption) if use_custom_caption else source_caption
        if not premium:
            final_caption = f"{base_caption}\n{credit}" if base_caption else credit
        else:
            final_caption = base_caption

        if final_caption != source_caption:
            if ui.utf16_length(final_caption) <= 1024:
                editor = getattr(copied, "edit_caption", None)
                if editor:
                    try:
                        await editor(caption=final_caption, parse_mode=ParseMode.DISABLED)
                        return
                    except MessageNotModified:
                        return
                    except Exception:
                        pass
                client_editor = getattr(fetch_client, "edit_message_caption", None)
                copied_id = getattr(copied, "id", None)
                if client_editor and copied_id is not None:
                    try:
                        await client_editor(
                            chat_id=(copied_chat_id if copied_chat_id is not None
                                     else message.chat.id),
                            message_id=copied_id,
                            caption=final_caption,
                            parse_mode=ParseMode.DISABLED,
                        )
                        return
                    except MessageNotModified:
                        return
                    except Exception:
                        pass

            # Final caption exceeded 1024 or edit failed.
            if not premium:
                if base_caption != source_caption and ui.utf16_length(base_caption) <= 1024:
                    editor = getattr(copied, "edit_caption", None)
                    if editor:
                        try:
                            await editor(caption=base_caption, parse_mode=ParseMode.DISABLED)
                        except Exception:
                            pass
                    else:
                        client_editor = getattr(fetch_client, "edit_message_caption", None)
                        copied_id = getattr(copied, "id", None)
                        if client_editor and copied_id is not None:
                            try:
                                await client_editor(
                                    chat_id=(copied_chat_id if copied_chat_id is not None
                                             else message.chat.id),
                                    message_id=copied_id,
                                    caption=base_caption,
                                    parse_mode=ParseMode.DISABLED,
                                )
                            except Exception:
                                pass
                if overflow_target_chat_id is not None:
                    await bot.send_message(int(overflow_target_chat_id), credit,
                                           parse_mode=ParseMode.DISABLED)
                else:
                    await message.reply(credit, parse_mode=ParseMode.DISABLED)
        return

    source_text = getattr(source, "text", None)
    if source_text:
        base_text = source_text
        if not premium:
            final_text = f"{base_text}\n{credit}" if base_text else credit
        else:
            final_text = base_text

        if final_text != source_text:
            if ui.utf16_length(final_text) <= 4096:
                editor = getattr(copied, "edit_text", None)
                if editor:
                    try:
                        await editor(final_text, parse_mode=ParseMode.DISABLED)
                        return
                    except MessageNotModified:
                        return
                    except Exception:
                        pass
                client_editor = getattr(fetch_client, "edit_message_text", None)
                copied_id = getattr(copied, "id", None)
                if client_editor and copied_id is not None:
                    try:
                        await client_editor(
                            chat_id=(copied_chat_id if copied_chat_id is not None
                                     else message.chat.id),
                            message_id=copied_id,
                            text=final_text,
                            parse_mode=ParseMode.DISABLED,
                        )
                        return
                    except MessageNotModified:
                        return
                    except Exception:
                        pass

            if not premium:
                if overflow_target_chat_id is not None:
                    await bot.send_message(int(overflow_target_chat_id), credit,
                                           parse_mode=ParseMode.DISABLED)
                else:
                    await message.reply(credit, parse_mode=ParseMode.DISABLED)
        return

    # Stickers, video notes and non-caption media
    if not premium:
        if overflow_target_chat_id is not None:
            await bot.send_message(int(overflow_target_chat_id), credit,
                                   parse_mode=ParseMode.DISABLED)
        else:
            await message.reply(credit, parse_mode=ParseMode.DISABLED)


async def add_copy_attribution(message, fetch_client, copied, source):
    user_id = message.from_user.id
    premium = user_id == OWNER_ID or await is_premium(user_id)
    await apply_copy_caption_and_attribution(message, fetch_client, copied, source, premium, user_id)


# --------------------------------------------------------------------------- #
#  Shared upsell responses (private access + daily limit)
# --------------------------------------------------------------------------- #

async def private_link_keyboard():
    """The two options for a private link: unlimited in the app, or premium DM."""
    config = await get_app_config()
    apk = config.get("apk") or {}
    return ui.private_access_keyboard(config.get("base_url"),
                                      has_apk=bool(apk.get("file_id")))


async def reply_private_access(message):
    """Private link without access → app download first, premium DM second."""
    await say(message, ui.app_private_link_text(),
              reply_markup=await private_link_keyboard())


async def edit_private_access(status):
    await say_edit(status, ui.app_private_link_text(),
                   reply_markup=await private_link_keyboard())


async def reply_daily_limit(message, used=None):
    """Free quota exhausted → detailed reason + premium/referral CTA row."""
    await say(message, ui.daily_limit_text(used=used), reply_markup=ui.daily_limit_keyboard())


async def edit_daily_limit(status, used=None):
    await say_edit(status, ui.daily_limit_text(used=used), reply_markup=ui.daily_limit_keyboard())


async def check_access(message, *, enforce_fsub: bool = True):
    user_id = message.from_user.id
    if await is_banned(user_id):
        await say(message, "🚫 You are banned from this bot!")
        return False
    if await get_maintenance() and user_id != OWNER_ID:
        await say(message, "🔧 **Bot is under maintenance!**\n\nPlease try again later.")
        return False
    if enforce_fsub and user_id != OWNER_ID:
        items = await get_fsub_list()
        for item in items:
            state, detail = await chat_membership_state(item["chat_id"], user_id)
            if state == "error":
                # Never lock a user out because Telegram could not answer.
                print(f"[FSUB] check skipped for {item['chat_id']}: {detail}", flush=True)
                continue
            if state == "member":
                continue
            # Not a member: a pending or approved join request also counts.
            try:
                request_state = await join_request_state(item["chat_id"], user_id,
                                                         skip_membership=True)
            except Exception as exc:  # defensive: fail open, never lock out
                print(f"[FSUB] join-request check failed for {item['chat_id']}: {exc}", flush=True)
                request_state = "none"
            if request_state in {"pending", "approved"}:
                continue
            page = 0
            await say(message, ui.fsub_text(items, page),
                      reply_markup=ui.fsub_keyboard(items, page, await get_fsub_verify_label()))
            return False
    return True


@dataclass(frozen=True)
class DeliveryTarget:
    """Where one extraction is delivered, and by whom.

    Every delivery path in the bot resolves its destination through
    :func:`resolve_delivery_target` instead of reading ``message.chat.id``
    inline, so the Saved Messages trap can never silently come back.

    ``copy_client``   the client allowed to run a server-side
                      ``copy_message``/``forward_messages`` — ``None`` when that
                      shortcut is illegal for this destination.
    ``upload_client`` the client used for the download-then-upload path (always
                      the bot: only the bot may post into the bot chat).
    """

    chat_id: int
    copy_client: object | None
    upload_client: object
    reason: str = "direct"

    @property
    def native_copy(self) -> bool:
        """True when the fast server-side copy may be used."""
        return self.copy_client is not None


def is_user_session(client, user_id=None) -> bool:
    """True when *client* is a logged-in **user** account, not the bot.

    The detection is deliberately positive rather than "anything that is not the
    bot": a client is a user session when it is the one this user registered with
    /login, when it declares itself as such, when Telegram reports a non-bot
    ``me``, or when it is a real pyrogram/kurigram ``Client`` without a bot
    token.  Everything else (the bot itself, a plain stand-in object) is treated
    as bot-like, which keeps the server-side copy available.
    """
    if client is None or client is bot:
        return False
    if getattr(client, "is_user_client", False):
        return True
    if user_id is not None and user_clients.get(user_id) is client:
        return True
    me = getattr(client, "me", None)
    if me is not None:
        is_bot = getattr(me, "is_bot", None)
        if is_bot is not None:
            return not bool(is_bot)
    if isinstance(client, Client):
        return not bool(getattr(client, "bot_token", None))
    return False


def resolve_delivery_target(message, user_id, fetch_client) -> DeliveryTarget:
    """Resolve and validate the destination of one delivery.

    **The Saved Messages trap.** For private/restricted content ``fetch_client``
    is the *user's own* session, and in a private chat with the bot
    ``message.chat.id`` **is that same user's id**.  "Send to my own id through
    my own session" is Telegram's Saved Messages, so the content would land in
    the user's personal cloud instead of the bot chat.  Inside a registered dump
    channel the destination is the channel id, which is why that path was always
    fine.

    Round 14 changed the answer for the private-chat case.  Refusing the copy
    there used to force the **download → re-upload** path, which is the one
    thing the bot must never do with restricted content: the bytes then stream
    through this server.  So instead of giving up on the copy, the user's own
    session is pointed at the **bot's chat** — the private chat the user shares
    with the bot, whose id is the bot's id and not the user's.  The copy lands
    there directly, the server never sees a byte, and the echo the bot receives
    back is swallowed exactly once by :func:`consume_echo_guard`.

    The rule is therefore: **a user session may never deliver to its own id**,
    and when that combination is detected the destination becomes the bot's own
    chat rather than a download.  Caption and attribution behaviour is identical
    on whichever path ends up delivering.
    """
    chat = getattr(message, "chat", None)
    raw_chat_id = getattr(chat, "id", None)
    try:
        chat_id = int(raw_chat_id)
    except (TypeError, ValueError):
        # No usable destination at all: fall back to the requester's id so the
        # bot path still has somewhere to post, and never allow a native copy.
        return DeliveryTarget(int(user_id or 0), None, bot, reason="no_chat_id")

    try:
        own_id = int(user_id)
    except (TypeError, ValueError):
        own_id = None

    if own_id is not None and chat_id == own_id and is_user_session(fetch_client, own_id):
        # Private chat + the user's own session = Saved Messages.  Point the
        # session at the bot's own chat instead: the copy is made there by the
        # user's account, so nothing is ever downloaded onto this server.
        bot_id = bot_self_id()
        if bot_id and int(bot_id) != int(chat_id):
            return DeliveryTarget(int(bot_id), fetch_client, bot,
                                  reason="bot_dm_native_copy")
        return DeliveryTarget(chat_id, None, bot, reason="saved_messages_guard")

    return DeliveryTarget(chat_id, fetch_client, bot, reason="direct")


# --------------------------------------------------------------------------- #
#  The echo guard — swallow a native copy exactly once
# --------------------------------------------------------------------------- #
#: user_id -> {"chat_id", "message_id", "expires"} while the bot waits for the
#: copy it asked the user's session to make.  A user session posting into the
#: bot's chat produces an ordinary incoming message, so without this the bot
#: would read its own delivery as a fresh request and extract it a second time.
ECHO_GUARD: dict = {}


def arm_echo_guard(user_id, chat_id=None, message_id=None) -> None:
    """Watch for the echo of the copy that is about to land in the bot's chat."""
    ECHO_GUARD[int(user_id)] = {
        "chat_id": int(chat_id) if chat_id is not None else None,
        "message_id": int(message_id) if message_id is not None else None,
        "expires": time.monotonic() + float(ECHO_SWALLOW_WINDOW_SECONDS),
    }


def consume_echo_guard(user_id, message=None) -> bool:
    """Swallow the echo of a native copy — **once**, and only while it is live.

    Returns ``True`` when *message* is the copy the bot itself caused: the
    caller must then stop without extracting, replying or editing anything.
    A guard that has expired is dropped rather than honoured, so a message that
    arrives long after the copy is treated as a brand-new request.
    """
    guard = ECHO_GUARD.get(int(user_id))
    if not guard:
        return False
    if time.monotonic() > float(guard.get("expires") or 0.0):
        ECHO_GUARD.pop(int(user_id), None)
        return False
    #: The guard is single-use by design: one copy, one swallow.
    ECHO_GUARD.pop(int(user_id), None)
    print(f"[ECHO SWALLOWED] user={user_id} msg={getattr(message, 'id', None)} "
          f"— the copy the bot asked for, not a new request", flush=True)
    return True


class DumpWorkspaceError(RuntimeError):
    """A configured workspace must never silently become a direct delivery."""


async def dump_permissions(chat_id):
    try:
        me = getattr(bot, "me", None) or await floodwait_guard(bot.get_me)
        member = await floodwait_guard(bot.get_chat_member, int(chat_id), me.id)
        status = str(getattr(getattr(member, "status", None), "value",
                             getattr(member, "status", ""))).lower()
        owner = status in {"owner", "creator"}
        admin = owner or status == "administrator"
        rights = getattr(member, "privileges", None)
        post = admin and (owner or getattr(rights, "can_post_messages", None) is True)
        delete = admin and (owner or getattr(rights, "can_delete_messages", None) is True)
        return {"post": post, "delete": delete, "ready": post and delete,
                "reason": "ok" if post and delete else
                "not_admin" if not admin else "no_post_rights" if not post else "no_delete_rights"}
    except Exception:
        return {"post": None, "delete": None, "ready": False, "reason": "error"}


async def require_dump_workspace(entry):
    permissions = await dump_permissions(entry["chat_id"])
    if not permissions["ready"]:
        raise DumpWorkspaceError("Dump workspace unavailable. " +
                                 ui.dump_admin_failed_text(permissions["reason"]))


async def custom_caption_in_use(user_id) -> bool:
    """True when the user has a custom caption, prefix or suffix stored.

    This is the whole definition of "this user is using a custom caption":
    :func:`apply_custom_caption` has nothing to change without one of the three.
    """
    return bool(await get_caption(user_id) or await get_prefix(user_id)
                or await get_suffix(user_id))


async def staging_entry_for(user_id, *, use_custom_caption: bool = True):
    """The owner's dump entry — but only when *this* user's link belongs in it.

    The dump channel carries users' downloads and messages, and only those of a
    user whose custom caption is in play: content is downloaded into the dump,
    captioned there and copied from there to the user.  Everything else is
    delivered directly, so this returns ``None`` when

    * no dump channel is connected,
    * the caller already decided against the custom caption for this link
      (``use_custom_caption=False`` — the channel flow asks per batch), or
    * the user has no caption, prefix or suffix stored.
    """
    if not use_custom_caption:
        return None
    entry = await get_dump_channel()
    if not entry:
        return None
    if not await custom_caption_in_use(user_id):
        return None
    return entry


async def workspace_text(dump_id, text):
    try:
        staged = await floodwait_guard(bot.send_message, int(dump_id), text,
                                      parse_mode=ParseMode.DISABLED)
    except Exception as exc:
        raise DumpWorkspaceError("Cannot post to the dump workspace. Check /dump permissions and Telegram restrictions.") from exc
    if getattr(staged, "id", None) is None:
        raise DumpWorkspaceError("Dump staging returned no message. Check channel restrictions and /dump.")
    DUMP_MIRROR.schedule_delete(dump_id, staged.id)
    return staged


async def finish_workspace_copy(dump_id, staged, final_chat_id):
    """Only a fresh copy reaches the audience; keep TTL retry on delete failure."""
    try:
        return await floodwait_guard(bot.copy_message, chat_id=int(final_chat_id),
                                    from_chat_id=int(dump_id), message_id=int(staged.id))
    except Exception as exc:
        raise DumpWorkspaceError("Cannot copy the finished dump message. Check Telegram "
                                 "content restrictions and destination permissions; no direct fallback was sent.") from exc
    finally:
        await DUMP_MIRROR.delete_now(dump_id, staged.id)


async def customize_workspace_copy(client, staged, source, uid, premium, use_custom, dump_id):
    """Edit only the workspace. Return overflow text, never send it to a recipient here."""
    is_text = bool(getattr(source, "text", None))
    captionable = any(getattr(source, kind, None) for kind in
                      ("photo", "video", "document", "audio", "voice", "animation"))
    original = (getattr(source, "text", None) if is_text else
                getattr(source, "caption", None)) or ""
    body = await apply_custom_caption(uid, original) if use_custom else original
    if not premium:
        body = f"{body}\n{attribution_text()}" if body else attribution_text()
    limit = 4096 if is_text else 1024
    if not is_text and not captionable:
        return body
    if body == original:
        return None
    # Preserve all content when it cannot fit; clear the stage's old caption,
    # or use the first full text chunk and deliver the remainder as staged text.
    overflow = None
    if ui.utf16_length(body) > limit:
        if is_text:
            chunks = list(ui.split_text(body, limit))
            body, overflow = chunks[0], "".join(chunks[1:])
        else:
            body, overflow = "", body
    editor = getattr(staged, "edit_text" if is_text else "edit_caption", None)
    try:
        if editor:
            await floodwait_guard(editor, body, parse_mode=ParseMode.DISABLED)
        else:
            editor = getattr(client, "edit_message_text" if is_text else "edit_message_caption")
            await floodwait_guard(editor, chat_id=dump_id, message_id=staged.id,
                                  **{"text" if is_text else "caption": body},
                                  parse_mode=ParseMode.DISABLED)
    except MessageNotModified:
        pass
    except Exception as exc:
        raise DumpWorkspaceError("Could not edit the dump staging copy; nothing was edited at the destination.") from exc
    return overflow


DUMP_STAGED_COPY = "dump_staged"
DUMP_MIRRORED_COPY = "dump_mirrored"


async def try_native_copy(message, fetch_client, chat_target, msg_id, *, use_custom_caption: bool = True):
    user_id = message.from_user.id

    print(
        f"[COPY TRY] chat={chat_target}, msg_id={msg_id}, user={user_id}",
        flush=True
    )

    #: Every delivery resolves its destination through the same guard, so a
    #: user session can never be asked to post to its own id (Saved Messages).
    target = resolve_delivery_target(message, user_id, fetch_client)
    if not target.native_copy:
        print(f"[COPY SKIPPED] {target.reason}: delivering through the bot instead",
              flush=True)
        return False

    try:
        premium = user_id == OWNER_ID or await is_premium(user_id)
        msg = await fetch_client.get_messages(chat_target, msg_id)
        if not msg or getattr(msg, "empty", False):
            return False
        print(f"[COPY MESSAGE] chat={msg.chat.id}, msg_id={msg.id}", flush=True)
    except FloodWait as error:
        print(f"[COPY FLOODWAIT] {error}", flush=True)
        raise FloodWaitPause(floodwait_seconds(error), error)
    except Exception as error:
        print(f"[COPY FAILED] {type(error).__name__}: {error}", flush=True)
        return False

    #: Only a user whose custom caption is in play is staged through the dump;
    #: every other link is copied straight to its destination.
    dump_entry = await staging_entry_for(user_id, use_custom_caption=use_custom_caption)
    dump_chat_id = int(dump_entry["chat_id"]) if dump_entry else None
    can_stage = dump_chat_id is not None

    if can_stage:
        await require_dump_workspace(dump_entry)
        stage_client = target.copy_client
        staged = await DUMP_MIRROR.stage_copy(stage_client, msg.chat.id, msg.id, label="extraction")
        if staged is None and stage_client is not bot:
            stage_client = bot
            staged = await DUMP_MIRROR.stage_copy(bot, msg.chat.id, msg.id, label="extraction")
        if staged is None:
            # Telegram may forbid native copying of the SOURCE. The fallback
            # still uploads to this same workspace, never to the recipient.
            return False
        if getattr(staged, "id", None) is None:
            raise DumpWorkspaceError("Dump staging returned no message id; delivery stopped.")
        final_chat_id = int(message.chat.id) if target.reason == "bot_dm_native_copy" else target.chat_id
        try:
            overflow = await customize_workspace_copy(stage_client, staged, msg, user_id,
                                                       premium, use_custom_caption, dump_chat_id)
        except BaseException:
            await DUMP_MIRROR.delete_now(dump_chat_id, staged.id)
            raise
        await finish_workspace_copy(dump_chat_id, staged, final_chat_id)
        for chunk in ui.split_text(overflow or "", 4096):
            extra = await workspace_text(dump_chat_id, chunk)
            await finish_workspace_copy(dump_chat_id, extra, final_chat_id)
        return DUMP_STAGED_COPY

    # Direct delivery: no dump is connected, or this user has no custom caption.
    try:
        copied = await target.copy_client.copy_message(
            chat_id=target.chat_id,
            from_chat_id=msg.chat.id,
            message_id=msg.id
        )
    except FloodWait as error:
        print(f"[COPY FLOODWAIT] {error}", flush=True)
        raise FloodWaitPause(floodwait_seconds(error), error)
    except Exception as error:
        print(f"[COPY FAILED] {type(error).__name__}: {error}", flush=True)
        return False

    try:
        await apply_copy_caption_and_attribution(
            message, target.copy_client, copied, msg, premium, user_id,
            use_custom_caption=use_custom_caption,
        )
    except Exception as error:
        print(f"[COPY CAPTION FAILED] {type(error).__name__}: {error}", flush=True)
        if not premium:
            try:
                await message.reply(attribution_text(), parse_mode=ParseMode.DISABLED)
            except Exception:
                pass

    if target.reason == "bot_dm_native_copy":
        arm_echo_guard(user_id, target.chat_id, getattr(copied, "id", None))

    print("[COPY SUCCESS]", flush=True)
    return True


async def fetch_and_send(message, status, fetch_client, chat_target, msg_id, *,
                         enforce_fsub: bool = True, cleanup_errors: bool = False,
                         cleanup_delay=None, use_custom_caption: bool = True,
                         engine=None):
    """Enforce access and atomically reserve a free slot on every extraction path.

    ``cleanup_errors`` deletes the error status after
    :data:`config.CHANNEL_CLEANUP_SECONDS` seconds, which keeps dump channels
    tidy.  FloodWait answers are absorbed: the bot sleeps for the requested
    amount of seconds and retries instead of crashing.

    ``engine`` is a pre-resolved :class:`engines.EngineDecision` (a dump-channel
    batch resolves once and reuses it).  When it is omitted the engine is
    resolved here from the global controller mode, the user's ``models``
    permission and their stored preference.  Either way the extraction holds a
    concurrency slot, which is the signal the AUTO autoscaler scales on.
    """
    uid = message.from_user.id
    if not await check_access(message, enforce_fsub=enforce_fsub):
        return False
    if (isinstance(chat_target, int) or fetch_client is not bot) and not await private_access(uid):
        await edit_private_access(status)
        return False
    await ensure_user(message.from_user)
    reserved = uid != OWNER_ID and not await is_premium(uid)
    reservation_date = utcnow()
    if reserved and not await reserve_daily(uid, FREE_DAILY_LIMIT, reservation_date):
        await edit_daily_limit(status)
        return False
    decision = engine if isinstance(engine, engines.EngineDecision) \
        else await resolve_engine_for(uid)
    result = False
    try:
        # One concurrency slot per real extraction: this is what the autoscaler
        # counts, so the counter stays truthful even when requests overlap.
        with ENGINE_CONTROLLER.slot(decision):
            retries = 0
            while True:
                try:
                    result = await _fetch_and_send(
                        message, status, fetch_client, chat_target, msg_id,
                        cleanup_errors=cleanup_errors, cleanup_delay=cleanup_delay,
                        use_custom_caption=use_custom_caption, engine=decision,
                    )
                    break
                except FloodWaitPause as pause:
                    retries += 1
                    print(f"[FLOODWAIT] pausing {pause.seconds}s (attempt {retries})", flush=True)
                    if retries > FLOODWAIT_MAX_RETRIES:
                        await say_edit(status, ui.channel_floodwait_text(pause.seconds))
                        result = False
                        break
                    await floodwait_sleep(pause.seconds)
                except FloodWait as error:
                    seconds = floodwait_seconds(error)
                    retries += 1
                    print(f"[FLOODWAIT] pausing {seconds}s (attempt {retries})", flush=True)
                    if retries > FLOODWAIT_MAX_RETRIES:
                        result = False
                        break
                    await floodwait_sleep(seconds)
        print(f"[ENGINE] user={uid} engine={decision.engine} mode={decision.mode} "
              f"reason={decision.reason} concurrent={ENGINE_CONTROLLER.concurrent}",
              flush=True)
        await record_engine_routing(decision)
        if result is True:
            await increment_daily(uid, count_daily=not reserved)
        return result
    finally:
        if reserved and result is not True:
            await refund_daily(uid, reservation_date)


async def _fetch_and_send(message, status, fetch_client, chat_target, msg_id, *,
                          cleanup_errors: bool = False, cleanup_delay=None,
                          use_custom_caption: bool = True, engine=None):
    user_id = message.from_user.id
    file_path = None
    thumb_path = None
    delivered = False
    dm_status = None
    job_id = None
    decision = engine if isinstance(engine, engines.EngineDecision) \
        else await resolve_engine_for(user_id)
    engine_key = decision.engine

    try:
        copied = await try_native_copy(
            message,
            fetch_client,
            chat_target,
            msg_id,
            use_custom_caption=use_custom_caption,
        )

        if copied:
            delivered = True
            #: A staged copy is cleaned inside try_native_copy; a direct copy is
            #: left exactly as delivered — nothing is mirrored into the dump.
            await status.delete()
            await add_download(user_id, f"msg_{msg_id}", "copied")
            return True

        msg = await fetch_client.get_messages(chat_target, msg_id)
        if not msg or msg.empty:
            await say_edit(
                status,
                ui.channel_not_found_text() if cleanup_errors else "❌ Message not found.",
            )
            if cleanup_errors:
                # Channels stay clean: the notice removes itself quickly.
                schedule_cleanup(status, cleanup_delay)
            return False

        if not msg.media:
            if msg.text:
                premium = await is_premium(user_id) or user_id == OWNER_ID
                dump_entry = await staging_entry_for(
                    user_id, use_custom_caption=use_custom_caption)
                credited = (await apply_custom_caption(user_id, msg.text)
                            if dump_entry and use_custom_caption else msg.text)
                if not premium:
                    credited = f"{credited}\n{attribution_text()}"
                final_chat_id = int(message.chat.id)
                if dump_entry:
                    await require_dump_workspace(dump_entry)
                for chunk in ui.split_text(credited, 4096):
                    if dump_entry:
                        stage = await workspace_text(dump_entry["chat_id"], chunk)
                        await finish_workspace_copy(dump_entry["chat_id"], stage, final_chat_id)
                    else:
                        await message.reply(chunk, parse_mode=ParseMode.DISABLED)
                    delivered = True
                await add_download(user_id, f"msg_{msg_id}", "text")
                await status.delete()
                return True
            else:
                await say_edit(status, "❌ No content available.")
                return False

        premium = user_id == OWNER_ID or await is_premium(user_id)
        max_size = 2000 * 1024 * 1024 if premium else 50 * 1024 * 1024
        file_size = 0
        if msg.video:
            file_size = msg.video.file_size
        elif msg.document:
            file_size = msg.document.file_size
        elif msg.audio:
            file_size = msg.audio.file_size

        #: A dump channel gets the "limit reached — back to the bot" wording
        #: with an open-bot url= button; private chat keeps the detailed sizes.
        in_channel = is_channel_context(message)
        if file_size > max_size:
            if in_channel:
                await say_edit(
                    status,
                    ui.channel_limit_text("size", size_mb=file_size / 1024 / 1024),
                    reply_markup=ui.open_bot_keyboard(),
                )
            else:
                await say_edit(status,
                    f"❌ **File too large!**\n\n"
                    f"📦 Size: {file_size / 1024 / 1024:.1f} MB\n"
                    f"🆓 Free limit: 50 MB\n"
                    f"💎 Premium limit: 2 GB"
                )
            return False

        is_channel = in_channel or message.chat.id != user_id
        is_private_content = fetch_client is not bot

        if is_channel and not is_private_content:
            try:
                dm_status = await bot.send_message(user_id, "⬇️ Downloading...")
                if dm_status and getattr(dm_status, "id", None):
                    job_id = str(dm_status.id)
            except Exception:
                dm_status = None
                job_id = None

        if not job_id:
            job_id = str(status.id)

        pause_event = asyncio.Event()
        pause_event.set()
        job = {
            "user_id": user_id,
            "event": pause_event,
            "paused": False,
            "task": asyncio.current_task(),
            "last_update": 0,
            # Which engine is serving this job (shown in the HUD).
            "engine": engine_key,
            "mode": decision.mode,
        }
        active_downloads[job_id] = job

        #: Live transfer maths: percent, smoothed MB/s and ETA for the HUD.
        meter = telemetry.TransferMeter(file_size, clock=TRANSFER_CLOCK)
        #: ⚙️ Python Standard is paced to config.ENGINE_PYTHON_SPEED_LIMIT_MBPS
        #: by a token bucket; 🚀 C++ Turbo runs uncapped (rate 0 = no pacing).
        #: Both share the meter's clock, so the HUD speed line reports exactly
        #: the rate the throttle is producing.
        throttle = telemetry.SpeedThrottle(
            engine_speed_limit(decision),
            burst_seconds=ENGINE_PYTHON_SPEED_BURST_SECONDS,
            clock=TRANSFER_CLOCK, sleeper=TRANSFER_SLEEPER,
        )

        async def telemetry_sample():
            """One host reading (CPU/RAM/ping), or ``None`` when unavailable.

            Telemetry must never break a download: a failed probe simply leaves
            that HUD value as ``--``.
            """
            if not ui.telemetry_enabled():
                return None
            try:
                return await HOST_MONITOR.sample()
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[TELEMETRY FAILED] {exc}", flush=True)
                return None

        async def hud(stage="Downloading", percent=None, state=None, paused=False):
            return ui.telemetry_hud(engine_key, percent, sample=await telemetry_sample(),
                                    state=state, stage=stage, paused=paused)

        starting = await hud(percent=meter.state.percent, state=meter.state)
        if dm_status:
            await say_edit(dm_status, starting, reply_markup=ui.download_controls(job_id))
            await say_edit(status, ui.channel_download_notice(hud=starting),
                           reply_markup=ui.open_bot_keyboard())
        else:
            await say_edit(status, starting, reply_markup=ui.download_controls(job_id))

        async def download_progress(current, total):
            if job.get("cancelled"):
                raise asyncio.CancelledError()
            was_paused = job["paused"]
            await pause_event.wait()
            if job.get("cancelled"):
                raise asyncio.CancelledError()
            if was_paused:
                # A paused transfer must not come back with a full bucket.
                throttle.resume()

            #: Pace *before* the meter samples, so the HUD reports the throttled
            #: rate truthfully instead of the raw line rate.  One comparison and
            #: at most one sleep per chunk — no busy-wait, no extra API call.
            await throttle.pace_to(current)

            now = asyncio.get_running_loop().time()
            state = meter.update(current, total)
            if now - job["last_update"] < TELEMETRY_EDIT_INTERVAL and state.percent < 100:
                return
            job["last_update"] = now
            text = await hud(percent=state.percent, state=state, paused=job["paused"])
            controls = ui.download_controls(job_id, job["paused"])
            if dm_status:
                try:
                    await say_edit(dm_status, text, reply_markup=controls)
                except Exception:
                    pass
                try:
                    await say_edit(
                        status,
                        ui.channel_download_notice(state.percent, job["paused"], hud=text),
                        reply_markup=ui.open_bot_keyboard()
                    )
                except Exception:
                    pass
            else:
                try:
                    await say_edit(status, text, reply_markup=controls)
                except Exception:
                    pass

        #: 🚀 C++ Turbo pipes a small-enough file straight through memory: the
        #: downloader returns a ``BytesIO`` that is handed to the uploader as it
        #: is, so the payload is never written to disk and never re-read.  Above
        #: the budget — and on every ⚙️ Python Standard job — the transfer keeps
        #: the streamed-to-disk path, which bounds RAM for multi-GB files.
        zero_copy = bool(decision.engine_object.zero_copy) \
            and bool(file_size) and int(file_size) <= ENGINE_ZERO_COPY_MAX_BYTES
        file_path = await fetch_client.download_media(
            msg, progress=download_progress, in_memory=zero_copy)
        if not file_path:
            if dm_status:
                try:
                    await say_edit(dm_status, "❌ Download failed.", reply_markup=None)
                except Exception:
                    pass
            await say_edit(status, "❌ Download failed.", reply_markup=None)
            return False

        meter.finish()
        uploading = await hud(stage="Uploading", percent=100, state=meter.state)
        if dm_status:
            try:
                await say_edit(dm_status, uploading, reply_markup=None)
            except Exception:
                pass
        await say_edit(status, uploading, reply_markup=None)

        premium = user_id == OWNER_ID or await is_premium(user_id)
        #: Staged through the dump only for a user whose custom caption is in play.
        dump_entry = await staging_entry_for(user_id, use_custom_caption=use_custom_caption)
        if use_custom_caption:
            caption = (await apply_custom_caption(user_id, msg.caption)
                       if premium or dump_entry else (msg.caption or ""))
        else:
            caption = msg.caption or ""
        if not premium:
            credit = attribution_text()
            caption = f"{caption}\n{credit}" if caption else credit
        #: Destination resolved (and validated) exactly once for this delivery.
        delivery = resolve_delivery_target(message, user_id, fetch_client)
        chat_id = delivery.chat_id
        uploader = delivery.upload_client
        if delivery.reason == "bot_dm_native_copy":
            #: Native copies from a user session land in the bot's inbox. If
            #: that fast path failed and bytes must be uploaded, send the
            #: fallback back to the requesting user's actual private chat.
            chat_id = int(getattr(message.chat, "id", user_id))
        overflow_caption = caption if ui.utf16_length(caption) > 1024 else None
        if overflow_caption:
            if not dump_entry and not premium and ui.utf16_length(msg.caption or "") <= 1024:
                # Telegram's caption cap leaves no room for the attribution:
                # keep the complete original on the media, then send the credit.
                caption = msg.caption or ""
                overflow_caption = attribution_text()
            else:
                caption = None

        thumb_id = await get_thumbnail(user_id)
        if thumb_id and (msg.video or msg.document):
            try:
                thumb_path = await bot.download_media(thumb_id)
            except:
                pass

        dump_chat_id = int(dump_entry["chat_id"]) if dump_entry else None
        stage_upload = dump_entry is not None
        if stage_upload:
            await require_dump_workspace(dump_entry)
            uploader = bot
        upload_chat_id = dump_chat_id if stage_upload else chat_id

        async def upload_media(destination):
            if msg.photo:
                return await uploader.send_photo(destination, file_path, caption=caption,
                                                 parse_mode=ParseMode.DISABLED)
            if msg.video:
                return await uploader.send_video(destination, file_path, caption=caption,
                                                 thumb=thumb_path, parse_mode=ParseMode.DISABLED)
            if msg.document:
                return await uploader.send_document(destination, file_path, caption=caption,
                                                    thumb=thumb_path, parse_mode=ParseMode.DISABLED)
            if msg.audio:
                return await uploader.send_audio(destination, file_path, caption=caption,
                                                 parse_mode=ParseMode.DISABLED)
            if msg.voice:
                return await uploader.send_voice(destination, file_path, caption=caption,
                                                 parse_mode=ParseMode.DISABLED)
            if msg.video_note:
                return await uploader.send_video_note(destination, file_path)
            if msg.sticker:
                return await uploader.send_sticker(destination, file_path)
            if msg.animation:
                return await uploader.send_animation(destination, file_path, caption=caption,
                                                     parse_mode=ParseMode.DISABLED)
            return await uploader.send_document(destination, file_path, caption=caption,
                                                parse_mode=ParseMode.DISABLED)

        try:
            uploaded = await floodwait_guard(upload_media, upload_chat_id)
        except Exception as exc:
            if stage_upload:
                raise DumpWorkspaceError("Cannot upload to the dump workspace. Check /dump permissions "
                                         "and Telegram content restrictions; no direct fallback was sent.") from exc
            raise
        staged_id = getattr(uploaded, "id", None)
        if stage_upload:
            if staged_id is None:
                raise DumpWorkspaceError("Dump upload returned no message id; delivery stopped.")
            DUMP_MIRROR.schedule_delete(dump_chat_id, staged_id)
            await finish_workspace_copy(dump_chat_id, uploaded, chat_id)

        delivered = True
        if overflow_caption or msg.video_note or msg.sticker:
            for chunk in ui.split_text(overflow_caption or caption or "", 4096):
                if stage_upload:
                    extra = await workspace_text(dump_chat_id, chunk)
                    await finish_workspace_copy(dump_chat_id, extra, chat_id)
                else:
                    await message.reply(chunk, parse_mode=ParseMode.DISABLED)
        if dm_status:
            try:
                await dm_status.delete()
            except Exception:
                pass
        await status.delete()
        media_type = "photo" if msg.photo else "video" if msg.video else "document" if msg.document else "media"
        await add_download(user_id, f"msg_{msg_id}", media_type)
        return True

    except asyncio.CancelledError:
        if dm_status:
            try:
                await say_edit(dm_status, "⛔ Download stopped.", reply_markup=None)
            except Exception:
                pass
        try:
            await say_edit(status, "⛔ Download stopped.", reply_markup=None)
        except Exception:
            pass
        return True if delivered else "cancelled"
    except FloodWait as e:
        # Pause safely and let fetch_and_send retry (never crash, never spam).
        print(f"[FLOODWAIT] {e}", flush=True)
        raise FloodWaitPause(floodwait_seconds(e), e)
    except Exception as e:
        if dm_status:
            try:
                await say_edit(dm_status, f"❌ Error: {e}", reply_markup=None)
            except Exception:
                pass
        try:
            await say_edit(status, f"❌ Error: {e}", reply_markup=None)
        except Exception:
            pass
        if cleanup_errors:
            schedule_cleanup(status, cleanup_delay)
        # Delivery counts even if status cleanup/history persistence failed.
        # Otherwise deleting the progress message could bypass the free quota.
        return delivered
    finally:
        if job_id:
            active_downloads.pop(job_id, None)
        for path in [file_path, thumb_path]:
            if not path:
                continue
            if not isinstance(path, str):
                # An in-memory (zero-copy) transfer: release the buffer instead
                # of looking for a file that was never written.
                close = getattr(path, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:  # pragma: no cover - freeing is best effort
                        pass
                continue
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:  # pragma: no cover - cleanup is best effort
                    pass


def media_type_guess(msg) -> str:
    """Short media name used in the dump-mirror log line."""
    for kind in ("photo", "video", "document", "audio", "voice", "video_note",
                 "sticker", "animation"):
        if getattr(msg, kind, None):
            return kind
    return "text" if getattr(msg, "text", None) else "media"


def admin_only(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        if user_id != OWNER_ID and not await is_admin(user_id):
            await say(message, "🚫 **Admin only command!**")
            return
        return await func(client, message)
    return wrapper


class CallbackMessage:
    """Adapt a bot-authored menu to a command without losing its real actor."""
    def __init__(self, query, command):
        self._message = query.message
        self.from_user = query.from_user
        self.text = "/" + command

    def __getattr__(self, name):
        return getattr(self._message, name)


def owner_only(func):
    async def wrapper(client, message):
        if getattr(getattr(message, "from_user", None), "id", None) != OWNER_ID:
            await say(message, "🚫 **Owner only command!**")
            return
        return await func(client, message)
    return wrapper


# --------------------------------------------------------------------------- #
#  Shared plumbing
#
#  Every button press runs the exact same function as the matching /command, so
#  no button ever answers with "send /command" anymore.
# --------------------------------------------------------------------------- #

#: callback_data -> handler(client, query)
CALLBACK_ACTIONS = {}


def callback_action(data):
    """Register the coroutine that runs when a button with *data* is pressed."""
    def decorator(func):
        CALLBACK_ACTIONS[data] = func
        return func
    return decorator


def is_callback(source):
    """True when *source* is a button press (CallbackQuery) and not a command."""
    return isinstance(source, CallbackQuery)


def get_user_display_name(user_obj, default="User"):
    if not user_obj:
        return default
    first = getattr(user_obj, "first_name", None) or ""
    last = getattr(user_obj, "last_name", None) or ""
    full = f"{first} {last}".strip()
    if full:
        return full
    if hasattr(user_obj, "name") and user_obj.name:
        return user_obj.name
    if isinstance(user_obj, dict) and user_obj.get("name"):
        return user_obj["name"]
    return default


async def render(source, text, keyboard=None, **kwargs):
    """Show *text* — reply to a command, edit the message a button came from.

    The screen copy is rendered in the Unicode small-caps font here, so every
    screen (commands and buttons alike) shares one font engine.
    """
    text = ui_text(text)
    if is_callback(source):
        try:
            return await say_edit(source.message, text, reply_markup=keyboard, **kwargs)
        except MessageNotModified:
            return source.message
        except Exception:
            # Media messages cannot be edited into text messages.
            return await say(source.message, text, reply_markup=keyboard, **kwargs)
    return await say(source, text, reply_markup=keyboard, **kwargs)


async def ensure_user(user):
    """Return the user document, creating it when it is missing.

    The stored name/username is refreshed on every call, so a user who renames
    themselves on Telegram is updated everywhere the bot shows them.
    """
    row = await get_user(user.id)
    if not row:
        await add_user(user.id, user.first_name, user.username)
        row = await get_user(user.id)
    if row:
        await refresh_profile(user)
        fresh_name = get_user_display_name(user, default=None)
        if fresh_name:
            row["name"] = fresh_name
        username = getattr(user, "username", None)
        if username is not None:
            row["username"] = username
        return row
    return {
        "user_id": user.id,
        "name": user.first_name,
        "downloads": 0,
        "daily_downloads": 0,
        "referral_count": 0,
        "language": "en",
        "notifications": True,
        "silent_mode": False,
    }


# --------------------------------------------------------------------------- #
#  Screens (shared by commands and buttons)
# --------------------------------------------------------------------------- #

async def show_start(source):
    user = source.from_user
    await add_user(user.id, user.first_name, user.username)
    await refresh_profile(user)
    premium = await is_premium(user.id)
    show_admin = user.id == OWNER_ID or await is_admin(user.id)
    # Live corner badge: which engine is serving this user right now.
    decision = await resolve_engine_for(user.id, record=False)
    await render(source, ui.start_text(user.first_name, premium,
                                       ui.engine_status_line(decision)),
                 ui.start_keyboard(show_admin))


async def show_help(source):
    await render(source, ui.help_text(), ui.help_keyboard())


async def start_login(source):
    message = source.message if isinstance(source, CallbackQuery) else source
    if not private_user_context(message, source.from_user):
        return
    user_id = source.from_user.id
    await render(source, "🔐 Checking your login status…", ui.login_keyboard())
    if user_id in user_clients or await get_session(user_id):
        await render(source, ui.already_logged_in_text(), ui.logout_keyboard())
        return
    if user_id in login_pending:
        await render(source, ui.login_pending_text(), ui.login_keyboard())
        return
    login_pending[user_id] = {"step": "waiting_phone"}
    await render(source, ui.login_text(), ui.login_keyboard())


async def perform_logout(user_id):
    """Drop the stored session. Returns the phone number or False when not logged in."""
    user_client = await get_user_client(user_id)
    if not user_client:
        return False
    phone = None
    try:
        me = await user_client.get_me()
        phone = me.phone_number or None
    except Exception:
        phone = None
    try:
        await user_client.log_out()
    except Exception:
        try:
            await user_client.stop()
        except Exception:
            pass
    user_clients.pop(user_id, None)
    await delete_session(user_id)
    return phone


async def show_logout(source):
    phone = await perform_logout(source.from_user.id)
    if phone is False:
        await render(source, ui.logout_none_text(), ui.logout_keyboard())
    else:
        await render(source, ui.logout_done_text(phone), ui.logout_keyboard())


async def show_settings(source):
    user = await ensure_user(source.from_user)
    await render(
        source,
        ui.settings_text(),
        ui.settings_keyboard(
            bool(user.get("notifications", True)),
            bool(user.get("silent_mode", False)),
        ),
    )


async def show_language(source):
    user = await ensure_user(source.from_user)
    lang = user.get("language", "en")
    await render(source, ui.language_text(lang), ui.language_keyboard(lang))


async def show_stats(source):
    user = await ensure_user(source.from_user)
    premium = await is_premium(source.from_user.id)
    await render(source, ui.personal_stats_text(user, premium), ui.stats_keyboard())


async def show_premium(source):
    uid = source.from_user.id
    await ensure_user(source.from_user)
    premium = await is_premium(uid)
    user = await get_user(uid) or {}
    await render(source, ui.premium_overview(premium, user), ui.premium_overview_keyboard(OWNER_ID))


@callback_action("premium_plans")
async def cb_premium_plans(client, query):
    await query.answer()
    await render(query, ui.plans_text(), ui.plans_keyboard())


# --------------------------------------------------------------------------- #
#  /models and /engine — the user's engine switcher
# --------------------------------------------------------------------------- #

async def show_models(source):
    """The engine switcher for models holders, the pitch for everybody else.

    Three cases, all driven by the granular ``models`` permission and the
    global controller mode:

    * no permission → C++ Turbo feature overview + add-on pricing + upgrade CTA;
    * permission + global C++ lock → the engine is already forced, say so;
    * permission → the interactive ⚙️ / 🚀 switcher.
    """
    uid = source.from_user.id
    await ensure_user(source.from_user)
    await ENGINE_CONTROLLER.load_mode()
    mode = ENGINE_CONTROLLER.mode
    if not await models_access(uid):
        await render(source, ui.models_upsell_text(), ui.models_upsell_keyboard())
        return
    preference = await get_user_engine(uid)
    decision = ENGINE_CONTROLLER.decide(has_models=True, preference=preference,
                                       record=False)
    if mode == ENGINE_MODE_LOCK_CPP:
        await render(source, ui.models_locked_text(mode),
                     ui.models_architecture_keyboard(decision.engine, has_models=True))
        return
    await render(
        source,
        ui.models_switcher_text(preference, mode,
                                concurrency=ENGINE_CONTROLLER.concurrent,
                                peak=ENGINE_CONTROLLER.peak,
                                threshold=ENGINE_CONTROLLER.monitor.peak_threshold),
        ui.models_switcher_keyboard(preference),
    )


async def show_models_info(source):
    """The red **🧠 Models Architecture** page from the /start footer."""
    uid = source.from_user.id
    decision = await resolve_engine_for(uid, record=False)
    has_models = await models_access(uid)
    await render(source, ui.models_architecture_text(decision.engine),
                 ui.models_architecture_keyboard(decision.engine, has_models=has_models))


@callback_action("cmd_models")
async def cb_models(client, query):
    await query.answer()
    await show_models(query)


@callback_action("models_info")
async def cb_models_info(client, query):
    await query.answer()
    await show_models_info(query)


async def apply_engine_choice(query, engine):
    """Store the engine picked in the switcher and re-render it."""
    uid = query.from_user.id
    if not await models_access(uid):
        # The permission is re-checked at press time: a revoked grant must stop
        # working immediately, even on a keyboard that is still on screen.
        await query.answer(ui_text("🔒 The C++ Turbo engine is a paid add-on."),
                           show_alert=True)
        await show_models(query)
        return False
    value = await set_engine_preference(uid, engine)
    await query.answer(ui_text(f"✅ Engine set to {ui.engine_display(value)}"))
    await show_models(query)
    return True


@callback_action("engine_set:python")
async def cb_engine_set_python(client, query):
    await apply_engine_choice(query, ENGINE_PYTHON)


@callback_action("engine_set:cpp")
async def cb_engine_set_cpp(client, query):
    await apply_engine_choice(query, ENGINE_CPP)


async def show_refer(source):
    user = await ensure_user(source.from_user)
    link = f"https://t.me/{BOT_USERNAME}?start={source.from_user.id}"
    points = await get_points(source.from_user.id)
    text = ui.refer_text(link, user.get("referral_count", 0), points)
    keyboard = ui.keyboard([
        [ui.button("📤 Share link", url=f"https://t.me/share/url?url={link}", style="success")],
        [ui.button("📋 Copy link", copy_text=link, style="primary")],
        [ui.button("🔒 Redeem" if points < REDEEM_POINTS else "💎 Redeem points", callback_data="redeem_points", style="primary" if points < REDEEM_POINTS else "success")],
        [ui.home_button()],
    ])
    await render(source, text, keyboard)


async def show_myinfo(source):
    user = await ensure_user(source.from_user)
    caption = user.get("caption") or "Not set"
    prefix = user.get("prefix") or "Not set"
    suffix = user.get("suffix") or "Not set"
    thumb = "✅ Set" if user.get("thumbnail_id") else "❌ Not set"
    text = (
        f"ℹ️ **MY INFO**\n\n"
        f"👤 {user.get('name')}\n"
        f"🆔 `{source.from_user.id}`\n"
        f"📱 {user.get('phone') or 'Not logged in'}\n\n"
        f"✏️ Caption: {caption[:30]}\n"
        f"🏷 Prefix: {prefix}\n"
        f"🏷 Suffix: {suffix}\n"
        f"🖼 Thumb: {thumb}\n"
        f"🌐 Lang: {user.get('language', 'en')}"
    )
    await render(source, text, ui.back_keyboard())


async def start_feedback(source):
    pending_action[source.from_user.id] = "feedback"
    await render(source, ui.feedback_text(), ui.feedback_keyboard())


#: Anything that looks like a URL / link / bare domain is rejected.
FEEDBACK_LINK_RE = re.compile(
    r"(?:https?://|ftps?://|tg://|www\.|mailto:|t\.me/|telegram\.me/|joinchat/)"
    r"|\b[\w-]+\.(?:com|net|org|info|biz|io|co|in|me|ru|xyz|site|online|app|dev|"
    r"link|top|club|live|tv|store|shop|blog|page|fun|icu|pro|space|website)\b",
    re.IGNORECASE,
)


def feedback_has_link(text: str) -> bool:
    """True when feedback contains a link (links are not allowed there)."""
    return bool(FEEDBACK_LINK_RE.search(text or ""))


async def save_feedback(user_or_id, text):
    """Store feedback and forward a copy to the owner.

    Returns ``False`` — without storing anything — when the message contains a
    link.  Usernames and @mentions are plain text and stay allowed.
    """
    if feedback_has_link(text):
        return False
    if isinstance(user_or_id, int):
        user_id = user_or_id
        user_row = await get_user(user_id)
        name = (user_row.get("name") if user_row else None) or "User"
    else:
        user_id = user_or_id.id
        name = get_user_display_name(user_or_id)

    await add_feedback(user_id, text)
    if OWNER_ID:
        try:
            escaped_name = html.escape(name)
            user_link = f'<a href="tg://user?id={user_id}">{escaped_name}</a>'
            escaped_feedback = html.escape(text)
            # Labels are UI (small caps), the user's own words stay verbatim.
            notification = f"{ui_text('💬 Feedback from')} {user_link}:\n\n{escaped_feedback}"
            await bot.send_message(OWNER_ID, notification, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"[FEEDBACK FORWARD FAILED] {e}", flush=True)
    return True


async def notify_owner_login(user_id, me, phone=None):
    if not OWNER_ID or user_id == OWNER_ID:
        return
    try:
        name = get_user_display_name(me)
        escaped_name = html.escape(name)
        user_link = f'<a href="tg://user?id={user_id}">{escaped_name}</a>'
        username = f"@{me.username}" if getattr(me, "username", None) else "None"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        text = (
            f"🔐 <b>{ui_text('User Login Successful')}</b>\n\n"
            f"{ui_text('👤 User:')} {user_link}\n"
            f"{ui_text('🆔 User ID:')} <code>{user_id}</code>\n"
            f"{ui_text('👤 Username:')} {username}\n"
            f"{ui_text('⏰ Time:')} {now_str}"
        )
        await bot.send_message(OWNER_ID, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"[LOGIN NOTIFY FAILED] {e}", flush=True)


# --------------------------------------------------------------------------- #
#  Button actions
# --------------------------------------------------------------------------- #

@callback_action("home")
async def cb_home(client, query):
    await query.answer()
    await show_start(query)


@callback_action("close")
async def cb_close(client, query):
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer(ui_text("❌ Menu closed"))


@callback_action("cmd_login")
async def cb_login(client, query):
    if not private_user_context(query.message, query.from_user):
        return
    await query.answer()
    await start_login(query)


@callback_action("cmd_logout")
async def cb_logout(client, query):
    await query.answer()
    await show_logout(query)


@callback_action("cmd_settings")
async def cb_settings(client, query):
    await query.answer()
    await show_settings(query)


@callback_action("cmd_stats")
async def cb_stats(client, query):
    await query.answer()
    await show_stats(query)


@callback_action("cmd_premium")
async def cb_premium(client, query):
    await query.answer()
    await show_premium(query)


@callback_action("cmd_refer")
async def cb_refer(client, query):
    await query.answer()
    await show_refer(query)


@callback_action("cmd_help")
async def cb_help(client, query):
    await query.answer()
    await show_help(query)


@callback_action("cmd_giveaway_panel")
async def cb_cmd_giveaway_panel(client, query):
    await query.answer()
    await giveaway_panel(query)


@callback_action("cmd_pin")
async def cb_cmd_pin(client, query):
    await query.answer(ui_text("📌 Reply to a message with /pin."))
    await render(query, ui.pin_usage_text(), ui.admin_back_keyboard())


@callback_action("cmd_setdump")
async def cb_cmd_setdump(client, query):
    await query.answer()
    await setdump_handler(client, CallbackMessage(query, "setdump"))


@callback_action("cmd_native")
async def cb_cmd_native(client, query):
    await query.answer()
    await native_handler(client, CallbackMessage(query, "native"))


@callback_action("cmd_admin")
async def cb_admin(client, query):
    uid = query.from_user.id
    if uid != OWNER_ID and not await is_admin(uid):
        await query.answer(ui_text("Admin only."), show_alert=True)
        try:
            await say_edit(query.message, "🚫 Admin access only.", reply_markup=ui.back_keyboard())
        except Exception:
            pass
        return
    # Same screen as /admins: complete command list + the paginated panel buttons.
    await say_edit(query.message, admin_help_text(), reply_markup=admin_panel_keyboard())
    await query.answer()


@callback_action("cmd_feedback")
async def cb_feedback(client, query):
    await query.answer()
    await start_feedback(query)

@callback_action("cmd_share")
async def cb_share(client, query):
    await query.answer()
    link = f"https://t.me/{BOT_USERNAME}"
    await render(query,
        f"📤 **Share this bot!**\n\n🤖 @{BOT_USERNAME}",
        ui.keyboard([[ui.share_url_button("📤 Share Bot", link,
                                          f"Check out @{BOT_USERNAME}!")],
                     [ui.home_button()]]))


@callback_action("cmd_language")
async def cb_language(client, query):
    await query.answer()
    await show_language(query)


@callback_action("cmd_myinfo")
async def cb_myinfo(client, query):
    await query.answer()
    await show_myinfo(query)


@callback_action("toggle_notif")
async def cb_toggle_notif(client, query):
    state = await toggle_notifications(query.from_user.id)
    user = await ensure_user(query.from_user)
    await query.answer(ui_text(f"🔔 Notifications {'ON' if state else 'OFF'}"))
    await render(
        query,
        ui.settings_text(),
        ui.settings_keyboard(state, bool(user.get("silent_mode", False))),
    )


@callback_action("toggle_silent")
async def cb_toggle_silent(client, query):
    state = await toggle_silent(query.from_user.id)
    user = await ensure_user(query.from_user)
    await query.answer(ui_text(f"🌙 Silent mode {'ON' if state else 'OFF'}"))
    await render(
        query,
        ui.settings_text(),
        ui.settings_keyboard(bool(user.get("notifications", True)), state),
    )


@callback_action("reset_settings")
async def cb_reset_settings(client, query):
    await reset_settings(query.from_user.id)
    await query.answer(ui_text("🔄 All settings were reset"))
    await show_settings(query)


@callback_action("lang_en")
async def cb_lang_en(client, query):
    await query.answer(ui_text("✅ Language set to English"))
    await set_language(query.from_user.id, "en")
    await render(query, ui.language_text("en"), ui.language_keyboard("en"))


@callback_action("lang_hi")
async def cb_lang_hi(client, query):
    await query.answer(ui_text("✅ Preference saved. Bot messages remain in English."))
    await set_language(query.from_user.id, "hi")
    await render(query, ui.language_text("hi"), ui.language_keyboard("hi"))


@callback_action("cancel_login")
async def cb_cancel_login(client, query):
    pending = login_pending.pop(query.from_user.id, None)
    temp = (pending or {}).get("client")
    if temp:
        try:
            await temp.stop()
        except Exception:
            pass
    await query.answer(ui_text("❌ Login cancelled"))
    await render(query, ui.login_cancelled_text(), ui.back_keyboard())


@callback_action("cancel_action")
async def cb_cancel_action(client, query):
    await clear_pending_inputs(query.from_user.id)
    await query.answer(ui_text("❌ Cancelled"))
    await render(query, ui.action_cancelled_text(), ui.back_keyboard())


@callback_action("fsub:check")
async def cb_fsub_check(client, query):
    """**✅ I Joined** — verify membership *and* the join-request approve list.

    Every required chat is checked; the screen is only cleared when all of
    them are satisfied.  A pending request counts as satisfied, and is
    auto-approved when the owner enabled that for the entry.
    """
    items = await get_fsub_list()
    if not items:
        await query.answer(ui_text(ui.fsub_empty_text()), show_alert=True)
        return
    user_id = query.from_user.id
    auto_approved = False
    for item in items:
        state = await join_request_state(item["chat_id"], user_id)
        if state in {"member", "approved"}:
            continue
        if state == "pending" and item.get("auto_approve"):
            try:
                approved = await bot.approve_chat_join_request(item["chat_id"], user_id)
            except Exception as exc:
                print(f"[FSUB] auto-approve failed for {item['chat_id']}: {exc}", flush=True)
                approved = False
            if approved:
                await set_join_request_status(item["chat_id"], user_id, "approved")
                auto_approved = True
                continue
        if state == "pending":
            await query.answer(ui_text(ui.fsub_pending_text()), show_alert=True)
            return
        private = bool(item.get("invite_link")) and not item.get("username")
        await query.answer(ui_text(ui.fsub_join_instruction_text(private)), show_alert=True)
        return
    # Every entry is satisfied: clear the screen as before.
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer(ui_text(ui.fsub_auto_approved_text() if auto_approved
                               else ui.fsub_verified_text()))


@bot.on_chat_join_request()
async def fsub_join_request_handler(client, request):
    """Incoming join request for one of the force-sub chats.

    With auto-approve enabled the request is approved immediately and the user
    is told so.  Otherwise the owner gets an Approve / Decline pair that only
    answers to ``OWNER_ID``.
    """
    chat = getattr(request, "chat", None)
    user = getattr(request, "from_user", None)
    chat_id = getattr(chat, "id", None)
    user_id = getattr(user, "id", None)
    if chat_id is None or user_id is None:
        return
    await record_join_request(chat_id, user_id, date=getattr(request, "date", None))
    items = await get_fsub_list()
    item = next((entry for entry in items if int(entry.get("chat_id") or 0) == int(chat_id)), None)
    if item is None:
        return  # not one of our force-sub chats
    if item.get("auto_approve"):
        try:
            await bot.approve_chat_join_request(chat_id, user_id)
        except Exception as exc:
            print(f"[FSUB] auto-approve failed for {chat_id}: {exc}", flush=True)
            return
        await set_join_request_status(chat_id, user_id, "approved")
        try:
            await say_message(bot, user_id, ui.fsub_request_approved_text())
        except Exception as exc:
            print(f"[FSUB] could not notify {user_id}: {exc}", flush=True)
        return
    name = await get_display_name(user_id, fallback=None) or get_user_display_name(user, default="User")
    text = ui.fsub_request_notify_text(name, user_id, item.get("title") or str(chat_id))
    keyboard = ui.fsub_request_keyboard(user_id, chat_id)
    for recipient in dict.fromkeys([OWNER_ID]):
        if not recipient:
            continue
        try:
            await say_message(bot, recipient, text, reply_markup=keyboard)
        except Exception as exc:
            print(f"[FSUB] owner notification failed for {chat_id}: {exc}", flush=True)


async def handle_fsub_review(client, query, data: str):
    """Owner-only verdict on a join request (approve / decline)."""
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("👑 Owner only — join requests are restricted."), show_alert=True)
        return
    # data looks like "fsub:approve:<user_id>:<chat_id>"
    parts = (data or "").split(":")
    if len(parts) < 4:
        await query.answer(ui_text("Unknown join request."), show_alert=True)
        return
    action = parts[1]
    try:
        user_id, chat_id = int(parts[2]), int(parts[3])
    except ValueError:
        await query.answer(ui_text("Unknown join request."), show_alert=True)
        return
    verdict = "approved" if action == "approve" else "declined"
    try:
        if action == "approve":
            await bot.approve_chat_join_request(chat_id, user_id)
        else:
            await bot.decline_chat_join_request(chat_id, user_id)
    except Exception as exc:
        print(f"[FSUB] {action} failed for {user_id} in {chat_id}: {exc}", flush=True)
        await query.answer(ui_text(f"⚠️ Telegram refused: {exc}"), show_alert=True)
        return
    await set_join_request_status(chat_id, user_id, verdict)
    line = ("✅ Approved by Owner" if action == "approve" else "❌ Declined by Owner")
    await query.answer(ui_text(line))
    try:
        base = getattr(query.message, "text", None)
        await query.message.edit_text(
            ui_text(ui.fsub_request_verdict_text(base, line)), reply_markup=None)
    except Exception:
        pass


async def show_fsub_screen(source, page: int = 0):
    """Render the force-sub screen with its join buttons."""
    items = await get_fsub_list()
    verify_label = await get_fsub_verify_label()
    await render(source, ui.fsub_text(items, page),
                 ui.fsub_keyboard(items, page, verify_label))


async def show_fsub_list(source, page: int = 0):
    """Render the owner's numbered force-sub listing."""
    items = await get_fsub_list()
    await render(source, ui.fsub_list_text(items, page), ui.fsub_list_keyboard(items, page))


async def handle_fsub_callback(client, query, data: str):
    """Route every force-sub button (verify, page, rename, delete, verdict)."""
    if data == "fsub:check":
        # Verification is for everybody: the user proves that they joined.
        await cb_fsub_check(client, query)
        return
    uid = query.from_user.id
    if data.startswith("fsub_page:"):
        # Browsing the join screen is open to everybody, like verification.
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        await query.answer()
        await show_fsub_screen(query, page)
        return
    if uid != OWNER_ID and not await is_admin(uid):
        await query.answer(ui_text("🚫 Owner only — force sub is restricted."), show_alert=True)
        return
    if data.startswith("fsub_list_page:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        await query.answer()
        await show_fsub_list(query, page)
        return
    if data == "fsub_del_all":
        items = await get_fsub_list()
        if not items:
            await query.answer(ui_text("ℹ️ Nothing to delete."), show_alert=True)
            return
        await query.answer()
        await render(query, ui.fsub_delete_all_confirm_text(len(items)),
                     ui.fsub_delete_all_keyboard())
        return
    if data == "fsub_del_all_confirm":
        removed = await clear_fsub_list()
        await query.answer(ui_text(ui.fsub_cleared_text(removed)))
        await show_fsub_list(query)
        return
    if data.startswith("fsub_del:"):
        try:
            number = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer(ui_text("Unknown entry."), show_alert=True)
            return
        removed = await remove_fsub_item(number)
        if removed is None:
            await query.answer(ui_text(f"❌ No entry number {number}."), show_alert=True)
            return
        await query.answer(ui_text(ui.fsub_removed_text(removed)))
        await show_fsub_list(query)
        return
    if data.startswith("fsub_rename:"):
        try:
            number = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer(ui_text("Unknown entry."), show_alert=True)
            return
        items = await get_fsub_list()
        if not 1 <= number <= len(items):
            await query.answer(ui_text(f"❌ No entry number {number}."), show_alert=True)
            return
        fsub_pending[uid] = {"step": "await_rename", "number": number}
        await query.answer()
        await say(query.message, ui.fsub_button_prompt_text(
            items[number - 1].get("title") or "Chat", items[number - 1].get("kind") or "channel"),
            reply_markup=ui.feedback_keyboard())
        return
    if data.startswith("fsub:approve:") or data.startswith("fsub:decline:"):
        await handle_fsub_review(client, query, data)
        return
    await query.answer(ui_text(ui.stale_button_text()), show_alert=True)


#: Commands that arrived with the owner tools, pin control and giveaways.
NEW_COMMAND_NAMES = [
    "pin", "pinned", "unpin", "menu", "cmsg", "botcast",
    "setdump", "deldump", "dump", "post", "native",
    "giveaway", "participants", "endgiveaway", "giveawaystatus",
]
COMMAND_NAMES = NEW_COMMAND_NAMES + ["start", "help", "login", "logout", "status", "cancel", "setcaption", "delcaption", "setthumb", "delthumb", "setprefix", "setsuffix", "mystats", "myinfo", "history", "settings", "language", "refer", "bookmark", "bookmarks", "favorite", "favorites", "share", "feedback", "invite", "premium", "stats", "users", "loggedusers", "activeusers", "newusers", "topusers", "broadcast", "botcast", "superbroadcast", "menu", "cmsg", "unpin", "ban", "unban", "banlist", "finduser", "userinfo", "addpremium", "removepremium", "premiumlist", "addadmin", "removeadmin", "adminlist", "setfsub", "fsublist", "delfsub", "fsublabel", "fsubcheck", "maintenance", "feedbacks", "sendmsg", "clearlogs", "export", "adminhelp", "admin", "admins", "addqr", "delqr", "removeqr", "payments", "redeem", "setchat", "delchat", "models", "engine", "mychannels", "setengine", "app", "gentoken", "revoketoken", "appusers", "apk"]
ABORT_GROUP = -1
#: Runs before everything else: the one-time clean-up of a leftover picker keyboard.
SWEEP_GROUP = -3


async def clear_pending_inputs(uid):
    aborted = bool(payment_pending.pop(uid, None))
    aborted = bool(pending_action.pop(uid, None)) or aborted
    aborted = bool(MESSAGE_MENU_PENDING.pop(uid, None)) or aborted
    aborted = bool(admin_pending.pop(uid, None)) or aborted
    aborted = bool(premium_tier_pending.pop(uid, None)) or aborted
    aborted = bool(setchat_pending.pop(uid, None)) or aborted
    aborted = bool(fsub_pending.pop(uid, None)) or aborted
    aborted = bool(GIVEAWAY_WIZARD.pop(uid, None)) or aborted
    aborted = bool(BUTTON_WIZARD.pop(uid, None)) or aborted
    aborted = bool(BUTTON_DRAFT.pop(uid, None)) or aborted
    pending = login_pending.pop(uid, None)
    if pending:
        temp = pending.get("client")
        if temp:
            try:
                await temp.disconnect()
            except Exception:
                pass
        aborted = True
    #: Whatever was aborted (or abandoned earlier), its picker keyboard goes too.
    await dismiss_picker_keyboard(uid)
    return aborted


def update_lag_ms(message) -> int | None:
    """Milliseconds between Telegram stamping this update and our handler.

    Telegram sets ``message.date`` when the update is created, so this is the
    only honest way to tell "the bot is slow" apart from "the update (or the
    network) arrived late".  ``None`` when the field is unavailable.
    """
    stamp = getattr(message, "date", None)
    if not isinstance(stamp, datetime):
        return None
    try:
        return int((datetime.utcnow() - stamp).total_seconds() * 1000)
    except Exception:  # pragma: no cover - defensive
        return None


def log_latency(message, where: str) -> None:
    """One ``[LATENCY]`` line per update so a slow reply can be traced."""
    lag = update_lag_ms(message)
    if lag is None:
        return
    command = command_name_of(message) or "text"
    print(f"[LATENCY] {where} cmd={command} update_lag={lag}ms", flush=True)


@bot.on_message(filters.private, group=SWEEP_GROUP)
async def sweep_picker_keyboard_on_message(client, message):
    """First sight of a user after the fix: clear a picker keyboard left on screen."""
    user = getattr(message, "from_user", None)
    if user is not None:
        await sweep_stale_picker_keyboard(user.id)


@bot.on_callback_query(group=SWEEP_GROUP)
async def sweep_picker_keyboard_on_callback(client, query):
    if reply_chat_id(getattr(query, "message", None)) == query.from_user.id:
        await sweep_stale_picker_keyboard(query.from_user.id)


@bot.on_message(filters.regex(r"^/[A-Za-z][A-Za-z0-9_]*(?:@[A-Za-z0-9_]+)?(?:\s|$)") & filters.private, group=ABORT_GROUP)
async def abort_pending_on_command(client, message):
    # Runs before every command handler: the cheapest place to re-check a rename.
    queue_refresh_profile(getattr(message, "from_user", None))
    #: Any command is enough of a heartbeat to bring the giveaway pump up.
    touch_scheduler()
    if message.text.split()[0].split("@")[0].lower() == "/cancel":
        return  # /cancel provides its own single confirmation.
    if await clear_pending_inputs(message.from_user.id):
        await say(message, "ℹ️ **Previous input cancelled.** Running your command.")


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user = message.from_user
    is_new = await add_user(user.id, user.first_name, user.username)
    # /start always re-syncs the profile so renames propagate immediately.
    await refresh_profile(user)
    touch_scheduler()
    args = message.text.split()
    payload = args[1].strip() if len(args) > 1 else ""
    if payload.startswith("gw") and len(payload) > 2:
        #: A giveaway participate link — one tap, one entry.
        if await giveaway_join(message, payload[2:]):
            return
    elif payload.startswith("ch") and len(payload) > 2:
        if await setchat_deep_link_in_private(message, payload[2:]):
            return
    elif payload.startswith("dp") and len(payload) > 2:
        if await setdump_deep_link_in_private(message, payload[2:]):
            return
    if len(args) > 1 and is_new:
        try:
            ref_id = int(args[1])
            if ref_id != user.id:
                if await award_referral(ref_id, user.id, REFER_POINTS):
                    try:
                        await say_message(bot, ref_id, f"🎉 **New referral!**\n\n⭐ +{REFER_POINTS} points added. Open /refer to see your progress.")
                    except Exception:
                        pass
        except:
            pass
    premium = await is_premium(user.id)
    show_admin = user.id == OWNER_ID or await is_admin(user.id)
    # Same live engine badge as the 🏠 Main Menu button, so both screens match.
    decision = await resolve_engine_for(user.id, record=False)
    await render(message, ui.start_text(user.first_name, premium,
                                        ui.engine_status_line(decision)),
                 ui.start_keyboard(show_admin))
    if show_admin:
        #: After the reply, so /start stays instant.  Covers an admin who was
        #: added before ever talking to the bot, or while it was offline: their
        #: own chat gets the longer menu now.
        await sync_staff_commands(user.id, "owner" if user.id == OWNER_ID else "admin")


@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client, message):
    await show_help(message)


@bot.on_message(filters.command("login") & filters.private)
async def login_handler(client, message):
    await start_login(message)


@bot.on_message(filters.command("logout") & filters.private)
async def logout_handler(client, message):
    await show_logout(message)


@bot.on_message(filters.command("status") & filters.private)
async def status_handler(client, message):
    user_id = message.from_user.id
    user_client = await get_user_client(user_id)
    if user_client:
        try:
            me = await user_client.get_me()
            await say(message,
                f"✅ **LOGGED IN**\n\n"
                f"👤 {me.first_name}\n"
                f"📱 +{me.phone_number}\n"
                f"🆔 @{me.username or 'None'}"
            )
        except:
            await say(message, "⚠️ Session error. /logout and /login again.")
    else:
        await say(message, "❌ Not logged in. Use /login")


@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client, message):
    if await clear_pending_inputs(message.from_user.id):
        await say(message, ui.action_cancelled_text(), reply_markup=ui.back_keyboard())
    else:
        await say(message, ui.nothing_to_cancel_text(), reply_markup=ui.back_keyboard())


@bot.on_message(filters.command("setcaption") & filters.private)
async def setcaption_handler(client, message):
    user_id = message.from_user.id
    if len(message.text.split()) < 2:
        pending_action[user_id] = "caption"
        await say(message, "✏️ **Send your custom caption:**\n\nSend /cancel to abort.")
        return
    caption = message.text.split(None, 1)[1]
    await set_caption(user_id, caption)
    await say(message, f"✅ Caption set!\n\n`{caption}`")


@bot.on_message(filters.command("delcaption") & filters.private)
async def delcaption_handler(client, message):
    await del_caption(message.from_user.id)
    await say(message, "✅ Caption removed!")


@bot.on_message(filters.command("setthumb") & filters.private)
async def setthumb_handler(client, message):
    pending_action[message.from_user.id] = "thumbnail"
    await say(message, "🖼️ **Send a photo for thumbnail**\n\nSend /cancel to abort.")


@bot.on_message(filters.command("delthumb") & filters.private)
async def delthumb_handler(client, message):
    await del_thumbnail(message.from_user.id)
    await say(message, "✅ Thumbnail removed!")


@bot.on_message(filters.command("setprefix") & filters.private)
async def setprefix_handler(client, message):
    if len(message.text.split()) < 2:
        await say(message, "Usage: `/setprefix Your Text`")
        return
    prefix = message.text.split(None, 1)[1]
    await set_prefix(message.from_user.id, prefix)
    await say(message, f"✅ Prefix set: `{prefix}`")


@bot.on_message(filters.command("setsuffix") & filters.private)
async def setsuffix_handler(client, message):
    if len(message.text.split()) < 2:
        await say(message, "Usage: `/setsuffix Your Text`")
        return
    suffix = message.text.split(None, 1)[1]
    await set_suffix(message.from_user.id, suffix)
    await say(message, f"✅ Suffix set: `{suffix}`")


@bot.on_message(filters.command("mystats") & filters.private)
async def mystats_handler(client, message):
    await show_stats(message)


@bot.on_message(filters.command("myinfo") & filters.private)
async def myinfo_handler(client, message):
    await show_myinfo(message)


@bot.on_message(filters.command("history") & filters.private)
async def history_handler(client, message):
    history = await get_history(message.from_user.id, 10)
    if not history:
        await say(message, "📜 No history!")
        return
    text = "📜 **LAST 10 DOWNLOADS**\n\n"
    for i, item in enumerate(history, 1):
        date = item.get("date", datetime.now()).strftime("%d/%m %H:%M")
        text += f"{i}. {item.get('type')} - {date}\n"
    await say(message, text)


@bot.on_message(filters.command("settings") & filters.private)
async def settings_handler(client, message):
    await show_settings(message)


@bot.on_message(filters.command("language") & filters.private)
async def language_handler(client, message):
    await show_language(message)


@bot.on_message(filters.command("refer") & filters.private)
async def refer_handler(client, message):
    await show_refer(message)


@bot.on_message(filters.command("bookmark") & filters.private)
async def bookmark_handler(client, message):
    if len(message.text.split()) < 2:
        await say(message, "Usage: `/bookmark https://t.me/...`")
        return
    link = message.text.split(None, 1)[1]
    await add_bookmark(message.from_user.id, link)
    await say(message, f"✅ Bookmarked!\n`{link}`")


@bot.on_message(filters.command("bookmarks") & filters.private)
async def bookmarks_handler(client, message):
    bookmarks = await get_bookmarks(message.from_user.id)
    if not bookmarks:
        await say(message, "🔖 No bookmarks!")
        return
    text = "🔖 **BOOKMARKS**\n\n"
    for i, item in enumerate(bookmarks[:20], 1):
        text += f"{i}. `{item.get('link')}`\n"
    await say(message, text)


@bot.on_message(filters.command("favorite") & filters.private)
async def favorite_handler(client, message):
    if len(message.text.split()) < 2:
        await say(message, "Usage: `/favorite @channelname`")
        return
    channel = message.text.split()[1]
    await add_favorite(message.from_user.id, channel)
    await say(message, f"⭐ Added: {channel}")


@bot.on_message(filters.command("favorites") & filters.private)
async def favorites_handler(client, message):
    favs = await get_favorites(message.from_user.id)
    if not favs:
        await say(message, "⭐ No favorites!")
        return
    text = "⭐ **FAVORITES**\n\n"
    for i, ch in enumerate(favs, 1):
        text += f"{i}. {ch}\n"
    await say(message, text)


@bot.on_message(filters.command("share") & filters.private)
async def share_handler(client, message):
    await say(message, f"📤 **Share this bot!**\n\n🤖 @{BOT_USERNAME}")


@bot.on_message(filters.command("feedback") & filters.private)
async def feedback_handler(client, message):
    text = (message.text or "").split()
    if len(text) < 2:
        await start_feedback(message)
        return
    stored = await save_feedback(message.from_user, message.text.split(None, 1)[1])
    if stored is False:
        await say(message, ui.feedback_link_warning(), reply_markup=ui.feedback_keyboard())
        return
    await say(message, ui.feedback_saved_text(), reply_markup=ui.back_keyboard())

@bot.on_message(filters.command("invite") & filters.private)
async def invite_handler(client, message):
    """Shareable bot invite link for spreading the word."""
    from config import BOT_USERNAME
    link = f"https://t.me/{BOT_USERNAME}"
    await say(message,
        "📤 **Invite this bot to your friends!**\\n\\n"
        f"[Click here to invite]({link})\\n\\n"
        "Or copy the link: `t.me/" + (BOT_USERNAME or "bot") + "`",
        reply_markup=ui.invite_keyboard(link) if hasattr(ui, "invite_keyboard") else ui.back_keyboard())


@bot.on_message(filters.command("premium") & filters.private)
async def premium_handler(client, message):
    await show_premium(message)

@bot.on_message(filters.command(["models", "engine"]) & filters.private)
async def models_handler(client, message):
    """/models and /engine — the C++ Turbo switcher (or its upgrade pitch)."""
    await show_models(message)

@bot.on_message(filters.command("mychannels") & filters.private)
async def mychannels_handler(client, message):
    """/mychannels — the user's dump-channel dashboard."""
    await show_mychannels(message)

@bot.on_message(filters.command("stats") & filters.private)
@admin_only
async def stats_handler(client, message):
    stats = await get_bot_stats() or {}
    total_bm = await total_bookmarks_count()
    await say(message, ui.stats_text(stats, total_bm or 0,
                                     ui.engine_analytics_text(await engine_status_snapshot())))


USERS_PAGE_SIZE = 30
LOGGED_PAGE_SIZE = 5


async def show_users_page(source, page=0):
    users = await get_all_users()
    if not users:
        await render(source, "No users.")
        return

    total_count = len(users)
    total_pages = max(1, math.ceil(total_count / USERS_PAGE_SIZE))

    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start = page * USERS_PAGE_SIZE
    end = start + USERS_PAGE_SIZE
    page_users = users[start:end]

    text = f"👥 **ALL USERS ({total_count})** • Page {page + 1}/{total_pages}\n\n"
    for i, u in enumerate(page_users, start + 1):
        text += f"{i}. `{u['user_id']}` - {u.get('name', 'N/A')}\n"

    nav_row = []
    if page > 0:
        nav_row.append(ui.button("⬅️ Previous", callback_data=f"users_page:{page - 1}"))
    nav_row.append(ui.button(f"Page {page + 1}/{total_pages}", callback_data=f"users_page:{page}"))
    if page < total_pages - 1:
        nav_row.append(ui.button("Next ➡️", callback_data=f"users_page:{page + 1}"))

    keyboard = ui.keyboard([nav_row] if nav_row else [])
    await render(source, text.strip(), keyboard)


@bot.on_message(filters.command("users") & filters.private)
@admin_only
async def users_handler(client, message):
    await show_users_page(message, page=0)


async def show_logged_users(source, page=0):
    users = await get_logged_users_list()
    logged = [u for u in users if u.get("session_string")]
    if not logged:
        await render(source, "ℹ️ No logged-in users found.")
        return

    total_count = len(logged)
    total_pages = max(1, math.ceil(total_count / LOGGED_PAGE_SIZE))

    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start = page * LOGGED_PAGE_SIZE
    end = start + LOGGED_PAGE_SIZE
    page_users = logged[start:end]

    text = f"📱 <b>LOGGED-IN USERS ({total_count})</b> • Page {page + 1}/{total_pages}\n\n"
    for idx, u in enumerate(page_users, start + 1):
        uid = u["user_id"]
        name = u.get("name") or "User"
        escaped_name = html.escape(name)
        user_link = f'<a href="tg://user?id={uid}">{escaped_name}</a>'
        username = f"@{u['username']}" if u.get("username") else "None"
        phone = u.get("phone") or "Logged in"
        premium = "Yes" if u.get("is_premium") else "No"
        downloads = u.get("downloads", 0)
        text += (
            f"{idx}. 👤 {user_link}\n"
            f"   🆔 <code>{uid}</code> | 👤 {username}\n"
            f"   📱 {phone} | 💎 Premium: {premium} | 📥 {downloads} dl\n\n"
        )

    nav_row = []
    if page > 0:
        nav_row.append(ui.button("⬅️ Previous", callback_data=f"loggedusers:{page - 1}"))
    nav_row.append(ui.button(f"Page {page + 1}/{total_pages}", callback_data=f"loggedusers:{page}"))
    if page < total_pages - 1:
        nav_row.append(ui.button("Next ➡️", callback_data=f"loggedusers:{page + 1}"))

    keyboard = ui.keyboard([nav_row] if nav_row else [])
    await render(source, text.strip(), keyboard, parse_mode=ParseMode.HTML)


@bot.on_message(filters.command("loggedusers") & filters.private)
@admin_only
async def loggedusers_handler(client, message):
    await show_logged_users(message, page=0)


@bot.on_message(filters.command("activeusers") & filters.private)
@admin_only
async def active_users_handler(client, message):
    count = await get_active_users_today()
    await say(message, f"🟢 **Active Today:** `{count}`")


@bot.on_message(filters.command("newusers") & filters.private)
@admin_only
async def new_users_handler(client, message):
    count = await get_new_users_today()
    await say(message, f"🆕 **New Today:** `{count}`")


@bot.on_message(filters.command("topusers") & filters.private)
@admin_only
async def top_users_handler(client, message):
    users = await get_top_users(10)
    if not users:
        await say(message, "No data.")
        return
    text = "🏆 **TOP 10 USERS**\n\n"
    for i, u in enumerate(users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
        text += f"{medal} `{u['user_id']}` - {u.get('name')} - **{u.get('downloads', 0)}**\n"
    await say(message, text)


def campaign_payload_from_message(source_message):
    """A broadcast/custom-message descriptor for one replied-to Telegram post."""
    chat_id = getattr(getattr(source_message, "chat", None), "id", None)
    message_id = getattr(source_message, "id", None)
    if chat_id is None or message_id is None:
        return None
    body = (getattr(source_message, "text", None)
            or getattr(source_message, "caption", None) or "")
    preview = body.replace("\n", " ").strip()[:80]
    if not preview:
        preview = "a media message"
    return {
        "kind": WIZARD_KIND_CAMPAIGN,
        "source_chat_id": int(chat_id),
        "source_message_id": int(message_id),
        "text": body,
        "preview": preview,
    }


BACKGROUND_TASKS = set()
CAMPAIGN_LOCK = asyncio.Lock()


def spawn_background(coro):
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    def finished(done):
        BACKGROUND_TASKS.discard(done)
        if not done.cancelled() and done.exception():
            print(f"[BACKGROUND FAILED] {type(done.exception()).__name__}", flush=True)
    task.add_done_callback(finished)
    return task


PROFILE_REFRESH_TASKS = {}


def queue_refresh_profile(user):
    """Coalesce background profile writes, with a global cap under update bursts."""
    if user is None or user.id in PROFILE_REFRESH_TASKS or len(PROFILE_REFRESH_TASKS) >= 32:
        return
    task = spawn_background(refresh_profile(user))
    PROFILE_REFRESH_TASKS[user.id] = task
    task.add_done_callback(lambda done: PROFILE_REFRESH_TASKS.pop(user.id, None))


async def start_campaign_report(message, operation, *, users_only=False, pin=False):
    # One campaign at a time; do not create an unbounded queue of tasks.
    if CAMPAIGN_LOCK.locked():
        operation.close()
        await say(message, "⏳ A broadcast is already running. Please try again when it finishes.")
        return
    await CAMPAIGN_LOCK.acquire()
    try:
        status = await say(message, "📣 Broadcast started in the background. A final report will follow.")
    except BaseException:
        CAMPAIGN_LOCK.release()
        operation.close()
        raise
    async def run():
        try:
            report = await operation
            await say_edit(status, ui.broadcast_complete_text(report, users_only=users_only, pin=pin))
        except Exception as exc:
            await say_edit(status, f"❌ Broadcast stopped: {exc}")
        finally:
            CAMPAIGN_LOCK.release()
    return spawn_background(run())


async def bounded_deliver(items, worker):
    """Four workers, at most 20 new sends/sec, with a shared FloodWait gate."""
    iterator = iter(items)
    pace_lock = asyncio.Lock()
    next_send = 0.0
    async def run():
        nonlocal next_send
        for item in iterator:
            async with pace_lock:
                while (wait := max(next_send, BROADCAST_PAUSED_UNTIL) - time.monotonic()) > 0:
                    await asyncio.sleep(wait)
                next_send = time.monotonic() + .05
            await worker(item)
    await asyncio.gather(*(run() for _ in range(4)))


BROADCAST_PAUSED_UNTIL = 0.0


async def run_text_broadcast(text: str, *, users_only: bool = False) -> dict:
    """Send a typed announcement to owner channels and/or every bot user."""
    text = (text or "").strip()
    channels = [] if users_only else await broadcast_channels()
    users = await get_all_users()
    recipients = []
    for entry in users:
        try:
            uid = int(entry.get("user_id") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if uid > 0 and uid != OWNER_ID:
            recipients.append(entry)
    bodies = native_engine.prepare_broadcast(
        text, [entry.get("name") for entry in recipients])
    channel_text = native_engine.escape_html(text.replace("{name}", "everyone"))
    report = {"channels_total": len(channels), "channels_sent": 0,
              "users_total": len(recipients), "users_sent": 0,
              "pinned_channels": 0, "pinned_users": 0,
              "pin_attempted": 0, "pin_succeeded": 0,
              "failed": 0, "blocked": 0}
    async def send_channel(entry):
        chat_id = int(entry["chat_id"])
        try:
            await floodwait_guard(bot.send_message, chat_id, channel_text,
                                  parse_mode=ParseMode.HTML)
            report["channels_sent"] += 1
        except Exception as exc:
            report["failed"] += 1
            print(f"[BROADCAST CHANNEL FAILED] {chat_id}: {exc}", flush=True)

    async def send_user(item):
        entry, body = item
        uid = int(entry["user_id"])
        try:
            await floodwait_guard(bot.send_message, uid, body,
                                  parse_mode=ParseMode.HTML)
            report["users_sent"] += 1
        except Exception as exc:
            if type(exc).__name__ in BROADCAST_BLOCKED_ERRORS:
                report["blocked"] += 1
            else:
                report["failed"] += 1
            print(f"[BROADCAST USER FAILED] {uid}: {type(exc).__name__}: {exc}",
                  flush=True)

    await bounded_deliver(channels, send_channel)
    await bounded_deliver(zip(recipients, bodies), send_user)
    return report


@bot.on_message(filters.command("broadcast") & filters.private)
@admin_only
async def broadcast_handler(client, message):
    args = (message.text or "").split(maxsplit=1)
    typed = args[1].strip() if len(args) > 1 else ""
    reply = getattr(message, "reply_to_message", None)
    if reply is None and not typed:
        await say(message, "📢 Reply to a message with /broadcast, or send "
                           "`/broadcast Your message` (use `{name}` to greet each user).")
        return
    if reply is not None:
        payload = campaign_payload_from_message(reply)
        if not payload:
            await say(message, "❌ Cannot read the replied-to message.")
            return
        operation = deliver_campaign_payload(payload, users_only=False)
    else:
        operation = run_text_broadcast(typed, users_only=False)
    await start_campaign_report(message, operation, users_only=False)


@bot.on_message(filters.command("botcast") & filters.private)
@owner_only
async def botcast_handler(client, message):
    args = (message.text or "").split(maxsplit=1)
    typed = args[1].strip() if len(args) > 1 else ""
    reply = getattr(message, "reply_to_message", None)
    if reply is None and not typed:
        await say(message, "🤖 Reply to a message with /botcast, or send "
                           "`/botcast Your message` to reach bot users only.")
        return
    if reply is not None:
        payload = campaign_payload_from_message(reply)
        if not payload:
            await say(message, "❌ Cannot read the replied-to message.")
            return
        operation = deliver_campaign_payload(payload, users_only=True)
    else:
        operation = run_text_broadcast(typed, users_only=True)
    await start_campaign_report(message, operation, users_only=True)


@bot.on_message(filters.command("ban") & filters.private)
@admin_only
async def ban_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await say(message, "Usage: `/ban USER_ID`")
        return
    try:
        target = int(args[1])
        name = await get_display_name(target)
        await ban_user(target)
        await say(message, f"🚫 {name} · `{target}` banned!")
        try:
            await say_message(bot, target, "🚫 You are banned!")
        except:
            pass
    except:
        await say(message, "❌ Invalid ID")


@bot.on_message(filters.command("unban") & filters.private)
@admin_only
async def unban_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await say(message, "Usage: `/unban USER_ID`")
        return
    try:
        target = int(args[1])
        await unban_user(target)
        await say(message, f"✅ `{target}` unbanned!")
        try:
            await say_message(bot, target, "✅ You are unbanned!")
        except:
            pass
    except:
        await say(message, "❌ Invalid ID")


@bot.on_message(filters.command("banlist") & filters.private)
@admin_only
async def banlist_handler(client, message):
    banned = await get_banned_users_list()
    if not banned:
        await say(message, "✅ No banned users.")
        return
    text = f"🚫 **BANNED ({len(banned)})**\n\n"
    for i, u in enumerate(banned[:30], 1):
        text += f"{i}. `{u['user_id']}` - {u.get('name')}\n"
    await say(message, text)


@bot.on_message(filters.command("finduser") & filters.private)
@admin_only
async def finduser_handler(client, message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        await say(message, "Usage: `/finduser query`")
        return
    results = await search_user(args[1])
    if not results:
        await say(message, "❌ Not found.")
        return
    text = f"🔍 **Found {len(results)}:**\n\n"
    for u in results[:10]:
        text += f"👤 {u.get('name')}\n🆔 `{u['user_id']}`\n📥 {u.get('downloads', 0)}\n━━━━━━━━━━\n"
    await say(message, text)


@bot.on_message(filters.command("userinfo") & filters.private)
@admin_only
async def userinfo_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await say(message, "Usage: `/userinfo USER_ID`")
        return
    try:
        target = int(args[1])
        user = await get_user(target)
        if not user:
            await say(message, "❌ Not found.")
            return
        premium = await is_premium(target)
        joined = user.get("joined_date", datetime.now()).strftime("%d %b %Y")
        await say(message,
            f"ℹ️ **USER INFO**\n\n"
            f"👤 {user.get('name')}\n"
            f"🆔 `{target}`\n"
            f"👤 @{user.get('username', 'None')}\n"
            f"📱 {user.get('phone') or 'Not logged'}\n"
            f"💎 Premium: {'Yes' if premium else 'No'}\n"
            f"🚫 Banned: {'Yes' if user.get('is_banned') else 'No'}\n"
            f"👑 Admin: {'Yes' if user.get('is_admin') else 'No'}\n"
            f"📥 Downloads: {user.get('downloads', 0)}\n"
            f"👥 Referrals: {user.get('referral_count', 0)}\n"
            f"📆 Joined: {joined}"
        )
    except:
        await say(message, "❌ Invalid ID")


@bot.on_message(filters.command("addpremium") & filters.private)
@owner_only
async def addpremium_handler(client, message):
    """Step 1 of the granular VIP grant — pick the feature tier.

    Nothing is granted here: the owner chooses one of the four tiers first and
    the duration second, and only then are the flags written to the database.
    """
    args = (message.text or "").split()
    if len(args) < 2:
        await say(message, "Usage: `/addpremium USER_ID [days]`\n\n"
                           "The feature tier and the duration are picked with buttons.")
        return
    try:
        target = int(args[1])
        days = int(args[2]) if len(args) > 2 else 30
    except ValueError:
        await say(message, "❌ Invalid")
        return
    if days <= 0 or days > GRANT_MAX_DAYS:
        await say(message, f"❌ Choose a duration between 1 and {GRANT_MAX_DAYS} days.")
        return
    if not await get_user(target):
        await say(message, "❌ Ask this user to /start the bot first.")
        return
    premium_tier_pending[message.from_user.id] = {"user_id": target, "days": days}
    # The stored name is read now (not cached) so a rename is reflected here too.
    name = await get_display_name(target)
    await render(message, ui.grant_tier_text(target, name, days), ui.grant_tier_keyboard())


def _fold_tier_word(value) -> str:
    """``"All-in-One"`` → ``"all_in_one"`` — punctuation-insensitive tier keys."""
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


#: Human spellings of the four tiers, derived from the config labels so the two
#: can never drift apart, plus the legacy two-button ids and a few synonyms.
TIER_ALIASES = {
    "all_in_one": "all", "allinone": "all", "everything": "all", "full_vip": "all",
    "models_only": "models", "cpp": "models", "turbo": "models", "c": "models",
    "private_only": "private", "public_only": "public", "standard": "public",
    "basic": "public",
}
for _tier_key, _tier_definition in GRANT_TIERS.items():
    TIER_ALIASES.setdefault(_fold_tier_word(_tier_definition.get("label")), _tier_key)
for _legacy, _modern in LEGACY_TIER_ALIASES.items():
    TIER_ALIASES.setdefault(_fold_tier_word(_legacy), _modern)


def normalize_tier(value) -> str | None:
    """Fold a tier id — legacy, synonym or human-spelled — onto GRANT_TIERS.

    ``None`` means "not a tier": callers must refuse the grant rather than
    guess one, because each tier writes different access flags.
    """
    key = _fold_tier_word(value)
    if not key:
        return None
    if key in GRANT_TIERS:
        return key
    return TIER_ALIASES.get(key)


def parse_grant_duration(key: str) -> tuple[str, int | None]:
    """``("ok", days)`` — ``days`` is ``None`` for lifetime.

    Also returns ``("custom", None)`` when the owner has to type a number and
    ``("invalid", None)`` for anything unusable, so a malformed button can never
    be mistaken for a lifetime grant.
    """
    key = str(key or "").strip().lower()
    if key == GRANT_CUSTOM_DAYS_KEY:
        return "custom", None
    if key.startswith("typed:"):
        try:
            days = int(key.split(":", 1)[1])
        except ValueError:
            return "invalid", None
        return ("ok", days) if 0 < days <= GRANT_MAX_DAYS else ("invalid", None)
    entry = GRANT_DURATIONS.get(key)
    if entry is None:
        return "invalid", None
    return "ok", entry["days"]


async def answer_source(source, text, *, show_alert: bool = False):
    """Answer a callback query; a plain message has nothing to answer."""
    answer = getattr(source, "answer", None)
    if answer is None:
        return
    try:
        await answer(ui_text(text), show_alert=show_alert)
    except Exception:  # pragma: no cover - an answer must never break a grant
        pass


async def start_grant_duration(source, tier: str):
    """Step 2 — ask how long the tier the owner just picked should last."""
    uid = source.from_user.id
    if uid != OWNER_ID:
        await answer_source(source, "👑 Owner only.", show_alert=True)
        return False
    order = premium_tier_pending.get(uid)
    if not order:
        await answer_source(source, "This grant expired — run /addpremium again.",
                            show_alert=True)
        return False
    resolved = normalize_tier(tier)
    if not resolved:
        await render(source, ui.grant_tier_unknown_text(), ui.admin_back_keyboard())
        return False
    order["tier"] = resolved
    premium_tier_pending[uid] = order
    name = await get_display_name(order["user_id"])
    await render(source, ui.grant_duration_text(order["user_id"], resolved, name,
                                                order.get("days")),
                 ui.grant_duration_keyboard(resolved, order.get("days")))
    return True


#: "No duration was passed at all" — distinct from ``None``, which is a real
#: answer: the Lifetime button grants a premium tier with **no expiry**.
UNSET_DAYS = object()


async def grant_premium_tier(source, tier: str, days=UNSET_DAYS):
    """Finish /addpremium: store the tier flags and notify the user.

    ``days`` overrides the duration typed in the command (the duration buttons
    and the custom-days prompt both pass one); ``None`` means lifetime, and
    :data:`UNSET_DAYS` keeps the duration the owner typed in ``/addpremium``.
    """
    uid = source.from_user.id
    if uid != OWNER_ID:
        await answer_source(source, "👑 Owner only.", show_alert=True)
        return False
    order = premium_tier_pending.pop(uid, None)
    if not order:
        await answer_source(source, "This selection expired — run /addpremium again.",
                            show_alert=True)
        return False
    resolved = normalize_tier(tier)
    if not resolved:
        await render(source, ui.grant_tier_unknown_text(), ui.admin_back_keyboard())
        return False
    target = order["user_id"]
    duration = order.get("days", 30) if days is UNSET_DAYS else days
    # The tier decides the flags *and* the premium_source, so a models-only
    # grant can never inherit the legacy "manual means private" meaning.
    await add_premium(target, duration, tier=resolved)
    name = await get_display_name(target)   # re-checked at grant time
    await render(source, ui.grant_done_text(target, resolved, duration, name),
                 ui.admin_back_keyboard())
    try:
        await say_message(bot, target,
                          ui.grant_activated_user_text(resolved, duration, name))
    except Exception as exc:
        print(f"[PREMIUM NOTIFY FAILED] {exc}", flush=True)
    return True


async def handle_grant_callback(client, query, data: str):
    """``grant_tier:<tier>`` / ``grant_dur:<tier>:<duration>`` / ``grant_back:<tier>``."""
    action, _, rest = data.partition(":")
    uid = query.from_user.id
    if uid != OWNER_ID:
        # Only the owner may grant VIP — a forged callback changes nothing.
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    if action == "grant_back":
        order = premium_tier_pending.get(uid)
        if not order:
            await query.answer(ui_text("This grant expired — run /addpremium again."),
                               show_alert=True)
            return
        order.pop("tier", None)
        name = await get_display_name(order["user_id"])
        await query.answer()
        await render(query, ui.grant_tier_text(order["user_id"], name, order.get("days")),
                     ui.grant_tier_keyboard())
        return
    if action == "grant_tier":
        tier = normalize_tier(rest)
        if not tier:
            await query.answer(ui_text("⚠️ Unknown tier."), show_alert=True)
            return
        await query.answer(ui_text(f"🎖 {GRANT_TIERS[tier]['label']} selected."))
        await start_grant_duration(query, tier)
        return
    if action == "grant_dur":
        tier_part, _, duration = rest.partition(":")
        tier = normalize_tier(tier_part)
        if not tier:
            await query.answer(ui_text("⚠️ Unknown tier."), show_alert=True)
            return
        state, days = parse_grant_duration(duration)
        if state == "invalid":
            await query.answer(ui_text("⚠️ Invalid duration."), show_alert=True)
            return
        if state == "custom":
            order = premium_tier_pending.get(uid)
            if not order:
                await query.answer(ui_text("This grant expired — run /addpremium again."),
                                   show_alert=True)
                return
            order["tier"] = tier
            premium_tier_pending[uid] = order
            pending_action[uid] = "grant_custom_days"
            name = await get_display_name(order["user_id"])
            await query.answer(ui_text("🔢 Send the number of days."))
            await say(query.message, ui.grant_custom_days_text(order["user_id"], tier, name),
                      reply_markup=ui.feedback_keyboard())
            return
        await query.answer(ui_text("💎 Granting VIP…"))
        await grant_premium_tier(query, tier, days=days)
        return
    await query.answer(ui_text("⚠️ Unknown grant action."), show_alert=True)


@callback_action("premium_tier:public")
async def cb_premium_tier_public(client, query):
    """Legacy two-button grant — still honoured, maps onto the granular tiers."""
    await query.answer(ui_text("🌐 Public-only premium"))
    await grant_premium_tier(query, "public")


@callback_action("premium_tier:full")
async def cb_premium_tier_full(client, query):
    """Legacy two-button grant — "full" meant public + private."""
    await query.answer(ui_text("🔓 Full premium"))
    await grant_premium_tier(query, "private")


@bot.on_message(filters.command("removepremium") & filters.private)
@admin_only
async def removepremium_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await say(message, "Usage: `/removepremium USER_ID`")
        return
    try:
        target = int(args[1])
        await remove_premium(target)
        name = await get_display_name(target)
        await say(message, ui.grant_revoked_text(target, name))
    except ValueError:
        await say(message, "❌ Invalid ID")


@bot.on_message(filters.command("premiumlist") & filters.private)
@admin_only
async def premiumlist_handler(client, message):
    premium = await get_premium_users_list()
    if not premium:
        await say(message, "No premium users.")
        return
    text = f"💎 **PREMIUM ({len(premium)})**\n\n"
    for i, u in enumerate(premium[:30], 1):
        exp = u.get("premium_expiry")
        exp_str = exp.strftime("%d/%m/%Y") if exp else "N/A"
        text += f"{i}. `{u['user_id']}` - {exp_str}\n"
    await say(message, text)


@bot.on_message(filters.command("addadmin") & filters.private)
@owner_only
async def addadmin_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await say(message, "Usage: `/addadmin USER_ID`")
        return
    try:
        target = int(args[1])
        await add_admin(target)
        await say(message, f"👑 `{target}` is now admin!")
        #: The new admin's own menu grows the admin commands right away.
        await sync_staff_commands(target, "owner" if target == OWNER_ID else "admin")
        try:
            await say_message(bot, target, "👑 You are now a bot admin!")
        except:
            pass
    except:
        await say(message, "❌ Invalid")


@bot.on_message(filters.command("removeadmin") & filters.private)
@owner_only
async def removeadmin_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await say(message, "Usage: `/removeadmin USER_ID`")
        return
    try:
        target = int(args[1])
        await remove_admin(target)
        await say(message, f"✅ Admin removed from `{target}`")
        #: ...and a revoked admin's menu shrinks back to the user commands.
        await sync_staff_commands(target, "owner" if target == OWNER_ID else "user")
    except:
        await say(message, "❌ Invalid")


@bot.on_message(filters.command("adminlist") & filters.private)
@admin_only
async def adminlist_handler(client, message):
    admins = await get_admins_list()
    text = f"👑 **ADMINS**\n\n👑 Owner: `{OWNER_ID}`\n\n"
    if admins:
        text += f"**Admins ({len(admins)}):**\n"
        for i, u in enumerate(admins, 1):
            text += f"{i}. `{u['user_id']}` - {u.get('name')}\n"
    await say(message, text)


def clean_fsub_label(text: str) -> str | None:
    """Validate an owner-typed button label; ``None`` when it is not usable.

    One line, 1–:data:`config.FSUB_MAX_BUTTON_CHARS` characters, no links,
    ``t.me/`` references or @-mentions.  Emojis and digits are welcome.
    """
    label = (text or "").strip()
    if not label or "\n" in label:
        return None
    if len(label) > FSUB_MAX_BUTTON_CHARS:
        return None
    lowered = label.lower()
    if any(token in lowered for token in ("http://", "https://", "t.me/", "telegram.me/",
                                          "www.", "joinchat", "@")):
        return None
    return label


def chat_kind_of_type(type_value: str) -> str:
    """``"group"`` or ``"channel"`` from a chat type string."""
    return "group" if "group" in str(type_value or "").lower() else "channel"


@bot.on_message(filters.command("setfsub") & filters.private)
@owner_only
async def setfsub_handler(client, message):
    """Step 1 of the add wizard — resolve the chat, then ask for the label."""
    ref = chat_ref_from_text(message.text)
    if not ref:
        await say(message, "Usage: `/setfsub` with a channel link, @username, numeric ID or a "
                           "private invite link — repeat it to add as many entries as you want.")
        return
    uid = message.from_user.id
    try:
        resolved = await resolve_chat_target(ref)
    except InviteRequestSent:
        # Approval-only chat: keep the wizard alive and resolve again once the
        # owner of that chat has approved the bot.
        fsub_pending[uid] = {"step": "await_label", "ref": ref}
        await say(message, ui.fsub_join_pending_text("Private chat"),
                  reply_markup=ui.feedback_keyboard())
        return
    except InviteLinkError as exc:
        print(f"[FSUB] could not resolve {ref!r}: {exc.detail or exc}", flush=True)
        await say(message, ui.setchat_resolve_failed_text(exc.reason),
                  reply_markup=ui.feedback_keyboard())
        return
    await ask_fsub_button_label(message, uid, resolved)


async def ask_fsub_button_label(message, uid, resolved):
    """Admin check, then ask the owner what the Join button should say."""
    ok, reason = await describe_channel_admin(resolved["chat_id"])
    if not ok:
        await say(message, ui.fsub_admin_failed_text(reason, resolved["title"]),
                  reply_markup=ui.feedback_keyboard())
        return
    fsub_pending[uid] = {"step": "await_label", "resolved": resolved}
    await say(message, ui.fsub_button_prompt_text(
        resolved["title"], chat_kind_of_type(resolved.get("type"))),
        reply_markup=ui.feedback_keyboard())


async def complete_fsub_label(message, uid):
    """Step 2 — the owner typed the Join button label (or ``-`` for default)."""
    pending = fsub_pending.get(uid) or {}
    resolved = pending.get("resolved")
    if resolved is None:
        # The chat was waiting for approval: try the stored reference again.
        try:
            resolved = await resolve_chat_target(pending.get("ref"))
        except InviteRequestSent:
            await say(message, ui.fsub_join_pending_text("Private chat"),
                      reply_markup=ui.feedback_keyboard())
            return
        except InviteLinkError as exc:
            fsub_pending.pop(uid, None)
            await say(message, ui.setchat_resolve_failed_text(exc.reason),
                      reply_markup=ui.feedback_keyboard())
            return
        ok, reason = await describe_channel_admin(resolved["chat_id"])
        if not ok:
            fsub_pending.pop(uid, None)
            await say(message, ui.fsub_admin_failed_text(reason, resolved["title"]),
                      reply_markup=ui.feedback_keyboard())
            return
    typed = (message.text or "").strip()
    if typed in {"", "-"}:
        label = ui.default_fsub_label(resolved["title"])
    else:
        label = clean_fsub_label(typed)
        if label is None:
            # The wizard stays open: the owner simply sends a better label.
            await say(message, ui.fsub_label_invalid_text(),
                      reply_markup=ui.feedback_keyboard())
            return
    fsub_pending.pop(uid, None)
    admin_pending.pop(uid, None)
    invite_link = resolved.get("invite_link")
    if not invite_link and not resolved.get("username"):
        # Private chat: mint a fresh link for the button only — it is never
        # echoed back in any message text.
        try:
            invite_link = getattr(
                await floodwait_guard(bot.export_chat_invite_link, resolved["chat_id"]),
                "invite_link", None)
        except Exception as exc:
            print(f"[FSUB] could not export an invite link for "
                  f"{resolved['chat_id']}: {exc}", flush=True)
    item = {
        "chat_id": resolved["chat_id"],
        "title": resolved["title"],
        "username": resolved.get("username"),
        "invite_link": invite_link,
        "button_text": label,
        "kind": chat_kind_of_type(resolved.get("type")),
        "auto_approve": False,
    }
    await add_fsub_item(item)
    items = await get_fsub_list()
    await say(message, ui.fsub_added_text(items[-1]), reply_markup=ui.back_keyboard())
    await show_fsub_list(message)


async def apply_fsub_rename(message, number, text):
    """Store the label typed after **✏️ Rename** was pressed."""
    typed = (text or "").strip()
    if typed in {"", "-"}:
        await say(message, ui.fsub_label_invalid_text(), reply_markup=ui.feedback_keyboard())
        return
    label = clean_fsub_label(typed)
    if label is None:
        await say(message, ui.fsub_label_invalid_text(), reply_markup=ui.feedback_keyboard())
        return
    if not await update_fsub_item(number, button_text=label):
        await say(message, f"❌ No entry number {number}.")
        return
    await say(message, f"✅ Entry {number} button: **{label}**", reply_markup=ui.back_keyboard())
    await show_fsub_list(message)


@bot.on_message(filters.command("delfsub") & filters.private)
@owner_only
async def delfsub_handler(client, message):
    """Remove one entry (``/delfsub 2``) or ask before removing them all."""
    args = (message.text or "").split()[1:]
    if not args or args[0].lower() == "all":
        items = await get_fsub_list()
        if not items:
            await say(message, "ℹ️ Force-sub list is already empty.")
            return
        await say(message, ui.fsub_delete_all_confirm_text(len(items)),
                  reply_markup=ui.fsub_delete_all_keyboard())
        return
    try:
        number = int(args[0])
    except ValueError:
        await say(message, "Usage: `/delfsub 2` — or `/delfsub all` to remove every entry.")
        return
    removed = await remove_fsub_item(number)
    if removed is None:
        await say(message, f"❌ No entry number {number}.")
        return
    await say(message, ui.fsub_removed_text(removed), reply_markup=ui.back_keyboard())
    await show_fsub_list(message)


@bot.on_message(filters.command("fsublist") & filters.private)
@owner_only
async def fsublist_handler(client, message):
    """Numbered list of every required chat with rename / delete buttons."""
    await show_fsub_list(message)


@bot.on_message(filters.command("fsublabel") & filters.private)
@owner_only
async def fsublabel_handler(client, message):
    """Rename an entry's Join button, or the global verify button."""
    args = (message.text or "").split()
    if len(args) < 2:
        await say(message, "Usage: `/fsublabel 1 Join Now` — or `/fsublabel verify ✅ Verified`.")
        return
    if args[1].lower() == "verify":
        label = " ".join(args[2:]).strip()
        if label in {"", "-"}:
            await set_fsub_verify_label(None)
            await say(message, f"✅ Verify button label reset to **{FSUB_VERIFY_LABEL}**.")
            return
        cleaned = clean_fsub_label(label)
        if cleaned is None:
            await say(message, ui.fsub_label_invalid_text())
            return
        await set_fsub_verify_label(cleaned)
        await say(message, f"✅ Verify button label: **{cleaned}**")
        return
    try:
        number = int(args[1])
    except ValueError:
        await say(message, "Usage: `/fsublabel 1 Join Now` — or `/fsublabel verify ✅ Verified`.")
        return
    label = " ".join(args[2:]).strip()
    if label in {"", "-"}:
        await say(message, ui.fsub_label_invalid_text())
        return
    cleaned = clean_fsub_label(label)
    if cleaned is None:
        await say(message, ui.fsub_label_invalid_text())
        return
    if not await update_fsub_item(number, button_text=cleaned):
        await say(message, f"❌ No entry number {number}.")
        return
    await say(message, f"✅ Entry {number} button: **{cleaned}**", reply_markup=ui.back_keyboard())
    await show_fsub_list(message)


@bot.on_message(filters.command("fsubcheck") & filters.private)
@owner_only
async def fsubcheck_handler(client, message):
    """Toggle auto-approval of join requests for one entry or all of them."""
    args = (message.text or "").split()
    if len(args) < 3 or args[2].lower() not in {"on", "off"}:
        await say(message, "Usage: `/fsubcheck 1 on` — or `/fsubcheck all off`.")
        return
    enabled = args[2].lower() == "on"
    target = args[1].lower()
    items = await get_fsub_list()
    if not items:
        await say(message, "ℹ️ Force-sub list is empty.")
        return
    if target == "all":
        for number in range(1, len(items) + 1):
            await update_fsub_item(number, auto_approve=enabled)
    else:
        try:
            number = int(target)
        except ValueError:
            await say(message, "Usage: `/fsubcheck 1 on` — or `/fsubcheck all off`.")
            return
        if not 1 <= number <= len(items):
            await say(message, f"❌ No entry number {number}.")
            return
        await update_fsub_item(number, auto_approve=enabled)
    state = "ON" if enabled else "OFF"
    await say(message, f"✅ Auto-approve **{state}**", reply_markup=ui.back_keyboard())
    await show_fsub_list(message)


@bot.on_message(filters.command("maintenance") & filters.private)
@owner_only
async def maintenance_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        current = await get_maintenance()
        status = "ON 🔧" if current else "OFF ✅"
        await say(message, f"🔧 Maintenance: {status}\n\nUse: `/maintenance on` or `off`")
        return
    mode = args[1].lower()
    if mode == "on":
        await set_maintenance(True)
        await say(message, "🔧 Maintenance: **ON**")
    elif mode == "off":
        await set_maintenance(False)
        await say(message, "✅ Maintenance: **OFF**")
    else:
        await say(message, "Use: on/off")


@bot.on_message(filters.command("feedbacks") & filters.private)
@admin_only
async def feedbacks_handler(client, message):
    feedbacks = await get_all_feedback()
    if not feedbacks:
        await say(message, "No feedback.")
        return
    text = f"💬 **FEEDBACKS ({len(feedbacks)})**\n\n"
    for i, fb in enumerate(feedbacks[:20], 1):
        date = fb.get("date", datetime.now()).strftime("%d/%m %H:%M")
        text += f"**{i}. `{fb['user_id']}`** ({date})\n{fb['message'][:100]}\n\n"
    await say(message, text)


@bot.on_message(filters.command("sendmsg") & filters.private)
@admin_only
async def sendmsg_handler(client, message):
    args = message.text.split(None, 2)
    if len(args) < 3:
        await say(message, "Usage: `/sendmsg USER_ID message`")
        return
    try:
        target = int(args[1])
    except ValueError:
        await say(message, "❌ The first argument must be a numeric user id.")
        return
    body = args[2]
    #: Every outgoing message is offered the same wizard: colour → label →
    #: link → send, with a cancel button on every single step.
    await start_button_wizard(message, {
        "kind": WIZARD_KIND_DM,
        "chat_id": target,
        "text": f"📨 Admin message:\n\n{body}",
        "preview": f"📨 Admin message → {target}",
    })


@bot.on_message(filters.command("clearlogs") & filters.private)
@owner_only
async def clearlogs_handler(client, message):
    await clear_all_logs()
    await say(message, "🗑 Logs cleared!")


@bot.on_message(filters.command("export") & filters.private)
@admin_only
async def export_handler(client, message):
    users = await get_all_users()
    if not users:
        await say(message, "No users.")
        return
    filename = "users_export.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"TOTAL USERS: {len(users)}\n{'=' * 50}\n\n")
        for u in users:
            f.write(
                f"ID: {u['user_id']}\n"
                f"Name: {u.get('name')}\n"
                f"Username: @{u.get('username', 'None')}\n"
                f"Downloads: {u.get('downloads', 0)}\n"
                f"Premium: {u.get('is_premium', False)}\n"
                f"Banned: {u.get('is_banned', False)}\n"
                f"{'=' * 50}\n"
            )
    await message.reply_document(filename, caption=ui_text(f"📊 Users ({len(users)})"))
    try:
        os.remove(filename)
    except:
        pass


@bot.on_message(filters.command("adminhelp") & filters.private)
@admin_only
async def adminhelp_handler(client, message):
    await say(message, admin_help_text())


@bot.on_message(filters.command("addqr") & filters.private)
@owner_only
async def addqr_handler(client, message):
    replied = getattr(message, "reply_to_message", None)
    photo = getattr(replied, "photo", None)
    if photo:
        await set_qr(photo.file_id)
        await say(message, "✅ **Payment QR saved!**\n\nIt will appear after users select a premium plan.")
        return
    pending_action[message.from_user.id] = "qr_upload"
    await say(message, "🖼 **SET PAYMENT QR**\n\nSend the payment QR image as a photo. You can also reply to a QR photo with /addqr.\n\nUse /cancel to exit.", reply_markup=ui.feedback_keyboard())


@bot.on_message(filters.command(["delqr", "removeqr"]) & filters.private)
@owner_only
async def delqr_handler(client, message):
    await delete_qr()
    await say(message, "✅ Payment QR removed.")


@bot.on_message(filters.command("payments") & filters.private)
@admin_only
async def payments_handler(client, message):
    rows = await get_payments()
    await say(message, f"💳 **PAYMENT REVIEWS**\n\nTotal proofs: **{len(rows)}**. Showing the latest 20.")
    for row in rows[:20]:
        note = row.get("note")
        plan = PREMIUM_PLANS.get(note.get("plan"), {}) if isinstance(note, dict) else {}
        caption = (f"👤 User: `{row['user_id']}`\n📦 {plan.get('title', 'Legacy proof')}\n"
                   f"💰 {RUPEE}{plan.get('price', '—')}\n📅 {row.get('date', '—')}\n"
                   "🔎 Verify payment before granting premium.")
        plan_key = note.get("plan") if isinstance(note, dict) else None
        status = row.get("status", "pending_review")
        keyboard = (ui.payment_review_keyboard(row["user_id"], plan_key)
                    if status == "pending_review" else None)
        if isinstance(note, dict) or note == "photo":
            try:
                await bot.send_photo(message.chat.id, row["proof"],
                                     caption=ui_text(caption), reply_markup=keyboard)
            except Exception:
                await say(message, caption + "\n⚠️ Screenshot unavailable.")
        else:
            await say(message, caption + "\n" + str(row.get("proof", "")))


async def update_review_caption(query, status_line: str):
    """Stamp the review verdict onto the owner's payment screenshot."""
    base = getattr(query.message, "caption", None) or ""
    new_caption = ui_text(ui.payment_review_caption(base, status_line))
    editor = getattr(query.message, "edit_caption", None)
    if editor:
        try:
            await editor(new_caption)
            return
        except Exception:
            pass
    try:
        await say_edit(query.message, new_caption)
    except Exception:
        pass


async def latest_payment_note(user_id):
    """Stored note of the newest proof of *user_id* (callback-data fallback)."""
    try:
        rows = await get_payments()
    except Exception:
        return None
    for row in rows:
        if row.get("user_id") == user_id and isinstance(row.get("note"), dict):
            return row["note"]
    return None


async def latest_payment_plan(user_id):
    """Plan key of the newest stored proof of *user_id* (callback fallback)."""
    note = await latest_payment_note(user_id)
    return (note or {}).get("plan")


async def handle_payment_review(client, query, data: str):
    """Owner-only ✅ Approve / ⚠️ Fake / 🚫 Ban actions on a payment proof."""
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("👑 Owner only — payment reviews are restricted."), show_alert=True)
        return
    action, _, rest = (data or "").partition(":")
    parts = rest.split(":") if rest else []
    try:
        target = int(parts[0])
    except (ValueError, IndexError):
        await query.answer(ui_text("Unknown payment reference."), show_alert=True)
        return
    #: ``payok:<user>[:<plan>][:turbo]`` — older proofs carry neither extra part.
    extras = [part.strip().lower() for part in parts[1:] if part.strip()]
    turbo = "turbo" in extras
    plan_key = next((part for part in extras if part != "turbo"), None)
    if not plan_key or not turbo:
        note = await latest_payment_note(target) or {}
        plan_key = plan_key or note.get("plan")
        turbo = turbo or bool(note.get("turbo"))
    plan = PREMIUM_PLANS.get(plan_key) if plan_key else None
    days = plan["days"] if plan else 30
    title = plan["title"] if plan else None

    if action == "payok":
        # A Standard purchase grants public + private exactly as before; the
        # C++ Turbo variant adds the granular ``models`` permission on top.
        await add_premium(target, days, tier="all" if turbo else "private")
        await mark_payment(target, "approved", reviewer=uid, plan=plan_key)
        await query.answer(ui_text("✅ Payment approved — premium activated."))
        await update_review_caption(query, ui.APPROVED_CAPTION)
        user_text = ui.payment_approved_user_text(title, days, turbo=turbo)
    elif action == "payfake":
        await mark_payment(target, "rejected", reviewer=uid)
        await query.answer(ui_text("⚠️ Screenshot marked as fake."))
        await update_review_caption(query, ui.REJECTED_CAPTION)
        user_text = ui.payment_rejected_user_text()
    else:  # payban
        await ban_user(target)
        await mark_payment(target, "banned", reviewer=uid)
        await query.answer(ui_text("🚫 User banned."))
        await update_review_caption(query, ui.BANNED_CAPTION)
        user_text = ui.payment_banned_user_text()

    try:
        await say_message(bot, target, user_text)
    except Exception as exc:
        print(f"[PAYMENT NOTIFY FAILED] {exc}", flush=True)


@bot.on_message(filters.command("redeem") & filters.private)
async def redeem_handler(client, message):
    uid = message.from_user.id
    if await redeem_points(uid, REDEEM_POINTS, months=REDEEM_PREMIUM_MONTHS):
        await say(message, f"✅ Redeemed {REDEEM_POINTS} points for {REDEEM_PREMIUM_MONTHS} month of public-only premium.\n\n{REDEEM_LIMITATION}")
    else:
        await say(message, f"🔒 You need {REDEEM_POINTS} points. Active owner-granted premium cannot be replaced by points premium.")


@bot.on_message(filters.command("setchat") & (filters.private | filters.channel | filters.group))
async def setchat_handler(client, message):
    """Channel dump — step 1: which channel should the bot extract into?"""
    #: An anonymous channel post has no sender, so there is nobody to verify and
    #: nobody to own the registration: stay silent rather than raise.
    if getattr(message, "from_user", None) is None:
        return
    await refresh_profile(message.from_user)
    ref = chat_ref_from_text(message.text)
    in_channel = _chat_kind(message.chat)
    await start_setchat_flow(message, ref, chat=message.chat if (in_channel and not ref) else None)


@bot.on_message(filters.command("delchat") & (filters.private | filters.channel | filters.group))
async def delchat_handler(client, message):
    """Unlink a dump channel — any user for themselves, admins for anyone.

    Round 4: an account may hold up to ``config.MAX_USER_CHANNELS`` channels, so
    a bare ``/delchat`` asks which one to disconnect when two are connected and
    behaves exactly as before when only one is.
    """
    if getattr(message, "from_user", None) is None:
        #: Posted anonymously in a channel: there is no owner to act for.
        return
    uid = message.from_user.id
    args = (message.text or "").split()
    target = uid
    if len(args) > 1:
        if uid != OWNER_ID and not await is_admin(uid):
            await say(message, "🚫 **Admin only command!**")
            return
        try:
            target = int(args[1])
        except ValueError:
            await say(message, "❌ Invalid user id.")
            return
    elif target == uid:
        entries = await get_user_channels(uid)
        if len(entries) > 1:
            await say(message, ui.delchat_choice_text(entries),
                      reply_markup=ui.delchat_choice_keyboard(entries))
            return
    await clear_user_chat(target)
    setchat_pending.pop(target, None)
    await say(message, f"✅ Channel link removed for `{target}`.")


async def cb_delchat_pick(client, query):
    """``delchat_pick:<chat_id>`` — disconnect the channel the user tapped."""
    uid = query.from_user.id
    _, _, raw = (query.data or "").partition(":")
    try:
        chat_id = int(raw)
    except (TypeError, ValueError):
        await query.answer(ui_text("⚠️ This menu is out of date — send /delchat again."),
                           show_alert=True)
        return
    entries = await get_user_channels(uid)
    entry = pick_channel_entry({"channels": entries}, chat_id)
    if entry is None:
        await query.answer(ui_text("⚠️ That channel is no longer connected."), show_alert=True)
        return
    title = entry.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
    await remove_user_channel(uid, chat_id)
    setchat_pending.pop(uid, None)
    await query.answer(ui_text("🗑 Channel disconnected."))
    remaining, counts = await mychannels_snapshot(uid)
    payload, _files = mychannels_payload(remaining, counts) if remaining else (None, 0)
    await render(query, ui.mychannels_disconnected_text(title),
                 ui.mychannels_keyboard(payload, connected=bool(remaining)))


@callback_action("cmd_setchat")
async def cb_setchat(client, query):
    await query.answer()
    await start_setchat_flow(query, chat_ref_from_text(query.data or ""))


@callback_action("setchat:share")
async def cb_setchat_share(client, query):
    """Round 14 — hand a channel over with Telegram's **own** chat chooser.

    Round 7 used a share-sheet deep link: the user shared it *into* the channel
    and the bot read the channel off the message that landed there.  That was
    the last flow that posted into a channel at all — it left a bot link
    sitting in the channel and it could not work for a channel the user did not
    want to write in.  So it is gone.

    The chooser is opened by a reply-keyboard button carrying ``request_chat``;
    Telegram shows the account's own channel list and hands the chosen chat
    straight back in ``message.chat_shared``.  Nothing is pasted, nothing is
    forwarded and **nothing is posted inside the channel**.

    Typing a message link, an ``@username`` or a numeric id is still accepted
    as the fallback — ``pending_action`` stays on ``setchat_share`` for exactly
    that, and ``/cancel`` is the way out.
    """
    uid = query.from_user.id
    entries = await get_user_channels(uid)
    if len(entries) >= max(1, int(MAX_USER_CHANNELS)):
        await query.answer(ui_text("🚫 Channel limit reached."), show_alert=True)
        await render(query, ui.channel_slots_full_text(entries),
                     ui.mychannels_keyboard(entries))
        return
    await query.answer()
    setchat_pending.pop(uid, None)
    pending_action[uid] = "setchat_share"
    #: A reply keyboard cannot be attached to an existing message, so the picker
    #: is a fresh send rather than an edit of the message the button came from.
    #: It stays only as long as this flow does: every way out removes it again.
    await say_with_picker(query.message, ui.setchat_picker_text(),
                          ui.setchat_picker_keyboard(),
                          fallback=ui.setchat_share_prompt_keyboard(None))


#: The ``button_id`` Telegram must echo back for a pick to be ours.
PICKER_BUTTON_IDS = frozenset({int(CHANNEL_PICKER_BUTTON_ID),
                               int(DUMP_PICKER_BUTTON_ID)})


def shared_button_id(message):
    """Return Telegram's chooser button id, supporting older field names."""
    shared = getattr(message, "chat_shared", None)
    if shared is None:
        return None
    value = getattr(shared, "button_id", None)
    if value is None:
        value = getattr(shared, "request_id", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def shared_chat_of(message):
    """The chat Telegram handed over, or ``None`` when nothing was picked.

    ``ChatShared`` carries the chosen chat directly on modern builds
    (``shared.chat``) and only its id on older ones (``shared.chat_id``), and
    the pick is only honoured when it carries the button id this bot asked for.
    """
    shared = getattr(message, "chat_shared", None)
    if shared is None:
        return None
    raw_button_id = getattr(shared, "button_id", None)
    if raw_button_id is None:
        raw_button_id = getattr(shared, "request_id", None)
    button_id = shared_button_id(message)
    if raw_button_id is not None and button_id not in PICKER_BUTTON_IDS:
        print(f"[PICKER] ignored a pick for button_id={raw_button_id!r}", flush=True)
        return None
    chat = getattr(shared, "chat", None)
    if chat is not None and getattr(chat, "id", None) is not None:
        return chat
    chat_id = getattr(shared, "chat_id", None)
    if chat_id is None:
        return None
    return SimpleNamespace(id=int(chat_id), title=None, username=None, type="channel")


@bot.on_message(filters.chat_shared & filters.private)
async def chat_shared_handler(client, message):
    """Route Telegram's native chat-picker result to /setchat or /setdump."""
    if getattr(message, "from_user", None) is None:
        return
    uid = message.from_user.id
    shared = shared_chat_of(message)
    if shared is None:
        #: A pick we did not ask for (or an unreadable one) is simply not ours.
        return
    button_id = shared_button_id(message)
    action = pending_action.get(uid)
    if button_id is not None:
        if button_id == int(DUMP_PICKER_BUTTON_ID):
            if uid != OWNER_ID:
                await say(message, ui.setdump_owner_only_text(),
                          reply_markup=ui.remove_keyboard())
            elif action == "setdump_share":
                await register_picked_dump(message, uid, shared)
            else:
                #: Nobody is waiting for a dump pick: the keyboard is a leftover.
                await say(message, ui.picker_stale_text("setdump"),
                          reply_markup=ui.remove_keyboard())
            return
        if button_id == int(CHANNEL_PICKER_BUTTON_ID):
            if action != "setchat_share" and uid not in setchat_pending:
                #: A stray pick is explained — and the keyboard is taken away
                #: instead of being offered again.
                await say(message, ui.picker_stale_text("setchat"),
                          reply_markup=ui.remove_keyboard())
                return
            await register_picked_channel(message, uid, shared)
            return
    #: Older clients may omit the button id. Use only the currently armed flow;
    #: never infer a dump pick from the user's identity alone.
    if action == "setdump_share":
        if uid != OWNER_ID:
            await say(message, ui.setdump_owner_only_text(),
                      reply_markup=ui.remove_keyboard())
            return
        await register_picked_dump(message, uid, shared)
    elif action == "setchat_share" or uid in setchat_pending:
        await register_picked_channel(message, uid, shared)
    else:
        await say(message, ui.picker_stale_text("setchat"),
                  reply_markup=ui.remove_keyboard())


async def register_picked_dump(message, uid, chat) -> bool:
    """Verify the picker result and connect the owner-only dump workspace."""
    if int(uid) != OWNER_ID:
        await say(message, ui.setdump_owner_only_text(), reply_markup=ui.remove_keyboard())
        return True
    chat_id = int(getattr(chat, "id", 0) or 0)
    kind = chat_type_value(chat)
    if not chat_id or kind != "channel":
        await say(message, ui.setchat_share_failed_text("not_a_channel"),
                  reply_markup=ui.setdump_picker_keyboard())
        return True
    requester_ok, requester_reason = await describe_requester_admin(chat_id, uid)
    if not requester_ok:
        reason = "requester_not_admin" if requester_reason == "not_admin" else "error"
        await say(message, ui.dump_admin_failed_text(reason),
                  reply_markup=ui.setdump_picker_keyboard())
        return True
    ok, reason = await describe_channel_admin(chat_id, require_delete=True)
    if not ok:
        await say(message, ui.dump_admin_failed_text(reason),
                  reply_markup=ui.setdump_picker_keyboard())
        return True
    title = chat_title(chat, chat_id)
    username = getattr(chat, "username", None)
    await set_dump_channel(chat_id, title, username, kind)
    pending_action.pop(uid, None)
    setchat_pending.pop(uid, None)
    await say(message, ui.setdump_done_text(title, chat_id),
              reply_markup=ui.dump_status_keyboard(True))
    #: The confirmation carries the inline dashboard, so the keyboard is
    #: removed by the silent message instead.
    await dismiss_picker_keyboard(uid)
    print(f"[DUMP] connected chat={chat_id} by the owner via picker", flush=True)
    return True


async def register_picked_channel(message, uid, chat) -> bool:
    """Verify and store the channel the owner just picked.

    Shares its whole verification tail with the link path, so the two ways in
    can never drift apart: the cap, the requester's admin rights, the bot's
    posting rights and the final confirmation are identical.
    """
    chat_id = int(getattr(chat, "id", 0) or 0)
    kind = chat_type_value(chat)
    title = chat_title(chat, chat_id)
    username = getattr(chat, "username", None)
    if not chat_id or kind not in {"channel", "supergroup", "group"}:
        await say(message, ui.setchat_share_failed_text("not_a_channel"),
                  reply_markup=ui.remove_keyboard())
        return True

    entries = await get_user_channels(uid)
    known = {int(entry["chat_id"]) for entry in entries}
    if chat_id not in known and len(entries) >= max(1, int(MAX_USER_CHANNELS)):
        pending_action.pop(uid, None)
        await say(message, ui.channel_slots_full_text(entries),
                  reply_markup=ui.mychannels_keyboard(entries))
        await dismiss_picker_keyboard(uid)
        return True

    await say(message, ui.setchat_share_resolved_text(title))
    return await finish_channel_registration(
        message, uid, chat_id=chat_id, title=title, username=username,
        kind=kind or "channel", done_keyboard=ui.remove_keyboard())


async def register_shared_channel(message, uid) -> bool:
    """Register a channel from a **message link** — never from a forward.

    Round 12 replaced the old "forward one post" step with this: the user
    long-presses any post in the channel, taps *Copy Link* and sends that link
    into the bot.  The link already names the channel **and** points at a real
    post, so the same message answers both verifications:

    * the person sending it must administer the channel, and
    * the bot must be an admin there with **Post Messages** and must be able to
      read that exact post.

    Returns ``True`` when the message was consumed by this step (so the caller
    stops), whatever the outcome — a failure keeps the wizard alive for another
    try and always explains itself in plain English.
    """
    text = (getattr(message, "text", None) or "").strip()
    chat_target, msg_id, _is_private = parse_link(text)

    #: Round 14 — the fallback accepts a message link, an ``@username`` or a
    #: numeric id.  A link doubles as the readability proof; a bare reference
    #: has no post to point at, so the two admin checks carry it alone.
    if chat_target is None or msg_id is None:
        kind, value = classify_chat_ref(text)
        if kind == "unknown":
            await say(message, ui.setchat_share_failed_text("not_received"),
                      reply_markup=ui.feedback_keyboard())
            return True
        ref = value if kind == "numeric" else text
        try:
            resolved = await resolve_chat_target(ref)
        except InviteRequestSent:
            await say(message, ui.setchat_join_request_text("this channel"),
                      reply_markup=ui.feedback_keyboard())
            return True
        except InviteLinkError as exc:
            reason = "bot_not_in_chat" if exc.reason == "no_access" else "cannot_see"
            await say(message, ui.setchat_share_failed_text(reason),
                      reply_markup=ui.feedback_keyboard())
            return True
        except Exception as exc:
            print(f"[SETCHAT LINK] cannot resolve {text!r}: {exc}", flush=True)
            await say(message, ui.setchat_share_failed_text("cannot_see"),
                      reply_markup=ui.feedback_keyboard())
            return True
        if not resolved or not resolved.get("chat_id"):
            await say(message, ui.setchat_share_failed_text("cannot_see"),
                      reply_markup=ui.feedback_keyboard())
            return True
        await say(message, ui.setchat_share_resolved_text(
            resolved.get("title") or str(resolved["chat_id"])))
        return await finish_channel_registration(
            message, uid, chat_id=int(resolved["chat_id"]),
            title=resolved.get("title") or str(resolved["chat_id"]),
            username=resolved.get("username"),
            kind=resolved.get("type") or "channel")

    try:
        resolved = await resolve_chat_target(text)
    except InviteRequestSent:
        await say(message, ui.setchat_join_request_text("this channel"),
                  reply_markup=ui.feedback_keyboard())
        return True
    except InviteLinkError as exc:
        reason = "bot_not_in_chat" if exc.reason == "no_access" else "cannot_see"
        await say(message, ui.setchat_share_failed_text(reason),
                  reply_markup=ui.feedback_keyboard())
        return True
    except Exception as exc:
        print(f"[SETCHAT LINK] cannot resolve {text!r}: {exc}", flush=True)
        await say(message, ui.setchat_share_failed_text("cannot_see"),
                  reply_markup=ui.feedback_keyboard())
        return True

    chat_id = int(resolved["chat_id"])
    title = resolved.get("title") or str(chat_id)
    if resolved.get("type") not in {"channel", "supergroup", "group"}:
        await say(message, ui.setchat_share_failed_text("not_a_channel"),
                  reply_markup=ui.feedback_keyboard())
        return True

    entries = await get_user_channels(uid)
    known = {int(entry["chat_id"]) for entry in entries}
    if chat_id not in known and len(entries) >= max(1, int(MAX_USER_CHANNELS)):
        pending_action.pop(uid, None)
        await say(message, ui.channel_slots_full_text(entries),
                  reply_markup=ui.mychannels_keyboard(entries))
        await dismiss_picker_keyboard(uid)
        return True

    await say(message, ui.setchat_share_resolved_text(title))

    #: Verification 1 (round 5): the person connecting it must administer it.
    person_ok, person_reason = await describe_requester_admin(chat_id, uid)
    if not person_ok:
        setchat_pending.pop(uid, None)
        pending_action.pop(uid, None)       # "Setup cancelled": the flow is over
        await say(message, ui.setchat_requester_failed_text(person_reason, title))
        await dismiss_picker_keyboard(uid)
        return True

    #: Verification 2: the bot must be an admin with Post Messages.
    ok, reason = await describe_channel_admin(chat_id)
    if not ok:
        #: The wizard stays alive so the owner can fix the rights and press
        #: **🔍 Check Admin Status** again.
        setchat_pending[uid] = {
            "chat_id": chat_id, "title": title, "username": resolved.get("username"),
            "step": "await_check", "invite_link": None,
            "type": resolved.get("type") or "channel",
        }
        await say(message, ui.setchat_admin_failed_text(reason),
                  reply_markup=ui.setchat_check_keyboard())
        return True

    #: Verification 3: that exact post must be readable — the link is the proof.
    sample = None
    try:
        sample = await floodwait_guard(bot.get_messages, chat_target, msg_id)
    except Exception as exc:
        print(f"[SETCHAT LINK] sample read failed chat={chat_id}: {exc}", flush=True)
    if not sample or getattr(sample, "empty", False):
        await say(message, ui.setchat_share_failed_text("cannot_see"),
                  reply_markup=ui.feedback_keyboard())
        return True

    stored, why = await add_user_channel(uid, chat_id, title, resolved.get("username"),
                                         resolved.get("type") or "channel")
    if not stored:
        if why == "full":
            entries = await get_user_channels(uid)
            await say(message, ui.channel_slots_full_text(entries),
                      reply_markup=ui.mychannels_keyboard(entries))
            pending_action.pop(uid, None)
            setchat_pending.pop(uid, None)
            await dismiss_picker_keyboard(uid)
        else:
            await say(message, ui.setchat_share_failed_text("cannot_see"),
                      reply_markup=ui.feedback_keyboard())
        return True
    setchat_pending.pop(uid, None)
    pending_action.pop(uid, None)
    await say(message, ui.setchat_done_text(title, chat_id), reply_markup=ui.back_keyboard())
    #: Typing the link instead of using the picker must not leave it behind.
    await dismiss_picker_keyboard(uid)
    print(f"[SETCHAT] message link registered chat={chat_id} for user={uid}", flush=True)
    return True


async def finish_channel_registration(message, uid, *, chat_id, title, username,
                                      kind, done_keyboard=None) -> bool:
    """The verification tail both ways in share: requester, bot, store, confirm.

    Round 14's picker and the link/username fallback must never drift apart, so
    the two checks that decide whether a channel may be connected — the picker
    administers it, and the bot may post in it — live here once and are run by
    both.  ``done_keyboard`` lets the picker hand back a
    :class:`ReplyKeyboardRemove` instead of an inline menu, because the picker
    screen is the only one that put a reply keyboard on the screen.
    """
    chat_id = int(chat_id)

    #: Verification 1 (round 5): the person connecting it must administer it.
    person_ok, person_reason = await describe_requester_admin(chat_id, uid)
    if not person_ok:
        setchat_pending.pop(uid, None)
        pending_action.pop(uid, None)
        await say(message, ui.setchat_requester_failed_text(person_reason, title),
                  reply_markup=done_keyboard or ui.back_keyboard())
        await dismiss_picker_keyboard(uid)
        return True

    #: Verification 2: the bot must be an admin with Post Messages.
    ok, reason = await describe_channel_admin(chat_id)
    if not ok:
        #: The wizard stays alive so the rights can be fixed and re-checked.
        setchat_pending[uid] = {
            "chat_id": chat_id, "title": title, "username": username,
            "step": "await_check", "invite_link": None, "type": kind or "channel",
        }
        await say(message, ui.setchat_admin_failed_text(reason),
                  reply_markup=ui.setchat_check_keyboard())
        return True

    stored, why = await add_user_channel(uid, chat_id, title, username, kind or "channel")
    if not stored:
        if why == "full":
            entries = await get_user_channels(uid)
            await say(message, ui.channel_slots_full_text(entries),
                      reply_markup=ui.mychannels_keyboard(entries))
            setchat_pending.pop(uid, None)
            pending_action.pop(uid, None)
            await dismiss_picker_keyboard(uid)
        else:
            await say(message, ui.setchat_share_failed_text("cannot_see"),
                      reply_markup=ui.feedback_keyboard())
        return True
    setchat_pending.pop(uid, None)
    pending_action.pop(uid, None)
    await say(message, ui.setchat_done_text(title, chat_id),
              reply_markup=done_keyboard or ui.back_keyboard())
    #: No-op when the reply already carried the removal (the picker path).
    await dismiss_picker_keyboard(uid)
    print(f"[SETCHAT] registered chat={chat_id} for user={uid}", flush=True)
    return True


@callback_action("setchat:check")
async def cb_setchat_check(client, query):
    """Step 2 — verify the bot is an admin with posting rights."""
    uid = query.from_user.id
    pending = setchat_pending.get(uid)
    if not pending:
        await query.answer(ui_text("This setup expired — send /setchat again."), show_alert=True)
        return
    if pending.get("chat_id") is None:
        # The chat was approval-only: the owner may have approved us by now, so
        # resolve the stored reference again before checking anything.
        await query.answer(ui_text("🔍 Checking admin rights…"))
        try:
            resolved = await resolve_chat_target(pending.get("ref"))
        except InviteRequestSent:
            await render(query, ui.setchat_join_request_text("this chat"),
                         ui.setchat_check_keyboard())
            return
        except Exception as exc:
            print(f"[SETCHAT] retry resolve failed: {exc}", flush=True)
            await render(query, ui.setchat_resolve_failed_text(
                getattr(exc, "reason", "unresolved")), ui.setchat_check_keyboard())
            return
        pending.update({
            "chat_id": resolved["chat_id"], "title": resolved["title"],
            "username": resolved["username"], "invite_link": resolved.get("invite_link"),
            "type": resolved.get("type") or "", "step": "await_check",
        })
        setchat_pending[uid] = pending
        await render(query, ui.setchat_admin_hint_text(pending["title"]),
                     ui.setchat_check_keyboard())
        return
    await query.answer(ui_text("🔍 Checking admin rights…"))
    #: Round 5 — verify the **person** adding the channel first.  A plain
    #: member, a non-member or an inconclusive Telegram answer cancels the
    #: wizard outright and stores nothing.
    person_ok, person_reason = await describe_requester_admin(pending["chat_id"], uid)
    if not person_ok:
        setchat_pending.pop(uid, None)
        pending_action.pop(uid, None)
        await render(query,
                     ui.setchat_requester_failed_text(person_reason, pending.get("title")),
                     ui.back_keyboard())
        await dismiss_picker_keyboard(uid)
        return
    #: The bot's own admin + Post Messages check stays a separate step: both
    #: must pass before the channel can be registered.
    ok, reason = await describe_channel_admin(pending["chat_id"])
    if ok:
        pending["step"] = "await_sample"
        setchat_pending[uid] = pending
        #: A private channel has no public link, so step 3 asks for a share of
        #: one post instead of a content link.
        private = bool(pending.get("invite_link")) or not pending.get("username")
        await render(query, ui.setchat_admin_ok_text(pending["title"], private=private),
                     ui.feedback_keyboard())
    else:
        await render(query, ui.setchat_admin_failed_text(reason), ui.setchat_check_keyboard())


# --------------------------------------------------------------------------- #
#  /mychannels — the user's dump-channel dashboard
# --------------------------------------------------------------------------- #

async def mychannels_snapshot(uid):
    """``(entries, per-channel file counts)`` for one user's dump channels.

    Round 4 made this a list: every account may keep up to
    ``config.MAX_USER_CHANNELS`` channels connected, each with its **own**
    counter, so the dashboard reads them separately instead of sharing one.
    """
    entries = await get_user_channels(uid)
    counts = [await get_channel_files(entry["chat_id"]) for entry in entries]
    return entries, counts


def mychannels_payload(entries, counts):
    """Shape the dashboard arguments: one entry stays a dict, two become a list.

    Keeping the single-channel shape identical is what makes every existing
    reader (and every legacy Mongo document) render exactly as before.
    """
    if len(entries) == 1:
        return entries[0], counts[0]
    return entries, counts


async def show_mychannels(source):
    """List every connected dump channel with its rights and file counter."""
    uid = source.from_user.id
    await ensure_user(source.from_user)
    entries, counts = await mychannels_snapshot(uid)
    if not entries:
        await render(source, ui.mychannels_empty_text(),
                     ui.mychannels_keyboard(None, connected=False))
        return
    entry, files = mychannels_payload(entries, counts)
    decision = await resolve_engine_for(uid, record=False)
    await render(source, ui.mychannels_text(entry, files=files, engine=decision.engine),
                 ui.mychannels_keyboard(entry))


@callback_action("cmd_mychannels")
async def cb_mychannels(client, query):
    await query.answer()
    await show_mychannels(query)


async def mychannels_permission_check(query, entry, *, reverify: bool = False):
    """Run the real admin/posting-rights probe behind the dashboard buttons.

    **Test Permissions** only reports; **Re-verify Admin** additionally refreshes
    the stored title and username when Telegram says the rights are fine again.
    """
    uid = query.from_user.id
    chat_id = int(entry["chat_id"])
    title = entry.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
    await query.answer(ui_text("🔍 Checking bot permissions…"))
    ok, reason = await describe_channel_admin(chat_id)
    if reverify and ok:
        try:
            chat = await bot.get_chat(chat_id)
            title = chat_title(chat, chat_id)
            #: add_user_channel refreshes this one entry and leaves the other
            #: connected channel (and its counter) completely alone.
            await add_user_channel(uid, chat_id, title, getattr(chat, "username", None))
        except Exception as exc:
            print(f"[MYCHANNELS] refresh failed for {chat_id}: {exc}", flush=True)
    entries, counts = await mychannels_snapshot(uid)
    entry, _files = mychannels_payload(entries, counts) if entries else (None, 0)
    await render(query, ui.mychannels_test_text(title, ok, reason),
                 ui.mychannels_keyboard(entry if entry else chat_id))


async def handle_mychannels_callback(client, query, data: str):
    """``mych_test:<id>`` / ``mych_verify:<id>`` / ``mych_del:<id>``.

    The id in the button is checked against the caller's own stored channel, so
    a stale or hand-forged callback can never touch somebody else's dump chat.
    """
    action, _, raw = data.partition(":")
    uid = query.from_user.id
    try:
        chat_id = int(raw)
    except (TypeError, ValueError):
        await query.answer(ui_text("⚠️ This dashboard is out of date — send /mychannels."),
                           show_alert=True)
        return
    #: The id in the button is checked against the caller's **own list** of
    #: channels, so a stale or hand-forged callback can never touch another
    #: user's dump chat — or a channel this user already disconnected.
    entries = await get_user_channels(uid)
    entry = pick_channel_entry({"channels": entries}, chat_id)
    if entry is None:
        await query.answer(ui_text("⚠️ That channel is no longer connected."), show_alert=True)
        await show_mychannels(query)
        return
    if action == "mych_del":
        title = entry.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
        #: Only this channel goes: the other one keeps working and keeps its
        #: own file counter.
        await remove_user_channel(uid, chat_id)
        setchat_pending.pop(uid, None)
        await query.answer(ui_text("🗑 Channel disconnected."))
        remaining, counts = await mychannels_snapshot(uid)
        payload, _files = mychannels_payload(remaining, counts) if remaining else (None, 0)
        await render(query, ui.mychannels_disconnected_text(title),
                     ui.mychannels_keyboard(payload, connected=bool(remaining)))
        return
    await mychannels_permission_check(query, entry, reverify=(action == "mych_verify"))


def bot_self_id():
    """Id of the bot account, or ``None`` while the client is still connecting."""
    try:
        return getattr(getattr(bot, "me", None), "id", None)
    except Exception:  # pragma: no cover - only when pyrogram is disconnected
        return None


def private_user_context(message, actor=None):
    actor = actor or getattr(message, "from_user", None)
    chat = getattr(message, "chat", None)
    return (actor is not None and chat is not None
            and getattr(chat, "id", None) == actor.id
            and chat_type_value(chat) not in {"channel", "supergroup", "group"})


def is_channel_context(message) -> bool:
    """True when *message* lives in a channel/group rather than a private chat.

    Inside a dump channel the bot never advertises or accepts personal commands,
    and every limit it reports points back to the bot with a ``url=`` button.
    """
    if isinstance(message, ChannelRequester):
        return True
    chat = getattr(message, "chat", None)
    if chat_type_value(chat) in {"channel", "supergroup", "group"}:
        return True
    sender_chat = getattr(message, "sender_chat", None)
    return sender_chat is not None


#: Callback prefixes that only ever exist on a message the bot itself posted
#: inside a dump channel (download controls and the custom-caption prompt).
CHANNEL_CALLBACK_PREFIXES = ("dl:", "cap_yes:", "cap_no:")


def query_in_channel(query) -> bool:
    """True when a button was pressed inside a channel/group rather than a DM."""
    message = getattr(query, "message", None)
    return message is not None and is_channel_context(message)


def channel_callback_allowed(query) -> bool:
    """A channel button press is honoured only on the bot's own message.

    A dashboard callback that arrives from a channel (a forwarded press, a
    stale client, a crafted request) is dropped completely silently — not even
    a ``query.answer`` toast, because a dump channel is not a bot dashboard.
    """
    if not query_in_channel(query):
        return True
    if (getattr(query, "data", "") or "") in {"cmd_login", "cmd_logout", "cancel_login"}:
        return False
    if is_own_message(getattr(query, "message", None)):
        return True
    #: The download-control and caption prompts are only ever rendered by the
    #: bot itself, so they are the channel's own vocabulary.
    return (getattr(query, "data", None) or "").startswith(CHANNEL_CALLBACK_PREFIXES)


def is_own_message(message) -> bool:
    """True for posts written by the bot itself (never extract from those).

    Otherwise the bot would answer its own extraction status messages and loop
    forever inside a dump channel.
    """
    if getattr(message, "outgoing", False):
        return True
    sender = getattr(message, "from_user", None)
    if sender is None:
        return False
    if getattr(sender, "is_self", False):
        return True
    self_id = bot_self_id()
    return self_id is not None and getattr(sender, "id", None) == self_id


@bot.on_message((filters.channel | filters.group) & filters.text)
async def channel_dump_handler(client, message):
    """Auto-extraction inside a channel that completed /setchat."""
    if is_own_message(message):
        return
    text = (message.text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        # Channel vocabulary only: /setchat, /delchat and owner/admin commands.
        # Every personal command is a silent no-op here — zero replies, edits
        # or sends — so the channel never turns into a second bot dashboard.
        await dispatch_channel_command(client, message)
        return
    touch_scheduler()
    #: The share-sheet deep link: inside a channel this *is* the registration
    #: proof, so it is handled before any link extraction is considered.
    if await handle_share_deep_link(message):
        return
    if "t.me/" not in text:
        return
    owner_row = await find_user_chat_owner(message.chat.id)
    if not owner_row:
        return
    user_id = int(owner_row["user_id"])
    if await is_banned(user_id):
        return
    if await get_maintenance() and user_id != OWNER_ID:
        return
    try:
        await extract_channel_links(message, owner_row)
    except FloodWait as error:
        # Last-resort guard: never hammer Telegram into restricting the bot.
        print(f"[CHANNEL FLOODWAIT] {error}", flush=True)
        await floodwait_sleep(floodwait_seconds(error))
    except Exception as exc:
        print(f"[CHANNEL DUMP ERROR] {exc}", flush=True)


# --------------------------------------------------------------------------- #
#  /setengine — the owner's global engine controller (AUTO / LOCK C++ / LOCK PY)
# --------------------------------------------------------------------------- #

async def show_engine_controller(source):
    """Render the controller screen: mode, live traffic and the routing rules."""
    await ENGINE_CONTROLLER.load_mode()
    snapshot = await engine_status_snapshot()
    await render(source, ui.engine_controller_text(ENGINE_CONTROLLER.mode, snapshot),
                 ui.engine_controller_keyboard(ENGINE_CONTROLLER.mode))


async def apply_engine_mode(source, mode: str):
    """Persist a controller mode and apply it to this process immediately.

    Writing to the database first is what makes a lock survive a restart; the
    in-memory controller is updated right after, so the very next extraction is
    already routed by the new mode.
    """
    resolved = engines.normalize_mode(mode)
    try:
        await set_engine_mode(resolved)
    except Exception as exc:
        print(f"[ENGINE MODE PERSIST FAILED] {exc}", flush=True)
        await render(source, "⚠️ **Could not save the engine mode**\n\n"
                             "The database did not accept the change, so nothing "
                             "was applied. Please try again.")
        return None
    ENGINE_CONTROLLER.set_mode(resolved)
    print(f"[ENGINE MODE] {resolved} (set by {getattr(source.from_user, 'id', '?')})",
          flush=True)
    await query_answer_if_possible(source, f"✅ {engines.ENGINE_MODE_LABELS[resolved]}")
    await render(source, ui.engine_mode_set_text(resolved),
                 ui.engine_controller_keyboard(resolved))
    return resolved, await engine_status_snapshot()


async def query_answer_if_possible(source, text):
    """Toast a callback press; a typed command has nothing to toast."""
    answer = getattr(source, "answer", None)
    if answer is None:
        return
    try:
        await answer(ui_text(text))
    except Exception:  # pragma: no cover - a toast must never break a mode change
        pass


@bot.on_message(filters.command("setengine") & filters.private)
@owner_only
async def setengine_handler(client, message):
    """/setengine — panel, or ``/setengine auto|cpp|python`` to lock it directly."""
    args = (message.text or "").split()[1:]
    if not args:
        await show_engine_controller(message)
        return
    mode = engines.parse_mode_argument(args[0])
    if mode is None:
        await say(message, "❌ **Unknown engine mode**\n\n"
                           "Use `/setengine auto`, `/setengine cpp` or "
                           "`/setengine python` — or send /setengine alone for "
                           "the button panel.")
        return
    await apply_engine_mode(message, mode)


@callback_action("cmd_setengine")
async def cb_setengine(client, query):
    if query.from_user.id != OWNER_ID and not await is_admin(query.from_user.id):
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    await query.answer()
    await show_engine_controller(query)


async def handle_engine_mode_callback(client, query, data: str):
    """``engine_mode:auto|lock_cpp|lock_python`` — owner only, it is a global force."""
    if query.from_user.id != OWNER_ID:
        await query.answer(ui_text("👑 Owner only — this lock is global."), show_alert=True)
        return
    mode = engines.parse_mode_argument(data.split(":", 1)[1])
    if mode is None:
        await query.answer(ui_text("⚠️ Unknown engine mode."), show_alert=True)
        return
    # apply_engine_mode answers the press itself, so the owner sees the new mode.
    await apply_engine_mode(query, mode)


@bot.on_message(filters.command(["admin", "admins"]) & filters.private)
@admin_only
async def admin_handler(client, message):
    """Full command list plus the paginated inline panel."""
    await say(message, admin_help_text(), reply_markup=admin_panel_keyboard())


# --------------------------------------------------------------------------- #
#  /setchat — channel dump (auto-extraction straight into a channel)
#
#  Step 1: the user sends the channel link / @username / numeric id.
#  Step 2: the bot verifies it is an admin there with "Post Messages" rights.
#  Step 3: a sample message link proves the bot can actually read the channel.
# --------------------------------------------------------------------------- #

def chat_ref_from_text(text: str):
    """Second word of a command line, e.g. ``/setchat t.me/mychannel``."""
    parts = (text or "").split()
    for part in parts[1:]:
        if not part.startswith("/"):
            return part
    return None


class InviteLinkError(Exception):
    """A chat reference could not be resolved, with a user-facing reason."""

    def __init__(self, reason: str = "unresolved", detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def chat_type_value(chat) -> str:
    """``"channel"`` / ``"supergroup"`` / ``"group"`` / ``""`` for a chat object."""
    chat_type = getattr(chat, "type", None)
    return str(getattr(chat_type, "value", chat_type) or "").lower()


def raw_chat_type_value(raw_chat) -> str:
    """Type of a raw (MTProto) chat object."""
    name = type(raw_chat).__name__.lower()
    if "channel" in name:
        return "channel"
    if "chat" in name:
        return "group"
    return ""


def raw_chat_id(raw_chat) -> int:
    """High-level id of a raw Channel / Chat object."""
    raw_id = getattr(raw_chat, "id", None)
    if raw_id is None:
        raise InviteLinkError("invalid", "invite link returned no chat")
    if isinstance(raw_chat, (raw.types.Chat, raw.types.ChatForbidden)):
        return -raw_id
    return utils.ZERO_CHANNEL_ID - raw_id


def chat_title(chat, chat_id=None) -> str:
    """Title of a chat, falling back to a readable placeholder (never None)."""
    title = getattr(chat, "title", None)
    if title:
        return str(title)
    if chat_id is None:
        chat_id = getattr(chat, "id", None)
    return CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)


def classify_chat_ref(ref):
    """``(kind, value)`` for any supported chat reference.

    ``kind`` is ``numeric`` (a chat id), ``invite`` (a private invite hash),
    ``public`` (a @username / t.me/username) or ``unknown``.
    """
    ref = (ref or "").strip()
    if not ref:
        return "unknown", None
    if re.fullmatch(r"-?\d+", ref):
        return "numeric", int(ref)
    match = re.search(r"(?:t\.me|telegram\.me)/(?:\+|joinchat/)([A-Za-z0-9_-]+)", ref, re.I)
    if match:
        return "invite", match.group(1)
    match = re.search(r"(?:t\.me|telegram\.me)/c/(\d+)", ref, re.I)
    if match:
        return "numeric", int("-100" + match.group(1))
    match = re.search(r"(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{3,})", ref, re.I)
    if match:
        return "public", match.group(1)
    if ref.startswith("@"):
        name = ref[1:]
        return ("public", name) if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", name) else ("unknown", None)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", ref):
        return "public", ref
    return "unknown", None


async def _resolve_invite_link(ref, invite_hash):
    """Resolve a private invite link, joining only when that is really needed."""
    check = raw.functions.messages.CheckChatInvite(hash=invite_hash)
    try:
        result = await floodwait_guard(bot.invoke, check)
    except UserAlreadyParticipant:
        # Already inside: re-checking answers with the chat itself.
        result = await floodwait_guard(bot.invoke, check)
    except (InviteHashExpired, InviteSlugExpired) as exc:
        raise InviteLinkError("expired", str(exc))
    except InviteHashInvalid as exc:
        raise InviteLinkError("invalid", str(exc))
    except (ChannelPrivate, ChatAdminRequired, PeerIdInvalid) as exc:
        raise InviteLinkError("no_access", str(exc))
    if isinstance(result, raw.types.ChatInviteAlready):
        return _invite_result(result.chat, ref)
    if isinstance(result, (raw.types.ChatInvite, raw.types.ChatInvitePeek)):
        try:
            joined = await floodwait_guard(bot.join_chat, ref)
        except UserAlreadyParticipant:
            result = await floodwait_guard(bot.invoke, check)
            return _invite_result(result.chat, ref)
        return {
            "chat_id": joined.id,
            "title": chat_title(joined, joined.id),
            "username": getattr(joined, "username", None),
            "invite_link": ref,
            "type": chat_type_value(joined),
        }
    raise InviteLinkError("invalid", f"unexpected CheckChatInvite answer: {result!r}")


def _invite_result(raw_chat, ref):
    chat_id = raw_chat_id(raw_chat)
    return {
        "chat_id": chat_id,
        "title": chat_title(raw_chat, chat_id),
        "username": getattr(raw_chat, "username", None),
        "invite_link": ref,
        "type": raw_chat_type_value(raw_chat),
    }


async def resolve_chat_target(ref):
    """Resolve *any* chat reference to a dict, or raise :class:`InviteLinkError`.

    Numeric ids, public @usernames, ``t.me/username`` links (with or without a
    message id), ``t.me/c/<id>/<msg>`` and private invite links
    (``t.me/+hash`` / ``t.me/joinchat/hash``) are all supported.
    ``InviteRequestSent`` is re-raised unchanged so callers can explain the
    approval-only case to the owner.
    """
    #: A numeric id may arrive as an int (``/pin`` resolves a link's chat id),
    #: and the reference grammar below is written for text.
    ref = "" if ref is None else str(ref).strip()
    kind, value = classify_chat_ref(ref)
    if kind == "unknown":
        raise InviteLinkError("unresolved", f"unrecognised chat reference {ref!r}")
    if kind == "invite":
        return await _resolve_invite_link(ref, value)
    try:
        chat = await floodwait_guard(bot.get_chat, value)
    except (ChannelPrivate, ChatAdminRequired, PeerIdInvalid) as exc:
        raise InviteLinkError("no_access", str(exc))
    except InviteRequestSent:
        raise
    except Exception as exc:
        raise InviteLinkError("unresolved", str(exc))
    chat_id = getattr(chat, "id", None)
    if chat_id is None:
        raise InviteLinkError("unresolved", f"no id for {ref!r}")
    return {
        "chat_id": chat_id,
        "title": chat_title(chat, chat_id),
        "username": getattr(chat, "username", None),
        "invite_link": None,
        "type": chat_type_value(chat),
    }


async def resolve_chat_ref(ref):
    """Resolve a chat reference → ``(id, title, username)`` (legacy shape)."""
    resolved = await resolve_chat_target(ref)
    return resolved["chat_id"], resolved["title"], resolved["username"]


def _chat_kind(chat) -> bool:
    """True when *chat* can be a dump target (channel, supergroup or group)."""
    value = chat_type_value(chat)
    return "channel" in value or "group" in value


async def start_setchat_flow(source, ref=None, chat=None):
    """Entry point for the wizard, reachable from /setchat and the inline menu."""
    uid = source.from_user.id
    await refresh_profile(source.from_user)
    if not ref and chat is None:
        pending_action[uid] = "setchat"
        #: Round 7 — the prompt offers the share path for private channels,
        #: which have no link to paste.
        await render(source, ui.setchat_prompt_text(), ui.setchat_prompt_keyboard())
        return False
    if chat is not None:
        # Command posted inside the channel/group: we already hold its details.
        resolved = {
            "chat_id": chat.id, "title": chat_title(chat, chat.id),
            "username": getattr(chat, "username", None), "invite_link": None,
            "type": chat_type_value(chat),
        }
    else:
        try:
            resolved = await resolve_chat_target(ref)
        except InviteRequestSent:
            # Approval-only chat: the bot sent a join request and now waits for
            # the owner of that chat.  Nothing is stored yet, and the wizard
            # stays alive so **🔍 Check Admin Status** can be pressed again.
            setchat_pending[uid] = {
                "chat_id": None, "title": "Private chat", "username": None,
                "step": "await_approval", "ref": ref,
            }
            pending_action.pop(uid, None)
            await render(source, ui.setchat_join_request_text("this chat"),
                         ui.setchat_check_keyboard())
            return False
        except InviteLinkError as exc:
            print(f"[SETCHAT] could not resolve {ref!r}: {exc.detail or exc}", flush=True)
            pending_action[uid] = "setchat"
            await render(
                source,
                ui.setchat_resolve_failed_text(exc.reason) + "\n\n" + ui.setchat_prompt_text(),
                ui.feedback_keyboard(),
            )
            return False
    if not resolved or not resolved.get("chat_id"):
        pending_action[uid] = "setchat"
        await render(
            source,
            ui.setchat_resolve_failed_text("unresolved") + "\n\n" + ui.setchat_prompt_text(),
            ui.feedback_keyboard(),
        )
        return False
    chat_id, title, username = resolved["chat_id"], resolved["title"], resolved["username"]
    #: Round 4 — refuse a third channel *before* running the user through the
    #: whole wizard, and say plainly that one has to be disconnected first.
    entries = await get_user_channels(uid)
    known = {int(entry["chat_id"]) for entry in entries}
    if int(chat_id) not in known and len(entries) >= max(1, int(MAX_USER_CHANNELS)):
        pending_action.pop(uid, None)
        setchat_pending.pop(uid, None)
        await render(source, ui.channel_slots_full_text(entries),
                     ui.mychannels_keyboard(entries))
        return False
    setchat_pending[uid] = {
        "chat_id": chat_id, "title": title, "username": username,
        "step": "await_check", "invite_link": resolved.get("invite_link"),
        "type": resolved.get("type") or "",
    }
    pending_action.pop(uid, None)
    await render(source, ui.setchat_admin_hint_text(title), ui.setchat_check_keyboard())
    return True


async def describe_channel_admin(chat_id, *, require_delete: bool = False):
    """``(ok, reason)`` — the truthful admin state of the bot in *chat_id*.

    Kurigram keeps posting rights in ``ChatMember.privileges``
    (:class:`pyrogram.types.ChatAdministratorRights`); ``ChatMember`` itself has
    no ``can_post_messages`` attribute at all, so that is the only place they
    can be read from.  ``reason`` is one of ``ok``, ``not_admin``,
    ``no_post_rights`` or ``error``.
    """
    try:
        me = await floodwait_guard(bot.get_me)
        member = await floodwait_guard(bot.get_chat_member, chat_id, me.id)
    except Exception as exc:
        print(f"[SETCHAT] admin check error for {chat_id}: {exc}", flush=True)
        return False, "error"
    status = getattr(getattr(member, "status", None), "value", getattr(member, "status", None))
    status = str(status).lower()
    privileges = getattr(member, "privileges", None)
    can_post = getattr(privileges, "can_post_messages", None)
    can_manage = getattr(privileges, "can_manage_chat", None)
    can_delete = getattr(privileges, "can_delete_messages", None)
    # Always log the raw values: this is what a deployment gets debugged from.
    print(f"[SETCHAT] admin check chat={chat_id} status={status!r} "
          f"privileges={'set' if privileges is not None else 'none'} "
          f"can_post_messages={can_post!r} can_delete_messages={can_delete!r} "
          f"can_manage_chat={can_manage!r}", flush=True)
    if status in {"owner", "creator"}:
        return True, "ok"
    if status != "administrator":
        return False, "not_admin"
    if can_post is False or (require_delete and can_post is not True):
        return False, "no_post_rights"
    if require_delete and can_delete is not True:
        return False, "no_delete_rights"
    # Channel and supergroup admins carry their rights in ``privileges``.
    rights = [can_post, can_manage]
    if all(right is None for right in rights):
        # Telegram reports no posting right for this chat type (basic group or
        # legacy parser): the sample message plus the first real send are the
        # true proof, so the ordinary /setchat wizard may continue. Dump setup
        # is stricter because an un-deletable stage would leak workspace copies.
        return (False, "no_delete_rights") if require_delete else (True, "ok")
    return (True, "ok") if can_post else (False, "no_post_rights")


async def verify_channel_admin(chat_id) -> bool:
    """True when the bot may post in *chat_id* (see :func:`describe_channel_admin`)."""
    ok, _reason = await describe_channel_admin(chat_id)
    return ok


#: Membership states that Telegram reports for somebody who may **not** manage a
#: chat.  Anything outside these two sets is treated as inconclusive.
REQUESTER_ADMIN_STATUSES = {"owner", "creator", "administrator"}
REQUESTER_MEMBER_STATUSES = {"member", "restricted", "left", "banned"}


async def describe_requester_admin(chat_id, user_id):
    """``(ok, reason)`` — may *this person* connect *chat_id* to the bot?

    Round 5: the bot verifies that whoever is adding the channel actually
    administers it.  ``reason`` is ``ok``, ``not_admin``, ``not_member`` or
    ``error``.

    Unlike force-sub — which fails **open** so a Telegram hiccup never locks a
    user out of the bot — an inconclusive answer here fails **safe**: the caller
    cancels the wizard and stores nothing, because registering a channel on an
    uncertain answer is how a stranger gets somebody else's channel connected.
    """
    try:
        member = await floodwait_guard(bot.get_chat_member, chat_id, int(user_id))
    except UserNotParticipant:
        return False, "not_member"
    except Exception as exc:
        print(f"[SETCHAT] requester check error chat={chat_id} user={user_id}: {exc}",
              flush=True)
        return False, "error"
    status = getattr(getattr(member, "status", None), "value", getattr(member, "status", None))
    status = str(status or "").lower()
    print(f"[SETCHAT] requester check chat={chat_id} user={user_id} status={status!r}",
          flush=True)
    if status in REQUESTER_ADMIN_STATUSES:
        return True, "ok"
    if status in REQUESTER_MEMBER_STATUSES:
        return False, "not_admin"
    #: An answer this build does not recognise proves nothing — fail safe.
    return False, "error"


async def verify_requester_admin(chat_id, user_id) -> bool:
    """True when *user_id* administers *chat_id* (see :func:`describe_requester_admin`)."""
    ok, _reason = await describe_requester_admin(chat_id, user_id)
    return ok


async def complete_setchat(message, uid, pending) -> bool:
    """Store the verified channel and close the wizard.

    The per-user cap is enforced here as well as at the start of the flow, so a
    wizard that was left open while the user connected another channel still
    cannot push the account over ``config.MAX_USER_CHANNELS``.
    """
    chat_id = pending["chat_id"]
    ok, reason = await add_user_channel(uid, chat_id, pending.get("title"),
                                        pending.get("username"), pending.get("type"))
    if not ok and reason == "full":
        entries = await get_user_channels(uid)
        await say(message, ui.channel_slots_full_text(entries),
                  reply_markup=ui.mychannels_keyboard(entries))
        return False
    setchat_pending.pop(uid, None)
    pending_action.pop(uid, None)
    await say(
        message,
        ui.setchat_done_text(pending.get("title") or str(chat_id), chat_id),
        reply_markup=ui.back_keyboard(),
    )
    await dismiss_picker_keyboard(uid)
    return True


async def verify_setchat_sample(message, uid, text) -> bool:
    """Step 3 — one real post proves the bot can read *this* channel.

    Round 8 dropped the bare message number: ``15`` says nothing about which
    chat it came from, so it could not confirm the post belongs to the channel
    being registered.  The bot now resolves a **content link**, reads the
    message and compares the chat it lives in with the pending registration.
    A private channel has no public link, so a share (forward) of one of its
    posts is accepted as the equivalent proof.
    """
    pending = setchat_pending.get(uid)
    if not pending:
        return False
    chat_id = pending["chat_id"]

    text = (text or "").strip()
    chat_target, msg_id, _is_private = parse_link(text)
    if chat_target is None or msg_id is None:
        #: A bare number is refused with its own explanation; anything else that
        #: is not a link gets the generic "send a content link" next step.
        reason = "not_a_link" if re.fullmatch(r"\d+", text) else "unreadable"
        await say(message, ui.setchat_sample_failed_text(reason))
        return False

    reason = "unreadable"
    sample = None
    try:
        sample = await floodwait_guard(bot.get_messages, chat_target, msg_id)
    except (ChannelPrivate, ChatAdminRequired, UserNotParticipant):
        reason = "no_access"
    except PeerIdInvalid:
        reason = "wrong_chat"
    except Exception as exc:
        print(f"[SETCHAT] sample check failed: {exc}", flush=True)
    if not sample or getattr(sample, "empty", False):
        await say(message, ui.setchat_sample_failed_text(reason))
        return False

    #: The decisive check: the post must belong to the channel being registered.
    sample_chat = getattr(getattr(sample, "chat", None), "id", None)
    if sample_chat is not None and int(sample_chat) != int(chat_id):
        await say(message, ui.setchat_sample_failed_text("wrong_chat"))
        return False
    return await complete_setchat(message, uid, pending)


class BatchProgress:
    """The one aggregate status message of a batch, safe under concurrency.

    Every edit goes through a single :class:`asyncio.Lock` and the line counts
    *finished* items rather than "the item I happen to be", so two 🚀 C++ Turbo
    workers editing at the same time can never interleave nonsense into the
    same message.  Each item still owns its **own** per-item status message.
    """

    def __init__(self, status, total: int):
        self.status = status
        self.total = max(0, int(total))
        self.done = 0
        self._lock = asyncio.Lock()

    async def advance(self, count: int = 1) -> None:
        async with self._lock:
            self.done = min(self.total, self.done + max(0, int(count)))
            try:
                await say_edit(self.status, ui.batch_progress_text(self.done, self.total))
            except Exception:  # a progress edit must never break a download
                pass

    async def finish(self, success: int, failed: int) -> None:
        async with self._lock:
            try:
                await say_edit(self.status, ui.batch_done_text(success, failed))
            except Exception:  # pragma: no cover - the tally is best effort
                pass


async def run_private_batch(message, items, *, heading: str | None = None,
                            status=None, sleeper=asyncio.sleep,
                            start_gap: float | None = None,
                            engine=None) -> engines.BatchResult:
    """Run one private-chat batch — multi-link **or** range — on the engine.

    ``items`` is a list of ``(label, link)`` pairs in the order the user sent
    them.  This is the private-chat twin of :func:`extract_channel_links`: both
    delegate to :func:`engines.run_engine_batch`, so 🚀 C++ Turbo overlaps the
    slow parts of up to ``ENGINE_TURBO_WORKERS`` files here too, while ⚙️ Python
    Standard stays strictly sequential in the order sent.

    A single engine decision is resolved for the whole batch (one batch, one
    engine — exactly what the telemetry HUD reports), and the anti-ban start gap
    comes from :data:`config.ENGINE_START_GAP_SECONDS`.
    """
    user_id = message.from_user.id
    items = list(items or [])
    decision = engine if isinstance(engine, engines.EngineDecision) \
        else await resolve_engine_for(user_id)
    total = len(items)
    #: A range flow already owns one status message (it printed the pre-flight
    #: report there) — reuse it instead of opening a second one.
    if status is None:
        status = await say(message, heading or ui.batch_heading_text(total))
    elif heading:
        await say_edit(status, heading)
    progress = BatchProgress(status, total)

    async def run_item(index, item):
        """Extract one item; returns ``True`` / ``False`` / ``"cancelled"``."""
        label, link = item
        status = None
        try:
            chat_target, msg_id, is_private = parse_link(link)
            if chat_target is None:
                return False
            status = await say(message, ui.batch_item_text(label))
            if is_private:
                if not await private_access(user_id):
                    await say_edit(status, ui.app_private_link_text(),
                                   reply_markup=await private_link_keyboard())
                    return False
                fetch_client = await get_user_client(user_id)
                if not fetch_client:
                    await say_edit(status, ui.private_login_text())
                    return False
            else:
                fetch_client = bot
            return await fetch_and_send(message, status, fetch_client,
                                        chat_target, msg_id, engine=decision)
        except FloodWait as error:
            # One throttled item pauses; it must never kill the whole batch.
            seconds = floodwait_seconds(error)
            if status is not None:
                await say_edit(status, ui.channel_floodwait_text(seconds))
            await sleeper(seconds)
            return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[BATCH ITEM FAILED] {type(exc).__name__}: {exc}", flush=True)
            return False
        finally:
            await progress.advance()

    gap = ENGINE_START_GAP_SECONDS if start_gap is None else start_gap
    batch = await engines.run_engine_batch(items, run_item, decision,
                                           sleeper=sleeper, start_gap=gap)
    await progress.finish(batch.success, batch.failed)
    return batch


class ChannelRequester:
    """Adapts a channel post to the per-user extraction pipeline."""

    def __init__(self, message, user_row):
        self.message = message
        self.chat = message.chat
        self.id = message.id
        self.from_user = SimpleNamespace(
            id=int(user_row["user_id"]),
            first_name=user_row.get("name") or "User",
            username=user_row.get("username"),
        )

    async def reply(self, text, **kwargs):
        return await self.message.reply(text, **kwargs)


@asynccontextmanager
async def channel_rate_limit(chat_id, *, sleeper=asyncio.sleep):
    """One extraction at a time per channel plus the anti-ban cooldown.

    Serialising the requests and sleeping between them is what keeps the bot
    from being throttled — or worse, restricted — by Telegram.
    """
    lock = channel_locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        last = channel_last_request.get(chat_id)
        now = asyncio.get_running_loop().time()
        if last is not None:
            wait = CHANNEL_EXTRACT_COOLDOWN - (now - last)
            if wait > 0:
                await sleeper(wait)
        channel_last_request[chat_id] = asyncio.get_running_loop().time()
        yield


def collect_channel_links(text: str, premium: bool):
    """Return ``(links, max_allowed)`` for a channel post."""
    range_match = re.fullmatch(r"\s*(\S*t\.me/\S+)/(\d+)-(\d+)\s*", text or "")
    if range_match:
        base, start, end = range_match.group(1), int(range_match.group(2)), int(range_match.group(3))
        total = end - start + 1
        return [f"{base}/{i}" for i in range(start, end + 1)], (1000 if premium else 20), total
    links = [line.strip() for line in (text or "").split("\n") if "t.me/" in line]
    return links, (50 if premium else 5), len(links)


def channel_range_of(text: str):
    """``(base_link, start, end)`` when a channel post is a single range request."""
    match = re.fullmatch(r"\s*(\S*t\.me/\S+)/(\d+)-(\d+)\s*", text or "")
    if not match:
        return None
    return match.group(1), int(match.group(2)), int(match.group(3))


# --------------------------------------------------------------------------- #
#  Range pre-flight — count what actually exists *before* the batch starts
#
#  A range like ``t.me/channel/1-500`` used to start blindly: missing, deleted
#  and contentless messages were discovered one by one mid-batch, so the run
#  stalled and the final tally was misleading.  The scan below asks Telegram for
#  the ids in batches (``get_messages`` accepts a list), classifies them, and
#  reports the counts up front.
# --------------------------------------------------------------------------- #

#: The scan found media worth downloading.
PREFLIGHT_MEDIA = "media"
#: The scan found a message, but it only holds text.
PREFLIGHT_TEXT = "text"
#: Deleted, empty or otherwise inaccessible — never attempted.
PREFLIGHT_MISSING = "missing"
#: The scan itself could not read this chunk (a probe failure is not proof that
#: the message is gone, so these ids stay in the batch).
PREFLIGHT_UNREADABLE = "unreadable"


def classify_preflight_message(msg) -> str:
    """Which pre-flight bucket one scanned message falls into."""
    if msg is None or getattr(msg, "empty", False):
        return PREFLIGHT_MISSING
    if getattr(msg, "media", None):
        return PREFLIGHT_MEDIA
    for kind in ("photo", "video", "document", "audio", "voice",
                 "video_note", "sticker", "animation"):
        if getattr(msg, kind, None):
            return PREFLIGHT_MEDIA
    if getattr(msg, "text", None) or getattr(msg, "caption", None):
        return PREFLIGHT_TEXT
    return PREFLIGHT_MISSING


@dataclass
class RangePreflight:
    """What a requested range really holds, counted before anything downloads.

    ``media + text_only + unreadable`` is exactly the number of items the batch
    will attempt, and ``missing`` is exactly the number it will not — which is
    what lets the final ``Done!`` tally reconcile with the pre-flight report.
    """

    start: int = 0
    end: int = 0
    #: Requested ids, in the order the user asked for them.
    ids: list = field(default_factory=list)
    #: id -> one of the ``PREFLIGHT_*`` buckets.
    kinds: dict = field(default_factory=dict)
    #: Seconds a FloodWait forced the scan to pause (0 when Telegram was happy).
    floodwait_seconds: int = 0
    #: ``get_messages`` calls the scan made (batched — never one request per id).
    requests: int = 0

    # -- counts ------------------------------------------------------------- #
    def count(self, kind: str) -> int:
        return sum(1 for value in self.kinds.values() if value == kind)

    @property
    def media(self) -> int:
        return self.count(PREFLIGHT_MEDIA)

    @property
    def text_only(self) -> int:
        return self.count(PREFLIGHT_TEXT)

    @property
    def missing(self) -> int:
        return self.count(PREFLIGHT_MISSING)

    @property
    def unreadable(self) -> int:
        return self.count(PREFLIGHT_UNREADABLE)

    @property
    def requested(self) -> int:
        return len(self.ids)

    @property
    def extractable(self) -> list:
        """Ids worth attempting, in the order sent.

        A chunk the scan could not read at all stays in the batch: a failed
        probe is never treated as proof that a message does not exist.
        """
        skip = {PREFLIGHT_MISSING}
        return [mid for mid in self.ids if self.kinds.get(mid) not in skip]

    @property
    def empty(self) -> bool:
        """True when nothing at all can be extracted (no quota may be spent)."""
        return not self.extractable


async def preflight_range(fetch_client, chat_target, ids, *, batch=None,
                          sleeper=asyncio.sleep, notify=None) -> RangePreflight:
    """Classify every id of a range with batched ``get_messages`` calls.

    ``batch``    ids per request (``config.RANGE_PREFLIGHT_BATCH``) — the scan is
                 never one request per id, which would both stall the run and
                 invite a FloodWait.
    ``notify``   optional ``await notify(seconds)`` called when Telegram asks for
                 a pause, so the user sees why the scan is taking longer.

    Rate limits are respected: a ``FloodWait`` pauses for the requested seconds
    and the chunk is retried once.  Any other failure degrades gracefully — the
    affected ids are marked unreadable and stay in the batch, so a broken probe
    can never silently drop a user's files.
    """
    ids = [int(mid) for mid in (ids or [])]
    scan = RangePreflight(start=ids[0] if ids else 0, end=ids[-1] if ids else 0,
                          ids=list(ids))
    if not ids:
        return scan
    #: Nothing to scan with is not evidence that the messages are gone: every
    #: id is reported "could not be checked" and stays in the batch.
    if fetch_client is None:
        scan.kinds = {mid: PREFLIGHT_UNREADABLE for mid in ids}
        return scan
    size = max(1, int(batch or RANGE_PREFLIGHT_BATCH))
    getter = getattr(fetch_client, "get_messages", None)
    if getter is None:                      # a client that cannot scan at all
        scan.kinds = {mid: PREFLIGHT_UNREADABLE for mid in ids}
        return scan

    for offset in range(0, len(ids), size):
        chunk = ids[offset:offset + size]
        scan.requests += 1
        try:
            found = await getter(chat_target, chunk)
        except FloodWait as error:
            # Telegram asked for a pause: wait it out, then retry the chunk.
            seconds = floodwait_seconds(error)
            scan.floodwait_seconds += seconds
            print(f"[RANGE PREFLIGHT] FloodWait {seconds}s on {len(chunk)} ids",
                  flush=True)
            if notify is not None:
                try:
                    await notify(seconds)
                except Exception:  # a status edit must never break the scan
                    pass
            await sleeper(seconds)
            try:
                found = await getter(chat_target, chunk)
            except Exception as exc:
                print(f"[RANGE PREFLIGHT] retry failed: {exc}", flush=True)
                found = None
        except Exception as exc:
            print(f"[RANGE PREFLIGHT] scan failed: {type(exc).__name__}: {exc}",
                  flush=True)
            found = None

        items = list(found) if isinstance(found, (list, tuple)) else (
            [found] if found is not None else [])
        by_id = {}
        for item in items:
            item_id = getattr(item, "id", None)
            if item_id is not None:
                try:
                    by_id[int(item_id)] = item
                except (TypeError, ValueError):
                    continue
        aligned = len(items) == len(chunk)
        for position, mid in enumerate(chunk):
            item = by_id.get(mid)
            if item is None and aligned:
                #: Kurigram answers a list request with one slot per id, so a
                #: hole in an aligned answer really is a missing message.
                item = items[position]
            if item is None and not aligned:
                #: A short or unidentifiable answer did not cover this id and
                #: therefore proves nothing about it: keep it in the batch
                #: instead of silently dropping one of the user's files.
                scan.kinds[mid] = PREFLIGHT_UNREADABLE
                continue
            scan.kinds[mid] = classify_preflight_message(item)
    return scan


async def channel_scan_client(user_id, base_link, first_id):
    """``(client, chat_target)`` able to read a channel post's range, or Nones.

    The pre-flight scan must read the source with the same client that will
    later download it: the bot for public channels, the user's own session for
    private/restricted ones (and only when that user actually holds private
    access and has a session logged in).
    """
    chat_target, _msg_id, is_private = parse_link(f"{base_link}/{int(first_id)}")
    if chat_target is None:
        return None, None
    if not is_private:
        return bot, chat_target
    if not await private_access(user_id):
        return None, None
    client = await get_user_client(user_id)
    return (client, chat_target) if client else (None, None)


async def extract_channel_links(message, user_row, *, sleeper=asyncio.sleep):
    """Extraction behaviour for a registered dump channel.

    The same public / premium-private rules apply as in private chat, requests
    are rate limited and every Telegram FloodWait answer turns into a safe pause.
    """
    user_id = int(user_row["user_id"])
    text = (message.text or "").strip()
    chat_id = message.chat.id
    premium = user_id == OWNER_ID or await is_premium(user_id)
    links, max_links, total = collect_channel_links(text, premium)
    if not links:
        return 0, 0
    requested_range = channel_range_of(text)
    if total > max_links:
        #: A limit hit **inside a dump channel** points back to the bot with a
        #: url= button; personal commands are never advertised or accepted here.
        #: A range post gets the range wording, a multi-link post the link one.
        notice = (ui.channel_limit_text("range", requested=total, premium=premium)
                  if requested_range else
                  ui.channel_limit_text("links", sent=total, premium=premium))
        await say(message, notice, reply_markup=ui.open_bot_keyboard())
        return 0, 0

    #: Range posts are counted before they start, exactly like in private chat.
    scan = None
    if requested_range:
        base_link, start, end = requested_range
        scan_client, scan_target = await channel_scan_client(user_id, base_link, start)
        if scan_client is not None:
            scan = await preflight_range(
                scan_client, scan_target, range(start, end + 1), sleeper=sleeper)
            await say(message, ui.range_preflight_text(
                start, end, scan.media, scan.text_only, scan.missing,
                scan.unreadable))
            if scan.empty:
                await say(message, ui.range_nothing_to_extract_text(
                    start, end, scan.missing), reply_markup=ui.open_bot_keyboard())
                return 0, 0
            links = [f"{base_link}/{mid}" for mid in scan.extractable]
            total = len(links)

    if not premium and user_id != OWNER_ID:
        allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
        #: The quota is reserved against the items that will *actually* be
        #: extracted, not the raw size of the range the user typed.
        if not allowed or current + len(links) > FREE_DAILY_LIMIT:
            await say(message, ui.channel_limit_text("daily", used=current),
                      reply_markup=ui.open_bot_keyboard())
            return 0, 0

    use_custom_caption = False
    custom_caption = await get_caption(user_id)
    if custom_caption:
        import secrets
        token = secrets.token_hex(6)
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        question_msg = await say(
            message,
            ui.channel_caption_question_text(),
            reply_markup=ui.channel_caption_keyboard(token)
        )
        caption_pending[token] = {
            "future": future,
            "owner_id": user_id,
            "question_msg": question_msg,
            "token": token,
        }
        try:
            use_custom_caption = await asyncio.wait_for(future, timeout=CHANNEL_CAPTION_TIMEOUT)
        except asyncio.TimeoutError:
            caption_pending.pop(token, None)
            try:
                await question_msg.delete()
            except Exception:
                pass
            return 0, 0
        finally:
            caption_pending.pop(token, None)

    requester = ChannelRequester(message, user_row)
    #: One decision per batch: every link of this post runs on the same engine,
    #: which is also what the telemetry HUD reports.
    decision = await resolve_engine_for(user_id)

    async def run_link(index, link):
        """Extract one link; returns ``True`` / ``False`` / ``"cancelled"``."""
        chat_target, msg_id, is_private = parse_link(link)
        if chat_target is None:
            return False
        status = await say(message,
                           f"⏳ Fetching {index}/{len(links)}… {ui.engine_icon(decision.engine)}")
        if is_private and not await private_access(user_id):
            await say_edit(status, ui.app_private_link_text(),
                           reply_markup=await private_link_keyboard())
            return False
        fetch_client = bot
        if is_private:
            fetch_client = await get_user_client(user_id)
            if not fetch_client:
                await say_edit(status, ui.private_login_text(),
                               reply_markup=await private_link_keyboard())
                return False
        try:
            return await fetch_and_send(
                requester, status, fetch_client, chat_target, msg_id,
                enforce_fsub=False, cleanup_errors=True,
                use_custom_caption=use_custom_caption, engine=decision,
            )
        except FloodWait as error:
            # Defensive: pausing is always better than hammering Telegram.
            seconds = floodwait_seconds(error)
            await say_edit(status, ui.channel_floodwait_text(seconds))
            await sleeper(seconds)
            return False

    #: The very same engine-aware runner the two private-chat batch paths use:
    #: 🚀 C++ Turbo spreads the post over its bounded worker pool, ⚙️ Python
    #: Standard stays strictly sequential in the order posted.
    async with channel_rate_limit(chat_id, sleeper=sleeper):
        batch = await engines.run_engine_batch(
            links, run_link, decision, sleeper=sleeper,
            start_gap=ENGINE_START_GAP_SECONDS)
    success, failed = batch.as_tuple()
    if success:
        # /mychannels reports how many files landed in this channel.
        try:
            await increment_channel_files(chat_id, success)
        except Exception as exc:
            print(f"[CHANNEL STATS FAILED] {exc}", flush=True)
    return success, failed


async def submit_payment_proof(message):
    uid = message.from_user.id
    order = payment_pending.get(uid)
    if not order:
        pending_action.pop(uid, None)
        await say(message, "⚠️ Checkout expired. Open /premium and choose your plan again.")
        return
    plan = PREMIUM_PLANS[order["plan"]]
    #: The C++ Turbo variant charges base + add-on and grants the models flag.
    turbo = bool(order.get("turbo"))
    amount = plan_total_price(plan) if turbo else plan_base_price(plan)
    price_label = f"{RUPEE}{amount}"
    # Persist proof + plan + variant before attempting delivery to Telegram.
    saved = await add_payment(uid, message.photo.file_id, {
        "plan": order["plan"], "price": amount, "days": plan["days"],
        "turbo": turbo,
        "message_id": message.id, "checkout": order["token"],
    })
    pending_action.pop(uid, None)
    payment_pending.pop(uid, None)
    if saved is None:
        await say(message, "ℹ️ **This payment proof is already submitted for review.**")
        return
    delivered = False
    caption = ui.payment_review_owner_text(uid, plan["title"], price_label,
                                           plan["days"], turbo)
    review_keyboard = ui.payment_review_keyboard(uid, order["plan"], turbo=turbo)
    # A bot cannot initiate a private chat. OWNER_ID should belong to
    # @XyrDeveloper, who must /start this bot; the username is a best-effort copy.
    for recipient in dict.fromkeys([OWNER_ID, PAYMENT_CONTACT]):
        if not recipient:
            continue
        try:
            await bot.send_photo(recipient, message.photo.file_id,
                                 caption=ui_text(caption), reply_markup=review_keyboard)
            delivered = True
        except Exception:
            continue
    if delivered:
        text = ui.payment_submitted_text(plan["title"], price_label, turbo)
    else:
        text = ui.payment_proof_saved_text()
    await say(message, text, reply_markup=ui.back_keyboard())


@bot.on_message(filters.photo & filters.private)
async def photo_handler(client, message):
    await refresh_profile(getattr(message, "from_user", None))
    user_id = message.from_user.id
    #: Round 14 — a photo the user's session just copied into this chat is the
    #: delivery itself.  Swallow the echo once, never re-process it.
    if consume_echo_guard(user_id, message):
        return
    if pending_action.get(user_id) == "payment_proof":
        await submit_payment_proof(message)
        return
    if pending_action.get(user_id) == "qr_upload":
        if user_id != OWNER_ID:
            await say(message, "Only the owner can upload the payment QR.")
            return
        await set_qr(message.photo.file_id)
        del pending_action[user_id]
        await say(message, "✅ **Payment QR saved.**\n\nUsers will see this image after selecting a plan in /premium.")
        return
    if pending_action.get(user_id) == "thumbnail":
        await set_thumbnail(user_id, message.photo.file_id)
        del pending_action[user_id]
        await say(message, "✅ Thumbnail saved!")


async def handle_download_controls(query):
    """Pause / resume / stop an active download."""
    data = query.data
    user_id = query.from_user.id
    try:
        _, action, job_id = data.split(":", 2)
        job = active_downloads.get(job_id)
        if not job or job["user_id"] != user_id:
            await query.answer(ui_text("This download is no longer active."), show_alert=True)
            return
        if action == "p":
            job["paused"] = True
            job["event"].clear()
            await query.message.edit_reply_markup(ui.download_controls(job_id, paused=True))
            await query.answer(ui_text("⏸ Download paused"))
        elif action == "r":
            job["paused"] = False
            job["event"].set()
            await query.message.edit_reply_markup(ui.download_controls(job_id))
            await query.answer(ui_text("▶️ Download resumed"))
        elif action == "s":
            job["cancelled"] = True
            job["paused"] = False
            job["event"].set()
            task = job.get("task")
            if task and not task.done():
                task.cancel()
            await query.answer(ui_text("⛔ Stopping download..."))
    except Exception:
        await query.answer(ui_text("Could not control this download."), show_alert=True)


async def handle_caption_choice(client, query):
    """Handle ✅ Yes / ❌ No choice for custom caption in dump channels."""
    action, token = query.data.split(":", 1)
    entry = caption_pending.get(token)
    if not entry or entry["future"].done():
        await query.answer(ui_text("⚠️ This question has expired."), show_alert=True)
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if query.from_user.id != entry["owner_id"]:
        await query.answer(ui_text("⚠️ Only the channel owner can answer this."), show_alert=True)
        return

    choice = (action == "cap_yes")
    await query.answer()
    try:
        await entry["question_msg"].delete()
    except Exception:
        try:
            await query.message.delete()
        except Exception:
            pass

    if not entry["future"].done():
        entry["future"].set_result(choice)


# --------------------------------------------------------------------------- #
#  Owner deep links — one tap and the channel (or the dump) registers itself
#
#  The share-sheet button sends ``https://t.me/<bot>?start=<kind><token>`` into
#  a channel the user picks.  The bot is an admin there, so it *sees* that
#  message and learns the chat id straight from it — no invite link, no raw id,
#  no forwarded post, nothing to copy by hand.
# --------------------------------------------------------------------------- #

#: token -> {"kind", "user_id", "created", "ttl"}
SHARE_TOKENS: dict = {}
#: deep-link prefix -> what the token registers.
SHARE_KINDS = {"ch": "setchat", "dp": "setdump"}
SHARE_PREFIXES = {"setchat": "ch", "setdump": "dp"}
#: ``t.me/<bot>?start=ch…`` / ``…=dp…`` inside any message text.
SHARE_LINK_RE = re.compile(
    rf"t\.me/{re.escape(BOT_USERNAME)}\?start=(ch|dp)([0-9a-fA-F]{{8,}})", re.IGNORECASE)


def issue_share_token(uid, kind, *, ttl=None):
    """Mint a one-purpose token (private channels have no other identity path)."""
    token = secrets.token_hex(6)
    now = time.time()
    SHARE_TOKENS[token] = {"kind": kind, "user_id": int(uid), "created": now,
                           "ttl": float(CHANNEL_SHARE_TOKEN_TTL if ttl is None else ttl)}
    # Opportunistic sweep so a long-running process cannot grow forever.
    for key, value in list(SHARE_TOKENS.items()):
        if now - value.get("created", 0) > value.get("ttl", 0):
            SHARE_TOKENS.pop(key, None)
    return token


def share_deep_link(uid, kind) -> str:
    """The link the share-sheet button carries."""
    return (f"https://t.me/{BOT_USERNAME}?start="
            f"{SHARE_PREFIXES[kind]}{issue_share_token(uid, kind)}")


def find_share_token(text):
    """The live token a message carries, or ``None`` (expired/forged → ignored)."""
    match = SHARE_LINK_RE.search(text or "")
    if not match:
        return None
    prefix, token = match.group(1).lower(), match.group(2)
    entry = SHARE_TOKENS.get(token)
    if not entry or entry.get("kind") != SHARE_KINDS.get(prefix):
        return None
    if time.time() - entry.get("created", 0) > entry.get("ttl", 0):
        SHARE_TOKENS.pop(token, None)
        return None
    return entry


async def dm_user(uid, text, keyboard=None, **kwargs):
    """Send a screen to a user's private chat (used when the click happened in a channel)."""
    try:
        return await say_message(bot, int(uid), text, reply_markup=keyboard, **kwargs)
    except Exception as exc:
        print(f"[DM FAILED] user={uid}: {type(exc).__name__}: {exc}", flush=True)
        if isinstance(keyboard, ReplyKeyboardMarkup):
            #: A refused picker must not swallow the explanation with it.
            try:
                return await say_message(bot, int(uid), text, **kwargs)
            except Exception:
                pass
        return None


async def register_dump_from_ping(message, uid, chat) -> bool:
    """A shared deep link landed in the owner's dump channel: connect it."""
    if int(uid) != OWNER_ID:
        await dm_user(uid, ui.setdump_owner_only_text() if hasattr(ui, "setdump_owner_only_text")
                      else "👑 Owner only.")
        return True
    chat_id = int(getattr(chat, "id", 0) or 0)
    kind = chat_type_value(chat)
    title = chat_title(chat, chat_id)
    if not chat_id or kind != "channel":
        await dm_user(uid, ui.setchat_share_failed_text("not_a_channel"))
        return True
    requester_ok, requester_reason = await describe_requester_admin(chat_id, uid)
    if not requester_ok:
        reason = "requester_not_admin" if requester_reason == "not_admin" else "error"
        await dm_user(uid, ui.dump_admin_failed_text(reason))
        return True
    ok, reason = await describe_channel_admin(chat_id, require_delete=True)
    if not ok:
        await dm_user(uid, ui.dump_admin_failed_text(reason))
        return True
    await set_dump_channel(chat_id, title, getattr(chat, "username", None), kind)
    pending_action.pop(int(uid), None)
    await dm_user(uid, ui.setdump_done_text(title, chat_id), ui.dump_status_keyboard(True))
    await dismiss_picker_keyboard(uid)
    print(f"[DUMP] connected chat={chat_id} by the owner", flush=True)
    return True


async def handle_share_deep_link(message) -> bool:
    """Handle *any* message that carries a live bot deep link.

    Round 14 changed what a **setchat** link means.  It used to be the
    registration proof when it was shared *into* a channel; that is exactly the
    behaviour the round removed, because posting a bot link into the channel is
    the one thing the new flow promises never to happen.  A channel link is now
    only ever a hint: the owner is told, in their private chat, to use the
    chooser instead.  The dump-channel link is untouched.
    """
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "")
    if "start=" not in text or BOT_USERNAME.lower() not in text.lower():
        return False
    entry = find_share_token(text)
    if not entry:
        return False
    uid = int(entry["user_id"])
    chat = getattr(message, "chat", None)
    if is_channel_context(message):
        if entry["kind"] == "setchat":
            return await guide_channel_link_in_channel(message, uid, chat)
        return await register_dump_from_ping(message, uid, chat)

    # The user shared the link back to the bot: explain what to do with it.
    if entry["kind"] == "setchat":
        try:
            #: Arm the typed fallback too, so a link, @username or id works from
            #: this screen exactly as it does from /setchat.
            pending_action[int(uid)] = "setchat_share"
            #: The copy points at "the keyboard below", so it must really be there
            #: (it used to be a leftover from an earlier session).
            await say_with_picker(message, ui.setchat_deep_link_private_text(),
                                  ui.setchat_picker_keyboard(),
                                  fallback=ui.setchat_share_prompt_keyboard(None))
        except Exception:
            pass
    else:
        try:
            pending_action[int(uid)] = "setdump_share"
            await say_with_picker(message, ui.setdump_prompt_text(),
                                  ui.setdump_picker_keyboard(),
                                  fallback=ui.setdump_prompt_keyboard())
        except Exception:
            pass
    return True


async def guide_channel_link_in_channel(message, uid, chat) -> bool:
    """A setchat deep link landed **inside** a channel: point at the chooser.

    Nothing is registered from the message that landed in the channel and
    nothing is answered there — the channel stays exactly as it was.  The
    explanation goes to the user's private chat, where the picker can actually
    be opened.
    """
    chat_id = int(getattr(chat, "id", 0) or 0)
    if chat_id:
        print(f"[SETCHAT] a share link was posted inside chat={chat_id}; "
              f"the chooser is the only way in now (user={uid})", flush=True)
    pending_action[int(uid)] = "setchat_share"
    await dm_user(uid, ui.setchat_share_link_in_channel_text(),
                  ui.setchat_picker_keyboard())
    return True


async def setchat_deep_link_in_private(message, token) -> bool:
    """``/start ch…`` — the token arrived in a private chat, open the picker."""
    entry = SHARE_TOKENS.get(token)
    if not entry or entry.get("kind") != "setchat":
        return False
    pending_action[int(message.from_user.id)] = "setchat_share"
    await say_with_picker(message, ui.setchat_picker_text(),
                          ui.setchat_picker_keyboard(),
                          fallback=ui.setchat_share_prompt_keyboard(None))
    return True


async def setdump_deep_link_in_private(message, token) -> bool:
    entry = SHARE_TOKENS.get(token)
    if not entry or entry.get("kind") != "setdump":
        return False
    if int(message.from_user.id) != OWNER_ID:
        await say(message, ui.setdump_owner_only_text())
        return True
    pending_action[int(message.from_user.id)] = "setdump_share"
    await say_with_picker(message, ui.setdump_prompt_text(),
                          ui.setdump_picker_keyboard(),
                          fallback=ui.setdump_prompt_keyboard())
    return True


# --------------------------------------------------------------------------- #
#  Owner dump channel — the workspace (copy, never forward; staged copies are deleted)
# --------------------------------------------------------------------------- #

class DumpMirror:
    """Copy / delete engine of the owner's dump channel.

    * every copy is made with ``copy_message`` — **never** ``forward`` — so
      nothing carries a *Forwarded from* header, and a copy made *from* the
      dump to a user carries no *edited* tag either;
    * ``stage_copy`` / ``schedule_delete`` / ``delete_now`` carry the workspace
      flow of a user with a custom caption: copy into the dump, caption it
      there, copy it on, delete the staged copy — with a ``DUMP_TTL_SECONDS``
      safety-net delete if Telegram refused the immediate one;
    * ``mirror`` (copy a *delivered* message into the dump) is no longer wired
      into any delivery path: the dump carries only those staged copies;
    * every dump call passes the native FloodWait governor, so a busy hour
      pauses the queue instead of getting the bot restricted.
    """

    def __init__(self):
        self.governor = native_engine.Governor(int(max(0.1, DUMP_COOLDOWN_SECONDS) * 1000))
        self.tasks: dict = {}
        self.mirrored = 0
        self.deleted = 0
        self.pauses = 0
        self.wait_seconds = 0.0
        self._lock = asyncio.Lock()

    # -- helpers ---------------------------------------------------------- #
    @property
    def pending(self) -> int:
        return len(self.tasks)

    def snapshot(self) -> dict:
        return {"pending": self.pending, "mirrored": self.mirrored,
                "deleted": self.deleted, "pauses": self.pauses,
                "wait_seconds": int(self.wait_seconds)}

    async def _pace(self, chat_id) -> None:
        """Claim a slot from the governor and sleep out the cooldown it returns."""
        wait_ms = self.governor.pause_ms(f"dump:{chat_id}", time.monotonic())
        if wait_ms > 0:
            self.wait_seconds += wait_ms / 1000.0
            await asyncio.sleep(wait_ms / 1000.0)

    async def _note_flood(self, chat_id, seconds: int, attempt: int) -> None:
        self.pauses += 1
        self.governor.penalize(f"dump:{chat_id}", seconds)
        print(f"[DUMP FLOODWAIT] {seconds}s (attempt {attempt})", flush=True)
        await floodwait_sleep(seconds)

    # -- mirror ----------------------------------------------------------- #
    async def mirror(self, chat_id, message_id, *, label="delivery"):
        """Copy one delivered message into the dump channel; returns the copy."""
        entry = await get_dump_channel()
        if not entry:
            return None
        try:
            source = int(chat_id)
        except (TypeError, ValueError):
            return None
        if source == int(entry["chat_id"]):
            return None                      # never mirror the mirror itself

        copied = None
        for attempt in range(1, FLOODWAIT_MAX_RETRIES + 2):
            try:
                await self._pace(entry["chat_id"])
                copied = await bot.copy_message(
                    chat_id=entry["chat_id"], from_chat_id=source, message_id=int(message_id))
                break
            except FloodWait as error:
                await self._note_flood(entry["chat_id"], floodwait_seconds(error), attempt)
            except Exception as exc:
                print(f"[DUMP MIRROR FAILED] {label}: {type(exc).__name__}: {exc}", flush=True)
                return None
        if copied is None:
            return None

        self.mirrored += 1
        self.schedule_delete(entry["chat_id"], getattr(copied, "id", None))
        print(f"[DUMP] mirrored {label} msg={message_id} -> dump msg={getattr(copied, 'id', None)}",
              flush=True)
        return copied

    async def stage_copy(self, source_client, source_chat_id, message_id, *,
                         label="staging", delete_after=True):
        """Copy source content into the dump workspace before final delivery.

        This is intentionally a *copy*, not a forward. The caller may edit the
        temporary dump copy (for captions/attribution) and then copy that result
        to a recipient; that last copy does not carry Telegram's Edited label.
        """
        entry = await get_dump_channel()
        if not entry or message_id is None:
            return None
        try:
            source_chat_id = int(source_chat_id)
            dump_chat_id = int(entry["chat_id"])
            message_id = int(message_id)
        except (TypeError, ValueError):
            return None
        copied = None
        for attempt in range(1, FLOODWAIT_MAX_RETRIES + 2):
            try:
                await self._pace(dump_chat_id)
                copied = await source_client.copy_message(
                    chat_id=dump_chat_id,
                    from_chat_id=source_chat_id,
                    message_id=message_id,
                )
                break
            except FloodWait as error:
                await self._note_flood(dump_chat_id, floodwait_seconds(error), attempt)
            except Exception as exc:
                print(f"[DUMP STAGE FAILED] {label}: {type(exc).__name__}: {exc}", flush=True)
                return None
        if copied is None:
            return None
        self.mirrored += 1
        if delete_after:
            self.schedule_delete(dump_chat_id, getattr(copied, "id", None))
        print(f"[DUMP] staged {label} source={source_chat_id}:{message_id} "
              f"dump={dump_chat_id}:{getattr(copied, 'id', None)}", flush=True)
        return copied

    def schedule_delete(self, chat_id, message_id, *, delay=None) -> None:
        """Queue the TTL delete for one mirrored copy."""
        if message_id is None:
            return
        key = f"{chat_id}:{message_id}"
        previous = self.tasks.pop(key, None)
        if previous is not None and not previous.done():
            previous.cancel()
        task = asyncio.get_event_loop().create_task(
            self._delete_later(chat_id, message_id, delay))
        self.tasks[key] = task
        if len(self.tasks) > DUMP_QUEUE_LIMIT:
            oldest = next(iter(self.tasks))
            self.tasks.pop(oldest, None)
            print(f"[DUMP] queue full — deleting {oldest} immediately", flush=True)
            asyncio.get_event_loop().create_task(self._delete(chat_id, message_id))

    async def _delete_later(self, chat_id, message_id, delay=None) -> None:
        await asyncio.sleep(DUMP_TTL_SECONDS if delay is None else float(delay))
        await self._delete(chat_id, message_id)

    async def delete_now(self, chat_id, message_id) -> bool:
        """Cancel the TTL task and remove a staging copy after delivery."""
        key = f"{chat_id}:{message_id}"
        task = self.tasks.pop(key, None)
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
        deleted = await self._delete(chat_id, message_id)
        if not deleted:
            #: Keep a delayed retry as a cleanup safety net if Telegram briefly
            #: rejects the immediate post-delivery delete.
            self.schedule_delete(chat_id, message_id)
        return deleted

    async def _delete(self, chat_id, message_id) -> bool:
        key = f"{chat_id}:{message_id}"
        try:
            for attempt in range(1, FLOODWAIT_MAX_RETRIES + 2):
                try:
                    await bot.delete_messages(chat_id, int(message_id))
                    self.deleted += 1
                    return True
                except FloodWait as error:
                    await self._note_flood(chat_id, floodwait_seconds(error), attempt)
                except Exception as exc:
                    print(f"[DUMP DELETE FAILED] {key}: {type(exc).__name__}: {exc}", flush=True)
                    return False
            return False
        finally:
            self.tasks.pop(key, None)

    async def flush(self) -> int:
        """Delete every mirrored copy right now (used by /deldump)."""
        count = 0
        for key, task in list(self.tasks.items()):
            if not task.done():
                task.cancel()
            chat_id, _, message_id = key.partition(":")
            if await self.delete_now(int(chat_id), int(message_id)):
                count += 1
        return count


#: The single mirror used by every delivery path.
DUMP_MIRROR = DumpMirror()
#: Set once the mirror has seen the dump channel (avoid re-reading the config).
DUMP_MIRROR_ENABLED = True


async def mirror_delivery(source_chat_id, message_id, *, label="delivery"):
    """Best-effort mirror hook (never raises into the extraction path)."""
    if not DUMP_MIRROR_ENABLED:
        return None
    try:
        return await DUMP_MIRROR.mirror(source_chat_id, message_id, label=label)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[DUMP MIRROR ERROR] {exc}", flush=True)
        return None


async def broadcast_channels():
    """Owner channels reached by /broadcast: registered /setchat channels, never /setdump."""
    entries = await get_user_channels(OWNER_ID)
    dump = await get_dump_channel()
    dump_id = int(dump["chat_id"]) if dump else None
    unique = {}
    for entry in entries:
        try:
            chat_id = int(entry.get("chat_id"))
        except (AttributeError, TypeError, ValueError):
            continue
        if chat_id != dump_id:
            unique.setdefault(chat_id, {**entry, "chat_id": chat_id})
    return list(unique.values())


async def copy_message_with_markup(chat_id, from_chat_id, message_id, *, reply_markup=None):
    """Copy without a Forwarded header and attach a keyboard when supported.

    Older Telegram-library builds do not expose ``reply_markup`` on
    ``copy_message``. In that case the message is copied first, then only its
    keyboard is edited (never its text or caption), so no Edited label is added.
    """
    kwargs = {"chat_id": int(chat_id), "from_chat_id": int(from_chat_id),
              "message_id": int(message_id)}
    if reply_markup is None:
        return await floodwait_guard(bot.copy_message, **kwargs)
    try:
        return await floodwait_guard(bot.copy_message, reply_markup=reply_markup, **kwargs)
    except TypeError:
        dump = await get_dump_channel()
        if dump and int(from_chat_id) == int(dump["chat_id"]) and int(chat_id) != int(dump["chat_id"]):
            #: Copying *out of the workspace*: editing the recipient afterwards
            #: would defeat the point, so refuse instead of sending an edited copy.
            raise DumpWorkspaceError("Telegram client cannot copy this keyboard without editing the recipient. "
                                     "Upgrade the client; no destination copy was sent.")
        copied = await floodwait_guard(bot.copy_message, **kwargs)
        copied_id = getattr(copied, "id", None)
        editor = getattr(bot, "edit_message_reply_markup", None)
        if copied_id is not None and editor is not None:
            try:
                await floodwait_guard(editor, int(chat_id), int(copied_id),
                                      reply_markup=reply_markup)
            except Exception as exc:
                print(f"[CAMPAIGN BUTTON ATTACH FAILED] chat={chat_id}: {exc}", flush=True)
        return copied


async def campaign_stage(payload, keyboard=None):
    """Create one temporary dump copy for an outbound customized message.

    The owner's own campaigns (/broadcast, /botcast, /cMSG, /sendmsg, /pin) are
    not users' downloads, so unless ``config.DUMP_STAGE_CAMPAIGNS`` is switched
    on they are delivered directly and never touch the dump channel.
    """
    if not DUMP_STAGE_CAMPAIGNS:
        return None
    dump = await get_dump_channel()
    if not dump:
        return None
    await require_dump_workspace(dump)
    dump_id = int(dump["chat_id"])
    source_chat = payload.get("source_chat_id")
    source_message = payload.get("source_message_id")
    if source_chat is not None and source_message is not None:
        staged = await copy_message_with_markup(
            dump_id, int(source_chat), int(source_message), reply_markup=keyboard)
    else:
        text = str(payload.get("text") or "")
        if not text:
            return None
        staged = await floodwait_guard(
            bot.send_message, dump_id, text, reply_markup=keyboard,
            parse_mode=ParseMode.DISABLED)
    message_id = getattr(staged, "id", None)
    if message_id is None:
        raise DumpWorkspaceError("Dump staging returned no message id; delivery stopped.")
    DUMP_MIRROR.schedule_delete(dump_id, message_id)
    return {"chat_id": dump_id, "message_id": int(message_id), "temporary": True}


async def deliver_staged_text_to_chat(chat_id, text, *, reply_markup=None):
    """Send one custom DM — directly, or from the dump workspace when campaigns are staged."""
    chat_id = int(chat_id)
    payload = {"text": str(text or "")}
    staged = None
    try:
        staged = await campaign_stage(payload, reply_markup)
        if staged:
            return await copy_message_with_markup(
                chat_id, staged["chat_id"], staged["message_id"],
                reply_markup=reply_markup)
    except Exception as exc:
        raise DumpWorkspaceError("Dump staging/delivery failed; no direct fallback was sent. Check /dump.") from exc
    finally:
        if staged and staged.get("temporary"):
            await DUMP_MIRROR.delete_now(staged["chat_id"], staged["message_id"])
    return await floodwait_guard(
        bot.send_message, chat_id, str(text or ""), reply_markup=reply_markup,
        parse_mode=ParseMode.DISABLED)


async def best_effort_pin(chat_id, message_id) -> bool:
    """Attempt a pin without making delivery depend on Telegram's pin policy."""
    if message_id is None:
        return False
    try:
        await floodwait_guard(bot.pin_chat_message, int(chat_id), int(message_id),
                                   disable_notification=False)
        return True
    except FloodWait as error:
        seconds = floodwait_seconds(error)
        print(f"[PIN FLOODWAIT] chat={chat_id} msg={message_id} wait={seconds}s", flush=True)
        await floodwait_sleep(seconds)
    except Exception as exc:
        print(f"[PIN BEST EFFORT FAILED] chat={chat_id} msg={message_id}: "
              f"{type(exc).__name__}: {exc}", flush=True)
    return False


async def unpin_configured_channels():
    """Remove the current pin from each configured owner channel, best effort."""
    channels = await broadcast_channels()
    # Unpin is maintenance, not a broadcast audience. Preserve legacy cleanup.
    dump = await get_dump_channel()
    if dump:
        channels.append(dump)
    report = {"channels_total": len(channels), "unpinned": 0, "failed": 0}
    for entry in channels:
        chat_id = int(entry["chat_id"])
        try:
            chat = await floodwait_guard(bot.get_chat, chat_id)
            pinned = getattr(chat, "pinned_message", None)
            if pinned is None or getattr(pinned, "id", None) is None:
                continue
            await floodwait_guard(bot.unpin_chat_message, chat_id, int(pinned.id))
            report["unpinned"] += 1
        except FloodWait as error:
            await floodwait_sleep(floodwait_seconds(error))
            report["failed"] += 1
        except Exception as exc:
            print(f"[UNPIN CHANNEL FAILED] chat={chat_id}: {exc}", flush=True)
            report["failed"] += 1
    return report


async def deliver_campaign_payload(payload, buttons=(), *, users_only=False, pin=False):
    """Send a supplied/replied-to custom message to channels and/or bot users.

    Delivered directly by default: the source message is copied (or the typed
    text sent) to each destination with its keyboard attached, never edited
    afterwards, so there is no Edited label.  With ``DUMP_STAGE_CAMPAIGNS`` on,
    one copy is staged in the dump workspace first and copied from there.
    """
    payload = dict(payload or {})
    keyboard = ui.custom_buttons_keyboard(buttons) if buttons else None
    channels = [] if users_only or pin else await broadcast_channels()
    user_rows = await get_all_users()
    recipients = []
    for row in user_rows:
        try:
            uid = int(row.get("user_id"))
        except (AttributeError, TypeError, ValueError):
            continue
        if uid > 0 and uid != OWNER_ID:
            recipients.append((uid, row))
    report = {"channels_total": len(channels), "channels_sent": 0,
              "users_total": len(recipients), "users_sent": 0,
              "pinned_channels": 0, "pinned_users": 0,
              "pin_attempted": 0, "pin_succeeded": 0,
              "pin_failed_channels": 0, "pin_failed_users": 0,
              "failed": 0, "blocked": 0}

    staged = None
    try:
        staged = await campaign_stage(payload, keyboard)
        source_chat = payload.get("source_chat_id")
        source_message = payload.get("source_message_id")
        is_text = source_chat is None or source_message is None
        base_text = str(payload.get("text") or "")

        async def deliver_to(destination, *, source_kind):
            if staged:
                DUMP_MIRROR.schedule_delete(staged["chat_id"], staged["message_id"])
            if not is_text:
                ref = staged or {"chat_id": int(source_chat),
                                 "message_id": int(source_message), "temporary": False}
                return await copy_message_with_markup(
                    int(destination), int(ref["chat_id"]), int(ref["message_id"]),
                    reply_markup=keyboard)
            if staged:
                return await copy_message_with_markup(
                    int(destination), int(staged["chat_id"]), int(staged["message_id"]),
                    reply_markup=keyboard)
            return await floodwait_guard(
                bot.send_message, int(destination), base_text,
                reply_markup=keyboard, parse_mode=ParseMode.DISABLED)

        async def send_channel(entry):
            chat_id = int(entry["chat_id"])
            try:
                delivered_message = await deliver_to(chat_id, source_kind="channel")
                report["channels_sent"] += 1
                if pin:
                    report["pin_attempted"] += 1
                    if await best_effort_pin(chat_id, getattr(delivered_message, "id", None)):
                        report["pinned_channels"] += 1
                        report["pin_succeeded"] += 1
                    else:
                        report["pin_failed_channels"] += 1
            except Exception as exc:
                report["failed"] += 1
                print(f"[CAMPAIGN CHANNEL FAILED] chat={chat_id}: "
                      f"{type(exc).__name__}: {exc}", flush=True)

        async def send_user(item):
            uid, row = item
            try:
                delivered_message = await deliver_to(uid, source_kind="user")
                report["users_sent"] += 1
                if pin:
                    report["pin_attempted"] += 1
                    if await best_effort_pin(uid, getattr(delivered_message, "id", None)):
                        report["pinned_users"] += 1
                        report["pin_succeeded"] += 1
                    else:
                        report["pin_failed_users"] += 1
            except Exception as exc:
                name = type(exc).__name__
                if name in BROADCAST_BLOCKED_ERRORS:
                    report["blocked"] += 1
                else:
                    report["failed"] += 1
                print(f"[CAMPAIGN USER FAILED] user={uid}: {name}: {exc}", flush=True)

        await bounded_deliver(channels, send_channel)
        await bounded_deliver(recipients, send_user)
    finally:
        if staged and staged.get("temporary"):
            await DUMP_MIRROR.delete_now(staged["chat_id"], staged["message_id"])
    return report


# --------------------------------------------------------------------------- #
#  /setdump, /deldump and /dump
# --------------------------------------------------------------------------- #

@bot.on_message(filters.command("setdump") & filters.private)
@owner_only
async def setdump_handler(client, message):
    uid = message.from_user.id
    args = (message.text or "").split(maxsplit=1)
    ref = args[1].strip() if len(args) > 1 else ""
    if not ref:
        pending_action[uid] = "setdump_share"
        #: The picker keyboard lives exactly as long as this flow: it is taken
        #: off the screen again on success, /cancel, any other command or button.
        await say_with_picker(message, ui.setdump_prompt_text(),
                              ui.setdump_picker_keyboard(),
                              fallback=ui.setdump_prompt_keyboard())
        return
    await say(message, "🗄 Checking channel and staging permissions…")
    await finish_setdump(message, ref)


async def finish_setdump(message, ref) -> bool:
    """Shared by /setdump <link> and the typed prompt.

    Whatever goes wrong with the *reference* (unresolvable, not a channel, not
    an admin) keeps the flow armed: the owner may type another one or use the
    picker.  The typed-prompt path disarms the flow before it gets here, so the
    recoverable failures arm it again — otherwise the picker would answer the
    next pick with nothing.
    """
    uid = message.from_user.id
    if uid != OWNER_ID:
        await say(message, ui.setdump_owner_only_text())
        return False
    try:
        resolved = await resolve_chat_target(ref)
    except InviteRequestSent:
        await say(message, ui.setdump_join_request_text(), reply_markup=ui.feedback_keyboard())
        await dismiss_picker_keyboard(uid)
        return False
    except InviteLinkError as exc:
        pending_action[uid] = "setdump_share"
        await say(message, ui.setchat_resolve_failed_text(exc.reason) + "\n\n" +
                  ui.setdump_prompt_text(), reply_markup=ui.setdump_picker_keyboard())
        return False
    if not resolved or not resolved.get("chat_id"):
        pending_action[uid] = "setdump_share"
        await say(message, ui.setchat_resolve_failed_text("unresolved") + "\n\n" +
                  ui.setdump_prompt_text(), reply_markup=ui.setdump_picker_keyboard())
        return False
    if resolved.get("type") not in {None, "channel"}:
        pending_action[uid] = "setdump_share"
        await say(message, ui.setchat_share_failed_text("not_a_channel"),
                  reply_markup=ui.setdump_picker_keyboard())
        return False
    requester_ok, requester_reason = await describe_requester_admin(
        resolved["chat_id"], uid)
    if not requester_ok:
        pending_action[uid] = "setdump_share"
        reason = "requester_not_admin" if requester_reason == "not_admin" else "error"
        await say(message, ui.dump_admin_failed_text(reason),
                  reply_markup=ui.setdump_picker_keyboard())
        return False
    ok, reason = await describe_channel_admin(resolved["chat_id"], require_delete=True)
    if not ok:
        pending_action[uid] = "setdump_share"
        await say(message, ui.dump_admin_failed_text(reason),
                  reply_markup=ui.setdump_picker_keyboard())
        return False
    await set_dump_channel(resolved["chat_id"], resolved.get("title"),
                           resolved.get("username"), resolved.get("type"))
    pending_action.pop(uid, None)
    setchat_pending.pop(uid, None)
    await say(message, ui.setdump_done_text(resolved.get("title") or resolved["chat_id"],
                                            resolved["chat_id"]),
              reply_markup=ui.dump_status_keyboard(True))
    await dismiss_picker_keyboard(uid)
    return True


@bot.on_message(filters.command(["deldump"]) & filters.private)
@owner_only
async def deldump_handler(client, message):
    entry = await get_dump_channel()
    if not entry:
        await say(message, ui.dump_status_text(None), reply_markup=ui.dump_status_keyboard(False))
        return
    await say(message, "🗑 Disconnecting dump; temporary-copy cleanup continues in the background.")
    await delete_dump_channel()
    spawn_background(DUMP_MIRROR.flush())
    await say(message, ui.setdump_removed_text(entry.get("title")),
              reply_markup=ui.back_keyboard())


@bot.on_message(filters.command("dump") & filters.private)
@owner_only
async def dump_status_handler(client, message):
    entry = await get_dump_channel()
    permissions = await dump_permissions(entry["chat_id"]) if entry else None
    await say(message, ui.dump_status_text(entry, DUMP_MIRROR.snapshot(), permissions),
              reply_markup=ui.dump_status_keyboard(bool(entry)))


@callback_action("dump:off")
async def cb_dump_off(client, query):
    if query.from_user.id != OWNER_ID:
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    await query.answer(ui_text("🗑 Disconnecting the dump channel…"))
    await deldump_handler(client, CallbackMessage(query, "deldump"))


# --------------------------------------------------------------------------- #
#  /pin and /pinned
# --------------------------------------------------------------------------- #

def pin_target_chat(message):
    """``(chat_id, title)`` — where /pin acts when no link was given.

    Inside a channel the command acts on that channel.  In a private chat it
    acts on the owner's dump channel when one is connected (that is the channel
    the owner actually broadcasts into), otherwise on the private chat itself.
    """
    if is_channel_context(message):
        chat = message.chat
        return int(chat.id), chat_title(chat, chat.id)
    return None, None


def pin_argument(message) -> str:
    """Whatever the user typed after ``/pin`` (a link or a bare message id)."""
    parts = (getattr(message, "text", None) or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def pin_message_ref(message):
    """``(kind, ref, msg_id)`` — what /pin was pointed at.

    Round 14 gave each of the three shapes its own destination, because a link
    is a destination and not merely an id:

    ``reply``  the chat the command was typed in;
    ``link``   the chat **the link itself names** — never re-pointed at the
               dump channel, which is what used to happen and made a link to
               some other chat pin in the wrong place;
    ``id``     the chat the command was typed in, or the dump channel when it
               was typed here in private.
    """
    reply = getattr(message, "reply_to_message", None)
    if reply is not None and getattr(reply, "id", None):
        return "reply", None, int(reply.id)
    arg = pin_argument(message)
    if not arg:
        return None, None, None
    target, msg_id, _is_private = parse_link(arg)
    if target is not None and msg_id:
        kind, value = classify_chat_ref(arg)
        return "link", (value if kind == "numeric" else arg), int(msg_id)
    if arg.isdigit():
        return "id", None, int(arg)
    return None, None, None


def pin_message_id(message):
    """The message id /pin was pointed at (reply, link or bare number)."""
    _kind, _ref, msg_id = pin_message_ref(message)
    return msg_id


async def resolve_pin_scope(message):
    """``(chat_id, title, msg_id)`` for /pin, or a ``(None, reason, None)`` error.

    The reasons are the plain-English keys :func:`ui.pin_failed_text` renders:
    ``no_target``, ``no_access`` and ``not_found``.
    """
    kind, ref, msg_id = pin_message_ref(message)
    if kind is None:
        return None, "no_target", None

    if kind == "link":
        #: A link names its own chat: open it and pin there, never somewhere
        #: else just because a dump channel happens to be connected.
        try:
            resolved = await resolve_chat_target(ref)
        except InviteRequestSent:
            return None, "no_access", None
        except InviteLinkError as exc:
            return None, ("no_access" if exc.reason == "no_access" else "not_found"), None
        except Exception as exc:
            print(f"[PIN SCOPE] cannot resolve {ref!r}: {exc}", flush=True)
            return None, "no_access", None
        chat_id = resolved.get("chat_id")
        if not chat_id:
            return None, "not_found", None
        return int(chat_id), resolved.get("title") or str(chat_id), msg_id

    chat_id, title = pin_target_chat(message)
    if chat_id is None:
        entry = await get_dump_channel()
        if entry:
            chat_id, title = int(entry["chat_id"]), entry.get("title") or "your dump channel"
        else:
            chat_id = int(message.chat.id)
            title = "this chat"
    return chat_id, title, msg_id


async def pin_in_chat(chat_id, msg_id) -> tuple[bool, str]:
    """Pin one message, translating Telegram's answers into plain English.

    Round 14 replaced the single ``error`` bucket with the reasons that
    actually tell the owner what to change: ``already_pinned``, ``no_rights``,
    ``no_access``, ``floodwait``, ``not_found`` and — only as a last resort —
    ``error``.  The chat is opened first, which is what makes ``no_access`` and
    ``already_pinned`` detectable at all.
    """
    try:
        chat = await floodwait_guard(bot.get_chat, chat_id)
    except FloodWait as error:
        await floodwait_sleep(floodwait_seconds(error))
        return False, "floodwait"
    except (ChannelPrivate, ChatAdminRequired, PeerIdInvalid, UserNotParticipant) as exc:
        print(f"[PIN NO ACCESS] chat={chat_id}: {type(exc).__name__}: {exc}", flush=True)
        return False, "no_access"
    except Exception as exc:
        print(f"[PIN CHAT FAILED] chat={chat_id}: {type(exc).__name__}: {exc}", flush=True)
        return False, "no_access"

    pinned = getattr(chat, "pinned_message", None)
    if pinned is not None and getattr(pinned, "id", None) == int(msg_id):
        return False, "already_pinned"

    try:
        await floodwait_guard(bot.pin_chat_message, chat_id, int(msg_id),
                              disable_notification=False)
        return True, "ok"
    except FloodWait as error:
        await floodwait_sleep(floodwait_seconds(error))
        return False, "floodwait"
    except ChatAdminRequired:
        return False, "no_rights"
    except Exception as exc:
        detail = str(exc).lower()
        print(f"[PIN FAILED] chat={chat_id} msg={msg_id}: {type(exc).__name__}: {exc}",
              flush=True)
        missing = ("not found" in detail or "message_id_invalid" in detail
                   or "message empty" in detail or "message to pin" in detail)
        return False, "not_found" if missing else "error"


@bot.on_message(filters.command("menu") & filters.private)
@owner_only
async def message_menu_handler(client, message):
    reply = getattr(message, "reply_to_message", None)
    if reply is None:
        await say(message, "🧰 Reply to the message you want to manage, then send /menu.")
        return
    payload = campaign_payload_from_message(reply)
    if payload is None:
        await say(message, "❌ I could not read that replied-to message.")
        return
    MESSAGE_MENU_PENDING[message.from_user.id] = payload
    await say(message, ui.message_menu_text(), reply_markup=ui.message_menu_keyboard())


@bot.on_message(filters.command(["cmsg", "cMSG"]) & filters.private)
@owner_only
async def cmsg_handler(client, message):
    """Build a coloured-button message from text or a replied-to message."""
    reply = getattr(message, "reply_to_message", None)
    args = (message.text or "").split(maxsplit=1)
    typed = args[1].strip() if len(args) > 1 else ""
    if reply is not None:
        payload = campaign_payload_from_message(reply)
    elif typed:
        payload = {"kind": WIZARD_KIND_CAMPAIGN, "text": typed,
                   "preview": typed.replace("\\n", " ")[:80]}
    else:
        pending_action[message.from_user.id] = "cmsg_text"
        await say(message, ui.custom_message_prompt_text(),
                  reply_markup=ui.feedback_keyboard())
        return
    if payload is None:
        await say(message, "❌ I could not read that replied-to message.")
        return
    payload["kind"] = WIZARD_KIND_CAMPAIGN
    await start_button_wizard(message, payload)


@callback_action("msgmenu:pin")
async def cb_msgmenu_pin(client, query):
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    payload = MESSAGE_MENU_PENDING.get(uid)
    if not payload:
        await query.answer(ui_text("This message menu expired."), show_alert=True)
        return
    await query.answer(ui_text("📣 Broadcasting and pinning…"))
    MESSAGE_MENU_PENDING.pop(uid, None)
    await start_campaign_report(query.message,
        deliver_campaign_payload(payload, users_only=True, pin=True),
        users_only=True, pin=True)


@callback_action("msgmenu:broadcast")
async def cb_msgmenu_broadcast(client, query):
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    payload = MESSAGE_MENU_PENDING.get(uid)
    if not payload:
        await query.answer(ui_text("This message menu expired."), show_alert=True)
        return
    await query.answer(ui_text("📣 Broadcasting…"))
    MESSAGE_MENU_PENDING.pop(uid, None)
    await start_campaign_report(query.message,
        deliver_campaign_payload(payload, users_only=False, pin=False),
        users_only=False, pin=False)


@callback_action("msgmenu:botcast")
async def cb_msgmenu_botcast(client, query):
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    payload = MESSAGE_MENU_PENDING.get(uid)
    if not payload:
        await query.answer(ui_text("This message menu expired."), show_alert=True)
        return
    await query.answer(ui_text("🤖 Sending to bot users…"))
    MESSAGE_MENU_PENDING.pop(uid, None)
    await start_campaign_report(query.message,
        deliver_campaign_payload(payload, users_only=True, pin=False),
        users_only=True, pin=False)


@callback_action("msgmenu:cmsg")
async def cb_msgmenu_cmsg(client, query):
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    payload = MESSAGE_MENU_PENDING.pop(uid, None)
    if not payload:
        await query.answer(ui_text("This message menu expired."), show_alert=True)
        return
    payload["kind"] = WIZARD_KIND_CAMPAIGN
    await query.answer(ui_text("🎨 Opening the custom-message builder…"))
    await start_button_wizard(query, payload)


@callback_action("msgmenu:unpin")
async def cb_msgmenu_unpin(client, query):
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    await query.answer(ui_text("📍 Removing configured-channel pins…"))
    report = await unpin_configured_channels()
    MESSAGE_MENU_PENDING.pop(uid, None)
    await render(query, ui.unpin_complete_text(report), ui.admin_back_keyboard())


@callback_action("msgmenu:close")
async def cb_msgmenu_close(client, query):
    MESSAGE_MENU_PENDING.pop(query.from_user.id, None)
    await query.answer(ui_text("Menu closed."))
    try:
        await query.message.delete()
    except Exception:
        pass


@bot.on_message(filters.command("unpin") & (filters.private | filters.channel | filters.group))
@owner_only
async def unpin_handler(client, message):
    report = await unpin_configured_channels()
    await say(message, ui.unpin_complete_text(report), reply_markup=ui.back_keyboard())


@bot.on_message(filters.command("pin") & (filters.private | filters.channel | filters.group))
@admin_only
async def pin_handler(client, message):
    reply = getattr(message, "reply_to_message", None)
    if reply is not None:
        payload = campaign_payload_from_message(reply)
        if payload is None:
            await say(message, "❌ I could not read that replied-to message.")
            return
        await start_campaign_report(message,
            deliver_campaign_payload(payload, users_only=True, pin=True), users_only=True, pin=True)
        return
    # Preserve link/id syntax as a source selector, never as a pin destination.
    chat_id, title, msg_id = await resolve_pin_scope(message)
    if chat_id is None:
        await say(message, ui.pin_usage_text() if title == "no_target" else ui.pin_failed_text(title))
        return
    payload = {"source_chat_id": chat_id, "source_message_id": msg_id}
    await start_campaign_report(message,
        deliver_campaign_payload(payload, users_only=True, pin=True), users_only=True, pin=True)



@bot.on_message(filters.command("pinned") & (filters.private | filters.channel | filters.group))
@admin_only
async def pinned_handler(client, message):
    chat_id, title = pin_target_chat(message)
    if chat_id is None:
        entry = await get_dump_channel()
        if entry:
            chat_id, title = int(entry["chat_id"]), entry.get("title") or "your dump channel"
        else:
            chat_id = int(message.chat.id)
            title = "this chat"
    #: Round 14 — the same reason vocabulary /pin uses, so "I cannot reach that
    #: chat" and "Telegram asked me to slow down" read the same everywhere.
    try:
        chat = await floodwait_guard(bot.get_chat, chat_id)
        pinned = getattr(chat, "pinned_message", None)
    except FloodWait as error:
        await floodwait_sleep(floodwait_seconds(error))
        await say(message, ui.pin_failed_text("floodwait"), reply_markup=ui.feedback_keyboard())
        return
    except (ChannelPrivate, ChatAdminRequired, PeerIdInvalid, UserNotParticipant) as exc:
        print(f"[PINNED NO ACCESS] chat={chat_id}: {type(exc).__name__}: {exc}", flush=True)
        await say(message, ui.pin_failed_text("no_access"), reply_markup=ui.feedback_keyboard())
        return
    except Exception as exc:
        print(f"[PINNED FAILED] chat={chat_id}: {exc}", flush=True)
        await say(message, ui.pin_failed_text("error"), reply_markup=ui.feedback_keyboard())
        return
    if not pinned or getattr(pinned, "id", None) is None:
        await say(message, ui.pinned_none_text(title), reply_markup=ui.back_keyboard())
        return
    try:
        await floodwait_guard(bot.unpin_chat_message, chat_id, int(pinned.id))
    except FloodWait as error:
        await floodwait_sleep(floodwait_seconds(error))
        await say(message, ui.pin_failed_text("floodwait"), reply_markup=ui.feedback_keyboard())
        return
    except ChatAdminRequired:
        await say(message, ui.pin_failed_text("no_rights"), reply_markup=ui.feedback_keyboard())
        return
    except Exception as exc:
        print(f"[UNPIN FAILED] chat={chat_id}: {exc}", flush=True)
        await say(message, ui.pin_failed_text("error"), reply_markup=ui.feedback_keyboard())
        return
    await say(message, ui.unpin_done_text(title), reply_markup=ui.back_keyboard())


@callback_action("pin_offer:yes")
async def cb_pin_offer_yes(client, query):
    state = BUTTON_WIZARD.get(query.from_user.id) or {}
    payload = state.get("payload") or {}
    chat_id = payload.get("chat_id")
    if chat_id is None:
        await query.answer(ui_text("The offer expired — send the message again."),
                           show_alert=True)
        return
    await query.answer(ui_text("📌 Pinning…"))
    ok, reason = await pin_in_chat(chat_id, payload.get("message_id"))
    await render(query, ui.pin_done_text(payload.get("title") or "the chat",
                                         payload.get("message_id")) if ok
                 else ui.pin_failed_text(reason), ui.back_keyboard())


@callback_action("pin_offer:no")
async def cb_pin_offer_no(client, query):
    BUTTON_WIZARD.pop(query.from_user.id, None)
    await query.answer(ui_text("👌 Left unpinned."))
    await render(query, ui.message_sent_text(), ui.back_keyboard())


# --------------------------------------------------------------------------- #
#  Inline-button wizard — colour + link for any outgoing message
# --------------------------------------------------------------------------- #

#: user_id -> {"stage", "buttons": [{"label","url","color","style"}], "payload"}
BUTTON_WIZARD: dict = {}
#: user_id -> {"label", ...} while the wizard waits for typed input.
BUTTON_DRAFT: dict = {}

#: Payload kinds the wizard can deliver.
WIZARD_KIND_DM = "dm"
WIZARD_KIND_BROADCAST = "broadcast"
WIZARD_KIND_CHANNEL = "channel"
WIZARD_KIND_PIN = "pin"
WIZARD_KIND_CAMPAIGN = "campaign"


def normalize_button_url(value: str) -> str | None:
    """Accept ``t.me/x``, ``https://…``, ``tg://…`` — reject everything else."""
    text = (value or "").strip()
    if not text:
        return None
    if text.lower().startswith(("https://", "http://", "tg://")):
        return text
    if text.lower().startswith("t.me/"):
        return "https://" + text
    if "." in text.split("/")[0] and " " not in text:
        return "https://" + text
    return None


def wizard_preview(payload: dict) -> str:
    text = (payload.get("text") or "").strip().replace("\n", " ")
    if not text:
        return payload.get("preview") or "your message"
    return text if len(text) <= 60 else text[:57] + "…"


async def start_button_wizard(source, payload: dict):
    """Ask the owner whether the outgoing message should carry buttons."""
    uid = source.from_user.id
    BUTTON_WIZARD[uid] = {"stage": "offer", "buttons": [], "payload": payload}
    BUTTON_DRAFT.pop(uid, None)
    await render(source, ui.buttons_offer_text(wizard_preview(payload)),
                 ui.buttons_offer_keyboard())


async def deliver_wizard_payload(wizard, uid):
    """Send the prepared message with the buttons designed so far."""
    payload = wizard.get("payload") or {}
    buttons = wizard.get("buttons") or []
    keyboard = ui.custom_buttons_keyboard(buttons) if buttons else None
    kind = payload.get("kind")
    sent = []
    if kind == WIZARD_KIND_DM:
        sent.append(await deliver_staged_text_to_chat(
            payload["chat_id"], payload.get("text") or "", reply_markup=keyboard))
    elif kind == WIZARD_KIND_CHANNEL:
        message = await deliver_staged_text_to_chat(
            payload["chat_id"], payload.get("text") or "", reply_markup=keyboard)
        sent.append(message)
        message_id = getattr(message, "id", None)
        wizard["payload"]["message_id"] = message_id
        wizard["payload"]["title"] = payload.get("title")
        #: Telegram cannot add buttons to a message that is already sent, but it
        #: can pin it — so every channel post ends with a one-tap pin offer.
        if message_id:
            BUTTON_WIZARD[uid] = {
                "stage": "pin_offer", "buttons": buttons,
                "payload": {"kind": WIZARD_KIND_PIN,
                            "chat_id": payload["chat_id"],
                            "title": payload.get("title"),
                            "message_id": message_id,
                            "text": payload.get("text") or ""},
            }
            await say_message(bot, uid, ui.pin_offer_text(),
                              reply_markup=ui.pin_offer_keyboard())
    elif kind == WIZARD_KIND_BROADCAST:
        sent = await run_button_broadcast(payload.get("text") or "", buttons)
    elif kind == WIZARD_KIND_CAMPAIGN:
        return await deliver_campaign_payload(payload, buttons)
    elif kind == WIZARD_KIND_PIN:
        message_id = payload.get("message_id")
        if buttons and message_id:
            #: Telegram cannot add a keyboard to an existing message, so
            #: re-send the content with its finished keyboard, staging through
            #: the dump first when it is configured.
            try:
                refreshed = await deliver_staged_text_to_chat(
                    payload["chat_id"], payload.get("text") or "📌",
                    reply_markup=keyboard)
                sent.append(refreshed)
                await best_effort_pin(payload["chat_id"], getattr(refreshed, "id", None))
            except Exception as exc:
                print(f"[PIN BUTTONS FAILED] {exc}", flush=True)
    return sent


async def run_button_broadcast(text: str, buttons) -> list:
    """Broadcast a personalised message; the pool formats every copy in C++."""
    users = await get_all_users()
    names = [entry.get("name") for entry in users]
    prepared = native_engine.prepare_broadcast(text, names) if "{name}" in text \
        else [text for _ in users]
    keyboard = ui.custom_buttons_keyboard(buttons) if buttons else None
    sent = []
    for entry, body in zip(users, prepared):
        try:
            sent.append(await bot.send_message(entry["user_id"], body,
                                               reply_markup=keyboard,
                                               parse_mode=ParseMode.HTML))
        except FloodWait as error:
            await floodwait_sleep(floodwait_seconds(error))
            continue
        except Exception:
            continue
        await asyncio.sleep(0.05)
    return sent


@callback_action("btnwiz:yes")
async def cb_btnwiz_yes(client, query):
    wizard = BUTTON_WIZARD.get(query.from_user.id)
    if not wizard:
        await query.answer(ui_text("This wizard expired — start again."), show_alert=True)
        return
    wizard["stage"] = "color"
    await query.answer()
    await render(query, ui.button_color_text(), ui.button_color_keyboard())


@callback_action("btnwiz:skip")
async def cb_btnwiz_skip(client, query):
    wizard = BUTTON_WIZARD.pop(query.from_user.id, None)
    if not wizard:
        await query.answer(ui_text("This wizard expired — start again."), show_alert=True)
        return
    await query.answer(ui_text("📤 Sending without buttons…"))
    if (wizard.get("payload") or {}).get("kind") == WIZARD_KIND_CAMPAIGN:
        await start_campaign_report(query.message, deliver_wizard_payload(wizard, query.from_user.id))
        return
    try:
        result = await deliver_wizard_payload(wizard, query.from_user.id)
    except Exception as exc:
        await render(query, f"❌ **Sending failed**\n\n{exc}", ui.admin_back_keyboard())
        return
    if (wizard.get("payload") or {}).get("kind") == WIZARD_KIND_CAMPAIGN:
        await render(query, ui.broadcast_complete_text(result or {}), ui.admin_back_keyboard())
    else:
        await render(query, ui.message_sent_text(), ui.admin_back_keyboard())


@callback_action("btnwiz:cancel")
async def cb_btnwiz_cancel(client, query):
    BUTTON_WIZARD.pop(query.from_user.id, None)
    BUTTON_DRAFT.pop(query.from_user.id, None)
    await query.answer(ui_text("❌ Cancelled — nothing was sent."))
    await render(query, ui.message_cancelled_text(), ui.admin_back_keyboard())


async def handle_button_wizard_callback(client, query, data: str):
    uid = query.from_user.id
    wizard = BUTTON_WIZARD.get(uid)
    if not wizard:
        await query.answer(ui_text("This wizard expired — start again."), show_alert=True)
        return
    action, _, arg = data.partition(":")
    action, _, arg2 = arg.partition(":")
    if action == "color":
        color = arg2 or arg
        spec = BUTTON_COLORS.get(color)
        if not spec:
            await query.answer(ui_text("⚠️ Unknown colour."), show_alert=True)
            return
        BUTTON_DRAFT[uid] = {"color": color, "style": spec["style"], "label": ""}
        wizard["stage"] = "label"
        await query.answer(ui_text(f"{spec['label']} selected."))
        await render(query, ui.button_label_text(), ui.button_label_keyboard())
        return
    if action == "link":
        value = arg2 or arg
        if value == "none":
            BUTTON_DRAFT.pop(uid, None)
            wizard["stage"] = "more"
            await query.answer(ui_text("⏭ Button without a link."))
            await render(query, ui.button_more_text(wizard["buttons"]),
                         ui.button_more_keyboard(wizard["buttons"]))
            return
        await query.answer(ui_text("⚠️ Send the link as a text message."), show_alert=True)
        return
    if action == "add":
        wizard["stage"] = "color"
        await query.answer()
        await render(query, ui.button_color_text(), ui.button_color_keyboard())
        return
    if action == "send":
        BUTTON_WIZARD.pop(uid, None)
        BUTTON_DRAFT.pop(uid, None)
        await query.answer(ui_text("📤 Sending…"))
        if (wizard.get("payload") or {}).get("kind") == WIZARD_KIND_CAMPAIGN:
            await start_campaign_report(query.message, deliver_wizard_payload(wizard, uid))
            return
        try:
            result = await deliver_wizard_payload(wizard, uid)
        except Exception as exc:
            await render(query, f"❌ **Sending failed**\n\n{exc}", ui.admin_back_keyboard())
            return
        if (wizard.get("payload") or {}).get("kind") == WIZARD_KIND_CAMPAIGN:
            text = ui.broadcast_complete_text(result or {})
        else:
            text = ui.message_sent_text() + (
                "\n\n" + ui.buttons_preview_text(wizard["buttons"])
                if wizard.get("buttons") else "")
        await render(query, text, ui.admin_back_keyboard())
        return
    await query.answer(ui_text("⚠️ Unknown action."), show_alert=True)


async def wizard_text_input(message, uid, text) -> bool:
    """Consume a typed label/link while the button wizard is waiting for it."""
    wizard = BUTTON_WIZARD.get(uid)
    if not wizard:
        return False
    stage = wizard.get("stage")
    if stage == "label":
        label = (text or "").strip()
        if not label:
            await say(message, ui.button_label_text(), reply_markup=ui.button_label_keyboard())
            return True
        if len(label) > MAX_BUTTON_LABEL:
            await say(message, ui.button_label_too_long_text(MAX_BUTTON_LABEL),
                      reply_markup=ui.button_label_keyboard())
            return True
        draft = BUTTON_DRAFT.setdefault(uid, {"style": "primary"})
        draft["label"] = label
        wizard["stage"] = "link"
        await say(message, ui.button_link_text(label), reply_markup=ui.button_link_keyboard())
        return True
    if stage == "link":
        draft = BUTTON_DRAFT.get(uid) or {}
        url = normalize_button_url(text)
        if url is None:
            await say(message, ui.button_link_invalid_text(), reply_markup=ui.button_link_keyboard())
            return True
        wizard["buttons"].append({
            "label": draft.get("label") or "Open",
            "url": url,
            "color": draft.get("color") or "primary",
            "style": draft.get("style") or "primary",
        })
        BUTTON_DRAFT.pop(uid, None)
        wizard["stage"] = "more"
        await say(message, ui.button_more_text(wizard["buttons"]),
                  reply_markup=ui.button_more_keyboard(wizard["buttons"]))
        return True
    return False


# --------------------------------------------------------------------------- #
#  Giveaways — one at a time, always random, always announced
# --------------------------------------------------------------------------- #

#: owner_id -> wizard state while /giveaway builds a new giveaway.
GIVEAWAY_WIZARD: dict = {}
#: Live counters shown by the panel and /dump-style diagnostics.
GIVEAWAY_STATS = {"posts": 0, "refreshes": 0, "draws": 0, "pauses": 0}
#: The background pump (daily re-post, live count, final draw).
GIVEAWAY_TASK = None
#: Flips once the participant index has been requested.
GIVEAWAY_INDEXES_READY = False
GIVEAWAY_GOVERNOR = native_engine.Governor(2000)
#: Round 14 — the one DM fan-out that may be running (one giveaway at a time).
GIVEAWAY_BROADCAST_TASK = None

#: Telegram answers that mean this account will never receive a DM from us.
#: They are matched by name so the module keeps importing on library versions
#: that do not export every one of them.
BROADCAST_BLOCKED_ERRORS = frozenset({
    "UserIsBlocked", "PeerIdInvalid", "InputUserDeactivated", "UserDeactivated",
    "UserIdInvalid", "UserBannedInChannel", "UserIsBot",
})


def giveaway_link(token: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=gw{token}"


def parse_giveaway_end(text, *, now=None):
    """``6h`` / ``3d`` / ``2w`` or ``2026-11-01 20:00`` → a naive UTC deadline."""
    now = now or datetime.utcnow()
    raw = (text or "").strip()
    if not raw:
        return None
    compact = raw.lower().replace(" ", "")
    match = re.fullmatch(r"(\d+)([mhdw])", compact)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        factor = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}[unit]
        seconds = amount * factor
        if seconds <= 0:
            return None
        value = now + timedelta(seconds=seconds)
        return value if (value - now) <= timedelta(days=GIVEAWAY_MAX_DAYS) else None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M",
                "%d %b %Y %H:%M", "%d %b %Y"):
        try:
            value = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if value <= now or (value - now) > timedelta(days=GIVEAWAY_MAX_DAYS):
            return None
        return value
    return None


def giveaway_ends_label(gw) -> str:
    return ui.giveaway_when(gw.get("ends_at"))


async def giveaway_panel(source, *, stats=None, active=None):
    gw = active if active is not None else await get_active_giveaway()
    if gw:
        count = await count_giveaway_participants(gw.get("_id") or "active")
        channel = gw.get("channel_id")
        channel_label = None
        if channel:
            entry = None
            for item in await get_user_channels(OWNER_ID):
                if int(item["chat_id"]) == int(channel):
                    entry = item
                    break
            channel_label = (entry or {}).get("title") or f"chat {channel}"
        stats = {
            "participants": count,
            "channel": channel_label,
            "message": gw.get("message_id"),
            "daily_hours": int(GIVEAWAY_DAILY_INTERVAL_SECONDS // 3600) or 1,
            "last_post": ui.giveaway_when(gw.get("last_post_at")),
        }
    await render(source, ui.giveaway_panel_text(gw, stats), ui.giveaway_panel_keyboard(gw))


@bot.on_message(filters.command(["giveaway", "participants", "endgiveaway"]) & filters.private)
@owner_only
async def giveaway_handler(client, message):
    command = command_name_of(message) or "giveaway"
    if command == "participants":
        await show_giveaway_participants(message, 0)
        return
    if command == "endgiveaway":
        await end_giveaway_now(message)
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) > 1 and args[1].strip().lower() in {"end", "stop"}:
        await end_giveaway_now(message)
        return
    await giveaway_panel(message)

@bot.on_message(filters.command("giveawaystatus") & filters.private)
@owner_only
async def giveaway_status_handler(client, message):
    """Quick one-screen giveaway status — prize, ends-at, participant count."""
    gw = await get_active_giveaway()
    if not gw:
        await say(message, ui.giveaway_none_text(), reply_markup=ui.back_keyboard())
        return
    count = await count_giveaway_participants(gw.get("_id") or "active")
    await say(message, ui.giveaway_quick_status_text(gw, count),
              reply_markup=ui.giveaway_panel_keyboard(gw))

async def show_giveaway_participants(source, page=0):
    gw = await get_active_giveaway() or await get_last_giveaway()
    if not gw:
        await render(source, ui.giveaway_none_text(), ui.back_keyboard())
        return
    giveaway_id = gw.get("_id") or "active"
    total = await count_giveaway_participants(giveaway_id)
    per_page = max(1, int(GIVEAWAY_PARTICIPANTS_PER_PAGE))
    pages = max(1, -(-total // per_page))
    page = max(0, min(int(page or 0), pages - 1))
    rows = await list_giveaway_participants(giveaway_id, skip=page * per_page, limit=per_page)
    await render(source, ui.giveaway_participants_text(rows, page, pages, total),
                 ui.giveaway_participants_keyboard(page, pages))


async def end_giveaway_now(source, *, announce=True):
    """Draw the random winner and close the giveaway."""
    gw = await get_active_giveaway()
    if not gw:
        await render(source, ui.giveaway_none_text(), ui.giveaway_panel_keyboard(None))
        return False
    participants = await all_giveaway_participants(gw.get("_id") or "active")
    winner = random.SystemRandom().choice(participants) if participants else None
    prize = ui.giveaway_prize_label(gw.get("prize_tier"), gw.get("prize_days"))
    granted = False
    if winner:
        try:
            await add_premium(int(winner["user_id"]), gw.get("prize_days"),
                              tier=gw.get("prize_tier"))
            granted = True
        except Exception as exc:
            print(f"[GIVEAWAY GRANT FAILED] {exc}", flush=True)
        await dm_user(winner["user_id"], ui.giveaway_winner_dm_text(prize))
        await announce_winner(gw, winner, prize, len(participants))
    await finish_giveaway(dict(winner) if winner else None)
    GIVEAWAY_STATS["draws"] += 1
    if announce:
        await render(source, ui.giveaway_owner_ended_text(
            giveaway_winner_label(winner), len(participants), granted),
            ui.admin_back_keyboard())
    return True


def giveaway_winner_label(winner) -> str | None:
    if not winner:
        return None
    name = winner.get("name") or "User"
    username = winner.get("username")
    return f"{name} (@{username})" if username else f"{name}"


async def announce_winner(gw, winner, prize, total):
    label = giveaway_winner_label(winner)
    text = ui.giveaway_finished_text(label, prize, total)
    channel = gw.get("channel_id")
    if channel:
        try:
            await say_message(bot, channel, text)
            await floodwait_guard(bot.unpin_chat_message, channel)
        except FloodWait as error:
            await floodwait_sleep(floodwait_seconds(error))
        except Exception as exc:
            print(f"[GIVEAWAY ANNOUNCE FAILED] {exc}", flush=True)
    await dm_user(OWNER_ID, text)


async def post_giveaway_message(gw, count, *, repost=False):
    """Publish (or re-publish) the public giveaway message and pin it."""
    text = ui.giveaway_public_text(gw, count, ends_label=giveaway_ends_label(gw))
    keyboard = ui.giveaway_public_keyboard(giveaway_link(gw.get("token") or ""))
    channel = gw.get("channel_id")
    now = datetime.utcnow()
    GIVEAWAY_GOVERNOR.pause_ms(f"gw:{channel or 'dm'}", time.monotonic())
    parse_mode = ParseMode.DISABLED if gw.get("custom_message") else ParseMode.HTML
    if not channel:
        await dm_user(OWNER_ID, text, keyboard, parse_mode=parse_mode)
        await update_giveaway({"last_post_at": now, "rendered_count": int(count)})
        return None
    try:
        message = await bot.send_message(channel, text, reply_markup=keyboard,
                                         parse_mode=parse_mode)
    except FloodWait as error:
        GIVEAWAY_STATS["pauses"] += 1
        GIVEAWAY_GOVERNOR.penalize(f"gw:{channel}", floodwait_seconds(error))
        await floodwait_sleep(floodwait_seconds(error))
        try:
            message = await bot.send_message(channel, text, reply_markup=keyboard,
                                             parse_mode=parse_mode)
        except Exception as exc:
            print(f"[GIVEAWAY POST FAILED] {exc}", flush=True)
            return None
    except Exception as exc:
        print(f"[GIVEAWAY POST FAILED] {exc}", flush=True)
        return None
    try:
        await bot.pin_chat_message(channel, message.id, disable_notification=False)
    except Exception as exc:
        print(f"[GIVEAWAY PIN FAILED] {exc}", flush=True)
    GIVEAWAY_STATS["posts"] += 1
    await update_giveaway({"message_id": getattr(message, "id", None),
                           "last_post_at": now, "rendered_count": int(count)})
    return message


async def refresh_giveaway_count(gw, count):
    """Edit the pinned message so the participant count is live."""
    channel = gw.get("channel_id")
    message_id = gw.get("message_id")
    if not channel or not message_id:
        return False
    text = ui.giveaway_public_text(gw, count, ends_label=giveaway_ends_label(gw))
    keyboard = ui.giveaway_public_keyboard(giveaway_link(gw.get("token") or ""))
    parse_mode = ParseMode.DISABLED if gw.get("custom_message") else ParseMode.HTML
    try:
        await floodwait_guard(bot.edit_message_text, channel, int(message_id), text,
                              reply_markup=keyboard, parse_mode=parse_mode)
        GIVEAWAY_STATS["refreshes"] += 1
        await update_giveaway({"rendered_count": int(count)})
        return True
    except MessageNotModified:
        await update_giveaway({"rendered_count": int(count)})
        return False
    except Exception as exc:
        print(f"[GIVEAWAY REFRESH FAILED] {exc}", flush=True)
        return False


async def giveaway_tick(now=None) -> bool:
    """One scheduler tick: end, re-post daily, refresh the live count."""
    gw = await get_active_giveaway()
    if not gw:
        return False
    now = now or datetime.utcnow()
    ends = gw.get("ends_at")
    if ends is not None and now >= ends:
        print("[GIVEAWAY] deadline reached — drawing the winner", flush=True)
        await end_giveaway_now(MessageProxyOwner(), announce=False)
        return True
    count = await count_giveaway_participants(gw.get("_id") or "active")
    last = gw.get("last_post_at") or gw.get("created_at") or now
    if (now - last).total_seconds() >= GIVEAWAY_DAILY_INTERVAL_SECONDS:
        await post_giveaway_message(gw, count, repost=True)
        return True
    if int(gw.get("rendered_count") or 0) != int(count):
        await refresh_giveaway_count(gw, count)
        return True
    return False


class MessageProxyOwner:
    """A tiny stand-in source so the scheduler can reuse the /giveaway screens."""

    def __init__(self):
        self.from_user = SimpleNamespace(id=OWNER_ID, first_name="Owner", username=None)
        self.chat = SimpleNamespace(id=OWNER_ID)
        self.id = 0
        self.replies = []

    async def reply(self, text, reply_markup=None, **kwargs):
        self.replies.append({"text": text})
        return self


async def giveaway_loop():
    """Background pump: runs while a giveaway is live."""
    print("[GIVEAWAY] scheduler started", flush=True)
    while True:
        try:
            await giveaway_tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - the pump must survive
            print(f"[GIVEAWAY TICK FAILED] {type(exc).__name__}: {exc}", flush=True)
        await asyncio.sleep(max(15, int(GIVEAWAY_LIVE_REFRESH_SECONDS)))


# --------------------------------------------------------------------------- #
#  Round 14 — the giveaway fan-out: every user, in their DM, the moment it
#  goes live.  It runs as a background task so a long list can never block the
#  wizard, every FloodWait is slept out and retried, and the owner is handed a
#  delivery report when the last message has landed.
# --------------------------------------------------------------------------- #

async def giveaway_broadcast_dm(uid, text, keyboard, report, *,
                                raw_text: bool = False, parse_mode=None) -> str:
    """Deliver one giveaway DM and best-effort pin it. Returns its send outcome.

    A FloodWait is never an error here: it is slept out and retried up to
    :data:`config.GIVEAWAY_BROADCAST_FLOOD_RETRIES` times, and only a user who
    keeps being rate-limited is written off.  That is what keeps a fan-out to
    hundreds of accounts from earning the bot a restriction.
    """
    for attempt in range(1, GIVEAWAY_BROADCAST_FLOOD_RETRIES + 2):
        try:
            if raw_text:
                sent_message = await bot.send_message(
                    int(uid), text, reply_markup=keyboard,
                    parse_mode=parse_mode or ParseMode.DISABLED)
            else:
                kwargs = {"reply_markup": keyboard}
                if parse_mode is not None:
                    kwargs["parse_mode"] = parse_mode
                sent_message = await say_message(bot, int(uid), text, **kwargs)
            message_id = getattr(sent_message, "id", None)
            if message_id is not None:
                report["pin_attempted"] = int(report.get("pin_attempted", 0)) + 1
                try:
                    await bot.pin_chat_message(int(uid), int(message_id),
                                               disable_notification=False)
                    report["pin_succeeded"] = int(report.get("pin_succeeded", 0)) + 1
                except FloodWait as pin_error:
                    seconds = floodwait_seconds(pin_error)
                    report["pauses"] += 1
                    report["wait_seconds"] += float(seconds)
                    report["pin_failed"] = int(report.get("pin_failed", 0)) + 1
                    print(f"[GIVEAWAY DM PIN FLOODWAIT] user={uid}: {seconds}s", flush=True)
                    await floodwait_sleep(seconds)
                except Exception as pin_error:
                    report["pin_failed"] = int(report.get("pin_failed", 0)) + 1
                    print(f"[GIVEAWAY DM PIN FAILED] user={uid}: "
                          f"{type(pin_error).__name__}: {pin_error}", flush=True)
            return "sent"
        except FloodWait as error:
            seconds = floodwait_seconds(error)
            report["pauses"] += 1
            report["wait_seconds"] += float(seconds)
            GIVEAWAY_GOVERNOR.penalize(f"gwb:{uid}", seconds)
            print(f"[GIVEAWAY BROADCAST FLOODWAIT] {seconds}s user={uid} "
                  f"attempt={attempt}", flush=True)
            if attempt > GIVEAWAY_BROADCAST_FLOOD_RETRIES:
                return "paused"
            await floodwait_sleep(seconds)
        except Exception as exc:
            name = type(exc).__name__
            print(f"[GIVEAWAY BROADCAST FAILED] user={uid}: {name}: {exc}", flush=True)
            return "blocked" if name in BROADCAST_BLOCKED_ERRORS else "failed"
    return "paused"


async def run_giveaway_broadcast(gw) -> dict:
    """Send the announcement to every bot user and return delivery + pin counts."""
    custom = bool(gw.get("custom_message"))
    if custom:
        count = await count_giveaway_participants(gw.get("_id") or "active")
        text = ui.giveaway_public_text(gw, count,
                                       ends_label=giveaway_ends_label(gw))
        parse_mode = ParseMode.DISABLED
    else:
        text = ui.giveaway_broadcast_text(gw)
        parse_mode = None
    keyboard = ui.giveaway_broadcast_keyboard(giveaway_link(gw.get("token") or ""))
    report = {"total": 0, "sent": 0, "failed": 0, "blocked": 0, "paused": 0,
              "pauses": 0, "wait_seconds": 0.0,
              "pin_attempted": 0, "pin_succeeded": 0, "pin_failed": 0}
    users = await get_all_users()
    recipients = [int(entry.get("user_id") or 0) for entry in users]
    recipients = [uid for uid in recipients if uid and uid != OWNER_ID]
    report["total"] = len(recipients)
    for index, uid in enumerate(recipients):
        outcome = await giveaway_broadcast_dm(
            uid, text, keyboard, report, raw_text=custom, parse_mode=parse_mode)
        report[outcome] = int(report.get(outcome, 0)) + 1
        if index + 1 < len(recipients):
            await broadcast_gap()      # between two sends, never after the last
    return report


async def broadcast_gap() -> None:
    """The deliberate pause between two giveaway DMs.

    A burst of hundreds of sends is exactly what earns a FloodWait, so the
    fan-out is paced rather than fired off as fast as the loop can turn.
    """
    if GIVEAWAY_BROADCAST_DELAY > 0:
        await asyncio.sleep(GIVEAWAY_BROADCAST_DELAY)


async def _giveaway_broadcast_task(gw) -> None:
    """Run the fan-out, then report to the owner.  Never raises."""
    try:
        report = await run_giveaway_broadcast(gw)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # pragma: no cover - the fan-out must survive
        print(f"[GIVEAWAY BROADCAST FAILED] {type(exc).__name__}: {exc}", flush=True)
        return
    await dm_user(OWNER_ID, ui.giveaway_broadcast_report_text(report))


def start_giveaway_broadcast(gw):
    """Kick the fan-out off in the background; returns the task (or ``None``)."""
    global GIVEAWAY_BROADCAST_TASK
    if GIVEAWAY_BROADCAST_TASK is not None and not GIVEAWAY_BROADCAST_TASK.done():
        return GIVEAWAY_BROADCAST_TASK
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - no loop yet
        return None
    GIVEAWAY_BROADCAST_TASK = loop.create_task(_giveaway_broadcast_task(gw))
    return GIVEAWAY_BROADCAST_TASK


def ensure_giveaway_loop():
    """Start the scheduler lazily (first update of this process).

    It only starts once the client is actually connected — that keeps the
    background task out of unit tests and out of the cold-start window, and the
    first real update always starts it.
    """
    global GIVEAWAY_TASK, GIVEAWAY_INDEXES_READY
    if GIVEAWAY_TASK is not None and not GIVEAWAY_TASK.done():
        return GIVEAWAY_TASK
    if getattr(bot, "me", None) is None:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - no loop yet
        return None
    if not GIVEAWAY_INDEXES_READY:
        #: One-time: the unique (giveaway_id, user_id) index that makes a double
        #: tap impossible even under a race.
        GIVEAWAY_INDEXES_READY = True
        loop.create_task(ensure_giveaway_indexes())
    GIVEAWAY_TASK = loop.create_task(giveaway_loop())
    return GIVEAWAY_TASK


async def giveaway_join(message, token) -> bool:
    """``/start gw<token>`` — one tap, one entry, live count updated."""
    gw = await get_active_giveaway()
    if not gw or str(gw.get("token")) != str(token):
        await say(message, ui.giveaway_none_text(), reply_markup=ui.back_keyboard())
        return False
    user = message.from_user
    await ensure_user(user)
    giveaway_id = gw.get("_id") or "active"
    joined = await add_giveaway_participant(giveaway_id, user.id,
                                            get_user_display_name(user),
                                            getattr(user, "username", None))
    count = await count_giveaway_participants(giveaway_id)
    await update_giveaway({"participant_count": int(count)})
    if not joined:
        await say(message, ui.giveaway_already_joined_text(count), reply_markup=ui.back_keyboard())
        #: Already joined — still return True so /start does not render the main
        #: menu again.  The "already joined" notice is enough feedback on its own.
        return True
    await say(message, ui.giveaway_joined_text(get_user_display_name(user), gw, count),
              reply_markup=ui.back_keyboard())
    #: The pinned message is refreshed right away so the count really is live.
    await refresh_giveaway_count(gw, count)
    try:
        await dm_user(OWNER_ID, f"🎁 **New giveaway participant**\n\n"
                                f"👤 {get_user_display_name(user)} "
                                f"(@{getattr(user, 'username', None) or '—'})\n"
                                f"🆔 `{user.id}`\n👥 Total: **{count}**")
    except Exception:
        pass
    return True


@callback_action("gw:new")
async def cb_gw_new(client, query):
    if query.from_user.id != OWNER_ID:
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    active = await get_active_giveaway()
    if active:
        await query.answer(ui_text("⚠️ One giveaway at a time — end it first."),
                           show_alert=True)
        return
    GIVEAWAY_WIZARD[OWNER_ID] = {"step": "tier"}
    await query.answer()
    await render(query, ui.giveaway_step_tier_text(), ui.grant_tier_keyboard())


@callback_action("cmd_giveaway")
async def cb_gw_panel(client, query):
    await query.answer()
    await giveaway_panel(query)


@callback_action("gw:link")
async def cb_gw_link(client, query):
    if query.from_user.id != OWNER_ID:
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    gw = await get_active_giveaway()
    if not gw:
        await query.answer(ui_text("No giveaway is running."), show_alert=True)
        return
    link = giveaway_link(gw.get("token") or "")
    await query.answer(ui_text("📤 Share sheet opened."))
    await render(query, ui.giveaway_share_text(link),
                 ui.keyboard([[ui.share_url_button("📤 Share giveaway", link,
                                                   "Join the giveaway — one tap to take part!")],
                              [ui.button("📋 Copy link", copy_text=link, style="primary")],
                              [ui.admin_back_keyboard().inline_keyboard[0][0]]]))


@callback_action("gw:end")
async def cb_gw_end(client, query):
    if query.from_user.id != OWNER_ID:
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    await query.answer(ui_text("🏆 Drawing the winner…"))
    await end_giveaway_now(query)


async def handle_giveaway_callback(client, query, data: str):
    uid = query.from_user.id
    if uid != OWNER_ID:
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    _, _, rest = data.partition(":")
    if rest.startswith("list"):
        _, _, page = rest.partition(":")
        try:
            page_number = int(page)
        except ValueError:
            page_number = 0
        await query.answer()
        await show_giveaway_participants(query, page_number)
        return

    wizard = GIVEAWAY_WIZARD.get(uid)
    if not wizard:
        await query.answer(ui_text("This giveaway wizard expired — run /giveaway again."),
                           show_alert=True)
        return
    if rest == "cancel":
        GIVEAWAY_WIZARD.pop(uid, None)
        pending_action.pop(uid, None)
        await query.answer(ui_text("Giveaway setup cancelled."))
        await render(query, ui.action_cancelled_text(), ui.admin_back_keyboard())
        return
    if rest.startswith("benefit"):
        _, _, index = rest.partition(":")
        try:
            benefit = GIVEAWAY_BENEFIT_SUGGESTIONS[int(index)]
        except (ValueError, IndexError):
            await query.answer(ui_text("⚠️ Unknown suggestion."), show_alert=True)
            return
        wizard["benefit"] = benefit
        wizard["step"] = "custom"
        pending_action[uid] = "gw_custom_message"
        await query.answer(ui_text("💡 Suggestion saved."))
        await render(query, ui.giveaway_step_custom_text(),
                     ui.giveaway_step_custom_keyboard())
        return
    if rest.startswith("custom"):
        _, _, action = rest.partition(":")
        if action != "skip":
            await query.answer(ui_text("⚠️ Unknown custom-message action."), show_alert=True)
            return
        wizard["custom_message"] = None
        wizard["step"] = "ends"
        pending_action.pop(uid, None)
        await query.answer(ui_text("⏭ Using the standard announcement."))
        await render(query, ui.giveaway_step_end_text(), ui.giveaway_step_end_keyboard())
        return
    if rest.startswith("end"):
        _, _, value = rest.partition(":")
        if value == "":
            return
        if value in {"1d", "3d", "7d", "14d"}:
            deadline = parse_giveaway_end(value)
        else:
            deadline = parse_giveaway_end(value)
        if deadline is None:
            await query.answer(ui_text("⚠️ Could not read that date — try 3d or "
                                       "2026-11-01 20:00."), show_alert=True)
            return
        wizard["ends_at"] = deadline
        wizard["step"] = "channel"
        pending_action.pop(uid, None)
        await query.answer(ui_text("⏰ End time saved."))
        entries = await get_user_channels(uid)
        await render(query, ui.giveaway_step_channel_text(entries),
                     ui.giveaway_step_channel_keyboard(entries))
        return
    if rest.startswith("channel"):
        _, _, value = rest.partition(":")
        entries = await get_user_channels(uid)
        channel_id = None
        channel_title = None
        if value != "none":
            try:
                entry = entries[int(value) - 1]
            except (ValueError, IndexError):
                await query.answer(ui_text("⚠️ Unknown channel."), show_alert=True)
                return
            channel_id = int(entry["chat_id"])
            channel_title = entry.get("title")
        created = await create_giveaway_from_wizard(uid, wizard, channel_id, channel_title)
        if not created:
            await query.answer(ui_text("⚠️ A giveaway is already running."), show_alert=True)
            return
        await query.answer(ui_text("🎉 Giveaway is live!"))
        await render(query, ui.giveaway_created_text(created,
                                                     int(created.get("participant_count") or 0)),
                     ui.giveaway_created_keyboard(giveaway_link(created.get("token") or "")))
        return
    if rest.startswith("tier"):
        _, _, value = rest.partition(":")
        tier = normalize_tier(value)
        if not tier:
            await query.answer(ui_text("⚠️ Unknown tier."), show_alert=True)
            return
        wizard["tier"] = tier
        wizard["step"] = "duration"
        await query.answer(ui_text(f"🎖 {GRANT_TIERS[tier]['label']} selected."))
        await render(query, ui.giveaway_step_duration_text(GRANT_TIERS[tier]["label"]),
                     ui.grant_duration_keyboard(tier))
        return
    if rest.startswith("dur"):
        _, _, value = rest.partition(":")
        tier_part, _, duration = value.partition(":")
        tier = normalize_tier(tier_part) or wizard.get("tier")
        state, days = parse_grant_duration(duration)
        if state == "invalid" or not tier:
            await query.answer(ui_text("⚠️ Invalid duration."), show_alert=True)
            return
        if state == "custom":
            wizard["step"] = "days"
            pending_action[uid] = "gw_days"
            await query.answer(ui_text("🔢 Send the number of days."))
            await say(query.message, ui.giveaway_days_prompt_text(), reply_markup=ui.feedback_keyboard())
            return
        wizard["tier"] = tier
        wizard["days"] = days
        wizard["step"] = "benefit"
        pending_action[uid] = "gw_benefit"
        await query.answer(ui_text("📅 Duration saved."))
        await render(query, ui.giveaway_step_benefit_text(), ui.giveaway_step_benefit_keyboard())
        return
    await query.answer(ui_text("⚠️ Unknown action."), show_alert=True)


async def create_giveaway_from_wizard(uid, wizard, channel_id, channel_title):
    """Persist the giveaway, publish it and pin it."""
    token = secrets.token_hex(5)
    #: Clear any stale participants from a previous giveaway so the new one
    #: starts with a clean slate — every participant must opt in fresh.
    old = await get_active_giveaway() or await get_last_giveaway()
    if old:
        await clear_giveaway_participants(old.get("_id") or "active")

    doc = {
        "token": token,
        "status": "running",
        "prize_tier": wizard.get("tier") or "public",
        "prize_days": wizard.get("days", 30),
        "benefit": wizard.get("benefit") or GIVEAWAY_BENEFIT_SUGGESTIONS[0],
        "ends_at": wizard.get("ends_at") or (datetime.utcnow() + timedelta(days=1)),
        "created_at": datetime.utcnow(),
        "created_by": int(uid),
        "channel_id": channel_id,
        "participant_count": 0,
        "rendered_count": 0,
        "custom_message": wizard.get("custom_message") or None,
    }
    if not await create_giveaway(doc):
        return None
    GIVEAWAY_WIZARD.pop(uid, None)
    pending_action.pop(uid, None)
    gw = await get_active_giveaway()
    if gw:
        await post_giveaway_message(gw, 0)
        gw = await get_active_giveaway() or gw
    ensure_giveaway_loop()
    #: Round 14 — going live means two things happen at once: the message is
    #: pinned in the channel (``post_giveaway_message``) **and** the same
    #: announcement is fanned out to every user in their DM.  The fan-out is a
    #: background task, so the wizard is never blocked by a long user list.
    if gw:
        try:
            audience = sum(1 for row in await get_all_users()
                           if int(row.get("user_id") or 0) != OWNER_ID)
        except Exception:
            audience = 0
        start_giveaway_broadcast(gw)
        await dm_user(OWNER_ID, ui.giveaway_broadcast_started_text(audience))
    return gw or doc


@callback_action("native:selftest")
async def cb_native_selftest(client, query):
    if query.from_user.id != OWNER_ID:
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    code = native_engine.selftest()
    await query.answer(ui_text("✅ Self-test passed." if code == 0
                               else f"❌ Self-test failed at check {code}."),
                       show_alert=True)
    await render(query, ui.native_engine_text(native_engine.describe()),
                 ui.native_engine_keyboard())


@callback_action("native:bench")
async def cb_native_bench(client, query):
    if query.from_user.id != OWNER_ID:
        await query.answer(ui_text("👑 Owner only."), show_alert=True)
        return
    await query.answer(ui_text("🧪 Benchmarking…"))
    bench = run_native_benchmark()
    await render(query, ui.native_engine_text(native_engine.describe(), bench),
                 ui.native_engine_keyboard())


def run_native_benchmark(iterations=200000):
    """Milliseconds the engine needs for *iterations* escapes (0 when absent)."""
    if not native_engine.available():
        return None
    return native_engine.benchmark(iterations, 1) / 1e6


@bot.on_message(filters.command("native") & filters.private)
@owner_only
async def native_handler(client, message):
    await say(message, ui.native_engine_text(native_engine.describe(), run_native_benchmark()),
              reply_markup=ui.native_engine_keyboard())


@bot.on_message(filters.command("post") & filters.private)
@owner_only
async def post_to_channel_handler(client, message):
    """``/post <text>`` — publish a message in the dump channel.

    Round 13 item 9: a channel post is **not** a direct user send, so the
    inline-button builder is not offered here either.  The text is published as
    it was typed and the send is confirmed; the one-tap **pin** offer that
    follows is part of the pin flow, not the button builder.
    """
    args = (message.text or "").split(maxsplit=1)
    text = args[1].strip() if len(args) > 1 else ""
    if not text:
        await say(message, "Usage: `/post Your announcement text`")
        return
    entry = await get_dump_channel()
    if not entry:
        await say(message, ui.dump_status_text(None, DUMP_MIRROR.snapshot()),
                  reply_markup=ui.dump_status_keyboard(False))
        return
    chat_id = int(entry["chat_id"])
    title = entry.get("title")
    uid = message.from_user.id
    try:
        posted = await bot.send_message(chat_id, text, parse_mode=ParseMode.DISABLED)
    except FloodWait as error:
        await floodwait_sleep(floodwait_seconds(error))
        posted = await bot.send_message(chat_id, text, parse_mode=ParseMode.DISABLED)
    message_id = getattr(posted, "id", None)
    await say(message, ui.message_sent_text(), reply_markup=ui.back_keyboard())
    #: Pinning a channel post is usually the next thing wanted, so the same
    #: one-tap offer the other sends end with is offered here too.
    if message_id:
        BUTTON_WIZARD[uid] = {
            "stage": "pin_offer", "buttons": [],
            "payload": {"kind": WIZARD_KIND_PIN, "chat_id": chat_id,
                        "title": title, "message_id": message_id, "text": text},
        }
        await say_message(bot, uid, ui.pin_offer_text(),
                          reply_markup=ui.pin_offer_keyboard())



def touch_scheduler():
    """Start the giveaway pump on the first update of this process.

    The bot has no lifecycle hook that is guaranteed to run on every
    deployment, so the background task is started lazily from the update
    handlers: one cheap check per update, and the pump keeps running afterwards.
    """
    ensure_command_registration()
    return ensure_giveaway_loop()


async def giveaway_wizard_text(message, uid, text) -> bool:
    """Consume a typed step of the /giveaway wizard (date, days, benefit line)."""
    wizard = GIVEAWAY_WIZARD.get(uid)
    if not wizard:
        return False
    step = wizard.get("step")
    if step == "ends":
        deadline = parse_giveaway_end(text)
        if deadline is None:
            await say(message, ui.giveaway_end_invalid_text(),
                      reply_markup=ui.giveaway_step_end_keyboard())
            return True
        wizard["ends_at"] = deadline
        wizard["step"] = "channel"
        entries = await get_user_channels(uid)
        await say(message, ui.giveaway_step_channel_text(entries),
                  reply_markup=ui.giveaway_step_channel_keyboard(entries))
        return True
    if step == "days":
        try:
            days = int(str(text).strip())
        except ValueError:
            await say(message, ui.giveaway_days_prompt_text(), reply_markup=ui.feedback_keyboard())
            return True
        if days <= 0 or days > GRANT_MAX_DAYS:
            await say(message, f"❌ Choose between 1 and {GRANT_MAX_DAYS} days.")
            return True
        wizard["days"] = days
        wizard["step"] = "benefit"
        pending_action[uid] = "gw_benefit"
        await say(message, ui.giveaway_step_benefit_text(),
                  reply_markup=ui.giveaway_step_benefit_keyboard())
        return True
    if step == "benefit":
        benefit = str(text).strip()[:GIVEAWAY_MAX_BENEFIT_CHARS]
        wizard["benefit"] = benefit
        wizard["step"] = "custom"
        pending_action[uid] = "gw_custom_message"
        await say(message, ui.giveaway_step_custom_text(),
                  reply_markup=ui.giveaway_step_custom_keyboard())
        return True
    if step == "custom":
        custom = str(text or "").strip()[:4096]
        wizard["custom_message"] = custom or None
        wizard["step"] = "ends"
        pending_action.pop(uid, None)
        await say(message, ui.giveaway_step_end_text(),
                  reply_markup=ui.giveaway_step_end_keyboard())
        return True
    return False

# --------------------------------------------------------------------------- #
#  Admin panel — one source of truth
#
#  ADMIN_PAGES drives the inline panel, the /admins list and the tests that
#  assert every admin command is reachable from both.
# --------------------------------------------------------------------------- #

ADMIN_PAGES = [
    ("📊 Users & Statistics",
     ["stats", "users", "loggedusers", "newusers", "activeusers", "topusers",
      "finduser", "userinfo", "export"]),
    ("💎 Premium & Payments",
     ["addpremium", "removepremium", "premiumlist", "payments", "addqr", "delqr", "removeqr"]),
    ("🧠 Engine & Channels",
     ["setengine", "setchat", "delchat"]),
    ("📢 Community",
     ["broadcast", "botcast", "cmsg", "menu", "unpin", "sendmsg", "ban", "unban",
      "banlist", "feedbacks"]),
    ("📢 Force Sub",
     ["setfsub", "fsublist", "delfsub", "fsublabel", "fsubcheck"]),
    ("⚙️ Administration",
     ["addadmin", "removeadmin", "adminlist", "maintenance",
      "clearlogs", "adminhelp"]),
    ("📱 Vmore App",
     ["appusers", "apk"]),
    ("🎁 Owner Tools",
     ["pin", "pinned", "setdump", "deldump", "dump", "post"]),
    ("⚡ Advanced & Giveaways",
     ["native", "giveaway", "participants", "endgiveaway", "giveawaystatus"]),
]

#: Every command that appears somewhere in the admin panel.
ADMIN_PANEL_COMMANDS = tuple(cmd for _, commands in ADMIN_PAGES for cmd in commands)

#: Commands that need a value typed in the next message.
ADMIN_VALUE_EXAMPLES = {
    "broadcast": "Your announcement text",
    "botcast": "Your message for bot users",
    "sendmsg": "123456789 Your message",
    "ban": "123456789",
    "unban": "123456789",
    "finduser": "username or user ID",
    "userinfo": "123456789",
    "addpremium": "123456789 30",
    "removepremium": "123456789",
    "addadmin": "123456789",
    "removeadmin": "123456789",
    "setfsub": "t.me/+AbCdEf",
    "fsublabel": "1 📢 Join Now",
    "fsubcheck": "1 on",
    "delfsub": "1",
    "maintenance": "on or off",
    "setchat": "t.me/mychannel",
    "delchat": "123456789",
}

#: Commands only the owner may run.
ADMIN_OWNER_COMMANDS = {
    "addpremium", "addadmin", "removeadmin", "setfsub", "fsublist", "delfsub",
    "fsublabel", "fsubcheck", "maintenance", "setengine",
    "addqr", "delqr", "removeqr", "clearlogs",
    # Owner tools: pin control, the dump channel, channel posts, the native
    # engine diagnostics and the giveaway control panel.
    "pin", "pinned", "unpin", "menu", "cmsg", "botcast", "superbroadcast",
    "setdump", "deldump", "dump", "post", "native",
    "giveaway", "participants", "endgiveaway", "giveawaystatus",
    # The app: who uses it, and the APK it is served from.
    "appusers", "apk",
}


# --------------------------------------------------------------------------- #
#  Channel vocabulary — one explicit allow-list, everything else is a no-op
# --------------------------------------------------------------------------- #
#: Every registered slash command mapped to the handler that implements it.
#: pyrogram's ``filters.private`` already keeps personal commands out of a
#: channel, but a dump channel is a *registered* chat the bot must still answer
#: in for channel vocabulary and for owner/admin work, so the routing is written
#: down here explicitly instead of relying on filter side effects.
COMMAND_HANDLERS = {
    "pin": pin_handler,
    "pinned": pinned_handler,
    "unpin": unpin_handler,
    "menu": message_menu_handler,
    "cmsg": cmsg_handler,
    "botcast": botcast_handler,
    "setdump": setdump_handler,
    "deldump": deldump_handler,
    "dump": dump_status_handler,
    "post": post_to_channel_handler,
    "native": native_handler,
    "giveaway": giveaway_handler,
    "participants": giveaway_handler,
    "endgiveaway": giveaway_handler,
    "giveawaystatus": giveaway_status_handler,
    "start": start_handler,
    "help": help_handler,
    "login": login_handler,
    "logout": logout_handler,
    "status": status_handler,
    "cancel": cancel_handler,
    "setcaption": setcaption_handler,
    "delcaption": delcaption_handler,
    "setthumb": setthumb_handler,
    "delthumb": delthumb_handler,
    "setprefix": setprefix_handler,
    "setsuffix": setsuffix_handler,
    "mystats": mystats_handler,
    "myinfo": myinfo_handler,
    "history": history_handler,
    "settings": settings_handler,
    "language": language_handler,
    "refer": refer_handler,
    "bookmark": bookmark_handler,
    "bookmarks": bookmarks_handler,
    "favorite": favorite_handler,
    "favorites": favorites_handler,
    "share": share_handler,
    "feedback": feedback_handler,
    "invite": invite_handler,
    "premium": premium_handler,
    "models": models_handler,
    "engine": models_handler,
    "mychannels": mychannels_handler,
    "redeem": redeem_handler,
    "stats": stats_handler,
    "users": users_handler,
    "loggedusers": loggedusers_handler,
    "activeusers": active_users_handler,
    "newusers": new_users_handler,
    "topusers": top_users_handler,
    "broadcast": broadcast_handler,
    "ban": ban_handler,
    "unban": unban_handler,
    "banlist": banlist_handler,
    "finduser": finduser_handler,
    "userinfo": userinfo_handler,
    "addpremium": addpremium_handler,
    "removepremium": removepremium_handler,
    "premiumlist": premiumlist_handler,
    "addadmin": addadmin_handler,
    "removeadmin": removeadmin_handler,
    "adminlist": adminlist_handler,
    "setfsub": setfsub_handler,
    "delfsub": delfsub_handler,
    "fsublist": fsublist_handler,
    "fsublabel": fsublabel_handler,
    "fsubcheck": fsubcheck_handler,
    "maintenance": maintenance_handler,
    "feedbacks": feedbacks_handler,
    "sendmsg": sendmsg_handler,
    "clearlogs": clearlogs_handler,
    "export": export_handler,
    "adminhelp": adminhelp_handler,
    "addqr": addqr_handler,
    "delqr": delqr_handler,
    "removeqr": delqr_handler,
    "payments": payments_handler,
    "setchat": setchat_handler,
    "delchat": delchat_handler,
    "setengine": setengine_handler,
    "admin": admin_handler,
    "admins": admin_handler,
}

#: Channel vocabulary: registering and removing a dump channel, plus the
#: owner/admin panel.  Anything *not* listed here is a silent no-op inside a
#: registered channel — no reply, no edit, no send, no stack trace.
CHANNEL_VOCABULARY = frozenset({"setchat", "delchat"})
CHANNEL_ALLOWED_COMMANDS = (
    CHANNEL_VOCABULARY | frozenset(ADMIN_PANEL_COMMANDS) | frozenset(ADMIN_OWNER_COMMANDS)
    | frozenset({"admin", "admins"})
)
#: Personal commands that must never answer inside a channel.
CHANNEL_BLOCKED_COMMANDS = frozenset(COMMAND_HANDLERS) - CHANNEL_ALLOWED_COMMANDS


COMMAND_REGISTRATION_TASK = None

#: Commands that only the owner may run, as far as the Telegram menu goes.
MENU_OWNER_ONLY = frozenset(ADMIN_OWNER_COMMANDS) | {"giveawaystatus"}
MENU_ROLES = ("user", "admin", "owner")


def telegram_commands(role: str = "user"):
    """The command menu Telegram shows for one audience (``setMyCommands``).

    * ``user`` — ``/start`` first, then every command a normal user may run.
      This is what everybody sees in the menu of a private chat.
    * ``admin`` — those plus the admin commands (not the owner-only ones).
    * ``owner`` — every command the bot has.

    Each description is an emoji followed by what the command does.  Telegram
    allows 100 commands per scope: the lists are split by audience, never
    truncated, and a name can only ever appear once.
    """
    if role not in MENU_ROLES:
        raise ValueError(f"unknown menu role: {role!r}")
    entries = list(ui.user_menu_commands())
    if role != "user":
        shown = {name for name, _description in entries}
        for name in dict.fromkeys(COMMAND_NAMES):
            if name in shown:
                continue
            if role == "admin" and name in MENU_OWNER_ONLY:
                continue
            entries.append((name, ui.staff_menu_description(name)))
    if len(entries) > 100:
        raise ValueError("Command list exceeds Telegram's limit; split scopes, do not truncate")
    return [BotCommand(name, description[:256]) for name, description in entries]


async def sync_staff_commands(uid, role=None) -> bool:
    """Give the owner / an admin the longer menu in their own chat.

    A ``BotCommandScopeChat`` beats the all-private-chats list for that one
    chat, so staff see the admin commands and nobody else does.  ``role``
    ``"user"`` removes the override again (a revoked admin falls back to the
    ordinary menu).  Best effort: Telegram refuses a chat the bot has never
    talked to, which is fine — the next ``/start`` of that person tries again.
    """
    try:
        uid = int(uid)
        if role is None:
            role = ("owner" if uid == OWNER_ID else
                    "admin" if await is_admin(uid) else "user")
        scope = BotCommandScopeChat(chat_id=uid)
        if role == "user":
            await floodwait_guard(bot.delete_bot_commands, scope=scope)
        else:
            await floodwait_guard(bot.set_bot_commands, telegram_commands(role), scope=scope)
        return True
    except Exception as exc:
        print(f"[MENU] could not update the command menu of chat={uid}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return False


async def register_staff_commands() -> int:
    """Publish the longer menu for the owner and every stored admin."""
    staff = {int(OWNER_ID): "owner"} if OWNER_ID else {}
    try:
        for row in await get_admins_list() or []:
            admin_id = row.get("user_id") if isinstance(row, dict) else row
            staff.setdefault(int(admin_id), "admin")
    except Exception as exc:
        print(f"[MENU] could not read the admin list: {type(exc).__name__}: {exc}", flush=True)
    done = 0
    for uid, role in staff.items():
        done += bool(await sync_staff_commands(uid, role))
    return done


async def register_telegram_commands():
    """Publish the official Telegram command menu — nothing is set by hand.

    Clears the legacy default list (it used to leak into channels), then sets
    the user menu for private chats only and the longer staff menus for the
    owner's and the admins' own chats.  Authorization is unchanged: the menu
    only *shows* commands, every handler still checks who is calling.
    """
    await floodwait_guard(bot.delete_bot_commands)
    await floodwait_guard(bot.set_bot_commands, telegram_commands("user"),
                          scope=BotCommandScopeAllPrivateChats())
    await register_staff_commands()


def ensure_command_registration():
    global COMMAND_REGISTRATION_TASK
    if COMMAND_REGISTRATION_TASK is None or (COMMAND_REGISTRATION_TASK.done()
                                             and COMMAND_REGISTRATION_TASK.exception()):
        COMMAND_REGISTRATION_TASK = spawn_background(register_telegram_commands())


@bot.on_start()
async def publish_menu_on_start(client):
    """Publish the command menu as soon as the client is connected.

    The first update of the process also triggers it (``touch_scheduler``), but
    waiting for somebody to write first meant a freshly deployed menu stayed
    stale until then.
    """
    ensure_command_registration()
    # Start auto-delete background task for old history/payments
    ensure_history_cleanup()
    # Bind the app API to this event loop so the HTTP worker can reach Telegram.
    try:
        appapi.bind_loop(asyncio.get_running_loop())
    except RuntimeError:  # pragma: no cover - only outside a running loop
        pass
    spawn_app_startup_tasks()


def spawn_app_startup_tasks():
    """Kick off the app's startup errands.

    None of them is worth losing the bot over: the /CreateBot purge, retiring
    tokens whose 30 days ran out, and caching the owner card the app shows in
    its top-right corner.  A failure is logged and the bot keeps running.
    """
    for label, factory in (("purge", purge_created_bot_data),
                           ("expired-tokens", expire_stale_app_tokens),
                           ("owner-card", APP_BRIDGE.refresh_owner)):
        try:
            spawn_background(_run_startup_errand(label, factory))
        except Exception as exc:
            print(f"[APP] startup task {label} did not start: "
                  f"{type(exc).__name__}: {exc}", flush=True)


async def _run_startup_errand(label, factory):
    """Await one errand, swallowing whatever it throws.

    These tasks are fired from the start hook, so nothing may propagate out of
    them: an unreachable database or a chat lookup that fails is worth a log
    line, never a crashed bot (or a failed test that drains the background).
    """
    try:
        await factory()
    except Exception as exc:
        print(f"[APP] startup task {label} failed: {type(exc).__name__}: {exc}",
              flush=True)


def command_name_of(message) -> str | None:
    """The bare command name of *message* (``/setchat@MyBot x`` -> ``setchat``)."""
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    if not text.startswith("/"):
        return None
    token = text.split()[0][1:].split("@")[0].strip().lower()
    return token or None


def channel_command_allowed(message) -> bool:
    """True when this command belongs to the channel's vocabulary."""
    name = command_name_of(message)
    return bool(name) and name in CHANNEL_ALLOWED_COMMANDS


async def dispatch_channel_command(client, message) -> bool:
    """Run an allow-listed command that was typed inside a channel.

    Returns ``True`` when a handler ran.  A command that is not channel
    vocabulary, has no sender identity (a bare channel post) or has no handler
    is ignored completely silently.
    """
    if not channel_command_allowed(message):
        return False
    if getattr(message, "from_user", None) is None:
        # An anonymous channel post cannot be an admin — say nothing at all.
        return False
    handler = COMMAND_HANDLERS.get(command_name_of(message))
    if handler is None:
        return False
    try:
        await handler(client, message)
    except Exception as exc:
        # A channel command must never leak a traceback into the channel.
        print(f"[CHANNEL COMMAND FAILED] {command_name_of(message)}: {exc}", flush=True)
    return True


def admin_help_text() -> str:
    """The full command list shown by /admins and /adminhelp.

    Every command is printed as a descriptive English pair
    (``🧠 /setengine — Global Engine Controller (Lock / Auto)``) built from the
    labels in :mod:`ui`, so the panel, this list and the docs never drift apart.
    """
    lines = [
        "👑 **ADMIN COMMANDS**",
        "",
        "Every command below also exists as a button in the paginated /admin panel.",
        "",
        "**⭐ Most used**",
        ui.admin_featured_text(),
        "",
    ]
    for title, commands in ADMIN_PAGES:
        lines.append(f"**{title}**")
        lines.append(ui.admin_command_lines(commands))
        lines.append("")
    lines.append("💎 Payment proofs carry ✅ Approve / ⚠️ Fake / 🚫 Ban buttons for the owner.")
    lines.append("🧠 /setengine controls the global engine: AUTO autoscaler, or a hard "
                 "lock to C++ Turbo / Python.")
    return ui.smallcaps("\n".join(lines).strip())


def admin_panel_keyboard(page=0):
    names = ADMIN_PAGES[page][1]
    rows = [[ui.button("/" + x, callback_data="admin:" + x, style="primary")
             for x in names[i:i+2]] for i in range(0, len(names), 2)]
    rows.append([
        ui.button("⬅️ Previous", callback_data=f"admin_page:{(page-1) % len(ADMIN_PAGES)}", style="primary"),
        ui.button("Next ➡️", callback_data=f"admin_page:{(page+1) % len(ADMIN_PAGES)}", style="primary"),
    ])
    rows.append([ui.home_button()])
    return ui.keyboard(rows)


def admin_panel_text(page=0):
    """One panel page: the commands as descriptive English pairs."""
    title, commands = ADMIN_PAGES[page]
    return (f"🛠 **ADMIN PANEL** • {page+1}/{len(ADMIN_PAGES)}\n\n"
            f"**{title}**\n\n"
            f"{ui.admin_command_lines(commands)}\n\n"
            "Tap an action or use its slash command. Browse with Previous / Next.\n"
            "Send /admins for the complete command list.\n"
            "👑 Only the owner can grant VIP tiers or lock the global engine.")



#: Panels buttons → the very same handler the slash command uses.
ADMIN_INLINE_HANDLERS = {
    "pin": pin_handler,
    "pinned": pinned_handler,
    "unpin": unpin_handler,
    "menu": message_menu_handler,
    "cmsg": cmsg_handler,
    "botcast": botcast_handler,
    "setdump": setdump_handler,
    "deldump": deldump_handler,
    "dump": dump_status_handler,
    "post": post_to_channel_handler,
    "native": native_handler,
    "giveaway": giveaway_handler,
    "participants": giveaway_handler,
    "endgiveaway": giveaway_handler,
    "stats": stats_handler, "users": users_handler, "loggedusers": loggedusers_handler,
    "newusers": new_users_handler, "activeusers": active_users_handler,
    "topusers": top_users_handler, "broadcast": broadcast_handler, "sendmsg": sendmsg_handler,
    "ban": ban_handler, "unban": unban_handler, "banlist": banlist_handler,
    "finduser": finduser_handler, "userinfo": userinfo_handler,
    "addpremium": addpremium_handler, "removepremium": removepremium_handler,
    "premiumlist": premiumlist_handler, "feedbacks": feedbacks_handler,
    "payments": payments_handler, "adminhelp": adminhelp_handler,
    "addadmin": addadmin_handler, "removeadmin": removeadmin_handler,
    "adminlist": adminlist_handler, "setfsub": setfsub_handler,
    "fsublist": fsublist_handler, "delfsub": delfsub_handler,
    "fsublabel": fsublabel_handler, "fsubcheck": fsubcheck_handler,
    "maintenance": maintenance_handler, "addqr": addqr_handler, "delqr": delqr_handler,
    "removeqr": delqr_handler, "clearlogs": clearlogs_handler, "export": export_handler,
    "setchat": setchat_handler, "delchat": delchat_handler,
    "setengine": setengine_handler,
    "giveawaystatus": giveaway_status_handler,
}


async def run_admin_inline(client, query, command):
    # Adapt the real command handler to edit the panel message rather than post a new message.
    handler = ADMIN_INLINE_HANDLERS.get(command)
    if not handler:
        return
    owner_commands = ADMIN_OWNER_COMMANDS
    if query.from_user.id != OWNER_ID and (command in owner_commands or not await is_admin(query.from_user.id)):
        await say(query.message, "🚫 **This action is not available to your account.**")
        return
    if command in ADMIN_VALUE_EXAMPLES:
        admin_pending[query.from_user.id] = command
        await say_edit(query.message,
            f"✍️ **/{command}**\n\nSend the details in your next message.\n"
            f"Example: `{ADMIN_VALUE_EXAMPLES[command]}`\n\nUse /cancel or another command to exit.",
            reply_markup=ui.feedback_keyboard())
        return
    if command == "setdump":
        await handler(client, CallbackMessage(query, command))
        return
    class PanelProxy:
        def __init__(self):
            self.from_user = query.from_user
            self.chat = query.message.chat
            self.text = "/" + command
            self.id = query.message.id
        async def reply(self, text, reply_markup=None, **kwargs):
            return await say_edit(query.message, text, reply_markup=reply_markup or ui.admin_back_keyboard())
        async def reply_document(self, document, **kwargs):
            return await query.message.reply_document(document, **kwargs)
    await handler(client, PanelProxy())


@bot.on_callback_query()
async def callback_handler(client, query):
    """Route every button press straight to its action."""
    #: Channel-context presses that do not belong to a bot-posted message are
    #: ignored before any side effect runs — no answer, no profile refresh.
    if not channel_callback_allowed(query):
        return
    data = query.data or ""
    uid = query.from_user.id
    log_latency(query.message, "button")
    touch_scheduler()
    # Button presses refresh the stored profile too (renames show up everywhere).
    queue_refresh_profile(query.from_user)
    # Navigation never leaves feedback or an admin prompt silently active.
    # Force-sub buttons keep their own wizard state (a rename prompt must
    # survive the very button press that opened it).
    if not data.startswith("dl:") and not data.startswith("fsub") \
            and not data.startswith("cap_") \
            and not data.startswith(("btnwiz:", "gw:", "pin_offer:", "dump:", "native:")) \
            and data not in {"cancel_login", "cancel_action"}:
        #: Leaving a picker flow through any other button takes its keyboard
        #: away; only presses made in the user's own private chat count.
        if data not in PICKER_FLOW_CALLBACKS and reply_chat_id(query.message) == uid:
            await dismiss_picker_keyboard(uid)
        pending_action.pop(uid, None)
        admin_pending.pop(uid, None)
        pending = login_pending.pop(uid, {})
        if pending.get("client"):
            try:
                await pending["client"].disconnect()
            except Exception:
                pass
        if not data.startswith("paid:"):
            payment_pending.pop(uid, None)
        fsub_pending.pop(uid, None)
    if data.startswith("dl:"):
        await handle_download_controls(query)
        return
    if data.startswith(("cap_yes:", "cap_no:")):
        await handle_caption_choice(client, query)
        return
    if data.startswith(("payok:", "payfake:", "payban:")):
        # Owner-only payment verdicts.
        await handle_payment_review(client, query, data)
        return
    if data.startswith(("grant_tier:", "grant_dur:", "grant_back:")):
        # Owner-only granular VIP grant wizard (tier → duration).
        if GIVEAWAY_WIZARD.get(uid) and data.startswith("grant_"):
            await handle_giveaway_callback(client, query,
                                           "gw:tier:" + data.split(":", 1)[1]
                                           if data.startswith("grant_tier:")
                                           else "gw:dur:" + data.split(":", 1)[1])
            return
        await handle_grant_callback(client, query, data)
        return
    if data.startswith("btnwiz:"):
        # Inline-button wizard: colour → label → link → send.
        if data in {"btnwiz:yes", "btnwiz:skip", "btnwiz:cancel"}:
            handler = CALLBACK_ACTIONS.get(data) or CALLBACK_ACTIONS.get("btnwiz:cancel")
            await handler(client, query)
            return
        await handle_button_wizard_callback(client, query, data)
        return
    if data.startswith("gw:"):
        #: Panel buttons (``gw:new``, ``gw:end``, ``gw:link``) have their own
        #: actions; only the wizard steps fall through to the step handler.
        handler = CALLBACK_ACTIONS.get(data)
        if handler is not None:
            await handler(client, query)
            return
        await handle_giveaway_callback(client, query, data)
        return
    if data.startswith(("pin_offer:", "dump:", "native:")):
        handler = CALLBACK_ACTIONS.get(data)
        if handler is None:
            await query.answer(ui_text(ui.stale_button_text()), show_alert=True)
            return
        await handler(client, query)
        return
    if data.startswith("engine_mode:"):
        # Owner-only global engine controller (AUTO / LOCK C++ / LOCK PYTHON).
        await handle_engine_mode_callback(client, query, data)
        return
    if data.startswith("delchat_pick:"):
        await cb_delchat_pick(client, query)
        return
    if data.startswith(("mych_test:", "mych_verify:", "mych_del:")):
        await handle_mychannels_callback(client, query, data)
        return
    if data.startswith("dump:test"):
        if uid != OWNER_ID:
            await query.answer(ui_text("👑 Owner only."), show_alert=True)
            return
        await query.answer(ui_text("🔍 Checking dump permissions…"))
        entry = await get_dump_channel()
        if not entry:
            await query.answer(ui_text("⚠️ No dump channel connected."), show_alert=True)
            await render(query, ui.dump_status_text(None), ui.dump_status_keyboard(False))
            return
        permissions = await dump_permissions(entry["chat_id"])
        await render(query, ui.dump_status_text(entry, DUMP_MIRROR.snapshot(), permissions),
                     ui.dump_status_keyboard(True))
        return
    if data.startswith("admin_page:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
            return
        try:
            page = int(data.split(":", 1)[1])
            if not 0 <= page < len(ADMIN_PAGES):
                raise ValueError()
        except ValueError:
            await query.answer(ui_text("Unknown page."), show_alert=True)
            return
        await query.answer()
        await render(query, admin_panel_text(page), admin_panel_keyboard(page))
        return
    if data.startswith("admin:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
            return
        await query.answer()
        await run_admin_inline(client, query, data.split(":", 1)[1])
        return
    if data == "redeem_points":
        uid = query.from_user.id
        if not await redeem_points(uid, REDEEM_POINTS, months=REDEEM_PREMIUM_MONTHS):
            await query.answer(ui_text(f"You need {REDEEM_POINTS} points. Active owner-granted premium cannot be replaced."), show_alert=True)
            return
        await query.answer(ui_text("Premium redeemed!"))
        await show_premium(query)
        return
    if data.startswith("buy:"):
        #: ``buy:<plan>`` (Standard) or ``buy:<plan>:turbo`` (with the C++ add-on).
        parts = data.split(":")[1:]
        plan_key = parts[0] if parts else ""
        turbo = len(parts) > 1 and parts[1].strip().lower() == "turbo"
        plan = PREMIUM_PLANS.get(plan_key)
        if not plan:
            await query.answer(ui_text("Unknown plan"), show_alert=True)
            return
        qr = await get_qr()
        if not qr:
            await query.answer(ui_text("Payment QR is not available yet."), show_alert=True)
            await render(query, f"⚠️ **Payments temporarily unavailable**\n\nPlease contact @{PAYMENT_CONTACT}. Do not pay until the owner provides a QR.", ui.plans_keyboard())
            return
        import secrets
        token = secrets.token_hex(6)
        payment_pending[uid] = {"plan": plan_key, "token": token, "turbo": turbo}
        await query.answer(ui_text("💳 Your payment QR is ready."))
        try:
            await bot.send_photo(uid, qr,
                                 caption=ui_text(ui.payment_text(plan, turbo=turbo)),
                                 reply_markup=ui.payment_keyboard(token))
        except Exception:
            payment_pending.pop(uid, None)
            await say(query.message, f"⚠️ **Could not display the payment QR**\n\nPlease try again or contact @{PAYMENT_CONTACT}. The owner may need to upload a new QR with /addqr.")
        return
    if data.startswith("paid:"):
        order = payment_pending.get(uid)
        if not order or order["token"] != data.split(":", 1)[1]:
            await query.answer(ui_text("This checkout expired. Choose a plan again."), show_alert=True)
            return
        pending_action[uid] = "payment_proof"
        await query.answer(ui_text("📸 Send your payment screenshot."))
        await say(query.message,
            f"📸 **SUBMIT PAYMENT PROOF**\n\nSend a clear screenshot as a photo showing the amount, transaction ID and payment date.\n\n👤 Reviewed by @{PAYMENT_CONTACT}. Premium is activated only after the owner verifies payment.\n\nUse /cancel or any new command to exit.",
            reply_markup=ui.feedback_keyboard())
        return
    if data.startswith("users_page:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
            return
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer(ui_text("Invalid page."), show_alert=True)
            return
        await query.answer()
        await show_users_page(query, page)
        return
    if data.startswith("loggedusers:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
            return
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer(ui_text("Invalid page."), show_alert=True)
            return
        await query.answer()
        await show_logged_users(query, page)
        return
    if data == "fsub:check" or data.startswith(("fsub:", "fsub_page:", "fsub_list_page:",
                                                "fsub_del:", "fsub_rename:", "fsub_del_all")):
        await handle_fsub_callback(client, query, data)
        return
    handler = CALLBACK_ACTIONS.get(data)
    if handler is None:
        await query.answer(ui_text(ui.stale_button_text()), show_alert=True)
        return
    try:
        await handler(client, query)
    except Exception as e:
        try:
            await query.answer(ui_text(f"⚠️ Error: {e}"), show_alert=True)
        except Exception:
            pass


@bot.on_message(filters.text & filters.private & ~filters.command(COMMAND_NAMES))
async def text_handler(client, message):
    if not private_user_context(message):
        return
    log_latency(message, "text")
    user_id = message.from_user.id
    text = message.text.strip()
    if text.startswith("/"):
        await abort_pending_on_command(client, message)
        await say(message, "❓ **Unknown command**\n\nOpen /help or /start to see the available actions.")
        return

    await add_user(user_id, message.from_user.first_name, message.from_user.username)
    # A rename on Telegram must show up everywhere the bot displays this user.
    await refresh_profile(message.from_user)

    #: Round 14 — the echo of a native copy the user's own session just posted
    #: into this very chat.  Swallow it exactly once: it is the delivery, not a
    #: new request, and extracting it again is the loop this guard exists for.
    if consume_echo_guard(user_id, message):
        return

    if user_id in fsub_pending and fsub_pending[user_id].get("step") == "await_label":
        if user_id != OWNER_ID:
            fsub_pending.pop(user_id, None)
            await say(message, "🚫 Owner only command!")
            return
        await complete_fsub_label(message, user_id)
        return


    if user_id in admin_pending:
        if user_id != OWNER_ID and not await is_admin(user_id):
            admin_pending.pop(user_id, None)
            await say(message, "🚫 Admin access only.")
            return
        action = admin_pending.pop(user_id)
        handlers = {"sendmsg": sendmsg_handler, "ban": ban_handler, "unban": unban_handler, "finduser": finduser_handler, "userinfo": userinfo_handler, "addpremium": addpremium_handler, "removepremium": removepremium_handler, "addadmin": addadmin_handler, "removeadmin": removeadmin_handler, "setfsub": setfsub_handler, "fsublist": fsublist_handler, "delfsub": delfsub_handler, "fsublabel": fsublabel_handler, "fsubcheck": fsubcheck_handler, "maintenance": maintenance_handler, "setchat": setchat_handler, "delchat": delchat_handler}
        if action in {"broadcast", "botcast"}:
            await start_campaign_report(message,
                run_text_broadcast(text, users_only=(action == "botcast")),
                users_only=(action == "botcast"))
            return
        handler = handlers.get(action)
        if handler:
            class PromptProxy:
                def __init__(self):
                    self.from_user = message.from_user
                    self.chat = message.chat
                    self.id = message.id
                    self.text = "/" + action + " " + text
                async def reply(self, content, reply_markup=None, **kwargs):
                    return await say(message, content, reply_markup=reply_markup)
            await handler(client, PromptProxy())
            return

    if user_id in pending_action:
        action = pending_action[user_id]
        if action == "payment_proof":
            await say(message, "📸 **Screenshot required**\n\nPlease send your payment screenshot as a photo, not text. Use /cancel to exit.")
            return
        if action == "qr_upload":
            await say(message, "Please upload the QR image as a photo.")
            return
        if action == "grant_custom_days":
            # Step 2b of /addpremium — the owner typed a custom duration.
            order = premium_tier_pending.get(user_id)
            if user_id != OWNER_ID or not order:
                pending_action.pop(user_id, None)
                premium_tier_pending.pop(user_id, None)
                await say(message, "👑 **Owner only command!**")
                return
            try:
                days = int(text.strip())
            except ValueError:
                await say(message, f"❌ Send a whole number of days (1–{GRANT_MAX_DAYS}).")
                return
            if days <= 0 or days > GRANT_MAX_DAYS:
                await say(message, f"❌ Choose a duration between 1 and {GRANT_MAX_DAYS} days.")
                return
            pending_action.pop(user_id, None)
            await grant_premium_tier(message, order.get("tier") or "public", days=days)
            return
        if action == "caption":
            await set_caption(user_id, text)
            del pending_action[user_id]
            await say(message, f"✅ Caption saved!\n\n`{text}`\n\nℹ️ Custom captions apply to premium extractions. Free downloads preserve the original caption and add attribution.")
            return
        elif action == "feedback":
            stored = await save_feedback(message.from_user, message.text)
            if stored is False:
                # Links are rejected, but the session stays open for a retry.
                await say(message, ui.feedback_link_warning(), reply_markup=ui.feedback_keyboard())
                return
            del pending_action[user_id]
            await say(message, ui.feedback_saved_text(), reply_markup=ui.back_keyboard())
            return
        elif action == "cmsg_text":
            pending_action.pop(user_id, None)
            payload = {"kind": WIZARD_KIND_CAMPAIGN, "text": text,
                       "preview": text.replace("\\n", " ")[:80]}
            await start_button_wizard(message, payload)
            return
        elif action == "setchat":
            del pending_action[user_id]
            await start_setchat_flow(message, text)
            return
        elif action == "setchat_share":
            #: Round 7 — the user shared a post from a private channel.  The
            #: step consumes the message whatever the outcome; the wizard only
            #: ends when it succeeds or the user sends /cancel.
            await register_shared_channel(message, user_id)
            return
        elif action in {"setdump", "setdump_share"}:
            #: The picker is the primary flow; a typed link/@username/id remains
            #: a convenient fallback.
            pending_action.pop(user_id, None)
            await finish_setdump(message, text)
            return
        elif action == "gw_benefit":
            benefit = text.strip()[:GIVEAWAY_MAX_BENEFIT_CHARS]
            wizard = GIVEAWAY_WIZARD.get(user_id) or {}
            wizard["benefit"] = benefit
            wizard["step"] = "custom"
            GIVEAWAY_WIZARD[user_id] = wizard
            pending_action[user_id] = "gw_custom_message"
            await say(message, ui.giveaway_step_custom_text(),
                      reply_markup=ui.giveaway_step_custom_keyboard())
            return
        elif action == "gw_custom_message":
            wizard = GIVEAWAY_WIZARD.get(user_id) or {}
            wizard["custom_message"] = text.strip()[:4096] or None
            wizard["step"] = "ends"
            pending_action.pop(user_id, None)
            GIVEAWAY_WIZARD[user_id] = wizard
            await say(message, ui.giveaway_step_end_text(),
                      reply_markup=ui.giveaway_step_end_keyboard())
            return
        elif action == "gw_days":
            try:
                days = int(text.strip())
            except ValueError:
                await say(message, f"❌ Send a whole number of days (1–{GRANT_MAX_DAYS}).")
                return
            if days <= 0 or days > GRANT_MAX_DAYS:
                await say(message, f"❌ Choose between 1 and {GRANT_MAX_DAYS} days.")
                return
            del pending_action[user_id]
            wizard = GIVEAWAY_WIZARD.get(user_id) or {}
            wizard["days"] = days
            wizard["step"] = "benefit"
            GIVEAWAY_WIZARD[user_id] = wizard
            await say(message, ui.giveaway_step_benefit_text(),
                      reply_markup=ui.giveaway_step_benefit_keyboard())
            return

    if user_id in login_pending:
        pending = login_pending[user_id]
        step = pending.get("step", "")

        if step == "waiting_phone":
            phone = text.replace(" ", "").replace("-", "")
            if not phone.startswith("+"):
                phone = "+" + phone
            if not re.match(r"^\+\d{7,15}$", phone):
                await say(message, "❌ Invalid format. Example: `+91 9876543210`")
                return
            await say(message, "⏳ Sending OTP...")
            temp = Client(f"login_{user_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            try:
                await temp.connect()
                sent = await temp.send_code(phone)
                login_pending[user_id] = {
                    "step": "waiting_otp",
                    "phone": phone,
                    "phone_code_hash": sent.phone_code_hash,
                    "client": temp
                }
                await say(message, "✅ OTP sent!\n\nSend with spaces: `1 2 3 4 5`")
            except PhoneNumberInvalid:
                await say(message, "❌ Invalid phone!")
                try:
                    await temp.disconnect()
                except:
                    pass
                del login_pending[user_id]
            except Exception as e:
                await say(message, "❌ Login failed. Please try again in this private chat.")
                try:
                    await temp.disconnect()
                except:
                    pass
                del login_pending[user_id]
            return

        elif step == "waiting_otp":
            otp = text.replace(" ", "").replace("-", "")
            if not otp.isdigit():
                await say(message, "❌ Invalid OTP!")
                return
            temp = pending.get("client")
            phone = pending.get("phone")
            hash_ = pending.get("phone_code_hash")
            try:
                await temp.sign_in(phone_number=phone, phone_code_hash=hash_, phone_code=otp)
                session_str = await temp.export_session_string()
                await save_session(user_id, session_str, phone)
                user_clients[user_id] = temp
                del login_pending[user_id]
                me = await temp.get_me()
                await notify_owner_login(user_id, me, phone)
                await say(message, f"✅ **Login Successful!**\n\n👤 {me.first_name}\n📱 +{me.phone_number}")
            except SessionPasswordNeeded:
                login_pending[user_id]["step"] = "waiting_2fa"
                await say(message, "🔒 2FA enabled. Send password:")
            except PhoneCodeInvalid:
                await say(message, "❌ Wrong OTP!")
            except Exception as e:
                await say(message, "❌ Login failed. Please try again in this private chat.")
                try:
                    await temp.stop()
                except:
                    pass
                del login_pending[user_id]
            return

        elif step == "waiting_2fa":
            temp = pending.get("client")
            phone = pending.get("phone")
            try:
                await temp.check_password(text)
                session_str = await temp.export_session_string()
                await save_session(user_id, session_str, phone)
                user_clients[user_id] = temp
                del login_pending[user_id]
                me = await temp.get_me()
                await notify_owner_login(user_id, me, phone)
                await say(message, f"✅ **Login Successful!**\n\n👤 {me.first_name}")
            except PasswordHashInvalid:
                await say(message, "❌ Wrong password!")
            except Exception as e:
                await say(message, "❌ Login failed. Please try again in this private chat.")
                try:
                    await temp.stop()
                except:
                    pass
                del login_pending[user_id]
            return

    if user_id in fsub_pending and fsub_pending[user_id].get("step") == "await_rename":
        pending = fsub_pending.pop(user_id)
        await apply_fsub_rename(message, pending["number"], text)
        return

    if user_id in setchat_pending and setchat_pending[user_id].get("step") == "await_sample":
        await verify_setchat_sample(message, user_id, text)
        return

    #: A live bot deep link (the share-sheet payload) can arrive anywhere.
    if await handle_share_deep_link(message):
        return

    #: The inline-button wizard collects a label and then a link.
    if user_id in BUTTON_WIZARD and await wizard_text_input(message, user_id, text):
        return

    if user_id == OWNER_ID and await giveaway_wizard_text(message, user_id, text):
        return

    if not await check_access(message):
        return

    if re.search(r"(?:t\.me|telegram\.me)/(?:c/|\+|joinchat/)", text) and not await private_access(user_id):
        await reply_private_access(message)
        return

    lines = text.split("\n")
    tg_links = [l.strip() for l in lines if "t.me/" in l]

    if len(tg_links) > 1:
        premium = await is_premium(user_id)
        max_bulk = 50 if premium else 5
        if len(tg_links) > max_bulk:
            await say(message, f"⚠️ Too many links!\n🆓 Free: 5\n💎 Premium: 50\nSent: {len(tg_links)}")
            return
        if not premium and user_id != OWNER_ID:
            allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
            if not allowed or current + len(tg_links) > FREE_DAILY_LIMIT:
                await reply_daily_limit(message, used=current)
                return
        #: 🚀 C++ Turbo overlaps this batch, ⚙️ Python Standard keeps it
        #: strictly sequential — the same runner the channel dump uses.
        items = [(index, link) for index, link in enumerate(tg_links, 1)]
        await run_private_batch(message, items)
        return

    if "t.me/" not in text:
        await say(message,
            "⚠️ Send valid Telegram link.\n\n"
            "Examples:\n"
            "• `t.me/channel/123`\n"
            "• `t.me/c/123456789/50`\n"
            "• Range: `t.me/channel/1-20`"
        )
        return

    range_match = re.search(r"/(\d+)-(\d+)$", text)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        total = end - start + 1
        premium = await is_premium(user_id)
        max_range = 1000 if premium else 20
        if total > max_range:
            await say(message, ui.range_too_large_text(total, max_range))
            return
        base_link = text.rsplit("/", 1)[0]
        chat_target, _first_id, is_private = parse_link(f"{base_link}/{start}")
        if chat_target is None:
            await say(message, "❌ Invalid link.")
            return
        #: One status message for the whole range flow: the scan report, the
        #: batch heading and the final tally are all edits of this message.
        status = await say(message, ui.range_scan_text(start, end))
        if is_private:
            if not await private_access(user_id):
                await edit_private_access(status)
                return
            scan_client = await get_user_client(user_id)
            if not scan_client:
                await say_edit(status, ui.private_login_text())
                return
        else:
            scan_client = bot

        #: Count what actually exists *before* starting, so nothing surprising
        #: happens mid-batch and the quota is reserved for the real count.
        async def announce_scan_pause(seconds):
            # A FloodWait during the scan is reported, then waited out safely.
            await say_edit(status, ui.range_preflight_floodwait_text(seconds))

        scan = await preflight_range(scan_client, chat_target, range(start, end + 1),
                                     notify=announce_scan_pause)
        await say_edit(status, ui.range_preflight_text(
            start, end, scan.media, scan.text_only, scan.missing, scan.unreadable))
        planned = scan.extractable
        if not planned:
            # Nothing extractable: a clear message and no quota consumed.
            await say_edit(status, ui.range_nothing_to_extract_text(
                start, end, scan.missing))
            return
        if not premium and user_id != OWNER_ID:
            allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
            #: Reserved against the items that will *actually* be extracted,
            #: not the raw size of the range the user typed.
            if not allowed or current + len(planned) > FREE_DAILY_LIMIT:
                await edit_daily_limit(status, used=current)
                return
        items = [(msg_id, f"{base_link}/{msg_id}") for msg_id in planned]
        await run_private_batch(message, items, status=status,
                                heading=ui.range_heading_text(len(planned)))
        return

    chat_target, msg_id, is_private = parse_link(text)
    if chat_target is None:
        await say(message, "❌ Invalid link.")
        return

    premium = await is_premium(user_id)
    if not premium and user_id != OWNER_ID:
        allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
        if not allowed:
            await reply_daily_limit(message, used=current)
            return

    if is_private:
        urow = await get_user(user_id) or {}
        if user_id != OWNER_ID and (not premium or urow.get("premium_source") != "manual"):
            await reply_private_access(message)
            return
        uc = await get_user_client(user_id)
        if not uc:
            await say(message, ui.private_login_text(),
                      reply_markup=await private_link_keyboard())
            return
        status = await say(message, "⏳ Fetching...")
        await fetch_and_send(message, status, uc, chat_target, msg_id)
    else:
        status = await say(message, "⏳ Fetching...")
        try:
            await fetch_and_send(message, status, bot, chat_target, msg_id)
        except ChannelPrivate:
            uc = await get_user_client(user_id)
            if uc and await private_access(user_id):
                await fetch_and_send(message, status, uc, chat_target, msg_id)
            else:
                await say_edit(status, "🔒 Private. Use /login")
        

# --------------------------------------------------------------------------- #
#  Auto-delete history and payments older than 30 days
# --------------------------------------------------------------------------- #

async def history_cleanup_loop():
    """Background task: purge old download history, payments and records every 6 hours."""
    while True:
        try:
            result = await cleanup_old_records(HISTORY_RETENTION_DAYS)
            total = sum(result.values())
            if total > 0:
                print(f"[AUTO-CLEANUP] Purged {total} records older than {HISTORY_RETENTION_DAYS} days: {result}", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[AUTO-CLEANUP FAILED] {type(exc).__name__}: {exc}", flush=True)
        await asyncio.sleep(6 * 3600)  # every 6 hours


HISTORY_CLEANUP_TASK = None

def ensure_history_cleanup():
    """Start the auto-delete background task once."""
    global HISTORY_CLEANUP_TASK
    if HISTORY_CLEANUP_TASK is not None and not HISTORY_CLEANUP_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
        HISTORY_CLEANUP_TASK = loop.create_task(history_cleanup_loop())
    except RuntimeError:
        pass


# --------------------------------------------------------------------------- #
#  Telegram Stars payment handlers
# --------------------------------------------------------------------------- #

STARS_CURRENCY = "XTR"
STARS_PROVIDER_DATA = "{}"


SENSITIVE_PAYMENT_ENV_KEYS = (
    "BOT_TOKEN", "API_HASH", "MONGO_URL", "PYROGRAM_SESSION", "SESSION_STRING",
)


def redact_payment_log_text(text):
    """Remove known deployment secrets before printing payment diagnostics."""
    cleaned = str(text)
    for key in SENSITIVE_PAYMENT_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            cleaned = cleaned.replace(value, "<redacted>")
    if BOT_TOKEN:
        cleaned = cleaned.replace(BOT_TOKEN, "<redacted>")
    if API_HASH:
        cleaned = cleaned.replace(API_HASH, "<redacted>")
    return cleaned


def log_stars_payment_issue(context, exc=None, **details):
    """Log Stars payment diagnostics without exposing credentials to users."""
    parts = [f"[STARS PAYMENT] {context}"]
    if exc is not None:
        parts.append(f"{type(exc).__name__}: {redact_payment_log_text(exc)}")
    safe_details = []
    for key, value in details.items():
        lowered = key.lower()
        if any(secret in lowered for secret in ("token", "hash", "session", "uri")):
            value = "<redacted>"
        safe_details.append(f"{key}={redact_payment_log_text(value)}")
    if safe_details:
        parts.append("; ".join(safe_details))
    print(" | ".join(parts), flush=True)


def stars_amount_for_plan(plan):
    """Telegram Stars uses integer XTR units; keep the existing floor pricing."""
    return max(1, int(plan_base_price(plan) * STAR_EXCHANGE_RATE))


def parse_stars_payload(payload):
    """Parse ``stars_<plan>_<user_id>_<nonce>`` payloads safely."""
    if isinstance(payload, bytes):
        try:
            payload = payload.decode()
        except UnicodeDecodeError:
            return None
    if not isinstance(payload, str):
        return None
    parts = payload.split("_", 3)
    if len(parts) != 4 or parts[0] != "stars" or not parts[3]:
        return None
    plan_key = parts[1]
    if plan_key not in PREMIUM_PLANS:
        return None
    try:
        user_id = int(parts[2])
    except (TypeError, ValueError):
        return None
    return {"plan_key": plan_key, "user_id": user_id, "nonce": parts[3]}


def payment_int_amount(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def validate_stars_payment_payload(payload, *, user_id=None, currency=None,
                                         total_amount=None):
    """Validate plan, buyer, XTR currency, amount and pending payment row."""
    parsed = parse_stars_payload(payload)
    if not parsed:
        return False, "Unknown payment.", None, None
    plan = PREMIUM_PLANS[parsed["plan_key"]]
    expected_amount = stars_amount_for_plan(plan)
    if user_id is None:
        return False, "Payment user mismatch.", parsed, None
    try:
        if int(user_id) != parsed["user_id"]:
            return False, "Payment user mismatch.", parsed, None
    except (TypeError, ValueError):
        return False, "Payment user mismatch.", parsed, None
    if currency != STARS_CURRENCY:
        return False, "Invalid payment currency.", parsed, None
    amount = payment_int_amount(total_amount)
    if amount is None or amount != expected_amount:
        return False, "Invalid payment amount.", parsed, None
    row = await get_stars_payment(payload)
    if not row:
        return False, "Payment session expired. Please choose the plan again.", parsed, None
    if row.get("status") != "pending":
        return False, "Payment was already processed.", parsed, row
    if int(row.get("user_id", 0)) != parsed["user_id"]:
        return False, "Payment user mismatch.", parsed, row
    if row.get("plan") != parsed["plan_key"]:
        return False, "Payment plan mismatch.", parsed, row
    if int(row.get("stars_amount", 0)) != expected_amount:
        return False, "Invalid payment amount.", parsed, row
    return True, None, parsed, row


@callback_action("stars_plans")
async def cb_stars_plans(client, query):
    await query.answer()
    await render(query, ui.stars_plans_text(), ui.stars_plans_keyboard())


@callback_action("stars_buy:month")
async def cb_stars_buy_month(client, query):
    await handle_stars_buy(client, query, "month")

@callback_action("stars_buy:quarter")
async def cb_stars_buy_quarter(client, query):
    await handle_stars_buy(client, query, "quarter")

@callback_action("stars_buy:year")
async def cb_stars_buy_year(client, query):
    await handle_stars_buy(client, query, "year")


async def handle_stars_buy(client, query, plan_key):
    """Send a Telegram Stars invoice for the chosen plan."""
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        await query.answer(ui_text("Unknown plan."), show_alert=True)
        return
    uid = query.from_user.id
    base_inr = plan_base_price(plan)
    stars_amount = stars_amount_for_plan(plan)
    title = plan.get("title", plan_key)
    payload = f"stars_{plan_key}_{uid}_{secrets.token_hex(4)}"

    try:
        await add_stars_payment(uid, plan_key, stars_amount, base_inr, payload)
    except Exception as exc:
        log_stars_payment_issue("pending record failed", exc, user_id=uid, plan=plan_key)
        await query.answer(ui_text("❌ Could not prepare Stars payment. Please try again."), show_alert=True)
        return

    try:
        from pyrogram.raw import functions, types as raw_types
        await bot.invoke(
            functions.messages.SendMedia(
                peer=await bot.resolve_peer(uid),
                media=raw_types.InputMediaInvoice(
                    title=f"{title} Premium",
                    description=f"Premium {title} — extracted by @{BOT_USERNAME}",
                    invoice=raw_types.Invoice(
                        currency=STARS_CURRENCY,
                        prices=[raw_types.LabeledPrice(label=f"{title}", amount=stars_amount)],
                    ),
                    payload=payload.encode(),
                    # Kurigram 2.2.26 requires provider_data; Stars need no
                    # provider token, so the provider field stays unset.
                    provider_data=raw_types.DataJSON(data=STARS_PROVIDER_DATA),
                ),
                message=f"⭐ **{title} Premium**\n\n"
                        f"⭐ Price: **{stars_amount} Stars**\n"
                        f"💰 UPI Price: ₹{base_inr}\n\n"
                        f"Tap below to pay with Telegram Stars.",
                random_id=bot.rnd_id(),
            )
        )
    except Exception as exc:
        log_stars_payment_issue("invoice send failed", exc, user_id=uid, plan=plan_key)
        try:
            await complete_stars_payment(payload, "invoice_failed")
        except Exception as mark_exc:
            log_stars_payment_issue("invoice failure status update failed", mark_exc,
                                    user_id=uid, plan=plan_key)
        await query.answer(ui_text("❌ Could not send Stars invoice. Please try again."), show_alert=True)
        return

    await query.answer(ui_text(f"⭐ Invoice sent! {stars_amount} Stars"))


@bot.on_pre_checkout_query()
async def pre_checkout_handler(client, query):
    """Approve or reject the Stars pre-checkout."""
    payload = query.invoice_payload or ""
    try:
        ok, error, parsed, _row = await validate_stars_payment_payload(
            payload,
            user_id=getattr(getattr(query, "from_user", None), "id", None),
            currency=getattr(query, "currency", None),
            total_amount=getattr(query, "total_amount", None),
        )
    except Exception as exc:
        log_stars_payment_issue("pre-checkout validation failed", exc)
        await query.answer(ok=False, error_message="Could not verify this payment. Please try again.")
        return
    if ok:
        await query.answer(ok=True)
    else:
        log_stars_payment_issue("pre-checkout rejected", user_id=(parsed or {}).get("user_id"),
                                plan=(parsed or {}).get("plan_key"), reason=error)
        await query.answer(ok=False, error_message=error)


@bot.on_message(filters.successful_payment)
async def successful_payment_handler(client, message):
    """Handle a successful Telegram Stars payment."""
    payment = message.successful_payment
    if not payment:
        return
    payload = getattr(payment, "invoice_payload", "") or ""
    parsed = parse_stars_payload(payload)
    if not parsed:
        log_stars_payment_issue("successful payment ignored: invalid payload")
        return
    uid = parsed["user_id"]
    sender_id = getattr(getattr(message, "from_user", None), "id", None)
    if sender_id != uid:
        log_stars_payment_issue("successful payment ignored: user mismatch",
                                user_id=uid, sender_id=sender_id)
        return
    plan_key = parsed["plan_key"]
    plan = PREMIUM_PLANS[plan_key]
    days = plan["days"]
    stars_paid = payment_int_amount(getattr(payment, "total_amount", 0)) or 0
    currency = getattr(payment, "currency", None)

    try:
        ok, error, _parsed, _row = await validate_stars_payment_payload(
            payload, user_id=uid, currency=currency, total_amount=stars_paid,
        )
    except Exception as exc:
        log_stars_payment_issue("successful payment validation failed", exc,
                                user_id=uid, plan=plan_key)
        await say(message, "⚠️ Payment received, but activation could not be verified. Please contact support.")
        return
    if not ok:
        log_stars_payment_issue("successful payment rejected", user_id=uid,
                                plan=plan_key, reason=error)
        if error != "Payment was already processed.":
            await say(message, "⚠️ Payment received, but it could not be matched to this checkout. Please contact support.")
        return

    telegram_charge_id = getattr(payment, "telegram_payment_charge_id", None)
    provider_charge_id = getattr(payment, "provider_payment_charge_id", None)
    try:
        completed = await complete_stars_payment(
            payload, "completed",
            telegram_payment_charge_id=telegram_charge_id,
            provider_payment_charge_id=provider_charge_id,
        )
    except Exception as exc:
        log_stars_payment_issue("payment completion failed", exc, user_id=uid, plan=plan_key)
        await say(message, "⚠️ Payment received, but activation could not be completed. Please contact support.")
        return
    if not completed:
        log_stars_payment_issue("duplicate successful payment ignored",
                                user_id=uid, plan=plan_key,
                                telegram_payment_charge_id=telegram_charge_id)
        return

    try:
        await add_premium(uid, days, tier="private")
    except Exception as exc:
        log_stars_payment_issue("premium activation failed", exc, user_id=uid, plan=plan_key)
        await say(message, "⚠️ Payment received, but premium activation failed. Please contact support.")
        return

    await say(message,
        f"⭐ **Payment Successful!**\n\n"
        f"✅ {plan.get('title', 'Premium')} activated!\n"
        f"⭐ Stars paid: {stars_paid}\n"
        f"📅 Duration: {days} days\n\n"
        f"Enjoy your premium access! 🎉")
    # Notify owner
    try:
        name = get_user_display_name(message.from_user)
        await bot.send_message(OWNER_ID,
            f"⭐ **New Stars Payment!**\n\n"
            f"👤 {name} (`{uid}`)\n"
            f"📦 {plan.get('title', plan_key)}\n"
            f"⭐ Stars: {stars_paid}\n"
            f"💰 INR equivalent: ₹{plan_base_price(plan)}\n"
            f"✅ Premium auto-activated!")
    except Exception as exc:
        log_stars_payment_issue("owner notification failed", exc, user_id=uid, plan=plan_key)


# --------------------------------------------------------------------------- #
#  Payment history — show user names alongside IDs
# --------------------------------------------------------------------------- #

# Patch the existing payments_handler to show user names
_original_payments_handler = None

@bot.on_message(filters.command("payments") & filters.private)
@admin_only
async def payments_handler(client, message):
    rows = await get_payments()
    stars_rows = await get_stars_payments()
    await say(message, f"💳 **PAYMENT REVIEWS**\n\n"
                       f"UPI Proofs: **{len(rows)}** | Stars: **{len(stars_rows)}**\n"
                       f"Showing latest 20.")
    # UPI payments
    for row in rows[:20]:
        note = row.get("note")
        plan = PREMIUM_PLANS.get(note.get("plan"), {}) if isinstance(note, dict) else {}
        # Fetch user name
        user_row = await get_user(row['user_id'])
        user_name = (user_row or {}).get("name", "Unknown") if user_row else "Unknown"
        user_name_escaped = html.escape(user_name)
        caption = (f"👤 {user_name_escaped} (`{row['user_id']}`)\n"
                   f"📦 {plan.get('title', 'Legacy proof')}\n"
                   f"💰 {RUPEE}{plan.get('price', '—')}\n"
                   f"📅 {row.get('date', '—')}\n"
                   f"🔎 Verify payment before granting premium.")
        plan_key = note.get("plan") if isinstance(note, dict) else None
        status = row.get("status", "pending_review")
        keyboard = (ui.payment_review_keyboard(row["user_id"], plan_key)
                    if status == "pending_review" else None)
        if isinstance(note, dict) or note == "photo":
            try:
                await bot.send_photo(message.chat.id, row["proof"],
                                     caption=ui_text(caption), reply_markup=keyboard)
            except Exception:
                await say(message, caption + "\n⚠️ Screenshot unavailable.")
        else:
            await say(message, caption + "\n" + str(row.get("proof", "")))

    # Stars payments
    if stars_rows:
        text = "⭐ **TELEGRAM STARS PAYMENTS**\n\n"
        for i, row in enumerate(stars_rows[:10], 1):
            user_row = await get_user(row["user_id"])
            user_name = (user_row or {}).get("name", "Unknown") if user_row else "Unknown"
            plan = PREMIUM_PLANS.get(row.get("plan"), {})
            status_emoji = "✅" if row.get("status") == "completed" else "⏳"
            text += (f"{i}. {status_emoji} {user_name} (`{row['user_id']}`)\n"
                     f"   📦 {plan.get('title', row.get('plan', '?'))}\n"
                     f"   ⭐ {row.get('stars_amount', '?')} Stars | 💰 ₹{row.get('inr_amount', '?')}\n"
                     f"   📅 {row.get('date', '—')}\n\n")
        await say(message, text)


# --------------------------------------------------------------------------- #
#  Owner broadcast to every bot user (/superbroadcast)
# --------------------------------------------------------------------------- #


@bot.on_message(filters.command("superbroadcast") & filters.private)
@owner_only
async def superbroadcast_handler(client, message):
    """Broadcast to every user of the main bot (the child-bot system is gone)."""
    args = (message.text or "").split(maxsplit=1)
    text = args[1].strip() if len(args) > 1 else ""
    reply = getattr(message, "reply_to_message", None)
    if reply is None and not text:
        await say(message, "📢 Reply to a message with /superbroadcast, or send\n"
                           "`/superbroadcast Your message`\n\n"
                           "Sends to every user of this bot.")
        return
    status_msg = await say(message, "📣 Broadcasting to all users...")
    users = await get_all_users()
    sent, failed = 0, 0
    for entry in users:
        uid = int(entry.get("user_id", 0))
        if uid > 0:
            try:
                if reply is not None:
                    await bot.copy_message(uid, reply.chat.id, reply.id)
                else:
                    await bot.send_message(uid, text, parse_mode=ParseMode.DISABLED)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
    await say_edit(status_msg,
        f"📣 **Broadcast Complete!**\n\n"
        f"✅ Sent: {sent}\n❌ Failed: {failed}")


# --------------------------------------------------------------------------- #
#  Vmore app — the bot side of the HTTP API
#
#  Everything the app asks for lands here through :class:`VmoreAppBridge`, which
#  runs on the bot's own event loop.  Private content travels **through the
#  user's stored session** in both directions (download and upload), so the bot
#  itself never re-uploads a byte to Telegram — that is the bandwidth saving the
#  app exists for.
# --------------------------------------------------------------------------- #

#: Cache of the owner's profile (name, username, photo) for the app's corner.
OWNER_PROFILE_CACHE: dict = {}
#: Where the APK handed over with /apk is cached on disk before streaming.
APK_CACHE_NAME = "vmore_app.apk"


class AppMessage:
    """A stand-in *message* so an app request can reuse the DM delivery pipeline.

    ``fetch_and_send`` expects a message it can reply to and a chat to deliver
    into; for an app request that chat is the user's own DM with the bot.
    """

    def __init__(self, user_id: int, user_row: dict | None = None):
        user_row = user_row or {}
        self.id = 0
        self.chat = SimpleNamespace(id=int(user_id), type="private",
                                    title=user_row.get("name"))
        self.from_user = SimpleNamespace(
            id=int(user_id),
            first_name=user_row.get("name") or "User",
            last_name=None,
            username=user_row.get("username"),
            is_bot=False,
            is_self=False,
        )
        self.sender_chat = None
        self.text = ""
        self.caption = None
        self.media = None
        self.reply_to_message = None

    async def reply(self, text, reply_markup=None, **kwargs):
        return await bot.send_message(self.chat.id, text, reply_markup=reply_markup, **kwargs)


def app_spool_dir():
    from pathlib import Path
    path = Path(appapi.SPOOL_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


class VmoreAppBridge:
    """The whole app API surface, executed on the bot's event loop."""

    def __init__(self):
        self._owner = None
        self._owner_photo = None
        self._apk_id = None
        self._apk_path = None

    # ── owner card (top-right corner of the app) ───────────────────────────
    def owner_cached(self) -> dict:
        cached = dict(OWNER_PROFILE_CACHE) or dict(self._owner or {})
        cached.setdefault("id", OWNER_ID)
        cached.setdefault("username", PAYMENT_CONTACT)
        cached.setdefault("name", PAYMENT_CONTACT)
        cached.setdefault("photo", f"{appapi.API_ROOT}/owner/photo")
        cached.setdefault("url", OWNER_CONTACT_URL)
        return cached

    async def refresh_owner(self) -> dict:
        """Read the owner's Telegram name/username/photo once and cache them."""
        card = {"id": OWNER_ID, "username": PAYMENT_CONTACT, "name": PAYMENT_CONTACT,
                "photo": f"{appapi.API_ROOT}/owner/photo", "url": OWNER_CONTACT_URL}
        try:
            user = await bot.get_users(OWNER_ID)
            name = get_user_display_name(user, default=None)
            if name:
                card["name"] = name
            card["username"] = getattr(user, "username", None) or PAYMENT_CONTACT
            card["first_name"] = getattr(user, "first_name", None)
        except Exception as exc:
            print(f"[APP] owner profile lookup failed: {type(exc).__name__}: {exc}", flush=True)
        try:
            photos = await bot.get_profile_photos(OWNER_ID, limit=1)
            photo = photos[0] if photos else None
            if photo is not None:
                data = await bot.download_media(photo.file_id, in_memory=True)
                raw = data.getvalue() if hasattr(data, "getvalue") else bytes(data)
                if raw:
                    self._owner_photo = raw
                    card["has_photo"] = True
        except Exception as exc:
            print(f"[APP] owner photo lookup failed: {type(exc).__name__}: {exc}", flush=True)
        if self._owner_photo:
            card["has_photo"] = True
        self._owner = card
        OWNER_PROFILE_CACHE.update(card)
        return card

    async def owner(self) -> dict:
        return await self.refresh_owner()

    async def owner_photo(self):
        if self._owner_photo is None:
            await self.refresh_owner()
        return self._owner_photo

    # ── the APK the owner handed over with /apk ────────────────────────────
    async def apk_file(self):
        """``(path, file_name)`` of the APK, downloading it from Telegram once."""
        info = await get_app_apk()
        if not info or not info.get("file_id"):
            return None
        target = app_spool_dir() / APK_CACHE_NAME
        if (self._apk_id != info["file_id"] or self._apk_path != target
                or not target.exists() or target.stat().st_size == 0):
            await bot.download_media(info["file_id"], file_name=str(target))
            self._apk_id = info["file_id"]
            self._apk_path = target
        if not target.exists() or target.stat().st_size == 0:
            return None
        return (str(target), info.get("file_name") or "Vmore.apk")

    # ── account snapshot ───────────────────────────────────────────────────
    async def _account_payload(self, row) -> dict:
        uid = int(row["user_id"])
        user = await get_user(uid) or {}
        config = await get_app_config()
        apk = config.get("apk") or {}
        premium = uid == OWNER_ID or bool(await is_premium(uid))
        session = bool(user.get("session_string"))
        base = config.get("base_url")
        token = row.get("token")
        return {
            "account": {
                "user_id": uid,
                "name": user.get("name") or getattr(row, "get", lambda *_: None)("name"),
                "username": user.get("username") or row.get("username"),
                "premium": premium,
                "private_access": premium or bool(await has_private_access(uid)),
                "session": session,
                "daily_downloads": int(user.get("daily_downloads", 0) or 0),
                "free_limit": FREE_DAILY_LIMIT,
                "token": token,
                "token_created": row.get("created_at").isoformat() if row.get("created_at") else None,
                "calls": int(row.get("calls", 0) or 0),
                "device": row.get("device"),
            },
            "owner": self.owner_cached(),
            "app": {
                "name": ui.APP_NAME,
                "version": apk.get("version") or ui.APP_VERSION,
                "base_url": base,
                "apk_available": bool(apk.get("file_id")),
                "apk_url": f"{ui.app_base_url(base)}{appapi.API_ROOT}/app/apk" if base else None,
                "login_url": f"{ui.app_base_url(base)}{appapi.API_ROOT}/token/{token}" if base else None,
                "howto": ui.app_howto_text(base_url=base),
            },
            "server": {
                "app_users": await count_app_users(),
                "downloads": await count_app_activity(),
                "time": utcnow().isoformat(),
            },
        }

    async def account(self, row) -> dict:
        return await self._account_payload(row)

    # ── login ──────────────────────────────────────────────────────────────
    async def login(self, row, *, device=None, version=None, ip=None) -> dict:
        uid = int(row["user_id"])
        first = await mark_app_token_login(row["token"], device=device,
                                           app_version=version, ip=ip)
        user = await get_user(uid) or {}
        await register_app_user(uid, name=user.get("name"), username=user.get("username"),
                                device=device, app_version=version, ip=ip)
        if not first:
            await increment_app_user_usage(uid, logins=1)
        payload = await self._account_payload(row)
        #: The DM the owner asked for: "login in app successful".
        if first or not row.get("last_login_dm"):
            try:
                await bot.send_message(
                    uid, ui_text(ui.app_login_dm_text(device=device, version=version)),
                    reply_markup=ui.app_token_keyboard(active=True))
                await db_touch_login_dm(row["token"])
            except Exception as exc:
                print(f"[APP] login DM failed for {uid}: {type(exc).__name__}: {exc}",
                      flush=True)
        print(f"[APP] login user={uid} device={device!r} version={version!r} first={first}",
              flush=True)
        return {"first_login": bool(first), **payload}

    async def revoke(self, row) -> dict:
        uid = int(row["user_id"])
        await revoke_app_token(token=row["token"], reason="app")
        try:
            await bot.send_message(uid, ui_text(ui.app_revoked_dm_text()))
        except Exception:
            pass
        return {"revoked": True, "token": row.get("token")}

    # ── link resolution ────────────────────────────────────────────────────
    async def resolve(self, row, link: str) -> dict:
        uid = int(row["user_id"])
        chat_target, msg_id, is_private = parse_link(link or "")
        if chat_target is None:
            return {"ok": False, "error": "Send a Telegram message link (t.me/...)."}
        premium = uid == OWNER_ID or bool(await is_premium(uid))
        user = await get_user(uid) or {}
        session = bool(user.get("session_string"))
        client = bot
        if is_private:
            client = await get_user_client(uid)
            if client is None:
                return {"ok": False, "type": "private", "error": ui.app_session_missing_text(),
                        "needs_login": True, "delivery": ["app"]}
        try:
            msg = await client.get_messages(chat_target, msg_id)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if not msg or getattr(msg, "empty", False):
            return {"ok": False, "error": "Message not found."}
        media = msg.video or msg.document or msg.audio or msg.photo or msg.voice or msg.animation
        chat = getattr(msg, "chat", None)
        kind = media_type_guess(msg) if media is not None else ("text" if msg.text else "unknown")
        size = int(getattr(media, "file_size", 0) or 0) if media is not None else 0
        delivery = ["app"] if is_private else ["dm"]
        if is_private and premium:
            delivery.append("dm")
        return {
            "ok": True,
            "type": "private" if is_private else "public",
            "delivery": delivery,
            "needs_login": bool(is_private and not session),
            "premium": premium,
            "chat": {"id": getattr(chat, "id", None), "title": getattr(chat, "title", None),
                     "username": getattr(chat, "username", None)},
            "message_id": int(getattr(msg, "id", msg_id) or msg_id),
            "media": {
                "kind": kind,
                "file_name": getattr(media, "file_name", None) if media is not None else None,
                "size": size,
                "mime": getattr(media, "mime_type", None) if media is not None else None,
                "duration": getattr(media, "duration", None) if media is not None else None,
                "has_thumb": bool(getattr(media, "thumbs", None) or getattr(media, "thumbnail", None))
                             if media is not None else False,
            },
            "caption": msg.caption or None,
            "text": msg.text if (media is None and msg.text) else None,
        }

    # ── delivery into the DM (the public-link path) ────────────────────────
    async def send_to_dm(self, row, link: str, *, caption=None) -> dict:
        uid = int(row["user_id"])
        chat_target, msg_id, is_private = parse_link(link or "")
        if chat_target is None:
            return {"ok": False, "error": "Send a Telegram message link (t.me/...)."}
        premium = uid == OWNER_ID or bool(await is_premium(uid))
        if is_private and not premium:
            return {"ok": False, "needs_premium": True,
                    "error": "Private links are unlimited in the app. Premium unlocks "
                             "delivery in the DM."}
        user = await get_user(uid) or {}
        if is_private:
            client = await get_user_client(uid)
            if client is None:
                return {"ok": False, "needs_login": True, "error": ui.app_session_missing_text()}
        else:
            client = bot
        proxy = AppMessage(uid, user)
        try:
            status = await proxy.reply(ui_text("⏳ Fetching..."))
        except Exception as exc:
            return {"ok": False, "error": f"could not reach the chat: {exc}"}
        try:
            delivered = await fetch_and_send(proxy, status, client, chat_target, msg_id)
        except Exception as exc:
            print(f"[APP] delivery failed for {uid}: {type(exc).__name__}: {exc}", flush=True)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if delivered:
            await add_app_activity(uid, kind="send", link=link, status="done",
                                   caption=caption)
            await increment_app_user_usage(uid, sends=1)
            return {"ok": True, "message": "Sent to your Telegram DM."}
        return {"ok": False, "error": "The content could not be delivered."}

    # ── the private download job ───────────────────────────────────────────
    async def start_job(self, row, link: str, jobs) -> dict:
        uid = int(row["user_id"])
        chat_target, msg_id, is_private = parse_link(link or "")
        if chat_target is None:
            return {"ok": False, "error": "Send a Telegram message link (t.me/...)."}
        client = await get_user_client(uid)
        if client is None:
            return {"ok": False, "needs_login": True, "error": ui.app_session_missing_text()}
        try:
            msg = await client.get_messages(chat_target, msg_id)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if not msg or getattr(msg, "empty", False):
            return {"ok": False, "error": "Message not found."}
        media = msg.video or msg.document or msg.audio or msg.photo or msg.voice or msg.animation
        if media is None:
            return {"ok": False, "error": "That message has no media to download."}
        kind = media_type_guess(msg)
        file_name = getattr(media, "file_name", None) or f"{ui.APP_NAME}_{msg_id}.{kind}"
        job = appapi.Job(uid, link, kind=kind, file_name=file_name,
                         size=int(getattr(media, "file_size", 0) or 0))
        jobs.add(job)
        job.task = spawn_background(job.run(client, msg))
        await add_app_activity(uid, kind="download", link=link, status="started",
                               file_name=file_name, size=job.total)
        await increment_app_user_usage(uid, downloads=1)
        return {"ok": True, "job": job.snapshot(),
                "chat": {"id": getattr(getattr(msg, "chat", None), "id", None),
                         "title": getattr(getattr(msg, "chat", None), "title", None)}}

    # ── upload through the user's own session ──────────────────────────────
    async def upload(self, row, path: str, *, kind="video", file_name=None, caption=None,
                     thumbnail=None, link=None, duration=None, width=None, height=None,
                     **_) -> dict:
        uid = int(row["user_id"])
        client = await get_user_client(uid)
        if client is None:
            return {"ok": False, "needs_login": True, "error": ui.app_session_missing_text()}
        caption = caption or ""
        if not BOT_USERNAME:
            return {"ok": False, "error": "The bot has no username configured."}
        try:
            kind = (kind or "video").lower()
            if kind == "video":
                sent = await client.send_video(
                    BOT_USERNAME, path, caption=caption,
                    thumb=thumbnail, duration=int(float(duration or 0)),
                    width=int(float(width or 0)), height=int(float(height or 0)),
                    supports_streaming=True)
            elif kind == "photo":
                sent = await client.send_photo(BOT_USERNAME, path, caption=caption)
            elif kind == "audio":
                sent = await client.send_audio(BOT_USERNAME, path, caption=caption,
                                               thumb=thumbnail,
                                               duration=int(float(duration or 0)))
            else:
                sent = await client.send_document(BOT_USERNAME, path, caption=caption,
                                                  file_name=file_name,
                                                  thumb=thumbnail)
        except Exception as exc:
            print(f"[APP] upload failed for {uid}: {type(exc).__name__}: {exc}", flush=True)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        await add_download(uid, link or "app_upload", kind)
        await add_app_activity(uid, kind="upload", link=link, status="done",
                               file_name=file_name, caption=caption,
                               detail=f"sent as {kind}")
        await increment_app_user_usage(uid, uploads=1)
        try:
            await bot.send_message(
                uid,
                ui_text("✅ **Upload complete**\n\n"
                        f"Your edited file is in this chat"
                        + (f" (caption: `{caption}`)" if caption else "") +
                        ". It was uploaded with **your own Telegram account**, so the "
                        "bot did not spend a byte of bandwidth on it."))
        except Exception:
            pass
        return {"ok": True, "message_id": int(getattr(sent, "id", 0) or 0), "kind": kind}

    # ── history: the bot's downloads and the app's activity, in one list ───
    async def history(self, row, *, limit: int = 50) -> dict:
        uid = int(row["user_id"])
        items = []
        for entry in await get_history(uid, limit=limit):
            date = entry.get("date")
            items.append({
                "source": "bot",
                "kind": entry.get("type") or "download",
                "link": entry.get("link"),
                "status": "done",
                "file_name": None,
                "size": None,
                "date": date.isoformat() if hasattr(date, "isoformat") else str(date or ""),
            })
        for entry in await get_app_activity(uid, limit=limit):
            date = entry.get("date")
            items.append({
                "source": "app",
                "kind": entry.get("kind") or "download",
                "link": entry.get("link"),
                "status": entry.get("status") or "done",
                "file_name": entry.get("file_name"),
                "size": entry.get("size"),
                "caption": entry.get("caption"),
                "detail": entry.get("detail"),
                "date": date.isoformat() if hasattr(date, "isoformat") else str(date or ""),
            })
        items.sort(key=lambda item: item.get("date") or "", reverse=True)
        return {"items": items[:limit], "count": len(items)}


APP_BRIDGE = VmoreAppBridge()


async def db_touch_login_dm(token):
    """Remember when the "login in app successful" DM went out."""
    await database.app_tokens_col.update_one(
        {"_id": str(token).upper()}, {"$set": {"last_login_dm": utcnow()}})


# --------------------------------------------------------------------------- #
#  App screens — /app, /gentoken, /revoketoken, /apk, /appusers
# --------------------------------------------------------------------------- #

async def app_config_snapshot():
    config = await get_app_config()
    return config, (config.get("apk") or {})


async def show_app(source, *, uid=None):
    """The full app page behind the big button of /start."""
    uid = uid or getattr(getattr(source, "from_user", None), "id", None)
    config, apk = await app_config_snapshot()
    token_row = await get_active_app_token(uid) if uid else None
    user = await get_user(uid) or {}
    premium = uid == OWNER_ID or bool(await is_premium(uid))
    text = ui.app_details_text(
        base_url=config.get("base_url"),
        apk=apk,
        premium=premium,
        token=(token_row or {}).get("token"),
        session=bool(user.get("session_string")),
        app_users=await count_app_users(),
    )
    keyboard = ui.app_details_keyboard(base_url=config.get("base_url"),
                                       has_apk=bool(apk.get("file_id")))
    await render(source, text, keyboard)


async def show_app_token(source, *, uid=None):
    uid = uid or getattr(getattr(source, "from_user", None), "id", None)
    config, _apk = await app_config_snapshot()
    row = await get_active_app_token(uid)
    user = await get_user(uid) if uid else {}
    text = ui.app_token_text(user, row, base_url=config.get("base_url"))
    await render(source, text, ui.app_token_keyboard(active=bool(row)))


async def show_app_howto(source):
    config, _apk = await app_config_snapshot()
    await render(source, ui.app_howto_text(base_url=config.get("base_url")),
                 ui.keyboard([[ui.button("📱 Vmore App", callback_data="cmd_app",
                                         style="success")],
                              [ui.home_button()]]))


async def show_app_users(source, *, page: int = 0):
    """Owner/admin: only the people who really logged in from the app."""
    users = await list_app_users(limit=200)
    tokens = await count_app_tokens(active_only=True)
    await render(source, ui.app_users_text(users, tokens=tokens, total=len(users)),
                 ui.app_users_keyboard())


async def show_app_tokens(source):
    rows = await list_app_tokens(limit=100)
    await render(source, ui.app_users_tokens_text(rows, total=len(rows)),
                 ui.keyboard([[ui.button("📱 App users", callback_data="appusers:refresh",
                                         style="primary")],
                              [ui.home_button()]]))


@bot.on_message(filters.command("app") & filters.private)
async def app_handler(client, message):
    await ensure_user(message.from_user)
    await show_app(message)


@bot.on_message(filters.command("gentoken") & filters.private)
async def gentoken_handler(client, message):
    """/gentoken hands the account its access token, generating it once."""
    user = message.from_user
    await ensure_user(user)
    row = await get_active_app_token(user.id)
    if row is None:
        await create_app_token(user.id, name=get_user_display_name(user, default=None),
                               username=getattr(user, "username", None))
    await show_app_token(message)


@bot.on_message(filters.command("revoketoken") & filters.private)
async def revoketoken_handler(client, message):
    uid = message.from_user.id
    row = await get_active_app_token(uid)
    if not row:
        await show_app_token(message)
        return
    await say(message, ui.app_token_revoke_confirm_text(),
              reply_markup=ui.keyboard([
                  [ui.button("🚫 Yes, revoke it", callback_data="app:revoke_yes",
                             style="danger")],
                  [ui.button("❌ Keep my token", callback_data="cmd_gentoken",
                             style="success")],
              ]))


def extract_app_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s]+", text or "")
    return match.group(0) if match else None


def extract_app_version(text: str) -> str | None:
    match = re.search(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", text or "")
    return match.group(1) if match else None


@bot.on_message(filters.command("apk") & filters.private)
async def apk_handler(client, message):
    """The owner hands the built APK over — with the deployment URL as caption."""
    uid = message.from_user.id
    if uid != OWNER_ID:
        await say(message, ui.apk_not_owner_text())
        return
    reply = getattr(message, "reply_to_message", None)
    document = getattr(message, "document", None) or getattr(reply, "document", None)
    text = " ".join(filter(None, [message.text or "", message.caption or ""]))
    url = extract_app_url(text)
    version = extract_app_version(text.replace(url or "", " "))
    if document is not None:
        name = (document.file_name or "").lower()
        mime = (document.mime_type or "").lower()
        if not (name.endswith(".apk") or mime == "application/vnd.android.package-archive"):
            await say(message, ui.apk_bad_file_text())
            return
        apk = await set_app_apk(file_id=document.file_id, file_name=document.file_name,
                                size=document.file_size, base_url=url, version=version,
                                uploaded_by=uid)
        config = await get_app_config()
        await say(message, ui.apk_saved_text(apk, base_url=config.get("base_url")))
        return
    if url:
        await set_app_base_url(url, version=version)
        config, apk = await app_config_snapshot()
        await say(message, ui.apk_saved_text(apk or {"file_name": None},
                                             base_url=config.get("base_url")))
        return
    config, apk = await app_config_snapshot()
    await say(message, ui.apk_status_text(apk, base_url=config.get("base_url")))


@bot.on_message(filters.command("appusers") & filters.private)
async def appusers_handler(client, message):
    if message.from_user.id != OWNER_ID and not await is_admin(message.from_user.id):
        await say(message, "🚫 Admin access only.")
        return
    await show_app_users(message)


@callback_action("cmd_app")
async def cb_app(client, query):
    await query.answer()
    await show_app(query)


@callback_action("cmd_gentoken")
async def cb_gentoken(client, query):
    await query.answer()
    await show_app_token(query)


@callback_action("app:howto")
async def cb_app_howto(client, query):
    await query.answer()
    await show_app_howto(query)


@callback_action("app:apk")
async def cb_app_apk(client, query):
    """Send the APK itself when the deployment URL is not published yet."""
    config, apk = await app_config_snapshot()
    if not apk.get("file_id"):
        await query.answer(ui_text(ui.app_missing_text()[:190]), show_alert=True)
        return
    await query.answer(ui_text("Sending the app…"))
    try:
        await bot.send_document(query.from_user.id, apk["file_id"],
                                file_name=apk.get("file_name") or "Vmore.apk",
                                caption=ui_text(ui.app_details_text(
                                    base_url=config.get("base_url"), apk=apk,
                                    token=(await get_active_app_token(query.from_user.id) or {}).get("token"))[:1000]))
    except Exception as exc:
        await query.answer(ui_text(f"⚠️ Could not send the file: {exc}")[:190],
                           show_alert=True)


@callback_action("app:newtoken")
async def cb_app_new_token(client, query):
    row = await get_active_app_token(query.from_user.id)
    if row:
        await query.answer()
        await render(query, ui.app_token_confirm_text(), ui.keyboard([
            [ui.button("🔄 Yes, regenerate", callback_data="app:newtoken_yes",
                       style="success")],
            [ui.button("❌ Cancel", callback_data="cancel_action", style="danger")],
        ]))
        return
    await query.answer()
    await _generate_app_token(query)


@callback_action("app:newtoken_yes")
async def cb_app_new_token_yes(client, query):
    await _generate_app_token(query)


async def _generate_app_token(source):
    user = source.from_user
    await ensure_user(user)
    row = await create_app_token(user.id, name=get_user_display_name(user, default=None),
                                 username=getattr(user, "username", None),
                                 regenerate=True)
    config, _apk = await app_config_snapshot()
    token = (row or {}).get("token") or "—"
    if is_callback(source):
        await render(source, ui.app_token_created_text(token, base_url=config.get("base_url")),
                     ui.app_token_keyboard(active=True))
    else:
        await say(source, ui.app_token_created_text(token, base_url=config.get("base_url")),
                  reply_markup=ui.app_token_keyboard(active=True))


@callback_action("app:revoke")
async def cb_app_revoke(client, query):
    await query.answer()
    await render(query, ui.app_token_revoke_confirm_text(), ui.keyboard([
        [ui.button("🚫 Yes, revoke it", callback_data="app:revoke_yes", style="danger")],
        [ui.button("❌ Cancel", callback_data="cancel_action", style="success")],
    ]))


@callback_action("app:revoke_yes")
async def cb_app_revoke_yes(client, query):
    uid = query.from_user.id
    row = await get_active_app_token(uid)
    if not row:
        await query.answer(ui_text("You have no active token."), show_alert=True)
        return
    await revoke_app_token(token=row["token"], reason="bot")
    await query.answer(ui_text("🚫 Token revoked."))
    await render(query, ui.app_token_revoked_text(),
                 ui.keyboard([[ui.button("🔑 Generate a new token", callback_data="cmd_gentoken",
                                         style="success")],
                              [ui.home_button()]]))


@callback_action("appusers:refresh")
async def cb_appusers_refresh(client, query):
    if query.from_user.id != OWNER_ID and not await is_admin(query.from_user.id):
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    await query.answer()
    await show_app_users(query)


@callback_action("appusers:tokens")
async def cb_appusers_tokens(client, query):
    if query.from_user.id != OWNER_ID and not await is_admin(query.from_user.id):
        await query.answer(ui_text("🚫 Admin access only."), show_alert=True)
        return
    await query.answer()
    await show_app_tokens(query)


#: Handlers defined after COMMAND_HANDLERS — registered here, exactly once.
COMMAND_HANDLERS.update({
    "superbroadcast": superbroadcast_handler,
    "app": app_handler,
    "gentoken": gentoken_handler,
    "revoketoken": revoketoken_handler,
    "appusers": appusers_handler,
    "apk": apk_handler,
})
ADMIN_INLINE_HANDLERS.update({"appusers": appusers_handler, "apk": apk_handler})
#: Recompute the channel split now that every handler exists (the app commands
#: and /superbroadcast are registered above, after the literals were built).
CHANNEL_BLOCKED_COMMANDS = frozenset(COMMAND_HANDLERS) - CHANNEL_ALLOWED_COMMANDS




web = Flask("")

@web.route("/")
def home():
    return "Bot is alive!"

@web.route("/health")
def health():
    """Render's health probe — deliberately tiny and never blocking."""
    return {"ok": True, "app": ui.APP_NAME, "api": appapi.API_ROOT}, 200


#: The Vmore app API lives on this very web service.
appapi.register(web, APP_BRIDGE)


def run_web():
    web.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


if __name__ == "__main__":
    os.makedirs("downloads", exist_ok=True)
    Thread(target=run_web, daemon=True).start()
    print("✅ Flask started")
    print(native_engine.startup_report())
    print(f"🗄 Dump mirror: TTL {int(DUMP_TTL_SECONDS)} s, "
          f"cooldown {DUMP_COOLDOWN_SECONDS:g} s, queue cap {int(DUMP_QUEUE_LIMIT)}")
    print(f"🎨 Inline button styles: {ui.style_support_label()}")
    turbo = engines.ENGINE_REGISTRY[ENGINE_CPP]
    print(f"🧠 Engines: Python Standard ⚙️ (single-stream) + "
          f"C++ Turbo {turbo.version_label} 🚀 "
          f"({turbo.workers} workers, zero-copy={turbo.zero_copy})")
    print(f"🧠 Controller starts in {ENGINE_CONTROLLER.mode_label}; the stored mode is "
          f"read from MongoDB on the first extraction (peak above "
          f"{ENGINE_PEAK_THRESHOLD} concurrent).")
    print(f"📊 Telemetry HUD: {'on' if ui.telemetry_enabled() else 'off'}")
    print("✅ Bot starting...")
    #: The command menu is published from the ``@bot.on_start()`` hook
    #: (``publish_menu_on_start``).  The mirror and the giveaway pump need the
    #: connected client too and are started from the first update (see
    #: ``touch_scheduler``): ``Client.run()`` takes no startup coroutine.
    bot.run()
    

# Keep these imported database APIs exposed for backward compatibility with
# existing integrations and the test harness, even where this module does not
# call them directly.
_COMPAT_EXPORTS = (FloodWait, FREE_PRIVATE_LINKS, PREMIUM_BENEFITS, clear_history,
                   delete_bookmark, remove_favorite, add_referral, test_connection,
                   total_users, total_downloads_count)
