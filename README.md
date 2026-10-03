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
- Free extractions preserve the source message. When the owner has connected a dump channel **and the user has a custom caption in play** (`/setcaption`, `/setprefix` or `/setsuffix`), the content is downloaded into the dump first, the caption/attribution is applied to that temporary copy, and the finished copy is then copied from the dump to the user, so the recipient sees neither a “Forwarded from” header nor an “Edited” label. Every other link is delivered directly and never touches the dump (a free user's attribution on such a link is added the legacy way, by editing the copy). Premium custom-caption commands remain available; free extractions without a custom caption do not replace the source caption. If Telegram's 1,024-character caption limit leaves no room, the original stays on the media and attribution follows in a separate message. Sticker/video-note attribution is also sent separately because these media cannot have captions. Long text is split without truncation.

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
📢 /broadcast — Channels & Users         🚫 /ban & /unban — User Moderation
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

| Engine | Pipeline | Throughput cap | Who gets it |
| --- | --- | --- | --- |
| ⚙️ **Python Standard** | single stream, one item at a time in the order sent, buffered download → upload | **~3 MB/s** (`ENGINE_PYTHON_SPEED_LIMIT_MBPS`, token-bucket paced; `0` disables the cap) | free/sample users and anyone without the `models` feature |
| 🚀 **C++ Turbo** `v2.4` | bounded worker pool (`ENGINE_TURBO_WORKERS`, default **4**) over multi-link, range and channel batches, zero-copy stream piping (files up to `ENGINE_ZERO_COPY_MAX_MB`, default **512 MB**, are handed to the uploader straight from memory), priority routing above `ENGINE_PEAK_THRESHOLD` concurrent extractions | **uncapped** — no throughput limit at all | users whose plan grants `models`, and everybody during a traffic peak or a global C++ lock |

### The native C++ engine (`native/`)

Next to the Turbo pipeline there is a **real, compiled C++ engine** — not a label: `native/restriction_engine.{hpp,cpp}` build into `librestriction_engine.so` (`make -C native`, or `cmake -S native -B native/build`, or let the bot build it on first import) and `native_engine.py` loads it with `ctypes`. It answers on the hot path:

| Entry point | What the C++ does | Where the bot uses it |
| --- | --- | --- |
| `re_parse_link` | the whole Telegram message-URL grammar (usernames, `/s/` previews, topics, `t.me/c/…`, invites) | `main.parse_link` — **every** link the bot sees |
| `re_scan` | one pass over an incoming message: command + command index, link count, private/invite/multi-link/range flags | instant command dispatch without a Python regex |
| `re_gov_*` | the FloodWait governor (per-key cooldown + penalty, one mutex-guarded table) | dump channels, the owner dump mirror, the giveaway poster |
| `re_escape_batch` / `re_pool_*` | HTML escaping on a real `std::thread` pool | broadcast personalisation (thousands of copies), mirror captions |
| `re_bucket_charge` | token-bucket maths for the ⚙️ Python speed cap | `telemetry.SpeedThrottle` |

`/native` (owner) shows the live report — version, compiler, thread count, tasks run, governor waits and a self-test — and the startup log prints the same line. When no compiler is present the bridge falls back to a byte-for-byte equivalent Python implementation, so the bot never breaks; `tests/test_cpp_engine.py` asserts the two backends return **identical** results, which is what makes the swap safe.

> **On the old 2-second reply.** Nothing in front of a reply sleeps: the command path is native parse → the handler's own reads → the Telegram call. Every private message and button press now prints `[LATENCY] … update_lag=…ms` — Telegram stamps each update with its own UTC time, so that line separates a **late update** (network/host/queue) from a **slow handler** (the bot's own work, which is microseconds). The only deliberate wait inside a request is the `ENGINE_START_GAP_SECONDS` spacing between items of a batch.

> **TgCrypto is not a Turbo feature.** The native C cipher is installed for the whole bot, so *both* engines use it on every MTProto chunk and it differentiates nothing. Earlier copy claimed otherwise; the engine pages (`/models`, **🧠 Models Architecture**) now list only what the code really does.

