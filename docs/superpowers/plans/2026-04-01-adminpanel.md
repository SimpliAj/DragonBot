# /adminpanel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/adminpanel` command in `cogs/adminpanel.py` that gives server administrators (and DEV_USER_ID) a guild-scoped management panel with Give, Reset, Spawn, and Info sections.

**Architecture:** New standalone cog `cogs/adminpanel.py` — no changes to `devpanel.py` or `admin.py`. Reuses modals from `devpanel.py` directly. All operations hard-coded to `interaction.guild_id`; no cross-guild capability. `clearevents` is implemented directly in this file (not via `_run`) since the existing `handle_dev_command` version is global.

**Tech Stack:** discord.py (`discord.ui.View`, `discord.ui.Modal`, `app_commands`), sqlite3, existing `_run()` helper from `devpanel.py`, state dicts from `state.py`

---

## File Map

| File | Action | What changes |
|---|---|---|
| `cogs/adminpanel.py` | **Create** | Full new cog with all views, modals, and the `/adminpanel` command |
| `main.py` | **Modify** | Add `'cogs.adminpanel'` to the `extensions` list |

---

### Task 1: Create `cogs/adminpanel.py` — skeleton + access check

**Files:**
- Create: `cogs/adminpanel.py`

- [ ] **Step 1: Create the file with imports and the bare command**

```python
"""
cogs/adminpanel.py - /adminpanel slash command (server admins + DEV_USER_ID).
Guild-scoped only — all operations affect the current server exclusively.
"""

import sqlite3
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import DEV_USER_ID, DRAGON_TYPES, PACK_TYPES
from state import (
    active_dragonfest, active_dragonscales, raid_boss_active,
)

# Reuse modals from devpanel — they have no guild-switching logic
from cogs.devpanel import (
    _run,
    GiveCoinsAmountModal,
    GiveDragonsAmountModal,
    DragonFestModal,
    SpawnRaidModal,
    ResetUserModal,
    FixSoftlockModal,
    _DRAGON_OPTIONS,
    _PACK_OPTIONS,
    _MINUTES_OPTIONS,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == DEV_USER_ID
    )


def _main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Admin Panel",
        description="Manage your server. Select a category below.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="🎁 Give",   value="Coins, packs, dragonscale, dragons, giveaway", inline=False)
    embed.add_field(name="🔄 Reset",  value="Quests, breed cooldown, adventure CD, bingo", inline=False)
    embed.add_field(name="⚔️ Spawn",  value="Dragonfest, raid boss, black market, kill raid", inline=False)
    embed.add_field(name="📊 Info",   value="Spawn status, raid info, fix softlock, clear events", inline=False)
    return embed


class AdminPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="adminpanel", description="Server admin control panel")
    async def adminpanel(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ Access denied.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_main_embed(), view=AdminPanelView(self.bot), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminPanelCog(bot))
```

- [ ] **Step 2: Register the cog in `main.py`**

In `main.py`, add `'cogs.adminpanel'` to the `extensions` list after `'cogs.devpanel'`:

```python
        extensions = [
            'cogs.tasks',
            'cogs.events',
            'cogs.admin',
            'cogs.topgg',
            'cogs.devpanel',
            'cogs.adminpanel',   # ← add this line
            'cogs.economy',
            ...
        ]
```

- [ ] **Step 3: Add stub `AdminPanelView` so the bot starts without errors**

Add this class to `cogs/adminpanel.py` before `AdminPanelCog`:

```python
class AdminPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot
```

- [ ] **Step 4: Start the bot and verify `/adminpanel` exists and access control works**

Start: `python main.py`

Expected:
- `/adminpanel` appears in Discord slash command list
- A non-admin user gets `❌ Access denied.`
- An admin user gets the embed with 4 fields (Give, Reset, Spawn, Info) — no buttons yet

---

### Task 2: Give category

**Files:**
- Modify: `cogs/adminpanel.py`

All Give views use `interaction.guild_id` — no "Change Guild" button anywhere.

- [ ] **Step 1: Add `AdminGiveCoinsView`**

```python
class AdminGiveCoinsView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        await interaction.response.send_modal(GiveCoinsAmountModal(self.bot, select.values[0]))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))
```

- [ ] **Step 2: Add `AdminGiveDragonsView`**

```python
class AdminGiveDragonsView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot
        self.selected_user = None
        self.selected_dragon = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_user = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select dragon type…", options=_DRAGON_OPTIONS, row=1)
    async def dragon_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_dragon = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Give", emoji="🐉", style=discord.ButtonStyle.primary, row=2)
    async def give(self, interaction: discord.Interaction, _):
        if not self.selected_user or not self.selected_dragon:
            await interaction.response.send_message("❌ Select a user and dragon type first.", ephemeral=True)
            return
        await interaction.response.send_modal(
            GiveDragonsAmountModal(self.bot, self.selected_user, self.selected_dragon))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))
```

- [ ] **Step 3: Add `AdminGivePackModal` and `AdminGivePackView`**

