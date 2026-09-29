"""Buttons, styles and screen copy for the bot.

Telegram renders coloured inline buttons — **blue** (``primary``), **green**
(``success``) and **red** (``danger``) — since Bot API 9.4 / MTProto layer 222.
Kurigram (the pyrofork/pyrogram fork used by this bot) exposes them through
:class:`pyrogram.enums.ButtonStyle`; older pyrogram builds do not know the
parameter at all.

Everything in this module therefore goes through :func:`button`, which:

* uses the native colour when the installed library supports it, and
* silently falls back to a plain (transparent) button when it does not.

``BUTTON_STYLES=off`` in the environment forces plain buttons, ``BUTTON_STYLES=auto``
(the default) enables them whenever the library can render them.

This module is deliberately free of bot/state/DB logic so that it can be unit
tested on its own.
"""

from __future__ import annotations

import inspect
import os
import re

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

try:  # kurigram / newer pyrogram builds
    from pyrogram.enums import ButtonStyle
except Exception:  # pragma: no cover - legacy pyrogram/pyrofork
    ButtonStyle = None

try:  # custom-text ("copy") buttons, layer 178+
    from pyrogram.types import CopyTextButton
except Exception:  # pragma: no cover - legacy pyrogram/pyrofork
    CopyTextButton = None


# --------------------------------------------------------------------------- #
#  Unicode small-caps font engine
#
#  Every visible piece of UI text — headings, screen copy and inline button
#  labels — is rendered through :func:`smallcaps`.  The conversion is
#  deliberately context aware: URLs, @mentions, /commands, ``code`` spans and
#  HTML tags are copied through untouched, so links stay clickable, mentions
#  stay valid and callback_data never changes.
#
#  ``SMALL_CAPS=off`` in the environment disables the font (handy while
#  debugging); ``SMALL_CAPS=auto`` — the default — keeps it enabled.
# --------------------------------------------------------------------------- #

#: The documented letter mapping (numbers and symbols are always untouched).
SMALL_CAPS_MAP = {
    "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ғ", "G": "ɢ",
    "H": "ʜ", "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ", "M": "ᴍ", "N": "ɴ",
    "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ", "S": "s", "T": "ᴛ", "U": "ᴜ",
    "V": "ᴠ", "W": "ᴡ", "X": "x", "Y": "ʏ", "Z": "ᴢ",
}

#: Letters are case insensitive: "Hello" and "HELLO" both render as "ʜᴇʟʟᴏ".
SMALL_CAPS_TABLE = str.maketrans({
    **SMALL_CAPS_MAP,
    **{letter.lower(): glyph for letter, glyph in SMALL_CAPS_MAP.items()},
})

#: Inverse table, used to fold rendered text back to plain ASCII.
PLAIN_TABLE = str.maketrans({glyph: letter.lower() for letter, glyph in SMALL_CAPS_MAP.items()})

#: Regions that must survive the conversion byte for byte.
PROTECTED_PATTERNS = (
    r"`[^`]*`",                                                  # `inline code`
    r"<[^<>]*>",                                                 # <b>HTML</b>
    r"&[A-Za-z][A-Za-z0-9]*;|&#\d+;|&#[xX][0-9A-Fa-f]+;",         # &lt; &amp; entities
    r"(?:https?|ftps?|tg|mailto)://\S*",                         # https:// t.me/ tg://
    r"www\.\S*",                                                # www.example.com
    r"(?:t|telegram)\.me(?:/\S*)?",                              # bare t.me/channel/1
    r"(?<![\w@/])@[A-Za-z0-9_]{3,}",                             # @username / @channel
    r"(?<![\w/])/[A-Za-z][A-Za-z0-9_]*(?:@[A-Za-z0-9_]+)?",      # /command, /command@bot
    r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}",                          # e-mail addresses
)
PROTECTED_RE = re.compile("|".join(PROTECTED_PATTERNS))


def small_caps_enabled() -> bool:
    """True unless ``SMALL_CAPS=off`` was requested in the environment."""
    return os.environ.get("SMALL_CAPS", "auto").strip().lower() not in {
        "0", "off", "false", "no", "plain", "disable", "disabled",
    }


