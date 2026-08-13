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
                f"💎 Premium limit: 2 GB"
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


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user = message.from_user
    is_new = await add_user(user.id, user.first_name, user.username)
    args = message.text.split()
    if len(args) > 1 and is_new:
        try:
            ref_id = int(args[1])
            if ref_id != user.id:
                await add_referral(ref_id, user.id)
        except:
            pass
    premium = await is_premium(user.id)
    badge = "💎 Premium" if premium else "🆓 Free"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login", callback_data="cmd_login"),
         InlineKeyboardButton("🚪 Logout", callback_data="cmd_logout")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="cmd_settings"),
         InlineKeyboardButton("📊 Stats", callback_data="cmd_stats")],
        [InlineKeyboardButton("💎 Premium", callback_data="cmd_premium"),
         InlineKeyboardButton("🎁 Refer", callback_data="cmd_refer")],
        [InlineKeyboardButton("📖 Help", callback_data="cmd_help"),
         InlineKeyboardButton("💬 Feedback", callback_data="cmd_feedback")]
    ])
    await message.reply(
        f"👋 **Hello {user.first_name}!**\n\n"
        f"🤖 **Restricted Content Saver Bot**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎖 **Status:** {badge}\n\n"
        f"📌 Send any Telegram link to save content!\n"
        f"🔒 For private links: /login first\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=buttons
    )


@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client, message):
    await message.reply(
        "📖 **HELP MENU**\n\n"
        "**🔐 Account:**\n/login /logout /status /cancel\n\n"
        "**📥 Download:**\nSend link or range: `t.me/ch/1-20`\n\n"
        "**🎨 Customization:**\n/setcaption /delcaption\n/setthumb /delthumb\n/setprefix /setsuffix\n\n"
        "**📊 Info:**\n/mystats /myinfo /history\n\n"
        "**⚙️ Settings:**\n/settings /language\n\n"
        "**🎁 Extra:**\n/refer /bookmark /bookmarks\n/favorite /favorites /share /feedback /premium"
    )


@bot.on_message(filters.command("login") & filters.private)
async def login_handler(client, message):
    user_id = message.from_user.id
    if await get_user_client(user_id):
        await message.reply("✅ Already logged in! Use /logout first.")
        return
    if user_id in login_pending:
        await message.reply("⏳ Login in progress. Send /cancel.")
        return
    login_pending[user_id] = {"step": "waiting_phone"}
    await message.reply(
        "🔐 **LOGIN**\n\n"
        "Send phone with country code:\n"
        "Example: `+91 9876543210`\n\n"
        "Send /cancel to abort."
    )


@bot.on_message(filters.command("logout") & filters.private)
async def logout_handler(client, message):
    user_id = message.from_user.id
    user_client = await get_user_client(user_id)
    if not user_client:
        await message.reply("ℹ️ Not logged in.")
        return
    try:
        me = await user_client.get_me()
        phone = me.phone_number or "Unknown"
    except:
        phone = "Unknown"
    try:
        await user_client.log_out()
    except:
        try:
            await user_client.stop()
        except:
            pass
    if user_id in user_clients:
        del user_clients[user_id]
    await delete_session(user_id)
    await message.reply(f"✅ **Logged out!**\n📱 `+{phone}`")


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
    user_id = message.from_user.id
    if user_id in login_pending:
        pending = login_pending[user_id]
        temp = pending.get("client")
        if temp:
            try:
                await temp.stop()
            except:
                pass
        del login_pending[user_id]
        await message.reply("❌ Login cancelled.")
    elif user_id in pending_action:
        del pending_action[user_id]
        await message.reply("❌ Action cancelled.")
    else:
        await message.reply("ℹ️ Nothing to cancel.")


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
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user:
        await message.reply("Send /start first!")
        return
    premium = await is_premium(user_id)
    badge = "💎 Premium" if premium else "🆓 Free"
    joined = user.get("joined_date", datetime.now()).strftime("%d %b %Y")
    await message.reply(
        f"📊 **YOUR STATS**\n\n"
        f"👤 {user.get('name')}\n"
        f"🎖 Status: {badge}\n"
        f"📥 Total: {user.get('downloads', 0)}\n"
        f"📅 Today: {user.get('daily_downloads', 0)}\n"
        f"👥 Referrals: {user.get('referral_count', 0)}\n"
        f"📆 Joined: {joined}"
    )