Both differences are real rather than cosmetic, and the test suite measures them: a Turbo batch runs up to four items' slow phases (download + re-upload) at the same time while a Python batch stays strictly sequential in the order sent, a Turbo download asks Kurigram for an in-memory transfer (`download_media(..., in_memory=True)`) whose `BytesIO` is passed straight to `send_video` — no temp file, no re-read — and a Python download is provably paced to ~3 MB/s against a fake clock while a Turbo one sleeps not at all. A single-item request never spawns the pool (there is nothing to overlap), and a file above the zero-copy budget — or an unknown size — keeps the streamed-to-disk path so a multi-GB premium upload can never exhaust RAM.

**Where 🚀 C++ Turbo helps — and where it changes nothing.** Turbo pays off on *batches*: a multi-link post, a `1-500` range or a dump-channel post, where up to `ENGINE_TURBO_WORKERS` items genuinely overlap, plus the missing speed cap and zero-copy piping on every file. It does **not** parallelise a single small file: that is one MTProto stream on both engines, so the worker pool stays idle and the only wins there are the zero-copy path (no temp file, no re-read) and the absent ~3 MB/s throttle. Item starts stay spaced by `ENGINE_START_GAP_SECONDS` (default **3.0 s**) on both engines, so parallelism never turns into hammering Telegram.

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

`/mychannels` — command and main-menu button — lists **every** dump channel the account has connected (up to `MAX_USER_CHANNELS`, default **2**):

- 📌 title, 🆔 chat id, 🗂 type and 🔗 public handle when known
- 🔐 **bot posting rights**, from the same `describe_channel_admin` probe the `/setchat` wizard uses: *admin with posting rights*, *not an admin*, *admin but Post Messages disabled*, or *Telegram did not answer*
- 📦 **files extracted here**, a **per-channel** counter incremented after every successful batch — the two channels never share a total
- 🟢 the user's **active engine** badge
- 🔗 `Connected: 2/2` when the account is at its limit

Buttons are **per channel**: **🔍 Test Permissions** (re-runs the probe and reports), **🔄 Re-verify Admin** (the same probe, refreshing the stored title/username when the rights are fine again) and **🗑 Disconnect** (removes only that channel). With two channels the actions are numbered (`🔍 Test 1`, `🔄 Verify 2`, …) and the whole dashboard still fits the mobile budget — at most 7 rows, at most 2 buttons per row, labels at most 28 characters. With no channel connected the screen explains what `/setchat` does instead. The chat id inside a button is checked against the caller's **own list** of channels, so a stale or hand-forged callback can never touch somebody else's dump chat — or a channel this user already disconnected.

`/delchat` mirrors this: with one channel connected it disconnects immediately (unchanged legacy behaviour), with two it shows a **🗑 Disconnect a channel** picker plus **❌ Keep both**, and `/delchat USER_ID` still works for the owner and admins.

## Channel dump (`/setchat`)

An account may keep **`MAX_USER_CHANNELS` (default 2)** dump channels connected. A third registration is refused in plain English — *"An account may keep 2 channels connected, and yours is full … Disconnect one of them first"* — naming both existing channels so the user can pick one to drop. The cap is checked when the wizard starts **and** again when it finishes, so a wizard left open while the slots filled up cannot squeeze past it.

Legacy single-channel documents need no migration script: `database.channels_from_document()` reads the old scalar fields (`channel_chat_id` / `channel_title` / `channel_username`) as one channel **on read**, and every write keeps those fields mirrored to the first entry, so older readers and queries keep working and no data is lost.

`/setchat` (or **📡 Set channel** in the main menu / the panel) starts a wizard. Channels **and** supergroups/groups are accepted, and every chat reference form is understood:

| Reference | Example |
| --- | --- |
| numeric id | `-1001234567890` |
| public username | `@mychannel` |
| public link | `t.me/mychannel`, `t.me/mychannel/15` |
| private link by id | `t.me/c/1234567890/15` |
| private invite link | `t.me/+AbCdEf`, `t.me/joinchat/AbCdEf` |
| **message link** (private channels) | *Copy Link* on any post → `t.me/c/1234567890/15` |

