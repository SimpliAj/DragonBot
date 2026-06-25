# Trophy System Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 1x purchase limits on shop trophies, a Supporter Trophy, 9 earned trophies with auto-notifications, and display all trophies in /stats Page 1.

**Architecture:** Central emoji/definition config in config.py; `award_trophy()` in achievements.py; new `user_trophies` DB table; hooks at existing trigger points across multiple files.

**Tech Stack:** Python, discord.py 2.x, SQLite

---

### Task 1: Config — TROPHY_EMOJIS + EARNED_TROPHIES + supporter_trophy item

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add TROPHY_EMOJIS and EARNED_TROPHIES dicts to config.py**

Find the end of the ACHIEVEMENTS dict in `config.py` and add after it:

```python
# ==================== TROPHY CONFIG ====================
TROPHY_EMOJIS = {
    'server_trophy':      '<:server_trophy:1485065649737826395>',
    'supporter_trophy':   '🎖️',        # replace with <:name:ID> when custom emoji is ready
    'quest_master':       '<:quest_master:1485066499012952115>',
    'nest_master':        '🏰',        # replace with <:name:ID> when custom emoji is ready
    'dragonpass_legend':  '🎫',        # replace with <:name:ID> when custom emoji is ready
    'dragon_scholar':     '🐉',        # replace with <:name:ID> when custom emoji is ready
    'raid_destroyer':     '⚔️',        # replace with <:name:ID> when custom emoji is ready
    'dragon_millionaire': '💰',        # replace with <:name:ID> when custom emoji is ready
    'breeding_master':    '🥚',        # replace with <:name:ID> when custom emoji is ready
    'alpha_lord':         '✨',        # replace with <:name:ID> when custom emoji is ready
    'mythic_hunter':      '🌟',        # replace with <:name:ID> when custom emoji is ready
}

EARNED_TROPHIES = {
    'quest_master': {
        'name': 'Quest Master',
        'description': 'Complete all 3 active Dragonpass quests in one refresh',
        'icon': TROPHY_EMOJIS['quest_master'],
    },
    'nest_master': {
        'name': 'Nest Master',
        'description': 'Reach Dragon Nest level 10',
        'icon': TROPHY_EMOJIS['nest_master'],
    },
    'dragonpass_legend': {
        'name': 'Dragonpass Legend',
        'description': 'Complete Dragonpass level 30',
        'icon': TROPHY_EMOJIS['dragonpass_legend'],
    },
    'dragon_scholar': {
        'name': 'Dragon Scholar',
        'description': 'Catch every dragon type at least once',
        'icon': TROPHY_EMOJIS['dragon_scholar'],
    },
    'raid_destroyer': {
        'name': 'Raid Destroyer',
        'description': 'Land the killing blow on a raid boss',
        'icon': TROPHY_EMOJIS['raid_destroyer'],
    },
    'dragon_millionaire': {
        'name': 'Dragon Millionaire',
        'description': 'Reach a balance of 1,000,000 coins',
        'icon': TROPHY_EMOJIS['dragon_millionaire'],
    },
    'breeding_master': {
        'name': 'Breeding Master',
        'description': 'Reach breeding level 10',
        'icon': TROPHY_EMOJIS['breeding_master'],
    },
    'alpha_lord': {
        'name': 'Alpha Lord',
        'description': 'Create 10 Alpha Dragons',
        'icon': TROPHY_EMOJIS['alpha_lord'],
    },
    'mythic_hunter': {
        'name': 'Mythic Hunter',
        'description': 'Catch a Mythic or Ultra dragon',
        'icon': TROPHY_EMOJIS['mythic_hunter'],
    },
}
```

Also add `supporter_trophy` to the existing `ITEMS` dict (near `server_trophy` around line 421):

```python
'supporter_trophy': {
    'name': 'Supporter Trophy', 'emoji': '🎖️', 'rarity': 'legendary',
    'description': 'Cosmetic — displayed in your /stats profile',
    'shop_cost': 50000,
},
```

- [ ] **Step 2: Verify**

```bash
cd /home/drachenbot && python3 -c "from config import TROPHY_EMOJIS, EARNED_TROPHIES; print('OK', len(EARNED_TROPHIES))"
```
Expected: `OK 9`

