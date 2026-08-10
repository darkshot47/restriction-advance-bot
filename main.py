import os
import re
import asyncio
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    PasswordHashInvalid,
    FloodWait,
    UserNotParticipant,
    ChannelPrivate
)

# ═══════════════════════════════════════
#         CONFIGURATION
# ═══════════════════════════════════════

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ═══════════════════════════════════════
#         BOT CLIENT
# ═══════════════════════════════════════

bot = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ═══════════════════════════════════════
#   IN-MEMORY STORAGE
# ═══════════════════════════════════════

user_clients = {}
login_pending = {}


# ═══════════════════════════════════════
#         HELPER FUNCTIONS
# ═══════════════════════════════════════

def parse_link(link: str):
    link = link.strip().rstrip("/")
    parts = link.split("/")

    try:
        msg_id = int(parts[-1])
    except ValueError:
        return None, None, None

    if "c" in parts:
        idx = parts.index("c")
        chat_id = int(f"-100{parts[idx + 1]}")
        return chat_id, msg_id, True
    else:
        username = parts[-2]
        if username.lower() in ["c", "joinchat", "addstickers"]:
            return None, None, None
        return username, msg_id, False


async def get_user_client(user_id: int):
    if user_id in user_clients:
        client = user_clients[user_id]
        try:
            if await client.get_me():
                return client
        except Exception:
            pass
        try:
            await client.stop()
        except:
            pass
        del user_clients[user_id]
    return None
    # ═══════════════════════════════════════
#         /start COMMAND
# ═══════════════════════════════════════

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    name = user.first_name or "User"

    await message.reply(
        f"👋 **Hello {name}! Welcome to Restricted Content Saver Bot!**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 **What does this bot do?**\n"
        "This bot helps you **save & download** restricted content\n"
        "(Photos, Videos, Docs, Audio, etc.) from Telegram channels\n"
        "where saving/forwarding is **disabled**.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 **How to use:**\n\n"
        "1️⃣ **Public Channel Link:**\n"
        "   Just send the link — no login needed!\n"
        "   `https://t.me/channelname/123`\n\n"
        "2️⃣ **Private Channel Link:**\n"
        "   You must /login first with your Telegram account.\n"
        "   `https://t.me/c/1234567890/123`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔐 **Account Commands:**\n"
        "• /login  → Login with your Telegram account\n"
        "• /logout → Logout from your account\n"
        "• /status → Check your login status\n"
        "• /cancel → Cancel ongoing login process\n"
        "• /help   → Show help\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ **Send any Telegram message link to get started!**",
        quote=True
    )


# ═══════════════════════════════════════
#         /help COMMAND
# ═══════════════════════════════════════

@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    await message.reply(
        "📖 **Help Menu**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Commands:**\n"
        "• /start  → Welcome message\n"
        "• /login  → Login with Telegram account\n"
        "• /logout → Logout from account\n"
        "• /status → Check login status\n"
        "• /cancel → Cancel login process\n"
        "• /help   → This menu\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Supported Links:**\n\n"
        "🌐 Public:\n"
        "`https://t.me/channelname/123`\n"
        "No login needed!\n\n"
        "🔒 Private:\n"
        "`https://t.me/c/1234567890/123`\n"
        "/login required!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Login Steps:**\n"
        "1. Send /login\n"
        "2. Enter phone: `+91 9876543210`\n"
        "3. Enter OTP with spaces: `1 2 3 4 5`\n"
        "4. Enter 2FA password if enabled\n"
        "5. Done! ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "You must be a **member** of the\n"
        "private channel on your logged-in account.",
        quote=True
    )


# ═══════════════════════════════════════
#         /status COMMAND
# ═══════════════════════════════════════

