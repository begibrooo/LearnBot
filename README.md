# 🎓 LearnBot — Telegram Learning Platform

A production-ready Telegram bot for building a learning platform with VIP content, promo codes, referrals, and admin management.

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Run
```bash
python main.py
```

---

## ⚙️ .env Configuration

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Your bot token from @BotFather |
| `ADMIN_IDS` | Comma-separated Telegram user IDs for admins |
| `CONTENT_CHANNEL_ID` | ID of private channel where content is stored |
| `REQUIRED_CHANNELS` | Channels users must join (comma-separated) |
| `INVITES_PER_FREE_PASS` | How many referrals = 1 free pass (default: 5) |
| `MAX_WRONG_ATTEMPTS` | Code attempts before lockout (default: 3) |
| `LOCKOUT_MINUTES` | Lockout duration in minutes (default: 15) |

---

## 📂 Project Structure

```
learnbot/
├── main.py                  # Entry point
├── config.py                # Settings (pydantic-settings)
├── requirements.txt
├── .env.example
├── database/
│   ├── db.py                # Schema + init
│   ├── users.py             # User CRUD
│   ├── content.py           # Categories, levels, lessons
│   ├── promos.py            # Promo codes
│   └── analytics.py        # Logs, channels, support
├── handlers/
│   ├── start.py             # /start + referral
│   ├── subscription.py      # Channel gate
│   ├── menu.py              # Main menu
│   ├── lessons.py           # Browse, unlock, open lessons
│   ├── profile.py           # User profile
│   ├── search.py            # Search + inline search
│   ├── promo.py             # Enter promo code
│   ├── referral.py          # Invite link + stats
│   ├── leaderboard.py       # Top inviters
│   ├── support.py           # Support tickets + admin reply
│   ├── admin_main.py        # Admin panel entry
│   ├── admin_content.py     # Manage categories/levels/lessons
│   ├── admin_promo.py       # Manage promo codes
│   ├── admin_users.py       # Manage users
│   └── admin_broadcast.py  # Broadcast + channel management
├── middlewares/
│   ├── auth.py              # Auto-register, ban check
│   └── throttle.py         # Rate limiting
├── keyboards/
│   ├── user.py              # User-facing keyboards
│   └── admin.py            # Admin keyboards
└── utils/
    └── helpers.py          # Sub check, content delivery, formatting
```

---

## 🛠 Admin Commands

| Command | Description |
|---------|-------------|
| `/admin` | Open admin panel |
| `/del_cat <id>` | Delete category |
| `/del_lvl <id>` | Delete level |
| `/del_les <id>` | Delete lesson |
| `/del_promo <id>` | Delete promo code |
| `/add_channel @handle` | Add required channel |
| `/remove_channel @handle` | Remove required channel |

---

## 📦 Deploy on Railway

1. Push to GitHub
2. Connect repo in Railway
3. Add env variables in Railway dashboard
4. Deploy — it runs `python main.py` automatically

---

## 🔑 Lesson Content Types

When adding a lesson, send:
- **Forwarded message** from private channel → stored as `forward` (message_id + channel_id)
- **Video/Photo/Document/Audio** → stored as `file_id`

The bot automatically detects the type and delivers correctly.

---

## 🎟 Promo Types

| Type | Effect |
|------|--------|
| `free_pass` | Grants N free passes to user |
| `lesson_unlock` | Unlocks a specific lesson |
| `file_reward` | Sends a file to the user |