@bot.on_message(filters.command("myinfo") & filters.private)
async def myinfo_handler(client, message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user:
        await message.reply("Send /start first!")
        return
    caption = user.get("caption") or "Not set"
    prefix = user.get("prefix") or "Not set"
    suffix = user.get("suffix") or "Not set"
    thumb = "✅ Set" if user.get("thumbnail_id") else "❌ Not set"
    await message.reply(
        f"ℹ️ **MY INFO**\n\n"
        f"👤 {user.get('name')}\n"
        f"🆔 `{user_id}`\n"
        f"📱 {user.get('phone') or 'Not logged in'}\n\n"
        f"✏️ Caption: {caption[:30] if caption != 'Not set' else caption}\n"
        f"🏷 Prefix: {prefix}\n"
        f"🏷 Suffix: {suffix}\n"
        f"🖼 Thumb: {thumb}\n"
        f"🌐 Lang: {user.get('language', 'en')}"
    )


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
    user = await get_user(message.from_user.id)
    if not user:
        await message.reply("Send /start first!")
        return
    notif = "🔔 ON" if user.get("notifications", True) else "🔕 OFF"
    silent = "🌙 ON" if user.get("silent_mode", False) else "🔊 OFF"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Notifications: {notif}", callback_data="toggle_notif")],
        [InlineKeyboardButton(f"Silent: {silent}", callback_data="toggle_silent")],
        [InlineKeyboardButton("🌐 Language", callback_data="cmd_language")],
        [InlineKeyboardButton("🔄 Reset All", callback_data="reset_settings")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await message.reply("⚙️ **SETTINGS**", reply_markup=buttons)


@bot.on_message(filters.command("language") & filters.private)
async def language_handler(client, message):
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇮🇳 Hindi", callback_data="lang_hi")]
    ])
    await message.reply("🌐 **Choose language:**", reply_markup=buttons)


