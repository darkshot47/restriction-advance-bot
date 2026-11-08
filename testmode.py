"""Owner-only test mode: walk the whole user journey without touching anything.

Why this exists
---------------
Every screen of the bot is driven by live data — a quota counter, a payment
record, a premium flag — so the only way to know what a user *actually* sees
after paying was to pay.  Test mode renders the same copy from the same ``ui``
functions with made-up data, one step at a time, and explains what the bot would
do next.

Guarantees
----------
* **Read-only.** Nothing here writes to MongoDB, sends a message to a user,
  activates premium, or charges anything.  The only side effect is the text the
  owner is reading.
* **Honest.** The copy is the real copy (``ui.premium_overview``,
  ``ui.plans_text``, ``ui.payment_text`` …), not a mock-up, so a wording bug is
  visible here before a user finds it.
* **Pure.** No Telegram or database imports: the whole file is unit tested.

A "step" is a key from :data:`STEPS`; :func:`screen` returns the text and the
button rows for it, and :func:`amount_outcome` explains what a custom amount
would mean.
"""

from __future__ import annotations

TEST_BANNER = "🧪 **TEST MODE** — nothing is charged, nothing is saved"

#: ``(key, label)`` in journey order: the exact path a paying user walks.
STEPS = (
    ("start", "🆕 /start (new user)"),
    ("free_limit", "🎁 Daily quota hit"),
    ("private_lock", "🔒 Private link locked"),
    ("premium", "💎 Premium page"),
    ("plans", "🛍 Plan chooser"),
    ("payment", "💳 Payment screen"),
    ("proof", "📸 Proof submitted"),
    ("review", "👑 Owner review"),
    ("approved", "✅ After approval"),
    ("premium_user", "⚡ Premium extraction"),
    ("custom", "✏️ Custom amount"),
)

_NEXT_HINT = {
    "start": "a link is pasted → the bot extracts it (3 free per day)",
    "free_limit": "the 4th link of the day → quota screen with the premium pitch",
    "private_lock": "a restricted/private link → premium required before any work",
    "premium": "Buy Plan → the plan chooser (one price per duration)",
    "plans": "a plan is tapped → the owner's QR and the exact amount",
    "payment": "I've paid → the bot asks for a screenshot as a photo",
    "proof": "the screenshot reaches the owner with Approve / Fake / Ban buttons",
    "review": "Approve → premium is written and the user is notified",
    "approved": "the new premium user pastes a link → private access works",
    "premium_user": "nothing left to buy — this is the end state",
    "custom": "type any amount to see exactly what that payment would do",
}


def label_of(key: str) -> str:
    for step_key, label in STEPS:
        if step_key == key:
            return label
    return key


def index_of(key: str) -> int:
    for index, (step_key, _label) in enumerate(STEPS):
        if step_key == key:
            return index
    return 0


def next_key(key: str) -> str:
    index = min(len(STEPS) - 1, index_of(key) + 1)
    return STEPS[index][0]


def prev_key(key: str) -> str:
    index = max(0, index_of(key) - 1)
    return STEPS[index][0]


