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

#: Public style handles: the wire enum member when the installed library
#: supports coloured buttons, ``None`` otherwise.  Callers and tests assert the
#: RED **🧠 Models Architecture** button with :data:`BUTTON_DANGER`.
BUTTON_PRIMARY = _ENUM_BY_NAME.get("primary")
BUTTON_SUCCESS = _ENUM_BY_NAME.get("success")
BUTTON_DANGER = _ENUM_BY_NAME.get("danger")


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


def payment_review_keyboard(user_id: int, plan: str | None = None,
                            turbo: bool = False) -> InlineKeyboardMarkup:
    """Owner-only approve / fake / ban buttons attached to a payment proof.

    ``callback_data`` is ``payok:<user>[:<plan>][:turbo]`` — the ``turbo`` part
    tells the approval handler to grant the C++ Turbo ``models`` permission too.
    """
    plan_part = f":{plan}" if plan else ""
    turbo_part = ":turbo" if turbo else ""
    return keyboard([
        [
            button("✅ Approve", callback_data=f"payok:{user_id}{plan_part}{turbo_part}",
                   style="success"),
            button("⚠️ Fake", callback_data=f"payfake:{user_id}", style="danger"),
        ],
        [button("🚫 Ban User", callback_data=f"payban:{user_id}", style="danger")],
    ])


def start_keyboard(show_admin: bool = False) -> InlineKeyboardMarkup:
    """Main menu of /start — every button runs its action directly.

    Layout budget (mobile): 7 rows maximum, 2 buttons maximum per row.  The
    last row is always the red **🧠 Models Architecture** button, so the
    dual-engine explainer is one tap away from every menu.
    """
    rows = [
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
            button("📡 Set channel", callback_data="cmd_setchat", style="primary"),
            button("📺 My Channels", callback_data="cmd_mychannels", style="primary"),
        ],
        [
            button("📖 Help", callback_data="cmd_help", style="primary"),
            button("💬 Feedback", callback_data="cmd_feedback", style="primary"),
        ],
        [
            button("🌐 Language", callback_data="cmd_language", style="primary"),
        ] + ([button("🛠 Admins", callback_data="cmd_admin", style="primary")] if show_admin else []),
        # Red (ButtonStyle.DANGER) footer button — the engine architecture page.
        [models_architecture_button()],
    ]
    return keyboard(rows)


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


def fsub_item_url(item) -> str | None:
    """The only place a chat link is allowed to exist: inside a URL button."""
    if item.get("invite_link"):
        return item["invite_link"]
    if item.get("username"):
        return f"https://t.me/{item['username']}"
    return None


def clamp_label(text: str, limit: int = 28) -> str:
    """Keep a button label inside the mobile budget (never drops emojis)."""
    text = text or ""
    return text if len(text) <= limit else text[:limit]


