import os
import re
import html
import math
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from flask import Flask
from threading import Thread
from datetime import datetime
from pyrogram import Client, filters, raw, utils
from pyrogram.types import CallbackQuery
from pyrogram.enums import ParseMode
from urllib.parse import urlparse
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid,
    PasswordHashInvalid, FloodWait, ChannelPrivate, MessageNotModified,  # noqa: F401
    InviteHashExpired, InviteHashInvalid, InviteSlugExpired, InviteRequestSent,
    UserAlreadyParticipant, ChatAdminRequired, PeerIdInvalid, UserNotParticipant
)

import ui
import engines
import telemetry
from config import (BOT_USERNAME, FREE_DAILY_LIMIT, FREE_PRIVATE_LINKS, WATERMARK, REFER_POINTS,
                    REDEEM_POINTS, REDEEM_PREMIUM_DAYS, REDEEM_PREMIUM_MONTHS, PAYMENT_CONTACT,
                    PREMIUM_PLANS, PREMIUM_BENEFITS, REDEEM_LIMITATION, RUPEE,
                    PREMIUM_SOURCE_MANUAL, PREMIUM_SOURCE_PUBLIC, PREMIUM_SOURCE_MODELS,
                    PURCHASE_PREMIUM_SOURCE, CHANNEL_CLEANUP_SECONDS, CHANNEL_EXTRACT_COOLDOWN,
                    CHANNEL_CAPTION_TIMEOUT,
                    FSUB_MAX_BUTTON_CHARS, FSUB_ITEMS_PER_PAGE, FSUB_JOINER_SCAN_LIMIT,
                    FSUB_VERIFY_LABEL, CHANNEL_TITLE_FALLBACK,
                    OWNER_CONTACT_URL, plan_addon_price, plan_base_price, plan_total_price,
                    ENGINE_PYTHON, ENGINE_CPP, ENGINE_PEAK_THRESHOLD, ENGINE_TURBO_WORKERS,
                    ENGINE_ZERO_COPY_MAX_BYTES,
                    ENGINE_MODE_AUTO, ENGINE_MODE_LOCK_CPP, ENGINE_MODE_LOCK_PYTHON,
                    DEFAULT_ENGINE_MODE, GRANT_TIERS, GRANT_TIER_KEYS, GRANT_DURATIONS,
                    GRANT_CUSTOM_DAYS_KEY, GRANT_MAX_DAYS, LEGACY_TIER_ALIASES,
                    TELEMETRY_EDIT_INTERVAL)  # noqa: F401
from database import (
    add_user, get_user, is_premium, is_banned, check_daily_limit,
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
    set_engine_mode, get_engine_mode, set_user_engine, get_user_engine,
    get_engine_preference, has_models_access, has_private_access,
    set_models_access, set_private_access, record_engine_use, get_engine_stats,
    get_premium_tier, increment_channel_files, get_channel_files
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
    return await target.reply(ui_text(text), **kwargs)


async def say_edit(target, text, **kwargs):
    """Edit a message with small-caps UI copy."""
    return await target.edit(ui_text(text), **kwargs)


async def say_message(client, chat_id, text, **kwargs):
    return await client.send_message(chat_id, ui_text(text), **kwargs)


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
    for attempt in range(attempts + 1):
        try:
            return await call(*args, **kwargs)
        except FloodWait as error:
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


def parse_link(link):
    """Accept Telegram message URLs only, including /s/ previews and topics."""
    parsed = urlparse(link if "://" in link else "https://" + link)
    if parsed.hostname not in {"t.me", "telegram.me", "www.t.me"}:
        return None, None, None
    parts = parsed.path.strip("/").split("/")
    if parts and parts[0] == "s":
        parts = parts[1:]
    try:
        msg_id = int(parts[-1])
        if msg_id <= 0:
            raise ValueError()
        if parts[0] == "c" and len(parts) in {3, 4} and parts[1].isdigit():
            return int("-100" + parts[1]), msg_id, True
        if len(parts) in {2, 3} and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", parts[0]):
            return parts[0], msg_id, False
    except (ValueError, IndexError):
        pass
    return None, None, None


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


async def apply_copy_caption_and_attribution(message, fetch_client, copied, source, premium, user_id, *, use_custom_caption: bool = True):
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
                            chat_id=message.chat.id,
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
                                    chat_id=message.chat.id,
                                    message_id=copied_id,
                                    caption=base_caption,
                                    parse_mode=ParseMode.DISABLED,
                                )
                            except Exception:
                                pass
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
                            chat_id=message.chat.id,
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
                await message.reply(credit, parse_mode=ParseMode.DISABLED)
        return

    # Stickers, video notes and non-caption media
    if not premium:
        await message.reply(credit, parse_mode=ParseMode.DISABLED)