---

### Task 2: Database — user_trophies table

**Files:**
- Modify: `database.py`

- [ ] **Step 1: Add table creation inside init_db()**

After the `dragonpass_completions` CREATE TABLE block and before `conn.commit()`:

```python
c.execute('''CREATE TABLE IF NOT EXISTS user_trophies (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    trophy_id TEXT NOT NULL,
    earned_at INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, trophy_id)
)''')
```

- [ ] **Step 2: Verify**

```bash
cd /home/drachenbot && python3 -c "from database import init_db; init_db(); import sqlite3; c=sqlite3.connect('dragon_bot.db').cursor(); c.execute(\"SELECT name FROM sqlite_master WHERE name='user_trophies'\"); print(c.fetchone())"
```
Expected: `('user_trophies',)`

---

### Task 3: award_trophy() function in achievements.py

**Files:**
- Modify: `achievements.py`

- [ ] **Step 1: Update config import line**

Change:
```python
from config import ACHIEVEMENTS, DRAGON_RARITY_TIERS
```
to:
```python
from config import ACHIEVEMENTS, DRAGON_RARITY_TIERS, EARNED_TROPHIES, TROPHY_EMOJIS
```

- [ ] **Step 2: Add award_trophy() function before check_and_award_achievements**

```python
async def award_trophy(bot: discord.Client, guild_id: int, user_id: int, trophy_id: str):
    """Award an earned trophy if not already owned. Sends notification to spawn channel."""
    trophy = EARNED_TROPHIES.get(trophy_id)
    if not trophy:
        return

    try:
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute(
            'SELECT 1 FROM user_trophies WHERE guild_id = ? AND user_id = ? AND trophy_id = ?',
            (guild_id, user_id, trophy_id),
        )
        if c.fetchone():
            conn.close()
            return  # already earned

        c.execute(
            'INSERT INTO user_trophies (guild_id, user_id, trophy_id, earned_at) VALUES (?, ?, ?, ?)',
            (guild_id, user_id, trophy_id, int(time.time())),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f'award_trophy DB error: {e}')
        return

    if not bot:
        return

    try:
        conn2 = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c2 = conn2.cursor()
        c2.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
        row = c2.fetchone()
        conn2.close()
        if not row or not row[0]:
            return

        channel = bot.get_channel(row[0])
        if not channel:
            return

        member = channel.guild.get_member(user_id)
        display_name = member.display_name if member else f'<@{user_id}>'
        emoji = trophy['icon']

        embed = discord.Embed(
            title=f'{emoji} Trophy Unlocked!',
            description=f'**{display_name}** earned the **{trophy["name"]}** trophy!\n\n_{trophy["description"]}_',
            color=0xF1C40F,
        )
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f'award_trophy notification error: {e}')
```

- [ ] **Step 3: Verify**

```bash
cd /home/drachenbot && python3 -c "from achievements import award_trophy; print('OK')"
```
Expected: `OK`

---

### Task 4: Shop — 1x purchase limit + Supporter Trophy in economy.py

**Files:**
- Modify: `cogs/economy.py`

- [ ] **Step 1: Add Supporter Trophy to items_data dict (around line 192)**

After `'consumable_server_trophy'` entry:
```python
'consumable_supporter_trophy':   {'name': 'Supporter Trophy',   'price': 50000,  'emoji': '🎖️'},
```

- [ ] **Step 2: Update cosmetics category (around line 290)**

```python
'lines': [
    '🥇 **Server Trophy** — 25,000 🪙',
    '   └─ Displayed as trophies in your `/stats` profile (limit: 1)',
    '🎖️ **Supporter Trophy** — 50,000 🪙',
    '   └─ Exclusive supporter cosmetic in your `/stats` profile (limit: 1)',
],
'options': [
    discord.SelectOption(label="Server Trophy",    description="25,000 🪙 - Shown in /stats (limit: 1)", emoji="🥇", value="consumable_server_trophy"),
    discord.SelectOption(label="Supporter Trophy", description="50,000 🪙 - Shown in /stats (limit: 1)", emoji="🎖️", value="consumable_supporter_trophy"),
],
```

- [ ] **Step 3: Add 1x limit check and supporter_trophy hint in consumable handler**