def amount_outcome(amount) -> dict:
    """What a payment of *amount* rupees would mean.

    The result is a dict with ``kind`` (``exact`` / ``underpaid`` / ``partial``
    / ``overpaid`` / ``invalid``), a human ``title``, the ``plan`` it maps to and
    the number of ``days`` that would be granted.
    """
    from config import PREMIUM_PLANS, plan_base_price

    try:
        value = int(round(float(amount)))
    except (TypeError, ValueError):
        return {"kind": "invalid", "title": "That is not an amount", "plan": None,
                "days": 0, "amount": 0}

    if value <= 0:
        return {"kind": "invalid", "title": "An amount must be more than zero",
                "plan": None, "days": 0, "amount": 0}

    plans = sorted(PREMIUM_PLANS.items(), key=lambda item: plan_base_price(item[1]))
    cheapest_key, cheapest = plans[0]
    priciest_key, priciest = plans[-1]
    cheapest_price = plan_base_price(cheapest)
    priciest_price = plan_base_price(priciest)

    for key, plan in plans:
        if plan_base_price(plan) == value:
            return {
                "kind": "exact",
                "title": f"Exact price of {plan.get('title', key)}",
                "plan": key,
                "days": int(plan.get("days", 30)),
                "amount": value,
            }

    if value < cheapest_price:
        return {
            "kind": "underpaid",
            "title": f"Below the cheapest plan ({cheapest.get('title', cheapest_key)})",
            "plan": None,
            "days": 0,
            "amount": value,
        }

    if value > priciest_price:
        return {
            "kind": "overpaid",
            "title": f"Above the longest plan ({priciest.get('title', priciest_key)})",
            "plan": priciest_key,
            "days": int(priciest.get("days", 365)),
            "amount": value,
        }

    lower_key, lower = plans[0]
    for key, plan in plans:
        if plan_base_price(plan) < value:
            lower_key, lower = key, plan
    return {
        "kind": "partial",
        "title": f"Between two plans — closest is {lower.get('title', lower_key)}",
        "plan": lower_key,
        "days": int(lower.get("days", 30)),
        "amount": value,
    }


def _amount_block(amount) -> list[str]:
    outcome = amount_outcome(amount)
    kind = outcome["kind"]
    lines = [
        "",
        f"💠 **Simulated payment: ₹{outcome['amount']}**",
        f"• Verdict: **{outcome['title']}**",
    ]
    if kind == "exact":
        lines += [
            f"• The bot would grant: **{outcome['days']} days** of public + private",
            "• Owner taps ✅ Approve → premium is written instantly",
        ]
    elif kind == "underpaid":
        lines += [
            "• The bot would *not* activate anything automatically",
            "• The owner sees the amount next to the plan price and can mark it fake",
        ]
    elif kind == "partial":
        lines += [
            f"• The owner decides: grant {outcome['days']} days, or ask for the rest",
            "• Nothing is activated until the owner approves",
        ]
    elif kind == "overpaid":
        lines += [
            f"• The longest plan is granted ({outcome['days']} days) and the extra is",
            "  left to the owner to refund or extend — the bot never decides alone",
        ]
    else:
        lines += ["• Nothing would happen: the bot waits for a real amount"]
    return lines