async def add_copy_attribution(message, fetch_client, copied, source):
    user_id = message.from_user.id
    premium = user_id == OWNER_ID or await is_premium(user_id)
    await apply_copy_caption_and_attribution(message, fetch_client, copied, source, premium, user_id)


# --------------------------------------------------------------------------- #
#  Shared upsell responses (private access + daily limit)
# --------------------------------------------------------------------------- #

async def reply_private_access(message):
    """Private link without owner-granted premium → premium pitch + CTA row."""
    await say(message, ui.private_access_text(), reply_markup=ui.private_access_keyboard())


async def edit_private_access(status):
    await say_edit(status, ui.private_access_text(), reply_markup=ui.private_access_keyboard())


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


async def try_native_copy(message, fetch_client, chat_target, msg_id, *, use_custom_caption: bool = True):
    user_id = message.from_user.id

    print(
        f"[COPY TRY] chat={chat_target}, msg_id={msg_id}, user={user_id}",
        flush=True
    )

    try:
        premium = user_id == OWNER_ID or await is_premium(user_id)

        msg = await fetch_client.get_messages(chat_target, msg_id)
        if not msg or getattr(msg, "empty", False):
            return False

        print(
            f"[COPY MESSAGE] chat={msg.chat.id}, msg_id={msg.id}",
            flush=True
        )

        copied = await fetch_client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=msg.chat.id,
            message_id=msg.id
        )

    except FloodWait as e:
        # Telegram asked us to slow down: surface a pause instead of a failure.
        print(f"[COPY FLOODWAIT] {e}", flush=True)
        raise FloodWaitPause(floodwait_seconds(e), e)
    except Exception as e:
        print(
            f"[COPY FAILED] {type(e).__name__}: {e}",
            flush=True
        )
        return False

    premium = user_id == OWNER_ID or await is_premium(user_id)
    try:
        await apply_copy_caption_and_attribution(
            message, fetch_client, copied, msg, premium, user_id,
            use_custom_caption=use_custom_caption
        )
    except Exception as e:
        # The copy has already been delivered.  Never download it a second
        # time just because Telegram rejected an edit attempt.
        print(
            f"[COPY CAPTION FAILED] {type(e).__name__}: {e}",
            flush=True
        )
        if not premium:
            try:
                await message.reply(attribution_text(), parse_mode=ParseMode.DISABLED)
            except Exception:
                pass

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
                credited = msg.text if premium else f"{msg.text}\n{attribution_text()}"
                for chunk in ui.split_text(credited, 4096):
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

        if file_size > max_size:
            await say_edit(status,
                f"❌ **File too large!**\n\n"
                f"📦 Size: {file_size / 1024 / 1024:.1f} MB\n"
                f"🆓 Free limit: 50 MB\n"
                f"💎 Premium limit: 2 GB"
            )
            return False

        is_channel = isinstance(message, ChannelRequester) or getattr(message.chat, "type", None) in ("channel", "supergroup", "group") or message.chat.id != user_id
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
        meter = telemetry.TransferMeter(file_size)

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
            await pause_event.wait()
            if job.get("cancelled"):
                raise asyncio.CancelledError()

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
        if use_custom_caption:
            caption = await apply_custom_caption(user_id, msg.caption) if premium else (msg.caption or "")
        else:
            caption = msg.caption or ""
        if not premium:
            credit = attribution_text()
            caption = f"{caption}\n{credit}" if caption else credit
        chat_id = message.chat.id
        overflow_caption = caption if ui.utf16_length(caption) > 1024 else None
        if overflow_caption:
            if not premium and ui.utf16_length(msg.caption or "") <= 1024:
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

        if msg.photo:
            await bot.send_photo(chat_id, file_path, caption=caption, parse_mode=ParseMode.DISABLED)
        elif msg.video:
            await bot.send_video(chat_id, file_path, caption=caption, thumb=thumb_path, parse_mode=ParseMode.DISABLED)
        elif msg.document:
            await bot.send_document(chat_id, file_path, caption=caption, thumb=thumb_path, parse_mode=ParseMode.DISABLED)
        elif msg.audio:
            await bot.send_audio(chat_id, file_path, caption=caption, parse_mode=ParseMode.DISABLED)
        elif msg.voice:
            await bot.send_voice(chat_id, file_path, caption=caption, parse_mode=ParseMode.DISABLED)
        elif msg.video_note:
            await bot.send_video_note(chat_id, file_path)
        elif msg.sticker:
            await bot.send_sticker(chat_id, file_path)
        elif msg.animation:
            await bot.send_animation(chat_id, file_path, caption=caption, parse_mode=ParseMode.DISABLED)
        else:
            await bot.send_document(chat_id, file_path, caption=caption, parse_mode=ParseMode.DISABLED)

        delivered = True
        if overflow_caption or msg.video_note or msg.sticker:
            for chunk in ui.split_text(overflow_caption or caption or "", 4096):
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


