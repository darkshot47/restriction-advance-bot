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
try:  # the reply keyboard Telegram's own chat chooser is built from
    from pyrogram.types import (
        KeyboardButton, KeyboardButtonRequestChat, ReplyKeyboardMarkup,
        ChatAdministratorRights,
    )
except Exception:  # pragma: no cover - legacy pyrogram without request_chat
    KeyboardButton = KeyboardButtonRequestChat = None
    ReplyKeyboardMarkup = ChatAdministratorRights = None

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


def private_access_keyboard(base_url: str | None = None, *, has_apk: bool = True) -> InlineKeyboardMarkup:
    """Two options for a private link, exactly as the owner asked for.

    Row 1 — **♾️ Unlimited Download** → the Vmore app (the APK comes straight
    from this deployment; without a known base URL the button asks the bot to
    send the same APK in the chat instead).
    Row 2 — the premium upsell: premium is what unlocks delivery **in the DM**.
    """
    rows = [[app_download_button(base_url, has_apk=has_apk)]]
    rows.extend(premium_upsell_keyboard().inline_keyboard)
    return keyboard(rows)


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

    User commands are listed first with emojis.  Admin tools are kept out of
    the main menu — only the ``/admins`` panel link appears for admins, at the
    very bottom, so regular users never see owner-only actions.
    """
    rows = [
        # ── User commands (everyone) ──────────────────────────────────────
        [
            button("🔐 Login", callback_data="cmd_login", style="success"),
            button("🚪 Logout", callback_data="cmd_logout", style="danger"),
        ],
        [
            button("💎 Premium", callback_data="cmd_premium", style="success"),
            button("🎁 Refer", callback_data="cmd_refer", style="primary"),
        ],
        [
            button("📊 Stats", callback_data="cmd_stats", style="primary"),
            button("📡 Set channel", callback_data="cmd_setchat", style="primary"),
        ],
        [
            button("📺 My Channels", callback_data="cmd_mychannels", style="primary"),
            button("📖 Help", callback_data="cmd_help", style="primary"),
        ],
        [
            button("⚙️ Settings", callback_data="cmd_settings", style="primary"),
            button("💬 Feedback", callback_data="cmd_feedback", style="primary"),
        ],
        # ── Admin row (owner / admins only) ───────────────────────────────
        # The /admins panel is the single entry point for all admin commands;
        # nothing else from the admin toolbox appears here.  Everybody else
        # keeps the language switch and the share button on this row.
        ([button("🛠 Admins", callback_data="cmd_admin", style="primary"),
          button("🎁 Start Giveaway", callback_data="cmd_giveaway_panel",
                 style="success")]
         if show_admin else
         [button("🌐 Language", callback_data="cmd_language", style="primary"),
          button("📤 Share Bot", callback_data="cmd_share", style="success")]),
        # ── The app ───────────────────────────────────────────────────────
        # One full-width button at the very bottom: the Vmore app, its details
        # and its download.  The red 🧠 Models Architecture page (the dual
        # engine explainer) moved one tap deeper, into 📖 Help.
        [app_footer_button()],
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


def invite_keyboard(link: str) -> InlineKeyboardMarkup:
    """Share + copy buttons for the bot invite link."""
    return keyboard([
        [button(
            "📤 Share link",
            url=f"https://t.me/share/url?url={link}&text=Check out this awesome bot!",
            style="success",
        )],
        [button("📋 Copy link", copy_text=link, style="primary")],
        [home_button()],
    ])


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
    """The help screen carries the red engines page — /start owns the app button."""
    return keyboard([
        [button("🔐 Login", callback_data="cmd_login", style="success"),
         button("💎 Premium", callback_data="cmd_premium", style="success")],
        [button("⚙️ Settings", callback_data="cmd_settings", style="primary"),
         button("💬 Feedback", callback_data="cmd_feedback", style="primary")],
        [button("📱 Vmore App", callback_data="cmd_app", style="success"),
         button("🔑 My Access Token", callback_data="cmd_gentoken", style="primary")],
        [models_architecture_button()],
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


def share_url_button(label: str, url: str, text: str | None = None,
                     style: str | None = "success") -> InlineKeyboardButton | None:
    """A ``t.me/share/url`` button — Telegram's own share sheet, one tap away.

    Tapping it opens the share sheet: the user picks **any** chat or channel and
    the payload is posted there.  This is how the bot lets a user hand over a
    private channel (or invite a friend) without ever pasting a raw link into
    the conversation, and it is the same primitive ``refer_keyboard`` uses.
    """
    from urllib.parse import quote
    if not url:
        return None
    share = f"https://t.me/share/url?url={quote(url, safe='')}"
    if text:
        share += f"&text={quote(text, safe='')}"
    return button(clamp_label(label), url=share, style=style)


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
        "**🗄 Owner workspace:** /setdump /dump /deldump — temporary staging for users with a custom caption.\n"
        "**📣 Audiences:** /broadcast — bot users + /setchat channels, excluding /setdump.\n"
        "/botcast — bot users only. /pin — bot users only, with best-effort DM pins.\n"
        "**🛠 Message tools:** /menu /cmsg /unpin /pinned /post\n\n"
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
    from config import MAX_USER_CHANNELS
    return (
        "📡 **CHANNEL DUMP SETUP**\n\n"
        "Send me the channel or group where you added me as an admin — link, "
        "@username, numeric ID or a private invite link.\n\n"
        "Example: `@mychannel` or `-1001234567890`\n\n"
        "🔒 **Private channel?** Tap **📡 Share the channel**: one button opens "
        "Telegram's own share sheet, you pick the channel and send — that tells "
        "me exactly which channel it is. You can also paste one **message "
        "link** from it (the *Copy Link* action on any post).\n\n"
        f"Each account may keep up to {int(MAX_USER_CHANNELS)} channels connected. "
        "I verify that **you** administer the channel and that **I** may post in "
        "it before anything is switched on. Use /cancel to stop."
    )


def setchat_admin_hint_text(title: str) -> str:
    return (
        f"🏁 **Channel:** {title}\n\n"
        "Tap **🔍 Check Admin Status** so I can verify that I am an administrator there with the "
        "**Post Messages** permission."
    )


def setchat_admin_ok_text(title: str, *, private: bool = False) -> str:
    """Step 3 of the wizard: prove the bot can read one real post.

    Round 8 dropped the bare message number — a number says nothing about which
    chat it came from, so the bot now asks for one **content link** from the
    channel being registered.  Round 12 dropped the forward fallback: a private
    channel's *Copy Link* action produces a link too, so every channel is
    verified the same way and no forward is ever requested.
    """
    if private:
        return (
            f"✅ **Admin verified in {title}!**\n\n"
            "Final step: send me **one message link from this channel**.\n\n"
            "👉 Open the channel, long-press any post, tap **Copy Link** and paste "
            "that link here — I can read it because I am an admin in that channel.\n\n"
            "👉 Every Telegram channel supports *Copy Link* on a post, private ones "
            "included — that link is all I need.\n\n"
            "Use /cancel to stop — nothing is saved until this step passes."
        )
    return (
        f"✅ **Admin verified in {title}!**\n\n"
        "Final step: send me **one content link from this channel** — open any post, "
        "tap **Copy Message Link** and paste it here.\n\n"
        "I read that post and confirm it really belongs to the channel being registered. "
        "A bare message number is no longer accepted.\n\n"
        "Use /cancel to stop — nothing is saved until this step passes."
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


def setchat_sample_failed_text(reason: str = "unreadable") -> str:
    """Why the content-link step failed, always with the next thing to try.

    The wizard stays alive for a retry in every case; nothing is stored.
    """
    if reason == "wrong_chat":
        return (
            "❌ **Verification failed**\n\n"
            "That post belongs to a **different chat**, not the channel you are registering.\n\n"
            "👉 Open the channel you are adding, pick one of **its** posts, copy that "
            "message link and send it. The setup is still running — nothing was saved."
        )
    if reason == "deleted":
        return (
            "❌ **Verification failed**\n\n"
            "That post has been **deleted**, so there is nothing left for me to read.\n\n"
            "👉 Pick a different post in the same channel and send its link. "
            "The setup is still running — nothing was saved."
        )
    if reason == "no_access":
        return (
            "❌ **Verification failed**\n\n"
            "I **cannot see** that channel, so I cannot read the post you linked.\n\n"
            "👉 Make sure the bot is still a member with **Post Messages** on, then send "
            "another link. The setup is still running — nothing was saved."
        )
    if reason == "not_a_link":
        return (
            "❌ **Verification failed**\n\n"
            "I need **one content link from that channel**, not a message number.\n\n"
            "👉 Open the channel, tap a post, choose **Copy Message Link** and paste it "
            "here — private channels have that action too. "
            "The setup is still running — nothing was saved."
        )
    return (
        "❌ **Verification failed**\n\n"
        "That sample message could not be read.\n\n"
        "👉 Make sure the post still exists in the channel you are registering and send "
        "its message link again. The setup is still running — nothing was saved."
    )


#: ------------------------------------------------------------------------ #:
#:  Round 5 — the person adding the channel must be an admin of it
#: ------------------------------------------------------------------------ #:

def setchat_requester_failed_text(reason: str = "not_admin", title: str | None = None) -> str:
    """The adding user is not an admin — the wizard is cancelled, plainly.

    Unlike force-sub (which fails open on an inconclusive Telegram answer), an
    inconclusive result here **fails safe**: the setup is cancelled and nothing
    is stored, so a channel can never be registered by somebody who cannot
    manage it.  No stack traces, no invite links, no raw chat ids.
    """
    where = f" in {title}" if title else ""
    if reason == "not_member":
        return (
            "🚫 **Setup cancelled**\n\n"
            f"You are **not a member** of that channel{where}, so it cannot be "
            "registered.\n\n"
            "👉 Join the channel first, ask an owner to make you an administrator, "
            "then start again with /setchat."
        )
    if reason == "error":
        return (
            "🚫 **Setup cancelled**\n\n"
            f"Telegram did not tell me reliably whether you administer that channel{where}, "
            "and I never register a channel on an uncertain answer.\n\n"
            "👉 Try again in a minute with /setchat. Nothing was saved."
        )
    return (
        "🚫 **Setup cancelled**\n\n"
        f"You are **not an administrator** of that channel{where}. Only an owner or an "
        "administrator may connect a channel to this bot.\n\n"
        "👉 Ask the channel owner to promote you, then start again with /setchat. "
        "Nothing was saved."
    )


#: ------------------------------------------------------------------------ #:
#:  Round 7 — registering a private channel by sharing it into the bot
#: ------------------------------------------------------------------------ #:

def channel_picker_rights() -> "ChatAdministratorRights":
    """The one right a connected channel needs: Post Messages.

    Both sides of the chooser button are built from this object because
    Telegram requires ``bot_administrator_rights`` to be a subset of
    ``user_administrator_rights`` (see :func:`dump_picker_rights`).
    """
    return ChatAdministratorRights(is_anonymous=False, can_post_messages=True)


def setchat_picker_keyboard() -> "ReplyKeyboardMarkup":
    """Telegram's **own** channel chooser, opened by one reply-keyboard tap.

    The keyboard is **temporary**: it belongs to the picker flow and the bot
    removes it again (``ReplyKeyboardRemove``) the moment that flow ends —
    success, ``/cancel``, any other command or button.  ``one_time_keyboard``
    alone only collapses it; the button would stay one tap away for good.

    The button carries ``request_chat``; Telegram then shows the account's
    channel list and hands the chosen chat straight back to the bot in
    ``message.chat_shared``.  Nothing is pasted and nothing is posted inside
    the channel — which is exactly why this replaced the old share-sheet deep
    link, whose whole mechanism was "post a link into the channel".

    The rights are declared up front so the chooser only lists channels where
    the bot may already be promoted to a posting admin, and the pick is limited
    to one chat.
    """
    if KeyboardButton is None or KeyboardButtonRequestChat is None:
        return None                      # pragma: no cover - legacy pyrogram
    from config import CHANNEL_PICKER_BUTTON_ID
    chooser = green_reply_button(
        "📡 Pick my channel",
        request_chat=KeyboardButtonRequestChat(
            button_id=CHANNEL_PICKER_BUTTON_ID,
            chat_is_channel=True,
            chat_has_username=None,          # private channels are the point
            bot_is_member=True,              # only chats the bot is already in
            request_title=True,
            request_username=True,
            request_photo=True,
            max_quantity=1,
            user_administrator_rights=channel_picker_rights(),
            bot_administrator_rights=channel_picker_rights(),
        ),
    )
    return ReplyKeyboardMarkup(
        [[chooser]],
        resize_keyboard=True,
        one_time_keyboard=True,
        placeholder="Tap to choose your channel",
    )


def remove_keyboard():
    """Take the reply keyboard back off the screen after a pick."""
    from pyrogram.types import ReplyKeyboardRemove
    return ReplyKeyboardRemove()


def setchat_share_prompt_keyboard(share_url: str | None = None) -> InlineKeyboardMarkup:
    """Cancel only — the picker is a reply keyboard, so it cannot share a message.

    ``share_url`` is accepted and deliberately ignored: Round 14 stopped
    posting a deep link *into* the channel, because that is what made the
    channel dirty and is no longer how a channel is handed over.
    """
    return keyboard([
        [button("❌ Cancel", callback_data="cancel_action", style="danger")],
    ])


def setchat_share_prompt_text() -> str:
    """The **fallback** copy: type a link, @username or numeric id yourself."""
    from config import MAX_USER_CHANNELS
    return (
        "📡 **SHARE THE CHANNEL**\n\n"
        "Two ways to register a channel — pick whichever works for you:\n\n"
        "1️⃣ **Tap 📡 Pick my channel** on the keyboard below. Telegram's own "
        "channel chooser opens, you tap the channel once and I receive it "
        "directly — nothing is pasted and nothing is posted inside it.\n"
        "2️⃣ **Type it instead**: a message link (*Copy Link* on any post), an "
        "`@username`, or the numeric channel id.\n\n"
        "Add me as an admin with **Post Messages** first — I can only read the "
        "channel when I am in it. Nothing is switched on until both checks pass:\n"
        "**you** administer the channel and **I** may post in it.\n\n"
        f"Each account may keep up to {int(MAX_USER_CHANNELS)} channels connected. "
        "Use /cancel to stop."
    )


def setchat_picker_text() -> str:
    """How to select a channel — written out, step by step, on the picker screen.

    Round 14 requirement: the owner must never have to guess how the chooser
    works, so every step (promote the bot, then tap, then pick) is spelled out
    here and the list is explained before it is opened.
    """
    return (
        "📡 **PICK YOUR CHANNEL**\n\n"
        "**How to select it — three steps:**\n\n"
        "1️⃣ Open the channel → **Administrators** → **Add Admin** → add this "
        "bot → switch **Post Messages** ON (and **Pin Messages** if you want "
        "/pin to work there).\n"
        "2️⃣ Come back here and tap **📡 Pick my channel** on the keyboard "
        "below. Telegram's own channel list opens.\n"
        "3️⃣ Scroll to your channel and **tap it once**. The choice arrives "
        "here by itself.\n\n"
        "Only channels where I am already an admin are listed — if yours is "
        "missing, step 1 was not finished. Nothing is posted inside your "
        "channel and no link is ever pasted.\n\n"
        "Prefer typing? Send me a message link, an `@username` or the numeric "
        "channel id instead. Use /cancel to stop."
    )


def picker_stale_text(kind: str = "setchat") -> str:
    """A tap on a picker button whose flow is over — the keyboard is taken away.

    The picker keyboard is temporary now, so this only reaches somebody whose
    screen still carries one from an older session.  Nothing is saved.
    """
    if kind == "setdump":
        return (
            "🗄 **PICK THE DUMP CHANNEL**\n\n"
            "That chooser is no longer open, so I took it off your screen and "
            "nothing was connected. Send /setdump to start again."
        )
    return (
        "📡 **PICK YOUR CHANNEL**\n\n"
        "That chooser is no longer open, so I took it off your screen and "
        "nothing was saved. Send /setchat and tap **Share the channel** to "
        "start again."
    )


def setchat_share_link_in_channel_text() -> str:
    """Round 14 — a setchat deep link was posted *inside* a channel.

    That link used to be the registration proof, and posting it is exactly what
    the new flow stops doing: a channel should never receive a bot link.  The
    owner is therefore sent here, to their private chat, and given the picker.
    """
    return (
        "📡 **Use the channel picker instead**\n\n"
        "A setup link was posted inside one of your channels. I did not read "
        "the channel off it and I did not answer in the channel — nothing was "
        "registered from it.\n\n"
        "Channels are now handed over with Telegram's own chooser, so nothing "
        "is ever posted inside them:\n\n"
        "1️⃣ Tap **📡 Pick my channel** on the keyboard below.\n"
        "2️⃣ Pick the channel in Telegram's list.\n"
        "3️⃣ I verify it and connect it.\n\n"
        "You can also send /setchat and type a link, an `@username` or the "
        "numeric channel id."
    )


def setchat_share_failed_text(reason: str = "not_a_channel") -> str:
    """Plain English for every way a share can fail — never a raw link or id."""
    if reason == "not_received":
        return (
            "❌ **That was not a message link**\n\n"
            "I need one **message link** from the channel — open the channel, "
            "long-press any post, tap **Copy Link** and send that link here.\n\n"
            "You can also tap **📤 Send to my channel** above and let Telegram's "
            "share sheet hand me the channel in one tap. Use /cancel to stop."
        )
    if reason == "cancelled":
        return (
            "🚫 **Channel sharing cancelled**\n\n"
            "Nothing was registered. Send /setchat again whenever you want to restart."
        )
    if reason == "not_a_channel":
        return (
            "❌ **That is not a channel**\n\n"
            "I can only be connected to a **channel** or a **supergroup**.\n\n"
            "👉 Send a message link from the channel itself, not from a private "
            "chat or a basic group."
        )
    if reason == "bot_not_in_chat":
        return (
            "❌ **I am not in that channel**\n\n"
            "Add this bot to the channel before sharing a post from it.\n\n"
            "👉 Channel → Administrators → Add Admin → select this bot → turn "
            "**Post Messages** ON, then share a post again."
        )
    if reason == "cannot_see":
        return (
            "❌ **I cannot see that channel**\n\n"
            "Telegram would not let me open it, so I cannot verify anything.\n\n"
            "👉 Check the bot is still a member with **Post Messages** on, then share "
            "another post."
        )
    if reason == "not_admin":
        return (
            "🚫 **Setup cancelled**\n\n"
            "You are not an administrator of the channel you shared, so it cannot be "
            "registered.\n\n"
            "👉 Ask the channel owner to promote you, then share a post again."
        )
    return (
        "❌ **That share did not work**\n\n"
        "👉 Forward one post from the channel again, or send /setchat to start over."
    )


def setchat_share_resolved_text(title: str) -> str:
    """The share was understood: report the channel and run the verifications."""
    return (
        f"📡 **Channel received:** {title}\n\n"
        "Now checking that **you** administer it and that **I** may post in it…"
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


# --------------------------------------------------------------------------- #
#  Bulk batches — private chat and dump channels share this copy
# --------------------------------------------------------------------------- #

def batch_heading_text(total: int) -> str:
    """Opening line of a private multi-link batch."""
    return f"⏳ Processing {int(total)}..."


def range_heading_text(total: int) -> str:
    """Opening line of a private range batch."""
    return f"⏳ Range: {int(total)} messages"


def batch_item_text(label) -> str:
    """Per-item status message: each item keeps its own, so nothing interleaves."""
    return f"📥 {label}"


def batch_progress_text(done: int, total: int) -> str:
    """The shared aggregate line — counts *finished* items, so it stays true
    even while several 🚀 C++ Turbo workers edit it at the same time."""
    return f"⏳ {int(done)}/{int(total)}..."


def batch_done_text(success: int, failed: int) -> str:
    """Final tally of a batch."""
    return f"✅ Done!\n✅ {int(success)} ❌ {int(failed)}"


def private_login_text() -> str:
    """A private link arrived but the user has no session logged in."""
    return ("🔒 **Private link!**\n\n"
            "Please /login first — or take it through the "
            f"{APP_NAME} app, where private links are unlimited.")


def range_preflight_text(start: int, end: int, media: int, text_only: int,
                         unavailable: int, unreadable: int = 0) -> str:
    """What the pre-flight scan actually found before the batch starts."""
    line = (f"🔎 Range {int(start)}-{int(end)} → **{int(media)}** with media, "
            f"**{int(text_only)}** text-only, **{int(unavailable)}** unavailable")
    if int(unreadable) > 0:
        # A probe failure is not proof a message is gone: those ids stay in.
        line += (f"\n\nℹ️ {int(unreadable)} could not be checked and will be "
                 "attempted anyway.")
    return line


def range_scan_text(start: int, end: int) -> str:
    """Shown while the pre-flight scan counts the range."""
    return f"🔎 Checking range {int(start)}-{int(end)}…"


def range_too_large_text(total: int, max_range: int) -> str:
    """A range bigger than the tier allows (private chat wording)."""
    return ("⚠️ Range too large!\n"
            f"🆓 Free: 20\n💎 Premium: 1000\nRequested: {int(total)} "
            f"(limit {int(max_range)})")


def range_nothing_to_extract_text(start: int, end: int, unavailable: int) -> str:
    """A range where nothing at all is extractable — no quota is consumed."""
    return ("❌ **Nothing to extract**\n\n"
            f"None of the messages in range {int(start)}-{int(end)} could be read "
            f"({int(unavailable)} unavailable). They may be deleted, empty or "
            "hidden from the bot.\n\n"
            "No quota was used. Check the range and send it again.")


def range_preflight_floodwait_text(seconds) -> str:
    return ("⏳ Telegram asked for a pause while scanning the range. "
            f"Waiting **{int(seconds)}s** before continuing…")


# --------------------------------------------------------------------------- #
#  Limits hit **inside a dump channel** — always point back to the bot
#
#  A channel is not a place for personal commands: the reply explains the limit
#  and carries the open-bot ``url=`` button (``open_bot_keyboard``) so the user
#  can continue the conversation in private.  No raw link ever appears in the
#  body copy and no personal command is advertised or accepted there.
# --------------------------------------------------------------------------- #

def channel_limit_text(kind: str, *, sent: int | None = None, used: int | None = None,
                       limit: int | None = None, size_mb: float | None = None,
                       requested: int | None = None, premium: bool = False) -> str:
    """The "limit reached — continue in the bot" notice for a dump channel."""
    from config import FREE_DAILY_LIMIT
    back = "Continue in the bot with the button below."
    if kind == "daily":
        quota = FREE_DAILY_LIMIT if limit is None else int(limit)
        spent = quota if used is None else int(used)
        return (f"🚫 **Daily Free Limit Reached**\n\n"
                f"🆓 Free accounts get **{quota} public extractions per day** — "
                f"(**{spent}/{quota}** used today).\n\n"
                f"{back}")
    if kind == "links":
        free, paid = 5, 50
        return (f"⚠️ **Too many links in one post**\n\n"
                f"🆓 Free: {free}\n💎 Premium: {paid}\n"
                f"📨 Sent: {int(sent or 0)}\n\n{back}")
    if kind == "range":
        free, paid = 20, 1000
        return (f"⚠️ **Range too large**\n\n"
                f"🆓 Free: {free}\n💎 Premium: {paid}\n"
                f"📨 Requested: {int(requested or 0)}\n\n{back}")
    if kind == "size":
        size = f"{float(size_mb):.1f} MB" if size_mb is not None else "unknown"
        return (f"❌ **File too large**\n\n"
                f"📦 Size: {size}\n🆓 Free limit: 50 MB\n💎 Premium limit: 2 GB\n\n"
                f"{back}")
    return f"⚠️ **Limit reached**\n\n{back}"


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
    # Telegram Stars payment row
    rows.append([button("⭐ Pay with Telegram Stars", callback_data="stars_plans", style="success")])
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


def stars_plans_text():
    """Telegram Stars plan list — half of the UPI price."""
    from config import PREMIUM_PLANS, plan_base_price, STAR_EXCHANGE_RATE
    lines = ["⭐ **TELEGRAM STARS PAYMENT**\n",
             "Pay with Telegram Stars — official & instant!\n",
             "💱 Rate: ₹1 = 0.5 Stars (half of UPI price)\n",
             "⭐ Stars are sent directly to the bot owner.\n"]
    for key, plan in PREMIUM_PLANS.items():
        base_inr = plan_base_price(plan)
        stars = max(1, int(base_inr * STAR_EXCHANGE_RATE))
        lines.append(f"• **{plan['title']}** — ⭐{stars} Stars (₹{base_inr})")
    lines.append("\n📲 Select a plan below. An invoice will be sent via Telegram Stars.")
    lines.append("⭐ Stars go directly to the bot owner's Telegram account.")
    return "\n".join(lines)


def stars_plans_keyboard():
    """Keyboard for Telegram Stars plan selection."""
    from config import PREMIUM_PLANS, plan_base_price, STAR_EXCHANGE_RATE
    rows = []
    for key, plan in PREMIUM_PLANS.items():
        base_inr = plan_base_price(plan)
        stars = max(1, int(base_inr * STAR_EXCHANGE_RATE))
        rows.append([button(f"⭐ {plan['title']} · {stars} Stars",
                           callback_data=f"stars_buy:{key}", style="success")])
    rows.append([button("⬅️ Back to Plans", callback_data="premium_plans", style="primary"),
                 home_button()])
    return keyboard(rows)


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
    """Feature overview + add-on pricing for a user **without** the feature.

    Every claim is engine-specific and true of this codebase: a parallel worker
    pool on multi-item batches, zero-copy in-memory piping, an **uncapped**
    transfer rate against Python Standard's ``ENGINE_PYTHON_SPEED_LIMIT_MBPS``
    cap, and priority routing above ``ENGINE_PEAK_THRESHOLD``.
    """
    from config import (ENGINE_PEAK_THRESHOLD, ENGINE_PYTHON_SPEED_LIMIT_MBPS,
                        ENGINE_TURBO_WORKERS, ENGINE_ZERO_COPY_MAX_MB,
                        PREMIUM_PLANS, RUPEE, plan_addon_price, plan_base_price)
    rows = []
    for plan in PREMIUM_PLANS.values():
        addon = plan_addon_price(plan)
        base = plan_base_price(plan)
        if not addon:
            continue
        rows.append(f"• **{plan['title']}** — {RUPEE}{base} Standard · "
                    f"+{RUPEE}{addon} with C++ Turbo = **{RUPEE}{base + addon}**")
    pricing = "\n".join(rows) or "• C++ Turbo is sold as an add-on on every plan."
    workers = max(1, int(ENGINE_TURBO_WORKERS))
    cap = speed_cap_label(ENGINE_PYTHON_SPEED_LIMIT_MBPS)
    return "\n".join([
        "🚀 **C++ TURBO ENGINE**",
        "",
        "Your account runs on the **Python Standard** engine. The C++ Turbo "
        "engine is a paid add-on:",
        "",
        f"✅ Parallel worker pool — up to {workers} items of a multi-link, "
        "range or channel batch run at once; Python Standard is single-stream",
        f"✅ Zero-copy in-memory piping up to {int(ENGINE_ZERO_COPY_MAX_MB)} MB "
        "— no temp file, no re-read",
        f"✅ Uncapped speed, against Python Standard's {cap} cap",
        f"✅ Priority routing above {int(ENGINE_PEAK_THRESHOLD)} concurrent "
        "extractions",
        "✅ Live telemetry HUD with speed, ETA and server load",
        "",
        "ℹ️ A single small file is one MTProto stream on both engines, so there "
        "Turbo only adds the zero-copy path and the missing cap.",
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


def speed_cap_label(mbps=None) -> str:
    """``~3 MB/s`` for the Python Standard cap, ``uncapped`` when there is none."""
    from config import ENGINE_PYTHON_SPEED_LIMIT_MBPS
    value = ENGINE_PYTHON_SPEED_LIMIT_MBPS if mbps is None else mbps
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0:
        return "uncapped"
    shown = int(value) if float(value).is_integer() else round(value, 1)
    return f"~{shown} MB/s"


def models_architecture_text(active=None) -> str:
    """The detailed Python vs C++ Turbo page opened by the red /start button.

    Every claim here is engine-specific and actually true of this codebase.
    TgCrypto is deliberately **not** listed as a Turbo feature: the native C
    cipher is installed for the whole bot, so both engines use it on every
    MTProto chunk and it differentiates nothing.
    """
    from config import (ENGINE_PEAK_THRESHOLD, ENGINE_PYTHON_SPEED_LIMIT_MBPS,
                        ENGINE_TURBO_WORKERS, ENGINE_ZERO_COPY_MAX_MB,
                        PAYMENT_CONTACT, PREMIUM_PLANS, RUPEE, plan_addon_price,
                        plan_base_price)
    workers = max(1, int(ENGINE_TURBO_WORKERS))
    zero_copy_mb = max(0, int(ENGINE_ZERO_COPY_MAX_MB))
    cap = speed_cap_label(ENGINE_PYTHON_SPEED_LIMIT_MBPS)
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
        "• One item at a time per batch, strictly in the order you sent",
        f"• Download throughput capped at {cap} by a token-bucket pacer",
        "• Buffered transfer: streamed to disk, then re-uploaded",
        "• Included in every plan, free tier included",
        "",
        "🚀 **C++ TURBO**",
        f"• Parallel worker pool — up to {workers} items of a multi-link, range "
        "or channel batch run at the same time (Python Standard is single-stream)",
        f"• Zero-copy in-memory piping: files up to {zero_copy_mb} MB are handed "
        "to the uploader straight from memory — no temp file, no re-read",
        "• Uncapped speed — no throughput limit at all, against Python "
        f"Standard's {cap} cap",
        f"• Priority routing above {int(ENGINE_PEAK_THRESHOLD)} concurrent "
        "extractions",
        "",
        "📊 **TRAFFIC HANDLING**",
        "• Python Standard: 1 stream per batch — queues grow with traffic",
        f"• C++ Turbo: {workers} overlapping streams per batch — the download "
        "and the upload of different files run at the same time",
        "• Item starts stay spaced by the anti-ban gap on both engines, so "
        "parallelism never turns into hammering Telegram",
        "",
        "🔍 **WHERE TURBO DOES NOT CHANGE ANYTHING**",
        "A single small file is **one MTProto stream on both engines** — there "
        "is nothing to parallelise, so the worker pool stays idle. The win on "
        "that path is only the zero-copy piping (no temp file, no re-read) and "
        "the missing speed cap. Turbo pays off on batches: multi-link posts, "
        "ranges and dump-channel posts.",
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


def channel_entries(value) -> list[dict]:
    """Normalize any ``/mychannels`` argument into a list of channel entries.

    Accepts ``None`` (nothing connected), a bare chat id, one entry dict or a
    list of entries, so the single-channel call sites keep working unchanged
    while the dashboard can now render both of a user's channels.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, (list, tuple)):
        return [entry for entry in value if isinstance(entry, dict) and entry.get("chat_id")]
    try:
        return [{"chat_id": int(value), "title": None, "username": None, "type": "channel"}]
    except (TypeError, ValueError):
        return []