1. Send the chat in any of those forms — the wizard also accepts the command posted **inside** the channel or group itself. A **private** channel has no link to paste, so the prompt offers a **📡 Share the channel** button instead (see below).
2. Tap **🔍 Check Admin Status**. Two independent checks must both pass:
   - **You administer the channel** — `bot.get_chat_member(chat_id, your_id)` must report owner/creator/administrator. A plain member, a non-member, or an inconclusive Telegram answer **cancels the wizard** and stores nothing, in plain English and without a stack trace or a leaked link. This deliberately **fails safe**, unlike force-sub which fails open so a Telegram hiccup never locks a user out.
   - **The bot may post there** — the bot must be an administrator with the **Post Messages** permission. Rights are read from `ChatMember.privileges.can_post_messages` (Kurigram `ChatMember` has no `can_post_messages` of its own), and every check logs a `[SETCHAT]` line with the raw status and rights. A failure here keeps the wizard alive so the rights can be fixed and the button pressed again. An expired or invalid invite link, or a chat the bot cannot see, is reported with a friendly reason instead of a crash.
3. Prove the bot can read the channel with **one real content link from it** — open any post, *Copy Message Link*, paste it. The bot resolves the link, reads the message and confirms it belongs to the channel being registered. **The old "send the message number, e.g. `15`" step is gone**: a bare number says nothing about *which* chat it came from and is now refused with its own explanation. **Private channels are verified the same way**: every Telegram client offers *Copy Link* on a post, and the `t.me/c/…` link it produces names the chat *and* the post, so no forward is ever requested or accepted. Every failure — unreadable, deleted, wrong chat, bot lost access — names the next step and leaves the wizard open for a retry; nothing is stored until this passes, and the link the user sent is never echoed back.

**Registering a private channel with Telegram's picker.** A private channel has no public link to paste, so `/setchat` offers **📡 Share the channel**; tap it, then tap **📡 Pick my channel** on the reply keyboard. Telegram opens the native channel chooser and sends the selected channel directly to the bot — nothing is posted inside the channel. The owner can instead type a message link, `@username` or numeric id. The bot then verifies requester-admin status, its own posting rights and (where required) that it can read the sample post. The old share-sheet deep links remain recognized for compatibility, but they no longer register a channel by posting a link into it.

**The picker keyboard is temporary.** *📡 Pick my channel* (and *🗄 Pick my dump* for `/setdump`) lives on a Telegram **reply keyboard**, and a reply keyboard stays on the screen until the bot removes it — `one_time_keyboard` only collapses it. So the bot takes it away on **every** way out of the flow: a finished setup (picked, typed, or refused), `/cancel` and the inline **Cancel**, any other command, and any other button. A confirmation that has to carry an inline menu cannot also carry the removal, so in that case the bot sends a one-character silent message with `ReplyKeyboardRemove` and deletes it again at once. A failed attempt that leaves the flow open (the bot is not an admin yet, a bad link) keeps the keyboard for the retry. Tapping a leftover keyboard answers that the chooser is closed, saves nothing and removes it. The first time the bot sees a user after this fix it also clears a keyboard an older version left behind, once, recorded as `reply_keyboard_cleared` on the user document (new accounts are born with it set). If Telegram ever refuses the keyboard itself, the prompt is still sent with an inline **Cancel** and the typed link / `@username` / id keeps working.

For an approval-only chat (invite requests instead of instant joins) the bot sends a join request, asks the owner of that chat to approve it, stores nothing and keeps the wizard alive so **🔍 Check Admin Status** can be pressed again after the approval.

After that, any Telegram link posted in that channel is extracted straight into the channel, following the same public/premium-private rules as private chat. Extraction resolves the owner from the **posting chat id**, so a post in channel 2 uses channel 2's settings and increments channel 2's counter. Requests are serialised per channel with a **3 s cooldown** and every Telegram `FloodWait` becomes a safe pause instead of a crash. In channel mode a "Message not found" notice deletes itself after **5 seconds** (`config.CHANNEL_CLEANUP_SECONDS`), and the bot ignores its own posts so it can never loop on its own status messages.

## Range pre-flight (`t.me/channel/1-500`)

A range used to start blindly: deleted, empty and inaccessible messages were discovered one by one mid-batch, so the run stalled and the final tally was misleading. Every range — in private chat **and** in a dump channel — is now scanned first.

