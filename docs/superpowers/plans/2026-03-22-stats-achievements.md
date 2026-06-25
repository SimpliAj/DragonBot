# Stats Redesign + Achievements Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `/stats` embed with a 3-page paginated view, add spawn-channel achievement notifications, and expand the achievement catalogue with 8 new categories.

**Architecture:** A new `achievements.py` consolidates the two existing copies of `check_and_award_achievements` (currently in `bot.py:481` and `database.py:870`), adds a `bot` parameter for spawn-channel lookup, and extends the stat queries to cover all new achievement categories. `cogs/dragons.py` replaces the flat embed builder with `PaginatedStatsView`. New hook calls are added at ~10 event sites across `bot.py`, `cogs/raids.py`, `cogs/adventures.py`, `cogs/dragon_nest.py`, `cogs/dragonpass.py`, and `cogs/topgg.py`.

**Tech Stack:** Python 3.11, discord.py 2.x, SQLite 3

---

## Codebase Map

| File | What changes |
|---|---|
| `config.py` | Add ~35 new entries to `ACHIEVEMENTS` dict |
| `database.py` | Add `dragonpass_completions` table to `init_db()`; remove inline duplicate of `check_and_award_achievements` (replace with import) |
| `achievements.py` | **New file.** Authoritative `check_and_award_achievements` with spawn-channel notification and all new stat queries |
| `cogs/dragons.py` | Replace flat embed builder in `stats` command with `PaginatedStatsView` |
| `bot.py` | Remove inline duplicate of `check_and_award_achievements` (replace with import); add hook calls at catch, breeding-complete, dragonpass-level-30, and alpha-creation sites |
| `cogs/raids.py` | Add hook call after recording raid damage (~line 365) |
| `cogs/adventures.py` | Add hook call after adventure claim |
| `cogs/dragon_nest.py` | Add hook calls after nest level-up and nest upgrade |
| `cogs/topgg.py` | Add hook call in `_process_vote` |
| `cogs/social.py` | Update import: `from achievements import check_and_award_achievements` |

---

## Task 1 — Add New Achievement Definitions to `config.py`

**Files:**
- Modify: `config.py` (after line 520, end of `ACHIEVEMENTS` dict)

The existing `ACHIEVEMENTS` dict ends after `daily_100` at line 520. All new entries use the same structure:
```python
'key': {'name': str, 'description': str, 'category': str, 'requirement': int, 'reward_coins': int, 'icon': str}
```

- [ ] **Step 1: Add new achievement entries**

Open `config.py`. Find the closing `}` of `ACHIEVEMENTS` (line 520) and insert the following block **before** the closing brace:

```python
    # ===== RAIDS ACHIEVEMENTS =====
    'raid_first': {'name': 'Raid Initiate', 'description': 'Deal damage in your first raid', 'category': '⚔️ Raids', 'requirement': 1, 'reward_coins': 100, 'icon': '⚔️'},
    'raid_damage_10k': {'name': 'Raid Fighter', 'description': 'Deal 10,000 total raid damage', 'category': '⚔️ Raids', 'requirement': 10000, 'reward_coins': 500, 'icon': '🗡️'},
    'raid_damage_100k': {'name': 'Raid Veteran', 'description': 'Deal 100,000 total raid damage', 'category': '⚔️ Raids', 'requirement': 100000, 'reward_coins': 2000, 'icon': '🛡️'},
    'raid_damage_1m': {'name': 'Raid Legend', 'description': 'Deal 1,000,000 total raid damage', 'category': '⚔️ Raids', 'requirement': 1000000, 'reward_coins': 10000, 'icon': '💥'},
    'raid_attacks_10': {'name': 'Attack Spree', 'description': 'Make 10 raid attacks', 'category': '⚔️ Raids', 'requirement': 10, 'reward_coins': 200, 'icon': '🏹'},
    'raid_attacks_50': {'name': 'Battle Hardened', 'description': 'Make 50 raid attacks', 'category': '⚔️ Raids', 'requirement': 50, 'reward_coins': 1000, 'icon': '⚙️'},
    'raid_attacks_100': {'name': 'War Machine', 'description': 'Make 100 raid attacks', 'category': '⚔️ Raids', 'requirement': 100, 'reward_coins': 5000, 'icon': '🔱'},

    # ===== ADVENTURES ACHIEVEMENTS =====
    'adventure_first': {'name': 'Adventure Begins', 'description': 'Complete your first adventure', 'category': '🗺️ Adventures', 'requirement': 1, 'reward_coins': 100, 'icon': '🗺️'},
    'adventure_10': {'name': 'Explorer', 'description': 'Complete 10 adventures', 'category': '🗺️ Adventures', 'requirement': 10, 'reward_coins': 500, 'icon': '🧭'},
    'adventure_50': {'name': 'Adventurer', 'description': 'Complete 50 adventures', 'category': '🗺️ Adventures', 'requirement': 50, 'reward_coins': 2000, 'icon': '🌍'},
    'adventure_100': {'name': 'Legend of the Land', 'description': 'Complete 100 adventures', 'category': '🗺️ Adventures', 'requirement': 100, 'reward_coins': 10000, 'icon': '🏔️'},

    # ===== EXTENDED BREEDING ACHIEVEMENTS =====
    'breeder_50': {'name': 'Master Breeder', 'description': 'Breed 50 dragons', 'category': '🥚 Breeding', 'requirement': 50, 'reward_coins': 5000, 'icon': '🐲'},
    'breeding_level_5': {'name': 'Breeding Expert', 'description': 'Reach Breeding Level 5', 'category': '🥚 Breeding', 'requirement': 5, 'reward_coins': 2000, 'icon': '🔬'},
    'breeding_level_10': {'name': 'Breeding Master', 'description': 'Reach Breeding Level 10', 'category': '🥚 Breeding', 'requirement': 10, 'reward_coins': 10000, 'icon': '🧬'},

    # ===== EXTENDED NEST ACHIEVEMENTS =====
    'nest_upgrade_1': {'name': 'Nest Upgraded', 'description': 'Upgrade your Dragon Nest once', 'category': '🏰 Dragon Nest', 'requirement': 1, 'reward_coins': 500, 'icon': '🔨'},
    'nest_upgrade_3': {'name': 'Nest Reinforced', 'description': 'Reach Nest Upgrade Tier 3', 'category': '🏰 Dragon Nest', 'requirement': 3, 'reward_coins': 2000, 'icon': '🏗️'},
    'nest_upgrade_5': {'name': 'Nest Perfected', 'description': 'Reach Nest Upgrade Tier 5 (Max)', 'category': '🏰 Dragon Nest', 'requirement': 5, 'reward_coins': 10000, 'icon': '🏰'},
    'nest_bounties_50': {'name': 'Bounty Hunter', 'description': 'Complete 50 nest bounties', 'category': '🏰 Dragon Nest', 'requirement': 50, 'reward_coins': 2000, 'icon': '🎯'},
    'nest_bounties_100': {'name': 'Elite Bounty Hunter', 'description': 'Complete 100 nest bounties', 'category': '🏰 Dragon Nest', 'requirement': 100, 'reward_coins': 8000, 'icon': '🏹'},

    # ===== DRAGONPASS ACHIEVEMENTS =====
    'dragonpass_1': {'name': 'Pass Graduate', 'description': 'Complete the Dragonpass once (reach Level 30)', 'category': '🎫 Dragonpass', 'requirement': 1, 'reward_coins': 1000, 'icon': '🎫'},
    'dragonpass_3': {'name': 'Pass Veteran', 'description': 'Complete the Dragonpass 3 times', 'category': '🎫 Dragonpass', 'requirement': 3, 'reward_coins': 5000, 'icon': '🌟'},
    'dragonpass_5': {'name': 'Pass Legend', 'description': 'Complete the Dragonpass 5 times', 'category': '🎫 Dragonpass', 'requirement': 5, 'reward_coins': 15000, 'icon': '👑'},
    'dragonpass_10': {'name': 'Pass Master', 'description': 'Complete the Dragonpass 10 times', 'category': '🎫 Dragonpass', 'requirement': 10, 'reward_coins': 50000, 'icon': '💎'},

    # ===== EXTENDED ALPHA ACHIEVEMENTS =====
    'alpha_3': {'name': 'Alpha Collector', 'description': 'Craft 3 Alpha Dragons', 'category': '✨ Alpha', 'requirement': 3, 'reward_coins': 2000, 'icon': '💫'},
    'alpha_10': {'name': 'Alpha Overlord', 'description': 'Craft 10 Alpha Dragons', 'category': '✨ Alpha', 'requirement': 10, 'reward_coins': 20000, 'icon': '🌠'},

    # ===== VOTING ACHIEVEMENTS =====
    'vote_first': {'name': 'First Vote', 'description': 'Vote for the bot for the first time', 'category': '🗳️ Voting', 'requirement': 1, 'reward_coins': 200, 'icon': '🗳️'},
    'vote_10': {'name': 'Regular Voter', 'description': 'Vote 10 times total', 'category': '🗳️ Voting', 'requirement': 10, 'reward_coins': 500, 'icon': '📋'},
    'vote_50': {'name': 'Dedicated Voter', 'description': 'Vote 50 times total', 'category': '🗳️ Voting', 'requirement': 50, 'reward_coins': 2000, 'icon': '📜'},
    'vote_100': {'name': 'Top Voter', 'description': 'Vote 100 times total', 'category': '🗳️ Voting', 'requirement': 100, 'reward_coins': 10000, 'icon': '🏅'},
    'vote_streak_7': {'name': 'Weekly Supporter', 'description': 'Maintain a 7-day vote streak', 'category': '🗳️ Voting', 'requirement': 7, 'reward_coins': 1000, 'icon': '🔥'},
    'vote_streak_30': {'name': 'Monthly Supporter', 'description': 'Maintain a 30-day vote streak', 'category': '🗳️ Voting', 'requirement': 30, 'reward_coins': 5000, 'icon': '💎'},
```

