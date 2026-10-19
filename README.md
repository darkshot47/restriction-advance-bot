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
| everybody | all private chats | `/start` and the 33 user commands (e.g. `🚀 Start the bot and open the main menu`, `📖 Learn how to use the bot`, `📲 Download the Vmore app`, `🔐 Log in to your Telegram account` …) |
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

## Vmore — the standalone Android app

**Vmore** is the phone app that does the heavy work itself.  It signs in with the user's *own* Telegram
account, downloads a link's media **Telegram → phone** and uploads it **phone → Telegram**, so the host
never moves a byte.  There is no server address, no access token and no app API: everything runs on the
phone through TDLib, and the app is built by GitHub Actions from `android/` and published as a Release
APK.

### The user's flow

1. **Install** — download `Vmore.apk` from the stable Release link (or unzip `Vmore-apk.zip`) and allow
   "Install unknown apps" once.
2. **Sign in** — either paste the `api_id` and `api_hash` of your own Telegram application
   (my.telegram.org), or tap **Try a ready-made key**: Vmore walks the keys that open-source Telegram
   clients publish, gives each one up to sixty seconds, and stops the moment the login code is on its
   way.  A key Telegram refuses is left behind at once and the next one goes; the whole attempt ends
   with the screen back in your hands, one tap from your own pair.  Every step after the keys has a way
   back (Change the API details), the number is remembered and filled in next time, and the code screen
   offers **Send the code again**.  A refusal lands on the step it belongs to: a wrong code or a wrong
   two-step password never throws you back to `api_id`, Continue keeps working under the error, and a
   request that is never answered gives the screen back after forty-five seconds instead of waiting
   forever.  Then the code Telegram sends you, and the two-step password if the
   account has one.  Telegram refuses a published key with `API_ID_PUBLISHED_FLOOD` more often than not,
   which is exactly what the own-pair option is for.
3. **Paste a link** — one link or a whole batch, public (`t.me/channel/123`), private
   (`t.me/c/…`) or a range (`t.me/channel/1-500`, one job per message, up to 500 per link).  A chat can
   also be scanned: Vmore takes the channel's recent media and queues it.
4. **Pick the destination** — the chat list opens once; the choice is remembered as the default and can
   be changed per job.
5. **Start** — the queue resolves, downloads and uploads each job with the user's own session.  With
   **Delete the local copy** on (the default) the phone copy is removed right after a successful
   upload, the record stays in History, and the next job keeps going — bulk batches included.
6. **Runs in the background** — a real foreground service (`dataSync`) keeps a long batch alive with the
   app closed, with Pause all / Resume all / stop in the notification.
7. **While it works** — Home shows live progress (stage, percent, speed, ETA) and, when a job stops,
   Telegram's own reason in plain words; Queue shows every job with pause, retry, remove and open;
   History keeps every upload, download and failure.  A job that only hit a flood wait or a dropped
   connection is retried up to three times before it is called failed.

### Watching, editing and quality

* **Viewer** — video and audio playback with a 0.25x … 3x speed control (the last choice is remembered),
  seek bar, fullscreen, image zoom, text preview, and Save to device / Share / Open with another app.
* **Editor** — caption (with the file name template), a cover image picked from the gallery, an instant
  MP4 trim that runs on the phone (`MediaExtractor` + `MediaMuxer`, no re-encode), the destination chat
  and an **upload quality** choice: `File` keeps the original bytes, `Video` prepares an inline-playing
  video, `Photo` sends a fast preview.
* **Forward without download** — a job can be forwarded with TDLib, so zero bytes cross the phone.

### Getting the app from the bot

The app is one tap away from every menu, and it asks nothing on the way:

* **/start** ends with a full-width **📱 Vmore App** button, **/help** carries the same button, and the
  private-link pitch adds **♾️ Unlimited Download (App)** under the premium row — every one of them opens
  the app page or sends the file, never a form to fill in.
* **/app** (or the button) opens the app page: **📩 Send APK in chat**, **❓ How to use?** (install, sign in
  with the phone number and the code, and the optional `api_id`/`api_hash` from my.telegram.org), the
  **Owner** contact and Home. The app flow does not expose an external download URL or a GitHub link.
* **/apk** sends the APK the owner published straight into the chat as a document, with its version beside it.
  The owner running `/apk` **with an `.apk` document** — or replying `/apk` to one — stores that file as the
  build everybody receives and answers **✅ APK CONNECTED**; the version is read from the file name
  (`Vmore-2.2.12.apk` → `2.2.12`), and nothing else is asked for.