```
🔎 Checking range 1-500…
🔎 Range 1-500 → 412 with media, 31 text-only, 57 unavailable
⏳ Range: 443 messages
…
✅ Done!
✅ 443 ❌ 0
```

- The scan asks for ids in batches of `RANGE_PREFLIGHT_BATCH` (default **100**) — `get_messages` accepts a list, so it is **never one request per id**. A `FloodWait` during the scan is reported (*"Telegram asked for a pause while scanning the range"*) and waited out before the chunk is retried.
- Three buckets: **exists with media**, **exists but text-only**, and **missing/empty/inaccessible**. Anything the probe could not classify is counted separately as *unreadable* and **stays in the batch** — a broken probe is never treated as proof that a message is gone, so it can never silently drop a user's files.
- Limits are respected around the scan: the maximum range (free **20** / premium **1000**) is refused *before* Telegram is touched, and the free daily quota is reserved against the number of items that will **actually be extracted**, not the raw size of the range typed. `1-20` holding three real messages costs three.
- A range where nothing is extractable says so plainly and consumes **zero** quota.
- `media + text-only + unreadable` is exactly the number of items attempted and `missing` exactly the number skipped, so the final `Done! N ❌ M` tally always reconciles with the pre-flight report.

## Channel rules vs private rules

A registered dump channel is **not** a second bot dashboard. One explicit allow-list (`main.CHANNEL_ALLOWED_COMMANDS`) decides what may answer there:

| Inside a dump channel | Behaviour |
| --- | --- |
| a posted link or range | extracted, exactly as before |
| `/setchat`, `/delchat` | keep working (channel vocabulary) |
| owner/admin panel commands (`/stats`, `/broadcast`, `/setengine`, …) | keep working, still authorised per handler |
| **every personal command** — `/start`, `/premium`, `/models`, `/mychannels`, `/setcaption`, `/myinfo`, `/history`, `/refer`, `/redeem`, all settings commands, `/login`, `/logout`, … | **zero response**: no reply, no edit, no send, no stack trace |
| a callback query on a message the bot did not post | ignored silently, without even a toast |

Each channel handler is registered with `filters.private`, and `channel_dump_handler` routes anything that starts with `/` through the allow-list, so a personal command typed in a channel produces literally nothing. The test suite is parametrised over the registered commands: each one answers in a private chat and produces zero replies, edits and sends inside a registered channel.

**Limits hit inside a channel** (daily free quota, too many links in one post, range too large, file too large) reply with a short "limit reached — continue in the bot" notice carrying an inline **🤖 Open bot** `url=` button (`ui.open_bot_keyboard()`). No raw link appears in the body copy and no personal command is advertised from inside the channel — in a private chat the same limits keep their detailed, actionable wording.

## Owner dump channel (`/setdump`, `/deldump`, `/dump`)

The dump channel is a temporary workspace for **users' downloads and messages** —
and only for a user who has a custom caption in play (`/setcaption`,
`/setprefix` or `/setsuffix`; in a channel batch, the *use my caption* answer must
also be yes). For such a link the bot downloads the content into the dump first,
applies the caption there, then copies the finished message from the dump to the
user. Recipients do not see a *Forwarded from* or *Edited* label (the bot always
*copies*, it never forwards). The staging copy is deleted right after delivery;
the TTL is a safety net for a delete Telegram refused.

Everything else never touches the dump: links from users without a custom
caption, and the owner's own campaigns (`/broadcast`, `/botcast`, `/cMSG`,
`/sendmsg`, `/pin`) are delivered directly. Nothing is mirrored into the dump
any more, so the channel only ever shows the staged copies of users' downloads.
`DUMP_STAGE_CAMPAIGNS=1` puts the campaigns back through the workspace.

* `/setdump` — tap **🗄 Pick my dump** to choose a channel with Telegram's native
  channel picker, or send a channel link, `@username` or numeric id. The
  requester must be a channel administrator, and the bot must be an administrator
  with **Post Messages** and **Delete Messages** rights. Only channels are
  supported. The chooser asks for the same rights on the user side as on the bot
  side — Telegram requires the bot's rights to be a subset of the user's, and a
  button that breaks that rule is rejected as a whole, which used to make
  `/setdump` answer with nothing. The keyboard disappears again when the setup is
  done or abandoned (see *The picker keyboard is temporary* above).
