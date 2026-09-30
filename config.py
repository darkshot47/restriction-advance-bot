"""Product and access-tier configuration for the bot."""

import os

BOT_USERNAME = os.environ.get("BOT_USERNAME", "wantedkar99bot").lstrip("@")
FREE_DAILY_LIMIT = 3
FREE_PRIVATE_LINKS = False
WATERMARK = "Extracted by @wantedkar99bot"
REFER_POINTS = 10
REDEEM_POINTS = 100
REDEEM_PREMIUM_MONTHS = 1
# Kept for integrations that import the old constant; redemption uses calendar months.
REDEEM_PREMIUM_DAYS = 30
PAYMENT_CONTACT = "XyrDeveloper"
#: The single place the owner contact link is built from — every plan display,
#: pricing screen and payment-proof wizard uses this exact URL button.
OWNER_CONTACT_URL = f"https://t.me/{PAYMENT_CONTACT}"
#: Base price is the Standard (Python engine) plan; ``addon_price`` is the
#: optional C++ Turbo upgrade sold on top of it.  Total = price + addon_price.
PREMIUM_PLANS = {
    "month": {"title": "1 month", "price": 99, "addon_price": 50, "days": 30},
    "quarter": {"title": "3 months", "price": 249, "addon_price": 100, "days": 90},
    "year": {"title": "1 year", "price": 700, "addon_price": 149, "days": 365},
}
PREMIUM_BENEFITS = (
    "Unlimited public-channel extractions",
    "Up to 2 GB files",
    "Priority support",
)
#: Extra benefits unlocked by the C++ Turbo add-on.
TURBO_BENEFITS = (
    "Multi-threaded extraction workers",
    "Zero-copy stream piping",
    "Priority routing during traffic peaks",
)


def plan_addon_price(plan) -> int:
    """C++ Turbo add-on price of *plan* (``0`` when the plan has no add-on)."""
    try:
        return int((plan or {}).get("addon_price") or 0)
    except (TypeError, ValueError):
        return 0


def plan_base_price(plan) -> int:
    try:
        return int((plan or {}).get("price") or 0)
    except (TypeError, ValueError):
        return 0


def plan_total_price(plan) -> int:
    """Standard price + C++ Turbo add-on (₹149 / ₹349 / ₹849 for the shipped plans)."""
    return plan_base_price(plan) + plan_addon_price(plan)
REDEEM_LIMITATION = "This bot extracts restricted content from public channels only."
RUPEE = "₹"

# --------------------------------------------------------------------------- #
#  Access tiers
# --------------------------------------------------------------------------- #
#: Premium source for a full (public + private) owner grant.
PREMIUM_SOURCE_MANUAL = "manual"
#: Premium source for an owner grant that only unlocks public channels.
PREMIUM_SOURCE_PUBLIC = "public"
#: Premium source for a public grant that also unlocks the C++ Turbo switcher.
#: Deliberately distinct from ``manual``: the legacy ``premium_source in
#: {manual, purchase}`` shortcut means "private links allowed", so a
#: models-only grant must never carry that value.
PREMIUM_SOURCE_MODELS = "models"
#: Premium source for points redemption (public channels only).
PREMIUM_SOURCE_REDEEM = "redeem"
#: Tier granted when the owner approves a payment screenshot.
PURCHASE_PREMIUM_SOURCE = PREMIUM_SOURCE_MANUAL

# --------------------------------------------------------------------------- #
#  Limits, wording and channel-dump guards
# --------------------------------------------------------------------------- #
#: Free users' daily quota resets at midnight UTC — keep this in sync with
#: database.utcnow(), which is what the quota counters actually use.
DAILY_RESET_LABEL = "00:00 UTC"
#: Feedback may not contain links; only plain text and @mentions.
FEEDBACK_LINK_WARNING = (
    "⚠️ Links are not allowed in feedback. Please submit plain text with @mentions only."
)
#: A "Message not found" error in a channel is deleted after this many seconds.
CHANNEL_CLEANUP_SECONDS = 5
#: Minimum delay between two channel-dump extraction requests (anti-ban guard).
CHANNEL_EXTRACT_COOLDOWN = 3.0
#: Timeout (in seconds) for asking the owner whether to use the custom caption in a channel dump.
CHANNEL_CAPTION_TIMEOUT = int(os.environ.get("CHANNEL_CAPTION_TIMEOUT", "60"))

# --------------------------------------------------------------------------- #
#  Force subscription (multi-channel) limits and wording
# --------------------------------------------------------------------------- #
#: Longest custom join-button label the owner may type.  Button labels must
#: stay inside the 28 visible-character mobile budget, so the input limit is
#: kept a little below it to leave room for emojis.
FSUB_MAX_BUTTON_CHARS = 24
#: Join buttons shown per keyboard page (keeps every page ≤ 7 rows).
FSUB_ITEMS_PER_PAGE = 5
#: Entries shown per page of the owner management keyboard (two buttons each).
FSUB_LIST_PER_PAGE = 4
#: How many join requests are read when checking the approve list.
FSUB_JOINER_SCAN_LIMIT = 200
#: Default label of the "I joined" verification button.
FSUB_VERIFY_LABEL = "✅ I Joined"
#: Placeholder title used when Telegram reports no title for a chat.
CHANNEL_TITLE_FALLBACK = "Channel {chat_id}"

# --------------------------------------------------------------------------- #
#  Dual execution engines — Python Standard ⚙️ and C++ Turbo 🚀
#
#  ``ENGINE_*`` below is the single source of truth for engine ids, the global
#  controller modes, the autoscaler threshold and the live telemetry HUD.
#  engines.py holds the routing logic, telemetry.py the host sampling, ui.py
#  every piece of user-visible copy.
# --------------------------------------------------------------------------- #
#: Engine ids stored in the database and used in callback_data (ASCII only).
ENGINE_PYTHON = "python"
ENGINE_CPP = "cpp"
ENGINES = (ENGINE_PYTHON, ENGINE_CPP)

