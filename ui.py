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

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

try:  # kurigram / newer pyrogram builds
    from pyrogram.enums import ButtonStyle
except Exception:  # pragma: no cover - legacy pyrogram/pyrofork
    ButtonStyle = None

try:  # custom-text ("copy") buttons, layer 178+
    from pyrogram.types import CopyTextButton
except Exception:  # pragma: no cover - legacy pyrogram/pyrofork
    CopyTextButton = None


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
    return InlineKeyboardButton(text, **kwargs)


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
        [button("🌐 Language", callback_data="cmd_language", style="primary")],
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


def refer_text(link: str, count: int) -> str:
    return (
        "🎁 **REFERRAL**\n\n"
        f"👥 Your referrals: **{count}**\n\n"
        f"🔗 Your link:\n`{link}`\n\n"
        "Earn 10 points for each new friend. Redeem 100 points for 30 months of public-only premium."
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
    from config import PREMIUM_PLANS, REDEEM_LIMITATION
    title = "💎 **PREMIUM ACTIVE**" if premium else "💎 **PREMIUM BENEFITS**"
    expiry = user.get("premium_expiry")
    status = f"\n📅 Valid until: **{expiry:%d %b %Y}**" if premium and expiry else ""
    access = (REDEEM_LIMITATION if user.get("premium_source") == "redeem" else
              "Private-channel access requires premium manually granted by the owner and your own authorized Telegram session. Payment screenshots alone do not unlock it.")
    prices = "\n".join(f"• **₹{p['price']}** / {p['title']}" for p in PREMIUM_PLANS.values())
    return (f"{title}{status}\n\n"
            "✨ **What you get**\n"
            "✅ Unlimited downloads from public channels\n"
            "✅ Up to 2 GB per file\n"
            "✅ No extraction watermark\n"
            "✅ Priority support\n\n"
            f"💰 **Available plans**\n{prices}\n\n"
            f"🔐 **Access policy**\n{access}\n\n"
            "🆓 Free users get **3 public extractions daily** — no referrals required.\n\n"
            "👇 Tap **Buy Plan** to choose a duration. You will see the payment QR before submitting proof.")


def premium_overview_keyboard(owner_id=None):
    return keyboard([
        [button("🛍 Buy Plan", callback_data="premium_plans", style="success")],
        [button("🎁 Earn Points", callback_data="cmd_refer", style="primary"), home_button()],
    ] + ([[button("💬 Contact owner", url=f"tg://user?id={owner_id}", style="primary")]] if owner_id else []))


def plans_text():
    return ("🛍 **CHOOSE YOUR PLAN**\n\n"
            "💎 **1 month — ₹99**\n"
            "🌟 **3 months — ₹249**\n"
            "👑 **1 year — ₹700**\n\n"
            "📲 Select a plan to view the owner's QR. Pay the exact amount, tap **I've paid**, then upload a screenshot.\n\n"
            "🔎 All payments are checked manually by @XyrDeveloper before activation.")


def plans_keyboard():
    from config import PREMIUM_PLANS
    return keyboard([
        [button(f"{p['title']} · ₹{p['price']}", callback_data=f"buy:{key}", style="success")]
        for key, p in PREMIUM_PLANS.items()
    ] + [[button("⬅️ Benefits", callback_data="cmd_premium", style="primary"), home_button()]])


def payment_text(plan):
    return (f"💳 **PAYMENT DETAILS**\n\n📦 Plan: **{plan['title']}**\n💰 Amount: **₹{plan['price']}**\n\n"
            "① Scan this QR in your payment app.\n"
            "② Check the recipient and pay the exact amount.\n"
            "③ Save a screenshot showing the successful transaction.\n"
            "④ Tap **I've paid** below, then send the screenshot here.\n\n"
            "👤 Payment review: @XyrDeveloper\n"
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
