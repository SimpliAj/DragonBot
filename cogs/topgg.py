"""
cogs/topgg.py - Top.gg webhook listener and vote reward system.

Starts a lightweight aiohttp server on TOPGG_WEBHOOK_PORT (default 5000).
Set the webhook URL on top.gg to: http://<your-ip>:5000/topgg-webhook
Set Authorization on top.gg to the value of TOPGG_WEBHOOK_AUTH in .env
"""

import os
import time
import logging
import asyncio
from aiohttp import web

import discord
from discord.ext import commands

from database import get_db_connection, update_balance
from achievements import check_and_award_achievements

logger = logging.getLogger(__name__)

# Maps user_id -> guild_id: set when user runs /vote, used when webhook fires
_vote_guild_map: dict[int, int] = {}


def register_vote_guild(user_id: int, guild_id: int):
    """Called from /vote command to remember which guild the user voted from."""
    _vote_guild_map[user_id] = guild_id


WEBHOOK_PORT = int(os.getenv('TOPGG_WEBHOOK_PORT', '5000'))
WEBHOOK_AUTH = os.getenv('TOPGG_WEBHOOK_AUTH', '')

VOTE_WEEKEND_BONUS_PACK = 'wooden'  # extra pack on weekends

# Same custom emojis as Dragonpass
PACK_EMOJIS = {
    'wooden':  {'closed': '<:woodenchest:1446170002708238476>',  'open': '✅'},
    'stone':   {'closed': '<:stonechest:1446169958265389247>',   'open': '✅'},
    'bronze':  {'closed': '<:bronzechest:1446169758599745586>',  'open': '✅'},
    'silver':  {'closed': '<:silverchest:1446169917996011520>',  'open': '✅'},
    'gold':    {'closed': '<:goldchest:1446169876438978681>',    'open': '✅'},
    'diamond': {'closed': '<:diamondchest:1446169830720929985>', 'open': '✅'},
}
DRAGONSCALE_EMOJI = '<:dragonscale:1446278170998341693>'
DRAGONSCALE_EMOJI_CLAIMED = '✅'


def get_vote_reward_for_day(day: int) -> dict:
    """Return reward dict for a given day (1-30) in the cycle."""
    if day <= 10:
        if day % 2 == 0:
            return {'pack': 'stone',   'coins': 400,  'label': 'Stone Pack + 400 coins'}
        else:
            return {'pack': 'wooden',  'coins': 300,  'label': 'Wooden Pack + 300 coins'}
    elif day <= 20:
        if day % 2 == 0:
            return {'pack': 'silver',  'coins': 800,  'label': 'Silver Pack + 800 coins'}
        else:
            return {'pack': 'bronze',  'coins': 600,  'label': 'Bronze Pack + 600 coins'}
    elif day < 30:
        if day % 2 == 0:
            return {'pack': 'diamond', 'coins': 1500, 'label': 'Diamond Pack + 1,500 coins'}
        else:
            return {'pack': 'gold',    'coins': 1200, 'label': 'Gold Pack + 1,200 coins'}
    else:  # day 30 milestone
        return {'pack': 'dragonscale', 'coins': 3000, 'label': '⭐ Dragonscale + 3,000 coins'}


def build_vote_schedule_rows(day_in_cycle: int) -> list:
    """Build 3 separate row strings for embed fields. day_in_cycle = days collected so far (0-30)."""
    ranges = [('Days 1-10', 1, 10), ('Days 11-20', 11, 20), ('Days 21-30', 21, 30)]
    rows = []
    for label, start, end in ranges:
        row = ""
        for day in range(start, end + 1):
            reward = get_vote_reward_for_day(day)
            pack = reward['pack']
            if day <= day_in_cycle:
                row += DRAGONSCALE_EMOJI_CLAIMED if pack == 'dragonscale' else PACK_EMOJIS[pack]['open']
            else:
                row += DRAGONSCALE_EMOJI if pack == 'dragonscale' else PACK_EMOJIS[pack]['closed']
        rows.append((label, row))
    return rows