@bot.on_message(filters.command("status") & filters.private)
async def status_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_client = await get_user_client(user_id)

    if user_client:
        try:
            me = await user_client.get_me()
            name = me.first_name or ""
            if me.last_name:
                name += f" {me.last_name}"
            uname = f"@{me.username}" if me.username else "No username"
            phone = me.phone_number or "N/A"

            await message.reply(
                "✅ **You are logged in!**\n\n"
                f"👤 **Name:** {name}\n"
                f"📱 **Phone:** `+{phone}`\n"
                f"🆔 **Username:** {uname}\n\n"
                "You can access private channel content.\n"
                "Use /logout to logout.",
                quote=True
            )
        except Exception as e:
            await message.reply(
                f"⚠️ **Session error:** `{e}`\n"
                "Please /logout and /login again.",
                quote=True
            )
    else:
        await message.reply(
            "❌ **You are not logged in.**\n\n"
            "Use /login to access private channel content.",
            quote=True
        )


# ═══════════════════════════════════════
#         /cancel COMMAND
# ═══════════════════════════════════════

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id in login_pending:
        pending = login_pending[user_id]
        temp_client = pending.get("client")
        if temp_client:
            try:
                await temp_client.stop()
            except:
                pass
        del login_pending[user_id]
        await message.reply(
            "❌ **Login process cancelled.**\n\n"
            "Send /login to start again.",
            quote=True
        )
    else:
        await message.reply(
            "ℹ️ No active login process to cancel.",
            quote=True
        )
        # ═══════════════════════════════════════
#         /login COMMAND
# ═══════════════════════════════════════

@bot.on_message(filters.command("login") & filters.private)
async def login_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if await get_user_client(user_id):
        await message.reply(
            "✅ **Already logged in!**\n\n"
            "Use /logout first to switch accounts.\n"
            "Use /status to see current account info.",
            quote=True
        )
        return

    if user_id in login_pending:
        await message.reply(
            "⏳ **Login already in progress.**\n\n"
            "Complete it or send /cancel to restart.",
            quote=True
        )
        return

    login_pending[user_id] = {"step": "waiting_phone"}

    await message.reply(
        "🔐 **Login to Your Telegram Account**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📱 **Send your phone number with country code.**\n\n"
        "**Format:** `+CountryCode PhoneNumber`\n\n"
        "**Examples:**\n"
        "🇮🇳 India:      `+91 9876543210`\n"
        "🇺🇸 USA:        `+1 2345678901`\n"
        "🇬🇧 UK:         `+44 7911123456`\n"
        "🇷🇺 Russia:     `+7 9123456789`\n"
        "🇧🇩 Bangladesh: `+880 1812345678`\n"
        "🇵🇰 Pakistan:   `+92 3001234567`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔒 **Your data is safe:**\n"
        "• We never store your password.\n"
        "• Session is only in memory.\n"
        "• Use /logout anytime.\n"
        "• Send /cancel to abort.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📲 **Send your phone number now:**",
        quote=True
    )


# ═══════════════════════════════════════
#         /logout COMMAND
# ═══════════════════════════════════════

@bot.on_message(filters.command("logout") & filters.private)
async def logout_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_client = await get_user_client(user_id)

    if not user_client:
        await message.reply(
            "ℹ️ **You are not logged in.**\n\n"
            "Use /login to login.",
            quote=True
        )
        return

    try:
        me = await user_client.get_me()
        phone = me.phone_number or "Unknown"
        await user_client.stop()
    except:
        phone = "Unknown"

    if user_id in user_clients:
        del user_clients[user_id]

    await message.reply(
        "✅ **Logged out successfully!**\n\n"
        f"📱 **Phone:** `+{phone}`\n\n"
        "Your session has been removed from memory.\n"
        "Use /login to login again anytime.",
        quote=True
    )


# ═══════════════════════════════════════
#   TEXT HANDLER (Login Flow + Links)
# ═══════════════════════════════════════