* With no APK published yet (or if sending fails), the bot explains that the file is unavailable and asks the
  owner to publish it. It never falls back to a direct download link.

No screen in this flow mentions a server URL, a `/gentoken`-style wizard or an access token — there is
nothing of the kind to enter, because the app has no server.  Both commands are registered in the user
menu (*Open the Vmore App page* / *Download the Vmore app*) and in the admin panel under
**🎁 Owner Tools** (`/app — Vmore App Page`, `/apk — Send or Publish the APK`).

### Everything the app does

The list below is the whole feature set, all of it on the phone, none of it needing a server.

1. **Files** — a Library screen for everything Vmore left on the phone: search, sort by date, name or
   size, multi-select, upload the selection again, share it, or delete it with a confirmation.
2. **Data saving** — *only on Wi-Fi* and *only while charging* hold the queue and release it by
   themselves the moment the phone is back on Wi-Fi or on the charger; a speed limit caps the transfer
   rate (full, 4, 2, 1 or half a megabyte a second).
3. **Scheduled queue** — pick a time (Settings → Schedule) and the queue starts by itself, once or every
   day; while it waits the notification says so, and *Start now* ignores the wait.
4. **Battery** — Settings shows whether Android is free to let the queue run in the background, with one
   tap into the system's battery-optimization screen.
5. **Duplicate skip** — a file that was uploaded before (`file id` + size) is left out instead of being
   sent twice, and the job says so in the finish summary.
6. **Batch filters** — before a batch starts, keep only the kinds you want (`video`, `photo`, `audio`,
   `document`) and only a size range; everything else is skipped with a note, so a 500-message range does
   not drag 500 files through the phone.
7. **Share to Vmore and the clipboard banner** — *Share → Vmore* from any app sends the text straight to
   the link box, and a Telegram link already on the clipboard offers itself with one tap.
8. **Per-batch rules** — the kind, the filter and *skip duplicates* chosen on Home travel with the batch
   and are shown per job in the queue, while Queue and Editor can override the destination per job.
9. **Retry all and priority** — *Retry all failed* puts every failed job back at once (Wake up clears the
   waits), and the arrows on a waiting job move it up or down the queue.
10. **Statistics** — a dashboard with uploads, downloads, failures, bytes sent and received, the space
    the cleanup gave back, what is still on the phone, the average file, the queue size, the last
    activity, a seven-day chart and the busiest chats.
11. **Automatic skin** — Settings → Appearance: *Day* (the default), *Night*, or *Automatic*, which
    follows the clock (night between 18:00 and 06:00).  The header button flips between day and night in
    one tap.
12. **PIN lock** — a four to eight digit PIN (Settings → Privacy) guards the app after it has been left
    alone for a while; a wrong PIN shakes, and a forgotten PIN signs the account out.
13. **Player upgrade** — playback speed from 0.25x to 3x, *Play the next file by itself* so a folder of
    downloads runs as one long queue, picture-in-picture, fullscreen, rotate, screen-on while playing.
14. **Editor upgrade** — trim, caption, cover taken from the gallery **or from a frame of the video
    itself**, *Remove sound*, *Sound only* (the audio track saved as `.m4a`), and the upload quality
    (`File` / `Video` / `Photo`) for this upload only.
15. **Three accounts** — Settings holds up to three Telegram accounts, each with its own session folder,
    its own profile picture and its own credentials; *Switch* goes through the sign-in screen so Telegram
    is never left in a half state, and the queue, history and files stay.  Tapping *Switch* by accident is
    no longer a one-way door: the sign-in screen always carries a **Back to <account>** button whenever
    another slot holds a signed-in account, on every step and under every error, and a reset gets a fresh
    session folder of its own so a closing session can never break the next sign-in.
16. **Home-screen widget and Quick Settings tile** — the widget shows the job, the stage and the queue
    size with pause/resume and open; the Quick Settings tile does the same from the panel.
17. **Delete the downloaded files only** — Settings → Downloaded data shows how much is on the phone
    and **Delete downloaded files** removes those files in one go, after one confirmation.  Nothing else
    is touched: the history stays (each record simply stops offering a file that is gone), and the
    queue, every setting and the Telegram account stay signed in.  A file a waiting or running job
    still needs is left alone, so a batch is never broken by the cleanup.

### When something goes wrong

