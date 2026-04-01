"""
cogs/events.py - Event listeners: on_ready, on_message, on_app_command_error, on_error.
Also contains spawn_dragon, update_raid_embed, RaidTierSelectView, RaidAttackView.
Extracted verbatim from bot.py.
"""

import asyncio
import json
import random
import sqlite3
import time
import traceback
from datetime import datetime

import discord
from discord.ext import commands

from config import (
    DEV_USER_ID, DRAGON_RARITY_TIERS, DRAGON_TYPES, DRAGONNEST_UPGRADES,
    ERROR_WEBHOOK_URL, LEVEL_NAMES, PACK_TYPES,
)
from achievements import award_trophy, send_quest_notification
from database import get_user, get_user_async, init_db, is_player_softlocked, update_balance, update_balance_and_check_trophies
from state import (
    active_dragonscales, active_dragonfest, active_luckycharms,
    active_spawns, active_usable_items, dragonscale_event_starts,
    last_catch_attempts, last_spawn_data, premium_users,
    raid_boss_active, raid_boss_last_spawn, spawn_channels,
    RARITY_DAMAGE,
)
from utils import (
    add_dragons, apply_items, apply_perks, check_dragonpass_quests,
    format_time_remaining, get_active_item, get_breeding_cost,
    get_dragon_rarity, get_higher_rarity_dragon, get_passive_bonus,
    get_random_dragon, get_spawn_channel, is_raid_boss_active,
    set_spawn_channel, update_bingo_on_catch,
)

import logging
logger = logging.getLogger(__name__)


async def spawn_dragon(guild_id: int, channel, bot=None, catcher_id: int = None):
    """Spawn a dragon in the channel"""
    # Check if raid boss is active - block dragon spawns during raid
    if is_raid_boss_active(guild_id):
        return  # Don't spawn dragons during raid boss

    # Check if there's already an active spawn
    if guild_id in active_spawns:
        return  # Don't spawn if one already exists

    # Check if ANY user in the guild has Night Vision active
    night_vision_active = False
    night_vision_activator = None
    if guild_id in active_usable_items:
        for user_id, items_dict in active_usable_items[guild_id].items():
            if 'night_vision' in items_dict:
                current_time = int(time.time())
                if current_time < items_dict['night_vision']:
                    night_vision_active = True
                    night_vision_activator = user_id
                    break

    # Use higher rarity dragons if Night Vision is active, otherwise random
    if night_vision_active:
        dragon_key, dragon_data = get_higher_rarity_dragon()
    else:
        dragon_key, dragon_data = get_random_dragon()

    # Store if night vision is active for this spawn (for catch notification)
    night_vision_spawn = night_vision_active and catcher_id == night_vision_activator

    # Calculate actual coin reward (50% of dragon value, minimum 2)
    base_coin_reward = max(2, int(dragon_data['value'] / 2))

    # Apply server-wide Alpha coin boost for display
    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ?', (guild_id,))
    server_alpha_count = c.fetchone()[0]
    conn.close()

    displayed_coins = base_coin_reward
    if server_alpha_count > 0:
        server_coin_boost = 1 + (server_alpha_count * 0.08)  # +8% per Alpha Dragon on server
        displayed_coins = int(base_coin_reward * server_coin_boost)

    embed = discord.Embed(
        title=f"A wild {dragon_data['name']} Dragon appeared!",
        description=f"Type `dragon` to catch it!",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=dragon_data['image'])
    dragon_rarity = get_dragon_rarity(dragon_key)
    embed.set_footer(text=f"Coins: {displayed_coins} 🪙¦ Rarity: {dragon_rarity.capitalize()} ({dragon_data['spawn_chance']:.2f}%)")

    msg = await channel.send(embed=embed)

    spawn_ts = int(time.time())
    nv_activator = night_vision_activator if night_vision_active else None
    active_spawns[guild_id] = {
        'dragon_type': dragon_key,
        'channel_id': channel.id,
        'message_id': msg.id,
        'timestamp': spawn_ts,
        'night_vision_activator': nv_activator
    }

    try:
        _conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        _c = _conn.cursor()
        _c.execute(
            'INSERT OR REPLACE INTO active_dragon_spawns (guild_id, dragon_type, channel_id, message_id, spawn_timestamp, night_vision_activator) VALUES (?, ?, ?, ?, ?, ?)',
            (guild_id, dragon_key, channel.id, msg.id, spawn_ts, nv_activator)
        )
        _conn.commit()
        _conn.close()
    except Exception as _e:
        print(f'[spawn] Failed to persist active spawn: {_e}')

    # Dragon stays until caught (no despawn timer)


async def update_raid_embed(guild_id, channel_id, bot, user_tier=None):
    """Update the main raid boss embed with current HP and participant counts for ALL tiers"""
    try:
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_name, boss_rarity, reward_dragon, expires_at, message_id, easy_participants, normal_participants, hard_participants FROM raid_bosses WHERE guild_id = ?',
                  (guild_id,))
        boss_data = c.fetchone()

        if not boss_data or not boss_data[10]:  # No message_id stored
            conn.close()
            return

        easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_name, boss_rarity, reward_dragon, expires_at, message_id, easy_part_str, normal_part_str, hard_part_str = boss_data

        channel = bot.get_channel(channel_id)
        if channel:
            try:
                raid_msg = await channel.fetch_message(message_id)

                dragon_data = DRAGON_TYPES[reward_dragon]

                # Rebuild the ORIGINAL spawn embed with all 3 tiers and updated participant counts
                updated_embed = discord.Embed(
                    title=f"⚔️ RAID BOSS SPAWNED: {boss_name}",
                    description=f"**Rarity:** {boss_rarity.capitalize()}\n\n"
                                f"🎮 **Choose your difficulty tier below!**\n"
                                f"Each tier has its own HP pool and leaderboard.",
                    color=discord.Color.red()
                )

                # Calculate participant counts for each tier
                easy_participants = len(eval(easy_part_str)) if easy_part_str else 0
                normal_participants = len(eval(normal_part_str)) if normal_part_str else 0
                hard_participants = len(eval(hard_part_str)) if hard_part_str else 0

                # Easy tier
                updated_embed.add_field(
                    name="🟢 EASY TIER",
                    value=f"💚 For players with 0-10,000 damage potential\n"
                          f"📊 HP: {easy_hp:,} / {easy_max_hp:,}\n"
                          f"⚔️ Max Damage: 10,000\n"
                          f"👥 Participants: {easy_participants}",
                    inline=True
                )

                # Normal tier
                updated_embed.add_field(
                    name="🟡 NORMAL TIER",
                    value=f"💛 For players with 10,001-70,000 damage potential\n"
                          f"📊 HP: {normal_hp:,} / {normal_max_hp:,}\n"
                          f"⚔️ Max Damage: 70,000\n"
                          f"👥 Participants: {normal_participants}",
                    inline=True
                )

                # Hard tier
                updated_embed.add_field(
                    name="🔴 HARD TIER",
                    value=f"❤️ For players with 70,000+ damage potential\n"
                          f"📊 HP: {hard_hp:,} / {hard_max_hp:,}\n"
                          f"⚔️ Max Damage: 100,000\n"
                          f"👥 Participants: {hard_participants}",
                    inline=True
                )

                updated_embed.add_field(
                    name="🎁 Reward",
                    value=f"{dragon_data['emoji']} **{dragon_data['name']} Dragon**\n"
                          f"✨ 1x per victory + bonus coins",
                    inline=False
                )

                time_left = expires_at - int(time.time())
                hours = max(0, time_left // 3600)
                minutes = max(0, (time_left % 3600) // 60)
                updated_embed.add_field(
                    name="⏰ Duration",
                    value=f"{hours}h {minutes}m",
                    inline=True
                )

                updated_embed.set_footer(text="Click a button to choose your tier! You'll be locked in and cannot change.")

                await raid_msg.edit(embed=updated_embed)
            except Exception as e:
                print(f"Error updating raid embed: {e}")

        conn.close()
    except Exception as e:
        print(f"Error in update_raid_embed: {e}")


class RaidTierSelectView(discord.ui.View):
    def __init__(self, gid, bname, brarity, rdragon):
        super().__init__(timeout=None)
        self.guild_id = gid
        self.boss_name = bname
        self.boss_rarity = brarity
        self.reward_dragon = rdragon

    @discord.ui.button(label="🟢 EASY TIER", style=discord.ButtonStyle.success, emoji="💚")
    async def easy_tier_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_tier(btn_interaction, 'easy')

    @discord.ui.button(label="🟡 NORMAL TIER", style=discord.ButtonStyle.primary, emoji="💛")
    async def normal_tier_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_tier(btn_interaction, 'normal')

    @discord.ui.button(label="🔴 HARD TIER", style=discord.ButtonStyle.danger, emoji="❤️")
    async def hard_tier_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
        await self._join_tier(btn_interaction, 'hard')

    async def _join_tier(self, btn_interaction: discord.Interaction, tier: str):
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT tier FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                 (btn_interaction.guild_id, btn_interaction.user.id))
        existing = c.fetchone()

        if existing:
            conn.close()
            await btn_interaction.response.send_message(
                f"❌ You already joined **{existing[0].upper()}** tier! You cannot change.",
                ephemeral=True
            )
            return

        c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                 (btn_interaction.guild_id, btn_interaction.user.id))
        user_dragons = c.fetchall()

        if not user_dragons:
            conn.close()
            await btn_interaction.response.send_message(
                f"❌ You don't have any dragons! Catch some first.",
                ephemeral=True
            )
            return

        damage_potential = 0
        for dragon_type, count in user_dragons:
            dragon_rarity = 'common'
            for rarity, dragons in DRAGON_RARITY_TIERS.items():
                if dragon_type in dragons:
                    dragon_rarity = rarity
                    break

            damage_per_dragon = RARITY_DAMAGE[dragon_rarity]
            damage_potential += count * damage_per_dragon

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                 (btn_interaction.guild_id, btn_interaction.user.id, 'precisionstone'))
        stone_result = c.fetchone()
        precision_stones = stone_result[0] if stone_result else 0
        precision_bonus = min(precision_stones * 0.05, 0.30)
        damage_potential = int(damage_potential * (1 + precision_bonus))

        if tier == 'easy' and damage_potential > 10000:
            conn.close()
            await btn_interaction.response.send_message(
                f"❌ Your damage potential is **{damage_potential:,}**! Easy tier is for **0-10,000 damage**.\n"
                f"Please join Normal or Hard tier.",
                ephemeral=True
            )
            return
        elif tier == 'normal' and (damage_potential < 10000 or damage_potential > 70000):
            conn.close()
            await btn_interaction.response.send_message(
                f"❌ Your damage potential is **{damage_potential:,}**! Normal tier is for **10,001-70,000 damage**.\n"
                f"Please join an appropriate tier.",
                ephemeral=True
            )
            return
        elif tier == 'hard' and damage_potential < 70000:
            conn.close()
            await btn_interaction.response.send_message(
                f"❌ Your damage potential is only **{damage_potential:,}**! Hard tier requires **70,000+ damage**.\n"
                f"Please join Normal tier.",
                ephemeral=True
            )
            return

        c.execute('''INSERT INTO raid_damage (guild_id, user_id, tier, damage_dealt, attacks_made, last_attack_time)
                     VALUES (?, ?, ?, 0, 0, 0)
                     ON CONFLICT(guild_id, user_id) DO UPDATE SET tier = ?''',
                 (btn_interaction.guild_id, btn_interaction.user.id, tier, tier))

        c.execute(f'SELECT {tier}_participants FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1', (btn_interaction.guild_id,))
        result = c.fetchone()
        if result:
            participants = eval(result[0]) if result[0] else []
            if btn_interaction.user.id not in participants:
                participants.append(btn_interaction.user.id)
                c.execute(f'UPDATE raid_bosses SET {tier}_participants = ? WHERE guild_id = ? AND expires_at = (SELECT MAX(expires_at) FROM raid_bosses WHERE guild_id = ?)',
                         (str(participants), btn_interaction.guild_id, btn_interaction.guild_id))

        conn.commit()
        conn.close()

        # Update main raid embed with new participant count
        await update_raid_embed(btn_interaction.guild_id, btn_interaction.channel_id, btn_interaction.client)

        tier_names = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}
        await btn_interaction.response.send_message(
            f"✅ You joined the **{tier_names[tier]}** tier!\n\n"
            f"Your damage potential: **{damage_potential:,}**\n"
            f"You're now locked in. Use `/raidstatus` to see the boss HP and attack!",
            ephemeral=True
        )


