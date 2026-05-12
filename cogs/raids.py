import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
import json
import time
import math
import logging
import ast
import traceback
import random
from datetime import datetime
from typing import Optional
from config import *
from state import *
import database
from database import is_player_softlocked, update_balance, get_db_connection
from utils import *
from achievements import check_and_award_achievements, award_trophy, send_quest_notification

logger = logging.getLogger(__name__)


async def update_raid_embed(bot, guild_id, channel_id, user_tier=None):
    """Update the main raid boss embed with current HP and participant counts for ALL tiers"""
    try:
        conn = get_db_connection(120.0)
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
    def __init__(self, bot, gid, bname, brarity, rdragon):
        super().__init__(timeout=None)
        self.bot = bot
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
        conn = get_db_connection(120.0)
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
        await update_raid_embed(self.bot, btn_interaction.guild_id, btn_interaction.channel_id, tier)

        tier_names = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}
        await btn_interaction.response.send_message(
            f"✅ You joined the **{tier_names[tier]}** tier!\n\n"
            f"Your damage potential: **{damage_potential:,}**\n"
            f"You're now locked in. Use `/raidstatus` to see the boss HP and attack!",
            ephemeral=True
        )


class RaidAttackView(discord.ui.View):
    def __init__(self, bot, gid):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = gid

    @discord.ui.button(label="Attack!", style=discord.ButtonStyle.red, emoji="⚔️")
    async def attack_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
        current_time = int(time.time())

        conn_a = get_db_connection(120.0)
        c_a = conn_a.cursor()

        # Check if user is registered in raid_damage
        c_a.execute('SELECT tier FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        tier_result = c_a.fetchone()

        # Check if this is a shared-pool raid (no tier restriction)
        c_a.execute('''SELECT easy_max_hp, hard_max_hp, normal_max_hp FROM raid_bosses
                       WHERE guild_id = ?''', (btn_interaction.guild_id,))
        raid_type_result = c_a.fetchone()

        if not raid_type_result:
            conn_a.close()
            await btn_interaction.response.send_message("❌ No active raid boss!", ephemeral=True)
            return

        easy_max_hp, hard_max_hp, normal_max_hp = raid_type_result

        # TIER-BASED RAIDS: User MUST have selected a tier
        # Check if user is registered in raid_damage
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

        # War Drum: +10% damage for this attack, then consume 1
        c_a.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id, 'war_drum'))
        drum_result = c_a.fetchone()
        war_drum_used = False
        if drum_result and drum_result[0] > 0:
            damage = int(damage * 1.10)
            c_a.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                      (btn_interaction.guild_id, btn_interaction.user.id, 'war_drum'))
            war_drum_used = True

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
            # Set HP to 0 (not negative)
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

        await check_and_award_achievements(btn_interaction.guild_id, btn_interaction.user.id, bot=self.bot)

        # Get updated boss data for embed update
        c_a.execute('SELECT easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_name, boss_rarity, reward_dragon, expires_at, message_id FROM raid_bosses WHERE guild_id = ?',
                  (btn_interaction.guild_id,))
        boss_data = c_a.fetchone()

        if boss_data:
            easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_name, boss_rarity, reward_dragon, expires_at, message_id = boss_data

            # Update original embed message if message_id is stored
            if message_id:
                try:
                    raid_channel = self.bot.get_channel(btn_interaction.channel_id)
                    if raid_channel:
                        raid_msg = await raid_channel.fetch_message(message_id)
                        if raid_msg:
                            # Rebuild the embed with updated HP
                            dragon_data = DRAGON_TYPES[reward_dragon]
                            tier_emoji = {'easy': '🟢', 'normal': '🟡', 'hard': '🔴'}[user_tier]
                            tier_color = {'easy': discord.Color.green(), 'normal': discord.Color.blue(), 'hard': discord.Color.red()}[user_tier]
                            updated_embed = discord.Embed(
                                title=f"⚔️ {user_tier.upper()} TIER RAID",
                                description=f"Boss: {boss_name}\nRarity: {boss_rarity.title()}\nYour Tier: {tier_emoji} {user_tier.upper()}",
                                color=tier_color
                            )

                            # Show HP for current tier
                            if user_tier == 'easy':
                                current_hp, max_hp = easy_hp, easy_max_hp
                            elif user_tier == 'normal':
                                current_hp, max_hp = normal_hp, normal_max_hp
                            else:  # hard
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

                            # Get participant count
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

                            # Your stats
                            max_damage_per_attack = {'easy': '10,000', 'normal': '25,000', 'hard': '50,000'}[user_tier]
                            updated_embed.add_field(
                                name="Your Stats",
                                value=f"💥 Damage: {user_total_damage:,}\n⚔️ Max per Attack: {max_damage_per_attack}\n🔄 Attacks: {total_damage_result[0] if total_damage_result else 0}",
                                inline=False
                            )

                            # Leaderboard
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

        drum_note = " 🥁 *War Drum!*" if war_drum_used else ""

        # If tier is defeated, show victory message instead of normal attack message
        if tier_defeated:
            await btn_interaction.response.send_message(
                f"⚔️ {btn_interaction.user.mention} dealt **{damage:,}** damage!{drum_note} ({tier_names[user_tier]})\n"
                f"💥 Total Damage: **{user_total_damage:,}**\n\n"
                f"🎉 **{tier_names[user_tier]} TIER DEFEATED!**",
                ephemeral=False
            )
        else:
            await btn_interaction.response.send_message(
                f"⚔️ {btn_interaction.user.mention} dealt **{damage:,}** damage!{drum_note} ({tier_names[user_tier]})\n"
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
        await update_raid_embed(self.bot, btn_interaction.guild_id, btn_interaction.channel_id, user_tier)

        # Update the /raidstatus message if this is called from there
        if btn_interaction.message:
            try:
                c_a.execute('SELECT tier FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                          (btn_interaction.guild_id, btn_interaction.user.id))
                tier_result = c_a.fetchone()
                if tier_result:
                    user_tier_check = tier_result[0]

                    # Fetch fresh data for the raidstatus message
                    c_a.execute('''SELECT easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp,
                                   boss_name, boss_rarity, reward_dragon, expires_at, easy_participants, normal_participants, hard_participants
                                   FROM raid_bosses WHERE guild_id = ?''', (btn_interaction.guild_id,))
                    fresh_boss_data = c_a.fetchone()

                    if fresh_boss_data:
                        easy_hp_f, easy_max_hp_f, normal_hp_f, normal_max_hp_f, hard_hp_f, hard_max_hp_f, boss_name_f, boss_rarity_f, reward_dragon_f, expires_at_f, easy_part_f, normal_part_f, hard_part_f = fresh_boss_data

                        # Get user's damage and attacks
                        c_a.execute('SELECT damage_dealt, attacks_made FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                                  (btn_interaction.guild_id, btn_interaction.user.id))
                        user_stats = c_a.fetchone()
                        user_damage_f, user_attacks_f = user_stats if user_stats else (0, 0)

                        # Get tier HP and participants
                        tier_hp_map = {
                            'easy': (easy_hp_f, easy_max_hp_f, easy_part_f),
                            'normal': (normal_hp_f, normal_max_hp_f, normal_part_f),
                            'hard': (hard_hp_f, hard_max_hp_f, hard_part_f)
                        }
                        tier_hp_f, tier_max_hp_f, tier_part_f = tier_hp_map[user_tier_check]
                        tier_part = eval(tier_part_f) if tier_part_f else []

                        # Rebuild raidstatus embed with new data
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

                        # Get leaderboard for user's tier
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

                # Delete ONLY the defeated tier from the raid
                defeated_embed.add_field(
                    name="",
                    value="",
                    inline=False
                )

                # Delete only this defeated tier's damage records
                tier_name = list(defeated_tiers)[0]  # Get the defeated tier name
                c_a.execute('DELETE FROM raid_damage WHERE guild_id = ? AND tier = ?',
                           (btn_interaction.guild_id, tier_name))

                # Check if ANY raid tiers are still active (have damage records)
                remaining_tiers = c_a.execute('SELECT DISTINCT tier FROM raid_damage WHERE guild_id = ?',
                                             (btn_interaction.guild_id,)).fetchall()

                # Check if ALL tiers are now defeated (regardless of who played them)
                all_tiers_hp = c_a.execute('SELECT easy_hp, normal_hp, hard_hp FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1',
                                          (btn_interaction.guild_id,)).fetchone()

                if all_tiers_hp and all(hp <= 0 for hp in all_tiers_hp):
                    # ALL TIERS ARE DEFEATED - Delete entire raid
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
                    # Check if ANY raid tiers are still active (have damage records)
                    remaining_tiers = c_a.execute('SELECT DISTINCT tier FROM raid_damage WHERE guild_id = ?',
                                                 (btn_interaction.guild_id,)).fetchall()

                    # If NO tiers left, check if all PLAYED tiers were defeated
                    if not remaining_tiers:
                        # Get raid info to check which tiers had participants
                        raid_info = c_a.execute('SELECT easy_participants, normal_participants, hard_participants FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1',
                                               (btn_interaction.guild_id,)).fetchone()

                        if raid_info:
                            easy_part_str, normal_part_str, hard_part_str = raid_info
                            easy_had_players = bool(eval(easy_part_str)) if easy_part_str else False
                            normal_had_players = bool(eval(normal_part_str)) if normal_part_str else False
                            hard_had_players = bool(eval(hard_part_str)) if hard_part_str else False

                            # Get current HP to see which tiers were actually defeated
                            boss_hp = c_a.execute('SELECT easy_hp, normal_hp, hard_hp FROM raid_bosses WHERE guild_id = ? ORDER BY expires_at DESC LIMIT 1',
                                                 (btn_interaction.guild_id,)).fetchone()

                            if boss_hp:
                                easy_defeated = boss_hp[0] <= 0 if easy_had_players else True
                                normal_defeated = boss_hp[1] <= 0 if normal_had_players else True
                                hard_defeated = boss_hp[2] <= 0 if hard_had_players else True

                                # Dragons spawn only if all PLAYED tiers are defeated
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


class RaidBossStatusView(discord.ui.View):
    def __init__(self, bot, gid, bname, bmax_hp, brarity, rdragon):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = gid
        self.boss_name = bname
        self.boss_max_hp = bmax_hp
        self.boss_rarity = brarity
        self.reward_dragon = rdragon

    @discord.ui.button(label="Attack!", style=discord.ButtonStyle.red, emoji="⚔️")
    async def attack_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
        current_time = int(time.time())

        conn_a = get_db_connection(120.0)
        c_a = conn_a.cursor()

        # Check if this is a shared-pool raid
        c_a.execute('''SELECT easy_max_hp, hard_max_hp, normal_max_hp FROM raid_bosses
                       WHERE guild_id = ?''', (btn_interaction.guild_id,))
        raid_type_result = c_a.fetchone()

        if not raid_type_result:
            conn_a.close()
            await btn_interaction.response.send_message("❌ No active raid boss!", ephemeral=True)
            return

        easy_max_hp, hard_max_hp, normal_max_hp = raid_type_result
        is_shared_pool = (easy_max_hp == 0 and hard_max_hp == 0 and normal_max_hp > 0)

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
                    ephemeral=False
                )
                return

        c_a.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        user_dragons = c_a.fetchall()

        damage = 0
        for dragon_type, count in user_dragons:
            # Skip invalid dragon types and remove them from database
            if dragon_type not in DRAGON_TYPES:
                c_a.execute('DELETE FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                           (btn_interaction.guild_id, btn_interaction.user.id, dragon_type))
                continue
            dragon_value = DRAGON_TYPES[dragon_type]['value']
            damage += int(dragon_value) * count

        if damage <= 0:
            damage = 1

        # Apply Precision Stone passive bonus (+15% raid crit damage)
        precision_bonus = get_passive_bonus(btn_interaction.guild_id, btn_interaction.user.id, 'raid_crit')
        if precision_bonus > 0:
            damage = int(damage * (1 + precision_bonus))

        # Update HP based on raid type (shared-pool uses normal_hp, tier-based uses tier-specific columns)
        if is_shared_pool:
            c_a.execute('UPDATE raid_bosses SET normal_hp = normal_hp - ? WHERE guild_id = ?',
                      (damage, btn_interaction.guild_id))
        else:
            # For tier-based raids, find which tier is active and update it
            c_a.execute('''SELECT easy_hp, normal_hp, hard_hp FROM raid_bosses WHERE guild_id = ?''',
                       (btn_interaction.guild_id,))
            hp_result = c_a.fetchone()
            if hp_result:
                easy_hp, normal_hp, hard_hp = hp_result
                if easy_hp > 0:
                    c_a.execute('UPDATE raid_bosses SET easy_hp = easy_hp - ? WHERE guild_id = ?',
                              (damage, btn_interaction.guild_id))
                elif normal_hp > 0:
                    c_a.execute('UPDATE raid_bosses SET normal_hp = normal_hp - ? WHERE guild_id = ?',
                              (damage, btn_interaction.guild_id))
                elif hard_hp > 0:
                    c_a.execute('UPDATE raid_bosses SET hard_hp = hard_hp - ? WHERE guild_id = ?',
                              (damage, btn_interaction.guild_id))

        # Update participants list if needed (for shared-pool raids)
        if is_shared_pool:
            c_a.execute('SELECT normal_participants FROM raid_bosses WHERE guild_id = ?', (btn_interaction.guild_id,))
            part_result = c_a.fetchone()
            if part_result:
                participants_list = eval(part_result[0]) if part_result[0] else []
                if btn_interaction.user.id not in participants_list:
                    participants_list.append(btn_interaction.user.id)
                    c_a.execute('UPDATE raid_bosses SET normal_participants = ? WHERE guild_id = ?',
                              (str(participants_list), btn_interaction.guild_id))

        c_a.execute('INSERT INTO raid_damage (guild_id, user_id, tier, damage_dealt, attacks_made, last_attack_time) VALUES (?, ?, ?, ?, 1, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET damage_dealt = damage_dealt + ?, attacks_made = attacks_made + 1, last_attack_time = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id, 'normal', damage, current_time, damage, current_time))

        c_a.execute('SELECT damage_dealt FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                  (btn_interaction.guild_id, btn_interaction.user.id))
        total_damage_result = c_a.fetchone()
        user_total_damage = total_damage_result[0] if total_damage_result else damage

        conn_a.commit()

        await check_and_award_achievements(btn_interaction.guild_id, btn_interaction.user.id, bot=self.bot)

        _qr = await asyncio.to_thread(check_dragonpass_quests, btn_interaction.guild_id, btn_interaction.user.id, 'attack_raidboss', 1)
        if _qr and _qr[3]:
            await send_quest_notification(btn_interaction.client, btn_interaction.guild_id, btn_interaction.user.id, _qr[3])

        await btn_interaction.response.send_message(
            f"⚔️ {btn_interaction.user.mention} dealt **{damage:,}** damage!\n"
            f"💥 Total Damage: **{user_total_damage:,}**\n"
            f"⏰ Next attack in: **10 minutes**",
            ephemeral=False
        )

        # Get updated boss HP based on raid type
        if is_shared_pool:
            c_a.execute('SELECT normal_hp, normal_max_hp, boss_rarity, expires_at, reward_dragon, normal_participants FROM raid_bosses WHERE guild_id = ?', (btn_interaction.guild_id,))
        else:
            c_a.execute('SELECT easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_rarity, expires_at, reward_dragon, easy_participants, normal_participants, hard_participants FROM raid_bosses WHERE guild_id = ?', (btn_interaction.guild_id,))

        boss_update = c_a.fetchone()

        if not boss_update:
            conn_a.close()
            return

        if is_shared_pool:
            new_hp, max_hp, rarity, expires_at, reward_dragon, participants_str = boss_update
            participants_list = eval(participants_str) if participants_str else []
        else:
            easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, rarity, expires_at, reward_dragon, easy_part_str, normal_part_str, hard_part_str = boss_update
            # Find which tier is active
            if easy_max_hp > 0:
                new_hp, max_hp = easy_hp, easy_max_hp
                participants_str = easy_part_str
            elif normal_max_hp > 0:
                new_hp, max_hp = normal_hp, normal_max_hp
                participants_str = normal_part_str
            else:
                new_hp, max_hp = hard_hp, hard_max_hp
                participants_str = hard_part_str
            participants_list = eval(participants_str) if participants_str else []

        if new_hp <= 0:
            await award_trophy(btn_interaction.client, btn_interaction.guild_id, btn_interaction.user.id, 'raid_destroyer')
            reward_data = DRAGON_TYPES[reward_dragon]
            c_a.execute('SELECT user_id, damage_dealt FROM raid_damage WHERE guild_id = ? ORDER BY damage_dealt DESC LIMIT 10', (btn_interaction.guild_id,))
            top_damagers = c_a.fetchall()

            # Calculate coin rewards based on boss rarity
            coin_multipliers = {
                'epic': 1.0,
                'legendary': 1.5,
                'mythic': 2.5,
                'ultra': 5.0
            }
            base_coin_rewards = [1000, 750, 500, 400, 300, 250, 200, 150, 100, 50]
            multiplier = coin_multipliers.get(rarity, 1.0)
            adjusted_rewards = [int(coins * multiplier) for coins in base_coin_rewards]

            defeated_embed = discord.Embed(
                title=f"💀 {self.boss_name} DEFEATED!",
                description=f"The raid boss has been slain!\n\n🎁 **Rewards distributed to top 10 damagers:**",
                color=discord.Color.gold()
            )

            for idx, (uid, dmg) in enumerate(top_damagers, 1):
                member = btn_interaction.guild.get_member(uid)
                if member:
                    await add_dragons(btn_interaction.guild_id, uid, reward_dragon, 1)
                    bonus_coins = adjusted_rewards[idx-1]
                    await asyncio.to_thread(update_balance, btn_interaction.guild_id, uid, bonus_coins)

                    # 5% chance for Lucky Charm
                    lucky_charm_chance = random.randint(1, 100)
                    if lucky_charm_chance <= 5:
                        c_a.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                       VALUES (?, ?, ?, 1)
                                       ON CONFLICT(guild_id, user_id, item_type)
                                       DO UPDATE SET count = count + 1''',
                                    (btn_interaction.guild_id, uid, 'luckycharm'))

                    # 2% chance for Dragonscale
                    dragonscale_chance = random.randint(1, 100)
                    if dragonscale_chance <= 2:
                        c_a.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                       VALUES (?, ?, ?, 1)
                                       ON CONFLICT(guild_id, user_id, item_type)
                                       DO UPDATE SET count = count + 1''',
                                    (btn_interaction.guild_id, uid, 'dragonscale'))

                    medals = ['🥇', '🥈', '🥉']
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"

                    # Build reward text with drops
                    reward_text = f"💥 {dmg:,} damage\n{reward_data['emoji']} +1 {reward_data['name']}\n💰 +{bonus_coins}🪙"

                    if lucky_charm_chance <= 5:
                        reward_text += "\n🍀 +1 Lucky Charm (5%)"
                    if dragonscale_chance <= 2:
                        reward_text += "\n✨ +1 Dragonscale (2%)"

                    defeated_embed.add_field(
                        name=f"{medal} {member.display_name}",
                        value=reward_text,
                        inline=True
                    )

            # Add spawn notification
            defeated_embed.add_field(
                name="",
                value="",
                inline=False
            )
            defeated_embed.add_field(
                name="🐉 Dragons Are Spawning Again!",
                value="The raid is over! Wild dragons will now spawn normally. Get ready to catch them!",
                inline=False
            )

            c_a.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (btn_interaction.guild_id,))
            c_a.execute('DELETE FROM raid_damage WHERE guild_id = ?', (btn_interaction.guild_id,))
            del raid_boss_active[btn_interaction.guild_id]
            conn_a.commit()
            conn_a.close()

            # Send new defeated message
            try:
                defeated_message = await btn_interaction.channel.send(embed=defeated_embed)
                rewards_url = defeated_message.jump_url

                # Edit main raid boss embed to show defeated status with link
                defeated_main_embed = discord.Embed(
                    title=f"⚔️ Raid Boss: {self.boss_name}",
                    description=f"**Status:** ✅ **DEFEATED!**\n\n"
                                f"🎁 **Reward:** {reward_data['emoji']} {reward_data['name']} Dragon\n"
                                f"👥 **Total Participants:** {len(participants_list)}\n\n"
                                f"📊 [**View Rewards & Leaderboard**]({rewards_url})",
                    color=discord.Color.gold()
                )
                defeated_main_embed.set_footer(text="Raid boss has been defeated!")
                await btn_interaction.message.edit(embed=defeated_main_embed, view=None)
            except:
                pass
            return

        conn_a.close()

        hp_percentage = (new_hp / max_hp) * 100
        hp_bar_length = 20
        filled = int((hp_percentage / 100) * hp_bar_length)
        hp_bar = "█" * filled + "░" * (hp_bar_length - filled)

        time_left = expires_at - current_time

        reward_data = DRAGON_TYPES[reward_dragon]

        updated_embed = discord.Embed(
            title=f"⚔️ Raid Boss: {self.boss_name}",
            description=f"**Rarity:** {rarity.title()}\n**HP:** {new_hp:,} / {max_hp:,}\n{hp_bar} {hp_percentage:.1f}%\n\n🎁 **Reward:** {reward_data['emoji']} {reward_data['name']} Dragon\n👥 **Participants:** {len(participants_list)}\n⏰ **Time Left:** {format_time_remaining(time_left)}",
            color=discord.Color.red()
        )

        try:
            await btn_interaction.message.edit(embed=updated_embed, view=self)
        except:
            pass


async def spawn_raid_boss_ritual(bot, guild_id: int, channel: discord.TextChannel):
    """Spawn raid boss after ritual completion - shared pool for all players, no tier restrictions"""
    current_time = int(time.time())
    ritual = ritual_active.get(guild_id)
    if not ritual:
        logger.error(f"No ritual found for guild {guild_id}")
        return

    # Get the configured spawn channel for this guild
    spawn_channel_id = get_spawn_channel(guild_id)
    if not spawn_channel_id:
        # No spawn channel set - don't spawn the raid boss
        logger.warning(f"Raid boss not spawned for guild {guild_id}: No spawn channel configured")
        # Send error message in the current channel
        try:
            await channel.send("❌ **Raid Boss Spawn Failed!** No spawn channel has been configured with `/setchannel`. "
                             "Please use `/setchannel` in your desired raid channel first.")
        except Exception as e:
            logger.error(f"Failed to send spawn channel warning: {e}")
        return

    # Get the spawn channel from guild
    guild = channel.guild
    spawn_channel = guild.get_channel(spawn_channel_id)
    if not spawn_channel:
        logger.warning(f"Raid boss not spawned for guild {guild_id}: Spawn channel {spawn_channel_id} not found")
        try:
            await channel.send("❌ **Raid Boss Spawn Failed!** The configured spawn channel no longer exists. "
                             "Please use `/setchannel` to set a new one.")
        except Exception as e:
            logger.error(f"Failed to send channel not found warning: {e}")
        return

    # Use the configured spawn channel instead of the current channel
    channel = spawn_channel

    # Set up raid_boss_active FIRST before processing
    raid_boss_active[guild_id] = {
        'active': True,
        'spawn_time': current_time,
        'despawn_time': current_time + (4 * 60 * 60),  # 4 hours
        'manual_spawn': True
    }

    boss_rarity = ritual['boss_rarity']
    ritual_difficulty = ritual['difficulty']  # easy, normal, or hard (affects HP scaling)

    # Get eligible dragons for this rarity
    eligible_dragons = DRAGON_RARITY_TIERS.get(boss_rarity, [])
    if not eligible_dragons:
        logger.error(f"No eligible dragons for rarity {boss_rarity}")
        return

    reward_dragon = random.choice(eligible_dragons)

    # Verify reward dragon exists in DRAGON_TYPES
    if reward_dragon not in DRAGON_TYPES:
        logger.error(f"Reward dragon '{reward_dragon}' not found in DRAGON_TYPES")
        return

    # Boss stats
    boss_names = {
        'epic': ['Ancient Wyrm', 'Iron Goliath', 'Storm Titan', 'Frost Giant'],
        'legendary': ['Emerald Overlord', 'Diamond Behemoth', 'Obsidian Terror'],
        'mythic': ['Golden Sovereign', 'Platinum Destroyer', 'Crystal Devourer'],
        'ultra': ['Celestial Avatar', 'Void Incarnate', 'Cosmic Leviathan', 'Primordial Nightmare']
    }

    boss_name = random.choice(boss_names.get(boss_rarity, ['Mystery Boss']))

    # Calculate HP based on ritual dragon count and difficulty
    # All players share the same HP pool, no tier restrictions
    # HP ranges match the auto-spawn raid boss system (admin.py hp_limits)
    ritual_dragon_count = ritual['donated']

    if ritual_difficulty == 'easy':       # epic rarity
        boss_hp = ritual_dragon_count * 20000
        boss_hp = max(20000, min(boss_hp, 100000))
    elif ritual_difficulty == 'normal':   # legendary rarity
        boss_hp = ritual_dragon_count * 40000
        boss_hp = max(40000, min(boss_hp, 200000))
    else:                                 # hard → mythic rarity
        boss_hp = ritual_dragon_count * 75000
        boss_hp = max(150000, min(boss_hp, 300000))

    reward_data = DRAGON_TYPES[reward_dragon]

    # Store in DB - SHARED POOL (all in normal_hp, easy/hard empty)
    conn = get_db_connection(120.0)
    c = conn.cursor()

    c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (guild_id,))
    c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))

    participants_list = list(ritual['donors'].keys())

    # Insert with shared pool: all players fight same boss (stored in normal_hp)
    # easy_hp and hard_hp left at 0 to indicate this is a shared-pool raid
    c.execute('''INSERT INTO raid_bosses (guild_id, boss_name, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp,
                                         boss_rarity, reward_dragon, started_at, expires_at, easy_participants, normal_participants, hard_participants)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (guild_id, boss_name, 0, 0, boss_hp, boss_hp, 0, 0,
               boss_rarity, reward_dragon, current_time, current_time + (4 * 60 * 60), '[]', str(participants_list), '[]'))

    # Do NOT add donors to raid_damage - anyone can join and fight without tier restrictions

    conn.commit()
    conn.close()

    # Send raid boss spawn message
    difficulty_names = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}
    difficulty_emoji = {'easy': '🟢', 'normal': '🟡', 'hard': '🔴'}

    embed = discord.Embed(
        title=f"⚔️ {difficulty_emoji[ritual_difficulty]} COMMUNITY RAID BOSS: {boss_name}",
        description=f"**Rarity:** {boss_rarity.upper()}\n**Difficulty Scale:** {difficulty_names[ritual_difficulty]}\n\n"
                   f"🔓 **ALL PLAYERS CAN FIGHT** - No tier restrictions! Everyone attacks the same shared boss pool.",
        color=discord.Color.red()
    )

    embed.add_field(
        name="📊 Boss HP",
        value=f"{boss_hp:,} / {boss_hp:,}\n{'█' * 20} 100.0%",
        inline=False
    )

    embed.add_field(
        name="🎁 Reward",
        value=f"{reward_data['emoji']} **{reward_data['name']} Dragon**\n✨ 1x per victory + bonus coins",
        inline=False
    )

    embed.add_field(
        name="👥 Participants",
        value=f"{len(participants_list)} ritual donors",
        inline=True
    )

    embed.add_field(
        name="⏰ Time Left",
        value="4 hours",
        inline=True
    )

    embed.set_footer(text="Use /raidstatus to join and attack!")

    # Send message and store ID
    view = RaidBossStatusView(bot, guild_id, boss_name, boss_hp, boss_rarity, reward_dragon)
    raid_msg = await channel.send(embed=embed, view=view)

    # Update message_id in DB
    conn = get_db_connection(120.0)
    c = conn.cursor()
    c.execute('UPDATE raid_bosses SET message_id = ? WHERE guild_id = ?', (raid_msg.id, guild_id))
    conn.commit()
    conn.close()

    # Store message ID for runtime access
    raid_boss_active[guild_id]['message_id'] = raid_msg.id
    logger.info(f"Ritual raid boss spawned for guild {guild_id}: {boss_name} ({boss_rarity}) - shared pool, no tier restrictions")


class RaidsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ritual", description="Start a community ritual to summon a raid boss")
    @app_commands.describe(difficulty="Choose the boss difficulty: easy, normal, or hard")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Easy Boss", value="easy"),
        app_commands.Choice(name="Normal Boss", value="normal"),
        app_commands.Choice(name="Hard Boss", value="hard")
    ])
    async def ritual(self, interaction: discord.Interaction, difficulty: str):
        """Start a community ritual - users donate dragons to summon a raid boss"""
        await interaction.response.defer(ephemeral=False)

        guild_id = interaction.guild_id

        # Map difficulty to accepted donation rarities and spawned boss rarity
        difficulty_to_rarities = {
            'easy':   ['common', 'uncommon', 'rare'],
            'normal': ['epic', 'legendary', 'mythic'],
            'hard':   ['ultra'],
        }
        difficulty_to_boss_rarity = {
            'easy':   'rare',
            'normal': 'legendary',
            'hard':   'ultra',
        }
        rarities = difficulty_to_rarities.get(difficulty, ['common'])
        boss_rarity = difficulty_to_boss_rarity.get(difficulty, 'rare')

        # Check if ritual already active
        if guild_id in ritual_active:
            ritual = ritual_active[guild_id]
            progress = ritual['donated']
            required = ritual['required']
            progress_pct = int((progress / required) * 100)
            progress_bar = "█" * int(progress_pct / 10) + "░" * (10 - int(progress_pct / 10))

            existing_embed = discord.Embed(
                title=f"🔮 Community Ritual: {difficulty.upper()} Boss (ACTIVE)",
                description=f"A ritual is already in progress! Complete it first before starting a new one.\n\n"
                            f"📊 Progress: **{progress} / {required}** Dragons\n"
                            f"{progress_bar} {progress_pct}%",
                color=discord.Color.orange()
            )
            existing_embed.add_field(
                name="👥 Current Contributors",
                value=f"**{len(ritual['donors'])}** players have donated",
                inline=False
            )

            await interaction.followup.send(embed=existing_embed, ephemeral=False)
            return

        # Check if raid boss already active
        if guild_id in raid_boss_active and raid_boss_active[guild_id].get('active'):
            await interaction.followup.send("❌ A raid boss is already active! Defeat it first.", ephemeral=False)
            return

        # Dragons required per difficulty (scales with server size)
        conn = get_db_connection(120.0)
        c = conn.cursor()

        # Count distinct active players who own at least 1 dragon of any accepted rarity
        accepted_dragon_types = []
        for r in rarities:
            accepted_dragon_types.extend(DRAGON_RARITY_TIERS.get(r, []))
        placeholders = ','.join('?' * len(accepted_dragon_types))
        c.execute(f'''SELECT COUNT(DISTINCT user_id) FROM user_dragons
                      WHERE guild_id = ? AND dragon_type IN ({placeholders}) AND count > 0''',
                  (guild_id, *accepted_dragon_types))
        active = c.fetchone()[0] or 1

        conn.close()

        # Ritual requirements: Scale by active players
        # Small servers (1-10 active): 1 dragon
        # Medium servers (11-30): 2 dragons
        # Large servers (31-60): 3 dragons
        # Very large (60+): 4 dragons
        if active <= 10:
            required = 1
        elif active <= 30:
            required = 2
        elif active <= 60:
            required = 3
        else:
            required = 4

        # Initialize ritual
        ritual_active[guild_id] = {
            'difficulty': difficulty,
            'rarities': rarities,
            'boss_rarity': boss_rarity,
            'donated': 0,
            'required': required,
            'donors': {},
            'message_id': None
        }

        rarity_display = '/'.join(r.capitalize() for r in rarities)

        # Create ritual progress embed
        ritual_embed = discord.Embed(
            title=f"🔮 Community Ritual: {difficulty.upper()} Boss",
            description=f"Unite and donate dragons to summon a powerful raid boss!\n\n"
                        f"📊 Progress: **0 / {required}** Dragons",
            color=0x9B59B6
        )
        ritual_embed.add_field(
            name="🐉 How to Participate",
            value=f"Click **Donate Dragons** and contribute any **{rarity_display}** dragon!",
            inline=False
        )
        ritual_embed.add_field(
            name="💪 What Happens",
            value="Once all dragons are collected, the raid boss will spawn immediately!",
            inline=False
        )
        ritual_embed.set_footer(text="Every dragon counts! Work together to summon the boss.")

        bot_ref = self.bot

        # Create donate button view
        class RitualDonateView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label="Donate Dragons", style=discord.ButtonStyle.primary, emoji="🐉")
            async def donate_button(self, inter: discord.Interaction, button: discord.ui.Button):
                await inter.response.defer(ephemeral=True)

                gid = inter.guild_id
                if gid not in ritual_active:
                    await inter.followup.send("❌ No active ritual!", ephemeral=True)
                    return

                ritual = ritual_active[gid]
                ritual_rarities = ritual['rarities']

                # Get user's dragons of any accepted rarity
                conn = get_db_connection(120.0)
                c = conn.cursor()

                c.execute('''SELECT dragon_type, count FROM user_dragons
                             WHERE guild_id = ? AND user_id = ? AND count > 0
                             ORDER BY dragon_type''',
                          (gid, inter.user.id))
                user_dragons = c.fetchall()
                conn.close()

                # Filter by accepted rarities
                ritual_dragons = []
                for dragon_type, count in user_dragons:
                    dragon_rarity = 'common'
                    for r, dragons in DRAGON_RARITY_TIERS.items():
                        if dragon_type in dragons:
                            dragon_rarity = r
                            break

                    if dragon_rarity in ritual_rarities:
                        ritual_dragons.append((dragon_type, count))

                if not ritual_dragons:
                    rarity_str = '/'.join(ritual_rarities)
                    await inter.followup.send(f"❌ You don't have any {rarity_str} dragons!", ephemeral=True)
                    return

                # Selection modal
                class DonateSelectView(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=60)
                        options = []
                        for dragon_type, count in ritual_dragons:
                            dragon_data = DRAGON_TYPES[dragon_type]
                            options.append(discord.SelectOption(
                                label=f"{dragon_data['name']} ({count}x)",
                                emoji=dragon_data['emoji'],
                                value=dragon_type
                            ))

                        select = discord.ui.Select(
                            placeholder="Select dragon type to donate...",
                            options=options[:25]
                        )
                        select.callback = self.select_dragon
                        self.add_item(select)

                    async def select_dragon(self, inter2: discord.Interaction):
                        await inter2.response.defer()
                        selected_values = inter2.data.get("values", [])
                        dragon_type = selected_values[0] if selected_values else None
                        if not dragon_type:
                            await inter2.followup.send("❌ Please select a dragon type!", ephemeral=True)
                            return

                        # Amount modal
                        class AmountView(discord.ui.View):
                            def __init__(self):
                                super().__init__(timeout=60)

                            @discord.ui.button(label="1", style=discord.ButtonStyle.grey)
                            async def amount_1(self, inter3: discord.Interaction, btn: discord.ui.Button):
                                await self.process_donation(inter3, dragon_type, 1)

                            @discord.ui.button(label="3", style=discord.ButtonStyle.grey)
                            async def amount_3(self, inter3: discord.Interaction, btn: discord.ui.Button):
                                await self.process_donation(inter3, dragon_type, 3)

                            @discord.ui.button(label="5", style=discord.ButtonStyle.grey)
                            async def amount_5(self, inter3: discord.Interaction, btn: discord.ui.Button):
                                await self.process_donation(inter3, dragon_type, 5)

                            @discord.ui.button(label="10", style=discord.ButtonStyle.grey)
                            async def amount_10(self, inter3: discord.Interaction, btn: discord.ui.Button):
                                await self.process_donation(inter3, dragon_type, 10)

                            async def process_donation(self, inter3: discord.Interaction, dt: str, amount: int):
                                await inter3.response.defer(ephemeral=True)

                                if gid not in ritual_active:
                                    await inter3.followup.send("❌ Ritual cancelled!", ephemeral=True)
                                    return

                                # Check user has dragons
                                conn = get_db_connection(120.0)
                                c = conn.cursor()
                                c.execute('SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                          (gid, inter3.user.id, dt))
                                result = c.fetchone()

                                if not result or result[0] < amount:
                                    conn.close()
                                    await inter3.followup.send(f"❌ You don't have {amount} of that dragon!", ephemeral=True)
                                    return

                                # DON'T remove dragons yet! Only store the donation promise
                                # Dragons will be removed when ritual is complete
                                conn.close()

                                # Add to ritual (track donation WITHOUT removing dragons yet)
                                ritual['donated'] += amount
                                if inter3.user.id not in ritual['donors']:
                                    ritual['donors'][inter3.user.id] = {'amount': 0, 'dragons': []}
                                ritual['donors'][inter3.user.id]['amount'] += amount
                                ritual['donors'][inter3.user.id]['dragons'].append((dt, amount))

                                dragon_data = DRAGON_TYPES[dt]

                                # Check if ritual complete
                                if ritual['donated'] >= ritual['required']:
                                    # Ritual complete! Remove all dragons NOW and spawn boss
                                    conn = get_db_connection(120.0)
                                    c = conn.cursor()

                                    # Remove all donated dragons from all users
                                    for user_id, donor_info in ritual['donors'].items():
                                        for dragon_type, donation_amount in donor_info['dragons']:
                                            c.execute('UPDATE user_dragons SET count = count - ? WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                                      (donation_amount, gid, user_id, dragon_type))

                                    conn.commit()
                                    conn.close()

                                    await inter3.followup.send(
                                        f"✅ {inter3.user.mention} donated **{amount}x {dragon_data['name']}**!\n\n"
                                        f"🔮 **RITUAL COMPLETE!** All dragons collected! Summoning raid boss...",
                                        ephemeral=False
                                    )

                                    # Spawn raid boss BEFORE removing ritual (spawn_raid_boss_ritual needs the ritual data!)
                                    try:
                                        await spawn_raid_boss_ritual(bot_ref, inter3.guild_id, inter3.channel)
                                    except Exception as e:
                                        logger.error(f"Failed to spawn raid boss: {e}")
                                        await inter3.followup.send(f"❌ Error spawning raid boss: {e}", ephemeral=False)

                                    # NOW remove ritual from active
                                    del ritual_active[gid]

                                    # Also clean up raid_boss_active for this guild if needed
                                    # (spawn_raid_boss_ritual will have set it up already)
                                else:
                                    # Update ritual embed
                                    progress = ritual['donated']
                                    required = ritual['required']
                                    progress_pct = int((progress / required) * 100)
                                    progress_bar = "█" * int(progress_pct / 10) + "░" * (10 - int(progress_pct / 10))

                                    updated_embed = discord.Embed(
                                        title=f"🔮 Community Ritual: {ritual['difficulty'].upper()} Boss",
                                        description=f"Unite and donate dragons to summon a powerful raid boss!\n\n"
                                                    f"📊 Progress: **{progress} / {required}** Dragons\n"
                                                    f"{progress_bar} {progress_pct}%",
                                        color=0x9B59B6
                                    )
                                    updated_embed.add_field(
                                        name="🐉 How to Participate",
                                        value="Use the **Donate Dragons** button below!",
                                        inline=False
                                    )
                                    updated_embed.add_field(
                                        name="💪 Contributors",
                                        value=f"**{len(ritual['donors'])}** players donated so far",
                                        inline=False
                                    )
                                    updated_embed.set_footer(text="Dragons will be removed when ritual is complete!")

                                    if ritual['message_id']:
                                        try:
                                            msg = await inter3.channel.fetch_message(ritual['message_id'])
                                            await msg.edit(embed=updated_embed)
                                        except:
                                            pass

                                    await inter3.followup.send(
                                        f"✅ {inter3.user.mention} donated **{amount}x {dragon_data['name']}** (reserved)!\n"
                                        f"Progress: **{progress} / {required}** ({progress_pct}%)",
                                        ephemeral=False
                                    )

                        await inter2.followup.send("How many dragons do you want to donate?", view=AmountView(), ephemeral=True)

                await inter.followup.send("Select dragon type:", view=DonateSelectView(), ephemeral=True)

            @discord.ui.button(label="Cancel Ritual", style=discord.ButtonStyle.danger, emoji="❌")
            async def cancel_button(self, inter: discord.Interaction, button: discord.ui.Button):
                await inter.response.defer(ephemeral=True)

                gid = inter.guild_id
                if gid not in ritual_active:
                    await inter.followup.send("❌ No active ritual!", ephemeral=True)
                    return

                ritual = ritual_active[gid]

                # Return dragons to all donors
                if ritual['donors']:
                    conn = get_db_connection(120.0)
                    c = conn.cursor()

                    returned_users = []
                    for user_id, donor_info in ritual['donors'].items():
                        for dragon_type, donation_amount in donor_info['dragons']:
                            c.execute('UPDATE user_dragons SET count = count + ? WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                      (donation_amount, gid, user_id, dragon_type))
                        returned_users.append(f"<@{user_id}>")

                    conn.commit()
                    conn.close()

                    cancelled_embed = discord.Embed(
                        title="❌ Ritual Cancelled",
                        description=f"The {ritual['rarity'].upper()} ritual has been cancelled.\n\n"
                                    f"🐉 All {ritual['donated']} donated dragons have been returned to their owners.",
                        color=discord.Color.red()
                    )
                    cancelled_embed.add_field(
                        name="Returned to:",
                        value=", ".join(returned_users[:10]) + ("..." if len(returned_users) > 10 else ""),
                        inline=False
                    )

                    await inter.followup.send(embed=cancelled_embed, ephemeral=False)

                # Remove ritual
                del ritual_active[gid]

                # Edit/remove ritual message
                try:
                    if ritual['message_id']:
                        msg = await inter.channel.fetch_message(ritual['message_id'])
                        cancelled_main = discord.Embed(
                            title="❌ Ritual Cancelled",
                            description=f"This ritual has been cancelled and removed.",
                            color=discord.Color.red()
                        )
                        await msg.edit(embed=cancelled_main, view=None)
                except:
                    pass

        # Send the ritual embed with buttons
        ritual_msg = await interaction.followup.send(embed=ritual_embed, view=RitualDonateView())
        ritual_active[guild_id]['message_id'] = ritual_msg.id

    @app_commands.command(name="raidstatus", description="View the current raid boss and attack it!")
    async def raidstatus(self, interaction: discord.Interaction):
        """View current raid boss status and attack (tier-aware)"""
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        current_time = int(time.time())

        from database import get_server_config
        cfg = get_server_config(guild_id)
        if not cfg['raids_enabled']:
            await interaction.response.send_message(
                "❌ Raids are not enabled on this server. Ask an admin to enable them via `/serverconfig`.",
                ephemeral=True)
            return

        conn = get_db_connection(120.0)
        c = conn.cursor()

        # Check if there's an active raid boss
        c.execute('''SELECT boss_name, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp,
                     boss_rarity, expires_at, reward_dragon, easy_participants, normal_participants, hard_participants
                     FROM raid_bosses WHERE guild_id = ?''', (guild_id,))
        boss_data = c.fetchone()

        if not boss_data:
            conn.close()
            await interaction.response.send_message(
                "❌ No active raid boss! Check back later.",
                ephemeral=False)
            return

        boss_name, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, boss_rarity, expires_at, reward_dragon, easy_part_str, normal_part_str, hard_part_str = boss_data

        # Determine if this is a shared-pool raid (ritual) or tier-based raid
        # Shared-pool: easy_max_hp == 0 and hard_max_hp == 0 (all players in normal pool)
        # Tier-based: only one of easy/normal/hard has max_hp > 0
        is_shared_pool = (easy_max_hp == 0 and hard_max_hp == 0 and normal_max_hp > 0)

        # Check which tier user is in
        c.execute('SELECT tier, damage_dealt, attacks_made FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                 (guild_id, user_id))
        user_tier_data = c.fetchone()

        # SHARED POOL RAIDS: Everyone fights the same boss, no tier selection
        if is_shared_pool:
            # Show shared pool raid boss to everyone (donors and non-donors alike)
            normal_part = eval(normal_part_str) if normal_part_str else []

            hp_percentage = (normal_hp / normal_max_hp) * 100 if normal_max_hp > 0 else 0
            hp_bar_length = 20
            filled = int((hp_percentage / 100) * hp_bar_length)
            hp_bar = "█" * filled + "░" * (hp_bar_length - filled)

            time_left = expires_at - current_time
            reward_data = DRAGON_TYPES[reward_dragon]

            embed = discord.Embed(
                title=f"⚔️ COMMUNITY RAID BOSS: {boss_name}",
                description=f"**Rarity:** {boss_rarity.title()}\n\n"
                           f"**HP:** {normal_hp:,} / {normal_max_hp:,}\n"
                           f"{hp_bar} {hp_percentage:.1f}%\n\n"
                           f"🎁 **Reward:** {reward_data['emoji']} {reward_data['name']} Dragon\n"
                           f"👥 **Participants:** {len(normal_part)}\n"
                           f"⏰ **Time Left:** {format_time_remaining(time_left)}",
                color=discord.Color.red()
            )

            # If user is already fighting, show leaderboard
            if user_tier_data:
                user_tier, user_damage, user_attacks = user_tier_data

                # Get leaderboard
                c.execute('''SELECT user_id, damage_dealt FROM raid_damage
                             WHERE guild_id = ?
                             ORDER BY damage_dealt DESC LIMIT 5''',
                         (guild_id,))
                leaderboard = c.fetchall()

                if leaderboard:
                    lb_text = ""
                    for idx, (uid, dmg) in enumerate(leaderboard, 1):
                        member = interaction.guild.get_member(uid)
                        if member:
                            medals = ['🥇', '🥈', '🥉']
                            medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                            lb_text += f"{medal} {member.mention}: {dmg:,} damage\n"

                    embed.add_field(
                        name=f"📊 Top Attackers",
                        value=lb_text,
                        inline=False
                    )

                embed.add_field(
                    name="📈 Your Stats",
                    value=f"💥 Damage: {user_damage:,}\n⚔️ Attacks: {user_attacks}",
                    inline=False
                )

            view = RaidAttackView(self.bot, guild_id)
            conn.close()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
            return

        # TIER-BASED RAIDS: Players choose which tier to join
        if not user_tier_data:
            # User hasn't joined a tier yet - show the raid spawn embed with tier selection
            easy_part = eval(easy_part_str) if easy_part_str else []
            normal_part = eval(normal_part_str) if normal_part_str else []
            hard_part = eval(hard_part_str) if hard_part_str else []

            reward_data = DRAGON_TYPES[reward_dragon]

            # Create the same embed as when raid spawned - with all 3 tiers
            embed = discord.Embed(
                title=f"⚔️ RAID BOSS SPAWNED: {boss_name}",
                description=f"**Rarity:** {boss_rarity.capitalize()}\n\n"
                            f"🎮 **Choose your difficulty tier below!**\n"
                            f"Each tier has its own HP pool and leaderboard.",
                color=discord.Color.red()
            )

            # Easy tier
            embed.add_field(
                name="🟢 EASY TIER",
                value=f"💚 For players with 0-10,000 damage potential\n"
                      f"📊 HP: {easy_hp:,} / {easy_max_hp:,}\n"
                      f"⚔️ Max Damage: 10,000\n"
                      f"👥 Participants: {len(easy_part)}",
                inline=True
            )

            # Normal tier
            embed.add_field(
                name="🟡 NORMAL TIER",
                value=f"💛 For players with 10,001-70,000 damage potential\n"
                      f"📊 HP: {normal_hp:,} / {normal_max_hp:,}\n"
                      f"⚔️ Max Damage: 70,000\n"
                      f"👥 Participants: {len(normal_part)}",
                inline=True
            )

            # Hard tier
            embed.add_field(
                name="🔴 HARD TIER",
                value=f"❤️ For players with 70,000+ damage potential\n"
                      f"📊 HP: {hard_hp:,} / {hard_max_hp:,}\n"
                      f"⚔️ Max Damage: 100,000\n"
                      f"👥 Participants: {len(hard_part)}",
                inline=True
            )

            embed.add_field(
                name="🎁 Reward",
                value=f"{reward_data['emoji']} **{reward_data['name']} Dragon**\n"
                      f"✨ 1x per victory + bonus coins",
                inline=False
            )

            time_left = expires_at - current_time
            hours = max(0, time_left // 3600)
            minutes = max(0, (time_left % 3600) // 60)
            embed.add_field(
                name="⏰ Duration",
                value=f"{hours}h {minutes}m",
                inline=True
            )

            embed.set_footer(text="Click a button to choose your tier! You'll be locked in and cannot change.")

            # Create view with tier buttons
            view = RaidTierSelectView(self.bot, guild_id, boss_name, boss_rarity, reward_dragon)
            conn.close()

            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
            return

        user_tier, user_damage, user_attacks = user_tier_data

        # Show only user's tier
        tier_hp_data = {
            'easy': (easy_hp, easy_max_hp, easy_part_str),
            'normal': (normal_hp, normal_max_hp, normal_part_str),
            'hard': (hard_hp, hard_max_hp, hard_part_str)
        }

        tier_hp, tier_max_hp, tier_part_str = tier_hp_data[user_tier]
        tier_part = eval(tier_part_str) if tier_part_str else []

        # Check if defeated
        if tier_hp <= 0:
            # This tier is defeated
            c.execute('''SELECT user_id, damage_dealt FROM raid_damage
                         WHERE guild_id = ? AND tier = ?
                         ORDER BY damage_dealt DESC LIMIT 10''',
                     (guild_id, user_tier))
            tier_damagers = c.fetchall()

            reward_data = DRAGON_TYPES[reward_dragon]
            tier_names_display = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}

            embed = discord.Embed(
                title=f"🏆 {tier_names_display[user_tier]} TIER DEFEATED!",
                description=f"**{boss_name}** {tier_names_display[user_tier]} tier is defeated!\n\n"
                            f"{reward_data['emoji']} **Reward:** {reward_data['name']} Dragon",
                color=discord.Color.gold()
            )

            tier_rewards = {'easy': 1, 'normal': 2, 'hard': 3}
            dragon_count = tier_rewards[user_tier]

            for idx, (uid, dmg) in enumerate(tier_damagers, 1):
                member = interaction.guild.get_member(uid)
                if member:
                    medals = ['🥇', '🥈', '🥉']
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                    embed.add_field(
                        name=f"{medal} {member.display_name}",
                        value=f"💥 {dmg:,} damage | +{dragon_count}x dragons",
                        inline=True
                    )

            conn.close()
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        # Active boss - show tier-specific status
        hp_percentage = (tier_hp / tier_max_hp) * 100 if tier_max_hp > 0 else 0
        hp_bar_length = 20
        filled = int((hp_percentage / 100) * hp_bar_length)
        hp_bar = "█" * filled + "░" * (hp_bar_length - filled)

        time_left = expires_at - current_time

        reward_data = DRAGON_TYPES[reward_dragon]
        tier_names_display = {'easy': '🟢 EASY', 'normal': '🟡 NORMAL', 'hard': '🔴 HARD'}
        tier_damage_caps = {'easy': 25000, 'normal': 60000, 'hard': 100000}

        embed = discord.Embed(
            title=f"⚔️ {tier_names_display[user_tier]} TIER RAID",
            description=f"**Boss:** {boss_name}\n"
                       f"**Rarity:** {boss_rarity.title()}\n"
                       f"**Your Tier:** {tier_names_display[user_tier]}\n\n"
                       f"**HP:** {tier_hp:,} / {tier_max_hp:,}\n"
                       f"{hp_bar} {hp_percentage:.1f}%\n\n"
                       f"🎁 **Reward:** {reward_data['emoji']} {reward_data['name']} Dragon\n"
                       f"👥 **Participants in your tier:** {len(tier_part)}\n"
                       f"⏰ **Time Left:** {format_time_remaining(time_left)}\n\n"
                       f"**Your Stats:**\n"
                       f"💥 Damage: {user_damage:,}\n"
                       f"⚔️ Max per Attack: {tier_damage_caps[user_tier]:,}\n"
                       f"🔄 Attacks: {user_attacks}",
            color=discord.Color.red()
        )

        # Get leaderboard for user's tier
        c.execute('''SELECT user_id, damage_dealt FROM raid_damage
                     WHERE guild_id = ? AND tier = ?
                     ORDER BY damage_dealt DESC LIMIT 5''',
                 (guild_id, user_tier))
        tier_leaderboard = c.fetchall()

        if tier_leaderboard:
            lb_text = ""
            for idx, (uid, dmg) in enumerate(tier_leaderboard, 1):
                member = interaction.guild.get_member(uid)
                if member:
                    medals = ['🥇', '🥈', '🥉']
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                    lb_text += f"{medal} {member.mention}: {dmg:,} damage\n"

            embed.add_field(
                name=f"📊 Leaderboard ({user_tier.upper()} TIER)",
                value=lb_text,
                inline=False
            )

        # Create attack view
        view = RaidAttackView(self.bot, guild_id)
        conn.close()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(RaidsCog(bot))