Find `elif category == 'consumable':` (around line 513).

Add `supporter_trophy` to `consumable_hints`:
```python
'supporter_trophy': "Displayed as a trophy in your `/stats` profile!",
```

BEFORE `await asyncio.to_thread(update_balance, ...)`, add:
```python
# Enforce 1x purchase limit for shop trophies
if item in ('server_trophy', 'supporter_trophy'):
    try:
        _conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        _c = _conn.cursor()
        _c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                   (interaction.guild_id, modal_interaction.user.id, item))
        _row = _c.fetchone()
        _conn.close()
        if _row and _row[0] >= 1:
            await modal_interaction.response.send_message(
                '❌ You already own this trophy! Each trophy can only be purchased once.',
                ephemeral=True,
            )
            return
    except Exception:
        pass
```

- [ ] **Step 4: Verify**

```bash
cd /home/drachenbot && python3 -c "import cogs.economy; print('OK')"
```

---

### Task 5: /stats Page 1 — Trophies field in cogs/dragons.py

**Files:**
- Modify: `cogs/dragons.py`

- [ ] **Step 1: Add TROPHY_EMOJIS + EARNED_TROPHIES to imports**

Find the `from config import ...` line at top of `cogs/dragons.py`. Add `TROPHY_EMOJIS, EARNED_TROPHIES`.

- [ ] **Step 2: Replace existing trophy_count query (~line 1704) with full trophy queries**

Find and replace:
```python
# Get Server Trophy count
c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
          (guild_id, user_id, 'server_trophy'))
trophy_result = c.fetchone()
trophy_count = trophy_result[0] if trophy_result else 0
```

With:
```python
# Get all trophies (shop + earned)
_shop_trophy_types = ['server_trophy', 'supporter_trophy']
shop_trophies = []
for _t in _shop_trophy_types:
    c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
              (guild_id, user_id, _t))
    _r = c.fetchone()
    if _r and _r[0] > 0:
        shop_trophies.append(_t)

c.execute('SELECT trophy_id FROM user_trophies WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
earned_trophies_list = [row[0] for row in c.fetchall()]

all_trophy_ids = shop_trophies + earned_trophies_list
```

- [ ] **Step 3: Add Trophies field to build_page1()**

Inside `build_page1()`, before `e.set_footer(text="Page 1/3")`, add:

```python
if all_trophy_ids:
    _shop_names = {'server_trophy': 'Server Trophy', 'supporter_trophy': 'Supporter Trophy'}
    trophy_display = '  '.join(
        f"{TROPHY_EMOJIS.get(tid, '🏆')} **{EARNED_TROPHIES[tid]['name'] if tid in EARNED_TROPHIES else _shop_names.get(tid, tid)}**"
        for tid in all_trophy_ids
    )
    e.add_field(name='🏆 Trophies', value=trophy_display, inline=False)
```

- [ ] **Step 4: Verify**

```bash
cd /home/drachenbot && python3 -c "import cogs.dragons; print('OK')"
```

---

### Task 6: Hook — nest_master (cogs/dragon_nest.py)

**Files:**
- Modify: `cogs/dragon_nest.py`

- [ ] **Step 1: Add import**

```python
from achievements import award_trophy
```

- [ ] **Step 2: Add hook after level 10 is confirmed**

In the `submit_dragons` handler, after the DB commit that sets the new nest level and after reading `current_level` from DB, add:

```python
if current_level == 10:
    await award_trophy(btn_interaction.client, self.guild_id, self.user_id, 'nest_master')
```

- [ ] **Step 3: Verify**

```bash
cd /home/drachenbot && python3 -c "import cogs.dragon_nest; print('OK')"
```

---

### Task 7: Hook — raid_destroyer (cogs/raids.py)

**Files:**
- Modify: `cogs/raids.py`

- [ ] **Step 1: Add import**

```python
from achievements import award_trophy
```

- [ ] **Step 2: Add hook inside the killing-blow block**

Find `if new_hp <= 0:` (around line 929). The user whose button triggered this is `btn_interaction.user.id`. Add right after the `if new_hp <= 0:` line:

```python
await award_trophy(btn_interaction.client, btn_interaction.guild_id, btn_interaction.user.id, 'raid_destroyer')
```

- [ ] **Step 3: Verify**

```bash
cd /home/drachenbot && python3 -c "import cogs.raids; print('OK')"
```

---

### Task 8: Hook — dragon_scholar + mythic_hunter + dragon_millionaire (cogs/events.py)

**Files:**
- Modify: `cogs/events.py`

Note: `on_message` runs inside `EventsCog`. The bot is available as `self.bot`.

- [ ] **Step 1: Add imports at top of cogs/events.py**

```python
from achievements import award_trophy
from database import update_balance_and_check_trophies
```

(The `update_balance_and_check_trophies` function is added in Task 10 — implement Task 10 first if running sequentially, or add the import here and it will resolve once Task 10 is done.)

- [ ] **Step 2: Add trophy checks after successful catch**

After a dragon is successfully caught and the DB is updated, find the section in `on_message` where the dragon type and rarity are known. Add:

```python
# Trophy checks
_dragon_data = DRAGON_TYPES.get(spawn_data['dragon_type'], {})
_rarity = _dragon_data.get('rarity', '')

if _rarity in ('mythic', 'ultra'):
    await award_trophy(self.bot, guild_id, message.author.id, 'mythic_hunter')

_conn_s = sqlite3.connect('dragon_bot.db', timeout=120.0)
_c_s = _conn_s.cursor()
_c_s.execute('SELECT COUNT(*) FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
             (guild_id, message.author.id))
_unique = _c_s.fetchone()[0]
_conn_s.close()
if _unique >= len(DRAGON_TYPES):
    await award_trophy(self.bot, guild_id, message.author.id, 'dragon_scholar')
```

- [ ] **Step 3: Replace update_balance call for coin reward with trophy-aware version**

Find the `await asyncio.to_thread(update_balance, guild_id, message.author.id, coin_reward)` call for the dragon catch coin reward. Replace with:

```python
await update_balance_and_check_trophies(self.bot, guild_id, message.author.id, coin_reward)
```

- [ ] **Step 4: Verify**

```bash
cd /home/drachenbot && python3 -c "import cogs.events; print('OK')"
```

---

### Task 9: Hook — dragon_millionaire helper (database.py)

**Files:**
- Modify: `database.py`

- [ ] **Step 1: Add async helper after update_balance (around line 835)**

```python
async def update_balance_and_check_trophies(bot, guild_id: int, user_id: int, amount: float):
    """Update balance then check dragon_millionaire trophy on gains."""
    import asyncio
    await asyncio.to_thread(update_balance, guild_id, user_id, amount)
    if amount <= 0:
        return
    try:
        conn = sqlite3.connect(DB_PATH, timeout=60.0)
        c = conn.cursor()
        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        conn.close()
        if row and row[0] >= 1_000_000:
            from achievements import award_trophy
            await award_trophy(bot, guild_id, user_id, 'dragon_millionaire')
    except Exception:
        pass
```

- [ ] **Step 2: Verify**

```bash
cd /home/drachenbot && python3 -c "from database import update_balance_and_check_trophies; print('OK')"
```

---

### Task 10: Hook — quest_master + dragonpass_legend (utils.py + bot.py duplicate)

**Files:**
- Modify: `utils.py`
- Modify: `bot.py` (duplicate copy of check_dragonpass_quests)

**Important:** There are TWO copies of `check_dragonpass_quests`:
1. `utils.py:341` — used by callers in `cogs/`
2. `bot.py:2112` — used by callers inside `bot.py`

Both must be updated identically.

- [ ] **Step 1: Update utils.py — fix early return and add trophies return**

In `utils.py`, find the early return `return 0, 0` (around line 403, the `needs_quest_regen` path). Change to:
```python
return 0, 0, []
```

Find the normal return at line 479:
```python
return coins_gained, new_level - current_level
```
Replace with:
```python
trophies_to_award = []
if completed_count >= 3 and coins_gained > 0:
    trophies_to_award.append('quest_master')
if new_level == 30 and current_level < 30:
    trophies_to_award.append('dragonpass_legend')
return coins_gained, new_level - current_level, trophies_to_award
```

Also change the error return `return None` to stay as `return None` (callers already guard with `if result:`).