def _update_vote_streak(user_id: int) -> dict:
    """Increment total_votes and streak, return updated info."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO vote_streaks (user_id) VALUES (?)', (user_id,))
        c.execute('SELECT current_streak, last_vote_time, total_votes, best_streak FROM vote_streaks WHERE user_id = ?',
                  (user_id,))
        streak, last_vote, total, best = c.fetchone()

        now = int(time.time())
        streak = streak + 1 if now - last_vote < 48 * 3600 else 1
        total += 1
        best = max(best, streak)

        c.execute('UPDATE vote_streaks SET current_streak=?, last_vote_time=?, total_votes=?, best_streak=? WHERE user_id=?',
                  (streak, now, total, best, user_id))
        conn.commit()
        conn.close()
        return {'current_streak': streak, 'last_vote_time': now, 'total_votes': total, 'best_streak': best}
    except Exception as e:
        logger.error(f"_update_vote_streak error: {e}")
        return {'current_streak': 1, 'last_vote_time': int(time.time()), 'total_votes': 1, 'best_streak': 1}


def _give_pack(guild_id: int, user_id: int, pack_type: str):
    """Give a pack. pack_type = 'wooden', 'stone', etc."""
    if pack_type == 'dragonscale':
        _give_dragonscale(guild_id, user_id)
        return
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                     VALUES (?, ?, ?, 1)
                     ON CONFLICT(guild_id, user_id, pack_type)
                     DO UPDATE SET count = count + 1''',
                  (guild_id, user_id, pack_type))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"_give_pack error: {e}")


def _give_dragonscale(guild_id: int, user_id: int):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                     VALUES (?, ?, 'dragonscale', 1)
                     ON CONFLICT(guild_id, user_id, item_type)
                     DO UPDATE SET count = count + 1''',
                  (guild_id, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"_give_dragonscale error: {e}")


class TopggCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._runner = None
        self._site = None

    async def cog_load(self):
        app = web.Application()
        app.router.add_post('/topgg-webhook', self._handle_vote)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, '0.0.0.0', WEBHOOK_PORT)
        await self._site.start()
        logger.info(f"Top.gg webhook server listening on port {WEBHOOK_PORT}")

    async def cog_unload(self):
        if self._runner:
            await self._runner.cleanup()

    async def _handle_vote(self, request: web.Request) -> web.Response:
        auth = request.headers.get('Authorization', '')
        if auth != WEBHOOK_AUTH:
            logger.warning(f"Top.gg webhook: unauthorized from {request.remote}")
            return web.Response(status=401)
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400)

        user_id_str = data.get('user')
        if not user_id_str:
            return web.Response(status=400)

        user_id = int(user_id_str)
        is_weekend = data.get('isWeekend', False)
        is_test = data.get('type') == 'test'

        asyncio.create_task(self._process_vote(user_id, is_weekend, is_test))
        return web.Response(status=200)

    async def _process_vote(self, user_id: int, is_weekend: bool, is_test: bool = False):
        streak_info = _update_vote_streak(user_id)
        total = streak_info['total_votes']
        streak = streak_info['current_streak']

        # Day in 30-cycle (1-30)
        day_in_cycle = ((total - 1) % 30) + 1
        reward = get_vote_reward_for_day(day_in_cycle)

        # Use the guild the user ran /vote in; fall back to first shared guild
        target_guild_id = _vote_guild_map.pop(user_id, None)

        member = None
        if target_guild_id:
            guild = self.bot.get_guild(target_guild_id)
            if guild:
                member = guild.get_member(user_id)

        if member is None:
            for guild in self.bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    break

        if member is None:
            logger.info(f"Vote for user {user_id} — not in any shared guild.")
            return

        update_balance(member.guild.id, user_id, reward['coins'])
        _give_pack(member.guild.id, user_id, reward['pack'])
        if is_weekend:
            _give_pack(member.guild.id, user_id, VOTE_WEEKEND_BONUS_PACK)

        await self._notify(member, reward, day_in_cycle, streak, total, is_weekend, is_test)
        await check_and_award_achievements(member.guild.id, user_id, bot=self.bot)

    async def _notify(self, user: discord.Member, reward: dict, day_in_cycle: int,
                      streak: int, total: int, is_weekend: bool, is_test: bool):
        is_milestone = day_in_cycle == 30

        embed = discord.Embed(
            title=f"🗳️ Thanks for voting!{' (Test)' if is_test else ''}",
            color=discord.Color.gold(),
        )
        embed.description = f"**Day {day_in_cycle}/30** in your current cycle"

        reward_lines = [f"🎁 **{reward['label']}**"]
        if is_weekend:
            reward_lines.append("🌟 **Weekend bonus:** +1 Wooden Pack")
        if is_milestone:
            reward_lines.append("⭐ **30-day cycle complete! Starting over.**")

        embed.add_field(name="Today's Reward", value='\n'.join(reward_lines), inline=False)

        # Visual grid (3 separate fields to stay under 1024 char limit)
        for row_label, row_visual in build_vote_schedule_rows(day_in_cycle):
            embed.add_field(name=f"📅 {row_label}", value=row_visual, inline=False)

        embed.add_field(
            name="🔥 Vote Streak",
            value=f"**{streak}** vote{'s' if streak != 1 else ''} in a row | Total: **{total}**",
            inline=False,
        )
        embed.set_footer(text="Vote every 12h to keep your streak!")

        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            from utils import get_spawn_channel
            channel_id = get_spawn_channel(user.guild.id)
            if channel_id:
                channel = user.guild.get_channel(channel_id)
                if channel:
                    embed.description = f"{user.mention} voted for the bot!\n**Day {day_in_cycle}/30** in their cycle"
                    await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(TopggCog(bot))