def mychannels_keyboard(chat_id, *, connected: bool = True) -> InlineKeyboardMarkup:
    """Test permissions / re-verify admin rights / disconnect.

    With two channels connected every action is numbered per channel, and the
    whole dashboard still fits the mobile budget (max 7 rows, max 2 buttons per
    row, labels at most 28 visible characters).
    """
    entries = channel_entries(chat_id) if connected else []
    rows = []
    if len(entries) == 1:
        cid = int(entries[0]["chat_id"])
        rows += [
            [button("🔍 Test Permissions", callback_data=f"mych_test:{cid}", style="primary"),
             button("🔄 Re-verify Admin", callback_data=f"mych_verify:{cid}", style="primary")],
            [button("🗑 Disconnect", callback_data=f"mych_del:{cid}", style="danger")],
        ]
    elif entries:
        numbered = []
        for index, entry in enumerate(entries, start=1):
            cid = int(entry["chat_id"])
            numbered += [
                button(f"🔍 Test {index}", callback_data=f"mych_test:{cid}", style="primary"),
                button(f"🔄 Verify {index}", callback_data=f"mych_verify:{cid}", style="primary"),
                button(f"🗑 Disconnect {index}", callback_data=f"mych_del:{cid}", style="danger"),
            ]
        for start in range(0, len(numbered), 2):
            rows.append(numbered[start:start + 2])
    rows.append([button("📡 Set channel", callback_data="cmd_setchat", style="success"),
                 home_button()])
    return keyboard(rows)


