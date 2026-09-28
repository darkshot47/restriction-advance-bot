import os
import re
import html
import math
import asyncio
from flask import Flask
from threading import Thread
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
from pyrogram.enums import ParseMode
from urllib.parse import urlparse
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid,
    PasswordHashInvalid, FloodWait, ChannelPrivate, MessageNotModified  # noqa: F401
)

import ui
from config import (FREE_DAILY_LIMIT, FREE_PRIVATE_LINKS, WATERMARK, REFER_POINTS,
                    REDEEM_POINTS, REDEEM_PREMIUM_DAYS, REDEEM_PREMIUM_MONTHS, PAYMENT_CONTACT,
                    PREMIUM_PLANS, PREMIUM_BENEFITS, REDEEM_LIMITATION, RUPEE)  # noqa: F401
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
    get_fsub_channel, delete_fsub, add_admin, remove_admin, is_admin,
    get_admins_list, clear_all_logs, get_bot_stats, add_premium,
    remove_premium, ban_user, unban_user, get_points, award_referral,
    redeem_points, set_qr, get_qr, delete_qr, add_payment, get_payments,
    reserve_daily, refund_daily
)  # noqa: F401

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "wantedkar99bot").lstrip("@")

bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_clients = {}
login_pending = {}
pending_action = {}
admin_pending = {}
active_downloads = {}
payment_pending = {}


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
    if user_id == OWNER_ID:
        return True
    row = await get_user(user_id) or {}
    return await is_premium(user_id) and row.get("premium_source") == "manual"


def joined_channel(member):
    status = getattr(member.status, "value", member.status)
    return status in {"member", "administrator", "owner", "creator"} or (
        status == "restricted" and bool(getattr(member, "is_member", False)))


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


async def apply_copy_caption_and_attribution(message, fetch_client, copied, source, premium, user_id):
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
        base_caption = await apply_custom_caption(user_id, source_caption)
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
        base_text = await apply_custom_caption(user_id, source_text)
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


async def check_access(message):
    user_id = message.from_user.id
    if await is_banned(user_id):
        await message.reply("🚫 You are banned from this bot!")
        return False
    if await get_maintenance() and user_id != OWNER_ID:
        await message.reply("🔧 **Bot is under maintenance!**\n\nPlease try again later.")
        return False
    fsub = await get_fsub_channel()
    if fsub and user_id != OWNER_ID:
        try:
            member = await bot.get_chat_member(fsub, user_id)
            if not joined_channel(member):
                raise Exception("Not member")
        except:
            await message.reply(
                ui.fsub_text(fsub),
                reply_markup=ui.fsub_keyboard(fsub)
            )
            return False
    return True

async def try_native_copy(message, fetch_client, chat_target, msg_id):
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

    except Exception as e:
        print(
            f"[COPY FAILED] {type(e).__name__}: {e}",
            flush=True
        )
        return False

    premium = user_id == OWNER_ID or await is_premium(user_id)
    try:
        await apply_copy_caption_and_attribution(message, fetch_client, copied, msg, premium, user_id)
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


async def fetch_and_send(message, status, fetch_client, chat_target, msg_id):
    """Enforce access and atomically reserve a free slot on every extraction path."""
    uid = message.from_user.id
    if not await check_access(message):
        return False
    if (isinstance(chat_target, int) or fetch_client is not bot) and not await private_access(uid):
        await status.edit(REDEEM_LIMITATION)
        return False
    await ensure_user(message.from_user)
    reserved = uid != OWNER_ID and not await is_premium(uid)
    reservation_date = datetime.now()
    if reserved and not await reserve_daily(uid, FREE_DAILY_LIMIT, reservation_date):
        await status.edit(f"⛔ **Daily limit reached**\n\n🆓 Free: {FREE_DAILY_LIMIT} public extractions per day.\n💎 Explore /premium or earn points with /refer.")
        return False
    result = False
    try:
        result = await _fetch_and_send(message, status, fetch_client, chat_target, msg_id)
        if result is True:
            await increment_daily(uid, count_daily=not reserved)
        return result
    finally:
        if reserved and result is not True:
            await refund_daily(uid, reservation_date)


