# Restriction Advance Bot

A Telegram bot for saving messages from public channels and, **only for owner-granted premium**, private links the user's Telegram account is authorized to access. Built with Kurigram (Pyrogram-compatible API) and MongoDB.

## Access and referral rewards

| Plan | Daily extractions | Channels | Attribution |
| --- | ---: | --- | --- |
| Free, no referrals needed | 3 | Public only | `Extracted by @wantedkar99bot` |
| Points premium | Unlimited | Public only | None |
| Owner-granted manual premium | Unlimited | Public + authorized private | None |

- Each **new user** joining through `/refer`'s personal link awards the referrer **10 points**. Self-referrals, nonexistent referrers and repeat starts do not award extra points.
- `/redeem` and the inline redeem button spend **100 points** for **1 calendar month** of public-only premium, immediately.
- Repeat redemptions extend existing points premium. Redemption cannot overwrite active owner-granted premium or downgrade private access.
- Private-link restrictions are checked before single, range or bulk work begins and at the extraction boundary. Logging in alone does not unlock private links.
- Free daily slots are reserved atomically before extraction, including concurrent requests, and refunded on failure/cancellation. Days reset at server midnight; deploy in **UTC** for a UTC daily quota.
- Free media are copied server-side first, then the original caption is edited to add attribution underneath. Premium custom-caption commands remain available; free extractions do not replace the source caption. If Telegram's 1,024-character caption limit leaves no room, the original stays on the media and attribution follows in a separate message. Sticker/video-note attribution is also sent separately because these media cannot have captions. Long text is split without truncation.

## Premium purchase flow

1. `/premium` or **Premium** opens benefits, access conditions and prices — it does **not** immediately start checkout.
2. **Buy Plan** opens the plan selector:
   - **₹99 / 1 month** — manual activation for 30 days
   - **₹249 / 3 months** — 90 days
   - **₹700 / 1 year** — 365 days
3. Selecting a plan displays the owner's QR, exact amount and instructions.
4. **I've paid** asks for a screenshot **as a photo**. Text alone is not accepted as proof.
5. The screenshot and selected plan, price and duration are stored for `/payments`, then sent to the owner and, best effort, **@XyrDeveloper**.
6. The owner verifies the actual payment and runs `/addpremium USER_ID DAYS`. A screenshot or button press **never auto-approves payment**.

**Owner setup:** set `OWNER_ID` to @XyrDeveloper's numeric Telegram user ID and open/start the bot from that account. Telegram bots cannot initiate chats with arbitrary accounts; a username alone does not guarantee proof delivery. If both delivery attempts fail, the proof remains stored and the user is told to contact @XyrDeveloper directly — no false “sent” confirmation.

Use `/addqr`, then send the QR as a photo (or reply to a QR photo with `/addqr`). `/delqr` and `/removeqr` both remove it. Missing/invalid QR images do not start a proof-submission session. Checkout prompts are held in memory: after a restart, users can choose the plan again; already submitted proofs remain in MongoDB.

## Commands, feedback and admin panel

All existing slash commands are retained. Inline buttons and commands both work. A new slash command (including an unknown command), or navigation to another menu, cancels pending feedback instead of recording that command as feedback. `/cancel` and inline **Cancel** also clear checkout/input prompts.

`/admin`, `/admins`, or the **Admins** button in the owner's main menu open a compact, paginated command panel:

- Users/statistics and export
- Premium, payment proofs and QR management
- Broadcast, direct messages, bans and feedback
- Admin management, force subscription, maintenance and logs

Parameterized actions prompt for details with examples. Authorization is checked for callbacks as well as typed commands; **only the owner** can run `/addpremium`. Regular admins cannot gain private-access grant permission through inline prompts.

`/setfsub @channel` enables force subscription; `/delfsub` disables it. Make the bot an administrator of the required channel so membership checks work reliably. The join screen explains in English that users can use the bot only while they remain joined; membership is rechecked for each extraction.

## Presentation

English copy uses emoji, **bold headings**, clear steps and short inline labels. Admin pages use at most two buttons per row and six rows, rather than a single oversized command list. Native button colors are used when supported, with the existing fallback retained. Telegram controls the final font, keyboard width and rendering; the bot does not use inaccessible Unicode lookalike alphabets or promise a fixed full-screen layout. Legacy language buttons remain compatible; operational messages stay in English.

## Setup

Set `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`, `BOT_USERNAME` (without `@`), and `MONGO_URL`. `BOT_USERNAME` must match the actual bot so referral links work. The default is `wantedkar99bot`; free attribution is always `Extracted by @wantedkar99bot` as configured in `config.py`.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Do not commit credentials or Telegram session files. Only extract content you are authorized to access.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q main.py database.py ui.py config.py
```

Tests cover command/button compatibility, checkout sequencing, proof metadata and delivery failures, cancellation, private-access restrictions, attribution, concurrency-safe quotas, calendar-month redemption and actual database functions against a Mongo mock. They do **not** contact Telegram or a live MongoDB instance; verify QR rendering, proof delivery and membership checks with the deployed bot before accepting payments.