def fsub_keyboard(items, page: int = 0, verify_label: str | None = None) -> InlineKeyboardMarkup:
    """Join buttons for every required chat — links live only in these buttons.

    One item per row so long custom labels and emojis stay readable on a phone.
    At most five items per page; longer lists get a Previous / Next row.  The
    last row is always the verification button.
    """
    from config import FSUB_ITEMS_PER_PAGE, FSUB_VERIFY_LABEL
    items = list(items or [])
    per_page = FSUB_ITEMS_PER_PAGE
    pages = max(1, -(-len(items) // per_page)) if items else 1
    page = max(0, min(int(page or 0), pages - 1))
    rows = []
    for item in items[page * per_page:(page + 1) * per_page]:
        url = fsub_item_url(item)
        if not url:
            continue  # no link to offer — the title still appears in the text
        rows.append([button(clamp_label(item.get("button_text")), url=url, style="primary")])
    if pages > 1:
        rows.append([
            button("⬅️ Previous", callback_data=f"fsub_page:{(page - 1) % pages}", style="primary"),
            button("Next ➡️", callback_data=f"fsub_page:{(page + 1) % pages}", style="primary"),
        ])
    rows.append([button(verify_label or FSUB_VERIFY_LABEL, callback_data="fsub:check", style="success")])
    return keyboard(rows)


def fsub_pages(items) -> int:
    from config import FSUB_ITEMS_PER_PAGE
    items = list(items or [])
    return max(1, -(-len(items) // FSUB_ITEMS_PER_PAGE)) if items else 1


def fsub_list_keyboard(items, page: int = 0) -> InlineKeyboardMarkup:
    """Owner management keyboard: rename / delete per entry, plus delete-all.

    One entry per row (two buttons), so the page size is one lower than the
    join keyboard to keep the total inside the seven-row mobile budget.
    """
    from config import FSUB_LIST_PER_PAGE
    items = list(items or [])
    per_page = FSUB_LIST_PER_PAGE
    pages = max(1, -(-len(items) // per_page)) if items else 1
    page = max(0, min(int(page or 0), pages - 1))
    rows = []
    for offset, item in enumerate(items[page * per_page:(page + 1) * per_page]):
        number = page * per_page + offset + 1
        rows.append([
            button("✏️ Rename", callback_data=f"fsub_rename:{number}", style="primary"),
            button("🗑 Delete", callback_data=f"fsub_del:{number}", style="danger"),
        ])
    if pages > 1:
        rows.append([
            button("⬅️ Previous", callback_data=f"fsub_list_page:{(page - 1) % pages}", style="primary"),
            button("Next ➡️", callback_data=f"fsub_list_page:{(page + 1) % pages}", style="primary"),
        ])
    if items:
        rows.append([button("🗑 Delete all", callback_data="fsub_del_all", style="danger")])
    rows.append([home_button()])
    return keyboard(rows)


def download_controls(job_id: str, paused: bool = False) -> InlineKeyboardMarkup:
    """Pause/stop controls attached to an active download."""
    toggle = (
        button("▶️ Resume", callback_data=f"dl:r:{job_id}", style="success")
        if paused
        else button("⏸ Pause", callback_data=f"dl:p:{job_id}", style="primary")
    )
    return keyboard([[toggle, button("⛔ Stop", callback_data=f"dl:s:{job_id}", style="danger")]])


def channel_download_public_text(percent: int | None = None, paused: bool = False) -> str:
    """Notice shown in a public channel while downloading public content."""
    from config import BOT_USERNAME
    pct = f" {percent}%" if percent is not None else ""
    state = " (paused)" if paused else ""
    return (
        f"⬇️ **Downloading...{pct}{state}**\n\n"
        f"To stop this download, open @{BOT_USERNAME}."
    )


def open_bot_keyboard() -> InlineKeyboardMarkup:
    """Single open bot button for public channel downloads."""
    from config import BOT_USERNAME
    return keyboard([
        [button("🤖 Open bot", url=f"https://t.me/{BOT_USERNAME}", style="primary")]
    ])


def channel_caption_question_text() -> str:
    return "Use your custom caption for this download?"


def channel_caption_keyboard(token: str) -> InlineKeyboardMarkup:
    return keyboard([
        [
            button("✅ Yes", callback_data=f"cap_yes:{token}", style="success"),
            button("❌ No", callback_data=f"cap_no:{token}", style="danger"),
        ]
    ])


# --------------------------------------------------------------------------- #
#  Screen copy
# --------------------------------------------------------------------------- #

def start_text(name: str, premium: bool, engine_line: str | None = None) -> str:
    """Main menu copy.

    *engine_line* is the live corner badge built by :func:`active_engine_status`
    (for example ``⚡ Active Engine: [C++ Turbo 🚀 (Peak Auto-Scale)]``).  It is
    optional so callers that do not know the engine yet still render a menu.
    """
    badge = "💎 Premium" if premium else "🆓 Free"
    engine = f"{engine_line}\n" if engine_line else ""
    return (
        f"👋 **Hello {name}!**\n\n"
        f"🤖 **Restricted Content Saver Bot**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{engine}"
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
        "**🧠 Engines:**\n"
        "/models — Python Standard ⚙️ or C++ Turbo 🚀\n"
        "/mychannels — your dump-channel dashboard\n\n"
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


def fsub_text(items, page: int = 0) -> str:
    """Force-sub screen — required chats are named by title, never by link.

    Links only ever appear inside the URL buttons of :func:`fsub_keyboard`,
    so this text can be copied anywhere safely.
    """
    items = list(items or [])
    if not items:
        return "✅ **No channel to join.**"
    lines = [
        "⚠️ **Join required**",
        "",
        "Join using the buttons below, then tap **✅ I Joined**.",
        "You can use this bot only while you remain joined.",
        "",
    ]
    for index, item in enumerate(items, 1):
        icon = "👥" if item.get("kind") == "group" else "📢"
        lines.append(f"{icon} {index}. **{item.get('title') or 'Chat'}**")
    pages = fsub_pages(items)
    if pages > 1:
        lines += ["", f"Page {max(0, min(int(page or 0), pages - 1)) + 1}/{pages}"]
    return "\n".join(lines)


def fsub_list_pages(items) -> int:
    from config import FSUB_LIST_PER_PAGE
    items = list(items or [])
    return max(1, -(-len(items) // FSUB_LIST_PER_PAGE)) if items else 1


def fsub_list_text(items, page: int = 0) -> str:
    """Owner listing of every force-sub entry (titles, labels and ids only)."""
    items = list(items or [])
    if not items:
        return "ℹ️ **No force-sub entries.**\n\nAdd a channel or group with /setfsub."
    lines = [f"📢 **Force Sub** • {len(items)} entries", ""]
    for index, item in enumerate(items, 1):
        icon = "👥" if item.get("kind") == "group" else "📢"
        auto = " · auto-approve ON" if item.get("auto_approve") else ""
        lines.append(
            f"{icon} {index}. **{item.get('title') or 'Chat'}** · "
            f"button: \"{item.get('button_text')}\" · `{item.get('chat_id')}`{auto}"
        )
    pages = fsub_list_pages(items)
    if pages > 1:
        lines += ["", f"Page {max(0, min(int(page or 0), pages - 1)) + 1}/{pages}"]
    lines += ["", "Use ✏️ Rename / 🗑 Delete to manage entries, or 🗑 Delete all to clear."]
    return "\n".join(lines)


def fsub_button_prompt_text(title: str, kind: str = "channel") -> str:
    """Ask the owner for the custom label of the Join button."""
    from config import FSUB_MAX_BUTTON_CHARS
    default = default_fsub_label(title)
    who = "group" if str(kind).lower().startswith("group") else "channel"
    return (
        f"🔤 **{title}** — what should the Join button say for this {who}?\n\n"
        f"1–{FSUB_MAX_BUTTON_CHARS} characters, e.g. `Join` / `Join Announcement` / `📢 Join Update`\n\n"
        f"Send `-` for the default (**{default}**)."
    )


def default_fsub_label(title: str) -> str:
    """Suggested label, always inside the mobile budget."""
    from config import FSUB_MAX_BUTTON_CHARS
    label = f"✅ Join {title}".strip()
    return label[:FSUB_MAX_BUTTON_CHARS]


def fsub_admin_failed_text(reason: str, title: str) -> str:
    """Truthful reason why the bot cannot moderate a force-sub chat."""
    if reason == "no_post_rights":
        return (
            f"❌ I am an administrator in **{title}**, but **Post Messages** is OFF.\n\n"
            "👉 Channel → Administrators → this bot → turn **Post Messages** ON, then send /setfsub again."
        )
    if reason == "error":
        return (
            f"❌ **{title}** — Telegram did not respond.\n\n"
            "Send /setfsub again in a moment."
        )
    return (
        f"❌ Make me an administrator in **{title}**.\n\n"
        "👉 Chat → Administrators → Add Admin → select this bot, then send /setfsub again."
    )


def fsub_label_invalid_text() -> str:
    """Why an owner-typed button label was refused (wizard stays open)."""
    from config import FSUB_MAX_BUTTON_CHARS
    return (
        "❌ **This label cannot be used.**\n\n"
        f"Single line, 1–{FSUB_MAX_BUTTON_CHARS} characters, no links or @mentions.\n\n"
        "Send again, or `-` for default."
    )


def fsub_join_pending_text(title: str) -> str:
    """The chat is approval-only: a join request was sent, nothing is stored."""
    return (
        f"✅ **{title}** — join request sent.\n\n"
        "Ask the channel owner to approve, then tap **🔍 Check Admin Status** again."
    )


def fsub_request_notify_text(name: str, user_id: int, title: str) -> str:
    """Owner notification for an incoming join request (no links in the copy)."""
    return (
        "🔔 **Join request**\n\n"
        f"👤 {name} · `{user_id}`\n"
        f"📢 {title}\n\n"
        "Use the buttons below to approve or decline."
    )


def fsub_request_keyboard(user_id: int, chat_id) -> InlineKeyboardMarkup:
    """Owner-only verdict buttons for a join request."""
    return keyboard([
        [
            button("✅ Approve", callback_data=f"fsub:approve:{user_id}:{chat_id}", style="success"),
            button("❌ Decline", callback_data=f"fsub:decline:{user_id}:{chat_id}", style="danger"),
        ],
    ])


def fsub_delete_all_keyboard() -> InlineKeyboardMarkup:
    """Confirmation row for wiping the whole force-sub list."""
    return keyboard([
        [button("🗑 Delete all", callback_data="fsub_del_all_confirm", style="danger")],
        [button("❌ Cancel", callback_data="cancel_action", style="primary")],
    ])


def fsub_request_verdict_text(base: str | None, line: str) -> str:
    """Append the owner verdict to the original join-request notification."""
    base = (base or "").strip()
    return f"{base}\n\n{line}" if base else line


def fsub_request_approved_text() -> str:
    return "✅ **Your join request was approved**\n\nYou can now use the bot."


def fsub_auto_approved_text() -> str:
    return "✅ **Request verified and approved**\n\nSend a link now."


def fsub_verified_text() -> str:
    return "✅ **Verified!**\n\nSend a link now."


def fsub_pending_text() -> str:
    return ("⏳ **Your request is pending**\n\n"
            "Access will be granted once an admin approves — try again in a moment.")


def fsub_empty_text() -> str:
    return "✅ **No force-sub required** — send your link directly."


def fsub_join_instruction_text(private: bool) -> str:
    if private:
        return ("❌ **Tap Join to send a join request first**, then tap **✅ I Joined**.\n\n"
                "Access will be granted once the channel owner approves.")
    return "❌ **Join the channels first**, then tap **✅ I Joined**."


def fsub_added_text(item) -> str:
    icon = "👥" if item.get("kind") == "group" else "📢"
    return (
        f"✅ **Force-sub added**\n\n"
        f"{icon} {item.get('title')}\n"
        f"🔤 Button: **{item.get('button_text')}**\n\n"
        "Send /setfsub again to add more channels — no limit."
    )


def fsub_removed_text(item) -> str:
    return f"✅ **Removed:** {item.get('title')}"


def fsub_cleared_text(count: int) -> str:
    return f"✅ **Removed {count} force-sub entries**"


def fsub_delete_all_confirm_text(count: int) -> str:
    return (
        f"🗑 **Delete all {count} force-sub entries?**\n\n"
        "This cannot be undone. Tap **🗑 Delete all** to confirm."
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


def payment_approved_user_text(plan_title: str | None, days: int | None,
                               turbo: bool = False) -> str:
    detail = f"\n\n📦 {plan_title} • {days} days of full access" if plan_title and days else ""
    engine = ("\n🚀 **C++ Turbo unlocked** — switch your engine any time with /models."
              if turbo else "")
    return "🎉 Payment Approved! Your premium has been activated." + detail + engine


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
        "Send me the channel or group where you added me as an admin — link, "
        "@username, numeric ID or a private invite link.\n\n"
        "Example: `@mychannel` or `-1001234567890`\n\n"
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
        "Final step: send a sample message from this channel so I can verify that I can read its "
        "content — a message link, or just the message number (for example `15`)."
    )


def setchat_admin_failed_text(reason: str = "not_admin") -> str:
    """Tell the owner the *actual* reason the admin check failed."""
    if reason == "no_post_rights":
        return (
            "❌ **Admin check failed**\n\n"
            "I am an administrator, but **Post Messages** is OFF.\n\n"
            "👉 Channel → Administrators → this bot → turn **Post Messages** ON, "
            "then tap **🔍 Check Admin Status** again."
        )
    if reason == "error":
        return (
            "❌ **Admin check failed**\n\n"
            "Telegram did not respond. Tap **🔍 Check Admin Status** again; "
            "try later if it fails repeatedly."
        )
    return (
        "❌ **Admin check failed**\n\n"
        "Make me an administrator in that channel.\n\n"
        "👉 Channel → Administrators → Add Admin → select this bot → "
        "turn **Post Messages** ON, then tap **🔍 Check Admin Status** again."
    )


def setchat_join_request_text(title: str) -> str:
    """Approval-only chat: the bot sent a join request and waits."""
    return (
        f"✅ **{title}** — join request sent.\n\n"
        "Ask the channel owner to approve, then tap **🔍 Check Admin Status** again."
    )


def setchat_resolve_failed_text(reason: str = "unresolved") -> str:
    """Friendly, link-free explanation of a failed chat reference."""
    if reason == "expired":
        return ("❌ **This invite link has expired.**\n\n"
                "Send a fresh invite link from the channel.")
    if reason == "invalid":
        return ("❌ **This invite link looks invalid.**\n\n"
                "Copy the link properly and send it again.")
    if reason == "no_access":
        return ("🔒 **I do not have access to this chat.**\n\n"
                "Add the bot to the channel first, then send the link.")
    return ("❌ Could not resolve that chat. Send the channel link, @username or ID again.\n\n"
            "Public channels, private invite links, groups and supergroups are supported.")


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
        "That sample message could not be read. Make sure the message exists in the channel, that it "
        "is not deleted, and send the message link or the message number again."
    )


def setchat_usage_text() -> str:
    return ("Usage: `/setchat` with a channel link, @username, numeric ID or a private invite "
            "link — or use the **📡 Set channel** button in /admin to be guided step by step.")


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
    from config import (FREE_DAILY_LIMIT, PREMIUM_SOURCE_PUBLIC,
                        PREMIUM_SOURCE_REDEEM, REDEEM_LIMITATION, TURBO_BENEFITS)
    user = user or {}
    title = "💎 **PREMIUM ACTIVE**" if premium else "💎 **PREMIUM BENEFITS**"
    expiry = user.get("premium_expiry")
    status = f"\n📅 Valid until: **{expiry:%d %b %Y}**" if premium and expiry else (
        "\n♾ Valid: **lifetime**" if premium else "")
    source = user.get("premium_source")
    if source == PREMIUM_SOURCE_REDEEM:
        access = REDEEM_LIMITATION
    elif premium and source == PREMIUM_SOURCE_PUBLIC:
        access = "Public channels only — this grant does not include private or restricted links."
    else:
        access = ("Private-channel access requires premium manually granted by the owner and your own "
                  "authorized Telegram session. Payment screenshots alone do not unlock it.")
    # The C++ Turbo add-on is a separate, per-user feature flag.
    turbo = bool(user.get("has_models_access"))
    turbo_line = ("🚀 **C++ Turbo engine:** unlocked — switch it with /models"
                  if turbo else
                  "🚀 **C++ Turbo engine:** add-on available on every plan")
    turbo_benefits = "\n".join(f"✅ {item}" for item in TURBO_BENEFITS)
    return (f"{title}{status}\n\n"
            "✨ **What you get**\n"
            "✅ Unlimited downloads from public channels\n"
            "✅ Up to 2 GB per file\n"
            "✅ No extraction watermark\n"
            "✅ Priority support\n\n"
            f"🚀 **C++ Turbo add-on**\n{turbo_line}\n{turbo_benefits}\n\n"
            f"💰 **Available plans**\n{plans_table()}\n\n"
            f"🔐 **Access policy**\n{access}\n\n"
            f"🆓 Free users get **{FREE_DAILY_LIMIT} public extractions daily** — no referrals required.\n\n"
            "👇 Tap **Buy Plan** to choose a duration and a Standard or C++ Turbo "
            "price. You will see the payment QR before submitting proof.")


def premium_overview_keyboard(owner_id=None):
    """Benefits screen actions.

    ``owner_id`` is accepted for backwards compatibility; the contact button is
    now the owner's public link from ``config.PAYMENT_CONTACT``, which needs no
    numeric id and works for every user.
    """
    return keyboard([
        [button("🛍 Buy Plan", callback_data="premium_plans", style="success")],
        [button("🎁 Earn Points", callback_data="cmd_refer", style="primary"), home_button()],
        [button("🚀 C++ Turbo", callback_data="cmd_models", style="primary")],
        [owner_contact_button()],
    ])


def plans_text():
    """Plan list — built from config.PREMIUM_PLANS so prices never drift."""
    from config import PAYMENT_CONTACT
    return ("🛍 **CHOOSE YOUR PLAN**\n\n"
            "💰 **Tiered pricing — Standard or with the C++ Turbo add-on**\n"
            f"{plans_table()}\n\n"
            "⚙️ **Standard** runs on the Python engine.\n"
            "🚀 **With C++ Turbo** adds the multi-threaded, zero-copy engine and "
            "the /models switcher for the whole plan duration.\n\n"
            "📲 Select a plan to view the owner's QR. Pay the exact amount, tap "
            "**I've paid**, then upload a screenshot.\n\n"
            f"🔎 All payments are checked manually by @{PAYMENT_CONTACT} before "
            "activation. Tap **Contact Owner** for any question.")


def plans_keyboard():
    """One row per plan: Standard price and, when it exists, the C++ Turbo price.

    ``callback_data`` keeps the legacy ``buy:<plan>`` form for the Standard
    price and adds ``buy:<plan>:turbo`` for the C++ Turbo add-on, so buttons
    sent before this change still check out.  Both are plain ASCII.
    """
    from config import PREMIUM_PLANS, plan_addon_price, plan_base_price, plan_total_price
    rows = []
    for key, plan in PREMIUM_PLANS.items():
        title = plan.get("title", key)
        standard = button(f"💎 {title} · ₹{plan_base_price(plan)}",
                          callback_data=f"buy:{key}", style="success")
        if plan_addon_price(plan):
            turbo = button(f"🚀 {title} · ₹{plan_total_price(plan)}",
                           callback_data=f"buy:{key}:turbo", style="primary")
            rows.append([standard, turbo])
        else:
            rows.append([standard])
    rows.append([button("⬅️ Benefits", callback_data="cmd_premium", style="primary"),
                 home_button()])
    rows.append([owner_contact_button()])
    return keyboard(rows)


def payment_text(plan, turbo: bool = False):
    """Payment-proof wizard copy — the amount follows the chosen variant.

    ``turbo=True`` charges the plan **plus** the C++ Turbo add-on and lists what
    the add-on unlocks, so the screenshot the owner reviews matches the amount.
    """
    from config import PAYMENT_CONTACT, RUPEE, plan_addon_price, plan_base_price, plan_total_price
    plan = plan or {}
    amount = plan_total_price(plan) if turbo else plan_base_price(plan)
    title = plan.get("title", "Plan")
    engine = ("🚀 **C++ Turbo** (multi-threaded, zero-copy) + /models switcher"
              if turbo else "⚙️ **Python Standard** (single-stream)")
    addon = plan_addon_price(plan)
    breakdown = (f"\n🧩 Includes: {RUPEE}{plan_base_price(plan)} base + "
                 f"{RUPEE}{addon} C++ Turbo add-on" if turbo and addon else "")
    return (f"💳 **PAYMENT DETAILS**\n\n"
            f"📦 Plan: **{title}**\n"
            f"⚡ Engine: {engine}\n"
            f"💰 Amount: **{RUPEE}{amount}**{breakdown}\n\n"
            "① Scan this QR in your payment app.\n"
            "② Check the recipient and pay the exact amount.\n"
            "③ Save a screenshot showing the successful transaction.\n"
            "④ Tap **I've paid** below, then send the screenshot here.\n\n"
            f"👤 Payment review: @{PAYMENT_CONTACT}\n"
            "⏳ Premium starts only after owner verification. Never share your PIN or OTP.")


def payment_keyboard(token):
    """Proof-wizard actions — always with the explicit owner contact URL button."""
    return keyboard([
        [button("✅ I've paid", callback_data=f"paid:{token}", style="success")],
        [button("⬅️ Plans", callback_data="premium_plans", style="primary"),
         button("❌ Cancel", callback_data="cancel_action", style="danger")],
        [owner_contact_button()],
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


# --------------------------------------------------------------------------- #
#  Dual execution engines — Python Standard ⚙️ / C++ Turbo 🚀
#
#  Every engine string a user sees is built here: the /start corner badge, the
#  live telemetry HUD, the /models switcher and the red architecture page.
#  engines.py owns the routing decisions, this module owns the wording.
# --------------------------------------------------------------------------- #

def _engine_object(key):
    """The :class:`engines.Engine` for *key* (import kept lazy: ui has no deps)."""
    from engines import get_engine
    return get_engine(key)


def engine_key(key) -> str:
    """Normalised engine id (``"python"`` / ``"cpp"``) for any stored value."""
    from engines import normalize_engine
    return normalize_engine(key)


def engine_display(key) -> str:
    """``"C++ Turbo 🚀"`` — the label plus its icon."""
    return _engine_object(key).name


def engine_icon(key) -> str:
    return _engine_object(key).icon


def engine_version_label(key) -> str:
    """``"v2.4"`` for the turbo engine, ``""`` for engines without a version."""
    return _engine_object(key).version_label


def active_engine_status(key=None, badge: str = "", *, icon: str | None = None) -> str:
    """The live /start corner badge.

    ``⚡ Active Engine: [C++ Turbo 🚀 (Peak Auto-Scale)]``
    ``⚡ Active Engine: [C++ Turbo 🚀 (Global Lock)]``
    ``🟢 Active Engine: [Python Standard ⚙️]``
    """
    resolved = engine_key(key)
    turbo = resolved == "cpp"
    lead = icon or ("⚡" if turbo else "🟢")
    inner = engine_display(resolved)
    if badge:
        inner = f"{inner} ({badge})"
    return f"{lead} **Active Engine:** [{inner}]"


def engine_status_line(decision) -> str:
    """:func:`active_engine_status` built straight from an ``EngineDecision``."""
    if decision is None:
        return active_engine_status()
    return active_engine_status(getattr(decision, "engine", None),
                                getattr(decision, "badge", "") or "")


# --------------------------------------------------------------------------- #
#  Live download telemetry HUD (terminal style)
# --------------------------------------------------------------------------- #

#: Progress-bar cells. ``█`` is a filled cell, ``░`` an empty one.
BAR_FILLED = "█"
BAR_EMPTY = "░"
#: Unknown telemetry readings render as this, never as a fake zero.
UNKNOWN_VALUE = "--"


def progress_bar(percent, width: int | None = None) -> str:
    """``68`` → ``[████████░░░░]`` (12 cells by default)."""
    from config import TELEMETRY_BAR_WIDTH
    cells = int(TELEMETRY_BAR_WIDTH if width is None else width)
    cells = max(1, min(64, cells))
    try:
        value = 0 if percent is None else max(0, min(100, int(round(float(percent)))))
    except (TypeError, ValueError):
        value = 0
    filled = int(max(0, min(cells, round(value * cells / 100))))
    return f"[{BAR_FILLED * filled}{BAR_EMPTY * (cells - filled)}]"


def format_percent(value, digits: int = 1) -> str:
    """``19.234`` → ``19.2%``; ``None`` → ``--``."""
    if value is None:
        return UNKNOWN_VALUE
    try:
        return f"{float(value):.{digits}f}%"
    except (TypeError, ValueError):
        return UNKNOWN_VALUE


def format_ping(ms) -> str:
    """``11.4`` → ``11ms`` (whole milliseconds, the way a terminal shows it)."""
    if ms is None:
        return UNKNOWN_VALUE
    try:
        return f"{int(round(float(ms)))}ms"
    except (TypeError, ValueError):
        return UNKNOWN_VALUE


def format_speed(mbps) -> str:
    """``44.23`` → ``44.2 MB/s``; ``None`` → ``--``."""
    if mbps is None:
        return UNKNOWN_VALUE
    try:
        value = float(mbps)
    except (TypeError, ValueError):
        return UNKNOWN_VALUE
    if value >= 1024:
        return f"{value / 1024:.2f} GB/s"
    return f"{value:.1f} MB/s"


def format_eta(seconds) -> str:
    """``3`` → ``00:03``, ``3725`` → ``1:02:05``; ``None`` → ``--:--``."""
    if seconds is None:
        return "--:--"
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "--:--"
    if total < 0:
        return "--:--"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def telemetry_engine_line(key=None, state: str = "Active") -> str:
    """``⚡ Engine: C++ Turbo v2.4 [Active]`` / ``⚙️ Engine: Python Standard [Active]``."""
    resolved = engine_key(key)
    icon = "⚡" if resolved == "cpp" else engine_icon(resolved)
    version = engine_version_label(resolved)
    name = f"{_engine_object(resolved).label} {version}".strip()
    return f"{icon} **Engine:** {name} [{state}]"


def telemetry_load_line(sample=None) -> str:
    """``📊 Server Load: CPU 19.2% | RAM 41.8% | Ping 11ms``."""
    cpu = getattr(sample, "cpu_percent", None)
    ram = getattr(sample, "memory_percent", None)
    ping = getattr(sample, "ping_ms", None)
    return (f"📊 **Server Load:** CPU {format_percent(cpu)} | "
            f"RAM {format_percent(ram)} | Ping {format_ping(ping)}")


def telemetry_progress_line(percent=None, stage: str = "Downloading",
                            paused: bool = False, width: int | None = None) -> str:
    """``📥 Downloading: 68% [████████░░░░]``."""
    label = "Paused" if paused else (stage or "Downloading")
    shown = UNKNOWN_VALUE if percent is None else f"{max(0, min(100, int(percent)))}%"
    return f"📥 **{label}:** {shown} {progress_bar(percent, width)}"


def telemetry_speed_line(state=None) -> str:
    """``🚀 Speed: 44.2 MB/s • ETA: 00:03``."""
    speed = getattr(state, "speed_mbps", None)
    eta = getattr(state, "eta", None)
    return f"🚀 **Speed:** {format_speed(speed)} • **ETA:** {format_eta(eta)}"


def telemetry_enabled() -> bool:
    """False when ``TELEMETRY=off`` was requested in the environment."""
    from config import TELEMETRY_ENABLED
    return bool(TELEMETRY_ENABLED)


def telemetry_hud(key=None, percent=None, *, sample=None, state=None,
                  stage: str = "Downloading", paused: bool = False,
                  width: int | None = None, engine_state: str = "Active") -> str:
    """The full terminal-style HUD shown while a file is being extracted.

    ``⚡ Engine: C++ Turbo v2.4 [Active]``
    ``📥 Downloading: 68% [████████░░░░]``
    ``📊 Server Load: CPU 19.2% | RAM 41.8% | Ping 11ms``
    ``🚀 Speed: 44.2 MB/s • ETA: 00:03``

    Missing readings degrade to ``--`` instead of inventing numbers, and the
    server-load line disappears entirely when telemetry is switched off.
    """
    lines = [
        telemetry_engine_line(key, engine_state),
        telemetry_progress_line(percent, stage=stage, paused=paused, width=width),
    ]
    if telemetry_enabled():
        lines.append(telemetry_load_line(sample))
    lines.append(telemetry_speed_line(state))
    return "\n".join(lines)


#: Backwards friendly alias — the HUD *is* the download status text now.
download_hud = telemetry_hud


def channel_download_notice(percent=None, paused: bool = False, hud: str | None = None) -> str:
    """Public-channel download notice, optionally carrying the telemetry HUD."""
    body = channel_download_public_text(percent, paused)
    return f"{hud}\n\n{body}" if hud else body


# --------------------------------------------------------------------------- #
#  /models and /engine — the user-facing engine switcher
# --------------------------------------------------------------------------- #

def models_switcher_keyboard(active=None, *, can_switch: bool = True) -> InlineKeyboardMarkup:
    """``[ ⚙️ Python Standard ]`` / ``[ 🚀 C++ Turbo ]`` with the active one marked.

    The active engine is green (success) and carries a ✅, the other stays blue.
    When the global C++ lock is on, the choice is fixed and both buttons are
    replaced by a single "back" row by the caller.
    """
    current = engine_key(active)

    def pick(key: str, label: str):
        selected = key == current
        text = f"✅ {label}" if selected else label
        return button(text, callback_data=f"engine_set:{key}",
                      style="success" if selected else "primary")

    rows = [
        [pick("python", "⚙️ Python Standard")],
        [pick("cpp", "🚀 C++ Turbo")],
    ]
    if not can_switch:
        rows = []
    rows.append([button("🧠 Architecture", callback_data="models_info", style="primary"),
                 home_button()])
    return keyboard(rows)


def models_switcher_text(active=None, mode=None, *, concurrency: int = 0,
                         peak: bool = False, threshold: int | None = None) -> str:
    """Screen copy of the switcher for a user who holds the ``models`` feature."""
    from engines import ENGINE_MODE_LABELS, normalize_mode
    resolved = engine_key(active)
    mode_key = normalize_mode(mode)
    #: "Your Choice" only once the user actually picked an engine.
    badge = "Your Choice" if active else ""
    lines = [
        "🧠 **ENGINE SWITCHER**",
        "",
        active_engine_status(resolved, badge),
        "",
        f"🎛 **Controller mode:** {ENGINE_MODE_LABELS.get(mode_key, mode_key)}",
        f"📈 **Live traffic:** {int(concurrency)} concurrent"
        + (f" (peak above {int(threshold)})" if threshold is not None else ""),
        "",
        "Pick the engine used for **all** your extractions — private chat and "
        "dump channels alike. The choice is stored on your account.",
        "",
        "⚙️ **Python Standard** — single-stream, the reliable default.",
        "🚀 **C++ Turbo** — multi-threaded workers with zero-copy stream piping.",
    ]
    if mode_key == "lock_cpp":
        lines += ["", "🔒 The owner has locked **every** extraction to C++ Turbo, "
                      "so the switcher is fixed right now."]
    elif peak:
        lines += ["", "⚡ Traffic is above the autoscaler threshold — requests are "
                      "being pushed through C++ Turbo automatically."]
    return "\n".join(lines)


def models_locked_text(mode=None) -> str:
    """Shown to a models holder while the global C++ lock removes the choice."""
    from engines import ENGINE_MODE_LABELS, normalize_mode
    return "\n".join([
        "🧠 **ENGINE SWITCHER**",
        "",
        active_engine_status("cpp", "Global Lock"),
        "",
        f"🎛 **Controller mode:** {ENGINE_MODE_LABELS.get(normalize_mode(mode), 'Auto')}",
        "",
        "🔒 Every extraction on this bot is currently forced through the "
        "**C++ Turbo** engine by the owner, so your personal preference is "
        "already the fastest option. The switcher returns as soon as the global "
        "lock is lifted.",
    ])


def models_upsell_text() -> str:
    """Feature overview + add-on pricing for a user **without** the feature."""
    from config import PREMIUM_PLANS, RUPEE, plan_addon_price, plan_base_price
    rows = []
    for plan in PREMIUM_PLANS.values():
        addon = plan_addon_price(plan)
        base = plan_base_price(plan)
        if not addon:
            continue
        rows.append(f"• **{plan['title']}** — {RUPEE}{base} Standard · "
                    f"+{RUPEE}{addon} with C++ Turbo = **{RUPEE}{base + addon}**")
    pricing = "\n".join(rows) or "• C++ Turbo is sold as an add-on on every plan."
    return "\n".join([
        "🚀 **C++ TURBO ENGINE**",
        "",
        "Your account runs on the **Python Standard** engine. The C++ Turbo "
        "engine is a paid add-on:",
        "",
        "✅ Multi-threaded extraction workers instead of one stream",
        "✅ Zero-copy stream piping — the file is never re-buffered",
        "✅ Ultra-low latency during traffic peaks",
        "✅ Priority routing while the server is busy",
        "✅ Live telemetry HUD with speed, ETA and server load",
        "",
        "💰 **Add-on pricing**",
        pricing,
        "",
        "👇 Tap **Upgrade to C++ Turbo** to see the payment QR, or contact the "
        "owner for a manual grant.",
    ])


def models_upsell_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("🚀 Upgrade to C++ Turbo", callback_data="premium_plans", style="success")],
        [button("🧠 Architecture", callback_data="models_info", style="primary"),
         button("💎 Benefits", callback_data="cmd_premium", style="primary")],
        [owner_contact_button()],
        [home_button()],
    ])


def models_architecture_button() -> InlineKeyboardButton:
    """The red footer button of /start (``ButtonStyle.DANGER``)."""
    return button("🧠 Models Architecture", callback_data="models_info", style="danger")


def models_architecture_text(active=None) -> str:
    """The detailed Python vs C++ Turbo page opened by the red /start button."""
    from config import (ENGINE_PEAK_THRESHOLD, ENGINE_TURBO_WORKERS,
                        ENGINE_ZERO_COPY_MAX_MB, PAYMENT_CONTACT, PREMIUM_PLANS,
                        RUPEE, plan_addon_price, plan_base_price)
    workers = max(1, int(ENGINE_TURBO_WORKERS))
    zero_copy_mb = max(0, int(ENGINE_ZERO_COPY_MAX_MB))
    prices = "\n".join(
        f"• **{plan['title']}** — {RUPEE}{plan_base_price(plan)} Standard · "
        f"{RUPEE}{plan_base_price(plan) + plan_addon_price(plan)} with C++ Turbo"
        for plan in PREMIUM_PLANS.values()
    )
    lines = [
        "🧠 **MODELS ARCHITECTURE**",
        "",
        active_engine_status(active),
        "",
        "⚙️ **PYTHON STANDARD**",
        "• Single-thread, single-stream pipeline",
        "• One link at a time per extraction batch",
        "• Buffered transfer: download, then re-upload",
        "• Included in every plan, free tier included",
        "",
        "🚀 **C++ TURBO**",
        f"• Multi-threaded pool — up to {workers} concurrent workers",
        f"• Zero-copy stream piping: files up to {zero_copy_mb} MB are handed to "
        "the uploader straight from memory — no temp file, no re-read",
        "• Native C cipher (TgCrypto) on every MTProto chunk",
        f"• Priority routing above {int(ENGINE_PEAK_THRESHOLD)} concurrent extractions",
        "",
        "📊 **TRAFFIC HANDLING**",
        "• Python Standard: 1 stream per batch — queues grow with traffic",
        f"• C++ Turbo: {workers} overlapping streams per batch — the download and "
        "the upload of different files run at the same time",
        f"• Indicative throughput: up to ~{workers}x the concurrent streams of a "
        "single-stream batch on the same link",
        "",
        "🤖 **AUTO MODE (default)**",
        "The controller watches live concurrency. During a traffic spike every "
        "request is routed to C++ Turbo so nothing queues; when traffic returns "
        "to normal, free users go back to Python Standard automatically.",
        "",
        "🔓 **HOW TO UNLOCK C++ TURBO**",
        prices,
        "",
        f"Pay the add-on amount and send the screenshot, or tap **Contact Owner** "
        f"below to reach @{PAYMENT_CONTACT} for a manual grant. The owner can also "
        "grant it with /addpremium.",
    ]
    return "\n".join(lines)


def models_architecture_keyboard(active=None, *, has_models: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_models:
        rows.append([button("🎛 Open Switcher", callback_data="cmd_models", style="success")])
    else:
        rows.append([button("🚀 Upgrade to C++ Turbo", callback_data="premium_plans",
                            style="success")])
    rows.append([owner_contact_button()])
    rows.append([home_button()])
    return keyboard(rows)


# --------------------------------------------------------------------------- #
#  /setengine — the owner's global engine controller
# --------------------------------------------------------------------------- #

def engine_controller_keyboard(mode=None) -> InlineKeyboardMarkup:
    """AUTO / LOCK C++ / LOCK PYTHON, the active mode marked in green."""
    from engines import normalize_mode
    current = normalize_mode(mode)

    def pick(key: str, label: str):
        selected = key == current
        text = f"✅ {label}" if selected else label
        return button(text, callback_data=f"engine_mode:{key}",
                      style="success" if selected else "primary")

    return keyboard([
        [pick("auto", "🤖 Auto (Autoscaler)")],
        [pick("lock_cpp", "🚀 Lock to C++ Turbo")],
        [pick("lock_python", "⚙️ Lock to Python")],
        [button("📊 Refresh", callback_data="cmd_setengine", style="primary"), home_button()],
    ])


def engine_controller_text(mode=None, snapshot=None) -> str:
    """Owner screen: the active mode, live traffic and the routing rules."""
    from engines import ENGINE_MODE_LABELS, normalize_mode
    snapshot = snapshot or {}
    mode_key = normalize_mode(mode)
    routed = snapshot.get("routed") or {}
    autoscaler = "running" if snapshot.get("autoscaler", mode_key == "auto") else "paused"
    peak = "⚡ PEAK" if snapshot.get("peak") else "🟢 normal"
    lines = [
        "🧠 **GLOBAL ENGINE CONTROLLER**",
        "",
        f"🎛 **Mode:** {ENGINE_MODE_LABELS.get(mode_key, mode_key)}",
        f"🤖 **Autoscaler:** {autoscaler}",
        f"📈 **Traffic:** {int(snapshot.get('active', 0))} concurrent • {peak}",
        f"🎯 **Peak threshold:** {int(snapshot.get('threshold', 0))} concurrent",
        f"🔝 **Peak reached:** {int(snapshot.get('peak_active', 0))} concurrent "
        f"({int(snapshot.get('peak_events', 0))} spike(s))",
        f"⚙️ **Routed to Python:** {int(routed.get('python', 0))}",
        f"🚀 **Routed to C++ Turbo:** {int(routed.get('cpp', 0))}",
        "",
        "**🤖 Auto (Dynamic Autoscaler)** — default. Watches live traffic; above "
        "the threshold every request goes to C++ Turbo to kill the queue, and "
        "free users fall back to Python Standard when traffic normalises.",
        "",
        "**🚀 Lock to C++ Turbo** — global force: 100% of extractions (free and "
        "VIP) run on C++ Turbo. The autoscaler is paused.",
        "",
        "**⚙️ Lock to Python** — global default locked to Python Standard and the "
        "autoscaler disabled. Free users are locked to Python; premium users who "
        "hold the **models** permission keep their own /models switch.",
    ]
    return "\n".join(lines)


def engine_mode_set_text(mode=None) -> str:
    from engines import ENGINE_MODE_LABELS, normalize_mode
    return (f"✅ **Engine mode updated**\n\n"
            f"🎛 Active mode: **{ENGINE_MODE_LABELS.get(normalize_mode(mode), 'Auto')}**\n\n"
            "The new mode applies to every extraction from now on.")


# --------------------------------------------------------------------------- #
#  Owner contact + tiered pricing with the C++ Turbo add-on
# --------------------------------------------------------------------------- #

def contact_owner_url() -> str:
    """The one place the owner contact link is built (config is the truth)."""
    from config import OWNER_CONTACT_URL, PAYMENT_CONTACT
    return OWNER_CONTACT_URL or f"https://t.me/{PAYMENT_CONTACT}"


def owner_contact_button(label: str = "💬 Contact Owner") -> InlineKeyboardButton:
    """``[ 💬 Contact Owner ]`` — a URL button, because links live only in ``url=``.

    Shown on every plan display, pricing screen and payment-proof wizard.
    """
    return button(label, url=contact_owner_url(), style="primary")


def plan_addon_label(plan) -> str:
    """``"+₹50 C++ Turbo"`` — empty when a plan carries no add-on."""
    from config import RUPEE, plan_addon_price
    addon = plan_addon_price(plan)
    return f"+{RUPEE}{addon} C++ Turbo" if addon else ""


def plan_price_labels(plan) -> tuple[str, str]:
    """``("₹99", "₹149")`` — Standard price and price with the C++ add-on."""
    from config import RUPEE, plan_addon_price, plan_base_price, plan_total_price
    base = f"{RUPEE}{plan_base_price(plan)}"
    if not plan_addon_price(plan):
        return base, base
    return base, f"{RUPEE}{plan_total_price(plan)}"


def plans_table() -> str:
    """Every plan as ``Standard`` / ``with C++ Turbo`` / ``Total`` lines."""
    from config import PREMIUM_PLANS, RUPEE, plan_addon_price, plan_base_price
    lines = []
    for plan in PREMIUM_PLANS.values():
        base, addon = plan_base_price(plan), plan_addon_price(plan)
        title = plan.get("title", "Plan")
        if addon:
            lines.append(f"• **{title}** — {RUPEE}{base} Standard | "
                         f"+{RUPEE}{addon} C++ Turbo = **{RUPEE}{base + addon}**")
        else:
            lines.append(f"• **{title}** — {RUPEE}{base}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Granular VIP grants (/addpremium): tier first, then duration
# --------------------------------------------------------------------------- #

def grant_tier_keyboard() -> InlineKeyboardMarkup:
    """The four feature tiers, two per row, plus cancel.

    Labels stay inside the 28-character mobile budget — the full description of
    every tier is printed in :func:`grant_tier_text` instead of the button.
    """
    from config import GRANT_TIERS
    order = ["public", "models", "private", "all"]
    styles = {"public": "primary", "models": "success",
              "private": "primary", "all": "success"}
    buttons = []
    for key in order:
        tier = GRANT_TIERS.get(key)
        if not tier:
            continue
        buttons.append(button(f"{tier['number']} {tier['label']}",
                              callback_data=f"grant_tier:{key}", style=styles.get(key)))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([button("❌ Cancel", callback_data="cancel_action", style="danger")])
    return keyboard(rows)


def grant_tier_text(user_id, name: str | None = None, days=None) -> str:
    """Step 1 — which feature tier should this user get?"""
    from config import GRANT_TIERS
    who = f"{name} (`{user_id}`)" if name else f"`{user_id}`"
    lines = [
        "💎 **GRANULAR VIP GRANT**",
        "",
        f"👤 User: {who}",
        "",
        "**Step 1 of 2 — choose the feature tier**",
        "",
    ]
    for key in ("public", "models", "private", "all"):
        tier = GRANT_TIERS.get(key)
        if not tier:
            continue
        lines.append(f"{tier['number']} **{tier['label']}** — {tier['description']}")
    lines += ["", "📅 Step 2 asks for the duration once the tier is picked."]
    if days:
        lines.append(f"ℹ️ You typed `{days}` day(s) — that duration is offered as a "
                     "button in step 2.")
    return "\n".join(lines)


def grant_duration_keyboard(tier: str, days: int | None = None) -> InlineKeyboardMarkup:
    """Step 2 — ``[1 Month] [3 Months] [1 Year] [Lifetime] [Custom Days]``."""
    from config import GRANT_DURATIONS
    rows = [
        [button(f"📅 {GRANT_DURATIONS['month']['label']}",
                callback_data=f"grant_dur:{tier}:month", style="primary"),
         button(f"📅 {GRANT_DURATIONS['quarter']['label']}",
                callback_data=f"grant_dur:{tier}:quarter", style="primary")],
        [button(f"📅 {GRANT_DURATIONS['year']['label']}",
                callback_data=f"grant_dur:{tier}:year", style="primary"),
         button(f"♾ {GRANT_DURATIONS['lifetime']['label']}",
                callback_data=f"grant_dur:{tier}:lifetime", style="success")],
        [button("🔢 Custom Days", callback_data=f"grant_dur:{tier}:custom", style="primary")],
    ]
    if days:
        rows.append([button(f"✅ Use {int(days)} days",
                            callback_data=f"grant_dur:{tier}:typed:{int(days)}",
                            style="success")])
    rows.append([button("⬅️ Tier", callback_data=f"grant_back:{tier}", style="primary"),
                 button("❌ Cancel", callback_data="cancel_action", style="danger")])
    return keyboard(rows)


def grant_duration_text(user_id, tier: str, name: str | None = None,
                        days: int | None = None) -> str:
    """Step 2 copy — the chosen tier plus the duration choices."""
    from config import GRANT_DURATIONS, GRANT_TIERS
    definition = GRANT_TIERS.get(tier) or {}
    who = f"{name} (`{user_id}`)" if name else f"`{user_id}`"
    choices = " · ".join(
        f"**{value['label']}** ({'no expiry' if value['days'] is None else str(value['days']) + ' days'})"
        for value in GRANT_DURATIONS.values()
    )
    lines = [
        "💎 **GRANULAR VIP GRANT**",
        "",
        f"👤 User: {who}",
        f"🎖 Tier: **{definition.get('number', '')} {definition.get('label', tier)}**".strip(),
        "",
        "**Step 2 of 2 — choose the duration**",
        "",
        choices,
        "",
        "🔢 **Custom Days** asks for an exact number of days (1–36500).",
    ]
    if days:
        lines.append(f"ℹ️ `{int(days)}` day(s) from your command is one tap away below.")
    return "\n".join(lines)


def grant_custom_days_text(user_id, tier: str, name: str | None = None) -> str:
    who = f"{name} (`{user_id}`)" if name else f"`{user_id}`"
    return (f"🔢 **Custom duration**\n\n👤 User: {who}\n\n"
            "Send the number of days in your next message (1–36500).\n"
            "Example: `45`\n\nUse /cancel to exit.")


def grant_done_text(user_id, tier: str, days=None, name: str | None = None) -> str:
    """Owner confirmation — exactly what was stored on the user document."""
    from config import GRANT_TIERS
    definition = GRANT_TIERS.get(tier) or {}
    who = f"{name} (`{user_id}`)" if name else f"`{user_id}`"
    return "\n".join([
        "✅ **VIP GRANTED**",
        "",
        f"👤 User: {who}",
        f"🎖 Tier: **{definition.get('number', '')} {definition.get('label', tier)}**".strip(),
        f"🔓 Private channels: **{'yes' if definition.get('has_private_access') else 'no'}**",
        f"🚀 C++ Turbo models: **{'yes' if definition.get('has_models_access') else 'no'}**",
        "💎 Premium: **yes**",
        f"📅 Expiry: **{'lifetime — no expiry' if days is None else str(int(days)) + ' day(s)'}**",
        "",
        "The user has been notified with the full details of their tier.",
    ])


def grant_activated_user_text(tier: str, days=None, name: str | None = None) -> str:
    """The notification the granted user receives."""
    from config import GRANT_TIERS
    definition = GRANT_TIERS.get(tier) or {}
    greeting = f"👋 {name}, " if name else ""
    features = ["✅ Unlimited public-channel extractions"]
    if definition.get("has_private_access"):
        features.append("✅ Private and restricted channels (login required)")
    if definition.get("has_models_access"):
        features.append("✅ C++ Turbo engine switcher — /models")
    else:
        features.append("⚙️ Python Standard engine")
    expiry = ("♾ **Lifetime — no expiry**" if days is None
              else f"📅 Valid for **{int(days)} day(s)**")
    return "\n".join([
        "💎 **VIP ACTIVATED**",
        "",
        f"{greeting}the owner granted you a premium tier.",
        "",
        f"🎖 Tier: **{definition.get('number', '')} {definition.get('label', tier)}**".strip(),
        *features,
        expiry,
        "",
        "Open /start to use it. Tap 🧠 **Models Architecture** to see what the "
        "C++ Turbo engine changes." if definition.get("has_models_access")
        else "Open /start to use it.",
    ])


def grant_revoked_text(user_id, name: str | None = None) -> str:
    who = f"{name} (`{user_id}`)" if name else f"`{user_id}`"
    return (f"❌ **VIP REVOKED**\n\n👤 User: {who}\n\n"
            "Premium, private-channel access and the C++ Turbo models "
            "permission were all removed.")


def grant_tier_unknown_text() -> str:
    return "⚠️ **Unknown tier**\n\nRun /addpremium again and pick one of the four tiers."


# --------------------------------------------------------------------------- #
#  /mychannels — the user's channel management dashboard
# --------------------------------------------------------------------------- #

def mychannels_empty_text() -> str:
    return "\n".join([
        "📺 **MY CHANNELS**",
        "",
        "You have not connected a dump channel yet.",
        "",
        "Tap **Set channel** (or send /setchat) to link a channel or supergroup. "
        "Every link you post there is extracted automatically, and this "
        "dashboard then shows its permissions and file counter.",
    ])


def mychannels_keyboard(chat_id, *, connected: bool = True) -> InlineKeyboardMarkup:
    """Test permissions / re-verify admin rights / disconnect."""
    rows = []
    if connected and chat_id is not None:
        rows += [
            [button("🔍 Test Permissions", callback_data=f"mych_test:{int(chat_id)}",
                    style="primary"),
             button("🔄 Re-verify Admin", callback_data=f"mych_verify:{int(chat_id)}",
                    style="primary")],
            [button("🗑 Disconnect", callback_data=f"mych_del:{int(chat_id)}", style="danger")],
        ]
    rows.append([button("📡 Set channel", callback_data="cmd_setchat", style="success"),
                 home_button()])
    return keyboard(rows)


def mychannels_text(entry, *, admin_ok=None, admin_reason: str = "", files: int = 0,
                    engine=None) -> str:
    """The dashboard: title, id, posting rights and files extracted."""
    from config import CHANNEL_TITLE_FALLBACK
    entry = entry or {}
    chat_id = entry.get("chat_id")
    title = entry.get("title") or (CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
                                   if chat_id else "Unknown chat")
    if admin_ok is None:
        rights = "❔ Not checked yet — tap **Test Permissions**"
    elif admin_ok:
        rights = "✅ Admin with posting rights"
    else:
        reasons = {
            "not_admin": "❌ The bot is not an admin there",
            "no_post_rights": "⚠️ Admin, but **Post Messages** is disabled",
            "error": "❔ Telegram did not answer — try again",
        }
        rights = reasons.get(admin_reason, "❌ Cannot post there")
    kind = str(entry.get("type") or entry.get("kind") or "").lower()
    kind_label = {"supergroup": "Supergroup", "group": "Group",
                  "channel": "Channel"}.get(kind, "Channel or supergroup")
    lines = [
        "📺 **MY CHANNELS**",
        "",
        f"📌 **{title}**",
        f"🆔 ID: `{chat_id}`",
        f"🗂 Type: {kind_label}",
        f"🔐 Bot posting rights: {rights}",
        f"📦 Files extracted here: **{int(files)}**",
    ]
    if engine:
        lines += ["", active_engine_status(engine)]
    username = entry.get("username")
    if username:
        lines.append(f"🔗 Public handle: @{username}")
    lines += ["", "Use the buttons below to test the bot's permissions, re-verify "
                 "admin rights or disconnect this channel."]
    return "\n".join(lines)


def mychannels_test_text(title: str, ok: bool, reason: str = "") -> str:
    """Result of the **Test Permissions** / **Re-verify Admin** buttons."""
    if ok:
        return (f"✅ **Permissions OK**\n\n📌 {title}\n\n"
                "The bot is an admin and may post messages there. "
                "Extractions into this channel will work.")
    messages = {
        "not_admin": "The bot is **not an admin** in this chat. Add it as an "
                     "admin with **Post Messages** enabled, then tap "
                     "**Re-verify Admin**.",
        "no_post_rights": "The bot is an admin but **Post Messages** is "
                          "disabled. Enable that right and tap **Re-verify Admin**.",
        "error": "Telegram did not answer the permission check. This is usually "
                 "temporary — tap **Test Permissions** again in a moment.",
    }
    body = messages.get(reason, "The bot cannot post in this chat.")
    return (f"⚠️ **Permissions problem**\n\n📌 {title}\n\n{body}\n\n"
            "You can also disconnect it with /delchat and run /setchat again.")


def mychannels_disconnected_text(title: str) -> str:
    return (f"🗑 **Channel disconnected**\n\n📌 {title}\n\n"
            "The bot no longer extracts links posted there. "
            "Run /setchat to connect a channel again.")


# --------------------------------------------------------------------------- #
#  Admin panel — descriptive English command labels
# --------------------------------------------------------------------------- #

#: command -> the clean English description shown in /admin and /admins.
ADMIN_COMMAND_LABELS = {
    "setfsub": "Add Force Subscribe",
    "fsublist": "Manage Force Subs",
    "delfsub": "Delete Force Sub",
    "setchat": "Channel Setup Wizard",
    "setengine": "Global Engine Controller (Lock / Auto)",
    "addpremium": "Granular VIP Grant",
    "removepremium": "Revoke VIP",
    "stats": "Global & Engine Analytics",
    "broadcast": "Broadcast Message",
    "ban": "User Moderation",
    "unban": "User Moderation",
    "payments": "Verify Payment Proofs",
    "maintenance": "Maintenance Mode",
    # Everything else keeps a short, descriptive English label too.
    "users": "All Users List",
    "loggedusers": "Logged-in Users",
    "newusers": "New Users Today",
    "activeusers": "Active Users Today",
    "topusers": "Top Users",
    "finduser": "Find User",
    "userinfo": "User Info",
    "export": "Export Data",
    "premiumlist": "Premium Users List",
    "addqr": "Upload Payment QR",
    "delqr": "Delete Payment QR",
    "removeqr": "Delete Payment QR",
    "sendmsg": "Direct Message a User",
    "banlist": "Banned Users List",
    "feedbacks": "User Feedback Inbox",
    "addadmin": "Add Admin",
    "removeadmin": "Remove Admin",
    "adminlist": "Admin List",
    "clearlogs": "Clear Download Logs",
    "adminhelp": "Admin Help",
    "fsublabel": "Rename a Join Button",
    "fsubcheck": "Force Sub Health Check",
    "delchat": "Disconnect a Dump Channel",
    "redeem": "Redeem Points",
}

#: Emoji shown in front of each command in the panel text.
ADMIN_COMMAND_ICONS = {
    "setfsub": "📢", "fsublist": "📋", "delfsub": "🗑️", "setchat": "⚙️",
    "setengine": "🧠", "addpremium": "💎", "removepremium": "❌", "stats": "📊",
    "broadcast": "📢", "ban": "🚫", "unban": "🚫", "payments": "💳",
    "maintenance": "🛠️", "users": "👥", "loggedusers": "🔐", "newusers": "🆕",
    "activeusers": "📈", "topusers": "🏆", "finduser": "🔎", "userinfo": "ℹ️",
    "export": "📤", "premiumlist": "💎", "addqr": "🖼", "delqr": "🗑️",
    "removeqr": "🗑️", "sendmsg": "✉️", "banlist": "🚫", "feedbacks": "💬",
    "addadmin": "🛡", "removeadmin": "🛡", "adminlist": "🛡", "clearlogs": "🧹",
    "adminhelp": "❓", "fsublabel": "🏷", "fsubcheck": "🩺", "delchat": "🗑️",
    "redeem": "🎁",
}


def admin_command_label(command: str) -> str:
    """The descriptive English label of *command* (falls back to the name)."""
    return ADMIN_COMMAND_LABELS.get(command, command.replace("_", " ").title())


def admin_command_line(command: str) -> str:
    """``🧠 /setengine — Global Engine Controller (Lock / Auto)``."""
    icon = ADMIN_COMMAND_ICONS.get(command, "•")
    return f"{icon} /{command} — {admin_command_label(command)}"


def admin_command_lines(commands) -> str:
    return "\n".join(admin_command_line(command) for command in commands)


def engine_analytics_text(snapshot=None) -> str:
    """The engine half of ``/stats`` — global analytics for the owner/admins."""
    from engines import ENGINE_LABELS, ENGINE_MODE_LABELS, normalize_mode
    snapshot = snapshot or {}
    routed = snapshot.get("routed") or {}
    stored = snapshot.get("stored") or {}
    mode = normalize_mode(snapshot.get("mode"))
    total = sum(int(value) for value in routed.values()) or None
    lines = [
        "🧠 **ENGINE ANALYTICS**",
        "",
        f"🎛 **Controller mode:** {ENGINE_MODE_LABELS.get(mode, mode)}",
        f"🤖 **Autoscaler:** {'running' if snapshot.get('autoscaler') else 'paused'}",
        f"📈 **In flight now:** {int(snapshot.get('active', 0))} concurrent "
        f"(threshold {int(snapshot.get('threshold', 0))})",
        f"🔝 **Peak seen:** {int(snapshot.get('peak_active', 0))} concurrent • "
        f"{int(snapshot.get('peak_events', 0))} spike(s)",
        "",
        "**Routed this run**",
        f"⚙️ {ENGINE_LABELS.get('python', 'Python Standard')}: {int(routed.get('python', 0))}",
        f"🚀 {ENGINE_LABELS.get('cpp', 'C++ Turbo')}: {int(routed.get('cpp', 0))}",
    ]
    if total:
        share = int(routed.get("cpp", 0)) * 100 / total
        lines.append(f"📊 C++ Turbo share: {share:.1f}% of {int(total)} extractions")
    if stored:
        lines += [
            "",
            "**Routed all time (database)**",
            f"⚙️ Python Standard: {int(stored.get('python', 0))}",
            f"🚀 C++ Turbo: {int(stored.get('cpp', 0))}",
        ]
    lines += ["", "🧠 Use /setengine to change the mode or lock an engine globally."]
    return "\n".join(lines)


def stats_text(stats, bookmarks: int = 0, engine_block: str | None = None) -> str:
    """The global ``/stats`` screen (users, downloads and engine analytics)."""
    stats = stats or {}
    lines = [
        "📊 **BOT STATISTICS**",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "👥 **Users:**",
        f"├ Total: `{int(stats.get('total', 0))}`",
        f"├ Active Today: `{int(stats.get('active_today', 0))}`",
        f"├ New Today: `{int(stats.get('new_today', 0))}`",
        f"├ Premium: `{int(stats.get('premium', 0))}`",
        f"├ Banned: `{int(stats.get('banned', 0))}`",
        f"└ Admins: `{int(stats.get('admins', 0))}`",
        "",
        "🔐 **Feature grants:**",
        f"├ Private channels: `{int(stats.get('private_access', 0))}`",
        f"└ C++ Turbo models: `{int(stats.get('models_access', 0))}`",
        "",
        f"📥 Downloads: `{int(stats.get('total_downloads', 0))}`",
        f"🔖 Bookmarks: `{int(bookmarks)}`",
    ]
    if engine_block:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", "", engine_block]
    return "\n".join(lines)


#: The headline actions of the /admin panel.  A tuple of one or more commands
#: per line — ``("ban", "unban")`` is rendered as the single moderation pair
#: ``🚫 /ban & /unban — User Moderation``.
ADMIN_FEATURED_PAIRS = (
    ("setfsub",), ("fsublist",), ("delfsub",), ("setchat",), ("setengine",),
    ("addpremium",), ("removepremium",), ("stats",), ("broadcast",),
    ("ban", "unban"), ("payments",), ("maintenance",),
)


def admin_featured_text() -> str:
    """The twelve most-used admin actions as descriptive English pairs."""
    lines = []
    for group in ADMIN_FEATURED_PAIRS:
        icon = ADMIN_COMMAND_ICONS.get(group[0], "•")
        commands = " & ".join(f"/{command}" for command in group)
        lines.append(f"{icon} {commands} — {admin_command_label(group[0])}")
    return "\n".join(lines)


def payment_review_owner_text(user_id, plan_title: str, amount, days, turbo: bool = False) -> str:
    """Caption the owner receives with a proof screenshot."""
    engine = ("🚀 **C++ Turbo add-on included**" if turbo
              else "⚙️ Standard plan (Python engine)")
    duration = "lifetime" if days is None else f"{int(days)} days"
    return (f"💳 **PAYMENT REVIEW**\n\n"
            f"👤 User: `{user_id}`\n"
            f"📦 Plan: **{plan_title}** • **{amount}**\n"
            f"{engine}\n"
            f"📅 Duration: {duration}\n\n"
            "🔎 Verify this screenshot against your actual payment records.\n"
            f"👑 Owner approval: `/addpremium {user_id}` — or tap ✅ Approve, which "
            "grants exactly this plan and engine.")


def payment_submitted_text(plan_title: str, amount, turbo: bool = False) -> str:
    """Confirmation the buyer sees after uploading a screenshot."""
    from config import PAYMENT_CONTACT
    engine = "🚀 C++ Turbo add-on" if turbo else "⚙️ Standard plan"
    return (f"✅ **Payment proof submitted**\n\n"
            f"📦 {plan_title} • {amount} • {engine}\n"
            f"⏳ Awaiting verification by @{PAYMENT_CONTACT}. This is not an "
            "automatic payment confirmation.\n"
            "💎 The owner will activate your premium after checking payment.")


def payment_proof_saved_text() -> str:
    """Shown when the proof is stored but could not be delivered to the owner."""
    from config import PAYMENT_CONTACT
    return (f"⚠️ **Proof saved, delivery unavailable**\n\n"
            f"Please send your screenshot directly to @{PAYMENT_CONTACT}. "
            "Your proof remains available to the owner in /payments.")