* **A job retries four times**, and every retry asks Telegram for the message again — a file reference
  from a failed attempt has usually gone stale, and retrying with the stale one is what used to turn one
  hiccup into "download failed" on the first try.  Each attempt also re-requests a download that has
  stopped moving (45 seconds without a byte, twice), and Telegram resumes from the part it already sent,
  so nothing is downloaded twice.
* **A chat that protects its content still moves.**  Telegram forbids forwarding and saving there, but it
  still lets a signed-in client download the file to show it, which is what every official client does.
  So the download is always attempted; and when a *forward* is refused with "protected content", the queue
  does not fail the job — it downloads the file and sends a copy to the destination instead, exactly like
  the bot did.  The queue says in the log which route it took.
* **The upload of protected content is a real upload.**  Telegram refuses a message that *points at* a
  protected file (`CHAT_FORWARDS_RESTRICTED`), which is what kept failing after the file had downloaded:
  TDLib recognised the saved file by its path and offered the old reference again.  The upload is now
  built from a second name for the same file — a hard link where the phone can make one, a copy where it
  cannot — so TDLib uploads the bytes as a brand-new file.  The link costs no storage, it is removed when
  the upload ends, and if Telegram still refuses, the send happens once more this way before anything is
  called failed.
* **Only real dead ends stop early**: a chat this account may not read, an empty destination, no room on
  the phone, a message that is gone.  The queue names the reason it hit — and checks the free space before
  the transfer, so "no room" is not discovered half way through.
* **The log**: Settings → Check the Telegram connection lists the session, the destination, the failed
  jobs and the *last steps the queue took*, with Telegram's own error text.  One tap copies the whole
  report, which is what to send when a link will not move.

### The developer card, the ring and the buttons

* **Settings ends with the developer's own profile**, read through the signed-in account: the real name,
  the real handle, the real bio and the real profile picture, cached on the phone so the card paints
  instantly, refreshed once per visit, and one tap from a **direct chat** (`tg://resolve`, the web
  fallback when Telegram is not installed).  Nothing about it is baked into the APK.
* **That one card is alive.**  It is the single place the owner allowed colour, and it uses it: five soft
  clouds of colour (blue, violet, cyan, rose and a little amber) drift on their own paths behind the
  text, a band of light crosses the card, small dots rise, and the picture sits inside a multicolour
  ring that keeps turning.  A dark wash keeps the white name, bio and button the first thing read, and
  the animation stops with the screen instead of running in the background.
* **The story ring**: the logo on the sign-in screen, the profile picture in the home header and the
  developer's picture at the end of Settings all sit inside the circle Telegram draws around a profile
  with a story.  The arc travels around the logo without ever stopping; on the header it turns slowly
  enough that it is noticed only when looked at.  On the developer card the ring is a multicolour
  gradient turning once every seven seconds.  Every ring stops by itself when the screen leaves the
  window.
* **Buttons**: one radius (16dp), one weight, one letter spacing and a real ripple under the finger for
  the solid blue button, the outline button and every filter chip — so a screen with both reads as one
  design.
* **The sign-in steps breathe**: every button on the login card carries its own 13dp gap, so *Continue*,
  *Open my.telegram.org*, *Continue with a built-in key* and *Change the API details* are four separate
  steps instead of one stacked block.
* **Home options are Settings rows**: *Upload after download*, *Delete local copy* and *Forward without
  download* are full-width rows with a tinted switch on the right and a hairline divider between them, and
  *Quality*, *Filters* and *Schedule* are icon rows that show the value in force — a value that is doing
  something sits on the blue pill in white, so nothing wraps into three cramped lines any more.
* **Signing in without typing a key**: Telegram will not send a login code to any client that has no
  `api_id`/`api_hash`; it is a server rule, not an app one.  Vmore therefore keeps the built-in key pool,
  but it is no longer random: the key that last produced a code on this phone is tried first, the others
  follow, and the user's own pair stays one tap away on the same screen.

### Updates and the signing key

Android only installs an APK over an existing app when both carry the **same signature**.  Every build up
to 2.2.1 was signed with Android's *debug* key, and a CI runner generates that keystore from scratch each
time — so every APK had a different signature and the phone answered "App not installed".  The fix:

* the distribution APK is a **release** build signed with one stable key, kept with its password under
  [`android/signing/`](android/signing/README.md) where both the build and the owner can always reach it;
* the certificate's SHA-256 is recorded in
  [`android/tools/expected_signing.txt`](android/tools/expected_signing.txt) and the workflow **fails** if
  the key, or the APK's signature, is not the recorded one — that is what stops a lost or swapped key from
  silently breaking every update;
