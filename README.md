# Restriction Advance Bot

A Telegram bot for saving messages from public channels and, **only for owner-granted premium**, private links the user's Telegram account is authorized to access. Built with Kurigram (Pyrogram-compatible API) and MongoDB.

## Access and referral rewards

| Plan | Daily extractions | Channels | Engine | Attribution |
| --- | ---: | --- | --- | --- |
| Free, no referrals needed | 3 | Public only | ⚙️ Python Standard (🚀 Turbo during traffic peaks) | `Extracted by @wantedkar99bot` |
| Points premium (`premium_source=redeem`) | Unlimited | Public only | ⚙️ Python Standard | None |
| Owner-granted **1️⃣ Only Public** (`premium_source=public`) | Unlimited | Public only | ⚙️ Python Standard | None |
| Owner-granted **2️⃣ Public + Models** (`premium_source=models`) | Unlimited | Public only | ⚙️ / 🚀 switchable with `/models` | None |
| Owner-granted **3️⃣ Public + Private** (`premium_source=manual`) | Unlimited | Public + authorized private | ⚙️ Python Standard | None |
| Owner-granted **4️⃣ All-in-One** (`premium_source=manual`) | Unlimited | Public + authorized private | ⚙️ / 🚀 switchable with `/models` | None |

Access is stored as three independent flags on the user document — `is_premium`, `has_private_access` and `has_models_access` — plus `premium_tier` and `premium_expiry`. Documents written before this change carry no flags at all and keep working: the legacy `premium_source` (`manual` / purchase) still implies private access, while an explicitly stored `false` never falls back.