def smallcaps(text: str) -> str:
    """Render *text* in the Unicode small-caps font.

    Letters become small capitals, digits and punctuation are untouched, and
    URLs / @mentions / /commands / ``code`` / HTML tags are preserved exactly.
    The function is idempotent, so text may safely pass through it twice.
    """
    if not text or not isinstance(text, str):
        return text
    if not small_caps_enabled():
        return text

    pieces = []
    position = 0
    for match in PROTECTED_RE.finditer(text):
        pieces.append(text[position:match.start()].translate(SMALL_CAPS_TABLE))
        pieces.append(match.group(0))
        position = match.end()
    pieces.append(text[position:].translate(SMALL_CAPS_TABLE))
    return "".join(pieces)


#: Short alias used all over the bot code.
sc = smallcaps


def plain_caps(text: str) -> str:
    """Fold small-cap glyphs back to plain lowercase ASCII (search, logs, tests)."""
    if not text or not isinstance(text, str):
        return text
    return text.translate(PLAIN_TABLE)


#: Human readable meaning of every style (used in docs, logs and tests).
STYLE_COLORS = {
    "primary": "blue",
    "success": "green",
    "danger": "red",
}

#: Styles understood by :func:`button`.
VALID_STYLES = tuple(STYLE_COLORS)

_ENUM_BY_NAME = {}
if ButtonStyle is not None:  # pragma: no cover - depends on installed library
    _ENUM_BY_NAME = {
        "primary": getattr(ButtonStyle, "PRIMARY", None),
        "success": getattr(ButtonStyle, "SUCCESS", None),
        "danger": getattr(ButtonStyle, "DANGER", None),
    }


def _env_mode() -> str:
    return os.environ.get("BUTTON_STYLES", "auto").strip().lower()


def native_style_support() -> bool:
    """True when the installed Telegram library can send coloured buttons."""
    if ButtonStyle is None or not all(_ENUM_BY_NAME.values()):
        return False
    try:
        params = inspect.signature(InlineKeyboardButton.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - exotic builds
        return False
    return "style" in params


def styles_enabled() -> bool:
    """True when :func:`button` should attach a colour to styled buttons."""
    mode = _env_mode()
    if mode in {"0", "off", "false", "no", "plain"}:
        return False
    return native_style_support()


def style_support_label() -> str:
    """Short human readable status, handy for startup logs."""
    if styles_enabled():
        return "native (blue/green/red)"
    if native_style_support():
        return "disabled by BUTTON_STYLES"
    return "unavailable (library without ButtonStyle) - using plain buttons"


def button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    copy_text: str | None = None,
    switch_inline_query: str | None = None,
) -> InlineKeyboardButton | None:
    """Build an inline button, colouring it when Telegram/library allow it.

    The visible label is rendered in the Unicode small-caps font; only the
    label is touched — ``callback_data``, ``url`` and ``copy_text`` payloads are
    never converted.

    ``style`` is one of ``primary`` (blue), ``success`` (green) or ``danger``
    (red).  Returns ``None`` for buttons that the installed library cannot
    build (for example a copy button on an old pyrogram) so callers can drop
    them from their keyboard rows.
    """
    kwargs: dict = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    elif url is not None:
        kwargs["url"] = url
    elif switch_inline_query is not None:
        kwargs["switch_inline_query"] = switch_inline_query
    elif copy_text is not None:
        if CopyTextButton is None:
            return None
        kwargs["copy_text"] = CopyTextButton(text=copy_text)

    if style:
        style = style.lower()
        if style not in VALID_STYLES:
            raise ValueError(f"unknown button style: {style!r}")
        if styles_enabled():
            kwargs["style"] = _ENUM_BY_NAME[style]

    if not kwargs:
        raise ValueError("button() needs a callback_data, url, copy_text or switch_inline_query")
    return InlineKeyboardButton(smallcaps(text), **kwargs)


def keyboard(rows, *, filter_empty: bool = True) -> InlineKeyboardMarkup:
    """Assemble rows of buttons, dropping rows that resolved to no buttons."""
    built = []
    for row in rows:
        buttons = [b for b in row if b is not None]
        if buttons or not filter_empty:
            built.append(buttons)
    return InlineKeyboardMarkup(built)


