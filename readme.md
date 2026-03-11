# <img src="https://i.imgur.com/JbCyPi9.png" width="50" alt="Dragon Bot"> Dragon Bot

> **A feature-rich Discord bot for dragon collecting, breeding, and adventure gameplay.**

---

## 📋 Overview

Dragon Bot is a comprehensive Discord bot that provides an immersive dragon-themed experience with features including dragon collecting, breeding, raids, trading, and much more. Players can manage their dragon collection, participate in quests and raids, breed dragons, and trade on the marketplace.

### 🔗 Add Dragon Bot to Your Server

[**Invite Dragon Bot to Discord**](https://top.gg/de/bot/1445803895862333592/invite)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🐲 **Dragon Collection** | Collect, manage, and customize your dragon collection |
| 🥚 **Dragon Breeding** | Breed dragons together to create new offspring |
| ⚔️ **Raids & Battles** | Participate in cooperative raids and dragon battles |
| 🏪 **Marketplace** | Trade dragons and items with other players |
| 🎒 **Adventure System** | Embark on quests and missions to earn rewards |
| 💰 **Economy** | Complete economy system with gold, items, and taxes |
| 🎯 **Dragonpass** | Pass-based progression system with exclusive rewards |
| 👥 **Social Features** | Chat, friend system, and community engagement |
| 🏆 **Events** | Limited-time events with special rewards |
| 📊 **Admin Panel** | Comprehensive admin tools for server management |

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Discord Bot Token

### Steps

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd dragonbot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   - Copy `.env.example` to `.env`
   - Fill in your Discord bot token and other required values:
   ```bash
   cp .env.example .env
   ```

4. **Run the bot:**
   ```bash
   python bot.py
   ```

---

## 📁 Project Structure

```
bot.py                # Main bot entry point
main.py               # Core bot initialization
config.py             # Configuration and constants
database.py           # Database operations and schemas
state.py              # Global state management
utils.py              # Utility functions
requirements.txt      # Python dependencies

cogs/                 # Command modules
  ├── admin.py        # Admin commands
  ├── adventures.py   # Adventure and quest system
  ├── breeding.py     # Dragon breeding system
  ├── devpanel.py     # Developer panel
  ├── dragon_nest.py  # Dragon nest mechanics
  ├── dragonpass.py   # Dragonpass progression
  ├── dragons.py      # Dragon management
  ├── economy.py      # Economy and currency
  ├── events.py       # Event system
  ├── market.py       # Marketplace
  ├── packs.py        # Dragon packs/collections
  ├── raids.py        # Raid system
  ├── social.py       # Social features
  ├── tasks.py        # Background tasks
  └── topgg.py        # Top.gg integration
```

---

## 🔧 Configuration

Key configuration values can be found in [config.py](config.py):

- `DEV_USER_ID` - Developer user ID for dev commands
- `ERROR_WEBHOOK_URL` - Webhook URL for error logging
- `DRAGON_NEST_UPGRADE_COST` - Cost to upgrade dragon nests
- `DAILY_REWARD` - Daily login reward amount
- `DRAGONPASS_MAX_LEVEL` - Maximum dragonpass level
- `RAID_DURATION_MINUTES` - Duration of raid events

---

## 🗄️ Environment Variables

Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_bot_token_here
DEV_USER_ID=your_user_id
ERROR_WEBHOOK_URL=your_error_webhook_url
TOPGG_WEBHOOK_AUTH=your_topgg_webhook_auth_token_here
```

See [.env.example](.env.example) for all available options.

---

## 📦 Dependencies

- **discord.py** - Discord bot framework
- **python-dotenv** - Environment variable management
- **aiohttp** - Async HTTP client
- **pytz** - Timezone support

See requirements.txt for the complete list.

---