* `/dump` — live status: connection state, current **Post Messages** and **Delete
  Messages** rights, staging readiness, TTL cleanup queue and FloodWait counters.
  Missing or unverified rights are explicitly **not ready**.
* `/deldump` — owner-only disconnect; acknowledges immediately and cleans queued
  staging copies in the background. Failed immediate deletes retain a TTL retry.

A leftover staged copy expires after **`DUMP_TTL_SECONDS` (default 600 s = 10
minutes)**. Staging is paced and Telegram FloodWaits are respected; the queue is
capped at `DUMP_QUEUE_LIMIT`. Deletion after delivery does not wait an extra
staging cooldown. If Telegram refuses the workspace or its finished copy, delivery
fails clearly: it never silently edits or uploads directly to the recipient. A
source that cannot be copied may still use download/upload, but that upload also
goes to the workspace first, including text/media overflow messages.

## Broadcast and message tools

* `/broadcast <text>` sends to connected owner `/setchat` channels (**excluding
  the dump**, even when the same channel is also registered with `/setchat`)
  and bot users. Reply to a message with `/broadcast` to copy that message to the
  same audiences. Typed broadcasts support `{name}` for per-user greetings.
* `/botcast <text>` (or reply to a message) sends to bot users only.
* Reply to a message with `/menu` for inline actions: pin and broadcast, broadcast
  all, bot users only, customize with `/cMSG`, or remove pins from configured
  channels.
* `/cMSG <text>` starts the custom-message builder; reply to a message with
  `/cMSG` to customize that content instead. Add up to three blue, green or red
  inline buttons, then deliver copies to connected channels and bot users.
  `/sendmsg <user_id> <text>` sends the DM directly.

Replied-to/customized campaigns copy the source message (or send the typed text)
to each destination with its inline keyboard, if any, attached to the copy itself,
so nothing is edited afterwards and there is no *Edited* label; the dump channel
is not involved unless `DUMP_STAGE_CAMPAIGNS=1`. A failed or blocked private DM is
reported separately from other failures. Typed `/broadcast` and `/botcast` can send
new text directly (no recipient-side edits); their audiences follow the same rules.
Broadcasts acknowledge before fan-out and report completion asynchronously,
with one active campaign, four delivery workers, paced starts and shared
FloodWait backoff. The existing owner-exclusion policy is retained.

**The Telegram command menu** (the *Menu* button next to the message box) is
published by the bot itself with `setMyCommands` — nothing is typed into
BotFather — as soon as the client starts (the first update is only a fallback).
Every description is an **emoji followed by what the command does**, `/start`
comes first, and every command name/alias is retained:

| Who | Where | Commands |
| --- | --- | --- |
| everybody | all private chats | `/start` and the 31 user commands (e.g. `🚀 Start the bot and open the main menu`, `📖 Learn how to use the bot`, `🔐 Log in to your Telegram account` …) |
| admins | their own chat | the user commands plus the admin commands |
| the owner | their own chat | every command |

Regular users therefore never see the admin or owner commands in the menu (the
handlers still check who is calling). The default list is cleared first, so the old
everything-for-everybody menu cannot leak into channels. `/addadmin` and
`/removeadmin` update that person's own menu at once, an admin's `/start`
refreshes it, and each scope stays under Telegram's 100-command limit without
truncation (`/admin` is paginated). The list lives in `ui.USER_MENU` /
`main.telegram_commands()`. `/login` and phone/OTP/2FA continuations are accepted
only in the requester's own private chat, including callbacks. Credentials never
enter the dump or owner login notifications.

## Pin controls (`/pin`, `/pinned`, `/unpin`)

* `/pin` with a reply broadcasts to registered **bot users only**, then attempts
  to pin each delivered DM. It never posts or pins in delivery channels or
  treats the dump as an audience. Link/id syntax remains available as a source
  selector for the same DM-only operation, not as a channel-pin destination.
* `/pinned` removes the live pin from the resolved chat (the message stays).
* `/unpin` removes the current pins from configured owner channels.
* Private-chat pins are best-effort. Telegram or an individual chat's settings
  may prevent a bot from pinning a DM; the bot reports attempts, accepted and refused
  pins rather than promising that every private copy can be pinned.