- [ ] **Step 2: Verify no syntax errors**

```bash
python -c "from config import ACHIEVEMENTS; print(f'Total achievements: {len(ACHIEVEMENTS)}')"
```
Expected: `Total achievements: 64` (or similar, old count + 34 new)

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add 34 new achievement definitions across 8 categories"
```

---

## Task 2 — Add `dragonpass_completions` Table

**Files:**
- Modify: `database.py` — inside `init_db()` function

The `dragonpass_completions` table logs each time a user completes the Dragonpass (reaches level 30 and restarts). Multiple rows per user are intentional. Achievement check queries `COUNT(*)`.

- [ ] **Step 1: Add table creation to `init_db()`**

In `database.py`, find the block of `CREATE TABLE IF NOT EXISTS` calls inside `init_db()`. Add after the last table creation:

```python
    c.execute('''CREATE TABLE IF NOT EXISTS dragonpass_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        completed_at INTEGER NOT NULL
    )''')
```

- [ ] **Step 2: Verify table is created**

```bash
python -c "import database; database.init_db(); import sqlite3; conn = sqlite3.connect('dragon_bot.db'); print(conn.execute('SELECT name FROM sqlite_master WHERE name=\"dragonpass_completions\"').fetchone())"
```
Expected: `('dragonpass_completions',)`

- [ ] **Step 3: Commit**

```bash
git add database.py
git commit -m "feat: add dragonpass_completions table"
```

---

## Task 3 — Create `achievements.py`

**Files:**
- Create: `achievements.py` (project root, same level as `bot.py`)

This file is the single authoritative location for `check_and_award_achievements`. It replaces the duplicate copies in `bot.py:481` and `database.py:870`.

**Key differences from the existing copies:**
1. Takes `bot=None` parameter — when provided, looks up spawn channel from `guild_settings` and sends a per-achievement notification embed there.
2. Adds 7 new stat queries (raids, adventures, nest upgrade/bounties, dragonpass completions, votes, breeding level).
3. Adds all new achievement IDs to the `achievement_progress` dict.
4. Sends one embed **per newly unlocked achievement** to the spawn channel (not a combined embed), matching the spec's design.

- [ ] **Step 1: Create the file**

```python
# achievements.py
import sqlite3
import time
import logging
import discord

from config import ACHIEVEMENTS, DRAGON_RARITY_TIERS

logger = logging.getLogger(__name__)