- [ ] **Step 2: Make identical changes in bot.py copy (around line 2112)**

Find the duplicate `check_dragonpass_quests` function in `bot.py`. Apply exactly the same two changes (early return `→ return 0, 0, []` and normal return `→ 3-tuple with trophies_to_award`).

- [ ] **Step 3: Update all callers to handle the 3-tuple**

Run:
```bash
grep -n "check_dragonpass_quests" /home/drachenbot/bot.py /home/drachenbot/cogs/events.py /home/drachenbot/utils.py
```

For every call site, update the result handling. Two patterns exist:

**Pattern A — 2-tuple unpack:**
```python
coins, level_delta = check_dragonpass_quests(...)
```
Change to:
```python
result = check_dragonpass_quests(...)
if result:
    coins, level_delta, trophies = result
    for _tid in trophies:
        await award_trophy(bot_ref, guild_id, user_id, _tid)
```

**Pattern B — index access:**
```python
if result and result[1] > 0:
```
Change to:
```python
if result and len(result) >= 2 and result[1] > 0:
    for _tid in (result[2] if len(result) > 2 else []):
        await award_trophy(bot_ref, guild_id, user_id, _tid)
```

For `bot_ref`, use whatever bot object is in scope:
- In `EventsCog.on_message`: use `self.bot`
- In `bot.py` functions: use `bot` (the global bot instance)
- In `interaction` handlers: use `interaction.client`

- [ ] **Step 4: Verify**

```bash
cd /home/drachenbot && python3 -c "from utils import check_dragonpass_quests; print('OK')"
```

---

### Task 11: Hook — alpha_lord (bot.py) + breeding_master (cogs/breeding.py + bot.py)

**Files:**
- Modify: `bot.py` (alpha creation ~line 13083, breeding ~lines 16822, 17361)
- Modify: `cogs/breeding.py` (~lines 355, 367)

- [ ] **Step 1: Add award_trophy import to bot.py**

Find the imports at the top of `bot.py`. Add:
```python
from achievements import award_trophy
```

- [ ] **Step 2: alpha_lord hook in bot.py**

Find line 13083 where `check_and_award_achievements` is called after alpha INSERT. `new_count` is set just above (line 13066). Add AFTER the existing `check_and_award_achievements` call:

```python
if new_count >= 10:
    await award_trophy(bot, interaction.guild_id, interaction.user.id, 'alpha_lord')
```

- [ ] **Step 3: breeding_master hook in bot.py**

For each `xp_result = add_breeding_xp(...)` call in `bot.py` (~lines 16810, 16822, 17333, 17361), add after:

```python
if xp_result and xp_result.get('new_level') == 10:
    await award_trophy(bot, guild_id, user_id, 'breeding_master')
```

Use the correct `guild_id`/`user_id` variables in scope at each call site. For interaction-based handlers, these are `interaction.guild_id` and `interaction.user.id`.

- [ ] **Step 4: breeding_master hook in cogs/breeding.py**

For each `xp_result = add_breeding_xp(...)` call in `cogs/breeding.py` (~lines 355, 367), add after:

```python
if xp_result and xp_result.get('new_level') == 10:
    await award_trophy(inter4.client, inter4.guild_id, inter4.user.id, 'breeding_master')
```

Note: Use `inter4.client` (discord.py 2.x) — NOT `self.bot` which is not in scope at those call sites.

Also add import at top of `cogs/breeding.py`:
```python
from achievements import award_trophy
```

- [ ] **Step 5: Verify**

```bash
cd /home/drachenbot && python3 -c "import cogs.breeding; print('OK')"
```

---

### Final Verification

- [ ] **Restart bot and check for errors**

```bash
pm2 restart drachenbot && sleep 8 && tail -25 /root/.pm2/logs/drachenbot-error.log
```
Expected: No `ImportError`, `ModuleNotFoundError`, or `SyntaxError`.

- [ ] **Test: buy Server Trophy twice — second purchase blocked**

In Discord: `/shop` → Cosmetics → Server Trophy (buy once, then try again).
Expected: second attempt shows "❌ You already own this trophy!"

- [ ] **Test: /stats Page 1 shows Trophies field after owning a trophy**