* each release's notes carry the version, the version code and the signing fingerprint, and the same
  fingerprint can be read off the *installed* app (Settings → Check the Telegram connection), so an
  installed Vmore can be checked against the release it claims to be;
* if no keystore can be reached at all (a pull request from a fork, say), the build falls back to the debug
  key, says so loudly, and the release notes say the same.

Because the key used before this change was random, an already installed Vmore must be **uninstalled
once** before installing this build or newer.  From that build on, updates install over each other and the
data stays.

### On the phone, the first time

1. Allow "Install unknown apps" for the browser or file manager that opens the APK (Android asks once).
2. On Android 13 and newer, allow notifications when Vmore asks: the queue shows its progress there, and
   *Pause all* / *Resume all* live in that notification.
3. Settings shows whether Android may stop the queue in the background; one tap opens the system dialog
   that lifts the restriction.  Some phones (Xiaomi, Oppo, Vivo) also have their own "Autostart" switch —
   without it, a very long batch can be cut short when the screen has been off for a while.
4. The link's own rules still apply: a private link needs the account to be able to read the message.  A
   chat that protects its content cannot be forwarded, so Vmore downloads the file and sends it as a copy;
   when Telegram asks Vmore to wait (flood wait), the job pauses itself, says so in the queue, and retries
   up to three times.

### Look and feel

* **Day and night skins** — the in-app switch (Settings → Appearance, or the sun/moon button in the
  Home header) repaints the whole app: day is white with black text, night is black with white text.
  The choice is remembered, the day skin is the default, and it wins over the phone's own dark-mode
  setting.  `values/colors.xml` is the day palette, `values-night/colors.xml` the night one, and both
  carry the same names, so every drawable flips with them.
* **The account corner** — after the sign-in the header shows the name, the `@username` and the profile
  picture of the account.  The picture is downloaded **once**, copied into the app's private storage and
  read from there afterwards, so reopening the app never asks Telegram for it again.
* **Connection check** — Settings → Check the Telegram connection lists the session, the destination
  chat and the last failed jobs with Telegram's own words, and copies the whole report in one tap.

White, blue and black only (every shade in `colors.xml` is one of the three, the greys are white over
black), no emoji anywhere, and every screen animates in (`res/anim/`, staggered lists on the home
screen).

### Bot side

The bot keeps its own features.  A private/restricted link offers the premium route for delivery in the DM
**and** the app for unlimited downloading on the phone, and the `/CreateBot` child-bot system stays
retired.

### Building the APK

`.github/workflows/android.yml` builds `android/` (Java, no third-party dependencies) on every push that
touches it, verifies the APK with `aapt2 dump badging`, packs it **into a zip** (the owner's
requirement), uploads the zip as an artifact and (re)creates the **`vmore-latest` GitHub Release** with
`Vmore.apk`, `Vmore-apk.zip` and `SHA256SUMS.txt`.  Nothing is baked into the build: no server address,
no credentials.  TDLib (`TdApi.java` + `libtdjni.so` for `arm64-v8a` and `armeabi-v7a`) is generated
deterministically from the single pinned commit in
[`android/tdlib/TDLIB_COMMIT`](android/tdlib/TDLIB_COMMIT) — see
[`android/tdlib/README.md`](android/tdlib/README.md) — cached across runs, and the workflow asserts both
native libraries really landed inside the APK.

Stable links:

```
https://github.com/darkshot47/restriction-advance-bot/releases/latest/download/Vmore.apk
https://github.com/darkshot47/restriction-advance-bot/releases/latest/download/Vmore-apk.zip
```

### Icons

`android/icons/*.svg` are the design sources; each has an exact VectorDrawable twin in
`android/app/src/main/res/drawable/ic_*.xml`, which is what the build ships.

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
- `tests/test_round19_app_page_and_apk.py` — **the Vmore App page and the APK hand-over**: the 📱 button closing `/start` and sitting in `/help`, `/app` and `cmd_app` rendering the same page, the ♾️ button on the private-link pitch, `/apk` publishing the owner's document (or replying to one) without asking for anything, users receiving exactly that file in chat, no external-link fallback when nothing is published or sending fails, and every app screen checked for a server URL, a token wizard or a raw link.
- The retired app API has no test left: `appapi.py`, `/api/v2` and their three test modules
  (`test_round16_vmore_app.py`, `test_round17_zero_transfer.py`, `test_round18_td_direct.py`) are gone
  with the server the app no longer needs.