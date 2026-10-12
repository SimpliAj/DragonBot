import discord
from discord.ext import commands
import os
import asyncio
import logging
import threading
import time
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log'),
        logging.StreamHandler()
    ]
)

load_dotenv()

GATEWAY_WATCHDOG_TIMEOUT = 600  # seconds offline before we force a restart


def start_gateway_watchdog(threshold=GATEWAY_WATCHDOG_TIMEOUT):
    """
    Process-level liveness watchdog, deliberately on its own OS thread so it
    keeps working even when the asyncio event loop is completely blocked.

    Incident this exists to prevent (2026-09-01 21:00 -> 09-02 05:23 UTC,
    8h23m offline): sqlite lock storms froze the event loop for a full
    busy_timeout at a time. That blew discord.py's 60s ws_connect budget, so
    every reconnect attempt died with TimeoutError and its ExponentialBackoff
    climbed to the 2**10 (~17 min) cap and stayed pinned there all night.
    pm2 reported "online" the whole time because the process never exited, and
    nothing inside the process was able to notice or recover. Another
    discord.py bot on the same VPS resumed its session fine during the same
    window, so this was purely self-inflicted, not a network fault.

    The DB fixes remove the trigger; this is the backstop. If the gateway has
    been down -- or the event loop wedged -- for longer than the threshold, exit
    non-zero and let pm2 restart us, turning any future variant of this failure
    into a bounded outage instead of an open-ended one.
    """
    from state import gateway_state

    def _watch():
        while True:
            time.sleep(30)
            try:
                if not gateway_state.get('ever_connected'):
                    continue  # never connected yet (startup / Discord outage)
                stale = time.time() - gateway_state.get('last_ok', 0)
                if stale > threshold:
                    logging.critical(
                        'GATEWAY WATCHDOG: no healthy gateway heartbeat for %.0fs '
                        '(threshold %ds). Event loop wedged or gateway lost - '
                        'exiting so pm2 restarts the process.', stale, threshold
                    )
                    logging.shutdown()
                    os._exit(1)
            except Exception:
                pass

    threading.Thread(target=_watch, name='gateway-watchdog', daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)

async def main():
    from database import init_db
    async with bot:
        init_db()
        extensions = [
            'cogs.tasks',
            'cogs.backup',
            'cogs.events',
            'cogs.admin',
            'cogs.topgg',
            'cogs.devpanel',
            'cogs.adminpanel',
            'cogs.economy',
            'cogs.dragons',
            'cogs.dragon_nest',
            'cogs.dragonpass',
            'cogs.packs',
            'cogs.breeding',
            'cogs.raids',
            'cogs.market',
            'cogs.adventures',
            'cogs.social',
        ]
        for ext in extensions:
            await bot.load_extension(ext)
        start_gateway_watchdog()
        await bot.start(os.getenv('DISCORD_BOT_TOKEN'))

if __name__ == '__main__':
    asyncio.run(main())