@bot.on_message(filters.command("refer") & filters.private)
async def refer_handler(client, message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    count = user.get("referral_count", 0) if user else 0
    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    await message.reply(
        f"🎁 **REFERRAL**\n\n"
        f"👥 Your Referrals: {count}\n\n"
        f"🔗 Link:\n`{link}`"
    )


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
    user_id = message.from_user.id
    if len(message.text.split()) < 2:
        pending_action[user_id] = "feedback"
        await message.reply("💬 **Send your feedback:**\n\nSend /cancel to abort.")
        return
    fb = message.text.split(None, 1)[1]
    await add_feedback(user_id, fb)
    if OWNER_ID:
        try:
            await bot.send_message(OWNER_ID, f"💬 Feedback from {user_id}:\n\n{fb}")
        except:
            pass
    await message.reply("✅ Feedback sent!")


@bot.on_message(filters.command("premium") & filters.private)
async def premium_handler(client, message):
    user_id = message.from_user.id
    premium = await is_premium(user_id)
    if premium:
        user = await get_user(user_id)
        expiry = user.get("premium_expiry")
        exp = expiry.strftime("%d %b %Y") if expiry else "Unknown"
        await message.reply(f"💎 **PREMIUM ACTIVE!**\n\n📅 Expires: {exp}")
    else:
        await message.reply(
            "💎 **PREMIUM BENEFITS**\n\n"
            "✅ Unlimited downloads\n"
            "✅ 2 GB file size\n"
            "✅ 4x faster speed\n"
            "✅ Priority support\n"
            "✅ No ads\n\n"
            f"Contact owner to buy!"
        )
      

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


@bot.on_message(filters.command("users") & filters.private)
@admin_only
async def users_handler(client, message):
    users = await get_all_users_list()
    if not users:
        await message.reply("No users.")
        return
    text = f"👥 **ALL USERS ({len(users)})**\n\n"
    for i, u in enumerate(users[:30], 1):
        text += f"{i}. `{u['user_id']}` - {u.get('name', 'N/A')}\n"
    if len(users) > 30:
        text += f"\n...and {len(users) - 30} more"
    await message.reply(text)


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
    users = await get_all_users_list()
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
@admin_only
async def addpremium_handler(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: `/addpremium USER_ID [days]`")
        return
    try:
        target = int(args[1])
        days = int(args[2]) if len(args) > 2 else 30
        await add_premium(target, days)
        await message.reply(f"💎 `{target}` premium for {days} days!")
        try:
            await bot.send_message(target, f"💎 You got Premium for {days} days!")
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
    users = await get_all_users_list()
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


@bot.on_message(filters.photo & filters.private)
async def photo_handler(client, message):
    user_id = message.from_user.id
    if pending_action.get(user_id) == "thumbnail":
        await set_thumbnail(user_id, message.photo.file_id)
        del pending_action[user_id]
        await message.reply("✅ Thumbnail saved!")


@bot.on_callback_query()
async def callback_handler(client, query):
    data = query.data
    user_id = query.from_user.id
    if data == "close":
        await query.message.delete()
    elif data == "cmd_login":
        await query.answer("Send /login")
    elif data == "cmd_logout":
        await query.answer("Send /logout")
    elif data == "cmd_settings":
        await query.answer("Send /settings")
    elif data == "cmd_stats":
        await query.answer("Send /mystats")
    elif data == "cmd_premium":
        await query.answer("Send /premium")
    elif data == "cmd_refer":
        await query.answer("Send /refer")
    elif data == "cmd_help":
        await query.answer("Send /help")
    elif data == "cmd_feedback":
        await query.answer("Send /feedback")
    elif data == "cmd_language":
        await query.answer("Send /language")
    elif data == "toggle_notif":
        new = await toggle_notifications(user_id)
        await query.answer(f"Notifications: {'ON' if new else 'OFF'}")
    elif data == "toggle_silent":
        new = await toggle_silent(user_id)
        await query.answer(f"Silent: {'ON' if new else 'OFF'}")
    elif data == "reset_settings":
        await reset_settings(user_id)
        await query.answer("✅ Reset done!")
    elif data.startswith("lang_"):
        lang = data.split("_")[1]
        await set_language(user_id, lang)
        await query.answer(f"Language: {lang.upper()}")
    elif data == "check_fsub":
        fsub = await get_fsub_channel()
        if fsub:
            try:
                member = await bot.get_chat_member(fsub, user_id)
                if member.status not in ["left", "kicked"]:
                    await query.message.delete()
                    await query.answer("✅ Verified! Send your link.")
                else:
                    await query.answer("❌ Not joined!", show_alert=True)
            except:
                await query.answer("❌ Please join!", show_alert=True)


@bot.on_message(filters.text & filters.private & ~filters.command([
    "start", "help", "login", "logout", "status", "cancel",
    "setcaption", "delcaption", "setthumb", "delthumb",
    "setprefix", "setsuffix", "mystats", "myinfo", "history",
    "settings", "language", "refer", "bookmark", "bookmarks",
    "favorite", "favorites", "share", "feedback", "premium",
    "stats", "users", "activeusers", "newusers", "topusers",
    "broadcast", "ban", "unban", "banlist", "finduser",
    "userinfo", "addpremium", "removepremium", "premiumlist",
    "addadmin", "removeadmin", "adminlist", "setfsub", "delfsub",
    "maintenance", "feedbacks", "sendmsg", "clearlogs", "export",
    "adminhelp"
]))
async def text_handler(client, message):
    user_id = message.from_user.id
    text = message.text.strip()

    await add_user(user_id, message.from_user.first_name, message.from_user.username)

    if user_id in pending_action:
        action = pending_action[user_id]
        if action == "caption":
            await set_caption(user_id, text)
            del pending_action[user_id]
            await message.reply(f"✅ Caption set!\n\n`{text}`")
            return
        elif action == "feedback":
            await add_feedback(user_id, text)
            del pending_action[user_id]
            if OWNER_ID:
                try:
                    await bot.send_message(OWNER_ID, f"💬 Feedback from {user_id}:\n\n{text}")
                except:
                    pass
            await message.reply("✅ Feedback sent!")
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

    lines = text.split("\n")
    tg_links = [l.strip() for l in lines if "t.me/" in l]

    if len(tg_links) > 1:
        premium = await is_premium(user_id)
        max_bulk = 50 if premium else 5
        if len(tg_links) > max_bulk:
            await message.reply(f"⚠️ Too many links!\n🆓 Free: 5\n💎 Premium: 50\nSent: {len(tg_links)}")
            return
        if not premium:
            allowed, current = await check_daily_limit(user_id, 10)
            if not allowed or current + len(tg_links) > 10:
                await message.reply(f"⛔ Daily limit! Used: {current}/10")
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
                    uc = await get_user_client(user_id)
                    if not uc:
                        await ts.edit("🔒 Login required")
                        failed += 1
                        continue
                    ok = await fetch_and_send(message, ts, uc, chat_target, mid)
                else:
                    ok = await fetch_and_send(message, ts, bot, chat_target, mid)
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
            await message.reply(f"⚠️ Range too large!\n🆓 Free: 20\n💎 Premium: 1000")
            return
        if not premium:
            allowed, current = await check_daily_limit(user_id, 10)
            if not allowed or current + total > 10:
                await message.reply(f"⛔ Daily limit! Used: {current}/10")
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
                    uc = await get_user_client(user_id)
                    if not uc:
                        await ts.edit("🔒 Login required")
                        failed += 1
                        continue
                    ok = await fetch_and_send(message, ts, uc, chat_target, mid)
                else:
                    ok = await fetch_and_send(message, ts, bot, chat_target, mid)
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
    if not premium:
        allowed, current = await check_daily_limit(user_id, 10)
        if not allowed:
            await message.reply(f"⛔ **Daily limit!**\n\n🆓 Free: 10/day\n💎 Premium: Unlimited")
            return

    if is_private:
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
            if uc:
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_connection())
    print("✅ Bot starting...")
    bot.run()