def screen(key: str = "start", *, amount=None, plan_key: str = "month") -> tuple[str, list]:
    """Text and button rows for one step of the journey.

    ``amount`` (rupees) is only used by the ``payment`` and ``custom`` steps; it
    is what the owner types to see a payment screen with their own number.
    """
    import ui
    from config import (FREE_DAILY_LIMIT, PAYMENT_CONTACT, PREMIUM_PLANS, RUPEE,
                        plan_base_price)

    plan = PREMIUM_PLANS.get(plan_key) or next(iter(PREMIUM_PLANS.values()))
    price = plan_base_price(plan)
    lines: list[str] = [TEST_BANNER, f"📍 Step: {label_of(key)}", ""]

    if key == "start":
        lines += [
            "👋 **WELCOME TO THE BOT**",
            "",
            "Paste any Telegram link and it is saved for you.",
            "",
            f"🆓 Free users: **{FREE_DAILY_LIMIT} public extractions per day**, "
            "watermark on the copy.",
            "🔐 /login unlocks private links *after* premium.",
            "💎 /premium shows the plans.",
        ]
    elif key == "free_limit":
        lines += [
            "⏳ **DAILY LIMIT REACHED**",
            "",
            f"You already used all **{FREE_DAILY_LIMIT}** free extractions today.",
            "The counter resets at **00:00 UTC**.",
            "",
            "The screen ends with two buttons: **💎 Buy Premium** and **🎁 Earn Points**.",
        ]
    elif key == "private_lock":
        lines += [
            "🔒 **PRIVATE CHANNEL ACCESS (PREMIUM)**",
            "",
            "That link points at a private or restricted chat. Reading it needs:",
            "• active premium, and",
            "• your own logged-in Telegram session (`/login`).",
            "",
            "No download starts until both are true — free users never see the "
            "restricted content.",
        ]
    elif key == "premium":
        lines += [ui.premium_overview(False, {"premium_source": None})]
    elif key == "plans":
        lines += [ui.plans_text()]
    elif key == "payment":
        shown = amount if amount else price
        lines += [
            ui.payment_text(plan),
            "",
            f"🧪 The QR screen above is exactly what a user sees, with "
            f"**{RUPEE}{price}** for *{plan.get('title', plan_key)}*.",
        ]
        if amount:
            lines += _amount_block(amount)
    elif key == "proof":
        lines += [
            "📸 **PROOF ASKED**",
            "",
            "The user is told to send a screenshot **as a photo** — text is refused.",
            "",
            "👑 The owner receives it with three buttons:",
            "• ✅ Approve — grants this plan",
            "• ⚠️ Fake — rejects and marks the caption",
            "• 🚫 Ban — bans the account for a fraudulent proof",
        ]
    elif key == "review":
        lines += [
            f"👑 **OWNER VIEW** (@{PAYMENT_CONTACT})",
            "",
            "Caption the owner reads:",
            "",
            ui.payment_review_owner_text(999_000_001, plan.get("title", plan_key),
                                         f"{RUPEE}{price}", plan.get("days", 30)),
        ]
    elif key == "approved":
        lines += [
            "✅ **AFTER APPROVAL — WHAT THE USER GETS**",
            "",
            ui.payment_approved_user_text(plan.get("title", plan_key),
                                          plan.get("days", 30)),
            "",
            "At the same moment the bot writes:",
            "`is_premium = True`, `has_private_access = True`, the expiry date, "
            "and the `premium_source` of the plan.",
        ]
    elif key == "premium_user":
        lines += [
            "⚡ **PREMIUM EXTRACTION**",
            "",
            "• No daily counter — unlimited",
            "• Private / restricted channels work after `/login`",
            "• No watermark on the delivered copy",
            "• Files up to 2 GB",
            "",
            "The engine is picked automatically: a traffic spike moves the job to "
            "the faster pool without the user doing anything.",
        ]
    elif key == "custom":
        if amount:
            lines += _amount_block(amount)
            lines += ["", "The payment screen for this amount:", ""]
            lines += [ui.payment_text({**plan, "price": int(outcome_price(amount))})]
        else:
            lines += [
                "✏️ **CUSTOM AMOUNT**",
                "",
                "Tap **Type an amount** and send any number.",
                "You will see the payment screen with that amount and exactly what "
                "the bot would do with it — approved, underpaid, in between, or "
                "overpaid — without charging anything.",
            ]
    else:
        lines += ["Unknown step."]

    lines += ["", f"➡️ **Next:** {_NEXT_HINT.get(key, '')}"]

    rows = [
        [("◀️ Back", "tm:prev"), ("Next ▶️", "tm:next")],
        [("✏️ Type an amount", "tm:amount")],
        [("🖥 All steps", "tm:list")],
        [("❌ Exit test mode", "tm:exit")],
    ]
    return "\n".join(line for line in lines if line is not None), rows


def outcome_price(amount):
    """The amount as a plan price (falls back to the cheapest plan)."""
    from config import PREMIUM_PLANS, plan_base_price

    try:
        return max(1, int(round(float(amount))))
    except (TypeError, ValueError):
        return plan_base_price(next(iter(PREMIUM_PLANS.values())))


def list_text() -> str:
    lines = [TEST_BANNER, "", "🖥 **EVERY STEP OF THE USER JOURNEY**", ""]
    for index, (_key, label) in enumerate(STEPS, 1):
        lines.append(f"{index}. {label}")
    lines += [
        "",
        "Open any step to see the exact screen a user sees, plus what the bot "
        "does next. Nothing here is saved or charged.",
    ]
    return "\n".join(lines)


def list_rows() -> list:
    rows = []
    row = []
    for key, label in STEPS:
        row.append((label, f"tm:s:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("❌ Exit test mode", "tm:exit")])
    return rows