def delchat_choice_keyboard(entries) -> InlineKeyboardMarkup:
    """/delchat with two channels connected: pick the one to disconnect."""
    from config import CHANNEL_TITLE_FALLBACK
    rows = []
    for index, entry in enumerate(channel_entries(entries), start=1):
        title = entry.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=entry["chat_id"])
        rows.append([button(clamp_label(f"🗑 {index}. {title}"),
                            callback_data=f"delchat_pick:{int(entry['chat_id'])}",
                            style="danger")])
    rows.append([button("❌ Keep both", callback_data="cancel_action", style="primary")])
    return keyboard(rows)


def delchat_choice_text(entries) -> str:
    """/delchat asks which of the two connected channels to disconnect."""
    from config import CHANNEL_TITLE_FALLBACK
    lines = ["🗑 **DISCONNECT A CHANNEL**", ""]
    for index, entry in enumerate(channel_entries(entries), start=1):
        chat_id = entry["chat_id"]
        title = entry.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
        lines.append(f"{index}️⃣ **{title}** — `{chat_id}`")
    lines += ["", "Tap the channel you want to disconnect. The other one keeps working."]
    return "\n".join(lines)


def channel_limit_reached_text(kind: str = "daily") -> str:
    """A limit hit **inside a dump channel**: go back to the bot to continue.

    Deliberately short and command-free — a channel is not a dashboard, so the
    only way forward offered here is the open-bot ``url=`` button that always
    accompanies this text.
    """
    headings = {
        "daily": "🚫 **Daily Free Limit Reached**",
        "links": "🚫 **Too Many Links In One Post**",
        "range": "🚫 **Range Too Large**",
        "size": "🚫 **File Too Large**",
    }
    return "\n".join([
        headings.get(kind, headings["daily"]),
        "",
        "This limit cannot be lifted from inside the channel.",
        "",
        "👉 Open the bot with the button below to check your remaining quota, "
        "upgrade or continue there.",
    ])


def channel_rights_text(admin_ok, admin_reason: str = "") -> str:
    """The posting-rights line of one channel row."""
    if admin_ok is None:
        return "❔ Not checked yet — tap **Test Permissions**"
    if admin_ok:
        return "✅ Admin with posting rights"
    reasons = {
        "not_admin": "❌ The bot is not an admin there",
        "no_post_rights": "⚠️ Admin, but **Post Messages** is disabled",
        "error": "❔ Telegram did not answer — try again",
    }
    return reasons.get(admin_reason, "❌ Cannot post there")


def channel_kind_label(entry) -> str:
    kind = str((entry or {}).get("type") or (entry or {}).get("kind") or "").lower()
    return {"supergroup": "Supergroup", "group": "Group",
            "channel": "Channel"}.get(kind, "Channel or supergroup")


def mychannels_text(entry, *, admin_ok=None, admin_reason: str = "", files=0,
                    engine=None, rights=None) -> str:
    """The dashboard: title, id, type, posting rights, files and engine badge.

    ``entry`` may be one channel dict (the original single-channel shape) or a
    list of them; ``files`` and ``rights`` may then be per-channel lists, so
    both counters stay separate and truthful.
    """
    from config import CHANNEL_TITLE_FALLBACK
    entries = channel_entries(entry)
    single = not isinstance(entry, (list, tuple))
    counts = list(files) if isinstance(files, (list, tuple)) else [files] * max(1, len(entries))
    probes = list(rights) if isinstance(rights, (list, tuple)) else [admin_ok] * max(1, len(entries))
    lines = ["📺 **MY CHANNELS**"]
    if not entries:
        entry = entry or {}
        chat_id = entry.get("chat_id")
        title = entry.get("title") or (CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
                                       if chat_id else "Unknown chat")
        lines += ["", f"📌 **{title}**", f"🆔 ID: `{chat_id}`",
                  f"🗂 Type: {channel_kind_label(entry)}",
                  f"🔐 Bot posting rights: {channel_rights_text(admin_ok, admin_reason)}",
                  f"📦 Files extracted here: **{int(counts[0] or 0)}**"]
    else:
        from config import MAX_USER_CHANNELS
        if not single:
            lines += ["", f"🔗 Connected: **{len(entries)}/{int(MAX_USER_CHANNELS)}**"]
        for index, row in enumerate(entries, start=1):
            chat_id = row.get("chat_id")
            title = row.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
            probe = probes[index - 1] if index - 1 < len(probes) else None
            count = counts[index - 1] if index - 1 < len(counts) else 0
            head = f"📌 **{title}**" if single else f"📌 **{index}. {title}**"
            lines += ["", head, f"🆔 ID: `{chat_id}`",
                      f"🗂 Type: {channel_kind_label(row)}",
                      f"🔐 Bot posting rights: {channel_rights_text(probe, admin_reason)}",
                      f"📦 Files extracted here: **{int(count or 0)}**"]
            username = row.get("username")
            if username:
                lines.append(f"🔗 Public handle: @{username}")
    if engine:
        lines += ["", active_engine_status(engine)]
    lines += ["", "Use the buttons below to test the bot's permissions, re-verify "
                 "admin rights or disconnect a channel."]
    return "\n".join(lines)


def channel_slots_full_text(entries) -> str:
    """Round 4: the account already holds ``MAX_USER_CHANNELS`` channels.

    Plain English, no raw links, and the chat ids only where the dashboard
    already shows them (inline ``code``), so the user can tell the two apart
    before disconnecting one.
    """
    from config import CHANNEL_TITLE_FALLBACK, MAX_USER_CHANNELS
    limit = max(1, int(MAX_USER_CHANNELS))
    rows = []
    for index, entry in enumerate(channel_entries(entries), start=1):
        chat_id = entry["chat_id"]
        title = entry.get("title") or CHANNEL_TITLE_FALLBACK.format(chat_id=chat_id)
        rows.append(f"{index}️⃣ **{title}** — `{chat_id}`")
    listed = "\n".join(rows) or "• your connected channels"
    return "\n".join([
        "🚫 **CHANNEL LIMIT REACHED**",
        "",
        f"An account may keep **{limit}** channels connected, and yours is full:",
        "",
        listed,
        "",
        "👉 Disconnect one of them first, then run /setchat again to add the new "
        "channel.",
    ])


def setchat_prompt_keyboard() -> InlineKeyboardMarkup:
    """Step 1 of /setchat: type a reference, or share a private channel."""
    return keyboard([
        [button("📡 Share the channel", callback_data="setchat:share", style="primary")],
        [button("❌ Cancel", callback_data="cancel_action", style="danger")],
    ])


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
    "broadcast": "Users + /setchat Channels (Not Dump)",
    "botcast": "Broadcast to Bot Users Only",
    "cmsg": "Customize a Message",
    "unpin": "Unpin Configured Channels",
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
    # Owner tools (pinning, the dump channel, giveaways, the native engine).
    "pin": "Broadcast & Pin Bot User DMs",
    "pinned": "Remove the Live Pin",
    "setdump": "Connect Dump Channel",
    "deldump": "Disconnect Dump Channel",
    "dump": "Dump Channel Status",
    "post": "Post in the Dump Channel",
    "native": "Native C++ Engine Status",
    "giveaway": "Giveaway Control",
    "participants": "Giveaway Participants",
    "endgiveaway": "End Giveaway & Draw",
    # The Vmore app: who really uses it, and the APK the bot serves.
    "appusers": "Vmore App Users (Real Logins)",
    "apk": "Connect the App APK + Server URL",
}