@bot.on_message(
    filters.text & filters.private & ~filters.command(
        ["start", "help", "login", "logout", "status", "cancel"]
    )
)
async def text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    # ─── LOGIN FLOW ───
    if user_id in login_pending:
        pending = login_pending[user_id]
        step = pending.get("step", "")

        # ── STEP 1: Phone Number ──
        if step == "waiting_phone":
            phone = text.replace(" ", "").replace("-", "")
            if not phone.startswith("+"):
                phone = "+" + phone

            if not re.match(r"^\+\d{7,15}$", phone):
                await message.reply(
                    "❌ **Invalid format!**\n\n"
                    "Send with country code.\n"
                    "Example: `+91 9876543210`\n\n"
                    "Send /cancel to abort.",
                    quote=True
                )
                return

            await message.reply(
                f"📱 Number received: `{phone}`\n"
                "⏳ Sending OTP... Please wait.",
                quote=True
            )

            temp_client = Client(
                f"login_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                in_memory=True
            )

            try:
                await temp_client.connect()
                sent = await temp_client.send_code(phone)

                login_pending[user_id] = {
                    "step": "waiting_otp",
                    "phone": phone,
                    "phone_code_hash": sent.phone_code_hash,
                    "client": temp_client
                }

                await message.reply(
                    "✅ **OTP sent to your Telegram!**\n\n"
                    "📩 Check your Telegram app for the code.\n\n"
                    "⚠️ **Send OTP with spaces:**\n"
                    "If OTP is `12345` send as `1 2 3 4 5`\n\n"
                    "📲 **Send OTP now:**",
                    quote=True
                )

            except PhoneNumberInvalid:
                await message.reply(
                    "❌ **Invalid phone number!**\n"
                    "Please check and try /login again.",
                    quote=True
                )
                try:
                    await temp_client.disconnect()
                except:
                    pass
                del login_pending[user_id]

            except FloodWait as e:
                await message.reply(
                    f"⚠️ **Flood wait!**\n"
                    f"Try again after **{e.value} seconds**.\n\n"
                    "Send /cancel and try /login later.",
                    quote=True
                )
                try:
                    await temp_client.disconnect()
                except:
                    pass
                del login_pending[user_id]

            except Exception as e:
                await message.reply(
                    f"❌ **Error:** `{e}`\n\n"
                    "Send /cancel and try /login again.",
                    quote=True
                )
                try:
                    await temp_client.disconnect()
                except:
                    pass
                del login_pending[user_id]
            return

        # ── STEP 2: OTP ──
        elif step == "waiting_otp":
            otp = text.replace(" ", "").replace("-", "")

            if not otp.isdigit():
                await message.reply(
                    "❌ **Invalid OTP!** Only digits allowed.\n"
                    "Example: `1 2 3 4 5`\n\n"
                    "Send /cancel to abort.",
                    quote=True
                )
                return

            temp_client = pending.get("client")
            phone = pending.get("phone")
            phone_code_hash = pending.get("phone_code_hash")

            try:
                await temp_client.sign_in(
                    phone_number=phone,
                    phone_code_hash=phone_code_hash,
                    phone_code=otp
                )

                user_clients[user_id] = temp_client
                del login_pending[user_id]

                me = await temp_client.get_me()
                name = me.first_name or "User"

                await message.reply(
                    "✅ **Login Successful!**\n\n"
                    f"👤 **Welcome, {name}!**\n"
                    f"📱 **Phone:** `+{me.phone_number}`\n\n"
                    "You can now access **private channel** content!\n"
                    "Send any private channel link now.\n\n"
                    "Use /logout to logout anytime.",
                    quote=True
                )

            except SessionPasswordNeeded:
                login_pending[user_id]["step"] = "waiting_2fa"
                await message.reply(
                    "🔒 **2FA is enabled!**\n\n"
                    "Please send your **cloud password** now.\n\n"
                    "Password is not stored anywhere.\n"
                    "Send /cancel to abort.",
                    quote=True
                )

            except PhoneCodeInvalid:
                await message.reply(
                    "❌ **Wrong OTP!** Please try again.\n\n"
                    "📲 **Send the correct OTP:**",
                    quote=True
                )

            except FloodWait as e:
                await message.reply(
                    f"⚠️ **Flood wait!**\n"
                    f"Wait **{e.value} seconds**.\n\n"
                    "Send /cancel and try /login later.",
                    quote=True
                )
                try:
                    await temp_client.stop()
                except:
                    pass
                del login_pending[user_id]

            except Exception as e:
                await message.reply(
                    f"❌ **Error:** `{e}`\n\n"
                    "Send /cancel and try /login again.",
                    quote=True
                )
                try:
                    await temp_client.stop()
                except:
                    pass
                del login_pending[user_id]
            return

        # ── STEP 3: 2FA Password ──
        elif step == "waiting_2fa":
            password = text.strip()
            temp_client = pending.get("client")

            try:
                await temp_client.check_password(password)

                user_clients[user_id] = temp_client
                del login_pending[user_id]

                me = await temp_client.get_me()
                name = me.first_name or "User"

                await message.reply(
                    "✅ **Login Successful!**\n\n"
                    f"👤 **Welcome, {name}!**\n"
                    f"📱 **Phone:** `+{me.phone_number}`\n\n"
                    "You can now access **private channel** content!\n"
                    "Send any private channel link now.\n\n"
                    "Use /logout to logout anytime.",
                    quote=True
                )

            except PasswordHashInvalid:
                await message.reply(
                    "❌ **Wrong password!** Try again.\n\n"
                    "📲 **Send correct 2FA password:**",
                    quote=True
                )

            except FloodWait as e:
                await message.reply(
                    f"⚠️ **Flood wait!**\n"
                    f"Wait **{e.value} seconds**.\n\n"
                    "Send /cancel and try /login later.",
                    quote=True
                )
                try:
                    await temp_client.stop()
                except:
                    pass
                del login_pending[user_id]

            except Exception as e:
                await message.reply(
                    f"❌ **Error:** `{e}`\n\n"
                    "Send /cancel and try /login again.",
                    quote=True
                )
                try:
                    await temp_client.stop()
                except:
                    pass
                del login_pending[user_id]
            return

    # ─── LINK HANDLER ───
    if "t.me/" not in text:
        await message.reply(
            "⚠️ **Send a valid Telegram link.**\n\n"
            "Example:\n"
            "• `https://t.me/channelname/123`\n"
            "• `https://t.me/c/1234567890/123`\n\n"
            "Use /help for more info.",
            quote=True
        )
        return

    chat_target, msg_id, is_private = parse_link(text)

    if chat_target is None:
        await message.reply(
            "❌ **Could not parse this link.**\n\n"
            "Make sure it is a valid message link.",
            quote=True
        )
        return

    # ── Private Link ──
    if is_private:
        user_client = await get_user_client(user_id)

        if not user_client:
            await message.reply(
                "🔒 **This is a Private Channel Link!**\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "To access private channel content,\n"
                "you need to login first.\n\n"
                "📌 **Steps:**\n"
                "1️⃣ Send /login\n"
                "2️⃣ Enter phone: `+91 9876543210`\n"
                "3️⃣ Enter OTP: `1 2 3 4 5`\n"
                "4️⃣ Enter 2FA password if enabled\n"
                "5️⃣ Send the link again ✅\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "You must be a **member** of that\n"
                "private channel on your account.",
                quote=True
            )
            return

        status = await message.reply(
            "⏳ Fetching from private channel...",
            quote=True
        )
        await fetch_and_send(
            message, status, user_client, chat_target, msg_id
        )

    # ── Public Link ──
    else:
        status = await message.reply(
            "⏳ Fetching from public channel...",
            quote=True
        )

        try:
            await fetch_and_send(
                message, status, bot, chat_target, msg_id
            )

        except ChannelPrivate:
            user_client = await get_user_client(user_id)
            if user_client:
                await status.edit(
                    "🔒 Private channel detected,\n"
                    "trying with your account..."
                )
                await fetch_and_send(
                    message, status, user_client, chat_target, msg_id
                )
            else:
                await status.edit(
                    "🔒 **This channel is private!**\n\n"
                    "Use /login to access private content."
                )

        except Exception as e:
            user_client = await get_user_client(user_id)
            if user_client:
                await status.edit("🔄 Retrying with your account...")
                await fetch_and_send(
                    message, status, user_client, chat_target, msg_id
                )
            else:
                await status.edit(f"❌ **Error:** `{e}`")
                # ═══════════════════════════════════════
