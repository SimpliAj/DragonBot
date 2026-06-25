# Bot Status Control Design Spec
Date: 2026-04-01

## Overview

Add a "🤖 Status" button to the `/devpanel` main menu that lets the developer change the bot's Discord presence live (no restart needed). Status resets to Discord default on bot restart — no persistence required.

## Access

DEV_USER_ID only (existing `/devpanel` restriction, no changes needed).

## Implementation

**Modified file:** `cogs/devpanel.py` only — no new files.

Changes:
1. Add `_STATUS_OPTIONS` and `_ACTIVITY_OPTIONS` select option lists (module-level constants)
2. Add `SetStatusModal` — text input for activity text
3. Add `StatusView` — two selects + "Set Status" button + "← Back" button
4. Add "🤖 Status" button to existing `DevPanelView`

## UI Flow

```
/devpanel → main menu
  └── 🤖 Status → StatusView
        ├── Select: Status (online / idle / dnd / invisible)
        ├── Select: Activity type (none / playing / watching / listening / streaming)
        ├── [Set Status] → SetStatusModal (text input for activity text)
        │     └── on_submit: bot.change_presence(status, activity) → ✅ confirmation
        └── ← Back → main menu
```

## Select Options

**Status select (`_STATUS_OPTIONS`):**
- 🟢 Online → `discord.Status.online`
- 🟡 Idle → `discord.Status.idle`
- 🔴 Do Not Disturb → `discord.Status.dnd`
- ⚫ Invisible → `discord.Status.invisible`

**Activity type select (`_ACTIVITY_OPTIONS`):**
- ❌ No Activity → `None`
- 🎮 Playing → `discord.ActivityType.playing`
- 👀 Watching → `discord.ActivityType.watching`
- 🎵 Listening → `discord.ActivityType.listening`
- 📡 Streaming → `discord.ActivityType.streaming`

## `SetStatusModal`

- One `TextInput`: label "Activity Text", placeholder "e.g. Dragon Bot", required=False
- Receives `bot`, `status_value` (discord.Status), `activity_type` (ActivityType or None)
- If activity_type is None or text is empty: `activity = None`
- Otherwise: `activity = discord.Activity(type=activity_type, name=text)`
- Calls `await bot.change_presence(status=status_value, activity=activity)`
- Sends ephemeral confirmation: "✅ Status updated!"

## `StatusView`

- `selected_status`: defaults to `discord.Status.online`
- `selected_activity`: defaults to `None`
- Status select → stores value, defers
- Activity select → stores value, defers
- "Set Status" button → opens `SetStatusModal` with stored values
- "← Back" button → edits message back to `_main_embed()` + `DevPanelView`

## Behaviour Notes

- If user clicks "Set Status" without changing selects: uses defaults (online, no activity)
- Streaming activity requires a URL for the `discord.Streaming` activity type — use `discord.Activity(type=ActivityType.streaming, name=text)` which works without a URL (shows as streaming without a live link)
- No DB writes, no state persistence