def home_button() -> InlineKeyboardButton:
    return button("🏠 Main Menu", callback_data="home", style="primary")


def back_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[home_button()]])


def close_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[button("❌ Close", callback_data="close", style="danger")]])


def premium_upsell_keyboard() -> InlineKeyboardMarkup:
    """The dual call to action shown on private-access and daily-limit screens.

    One single row with two buttons, in this order:

    ``[ 💎 Buy Premium ]`` → ``/premium`` plans view (``cmd_premium``)
    ``[ 🎁 Earn Points ]`` → ``/refer`` rewards view (``cmd_refer``)
    """
    return keyboard([[
        button("💎 Buy Premium", callback_data="cmd_premium", style="success"),
        button("🎁 Earn Points", callback_data="cmd_refer", style="primary"),
    ]])


#: Backwards friendly alias — same keyboard, kept for callers using the old name.
upsell_keyboard = premium_upsell_keyboard


def private_access_keyboard() -> InlineKeyboardMarkup:
    return premium_upsell_keyboard()


def daily_limit_keyboard() -> InlineKeyboardMarkup:
    return premium_upsell_keyboard()


def setchat_check_keyboard() -> InlineKeyboardMarkup:
    """Verification step of the channel-dump (/setchat) flow."""
    return keyboard([
        [button("🔍 Check Admin Status", callback_data="setchat:check", style="primary")],
        [button("❌ Cancel", callback_data="cancel_action", style="danger")],
    ])


def premium_tier_keyboard() -> InlineKeyboardMarkup:
    """Owner choice between public-only and full premium access."""
    return keyboard([
        [
            button("🌐 Public Only", callback_data="premium_tier:public", style="primary"),
            button("🔓 Full (Public + Private)", callback_data="premium_tier:full", style="success"),
        ],
        [button("❌ Cancel", callback_data="cancel_action", style="danger")],
    ])


def payment_review_keyboard(user_id: int, plan: str | None = None) -> InlineKeyboardMarkup:
    """Owner-only approve / fake / ban buttons attached to a payment proof."""
    plan_part = f":{plan}" if plan else ""
    return keyboard([
        [
            button("✅ Approve", callback_data=f"payok:{user_id}{plan_part}", style="success"),
            button("⚠️ Fake", callback_data=f"payfake:{user_id}", style="danger"),
        ],
        [button("🚫 Ban User", callback_data=f"payban:{user_id}", style="danger")],
    ])


def start_keyboard(show_admin: bool = False) -> InlineKeyboardMarkup:
    """Main menu of /start — every button runs its action directly."""
    return keyboard([
        [
            button("🔐 Login", callback_data="cmd_login", style="success"),
            button("🚪 Logout", callback_data="cmd_logout", style="danger"),
        ],
        [
            button("⚙️ Settings", callback_data="cmd_settings", style="primary"),
            button("📊 Stats", callback_data="cmd_stats", style="primary"),
        ],
        [
            button("💎 Premium", callback_data="cmd_premium", style="success"),
            button("🎁 Refer", callback_data="cmd_refer", style="primary"),
        ],
        [
            button("📖 Help", callback_data="cmd_help", style="primary"),
            button("💬 Feedback", callback_data="cmd_feedback", style="primary"),
        ],
        [
            button("🌐 Language", callback_data="cmd_language", style="primary"),
            button("📡 Set channel", callback_data="cmd_setchat", style="primary"),
        ],
    ] + ([[button("🛠 Admins", callback_data="cmd_admin", style="primary")]] if show_admin else []))


def settings_keyboard(notifications: bool, silent: bool) -> InlineKeyboardMarkup:
    notif_label = "🔔 Notifications: ON" if notifications else "🔕 Notifications: OFF"
    silent_label = "🌙 Silent mode: ON" if silent else "🔊 Silent mode: OFF"
    return keyboard([
        [button(notif_label, callback_data="toggle_notif", style="primary")],
        [button(silent_label, callback_data="toggle_silent", style="primary")],
        [button("🌐 Language", callback_data="cmd_language", style="primary")],
        [button("🔄 Reset all", callback_data="reset_settings", style="danger")],
        [home_button()],
        [button("❌ Close", callback_data="close", style="danger")],
    ])