#: Emoji shown in front of each command in the panel text.
ADMIN_COMMAND_ICONS = {
    "setfsub": "📢", "fsublist": "📋", "delfsub": "🗑️", "setchat": "⚙️",
    "setengine": "🧠", "addpremium": "💎", "removepremium": "❌", "stats": "📊",
    "broadcast": "📢", "botcast": "🤖", "cmsg": "🎨", "unpin": "📍",
    "ban": "🚫", "unban": "🚫", "payments": "💳",
    "maintenance": "🛠️", "users": "👥", "loggedusers": "🔐", "newusers": "🆕",
    "activeusers": "📈", "topusers": "🏆", "finduser": "🔎", "userinfo": "ℹ️",
    "export": "📤", "premiumlist": "💎", "addqr": "🖼", "delqr": "🗑️",
    "removeqr": "🗑️", "sendmsg": "✉️", "banlist": "🚫", "feedbacks": "💬",
    "addadmin": "🛡", "removeadmin": "🛡", "adminlist": "🛡", "clearlogs": "🧹",
    "adminhelp": "❓", "fsublabel": "🏷", "fsubcheck": "🩺", "delchat": "🗑️",
    "redeem": "🎁", "pin": "📌", "pinned": "📍", "setdump": "🗄", "deldump": "🗑️",
    "dump": "📊", "post": "📰", "native": "⚡", "giveaway": "🎁",
    "participants": "👥", "endgiveaway": "🏆",
    "appusers": "📱", "apk": "📦",
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


# --------------------------------------------------------------------------- #
#  Telegram's official command menu (setMyCommands)
# --------------------------------------------------------------------------- #

#: Every command a normal user may run: ``(command, emoji, what it does)``.
#: ``/start`` comes first.  The bot publishes exactly this list as the menu of
#: every private chat, so the description Telegram shows is the emoji, a space
#: and then what the command does — never a bare command name.
USER_MENU = (
    ("start", "🚀", "Start the bot and open the main menu"),
    ("help", "📖", "Learn how to use the bot"),
    ("login", "🔐", "Log in to your Telegram account"),
    ("logout", "🚪", "Log out of your Telegram account"),
    ("status", "🔎", "Check your login status"),
    ("cancel", "❌", "Cancel what you are doing right now"),
    ("setcaption", "✏️", "Set a custom caption for your downloads"),
    ("delcaption", "🧽", "Remove your custom caption"),
    ("setprefix", "🔤", "Add a prefix to every caption"),
    ("setsuffix", "🔡", "Add a suffix to every caption"),
    ("setthumb", "🖼️", "Set a custom thumbnail"),
    ("delthumb", "🗑️", "Remove your custom thumbnail"),
    ("setchat", "📡", "Connect a channel to extract links in"),
    ("delchat", "🔌", "Disconnect a connected channel"),
    ("mychannels", "📺", "Manage your connected channels"),
    ("models", "🧠", "Choose your download engine"),
    ("engine", "🚀", "Switch between Python and C++ Turbo"),
    ("mystats", "📊", "See your download statistics"),
    ("myinfo", "👤", "View your profile and plan"),
    ("history", "📜", "Show your last 10 downloads"),
    ("settings", "⚙️", "Open your settings"),
    ("language", "🌐", "Change the bot language"),
    ("premium", "💎", "See premium plans and benefits"),
    ("redeem", "🏆", "Redeem your points for premium"),
    ("refer", "🎁", "Invite friends and earn points"),
    ("invite", "🔗", "Get the invite link of this bot"),
    ("share", "📤", "Share this bot with your friends"),
    ("bookmark", "🔖", "Save a link to your bookmarks"),
    ("bookmarks", "📚", "Show your saved bookmarks"),
    ("favorite", "⭐", "Add a channel to your favorites"),
    ("favorites", "🌟", "Show your favorite channels"),
    ("feedback", "💬", "Send feedback to the owner"),
    # The app: the details page, the access token and its revoke switch.
    ("app", "📱", "Open the Vmore app page"),
    ("gentoken", "🔑", "Create your app access token"),
    ("revoketoken", "🚫", "Revoke your app access token"),
)

#: Owner / admin commands whose menu line is written here instead of being
#: taken from the admin-panel label tables.
STAFF_MENU_EXTRA = {
    "menu": ("🧰", "Open the message tools for a replied message"),
    "giveawaystatus": ("📊", "Show the running giveaway"),
    "admin": ("🛡", "Open the admin panel"),
    "admins": ("🛡", "Open the admin panel"),
    # The panel labels of these read badly as a one-line menu entry.
    "broadcast": ("📢", "Broadcast to bot users and your channels"),
    "ban": ("🚫", "Ban a user"),
    "unban": ("✅", "Unban a user"),
}

#: Emoji for a staff command that has a label but no icon of its own.
STAFF_MENU_FALLBACK_ICON = "🛠️"


def user_menu_commands() -> list:
    """``[(command, description), ...]`` — /start first, then the user commands."""
    return [(name, f"{emoji} {text}") for name, emoji, text in USER_MENU]


def staff_menu_description(command: str) -> str:
    """``"<emoji> <label>"`` for an owner/admin command in the menu."""
    if command in STAFF_MENU_EXTRA:
        emoji, text = STAFF_MENU_EXTRA[command]
    else:
        emoji = ADMIN_COMMAND_ICONS.get(command, STAFF_MENU_FALLBACK_ICON)
        text = admin_command_label(command)
    return f"{emoji} {text}"[:256]


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


# --------------------------------------------------------------------------- #
#  /pin and /pinned — pin any message, drop the live pin
# --------------------------------------------------------------------------- #

def pin_usage_text() -> str:
    return (
        "📌 **PIN FOR BOT USERS**\n\n"
        "Reply to a message with /pin to copy it to registered bot users only, "
        "then attempt to pin each user's DM. Never posts or pins in /setchat "
        "channels or uses /setdump as a final audience.\n\n"
        "Private-chat pins are best-effort: Telegram may refuse them. "
        "The final report lists deliveries, pin attempts, accepted and refused pins.\n\n"
        "Existing `/pin <message link>` and `/pin <message id>` select the source "
        "for the same DM-only broadcast. /pinned and /unpin retain their unpin tools."
    )


def pin_no_target_text() -> str:
    return (
        "📌 **Nothing to pin**\n\n"
        "Reply to a message with /pin, send `/pin <message link>`, or connect a "
        "dump channel with /setdump and try again."
    )


def pin_done_text(chat_title: str, msg_id) -> str:
    return (f"📌 **Pinned in {chat_title}**\n\n"
            f"Message id: `{msg_id}`\n\n"
            "Pinned messages stay at the top of the chat for everyone. "
            "Send /pinned to remove it.")

#: Plain English for every way a pin can be refused.  Round 14 made these
#: distinct on purpose: "pin failed" told the owner nothing, while each of
#: these names the one thing that has to change.
PIN_FAILED_TEXTS = {
    "already_pinned": (
        "📌 **Already pinned**\n\n"
        "That exact message is the live pin in that chat right now, so there is "
        "nothing to do. Send /pinned to remove it first if you want it gone."
    ),
    "no_rights": (
        "⚠️ **I cannot pin here**\n\n"
        "Telegram's **Pin Messages** right is missing in that chat.\n\n"
        "👉 Add the bot as an admin with **Pin Messages** enabled and try "
        "again. Nothing was pinned."
    ),
    "no_access": (
        "🔒 **I cannot reach that chat**\n\n"
        "Telegram would not let me open it, so I can neither read its messages "
        "nor pin anything there.\n\n"
        "👉 Make sure I am still a member of the channel with **Pin Messages** "
        "on, then try again. Nothing was pinned."
    ),
    "floodwait": (
        "⏳ **Telegram asked me to slow down**\n\n"
        "I paused for the number of seconds Telegram asked for and stopped "
        "there — hammering on would only earn a longer restriction.\n\n"
        "👉 Send /pin again in a moment. Nothing was pinned yet."
    ),
    "not_found": (
        "❌ **I could not find that message**\n\n"
        "Check that the link belongs to the chat you are pinning in (or to your "
        "dump channel) and that I can still read it. Nothing was pinned.\n\n"
        "👉 Try the link again, or open the post and reply to it with /pin."
    ),
    "no_target": (
        "📌 **Nothing to pin**\n\n"
        "Reply to a message with /pin, send `/pin <message link>`, or connect a "
        "dump channel with /setdump and try again.\n\n"
        "👉 Send /pin on its own to see all three ways."
    ),
}


def pin_failed_text(reason: str = "error") -> str:
    if reason in PIN_FAILED_TEXTS:
        return PIN_FAILED_TEXTS[reason]
    return (
        "❌ **Pinning failed**\n\n"
        "Telegram did not accept the pin this time. Try again in a moment — "
        "nothing was pinned."
    )


def pinned_none_text(chat_title: str) -> str:
    return (f"📍 **No live pin in {chat_title}**\n\n"
            "There is no pinned message there right now, so there is nothing to "
            "remove.")


def unpin_done_text(chat_title: str) -> str:
    return (f"📍 **Live pin removed in {chat_title}**\n\n"
            "The message is still in the chat — only the pin is gone. "
            "Send /pin to pin something else.")


def pin_offer_text() -> str:
    return ("📌 **Pin this message?**\n\n"
            "I can pin the message I just posted so it stays on top of the chat "
            "for everyone.")


def pin_offer_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("📌 Pin it", callback_data="pin_offer:yes", style="success"),
         button("⏭ Not now", callback_data="pin_offer:no", style="primary")],
    ])


def message_menu_text() -> str:
    return ("🧰 **MESSAGE ACTIONS**\n\n"
            "Choose what to do with the message you replied to. Broadcast copies "
            "go straight to connected owner channels and bot users — the dump "
            "channel is never used for them.")


def unpin_complete_text(report: dict) -> str:
    total = int(report.get("channels_total", 0))
    done = int(report.get("unpinned", 0))
    failed = int(report.get("failed", 0))
    if total == 0:
        return ("📍 **NO CHANNELS CONNECTED**\n\n"
                "Connect a channel with /setdump or /setchat before using /unpin.")
    text = f"📍 **UNPIN COMPLETE**\n\nChannels checked: {total}\nPins removed: {done}"
    if failed:
        text += f"\n⚠️ Could not unpin: {failed}"
    return text


def message_menu_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("📌 Pin + broadcast", callback_data="msgmenu:pin", style="success"),
         button("📢 Broadcast all", callback_data="msgmenu:broadcast", style="primary")],
        [button("🤖 Bot users only", callback_data="msgmenu:botcast", style="primary"),
         button("🎨 Customize (cMSG)", callback_data="msgmenu:cmsg", style="success")],
        [button("📍 Unpin", callback_data="msgmenu:unpin", style="danger"),
         button("❌ Close", callback_data="msgmenu:close", style="danger")],
    ])


def custom_message_prompt_text() -> str:
    return ("🎨 **CUSTOM MESSAGE**\n\n"
            "Reply to any message with /cMSG, or send /cMSG and then send the "
            "message you want to customize. Add up to three blue, green or red "
            "inline buttons; I send it with the buttons attached to connected "
            "channels and bot users without an Edited label. Use /cancel to stop.")


def custom_message_offer_text(preview: str) -> str:
    return ("🎨 **CUSTOM MESSAGE READY**\n\n"
            f"┌ {preview}\n\n"
            "Add up to three coloured inline buttons, then send the finished "
            "copy to connected channels and bot users — or send it plain.")