#: Global controller modes (``/setengine`` + the admin panel).
ENGINE_MODE_AUTO = "auto"
ENGINE_MODE_LOCK_CPP = "lock_cpp"
ENGINE_MODE_LOCK_PYTHON = "lock_python"
ENGINE_MODES = (ENGINE_MODE_AUTO, ENGINE_MODE_LOCK_CPP, ENGINE_MODE_LOCK_PYTHON)
#: Default behaviour: the dynamic autoscaler decides per request.
DEFAULT_ENGINE_MODE = ENGINE_MODE_AUTO

#: Concurrent extractions above which AUTO mode routes everything to C++ Turbo.
ENGINE_PEAK_THRESHOLD = int(os.environ.get("ENGINE_PEAK_THRESHOLD", "8"))
#: Multi-threaded worker slots the C++ Turbo engine may run per bulk batch.
ENGINE_TURBO_WORKERS = int(os.environ.get("ENGINE_TURBO_WORKERS", "4"))
#: Files up to this size are piped straight through memory by the C++ Turbo
#: engine ("zero-copy"): the downloader hands a ``BytesIO`` to the uploader, so
#: the payload is never written to a temp file and never re-read from disk.
#: Anything bigger — and every Python Standard job — keeps the streamed-to-disk
#: path, so a 2 GB premium upload can never exhaust the host's RAM.
ENGINE_ZERO_COPY_MAX_MB = int(os.environ.get("ENGINE_ZERO_COPY_MAX_MB", "512"))
ENGINE_ZERO_COPY_MAX_BYTES = ENGINE_ZERO_COPY_MAX_MB * 1024 * 1024
#: Version string rendered in the telemetry HUD (``None`` hides it).
ENGINE_TURBO_VERSION = "2.4"
ENGINE_PYTHON_VERSION = None
#: Engine the user starts on before they ever pick one (models holders only).
DEFAULT_ENGINE_PREFERENCE = ENGINE_PYTHON

# --------------------------------------------------------------------------- #
#  Granular VIP tiers (/addpremium) and durations
# --------------------------------------------------------------------------- #
#: tier key -> the exact flags stored on the user document.
GRANT_TIERS = {
    "public": {
        "label": "Only Public",
        "number": "1️⃣",
        "has_private_access": False,
        "has_models_access": False,
        "source": PREMIUM_SOURCE_PUBLIC,
        "description": "Standard public extraction quota — no private channels, "
                       "no C++ Turbo switcher.",
    },
    "models": {
        "label": "Public + Models",
        "number": "2️⃣",
        "has_private_access": False,
        "has_models_access": True,
        "source": PREMIUM_SOURCE_MODELS,
        "description": "Public extraction plus the C++ Turbo engine switcher "
                       "(/models and /engine).",
    },
    "private": {
        "label": "Public + Private",
        "number": "3️⃣",
        "has_private_access": True,
        "has_models_access": False,
        "source": PREMIUM_SOURCE_MANUAL,
        "description": "Public extraction plus private/restricted channels the "
                       "user's own session may read.",
    },
    "all": {
        "label": "All-in-One",
        "number": "4️⃣",
        "has_private_access": True,
        "has_models_access": True,
        "source": PREMIUM_SOURCE_MANUAL,
        "description": "Full VIP access — public, private and the C++ Turbo "
                       "engine switcher.",
    },
}
GRANT_TIER_KEYS = tuple(GRANT_TIERS)
#: Legacy two-button tier ids kept so older buttons never become dead ends.
LEGACY_TIER_ALIASES = {"full": "private"}
#: duration key -> days (``None`` means lifetime / no expiry).
GRANT_DURATIONS = {
    "month": {"label": "1 Month", "days": 30},
    "quarter": {"label": "3 Months", "days": 90},
    "year": {"label": "1 Year", "days": 365},
    "lifetime": {"label": "Lifetime", "days": None},
}
GRANT_CUSTOM_DAYS_KEY = "custom"
GRANT_MAX_DAYS = 36500

# --------------------------------------------------------------------------- #
#  Live telemetry HUD
# --------------------------------------------------------------------------- #
#: Progress-bar cells — ``68%`` renders as ``[████████░░░░]`` at this width.
TELEMETRY_BAR_WIDTH = 12
#: Host the ping probe connects to (a TCP handshake, never an API call).
TELEMETRY_PING_HOST = os.environ.get("TELEMETRY_PING_HOST", "api.telegram.org")
TELEMETRY_PING_PORT = int(os.environ.get("TELEMETRY_PING_PORT", "443"))
#: Seconds a ping result is reused for (the HUD ticks far more often).
TELEMETRY_PING_TTL = float(os.environ.get("TELEMETRY_PING_TTL", "5"))
#: Seconds a CPU/RAM reading is reused for.
TELEMETRY_SAMPLE_TTL = float(os.environ.get("TELEMETRY_SAMPLE_TTL", "1.5"))
#: Set to ``off`` to render the HUD without the server-load line.
TELEMETRY_ENABLED = os.environ.get("TELEMETRY", "auto").strip().lower() not in {
    "0", "off", "false", "no",
}
#: Minimum seconds between two Telegram edits of the same progress message.
TELEMETRY_EDIT_INTERVAL = float(os.environ.get("TELEMETRY_EDIT_INTERVAL", "2"))
#: Speed window (seconds) used to smooth the MB/s reading.
TELEMETRY_SPEED_WINDOW = float(os.environ.get("TELEMETRY_SPEED_WINDOW", "5"))

