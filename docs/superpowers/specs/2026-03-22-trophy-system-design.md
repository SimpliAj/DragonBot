# Trophy System Expansion — Design Spec
Date: 2026-03-22

## Overview

Expand the existing trophy cosmetic system with:
1. Purchase limits on shop trophies (1x each)
2. Custom emoji IDs in /stats
3. New earned trophies (automatic, like achievements) with spawn-channel notifications

---

## Part 1: Shop Trophies (1x Purchase Limit)

### Existing: Server Trophy
- Price: 25,000 coins
- Emoji: custom ID 1485065649737826395
- Stored in: user_items table, item_type = 'server_trophy'
- Change: Block purchase if user_items.count >= 1 for this item_type

### New: Supporter Trophy
- Price: 50,000 coins
- Emoji: placeholder until custom ID provided
- Stored in: user_items table, item_type = 'supporter_trophy'
- Limit: Block purchase if user_items.count >= 1

### Where to add in economy.py
The shop flows through a modal. The actual deduction happens inside the modal's `on_submit` callback
inside the `elif category == 'consumable':` branch (around line 513-524).

Steps:
1. Add `consumable_supporter_trophy` entry to the `items_data` dict (same location as other items)
2. Add Supporter Trophy SelectOption to `categories['cosmetics']['options']`
3. Add Supporter Trophy line to `categories['cosmetics']['lines']`
4. Inside `on_submit`, inside the `consumable` branch, BEFORE calling `update_balance`,
   check if item in ('server_trophy', 'supporter_trophy'):
   - Query user_items for existing count
   - If count >= 1: respond with ephemeral error and return early
   - "You already own this trophy! Each trophy can only be purchased once."

---

## Part 2: Central Trophy Emoji Config (config.py)

Add TROPHY_EMOJIS dict:

```python
TROPHY_EMOJIS = {
    'server_trophy':      '<:server_trophy:1485065649737826395>',
    'supporter_trophy':   'placeholder',  # replace with <:name:ID> when available
    'quest_master':       '<:quest_master:1485066499012952115>',
    'nest_master':        'placeholder',
    'dragonpass_legend':  'placeholder',
    'dragon_scholar':     'placeholder',
    'raid_destroyer':     'placeholder',
    'dragon_millionaire': 'placeholder',
    'breeding_master':    'placeholder',
    'alpha_lord':         'placeholder',
    'mythic_hunter':      'placeholder',
}
```

Placeholders use standard emoji until custom IDs are provided.

---

## Part 3: Earned Trophies

### New DB Table (database.py)
Add inside init_db() after existing table creations:
```sql
CREATE TABLE IF NOT EXISTS user_trophies (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    trophy_id TEXT NOT NULL,
    earned_at INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, trophy_id)
)
```

### Trophy Definitions (config.py)
EARNED_TROPHIES dict with keys: name, description, icon (from TROPHY_EMOJIS).

Trophies:
- quest_master: Complete all 3 active Dragonpass quests in one refresh
- nest_master: Reach Dragon Nest level 10
- dragonpass_legend: Complete Dragonpass level 30
- dragon_scholar: Catch every dragon type at least once
- raid_destroyer: Land the killing blow on a raid boss (last attacker when HP reaches 0)
- dragon_millionaire: Reach a balance of 1,000,000 coins
- breeding_master: Reach breeding level 10 (milestone, not the absolute max which is 20)
- alpha_lord: Create 10 Alpha Dragons
- mythic_hunter: Catch a Mythic or Ultra dragon

### Award Function (achievements.py)
Add async award_trophy(bot, guild_id, user_id, trophy_id):
1. Check user_trophies — if already earned, return
2. Insert into user_trophies
3. Query guild_settings.spawn_channel
4. Send notification embed to spawn channel:
   - Title: "{emoji} Trophy Unlocked!"
   - Description: "{member} earned the {name} trophy!\n_{description}_"
   - Color: gold (0xF1C40F)

### Hook Points

| Trophy            | File                | Exact Hook Location                                                         |
|-------------------|---------------------|-----------------------------------------------------------------------------|
| nest_master       | cogs/dragon_nest.py | After nest level updated to 10 in submit_dragons handler                    |
| dragonpass_legend | utils.py            | Inside check_dragonpass_quests(), after Dragonpass level reaches 30         |
| dragon_scholar    | cogs/events.py      | After catch: if unique dragon count == len(DRAGON_TYPES)                    |
| raid_destroyer    | cogs/raids.py       | Inside `if new_hp <= 0:` block — btn_interaction.user.id is the last hitter |
| dragon_millionaire| database.py         | After update_balance: if new balance >= 1_000_000                           |
| breeding_master   | breeding handler    | After breeding level reaches 10                                             |
| alpha_lord        | alpha creation      | After user alpha count reaches 10                                           |
| mythic_hunter     | cogs/events.py      | After catch: if dragon rarity in ('mythic', 'ultra')                        |
| quest_master      | utils.py            | Inside check_dragonpass_quests(), inside `if completed_count >= 3:` block   |

---

## Part 4: /stats Display (Page 1)

Update build_page1() in cogs/dragons.py:

- Replace the existing scalar `trophy_count` query (cogs/dragons.py ~line 1704) with a full query:
  - Query user_items for shop trophies (server_trophy, supporter_trophy) where count > 0
  - Query user_trophies for all earned trophies for this user
- Combine into a list of (trophy_id, display_name) tuples
- If any trophies exist: add "Trophies" field rendering each as {TROPHY_EMOJIS[trophy_id]} {name}
- If no trophies: skip the field entirely

---

## Files Changed

| File                 | Change                                                                        |
|----------------------|-------------------------------------------------------------------------------|
| config.py            | Add TROPHY_EMOJIS, EARNED_TROPHIES dicts                                      |
| database.py          | Add user_trophies table in init_db()                                          |
| achievements.py      | Add award_trophy() function                                                   |
| cogs/economy.py      | Add items_data entry + SelectOption + 1x limit check for both shop trophies   |
| cogs/dragons.py      | Replace scalar trophy_count query; add Trophies field to Page 1               |
| cogs/events.py       | Hooks: dragon_scholar, mythic_hunter after catch                              |
| cogs/dragon_nest.py  | Hook: nest_master after level 10                                              |
| utils.py             | Hooks: quest_master + dragonpass_legend inside check_dragonpass_quests()      |
| cogs/raids.py        | Hook: raid_destroyer inside if new_hp <= 0 block                              |
| database.py          | Hook: dragon_millionaire after update_balance if balance >= 1_000_000         |
| breeding handler     | Hook: breeding_master after level 10                                          |
| alpha creation       | Hook: alpha_lord after 10th alpha created                                     |