def broadcast_complete_text(report: dict, *, users_only: bool = False,
                            pin: bool = False) -> str:
    channels_total = int(report.get("channels_total", 0))
    channels_sent = int(report.get("channels_sent", 0))
    users_total = int(report.get("users_total", 0))
    users_sent = int(report.get("users_sent", 0))
    lines = ["✅ **BROADCAST COMPLETE**", ""]
    if not users_only:
        lines.append(f"📣 Channels: {channels_sent}/{channels_total}")
    lines.append(f"🤖 Bot users: {users_sent}/{users_total}")
    if pin:
        lines.append(f"📌 Channel copies pinned: {int(report.get('pinned_channels', 0))}")
        pin_failures = int(report.get("pin_failed_channels", 0))
        if pin_failures:
            lines.append(f"⚠️ Could not pin {pin_failures} channel copy/copies. "
                         "The bot needs **Pin Messages** rights in each channel.")
        user_attempts = int(report.get("users_sent", 0))
        lines.append("ℹ️ Private-chat pins are best-effort: "
                     f"{int(report.get('pinned_users', 0))} accepted from "
                     f"{user_attempts} attempts; {int(report.get('pin_failed_users', 0))} refused.")
        if int(report.get("pin_failed_users", 0)):
            lines.append("Telegram or the chat's pin settings refused some private pins; "
                         "they are not guaranteed.")
    failures = int(report.get("failed", 0))
    blocked = int(report.get("blocked", 0))
    if failures:
        lines.append(f"⚠️ Could not deliver: {failures}")
    if blocked:
        lines.append(f"🚫 Blocked / unavailable bot users: {blocked}")
    if not users_only and channels_total == 0:
        lines.append("No delivery channel is connected. Use /setchat. /setdump is staging only and is excluded from audiences.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Owner dump channel — /setdump
# --------------------------------------------------------------------------- #

def setdump_prompt_keyboard(share_url: str | None = None) -> InlineKeyboardMarkup:
    """Compatibility keyboard for old deep links: only offers cancellation.

    New setup uses :func:`setdump_picker_keyboard`, because a reply keyboard is
    required for Telegram's native channel chooser. ``share_url`` is ignored.
    """
    return keyboard([[button("❌ Cancel", callback_data="cancel_action", style="danger")]])


def dump_picker_rights() -> "ChatAdministratorRights":
    """The admin rights the dump channel needs — Post **and** Delete Messages.

    The workspace has to remove its own staged copies, so the bot needs both
    rights.  Telegram insists that ``bot_administrator_rights`` is a **subset**
    of ``user_administrator_rights`` (the Bot API says the user's rights "must
    be a superset" of the bot's); a button whose bot rights are not covered by
    the user rights is rejected as an invalid reply markup.  That is exactly
    why ``/setdump`` used to answer with nothing at all: the user side asked
    for Post Messages only while the bot side also asked for Delete Messages.
    Both sides are therefore built from this one object.
    """
    return ChatAdministratorRights(
        is_anonymous=False, can_post_messages=True, can_delete_messages=True)


def setdump_picker_keyboard() -> "ReplyKeyboardMarkup":
    """Open Telegram's channel chooser for the owner's dump channel.

    Like the channel picker this keyboard is temporary: the bot takes it off
    the screen as soon as ``/setdump`` finishes or is abandoned.
    """
    if KeyboardButton is None or KeyboardButtonRequestChat is None:
        return None  # pragma: no cover - legacy Pyrogram without request_chat
    from config import DUMP_PICKER_BUTTON_ID
    chooser = green_reply_button(
        "🗄 Pick my dump",
        request_chat=KeyboardButtonRequestChat(
            button_id=DUMP_PICKER_BUTTON_ID,
            chat_is_channel=True,
            chat_has_username=None,
            bot_is_member=True,
            request_title=True,
            request_username=True,
            request_photo=True,
            max_quantity=1,
            user_administrator_rights=dump_picker_rights(),
            bot_administrator_rights=dump_picker_rights(),
        ),
    )
    return ReplyKeyboardMarkup(
        [[chooser]], resize_keyboard=True, one_time_keyboard=True,
        placeholder="Tap to choose your dump channel",
    )


def setdump_prompt_text() -> str:
    from config import DUMP_TTL_SECONDS
    minutes = max(1, int(DUMP_TTL_SECONDS) // 60)
    return (
        "🗄 **DUMP CHANNEL SETUP**\n\n"
        "The dump is a temporary workspace for **your users' downloads and "
        "messages** — and only for a user who has a custom caption switched on "
        "(/setcaption, /setprefix or /setsuffix). For such a link I download "
        "the content into this channel first, put the caption on it there, "
        "then copy it from here to the user without a *Forwarded from* or "
        "*Edited* label. The staged copy is removed right after delivery "
        f"(the mirror TTL is {minutes} minutes as a safety net).\n\n"
        "Everyone else, and your own broadcasts and custom messages, are "
        "delivered directly and never touch the dump.\n\n"
        "Tap **🗄 Pick my dump** below to choose the channel with Telegram's own "
        "channel picker, or send its link, `@username` or numeric id here.\n\n"
        "I must already be an administrator with posting and delete rights. "
        "Use /deldump to disconnect and /cancel to stop."
    )


def setdump_done_text(title: str, chat_id) -> str:
    from config import DUMP_TTL_SECONDS
    minutes = max(1, int(DUMP_TTL_SECONDS) // 60)
    return (
        f"✅ **Dump channel connected: {title}**\n\n"
        "A download or message requested by a user with a custom caption is "
        "now staged here first, captioned here and copied from here to the "
        "user. Staged copies are removed right after delivery (a leftover "
        f"copy expires after {minutes} minutes). FloodWait pauses are handled "
        "automatically.\n\n"
        "Other users, and your own broadcasts, never touch this channel.\n\n"
        "Send /dump for the live status or /deldump to disconnect."
    )


def setdump_removed_text(title: str | None = None) -> str:
    name = f"**{title}**" if title else "the dump channel"
    return (f"🗑 **Dump channel disconnected**\n\n"
            f"I no longer mirror extractions into {name}. "
            "Send /setdump to connect one again.")


def dump_status_text(entry, stats: dict | None = None, permissions: dict | None = None) -> str:
    from config import DUMP_TTL_SECONDS, DUMP_COOLDOWN_SECONDS
    stats = stats or {}
    if not entry:
        return ("🗄 **DUMP CHANNEL**\n\n"
                "No dump channel is connected.\n\n"
                "👉 Send /setdump to connect a temporary workspace. For a user "
                "with a custom caption the bot stages the download there, then "
                "copies it to that user so the recipient sees no *Forwarded* or "
                "*Edited* label. Everyone else is served directly.")
    permissions = permissions or {"post": None, "delete": None, "ready": False, "reason": "error"}
    title = entry.get("title") or f"chat {entry.get('chat_id')}"
    username = entry.get("username")
    lines = [
        "🗄 **DUMP CHANNEL**",
        "",
        f"📌 **{title}**",
        f"🆔 `{entry.get('chat_id')}`",
    ]
    if username:
        lines.append(f"🔗 @{username}")
    lines += [
        f"🧬 **Type:** {entry.get('kind') or 'channel'}",
        "✅ Connected / ready for staging" if permissions["ready"] else "⚠️ Configured / NOT ready for staging",
        "Post Messages: " + {True: "allowed", False: "missing", None: "unknown (check failed)"}[permissions["post"]],
        "Delete Messages: " + {True: "allowed", False: "missing", None: "unknown (check failed)"}[permissions["delete"]],
        "" if permissions["ready"] else dump_admin_failed_text(permissions["reason"]),
        "",
        "🎯 **Used for:** users' downloads and messages with a custom caption",
        f"⏳ **Mirror TTL:** {int(DUMP_TTL_SECONDS)} s "
        f"({max(1, int(DUMP_TTL_SECONDS) // 60)} min) then a leftover copy deletes itself",
        f"🐢 **Flood cooldown:** {DUMP_COOLDOWN_SECONDS:g} s between dump operations",
        f"📦 **Queued for deletion:** {int(stats.get('pending', 0))}",
        f"🪞 **Staged this run:** {int(stats.get('mirrored', 0))}",
        f"🗑 **Deleted this run:** {int(stats.get('deleted', 0))}",
        f"⏸ **FloodWait pauses:** {int(stats.get('pauses', 0))} "
        f"({int(stats.get('wait_seconds', 0))} s total)",
        "",
        "Copies never carry a *Forwarded from* header (the bot copies the "
        "message instead of forwarding it), and every delete runs through the "
        "FloodWait governor so a busy channel stays safe.",
    ]
    return "\n".join(lines)


def dump_status_keyboard(connected: bool) -> InlineKeyboardMarkup:
    """Dump channel dashboard — mirrors the ``/mychannels`` layout for the dump.

    When a dump is connected the owner gets a *Pick my dump* button (Telegram's
    native channel chooser) plus a test-permissions action, so the dump channel
    can be reconfigured or re-verified without leaving the flow.
    """
    rows = []
    if connected:
        rows.append([button("🗄 Pick my dump", callback_data="cmd_setdump",
                             style="success"),
                     button("🔍 Test Permissions", callback_data="dump:test",
                             style="primary")])
        rows.append([button("🗑 Disconnect", callback_data="dump:off", style="danger")])
    else:
        rows.append([button("🗄 Connect dump channel", callback_data="cmd_setdump",
                             style="success")])
    rows.append([home_button()])
    return keyboard(rows)


# --------------------------------------------------------------------------- #
#  Inline-button wizard — colour + link for any outgoing message
# --------------------------------------------------------------------------- #

def buttons_offer_text(preview: str) -> str:
    body = (
        " 🎛 **ADD INLINE BUTTONS?**\n\n"
        "Your message is ready:\n\n"
        f"┌ {preview}\n\n"
        "I can attach inline buttons to it. Tell me the **colour** and the "
        "**link** and I will build them — or skip and send it plain."
    )
    return body.lstrip()


def buttons_offer_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("✅ Yes, add buttons", callback_data="btnwiz:yes", style="success")],
        [button("⏭ Send without", callback_data="btnwiz:skip", style="primary")],
        [button("❌ Cancel everything", callback_data="btnwiz:cancel", style="danger")],
    ])


def button_color_text() -> str:
    return ("🎨 **BUTTON COLOUR**\n\n"
            "Pick the colour Telegram should render the button in:\n\n"
            "🔵 Blue — neutral links\n"
            "🟢 Green — the main action you want people to take\n"
            "🔴 Red — a warning, a stop, or a competing offer\n\n"
            "You can add up to "
            f"{__import__('config').MAX_MESSAGE_BUTTONS} buttons per message.")


def button_color_keyboard() -> InlineKeyboardMarkup:
    from config import BUTTON_COLORS
    rows = [[button(spec["label"], callback_data=f"btnwiz:color:{name}",
                    style=spec["style"])] for name, spec in BUTTON_COLORS.items()]
    rows.append([button("❌ Cancel everything", callback_data="btnwiz:cancel",
                        style="danger")])
    return keyboard(rows)


def button_label_text() -> str:
    from config import MAX_BUTTON_LABEL
    return ("✍️ **BUTTON TEXT**\n\n"
            f"Send the label people will see (max {int(MAX_BUTTON_LABEL)} "
            "characters, emojis welcome).\n\n"
            "Example: `🎬 Join Now`")


def button_label_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[button("❌ Cancel everything", callback_data="btnwiz:cancel",
                             style="danger")]])


def button_link_text(label: str) -> str:
    return ("🔗 **BUTTON LINK**\n\n"
            f"Send the address the **{label}** button should open.\n\n"
            "Paste it exactly as you copied it — your channel's invite link, a "
            "channel username, or any website address. I add the missing "
            "prefix myself if you leave it out.\n\n"
            "Tap **No link (just text)** if the button only has to look good.")


def button_link_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("⏭ No link (just text)", callback_data="btnwiz:link:none",
                style="primary")],
        [button("❌ Cancel everything", callback_data="btnwiz:cancel", style="danger")],
    ])


def buttons_summary(buttons) -> str:
    """One line per button already designed, used by the wizard's review step."""
    if not buttons:
        return "• no buttons yet"
    from config import BUTTON_COLORS
    lines = []
    for entry in buttons:
        color = BUTTON_COLORS.get(entry.get("color"), {}).get("label", entry.get("color"))
        link = entry.get("url") or "no link"
        lines.append(f"{color} — **{entry.get('label')}** → `{link}`")
    return "\n".join(lines)


def button_more_text(buttons) -> str:
    from config import MAX_MESSAGE_BUTTONS
    remaining = max(0, int(MAX_MESSAGE_BUTTONS) - len(buttons or []))
    return ("🧩 **BUTTONS SO FAR**\n\n"
            f"{buttons_summary(buttons)}\n\n"
            f"You can add {remaining} more, send the message now, or cancel "
            "everything.")


def button_more_keyboard(buttons) -> InlineKeyboardMarkup:
    from config import MAX_MESSAGE_BUTTONS
    rows = []
    if len(buttons or []) < int(MAX_MESSAGE_BUTTONS):
        rows.append([button("➕ Add another", callback_data="btnwiz:add", style="primary")])
    rows.append([button("📤 Send it now", callback_data="btnwiz:send", style="success")])
    rows.append([button("❌ Cancel everything", callback_data="btnwiz:cancel",
                        style="danger")])
    return keyboard(rows)


def custom_buttons_keyboard(buttons, *, extra_rows=None) -> InlineKeyboardMarkup:
    """Render the designed buttons (+ optional extra rows) as a real keyboard."""
    rows = []
    for entry in buttons or []:
        built = button(entry.get("label") or "Open",
                       url=entry.get("url") or None,
                       callback_data=None if entry.get("url") else "noop",
                       style=entry.get("style") or "primary")
        rows.append([built])
    rows.extend(extra_rows or [])
    return keyboard(rows)


def broadcast_with_buttons_text(prepared: int) -> str:
    return (f"📢 **Broadcasting to {int(prepared)} users**\n\n"
            "Messages are personalised and HTML-escaped on the C++ engine's "
            "thread pool before they go out.")


# --------------------------------------------------------------------------- #
#  Giveaways
# --------------------------------------------------------------------------- #

def giveaway_prize_label(tier: str, days) -> str:
    from config import GRANT_TIERS
    spec = GRANT_TIERS.get(tier or "") or {}
    number = spec.get("number", "🎁")
    label = spec.get("label", tier or "Premium")
    duration = "Lifetime" if days is None else f"{int(days)} days"
    return f"{number} {label} — {duration}"


def giveaway_when(value) -> str:
    """Format a giveaway deadline (naive UTC) for humans."""
    if value is None:
        return "—"
    try:
        return value.strftime("%d %b %Y • %H:%M UTC")
    except AttributeError:  # pragma: no cover - defensive
        return str(value)


def giveaway_panel_text(active, stats: dict | None = None) -> str:
    stats = stats or {}
    if not active:
        return ("🎁 **GIVEAWAY CONTROL**\n\n"
                "No giveaway is running right now.\n\n"
                "One giveaway at a time: start it here, and I post it in your "
                "channel, pin it, refresh the live participant count, re-post it "
                "once a day and draw the random winner when the timer runs out.\n\n"
                "👉 Tap **🎁 New giveaway** to begin.")
    lines = [
        "🎁 **GIVEAWAY CONTROL**",
        "",
        f"🎯 **Prize:** {giveaway_prize_label(active.get('prize_tier'), active.get('prize_days'))}",
        f"✨ **What they get:** {active.get('benefit') or '—'}",
        f"⏰ **Ends / winner announced:** {giveaway_when(active.get('ends_at'))}",
        f"👥 **Participants:** {int(stats.get('participants', 0))}",
        f"📰 **Channel:** {stats.get('channel') or 'not posted in a channel'}",
        f"📌 **Pinned message:** {stats.get('message') or '—'}",
        f"🔁 **Daily re-post:** every {int(stats.get('daily_hours', 24))} h",
        f"🕒 **Last re-post:** {stats.get('last_post') or 'just now'}",
        "",
        "The participant count on the pinned message updates live while the "
        "giveaway runs, and the winner is drawn randomly from everyone who "
        "joined — never by hand.",
    ]
    return "\n".join(lines)


def giveaway_panel_keyboard(active) -> InlineKeyboardMarkup:
    rows = []
    if active:
        rows.append([button("👥 Participants", callback_data="gw:list:0", style="primary"),
                     button("🛑 End now", callback_data="gw:end", style="danger")])
        rows.append([button("📤 Invite link", callback_data="gw:link", style="success")])
    else:
        rows.append([button("🎁 New giveaway", callback_data="gw:new", style="success")])
    rows.append([home_button()])
    return keyboard(rows)


def giveaway_step_tier_text() -> str:
    return ("🎁 **NEW GIVEAWAY • STEP 1/6**\n\n"
            "What is the prize? Pick the premium tier the winner receives.\n\n"
            "The tier decides exactly which features are unlocked and is granted "
            "with the full duration you choose in the next step.")


