"""
cogs/tasks.py - All @tasks.loop background tasks as TasksCog.
Extracted verbatim from bot.py.
"""

import asyncio
import datetime
import json
import random
import sqlite3
import time
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from config import (
    ADVENTURE_ITEMS, ADVENTURE_TYPES, BREEDING_CHANCES, BREEDING_COOLDOWNS,
    BLACK_MARKET_DURATION, BLACK_MARKET_ITEMS, BLACK_MARKET_SPAWN_INTERVAL,
    DRAGON_RARITY_TIERS, DRAGON_TYPES, DRAGONNEST_UPGRADES, LEVEL_NAMES,
    RAID_DURATION_HOURS, RAID_SPAWN_TIMES, normalize_dragon_type,
)
from database import get_db_connection
from state import (
    active_breeding_sessions, active_dragonfest, active_dragonscales,
    active_luckycharms, active_spawns, black_market_active,
    dragonscale_event_starts, last_catch_attempts, dragonpass_locks,
    premium_users, raid_boss_active, raid_boss_last_spawn, spawn_channels,
    spawn_locks,
)
from utils import (
    get_breeding_cost, get_dragon_rarity, get_spawn_channel,
    get_spawn_channel as _get_spawn_channel,
    get_setup_reminder_ignored_until, set_setup_reminder_ignored_until,
)

import logging
logger = logging.getLogger(__name__)


