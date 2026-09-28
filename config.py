"""Product and access-tier configuration for the bot."""

FREE_DAILY_LIMIT = 3
FREE_PRIVATE_LINKS = False
WATERMARK = "Extracted by @wantedkar99bot"
REFER_POINTS = 10
REDEEM_POINTS = 100
REDEEM_PREMIUM_MONTHS = 30
# Kept for integrations that import the old constant; redemption uses calendar months.
REDEEM_PREMIUM_DAYS = 900
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
REDEEM_LIMITATION = "Points premium covers public channels only. Private-channel links do not work with redemption points. Only premium manually granted by the owner unlocks private access."
RUPEE = "₹"
