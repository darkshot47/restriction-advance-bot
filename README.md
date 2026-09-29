# Restriction Advance Bot

A Telegram bot for saving messages from public channels and, **only for owner-granted premium**, private links the user's Telegram account is authorized to access. Built with Kurigram (Pyrogram-compatible API) and MongoDB.

## Access and referral rewards

| Plan | Daily extractions | Channels | Attribution |
| --- | ---: | --- | --- |
| Free, no referrals needed | 3 | Public only | `Extracted by @wantedkar99bot` |
| Points premium (`premium_source=redeem`) | Unlimited | Public only | None |
| Owner-granted **Public Only** (`premium_source=public`) | Unlimited | Public only | None |
| Owner-granted **Full** (`premium_source=manual`) | Unlimited | Public + authorized private | None |

- Each **new user** joining through `/refer`'s personal link awards the referrer **10 points**. Self-referrals, nonexistent referrers and repeat starts do not award extra points.
- `/redeem` and the inline redeem button spend **100 points** for **1 calendar month** of public-only premium, immediately.
- Repeat redemptions extend existing points premium. Redemption cannot overwrite active owner-granted premium or downgrade private access.
- Private-link restrictions are checked before single, range or bulk work begins and at the extraction boundary. Logging in alone does not unlock private links.
- A private/restricted link shows the **🔒 Private Channel Access (Premium Only)** pitch with one row: **[ 💎 Buy Premium ] [ 🎁 Earn Points ]**. The same screen is shown for single links, bulk lists and ranges, in private chat and inside a dump channel.
- Free daily slots are reserved atomically before extraction, including concurrent requests, and refunded on failure/cancellation. The quota resets at **00:00 UTC** (`database.utcnow()`), and hitting it shows the reason plus the same **[ 💎 Buy Premium ] [ 🎁 Earn Points ]** row.
- `/addpremium USER_ID DAYS` never grants immediately: the owner picks **🌐 Public Only** or **🔓 Full (Public + Private)** first, then the matching confirmation and the matching user notification are sent.
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
6. The owner verifies the actual payment. Every proof arrives with owner-only buttons: **✅ Approve** (activates the plan, stamps *✅ Approved by Owner* and notifies the user), **⚠️ Fake** (rejects, stamps the caption and notifies the user) and **🚫 Ban User** (bans for fraudulent proof, stamps the caption and notifies the user). `/addpremium USER_ID DAYS` is still available and now asks for the access tier. A screenshot or button press **never auto-approves payment**, and the review buttons only respond to `OWNER_ID`.

**Owner setup:** set `OWNER_ID` to @XyrDeveloper's numeric Telegram user ID and open/start the bot from that account. Telegram bots cannot initiate chats with arbitrary accounts; a username alone does not guarantee proof delivery. If both delivery attempts fail, the proof remains stored and the user is told to contact @XyrDeveloper directly — no false “sent” confirmation.

Use `/addqr`, then send the QR as a photo (or reply to a QR photo with `/addqr`). `/delqr` and `/removeqr` both remove it. Missing/invalid QR images do not start a proof-submission session. Checkout prompts are held in memory: after a restart, users can choose the plan again; already submitted proofs remain in MongoDB.

## Commands, feedback and admin panel

All existing slash commands are retained. Inline buttons and commands both work. A new slash command (including an unknown command), or navigation to another menu, cancels pending feedback instead of recording that command as feedback. `/cancel` and inline **Cancel** also clear checkout/input prompts.

`/admin`, `/admins`, or the **Admins** button in the owner's main menu open a compact, paginated command panel:

- Users & statistics (stats, users, logged users, new/active/top users, find/info/export)
- Premium & payments (add/remove premium, premium list, payment review, QR add/delete)
- Community (broadcast, direct message, ban/unban, ban list, feedback)
- **Channel dump** (`/setchat`, `/delchat`)
- Administration (admins, force subscription, maintenance, logs, help)

Every command in the panel also appears in the `/admins` list, and every panel button runs the same handler as its slash command. Parameterized actions prompt for details with examples. Authorization is checked for callbacks as well as typed commands; **only the owner** can run `/addpremium`. Regular admins cannot gain private-access grant permission through inline prompts.

## Channel dump (`/setchat`)

`/setchat` (or **📡 Set channel** in the main menu / the panel) starts a three-step wizard:

1. Send the channel as a link, `@username` or numeric ID — the wizard also accepts the command posted **inside** the channel itself.
2. Tap **🔍 Check Admin Status**: the bot verifies it is an administrator there *and* has the **Post Messages** permission.
3. Send one sample message link so the bot can prove it can read the channel; the link is then stored.

After that, any Telegram link posted in that channel is extracted straight into the channel, following the same public/premium-private rules as private chat. Requests are serialised per channel with a **3 s cooldown** and every Telegram `FloodWait` becomes a safe pause instead of a crash. In channel mode a "Message not found" notice deletes itself after **5 seconds** (`config.CHANNEL_CLEANUP_SECONDS`), and the bot ignores its own posts so it can never loop on its own status messages.

## Feedback

`/feedback` accepts plain text, emojis and `@mentions`. Any URL or link-like text (`https://…`, `www.…`, `t.me/…`, `telegram.me/…`, `joinchat`, bare domains, e-mails) is rejected with a warning and the session stays open so the user can retry — nothing is stored and the owner is not notified.

`/setfsub @channel` enables force subscription; `/delfsub` disables it. Make the bot an administrator of the required channel so membership checks work reliably. The join screen explains in English that users can use the bot only while they remain joined; membership is rechecked for each extraction.

## Presentation

Every visible heading, screen copy and inline button label is rendered through the **Unicode small-caps font engine** (`ui.smallcaps`). Digits and punctuation are untouched, and the conversion is context aware: URLs, `@usernames`, `/commands`, ``code`` spans, HTML tags/entities and every `callback_data` payload are copied through byte for byte, so links stay clickable and buttons keep working. `SMALL_CAPS=off` in the environment disables the font while debugging. Send-side text (`ui_text`/`say*`), captions, watermarks and extracted media payloads are never converted. Admin pages use at most two buttons per row and seven rows, rather than a single oversized command list. Native button colors are used when supported, with the existing fallback retained. Legacy language buttons remain compatible; operational messages stay in English.

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
.venv/bin/python -m compileall -q main.py database.py ui.py config.py tests
```

Tests cover command/button compatibility, checkout sequencing, proof metadata and delivery failures, cancellation, private-access restrictions, attribution, concurrency-safe quotas, calendar-month redemption and actual database functions against a Mongo mock. They also cover the round-three requirements: the small-caps engine and its protected regions (no rendered screen may leak plain ASCII copy outside links/commands), private-access and daily-limit screens with the dual button row, feedback link rejection, the `/addpremium` tier choice, the owner payment review actions, the `/setchat` wizard (admin check, sample verification, in-channel mode), channel-dump rate limiting/FloodWait handling and the five-second "Message not found" cleanup, every admin command being reachable from both `/admins` and the panel, and name/username re-sync so a rename shows up everywhere. They do **not** contact Telegram or a live MongoDB instance; verify QR rendering, proof delivery and membership checks with the deployed bot before accepting payments.