- Each **new user** joining through `/refer`'s personal link awards the referrer **10 points**. Self-referrals, nonexistent referrers and repeat starts do not award extra points.
- `/redeem` and the inline redeem button spend **100 points** for **1 calendar month** of public-only premium, immediately.
- Repeat redemptions extend existing points premium. Redemption cannot overwrite active owner-granted premium or downgrade private access.
- Private-link restrictions are checked before single, range or bulk work begins and at the extraction boundary. Logging in alone does not unlock private links.
- A private/restricted link shows the **🔒 Private Channel Access (Premium Only)** pitch with one row: **[ 💎 Buy Premium ] [ 🎁 Earn Points ]**. The same screen is shown for single links, bulk lists and ranges, in private chat and inside a dump channel.
- Free daily slots are reserved atomically before extraction, including concurrent requests, and refunded on failure/cancellation. The quota resets at **00:00 UTC** (`database.utcnow()`), and hitting it shows the reason plus the same **[ 💎 Buy Premium ] [ 🎁 Earn Points ]** row.
- `/addpremium USER_ID [DAYS]` never grants immediately: the owner picks one of the **four feature tiers** first, then the **duration**, and only then are the flags written and the user notified. See [Granular VIP grant](#granular-vip-grant-addpremium).
- Free media are copied server-side first, then the original caption is edited to add attribution underneath. Premium custom-caption commands remain available; free extractions do not replace the source caption. If Telegram's 1,024-character caption limit leaves no room, the original stays on the media and attribution follows in a separate message. Sticker/video-note attribution is also sent separately because these media cannot have captions. Long text is split without truncation.

## Premium purchase flow

1. `/premium` or **Premium** opens benefits, access conditions and prices — it does **not** immediately start checkout.
2. **Buy Plan** opens the plan selector. Every plan is sold in two variants — Standard (⚙️ Python engine) and **with the 🚀 C++ Turbo add-on** — and both prices come straight from `config.PREMIUM_PLANS`:

   | Plan | Standard | C++ Turbo add-on | With Turbo |
   | --- | ---: | ---: | ---: |
   | 1 month (30 days) | ₹99 | +₹50 | **₹149** |
   | 3 months (90 days) | ₹249 | +₹100 | **₹349** |
   | 1 year (365 days) | ₹700 | +₹149 | **₹849** |

3. Selecting a plan displays the owner's QR, the exact amount for the chosen variant (`₹99 base + ₹50 C++ Turbo add-on` for a Turbo month) and the instructions.
4. **I've paid** asks for a screenshot **as a photo**. Text alone is not accepted as proof.
5. The screenshot, plan, variant, price and duration are stored for `/payments`, then sent to the owner and, best effort, **@XyrDeveloper**.
6. The owner verifies the actual payment. Every proof arrives with owner-only buttons: **✅ Approve** (activates the plan, stamps *✅ Approved by Owner* and notifies the user), **⚠️ Fake** (rejects, stamps the caption and notifies the user) and **🚫 Ban User** (bans for fraudulent proof, stamps the caption and notifies the user). Approving a **Standard** proof grants tier 3️⃣ (public + private); approving a **Turbo** proof grants tier 4️⃣ (public + private + C++ Turbo models). `/addpremium USER_ID [DAYS]` is still available and asks for the tier first. A screenshot or button press **never auto-approves payment**, and the review buttons only respond to `OWNER_ID`.

**💬 Contact Owner** — an inline `url=` button pointing at `https://t.me/XyrDeveloper` — is rendered on every plan display, every pricing screen, the C++ Turbo upsell, the architecture page and the payment-proof wizard. `config.PAYMENT_CONTACT` is the single source of truth: changing it moves the button, the `@mention` and every amount breakdown at once. The link only ever appears inside a `url=` button, never in body copy.

**Owner setup:** set `OWNER_ID` to @XyrDeveloper's numeric Telegram user ID and open/start the bot from that account. Telegram bots cannot initiate chats with arbitrary accounts; a username alone does not guarantee proof delivery. If both delivery attempts fail, the proof remains stored and the user is told to contact @XyrDeveloper directly — no false “sent” confirmation.

Use `/addqr`, then send the QR as a photo (or reply to a QR photo with `/addqr`). `/delqr` and `/removeqr` both remove it. Missing/invalid QR images do not start a proof-submission session. Checkout prompts are held in memory: after a restart, users can choose the plan again; already submitted proofs remain in MongoDB.

## Commands, feedback and admin panel

All existing slash commands are retained. Inline buttons and commands both work. A new slash command (including an unknown command), or navigation to another menu, cancels pending feedback instead of recording that command as feedback. `/cancel` and inline **Cancel** also clear checkout/input prompts.

`/admin`, `/admins`, or the **Admins** button in the owner's main menu open a compact, paginated command panel. Its header lists the twelve most-used actions as clean, descriptive English command pairs — the same wording the inline buttons use:

```
📢 /setfsub — Add Force Subscribe      📋 /fsublist — Force Sub List
🗑️ /delfsub — Delete Force Subscribe    ⚙️ /setchat — Set Dump Channel
🧠 /setengine — Global Engine Controller 💎 /addpremium — Granular VIP Grant
❌ /removepremium — Remove VIP Access    📊 /stats — Global & Engine Analytics
📢 /broadcast — Broadcast Message        🚫 /ban & /unban — User Moderation
💳 /payments — Payment Review            🛠️ /maintenance — Maintenance Mode
```

The pages behind it are:

- Users & statistics (stats, users, logged users, new/active/top users, find/info/export)
- Premium & payments (add/remove premium, premium list, payment review, QR add/delete)
- **Engine & channels** (`/setengine` global engine controller, `/setchat`, `/delchat`)
- Community (broadcast, direct message, ban/unban, ban list, feedback)
- **Force Sub** (`/setfsub`, `/fsublist`, `/delfsub`, `/fsublabel`, `/fsubcheck`)
- Administration (admins, maintenance, logs, help)

Every command in the panel also appears in the `/admins` list, and every panel button runs the same handler as its slash command. Parameterized actions prompt for details with examples. Authorization is checked for callbacks as well as typed commands; **only the owner** can run `/addpremium`. Regular admins cannot gain private-access grant permission through inline prompts.

## Dual execution engines (⚙️ Python Standard / 🚀 C++ Turbo)

`engines.py` owns the two engines and the global controller that routes every extraction:

| Engine | Pipeline | Who gets it |
| --- | --- | --- |
| ⚙️ **Python Standard** | single stream, one link at a time, buffered download → upload | free/sample users and anyone without the `models` feature |
| 🚀 **C++ Turbo** `v2.4` | bounded worker pool (`ENGINE_TURBO_WORKERS`, default **4**), zero-copy stream piping (files up to `ENGINE_ZERO_COPY_MAX_MB`, default **512 MB**, are handed to the uploader straight from memory), native TgCrypto on every MTProto chunk | users whose plan grants `models`, and everybody during a traffic peak or a global C++ lock |

Both differences are real rather than cosmetic, and the test suite measures them: a Turbo dump-channel batch runs up to four links' slow phases (download + re-upload) at the same time while a Python batch stays strictly sequential, and a Turbo download asks Kurigram for an in-memory transfer (`download_media(..., in_memory=True)`) whose `BytesIO` is passed straight to `send_video` — no temp file, no re-read. A single-link post never spawns the pool (there is nothing to overlap), and a file above the zero-copy budget — or an unknown size — keeps the streamed-to-disk path so a multi-GB premium upload can never exhaust RAM.

**Global Engine Controller** — `/setengine` (owner only, also on the **🧠 Engine & Channels** panel page):

| Mode | Behaviour |
| --- | --- |
| 🤖 **Auto (Dynamic Autoscaler)** — default | watches live concurrent extractions; above `ENGINE_PEAK_THRESHOLD` (default **8**) *every* request is routed to 🚀 C++ Turbo to kill the queue, and free users fall back to ⚙️ Python Standard as soon as traffic normalises |
| 🚀 **Lock to C++** | global force: 100% of extractions (free **and** VIP) run on Turbo; the autoscaler is paused and the user switcher is fixed |
| ⚙️ **Lock to Python** | autoscaler off; free users are locked to Python Standard, while premium users holding the `models` permission keep their manual `/models` toggle |

`/setengine` alone opens the button panel; `/setengine auto|cpp|python` locks it in one step. The mode is persisted in MongoDB first and applied in memory second, so a lock survives a restart — and if the write fails nothing is applied and the owner is told. Peak detection is strict: *exceeding* the threshold counts, being equal to it does not. Every routing decision is counted per engine (this run and all time) and printed by `/stats`.

**User model switcher** — `/models` (alias `/engine`), plus the **📺 My Channels**-row button in the main menu:

- **With the `models` feature:** an interactive switcher, `[ ⚙️ Python Standard ]` and `[ 🚀 C++ Turbo ]`, the active one green and ticked. The choice is stored on the user document (`engine_preference`) and applies to private-chat extractions *and* dump-channel batches alike. The screen also shows the controller mode and the live traffic count.
- **Without it:** a feature overview — the C++ speed benefits, what zero-copy and multi-threading change, the add-on pricing per plan — plus **[ 🚀 Upgrade to C++ Turbo ]** and **[ 💬 Contact Owner ]**.
- The permission is re-checked at *press* time, so a revoked grant stops working immediately even on a keyboard still on screen, and a stored preference can never take effect without it. An expired premium document stops granting `models` too.

**Red Models button & /start badge.** The last row of `/start` is a dedicated `[ 🧠 Models Architecture ]` button styled **RED** (`ButtonStyle.DANGER`, falling back to a plain button where the library has no styles) opening the Python-vs-Turbo page: pipeline differences, worker counts and traffic-handling benchmarks, how AUTO scales, and how to unlock or purchase the add-on. The `/start` header carries the live engine badge, rendered identically by `/start` and the 🏠 button:

```
⚡ Active Engine: [C++ Turbo 🚀 (Peak Auto-Scale)]
⚡ Active Engine: [C++ Turbo 🚀 (Global Lock)]
🟢 Active Engine: [Python Standard ⚙️]
```

## Live telemetry HUD

While a file is being extracted the status message renders a terminal-style HUD (`telemetry.py` for the readings, `ui.telemetry_hud` for the copy):

```
⚡ Engine: C++ Turbo v2.4 [Active]
📥 Downloading: 68% [████████░░░░]
📊 Server Load: CPU 19.2% | RAM 41.8% | Ping 11ms
🚀 Speed: 44.2 MB/s • ETA: 00:03
```

- The engine line follows the routing decision (`⚙️ Engine: Python Standard [Active]` otherwise) and the stage flips to `Uploading` once the file goes back out.
- CPU comes from `/proc/stat` (load average as a fallback), RAM from `/proc/meminfo`, ping from a plain TCP handshake to `api.telegram.org:443` — no third-party dependency, no API call, no credentials.
- Readings are cached (`TELEMETRY_SAMPLE_TTL` 1.5 s, `TELEMETRY_PING_TTL` 5 s) and message edits are throttled to `TELEMETRY_EDIT_INTERVAL` (2 s), so a fast download never turns into edit spam.
- Telemetry is strictly best effort: a probe that fails or a sampler that raises leaves that value as `--` and the download continues. `TELEMETRY=off` drops the server-load line entirely.
- In a dump channel the public status message keeps its existing wording and carries the HUD above it.

## Granular VIP grant (`/addpremium`)

`/addpremium USER_ID [DAYS]` is a three-step, owner-only flow. Nothing is written until the last button press:

1. **Step 1 — feature tier**, four inline buttons backed by `config.GRANT_TIERS`:

   | Tier | Flags stored | `premium_source` |
   | --- | --- | --- |
   | 1️⃣ Only Public | `is_premium` | `public` |
   | 2️⃣ Public + Models | `is_premium`, `has_models_access` | `models` |
   | 3️⃣ Public + Private | `is_premium`, `has_private_access` | `manual` |
   | 4️⃣ All-in-One | `is_premium`, `has_private_access`, `has_models_access` | `manual` |

2. **Step 2 — duration**: `[📅 1 Month] [📅 3 Months]` / `[📅 1 Year] [♾ Lifetime]` / `[🔢 Custom Days]`. Lifetime stores `premium_expiry = None`. A `DAYS` argument typed with the command becomes a one-tap **✅ Use N days** button; **Custom Days** asks for an exact number (1–`GRANT_MAX_DAYS`, default 36500) in the next message and refuses garbage without dropping the session. **⬅️ Tier** returns to step 1.
3. **Store & notify**: the tier decides the flags *and* the `premium_source`, so a models-only grant can never inherit the legacy "manual means private" meaning. The owner sees exactly what was written (tier, private channels, C++ Turbo models, expiry) and the user is notified with the full details of their granted tier.

`/removepremium USER_ID` clears premium, both flags and the stored tier in one step and says so. Grant callbacks answer only to `OWNER_ID`; a stale or forged press changes nothing.

## User channel dashboard (`/mychannels`)

`/mychannels` — command and main-menu button — lists the user's configured dump channel/supergroup:

- 📌 title, 🆔 chat id, 🗂 type and 🔗 public handle when known
- 🔐 **bot posting rights**, from the same `describe_channel_admin` probe the `/setchat` wizard uses: *admin with posting rights*, *not an admin*, *admin but Post Messages disabled*, or *Telegram did not answer*
- 📦 **files extracted here**, a per-channel counter incremented after every successful batch
- 🟢 the user's **active engine** badge

Buttons: **🔍 Test Permissions** (re-runs the probe and reports), **🔄 Re-verify Admin** (the same probe, refreshing the stored title/username when the rights are fine again) and **🗑 Disconnect** (clears the channel, i.e. `/delchat`). With no channel connected the screen explains what `/setchat` does instead. The chat id inside a button is checked against the caller's own stored channel, so a stale or hand-forged callback can never touch somebody else's dump chat.

## Channel dump (`/setchat`)

`/setchat` (or **📡 Set channel** in the main menu / the panel) starts a three-step wizard. Channels **and** supergroups/groups are accepted, and every chat reference form is understood:

| Reference | Example |
| --- | --- |
| numeric id | `-1001234567890` |
| public username | `@mychannel` |
| public link | `t.me/mychannel`, `t.me/mychannel/15` |
| private link by id | `t.me/c/1234567890/15` |
| private invite link | `t.me/+AbCdEf`, `t.me/joinchat/AbCdEf` |

1. Send the chat in any of those forms — the wizard also accepts the command posted **inside** the channel or group itself.
2. Tap **🔍 Check Admin Status**: the bot verifies it is an administrator there *and* has the **Post Messages** permission. Rights are read from `ChatMember.privileges.can_post_messages` (Kurigram `ChatMember` has no `can_post_messages` of its own), and every check logs a `[SETCHAT]` line with the raw status and rights. An expired or invalid invite link, or a chat the bot cannot see, is reported with a friendly reason instead of a crash.
3. Send one sample message link — or, for a private channel where no public link exists, just the **bare message number** — so the bot can prove it can read the chat; the details are then stored.

For an approval-only chat (invite requests instead of instant joins) the bot sends a join request, asks the owner of that chat to approve it, stores nothing and keeps the wizard alive so **🔍 Check Admin Status** can be pressed again after the approval.

After that, any Telegram link posted in that channel is extracted straight into the channel, following the same public/premium-private rules as private chat. Requests are serialised per channel with a **3 s cooldown** and every Telegram `FloodWait` becomes a safe pause instead of a crash. In channel mode a "Message not found" notice deletes itself after **5 seconds** (`config.CHANNEL_CLEANUP_SECONDS`), and the bot ignores its own posts so it can never loop on its own status messages.

## Force subscription (multi-channel, private chats, join requests)

`/setfsub` takes a channel, supergroup or **private** chat in any of the reference forms listed above, and can be repeated as often as needed — there is no limit on the number of required chats. The wizard:

1. resolves the reference (joining a private chat when that is allowed, or sending a join request and waiting for approval),
2. verifies the bot is an administrator with posting rights there (the same `describe_channel_admin` check the `/setchat` wizard uses),
3. asks what the **Join** button should say, then saves the entry at the end of the list.

The custom label accepts 1–24 characters on a single line — emojis and digits welcome, links, `t.me/` references and `@`-mentions are not — and falls back to the default **✅ Join <title>** when the owner sends `-` or nothing. Labels are rendered through `ui.button()`, so the mobile budget (≤28 visible characters, ≤2 buttons per row) is never exceeded, and `callback_data` stays plain ASCII.

Owner commands (all also on the **📢 Force Sub** panel page and in `/admins`):

| Command | Effect |
| --- | --- |
| `/setfsub <link\|@user\|id>` | resolve a chat, ask for the button label, append it to the list |
| `/fsublist` | numbered list with each entry's title, button label, id and **✏️ Rename** / **🗑 Delete** |
| `/delfsub <number>` | remove one entry, `/delfsub all` (or the button) asks first, then removes everything |
| `/fsublabel <number> <text>` | rename one entry's Join button, `/fsublabel verify <text>` renames the global **✅ I Joined** button |
| `/fsubcheck <number\|all> on\|off` | toggle automatic approval of join requests for that entry |

The user-facing screen lists the required chats by title only and offers one **Join** button per entry plus the **✅ I Joined** button; more than `config.FSUB_ITEMS_PER_PAGE` entries paginate with Previous / Next. Pressing **✅ I Joined** re-checks every entry and only clears the screen once all of them are satisfied; a pending or approved join request counts as joined, and an entry with auto-approve enabled has its pending request approved on the spot.

**Join requests:** an incoming `@bot.on_chat_join_request` for a required chat is stored (`chat_id`, `user_id`, `date`, `status`). With auto-approve on, the request is approved and the user is told immediately. Otherwise the owner is notified with the joiner's fresh name and **✅ Approve** / **❌ Decline** buttons that only respond to `OWNER_ID`, exactly like the payment review actions.

Force subscription is owner-granted and never applies to the owner. Telegram errors during a membership check are logged and fail **open** — a transient network problem never locks a valid user out — and the bot still needs to be an administrator of every required chat for the checks to be reliable.

**Links never leak into copy:** invite links and usernames live inside the Join buttons (`url=`, or `copy_text`) only. No screen, list or confirmation ever prints a link back.

## Feedback

`/feedback` accepts plain text, emojis and `@mentions`. Any URL or link-like text (`https://…`, `www.…`, `t.me/…`, `telegram.me/…`, `joinchat`, bare domains, e-mails) is rejected with a warning and the session stays open so the user can retry — nothing is stored and the owner is not notified.

## Presentation

Every visible heading, screen copy and inline button label is rendered through the **Unicode small-caps font engine** (`ui.smallcaps`). Digits and punctuation are untouched, and the conversion is context aware: URLs, `@usernames`, `/commands`, ``code`` spans, HTML tags/entities and every `callback_data` payload are copied through byte for byte, so links stay clickable and buttons keep working. `SMALL_CAPS=off` in the environment disables the font while debugging. Send-side text (`ui_text`/`say*`), captions, watermarks and extracted media payloads are never converted. Admin pages use at most two buttons per row and seven rows, rather than a single oversized command list. Native button colors are used when supported, with the existing fallback retained. Legacy language buttons remain compatible; operational messages stay in English.

## Setup

Set `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`, `BOT_USERNAME` (without `@`), and `MONGO_URL`. `BOT_USERNAME` must match the actual bot so referral links work. The default is `wantedkar99bot`; free attribution is always `Extracted by @wantedkar99bot` as configured in `config.py`.

`config.py` is the single source of truth for pricing (`PREMIUM_PLANS` with each plan's `price` + `addon_price`), the owner contact (`PAYMENT_CONTACT` → `OWNER_CONTACT_URL`) and the grant vocabulary (`GRANT_TIERS`, `GRANT_DURATIONS`, `GRANT_MAX_DAYS`). Optional environment overrides, all with working defaults:

| Variable | Default | Effect |
| --- | --- | --- |
| `ENGINE_PEAK_THRESHOLD` | `8` | concurrent extractions the AUTO autoscaler must *exceed* to route everything to 🚀 C++ Turbo |
| `ENGINE_TURBO_WORKERS` | `4` | worker slots in the C++ Turbo pool per bulk batch |
| `ENGINE_ZERO_COPY_MAX_MB` | `512` | largest file the Turbo engine pipes through memory instead of a temp file |
| `TELEMETRY` | `auto` | `off` renders the HUD without the server-load line |
| `TELEMETRY_EDIT_INTERVAL` | `2` | minimum seconds between two Telegram edits of the same progress message |
| `TELEMETRY_SAMPLE_TTL` / `TELEMETRY_PING_TTL` | `1.5` / `5` | how long a CPU/RAM reading and a ping are reused |
| `TELEMETRY_PING_HOST` / `TELEMETRY_PING_PORT` | `api.telegram.org` / `443` | target of the latency probe (a TCP handshake only) |
| `TELEMETRY_BAR_WIDTH` | `12` | cells in the `[████████░░░░]` progress bar |
| `SMALL_CAPS` / `BUTTON_STYLES` | `auto` | `off` disables the font / the native button colours while debugging |

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
.venv/bin/python -m compileall -q main.py database.py ui.py config.py engines.py telemetry.py tests
```

Tests cover command/button compatibility, checkout sequencing, proof metadata and delivery failures, cancellation, private-access restrictions, attribution, concurrency-safe quotas, calendar-month redemption and actual database functions against a Mongo mock. They also cover the round-three requirements: the small-caps engine and its protected regions (no rendered screen may leak plain ASCII copy outside links/commands), private-access and daily-limit screens with the dual button row, feedback link rejection, the `/addpremium` tier choice, the owner payment review actions, the `/setchat` wizard (admin check, sample verification, in-channel mode), channel-dump rate limiting/FloodWait handling and the five-second "Message not found" cleanup, every admin command being reachable from both `/admins` and the panel, and name/username re-sync so a rename shows up everywhere.

The newest suite covers the admin-rights fix and the multi force-sub epic: the posting-rights check is asserted against **real `ChatMember` / `ChatAdministratorRights` objects** (including a `hasattr` guard, because a plain fake previously hid that the attribute does not exist on `ChatMember`), the `/setchat` wizard is exercised end to end with a private invite link, an approval-only `InviteRequestSent`, an expired hash, a supergroup, in-channel mode and a bare message number as the sample, `join_request_state` is checked for all five outcomes, the **✅ I Joined** button is checked for member, pending-with-auto-approve and not-joined, the join-request handler is checked for storage, the auto-approve DM and the owner-only Approve / Decline buttons, the multi force-sub list is checked for labels, ordering, pagination at twelve entries and deletion, `check_access` is checked for multiple entries with a fail-open on `ChatAdminRequired`, no fsub/setchat screen may contain a link while its keyboard keeps every link inside `url` buttons, and the new commands are checked in the panel, `/admins`, the inline handler map and the command-exclusion list. They do **not** contact Telegram or a live MongoDB instance; verify QR rendering, proof delivery and membership checks with the deployed bot before accepting payments.

The round-six suite (`tests/test_round6_dual_engine.py`, 253 tests) covers the dual-engine overhaul on the same in-memory fakes: the complete `resolve_engine` routing matrix as one parametrised truth table (three controller modes × `models` permission × stored preference × peak), the strict "exceeds the threshold" peak rule, `TrafficMonitor` concurrency accounting including slot restoration when an extraction raises, controller-mode persistence with a fall-back when the store is unreachable, autoscaler escalation and reversion through the real `fetch_and_send` path, and the C++ Turbo worker pool **measured** rather than assumed — a Turbo batch must reach `ENGINE_TURBO_WORKERS` overlapping links while a Python batch must never exceed one. The telemetry HUD is asserted against the specification's exact strings (`📥 Downloading: 68% [████████░░░░]`, `📊 Server Load: CPU 19.2% | RAM 41.8% | Ping 11ms`, `🚀 Speed: 44.2 MB/s • ETA: 00:03`) both as pure functions and as rendered inside a real download, with a deterministic host stand-in so no test reads `/proc` or opens a socket; probe failures, an unknown file size and a raising sampler must all degrade to `--` without breaking the transfer. Also covered: the red `ButtonStyle.DANGER` Models Architecture button and its page, the `/start` badge parity, the switcher (including refusal once the permission is revoked, and the two lock modes), `/setengine` in all three modes plus owner-only enforcement and a failed database write, the four-tier granular grant end to end (tier → flags → duration → stored document → user notice, custom days, `grant_back`, stale and forged callbacks), `/removepremium`, the tiered pricing maths straight from `config`, the Contact Owner `url=` button on every pricing surface, the `/mychannels` dashboard with all four posting-rights outcomes and a forged chat id, the engine block of `/stats`, the twelve admin command pairs, and the real `database.py` functions for every new field against a Mongo mock. Every new keyboard is checked against the standing constraints — at most 7 rows and 2 buttons per row, labels within 28 characters, ASCII-only `callback_data`, links only inside `url=` buttons — and every new screen is checked for English-only copy (no Devanagari) with no raw link in the prose.