def giveaway_step_duration_text(tier_label: str) -> str:
    return (f"🎁 **NEW GIVEAWAY • STEP 2/6**\n\n"
            f"Prize tier: **{tier_label}**\n\n"
            "How long should the winner's premium last?")


def giveaway_step_benefit_text() -> str:
    from config import GIVEAWAY_BENEFIT_SUGGESTIONS, GIVEAWAY_MAX_BENEFIT_CHARS
    suggestions = "\n".join(f"• {line}" for line in GIVEAWAY_BENEFIT_SUGGESTIONS)
    return ("🎁 **NEW GIVEAWAY • STEP 3/6**\n\n"
            "Type the **benefit line** that is shown in the public giveaway "
            "message — the clear reason to join.\n\n"
            f"Max {int(GIVEAWAY_MAX_BENEFIT_CHARS)} characters. Suggestions:\n"
            f"{suggestions}\n\n"
            "Tap a suggestion below to use it as it is.")


def giveaway_step_benefit_keyboard() -> InlineKeyboardMarkup:
    from config import GIVEAWAY_BENEFIT_SUGGESTIONS
    rows = []
    for index, _ in enumerate(GIVEAWAY_BENEFIT_SUGGESTIONS):
        rows.append([button(f"💡 Suggestion {index + 1}",
                            callback_data=f"gw:benefit:{index}", style="primary")])
    rows.append([button("❌ Cancel everything", callback_data="gw:cancel",
                        style="danger")])
    return keyboard(rows)


def giveaway_step_custom_text() -> str:
    return ("🎁 **NEW GIVEAWAY • STEP 4/6**\n\n"
            "Send the announcement text you want everyone to see. Put `[]` "
            "where the current participant count should appear; the brackets "
            "will be replaced by the number. Leave it blank with **Skip custom "
            "message** to use the standard announcement.")


def giveaway_step_custom_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("⏭ Skip custom message", callback_data="gw:custom:skip", style="primary")],
        [button("❌ Cancel everything", callback_data="gw:cancel", style="danger")],
    ])


def giveaway_step_end_text() -> str:
    from config import GIVEAWAY_MAX_DAYS
    return ("🎁 **NEW GIVEAWAY • STEP 5/6**\n\n"
            "When does it end? That is also the moment the random winner is "
            "announced.\n\n"
            "Type a duration (`6h`, `3d`, `2w`) or an exact UTC date and time "
            f"(`2026-11-01 20:00`). Maximum {int(GIVEAWAY_MAX_DAYS)} days.\n\n"
            "The countdown is shown in the giveaway message and re-posted daily.")


def giveaway_step_end_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("⚡ 1 day", callback_data="gw:end:1d", style="primary"),
         button("📅 3 days", callback_data="gw:end:3d", style="primary")],
        [button("🗓 1 week", callback_data="gw:end:7d", style="primary"),
         button("📆 2 weeks", callback_data="gw:end:14d", style="primary")],
        [button("❌ Cancel everything", callback_data="gw:cancel", style="danger")],
    ])


def giveaway_step_channel_text(entries) -> str:
    listed = "\n".join(
        f"{index}️⃣ {entry.get('title') or entry.get('chat_id')}"
        for index, entry in enumerate(entries or [], start=1))
    body = listed or "• no channel connected yet"
    return ("🎁 **NEW GIVEAWAY • STEP 6/6**\n\n"
            "Where should I publish it? Pick a connected channel — I post the "
            "message there, pin it and keep the participant count updated on "
            "that pinned copy.\n\n"
            f"{body}\n\n"
            "No channel? Tap **Post in the bot only** and participants join "
            "through the link you share yourself.")


def giveaway_step_channel_keyboard(entries) -> InlineKeyboardMarkup:
    rows = []
    for index, entry in enumerate(entries or [], start=1):
        rows.append([button(f"{index}️⃣ {clamp_label(entry.get('title') or 'Channel')}",
                            callback_data=f"gw:channel:{index}", style="primary")])
    rows.append([button("💬 Post in the bot only", callback_data="gw:channel:none",
                        style="success")])
    rows.append([button("❌ Cancel everything", callback_data="gw:cancel",
                        style="danger")])
    return keyboard(rows)


def giveaway_share_button(link: str):
    return share_url_button("📤 Share giveaway", link,
                            "Join the giveaway — one tap to take part!", "success")


def giveaway_created_text(gw, participants: int = 0) -> str:
    channel = "your channel" if gw.get("channel_id") else "the bot only"
    return (
        "🎉 **GIVEAWAY IS LIVE**\n\n"
        f"🎯 **Prize:** {giveaway_prize_label(gw.get('prize_tier'), gw.get('prize_days'))}\n"
        f"✨ **Benefit:** {gw.get('benefit')}\n"
        f"⏰ **Ends:** {giveaway_when(gw.get('ends_at'))}\n"
        f"📰 **Published in:** {channel}\n\n"
        "The message is pinned where it was posted, the participant count on it "
        "updates live, and it is re-posted once a day until the timer runs out. "
        "At the end I draw a random winner from every participant and grant the "
        "prize automatically.\n\n"
        "Share the button below so people can join with one tap."
    )


def giveaway_created_keyboard(link: str | None) -> InlineKeyboardMarkup:
    rows = [[giveaway_share_button(link)]] if link else []
    rows.append([button("👥 Participants", callback_data="gw:list:0", style="primary"),
                 button("🛑 End now", callback_data="gw:end", style="danger")])
    return keyboard(rows)


def giveaway_public_text(gw, participants: int, *, ends_label: str | None = None) -> str:
    template = gw.get("custom_message")
    if template:
        return re.sub(r"\[\s*\]", str(int(participants)), str(template))
    prize = giveaway_prize_label(gw.get("prize_tier"), gw.get("prize_days"))
    lines = [
        "🎁 **GIVEAWAY**",
        "",
        f"🏆 **Prize:** {prize}",
        f"✨ **What you get:** {gw.get('benefit') or 'Premium access'}",
        "",
        f"👥 **Participants:** {int(participants)}",
        f"⏳ **Ends:** {ends_label or giveaway_when(gw.get('ends_at'))}",
        "",
        "How it works:",
        "1️⃣ Tap **🎉 Participate** below — one tap, nothing to fill in.",
        "2️⃣ You are in the draw immediately (the count above goes up live).",
        "3️⃣ At the end time a **random** participant is picked and the winner "
        "is announced right here and granted the prize automatically.",
        "",
        "Everyone can join once. Good luck!",
    ]
    return "\n".join(lines)


def giveaway_public_keyboard(link: str | None) -> InlineKeyboardMarkup:
    rows = []
    if link:
        rows.append([button("🎉 Participate", url=link, style="success")])
        rows.append([button("📋 Copy link", copy_text=link, style="primary")])
    return keyboard(rows) if rows else keyboard([])


#: Round 14 — the giveaway fan-out.  Every user receives this in their DM the
#: moment the giveaway goes live, and the owner receives a delivery report
#: once the whole fan-out has finished.
def giveaway_broadcast_text(gw) -> str:
    """The DM every user gets the instant a giveaway starts."""
    return (
        "🎁 **A giveaway just started!**\n\n"
        f"🏆 **Prize:** {giveaway_prize_label(gw.get('prize_tier'), gw.get('prize_days'))}\n"
        f"✨ {gw.get('benefit') or ''}\n"
        f"⏳ **Draw:** {giveaway_when(gw.get('ends_at'))}\n\n"
        "Tap **Participate** below to take part — one tap, one entry, and the "
        "winner is drawn randomly when the timer runs out.\n\n"
        "Good luck! 🍀"
    )


def giveaway_broadcast_keyboard(link: str | None) -> InlineKeyboardMarkup:
    """Participate + copy, same as the public message (label budget respected)."""
    return giveaway_public_keyboard(link)


def giveaway_broadcast_started_text(total: int) -> str:
    return (
        "📣 **Announcing the giveaway**\n\n"
        "The message is pinned in the channel and I am now delivering it to "
        f"**{int(total)}** users in their private chats. I will also try to pin "
        "each DM where Telegram allows it. This runs in the background — I will "
        "send you a delivery report as soon as the last one is done.\n\n"
        "Telegram rate limits are respected, so a large list takes a while."
    )


def giveaway_broadcast_report_text(report: dict) -> str:
    """The owner's delivery report for one fan-out."""
    lines = [
        "📣 **Giveaway delivery report**\n",
        f"👥 Users on the list: **{int(report.get('total', 0))}**",
        f"✅ Delivered: **{int(report.get('sent', 0))}**",
    ]
    failed = int(report.get("failed", 0))
    blocked = int(report.get("blocked", 0))
    paused = int(report.get("paused", 0))
    if failed:
        lines.append(f"⚠️ Could not deliver: **{failed}**")
    if blocked:
        lines.append(f"🚫 Never started the bot: **{blocked}**")
    if paused:
        lines.append(f"⏳ Skipped after rate limits: **{paused}**")
    wait = float(report.get("wait_seconds", 0.0) or 0.0)
    if wait:
        lines.append(f"⏱ Time spent waiting on Telegram: **{wait:.0f}s**")
    lines.append("")
    lines.append("The giveaway message itself stays pinned in the channel.")
    lines.append(f"📌 Private-chat pin attempts: {int(report.get('pin_attempted', 0))}; "
                 f"Telegram accepted {int(report.get('pin_succeeded', 0))}.")
    lines.append("Telegram may not allow bots to pin messages in private chats.")
    return "\n".join(lines)


def giveaway_joined_text(name: str, gw, count: int) -> str:
    return (
        "🎉 **You are in the draw!**\n\n"
        f"👤 {name}\n"
        f"🏆 **Prize:** {giveaway_prize_label(gw.get('prize_tier'), gw.get('prize_days'))}\n"
        f"✨ {gw.get('benefit') or ''}\n"
        f"👥 You are participant **#{int(count)}**\n"
        f"⏳ Draw: {giveaway_when(gw.get('ends_at'))}\n\n"
        "I will message you here if you win — and the winner is picked "
        "randomly, so every single participant has the same chance."
    )


def giveaway_already_joined_text(count: int) -> str:
    return ("☑️ **You already joined this giveaway**\n\n"
            f"👥 Participants so far: **{int(count)}**\n\n"
            "Each account joins once, so your place in the draw is safe.")


def giveaway_none_text() -> str:
    return ("🎁 **No giveaway is running**\n\n"
            "There is nothing to join right now. Watch this chat — the next "
            "giveaway is announced here.")


def giveaway_quick_status_text(gw, count: int) -> str:
    """One-screen summary for ``/giveawaystatus`` — prize, timer, participants."""
    from datetime import datetime_utcnow
    now = datetime_utcnow()
    ends_at = gw.get("ends_at")
    ends_in = None
    if ends_at:
        try:
            ends_in = int((ends_at - now).total_seconds())
        except (TypeError, ValueError):
            ends_in = None
    prize = giveaway_prize_label(gw.get("prize_tier"), gw.get("prize_days"))
    lines = [
        "🎁 **GIVEAWAY STATUS**",
        "",
        f"🎯 **Prize:** {prize}",
        f"👥 **Participants:** {int(count)}",
        f"🔗 **Token:** `{gw.get('token') or '—'}`",
        "",
    ]
    if ends_in is not None and ends_in > 0:
        lines.append(f"⏱ **Ends in:** {giveaway_when(ends_at)}")
    else:
        lines.append("✅ **Ends:** — (no deadline set)")
    if gw.get("channel_id"):
        lines.append(f"📡 **Channel:** `{gw.get('channel_id')}`")
    lines += [
        "",
        f"📅 **Started:** {giveaway_when(gw.get('created_at'))}",
        f"👑 **Created by:** `{gw.get('created_by') or '—'}`",
        "",
        "Use ``/giveaway`` for the full panel, ``/participants`` to browse "
        "the list, or ``/endgiveaway`` to draw the winner now.",
    ]
    return "\n".join(lines)


def giveaway_closed_text() -> str:
    return ("🔒 **This giveaway has ended**\n\n"
            "The winner has been drawn and announced. Stay tuned for the next "
            "one!")


def giveaway_participants_text(rows, page: int, pages: int, total: int) -> str:
    lines = [
        "👥 **GIVEAWAY PARTICIPANTS**",
        "",
        f"🔢 **Total joined:** {int(total)}",
        f"📄 Page {int(page) + 1}/{int(pages)}",
        "",
    ]
    if not rows:
        lines.append("Nobody has joined yet — share the invite link the giveaway "
                     "panel gives you.")
    for index, row in enumerate(rows, start=1 + int(page) * 10):
        handle = f"@{row['username']}" if row.get("username") else "no username"
        lines.append(f"{index}. {row.get('name') or 'User'} — {handle} · "
                     f"`{row.get('user_id')}`")
    lines += ["", "🎲 The winner is drawn at random from this exact list."]
    return "\n".join(lines)


def giveaway_participants_keyboard(page: int, pages: int) -> InlineKeyboardMarkup:
    rows = []
    if pages > 1:
        rows.append([
            button("⬅️ Previous", callback_data=f"gw:list:{(page - 1) % pages}",
                   style="primary"),
            button("Next ➡️", callback_data=f"gw:list:{(page + 1) % pages}",
                   style="primary"),
        ])
    rows.append([button("🛑 End now", callback_data="gw:end", style="danger")])
    rows.append([button("🎁 Panel", callback_data="cmd_giveaway", style="primary")])
    return keyboard(rows)


def giveaway_finished_text(winner_label: str | None, prize: str, total: int) -> str:
    if winner_label is None:
        return ("🎁 **GIVEAWAY CLOSED**\n\n"
                "The timer ran out but nobody joined, so there is no winner this "
                "time. The prize stays with the owner.")
    return ("🏆 **GIVEAWAY WINNER ANNOUNCED**\n\n"
            f"🎉 **{winner_label}**\n"
            f"🏆 **Prize:** {prize}\n"
            f"👥 Drawn from **{int(total)}** participants\n\n"
            "The winner was picked randomly and the prize is being granted "
            "automatically. Congratulations!")


