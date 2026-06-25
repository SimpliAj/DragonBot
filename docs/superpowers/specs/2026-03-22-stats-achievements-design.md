# Stats Redesign + Achievements Overhaul

**Date:** 2026-03-22
**Files affected:** `cogs/dragons.py`, `database.py`, `config.py`, `bot.py`, `cogs/raids.py`, `cogs/adventures.py`, `cogs/dragon_nest.py`, `cogs/dragonpass.py`, `cogs/economy.py`

---

## Part 1 — /stats Redesign

### Goal
Replace the current single flat embed with a 3-page paginated embed. Page 1 shows the most important stats; Pages 2 and 3 show detail categories accessible via navigation buttons.

### Pages

**Page 1 — Overview** (always visible first):
- Economy: Balance, Total Dragons, Unique Types
- Dragon Nest: Level/10, Upgrade Tier/5, Bounties Completed
- Dragonpass: Level/30, Season
- Alpha Dragons: Count created, total Catch Boost %

**Page 2 — Activity:**
- Raids: Total damage dealt, total attacks (hidden if 0)
- Adventures: Adventures completed (hidden if 0)
- Breeding: Dragons bred, Breeding Level

**Page 3 — Progress & Records:**
- Rarest Dragon Owned (hidden if no dragons)
- Fastest / Slowest Catch Time (hidden if no catches)
- Achievements Unlocked count
- Votes: Total, current streak, best streak (hidden if 0)

### Navigation
- ◀️ / ▶️ buttons on all pages
- Footer: "Page X/3"
- Fields with value 0 on Pages 2 and 3 are hidden entirely

### Implementation
`PaginatedStatsView(discord.ui.View)` with a list of 3 embed builders. Each button click calls `interaction.response.edit_message(embed=pages[self.page], view=self)`. All DB queries run once upfront before sending the first page. View timeout: default 180 seconds; buttons become inactive after timeout (no `on_timeout` override needed).

---

## Part 2 — Achievements: Auto-Notification

### Goal
When a user earns a new achievement, automatically send an embed to the server's spawn channel. Currently achievements are only visible via `/achievements`.

### Notification Embed
```
Title:   Achievement Unlocked!
Fields:  [achievement name] — [description]
         Reward: +X coins
Footer:  [username]
Color:   Gold
```

### Architecture
New function `check_and_award_achievements(bot, guild_id, user_id, event_type, value)` added to a new `achievements.py` module (imported where needed; keeps `database.py` focused on schema/CRUD).

**Flow:**
1. Called from event handlers with `event_type` (e.g. `'catch'`, `'raid_damage'`) and a numeric `value`
2. Queries all achievements matching `event_type`
3. Filters to those the user has not yet earned
4. Checks if current stat value meets the achievement threshold
5. For each newly earned achievement: inserts into `user_achievements`, awards coins via `update_balance`, sends embed to spawn channel via `bot.get_channel(spawn_channel_id)`
6. Returns list of newly awarded achievement keys

**Spawn channel lookup:** `SELECT spawn_channel_id FROM spawn_config WHERE guild_id = ?`

**Calling pattern** (mirrors existing `check_dragonpass_quests`):
```python
await asyncio.to_thread(check_and_award_achievements, bot, guild_id, user_id, 'catch', total_caught)
```
For bot-instance access in threaded calls, pass `bot` as argument.

### Hook Points

| Event | Location | event_type |
|---|---|---|
| Dragon caught | `bot.py` catch handler | `catch`, `rarity_{rarity}`, `unique_types` |
| Raid attack | `cogs/raids.py` or `bot.py` attack handler | `raid_damage`, `raid_attacks` |
| Adventure claimed | `cogs/adventures.py` claim handler | `adventures_completed` |
| Dragon bred | `bot.py` breeding complete | `dragons_bred`, `breeding_level` |
| Nest level up | `cogs/dragon_nest.py` submit_dragons | `nest_level`, `nest_bounties` |
| Nest upgrade | `cogs/dragon_nest.py` upgrade handler | `nest_upgrade` |
| Dragonpass complete | `cogs/dragonpass.py` level 30 handler | `dragonpass_completed` — caller inserts a row into `dragonpass_completions`, then queries total count and passes that as `value` |
| Alpha created | `bot.py` alpha creation | `alphas_created` |
| Vote | vote handler | `total_votes`, `vote_streak` |
| Balance milestone | inline call added at each `update_balance` call site where a coin gain occurs (catch reward, daily, adventure claim, raid reward); NOT added to loss sites (e.g. shop purchases) | `balance` — caller passes the user's new balance total after the update |

---

## Part 3 — Achievement Definitions

All defined in `config.py` in `ACHIEVEMENTS` dict. Each entry:
```python
'key': {
    'name': str, 'description': str, 'category': str,
    'event_type': str, 'threshold': int,
    'reward_coins': int, 'icon': str  # icon shown as inline emoji in notification embed title
}
```

