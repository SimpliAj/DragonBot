# <img src="https://i.imgur.com/JbCyPi9.png" width="50" alt="Dragon Bot"> Dragon Bot

> **A feature-rich Discord bot for dragon catching, breeding, raiding, and building your ultimate dragon empire.**

[**➕ Add Dragon Bot to Your Server**](https://top.gg/de/bot/1445803895862333592/invite) · [**⭐ Vote on Top.gg**](https://top.gg/bot/1445803895862333592/vote)

---

## 📋 Overview

Dragon Bot delivers a deep, immersive dragon experience for Discord communities. Members race to catch wild dragons, breed them to unlock rarer tiers, conquer daily raid bosses, compete on leaderboards, and trade in a fully-featured economy — all without leaving Discord.

**8 rarity tiers · 22 unique dragon types · Daily raids · Full economy · Progression system**

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| ⚡ **Dragon Catching** | Dragons spawn randomly in configured channels — be fastest to type `dragon` and claim them |
| 🔄 **Breeding System** | Cross-breed two dragons for a chance at higher rarities, up to Ultra tier |
| 📋 **Breed Queue** | Schedule automatic round-the-clock breeding with `/breedqueue` |
| 🗺️ **Adventures** | Send dragons on 30-minute to 3-hour expeditions for coins, items, and rare dragons |
| ⚔️ **Raid Bosses** | Daily community raids at 8:00 UTC & 20:00 UTC — difficulty scales to group size |
| 🏰 **Dragon Nest** | Personal leveling system with 5 upgrade tiers and permanent passive perks |
| 📦 **Dragon Packs** | Open packs to discover dragons; collect materials to craft powerful Alpha Dragons |
| 🎯 **Dragonpass** | 30-tier reward progression system with exclusive items |
| 🎲 **Dragon Bingo** | Catch specific dragons to complete your bingo card for bonus rewards |
| 🏪 **Marketplace** | Buy and sell dragons with other players via `/market` |
| 🛒 **Shop** | Spend coins on packs, boosts, and passive skill items |
| 🎰 **Casino & Coinflip** | Gamble coins or challenge other players |
| 🏆 **Leaderboards** | Compete for top catches, fastest reflexes, rarest dragons, and more |
| 🏅 **Achievements** | Unlock milestones and showcase your progress |
| 📊 **Admin Panel** | Full server control panel for admins |

---

## 🐉 Dragon Rarity Tiers

```
Common → Uncommon → Rare → Epic → Legendary → Mythic → Ultra
```

| Tier | Dragons |
|------|---------|
| Common | Stone, Ember, Frost |
| Uncommon | Storm, Ocean, Nature |
| Rare | Amethyst, Topaz, Ruby, Sapphire |
| Epic | Iron, Silver |
| Legendary | Emerald, Diamond, Obsidian |
| Mythic | Gold, Platinum, Crystal |
| Ultra ✨ | Celestial, Void, Cosmic, Primordial |

---

## 📖 Commands

### Catching & Collection
| Command | Description |
|---------|-------------|
| `/inventory` | View your dragon collection |
| `/dragonlogue` | Browse all discovered dragons on your server |
| `/stats` | View detailed statistics for any user |

### Breeding
| Command | Description |
|---------|-------------|
| `/breed` | Cross-breed two dragons |
| `/breedqueue` | Schedule automatic breeding |

### Adventures & Raids
| Command | Description |
|---------|-------------|
| `/adventure` | Send a dragon on an expedition |
| `/adventures` | View active adventures and collect rewards |
| `/raidstatus` | View the current raid boss and attack it |
| `/ritual` | Start a community ritual to summon a raid boss |

### Progression
| Command | Description |
|---------|-------------|
| `/dragonpass` | View your Dragonpass progress |
| `/dragonnest` | Access Dragon Nest leveling and perks |
| `/skill` | View your active passive item skills |
| `/achievements` | View your achievements |
| `/daily` | Claim your daily reward |

### Economy
| Command | Description |
|---------|-------------|
| `/bal` | Check your coin balance |
| `/shop` | Browse the item shop |
| `/market` | Marketplace for trading dragons |
| `/mylistings` | View and manage your marketplace listings |
| `/pricecheck` | Check current market prices |
| `/openpacks` | Open dragon packs |
| `/alphadragons` | View and craft Alpha Dragons |
| `/casino` | Gamble your coins |
| `/coinflip` | Challenge someone to a coin flip |
| `/gift` | Send a dragon to another player |

### Social & Info
| Command | Description |
|---------|-------------|
| `/leaderboard` | Server leaderboards |
| `/bingo` | Play dragon bingo |
| `/vote` | Vote for the bot and earn rewards |
| `/help` | View all available commands |
| `/info` | Bot statistics |

### Server Setup *(Admin only)*
| Command | Description |
|---------|-------------|
| `/setchannel` | Set the dragon spawn channel |
| `/serverconfig` | Configure raid and marketplace settings |
| `/adminpanel` | Full server admin control panel |

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Discord Bot Token

### Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/SimpliAj/DragonBot.git
   cd DragonBot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

4. **Run the bot:**
   ```bash
   python main.py
   ```

---

## 📁 Project Structure

```
main.py               # Bot entry point
config.py             # Configuration, constants, rarity tiers, item definitions
database.py           # SQLite database operations and schemas
state.py              # Global state management
utils.py              # Shared utility functions
achievements.py       # Achievement definitions and logic
requirements.txt      # Python dependencies

cogs/                 # Command modules (discord.py Cogs)
  ├── admin.py        # Admin commands
  ├── adminpanel.py   # Server admin control panel
  ├── adventures.py   # Adventure and expedition system
  ├── backup.py       # Database backup tasks
  ├── breeding.py     # Dragon breeding and queue system
  ├── devpanel.py     # Developer panel
  ├── dragon_nest.py  # Dragon Nest leveling and perks
  ├── dragonpass.py   # Dragonpass progression (30 tiers)
  ├── dragons.py      # Dragon catching and management
  ├── economy.py      # Currency, shop, casino, coinflip
  ├── events.py       # Event system
  ├── market.py       # Player-to-player marketplace
  ├── packs.py        # Dragon packs and Alpha Dragons
  ├── raids.py        # Raid boss system (twice daily)
  ├── social.py       # Leaderboards, bingo, achievements
  ├── tasks.py        # Background scheduled tasks
  └── topgg.py        # Top.gg vote integration
```

---

## 🔧 Configuration

Key values in [`config.py`](config.py):

| Constant | Description |
|----------|-------------|
| `DEV_USER_ID` | Developer user ID for dev panel access |
| `ERROR_WEBHOOK_URL` | Discord webhook for error logging |
| `DRAGON_NEST_UPGRADE_COST` | Coin cost to upgrade Dragon Nest |
| `DAILY_REWARD` | Daily login reward amount |
| `DRAGONPASS_MAX_LEVEL` | Maximum Dragonpass tier (30) |
| `RAID_DURATION_MINUTES` | Duration of each raid event |
| `DRAGON_RARITY_TIERS` | Rarity tier → dragon type mapping |
| `BREEDING_CHANCES` | Outcome probabilities per parent combination |

---

## 🗄️ Environment Variables

Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_bot_token_here
DEV_USER_ID=your_discord_user_id
ERROR_WEBHOOK_URL=your_error_webhook_url
TOPGG_WEBHOOK_AUTH=your_topgg_webhook_auth_token
```

See [`.env.example`](.env.example) for all available options.

---

## 📦 Dependencies

- **discord.py** — Discord bot framework
- **python-dotenv** — Environment variable management
- **aiohttp** — Async HTTP client
- **pytz** — Timezone support

See [`requirements.txt`](requirements.txt) for the complete list.

---