class RaidAttackView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.guild_id = gid

    @discord.ui.button(label="Attack!", style=discord.ButtonStyle.red, emoji="⚔️")
    async def attack_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
        current_time = int(time.time())

        conn_a = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c_a = conn_a.cursor()

        c_a.execute('SELECT tier FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        tier_result = c_a.fetchone()

        c_a.execute('''SELECT easy_max_hp, hard_max_hp, normal_max_hp FROM raid_bosses
                       WHERE guild_id = ?''', (btn_interaction.guild_id,))
        raid_type_result = c_a.fetchone()

        if not raid_type_result:
            conn_a.close()
            await btn_interaction.response.send_message("❌ No active raid boss!", ephemeral=True)
            return

        easy_max_hp, hard_max_hp, normal_max_hp = raid_type_result

        c_a.execute('SELECT tier FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        tier_result = c_a.fetchone()

        if not tier_result:
            conn_a.close()
            await btn_interaction.response.send_message(
                "❌ You haven't selected a tier yet! Use `/raidstatus` to join a tier.",
                ephemeral=True
            )
            return

        user_tier = tier_result[0]

        c_a.execute('SELECT last_attack_time FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        cooldown_result = c_a.fetchone()

        if cooldown_result and cooldown_result[0]:
            time_since_last = current_time - cooldown_result[0]
            cooldown_duration = 10 * 60

            if time_since_last < cooldown_duration:
                time_left = cooldown_duration - time_since_last
                minutes_left = time_left // 60
                seconds_left = time_left % 60
                conn_a.close()
                await btn_interaction.response.send_message(
                    f"⏰ You're still recovering! Attack again in **{minutes_left}m {seconds_left}s**",
                    ephemeral=True
                )
                return

        c_a.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        user_dragons = c_a.fetchall()

        if not user_dragons:
            conn_a.close()
            await btn_interaction.response.send_message(
                "❌ You need dragons to attack!",
                ephemeral=True
            )
            return

        damage = 0
        for dragon_type, count in user_dragons:
            dragon_rarity = 'common'
            for rarity, dragons in DRAGON_RARITY_TIERS.items():
                if dragon_type in dragons:
                    dragon_rarity = rarity
                    break

            damage_per_dragon = RARITY_DAMAGE[dragon_rarity]
            damage += count * damage_per_dragon

        c_a.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id, 'precisionstone'))
        stone_result = c_a.fetchone()
        precision_stones = stone_result[0] if stone_result else 0
        precision_bonus = min(precision_stones * 0.05, 0.30)
        damage = int(damage * (1 + precision_bonus))

        if damage <= 0:
            damage = 1

        c_a.execute(f'UPDATE raid_bosses SET {user_tier}_hp = {user_tier}_hp - ? WHERE guild_id = ?',
                  (damage, btn_interaction.guild_id))

        # Check if tier is defeated
        c_a.execute(f'SELECT {user_tier}_hp FROM raid_bosses WHERE guild_id = ?', (btn_interaction.guild_id,))
        hp_check = c_a.fetchone()
        tier_defeated = False
        if hp_check and hp_check[0] <= 0:
            tier_defeated = True
            c_a.execute(f'UPDATE raid_bosses SET {user_tier}_hp = 0 WHERE guild_id = ?', (btn_interaction.guild_id,))

        c_a.execute('''INSERT INTO raid_damage (guild_id, user_id, tier, damage_dealt, attacks_made, last_attack_time)
                       VALUES (?, ?, ?, ?, 1, ?)
                       ON CONFLICT(guild_id, user_id)
                       DO UPDATE SET damage_dealt = damage_dealt + ?, attacks_made = attacks_made + 1, last_attack_time = ?''',
                  (btn_interaction.guild_id, btn_interaction.user.id, user_tier, damage, current_time, damage, current_time))

        c_a.execute('SELECT damage_dealt FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        total_damage_result = c_a.fetchone()
        user_total_damage = total_damage_result[0] if total_damage_result else damage

        conn_a.commit()

        # Get updated boss data for embed update
        c_a.execute('SELECT easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_name, boss_rarity, reward_dragon, expires_at, message_id FROM raid_bosses WHERE guild_id = ?',
                  (btn_interaction.guild_id,))
        boss_data = c_a.fetchone()

        if boss_data:
            easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_name, boss_rarity, reward_dragon, expires_at, message_id = boss_data

            if message_id:
                try:
                    raid_channel = btn_interaction.client.get_channel(btn_interaction.channel_id)
                    if raid_channel:
                        raid_msg = await raid_channel.fetch_message(message_id)
                        if raid_msg:
                            dragon_data = DRAGON_TYPES[reward_dragon]
                            tier_emoji = {'easy': '🟢', 'normal': '🟡', 'hard': '🔴'}[user_tier]
                            tier_color = {'easy': discord.Color.green(), 'normal': discord.Color.blue(), 'hard': discord.Color.red()}[user_tier]
                            updated_embed = discord.Embed(
                                title=f"⚔️ {user_tier.upper()} TIER RAID",
                                description=f"Boss: {boss_name}\nRarity: {boss_rarity.title()}\nYour Tier: {tier_emoji} {user_tier.upper()}",
                                color=tier_color
                            )

                            if user_tier == 'easy':
                                current_hp, max_hp = easy_hp, easy_max_hp
                            elif user_tier == 'normal':
                                current_hp, max_hp = normal_hp, normal_max_hp
                            else:
                                current_hp, max_hp = hard_hp, hard_max_hp

                            hp_percent = (current_hp / max_hp * 100) if max_hp > 0 else 0
                            bar_length = 20
                            filled = int(bar_length * hp_percent / 100)
                            bar = '█' * filled + '░' * (bar_length - filled)

                            updated_embed.add_field(
                                name="HP",
                                value=f"{bar} {hp_percent:.1f}%\n{current_hp:,} / {max_hp:,}",
                                inline=False
                            )

                            updated_embed.add_field(
                                name="🎁 Reward",
                                value=f"{dragon_data['emoji']} **{dragon_data['name']} Dragon**",
                                inline=True
                            )

                            c_a.execute(f'SELECT {user_tier}_participants FROM raid_bosses WHERE guild_id = ?', (btn_interaction.guild_id,))
                            part_result = c_a.fetchone()
                            participants = len(eval(part_result[0])) if part_result and part_result[0] else 0
                            updated_embed.add_field(
                                name="👥 Participants",
                                value=f"{participants}",
                                inline=True
                            )

                            time_left = expires_at - int(time.time())
                            hours = time_left // 3600
                            minutes = (time_left % 3600) // 60
                            updated_embed.add_field(
                                name="⏰ Time Left",
                                value=f"{hours}h {minutes}m",
                                inline=True
                            )

                            max_damage_per_attack = {'easy': '10,000', 'normal': '25,000', 'hard': '50,000'}[user_tier]
                            updated_embed.add_field(
                                name="Your Stats",
                                value=f"💥 Damage: {user_total_damage:,}\n⚔️ Max per Attack: {max_damage_per_attack}\n🔄 Attacks: {total_damage_result[0] if total_damage_result else 0}",
                                inline=False
                            )

                            c_a.execute(f'SELECT user_id, damage_dealt FROM raid_damage WHERE guild_id = ? AND tier = ? ORDER BY damage_dealt DESC LIMIT 5', (btn_interaction.guild_id, user_tier))
                            leaderboard = c_a.fetchall()
                            lb_text = "**Leaderboard (" + user_tier.upper() + " TIER)**\n"
                            for idx, (uid, dmg) in enumerate(leaderboard, 1):
                                member = btn_interaction.guild.get_member(uid)
                                if member:
                                    medals = ['🥇', '🥈', '🥉']
                                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                                    lb_text += f"{medal} @{member.name}: {dmg:,} damage\n"

                            updated_embed.add_field(
                                name="📊 Leaderboard",
                                value=lb_text,
                                inline=False
                            )

                            await raid_msg.edit(embed=updated_embed)
                except Exception as e:
                    print(f"Error updating raid embed: {e}")

        tier_names = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}

        if tier_defeated:
            await btn_interaction.response.send_message(
                f"⚔️ {btn_interaction.user.mention} dealt **{damage:,}** damage! ({tier_names[user_tier]})\n"
                f"💥 Total Damage: **{user_total_damage:,}**\n\n"
                f"🎉 **{tier_names[user_tier]} TIER DEFEATED!**",
                ephemeral=False
            )
        else:
            await btn_interaction.response.send_message(
                f"⚔️ {btn_interaction.user.mention} dealt **{damage:,}** damage! ({tier_names[user_tier]})\n"
                f"💥 Total Damage: **{user_total_damage:,}**\n"
                f"⏰ Next attack in: **10 minutes**",
                ephemeral=False
            )

        # Ensure user is in the participants list for their tier
        c_a.execute(f'SELECT {user_tier}_participants FROM raid_bosses WHERE guild_id = ?', (btn_interaction.guild_id,))
        part_result = c_a.fetchone()
        if part_result:
            participants = eval(part_result[0]) if part_result[0] else []
            if btn_interaction.user.id not in participants:
                participants.append(btn_interaction.user.id)
                c_a.execute(f'UPDATE raid_bosses SET {user_tier}_participants = ? WHERE guild_id = ?',
                           (str(participants), btn_interaction.guild_id))
                conn_a.commit()

        # Update the ORIGINAL raid spawn embed with updated HP/participants
        await update_raid_embed(btn_interaction.guild_id, btn_interaction.channel_id, btn_interaction.client, user_tier)

        # Update the /raidstatus message if this is called from there
        if btn_interaction.message:
            try:
                c_a.execute('SELECT tier FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                          (btn_interaction.guild_id, btn_interaction.user.id))
                tier_result = c_a.fetchone()
                if tier_result:
                    user_tier_check = tier_result[0]

                    c_a.execute('''SELECT easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp,
                                   boss_name, boss_rarity, reward_dragon, expires_at, easy_participants, normal_participants, hard_participants
                                   FROM raid_bosses WHERE guild_id = ?''', (btn_interaction.guild_id,))
                    fresh_boss_data = c_a.fetchone()

                    if fresh_boss_data:
                        easy_hp_f, easy_max_hp_f, normal_hp_f, normal_max_hp_f, hard_hp_f, hard_max_hp_f, boss_name_f, boss_rarity_f, reward_dragon_f, expires_at_f, easy_part_f, normal_part_f, hard_part_f = fresh_boss_data

                        c_a.execute('SELECT damage_dealt, attacks_made FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                                  (btn_interaction.guild_id, btn_interaction.user.id))
                        user_stats = c_a.fetchone()
                        user_damage_f, user_attacks_f = user_stats if user_stats else (0, 0)

                        tier_hp_map = {
                            'easy': (easy_hp_f, easy_max_hp_f, easy_part_f),
                            'normal': (normal_hp_f, normal_max_hp_f, normal_part_f),
                            'hard': (hard_hp_f, hard_max_hp_f, hard_part_f)
                        }
                        tier_hp_f, tier_max_hp_f, tier_part_f = tier_hp_map[user_tier_check]
                        tier_part = eval(tier_part_f) if tier_part_f else []

                        hp_percentage = (tier_hp_f / tier_max_hp_f * 100) if tier_max_hp_f > 0 else 0
                        hp_bar_length = 20
                        filled = int((hp_percentage / 100) * hp_bar_length)
                        hp_bar = "█" * filled + "░" * (hp_bar_length - filled)

                        time_left = expires_at_f - int(time.time())
                        reward_data = DRAGON_TYPES[reward_dragon_f]
                        tier_names_display = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}
                        tier_damage_caps = {'easy': 25000, 'normal': 60000, 'hard': 100000}

                        updated_raidstatus_embed = discord.Embed(
                            title=f"⚔️ {tier_names_display[user_tier_check]} TIER RAID",
                            description=f"**Boss:** {boss_name_f}\n"
                                       f"**Rarity:** {boss_rarity_f.title()}\n"
                                       f"**Your Tier:** {tier_names_display[user_tier_check]}\n\n"
                                       f"**HP:** {tier_hp_f:,} / {tier_max_hp_f:,}\n"
                                       f"{hp_bar} {hp_percentage:.1f}%\n\n"
                                       f"🎁 **Reward:** {reward_data['emoji']} {reward_data['name']} Dragon\n"
                                       f"👥 **Participants in your tier:** {len(tier_part)}\n"
                                       f"⏰ **Time Left:** {format_time_remaining(time_left)}\n\n"
                                       f"**Your Stats:**\n"
                                       f"💥 Damage: {user_damage_f:,}\n"
                                       f"⚔️ Max per Attack: {tier_damage_caps[user_tier_check]:,}\n"
                                       f"🔄 Attacks: {user_attacks_f}",
                            color=discord.Color.red()
                        )

                        c_a.execute('''SELECT user_id, damage_dealt FROM raid_damage
                                     WHERE guild_id = ? AND tier = ?
                                     ORDER BY damage_dealt DESC LIMIT 5''',
                                   (btn_interaction.guild_id, user_tier_check))
                        tier_leaderboard = c_a.fetchall()

                        if tier_leaderboard:
                            lb_text = ""
                            for idx, (uid, dmg) in enumerate(tier_leaderboard, 1):
                                member = btn_interaction.guild.get_member(uid)
                                if member:
                                    medals = ['🥇', '🥈', '🥉']
                                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                                    lb_text += f"{medal} {member.mention}: {dmg:,} damage\n"

                            updated_raidstatus_embed.add_field(
                                name=f"📊 Leaderboard ({user_tier_check.upper()} TIER)",
                                value=lb_text,
                                inline=False
                            )

                        await btn_interaction.message.edit(embed=updated_raidstatus_embed)
            except Exception as e:
                print(f"Error updating raidstatus message: {e}")

        c_a.execute('SELECT easy_hp, normal_hp, hard_hp, expires_at, reward_dragon, boss_rarity, boss_name FROM raid_bosses WHERE guild_id = ?',
                  (btn_interaction.guild_id,))
        boss_update = c_a.fetchone()

        if boss_update:
            easy_hp, normal_hp, hard_hp, expires_at, reward_dragon, boss_rarity, boss_name = boss_update

            defeated_tiers = []
            if easy_hp <= 0:
                defeated_tiers.append('easy')
            if normal_hp <= 0:
                defeated_tiers.append('normal')
            if hard_hp <= 0:
                defeated_tiers.append('hard')

            if defeated_tiers:
                reward_data = DRAGON_TYPES[reward_dragon]

                defeated_embed = discord.Embed(
                    title=f"💀 RAID TIER(S) DEFEATED!",
                    description=f"**{boss_name}** has been slain!\n\n🎁 **Rewards distributed per tier:**",
                    color=discord.Color.gold()
                )

                tier_rewards = {'easy': 1, 'normal': 2, 'hard': 3}

                for tier in defeated_tiers:
                    tier_names_display = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}

                    c_a.execute('''SELECT user_id, damage_dealt FROM raid_damage
                                  WHERE guild_id = ? AND tier = ?
                                  ORDER BY damage_dealt DESC LIMIT 10''',
                               (btn_interaction.guild_id, tier))
                    tier_damagers = c_a.fetchall()

                    coin_multipliers = {'epic': 1.0, 'legendary': 1.5, 'mythic': 2.5, 'ultra': 5.0}
                    base_coin_rewards = [1000, 750, 500, 400, 300, 250, 200, 150, 100, 50]
                    multiplier = coin_multipliers.get(boss_rarity, 1.0)
                    adjusted_rewards = [int(coins * multiplier) for coins in base_coin_rewards]

                    dragon_reward_count = tier_rewards[tier]

                    tier_field = f"**Leaderboard:**\n"
                    for idx, (uid, dmg) in enumerate(tier_damagers, 1):
                        member = btn_interaction.guild.get_member(uid)
                        if member:
                            await add_dragons(btn_interaction.guild_id, uid, reward_dragon, dragon_reward_count)
                            bonus_coins = adjusted_rewards[idx-1]
                            await asyncio.to_thread(update_balance, btn_interaction.guild_id, uid, bonus_coins)

                            lucky_charm_chance = random.randint(1, 100)
                            if lucky_charm_chance <= 5:
                                c_a.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                               VALUES (?, ?, ?, 1)
                                               ON CONFLICT(guild_id, user_id, item_type)
                                               DO UPDATE SET count = count + 1''',
                                            (btn_interaction.guild_id, uid, 'luckycharm'))

                            dragonscale_chance = random.randint(1, 100)
                            if dragonscale_chance <= 2:
                                c_a.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                               VALUES (?, ?, ?, 1)
                                               ON CONFLICT(guild_id, user_id, item_type)
                                               DO UPDATE SET count = count + 1''',
                                            (btn_interaction.guild_id, uid, 'dragonscale'))

                            medals = ['🥇', '🥈', '🥉']
                            medal = medals[idx-1] if idx <= 3 else f"#{idx}"

                            reward_text = f"💥 {dmg:,} dmg | {reward_data['emoji']} +{dragon_reward_count} | 💰 +{bonus_coins}"
                            if lucky_charm_chance <= 5:
                                reward_text += " | 🍀+1"
                            if dragonscale_chance <= 2:
                                reward_text += " | ✨+1"

                            tier_field += f"{medal} {member.display_name}: {reward_text}\n"

                    defeated_embed.add_field(
                        name=tier_names_display[tier],
                        value=tier_field,
                        inline=False
                    )

                # Delete only this defeated tier's damage records
                tier_name = list(defeated_tiers)[0]
                c_a.execute('DELETE FROM raid_damage WHERE guild_id = ? AND tier = ?',
                           (btn_interaction.guild_id, tier_name))

                # Check if ANY raid tiers are still active
                remaining_tiers = c_a.execute('SELECT DISTINCT tier FROM raid_damage WHERE guild_id = ?',
                                             (btn_interaction.guild_id,)).fetchall()

                # Check if ALL tiers are now defeated
                all_tiers_hp = c_a.execute('SELECT easy_hp, normal_hp, hard_hp FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1',
                                          (btn_interaction.guild_id,)).fetchone()

                if all_tiers_hp and all(hp <= 0 for hp in all_tiers_hp):
                    defeated_embed.add_field(
                        name="🐉 Dragons Are Spawning Again!",
                        value="All raid tiers have been defeated! Wild dragons will now spawn normally.",
                        inline=False
                    )
                    c_a.execute('DELETE FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1', (btn_interaction.guild_id,))
                    c_a.execute('DELETE FROM raid_damage WHERE guild_id = ?', (btn_interaction.guild_id,))
                    if btn_interaction.guild_id in raid_boss_active:
                        del raid_boss_active[btn_interaction.guild_id]
                else:
                    remaining_tiers = c_a.execute('SELECT DISTINCT tier FROM raid_damage WHERE guild_id = ?',
                                                 (btn_interaction.guild_id,)).fetchall()

                    if not remaining_tiers:
                        raid_info = c_a.execute('SELECT easy_participants, normal_participants, hard_participants FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1',
                                               (btn_interaction.guild_id,)).fetchone()

                        if raid_info:
                            easy_part_str, normal_part_str, hard_part_str = raid_info
                            easy_had_players = bool(eval(easy_part_str)) if easy_part_str else False
                            normal_had_players = bool(eval(normal_part_str)) if normal_part_str else False
                            hard_had_players = bool(eval(hard_part_str)) if hard_part_str else False

                            boss_hp = c_a.execute('SELECT easy_hp, normal_hp, hard_hp FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1',
                                                 (btn_interaction.guild_id,)).fetchone()

                            if boss_hp:
                                easy_defeated = boss_hp[0] <= 0 if easy_had_players else True
                                normal_defeated = boss_hp[1] <= 0 if normal_had_players else True
                                hard_defeated = boss_hp[2] <= 0 if hard_had_players else True

                                all_played_defeated = easy_defeated and normal_defeated and hard_defeated

                                if all_played_defeated:
                                    defeated_embed.add_field(
                                        name="🐉 Dragons Are Spawning Again!",
                                        value="All raid tiers have been defeated! Wild dragons will now spawn normally.",
                                        inline=False
                                    )
                                    c_a.execute('DELETE FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1', (btn_interaction.guild_id,))
                                    if btn_interaction.guild_id in raid_boss_active:
                                        del raid_boss_active[btn_interaction.guild_id]
                                else:
                                    defeated_embed.add_field(
                                        name="✅ Tier Defeated!",
                                        value="This raid tier has been defeated, but other tiers are still being played!",
                                        inline=False
                                    )
                        else:
                            defeated_embed.add_field(
                                name="✅ Tier Defeated!",
                                value="This raid tier has been defeated!",
                                inline=False
                            )
                    else:
                        defeated_embed.add_field(
                            name="✅ Tier Defeated!",
                            value="This raid tier has been defeated, but other tiers are still active!",
                            inline=False
                        )

                conn_a.commit()

                try:
                    defeated_message = await btn_interaction.channel.send(embed=defeated_embed)
                except:
                    pass

        conn_a.close()


