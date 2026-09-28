# restriction-advance-bot

Telegram bot that saves content from restricted/private channels with a user
account, plus a full set of admin tools.

## Features

- **Working inline menu** — every button on the `/start` screen runs its action
  directly (no more “send /login” hints):

  | Button | Action |
  | --- | --- |
  | 🔐 Login | starts the phone/OTP login flow (with ❌ Cancel login) |
  | 🚪 Logout | drops the stored session and shows the login button again |
  | ⚙️ Settings | notification / silent-mode toggles, language, reset |
  | 📊 Stats | your personal stats (downloads, referrals, join date) |
  | 💎 Premium | premium status or benefits + contact-owner button |
  | 🎁 Refer | referral link with 📤 Share and 📋 Copy buttons |
  | 📖 Help | help screen with quick actions |
  | 💬 Feedback | asks for your message, stores it and forwards it to the owner |
  | 🌐 Language | English / Hindi picker, current language is ticked |

- **Native Telegram button colours** — blue (`primary`), green (`success`) and
  red (`danger`) inline buttons, e.g. green 🔐 Login, red 🚪 Logout/⛔ Stop and
  blue navigation buttons. Buttons degrade to plain (transparent) style when the
  installed library cannot render colours; set `BUTTON_STYLES=off` to disable
  colours on purpose.
- Private-channel downloads through a saved MTProto user session, bulk links,
  message ranges, pause/resume/stop controls, custom captions, prefixes,
  suffixes and thumbnails.
- Admin tooling: stats, users, broadcast, ban/unban, premium management,
  force-subscribe channel, maintenance mode, feedback inbox, exports.

## Requirements

- Python 3.11+
- MongoDB (`MONGO_URL`)
- Telegram API credentials (`API_ID`, `API_HASH`) and a bot token (`BOT_TOKEN`)

The bot runs on **Kurigram**, the maintained pyrogram fork. It installs the
`pyrogram` module, which is what the code imports. When upgrading an existing
deployment from `pyrofork`, remove the old library first:

```bash
pip uninstall -y pyrofork
pip install -r requirements.txt
```

## Run

```bash
pip install -r requirements.txt
API_ID=123456 API_HASH=... BOT_TOKEN=... MONGO_URL=mongodb://... \
OWNER_ID=123456789 BOT_USERNAME=YourBot python main.py
```

A small Flask app answers on `$PORT` (default `8080`) so the bot also works on
hosts that expect an HTTP health check.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers the button-style helpers, the keyboard layout, every menu
button action (login/logout/settings/stats/premium/refer/help/feedback/language)
and the matching `/commands`. No network or database is used — MongoDB and the
Telegram client are replaced with in-memory fakes. CI (`.github/workflows/tests.yml`)
runs the same command on every push and pull request.