```python
class AdminGivePackModal(discord.ui.Modal, title="Give Pack"):
    amount = discord.ui.TextInput(label="Amount", placeholder="e.g. 3")

    def __init__(self, bot, guild_id: int, user, pack_type: str):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.user = user
        self.pack_type = pack_type

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'givepack',
                       [str(self.guild_id), str(self.user.id),
                        self.pack_type, self.amount.value])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class AdminGivePackView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_user = None
        self.selected_pack = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_user = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select pack type…", options=_PACK_OPTIONS, row=1)
    async def pack_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_pack = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Give", emoji="📦", style=discord.ButtonStyle.primary, row=2)
    async def give(self, interaction: discord.Interaction, _):
        if not self.selected_user or not self.selected_pack:
            await interaction.response.send_message("❌ Select a user and pack type first.", ephemeral=True)
            return
        await interaction.response.send_modal(
            AdminGivePackModal(self.bot, self.guild_id, self.selected_user, self.selected_pack))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=3)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))
```

- [ ] **Step 4: Add `AdminGiveDragonscaleView`**

```python
class AdminGiveDragonscaleView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_user = None
        self.selected_minutes = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_user = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select duration…", options=_MINUTES_OPTIONS, row=1)
    async def minutes_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_minutes = int(select.values[0])
        await interaction.response.defer()

    @discord.ui.button(label="Give Dragonscale", emoji="🟪", style=discord.ButtonStyle.primary, row=2)
    async def give(self, interaction: discord.Interaction, _):
        if not self.selected_user or not self.selected_minutes:
            await interaction.response.send_message("❌ Select a user and duration first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()
            c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                      (self.guild_id, self.selected_user.id))
            row = c.fetchone()
            if row:
                c.execute('UPDATE dragonscales SET minutes = minutes + ? WHERE guild_id = ? AND user_id = ?',
                          (self.selected_minutes, self.guild_id, self.selected_user.id))
            else:
                c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?)',
                          (self.guild_id, self.selected_user.id, self.selected_minutes))
            conn.commit()
            conn.close()
            mins = self.selected_minutes
            label = f"{mins}m" if mins < 60 else f"{mins // 60}h" + (f" {mins % 60}m" if mins % 60 else "")
            await interaction.followup.send(
                f"✅ Gave **{label}** of Dragonscale 🟪 to {self.selected_user.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=3)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))
```

- [ ] **Step 5: Add `AdminGiveView` (Give submenu)**

```python
class AdminGiveView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Give Coins", emoji="🪙", style=discord.ButtonStyle.primary)
    async def give_coins(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🪙 Give Coins", color=discord.Color.gold()),
            view=AdminGiveCoinsView(self.bot))

    @discord.ui.button(label="Give Dragons", emoji="🐉", style=discord.ButtonStyle.primary)
    async def give_dragons(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🐉 Give Dragons", color=discord.Color.green()),
            view=AdminGiveDragonsView(self.bot))

    @discord.ui.button(label="Give Pack", emoji="📦", style=discord.ButtonStyle.primary)
    async def give_pack(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="📦 Give Pack", color=discord.Color.blue()),
            view=AdminGivePackView(self.bot, interaction.guild_id))

    @discord.ui.button(label="Give Dragonscale", emoji="🟪", style=discord.ButtonStyle.primary)
    async def give_dragonscale(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🟪 Give Dragonscale", color=discord.Color.purple()),
            view=AdminGiveDragonscaleView(self.bot, interaction.guild_id))

    @discord.ui.button(label="Giveaway", emoji="🎁", style=discord.ButtonStyle.secondary)
    async def giveaway(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'giveaway', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))
```

- [ ] **Step 6: Wire Give button into `AdminPanelView`**

Replace the stub `AdminPanelView` with:

```python
class AdminPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @discord.ui.button(label="🎁 Give", style=discord.ButtonStyle.primary)
    async def give(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))
```

(The remaining category buttons — Reset, Spawn, Info — will be added in Tasks 3–5.)

- [ ] **Step 7: Verify Give works**

Restart bot. Open `/adminpanel` → click Give → test each sub-action:
- Give Coins: select user → enter amount → ✅ confirmation
- Give Dragons: select user + type → enter amount → ✅ confirmation
- Give Pack: select user + pack → enter amount → ✅ confirmation (no "Change Guild" button visible)
- Give Dragonscale: select user + duration → ✅ confirmation (no "Change Guild" button visible)
- Giveaway: fires giveaway in server ✅
- ← Back returns to main menu ✅

---

### Task 3: Reset category

**Files:**
- Modify: `cogs/adminpanel.py`

- [ ] **Step 1: Add `AdminResetView`**

```python
class AdminResetView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Reset Quests", emoji="📋", style=discord.ButtonStyle.danger)
    async def reset_quests(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'resetquests', [])

    @discord.ui.button(label="Reset Breed CD", emoji="⏱️", style=discord.ButtonStyle.secondary)
    async def reset_breed_cd(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            ResetUserModal(self.bot, 'resetbreedcooldown', 'Reset Breed Cooldown'))

    @discord.ui.button(label="Reset Adventure CD", emoji="🗺️", style=discord.ButtonStyle.secondary)
    async def reset_adventure_cd(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            ResetUserModal(self.bot, 'resetadventurecd', 'Reset Adventure Cooldowns'))

    @discord.ui.button(label="Reset Bingo", emoji="🎯", style=discord.ButtonStyle.danger)
    async def reset_bingo(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'resetbingo', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))
```