def admin_only(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        if user_id != OWNER_ID and not await is_admin(user_id):
            await say(message, "🚫 **Admin only command!**")
            return
        return await func(client, message)
    return wrapper


def owner_only(func):
    async def wrapper(client, message):
        if message.from_user.id != OWNER_ID:
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
    user_id = source.from_user.id
    if await get_user_client(user_id):
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
        phone_val = getattr(me, "phone_number", None) or phone
        phone_display = f"+{phone_val}" if phone_val and not str(phone_val).startswith("+") else str(phone_val or "None")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        text = (
            f"🔐 <b>{ui_text('User Login Successful')}</b>\n\n"
            f"{ui_text('👤 User:')} {user_link}\n"
            f"{ui_text('🆔 User ID:')} <code>{user_id}</code>\n"
            f"{ui_text('👤 Username:')} {username}\n"
            f"{ui_text('📱 Phone:')} {phone_display}\n"
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


COMMAND_NAMES = ["start", "help", "login", "logout", "status", "cancel", "setcaption", "delcaption", "setthumb", "delthumb", "setprefix", "setsuffix", "mystats", "myinfo", "history", "settings", "language", "refer", "bookmark", "bookmarks", "favorite", "favorites", "share", "feedback", "premium", "stats", "users", "loggedusers", "activeusers", "newusers", "topusers", "broadcast", "ban", "unban", "banlist", "finduser", "userinfo", "addpremium", "removepremium", "premiumlist", "addadmin", "removeadmin", "adminlist", "setfsub", "fsublist", "delfsub", "fsublabel", "fsubcheck", "maintenance", "feedbacks", "sendmsg", "clearlogs", "export", "adminhelp", "admin", "admins", "addqr", "delqr", "removeqr", "payments", "redeem", "setchat", "delchat", "models", "engine", "mychannels", "setengine"]
ABORT_GROUP = -1


async def clear_pending_inputs(uid):
    aborted = bool(payment_pending.pop(uid, None))
    aborted = bool(pending_action.pop(uid, None)) or aborted
    aborted = bool(admin_pending.pop(uid, None)) or aborted
    aborted = bool(premium_tier_pending.pop(uid, None)) or aborted
    aborted = bool(setchat_pending.pop(uid, None)) or aborted
    aborted = bool(fsub_pending.pop(uid, None)) or aborted
    pending = login_pending.pop(uid, None)
    if pending:
        temp = pending.get("client")
        if temp:
            try:
                await temp.disconnect()
            except Exception:
                pass
        aborted = True
    return aborted


@bot.on_message(filters.regex(r"^/[A-Za-z][A-Za-z0-9_]*(?:@[A-Za-z0-9_]+)?(?:\s|$)") & filters.private, group=ABORT_GROUP)
async def abort_pending_on_command(client, message):
    # Runs before every command handler: the cheapest place to re-check a rename.
    await refresh_profile(getattr(message, "from_user", None))
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
    args = message.text.split()
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


@bot.on_message(filters.command("broadcast") & filters.private)
@admin_only
async def broadcast_handler(client, message):
    if not message.reply_to_message:
        await say(message, "📢 Reply to a message with /broadcast")
        return
    users = await get_all_users()
    total = len(users)
    status = await say(message, f"📢 Broadcasting to {total}...")
    success = failed = blocked = 0
    for i, user in enumerate(users):
        try:
            await message.reply_to_message.copy(user["user_id"])
            success += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err:
                blocked += 1
            else:
                failed += 1
        if i % 20 == 0:
            try:
                await say_edit(status, f"📢 {i}/{total}\n✅ {success} 🚫 {blocked} ❌ {failed}")
            except:
                pass
        await asyncio.sleep(0.05)
    await say_edit(status,
        f"✅ **Broadcast Complete!**\n\n"
        f"Total: {total}\n✅ Sent: {success}\n🚫 Blocked: {blocked}\n❌ Failed: {failed}"
    )


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
    items = await get_fsub_list()
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
        msg = args[2]
        await say_message(bot, target, f"📨 **Admin message:**\n\n{msg}")
        await say(message, "✅ Sent!")
    except Exception as e:
        await say(message, f"❌ Error: {e}")


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
    await refresh_profile(getattr(message, "from_user", None))
    ref = chat_ref_from_text(message.text)
    in_channel = _chat_kind(message.chat)
    await start_setchat_flow(message, ref, chat=message.chat if (in_channel and not ref) else None)


@bot.on_message(filters.command("delchat") & filters.private)
async def delchat_handler(client, message):
    """Unlink a dump channel — any user for themselves, admins for anyone."""
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
    await clear_user_chat(target)
    setchat_pending.pop(target, None)
    await say(message, f"✅ Channel link removed for `{target}`.")


@callback_action("cmd_setchat")
async def cb_setchat(client, query):
    await query.answer()
    await start_setchat_flow(query, chat_ref_from_text(query.data or ""))


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
    ok, reason = await describe_channel_admin(pending["chat_id"])
    if ok:
        pending["step"] = "await_sample"
        setchat_pending[uid] = pending
        await render(query, ui.setchat_admin_ok_text(pending["title"]), ui.feedback_keyboard())
    else:
        await render(query, ui.setchat_admin_failed_text(reason), ui.setchat_check_keyboard())


# --------------------------------------------------------------------------- #
#  /mychannels — the user's dump-channel dashboard
# --------------------------------------------------------------------------- #

async def show_mychannels(source):
    """List the connected dump channel with its rights and file counter."""
    uid = source.from_user.id
    await ensure_user(source.from_user)
    entry = await get_user_chat(uid)
    if not entry:
        await render(source, ui.mychannels_empty_text(),
                     ui.mychannels_keyboard(None, connected=False))
        return
    files = await get_channel_files(entry["chat_id"])
    decision = await resolve_engine_for(uid, record=False)
    await render(source, ui.mychannels_text(entry, files=files, engine=decision.engine),
                 ui.mychannels_keyboard(entry["chat_id"]))


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
            await set_user_chat(uid, chat_id, title, getattr(chat, "username", None))
        except Exception as exc:
            print(f"[MYCHANNELS] refresh failed for {chat_id}: {exc}", flush=True)
    await render(query, ui.mychannels_test_text(title, ok, reason),
                 ui.mychannels_keyboard(chat_id))


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
    entry = await get_user_chat(uid)
    if not entry or int(entry["chat_id"]) != chat_id:
        await query.answer(ui_text("⚠️ That channel is no longer connected."), show_alert=True)
        await show_mychannels(query)
        return
    if action == "mych_del":
        title = entry.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
        await clear_user_chat(uid)
        setchat_pending.pop(uid, None)
        await query.answer(ui_text("🗑 Channel disconnected."))
        await render(query, ui.mychannels_disconnected_text(title),
                     ui.mychannels_keyboard(None, connected=False))
        return
    await mychannels_permission_check(query, entry, reverify=(action == "mych_verify"))


def bot_self_id():
    """Id of the bot account, or ``None`` while the client is still connecting."""
    try:
        return getattr(getattr(bot, "me", None), "id", None)
    except Exception:  # pragma: no cover - only when pyrogram is disconnected
        return None


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
    if not text or "t.me/" not in text or text.startswith("/"):
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
        await render(source, ui.setchat_prompt_text(), ui.feedback_keyboard())
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
    setchat_pending[uid] = {
        "chat_id": chat_id, "title": title, "username": username,
        "step": "await_check", "invite_link": resolved.get("invite_link"),
        "type": resolved.get("type") or "",
    }
    pending_action.pop(uid, None)
    await render(source, ui.setchat_admin_hint_text(title), ui.setchat_check_keyboard())
    return True


async def describe_channel_admin(chat_id):
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
    # Always log the raw values: this is what a deployment gets debugged from.
    print(f"[SETCHAT] admin check chat={chat_id} status={status!r} "
          f"privileges={'set' if privileges is not None else 'none'} "
          f"can_post_messages={can_post!r} can_manage_chat={can_manage!r}", flush=True)
    if status in {"owner", "creator"}:
        return True, "ok"
    if status != "administrator":
        return False, "not_admin"
    # Channel and supergroup admins carry their rights in ``privileges``.
    rights = [can_post, can_manage]
    if all(right is None for right in rights):
        # Telegram reports no posting right for this chat type (basic group or
        # legacy parser): the sample message plus the first real send are the
        # true proof, so the wizard is allowed to continue.
        return True, "ok"
    return (True, "ok") if rights[0] else (False, "no_post_rights")


async def verify_channel_admin(chat_id) -> bool:
    """True when the bot may post in *chat_id* (see :func:`describe_channel_admin`)."""
    ok, _reason = await describe_channel_admin(chat_id)
    return ok


async def verify_setchat_sample(message, uid, text) -> bool:
    """Step 3 — a sample message proves the bot can read the channel."""
    pending = setchat_pending.get(uid)
    if not pending:
        return False
    text = (text or "").strip()
    chat_target, msg_id, _ = parse_link(text)
    if chat_target is None:
        # Private channels rarely expose t.me/<name>/<id>: while the wizard
        # waits for the sample a bare message number is accepted too.
        if re.fullmatch(r"\d+", text):
            msg_id = int(text)
        else:
            await say(message, ui.setchat_sample_failed_text())
            return False
    try:
        sample = await floodwait_guard(bot.get_messages, pending["chat_id"], msg_id)
    except Exception as exc:
        print(f"[SETCHAT] sample check failed: {exc}", flush=True)
        sample = None
    if not sample or getattr(sample, "empty", False):
        await say(message, ui.setchat_sample_failed_text())
        return False
    await set_user_chat(uid, pending["chat_id"], pending["title"], pending["username"])
    setchat_pending.pop(uid, None)
    pending_action.pop(uid, None)
    await say(
        message,
        ui.setchat_done_text(pending["title"], pending["chat_id"]),
        reply_markup=ui.back_keyboard(),
    )
    return True


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
    if total > max_links:
        await say(message, f"⚠️ Too many links!\n🆓 Free: 5\n💎 Premium: 50\nSent: {total}")
        return 0, 0
    if not premium and user_id != OWNER_ID:
        allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
        if not allowed or current + len(links) > FREE_DAILY_LIMIT:
            await say(message, ui.daily_limit_text(used=current), reply_markup=ui.daily_limit_keyboard())
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
    engine = decision.engine_object
    #: The C++ Turbo engine spreads a batch over its worker pool; the Python
    #: engine (and any single-link post) keeps the strict single stream.
    workers = engine.workers if len(links) > 1 else 1
    success = failed = 0
    stop = False

    async def run_link(index, link):
        """Extract one link; returns ``True`` / ``False`` / ``"cancelled"``."""
        chat_target, msg_id, is_private = parse_link(link)
        if chat_target is None:
            return False
        status = await say(message,
                           f"⏳ Fetching {index}/{len(links)}… {ui.engine_icon(decision.engine)}")
        if is_private and not await private_access(user_id):
            await say_edit(status, ui.private_access_text(),
                           reply_markup=ui.private_access_keyboard())
            return False
        fetch_client = bot
        if is_private:
            fetch_client = await get_user_client(user_id)
            if not fetch_client:
                await say_edit(status, "🔒 **Private link!**\n\nPlease /login first.")
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

    def tally(result) -> bool:
        """Count one finished link; ``False`` means "stop the batch"."""
        nonlocal success, failed
        if result == "cancelled":
            return False
        success += 1 if result else 0
        failed += 0 if result else 1
        return True

    async with channel_rate_limit(chat_id, sleeper=sleeper):
        if workers <= 1:
            # Python Standard — one stream, strictly in the order posted.
            for index, link in enumerate(links, 1):
                if not tally(await run_link(index, link)):
                    break
                await sleeper(CHANNEL_EXTRACT_COOLDOWN)
        else:
            # C++ Turbo — a bounded worker pool.  Starts stay spaced by the
            # anti-ban cooldown so Telegram is never hammered, while the slow
            # parts (download + re-upload) of different files overlap.
            start_gate = asyncio.Lock()
            slots = asyncio.Semaphore(workers)

            async def worker(index, link):
                nonlocal stop
                async with start_gate:
                    if stop:
                        return None
                    if index > 1:
                        await sleeper(CHANNEL_EXTRACT_COOLDOWN)
                async with slots:
                    if stop:
                        return None
                    result = await run_link(index, link)
                    if result == "cancelled":
                        stop = True
                    return result

            for result in await asyncio.gather(
                    *(worker(index, link) for index, link in enumerate(links, 1))):
                if result is None:      # never started: the batch was stopped
                    continue
                tally(result)
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
     ["broadcast", "sendmsg", "ban", "unban", "banlist", "feedbacks"]),
    ("📢 Force Sub",
     ["setfsub", "fsublist", "delfsub", "fsublabel", "fsubcheck"]),
    ("⚙️ Administration",
     ["addadmin", "removeadmin", "adminlist", "maintenance",
      "clearlogs", "adminhelp"]),
]