#   CORE FETCH & SEND FUNCTION
# ═══════════════════════════════════════

async def fetch_and_send(
    message: Message,
    status,
    fetch_client: Client,
    chat_target,
    msg_id: int
):
    file_path = None
    try:
        msg = await fetch_client.get_messages(chat_target, msg_id)

        if not msg or msg.empty:
            await status.edit("❌ **Message not found or deleted.**")
            return

        # ── Text Only ──
        if not msg.media:
            if msg.text:
                await message.reply(msg.text)
                await status.delete()
            else:
                await status.edit("❌ **No content in this message.**")
            return

        # ── Media ──
        await status.edit("⬇️ Downloading...")
        file_path = await fetch_client.download_media(msg)

        if not file_path:
            await status.edit("❌ **Failed to download media.**")
            return

        await status.edit("⬆️ Uploading...")
        caption = msg.caption or ""
        chat_id = message.chat.id

        if msg.photo:
            await bot.send_photo(chat_id, file_path, caption=caption)
        elif msg.video:
            await bot.send_video(chat_id, file_path, caption=caption)
        elif msg.document:
            await bot.send_document(chat_id, file_path, caption=caption)
        elif msg.audio:
            await bot.send_audio(chat_id, file_path, caption=caption)
        elif msg.voice:
            await bot.send_voice(chat_id, file_path, caption=caption)
        elif msg.video_note:
            await bot.send_video_note(chat_id, file_path)
        elif msg.sticker:
            await bot.send_sticker(chat_id, file_path)
        elif msg.animation:
            await bot.send_animation(chat_id, file_path, caption=caption)
        else:
            await bot.send_document(chat_id, file_path, caption=caption)

        await status.delete()

    except ChannelPrivate:
        await status.edit(
            "🔒 **Private channel!**\n\n"
            "Make sure your account is a\n"
            "member of this channel."
        )
    except UserNotParticipant:
        await status.edit(
            "❌ **Not a member!**\n\n"
            "Your account is not a member\n"
            "of this channel.\n"
            "Join the channel first, then try again."
        )
    except FloodWait as e:
        await status.edit(
            f"⚠️ **Flood wait!**\n"
            f"Please wait **{e.value} seconds**."
        )
    except Exception as e:
        await status.edit(f"❌ **Error:** `{e}`")

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass


# ═══════════════════════════════════════
#         FLASK KEEP ALIVE
# ═══════════════════════════════════════

web = Flask("")


@web.route("/")
def home():
    return "Bot is alive!"


def run_web():
    web.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )


# ═══════════════════════════════════════
#         MAIN ASYNC FUNCTION
# ═══════════════════════════════════════

async def main():
    os.makedirs("downloads", exist_ok=True)

    # Flask alag thread me
    Thread(target=run_web, daemon=True).start()
    print("Flask server started.")

    # Bot start karo
    await bot.start()
    print("Bot is LIVE!")
    print("Send any Telegram link to get content!")

    # Bot ko chalta rakho
    await idle()

    # Shutdown pe sab user sessions band karo
    print("Stopping all user sessions...")
    for uid, uclient in list(user_clients.items()):
        try:
            await uclient.stop()
        except:
            pass

    await bot.stop()
    print("Bot stopped.")


# ═══════════════════════════════════════
#         ENTRY POINT
# ═══════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(main())
