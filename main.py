import os
import re
import asyncio
from flask import Flask
from threading import Thread
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid,
    PasswordHashInvalid, FloodWait, ChannelPrivate
)

from database import (
    add_user, get_user, is_premium, is_banned, check_daily_limit,
    increment_daily, save_session, get_session, delete_session,
    set_caption, get_caption, del_caption, set_thumbnail, get_thumbnail,
    del_thumbnail, set_prefix, get_prefix, set_suffix, get_suffix,
    add_download, get_history, clear_history, add_bookmark, get_bookmarks,
    delete_bookmark, add_favorite, get_favorites, remove_favorite,
    set_language, toggle_notifications, toggle_silent, reset_settings,
    add_referral, add_feedback, test_connection, total_users,
    get_all_users_list, get_banned_users_list, get_premium_users_list,
    get_active_users_today, get_new_users_today, get_top_users,
    total_downloads_count, total_bookmarks_count, get_all_feedback,
    search_user, set_maintenance, get_maintenance, set_fsub_channel,
    get_fsub_channel, delete_fsub, add_admin, remove_admin, is_admin,
    get_admins_list, clear_all_logs, get_bot_stats, add_premium,
    remove_premium, ban_user, unban_user
)

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourBot")

bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_clients = {}
login_pending = {}
pending_action = {}


def parse_link(link):
    link = link.strip().rstrip("/")
    parts = link.split("/")
    try:
        msg_id = int(parts[-1])
    except:
        return None, None, None
    if "c" in parts:
        idx = parts.index("c")
        chat_id = int(f"-100{parts[idx + 1]}")
        return chat_id, msg_id, True
    else:
        username = parts[-2]
        if username.lower() in ["c", "joinchat"]:
            return None, None, None
        return username, msg_id, False


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
    return result.strip()


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
            if member.status in ["left", "kicked"]:
                raise Exception("Not member")
        except:
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{fsub.replace('@', '')}")],
                [InlineKeyboardButton("✅ I Joined", callback_data="check_fsub")]
            ])
            await message.reply(
                f"⚠️ **You must join {fsub} first!**\n\n"
                f"Join the channel and click the button below.",
                reply_markup=buttons
            )
            return False
    return True


async def fetch_and_send(message, status, fetch_client, chat_target, msg_id):
    user_id = message.from_user.id
    file_path = None
    thumb_path = None
    try:
        msg = await fetch_client.get_messages(chat_target, msg_id)
        if not msg or msg.empty:
            await status.edit("❌ Message not found.")
            return False
        if not msg.media:
            if msg.text:
                await message.reply(msg.text)
                await status.delete()
                return True
            else:
                await status.edit("❌ No content available.")
                return False

        premium = await is_premium(user_id)
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
                f"💎 Premium limit: 2 GB\n\n"
                f"Upgrade to Premium for larger files!"
            )
            return False

        await status.edit("⬇️ Downloading...")
        file_path = await fetch_client.download_media(msg)
        if not file_path:
            await status.edit("❌ Download failed.")
            return False

        await status.edit("⬆️ Uploading...")
        caption = await apply_custom_caption(user_id, msg.caption)
        chat_id = message.chat.id

        thumb_id = await get_thumbnail(user_id)
        if thumb_id and (msg.video or msg.document):
            try:
                thumb_path = await bot.download_media(thumb_id)
            except:
                pass

        if msg.photo:
            await bot.send_photo(chat_id, file_path, caption=caption)
        elif msg.video:
            await bot.send_video(chat_id, file_path, caption=caption, thumb=thumb_path)
        elif msg.document:
            await bot.send_document(chat_id, file_path, caption=caption, thumb=thumb_path)
        elif msg.audio:
            await bot.send_audio(chat_id, file_path, caption=caption)
        elif msg.voice:
            await bot.send_voice(chat_id, file_path)
        elif msg.video_note:
            await bot.send_video_note(chat_id, file_path)
        elif msg.sticker:
            await bot.send_sticker(chat_id, file_path)
        elif msg.animation:
            await bot.send_animation(chat_id, file_path, caption=caption)
        else:
            await bot.send_document(chat_id, file_path, caption=caption)

        await status.delete()
        media_type = "photo" if msg.photo else "video" if msg.video else "document" if msg.document else "media"
        await add_download(user_id, f"msg_{msg_id}", media_type)
        await increment_daily(user_id)
        return True

    except Exception as e:
        await status.edit(f"❌ Error: {e}")
        return False
    finally:
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
