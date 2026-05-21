# Bot Status Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "🤖 Status" button to `/devpanel` that lets the developer change the bot's Discord presence live (status + activity type + text) without a restart.

**Architecture:** All changes are confined to `cogs/devpanel.py`. Two module-level option lists (`_STATUS_OPTIONS`, `_ACTIVITY_OPTIONS`) feed a `StatusView` with two selects. A "Set Status" button on that view opens `SetStatusModal`, which calls `await bot.change_presence()`. A "← Back" button returns to the main panel. A new button on `DevPanelView` navigates to `StatusView`.

**Tech Stack:** discord.py — `discord.ui.View`, `discord.ui.Modal`, `discord.ui.Select`, `discord.ui.Button`, `bot.change_presence()`

---

### Task 1: Add `_STATUS_OPTIONS` and `_ACTIVITY_OPTIONS` constants

**Files:**
- Modify: `cogs/devpanel.py` — after the existing `_MINUTES_OPTIONS` block (line 35)

These are module-level constants, built once at import time, following the same pattern as `_DRAGON_OPTIONS`, `_PACK_OPTIONS`, and `_MINUTES_OPTIONS` already in the file.

- [ ] **Step 1: Open `cogs/devpanel.py` and locate the constants section**

  Find the block ending with `_MINUTES_OPTIONS` around line 35. The new constants go immediately after it, before the `_FakeChannel` class.

- [ ] **Step 2: Insert the two new option lists**

  Add this block after line 35 (the closing `]` of `_MINUTES_OPTIONS`):

  ```python
  _STATUS_OPTIONS = [
      discord.SelectOption(label="🟢 Online",          value="online"),
      discord.SelectOption(label="🟡 Idle",             value="idle"),
      discord.SelectOption(label="🔴 Do Not Disturb",   value="dnd"),
      discord.SelectOption(label="⚫ Invisible",         value="invisible"),
  ]
  _ACTIVITY_OPTIONS = [
      discord.SelectOption(label="❌ No Activity",   value="none"),
      discord.SelectOption(label="🎮 Playing",       value="playing"),
      discord.SelectOption(label="👀 Watching",      value="watching"),
      discord.SelectOption(label="🎵 Listening",     value="listening"),
      discord.SelectOption(label="📡 Streaming",     value="streaming"),
  ]
  ```

- [ ] **Step 3: Verify syntax by running a quick import check**

  ```bash
  python -c "import ast; ast.parse(open('cogs/devpanel.py', encoding='utf-8').read()); print('OK')"
  ```
  Expected: `OK`

---

### Task 2: Add `SetStatusModal`

**Files:**
- Modify: `cogs/devpanel.py` — in the Modals section, after `FixSoftlockModal` (around line 247)

`SetStatusModal` receives the pre-selected `discord.Status` and activity type from `StatusView`, shows a single optional text input, then calls `bot.change_presence()`.

- [ ] **Step 1: Add `SetStatusModal` after `FixSoftlockModal`**

  Insert after the closing of `FixSoftlockModal` (the `except` block ending around line 247):

  ```python
  class SetStatusModal(discord.ui.Modal, title="Set Bot Status"):
      activity_text = discord.ui.TextInput(
          label="Activity Text",
          placeholder="e.g. Dragon Bot",
          required=False,
      )

      def __init__(self, bot, status_value: discord.Status, activity_type):
          super().__init__()
          self.bot = bot
          self.status_value = status_value
          self.activity_type = activity_type

      async def on_submit(self, interaction: discord.Interaction):
          text = self.activity_text.value.strip()
          if self.activity_type is None or not text:
              activity = None
          else:
              activity = discord.Activity(type=self.activity_type, name=text)
          await self.bot.change_presence(status=self.status_value, activity=activity)
          await interaction.response.send_message("✅ Status updated!", ephemeral=True)
  ```

- [ ] **Step 2: Verify syntax**

  ```bash
  python -c "import ast; ast.parse(open('cogs/devpanel.py', encoding='utf-8').read()); print('OK')"
  ```
  Expected: `OK`

---

### Task 3: Add `StatusView`

**Files:**
- Modify: `cogs/devpanel.py` — in the Category Views section, before `DevPanelView` (around line 604)

`StatusView` holds the currently-selected status and activity type as instance state, updates them via the two selects, and opens `SetStatusModal` on the "Set Status" button.

The `_STATUS_VALUE_MAP` and `_ACTIVITY_VALUE_MAP` dicts translate the string select values to discord objects — these go just before the class, or inline inside the class methods.