def giveaway_winner_dm_text(prize: str) -> str:
    return ("🎉 **YOU WON THE GIVEAWAY!**\n\n"
            f"🏆 **Prize:** {prize}\n\n"
            "Your premium has been granted automatically — open /premium or "
            "/models to see your access. Congratulations, and thank you for "
            "taking part!")


def giveaway_owner_ended_text(winner_label: str | None, total: int, granted: bool) -> str:
    if winner_label is None:
        return ("🛑 **Giveaway closed by hand**\n\n"
                "Nobody had joined, so no winner was drawn.")
    state = "granted" if granted else "recorded — grant it with /addpremium"
    return ("🛑 **Giveaway closed by hand**\n\n"
            f"🏆 Winner: **{winner_label}**\n"
            f"👥 Participants: {int(total)}\n"
            f"💎 Prize: {state}.")


def giveaway_ending_soon_text(minutes: int) -> str:
    return ("⏳ **Giveaway ending soon**\n\n"
            f"Only {int(minutes)} minutes left to join the giveaway. "
            "Tap the participate button to be in the random draw.")


def giveaway_updated_text(participants: int) -> str:
    return f"👥 **Participants:** {int(participants)}"


# --------------------------------------------------------------------------- #
#  Native C++ engine — /native diagnostics
# --------------------------------------------------------------------------- #

def native_engine_text(info: dict, bench_ms: float | None = None) -> str:
    """Status of the compiled engine behind the bot's hot paths."""
    info = info or {}
    if info.get("backend") != "native":
        return (
            "🐍 **NATIVE ENGINE**\n\n"
            "The compiled C++ engine is **not loaded**, so the bot is running its "
            "pure-Python fallback. Everything still works — links are parsed, "
            "commands classified and FloodWait pauses honoured by the reference "
            "implementation.\n\n"
            f"📄 **Why:** {info.get('log') or 'not built'}\n\n"
            "👉 Install a C++17 compiler (`g++`) and restart, or set a prebuilt "
            "library path with `NATIVE_ENGINE_LIB`. Forcing the fallback is done "
            "with `NATIVE_ENGINE=off`."
        )
    bench = f"{bench_ms:.2f} ms / 200k ops" if bench_ms is not None else "—"
    return (
        "⚡ **NATIVE C++ ENGINE**\n\n"
        f"🧬 **Version:** {info.get('version')}\n"
        f"🔧 **Built with:** {info.get('compiler')}\n"
        f"🧵 **Worker threads:** {int(info.get('threads', 1))}\n"
        f"✅ **Self-test:** {'passed' if int(info.get('selftest', 0)) == 0 else 'FAILED'}\n"
        f"📚 **Commands registered:** {int(info.get('commands', 0))}\n"
        f"⚙️ **Jobs run on the pool:** {int(info.get('tasks', 0))}\n"
        f"🐢 **Governor keys:** {int(info.get('governor_keys', 0))} "
        f"({int(info.get('governor_wait_ms', 0))} ms of pauses enforced)\n"
        f"🚀 **Benchmark:** {bench}\n\n"
        "**What it runs**\n"
        "🔗 every message link (`re_parse_link`) — same grammar, in C++\n"
        "🧠 message classification (`re_scan`): command / links / range\n"
        "⚙️ the Python Standard speed cap (`re_bucket_charge`)\n"
        "🐢 the FloodWait governor (`re_gov_*`) for channels and the mirror\n"
        "🧵 parallel HTML escaping on a real `std::thread` pool\n\n"
        f"📄 **Library:** `{info.get('library') or 'in process'}`"
    )


def native_engine_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("🔄 Re-run self-test", callback_data="native:selftest", style="success"),
         button("🧪 Benchmark", callback_data="native:bench", style="primary")],
        [home_button()],
    ])


# --------------------------------------------------------------------------- #
#  Deep links, dump setup and the button wizard — the remaining copy
# --------------------------------------------------------------------------- #

def setchat_deep_link_private_text() -> str:
    """Round 14 — a setchat link that came back to the bot in a private chat.

    The link no longer registers anything and no longer belongs in a channel,
    so the screen simply opens the chooser and names the typed fallback.
    """
    return (
        "📡 **PICK YOUR CHANNEL**\n\n"
        "That setup link is no longer needed — channels are handed over with "
        "Telegram's own chooser now, so nothing is ever posted inside them.\n\n"
        "1️⃣ Tap **📡 Pick my channel** on the keyboard below.\n"
        "2️⃣ Pick the channel in Telegram's list.\n"
        "3️⃣ I verify it and connect it.\n\n"
        "You can also send me one **message link** from the channel, or its "
        "@username, right here. Use /cancel to stop."
    )


def setdump_deep_link_private_text() -> str:
    return (
        "🗄 **PICK THE DUMP CHANNEL**\n\n"
        "Tap **🗄 Pick my dump** below to select it with Telegram's channel "
        "picker, or send its link, `@username` or numeric id.\n\n"
        "Use /cancel to stop."
    )


def setdump_owner_only_text() -> str:
    return ("👑 **Owner only**\n\n"
            "The dump channel is the owner's temporary workspace, so only the "
            "owner may connect or disconnect it.")


def setdump_join_request_text() -> str:
    return ("⏳ **Join request sent**\n\n"
            "That chat only accepts members by approval, so I asked to join. "
            "Once the owner approves me, send /setdump again — nothing is "
            "connected yet.")


def dump_admin_failed_text(reason: str = "not_admin") -> str:
    if reason == "requester_not_admin":
        return ("⚠️ **The selected channel is not yours to connect**\n\n"
                "Your Telegram account is not an administrator there. Ask the "
                "channel owner to make you an admin, then choose it again. "
                "Nothing has been connected.")
    base = ("⚠️ **I cannot work with that channel yet**\n\n"
            "{detail}\n\n"
            "👉 Make me an administrator with **Post Messages** and **Delete "
            "Messages** (the workspace deletes its own copies) and send /setdump "
            "again. Staging is unavailable until these permissions are verified.")
    details = {
        "not_admin": "I am not an administrator in that chat.",
        "no_post_rights": "I am an admin there but **Post Messages** is disabled.",
        "no_delete_rights": "I am an admin there but **Delete Messages** is disabled. "
                           "The temporary workspace must be cleaned after each delivery.",
        "requester_not_admin": "Your Telegram account is not an administrator of that channel.",
        "error": "Telegram did not answer the permission check — this is usually "
                 "temporary, try again in a moment.",
    }
    return base.format(detail=details.get(reason, "I could not verify my rights in that chat."))


def message_sent_text() -> str:
    return "📤 **Message sent**\n\nEverything you designed went out exactly as previewed."


def message_cancelled_text() -> str:
    return ("❌ **Cancelled**\n\nNothing was sent — no message, no broadcast, "
            "no channel post, no pin.")


def buttons_preview_text(buttons) -> str:
    if not buttons:
        return ""
    return "🎛 **Buttons attached**\n\n" + buttons_summary(buttons)


def button_label_too_long_text(limit: int) -> str:
    return (f"✍️ **Too long**\n\nA button label may hold at most **{int(limit)}** "
            "characters so it never gets cut off on a phone. Send a shorter one.")


def button_link_invalid_text() -> str:
    return ("❌ **That is not an address I can use**\n\n"
            "Paste a normal web address, an invite link or a channel username — "
            "or tap **No link (just text)**. Nothing has been sent yet, so this "
            "step is still open.")


def giveaway_share_text(link: str) -> str:
    return ("📤 **SHARE THE GIVEAWAY**\n\n"
            "The button below opens Telegram's share sheet — pick any chat or "
            "channel and the invite goes out with one tap:\n\n"
            "• **📤 Share giveaway** — send it anywhere.\n"
            "• **📋 Copy link** — paste it wherever you like (a channel post, "
            "your bio, another bot).\n\n"
            "Every tap on that link joins the giveaway and the participant "
            "count on the pinned message goes up live.")


def giveaway_days_prompt_text() -> str:
    return ("🔢 **How many days?**\n\n"
            "Send the number of days the winner's premium should last "
            "(for example `45`). The same duration is shown in the giveaway "
            "message.")


def giveaway_end_invalid_text() -> str:
    from config import GIVEAWAY_MAX_DAYS
    return ("❌ **I could not read that date**\n\n"
            "Send a duration like `6h`, `3d` or `2w`, or a full UTC date and "
            f"time like `2026-11-01 20:00` (max {int(GIVEAWAY_MAX_DAYS)} days "
            "from now). Nothing was scheduled yet.")


# --------------------------------------------------------------------------- #
#  Vmore app — access tokens, the APK and the in-app experience
#
#  The app is the bandwidth saver: a private link's content is downloaded and
#  uploaded with the **user's own Telegram data** straight from the phone, so
#  nothing is ever re-uploaded to Telegram by the bot.  The app never asks for a
#  session string — one access token (``HPSEG9``) is the whole login.
# --------------------------------------------------------------------------- #

#: Product name.  Kept here so every screen, button and the APK agree.
APP_NAME = "Vmore"
#: Shown on the app screen; the workflow stamps the same version into the APK.
APP_VERSION = "1.0.0"
#: Where the app talks to this deployment.
APP_API_PATH = "/api/v2"
#: Mirrors ``database.APP_TOKEN_LIFETIME_DAYS`` — kept here (not imported) so this
#: module stays free of database imports; the test suite pins the two together.
APP_TOKEN_LIFETIME_DAYS = 30
#: The APK is never handed out as a public link: the **Unlimited Download (App)**
#: button fires ``app:apk`` and the bot sends the file the owner uploaded with
#: ``/apk`` straight into the chat. No release URL — nothing about the owner's
#: hosting or accounts — ever leaks to a user.


def green_reply_button(text: str, **kwargs):
    """A **green** reply keyboard button (``ButtonStyle.SUCCESS``).

    Every reply keyboard in this bot is green: the channel picker and the dump
    picker are the only ones, and Telegram renders the colour on the wire
    (``keyboardButtonStyle.bg_success``).  Inline keyboards are untouched.
    """
    if KeyboardButton is None:  # pragma: no cover - legacy pyrogram
        return None
    if styles_enabled():
        kwargs.setdefault("style", _ENUM_BY_NAME.get("success"))
    return KeyboardButton(text, **kwargs)


