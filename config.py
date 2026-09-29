"""Product and access-tier configuration for the bot."""

FREE_DAILY_LIMIT = 3
FREE_PRIVATE_LINKS = False
WATERMARK = "Extracted by @wantedkar99bot"
REFER_POINTS = 10
REDEEM_POINTS = 100
REDEEM_PREMIUM_MONTHS = 1
# Kept for integrations that import the old constant; redemption uses calendar months.
REDEEM_PREMIUM_DAYS = 30
PAYMENT_CONTACT = "XyrDeveloper"
PREMIUM_PLANS = {
    "month": {"title": "1 month", "price": 99, "days": 30},
    "quarter": {"title": "3 months", "price": 249, "days": 90},
    "year": {"title": "1 year", "price": 700, "days": 365},
}
PREMIUM_BENEFITS = (
    "Unlimited public-channel extractions",
    "Up to 2 GB files",
    "Priority support",
)
REDEEM_LIMITATION = "This bot extracts restricted content from public channels only."
RUPEE = "₹"

# --------------------------------------------------------------------------- #
#  Access tiers
# --------------------------------------------------------------------------- #
#: Premium source for a full (public + private) owner grant.
PREMIUM_SOURCE_MANUAL = "manual"
#: Premium source for an owner grant that only unlocks public channels.
PREMIUM_SOURCE_PUBLIC = "public"
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
