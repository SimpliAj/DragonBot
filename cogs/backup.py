"""
cogs/backup.py - Automatic and manual SQLite database backups.
"""

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone

from discord.ext import commands, tasks

from config import DB_PATH

logger = logging.getLogger(__name__)

BACKUP_DIR = 'backups'


async def backup_db() -> str:
    """
    Create a hot backup of DB_PATH into the backups/ directory.

    Uses sqlite3.Connection.backup() — safe with WAL mode and concurrent
    connections. Returns the backup filename. Raises on failure.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')
    dest_path = os.path.join(BACKUP_DIR, f'dragon_bot_{timestamp}.db')

    def _do_backup():
        src = sqlite3.connect(DB_PATH, timeout=30.0)
        dst = sqlite3.connect(dest_path, timeout=30.0)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

    await asyncio.get_running_loop().run_in_executor(None, _do_backup)
    logger.info(f'Database backed up to {dest_path}')
    return dest_path


class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduled_backup.start()

    def cog_unload(self):
        self.scheduled_backup.cancel()

    @tasks.loop(hours=12)
    async def scheduled_backup(self):
        try:
            path = await backup_db()
            logger.info(f'Scheduled backup complete: {path}')
        except Exception as e:
            logger.error(f'Scheduled backup failed: {e}')

    @scheduled_backup.before_loop
    async def before_scheduled_backup(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(BackupCog(bot))