### Existing (event_type fields added)
Catching (1/10/50/100/250/500/1000) — `event_type: 'catch'`
Rarity (first of each rarity) — `event_type: 'rarity_common'`, `'rarity_rare'`, etc. (dynamic per rarity string)
Collection (5/10/15 types) — `event_type: 'unique_types'`

### New: Economy
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `balance_10k` | First Fortune | balance >= 10,000 | 500 |
| `balance_100k` | Coin Hoarder | balance >= 100,000 | 2,000 |
| `balance_1m` | Dragon Millionaire | balance >= 1,000,000 | 10,000 |
| `balance_10m` | Dragon Tycoon | balance >= 10,000,000 | 50,000 |

### New: Raids
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `raid_first` | Raid Initiate | damage >= 1 | 100 |
| `raid_damage_10k` | Raid Fighter | total damage >= 10,000 | 500 |
| `raid_damage_100k` | Raid Veteran | total damage >= 100,000 | 2,000 |
| `raid_damage_1m` | Raid Legend | total damage >= 1,000,000 | 10,000 |
| `raid_attacks_10` | Attack Spree | attacks >= 10 | 200 |
| `raid_attacks_50` | Battle Hardened | attacks >= 50 | 1,000 |
| `raid_attacks_100` | War Machine | attacks >= 100 | 5,000 |

### New: Adventures
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `adventure_first` | First Steps | completed >= 1 | 100 |
| `adventure_10` | Explorer | completed >= 10 | 500 |
| `adventure_50` | Adventurer | completed >= 50 | 2,000 |
| `adventure_100` | Legend of the Land | completed >= 100 | 10,000 |

### New: Breeding
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `breeding_first` | Dragon Parent | bred >= 1 | 200 |
| `breeding_10` | Dragon Breeder | bred >= 10 | 1,000 |
| `breeding_50` | Master Breeder | bred >= 50 | 5,000 |
| `breeding_level_5` | Breeding Expert | breeding level >= 5 | 2,000 |
| `breeding_level_10` | Breeding Master | breeding level >= 10 | 10,000 |

### New: Dragon Nest
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `nest_level_5` | Nest Builder | nest level >= 5 | 1,000 |
| `nest_level_10` | Primordial Keeper | nest level >= 10 | 10,000 |
| `nest_upgrade_1` | Nest Upgraded | upgrade tier >= 1 | 500 |
| `nest_upgrade_3` | Nest Reinforced | upgrade tier >= 3 | 2,000 |
| `nest_upgrade_5` | Nest Perfected | upgrade tier >= 5 | 10,000 |
| `nest_bounties_50` | Bounty Hunter | bounties >= 50 | 2,000 |
| `nest_bounties_100` | Elite Bounty Hunter | bounties >= 100 | 8,000 |

### New: Dragonpass
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `dragonpass_1` | Pass Graduate | completed >= 1 | 1,000 |
| `dragonpass_3` | Pass Veteran | completed >= 3 | 5,000 |
| `dragonpass_5` | Pass Legend | completed >= 5 | 15,000 |
| `dragonpass_10` | Pass Master | completed >= 10 | 50,000 |

*Tracked by counting rows in a new `dragonpass_completions (guild_id, user_id, completed_at)` table, incremented when a user reaches Dragonpass level 30.*

### New: Alpha Dragons
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `alpha_first` | Alpha Tamer | alphas >= 1 | 500 |
| `alpha_3` | Alpha Collector | alphas >= 3 | 2,000 |
| `alpha_5` | Alpha Commander | alphas >= 5 | 5,000 |
| `alpha_10` | Alpha Overlord | alphas >= 10 | 20,000 |

### New: Voting
| Key | Name | Threshold | Reward |
|---|---|---|---|
| `vote_first` | First Vote | total votes >= 1 | 200 |
| `vote_10` | Regular Voter | total votes >= 10 | 500 |
| `vote_50` | Dedicated Voter | total votes >= 50 | 2,000 |
| `vote_100` | Top Voter | total votes >= 100 | 10,000 |
| `vote_streak_7` | Weekly Supporter | streak >= 7 | 1,000 |
| `vote_streak_30` | Monthly Supporter | streak >= 30 | 5,000 |

---

## Database Changes

- `dragonpass_completions` table: `(guild_id, user_id, completed_at INTEGER)` — new log table, no unique constraint, multiple rows per user intentional (one row per completion). Achievement check uses `COUNT(*)` of rows for this user.
- `check_and_award_achievements` queries the user's current balance via `SELECT balance FROM users` when `event_type = 'balance'` to compare against thresholds; no new column needed.
- Alpha catch boost on Page 1 stats is derived from `SUM(catch_boost) FROM user_alphas` — no new column needed.
- No other schema changes; existing `user_achievements` table used for all tracking.

---

## Error Handling

- If spawn channel not found (deleted/unconfigured): skip notification silently, still award achievement + coins
- If achievement already earned: skip silently (idempotent)
- DB errors in `check_and_award_achievements`: catch exception, log, do not crash the calling event handler