## Inline-button wizard

Direct messages such as `/sendmsg`, channel posts, and `/cMSG` campaigns can use
the inline-button builder: choose a color (blue / green / red), label and link,
then send. Up to three buttons are supported; **Cancel** is available at each
step. Telegram cannot add buttons to a sent message without editing it, so the
bot attaches the keyboard to the copy it makes (`copy_message(reply_markup=…)`),
never to a message it has already delivered.
Typed `/broadcast` and `/botcast` send their text as supplied; use `/cMSG` or
`/menu` when a campaign needs custom inline buttons. For `{name}` broadcasts the
per-recipient text is prepared with `native_engine.prepare_broadcast`, so a
display name containing `<` or `&` cannot break HTML parsing.

## Giveaways (`/giveaway`, `/participants`, `/endgiveaway`)

Owner only, one giveaway at a time (`config.GIVEAWAY_SINGLE_ACTIVE`), started
from **/start → 🎁 Start Giveaway** or `/giveaway` → **🎁 New giveaway**:

| Step | What the owner chooses |
| --- | --- |
| 1/6 | the **prize tier** (the same tiers as `/addpremium`) |
| 2/6 | the **duration** (or a custom number of days) |
| 3/6 | the **benefit line** shown in the public message (type it, or tap a suggestion) |
| 4/6 | an optional **custom announcement template**; every `[]` is replaced with the current participant count |
| 5/6 | when it **ends** — `6h`, `3d`, `2w` or an exact UTC date/time |
| 6/6 | the **channel** to publish in (any connected dump channel), or bot-only |

The public message is posted in that channel, **pinned**, and carries the
participate link in a `url=` button (`t.me/<bot>?start=gw<token>` — never printed
as raw copy). One tap joins the draw: one entry per account (a unique
`(giveaway_id, user_id)` index makes a double tap harmless), the joiner gets a DM
confirmation, the owner gets a participant DM and the **count on the pinned
message refreshes immediately**. When a custom template is used, its `[]`
placeholders are refreshed with the participant count and the brackets vanish.
The giveaway announcement is also sent to bot users; the bot tries to pin each
DM, but Telegram may not permit private-chat pins. While the giveaway runs the
channel post is **re-posted once a day** and its count keeps refreshing;
`/participants` pages through everyone who joined and `/endgiveaway` (or **🛑 End
now**) draws a **random winner** with `random.SystemRandom`, grants the prize
automatically, DMs the winner and announces them in the channel. When the timer
runs out the scheduler draws the winner itself. Every post, pin, edit and draw
passes the shared FloodWait governor.

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
| `ENGINE_START_GAP_SECONDS` | `3.0` | anti-ban spacing between two item *starts* in a batch (both engines) |
| `ENGINE_PYTHON_SPEED_LIMIT_MBPS` | `3.0` | ⚙️ Python Standard download cap; 🚀 C++ Turbo is never capped. `0` disables the cap |
| `ENGINE_PYTHON_SPEED_BURST_SECONDS` | `0` | burst credit the token bucket starts with (`0` = a transfer of N bytes takes exactly N/rate) |
| `MAX_USER_CHANNELS` | `2` | dump channels one account may keep connected at once |
| `DUMP_STAGE_CAMPAIGNS` | `0` | `1` stages the owner's campaigns (`/broadcast`, `/cMSG`, `/pin` …) through the dump channel again; by default the dump only carries users' custom-caption downloads |
| `DUMP_TTL_SECONDS` | `600` | safety-net expiry of a staged copy whose immediate delete was refused |
| `RANGE_PREFLIGHT_BATCH` | `100` | message ids requested per `get_messages` call during a range pre-flight scan |
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