- [ ] **Step 1: Add `StatusView` before `DevPanelView`**

  Insert immediately before the `# ── Main Panel` comment block (around line 588):

  ```python
  _STATUS_VALUE_MAP = {
      "online":    discord.Status.online,
      "idle":      discord.Status.idle,
      "dnd":       discord.Status.dnd,
      "invisible": discord.Status.invisible,
  }
  _ACTIVITY_VALUE_MAP = {
      "none":      None,
      "playing":   discord.ActivityType.playing,
      "watching":  discord.ActivityType.watching,
      "listening": discord.ActivityType.listening,
      "streaming": discord.ActivityType.streaming,
  }


  class StatusView(discord.ui.View):
      def __init__(self, bot):
          super().__init__(timeout=120)
          self.bot = bot
          self.selected_status = discord.Status.online
          self.selected_activity = None

      @discord.ui.select(
          placeholder="Status…",
          options=_STATUS_OPTIONS,
          row=0,
      )
      async def status_select(self, interaction: discord.Interaction, select: discord.ui.Select):
          self.selected_status = _STATUS_VALUE_MAP[select.values[0]]
          await interaction.response.defer()

      @discord.ui.select(
          placeholder="Activity type…",
          options=_ACTIVITY_OPTIONS,
          row=1,
      )
      async def activity_select(self, interaction: discord.Interaction, select: discord.ui.Select):
          self.selected_activity = _ACTIVITY_VALUE_MAP[select.values[0]]
          await interaction.response.defer()

      @discord.ui.button(label="Set Status", emoji="🤖", style=discord.ButtonStyle.primary, row=2)
      async def set_status(self, interaction: discord.Interaction, _):
          await interaction.response.send_modal(
              SetStatusModal(self.bot, self.selected_status, self.selected_activity)
          )

      @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
      async def back(self, interaction: discord.Interaction, _):
          await interaction.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))
  ```

- [ ] **Step 2: Verify syntax**

  ```bash
  python -c "import ast; ast.parse(open('cogs/devpanel.py', encoding='utf-8').read()); print('OK')"
  ```
  Expected: `OK`

---

### Task 4: Add "🤖 Status" button to `DevPanelView` and update `_main_embed`

**Files:**
- Modify: `cogs/devpanel.py` — `DevPanelView` class (around line 604) and `_main_embed()` function (around line 590)

`DevPanelView` currently has 4 buttons on row 0 (Give, Reset, Spawn, Info) and 1 on row 1 (Danger). The Status button goes on row 1 alongside Danger.

- [ ] **Step 1: Add "🤖 Status" button to `DevPanelView`**

  In `DevPanelView`, after the existing `danger` button, add:

  ```python
  @discord.ui.button(label="🤖 Status", style=discord.ButtonStyle.secondary, row=1)
  async def status(self, i, _):
      await i.response.edit_message(
          embed=discord.Embed(title="🤖 Bot Status", color=discord.Color.blurple()),
          view=StatusView(self.bot))
  ```

- [ ] **Step 2: Update `_main_embed()` to mention Status**

  In `_main_embed()`, after the `⚠️ Danger` field, add:

  ```python
  embed.add_field(name="🤖 Status", value="Online/idle/dnd/invisible, activity text", inline=False)
  ```

- [ ] **Step 3: Verify syntax**

  ```bash
  python -c "import ast; ast.parse(open('cogs/devpanel.py', encoding='utf-8').read()); print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 4: Commit**

  ```bash
  git add cogs/devpanel.py
  git commit -m "feat(devpanel): add bot status control panel"
  ```

---

## Self-Review Notes

- **Spec coverage:**
  - ✅ `_STATUS_OPTIONS` / `_ACTIVITY_OPTIONS` constants → Task 1
  - ✅ `SetStatusModal` with optional text input, `change_presence` call → Task 2
  - ✅ `StatusView` with two selects, Set Status button, Back button → Task 3
  - ✅ "🤖 Status" button on `DevPanelView` → Task 4
  - ✅ No persistence (no DB writes)
  - ✅ Streaming activity uses `discord.Activity(type=ActivityType.streaming, name=text)` — no URL required
  - ✅ Defaults to online / no activity when user clicks Set Status without changing selects

- **Type consistency:** `SetStatusModal` receives `discord.Status` and `discord.ActivityType | None` — `StatusView` stores them as the same types via `_STATUS_VALUE_MAP` / `_ACTIVITY_VALUE_MAP`. Consistent throughout.

- **No placeholders:** All steps contain complete code.
