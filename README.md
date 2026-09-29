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
- **Force Sub** (`/setfsub`, `/fsublist`, `/delfsub`, `/fsublabel`, `/fsubcheck`)
- Administration (admins, maintenance, logs, help)

Every command in the panel also appears in the `/admins` list, and every panel button runs the same handler as its slash command. Parameterized actions prompt for details with examples. Authorization is checked for callbacks as well as typed commands; **only the owner** can run `/addpremium`. Regular admins cannot gain private-access grant permission through inline prompts.

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

Tests cover command/button compatibility, checkout sequencing, proof metadata and delivery failures, cancellation, private-access restrictions, attribution, concurrency-safe quotas, calendar-month redemption and actual database functions against a Mongo mock. They also cover the round-three requirements: the small-caps engine and its protected regions (no rendered screen may leak plain ASCII copy outside links/commands), private-access and daily-limit screens with the dual button row, feedback link rejection, the `/addpremium` tier choice, the owner payment review actions, the `/setchat` wizard (admin check, sample verification, in-channel mode), channel-dump rate limiting/FloodWait handling and the five-second "Message not found" cleanup, every admin command being reachable from both `/admins` and the panel, and name/username re-sync so a rename shows up everywhere.

The newest suite covers the admin-rights fix and the multi force-sub epic: the posting-rights check is asserted against **real `ChatMember` / `ChatAdministratorRights` objects** (including a `hasattr` guard, because a plain fake previously hid that the attribute does not exist on `ChatMember`), the `/setchat` wizard is exercised end to end with a private invite link, an approval-only `InviteRequestSent`, an expired hash, a supergroup, in-channel mode and a bare message number as the sample, `join_request_state` is checked for all five outcomes, the **✅ I Joined** button is checked for member, pending-with-auto-approve and not-joined, the join-request handler is checked for storage, the auto-approve DM and the owner-only Approve / Decline buttons, the multi force-sub list is checked for labels, ordering, pagination at twelve entries and deletion, `check_access` is checked for multiple entries with a fail-open on `ChatAdminRequired`, no fsub/setchat screen may contain a link while its keyboard keeps every link inside `url` buttons, and the new commands are checked in the panel, `/admins`, the inline handler map and the command-exclusion list. They do **not** contact Telegram or a live MongoDB instance; verify QR rendering, proof delivery and membership checks with the deployed bot before accepting payments.