def app_base_url(stored: str | None = None) -> str | None:
    """The deployment URL, normalised (``https://host`` — never a trailing slash)."""
    url = (stored or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def app_apk_url(stored_base_url: str | None = None) -> str | None:
    base = app_base_url(stored_base_url)
    return f"{base}{APP_API_PATH}/app/apk" if base else None


def app_footer_button() -> InlineKeyboardButton:
    """The full-width **big** app button that owns the last row of ``/start``."""
    return button("📱 Vmore App", callback_data="cmd_app", style="success")


def app_download_button(stored_base_url: str | None = None, *, has_apk: bool = True,
                        label: str = "♾️ Unlimited Download (App)"):
    """Download-the-app button: the bot always sends the APK **in this chat**.

    One tap fires ``app:apk`` (``cb_app_apk``) and the file the owner connected
    with ``/apk`` lands right here. No URL button is ever offered, so nothing
    about the owner (a repository, a hosting account, anything) leaks to the
    people asking for the app.
    """
    return button(label, callback_data="app:apk", style="success")


def app_details_text(*, base_url=None, apk=None, premium: bool = False,
                     token: str | None = None, session: bool = False,
                     app_users: int | None = None, owner: str = "XyrDeveloper") -> str:
    """The **full** app page behind the big button of ``/start``."""
    apk = apk or {}
    size = apk.get("size")
    size_line = f"{size / (1024 * 1024):.1f} MB" if size else "—"
    version = apk.get("version") or APP_VERSION
    name = apk.get("file_name") or f"{APP_NAME}.apk"
    base = app_base_url(base_url)
    token_line = (f"🔑 Your access token: `{token}`" if token
                  else "🔑 Generate your access token with /gentoken")
    session_line = ("🔓 Telegram session: **connected** — private downloads are ready."
                    if session else
                    "🔒 Telegram session: **not connected** — run /login once so the "
                    "app can download private content with your own data.")
    plan_line = "💎 Plan: **Premium**" if premium else "💎 Plan: **Free**"
    lines = [
        f"📱 **{APP_NAME} — UNLIMITED DOWNLOAD APP**",
        "",
        f"**Version:** `{version}`",
        f"**Build:** `{name}` • `{size_line}`",
    ]
    lines += [
        f"**Server:** `{base or 'not set yet — the owner runs /apk with the URL'}`",
        f"**Owner:** @{owner}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "**Why the app saves your bandwidth**",
        "• Private links download **with your own Telegram data** — the server "
        "never re-uploads a file to Telegram.",
        "• Unlimited private downloads, no premium required.",
        "• Pause / stop any download, resume it later.",
        "• Download notification with live progress in the notification bar.",
        "",
        "**What you can do inside**",
        "• Paste a public link → it lands in your Telegram DM directly.",
        "• Paste a private link → download it in the app, then edit: caption, "
        "thumbnail, and trim the video from the front or the back.",
        "• Watch videos and open documents / PDFs right in the app.",
        "• Save anything to your device, and see downloads + history together.",
        "• Revoke your access token whenever you want.",
        "",
        "**Your account**",
        token_line,
        session_line,
        plan_line,
    ]
    if app_users is not None:
        lines.append(f"👥 App users: `{int(app_users)}`")
    lines += [
        "",
        "Tap **⬇️ Download App** below, then open the file and install it.",
        f"🔐 Login inside {APP_NAME} = only your access token, never a session.",
    ]
    return "\n".join(lines)


def app_details_keyboard(*, base_url=None, has_apk: bool = True,
                         token: str | None = None) -> InlineKeyboardMarkup:
    """The buttons of the app page — download is always first."""
    rows = [
        [app_download_button(base_url, has_apk=has_apk,
                             label="⬇️ Download App (Unlimited)")],
        [
            button("📩 Send APK in chat", callback_data="app:apk", style="primary"),
            button("❓ How to use?", callback_data="app:howto", style="primary"),
        ],
        [
            button("🔑 My Access Token", callback_data="cmd_gentoken", style="success"),
            button("🚫 Revoke Token", callback_data="app:revoke", style="danger"),
        ],
        [owner_contact_button()],
        [home_button()],
    ]
    return keyboard(rows)


def app_missing_text() -> str:
    return (f"⚠️ **The {APP_NAME} APK is not uploaded yet**\n\n"
            "The owner adds it with `/apk` — send the APK file with the deployment "
            "URL as the caption. Nothing else is needed.")


def app_howto_text(*, base_url=None) -> str:
    """The in-bot version of the app's own **How to use?** screen."""
    base = app_base_url(base_url) or "https://your-app-url.onrender.com"
    return (
        f"❓ **HOW TO USE {APP_NAME}**\n\n"
        "**1. Install the app**\n"
        "Tap the download button on the app page and install the APK (allow "
        "\"Install unknown apps\" once).\n\n"
        "**2. Get your access token**\n"
        "Send /gentoken here. You get a short code like `HPSEG9` — that is your "
        "whole login. No phone number, no session, no OTP.\n\n"
        "**3. Open the app and log in**\n"
        "Enter the server address and the token — or paste the whole line below, "
        "the app keeps the part it needs:\n"
        f"`{base}{APP_API_PATH}/token/HPSEG9`\n"
        "(it is the same link /gentoken shows for your own token).\n\n"
        "**4. Paste a link**\n"
        "• **Public link** → the app asks the bot to send it to your Telegram DM. "
        "Nothing downloads on your phone.\n"
        "• **Private link** → the app downloads it with **your own Telegram "
        "data**, so it is unlimited and free.\n\n"
        "**5. Edit before uploading**\n"
        "Change the caption, set your thumbnail, trim the video from the front or "
        "the back — then upload. The finished file is uploaded from your account "
        "into your chat with the bot.\n\n"
        "**6. Keep or watch**\n"
        "Save to device, play the video, open documents — and see every download "
        "and its history in one list.\n\n"
        "**Buttons in the notification**\n"
        "Pause / Stop while downloading, and a notification the moment it "
        "finishes.\n\n"
        "**Not working?**\n"
        "• Private download needs one `/login` in this bot first — the app uses "
        "that session for you.\n"
        "• Token lost or leaked? Send /gentoken and regenerate it, or /revoketoken "
        "to switch it off."
    )


def app_token_text(user_row=None, row=None, *, base_url=None) -> str:
    """The /gentoken screen — the token, its 30-day life and how to reset it."""
    row = row or {}
    token = row.get("token")
    active = bool(token) and not row.get("revoked")
    base = app_base_url(base_url)
    lines = [
        "🔑 **YOUR APP ACCESS TOKEN**",
        "",
    ]
    if active:
        lines += [
            f"`{token}`",
            "",
            "Enter this token in the app once — it is your only login. No phone "
            "number, no OTP, no session string.",
            "",
        ]
        lines += _token_life_lines(row)
        lines.append("")
    else:
        expired = bool(token) and app_token_expired(row)
        lines += [
            ("Your token **expired** — the 30 days are over."
             if expired else "You do not have a live token right now."),
            "",
            "Tap **🆕 Generate Token** below and the bot hands you a fresh short "
            "code like `HPSEG9`.",
            "",
        ]
    if base:
        lines += [
            "**Server address in the app**",
            f"`{base}{APP_API_PATH}/token/{token or 'YOUR-TOKEN'}`",
            "",
        ]
    lines += [
        "**How it works**",
        "• One account = one active token. Regenerating kills the old one.",
        f"• A token lives `{APP_TOKEN_LIFETIME_DAYS}` days, then the app asks for "
        "a new one — /gentoken hands it over in one tap.",
        "• The token only ever touches your own account: it is the key to your "
        "downloads, history and uploads.",
        "• Revoke it any time with 🚫 **Revoke Token** or /revoketoken.",
        "",
        f"Generate it here, use it inside {APP_NAME}.",
    ]
    return "\n".join(lines)


def app_token_keyboard(*, active: bool = True) -> InlineKeyboardMarkup:
    """Token screen buttons — generate / regenerate, revoke, open the app page."""
    if active:
        first = button("🔄 Regenerate Token", callback_data="app:newtoken",
                       style="success")
    else:
        first = button("🆕 Generate Token", callback_data="app:newtoken",
                       style="success")
    return keyboard([
        [first],
        [button("🚫 Revoke Token", callback_data="app:revoke", style="danger"),
         button("📱 Vmore App", callback_data="cmd_app", style="primary")],
        [home_button()],
    ])


def _token_life_lines(row) -> list[str]:
    """``🕒 valid for 12 more days (until 2026-11-07)`` for the token screen."""
    from database import app_token_days_left
    expiry = row.get("expires_at")
    days = app_token_days_left(row)
    if expiry is None:
        return []
    if days <= 0:
        return [f"🕒 **Expired** on `{expiry:%Y-%m-%d}` — regenerate to keep using "
                f"{APP_NAME}."]
    return [f"🕒 **Valid for {days} more day{'s' if days != 1 else ''}** "
            f"(until `{expiry:%Y-%m-%d}`)."]


def app_token_confirm_text() -> str:
    return ("🔄 **Regenerate your access token?**\n\n"
            "The token you have now stops working immediately — every app that is "
            "signed in with it will be signed out. A new one is created right away.")


def app_token_revoke_confirm_text() -> str:
    return ("🚫 **Revoke your access token?**\n\n"
            "The app can no longer reach your account until you generate a new "
            "token with /gentoken. Your download history stays.")


def app_token_created_text(token: str, *, base_url=None) -> str:
    base = app_base_url(base_url)
    lines = [
        "✅ **TOKEN READY**",
        "",
        f"`{token}`",
        "",
        f"Open {APP_NAME} and paste it — that is the whole login.",
    ]
    if base:
        lines += ["", f"Server: `{base}{APP_API_PATH}/token/{token}`"]
    return "\n".join(lines)


def app_token_revoked_text() -> str:
    return ("🚫 **Token revoked**\n\n"
            "The app is signed out. Send /gentoken whenever you want a new one.")


def app_token_invalid_text() -> str:
    return ("❌ **This token is not active**\n\n"
            "It was revoked or never existed. Send /gentoken here to get a fresh "
            "one from the bot.")


def app_token_expired_text() -> str:
    return ("⌛ **This access token has expired**\n\n"
            f"A token is valid for `{APP_TOKEN_LIFETIME_DAYS}` days. Send /gentoken "
            f"in the bot and paste the new code into {APP_NAME} — it takes a second.")


def app_login_dm_text(*, device=None, version=None) -> str:
    """The DM the bot sends the moment the app logs in with a token."""
    lines = [
        "✅ **LOGIN IN APP SUCCESSFUL**",
        "",
        f"📱 {APP_NAME}" + (f" • `{version}`" if version else ""),
    ]
    if device:
        lines.append(f"📲 Device: `{device}`")
    lines += [
        "",
        "Your access token is active. Paste any Telegram link inside the app:",
        "• **Public** → straight to this DM.",
        "• **Private** → downloaded with your own data, unlimited.",
        "",
        "Send /revoketoken any time to sign the app out.",
    ]
    return "\n".join(lines)


def app_revoked_dm_text() -> str:
    return ("🚫 **App access token revoked**\n\n"
            f"{APP_NAME} is signed out. Send /gentoken to create a new token.")


def app_users_text(users, *, tokens: int = 0, total: int | None = None) -> str:
    """Owner/admin view: the people who really **use** the app."""
    users = list(users or [])
    total = len(users) if total is None else int(total)
    lines = [
        "📱 **VMORE APP USERS**",
        "",
        f"👥 App users: `{total}` • 🔑 Live tokens: `{int(tokens)}`",
        "",
        "Only accounts that actually logged in from the app are listed here — "
        "generating a token alone never counts.",
        "",
    ]
    if not users:
        lines.append("No app logins yet.")
        return "\n".join(lines)
    for index, row in enumerate(users, 1):
        name = row.get("name") or "User"
        username = row.get("username")
        handle = f" @{username}" if username else ""
        device = row.get("device") or "—"
        version = row.get("app_version") or "—"
        last = row.get("last_seen")
        last_text = last.strftime("%Y-%m-%d %H:%M") if hasattr(last, "strftime") else "—"
        lines += [
            f"{index}. **{name}**{handle} (`{row.get('user_id')}`)",
            f"   ⬇️ {int(row.get('downloads', 0))} • ⬆️ {int(row.get('uploads', 0))} "
            f"• 🚀 {int(row.get('sends', 0))} • 🔐 {int(row.get('logins', 0))}",
            f"   📲 {device} • `v{version}` • 🕛 {last_text}",
            "",
        ]
    return "\n".join(lines)


def app_users_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [button("🔄 Refresh", callback_data="appusers:refresh", style="primary"),
         button("🔑 Tokens", callback_data="appusers:tokens", style="primary")],
        [home_button()],
    ])


def app_users_tokens_text(rows, *, total: int = 0) -> str:
    """Owner view of token holders — deliberately separate from app users."""
    rows = list(rows or [])
    lines = [
        "🔑 **ACCESS TOKENS**",
        "",
        f"Generated: `{int(total or len(rows))}`",
        "",
        "Having a token is **not** the same as using the app — /appusers lists the "
        "people who signed in.",
        "",
    ]
    if not rows:
        lines.append("No tokens yet.")
        return "\n".join(lines)
    for index, row in enumerate(rows, 1):
        state = "🚫 revoked" if row.get("revoked") else "✅ active"
        used = row.get("last_used")
        used_text = used.strftime("%Y-%m-%d %H:%M") if hasattr(used, "strftime") else "never"
        lines += [
            f"{index}. `{row.get('token')}` — {state}",
            f"   👤 `{row.get('user_id')}` • 🔐 {int(row.get('calls', 0))} calls "
            f"• 🕛 {used_text}",
            "",
        ]
    return "\n".join(lines)


def apk_status_text(apk=None, *, base_url=None) -> str:
    """``/apk`` — what the bot currently serves, and how to change it."""
    apk = apk or {}
    base = app_base_url(base_url)
    lines = [
        "📦 **VMORE APK**",
        "",
    ]
    if apk.get("file_id"):
        size = apk.get("size")
        lines += [
            "✅ An APK is connected.",
            "",
            f"📄 File: `{apk.get('file_name') or 'Vmore.apk'}`",
            f"📦 Size: {f'{size / (1024 * 1024):.1f} MB' if size else '—'}",
            f"🏷 Version: `{apk.get('version') or APP_VERSION}`",
            f"🌐 Server: `{base or 'not set'}`",
            "",
        ]
    else:
        lines += [
            "⚠️ No APK is connected yet.",
            "",
        ]
    lines += [
        "**How to update it**",
        "1️⃣ Send the APK file to this chat with the server URL as the caption:",
        f"`{base or 'https://your-app.onrender.com'}`",
        "2️⃣ Or reply `/apk` to an APK you already sent.",
        "",
        "The same file is served at "
        f"`{(base or 'https://your-app.onrender.com')}{APP_API_PATH}/app/apk` and the "
        "⬇️ button on every app screen points there.",
    ]
    return "\n".join(lines)


def apk_saved_text(apk, *, base_url=None) -> str:
    size = (apk or {}).get("size")
    base = app_base_url(base_url)
    lines = [
        "✅ **APK CONNECTED**",
        "",
        f"📄 {apk.get('file_name') or 'Vmore.apk'}",
        f"📦 {f'{size / (1024 * 1024):.1f} MB' if size else '—'} "
        f"• 🏷 `{apk.get('version') or APP_VERSION}`",
        f"🌐 Server: `{base or 'not set'}`",
    ]
    if base:
        lines += ["", f"⬇️ Direct download: `{base}{APP_API_PATH}/app/apk`"]
    lines += ["", "Every app button in the bot now points at this file."]
    return "\n".join(lines)


def apk_not_owner_text() -> str:
    return "🚫 **Owner only**\n\nOnly the owner can replace the app file."


def apk_bad_file_text() -> str:
    return ("❌ **That is not an APK**\n\nSend the `.apk` file itself (as a "
            "document) — the caption may carry the server URL.")


def app_private_link_text() -> str:
    """The private-link screen: two options, app first."""
    return (
        "🔒 **PRIVATE / RESTRICTED LINK**\n\n"
        "Pick how you want it:\n\n"
        "♾️ **Unlimited Download (App)** — the Vmore app downloads it with your "
        "own Telegram data. Unlimited, free, no DM delivery needed.\n\n"
        "💎 **Premium** — the bot delivers it right here in this DM, up to 2 GB "
        "per file."
    )


def app_offline_text() -> str:
    return (f"⚠️ **{APP_NAME} is not reachable**\n\n"
            "The owner has not published a server URL yet. Use the second option, "
            "or try again after the owner runs `/apk` with the URL.")


def app_session_missing_text() -> str:
    """A private link needs one /login in the bot — the app reuses that session."""
    return (f"🔓 **One step first: `/login` in this bot**\n\n"
            f"{APP_NAME} downloads private content with **your own Telegram data**, "
            "so it needs the session you connect with `/login` here — once. The app "
            "itself never asks for a phone number, an OTP or a session string: your "
            "access token is the whole login.\n\n"
            "After that, every private link is unlimited in the app.")