async def check_and_award_achievements(
    guild_id: int,
    user_id: int,
    bot: discord.Client = None,
    interaction: discord.Interaction = None,
):
    """
    Check all achievements for a user, award any newly earned ones, and send notifications.

    Notification targets (both optional, both used when provided):
    - interaction: sends a combined followup embed listing all newly unlocked achievements
    - bot: sends one embed per achievement to the guild's spawn channel
    """
    try:
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # --- Gather stats ---

        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        balance = row[0] if row else 0

        c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        total_caught = row[0] if row and row[0] else 0

        c.execute('SELECT COUNT(*) FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0', (guild_id, user_id))
        unique_types = c.fetchone()[0]

        # Rarity flags (1 if user owns any dragon of that rarity)
        rarity_flags = {r: 0 for r in ('uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra')}
        for rarity_tier, dragons in DRAGON_RARITY_TIERS.items():
            if rarity_tier not in rarity_flags:
                continue
            for dragon_type in dragons:
                c.execute(
                    'SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                    (guild_id, user_id, dragon_type),
                )
                r = c.fetchone()
                if r and r[0] > 0:
                    rarity_flags[rarity_tier] = 1
                    break

        c.execute(
            '''SELECT COUNT(*) FROM trade_offers
               WHERE guild_id = ? AND (sender_id = ? OR receiver_id = ?) AND status = 'completed' ''',
            (guild_id, user_id, user_id),
        )
        trades_completed = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM bred_dragons WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        breeds_completed = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        alphas_crafted = c.fetchone()[0]

        c.execute('SELECT level, bounties_completed, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        nest_level = row[0] if row else 0
        nest_bounties = row[1] if row else 0
        nest_upgrade = row[2] if row else 0

        # Breeding level
        c.execute('SELECT level FROM breeding_xp WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        breeding_level = row[0] if row else 1

        # Raid stats
        c.execute(
            'SELECT SUM(damage_dealt), SUM(attacks_made) FROM raid_damage WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        row = c.fetchone()
        raid_damage = row[0] if row and row[0] else 0
        raid_attacks = row[1] if row and row[1] else 0

        # Adventures completed
        c.execute(
            'SELECT COUNT(*) FROM user_adventures WHERE guild_id = ? AND user_id = ? AND claimed = 1',
            (guild_id, user_id),
        )
        adventures_done = c.fetchone()[0]

        # Dragonpass completions
        c.execute(
            'SELECT COUNT(*) FROM dragonpass_completions WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        dragonpass_completions = c.fetchone()[0]

        # Vote stats (user_id only, no guild_id column in vote_streaks)
        c.execute(
            'SELECT total_votes, current_streak FROM vote_streaks WHERE user_id = ?',
            (user_id,),
        )
        row = c.fetchone()
        total_votes = row[0] if row else 0
        vote_streak = row[1] if row else 0

        # --- Build progress map ---
        achievement_progress = {
            # Catching
            'catch_1': total_caught,
            'catch_10': total_caught,
            'catch_50': total_caught,
            'catch_100': total_caught,
            'catch_250': total_caught,
            'catch_500': total_caught,
            'catch_1000': total_caught,
            # Rarity
            'first_uncommon': rarity_flags['uncommon'],
            'first_rare': rarity_flags['rare'],
            'first_epic': rarity_flags['epic'],
            'first_legendary': rarity_flags['legendary'],
            'first_mythic': rarity_flags['mythic'],
            'first_ultra': rarity_flags['ultra'],
            # Collection
            'collector_5': unique_types,
            'collector_10': unique_types,
            'collector_15': unique_types,
            'collector_all': unique_types,
            # Wealth
            'rich_1k': balance,
            'rich_10k': balance,
            'rich_100k': balance,
            'rich_1m': balance,
            'rich_10m': balance,
            'rich_100m': balance,
            'rich_500m': balance,
            # Breeding (count)
            'breeder_1': breeds_completed,
            'breeder_5': breeds_completed,
            'breeder_10': breeds_completed,
            'breeder_50': breeds_completed,
            # Breeding level
            'breeding_level_5': breeding_level,
            'breeding_level_10': breeding_level,
            # Alpha
            'alpha_1': alphas_crafted,
            'alpha_3': alphas_crafted,
            'alpha_5': alphas_crafted,
            'alpha_10': alphas_crafted,
            # Trading
            'trader_1': trades_completed,
            'trader_5': trades_completed,
            'trader_10': trades_completed,
            # Dragon Nest
            'nest_level_5': nest_level,
            'nest_level_10': nest_level,
            'nest_upgrade_1': nest_upgrade,
            'nest_upgrade_3': nest_upgrade,
            'nest_upgrade_5': nest_upgrade,
            'nest_bounties_50': nest_bounties,
            'nest_bounties_100': nest_bounties,
            # Daily (placeholder — tracking not yet implemented)
            'daily_7': 0,
            'daily_14': 0,
            'daily_30': 0,
            'daily_100': 0,
            # Raids
            'raid_first': raid_damage,
            'raid_damage_10k': raid_damage,
            'raid_damage_100k': raid_damage,
            'raid_damage_1m': raid_damage,
            'raid_attacks_10': raid_attacks,
            'raid_attacks_50': raid_attacks,
            'raid_attacks_100': raid_attacks,
            # Adventures
            'adventure_first': adventures_done,
            'adventure_10': adventures_done,
            'adventure_50': adventures_done,
            'adventure_100': adventures_done,
            # Dragonpass
            'dragonpass_1': dragonpass_completions,
            'dragonpass_3': dragonpass_completions,
            'dragonpass_5': dragonpass_completions,
            'dragonpass_10': dragonpass_completions,
            # Voting
            'vote_first': total_votes,
            'vote_10': total_votes,
            'vote_50': total_votes,
            'vote_100': total_votes,
            'vote_streak_7': vote_streak,
            'vote_streak_30': vote_streak,
        }

        # --- Check and award ---
        newly_unlocked = []
        total_coins_awarded = 0

        for ach_id, ach_data in ACHIEVEMENTS.items():
            progress = achievement_progress.get(ach_id, 0)
            requirement = ach_data['requirement']

            c.execute(
                'SELECT unlocked FROM user_achievements WHERE guild_id = ? AND user_id = ? AND achievement_id = ?',
                (guild_id, user_id, ach_id),
            )
            row = c.fetchone()
            is_unlocked = bool(row[0]) if row else False

            if progress >= requirement and not is_unlocked:
                c.execute(
                    '''INSERT OR REPLACE INTO user_achievements
                       (guild_id, user_id, achievement_id, progress, unlocked, unlocked_at)
                       VALUES (?, ?, ?, ?, 1, ?)''',
                    (guild_id, user_id, ach_id, progress, int(time.time())),
                )
                c.execute(
                    'UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
                    (ach_data['reward_coins'], guild_id, user_id),
                )
                newly_unlocked.append({
                    'id': ach_id,
                    'name': ach_data['name'],
                    'description': ach_data['description'],
                    'icon': ach_data['icon'],
                    'reward': ach_data['reward_coins'],
                    'category': ach_data.get('category', 'Other'),
                })
                total_coins_awarded += ach_data['reward_coins']
            else:
                # Update progress only — do NOT use INSERT OR REPLACE here because it
                # would delete+reinsert the row, wiping the unlocked_at timestamp.
                c.execute(
                    '''INSERT INTO user_achievements (guild_id, user_id, achievement_id, progress, unlocked)
                       VALUES (?, ?, ?, ?, 0)
                       ON CONFLICT(guild_id, user_id, achievement_id)
                       DO UPDATE SET progress = excluded.progress WHERE unlocked = 0''',
                    (guild_id, user_id, ach_id, progress),
                )

        conn.commit()
        conn.close()

        if not newly_unlocked:
            return

        # --- Notify via interaction followup (existing behaviour) ---
        if interaction:
            try:
                embed = discord.Embed(
                    title="🎉 Achievement(s) Unlocked!",
                    description=f"You've earned {len(newly_unlocked)} new achievement(s)!",
                    color=discord.Color.gold(),
                )
                for ach in newly_unlocked:
                    embed.add_field(
                        name=f"{ach['icon']} {ach['name']}",
                        value=f"_{ach['description']}_\n+**{ach['reward']}** 🪙",
                        inline=False,
                    )
                embed.set_footer(text=f"Total earned: +{total_coins_awarded} 🪙")
                await interaction.followup.send(embed=embed, ephemeral=False)
            except Exception as e:
                logger.error(f"Achievement interaction notify error: {e}")

        # --- Notify via spawn channel (new behaviour) ---
        if bot:
            try:
                conn2 = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c2 = conn2.cursor()
                c2.execute(
                    'SELECT spawn_channel FROM guild_settings WHERE guild_id = ?',
                    (guild_id,),
                )
                row = c2.fetchone()
                conn2.close()
                channel_id = row[0] if row else None

                if channel_id:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        # Try to get display name
                        guild = bot.get_guild(guild_id)
                        member = guild.get_member(user_id) if guild else None
                        username = member.display_name if member else str(user_id)

                        for ach in newly_unlocked:
                            notify_embed = discord.Embed(
                                title="🏆 Achievement Unlocked!",
                                color=discord.Color.gold(),
                            )
                            notify_embed.add_field(
                                name=f"{ach['icon']} {ach['name']}",
                                value=f"{ach['description']}\n💰 Reward: **+{ach['reward']:,}** coins",
                                inline=False,
                            )
                            notify_embed.set_footer(text=username)
                            await channel.send(embed=notify_embed)
            except Exception as e:
                logger.error(f"Achievement spawn-channel notify error: {e}")

    except Exception as e:
        logger.error(f"check_and_award_achievements error for user {user_id}: {e}")
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from achievements import check_and_award_achievements; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add achievements.py
git commit -m "feat: create achievements.py with consolidated check_and_award_achievements"
```

---

## Task 4 — Update Imports (Replace Duplicate Copies)

**Files:**
- Modify: `database.py` — remove inline function, add import
- Modify: `bot.py` — remove inline function, add import
- Modify: `cogs/social.py` — update import source

**IMPORTANT:** The existing function in `database.py` starts at line 870. The existing function in `bot.py` starts at line 481. Both extend to roughly 160 lines each. Replace each with an import statement.

- [ ] **Step 1: Replace in `database.py`**

Find the block starting at line 870:
```python
# ==================== ACHIEVEMENTS ====================
async def check_and_award_achievements(guild_id: int, user_id: int, interaction: discord.Interaction = None):
    ...
```

Replace the entire function (through its last line before `# ==================== ITEM COST CALCULATION ====================`) with:

```python
# ==================== ACHIEVEMENTS ====================
from achievements import check_and_award_achievements  # noqa: F401 — re-exported for importers
```

- [ ] **Step 2: Replace in `bot.py`**

Find the block starting at line 481:
```python
async def check_and_award_achievements(guild_id: int, user_id: int, interaction: discord.Interaction = None):
    ...
```

Replace the entire function (through its last `except` block before the next top-level definition) with:

```python
from achievements import check_and_award_achievements
```

- [ ] **Step 3: Update `cogs/social.py`**

Line 13 currently reads:
```python
from database import check_and_award_achievements, update_balance
```

Change to:
```python
from achievements import check_and_award_achievements
from database import update_balance
```

Also update every call to `check_and_award_achievements` in `social.py` (around line 328) to pass `bot=self.bot` (assuming the cog has `self.bot`):
```python
await check_and_award_achievements(guild_id, user_id, bot=self.bot, interaction=interaction)
```

- [ ] **Step 4: Update existing call in `bot.py` `/achievements` command**

Find the call at bot.py line 19287:
```python
await check_and_award_achievements(guild_id, user_id, interaction)
```

Update to pass keyword args (keeps interaction for followup, adds bot for spawn channel):
```python
await check_and_award_achievements(guild_id, user_id, bot=bot, interaction=interaction)
```

- [ ] **Step 5: Verify bot starts without import errors**

```bash
python -c "import bot" 2>&1 | head -20
```
Expected: No `ImportError` or `NameError`.

- [ ] **Step 6: Commit**

```bash
git add database.py bot.py cogs/social.py
git commit -m "refactor: consolidate check_and_award_achievements into achievements.py"
```

---

## Task 5 — Paginated `/stats` View

**Files:**
- Modify: `cogs/dragons.py` — `stats` command starting at line 1643

The DB queries (lines 1654–1755) are already complete — all data is fetched. Only the embed-building section needs replacing (lines 1759–end of function).

**Design:**
- Page 1 — Overview: Economy, Dragon Nest, Dragonpass, Alpha Dragons
- Page 2 — Activity: Raids (hidden if 0), Adventures, Breeding
- Page 3 — Records: Rarest Dragon, Catch Times, Achievements, Votes (hidden if 0)
- Navigation: ◀️ / ▶️ buttons, footer "Page X/3", 180s timeout

- [ ] **Step 1: Replace embed builder in `stats` command**

After `conn.close()` (line 1757), replace everything from the `embed = discord.Embed(...)` line to the end of the function with:

```python
        # --- Build the 3 pages ---
        def build_page1():
            level_name = LEVEL_NAMES.get(nest_level, "Hatchling")
            e = discord.Embed(
                title=f"📊 {user.display_name}'s Profile",
                color=0x5865F2,
            )
            e.set_thumbnail(url=user.display_avatar.url)
            e.add_field(
                name="💰 Economy",
                value=(
                    f"Balance: **{balance:,.0f}** 🪙\n"
                    f"Total Dragons: **{total_dragons:,}**\n"
                    f"Unique Types: **{unique_dragons}/{len(DRAGON_TYPES)}**"
                ),
                inline=True,
            )
            e.add_field(
                name="🏰 Dragon Nest",
                value=(
                    f"Level: **{nest_level}/10** ({level_name})\n"
                    f"Upgrade Tier: **{nest_upgrade}/5**\n"
                    f"Bounties: **{bounties_completed}**"
                ),
                inline=True,
            )
            e.add_field(
                name="🎁 Dragonpass",
                value=f"Level: **{pass_level}/30**\nSeason: **1**",
                inline=True,
            )
            e.add_field(
                name="✨ Alpha Dragons",
                value=(
                    f"Created: **{alpha_count}**\n"
                    f"Catch Boost: **+{total_catch_boost * 100:.1f}%**"
                ),
                inline=True,
            )
            e.set_footer(text="Page 1/3")
            return e

        def build_page2():
            e = discord.Embed(
                title=f"📊 {user.display_name}'s Activity",
                color=0x5865F2,
            )
            e.set_thumbnail(url=user.display_avatar.url)
            if raid_damage_total > 0:
                e.add_field(
                    name="⚔️ Raids",
                    value=(
                        f"Total Damage: **{raid_damage_total:,}**\n"
                        f"Attacks Made: **{raid_attacks_total:,}**"
                    ),
                    inline=True,
                )
            if adventures_done > 0:
                e.add_field(
                    name="🗺️ Adventures",
                    value=f"Completed: **{adventures_done}**",
                    inline=True,
                )
            e.add_field(
                name="🥚 Breeding",
                value=(
                    f"Dragons Bred: **{dragons_bred}**\n"
                    f"Breeding Level: **{breeding_level}**"
                ),
                inline=True,
            )
            if not e.fields:
                e.description = "*No activity recorded yet.*"
            e.set_footer(text="Page 2/3")
            return e

        def build_page3():
            e = discord.Embed(
                title=f"📊 {user.display_name}'s Records",
                color=0x5865F2,
            )
            e.set_thumbnail(url=user.display_avatar.url)
            if rarest_dragon:
                rarest_data = DRAGON_TYPES[rarest_dragon]
                e.add_field(
                    name="🌟 Rarest Dragon Owned",
                    value=(
                        f"{rarest_data['emoji']} **{rarest_data['name']}**\n"
                        f"(Spawn Rate: {rarest_data['spawn_chance']:.2f}%)"
                    ),
                    inline=False,
                )
            if fastest_result or slowest_result:
                parts = []
                if fastest_result:
                    fd = DRAGON_TYPES[fastest_result[0]]
                    parts.append(f"⚡ **Fastest:** {fastest_result[1]:.2f}s ({fd['emoji']} {fd['name']})")
                if slowest_result:
                    sd = DRAGON_TYPES[slowest_result[0]]
                    parts.append(f"🐢 **Slowest:** {slowest_result[1]:.2f}s ({sd['emoji']} {sd['name']})")
                e.add_field(name="⏱️ Catch Times", value="\n".join(parts), inline=False)
            e.add_field(
                name="🏅 Achievements",
                value=f"Unlocked: **{achievements_count}**",
                inline=True,
            )
            if total_votes > 0:
                e.add_field(
                    name="🗳️ Votes",
                    value=(
                        f"Total: **{total_votes}**\n"
                        f"Streak: **{vote_streak}** | Best: **{best_streak}**"
                    ),
                    inline=True,
                )
            e.set_footer(text="Page 3/3")
            return e

        pages = [build_page1(), build_page2(), build_page3()]

        class PaginatedStatsView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.page = 0

            @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
            async def prev_page(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.page = (self.page - 1) % len(pages)
                await btn_interaction.response.edit_message(embed=pages[self.page], view=self)

            @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
            async def next_page(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.page = (self.page + 1) % len(pages)
                await btn_interaction.response.edit_message(embed=pages[self.page], view=self)

        await interaction.followup.send(embed=pages[0], view=PaginatedStatsView())
```

- [ ] **Step 2: Verify bot loads cog without syntax error**

```bash
python -c "
import discord
from unittest.mock import MagicMock
# Just check syntax
import ast, pathlib
src = pathlib.Path('cogs/dragons.py').read_text()
ast.parse(src)
print('Syntax OK')
"
```
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add cogs/dragons.py
git commit -m "feat: replace /stats flat embed with 3-page PaginatedStatsView"
```

---

## Task 6 — Hook: Dragon Caught (`bot.py`)

**Files:**
- Modify: `bot.py` — catch handler, after `check_dragonpass_quests` calls (~line 6308)

- [ ] **Step 1: Add hook after dragonpass level-up notification**

Find the block around line 6346 where `await message.channel.send(embed=levelup_embed)` is called. Immediately after the `if result and result[1] > 0:` block (i.e., after dragonpass handling, before Dragon Nest bounty code at ~line 6348), insert:

```python
                    # Achievement check after catch
                    await check_and_award_achievements(guild_id, message.author.id, bot=bot)
```

- [ ] **Step 2: Commit**

```bash
git add bot.py
git commit -m "feat: check achievements on dragon catch"
```

---

## Task 7 — Hook: Raid Attack (`cogs/raids.py`)

**Files:**
- Modify: `cogs/raids.py` — after `raid_damage` is updated (~line 365)

- [ ] **Step 1: Add import at top of file**

At the top of `cogs/raids.py`, find the existing imports and add:
```python
from achievements import check_and_award_achievements
```

- [ ] **Step 2: Add hook after recording damage**

Find the two locations where `INSERT INTO raid_damage ... DO UPDATE SET damage_dealt = damage_dealt + ?, attacks_made = attacks_made + 1` is called (around lines 363 and 876). After each such block (but still inside the `async` context), add:

```python
        await check_and_award_achievements(btn_interaction.guild_id, btn_interaction.user.id, bot=self.bot)
```

Adjust `btn_interaction` / `interaction` variable name to match the surrounding code.

- [ ] **Step 3: Commit**

```bash
git add cogs/raids.py
git commit -m "feat: check achievements on raid attack"
```

---

## Task 8 — Hook: Adventure Claimed (`bot.py`)

**Files:**
- Modify: `bot.py` — background adventure-completion task, around line 20308

The actual claim logic is in `bot.py`, **not** in `cogs/adventures.py`. The relevant SQL is:
```python
c.execute('''UPDATE user_adventures
            SET status = 'completed', rewards_coins = ?, rewards_dragons = ?, claimed = 1
            WHERE adventure_id = ?''', ...)
conn.commit()  # line ~20313
```

- [ ] **Step 1: Add hook after `conn.commit()` at line ~20313**

Immediately after `conn.commit()` (right before `# Prepare DM data to send`), insert:

```python
            # Achievement check after adventure claim
            await check_and_award_achievements(guild_id, user_id, bot=bot)
```

- [ ] **Step 2: Commit**

```bash
git add bot.py
git commit -m "feat: check achievements on adventure claim"
```

---

## Task 9 — Hook: Breeding Complete (`bot.py`)

**Files:**
- Modify: `bot.py` — breeding completion, around line 20053

- [ ] **Step 1: Add hook after successful breed**

Find the line `c.execute('UPDATE breeding_queue SET status = "completed_success" WHERE queue_id = ?', (queue_id,))` (~line 20053). After the `conn.commit()` that follows, add:

```python
                await check_and_award_achievements(guild_id, user_id, bot=bot)
```

- [ ] **Step 2: Commit**

```bash
git add bot.py
git commit -m "feat: check achievements on breeding complete"
```

---

## Task 10 — Hook: Dragonpass Level 30 (`bot.py`)

**Files:**
- Modify: `bot.py` — dragonpass level-up handler, around line 6312

The dragonpass completion happens when the user reaches level 30 by completing quests. The level-up is detected at line 6312 when `result[1] > 0` and `new_level == 30`.

- [ ] **Step 1: Add dragonpass_completions insert and achievement hook**

Inside the `if result and result[1] > 0:` block (around line 6312), after the `await message.channel.send(embed=levelup_embed)` call, add:

```python
                        # Log dragonpass completion and check achievement
                        if new_level == 30:
                            conn_dp_log = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c_dp_log = conn_dp_log.cursor()
                            c_dp_log.execute(
                                'INSERT INTO dragonpass_completions (guild_id, user_id, completed_at) VALUES (?, ?, ?)',
                                (guild_id, message.author.id, int(time.time())),
                            )
                            conn_dp_log.commit()
                            conn_dp_log.close()
                            await check_and_award_achievements(guild_id, message.author.id, bot=bot)
```

- [ ] **Step 2: Commit**

```bash
git add bot.py
git commit -m "feat: log dragonpass completion and check achievements at level 30"
```

---

## Task 11 — Hook: Dragon Nest Level Up + Upgrade (`cogs/dragon_nest.py`)

**Files:**
- Modify: `cogs/dragon_nest.py`

- [ ] **Step 1: Add import at top of file**

```python
from achievements import check_and_award_achievements
```

- [ ] **Step 2: Add hook after nest level-up**

In `submit_dragons`, find the `conn.commit()` + `conn.close()` pair that follows the `UPDATE dragon_nest SET level = ?` statement. Insert the hook **after** `conn.close()` (not between two DB connection opens, to avoid lock conflicts):

```python
        await check_and_award_achievements(self.guild_id, self.user_id, bot=interaction.client)
```

- [ ] **Step 3: Add hook after nest upgrade**

In the nest upgrade button callback, find the `conn.commit()` + `conn.close()` that follows `UPDATE dragon_nest SET upgrade_level = upgrade_level + 1`. Insert the hook **after** `conn.close()`:

```python
        await check_and_award_achievements(self.guild_id, self.user_id, bot=interaction.client)
```

- [ ] **Step 4: Commit**

```bash
git add cogs/dragon_nest.py
git commit -m "feat: check achievements on nest level up and upgrade"
```

---

## Task 12 — Hook: Vote (`cogs/topgg.py`)

**Files:**
- Modify: `cogs/topgg.py`

- [ ] **Step 1: Add import at top of file**

```python
from achievements import check_and_award_achievements
```

- [ ] **Step 2: Add hook at end of `_process_vote`**

`_process_vote` is at line 186. After `await self._notify(...)` (line 219), add:

```python
        if member:
            guild_id = member.guild.id
            await check_and_award_achievements(guild_id, user_id, bot=self.bot)
```

- [ ] **Step 3: Commit**

```bash
git add cogs/topgg.py
git commit -m "feat: check achievements on vote"
```

---

## Task 13 — Hook: Alpha Dragon Created (`bot.py`)

**Files:**
- Modify: `bot.py` — alpha creation, around line 13231

- [ ] **Step 1: Add hook after alpha INSERT**

Find `c.execute('''INSERT INTO user_alphas (guild_id, user_id, alpha_id, name, catch_boost, created_at)` (~line 13231). After the `conn.commit()` and `conn.close()`, add:

```python
        await check_and_award_achievements(interaction.guild_id, interaction.user.id, bot=bot)
```

- [ ] **Step 2: Commit**

```bash
git add bot.py
git commit -m "feat: check achievements on alpha dragon creation"
```

---

## Final Verification

- [ ] **Start the bot and confirm no import errors**

```bash
python bot.py 2>&1 | head -30
```

- [ ] **Manually test `/stats`** — verify 3 pages with ◀️ ▶️ navigation, correct data on each page.

- [ ] **Trigger an achievement** — catch a dragon, confirm embed appears in spawn channel.

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: stats redesign + achievements overhaul complete"
```