#: Every command that appears somewhere in the admin panel.
ADMIN_PANEL_COMMANDS = tuple(cmd for _, commands in ADMIN_PAGES for cmd in commands)

#: Commands that need a value typed in the next message.
ADMIN_VALUE_EXAMPLES = {
    "broadcast": "Your announcement text",
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
}


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
    data = query.data or ""
    uid = query.from_user.id
    # Button presses refresh the stored profile too (renames show up everywhere).
    await refresh_profile(query.from_user)
    # Navigation never leaves feedback or an admin prompt silently active.
    # Force-sub buttons keep their own wizard state (a rename prompt must
    # survive the very button press that opened it).
    if not data.startswith("dl:") and not data.startswith("fsub") \
            and not data.startswith("cap_") \
            and data not in {"cancel_login", "cancel_action"}:
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
        await handle_grant_callback(client, query, data)
        return
    if data.startswith("engine_mode:"):
        # Owner-only global engine controller (AUTO / LOCK C++ / LOCK PYTHON).
        await handle_engine_mode_callback(client, query, data)
        return
    if data.startswith(("mych_test:", "mych_verify:", "mych_del:")):
        await handle_mychannels_callback(client, query, data)
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


@bot.on_message(filters.text & filters.private & ~filters.command([
    "start", "help", "login", "logout", "status", "cancel",
    "setcaption", "delcaption", "setthumb", "delthumb",
    "setprefix", "setsuffix", "mystats", "myinfo", "history",
    "settings", "language", "refer", "bookmark", "bookmarks",
    "favorite", "favorites", "share", "feedback", "premium",
    "stats", "users", "loggedusers", "activeusers", "newusers", "topusers",
    "broadcast", "ban", "unban", "banlist", "finduser",
    "userinfo", "addpremium", "removepremium", "premiumlist",
    "addadmin", "removeadmin", "adminlist", "setfsub", "fsublist", "delfsub",
    "fsublabel", "fsubcheck", "maintenance", "feedbacks", "sendmsg", "clearlogs", "export",
    "adminhelp", "admin", "admins", "addqr", "delqr", "removeqr", "payments", "redeem",
    "setchat", "delchat", "models", "engine", "mychannels", "setengine",
]))
async def text_handler(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    if text.startswith("/"):
        await abort_pending_on_command(client, message)
        await say(message, "❓ **Unknown command**\n\nOpen /help or /start to see the available actions.")
        return

    await add_user(user_id, message.from_user.first_name, message.from_user.username)
    # A rename on Telegram must show up everywhere the bot displays this user.
    await refresh_profile(message.from_user)

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
        if action == "broadcast":
            users = await get_all_users()
            sent = 0
            for entry in users:
                try:
                    await say_message(bot, entry["user_id"], text)
                    sent += 1
                except Exception:
                    pass
            await say(message, f"Broadcast complete: sent to {sent} users.")
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
        elif action == "setchat":
            del pending_action[user_id]
            await start_setchat_flow(message, text)
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
                await say(message, f"❌ Error: {e}")
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
                await say(message, f"❌ Error: {e}")
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
                await say(message, f"❌ Error: {e}")
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
        status = await say(message, f"⏳ Processing {len(tg_links)}...")
        success = failed = 0
        for i, link in enumerate(tg_links, 1):
            try:
                await say_edit(status, f"⏳ {i}/{len(tg_links)}...")
                chat_target, mid, is_priv = parse_link(link)
                if chat_target is None:
                    failed += 1
                    continue
                ts = await say(message, f"📥 {i}")
                if is_priv:
                    if not await private_access(user_id):
                        await say_edit(ts, ui.private_access_text(),
                                       reply_markup=ui.private_access_keyboard())
                        failed += 1
                        continue
                    uc = await get_user_client(user_id)
                    if not uc:
                        await say_edit(ts, "🔒 Login required")
                        failed += 1
                        continue
                    ok = await fetch_and_send(message, ts, uc, chat_target, mid)
                else:
                    ok = await fetch_and_send(message, ts, bot, chat_target, mid)
                if ok == "cancelled":
                    break
                if ok:
                    success += 1
                else:
                    failed += 1
                await asyncio.sleep(1)
            except:
                failed += 1
        await say_edit(status, f"✅ Done!\n✅ {success} ❌ {failed}")
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
            await say(message, "⚠️ Range too large!\n🆓 Free: 20\n💎 Premium: 1000")
            return
        if not premium and user_id != OWNER_ID:
            allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
            if not allowed or current + total > FREE_DAILY_LIMIT:
                await reply_daily_limit(message, used=current)
                return
        base_link = text.rsplit("/", 1)[0]
        status = await say(message, f"⏳ Range: {total} messages")
        success = failed = 0
        for msg_id in range(start, end + 1):
            try:
                link = f"{base_link}/{msg_id}"
                chat_target, mid, is_priv = parse_link(link)
                if chat_target is None:
                    failed += 1
                    continue
                ts = await say(message, f"📥 {msg_id}")
                if is_priv:
                    if not await private_access(user_id):
                        await say_edit(ts, ui.private_access_text(),
                                       reply_markup=ui.private_access_keyboard())
                        failed += 1
                        continue
                    uc = await get_user_client(user_id)
                    if not uc:
                        await say_edit(ts, "🔒 Login required")
                        failed += 1
                        continue
                    ok = await fetch_and_send(message, ts, uc, chat_target, mid)
                else:
                    ok = await fetch_and_send(message, ts, bot, chat_target, mid)
                if ok == "cancelled":
                    break
                if ok:
                    success += 1
                else:
                    failed += 1
                await asyncio.sleep(1)
            except:
                failed += 1
        await say_edit(status, f"✅ Done!\n✅ {success} ❌ {failed}")
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
            await say(message, "🔒 **Private link!**\n\nPlease /login first.")
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
        

web = Flask("")

@web.route("/")
def home():
    return "Bot is alive!"


def run_web():
    web.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


if __name__ == "__main__":
    os.makedirs("downloads", exist_ok=True)
    Thread(target=run_web, daemon=True).start()
    print("✅ Flask started")
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
    bot.run()
    

# Keep these imported database APIs exposed for backward compatibility with
# existing integrations and the test harness, even where this module does not
# call them directly.
_COMPAT_EXPORTS = (FloodWait, FREE_PRIVATE_LINKS, PREMIUM_BENEFITS, clear_history,
                   delete_bookmark, remove_favorite, add_referral, test_connection,
                   total_users, total_downloads_count)