class IgnoreReminderView(discord.ui.View):
    """Persistent view for the setup reminder ignore button. Survives bot restarts via custom_id."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        btn = discord.ui.Button(
            label="Ignore for 7 days",
            style=discord.ButtonStyle.secondary,
            emoji="🔕",
            custom_id=f"ignore_reminder_{guild_id}",
        )
        btn.callback = self._callback
        self.add_item(btn)

    async def _callback(self, interaction: discord.Interaction):
        guild_id = int(interaction.data["custom_id"].split("_")[-1])
        until = int(time.time()) + 7 * 24 * 3600
        set_setup_reminder_ignored_until(guild_id, until)
        # Rebuild view with disabled button
        new_view = discord.ui.View()
        new_btn = discord.ui.Button(
            label="Reminder paused for 7 days",
            style=discord.ButtonStyle.secondary,
            emoji="🔕",
            disabled=True,
        )
        new_view.add_item(new_btn)
        await interaction.response.edit_message(view=new_view)


class TasksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_locks_task.start()
        self.auto_manage_raid_bosses.start()
        self.auto_spawn_dragons.start()
        self.check_dragon_nest_expiry.start()
        self.check_dragonfest_expiry.start()
        self.check_dragonscale_expiry.start()
        self.check_lucky_charm_expiry.start()
        self.spawn_black_market.start()
        self.process_breeding_queue.start()
        self.process_adventures.start()
        self.cleanup_stuck_sessions.start()
        self.setup_reminder.start()
        self.vote_reminder_task.start()
        self.vote_streak_reset_task.start()

    async def cog_load(self):
        """Re-register persistent ignore-reminder views for all unconfigured guilds after restart."""
        from database import get_db_connection
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute('SELECT guild_id FROM guild_settings WHERE spawn_channel IS NULL OR spawn_channel = 0')
            rows = c.fetchall()
        finally:
            conn.close()
        for (guild_id,) in rows:
            self.bot.add_view(IgnoreReminderView(guild_id))

    def cog_unload(self):
        self.cleanup_locks_task.cancel()
        self.auto_manage_raid_bosses.cancel()
        self.auto_spawn_dragons.cancel()
        self.check_dragon_nest_expiry.cancel()
        self.check_dragonfest_expiry.cancel()
        self.check_dragonscale_expiry.cancel()
        self.check_lucky_charm_expiry.cancel()
        self.spawn_black_market.cancel()
        self.process_breeding_queue.cancel()
        self.process_adventures.cancel()
        self.cleanup_stuck_sessions.cancel()

    # ==================== CLEANUP LOCKS TASK ====================
    @tasks.loop(minutes=30)
    async def cleanup_locks_task(self):
        """Periodically clean up unused locks to prevent memory leaks"""
        try:
            current_time = time.time()

            # Log initial sizes
            initial_locks_size = len(dragonpass_locks) + len(spawn_locks)

            # In production, you'd track access times. For now, just log size
            if initial_locks_size > 10000:
                logger.warning(f"High lock count: {initial_locks_size} locks. Consider cleanup strategy.")

            # Similarly for catch attempts (clear old entries)
            for guild_id in list(last_catch_attempts.keys()):
                if current_time - last_catch_attempts[guild_id].get('timestamp', 0) > 3600:
                    del last_catch_attempts[guild_id]
        except Exception as e:
            logger.error(f"Lock cleanup error: {e}")

    @cleanup_locks_task.before_loop
    async def before_cleanup_locks(self):
        await self.bot.wait_until_ready()

    # ==================== AUTO-SPAWN TASK ====================
    @tasks.loop(minutes=1)
    async def auto_manage_raid_bosses(self):
        """Auto-spawn raid bosses at 08:00, 16:00, 20:00 Vienna time (UTC+1/+2) - WITH TIER SYSTEM"""
        try:
            from datetime import datetime, timezone, timedelta

            # Get Vienna time - use UTC+1 for winter (December-March), UTC+2 for summer
            utc_now = datetime.now(timezone.utc)
            month = utc_now.month
            vienna_offset = timedelta(hours=2) if 4 <= month <= 10 else timedelta(hours=1)
            vienna_time = utc_now + vienna_offset
            current_hour = vienna_time.hour

            for guild in self.bot.guilds:
                try:
                    guild_id = guild.id

                    # Check server config — raids must be enabled per guild
                    from database import get_server_config
                    guild_config = get_server_config(guild_id)
                    if not guild_config['raids_enabled']:
                        continue

                    # Use per-guild raid times (falls back to default [8, 16, 20])
                    guild_raid_times = guild_config['raid_times']

                    # Check if we're currently in a raid spawn hour
                    in_spawn_hour = current_hour in guild_raid_times

                    # Check if already spawned this hour
                    already_spawned_this_hour = False
                    if guild_id in raid_boss_last_spawn:
                        last_spawn_time = datetime.fromtimestamp(raid_boss_last_spawn[guild_id], tz=timezone.utc)
                        last_spawn_vienna = last_spawn_time + vienna_offset
                        last_spawn_hour = last_spawn_vienna.hour
                        if last_spawn_hour == current_hour:
                            already_spawned_this_hour = True

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()

                    # === SPAWN LOGIC ===
                    if in_spawn_hour and not already_spawned_this_hour:
                        c.execute('SELECT expires_at FROM raid_bosses WHERE guild_id = ?', (guild_id,))
                        active_boss = c.fetchone()

                        if not active_boss:  # No active boss - spawn one!
                            # Only delete old/expired raids, not active ones
                            c.execute('DELETE FROM raid_bosses WHERE guild_id = ? AND expires_at < ?',
                                     (guild_id, int(time.time())))
                            c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))

                            # Calculate players and their damage potential
                            c.execute('''SELECT user_id FROM user_dragons
                                         WHERE guild_id = ? AND count > 0''', (guild_id,))
                            player_ids = [row[0] for row in c.fetchall()]
                            active_players = len(set(player_ids)) or 1

                            # Calculate average damage potential per player
                            total_potential_damage = 0
                            if player_ids:
                                from state import RARITY_DAMAGE
                                for player_id in set(player_ids):
                                    c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                                             (guild_id, player_id))
                                    user_dragons_list = c.fetchall()

                                    player_potential = 0
                                    for dragon_type, count in user_dragons_list:
                                        dragon_rarity = 'common'
                                        for rarity, dragons in DRAGON_RARITY_TIERS.items():
                                            if dragon_type in dragons:
                                                dragon_rarity = rarity
                                                break

                                        damage_per_dragon = RARITY_DAMAGE[dragon_rarity]
                                        player_potential += count * damage_per_dragon

                                    total_potential_damage += player_potential
                            else:
                                total_potential_damage = 5000

                            avg_damage_per_player = total_potential_damage / active_players if active_players > 0 else 1500

                            # Generate boss with rarity
                            boss_rarities = ['epic', 'legendary', 'mythic', 'ultra']
                            boss_rarity = random.choices(boss_rarities, weights=[50, 30, 15, 5])[0]

                            rarity_attack_targets = {'epic': 4, 'legendary': 6, 'mythic': 8, 'ultra': 10}
                            attacks_needed = rarity_attack_targets[boss_rarity]

                            if active_players == 1:
                                player_multiplier = 0.8
                            elif active_players == 2:
                                player_multiplier = 1.0
                            elif active_players <= 5:
                                player_multiplier = 1.0 + (active_players - 2) * 0.2
                            else:
                                player_multiplier = 1.6

                            base_hp = int(avg_damage_per_player * attacks_needed * player_multiplier)

                            # TIER SYSTEM: Different HP for each difficulty
                            easy_hp = int(base_hp * 3.0)
                            normal_hp = int(base_hp * 4.0)
                            hard_hp = int(base_hp * 6.0)

                            hp_limits = {'epic': (20000, 100000), 'legendary': (40000, 200000),
                                        'mythic': (60000, 300000), 'ultra': (80000, 400000)}
                            min_hp, max_hp = hp_limits[boss_rarity]
                            easy_hp = max(min_hp // 2, min(easy_hp, max_hp // 3))
                            normal_hp = max(min_hp, min(normal_hp, max_hp // 2))
                            hard_hp = max(int(min_hp * 2), min(hard_hp, max_hp))

                            boss_names = {
                                'epic': ['Ancient Wyrm', 'Iron Goliath', 'Storm Titan', 'Frost Giant'],
                                'legendary': ['Emerald Overlord', 'Diamond Behemoth', 'Obsidian Terror'],
                                'mythic': ['Golden Sovereign', 'Platinum Destroyer', 'Crystal Devourer'],
                                'ultra': ['Celestial Avatar', 'Void Incarnate', 'Cosmic Leviathan']
                            }

                            boss_name = random.choice(boss_names[boss_rarity])
                            reward_dragons = DRAGON_RARITY_TIERS[boss_rarity]
                            reward_dragon = random.choice(reward_dragons)

                            current_unix = int(time.time())
                            expires_at = current_unix + (RAID_DURATION_HOURS * 3600)

                            c.execute('''INSERT OR REPLACE INTO raid_bosses (guild_id, boss_name, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp,
                                                                 boss_rarity, reward_dragon, started_at, expires_at, easy_participants, normal_participants, hard_participants)
                                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                      (guild_id, boss_name, easy_hp, easy_hp, normal_hp, normal_hp, hard_hp, hard_hp,
                                       boss_rarity, reward_dragon, current_unix, expires_at, '[]', '[]', '[]'))

                            conn.commit()

                            raid_boss_active[guild_id] = {
                                'active': True,
                                'spawn_time': current_unix,
                                'despawn_time': expires_at,
                                'manual_spawn': False
                            }
                            raid_boss_last_spawn[guild_id] = current_unix

                            # Announce spawn
                            dragon_data = DRAGON_TYPES[reward_dragon]
                            embed = discord.Embed(
                                title=f"⚔️ RAID BOSS SPAWNED: {boss_name}",
                                description=f"**Rarity:** {boss_rarity.upper()}\n\n🎮 **Choose your difficulty tier!**\nEach tier has its own HP pool and leaderboard.",
                                color=discord.Color.red()
                            )

                            embed.add_field(name="🟢 EASY TIER",
                                value=f"💚 For players with 0-10,000 damage potential\n📊 HP: {easy_hp:,} / {easy_hp:,}\n⚔️ Max Damage: 10,000\n👥 Participants: 0", inline=True)
                            embed.add_field(name="🟡 NORMAL TIER",
                                value=f"💛 For players with 10,001-70,000 damage potential\n📊 HP: {normal_hp:,} / {normal_hp:,}\n⚔️ Max Damage: 70,000\n👥 Participants: 0", inline=True)
                            embed.add_field(name="🔴 HARD TIER",
                                value=f"❤️ For players with 70,000+ damage potential\n📊 HP: {hard_hp:,} / {hard_hp:,}\n⚔️ Max Damage: 100,000\n👥 Participants: 0", inline=True)
                            embed.add_field(name="🎁 Reward", value=f"{dragon_data['emoji']} **{dragon_data['name']} Dragon**\n✨ 1x per victory + bonus coins", inline=False)
                            embed.add_field(name="⏰ Duration", value=f"{RAID_DURATION_HOURS} hours", inline=True)
                            embed.set_footer(text="Click a button to choose your tier! You'll be locked in and cannot change.")

                            try:
                                c_settings = conn.cursor()
                                c_settings.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
                                channel_row = c_settings.fetchone()
                                channel_id = channel_row[0] if channel_row and channel_row[0] else None

                                # Only spawn raid boss if spawn channel is configured
                                if channel_id:
                                    channel = self.bot.get_channel(channel_id)
                                    if channel:
                                        from cogs.raids import RaidTierSelectView
                                        view = RaidTierSelectView(guild_id, boss_name, boss_rarity, reward_dragon)
                                        await channel.send(embed=embed, view=view)
                                    else:
                                        # Channel was deleted - remove from DB
                                        c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (guild_id,))
                                        c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))
                                        if guild_id in raid_boss_active:
                                            del raid_boss_active[guild_id]
                                        conn.commit()
                                else:
                                    # No spawn channel configured - don't spawn the raid boss
                                    c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (guild_id,))
                                    c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))
                                    if guild_id in raid_boss_active:
                                        del raid_boss_active[guild_id]
                                    conn.commit()
                            except Exception as e:
                                print(f"Error sending raid spawn announcement: {e}")

                    # === DESPAWN LOGIC ===
                    if guild_id in raid_boss_active:
                        current_time = int(time.time())
                        spawn_time = raid_boss_active[guild_id]['spawn_time']
                        time_since_spawn = current_time - spawn_time

                        # Check if raid expired (2 hours) or no one joined in 30 minutes
                        if current_time > raid_boss_active[guild_id]['despawn_time'] or time_since_spawn > 1800:  # 1800 seconds = 30 minutes
                            # If no one has joined after 30 minutes, despawn
                            if time_since_spawn > 1800:
                                c.execute('SELECT easy_participants, normal_participants, hard_participants FROM raid_bosses WHERE guild_id = ?', (guild_id,))
                                participants_row = c.fetchone()

                                if participants_row:
                                    easy_part_str, normal_part_str, hard_part_str = participants_row
                                    easy_joined = bool(eval(easy_part_str)) if easy_part_str else False
                                    normal_joined = bool(eval(normal_part_str)) if normal_part_str else False
                                    hard_joined = bool(eval(hard_part_str)) if hard_part_str else False

                                    # If NO ONE joined any tier, despawn the raid
                                    if not (easy_joined or normal_joined or hard_joined):
                                        c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (guild_id,))
                                        c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))
                                        # Reset spawn time so dragons spawn again soon
                                        c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                                                  (int(time.time()), guild_id))
                                        conn.commit()

                                        if guild_id in raid_boss_active:
                                            del raid_boss_active[guild_id]

                                        try:
                                            c_settings = conn.cursor()
                                            c_settings.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
                                            channel_row = c_settings.fetchone()

                                            if channel_row and channel_row[0]:
                                                channel = self.bot.get_channel(channel_row[0])
                                                if channel:
                                                    embed = discord.Embed(
                                                        title="💀 Raid Boss Despawned",
                                                        description="No one participated for 30 minutes. The boss got bored and left!",
                                                        color=discord.Color.dark_gray()
                                                    )
                                                    await channel.send(embed=embed)
                                        except:
                                            pass

                            # Normal despawn after 2 hours
                            elif current_time > raid_boss_active[guild_id]['despawn_time']:
                                c.execute('SELECT easy_hp, normal_hp, hard_hp, easy_participants, normal_participants, hard_participants, reward_dragon, boss_rarity FROM raid_bosses WHERE guild_id = ?', (guild_id,))
                                boss_row = c.fetchone()

                                if boss_row:
                                    easy_hp, normal_hp, hard_hp, easy_part_str, normal_part_str, hard_part_str, reward_dragon, boss_rarity = boss_row

                                    # Check which tiers are still alive (not defeated)
                                    escaped_tiers = []
                                    if easy_hp > 0 and bool(eval(easy_part_str) if easy_part_str else False):
                                        escaped_tiers.append('easy')
                                    if normal_hp > 0 and bool(eval(normal_part_str) if normal_part_str else False):
                                        escaped_tiers.append('normal')
                                    if hard_hp > 0 and bool(eval(hard_part_str) if hard_part_str else False):
                                        escaped_tiers.append('hard')

                                    # Send escape message for undefeated tiers + Shield Rune consolation
                                    if escaped_tiers:
                                        # Shield Rune: give consolation coins to participants who have one
                                        SHIELD_RUNE_CONSOLATION = 300
                                        for escaped_tier in escaped_tiers:
                                            c.execute(f'SELECT user_id FROM raid_damage WHERE guild_id = ? AND tier = ?',
                                                      (guild_id, escaped_tier))
                                            escaped_participants = [row[0] for row in c.fetchall()]
                                            for uid in escaped_participants:
                                                c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                                          (guild_id, uid, 'shield_rune'))
                                                rune_row = c.fetchone()
                                                if rune_row and rune_row[0] > 0:
                                                    c.execute('UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
                                                              (SHIELD_RUNE_CONSOLATION, guild_id, uid))
                                                    c.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                                              (guild_id, uid, 'shield_rune'))
                                        conn.commit()

                                        try:
                                            c_settings = conn.cursor()
                                            c_settings.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
                                            channel_row = c_settings.fetchone()

                                            if channel_row and channel_row[0]:
                                                channel = self.bot.get_channel(channel_row[0])
                                                if channel:
                                                    tier_names = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}
                                                    escaped_text = ', '.join([tier_names[t] for t in escaped_tiers])

                                                    embed = discord.Embed(
                                                        title="💀 Raid Boss Escaped!",
                                                        description=f"The boss escaped before {escaped_text} tier(s) could be defeated!\n\n"
                                                                    f"❌ No rewards for these groups.\n"
                                                                    f"🔷 Players with a **Shield Rune** received {SHIELD_RUNE_CONSOLATION} coins consolation.",
                                                        color=discord.Color.dark_gray()
                                                    )
                                                    await channel.send(embed=embed)
                                        except:
                                            pass

                                    # Delete raid data
                                    c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (guild_id,))
                                    c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))
                                    # Reset spawn time so dragons spawn again soon
                                    c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                                              (int(time.time()), guild_id))
                                    conn.commit()

                                    if guild_id in raid_boss_active:
                                        del raid_boss_active[guild_id]

                    conn.close()

                except Exception as e:
                    print(f"❌ Error in auto_manage_raid_bosses for guild {guild_id}: {e}")

        except Exception as e:
            print(f"❌ Critical error in auto_manage_raid_bosses: {e}")

    @auto_manage_raid_bosses.before_loop
    async def before_auto_manage_raid_bosses(self):
        await self.bot.wait_until_ready()

    # ==================== AUTO-SPAWN TASK ====================
    @tasks.loop(seconds=30)
    async def auto_spawn_dragons(self):
        """Auto-spawn dragons every 3-15 minutes (random) if no active spawn"""
        for guild in self.bot.guilds:
            guild_id = guild.id

            # Skip if already has active spawn
            if guild_id in active_spawns:
                continue

            # Check if spawn channel is set
            channel_id = get_spawn_channel(guild_id)
            if not channel_id:
                continue

            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            # Get last spawn time
            conn = None
            try:
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                # Check spawn_config for last_spawn_time (backward compatibility)
                c.execute('SELECT last_spawn_time FROM spawn_config WHERE guild_id = ?', (guild_id,))
                result = c.fetchone()

                current_time = int(time.time())

                # If no spawn_config exists for this guild, create one with current time
                if not result:
                    c.execute('INSERT OR IGNORE INTO spawn_config (guild_id, spawn_channel_id, last_spawn_time) VALUES (?, ?, ?)',
                              (guild_id, None, current_time))
                    conn.commit()
                    last_spawn_time = current_time
                else:
                    last_spawn_time = result[0]
                    # If last_spawn_time is 0 (old data), set it to current time
                    if last_spawn_time == 0 or last_spawn_time is None:
                        last_spawn_time = current_time
                        c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                                  (current_time, guild_id))
                        conn.commit()

                # Check if dragonscale/dragonfest/premium is active (shorter interval: 30-90 seconds)
                has_active_dragonscale = guild_id in active_dragonscales and active_dragonscales[guild_id] > current_time

                # Check dragonfest - handle both old int format and new dict format
                has_dragonfest = False
                if guild_id in active_dragonfest:
                    dragonfest_data = active_dragonfest[guild_id]
                    dragonfest_end_time = dragonfest_data['end'] if isinstance(dragonfest_data, dict) else dragonfest_data
                    has_dragonfest = dragonfest_end_time > current_time

                has_premium = guild_id in premium_users and any(end_time > current_time for end_time in premium_users[guild_id].values())

                if has_active_dragonscale or has_dragonfest or has_premium:
                    # During events: INSTANT spawns (max 2-5 seconds after any spawn)
                    spawn_interval = random.randint(2, 5)  # 2-5 seconds during events
                else:
                    # Normal mode: 3-15 minutes
                    spawn_interval = random.randint(180, 900)  # 3-15 minutes normal

                # Spawn if enough time has passed
                if current_time - last_spawn_time >= spawn_interval:
                    try:
                        from cogs.events import spawn_dragon
                        await spawn_dragon(guild_id, channel, self.bot)
                        c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                                  (current_time, guild_id))
                        conn.commit()
                    except discord.Forbidden:
                        # Bot missing permissions in this channel/guild
                        try:
                            owner = await self.bot.fetch_user(guild.owner_id)
                            embed = discord.Embed(
                                title="⚠️ Missing Permissions",
                                description=f"**Dragon Bot** is missing permissions in **{guild.name}**!\n\n"
                                            f"The bot needs the following permissions:\n"
                                            f"• Send Messages\n"
                                            f"• Embed Links\n"
                                            f"• Add Reactions\n\n"
                                            f"Please update the bot's role permissions or Dragon spawning will stop working.",
                                color=discord.Color.red()
                            )
                            embed.set_footer(text="Configure permissions in Server Settings → Roles")
                            await owner.send(embed=embed)
                        except:
                            pass  # Silently fail if we can't send DM
                    except Exception as e:
                        print(f"Error spawning dragon in guild {guild_id}: {e}")
            except sqlite3.OperationalError as e:
                print(f"Database error in auto_spawn_dragons for guild {guild_id}: {e}")
            finally:
                if conn:
                    conn.close()

    @auto_spawn_dragons.before_loop
    async def before_auto_spawn_dragons(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def check_dragon_nest_expiry(self):
        """Check for expired Dragon Nest sessions and handle success/failure"""
        conn = None
        try:
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            current_time = int(time.time())

            # Get all expired active nests
            c.execute('SELECT guild_id, user_id, active_until FROM dragon_nest_active WHERE active_until <= ?',
                      (current_time,))
            expired_nests = c.fetchall()

            if not expired_nests:
                return

            for guild_id, user_id, active_until in expired_nests:
                # Get bounty status
                c.execute('SELECT level, bounties_active FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (guild_id, user_id))
                result = c.fetchone()

                if not result:
                    continue

                level = result[0]
                bounties_active = result[1]

                if not bounties_active:
                    # Remove expired entry
                    c.execute('DELETE FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                              (guild_id, user_id))
                    continue

                import ast
                bounties = ast.literal_eval(bounties_active)

                # Timer expired - this ONLY happens if bounties were NOT completed during active catching
                # If all bounties were completed, the session would have ended immediately
                # Therefore, timer expiry = FAILURE (incomplete bounties)

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                member = guild.get_member(user_id)
                if not member:
                    continue

                # FAILURE - Downrank for not completing bounties in time
                new_level = max(level - 1, 0)

                # Remove the last perk the user earned (if any)
                c.execute('''DELETE FROM user_perks
                             WHERE guild_id = ? AND user_id = ?
                             AND perk_id IN (
                                 SELECT perk_id FROM user_perks
                                 WHERE guild_id = ? AND user_id = ?
                                 ORDER BY rowid DESC LIMIT 1
                             )''',
                          (guild_id, user_id, guild_id, user_id))

                c.execute('UPDATE dragon_nest SET level = ?, bounties_active = NULL, speedrun_catches = 0, perks_activated_at_current_level = 0 WHERE guild_id = ? AND user_id = ?',
                          (new_level, guild_id, user_id))

                # Remove active session
                c.execute('DELETE FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                          (guild_id, user_id))

                conn.commit()

                # Send failure message in channel
                try:
                    channel = guild.get_channel(spawn_channels.get(guild_id)) if guild_id in spawn_channels else guild.text_channels[0] if guild.text_channels else None
                    if channel and member:
                        incomplete_bounties = sum(1 for bounty in bounties if bounty['progress'] < bounty['target'])

                        # Create failure embed
                        fail_embed = discord.Embed(
                            title="💀 Dragon Nest Failed!",
                            description=f"You didn't complete all bounties in time ({incomplete_bounties} incomplete).",
                            color=discord.Color.red()
                        )
                        fail_embed.add_field(
                            name="📉 Demotion",
                            value=f"You've been demoted to **Level {new_level}: {LEVEL_NAMES.get(new_level, 'Unknown')}**.",
                            inline=False
                        )
                        fail_embed.add_field(
                            name="🔄 Try Again",
                            value="Use `/dragonnest` to start a new session!",
                            inline=False
                        )
                        fail_embed.set_thumbnail(url=member.display_avatar.url)

                        await channel.send(member.mention, embed=fail_embed)
                except Exception as e:
                    print(f"Failed to send Dragon Nest failure message: {e}")
        except sqlite3.OperationalError as e:
            print(f"Database error in check_dragon_nest_expiry: {e}")
        except Exception as e:
            print(f"Unexpected error in check_dragon_nest_expiry: {e}")
        finally:
            if conn:
                conn.close()

    @check_dragon_nest_expiry.before_loop
    async def before_check_dragon_nest_expiry(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def check_dragonfest_expiry(self):
        """Check for expired Dragonfest events and post summary"""
        conn = None
        try:
            current_time = int(time.time())
            expired_guilds = []

            for guild_id, data in list(active_dragonfest.items()):
                # Handle both old int format and new dict format
                end_time = data['end'] if isinstance(data, dict) else data
                if end_time <= current_time:
                    expired_guilds.append((guild_id, data))

            if not expired_guilds:
                return

            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            for guild_id, data in expired_guilds:
                # Get event start time
                start_time = data['start'] if isinstance(data, dict) else (current_time - 3600)

                # Get stats from the event log
                c.execute('''SELECT user_id, SUM(amount) as total_catches FROM dragonfest_event_log
                             WHERE guild_id = ? AND event_start >= ?
                             GROUP BY user_id
                             ORDER BY total_catches DESC LIMIT 10''',
                          (guild_id, start_time))
                stats = c.fetchall()

                # Get top dragons caught during event from the event log
                c.execute('''SELECT dragon_type, SUM(amount) as count FROM dragonfest_event_log
                             WHERE guild_id = ? AND event_start >= ?
                             GROUP BY dragon_type''',
                          (guild_id, start_time))
                all_dragons = c.fetchall()

                # Sort by rarity to show the rarest dragons (only up to 3)
                rarest_dragons = []
                for dragon_type, count in all_dragons:
                    rarity = next((r for r, dragons in DRAGON_RARITY_TIERS.items() if dragon_type in dragons), 'common')
                    rarity_order = {'mythic': 0, 'ultra': 1, 'legendary': 2, 'epic': 3, 'rare': 4, 'uncommon': 5, 'common': 6}
                    rarest_dragons.append((dragon_type, count, rarity_order.get(rarity, 99)))

                # Sort by rarity first (lower number = rarer), then by count
                rarest_dragons.sort(key=lambda x: (x[2], -x[1]))
                rarest_dragons = rarest_dragons[:3]

                guild = self.bot.get_guild(guild_id)
                if guild:
                    channel = guild.get_channel(spawn_channels.get(guild_id)) if guild_id in spawn_channels else guild.text_channels[0] if guild.text_channels else None
                    if channel:
                        try:
                            # First send "Event Ended" notification
                            ended_embed = discord.Embed(
                                title="🎉 Dragonfest Event Ended!",
                                description="The event spawn boost has ended.\n\nCalculating statistics...",
                                color=0xFEE75C
                            )
                            await channel.send(embed=ended_embed)

                            # Wait 2 seconds before showing statistics
                            await asyncio.sleep(2)

                            # Build summary embed
                            embed = discord.Embed(
                                title="📊 Dragonfest Event Results",
                                description="Final Statistics",
                                color=0xFEE75C
                            )

                            if stats:
                                leaderboard_text = ""
                                medals = ["🥇", "🥈", "🥉"]
                                total_catches = 0

                                for i, (user_id, catches) in enumerate(stats, 1):
                                    member = guild.get_member(user_id)
                                    if member:
                                        medal = medals[i-1] if i <= 3 else f"**{i}.**"
                                        leaderboard_text += f"{medal} {member.display_name}: **{catches}** dragons\n"
                                        total_catches += catches

                                embed.add_field(name="📊 Top Catchers", value=leaderboard_text or "No catches", inline=False)
                                embed.add_field(name="🐉 Total Caught", value=f"**{total_catches}** dragons", inline=False)

                                # Add rarest dragons if available
                                if rarest_dragons:
                                    rarest_text = ""
                                    for dragon_type, count, _ in rarest_dragons:
                                        if dragon_type in DRAGON_TYPES:
                                            dragon_data = DRAGON_TYPES[dragon_type]
                                            rarest_text += f"{dragon_data['emoji']} **{dragon_data['name']}** - {count}x caught\n"
                                    if rarest_text:
                                        embed.add_field(name="✨ Rarest Dragons", value=rarest_text, inline=False)
                            else:
                                embed.add_field(name="📊 Top Catchers", value="No catches during event", inline=False)

                            embed.set_footer(text="Thanks for participating! 🎊")

                            await channel.send(embed=embed)
                        except Exception as e:
                            print(f"Failed to send dragonfest summary: {e}")

                # Clean up
                active_dragonfest.pop(guild_id, None)
                c.execute('DELETE FROM dragonfest_event_log WHERE guild_id = ? AND event_start >= ?',
                          (guild_id, start_time))

                conn.commit()
        except sqlite3.OperationalError as e:
            print(f"Database error in check_dragonfest_expiry: {e}")
        except Exception as e:
            print(f"Unexpected error in check_dragonfest_expiry: {e}")
        finally:
            if conn:
                conn.close()

    @check_dragonfest_expiry.before_loop
    async def before_check_dragonfest_expiry(self):
        await self.bot.wait_until_ready()

    # Check for expired dragonscale events and post summaries
    @tasks.loop(seconds=10)
    async def check_dragonscale_expiry(self):
        """Check for expired dragonscale events and post summaries"""
        conn = None
        try:
            current_time = int(time.time())
            expired_guilds = []

            for guild_id, end_time in list(active_dragonscales.items()):
                if end_time <= current_time:
                    expired_guilds.append(guild_id)

            if not expired_guilds:
                return

            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            for guild_id in expired_guilds:
                # Get all event_start times for this guild from the event log
                c.execute('SELECT DISTINCT event_start FROM dragonscale_event_log WHERE guild_id = ?',
                          (guild_id,))
                event_starts = [row[0] for row in c.fetchall()]

                if not event_starts:
                    # No data for this event
                    print(f"[DRAGONSCALE] No event_starts found for guild {guild_id}")
                    continue

                print(f"[DRAGONSCALE] Found {len(event_starts)} event_start times: {event_starts}")

                # Read from the simple event log (not the aggregated stats table)
                query_users = '''SELECT user_id, SUM(amount) as total_catches FROM dragonscale_event_log
                             WHERE guild_id = ? AND event_start IN ({})
                             GROUP BY user_id
                             ORDER BY total_catches DESC LIMIT 10'''.format(','.join('?' * len(event_starts)))
                params_users = (guild_id,) + tuple(event_starts)
                c.execute(query_users, params_users)
                stats = c.fetchall()

                # Get ALL dragons caught during event(s) from the log
                query_dragons = '''SELECT dragon_type, SUM(amount) as count FROM dragonscale_event_log
                             WHERE guild_id = ? AND event_start IN ({})
                             GROUP BY dragon_type'''.format(','.join('?' * len(event_starts)))
                params_dragons = (guild_id,) + tuple(event_starts)
                c.execute(query_dragons, params_dragons)
                all_dragons = c.fetchall()

                # Sort by rarity to show the rarest dragons caught (only up to 3)
                rarest_dragons = []
                for dragon_type, count in all_dragons:
                    rarity = next((r for r, dragons in DRAGON_RARITY_TIERS.items() if dragon_type in dragons), 'common')
                    rarity_order = {'mythic': 0, 'ultra': 1, 'legendary': 2, 'epic': 3, 'rare': 4, 'uncommon': 5, 'common': 6}
                    rarest_dragons.append((dragon_type, count, rarity_order.get(rarity, 99)))

                # Sort by rarity first (lower number = rarer), then by count descending
                rarest_dragons.sort(key=lambda x: (x[2], -x[1]))
                print(f"[DRAGONSCALE] Rarest dragons (after sort): {rarest_dragons}")
                rarest_dragons = rarest_dragons[:3]

                guild = self.bot.get_guild(guild_id)
                if guild:
                    channel = guild.get_channel(spawn_channels.get(guild_id)) if guild_id in spawn_channels else guild.text_channels[0] if guild.text_channels else None
                    if channel:
                        try:
                            # First send "Event Ended" notification
                            ended_embed = discord.Embed(
                                title="⚡ Dragonscale Event Ended!",
                                description="The server-wide spawn boost has ended.\n\nCalculating statistics...",
                                color=discord.Color.gold()
                            )
                            await channel.send(embed=ended_embed)

                            # Wait 2 seconds before showing statistics
                            await asyncio.sleep(2)

                            # Build summary embed
                            embed = discord.Embed(
                                title="📊 Event Statistics",
                                description="Here's how everyone did:",
                                color=discord.Color.gold()
                            )

                            if stats:
                                leaderboard_text = ""
                                medals = ["🥇", "🥈", "🥉"]
                                total_catches = 0

                                for i, (user_id, catches) in enumerate(stats, 1):
                                    member = guild.get_member(user_id)
                                    if member:
                                        medal = medals[i-1] if i <= 3 else f"**{i}.**"
                                        leaderboard_text += f"{medal} {member.display_name}: **{catches}** dragons\n"
                                        total_catches += catches

                                embed.add_field(name="📊 Top Catchers", value=leaderboard_text or "No catches", inline=False)
                                embed.add_field(name="🐉 Total Caught", value=f"**{total_catches}** dragons", inline=False)

                                # Add rarest dragons
                                if rarest_dragons:
                                    rarest_text = ""
                                    for dragon_type, count, _ in rarest_dragons[:3]:
                                        if dragon_type in DRAGON_TYPES:
                                            dragon_data = DRAGON_TYPES[dragon_type]
                                            rarest_text += f"{dragon_data['emoji']} **{dragon_data['name']}**\n"
                                    if rarest_text:
                                        embed.add_field(name="✨ Rarest Dragons Caught", value=rarest_text, inline=False)
                            else:
                                embed.add_field(name="📊 Top Catchers", value="No catches during event", inline=False)

                            embed.set_footer(text="Thanks for participating! Collect more dragonscales to start another event! ⚡")

                            await channel.send(embed=embed)
                        except Exception as e:
                            print(f"Failed to send dragonscale summary: {e}")

                # Clean up - remove guild from active events and clear its stats for all event_starts
                active_dragonscales.pop(guild_id, None)
                # Delete all dragonscale stats for this guild (all event_starts)
                c.execute('DELETE FROM dragonscale_stats WHERE guild_id = ?', (guild_id,))

                # Clean up event start tracking
                dragonscale_event_starts.pop(guild_id, None)

                # Delete the event log for this guild
                c.execute('DELETE FROM dragonscale_event_log WHERE guild_id = ? AND event_start IN ({})'.format(','.join('?' * len(event_starts))),
                         (guild_id,) + tuple(event_starts))

                conn.commit()
        except sqlite3.OperationalError as e:
            print(f"Database error in check_dragonscale_expiry: {e}")
        except Exception as e:
            print(f"Unexpected error in check_dragonscale_expiry: {e}")
        finally:
            if conn:
                conn.close()

    @check_dragonscale_expiry.before_loop
    async def before_check_dragonscale_expiry(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def check_lucky_charm_expiry(self):
        """Check for expired lucky charms and remove them from active memory"""
        try:
            current_time = int(time.time())

            # Iterate through all guilds with active lucky charms
            for guild_id in list(active_luckycharms.keys()):
                expired_users = []

                # Check each user's lucky charms
                for user_id, end_time in list(active_luckycharms[guild_id].items()):
                    if end_time <= current_time:
                        expired_users.append(user_id)

                # Remove expired lucky charms
                for user_id in expired_users:
                    del active_luckycharms[guild_id][user_id]

                # If guild has no more active lucky charms, remove the guild entry
                if not active_luckycharms[guild_id]:
                    del active_luckycharms[guild_id]

        except Exception as e:
            print(f"Error in check_lucky_charm_expiry: {e}")

    @check_lucky_charm_expiry.before_loop
    async def before_check_lucky_charm_expiry(self):
        await self.bot.wait_until_ready()

    # ==================== BLACK MARKET TASK ====================
    @tasks.loop(minutes=30)
    async def spawn_black_market(self):
        """Automatically spawn Black Market with fixed selection: 2 packs, 1 epic+ dragon, 1 random item"""
        current_time = int(time.time())

        for guild_id, channel_id in spawn_channels.items():
            # Check server config — black market must be enabled per guild
            from database import get_server_config
            guild_config = get_server_config(guild_id)
            if not guild_config['blackmarket_enabled']:
                continue

            interval_seconds = guild_config['blackmarket_interval_hours'] * 3600
            max_per_day = guild_config['blackmarket_max_per_day']

            # Check if black market is already active
            if guild_id in black_market_active:
                if black_market_active[guild_id]['end_time'] > current_time:
                    continue
                # Check if enough time has passed since last close
                time_since_closed = current_time - black_market_active[guild_id]['end_time']
                if time_since_closed < interval_seconds:
                    continue
                # Check daily cap
                spawns_today = black_market_active[guild_id].get('spawns_today', 0)
                last_spawn_day = black_market_active[guild_id].get('last_spawn_day', 0)
                today_day = current_time // 86400
                if last_spawn_day == today_day and spawns_today >= max_per_day:
                    continue

            # 20% chance to spawn
            if random.random() > 0.2:
                continue

            # Select 2 random packs
            pack_items = ['pack_wooden', 'pack_stone', 'pack_bronze']
            selected_packs = random.sample(pack_items, 2)

            # Select 1 epic or higher rarity dragon
            epic_dragons = []
            for rarity in ['epic', 'legendary', 'mythic', 'ultra']:
                epic_dragons.extend(DRAGON_RARITY_TIERS[rarity])

            selected_dragon = random.choice(epic_dragons)
            dragon_data = DRAGON_TYPES[selected_dragon]

            # Select 1 random special item
            special_items = ['dna_sample', 'lucky_charm', 'lucky_dice', 'night_vision']
            selected_item = random.choice(special_items)

            # Calculate dragon price: 25% discount on normal value
            base_dragon_price = int(dragon_data['value'] * 20)
            black_market_dragon_price = int(base_dragon_price * 0.75)

            # Create items list with stock
            items_list = []
            for pack_key in selected_packs:
                items_list.append({
                    'key': pack_key,
                    'stock': random.randint(3, 8),
                    'is_dragon': False
                })

            # Add dragon
            items_list.append({
                'key': selected_dragon,
                'stock': random.randint(1, 3),
                'price': black_market_dragon_price,
                'is_dragon': True,
                'dragon_data': dragon_data
            })

            # Add special item
            items_list.append({
                'key': selected_item,
                'stock': random.randint(2, 5),
                'is_dragon': False
            })

            end_time = current_time + BLACK_MARKET_DURATION
            today_day = current_time // 86400
            prev = black_market_active.get(guild_id, {})
            prev_day = prev.get('last_spawn_day', 0)
            prev_count = prev.get('spawns_today', 0) if prev_day == today_day else 0
            black_market_active[guild_id] = {
                'end_time': end_time,
                'items': items_list,
                'message_id': None,
                'spawns_today': prev_count + 1,
                'last_spawn_day': today_day,
            }

            guild = self.bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    # Build items display (no prices, no discounts)
                    items_text = ""
                    for item in items_list:
                        if item['is_dragon']:
                            # Get rarity
                            rarity = 'common'
                            for r, dragons in DRAGON_RARITY_TIERS.items():
                                if selected_dragon in dragons:
                                    rarity = r
                                    break
                            items_text += f"{item['dragon_data']['emoji']} **{item['dragon_data']['name']} Dragon** ({rarity.title()}) | Stock: {item['stock']}\n"
                        else:
                            item_info = BLACK_MARKET_ITEMS[item['key']]
                            items_text += f"{item_info['emoji']} **{item_info['name']}** | Stock: {item['stock']}\n"

                    embed = discord.Embed(
                        title="🎩 BLACK MARKET OPENED!",
                        description=f"**A mysterious merchant has appeared with rare deals...**\n\n"
                                    f"{items_text}\n"
                                    f"⏰ Available for **30 minutes**!\n\n"
                                    f"Click the button below to shop!",
                        color=0xFEE75C
                    )
                    embed.set_footer(text="💎 Limited quantities - first come, first served!")

                    class BlackMarketAnnounceView(discord.ui.View):
                        def __init__(self_inner):
                            super().__init__(timeout=None)

                        @discord.ui.button(label="Shop Black Market", style=discord.ButtonStyle.success, emoji="🎩")
                        async def shop_market_button(self_inner, interaction: discord.Interaction, button: discord.ui.Button):
                            """Show Black Market shop"""
                            current_time = int(time.time())
                            gid = interaction.guild_id

                            # Check if black market is still active
                            if gid not in black_market_active or black_market_active[gid]['end_time'] < current_time:
                                await interaction.response.send_message("❌ The Black Market has closed!", ephemeral=False)
                                return

                            # Get user balance (use async to prevent event loop blocking)
                            from database import get_user_async
                            user_data = await get_user_async(gid, interaction.user.id)
                            balance = user_data[2]

                            # Create shop selection
                            class BlackMarketSelect(discord.ui.Select):
                                def __init__(self_select):
                                    options = []
                                    for item in black_market_active[gid]['items']:
                                        if item['is_dragon']:
                                            rarity = 'common'
                                            for r, dragons in DRAGON_RARITY_TIERS.items():
                                                if item['key'] in dragons:
                                                    rarity = r
                                                    break
                                            options.append(
                                                discord.SelectOption(
                                                    label=f"{item['dragon_data']['name']} Dragon ({rarity.title()}) - {item['price']:,}🪙",
                                                    description=f"Stock: {item['stock']} | Rarity: {rarity.title()}",
                                                    value=item['key'],
                                                    emoji=item['dragon_data']['emoji']
                                                )
                                            )
                                        else:
                                            item_info = BLACK_MARKET_ITEMS[item['key']]
                                            options.append(
                                                discord.SelectOption(
                                                    label=f"{item_info['name']} - {item_info['black_price']:,}🪙",
                                                    description=f"Stock: {item['stock']}",
                                                    value=item['key'],
                                                    emoji=item_info['emoji']
                                                )
                                            )
                                    super().__init__(placeholder="Select item to purchase...", options=options, min_values=1, max_values=1)

                                async def callback(self_select, select_interaction: discord.Interaction):
                                    # Check softlock status
                                    from database import is_player_softlocked
                                    is_softlocked, upgrade_level = is_player_softlocked(gid, select_interaction.user.id)
                                    if is_softlocked:
                                        upgrade_cost = DRAGONNEST_UPGRADES[upgrade_level + 1]['cost']
                                        softlock_embed = discord.Embed(
                                            title="🔒 Dragon Nest Upgrade Required!",
                                            description=f"You have enough coins to upgrade your Dragon Nest!\n\n"
                                                        f"**Current Level:** {upgrade_level}\n"
                                                        f"**Upgrade Cost:** {upgrade_cost:,} 🪙\n\n"
                                                        f"You're **softlocked** from shopping until you upgrade.\n"
                                                        f"Use `/dragonnest` to upgrade!",
                                            color=discord.Color.red()
                                        )
                                        await select_interaction.response.send_message(embed=softlock_embed, ephemeral=False, delete_after=5)
                                        return

                                    item_key = self_select.values[0]

                                    # Find item in market
                                    market_item = None
                                    for item in black_market_active[gid]['items']:
                                        if item['key'] == item_key:
                                            market_item = item
                                            break

                                    if not market_item:
                                        await select_interaction.response.send_message("❌ Item not found!", ephemeral=False)
                                        return

                                    if market_item['stock'] <= 0:
                                        await select_interaction.response.send_message("❌ Out of stock!", ephemeral=False)
                                        return

                                    if market_item['is_dragon']:
                                        price = market_item['price']
                                        item_info = market_item['dragon_data']
                                    else:
                                        item_info = BLACK_MARKET_ITEMS[item_key]
                                        price = item_info['black_price']

                                    from database import get_user
                                    user_data = get_user(gid, select_interaction.user.id)
                                    balance = user_data[2]

                                    if balance < price:
                                        await select_interaction.response.send_message(
                                            f"❌ You need **{price:,}** 🪙 but only have **{int(balance):,}** 🪙!",
                                            ephemeral=False
                                        )
                                        return

                                    # Process purchase
                                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                    c = conn.cursor()

                                    # Deduct balance
                                    c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                                              (price, gid, select_interaction.user.id))

                                    if market_item['is_dragon']:
                                        # Add dragon
                                        from utils import add_dragons
                                        await add_dragons(gid, select_interaction.user.id, item_key, 1)
                                        item_name = f"{item_info['emoji']} {item_info['name']} Dragon"
                                    else:
                                        # Add item based on type
                                        if item_key.startswith('pack_'):
                                            pack_type = item_key.split('_')[1]
                                            c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                                         VALUES (?, ?, ?, 1)
                                                         ON CONFLICT(guild_id, user_id, pack_type)
                                                         DO UPDATE SET count = count + 1''',
                                                      (gid, select_interaction.user.id, pack_type))
                                        else:
                                            # Special items: dna_sample, lucky_charm, lucky_dice, night_vision
                                            item_type_map = {
                                                'dna_sample': 'dna',
                                                'lucky_charm': None,
                                                'lucky_dice': 'lucky_dice',
                                                'night_vision': 'night_vision'
                                            }

                                            if item_key == 'lucky_charm':
                                                c.execute('''INSERT INTO user_luckycharms (guild_id, user_id, count)
                                                             VALUES (?, ?, 1)
                                                             ON CONFLICT(guild_id, user_id)
                                                             DO UPDATE SET count = count + 1''',
                                                          (gid, select_interaction.user.id))
                                            elif item_type_map.get(item_key):
                                                item_type = item_type_map[item_key]
                                                c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                                             VALUES (?, ?, ?, 1)
                                                             ON CONFLICT(guild_id, user_id, item_type)
                                                             DO UPDATE SET count = count + 1''',
                                                          (gid, select_interaction.user.id, item_type))

                                        item_name = f"{item_info['emoji']} {item_info['name']}"

                                    conn.commit()
                                    conn.close()

                                    # Reduce stock
                                    market_item['stock'] -= 1

                                    success_embed = discord.Embed(
                                        title="✅ Purchase Complete!",
                                        description=f"You've acquired **{item_name}** from the Black Market!\n\n"
                                                    f"💰 Paid: **{price:,}** 🪙",
                                        color=discord.Color.green()
                                    )
                                    await select_interaction.response.send_message(embed=success_embed, ephemeral=False)

                                    # Update the main announcement embed with new stock
                                    if black_market_active[gid]['message_id']:
                                        try:
                                            guild_obj = self.bot.get_guild(gid) if hasattr(self, 'bot') else None
                                            if guild_obj:
                                                for ch in guild_obj.text_channels:
                                                    try:
                                                        msg = await ch.fetch_message(black_market_active[gid]['message_id'])
                                                        if msg:
                                                            # Rebuild items display with updated stock
                                                            items_text = ""
                                                            for item in black_market_active[gid]['items']:
                                                                if item['is_dragon']:
                                                                    rarity = 'common'
                                                                    for r, dragons in DRAGON_RARITY_TIERS.items():
                                                                        if item['key'] in dragons:
                                                                            rarity = r
                                                                            break
                                                                    items_text += f"{item['dragon_data']['emoji']} **{item['dragon_data']['name']} Dragon** ({rarity.title()}) | Stock: {item['stock']}\n"
                                                                else:
                                                                    item_info2 = BLACK_MARKET_ITEMS[item['key']]
                                                                    items_text += f"{item_info2['emoji']} **{item_info2['name']}** | Stock: {item['stock']}\n"

                                                            updated_embed = discord.Embed(
                                                                title="🎩 BLACK MARKET OPENED!",
                                                                description=f"**A mysterious merchant has appeared with rare deals...**\n\n"
                                                                            f"{items_text}\n"
                                                                            f"⏰ Available for **30 minutes**!\n\n"
                                                                            f"Click the button below to shop!",
                                                                color=0xFEE75C
                                                            )
                                                            updated_embed.set_footer(text="💎 Limited quantities - first come, first served!")
                                                            await msg.edit(embed=updated_embed)
                                                            break
                                                    except:
                                                        pass
                                        except:
                                            pass

                            class BlackMarketView(discord.ui.View):
                                def __init__(self_view):
                                    super().__init__(timeout=300)
                                    self_view.add_item(BlackMarketSelect())

                            time_left = black_market_active[gid]['end_time'] - current_time
                            minutes_left = time_left // 60

                            market_embed = discord.Embed(
                                title="🎩 Black Market - OPEN",
                                description=f"**Limited Time Offers!**\n\n",
                                color=0xFEE75C
                            )

                            for item in black_market_active[gid]['items']:
                                if item['is_dragon']:
                                    rarity = 'common'
                                    for r, dragons in DRAGON_RARITY_TIERS.items():
                                        if item['key'] in dragons:
                                            rarity = r
                                            break
                                    market_embed.description += f"{item['dragon_data']['emoji']} **{item['dragon_data']['name']} Dragon** ({rarity.title()})\n"
                                    market_embed.description += f"   Stock: {item['stock']}\n\n"
                                else:
                                    item_info = BLACK_MARKET_ITEMS[item['key']]
                                    market_embed.description += f"{item_info['emoji']} **{item_info['name']}**\n"
                                    market_embed.description += f"   Stock: {item['stock']}\n\n"

                            market_embed.description += f"\n⏰ Market closes in **{minutes_left}** minutes!"
                            market_embed.set_footer(text="💎 Limited quantities - act fast!")

                            await interaction.response.send_message(embed=market_embed, view=BlackMarketView(), ephemeral=False)

                    try:
                        market_message = await channel.send(embed=embed, view=BlackMarketAnnounceView())
                        black_market_active[guild_id]['message_id'] = market_message.id
                    except:
                        pass

    @spawn_black_market.before_loop
    async def before_spawn_black_market(self):
        await self.bot.wait_until_ready()

    # ==================== BREEDING QUEUE PROCESSOR ====================
    @tasks.loop(minutes=1)
    async def process_breeding_queue(self):
        """Process queued breedings every minute - starts when cooldown is ready"""
        current_time = int(time.time())

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get ALL pending breedings (not filtered by scheduled_for anymore)
        c.execute('''SELECT queue_id, guild_id, user_id, parent1_type, parent2_type
                     FROM breeding_queue
                     WHERE status = 'pending'
                     ORDER BY created_at ASC''')
        all_breedings = c.fetchall()

        for queue_id, guild_id, user_id, parent1, parent2 in all_breedings:
            try:
                # NORMALIZE dragon types from DB
                parent1 = normalize_dragon_type(parent1)
                parent2 = normalize_dragon_type(parent2)

                # Validate normalized dragons exist
                if parent1 not in DRAGON_TYPES or parent2 not in DRAGON_TYPES:
                    # Invalid dragons - remove from queue
                    c.execute('DELETE FROM breeding_queue WHERE queue_id = ?', (queue_id,))
                    conn.commit()
                    continue

                # Check if user is ready to breed (cooldown wise)
                c.execute('SELECT last_breed, last_breed_rarity FROM breeding_cooldowns WHERE guild_id = ? AND user_id = ?',
                         (guild_id, user_id))
                cooldown_result = c.fetchone()

                # If has cooldown, check if ready
                if cooldown_result:
                    last_breed = cooldown_result[0]
                    last_rarity = cooldown_result[1] if len(cooldown_result) > 1 else 'common'
                    cooldown_duration = BREEDING_COOLDOWNS.get(last_rarity, BREEDING_COOLDOWNS['common'])

                    if current_time - last_breed < cooldown_duration:
                        # Still in cooldown, skip this breeding
                        continue

                # Check if user has enough coins
                # Calculate the actual breeding cost first
                p1_rarity = get_dragon_rarity(parent1)
                p2_rarity = get_dragon_rarity(parent2)
                breeding_cost = get_breeding_cost(p1_rarity, p2_rarity)

                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                         (guild_id, user_id))
                balance_result = c.fetchone()
                balance = balance_result[0] if balance_result else 0

                if balance < breeding_cost:
                    # Not enough coins - remove from queue and notify user
                    c.execute('DELETE FROM breeding_queue WHERE queue_id = ?', (queue_id,))
                    conn.commit()

                    # Get dragon info for DM
                    p1_data = DRAGON_TYPES.get(parent1, {})
                    p2_data = DRAGON_TYPES.get(parent2, {})

                    # Send DM to user
                    try:
                        guild = self.bot.get_guild(guild_id)
                        user = guild.get_member(user_id) if guild else None

                        if user:
                            dm_embed = discord.Embed(
                                title="💔 Breeding Cancelled",
                                description=f"Your queued breeding was cancelled because you don't have enough coins!",
                                color=discord.Color.red()
                            )
                            dm_embed.add_field(
                                name="❌ Cancelled Breeding",
                                value=f"{p1_data.get('emoji', '🐉')} {p1_data.get('name', parent1)} + {p2_data.get('emoji', '🐉')} {p2_data.get('name', parent2)}",
                                inline=False
                            )
                            dm_embed.add_field(
                                name="💰 Cost",
                                value=f"Required: {breeding_cost:,}🪙\nYou have: {int(balance):,}🪙",
                                inline=False
                            )
                            dm_embed.set_footer(text=f"Server: {guild.name if guild else 'Unknown'}")

                            # Add button to go to spawn channel if it exists
                            channel_id = get_spawn_channel(guild_id)
                            if channel_id:
                                class GoToChannelView(discord.ui.View):
                                    def __init__(self_view):
                                        super().__init__(timeout=None)
                                        channel = guild.get_channel(channel_id)
                                        if channel:
                                            self_view.add_item(discord.ui.Button(
                                                label=f"Go to {guild.name}",
                                                url=f"https://discord.com/channels/{guild_id}/{channel_id}",
                                                emoji="📍"
                                            ))
                                await user.send(embed=dm_embed, view=GoToChannelView())
                            else:
                                await user.send(embed=dm_embed)
                    except:
                        pass

                    continue

                # Roll for offspring
                def get_rarity(dragon_type):
                    for rarity, dragons in DRAGON_RARITY_TIERS.items():
                        if dragon_type in dragons:
                            return rarity
                    return 'common'

                rarity1 = get_rarity(parent1)
                rarity2 = get_rarity(parent2)

                breeding_key = (rarity1, rarity2)
                if breeding_key not in BREEDING_CHANCES:
                    breeding_key = (rarity2, rarity1)

                chances = BREEDING_CHANCES.get(breeding_key, {'common': 100})

                roll = random.randint(1, 100)
                cumulative = 0
                result_rarity = 'fail'

                for rarity, chance in chances.items():
                    cumulative += chance
                    if roll <= cumulative:
                        result_rarity = rarity
                        break

                # Set cooldown
                rarity_order = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra']
                rarity1_idx = rarity_order.index(rarity1)
                rarity2_idx = rarity_order.index(rarity2)
                higher_rarity = rarity1 if rarity1_idx >= rarity2_idx else rarity2

                c.execute('''INSERT INTO breeding_cooldowns (guild_id, user_id, last_breed, last_breed_rarity)
                             VALUES (?, ?, ?, ?)
                             ON CONFLICT(guild_id, user_id)
                             DO UPDATE SET last_breed = ?, last_breed_rarity = ?''',
                          (guild_id, user_id, current_time, higher_rarity, current_time, higher_rarity))

                # Handle result
                if result_rarity == 'fail':
                    # Deduct cost
                    c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                             (breeding_cost, guild_id, user_id))

                    # Consume one parent
                    consumed = random.choice([parent1, parent2])
                    c.execute('UPDATE user_dragons SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                             (guild_id, user_id, consumed))
                    c.execute('UPDATE breeding_queue SET status = "completed_fail" WHERE queue_id = ?', (queue_id,))

                    # Send notification to user and channel
                    try:
                        user = await self.bot.fetch_user(user_id)
                        p1_data = DRAGON_TYPES[parent1]
                        p2_data = DRAGON_TYPES[parent2]
                        consumed_data = DRAGON_TYPES[consumed]

                        embed = discord.Embed(
                            title="❌ Breeding Failed",
                            description=f"**Breeder:** {user.mention}",
                            color=discord.Color.red()
                        )
                        embed.add_field(
                            name="Parents",
                            value=f"{p1_data['emoji']} **{p1_data['name']}** + {p2_data['emoji']} **{p2_data['name']}**",
                            inline=False
                        )
                        embed.add_field(
                            name="Result",
                            value=f"No offspring produced\n\n{consumed_data['emoji']} **{consumed_data['name']}** was consumed",
                            inline=False
                        )
                        embed.add_field(name="ℹ️ Info", value=f"💰 Cost: {breeding_cost:,}🪙\n✅ Parents remain in inventory", inline=False)

                        # Get guild name
                        guild = self.bot.get_guild(guild_id)
                        embed.set_footer(text=f"Better luck next time! | Server: {guild.name if guild else 'Unknown'}")

                        # Add button to go to spawn channel if it exists
                        channel_id = get_spawn_channel(guild_id)
                        if channel_id:
                            class GoToChannelView(discord.ui.View):
                                def __init__(self_view):
                                    super().__init__(timeout=None)
                                    channel = guild.get_channel(channel_id)
                                    if channel:
                                        self_view.add_item(discord.ui.Button(
                                            label=f"Go to {guild.name}",
                                            url=f"https://discord.com/channels/{guild_id}/{channel_id}",
                                            emoji="📍"
                                        ))
                            await user.send(embed=embed, view=GoToChannelView())
                        else:
                            await user.send(embed=embed)

                        # Try to send to spawn channel
                        try:
                            c.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
                            channel_result = c.fetchone()
                            if channel_result and channel_result[0]:
                                channel = self.bot.get_channel(channel_result[0])
                                if channel:
                                    await channel.send(embed=embed)
                        except:
                            pass
                    except:
                        pass
                else:
                    # Deduct cost
                    c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                             (breeding_cost, guild_id, user_id))

                    # Create offspring
                    possible_offspring = DRAGON_RARITY_TIERS[result_rarity]
                    offspring = random.choice(possible_offspring)

                    c.execute('''INSERT OR IGNORE INTO user_dragons (guild_id, user_id, dragon_type, count)
                                VALUES (?, ?, ?, 1)''',
                             (guild_id, user_id, offspring))
                    c.execute('UPDATE user_dragons SET count = count + 1 WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                             (guild_id, user_id, offspring))
                    c.execute('UPDATE breeding_queue SET status = "completed_success" WHERE queue_id = ?', (queue_id,))

                    # Send notification to user and channel
                    try:
                        user = await self.bot.fetch_user(user_id)
                        p1_data = DRAGON_TYPES[parent1]
                        p2_data = DRAGON_TYPES[parent2]
                        offspring_data = DRAGON_TYPES[offspring]

                        # Calculate offspring value (simple formula)
                        p1_value = DRAGON_TYPES[parent1].get('value', 100)
                        p2_value = DRAGON_TYPES[parent2].get('value', 100)
                        offspring_value = (p1_value + p2_value) / 2 * (1 + (rarity_order.index(result_rarity) * 0.15))

                        # Store roll result for display
                        roll_result = roll

                        embed = discord.Embed(
                            title="✨ Breeding Successful!",
                            description=f"**Breeder:** {user.mention}",
                            color=discord.Color.from_rgb(255, 215, 0)
                        )
                        embed.add_field(
                            name="Parents",
                            value=f"{p1_data['emoji']} **{p1_data['name']}** + {p2_data['emoji']} **{p2_data['name']}**",
                            inline=False
                        )
                        embed.add_field(
                            name="Offspring",
                            value=f"{offspring_data['emoji']} **{offspring_data['name']}**",
                            inline=True
                        )
                        embed.add_field(
                            name="Rarity",
                            value=f"**{result_rarity.upper()}**",
                            inline=True
                        )
                        embed.add_field(
                            name="Value",
                            value=f"**{offspring_value:.2f}🪙**",
                            inline=True
                        )
                        embed.add_field(
                            name="ℹ️ Info",
                            value=f"✅ Parents remain in inventory\n💰 Cost: {breeding_cost:,}🪙\n🎲 Rolled: {roll_result}/100",
                            inline=False
                        )

                        # Cooldown info
                        cooldown_duration = BREEDING_COOLDOWNS.get(higher_rarity, BREEDING_COOLDOWNS['common'])
                        cooldown_hours = cooldown_duration // 3600
                        cooldown_mins = (cooldown_duration % 3600) // 60
                        embed.add_field(
                            name="⏰ Cooldown",
                            value=f"**{cooldown_hours}h {cooldown_mins}m** ({higher_rarity.capitalize()} tier)",
                            inline=False
                        )

                        # Get guild name
                        guild = self.bot.get_guild(guild_id)
                        embed.set_footer(text=f"Congratulations on the new addition! | Server: {guild.name if guild else 'Unknown'}")

                        # Add button to go to spawn channel if it exists
                        channel_id = get_spawn_channel(guild_id)
                        if channel_id:
                            class GoToChannelView(discord.ui.View):
                                def __init__(self_view):
                                    super().__init__(timeout=None)
                                    channel = guild.get_channel(channel_id)
                                    if channel:
                                        self_view.add_item(discord.ui.Button(
                                            label=f"Go to {guild.name}",
                                            url=f"https://discord.com/channels/{guild_id}/{channel_id}",
                                            emoji="📍"
                                        ))
                            await user.send(embed=embed, view=GoToChannelView())
                        else:
                            await user.send(embed=embed)

                        # Try to send to spawn channel
                        try:
                            c.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
                            channel_result = c.fetchone()
                            if channel_result and channel_result[0]:
                                channel = self.bot.get_channel(channel_result[0])
                                if channel:
                                    await channel.send(embed=embed)
                        except:
                            pass
                    except:
                        pass

                conn.commit()

            except Exception as e:
                print(f"Breeding queue error: {e}")
                c.execute('UPDATE breeding_queue SET status = "error" WHERE queue_id = ?', (queue_id,))
                conn.commit()

        conn.close()

    @process_breeding_queue.before_loop
    async def before_process_breeding_queue(self):
        await self.bot.wait_until_ready()

    # ==================== ADVENTURE PROCESSOR ====================
    @tasks.loop(minutes=1)
    async def process_adventures(self):
        """Process completed adventures and reward players"""
        # Run database operations in thread pool to avoid blocking event loop
        dms_to_send = await asyncio.to_thread(self.process_adventures_sync)

        # Send DMs asynchronously after database operations complete
        for user_id, dm_data, guild_id in dms_to_send:
            try:
                user = await self.bot.fetch_user(user_id)
                if user:
                    # Add button to go to spawn channel if it exists
                    channel_id = get_spawn_channel(guild_id)
                    if channel_id:
                        guild = self.bot.get_guild(guild_id)
                        class GoToChannelView(discord.ui.View):
                            def __init__(self_view):
                                super().__init__(timeout=None)
                                channel = guild.get_channel(channel_id) if guild else None
                                if channel:
                                    self_view.add_item(discord.ui.Button(
                                        label=f"Go to {guild.name}",
                                        url=f"https://discord.com/channels/{guild_id}/{channel_id}",
                                        emoji="📍"
                                    ))
                        await user.send(embed=dm_data, view=GoToChannelView())
                    else:
                        await user.send(embed=dm_data)
            except Exception as e:
                # Silently fail if we can't send DM (user might have DMs disabled)
                pass

    def process_adventures_sync(self):
        """Synchronous adventure processing - runs in thread pool"""
        current_time = int(time.time())
        dms_to_send = []  # Collect DMs to send after database operations

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get all completed adventures that haven't been claimed
        c.execute('''SELECT adventure_id, guild_id, user_id, dragons_sent, adventure_type, returns_at, double_loot
                     FROM user_adventures
                     WHERE status = 'active' AND returns_at <= ? AND claimed = 0''', (current_time,))
        completed = c.fetchall()

        for adventure_id, guild_id, user_id, dragons_json, adv_type, returns_at, double_loot in completed:
            try:
                # Ensure IDs are integers and handle None values
                adventure_id = int(adventure_id) if adventure_id else 0
                guild_id = int(guild_id) if guild_id else 0
                user_id = int(user_id) if user_id else 0
                returns_at = int(returns_at) if returns_at else current_time

                adventure_config = ADVENTURE_TYPES.get(adv_type, {})
                coins_range = adventure_config.get('rewards', {}).get('coins', (100, 300))
                dragon_chance = adventure_config.get('rewards', {}).get('dragon_chance', 0.15)

                # Roll for overall success/failure
                success_rate = adventure_config.get('success_rate', 0.70)

                # Initialize reward variables
                coins_earned = 0
                rewards_dragons = []
                rewards_items = []

                if random.random() < success_rate:
                    # Adventure succeeded! Roll for rewards
                    coins_earned = random.randint(coins_range[0], coins_range[1])

                    # Roll for dragon
                    if random.random() < dragon_chance:
                        # Got a dragon! Rarity depends on adventure type
                        possible_rarities = list(DRAGON_RARITY_TIERS.keys())

                        # Different rarity weights based on adventure difficulty
                        if adv_type == 'exploration':
                            # Mostly common/uncommon
                            weights = [60, 25, 10, 3, 1, 1, 0]
                        elif adv_type == 'treasure_hunt':
                            # More uncommon/rare
                            weights = [40, 35, 15, 7, 2, 1, 0]
                        elif adv_type == 'dragon_raid':
                            # Epic and legendary possible
                            weights = [25, 30, 25, 15, 4, 1, 0]
                        else:  # legendary_quest
                            # Best chance for high rarity
                            weights = [10, 20, 30, 25, 10, 4, 1]

                        reward_rarity = random.choices(possible_rarities, weights=weights)[0]
                        reward_dragon = random.choice(DRAGON_RARITY_TIERS[reward_rarity])

                        # Ensure reward_dragon is a string, not a list
                        if isinstance(reward_dragon, list):
                            reward_dragon = reward_dragon[0] if reward_dragon else 'stone'

                        rewards_dragons.append(reward_dragon)

                        # Add dragon to user
                        c.execute('''INSERT OR IGNORE INTO user_dragons (guild_id, user_id, dragon_type, count)
                                    VALUES (?, ?, ?, 1)''', (guild_id, user_id, reward_dragon))
                        c.execute('UPDATE user_dragons SET count = count + 1 WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                 (guild_id, user_id, reward_dragon))

                    # Roll for item (separate from dragon)
                    item_chance = adventure_config.get('rewards', {}).get('item_chance', 0.10)
                    # Double Loot Bag: roll twice for items
                    item_rolls = 2 if double_loot else 1
                    adv_item_keys = list(ADVENTURE_ITEMS.keys())
                    adv_item_weights = [ADVENTURE_ITEMS[k].get('weight', 10) for k in adv_item_keys]
                    for _ in range(item_rolls):
                        if random.random() < item_chance:
                            # Got an item! Weighted random selection
                            item_type = random.choices(adv_item_keys, weights=adv_item_weights)[0]
                            item_data = ADVENTURE_ITEMS[item_type]
                            rewards_items.append(item_type)

                            item_storage_type = item_data.get('type', 'item')

                            # Add item to user inventory
                            if item_storage_type == 'dragonscale':
                                item_duration_minutes = random.randint(item_data['min_duration'], item_data['max_duration'])
                                c.execute('''INSERT OR IGNORE INTO dragonscales (guild_id, user_id, minutes)
                                            VALUES (?, ?, ?)''', (guild_id, user_id, item_duration_minutes))
                                c.execute('UPDATE dragonscales SET minutes = minutes + ? WHERE guild_id = ? AND user_id = ?',
                                         (item_duration_minutes, guild_id, user_id))

                            elif item_storage_type == 'luckycharm':
                                c.execute('''INSERT OR IGNORE INTO user_luckycharms (guild_id, user_id, count)
                                            VALUES (?, ?, 1)''', (guild_id, user_id))
                                c.execute('UPDATE user_luckycharms SET count = count + 1 WHERE guild_id = ? AND user_id = ?',
                                         (guild_id, user_id))

                            elif item_storage_type == 'item':
                                c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, 1)
                                             ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + 1''',
                                         (guild_id, user_id, item_type))

                    # Success: Set cooldown equal to adventure duration
                    cooldown_duration = adventure_config['duration']

                    # Add coins on success
                    c.execute('UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
                             (coins_earned, guild_id, user_id))
                else:
                    # Adventure failed - no rewards
                    coins_earned = 0
                    rewards_dragons = []
                    rewards_items = []

                    # Failure: Set cooldown to 1.5x the adventure duration
                    cooldown_duration = int(adventure_config['duration'] * 1.5)

                # Apply cooldown
                cooldown_until = int(time.time()) + cooldown_duration
                c.execute('''INSERT INTO adventure_cooldowns (guild_id, user_id, adventure_type, cooldown_until)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(guild_id, user_id, adventure_type)
                            DO UPDATE SET cooldown_until = ?''',
                         (guild_id, user_id, adv_type, cooldown_until, cooldown_until))

                # Mark as completed and claimed
                c.execute('''UPDATE user_adventures
                            SET status = 'completed', rewards_coins = ?, rewards_dragons = ?, claimed = 1
                            WHERE adventure_id = ?''',
                         (coins_earned, json.dumps(rewards_dragons), adventure_id))

                conn.commit()

                # Prepare DM data to send (will be sent async after database operations)
                # Since dragons are no longer sent, just show results
                dragons_sent_count = 0  # No dragons sent anymore

                # Build reward summary
                reward_lines = []
                if coins_earned > 0:
                    reward_lines.append(f"💰 {coins_earned:,} coins")
                if rewards_dragons:
                    dragon_names = []
                    for dt in rewards_dragons:
                        d = DRAGON_TYPES.get(dt, {})
                        dragon_names.append(f"{d.get('emoji', '🐉')} {d.get('name', dt)}")
                    reward_lines.append('\n'.join(dragon_names))
                if rewards_items:
                    reward_lines.append(f"📦 {', '.join(rewards_items)}")

                if not reward_lines:
                    reward_lines = ["❌ No rewards found"]

                rewards_text = "\n".join(reward_lines)

                # Get cooldown info
                c.execute('SELECT cooldown_until FROM adventure_cooldowns WHERE guild_id = ? AND user_id = ? AND adventure_type = ?',
                         (guild_id, user_id, adv_type))
                cooldown_row = c.fetchone()
                cooldown_until = int(cooldown_row[0]) if cooldown_row and cooldown_row[0] else 0
                time_until_next = max(0, cooldown_until - int(time.time()))
                cooldown_hours = time_until_next // 3600
                cooldown_mins = (time_until_next % 3600) // 60

                if cooldown_hours > 0:
                    cooldown_str = f"{cooldown_hours}h {cooldown_mins}m"
                else:
                    cooldown_str = f"{cooldown_mins}m"

                # Determine status
                if coins_earned > 0 or rewards_dragons or rewards_items:
                    status_emoji = "✅"
                    status_text = "Success!"
                else:
                    status_emoji = "❌"
                    status_text = "Failed!"

                # Get guild name for this adventure
                adventure_guild_id = c.execute('SELECT guild_id FROM user_adventures WHERE user_id = ? AND adventure_id = ?',
                                              (user_id, adventure_id)).fetchone()
                guild_name = "Unknown"
                if adventure_guild_id:
                    guild = self.bot.get_guild(adventure_guild_id[0])
                    guild_name = guild.name if guild else "Unknown"

                # Build embed
                embed = discord.Embed(
                    title="🏆 Adventure Complete!",
                    description=f"**Type:** {adv_type.replace('_', ' ').title()}\n"
                               f"**Result:** {status_emoji} {status_text}\n\n"
                               f"**Rewards:**\n{rewards_text}",
                    color=discord.Color.gold() if coins_earned > 0 else discord.Color.red()
                )

                embed.add_field(
                    name="⏰ Next Adventure Ready In",
                    value=cooldown_str,
                    inline=False
                )

                embed.set_footer(text=f"Server: {guild_name}")

                # Collect DM to send (will be sent async by process_adventures)
                dms_to_send.append((user_id, embed, guild_id))

            except Exception as e:
                logger.error(f"Adventure processing error for adventure_id {adventure_id}: {e}", exc_info=True)
                print(f"Adventure processing error: {e}")

        conn.close()
        return dms_to_send

    @process_adventures.before_loop
    async def before_process_adventures(self):
        await self.bot.wait_until_ready()

    # ==================== CLEANUP TASK ====================
    @tasks.loop(minutes=5)
    async def cleanup_stuck_sessions(self):
        """Clean up stuck breeding sessions (timeout after 30 minutes)"""
        current_time = int(time.time())
        timeout_duration = 30 * 60  # 30 minutes

        # Find and remove old sessions
        expired_sessions = [
            key for key, timestamp in active_breeding_sessions.items()
            if current_time - timestamp > timeout_duration
        ]

        for session_key in expired_sessions:
            del active_breeding_sessions[session_key]

        if expired_sessions:
            print(f"Cleaned up {len(expired_sessions)} stuck breeding sessions")

    @cleanup_stuck_sessions.before_loop
    async def before_cleanup_stuck_sessions(self):
        await self.bot.wait_until_ready()

    # ==================== SETUP REMINDER ====================
    @tasks.loop(hours=24)
    async def setup_reminder(self):
        """DM guild owner/admins daily if the bot has not been configured (no spawn channel set)."""
        current_time = int(time.time())

        for guild in self.bot.guilds:
            if get_spawn_channel(guild.id):
                continue  # Already configured

            ignored_until = get_setup_reminder_ignored_until(guild.id)
            if ignored_until and current_time < ignored_until:
                continue  # User snoozed reminders

            embed = discord.Embed(
                title="⚠️ Dragon Bot Not Configured",
                description=(
                    f"**Dragon Bot** is in your server **{guild.name}** but has not been set up yet.\n\n"
                    "**Required Setup:**\n"
                    "Use `/setchannel` in the channel where you want dragons to spawn.\n\n"
                    "**Optional:**\n"
                    "• `/setup` — view all configuration options\n"
                    "• `/help` — see all available commands\n\n"
                    "Dragons will not spawn until a spawn channel is set."
                ),
                color=discord.Color.orange()
            )

            guild_id = guild.id
            view = IgnoreReminderView(guild_id)
            self.bot.add_view(view)  # Register so it survives future restarts

            # Try to DM owner first
            recipients = set()
            if guild.owner:
                recipients.add(guild.owner)

            # Also try admins who can manage the guild
            try:
                for member in guild.members:
                    if member.guild_permissions.administrator and not member.bot:
                        recipients.add(member)
                    if len(recipients) >= 3:
                        break
            except Exception:
                pass

            for recipient in recipients:
                try:
                    await recipient.send(embed=embed, view=view)
                except Exception:
                    pass

    @setup_reminder.before_loop
    async def before_setup_reminder(self):
        await self.bot.wait_until_ready()

    # ==================== VOTE REMINDER ====================
    _VIENNA = ZoneInfo('Europe/Vienna')
    _TOPGG_VOTE_URL = 'https://top.gg/bot/1445803895862333592/vote'

    @tasks.loop(time=datetime.time(20, 0, tzinfo=ZoneInfo('Europe/Vienna')))
    async def vote_reminder_task(self):
        """DM users with active streak who haven't voted today (runs at 20:00 Vienna)."""
        today = datetime.datetime.now(self._VIENNA).date()
        today_midnight_ts = int(datetime.datetime.combine(
            today, datetime.time(0, 0), tzinfo=self._VIENNA
        ).timestamp())
        today_str = today.isoformat()

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            '''SELECT user_id, current_streak, total_votes FROM vote_streaks
               WHERE current_streak > 0
               AND last_vote_time < ?
               AND (last_reminder_date IS NULL OR last_reminder_date != ?)''',
            (today_midnight_ts, today_str)
        )
        rows = c.fetchall()
        conn.close()

        for user_id, streak, total_votes in rows:
            member = None
            for guild in self.bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    break
            if not member:
                continue

            day_in_cycle = ((total_votes) % 30) + 1

            embed = discord.Embed(
                title="⏰ Don't forget to vote!",
                description=(
                    f"You haven't voted today yet!\n"
                    f'**Day {day_in_cycle}/30** in your current cycle — **{streak}-day streak** is at risk! 🔥\n\n'
                    f'[➡️ Vote now]({self._TOPGG_VOTE_URL})'
                ),
                color=discord.Color.orange(),
            )
            embed.set_footer(text="Streaks reset at midnight if you don't vote.")

            try:
                await member.send(embed=embed)
                conn = get_db_connection()
                conn.execute(
                    'UPDATE vote_streaks SET last_reminder_date = ? WHERE user_id = ?',
                    (today_str, user_id)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    @vote_reminder_task.before_loop
    async def before_vote_reminder_task(self):
        await self.bot.wait_until_ready()

    # ==================== VOTE STREAK RESET ====================

    @tasks.loop(time=datetime.time(0, 0, tzinfo=ZoneInfo('Europe/Vienna')))
    async def vote_streak_reset_task(self):
        """Reset streak for users who didn't vote yesterday (runs at midnight Vienna)."""
        yesterday = (datetime.datetime.now(self._VIENNA) - datetime.timedelta(days=1)).date()
        yesterday_midnight_ts = int(datetime.datetime.combine(
            yesterday, datetime.time(0, 0), tzinfo=self._VIENNA
        ).timestamp())

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'UPDATE vote_streaks SET current_streak = 0 WHERE current_streak > 0 AND last_vote_time < ?',
            (yesterday_midnight_ts,)
        )
        affected = c.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f'vote_streak_reset: {affected} users had their streak reset')

    @vote_streak_reset_task.before_loop
    async def before_vote_streak_reset_task(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TasksCog(bot))
