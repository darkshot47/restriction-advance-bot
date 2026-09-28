# Restriction Advance Bot

A Telegram bot for saving messages from public channels and, for owner-granted manual premium, private/restricted links. It runs on Kurigram (Pyrogram-compatible API) and stores state in MongoDB.

## Access plans

| Plan | Daily extractions | Channels | Watermark |
| --- | ---: | --- | --- |
| Free | 3 | Public only | Yes, appended below the original caption |
| Points premium | Unlimited | Public only | No |
| Owner-granted manual premium | Unlimited | Public and private/restricted | No |

Referrals award **10 points** per new user. Redeem at **100 points** for **30 days** of points premium. Points premium does not enable private links; those are available only when the owner grants premium manually.

## Premium purchase

Available prices are **₹99 / 1 month**, **₹249 / 3 months**, and **₹700 / 1 year**. The owner can upload a payment QR with `/addqr` and remove it with `/delqr` or `/removeqr`. Users choose a plan under `/premium`, pay, then send a photo or text proof. Payment proofs are recorded for `/payments` and forwarded to the owner/payment contact **@XyrDeveloper**. A missing QR prompts users to contact the owner.

## Admin

`/admin` opens an inline command panel. Admin commands include user/statistics management, broadcast and messaging, bans, premium, force-subscription, maintenance, payments, QR management, logs, export, and admin management. The owner configures the force-subscription channel with `/setfsub` and removes it with `/delfsub`.

## Setup

Set `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`, `BOT_USERNAME`, and `MONGO_URL`. Install runtime requirements with `pip install -r requirements.txt`; install development requirements with `pip install -r requirements-dev.txt`. For externally managed Python installations, use a virtual environment.

## Tests

Run `python -m pytest -q` from the repository root. The suite includes the original round-one compatibility coverage plus round-two reward/access checks.