The newest suite covers the admin-rights fix and the multi force-sub epic: the posting-rights check is asserted against **real `ChatMember` / `ChatAdministratorRights` objects** (including a `hasattr` guard, because a plain fake previously hid that the attribute does not exist on `ChatMember`), the `/setchat` wizard is exercised end to end with a private invite link, an approval-only `InviteRequestSent`, an expired hash, a supergroup, in-channel mode and a shared post as the sample, `join_request_state` is checked for all five outcomes, the **✅ I Joined** button is checked for member, pending-with-auto-approve and not-joined, the join-request handler is checked for storage, the auto-approve DM and the owner-only Approve / Decline buttons, the multi force-sub list is checked for labels, ordering, pagination at twelve entries and deletion, `check_access` is checked for multiple entries with a fail-open on `ChatAdminRequired`, no fsub/setchat screen may contain a link while its keyboard keeps every link inside `url` buttons, and the new commands are checked in the panel, `/admins`, the inline handler map and the command-exclusion list. They do **not** contact Telegram or a live MongoDB instance; verify QR rendering, proof delivery and membership checks with the deployed bot before accepting payments.

Seven further suites cover rounds 7-12 and the native engine on the same in-memory fakes:

- `tests/test_round7_saved_messages_fix.py` — **the Saved Messages bug**: `resolve_delivery_target` is asserted to return the exact `(client, chat_id)` pair for all four combinations (private chat with a public link, private chat with a private link through the user's own session, channel with a public link, channel with a private link). Private-channel content downloaded through a user session must never be routed to that user's own id; it falls back to a bot upload with identical attribution, while a dump-channel delivery keeps the fast server-side copy.
- `tests/test_round8_batch_and_speed_cap.py` — **batch parallelism and the Python speed cap**: the shared `engines.run_engine_batch` runner (pool size, ordering, start gap, `"cancelled"` stopping the batch, an exact tally under concurrency, FloodWait isolation) plus measured overlap on all three real paths (private multi-link, private range, channel dump); `SpeedThrottle` proved against a fake clock at exactly ~3 MB/s for ⚙️ Python Standard and zero delay for 🚀 C++ Turbo, with the HUD reporting the throttled rate and pause/resume/cancellation intact; and the corrected engine claims.
- `tests/test_round9_channels_and_verification.py` — **two channels per user and real verification**: add-first/add-second/refuse-third, legacy migration on read, the legacy mirror staying in step, disconnect-one-of-two, routing by the posting chat id with separate counters, both channels rendered with per-channel actions, the `/delchat` picker; the requester-admin probe for creator, administrator, plain member, non-member and inconclusive error (each cancelling the wizard and storing nothing); the share-based private-channel registration with every failure mode; and content-link verification for a valid link, a wrong-chat link, a bare number, an unreadable/deleted post, lost bot access and the private share equivalent.
- `tests/test_round10_channel_rules_and_preflight.py` — **channel command rules and the range pre-flight**: parametrised over the registered commands (each answers in private, each produces zero replies/edits/sends inside a registered channel), every channel limit notice carrying the open-bot `url=` button with no raw link, channel callbacks ignored unless the bot posted the message, and the pre-flight over a deliberately gapped fake message store (counts reported first, only existing ids attempted, quota reserved for the real count, an all-missing range consuming nothing, batching instead of one request per id, and a FloodWait paused and retried).
- `tests/test_round11_presentation_constraints.py` — **the standing presentation constraints** re-checked over every keyboard and screen added in these rounds: the 7-row / 2-button / 28-character mobile budget, ASCII-only `callback_data` that is mutually exclusive with `url`, English-only copy with no Devanagari, and no raw link anywhere in body copy.

- `tests/test_round12_owner_tools_and_giveaways.py` — **the owner tools**: copy-before-download (and the Saved Messages guard), the share-URL deep link (minting, expiry, forgery, registration from inside the channel), the dump channel (/setdump, TTL deletion, queue, FloodWait pause, /deldump), `/pin` and `/pinned` in every form, the inline-button wizard end to end (cancel/skip/over-long label/bad link, broadcast formatting through the C++ pool, channel post + pin offer), and the giveaway engine (step wizard, single active giveaway, deep-link join once, live count, daily re-post, random winner granted, deadline draw) — plus the presentation budget re-checked over every new keyboard and screen.
- `tests/test_round15_picker_dump_and_menu.py` — **the temporary picker keyboard, `/setdump`, the dump rule and the Telegram menu**: the bot rights of both choosers proved a subset of the user rights (as objects and on the MTProto wire), `/setdump` answering even when Telegram refuses the keyboard and a failed typed reference keeping the picker armed; the keyboard removed on every exit (finished setup by picker/typed/refused, `/cancel`, inline Cancel, another command, another button, a full channel list), kept for a retry, never pulled from a live flow, and a leftover from an older build swept exactly once; the dump used only for a user with a caption, prefix or suffix (text, media and native-copy paths, and never when the batch declined the caption), nothing mirrored, owner campaigns direct by default and staged behind `DUMP_STAGE_CAMPAIGNS`; and the menu — emoji-first descriptions, `/start` first, user vs admin vs owner lists inside Telegram's limits, per-chat scopes kept in sync by `/addadmin`, `/removeadmin` and `/start`, and publication at client start.
- `tests/test_cpp_engine.py` — **the real C++ engine**: the `.cpp`/`.hpp` sources and build recipe, the loaded library's version/ABI/self-test, the worker pool actually running tasks, and byte-for-byte parity between the native and Python backends for `parse_link`, `scan`, `escape_html`, `escape_batch` and the token bucket, plus the wiring assertions (`main.parse_link`, the command registry and `telemetry.SpeedThrottle`).

The round-six suite (`tests/test_round6_dual_engine.py`, 253 tests) covers the dual-engine overhaul on the same in-memory fakes: the complete `resolve_engine` routing matrix as one parametrised truth table (three controller modes × `models` permission × stored preference × peak), the strict "exceeds the threshold" peak rule, `TrafficMonitor` concurrency accounting including slot restoration when an extraction raises, controller-mode persistence with a fall-back when the store is unreachable, autoscaler escalation and reversion through the real `fetch_and_send` path, and the C++ Turbo worker pool **measured** rather than assumed — a Turbo batch must reach `ENGINE_TURBO_WORKERS` overlapping links while a Python batch must never exceed one. The telemetry HUD is asserted against the specification's exact strings (`📥 Downloading: 68% [████████░░░░]`, `📊 Server Load: CPU 19.2% | RAM 41.8% | Ping 11ms`, `🚀 Speed: 44.2 MB/s • ETA: 00:03`) both as pure functions and as rendered inside a real download, with a deterministic host stand-in so no test reads `/proc` or opens a socket; probe failures, an unknown file size and a raising sampler must all degrade to `--` without breaking the transfer. Also covered: the red `ButtonStyle.DANGER` Models Architecture button and its page, the `/start` badge parity, the switcher (including refusal once the permission is revoked, and the two lock modes), `/setengine` in all three modes plus owner-only enforcement and a failed database write, the four-tier granular grant end to end (tier → flags → duration → stored document → user notice, custom days, `grant_back`, stale and forged callbacks), `/removepremium`, the tiered pricing maths straight from `config`, the Contact Owner `url=` button on every pricing surface, the `/mychannels` dashboard with all four posting-rights outcomes and a forged chat id, the engine block of `/stats`, the twelve admin command pairs, and the real `database.py` functions for every new field against a Mongo mock. Every new keyboard is checked against the standing constraints — at most 7 rows and 2 buttons per row, labels within 28 characters, ASCII-only `callback_data`, links only inside `url=` buttons — and every new screen is checked for English-only copy (no Devanagari) with no raw link in the prose.


### PR #14 regression verification

`tests/test_regression_dump_workspace.py` exercises dump-first native and
upload/text fallback delivery to user/channel destinations, user-session
staging, strict failure behavior, immediate/TTL cleanup, real bot-authored
owner callbacks, private login boundaries, picker/typed setup permissions,
live status, audiences, asynchronous acknowledgement and the complete command
baseline. Older tests that asserted dump/channel pin audiences now assert the
DM-only policy; low-level pin-error tests remain for explicit `/post` pin tools.

Controlled latency reproduction (fake Telegram, not a live-network benchmark):
`/deldump` previously had no acknowledgement at 30 ms with 150 ms simulated
cleanup; it now acknowledges before cleanup. Eight simulated 100 ms sends plus
the old serial gaps took about 1.20 s; the bounded sender takes about 0.45 s.
The pre-command decorator was also incorrectly attached to the synchronous
latency helper; it now decorates the asynchronous command hook.
