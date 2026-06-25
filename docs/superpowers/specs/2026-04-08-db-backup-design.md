# DB Backup System Design

**Date:** 2026-04-08

## Goal

Automatically back up `dragon_bot.db` every 12 hours and allow the developer to trigger a manual backup at any time via `/devpanel`. Backups are kept forever (no rotation). This prevents data loss from accidental wipes or corruption.

---

## Architecture

Single new file: `cogs/backup.py`

- Contains `backup_db()` — a standalone async function that performs the backup
- Contains `BackupCog` — a `commands.Cog` with a `@tasks.loop(hours=12)` that calls `backup_db()`
- Registered in `main.py` alongside all other cogs
- `cogs/devpanel.py` — "💾 Backup DB" button added to `DangerView`, calls `backup_db()`

---

## Components

### `backup_db()` — `cogs/backup.py`

```python
async def backup_db() -> str:
```

- Creates `backups/` directory (relative to bot working directory) if it doesn't exist, using `os.makedirs(..., exist_ok=True)`
- Generates destination filename: `dragon_bot_YYYY-MM-DD_HH-MM-SS.db` using current UTC time
- Opens source connection to `DB_PATH` (from `config.py`)
- Opens destination connection to the new backup file
- Calls `src_conn.backup(dest_conn)` — SQLite's built-in hot-backup API; safe with WAL mode and concurrent writes
- Closes both connections
- Logs success with filename to module logger
- Returns the backup filename (string) so callers can report it to the user
- On any exception: logs the error, re-raises so callers can handle it

### `BackupCog` — `cogs/backup.py`

- `@tasks.loop(hours=12)` — starts on cog load, runs `backup_db()` every 12 hours
- `cog_unload` cancels the loop
- Errors inside the task are caught and logged; the loop continues running

### Manual trigger — `cogs/devpanel.py`

- "💾 Backup DB" button added to existing `DangerView` (row 1, secondary style)
- On click: `await interaction.response.defer(ephemeral=True)`, calls `backup_db()`, responds with `✅ Backup saved: <filename>`
- On error: responds with `❌ Backup failed: <error>`

### `main.py`

- Adds `'cogs.backup'` to the extensions list

---

## Data

- **Source:** `DB_PATH` from `config.py` (currently `'dragon_bot.db'`)
- **Destination:** `backups/dragon_bot_YYYY-MM-DD_HH-MM-SS.db`
- **Retention:** All backups kept (no deletion)
- **Method:** `sqlite3.Connection.backup()` — atomic, WAL-safe, no risk of partial copy

---

## Error Handling

- `backup_db()` re-raises exceptions so both the task and the devpanel button can handle them appropriately
- Task: catches and logs, loop keeps running
- Devpanel button: catches and sends ephemeral error message to the user

---

## Out of Scope

- Remote/cloud backup destinations
- Backup rotation or pruning
- Restore functionality (backups are just files — copy manually if needed)
- Backup on shutdown/restart
