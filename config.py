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
#: How many dump channels one user may register with /setchat.
MAX_USER_CHANNELS = int(os.environ.get("MAX_USER_CHANNELS", "2"))
#: Message ids requested per ``get_messages`` call while pre-scanning a range.
#: Telegram accepts a list of ids, so the scan is batched instead of firing one
#: request per id (which would both stall the run and risk a FloodWait).
RANGE_PREFLIGHT_BATCH = int(os.environ.get("RANGE_PREFLIGHT_BATCH", "100"))
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
#: Seconds between two *item starts* inside one bulk batch.  The C++ Turbo pool
#: overlaps the slow parts of several files, but the starts stay spaced by this
#: gap so Telegram is never hammered.  Defaults to the same anti-ban value the
#: channel dump cooldown uses (``CHANNEL_EXTRACT_COOLDOWN``).
ENGINE_START_GAP_SECONDS = float(os.environ.get(
    "ENGINE_START_GAP_SECONDS", "3.0"))
#: Download throughput cap of the ⚙️ Python Standard engine, in MB/s.  This is
#: what makes C++ Turbo visibly faster on a single stream: Python Standard is
#: paced by a token bucket, C++ Turbo is uncapped.  ``0`` (or an empty value)
#: disables the cap entirely.
ENGINE_PYTHON_SPEED_LIMIT_MBPS = float(os.environ.get(
    "ENGINE_PYTHON_SPEED_LIMIT_MBPS", "3.0") or 0)
#: Burst allowance of the Python Standard token bucket, expressed in seconds of
#: full-rate transfer.  ``0`` (the default) means a strict cap: the transfer of
#: *N* bytes takes exactly ``N / ENGINE_PYTHON_SPEED_LIMIT_MBPS`` seconds, which
#: is what makes the throttle measurable.  A positive value would let the first
#: chunks of a transfer go out at line rate before the pacing kicks in.
ENGINE_PYTHON_SPEED_BURST_SECONDS = float(os.environ.get(
    "ENGINE_PYTHON_SPEED_BURST_SECONDS", "0"))
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
#  Owner dump channel (the mirror) — copy, never forward
# --------------------------------------------------------------------------- #
#: Every delivered extraction is mirrored into the owner's dump channel and
#: deleted again after this many seconds (10 minutes by default).  The mirror
#: uses ``copy_message`` — never ``forward`` — so nothing carries a
#: "Forwarded from" header, and the copy is removed again once it has served
#: its purpose.
DUMP_TTL_SECONDS = int(os.environ.get("DUMP_TTL_SECONDS", "600"))
#: How many mirrored messages may wait for their TTL delete at the same time.
#: Beyond this the oldest entry is deleted immediately instead of queueing.
DUMP_QUEUE_LIMIT = int(os.environ.get("DUMP_QUEUE_LIMIT", "500"))
#: Seconds between two dump-channel operations (mirror / delete) — halves the
#: chance of a FloodWait and is one of the governor's keys.
DUMP_COOLDOWN_SECONDS = float(os.environ.get("DUMP_COOLDOWN_SECONDS", "1.0"))

# --------------------------------------------------------------------------- #
#  /pin, /pinned and the inline-button wizard
# --------------------------------------------------------------------------- #
#: Most buttons one outgoing message may carry (each gets its own row, so the
#: keyboard stays inside the 7-row / 2-button mobile budget).
MAX_MESSAGE_BUTTONS = int(os.environ.get("MAX_MESSAGE_BUTTONS", "3"))
#: Longest button label the wizard accepts.
MAX_BUTTON_LABEL = int(os.environ.get("MAX_BUTTON_LABEL", "28"))
#: Colour names the wizard offers, mapped to the ui.button styles.
BUTTON_COLORS = {
    "blue": {"label": "🔵 Blue", "style": "primary"},
    "green": {"label": "🟢 Green", "style": "success"},
    "red": {"label": "🔴 Red", "style": "danger"},
}

# --------------------------------------------------------------------------- #
#  Giveaways
# --------------------------------------------------------------------------- #
#: One giveaway at a time is allowed — this is the only guard the panel needs.
GIVEAWAY_SINGLE_ACTIVE = True
#: Seconds between two live-count refreshes of the pinned giveaway message.
GIVEAWAY_LIVE_REFRESH_SECONDS = int(os.environ.get("GIVEAWAY_LIVE_REFRESH_SECONDS", "60"))
#: The public giveaway message is re-posted (and re-pinned) once every N hours
#: while the giveaway runs.
GIVEAWAY_DAILY_INTERVAL_SECONDS = int(
    os.environ.get("GIVEAWAY_DAILY_INTERVAL_SECONDS", str(24 * 3600)))
#: Rows per page of the owner's participant list.
GIVEAWAY_PARTICIPANTS_PER_PAGE = int(os.environ.get("GIVEAWAY_PARTICIPANTS_PER_PAGE", "10"))
#: Longest benefit line the owner may type.
GIVEAWAY_MAX_BENEFIT_CHARS = int(os.environ.get("GIVEAWAY_MAX_BENEFIT_CHARS", "200"))
#: Longest a giveaway may run (the end date doubles as the announcement date).
GIVEAWAY_MAX_DAYS = int(os.environ.get("GIVEAWAY_MAX_DAYS", "365"))
#: Suggested benefit lines offered as one-tap buttons in the wizard.
GIVEAWAY_BENEFIT_SUGGESTIONS = (
    "Unlimited public + private extractions, 2 GB files, C++ Turbo speed",
    "C++ Turbo engine: 4 worker slots, zero-copy streaming, no speed cap",
    "Private channel access + the C++ Turbo switcher, full VIP",
)

# --------------------------------------------------------------------------- #
#  Native C++ engine (native/restriction_engine.cpp)
# --------------------------------------------------------------------------- #
#: Seconds the channel-share deep link a user can send into a channel stays
#: valid before it has to be regenerated.
CHANNEL_SHARE_TOKEN_TTL = int(os.environ.get("CHANNEL_SHARE_TOKEN_TTL", "3600"))

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

