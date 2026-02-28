# PenipuMY Bot

Open-source Telegram bot for detecting and reporting scam phone numbers, bank accounts, and social media profiles in Malaysia.

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-20.7-26A5E4?logo=telegram&logoColor=white)](https://github.com/python-telegram-bot/python-telegram-bot)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Features

### Search & Lookup
- **Multi-source search** — phone numbers, bank accounts, names, and social media URLs
- **SemakMule integration** — cross-reference against Malaysian police scam database
- **Truecaller integration** — reverse phone lookup with name, carrier, and spam detection
- **Social Media ID Tracker** — resolve usernames to permanent platform IDs (Instagram, TikTok, Telegram, Facebook, Twitter/X, Threads)
- **Username change detection** — automatically detects when a scammer changes their social media username
- **QR code scanning** — extract and look up phone numbers from DuitNow QR codes
- **Per-user rate limiting** — configurable limits on API lookups to prevent abuse

### Reporting System
- **Guided report submission** — step-by-step wizard for submitting scam reports
- **Evidence upload** — attach up to 10 screenshots per report
- **Multiple identifier types** — report phone numbers, bank accounts, or social media profiles
- **Report updates** — reporters can provide additional information via deep links when requested by admin

### Admin Review
- **In-bot admin panel** — review, verify, or dispute reports directly in Telegram
- **Needs Info flow** — request additional information from reporters with optional reason
- **Profile linking** — link verified reports to scammer profiles for aggregation
- **Notification system** — automatic Telegram notifications to reporters on status changes (verified, disputed, needs info, auto-archived)

### Automation
- **Auto-archive** — reports in "Needs Info" status for 30+ days are automatically rejected
- **Truecaller caching** — results stored locally to reduce redundant API calls
- **Activity tracking** — user registration and last-active timestamps

---

## Quick Start

### Prerequisites

- Python 3.8+
- Telegram Bot Token from [@BotFather](https://t.me/botfather)
- Playwright Chromium (for statistics image rendering, optional)

### Installation

```bash
# Clone the repository
git clone https://github.com/affifuddin-hazam/PenipuMY.git
cd PenipuMY

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your values (see Configuration below)

# Run the bot
python main.py
```

The database is created automatically on first run.

---

## Configuration

### Required Environment Variables

```env
# Telegram Bot (get from @BotFather)
BOT_TOKEN=your_telegram_bot_token

# Admin access (comma-separated Telegram user IDs)
ADMIN_USER_IDS=123456789
```

### Optional Environment Variables

```env
# Require users to join a channel before using the bot
REQUIRED_CHANNEL_ID=@YourChannel
REQUIRED_CHANNEL_URL=https://t.me/YourChannel
```

### Demo API Flags

The bot ships with **dummy API modules** that return configurable demo data. This allows the bot to run without real API credentials. Set these flags to control the dummy behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_SEMAKMULE_POLICE_REPORTS` | `0` | Number of police reports returned. Set `0` for clean, `1`+ for flagged. |
| `DEMO_TRUECALLER_FOUND` | `true` | Set `true` to return a demo name, `false` for "no record found". |
| `DEMO_SOCIAL_TRACKER_FOUND` | `true` | Set `true` to return a resolved profile, `false` for "not found". |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Toggle rate limiting on/off. |
| `RATE_LIMIT_MAX` | `2` | Maximum lookups per window per user. |
| `RATE_LIMIT_WINDOW_HOURS` | `5` | Rate limit window duration in hours. |

Rate limiting only counts successful live API lookups. Cache hits, skipped lookups, and failed requests are not counted.

---

## Project Structure

```
PenipuMY-Bot/
├── main.py                 # Entry point — handler registration, JobQueue setup
├── config.py               # Environment variables, state constants, demo flags
├── database.py             # SQLite schema, migrations, connection helper
├── bot_utils.py            # Shared utilities — safe message editing, notifications
│
├── handlers_general.py     # /start, statistics, cancel, auto-archive job
├── handlers_search.py      # Search flow — phone, bank, social, QR code
├── handlers_report.py      # Report submission wizard
├── handlers_admin.py       # Admin review panel — verify, dispute, needs info
├── handlers_update.py      # Reporter update flow (deep link entry)
│
├── truecaller_api.py       # Truecaller API (dummy — returns demo data)
├── truecaller_db.py        # Truecaller result caching (SQLite)
├── semakmule_apiv2.py      # SemakMule PDRM API (dummy — returns demo data)
├── social_tracker.py       # Social media URL parser + ID tracker (dummy lookups)
├── rate_limit.py           # Per-user rate limiting (in-memory)
│
├── image_generator.py      # Profile card image generation (Jinja2 + Playwright)
├── qr_utils.py             # QR code scanning utilities
├── duitnow_parser.py       # DuitNow QR payload parser
│
├── templates/              # HTML templates for card generation
├── static/                 # Static assets (fonts, images)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
└── LICENSE                 # MIT License
```

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu — search, report, statistics, admin panel |

All interactions are button-driven via inline keyboards. The bot uses conversation handlers with the following flows:

- **Search** — enter a phone number, bank account, name, social URL, or send a QR code image
- **Report** — guided wizard: title, description, identifier type, amount, screenshots, confirmation
- **Admin** — review queue: verify (link to profile), dispute, request more info, skip
- **Update** — deep link (`/start update_<id>`) for reporters to respond to "Needs Info" requests

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Push and open a Pull Request

---

## Disclaimer

- This bot is provided for **educational and community safety purposes**
- Information is crowd-sourced and may not be 100% accurate — always verify through official channels
- The dummy API modules return simulated data; connect real APIs for production use
- User data is stored locally in SQLite — no data is shared with third parties
- The developers are not liable for any misuse of this software

### If You've Been Scammed

1. **Police Report** — [SemakMule](https://semakmule.rmp.gov.my/)
2. **Contact your bank** immediately to freeze transactions
3. **MCMC** — [Malaysian Communications and Multimedia Commission](https://aduan.skmm.gov.my/)
4. **National Scam Response Centre** — call **997**

---

## License

[MIT License](LICENSE) - Copyright (c) 2025 PenipuMY