def language_keyboard(current: str = "en") -> InlineKeyboardMarkup:
    current = (current or "en").lower()

    def lang_button(code: str, label: str):
        selected = code == current
        text = f"✅ {label}" if selected else label
        return button(text, callback_data=f"lang_{code}", style="success" if selected else "primary")

    return keyboard([
        [lang_button("en", "🇬🇧 English")],
        [lang_button("hi", "🇮🇳 Hindi")],
        [home_button()],
    ])


def login_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[button("❌ Cancel login", callback_data="cancel_login", style="danger")]])


def logout_keyboard() -> InlineKeyboardMarkup:
    """Shown after a successful logout (and when the user was not logged in)."""
    return keyboard([
        [button("🔐 Login", callback_data="cmd_login", style="success")],
        [home_button()],
    ])


def feedback_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[button("❌ Cancel", callback_data="cancel_action", style="danger")]])


def stats_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("ℹ️ My info", callback_data="cmd_myinfo", style="primary")],
        [home_button()],
    ])


def premium_keyboard(is_premium: bool, owner_id: int | None = None) -> InlineKeyboardMarkup:
    """Compatibility entry point for the current benefits-first flow."""
    return premium_overview_keyboard(owner_id)


def refer_keyboard(link: str) -> InlineKeyboardMarkup:
    """Share + copy buttons for the referral link."""
    rows = [
        [button(
            "📤 Share link",
            url=f"https://t.me/share/url?url={link}&text=Save restricted Telegram content with this bot!",
            style="success",
        )],
        [button("📋 Copy link", copy_text=link, style="primary")],
        [home_button()],
    ]
    return keyboard(rows)


def help_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("🔐 Login", callback_data="cmd_login", style="success"),
         button("💎 Premium", callback_data="cmd_premium", style="success")],
        [button("⚙️ Settings", callback_data="cmd_settings", style="primary"),
         button("💬 Feedback", callback_data="cmd_feedback", style="primary")],
        [home_button()],
    ])


def fsub_keyboard(channel: str) -> InlineKeyboardMarkup:
    handle = channel.replace("@", "")
    return keyboard([
        [button("📢 Join channel", url=f"https://t.me/{handle}", style="primary")],
        [button("✅ I joined", callback_data="check_fsub", style="success")],
    ])


def download_controls(job_id: str, paused: bool = False) -> InlineKeyboardMarkup:
    """Pause/stop controls attached to an active download."""
    toggle = (
        button("▶️ Resume", callback_data=f"dl:r:{job_id}", style="success")
        if paused
        else button("⏸ Pause", callback_data=f"dl:p:{job_id}", style="primary")
    )
    return keyboard([[toggle, button("⛔ Stop", callback_data=f"dl:s:{job_id}", style="danger")]])


# --------------------------------------------------------------------------- #
#  Screen copy
# --------------------------------------------------------------------------- #

