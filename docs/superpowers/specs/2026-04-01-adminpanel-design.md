# /adminpanel Design Spec
Date: 2026-04-01

## Overview

New `/adminpanel` slash command for server administrators. Lets admins manage their own server via an interactive Discord UI. Entirely separate from `/devpanel` (which remains DEV_USER_ID-only).

## Access Control

- Allowed: `interaction.user.guild_permissions.administrator` OR `interaction.user.id == DEV_USER_ID`
- Denied: everyone else → ephemeral "❌ Access denied."
- Scope: always `interaction.guild_id` — no cross-guild operations, no "Change Guild" button

## Implementation

**New file:** `cogs/adminpanel.py`  
**No changes** to `devpanel.py` or `admin.py`.

Reuse modals from `devpanel.py` where they have no guild-switching logic:
- `GiveCoinsAmountModal`, `GiveDragonsAmountModal`, `GrantPassLevelsModal`, `ResetUserModal`, `DragonFestModal`, `SpawnRaidModal`, `FixSoftlockModal`

Create guild-locked versions (no "Change Guild" button) for:
- `AdminGivePackView` — like `GivePackView` but guild_id = interaction.guild_id, no change-guild button
- `AdminGiveDragonscaleView` — like `GiveDragonscaleView` but guild_id = interaction.guild_id, no change-guild button

All `_run()` calls use `interaction.guild_id` implicitly via `FakeMessage.guild`.

## Categories & Actions

### 🎁 Give
| Action | Modal/Mechanism |
|---|---|
| Give Coins | UserSelect → `GiveCoinsAmountModal` |
| Give Pack | UserSelect + PackSelect → amount modal (guild-locked) |
| Give Dragonscale | UserSelect + duration select (guild-locked) |
| Give Dragons | UserSelect + DragonSelect → amount modal |
| Giveaway | Direct `_run('giveaway', [])` |

### 🔄 Reset
| Action | Modal/Mechanism |
|---|---|
| Reset Quests | Direct `_run('resetquests', [])` — resets all users in guild |
| Reset Breed Cooldown | `ResetUserModal` → `resetbreedcooldown` |
| Reset Adventure CD | `ResetUserModal` → `resetadventurecd` |
| Reset Bingo | Direct `_run('resetbingo', [])` |

### ⚔️ Spawn
| Action | Modal/Mechanism |
|---|---|
| Dragonfest | `DragonFestModal` |
| Spawn Raid Boss | `SpawnRaidModal` |
| Spawn Black Market | Direct `_run('spawnblackmarket', [])` |
| Kill Raid Boss | Direct `_run('raidkill', [])` |

### 📊 Info
| Action | Modal/Mechanism |
|---|---|
| Spawn Status | Direct `_run('spawnstatus', [])` |
| Raid Info | Direct `_run('raidinfo', [])` |
| Fix Softlock | `FixSoftlockModal` |
| Clear Events | Direct `_run('clearevents', [])` — guild-scoped only |

## UI Structure

```
/adminpanel
└── AdminPanelView (main menu)
    ├── 🎁 Give → AdminGiveView
    │   ├── Give Coins → AdminGiveCoinsView (UserSelect → modal)
    │   ├── Give Pack → AdminGivePackView (UserSelect + PackSelect → modal)
    │   ├── Give Dragonscale → AdminGiveDragonscaleView
    │   ├── Give Dragons → AdminGiveDragonsView
    │   ├── Giveaway → direct run
    │   └── ← Back
    ├── 🔄 Reset → AdminResetView
    │   ├── Reset Quests → direct run
    │   ├── Reset Breed Cooldown → ResetUserModal
    │   ├── Reset Adventure CD → ResetUserModal
    │   ├── Reset Bingo → direct run
    │   └── ← Back
    ├── ⚔️ Spawn → AdminSpawnView (identical to SpawnView from devpanel)
    │   ├── Dragonfest → DragonFestModal
    │   ├── Spawn Raid Boss → SpawnRaidModal
    │   ├── Spawn Black Market → direct run
    │   ├── Kill Raid Boss → direct run
    │   └── ← Back
    └── 📊 Info → AdminInfoView
        ├── Spawn Status → direct run
        ├── Raid Info → direct run
        ├── Fix Softlock → FixSoftlockModal
        ├── Clear Events → direct run
        └── ← Back
```

## Verification of Guild-Scope

- `_run()` builds `FakeMessage` with `msg.guild = interaction.guild` — so all `handle_dev_command` calls that use `message.guild.id` are automatically guild-scoped.
- `AdminGivePackView` and `AdminGiveDragonscaleView` get `guild_id = interaction.guild_id` at construction and never expose a "Change Guild" button.
- `resetquests` and `resetbingo` in `handle_dev_command` are already guild-scoped via `WHERE guild_id = ?` ✅

### Clear Events — guild-scoped implementation

`clearevents` in `handle_dev_command` is **global** (clears all guilds). The admin panel must NOT call `_run('clearevents', [])`. Instead, implement it directly in `adminpanel.py`:

```python
gid = interaction.guild_id
# In-memory state dicts (imported from state.py):
active_dragonfest.pop(gid, None)
active_dragonscales.pop(gid, None)
raid_boss_active.pop(gid, None)

# DB cleanup scoped to guild:
c.execute('DELETE FROM dragonfest_stats WHERE guild_id = ?', (gid,))
c.execute('DELETE FROM dragonscale_stats WHERE guild_id = ?', (gid,))
c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (gid,))
c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (gid,))
c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?', (current_time, gid))
```
