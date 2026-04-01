import discord
from discord.ext import commands
import os
import asyncio
import logging
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
        await bot.start(os.getenv('DISCORD_BOT_TOKEN'))

if __name__ == '__main__':
    asyncio.run(main())