def start_text(name: str, premium: bool) -> str:
    badge = "💎 Premium" if premium else "🆓 Free"
    return (
        f"👋 **Hello {name}!**\n\n"
        f"🤖 **Restricted Content Saver Bot**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎖 **Status:** {badge}\n\n"
        f"📌 Send any Telegram link to save content!\n"
        f"🆓 Free: **3 public extractions daily**. No referrals needed.\n"
        f"🔐 Private links require **owner-granted premium** and login.\n\n"
        f"All buttons below work instantly — no commands needed.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def help_text() -> str:
    return (
        "📖 **HELP MENU**\n\n"
        "**🔐 Account:**\n"
        "Login / Logout / Status — use the buttons below\n\n"
        "**📥 Download:**\n"
        "Send a link or a range: `t.me/ch/1-20`\n\n"
        "**🎨 Customization:**\n"
        "/setcaption /delcaption\n"
        "/setthumb /delthumb\n"
        "/setprefix /setsuffix\n\n"
        "**📊 Info:**\n"
        "/mystats /myinfo /history /status\n\n"
        "**⚙️ Settings:**\n"
        "Notifications, silent mode and language\n\n"
        "**🎁 Extra:**\n"
        "/refer /bookmark /bookmarks\n"
        "/favorite /favorites /share /feedback /premium /redeem\n\n"
        "👑 Owner & admins: /admin or /admins. Commands and inline buttons both work."
    )


def settings_text() -> str:
    return (
        "⚙️ **SETTINGS**\n\n"
        "Tap a switch to change it — the menu updates instantly."
    )


def language_text(current: str = "en") -> str:
    names = {"en": "🇬🇧 English", "hi": "🇮🇳 Hindi"}
    current = (current or "en").lower()
    return (
        "🌐 **LANGUAGE**\n\n"
        f"Current: **{names.get(current, current)}**\n\n"
        "Pick a language below:"
    )


def login_text() -> str:
    return (
        "🔐 **LOGIN**\n\n"
        "Send your phone number with country code:\n"
        "Example: `+91 9876543210`\n\n"
        "Press ❌ Cancel login to abort."
    )


def login_pending_text() -> str:
    return (
        "⏳ **Login already in progress.**\n\n"
        "Send your phone number, or press ❌ Cancel login."
    )


def already_logged_in_text() -> str:
    return "✅ **Already logged in!**\n\nPress 🚪 Logout first if you want to switch account."


def logout_done_text(phone: str | None) -> str:
    number = f"`+{phone}`" if phone else "`Unknown`"
    return (
        "✅ **Logged out!**\n\n"
        f"📱 {number}\n\n"
        "Your session was removed from the server."
    )


def logout_none_text() -> str:
    return "ℹ️ **You are not logged in.**\n\nPress 🔐 Login to connect your account."


def feedback_text() -> str:
    return (
        "💬 **FEEDBACK**\n\n"
        "Send your feedback, bug report or suggestion as the next message.\n\n"
        "Send any new command or tap another menu to cancel automatically. You can also press ❌ Cancel."
    )


def premium_text(premium: bool, expiry=None, owner_id: int | None = None) -> str:
    """Compatibility entry point; keep legacy screens consistent."""
    return premium_overview(premium, {"premium_expiry": expiry})


def refer_text(link: str, count: int, points: int | None = None) -> str:
    """Referral screen copy — the single source of truth for /refer."""
    from config import (REDEEM_LIMITATION, REDEEM_POINTS, REDEEM_PREMIUM_MONTHS, REFER_POINTS)
    points = count * REFER_POINTS if points is None else points
    filled = min(10, points * 10 // REDEEM_POINTS)
    bar = "█" * filled + "░" * (10 - filled)
    return (
        "🎁 **REFERRALS & REWARDS**\n\n"
        f"👥 Referrals: {count}\n"
        f"⭐ **Points: {points} / {REDEEM_POINTS}**\n"
        f"🎉 Each new friend earns you **{REFER_POINTS} points**.\n"
        f"💎 Redeem **{REDEEM_POINTS} points** for **{REDEEM_PREMIUM_MONTHS} month** of public-only premium.\n"
        "Only new users joining through your link count, once each.\n"
        f"Progress: {bar}\n"
        f"Your link: {link}\n\n{REDEEM_LIMITATION}"
    )


def personal_stats_text(user: dict, premium: bool) -> str:
    badge = "💎 Premium" if premium else "🆓 Free"
    joined = user.get("joined_date")
    joined = joined.strftime("%d %b %Y") if hasattr(joined, "strftime") else "—"
    return (
        f"📊 **YOUR STATS**\n\n"
        f"👤 {user.get('name') or 'Unknown'}\n"
        f"🎖 Status: {badge}\n"
        f"📥 Total downloads: {user.get('downloads', 0)}\n"
        f"📅 Today: {user.get('daily_downloads', 0)}\n"
        f"👥 Referrals: {user.get('referral_count', 0)}\n"
        f"📆 Joined: {joined}"
    )


def fsub_text(channel: str) -> str:
    return (
        f"⚠️ **You must join {channel} first!**\n\n"
        "You can use this bot only while you remain joined to the channel.\n\n"
        "📢 Join now, then tap **I joined** to verify. Membership is checked again when you extract content."
    )


def feedback_saved_text() -> str:
    return "✅ **Feedback sent!**\n\nThanks a lot, it really helps."


def feedback_link_warning() -> str:
    """Shown when a feedback message contains a URL; the message is rejected."""
    from config import FEEDBACK_LINK_WARNING
    return FEEDBACK_LINK_WARNING


# --------------------------------------------------------------------------- #
#  Private access, daily limit and premium tiers
# --------------------------------------------------------------------------- #

def private_access_text() -> str:
    """Shown whenever a private/restricted link needs owner-granted premium."""
    return (
        "🔒 **Private Channel Access (Premium Only)**\n\n"
        "Private channel and restricted group extraction is available exclusively for Premium users.\n\n"
        "Upgrade to Premium or refer friends to earn points!"
    )


def daily_limit_text(limit: int | None = None, used: int | None = None) -> str:
    """Detailed reason why the free daily quota is exhausted."""
    from config import DAILY_RESET_LABEL, FREE_DAILY_LIMIT
    limit = FREE_DAILY_LIMIT if limit is None else limit
    used = limit if used is None else used
    return (
        "🚫 **Daily Free Limit Reached**\n\n"
        f"🆓 Free accounts get **{limit} public extractions per day** — that quota is used up "
        f"(**{used}/{limit}** used today).\n\n"
        f"🕛 The free quota resets every day at **{DAILY_RESET_LABEL}**.\n"
        "💎 Premium members extract without any daily limit.\n\n"
        "💎 **Buy Premium** for unlimited extractions.\n"
        "🎁 **Earn Points** to unlock free premium through referrals."
    )


def premium_tier_text(user_id, days, name: str | None = None) -> str:
    """Owner prompt: which premium tier should this user get?"""
    who = f"👤 {name} · `{user_id}`\n\n" if name else ""
    return (
        f"Select Premium Access Tier for User `{user_id}` ({days} days):\n\n"
        f"{who}"
        "🌐 **Public Only** — unlimited public extractions, private links stay blocked.\n"
        "🔓 **Full (Public + Private)** — public *and* private/restricted extraction.\n\n"
        "👑 Only the owner can grant full private access."
    )


def premium_tier_granted_text(user_id, days, tier: str, name: str | None = None) -> str:
    """Owner confirmation after a tier was picked."""
    label = "🌐 Public Only" if tier == "public" else "🔓 Full (Public + Private)"
    access = ("Public channels only — private links stay blocked."
              if tier == "public" else "Public + private channels (owner-granted).")
    return (
        "💎 **Premium activated**\n\n"
        f"👤 User: {name or 'User'} · `{user_id}`\n"
        f"📅 Duration: **{days} days**\n"
        f"🎖 Access: **{label}**\n"
        f"🔐 Scope: {access}"
    )


def premium_activated_user_text(days, tier: str = "full", plan: str | None = None) -> str:
    """Notification the user receives after their premium is activated."""
    header = f"🎉 **{plan}**\n\n" if plan else "🎉 **PREMIUM ACTIVATED!**\n\n"
    if tier == "public":
        return (
            f"{header}"
            f"📅 Your plan is active for **{days} days**.\n"
            "✅ Unlimited public extractions\n"
            "✅ No extraction watermark\n"
            "🔒 Private channels are **not** included in this tier.\n\n"
            "Ask the owner if you need full private access. Open /premium to see your status."
        )
    return (
        f"{header}"
        f"📅 Your plan is active for **{days} days**.\n"
        "✅ Unlimited public extractions\n"
        "✅ No extraction watermark\n"
        "🔐 Private links are now enabled. Use /login with an account authorized to view the channel.\n\n"
        "Open /premium to see your status."
    )


def payment_approved_user_text(plan_title: str | None, days: int | None) -> str:
    detail = f"\n\n📦 {plan_title} • {days} days of full access" if plan_title and days else ""
    return "🎉 Payment Approved! Your premium has been activated." + detail


def payment_rejected_user_text() -> str:
    return "❌ Payment Rejected! Your payment screenshot was marked as fake/invalid."


def payment_banned_user_text() -> str:
    return ("🚫 You have been banned from this bot.\n\n"
            "Reason: Submitting fraudulent payment proof.")


def payment_review_caption(base: str | None, status_line: str) -> str:
    """Append a review verdict to the original payment-review caption."""
    base = (base or "").strip()
    return f"{base}\n\n{status_line}" if base else status_line


APPROVED_CAPTION = "✅ Approved by Owner"
REJECTED_CAPTION = "❌ Rejected by Owner — marked as fake/invalid"
BANNED_CAPTION = "🚫 Banned — fraudulent payment proof"


# --------------------------------------------------------------------------- #
#  Channel dump (/setchat)
# --------------------------------------------------------------------------- #

def setchat_prompt_text() -> str:
    return (
        "📡 **CHANNEL DUMP SETUP**\n\n"
        "Send me the channel where you added me as an admin — link, @username or numeric ID.\n\n"
        "Example: `https://t.me/mychannel` or `@mychannel` or `-1001234567890`\n\n"
        "I verify my admin rights before enabling automatic extraction. Use /cancel to stop."
    )


def setchat_admin_hint_text(title: str) -> str:
    return (
        f"🏁 **Channel:** {title}\n\n"
        "Tap **🔍 Check Admin Status** so I can verify that I am an administrator there with the "
        "**Post Messages** permission."
    )


def setchat_admin_ok_text(title: str) -> str:
    return (
        f"✅ **Admin verified in {title}!**\n\n"
        "Final step: send a sample message link from this channel "
        "(for example `https://t.me/mychannel/15`) so I can verify that I can read its content."
    )


def setchat_admin_failed_text() -> str:
    return (
        "❌ **Admin check failed**\n\n"
        "I am not an administrator of that channel, or I cannot post messages there.\n\n"
        "👉 Open the channel → **Administrators** → **Add Admin** → select this bot and enable "
        "**Post Messages**, then tap **🔍 Check Admin Status** again."
    )


def setchat_done_text(title: str, chat_id) -> str:
    return (
        "✅ **Channel dump enabled**\n\n"
        f"🏁 {title}\n🆔 `{chat_id}`\n\n"
        "Send any Telegram link in that channel and I extract it directly there, following the same "
        "public / premium rules as in private chat.\n\n"
        "🛡 Requests are rate limited and FloodWait pauses are handled safely."
    )


def setchat_sample_failed_text() -> str:
    return (
        "❌ **Verification failed**\n\n"
        "That sample link could not be read. Make sure the message exists in the channel, that it is "
        "not deleted, and send the link again (for example `https://t.me/mychannel/15`)."
    )


def setchat_usage_text() -> str:
    return ("Usage: `/setchat t.me/mychannel` — or use the **📡 Set channel** button in "
            "/admin to be guided step by step.")


def channel_not_found_text() -> str:
    from config import CHANNEL_CLEANUP_SECONDS
    return ("❌ Message not found.\n\n"
            f"🕛 This notice is removed automatically in {CHANNEL_CLEANUP_SECONDS} seconds "
            "to keep the channel clean.")


def channel_floodwait_text(seconds) -> str:
    return (f"⏳ Telegram rate limit reached. Pausing safely for **{seconds}s** before continuing…")


def feedback_cancelled_text() -> str:
    return "❌ **Feedback cancelled.**"


def login_cancelled_text() -> str:
    return "❌ **Login cancelled.**"


def action_cancelled_text() -> str:
    return "❌ **Action cancelled.**"


def nothing_to_cancel_text() -> str:
    return "ℹ️ **Nothing to cancel.**"


def stale_button_text() -> str:
    return (
        "⚠️ **This button is out of date.**\n\n"
        "Send /start to reload the menu."
    )


# Keep headings styled with Telegram formatting rather than replacing letters
# with inaccessible Unicode lookalikes. Button labels stay short on mobile.
def premium_overview(premium, user):
    from config import (FREE_DAILY_LIMIT, PREMIUM_PLANS, PREMIUM_SOURCE_PUBLIC,
                        PREMIUM_SOURCE_REDEEM, REDEEM_LIMITATION)
    title = "💎 **PREMIUM ACTIVE**" if premium else "💎 **PREMIUM BENEFITS**"
    expiry = user.get("premium_expiry")
    status = f"\n📅 Valid until: **{expiry:%d %b %Y}**" if premium and expiry else ""
    source = user.get("premium_source")
    if source == PREMIUM_SOURCE_REDEEM:
        access = REDEEM_LIMITATION
    elif premium and source == PREMIUM_SOURCE_PUBLIC:
        access = "Public channels only — this grant does not include private or restricted links."
    else:
        access = ("Private-channel access requires premium manually granted by the owner and your own "
                  "authorized Telegram session. Payment screenshots alone do not unlock it.")
    prices = "\n".join(f"• **₹{p['price']}** / {p['title']}" for p in PREMIUM_PLANS.values())
    return (f"{title}{status}\n\n"
            "✨ **What you get**\n"
            "✅ Unlimited downloads from public channels\n"
            "✅ Up to 2 GB per file\n"
            "✅ No extraction watermark\n"
            "✅ Priority support\n\n"
            f"💰 **Available plans**\n{prices}\n\n"
            f"🔐 **Access policy**\n{access}\n\n"
            f"🆓 Free users get **{FREE_DAILY_LIMIT} public extractions daily** — no referrals required.\n\n"
            "👇 Tap **Buy Plan** to choose a duration. You will see the payment QR before submitting proof.")


def premium_overview_keyboard(owner_id=None):
    return keyboard([
        [button("🛍 Buy Plan", callback_data="premium_plans", style="success")],
        [button("🎁 Earn Points", callback_data="cmd_refer", style="primary"), home_button()],
    ] + ([[button("💬 Contact owner", url=f"tg://user?id={owner_id}", style="primary")]] if owner_id else []))


def plans_text():
    """Plan list — built from config.PREMIUM_PLANS so prices never drift."""
    from config import PAYMENT_CONTACT, PREMIUM_PLANS, RUPEE
    icons = ("💎", "🌟", "👑")
    lines = "\n".join(
        f"{icons[index % len(icons)]} **{plan['title']} — {RUPEE}{plan['price']}**"
        for index, plan in enumerate(PREMIUM_PLANS.values())
    )
    return ("🛍 **CHOOSE YOUR PLAN**\n\n"
            f"{lines}\n\n"
            "📲 Select a plan to view the owner's QR. Pay the exact amount, tap **I've paid**, then upload a screenshot.\n\n"
            f"🔎 All payments are checked manually by @{PAYMENT_CONTACT} before activation.")


def plans_keyboard():
    from config import PREMIUM_PLANS
    return keyboard([
        [button(f"{p['title']} · ₹{p['price']}", callback_data=f"buy:{key}", style="success")]
        for key, p in PREMIUM_PLANS.items()
    ] + [[button("⬅️ Benefits", callback_data="cmd_premium", style="primary"), home_button()]])


def payment_text(plan):
    from config import PAYMENT_CONTACT, RUPEE
    return (f"💳 **PAYMENT DETAILS**\n\n📦 Plan: **{plan['title']}**\n💰 Amount: **{RUPEE}{plan['price']}**\n\n"
            "① Scan this QR in your payment app.\n"
            "② Check the recipient and pay the exact amount.\n"
            "③ Save a screenshot showing the successful transaction.\n"
            "④ Tap **I've paid** below, then send the screenshot here.\n\n"
            f"👤 Payment review: @{PAYMENT_CONTACT}\n"
            "⏳ Premium starts only after owner verification. Never share your PIN or OTP.")


def payment_keyboard(token):
    return keyboard([
        [button("✅ I've paid", callback_data=f"paid:{token}", style="success")],
        [button("⬅️ Plans", callback_data="premium_plans", style="primary"),
         button("❌ Cancel", callback_data="cancel_action", style="danger")],
    ])


def admin_back_keyboard():
    return keyboard([[button("🛠 Admins", callback_data="cmd_admin", style="primary"), home_button()]])


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


def split_text(text, limit):
    """Split Telegram text without losing content or breaking non-BMP characters."""
    chunk, size = [], 0
    for char in text:
        width = 2 if ord(char) > 0xFFFF else 1
        if size + width > limit:
            yield "".join(chunk)
            chunk, size = [], 0
        chunk.append(char)
        size += width
    if chunk:
        yield "".join(chunk)