- [ ] **Step 2: Add Reset button to `AdminPanelView`**

Add inside `AdminPanelView`:

```python
    @discord.ui.button(label="🔄 Reset", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🔄 Reset", color=discord.Color.orange()),
            view=AdminResetView(self.bot))
```

- [ ] **Step 3: Verify Reset works**

Restart bot. Open `/adminpanel` → Reset:
- Reset Quests: confirms `X users` reset ✅
- Reset Breed CD: enter user ID → ✅
- Reset Adventure CD: enter user ID → ✅
- Reset Bingo: confirms deleted bingo cards ✅
- ← Back works ✅

---

### Task 4: Spawn category

**Files:**
- Modify: `cogs/adminpanel.py`

- [ ] **Step 1: Add `AdminSpawnView`**

```python
class AdminSpawnView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Dragonfest", emoji="🎉", style=discord.ButtonStyle.primary)
    async def dragonfest(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(DragonFestModal(self.bot))

    @discord.ui.button(label="Spawn Raid Boss", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def spawn_raid(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(SpawnRaidModal(self.bot))

    @discord.ui.button(label="Spawn Black Market", emoji="🏴‍☠️", style=discord.ButtonStyle.primary)
    async def spawn_bm(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'spawnblackmarket', [])

    @discord.ui.button(label="Kill Raid Boss", emoji="💀", style=discord.ButtonStyle.danger)
    async def kill_raid(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'raidkill', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))
```

- [ ] **Step 2: Add Spawn button to `AdminPanelView`**

```python
    @discord.ui.button(label="⚔️ Spawn", style=discord.ButtonStyle.primary)
    async def spawn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="⚔️ Spawn", color=discord.Color.red()),
            view=AdminSpawnView(self.bot))
```

- [ ] **Step 3: Verify Spawn works**

Restart bot. Open `/adminpanel` → Spawn:
- Dragonfest: enter minutes → event starts in server ✅
- Spawn Raid Boss: enter hours (optional) → raid boss appears ✅
- Spawn Black Market → black market spawns ✅
- Kill Raid Boss → active raid ends ✅
- ← Back works ✅

---

### Task 5: Info category (including guild-scoped Clear Events)

**Files:**
- Modify: `cogs/adminpanel.py`

- [ ] **Step 1: Add `AdminInfoView` with guild-scoped `clear_events`**

```python
class AdminInfoView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Spawn Status", emoji="🔍", style=discord.ButtonStyle.secondary)
    async def spawn_status(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'spawnstatus', [])

    @discord.ui.button(label="Raid Info", emoji="⚔️", style=discord.ButtonStyle.secondary)
    async def raid_info(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'raidinfo', [])

    @discord.ui.button(label="Fix Softlock", emoji="🔓", style=discord.ButtonStyle.primary)
    async def fix_softlock(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(FixSoftlockModal(self.bot))

    @discord.ui.button(label="Clear Events", emoji="🧹", style=discord.ButtonStyle.danger)
    async def clear_events(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        current_time = int(time.time())
        try:
            # Clear in-memory state for this guild only
            active_dragonfest.pop(gid, None)
            active_dragonscales.pop(gid, None)
            raid_boss_active.pop(gid, None)

            # Clear DB entries for this guild only
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()
            c.execute('DELETE FROM dragonfest_stats WHERE guild_id = ?', (gid,))
            c.execute('DELETE FROM dragonscale_stats WHERE guild_id = ?', (gid,))
            c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (gid,))
            c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (gid,))
            c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                      (current_time, gid))
            conn.commit()
            conn.close()

            await interaction.followup.send(
                "🧹 **Events cleared** for this server.\n"
                "✅ Dragonfest, dragonscale events, and raid boss removed.",
                ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))
```

- [ ] **Step 2: Add Info button to `AdminPanelView`**

```python
    @discord.ui.button(label="📊 Info", style=discord.ButtonStyle.secondary)
    async def info(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="📊 Info", color=discord.Color.blue()),
            view=AdminInfoView(self.bot))
```

- [ ] **Step 3: Verify Info works**

Restart bot. Open `/adminpanel` → Info:
- Spawn Status → shows current spawn info for this server ✅
- Raid Info → shows raid info ✅
- Fix Softlock → enter user ID → fixes softlock ✅
- Clear Events → clears only this server's events (verify other guilds are unaffected) ✅
- ← Back works ✅

---

### Task 6: Final check — non-admin access

**Files:** none

- [ ] **Step 1: Verify access control**

As a user WITHOUT administrator permission (and not DEV_USER_ID):
- Run `/adminpanel` → should receive `❌ Access denied.` (ephemeral) and nothing else ✅

- [ ] **Step 2: Verify all "← Back" buttons return to the correct main menu embed**

Navigate through each category and click ← Back — should always return to the "⚙️ Admin Panel" embed with all 4 category fields ✅