async def _fetch_and_send(message, status, fetch_client, chat_target, msg_id):
    user_id = message.from_user.id
    file_path = None
    thumb_path = None
    delivered = False

    try:
        copied = await try_native_copy(
            message,
            fetch_client,
            chat_target,
            msg_id
        )

        if copied:
            delivered = True
            await status.delete()
            await add_download(user_id, f"msg_{msg_id}", "copied")
            return True

        msg = await fetch_client.get_messages(chat_target, msg_id)
        if not msg or msg.empty:
            await status.edit("❌ Message not found.")
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
                await status.edit("❌ No content available.")
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
            await status.edit(
                f"❌ **File too large!**\n\n"
                f"📦 Size: {file_size / 1024 / 1024:.1f} MB\n"
                f"🆓 Free limit: 50 MB\n"
                f"💎 Premium limit: 2 GB"
            )
            return False

        job_id = str(status.id)
        pause_event = asyncio.Event()
        pause_event.set()
        job = {
            "user_id": user_id,
            "event": pause_event,
            "paused": False,
            "task": asyncio.current_task(),
            "last_update": 0,
        }
        active_downloads[job_id] = job
        await status.edit("⬇️ Downloading...", reply_markup=ui.download_controls(job_id))

        async def download_progress(current, total):
            if job.get("cancelled"):
                raise asyncio.CancelledError()
            await pause_event.wait()
            if job.get("cancelled"):
                raise asyncio.CancelledError()

            now = asyncio.get_running_loop().time()
            if now - job["last_update"] < 2 and current < total:
                return
            job["last_update"] = now
            percent = int(current * 100 / total) if total else 0
            paused_label = " (paused)" if job["paused"] else ""
            try:
                await status.edit(
                    f"⬇️ Downloading... {percent}%{paused_label}",
                    reply_markup=ui.download_controls(job_id, job["paused"])
                )
            except Exception:
                pass

        file_path = await fetch_client.download_media(msg, progress=download_progress)
        if not file_path:
            await status.edit("❌ Download failed.", reply_markup=None)
            return False

        await status.edit("⬆️ Uploading...", reply_markup=None)
        premium = user_id == OWNER_ID or await is_premium(user_id)
        caption = await apply_custom_caption(user_id, msg.caption) if premium else (msg.caption or "")
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
        await status.delete()
        media_type = "photo" if msg.photo else "video" if msg.video else "document" if msg.document else "media"
        await add_download(user_id, f"msg_{msg_id}", media_type)
        return True

    except asyncio.CancelledError:
        try:
            await status.edit("⛔ Download stopped.", reply_markup=None)
        except Exception:
            pass
        return True if delivered else "cancelled"
    except Exception as e:
        try:
            await status.edit(f"❌ Error: {e}", reply_markup=None)
        except Exception:
            pass
        # Delivery counts even if status cleanup/history persistence failed.
        # Otherwise deleting the progress message could bypass the free quota.
        return delivered
    finally:
        if "job_id" in locals():
            active_downloads.pop(job_id, None)
        for path in [file_path, thumb_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass


def admin_only(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        if user_id != OWNER_ID and not await is_admin(user_id):
            await message.reply("🚫 **Admin only command!**")
            return
        return await func(client, message)
    return wrapper


def owner_only(func):
    async def wrapper(client, message):
        if message.from_user.id != OWNER_ID:
            await message.reply("🚫 **Owner only command!**")
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
    """Show *text* — reply to a command, edit the message a button came from."""
    if is_callback(source):
        try:
            return await source.message.edit_text(text, reply_markup=keyboard, **kwargs)
        except MessageNotModified:
            return source.message
        except Exception:
            # Media messages cannot be edited into text messages.
            return await source.message.reply(text, reply_markup=keyboard, **kwargs)
    return await source.reply(text, reply_markup=keyboard, **kwargs)


async def ensure_user(user):
    """Return the user document, creating it when it is missing."""
    row = await get_user(user.id)
    if row:
        return row
    await add_user(user.id, user.first_name, user.username)
    row = await get_user(user.id)
    return row or {
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
    premium = await is_premium(user.id)
    show_admin = user.id == OWNER_ID or await is_admin(user.id)
    await render(source, ui.start_text(user.first_name, premium), ui.start_keyboard(show_admin))


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


async def show_refer(source):
    user = await ensure_user(source.from_user)
    link = f"https://t.me/{BOT_USERNAME}?start={source.from_user.id}"
    points = await get_points(source.from_user.id)
    text = (f"🎁 **REFERRALS & REWARDS**\n\n👥 Referrals: {user.get('referral_count', 0)}\n"
            f"⭐ **Points: {points} / {REDEEM_POINTS}**\n"
            f"🎉 Each new friend earns you **{REFER_POINTS} points**.\n"
            f"💎 Redeem **{REDEEM_POINTS} points** for **{REDEEM_PREMIUM_MONTHS} month** of public-only premium.\n"
            "Only new users joining through your link count, once each.\n"
            f"Progress: {'█' * min(10, points * 10 // REDEEM_POINTS)}{'░' * max(0, 10 - min(10, points * 10 // REDEEM_POINTS))}\n"
            f"Your link: {link}\n\n{REDEEM_LIMITATION}")
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


async def save_feedback(user_or_id, text):
    """Store feedback and forward a copy to the owner."""
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
            notification = f"💬 Feedback from {user_link}:\n\n{escaped_feedback}"
            await bot.send_message(OWNER_ID, notification, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"[FEEDBACK FORWARD FAILED] {e}", flush=True)


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
            f"🔐 <b>User Login Successful</b>\n\n"
            f"👤 User: {user_link}\n"
            f"🆔 User ID: <code>{user_id}</code>\n"
            f"👤 Username: {username}\n"
            f"📱 Phone: {phone_display}\n"
            f"⏰ Time: {now_str}"
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
    await query.answer("❌ Menu closed")


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
        await query.answer("Admin only.", show_alert=True)
        try:
            await query.message.edit_text("🚫 Admin access only.", reply_markup=ui.back_keyboard())
        except Exception:
            pass
        return
    await query.message.edit_text(admin_panel_text(), reply_markup=admin_panel_keyboard())
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
    await query.answer(f"🔔 Notifications {'ON' if state else 'OFF'}")
    await render(
        query,
        ui.settings_text(),
        ui.settings_keyboard(state, bool(user.get("silent_mode", False))),
    )


@callback_action("toggle_silent")
async def cb_toggle_silent(client, query):
    state = await toggle_silent(query.from_user.id)
    user = await ensure_user(query.from_user)
    await query.answer(f"🌙 Silent mode {'ON' if state else 'OFF'}")
    await render(
        query,
        ui.settings_text(),
        ui.settings_keyboard(bool(user.get("notifications", True)), state),
    )


@callback_action("reset_settings")
async def cb_reset_settings(client, query):
    await reset_settings(query.from_user.id)
    await query.answer("🔄 All settings were reset")
    await show_settings(query)


@callback_action("lang_en")
async def cb_lang_en(client, query):
    await query.answer("✅ Language set to English")
    await set_language(query.from_user.id, "en")
    await render(query, ui.language_text("en"), ui.language_keyboard("en"))


@callback_action("lang_hi")
async def cb_lang_hi(client, query):
    await query.answer("✅ Preference saved. Bot messages remain in English.")
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
    await query.answer("❌ Login cancelled")
    await render(query, ui.login_cancelled_text(), ui.back_keyboard())


@callback_action("cancel_action")
async def cb_cancel_action(client, query):
    await clear_pending_inputs(query.from_user.id)
    await query.answer("❌ Cancelled")
    await render(query, ui.action_cancelled_text(), ui.back_keyboard())


@callback_action("check_fsub")
async def cb_check_fsub(client, query):
    fsub = await get_fsub_channel()
    if not fsub:
        await query.answer("✅ No channel to verify — send me a link!", show_alert=True)
        return
    try:
        member = await bot.get_chat_member(fsub, query.from_user.id)
        joined = joined_channel(member)
    except Exception:
        joined = False
    if joined:
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer("✅ Verified! Send me a link now.")
    else:
        await query.answer("❌ You have not joined the channel yet!", show_alert=True)


COMMAND_NAMES = ["start", "help", "login", "logout", "status", "cancel", "setcaption", "delcaption", "setthumb", "delthumb", "setprefix", "setsuffix", "mystats", "myinfo", "history", "settings", "language", "refer", "bookmark", "bookmarks", "favorite", "favorites", "share", "feedback", "premium", "stats", "users", "loggedusers", "activeusers", "newusers", "topusers", "broadcast", "ban", "unban", "banlist", "finduser", "userinfo", "addpremium", "removepremium", "premiumlist", "addadmin", "removeadmin", "adminlist", "setfsub", "delfsub", "maintenance", "feedbacks", "sendmsg", "clearlogs", "export", "adminhelp", "admin", "admins", "addqr", "delqr", "removeqr", "payments", "redeem"]
ABORT_GROUP = -1


async def clear_pending_inputs(uid):
    aborted = bool(payment_pending.pop(uid, None))
    aborted = bool(pending_action.pop(uid, None)) or aborted
    aborted = bool(admin_pending.pop(uid, None)) or aborted
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
    if message.text.split()[0].split("@")[0].lower() == "/cancel":
        return  # /cancel provides its own single confirmation.
    if await clear_pending_inputs(message.from_user.id):
        await message.reply("ℹ️ **Previous input cancelled.** Running your command.")


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user = message.from_user
    is_new = await add_user(user.id, user.first_name, user.username)
    args = message.text.split()
    if len(args) > 1 and is_new:
        try:
            ref_id = int(args[1])
            if ref_id != user.id:
                if await award_referral(ref_id, user.id, REFER_POINTS):
                    try:
                        await bot.send_message(ref_id, f"🎉 **New referral!**\n\n⭐ +{REFER_POINTS} points added. Open /refer to see your progress.")
                    except Exception:
                        pass
        except:
            pass
    premium = await is_premium(user.id)
    show_admin = user.id == OWNER_ID or await is_admin(user.id)
    await render(message, ui.start_text(user.first_name, premium), ui.start_keyboard(show_admin))


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
            await message.reply(
                f"✅ **LOGGED IN**\n\n"
                f"👤 {me.first_name}\n"
                f"📱 +{me.phone_number}\n"
                f"🆔 @{me.username or 'None'}"
            )
        except:
            await message.reply("⚠️ Session error. /logout and /login again.")
    else:
        await message.reply("❌ Not logged in. Use /login")


@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client, message):
    if await clear_pending_inputs(message.from_user.id):
        await message.reply(ui.action_cancelled_text(), reply_markup=ui.back_keyboard())
    else:
        await message.reply(ui.nothing_to_cancel_text(), reply_markup=ui.back_keyboard())


@bot.on_message(filters.command("setcaption") & filters.private)
async def setcaption_handler(client, message):
    user_id = message.from_user.id
    if len(message.text.split()) < 2:
        pending_action[user_id] = "caption"
        await message.reply("✏️ **Send your custom caption:**\n\nSend /cancel to abort.")
        return
    caption = message.text.split(None, 1)[1]
    await set_caption(user_id, caption)
    await message.reply(f"✅ Caption set!\n\n`{caption}`")


@bot.on_message(filters.command("delcaption") & filters.private)
async def delcaption_handler(client, message):
    await del_caption(message.from_user.id)
    await message.reply("✅ Caption removed!")


@bot.on_message(filters.command("setthumb") & filters.private)
async def setthumb_handler(client, message):
    pending_action[message.from_user.id] = "thumbnail"
    await message.reply("🖼️ **Send a photo for thumbnail**\n\nSend /cancel to abort.")


@bot.on_message(filters.command("delthumb") & filters.private)
async def delthumb_handler(client, message):
    await del_thumbnail(message.from_user.id)
    await message.reply("✅ Thumbnail removed!")


@bot.on_message(filters.command("setprefix") & filters.private)
async def setprefix_handler(client, message):
    if len(message.text.split()) < 2:
        await message.reply("Usage: `/setprefix Your Text`")
        return
    prefix = message.text.split(None, 1)[1]
    await set_prefix(message.from_user.id, prefix)
    await message.reply(f"✅ Prefix set: `{prefix}`")


@bot.on_message(filters.command("setsuffix") & filters.private)
async def setsuffix_handler(client, message):
    if len(message.text.split()) < 2:
        await message.reply("Usage: `/setsuffix Your Text`")
        return
    suffix = message.text.split(None, 1)[1]
    await set_suffix(message.from_user.id, suffix)
    await message.reply(f"✅ Suffix set: `{suffix}`")


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
        await message.reply("📜 No history!")
        return
    text = "📜 **LAST 10 DOWNLOADS**\n\n"
    for i, item in enumerate(history, 1):
        date = item.get("date", datetime.now()).strftime("%d/%m %H:%M")
        text += f"{i}. {item.get('type')} - {date}\n"
    await message.reply(text)


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
        await message.reply("Usage: `/bookmark https://t.me/...`")
        return
    link = message.text.split(None, 1)[1]
    await add_bookmark(message.from_user.id, link)
    await message.reply(f"✅ Bookmarked!\n`{link}`")


@bot.on_message(filters.command("bookmarks") & filters.private)
async def bookmarks_handler(client, message):
    bookmarks = await get_bookmarks(message.from_user.id)
    if not bookmarks:
        await message.reply("🔖 No bookmarks!")
        return
    text = "🔖 **BOOKMARKS**\n\n"
    for i, item in enumerate(bookmarks[:20], 1):
        text += f"{i}. `{item.get('link')}`\n"
    await message.reply(text)


@bot.on_message(filters.command("favorite") & filters.private)
async def favorite_handler(client, message):
    if len(message.text.split()) < 2:
        await message.reply("Usage: `/favorite @channelname`")
        return
    channel = message.text.split()[1]
    await add_favorite(message.from_user.id, channel)
    await message.reply(f"⭐ Added: {channel}")


@bot.on_message(filters.command("favorites") & filters.private)
async def favorites_handler(client, message):
    favs = await get_favorites(message.from_user.id)
    if not favs:
        await message.reply("⭐ No favorites!")
        return
    text = "⭐ **FAVORITES**\n\n"
    for i, ch in enumerate(favs, 1):
        text += f"{i}. {ch}\n"
    await message.reply(text)


@bot.on_message(filters.command("share") & filters.private)
async def share_handler(client, message):
    await message.reply(f"📤 **Share this bot!**\n\n🤖 @{BOT_USERNAME}")


@bot.on_message(filters.command("feedback") & filters.private)
async def feedback_handler(client, message):
    text = (message.text or "").split()
    if len(text) < 2:
        await start_feedback(message)
        return
    await save_feedback(message.from_user, message.text.split(None, 1)[1])
    await message.reply(ui.feedback_saved_text(), reply_markup=ui.back_keyboard())


@bot.on_message(filters.command("premium") & filters.private)
async def premium_handler(client, message):
    await show_premium(message)

@bot.on_message(filters.command("stats") & filters.private)
@admin_only
async def stats_handler(client, message):
    stats = await get_bot_stats()
    total_bm = await total_bookmarks_count()
    await message.reply(
        f"📊 **BOT STATISTICS**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **Users:**\n"
        f"├ Total: `{stats['total']}`\n"
        f"├ Active Today: `{stats['active_today']}`\n"
        f"├ New Today: `{stats['new_today']}`\n"
        f"├ Premium: `{stats['premium']}`\n"
        f"├ Banned: `{stats['banned']}`\n"
        f"└ Admins: `{stats['admins']}`\n\n"
        f"📥 Downloads: `{stats['total_downloads']}`\n"
        f"🔖 Bookmarks: `{total_bm}`"
    )


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
    await message.reply(f"🟢 **Active Today:** `{count}`")


@bot.on_message(filters.command("newusers") & filters.private)
@admin_only
async def new_users_handler(client, message):
    count = await get_new_users_today()
    await message.reply(f"🆕 **New Today:** `{count}`")


@bot.on_message(filters.command("topusers") & filters.private)
@admin_only
async def top_users_handler(client, message):
    users = await get_top_users(10)
    if not users:
        await message.reply("No data.")
        return
    text = "🏆 **TOP 10 USERS**\n\n"
    for i, u in enumerate(users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
        text += f"{medal} `{u['user_id']}` - {u.get('name')} - **{u.get('downloads', 0)}**\n"
    await message.reply(text)


@bot.on_message(filters.command("broadcast") & filters.private)
@admin_only
async def broadcast_handler(client, message):
    if not message.reply_to_message:
        await message.reply("📢 Reply to a message with /broadcast")
        return
    users = await get_all_users()
    total = len(users)
    status = await message.reply(f"📢 Broadcasting to {total}...")
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
                await status.edit(f"📢 {i}/{total}\n✅ {success} 🚫 {blocked} ❌ {failed}")
            except:
                pass
        await asyncio.sleep(0.05)
    await status.edit(
        f"✅ **Broadcast Complete!**\n\n"
        f"Total: {total}\n✅ Sent: {success}\n🚫 Blocked: {blocked}\n❌ Failed: {failed}"
    )


@bot.on_message(filters.command("ban") & filters.private)
@admin_only
async def ban_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/ban USER_ID`")
        return
    try:
        target = int(args[1])
        await ban_user(target)
        await message.reply(f"🚫 `{target}` banned!")
        try:
            await bot.send_message(target, "🚫 You are banned!")
        except:
            pass
    except:
        await message.reply("❌ Invalid ID")


@bot.on_message(filters.command("unban") & filters.private)
@admin_only
async def unban_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/unban USER_ID`")
        return
    try:
        target = int(args[1])
        await unban_user(target)
        await message.reply(f"✅ `{target}` unbanned!")
        try:
            await bot.send_message(target, "✅ You are unbanned!")
        except:
            pass
    except:
        await message.reply("❌ Invalid ID")


@bot.on_message(filters.command("banlist") & filters.private)
@admin_only
async def banlist_handler(client, message):
    banned = await get_banned_users_list()
    if not banned:
        await message.reply("✅ No banned users.")
        return
    text = f"🚫 **BANNED ({len(banned)})**\n\n"
    for i, u in enumerate(banned[:30], 1):
        text += f"{i}. `{u['user_id']}` - {u.get('name')}\n"
    await message.reply(text)


@bot.on_message(filters.command("finduser") & filters.private)
@admin_only
async def finduser_handler(client, message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply("Usage: `/finduser query`")
        return
    results = await search_user(args[1])
    if not results:
        await message.reply("❌ Not found.")
        return
    text = f"🔍 **Found {len(results)}:**\n\n"
    for u in results[:10]:
        text += f"👤 {u.get('name')}\n🆔 `{u['user_id']}`\n📥 {u.get('downloads', 0)}\n━━━━━━━━━━\n"
    await message.reply(text)


@bot.on_message(filters.command("userinfo") & filters.private)
@admin_only
async def userinfo_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/userinfo USER_ID`")
        return
    try:
        target = int(args[1])
        user = await get_user(target)
        if not user:
            await message.reply("❌ Not found.")
            return
        premium = await is_premium(target)
        joined = user.get("joined_date", datetime.now()).strftime("%d %b %Y")
        await message.reply(
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
        await message.reply("❌ Invalid ID")


@bot.on_message(filters.command("addpremium") & filters.private)
@owner_only
async def addpremium_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/addpremium USER_ID [days]`")
        return
    try:
        target = int(args[1])
        days = int(args[2]) if len(args) > 2 else 30
        if days <= 0 or days > 36500:
            await message.reply("❌ Choose a duration between 1 and 36,500 days.")
            return
        if not await get_user(target):
            await message.reply("❌ Ask this user to /start the bot first.")
            return
        await add_premium(target, days)
        await message.reply(f"💎 **Premium activated**\n\n👤 User: `{target}`\n📅 Duration: **{days} days**\n🔐 Access: **Public + private** (owner-granted).")
        try:
            await bot.send_message(target, f"🎉 **PREMIUM ACTIVATED!**\n\n📅 Your plan is active for **{days} days**.\n✅ Unlimited public extractions\n✅ No extraction watermark\n🔐 Private links are now enabled. Use /login with an account authorized to view the channel.\n\nOpen /premium to see your status.")
        except:
            pass
    except:
        await message.reply("❌ Invalid")


@bot.on_message(filters.command("removepremium") & filters.private)
@admin_only
async def removepremium_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/removepremium USER_ID`")
        return
    try:
        target = int(args[1])
        await remove_premium(target)
        await message.reply(f"✅ Premium removed from `{target}`")
    except:
        await message.reply("❌ Invalid ID")


@bot.on_message(filters.command("premiumlist") & filters.private)
@admin_only
async def premiumlist_handler(client, message):
    premium = await get_premium_users_list()
    if not premium:
        await message.reply("No premium users.")
        return
    text = f"💎 **PREMIUM ({len(premium)})**\n\n"
    for i, u in enumerate(premium[:30], 1):
        exp = u.get("premium_expiry")
        exp_str = exp.strftime("%d/%m/%Y") if exp else "N/A"
        text += f"{i}. `{u['user_id']}` - {exp_str}\n"
    await message.reply(text)


@bot.on_message(filters.command("addadmin") & filters.private)
@owner_only
async def addadmin_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/addadmin USER_ID`")
        return
    try:
        target = int(args[1])
        await add_admin(target)
        await message.reply(f"👑 `{target}` is now admin!")
        try:
            await bot.send_message(target, "👑 You are now a bot admin!")
        except:
            pass
    except:
        await message.reply("❌ Invalid")


@bot.on_message(filters.command("removeadmin") & filters.private)
@owner_only
async def removeadmin_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/removeadmin USER_ID`")
        return
    try:
        target = int(args[1])
        await remove_admin(target)
        await message.reply(f"✅ Admin removed from `{target}`")
    except:
        await message.reply("❌ Invalid")


@bot.on_message(filters.command("adminlist") & filters.private)
@admin_only
async def adminlist_handler(client, message):
    admins = await get_admins_list()
    text = f"👑 **ADMINS**\n\n👑 Owner: `{OWNER_ID}`\n\n"
    if admins:
        text += f"**Admins ({len(admins)}):**\n"
        for i, u in enumerate(admins, 1):
            text += f"{i}. `{u['user_id']}` - {u.get('name')}\n"
    await message.reply(text)


@bot.on_message(filters.command("setfsub") & filters.private)
@owner_only
async def setfsub_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/setfsub @channelname`")
        return
    channel = args[1]
    if not channel.startswith("@"):
        channel = "@" + channel
    await set_fsub_channel(channel)
    await message.reply(f"✅ Force sub: {channel}")


@bot.on_message(filters.command("delfsub") & filters.private)
@owner_only
async def delfsub_handler(client, message):
    await delete_fsub()
    await message.reply("✅ Force sub removed!")


@bot.on_message(filters.command("maintenance") & filters.private)
@owner_only
async def maintenance_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        current = await get_maintenance()
        status = "ON 🔧" if current else "OFF ✅"
        await message.reply(f"🔧 Maintenance: {status}\n\nUse: `/maintenance on` or `off`")
        return
    mode = args[1].lower()
    if mode == "on":
        await set_maintenance(True)
        await message.reply("🔧 Maintenance: **ON**")
    elif mode == "off":
        await set_maintenance(False)
        await message.reply("✅ Maintenance: **OFF**")
    else:
        await message.reply("Use: on/off")


@bot.on_message(filters.command("feedbacks") & filters.private)
@admin_only
async def feedbacks_handler(client, message):
    feedbacks = await get_all_feedback()
    if not feedbacks:
        await message.reply("No feedback.")
        return
    text = f"💬 **FEEDBACKS ({len(feedbacks)})**\n\n"
    for i, fb in enumerate(feedbacks[:20], 1):
        date = fb.get("date", datetime.now()).strftime("%d/%m %H:%M")
        text += f"**{i}. `{fb['user_id']}`** ({date})\n{fb['message'][:100]}\n\n"
    await message.reply(text)


@bot.on_message(filters.command("sendmsg") & filters.private)
@admin_only
async def sendmsg_handler(client, message):
    args = message.text.split(None, 2)
    if len(args) < 3:
        await message.reply("Usage: `/sendmsg USER_ID message`")
        return
    try:
        target = int(args[1])
        msg = args[2]
        await bot.send_message(target, f"📨 **Admin message:**\n\n{msg}")
        await message.reply("✅ Sent!")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@bot.on_message(filters.command("clearlogs") & filters.private)
@owner_only
async def clearlogs_handler(client, message):
    await clear_all_logs()
    await message.reply("🗑 Logs cleared!")


@bot.on_message(filters.command("export") & filters.private)
@admin_only
async def export_handler(client, message):
    users = await get_all_users()
    if not users:
        await message.reply("No users.")
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
    await message.reply_document(filename, caption=f"📊 Users ({len(users)})")
    try:
        os.remove(filename)
    except:
        pass


@bot.on_message(filters.command("adminhelp") & filters.private)
@admin_only
async def adminhelp_handler(client, message):
    await message.reply(
        "👑 **ADMIN COMMANDS**\n\n"
        "**📊 Stats:**\n/stats /users /activeusers /newusers /topusers\n\n"
        "**📢 Broadcast:**\n/broadcast /sendmsg\n\n"
        "**🚫 Users:**\n/ban /unban /banlist /finduser /userinfo\n\n"
        "**💎 Premium:**\n/addpremium /removepremium /premiumlist\n\n"
        "**👑 Admins (Owner):**\n/addadmin /removeadmin /adminlist\n\n"
        "**⚙️ Config (Owner):**\n/setfsub /delfsub /maintenance\n\n"
        "**📝 System:**\n/feedbacks /clearlogs /export"
    )


@bot.on_message(filters.command("addqr") & filters.private)
@owner_only
async def addqr_handler(client, message):
    replied = getattr(message, "reply_to_message", None)
    photo = getattr(replied, "photo", None)
    if photo:
        await set_qr(photo.file_id)
        await message.reply("✅ **Payment QR saved!**\n\nIt will appear after users select a premium plan.")
        return
    pending_action[message.from_user.id] = "qr_upload"
    await message.reply("🖼 **SET PAYMENT QR**\n\nSend the payment QR image as a photo. You can also reply to a QR photo with /addqr.\n\nUse /cancel to exit.", reply_markup=ui.feedback_keyboard())


@bot.on_message(filters.command(["delqr", "removeqr"]) & filters.private)
@owner_only
async def delqr_handler(client, message):
    await delete_qr()
    await message.reply("✅ Payment QR removed.")


@bot.on_message(filters.command("payments") & filters.private)
@admin_only
async def payments_handler(client, message):
    rows = await get_payments()
    await message.reply(f"💳 **PAYMENT REVIEWS**\n\nTotal proofs: **{len(rows)}**. Showing the latest 20.")
    for row in rows[:20]:
        note = row.get("note")
        plan = PREMIUM_PLANS.get(note.get("plan"), {}) if isinstance(note, dict) else {}
        caption = (f"👤 User: `{row['user_id']}`\n📦 {plan.get('title', 'Legacy proof')}\n"
                   f"💰 {RUPEE}{plan.get('price', '—')}\n📅 {row.get('date', '—')}\n"
                   "🔎 Verify payment before granting premium.")
        if isinstance(note, dict) or note == "photo":
            try:
                await bot.send_photo(message.chat.id, row["proof"], caption=caption)
            except Exception:
                await message.reply(caption + "\n⚠️ Screenshot unavailable.")
        else:
            await message.reply(caption + "\n" + str(row.get("proof", "")))


@bot.on_message(filters.command("redeem") & filters.private)
async def redeem_handler(client, message):
    uid = message.from_user.id
    if await redeem_points(uid, REDEEM_POINTS, months=REDEEM_PREMIUM_MONTHS):
        await message.reply(f"✅ Redeemed {REDEEM_POINTS} points for {REDEEM_PREMIUM_MONTHS} month of public-only premium.\n\n{REDEEM_LIMITATION}")
    else:
        await message.reply(f"🔒 You need {REDEEM_POINTS} points. Active owner-granted premium cannot be replaced by points premium.")


@bot.on_message(filters.command(["admin", "admins"]) & filters.private)
@admin_only
async def admin_handler(client, message):
    await message.reply(admin_panel_text(), reply_markup=admin_panel_keyboard())


async def submit_payment_proof(message):
    uid = message.from_user.id
    order = payment_pending.get(uid)
    if not order:
        pending_action.pop(uid, None)
        await message.reply("⚠️ Checkout expired. Open /premium and choose your plan again.")
        return
    plan = PREMIUM_PLANS[order["plan"]]
    # Persist proof + selected plan before attempting delivery to Telegram.
    saved = await add_payment(uid, message.photo.file_id, {
        "plan": order["plan"], "price": plan["price"], "days": plan["days"],
        "message_id": message.id, "checkout": order["token"],
    })
    pending_action.pop(uid, None)
    payment_pending.pop(uid, None)
    if saved is None:
        await message.reply("ℹ️ **This payment proof is already submitted for review.**")
        return
    delivered = False
    caption = (f"💳 **PAYMENT REVIEW**\n\n👤 User: `{uid}`\n"
               f"📦 Plan: **{plan['title']}** • **{RUPEE}{plan['price']}**\n"
               f"🔎 Verify this screenshot against your actual payment records.\n"
               f"👑 Owner approval: `/addpremium {uid} {plan['days']}`")
    # A bot cannot initiate a private chat. OWNER_ID should belong to
    # @XyrDeveloper, who must /start this bot; the username is a best-effort copy.
    for recipient in dict.fromkeys([OWNER_ID, PAYMENT_CONTACT]):
        if not recipient:
            continue
        try:
            await bot.send_photo(recipient, message.photo.file_id, caption=caption)
            delivered = True
        except Exception:
            continue
    if delivered:
        text = (f"✅ **Payment proof submitted**\n\n📦 {plan['title']} • {RUPEE}{plan['price']}\n"
                f"⏳ Awaiting verification by @{PAYMENT_CONTACT}. This is not an automatic payment confirmation.\n"
                "💎 The owner will activate your premium after checking payment.")
    else:
        text = (f"⚠️ **Proof saved, delivery unavailable**\n\nPlease send your screenshot directly to @{PAYMENT_CONTACT}. "
                "Your proof remains available to the owner in /payments.")
    await message.reply(text, reply_markup=ui.back_keyboard())


@bot.on_message(filters.photo & filters.private)
async def photo_handler(client, message):
    user_id = message.from_user.id
    if pending_action.get(user_id) == "payment_proof":
        await submit_payment_proof(message)
        return
    if pending_action.get(user_id) == "qr_upload":
        if user_id != OWNER_ID:
            await message.reply("Only the owner can upload the payment QR.")
            return
        await set_qr(message.photo.file_id)
        del pending_action[user_id]
        await message.reply("✅ **Payment QR saved.**\n\nUsers will see this image after selecting a plan in /premium.")
        return
    if pending_action.get(user_id) == "thumbnail":
        await set_thumbnail(user_id, message.photo.file_id)
        del pending_action[user_id]
        await message.reply("✅ Thumbnail saved!")


async def handle_download_controls(query):
    """Pause / resume / stop an active download."""
    data = query.data
    user_id = query.from_user.id
    try:
        _, action, job_id = data.split(":", 2)
        job = active_downloads.get(job_id)
        if not job or job["user_id"] != user_id:
            await query.answer("This download is no longer active.", show_alert=True)
            return
        if action == "p":
            job["paused"] = True
            job["event"].clear()
            await query.message.edit_reply_markup(ui.download_controls(job_id, paused=True))
            await query.answer("⏸ Download paused")
        elif action == "r":
            job["paused"] = False
            job["event"].set()
            await query.message.edit_reply_markup(ui.download_controls(job_id))
            await query.answer("▶️ Download resumed")
        elif action == "s":
            job["cancelled"] = True
            job["paused"] = False
            job["event"].set()
            task = job.get("task")
            if task and not task.done():
                task.cancel()
            await query.answer("⛔ Stopping download...")
    except Exception:
        await query.answer("Could not control this download.", show_alert=True)


ADMIN_PAGES = [
    ("📊 Users & statistics", ["stats", "users", "newusers", "activeusers", "topusers", "finduser", "userinfo", "export"]),
    ("💎 Premium & payments", ["addpremium", "removepremium", "premiumlist", "payments", "addqr", "delqr", "removeqr"]),
    ("📢 Community", ["broadcast", "sendmsg", "ban", "unban", "banlist", "feedbacks"]),
    ("⚙️ Administration", ["addadmin", "removeadmin", "adminlist", "setfsub", "delfsub", "maintenance", "clearlogs", "adminhelp"]),
]


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
    return (f"🛠 **ADMIN PANEL** • {page+1}/{len(ADMIN_PAGES)}\n\n"
            f"**{ADMIN_PAGES[page][0]}**\n\n"
            "Tap an action or use its slash command. Browse with Previous / Next.\n"
            "👑 Only the owner can grant private-access premium.")


async def run_admin_inline(client, query, command):
    # Adapt the real command handler to edit the panel message rather than post a new message.
    handlers = {"stats": stats_handler, "users": users_handler, "loggedusers": loggedusers_handler, "newusers": new_users_handler, "activeusers": active_users_handler, "topusers": top_users_handler, "broadcast": broadcast_handler, "sendmsg": sendmsg_handler, "ban": ban_handler, "unban": unban_handler, "banlist": banlist_handler, "finduser": finduser_handler, "userinfo": userinfo_handler, "addpremium": addpremium_handler, "removepremium": removepremium_handler, "premiumlist": premiumlist_handler, "feedbacks": feedbacks_handler, "payments": payments_handler, "adminhelp": adminhelp_handler, "addadmin": addadmin_handler, "removeadmin": removeadmin_handler, "adminlist": adminlist_handler, "setfsub": setfsub_handler, "delfsub": delfsub_handler, "maintenance": maintenance_handler, "addqr": addqr_handler, "delqr": delqr_handler, "removeqr": delqr_handler, "clearlogs": clearlogs_handler, "export": export_handler}
    handler = handlers.get(command)
    if not handler:
        return
    owner_commands = {"addpremium", "addadmin", "removeadmin", "setfsub", "delfsub", "maintenance", "addqr", "delqr", "removeqr", "clearlogs"}
    if query.from_user.id != OWNER_ID and (command in owner_commands or not await is_admin(query.from_user.id)):
        await query.message.reply("🚫 **This action is not available to your account.**")
        return
    needs_value = {"broadcast", "sendmsg", "ban", "unban", "finduser", "userinfo", "addpremium", "removepremium", "addadmin", "removeadmin", "setfsub", "maintenance"}
    if command in needs_value:
        admin_pending[query.from_user.id] = command
        examples = {
            "broadcast": "Your announcement text", "sendmsg": "123456789 Your message",
            "ban": "123456789", "unban": "123456789", "finduser": "username or user ID",
            "userinfo": "123456789", "addpremium": "123456789 30", "removepremium": "123456789",
            "addadmin": "123456789", "removeadmin": "123456789", "setfsub": "@channelname",
            "maintenance": "on or off",
        }
        await query.message.edit_text(
            f"✍️ **/{command}**\n\nSend the details in your next message.\n"
            f"Example: `{examples[command]}`\n\nUse /cancel or another command to exit.",
            reply_markup=ui.feedback_keyboard())
        return
    class PanelProxy:
        def __init__(self):
            self.from_user = query.from_user
            self.chat = query.message.chat
            self.text = "/" + command
            self.id = query.message.id
        async def reply(self, text, reply_markup=None, **kwargs):
            return await query.message.edit_text(text, reply_markup=reply_markup or ui.admin_back_keyboard())
        async def reply_document(self, document, **kwargs):
            return await query.message.reply_document(document, **kwargs)
    await handler(client, PanelProxy())


@bot.on_callback_query()
async def callback_handler(client, query):
    """Route every button press straight to its action."""
    data = query.data or ""
    uid = query.from_user.id
    # Navigation never leaves feedback or an admin prompt silently active.
    if not data.startswith("dl:") and data not in {"cancel_login", "cancel_action"}:
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
    if data.startswith("dl:"):
        await handle_download_controls(query)
        return
    if data.startswith("admin_page:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer("🚫 Admin access only.", show_alert=True)
            return
        try:
            page = int(data.split(":", 1)[1])
            if not 0 <= page < len(ADMIN_PAGES):
                raise ValueError()
        except ValueError:
            await query.answer("Unknown page.", show_alert=True)
            return
        await query.answer()
        await render(query, admin_panel_text(page), admin_panel_keyboard(page))
        return
    if data.startswith("admin:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer("🚫 Admin access only.", show_alert=True)
            return
        await query.answer()
        await run_admin_inline(client, query, data.split(":", 1)[1])
        return
    if data == "redeem_points":
        uid = query.from_user.id
        if not await redeem_points(uid, REDEEM_POINTS, months=REDEEM_PREMIUM_MONTHS):
            await query.answer(f"You need {REDEEM_POINTS} points. Active owner-granted premium cannot be replaced.", show_alert=True)
            return
        await query.answer("Premium redeemed!")
        await show_premium(query)
        return
    if data.startswith("buy:"):
        plan_key = data.split(":", 1)[1]
        plan = PREMIUM_PLANS.get(plan_key)
        if not plan:
            await query.answer("Unknown plan", show_alert=True)
            return
        qr = await get_qr()
        if not qr:
            await query.answer("Payment QR is not available yet.", show_alert=True)
            await render(query, f"⚠️ **Payments temporarily unavailable**\n\nPlease contact @{PAYMENT_CONTACT}. Do not pay until the owner provides a QR.", ui.plans_keyboard())
            return
        import secrets
        token = secrets.token_hex(6)
        payment_pending[uid] = {"plan": plan_key, "token": token}
        await query.answer("💳 Your payment QR is ready.")
        try:
            await bot.send_photo(uid, qr, caption=ui.payment_text(plan), reply_markup=ui.payment_keyboard(token))
        except Exception:
            payment_pending.pop(uid, None)
            await query.message.reply(f"⚠️ **Could not display the payment QR**\n\nPlease try again or contact @{PAYMENT_CONTACT}. The owner may need to upload a new QR with /addqr.")
        return
    if data.startswith("paid:"):
        order = payment_pending.get(uid)
        if not order or order["token"] != data.split(":", 1)[1]:
            await query.answer("This checkout expired. Choose a plan again.", show_alert=True)
            return
        pending_action[uid] = "payment_proof"
        await query.answer("📸 Send your payment screenshot.")
        await query.message.reply(
            f"📸 **SUBMIT PAYMENT PROOF**\n\nSend a clear screenshot as a photo showing the amount, transaction ID and payment date.\n\n👤 Reviewed by @{PAYMENT_CONTACT}. Premium is activated only after the owner verifies payment.\n\nUse /cancel or any new command to exit.",
            reply_markup=ui.feedback_keyboard())
        return
    if data.startswith("users_page:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer("🚫 Admin access only.", show_alert=True)
            return
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Invalid page.", show_alert=True)
            return
        await query.answer()
        await show_users_page(query, page)
        return
    if data.startswith("loggedusers:"):
        if uid != OWNER_ID and not await is_admin(uid):
            await query.answer("🚫 Admin access only.", show_alert=True)
            return
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Invalid page.", show_alert=True)
            return
        await query.answer()
        await show_logged_users(query, page)
        return
    handler = CALLBACK_ACTIONS.get(data)
    if handler is None:
        await query.answer(ui.stale_button_text(), show_alert=True)
        return
    try:
        await handler(client, query)
    except Exception as e:
        try:
            await query.answer(f"⚠️ Error: {e}", show_alert=True)
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
    "addadmin", "removeadmin", "adminlist", "setfsub", "delfsub",
    "maintenance", "feedbacks", "sendmsg", "clearlogs", "export",
    "adminhelp", "admin", "admins", "addqr", "delqr", "removeqr", "payments", "redeem"
]))
async def text_handler(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    if text.startswith("/"):
        await abort_pending_on_command(client, message)
        await message.reply("❓ **Unknown command**\n\nOpen /help or /start to see the available actions.")
        return

    await add_user(user_id, message.from_user.first_name, message.from_user.username)

    if user_id in admin_pending:
        if user_id != OWNER_ID and not await is_admin(user_id):
            admin_pending.pop(user_id, None)
            await message.reply("🚫 Admin access only.")
            return
        action = admin_pending.pop(user_id)
        handlers = {"sendmsg": sendmsg_handler, "ban": ban_handler, "unban": unban_handler, "finduser": finduser_handler, "userinfo": userinfo_handler, "addpremium": addpremium_handler, "removepremium": removepremium_handler, "addadmin": addadmin_handler, "removeadmin": removeadmin_handler, "setfsub": setfsub_handler, "maintenance": maintenance_handler}
        if action == "broadcast":
            users = await get_all_users()
            sent = 0
            for entry in users:
                try:
                    await bot.send_message(entry["user_id"], text)
                    sent += 1
                except Exception:
                    pass
            await message.reply(f"Broadcast complete: sent to {sent} users.")
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
                    return await message.reply(content, reply_markup=reply_markup)
            await handler(client, PromptProxy())
            return

    if user_id in pending_action:
        action = pending_action[user_id]
        if action == "payment_proof":
            await message.reply("📸 **Screenshot required**\n\nPlease send your payment screenshot as a photo, not text. Use /cancel to exit.")
            return
        if action == "qr_upload":
            await message.reply("Please upload the QR image as a photo.")
            return
        if action == "caption":
            await set_caption(user_id, text)
            del pending_action[user_id]
            await message.reply(f"✅ Caption saved!\n\n`{text}`\n\nℹ️ Custom captions apply to premium extractions. Free downloads preserve the original caption and add attribution.")
            return
        elif action == "feedback":
            del pending_action[user_id]
            await save_feedback(message.from_user, message.text)
            await message.reply(ui.feedback_saved_text(), reply_markup=ui.back_keyboard())
            return

    if user_id in login_pending:
        pending = login_pending[user_id]
        step = pending.get("step", "")

        if step == "waiting_phone":
            phone = text.replace(" ", "").replace("-", "")
            if not phone.startswith("+"):
                phone = "+" + phone
            if not re.match(r"^\+\d{7,15}$", phone):
                await message.reply("❌ Invalid format. Example: `+91 9876543210`")
                return
            await message.reply("⏳ Sending OTP...")
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
                await message.reply("✅ OTP sent!\n\nSend with spaces: `1 2 3 4 5`")
            except PhoneNumberInvalid:
                await message.reply("❌ Invalid phone!")
                try:
                    await temp.disconnect()
                except:
                    pass
                del login_pending[user_id]
            except Exception as e:
                await message.reply(f"❌ Error: {e}")
                try:
                    await temp.disconnect()
                except:
                    pass
                del login_pending[user_id]
            return

        elif step == "waiting_otp":
            otp = text.replace(" ", "").replace("-", "")
            if not otp.isdigit():
                await message.reply("❌ Invalid OTP!")
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
                await message.reply(f"✅ **Login Successful!**\n\n👤 {me.first_name}\n📱 +{me.phone_number}")
            except SessionPasswordNeeded:
                login_pending[user_id]["step"] = "waiting_2fa"
                await message.reply("🔒 2FA enabled. Send password:")
            except PhoneCodeInvalid:
                await message.reply("❌ Wrong OTP!")
            except Exception as e:
                await message.reply(f"❌ Error: {e}")
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
                await message.reply(f"✅ **Login Successful!**\n\n👤 {me.first_name}")
            except PasswordHashInvalid:
                await message.reply("❌ Wrong password!")
            except Exception as e:
                await message.reply(f"❌ Error: {e}")
                try:
                    await temp.stop()
                except:
                    pass
                del login_pending[user_id]
            return

    if not await check_access(message):
        return

    if re.search(r"(?:t\.me|telegram\.me)/(?:c/|\+|joinchat/)", text) and not await private_access(user_id):
        await message.reply("🔒 **Private access unavailable**\n\n" + REDEEM_LIMITATION)
        return

    lines = text.split("\n")
    tg_links = [l.strip() for l in lines if "t.me/" in l]

    if len(tg_links) > 1:
        premium = await is_premium(user_id)
        max_bulk = 50 if premium else 5
        if len(tg_links) > max_bulk:
            await message.reply(f"⚠️ Too many links!\n🆓 Free: 5\n💎 Premium: 50\nSent: {len(tg_links)}")
            return
        if not premium and user_id != OWNER_ID:
            allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
            if not allowed or current + len(tg_links) > FREE_DAILY_LIMIT:
                await message.reply(f"⛔ Daily limit! Used: {current}/{FREE_DAILY_LIMIT}")
                return
        status = await message.reply(f"⏳ Processing {len(tg_links)}...")
        success = failed = 0
        for i, link in enumerate(tg_links, 1):
            try:
                await status.edit(f"⏳ {i}/{len(tg_links)}...")
                chat_target, mid, is_priv = parse_link(link)
                if chat_target is None:
                    failed += 1
                    continue
                ts = await message.reply(f"📥 {i}")
                if is_priv:
                    urow = await get_user(user_id) or {}
                    if user_id != OWNER_ID and (not await is_premium(user_id) or urow.get("premium_source") != "manual"):
                        await ts.edit("🔒 Private links are available only with premium granted manually by the owner.")
                        failed += 1
                        continue
                    uc = await get_user_client(user_id)
                    if not uc:
                        await ts.edit("🔒 Login required")
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
        await status.edit(f"✅ Done!\n✅ {success} ❌ {failed}")
        return

    if "t.me/" not in text:
        await message.reply(
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
            await message.reply("⚠️ Range too large!\n🆓 Free: 20\n💎 Premium: 1000")
            return
        if not premium and user_id != OWNER_ID:
            allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
            if not allowed or current + total > FREE_DAILY_LIMIT:
                await message.reply(f"⛔ Daily limit! Used: {current}/{FREE_DAILY_LIMIT}")
                return
        base_link = text.rsplit("/", 1)[0]
        status = await message.reply(f"⏳ Range: {total} messages")
        success = failed = 0
        for msg_id in range(start, end + 1):
            try:
                link = f"{base_link}/{msg_id}"
                chat_target, mid, is_priv = parse_link(link)
                if chat_target is None:
                    failed += 1
                    continue
                ts = await message.reply(f"📥 {msg_id}")
                if is_priv:
                    urow = await get_user(user_id) or {}
                    if user_id != OWNER_ID and (not await is_premium(user_id) or urow.get("premium_source") != "manual"):
                        await ts.edit("🔒 Private links are available only with premium granted manually by the owner.")
                        failed += 1
                        continue
                    uc = await get_user_client(user_id)
                    if not uc:
                        await ts.edit("🔒 Login required")
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
        await status.edit(f"✅ Done!\n✅ {success} ❌ {failed}")
        return

    chat_target, msg_id, is_private = parse_link(text)
    if chat_target is None:
        await message.reply("❌ Invalid link.")
        return

    premium = await is_premium(user_id)
    if not premium and user_id != OWNER_ID:
        allowed, current = await check_daily_limit(user_id, FREE_DAILY_LIMIT)
        if not allowed:
            await message.reply(f"⛔ **Daily limit!**\n\n🆓 Free: {FREE_DAILY_LIMIT}/day\n💎 Premium: Unlimited")
            return

    if is_private:
        urow = await get_user(user_id) or {}
        if user_id != OWNER_ID and (not premium or urow.get("premium_source") != "manual"):
            msg = REDEEM_LIMITATION if premium and urow.get("premium_source") == "redeem" else "🔒 Private links are available only with premium granted manually by the owner."
            await message.reply(msg)
            return
        uc = await get_user_client(user_id)
        if not uc:
            await message.reply("🔒 **Private link!**\n\nPlease /login first.")
            return
        status = await message.reply("⏳ Fetching...")
        await fetch_and_send(message, status, uc, chat_target, msg_id)
    else:
        status = await message.reply("⏳ Fetching...")
        try:
            await fetch_and_send(message, status, bot, chat_target, msg_id)
        except ChannelPrivate:
            uc = await get_user_client(user_id)
            if uc and await private_access(user_id):
                await fetch_and_send(message, status, uc, chat_target, msg_id)
            else:
                await status.edit("🔒 Private. Use /login")
        

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
    print("✅ Bot starting...")
    bot.run()
    

# Keep these imported database APIs exposed for backward compatibility with
# existing integrations and the test harness, even where this module does not
# call them directly.
_COMPAT_EXPORTS = (FloodWait, FREE_PRIVATE_LINKS, PREMIUM_BENEFITS, clear_history,
                   delete_bookmark, remove_favorite, add_referral, test_connection,
                   total_users, total_downloads_count)