class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.bot.user} is online!')
        init_db()

        # Sync slash commands with Discord
        try:
            synced = await self.bot.tree.sync()
            print(f'✅ Synced {len(synced)} slash commands')
        except Exception as e:
            print(f'❌ Failed to sync commands: {e}')

        # Clean up old bot messages from previous sessions
        async def cleanup_old_messages():
            """Delete old dragon spawns, black market, and other bot messages that won't work"""
            try:
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                c.execute('SELECT guild_id, spawn_channel_id FROM spawn_config')
                spawn_channels_list = c.fetchall()
                conn.close()

                deleted_count = 0
                for guild_id, channel_id in spawn_channels_list:
                    try:
                        channel = self.bot.get_channel(channel_id)
                        if not channel:
                            continue

                        messages_to_check = []
                        async for message in channel.history(limit=3):
                            messages_to_check.append(message)

                        current_time = int(time.time())

                        for message in messages_to_check:
                            message_age = current_time - int(message.created_at.timestamp())

                            if message_age < 1:
                                continue

                            if message_age > 120:
                                continue

                            if message.author == self.bot.user:
                                try:
                                    await message.delete()
                                    deleted_count += 1
                                except:
                                    pass
                    except Exception as e:
                        logger.error(f'Error cleaning up channel {channel_id}: {e}')

                if deleted_count > 0:
                    print(f'🧹 Cleaned up {deleted_count} old bot messages from previous sessions')
            except Exception as e:
                logger.error(f'Error in cleanup_old_messages: {e}')

        # Run database operations in thread to avoid blocking event loop
        def load_data():
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()
            c.execute('SELECT guild_id, spawn_channel_id FROM spawn_config')
            for guild_id, channel_id in c.fetchall():
                spawn_channels[guild_id] = channel_id

            c.execute('SELECT guild_id, user_id, premium_until FROM premium_users')
            current_time = int(time.time())
            for guild_id, user_id, premium_until in c.fetchall():
                if premium_until > current_time:
                    if guild_id not in premium_users:
                        premium_users[guild_id] = {}
                    premium_users[guild_id][user_id] = premium_until

            # Recover active Dragonfest events from database
            c.execute('DELETE FROM dragonfest_stats WHERE event_start < ?', (current_time - 7200,))

            c.execute('''SELECT DISTINCT guild_id, MAX(event_start) FROM dragonfest_stats
                         WHERE event_start > ? GROUP BY guild_id''',
                      (current_time - 7200,))
            for guild_id, event_start in c.fetchall():
                if guild_id not in active_dragonfest:
                    estimated_end = event_start + 7200
                    if estimated_end > current_time:
                        active_dragonfest[guild_id] = {'start': event_start, 'end': estimated_end}
                        print(f"🎉 Recovered Dragonfest for guild {guild_id}, active for ~{(estimated_end - current_time) // 60} more minutes")

            # NOTE: We do NOT auto-recover dragonscale events because we don't store actual duration
            c.execute('DELETE FROM dragonscale_stats')

            # Recover active Raid Bosses from database
            c.execute('SELECT guild_id, expires_at FROM raid_bosses WHERE expires_at > ?', (current_time,))
            for guild_id, expires_at in c.fetchall():
                raid_boss_active[guild_id] = {
                    'active': True,
                    'spawn_time': current_time,
                    'despawn_time': expires_at,
                    'manual_spawn': False
                }
                print(f"⚔️ Recovered Raid Boss for guild {guild_id}, despawning in ~{(expires_at - current_time) // 60} minutes")

            conn.commit()
            conn.close()

        await asyncio.to_thread(load_data)

        await cleanup_old_messages()

        print(f'🐉 Dragon Bot ready! Serving {len(self.bot.guilds)} servers')

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        """Global error handler for all slash commands"""
        error_msg = f"Command Error: {interaction.command.name if interaction.command else 'Unknown'}\nUser: {interaction.user}\nGuild: {interaction.guild}\nError: {str(error)}"
        error_traceback = ''.join(traceback.format_exception(type(error), error, error.__traceback__))

        logger.error(error_msg, exc_info=error)

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                embed_data = {
                    "username": "Dragon Bot Error Logger",
                    "embeds": [{
                        "title": "🔴 Command Error",
                        "description": f"**Command:** {interaction.command.name if interaction.command else 'Unknown'}\n**User:** {interaction.user}\n**Guild:** {interaction.guild}",
                        "color": 16711680,
                        "fields": [{
                            "name": "Error Details",
                            "value": f"```{error_traceback[:1024]}```" if len(error_traceback) > 1024 else f"```{error_traceback}```",
                            "inline": False
                        }]
                    }]
                }
                async with session.post(ERROR_WEBHOOK_URL, json=embed_data) as resp:
                    pass
        except:
            pass

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ **Error occurred!** Check logs for details.\n```{str(error)[:200]}```",
                    ephemeral=False
                )
            else:
                await interaction.followup.send(
                    f"❌ **Error occurred!** Check logs for details.\n```{str(error)[:200]}```",
                    ephemeral=False
                )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        """Catch all other errors"""
        error_msg = f"Event Error in {event}: {args} {kwargs}"
        error_traceback = traceback.format_exc()
        logger.error(error_msg, exc_info=True)

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                embed_data = {
                    "username": "Dragon Bot Error Logger",
                    "embeds": [{
                        "title": "🔴 Event Error",
                        "description": f"**Event:** {event}",
                        "color": 16711680,
                        "fields": [{
                            "name": "Error Details",
                            "value": f"```{error_traceback[:1024]}```" if len(error_traceback) > 1024 else f"```{error_traceback}```",
                            "inline": False
                        }]
                    }]
                }
                async with session.post(ERROR_WEBHOOK_URL, json=embed_data) as resp:
                    pass
        except:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        # Special check for Cat Bot (ID: 966695034340663367) posting in dragon channels
        CAT_BOT_ID = 966695034340663367

        if message.author.bot:
            if message.author.id == CAT_BOT_ID:
                if message.guild and message.guild.id in spawn_channels:
                    if spawn_channels[message.guild.id] == message.channel.id:
                        cat_bot_mocks = [
                            f"🐉 Ayo {message.author.mention}! This is **DRAGON** territory, not for your little kitties! 🐱\nGet your cats outta here! 😤",
                            f"😤 **INTRUDER ALERT!** {message.author.mention} is spawning CATS in the dragon channel!\n🐉 > 🐱 Know your place, cat bot!",
                            f"🔥 {message.author.mention} really thought they could spawn cats here? 💀\nThis is **DRAGON ZONE** buddy! 🐉 Take your meows elsewhere!",
                            f"🚨 **TERRITORY VIOLATION!** {message.author.mention} detected!\n\n🐉 Dragons > 🐱 Cats\nStay in your own channel, furball! 😂",
                            f"💀 Bruh {message.author.mention}... you're in the wrong neighborhood 🐉\nThis ain't no cat cafe, this is dragon territory! Get lost! 🔥",
                            f"⚔️ **DRAGON VS CAT BATTLE!**\n\n🐉 Dragon Bot: Infinite Power\n🐱 {message.author.mention}: Smol bean\n\nVerdict: GET OUT! 😤",
                        ]
                        await asyncio.sleep(0.5)
                        await message.channel.send(random.choice(cat_bot_mocks))
                        return
            return

        guild_id = message.guild.id
        message_lower = message.content.lower().strip()

        # ==================== DEV COMMANDS (-db prefix) ====================
        if message.content.startswith('-db ') and message.author.id == DEV_USER_ID:
            try:
                args = message.content[4:].strip().split()
                if not args:
                    return

                command = args[0].lower()

                # -db help
                if command == 'help':
                    embed = discord.Embed(
                        title="🔧 Dev Commands",
                        description="All commands use `-db` prefix",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Dragon Nest", value=(
                        "`-db reset-perks <@user>` - Reset all Dragon Nest perks for a user\n"
                        "`-db reset-perks *` - Reset all Dragon Nest perks for ALL users in server\n"
                        "`-db list-softlock` - Show all softlocked users\n"
                        "`-db fix-softlock <@user>` - Remove softlock from user\n"
                        "`-db set-dragonnest-level <@user> <level>` - Set Dragon Nest level (0-10)\n"
                    ), inline=False)
                    embed.add_field(name="Inventory", value=(
                        "`-db resetinventory <@user>` - Reset user's dragons, coins, and packs\n"
                    ), inline=False)
                    embed.add_field(name="Events", value=(
                        "`-db dragonfest <minutes>` - Start dragonfest\n"
                        "`-db spawnraid [hours]` - Spawn raid boss\n"
                        "`-db spawnblackmarket` - Spawn Black Market in this channel\n"
                        "`-db clearevents` - Clear all events\n"
                    ), inline=False)
                    embed.add_field(name="Spawn Management", value=(
                        "`-db spawnstatus` - Check dragon spawn status\n"
                        "`-db resetspawn` - Force dragons to spawn immediately\n"
                    ), inline=False)
                    embed.add_field(name="Raid Management", value=(
                        "`-db raidinfo` - Show current raid status\n"
                        "`-db raidkill` - Instantly defeat the raid boss\n"
                    ), inline=False)
                    embed.add_field(name="Giveaways", value=(
                        "`-db giveaway` - Create pack giveaway\n"
                    ), inline=False)
                    embed.add_field(name="Give Items", value=(
                        "`-db givepack <guild_id> <user_id> <type> <amount>`\n"
                        "`-db givepremium <guild_id> <user_id> <days>`\n"
                        "`-db givecoins <@user> <amount>`\n"
                        "`-db givedragons <@user> <type> <amount>`\n"
                    ), inline=False)
                    embed.add_field(name="Resets", value=(
                        "`-db resetquests` - Reset all Dragonpass quests\n"
                        "`-db resetbattlepass` - Reset battlepass for all\n"
                        "`-db resetbingo` - Reset all bingo cards\n"
                        "`-db resetbreedcooldown <@user>` - Reset breeding cooldown for a user\n"
                        "`-db resetbreeding` - Clear all breeding sessions\n"
                        "`-db wipeserver confirm` - ⚠️ DELETE EVERYTHING (all users/items/coins/alphas)\n"
                    ), inline=False)
                    embed.add_field(name="System", value=(
                        "`-db restart` - Restart the bot\n"
                        "`-db dbstatus` - Show database statistics\n"
                    ), inline=False)
                    embed.add_field(name="Dragonpass Admin", value=(
                        "`-db passgrant <user_id|*> <level>` - Set Dragonpass level for one user or all users in the server\n"
                    ), inline=False)
                    embed.add_field(name="Special Events", value=(
                        "`-db dragonfest <minutes>` - Start a Dragonfest event (server-wide boost)\n"
                    ), inline=False)
                    await message.channel.send(embed=embed)
                    return

                # Import commands from admin cog
                from cogs.admin import handle_dev_command
                await handle_dev_command(message, command, args[1:])
            except Exception as e:
                logger.error(f"Error in dev command '{args[0] if args else 'unknown'}': {e}", exc_info=True)
                try:
                    await message.channel.send(f"❌ **Error executing command:** {str(e)}")
                except:
                    pass
            return

        # Check for dragon typos ANYWHERE (not just in spawn channel with active spawn)
        common_typos = [
            'dragin', 'dargon', 'dragoon', 'drago', 'dragn', 'daragon',
            'dragan', 'draogn', 'drgaon', 'drgen', 'dragen', 'dragno',
            'drgon', 'dragom', 'dragpn', 'drqgon', 'drzgon', 'dragob',
            'draton', 'dravon', 'dragón', 'drágon',
            'draggon', 'dragoan', 'draragon', 'drgagon'
        ]

        word_count = len(message_lower.split())

        is_typo = False
        if message_lower != 'dragon' and word_count == 1:
            if message_lower in common_typos:
                is_typo = True
            elif len(message_lower) >= 4 and len(message_lower) <= 10:
                dragon_chars = set('dragon')
                msg_chars = set(message_lower)
                if len(dragon_chars & msg_chars) >= 5:
                    is_typo = True

        if is_typo:
            mock_messages = [
                f"🤡 Did you just try to type 'dragon'? You wrote '{message.content}' LMAO",
                f"😂 '{message.content}'??? It's literally just 'dragon' bro",
                f"💀 Imagine misspelling 'dragon' as '{message.content}'",
                f"🤦 '{message.content}' is NOT how you spell dragon buddy",
                f"😹 Nice try with '{message.content}', maybe learn to type?",
                f"🎪 Everyone look! {message.author.mention} typed '{message.content}' instead of 'dragon'",
                f"📚 D-R-A-G-O-N. Not '{message.content}'. Got it?",
                f"🥴 '{message.content}'... were you drunk while typing?",
                f"🤓 It's spelled 'dragon', not '{message.content}' genius",
                f"💩 That's not even close! '{message.content}' → 'dragon'",
                f"🎯 You missed! Try again: d-r-a-g-o-n (not '{message.content}')",
                f"👶 Even a 5 year old can spell 'dragon' better than '{message.content}'"
            ]
            await message.channel.send(random.choice(mock_messages))
            return

        # Check for "cat" in dragon channel - mock the user
        if message.content.lower().strip() == 'cat':
            if guild_id in spawn_channels and spawn_channels[guild_id] == message.channel.id:
                cat_mocks = [
                    f"🐉 {message.author.mention} just said 'cat' in the DRAGON channel??? 💀\nYou lost? This is dragon territory! 🐱❌",
                    f"😤 WHO SAID THE C-WORD IN HERE?! {message.author.mention} said **CAT**?!\nWrong channel buddy! 🐉 > 🐱",
                    f"🚨 **ALERT!** {message.author.mention} mentioned CATS in the dragon channel!\nDisgraceful! Get that outta here! 🐉",
                    f"💀 {message.author.mention}... did you really just say 'cat'? In the DRAGON channel?\nYou're as confused as a cat in a doghouse! 🤦",
                    f"😹 Bro {message.author.mention}, this is a DRAGON channel, not a **CAT** channel!\nLearn the difference! 🐉🚫🐱",
                    f"🔥 {message.author.mention} really thought cats belonged here??? 💀\nThis is DRAGON ZONE exclusive! Cats stay outside! 🚪",
                    f"⚔️ **DRAGON SUPREMACY!** {message.author.mention} tried to bring up cats! 🐱\n🐉 We don't do that here! Dragons only! 👑",
                    f"🤡 {message.author.mention} looking foolish saying 'cat' in the dragon channel lmaooo\nBetter luck next time genius! 😂",
                ]
                await message.channel.send(random.choice(cat_mocks))
                return

        # Check for dragon catch (must be in spawn channel with active spawn)
        if message.content.lower().strip() == 'dragon':

            if guild_id not in active_spawns:
                return

            spawn_data = active_spawns[guild_id]
            if spawn_data['channel_id'] != message.channel.id:
                return

            # Check if player is softlocked
            is_softlocked, upgrade_level = is_player_softlocked(guild_id, message.author.id)
            if is_softlocked:
                next_upgrade_level = upgrade_level + 1
                upgrade_cost = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('cost', 0)
                softlock_embed = discord.Embed(
                    title="🔒 Dragon Nest Upgrade Required!",
                    description=f"You have enough coins to upgrade your Dragon Nest!\n\n"
                                f"**Current Level:** {upgrade_level}\n"
                                f"**Upgrade Cost:** {upgrade_cost:,} 🪙\n\n"
                                f"You're **softlocked** until you upgrade. Use `/dragonnest` to upgrade!",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=softlock_embed, delete_after=5)
                return

            # Initialize pack_rewards at the start so it's available throughout the entire block
            pack_rewards = []

            # Use async spawn lock to prevent race conditions when multiple users catch simultaneously
            from state import get_spawn_lock
            spawn_lock = get_spawn_lock(guild_id)
            async with spawn_lock:
                # Double-check spawn still exists after acquiring lock
                if guild_id not in active_spawns:
                    current_time = time.time()

                    if guild_id in last_catch_attempts:
                        last_winner = last_catch_attempts[guild_id]
                        time_diff = round((current_time - last_winner['timestamp']) * 1000)

                        is_dragonscale_active = guild_id in active_dragonscales and active_dragonscales[guild_id] > current_time

                        if time_diff < 5000 and not is_dragonscale_active:
                            mock_messages = [
                                f"💀 {message.author.mention} was **{time_diff}ms** too slow! {last_winner['username']} caught the dragon first! 🐉",
                                f"⚡ **ALMOST!** {message.author.mention} missed by {time_diff}ms! {last_winner['username']} was faster! 🏃",
                                f"😅 {message.author.mention} tried, but {last_winner['username']} beat you by {time_diff}ms! Better luck next time! 🐉",
                                f"🏁 {message.author.mention} came in **2nd place** ({time_diff}ms behind {last_winner['username']})! So close! 😭",
                                f"⏱️ {message.author.mention}: {time_diff}ms **TOO SLOW**! {last_winner['username']} got the dragon! ⚡",
                                f"💨 {message.author.mention} lost the race by {time_diff}ms to {last_winner['username']}! Better practice your reflexes! 🐌",
                                f"🥈 {message.author.mention} got silver! {last_winner['username']} took gold ({time_diff}ms faster)! 🥇",
                            ]
                            await message.channel.send(random.choice(mock_messages))
                else:
                    spawn_data = active_spawns[guild_id]

                    last_spawn_data[guild_id] = spawn_data.copy()

                    try:
                        spawn_msg = await message.channel.fetch_message(spawn_data['message_id'])
                        await spawn_msg.delete()
                    except:
                        pass

                    del active_spawns[guild_id]

                    try:
                        conn_catch = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c_catch = conn_catch.cursor()
                        c_catch.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                                      (int(time.time()), guild_id))
                        c_catch.execute('DELETE FROM active_dragon_spawns WHERE guild_id = ?', (guild_id,))
                        conn_catch.commit()
                        conn_catch.close()
                    except:
                        pass

                    last_catch_attempts[guild_id] = {
                        'user_id': message.author.id,
                        'timestamp': time.time(),
                        'username': message.author.display_name
                    }

                    dragon_key = spawn_data['dragon_type']
                    dragon_data = DRAGON_TYPES[dragon_key]
                    item_boost_message = ""

                    # Check for Night Vision
                    if get_active_item(guild_id, message.author.id, 'night_vision'):
                        current_hour = datetime.now().hour
                        is_nighttime = current_hour >= 20 or current_hour < 8

                        if is_nighttime and random.random() < 0.5:
                            night_dragon_key, night_dragon_data = get_higher_rarity_dragon(min_value=dragon_data['value'])
                            dragon_key = night_dragon_key
                            dragon_data = night_dragon_data
                            item_boost_message = "\n🌙 **Night Vision triggered!** Higher rarity dragon found!"
                        elif not is_nighttime:
                            item_boost_message = "\n🌙 **Night Vision** (inactive - only works 20:00-08:00)"

                    catch_time = time.time() - spawn_data['timestamp']

                    # Record discovery if first time caught in server
                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('SELECT dragon_type FROM server_discoveries WHERE guild_id = ? AND dragon_type = ?',
                              (guild_id, dragon_key))
                    discovery = c.fetchone()
                    if not discovery:
                        c.execute('''INSERT INTO server_discoveries (guild_id, dragon_type, first_discovered_by, first_discovered_at, total_caught)
                                     VALUES (?, ?, ?, ?, 1)''',
                                  (guild_id, dragon_key, message.author.id, int(time.time())))
                    else:
                        c.execute('UPDATE server_discoveries SET total_caught = total_caught + 1 WHERE guild_id = ? AND dragon_type = ?',
                                  (guild_id, dragon_key))

                    # Update catch time records
                    c.execute('SELECT fastest_catch, slowest_catch FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                              (guild_id, message.author.id, dragon_key))
                    catch_record = c.fetchone()

                    if catch_record:
                        fastest = catch_record[0] if catch_record[0] > 0 else catch_time
                        slowest = catch_record[1] if catch_record[1] > 0 else catch_time

                        if catch_time < fastest:
                            fastest = catch_time
                        if catch_time > slowest:
                            slowest = catch_time

                        c.execute('''UPDATE user_dragons SET fastest_catch = ?, slowest_catch = ?
                                     WHERE guild_id = ? AND user_id = ? AND dragon_type = ?''',
                                  (fastest, slowest, guild_id, message.author.id, dragon_key))
                    else:
                        c.execute('''INSERT INTO user_dragons (guild_id, user_id, dragon_type, count, fastest_catch, slowest_catch)
                                     VALUES (?, ?, ?, 0, ?, ?)''',
                                  (guild_id, message.author.id, dragon_key, catch_time, catch_time))

                    conn.commit()
                    conn.close()

                    # Apply perks
                    base_amount = 1
                    final_amount, pack_rewards, time_bonus, perks_applied = apply_perks(guild_id, message.author.id, base_amount, dragon_key)

                    # Apply items (Night Vision, Dragon Magnet)
                    final_amount = apply_items(guild_id, message.author.id, final_amount)

                    # Apply Knowledge Book passive bonus (+2% catch per book)
                    knowledge_bonus = get_passive_bonus(guild_id, message.author.id, 'catch')
                    if knowledge_bonus > 0:
                        final_amount = int(final_amount * (1 + knowledge_bonus))
                        perks_applied.append(f"📚 Knowledge Book (+{int(knowledge_bonus*100)}% boost)")

                    # Apply Lucky Charm (2x catch rate)
                    current_time = int(time.time())
                    if guild_id in active_luckycharms and message.author.id in active_luckycharms[guild_id]:
                        if active_luckycharms[guild_id][message.author.id] > current_time:
                            final_amount *= 2
                            perks_applied.append(f"🍀 Lucky Charm (doubled!)")

                    # Check for Alpha Dragon server-wide effects
                    alpha_effect_triggered = False
                    alpha_owner_name = None
                    alpha_dragon_name = None
                    alpha_multiplier = 1
                    dragonscale_event_minutes = 0

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()

                    c.execute('''SELECT u.user_id, u.name FROM user_alphas u
                                 WHERE u.guild_id = ?''', (guild_id,))
                    all_alphas = c.fetchall()

                    if all_alphas and random.random() < 0.05:
                        alpha_owner_id, alpha_name = random.choice(all_alphas)
                        alpha_owner = message.guild.get_member(alpha_owner_id)

                        if random.random() < 0.95:
                            rng = random.random()
                            if rng < 0.75:
                                alpha_multiplier = 2
                            else:
                                alpha_multiplier = 3
                            final_amount *= alpha_multiplier
                            alpha_effect_triggered = True
                            alpha_owner_name = alpha_owner.display_name if alpha_owner else "Unknown"
                            alpha_dragon_name = alpha_name
                        else:
                            dragonscale_event_minutes = 0.5
                            dragonscale_event_seconds = 30

                            if guild_id not in active_dragonscales or active_dragonscales[guild_id] <= current_time:
                                active_dragonscales[guild_id] = current_time + dragonscale_event_seconds
                                dragonscale_event_starts[guild_id] = current_time
                            else:
                                active_dragonscales[guild_id] += dragonscale_event_seconds

                            conn.commit()
                            alpha_effect_triggered = True
                            alpha_owner_name = alpha_owner.display_name if alpha_owner else "Unknown"
                            alpha_dragon_name = alpha_name

                    # Add dragons and coins to user
                    if final_amount > 0:
                        await add_dragons(guild_id, message.author.id, dragon_key, final_amount)
                        bingo_just_completed = update_bingo_on_catch(guild_id, message.author.id, dragon_key)
                        base_coins = max(2, int(dragon_data['value'] * final_amount))
                        coins_earned = base_coins

                        c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ?', (guild_id,))
                        server_alpha_count = c.fetchone()[0]

                        c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ? AND user_id = ?', (guild_id, message.author.id))
                        user_alpha_count = c.fetchone()[0]

                        server_coin_bonus = server_alpha_count * 0.08
                        user_coin_bonus = user_alpha_count * 0.15
                        total_coin_multiplier = 1 + server_coin_bonus + user_coin_bonus
                        coins_earned = int(coins_earned * total_coin_multiplier)
                        alpha_coin_bonus = coins_earned - base_coins

                        # Gold Rush: +50% coin bonus if active
                        from utils import get_active_item as _get_active_item
                        if _get_active_item(guild_id, message.author.id, 'gold_rush'):
                            coins_earned = int(coins_earned * 1.5)

                        await update_balance_and_check_trophies(self.bot, guild_id, message.author.id, coins_earned)

                        # Track dragonfest catches if active
                        dragonfest_data = active_dragonfest.get(guild_id)
                        if dragonfest_data and (isinstance(dragonfest_data, dict) and dragonfest_data['end'] > current_time or isinstance(dragonfest_data, int) and dragonfest_data > current_time):
                            dragonfest_data = active_dragonfest.get(guild_id)
                            if isinstance(dragonfest_data, dict):
                                event_start = dragonfest_data['start']
                            else:
                                event_start = current_time

                            try:
                                conn_df = sqlite3.connect('dragon_bot.db', timeout=120.0, isolation_level=None)
                                c_df = conn_df.cursor()

                                c_df.execute('''INSERT INTO dragonfest_event_log
                                               (guild_id, user_id, event_start, dragon_type, amount, caught_at)
                                               VALUES (?, ?, ?, ?, ?, ?)''',
                                            (guild_id, message.author.id, event_start, dragon_key, final_amount, int(time.time())))

                                c_df.close()
                                conn_df.close()

                                print(f"[DRAGONFEST] Logged {dragon_key}x{final_amount}")
                            except Exception as e:
                                print(f"[DRAGONFEST] LOG ERROR: {e}")

                        # Track dragonscale catches if active
                        if guild_id in active_dragonscales and active_dragonscales[guild_id] > current_time:
                            event_start = dragonscale_event_starts.get(guild_id, current_time)

                            try:
                                conn_ds = sqlite3.connect('dragon_bot.db', timeout=120.0, isolation_level=None)
                                c_ds = conn_ds.cursor()

                                c_ds.execute('''INSERT INTO dragonscale_event_log
                                               (guild_id, user_id, event_start, dragon_type, amount, caught_at)
                                               VALUES (?, ?, ?, ?, ?, ?)''',
                                            (guild_id, message.author.id, event_start, dragon_key, final_amount, int(time.time())))

                                c_ds.close()
                                conn_ds.close()

                                print(f"[DRAGONSCALE] Logged {dragon_key}x{final_amount}")
                            except Exception as e:
                                print(f"[DRAGONSCALE] LOG ERROR: {e}")
                        else:
                            if guild_id in active_dragonscales:
                                print(f"[DRAGONSCALE] Event ended or not active")

                        # Check Dragonpass quests
                        dragon_rarity_index = list(DRAGON_TYPES.keys()).index(dragon_key)
                        is_rare = dragon_rarity_index >= 6

                        conn_dp = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c_dp = conn_dp.cursor()
                        c_dp.execute('SELECT level FROM dragonpass WHERE guild_id = ? AND user_id = ?', (guild_id, message.author.id))
                        dp_result = c_dp.fetchone()
                        current_dp_level = dp_result[0] if dp_result else 0
                        conn_dp.close()

                        result = await asyncio.to_thread(check_dragonpass_quests, guild_id, message.author.id, 'catch_dragon', final_amount, dragon_key, catch_time)
                        _r2 = await asyncio.to_thread(check_dragonpass_quests, guild_id, message.author.id, 'earn_coins', int(coins_earned))
                        _pending_quest_notifications = []
                        if result:
                            coins, level_delta, trophies, quest_info = result
                            for _tid in trophies:
                                await award_trophy(self.bot, guild_id, message.author.id, _tid)
                            if quest_info:
                                _pending_quest_notifications.append(quest_info)
                        if _r2 and _r2[3]:
                            _pending_quest_notifications.append(_r2[3])

                        if result and result[1] > 0:
                            level_up_count = result[1]
                            new_level = current_dp_level + level_up_count

                            if new_level <= 10:
                                pack_type = 'stone' if new_level % 2 == 0 else 'wooden'
                            elif new_level <= 20:
                                pack_type = 'silver' if new_level % 2 == 0 else 'bronze'
                            else:
                                pack_type = 'diamond' if new_level % 2 == 0 else 'gold'

                            pack_data = PACK_TYPES.get(pack_type, {})

                            levelup_embed = discord.Embed(
                                title="🎉 Dragonpass Level Up!",
                                description=f"{message.author.mention} has reached **Level {new_level}** in the Dragonpass!",
                                color=0xFFD700
                            )

                            levelup_embed.add_field(
                                name="🎁 Reward Earned",
                                value=f"**{pack_data.get('name', pack_type.capitalize())} Pack**\n{pack_data.get('emoji', '📦')}",
                                inline=True
                            )

                            levelup_embed.add_field(
                                name="⭐ Progress",
                                value=f"Level {new_level}/30",
                                inline=True
                            )

                            await message.channel.send(embed=levelup_embed)

                        # Check and update Dragon Nest bounties
                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()

                        c.execute('SELECT expires_at FROM raid_bosses WHERE guild_id = ? AND expires_at > ?',
                                  (guild_id, int(time.time())))
                        raid_active = c.fetchone()

                        c.execute('SELECT active_until FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                                  (guild_id, message.author.id))
                        active_result = c.fetchone()

                        if active_result and active_result[0] > int(time.time()) and not raid_active:
                            c.execute('SELECT bounties_active, speedrun_catches, level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                      (guild_id, message.author.id))
                            nest_result = c.fetchone()

                            if nest_result and nest_result[0]:
                                import ast
                                bounties = ast.literal_eval(nest_result[0])
                                speedrun_catches = nest_result[1]
                                nest_level = nest_result[2]

                                bounties_completed = 0
                                _rarity_order = {'common': 0, 'uncommon': 1, 'rare': 2, 'epic': 3, 'legendary': 4, 'mythic': 5, 'ultra': 6}
                                dragon_rarity_level = 0
                                for _rarity, _dragons in DRAGON_RARITY_TIERS.items():
                                    if dragon_key in _dragons:
                                        dragon_rarity_level = _rarity_order.get(_rarity, 0)
                                        break

                                for bounty in bounties:
                                    if bounty['type'] == 'catch_any':
                                        bounty['progress'] = min(bounty['progress'] + final_amount, bounty['target'])
                                    elif bounty['type'] == 'catch_rarity_or_higher' and bounty.get('rarity_level') and dragon_rarity_level >= bounty['rarity_level']:
                                        bounty['progress'] = min(bounty['progress'] + final_amount, bounty['target'])

                                    if bounty['progress'] >= bounty['target']:
                                        bounties_completed += 1

                                new_speedrun = speedrun_catches + final_amount

                                c.execute('UPDATE dragon_nest SET bounties_active = ?, speedrun_catches = ? WHERE guild_id = ? AND user_id = ?',
                                          (str(bounties), new_speedrun, guild_id, message.author.id))

                                total_bounties = len(bounties)
                                if bounties_completed >= total_bounties:
                                    c.execute('UPDATE dragon_nest SET bounties_completed = bounties_completed + 1 WHERE guild_id = ? AND user_id = ?',
                                              (guild_id, message.author.id))

                                    if nest_level < 10:
                                        new_level = nest_level + 1

                                        c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ? AND user_id = ?',
                                                 (guild_id, message.author.id))
                                        total_dragons_result = c.fetchone()
                                        total_dragons = total_dragons_result[0] if total_dragons_result and total_dragons_result[0] else 0

                                        if new_level <= 3:
                                            sacrifice_percentage = 0.10
                                        elif new_level <= 6:
                                            sacrifice_percentage = 0.15
                                        else:
                                            sacrifice_percentage = 0.20

                                        dragons_to_sacrifice = max(1, int(total_dragons * sacrifice_percentage))

                                        c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                                                 (guild_id, message.author.id))
                                        user_dragons_list = c.fetchall()

                                        sacrifice_list = {}
                                        dragons_needed = dragons_to_sacrifice

                                        import random as py_random
                                        user_dragons_list_shuffled = list(user_dragons_list)
                                        py_random.shuffle(user_dragons_list_shuffled)

                                        for dragon_type, available_count in user_dragons_list_shuffled:
                                            if dragons_needed <= 0:
                                                break
                                            take_count = min(available_count, dragons_needed)
                                            sacrifice_list[dragon_type] = take_count
                                            dragons_needed -= take_count

                                        sacrifice_display = ""
                                        for dragon_type, count in sacrifice_list.items():
                                            dragon_data_s = DRAGON_TYPES[dragon_type]
                                            sacrifice_display += f"{dragon_data_s['emoji']} **{count}x {dragon_data_s['name']}**\n"

                                        c.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                                     VALUES (?, ?, ?, ?)''',
                                                  (guild_id, message.author.id, new_level, json.dumps({
                                                      'sacrifice_list': sacrifice_list,
                                                      'new_level': new_level
                                                  })))

                                        c.execute('UPDATE dragon_nest SET bounties_active = NULL, speedrun_catches = 0 WHERE guild_id = ? AND user_id = ?',
                                                  (guild_id, message.author.id))

                                        c.execute('DELETE FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                                                  (guild_id, message.author.id))

                                        conn.commit()

                                        embed = discord.Embed(
                                            title="🎉 Dragon Nest Level Complete!",
                                            description=f"You completed all bounties and reached **Level {new_level}: {LEVEL_NAMES.get(new_level, 'Unknown')}**!\n\n"
                                                        f"🐉 **Dragons to Sacrifice:**\n{sacrifice_display}\n"
                                                        f"Click **Submit Dragons** to confirm and unlock your perk reward!",
                                            color=discord.Color.green()
                                        )

                                        _guild_id = guild_id
                                        _user_id = message.author.id
                                        _sacrifice_list = sacrifice_list
                                        _new_level = new_level
                                        _bot = self.bot

                                        class _NestSacrificeView(discord.ui.View):
                                            def __init__(self):
                                                super().__init__(timeout=300)
                                                btn = discord.ui.Button(label="💾 Submit Dragons", style=discord.ButtonStyle.success)
                                                btn.callback = self.submit_dragons
                                                self.add_item(btn)

                                            async def submit_dragons(self, btn_inter: discord.Interaction):
                                                if btn_inter.user.id != _user_id:
                                                    await btn_inter.response.send_message("This is not your action!", ephemeral=True)
                                                    return
                                                await btn_inter.response.defer()
                                                conn2 = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                                c2 = conn2.cursor()
                                                for dt, cnt in _sacrifice_list.items():
                                                    c2.execute('UPDATE user_dragons SET count = count - ? WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                                               (cnt, _guild_id, _user_id, dt))
                                                c2.execute('UPDATE dragon_nest SET level = ? WHERE guild_id = ? AND user_id = ?',
                                                           (_new_level, _guild_id, _user_id))
                                                c2.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ?',
                                                           (_guild_id, _user_id))
                                                c2.execute('SELECT level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                                           (_guild_id, _user_id))
                                                current_level = c2.fetchone()[0]
                                                from utils import generate_unique_perks
                                                perk_store_level = current_level + 1 if current_level < 10 else 10
                                                new_perks = generate_unique_perks(perk_store_level, 3, 0)
                                                c2.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                                              VALUES (?, ?, ?, ?)''',
                                                           (_guild_id, _user_id, perk_store_level, json.dumps({'selected_perks': new_perks})))
                                                conn2.commit()
                                                conn2.close()
                                                if current_level == 10:
                                                    from achievements import award_trophy
                                                    await award_trophy(_bot, _guild_id, _user_id, 'nest_master')
                                                await check_and_award_achievements(_guild_id, _user_id, bot=_bot)
                                                self.stop()
                                                if current_level < 10:
                                                    await btn_inter.followup.send(
                                                        f"✨ **Level {_new_level} Unlocked!**\n🎁 A new perk is waiting! Use `/dragonnest` to claim it.",
                                                        ephemeral=False
                                                    )
                                                else:
                                                    await btn_inter.followup.send(
                                                        f"🏆 **Max Level Reached!**\nYou've reached the maximum Dragon Nest level!\n🎁 Your final perk is waiting! Use `/dragonnest` to claim it.",
                                                        ephemeral=False
                                                    )

                                        await message.channel.send(embed=embed, view=_NestSacrificeView())
                                    else:
                                        # Max level
                                        c.execute('UPDATE dragon_nest SET bounties_active = NULL, speedrun_catches = 0 WHERE guild_id = ? AND user_id = ?',
                                                  (guild_id, message.author.id))
                                        c.execute('DELETE FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                                                  (guild_id, message.author.id))
                                        conn.commit()

                                        try:
                                            await message.channel.send(f"🎉 {message.author.mention} **Dragon Nest Complete!**\nYou've completed all bounties at max level! Well done!")
                                        except:
                                            pass

                        conn.commit()
                        conn.close()

                        # Trophy checks after catch
                        _dragon_data = DRAGON_TYPES.get(spawn_data['dragon_type'], {})
                        _rarity = _dragon_data.get('rarity', '')

                        if _rarity in ('mythic', 'ultra'):
                            await award_trophy(self.bot, guild_id, message.author.id, 'mythic_hunter')

                        _conn_s = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        _c_s = _conn_s.cursor()
                        _c_s.execute('SELECT COUNT(*) FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                                     (guild_id, message.author.id))
                        _unique = _c_s.fetchone()[0]
                        _conn_s.close()
                        if _unique >= len(DRAGON_TYPES):
                            await award_trophy(self.bot, guild_id, message.author.id, 'dragon_scholar')

                        # Auto-bingo completion notification
                        if bingo_just_completed:
                            try:
                                await update_balance_and_check_trophies(self.bot, guild_id, message.author.id, 500)
                                _bq = await asyncio.to_thread(check_dragonpass_quests, guild_id, message.author.id, 'complete_bingo', 1)
                                if _bq and _bq[3]:
                                    await send_quest_notification(self.bot, guild_id, message.author.id, _bq[3])
                                bingo_embed = discord.Embed(
                                    title="🎉 BINGO!",
                                    description=f"**{message.author.mention} completed a bingo line!**\n🏆 Reward: **500** 🪙",
                                    color=discord.Color.gold()
                                )
                                await message.channel.send(content=message.author.mention, embed=bingo_embed)
                            except Exception as e:
                                logger.error(f"Bingo completion handling failed: {e}")

                    # Add packs if any
                    if pack_rewards:
                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()
                        for pack_tier in pack_rewards:
                            c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                         VALUES (?, ?, ?, 1)
                                         ON CONFLICT(guild_id, user_id, pack_type)
                                         DO UPDATE SET count = count + 1''',
                                      (guild_id, message.author.id, pack_tier))
                        conn.commit()
                        conn.close()

                    # Extend dragonscale time if applicable
                    if time_bonus > 0 and guild_id in active_dragonscales:
                        if active_dragonscales[guild_id] > int(time.time()):
                            active_dragonscales[guild_id] += time_bonus * 60

                    # Send success message
                    catch_secs = round(catch_time, 1)

                    embed = discord.Embed(
                        title=f"🎉 {message.author.display_name} caught the dragon!",
                        description=f"{final_amount}x {dragon_data['emoji']} **{dragon_data['name']} Dragon**",
                        color=discord.Color.gold()
                    )

                    # Catch time + coins as inline fields
                    embed.add_field(name="⏱️ Catch Time", value=f"{catch_secs}s", inline=True)

                    if final_amount > 0:
                        coins_value = f"{int(coins_earned)}"
                        if alpha_coin_bonus > 0:
                            coins_value += f"\n*(+{alpha_coin_bonus} from Alpha)*"
                        embed.add_field(name="🪙 Earned", value=coins_value, inline=True)
                    else:
                        embed.add_field(name="💀 Result", value="Lost all dragons!", inline=True)

                    # Bonus packs
                    if pack_rewards:
                        packs_text = ", ".join([PACK_TYPES[p]['emoji'] + " " + PACK_TYPES[p]['name'] for p in pack_rewards])
                        embed.add_field(name="📦 Bonus Packs", value=packs_text, inline=False)

                    # Dragonscale time bonus
                    if time_bonus > 0:
                        embed.add_field(name="<:dragonscale:1446278170998341693> Dragonscale", value=f"+{time_bonus} minutes", inline=True)

                    # Active perks (only if any)
                    if perks_applied:
                        embed.add_field(name="✨ Active Perks", value=" • ".join(perks_applied), inline=False)

                    # Alpha dragon influence
                    if alpha_effect_triggered:
                        if alpha_multiplier > 1:
                            embed.add_field(
                                name="🌟 Alpha Influence",
                                value=f"{alpha_owner_name}'s **{alpha_dragon_name}** blessed this catch! (x{alpha_multiplier})",
                                inline=False
                            )
                        elif dragonscale_event_minutes > 0:
                            online_count = sum(1 for m in message.guild.members if not m.bot and m.status != discord.Status.offline)
                            embed.add_field(
                                name="<:dragonscale:1446278170998341693> Dragonscale Event",
                                value=f"{alpha_owner_name}'s **{alpha_dragon_name}** triggered an event!\n+30 seconds for {online_count} online members",
                                inline=False
                            )

                    # Night vision
                    if guild_id in active_spawns and active_spawns[guild_id].get('night_vision_activator'):
                        embed.add_field(name="🌙 Night Vision", value="Higher rarity dragon found!", inline=False)
                    elif item_boost_message and "inactive" not in item_boost_message:
                        embed.add_field(name="🌙 Night Vision", value="Higher rarity dragon found!", inline=False)

                    await message.channel.send(embed=embed)

                    # Send quest notifications after catch embed
                    for _qinfo in _pending_quest_notifications:
                        await send_quest_notification(self.bot, guild_id, message.author.id, _qinfo)

                    # Instant respawn if dragonscale/dragonfest/premium is active
                    current_time = int(time.time())
                    has_active_dragonscale = guild_id in active_dragonscales and active_dragonscales[guild_id] > current_time

                    has_dragonfest = False
                    if guild_id in active_dragonfest:
                        dragonfest_data = active_dragonfest[guild_id]
                        dragonfest_end_time = dragonfest_data['end'] if isinstance(dragonfest_data, dict) else dragonfest_data
                        has_dragonfest = dragonfest_end_time > current_time

                    has_premium = guild_id in premium_users and any(end_time > current_time for end_time in premium_users[guild_id].values())

                    if has_active_dragonscale or has_dragonfest or has_premium:
                        await spawn_dragon(guild_id, message.channel, self.bot)

                        try:
                            conn_update = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c_update = conn_update.cursor()
                            c_update.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                                          (int(time.time()), guild_id))
                            conn_update.commit()
                            conn_update.close()
                        except:
                            pass

        await self.bot.process_commands(message)


async def setup(bot):
    await bot.add_cog(EventsCog(bot))
