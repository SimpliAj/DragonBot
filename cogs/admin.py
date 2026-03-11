"""
cogs/admin.py - Admin commands: setchannel and handle_dev_command.
Extracted verbatim from bot.py.
"""

import asyncio
import json
import random
import sqlite3
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import (
    BLACK_MARKET_DURATION, BLACK_MARKET_ITEMS, DRAGON_RARITY_TIERS,
    DRAGON_TYPES, DRAGONNEST_UPGRADES, LEVEL_NAMES, PACK_TYPES,
    RAID_DURATION_HOURS, DEV_USER_ID, generate_unique_perks,
)
from database import get_user, is_player_softlocked, update_balance
from state import (
    active_breeding_sessions, active_dragonfest, active_dragonscales,
    active_luckycharms, active_spawns, active_usable_items,
    black_market_active, last_spawn_data, premium_users,
    raid_boss_active, raid_boss_last_spawn, spawn_channels,
)
from utils import (
    add_dragons, format_time_remaining, get_spawn_channel,
    is_raid_boss_active, set_spawn_channel,
)

import logging
logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setchannel", description="Set current channel as dragon spawn channel (Admin only)")
    async def setchannel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions!", ephemeral=False)
            return

        # Check if channel name contains "cat" (people confusing bots)
        channel_name = interaction.channel.name.lower()
        if 'cat' in channel_name:
            cat_channel_mocks = [
                f"🐱❌ Bruh... this channel is called **{interaction.channel.name}**\n\n"
                f"You're trying to set a **CAT** channel for **DRAGONS**??? 💀\n"
                f"Go catch your cats somewhere else, this is for **DRAGONS** 🐉",

                f"😂 LMFAOOO you're setting **{interaction.channel.name}** as the dragon spawn channel?!\n\n"
                f"That's a **CAT CHANNEL** genius! 🐱\n"
                f"Dragons don't spawn where cats live! 🐉",

                f"🤡 Imagine setting a channel with '**cat**' in the name for dragons...\n\n"
                f"**Wrong bot buddy!** This is Dragon Bot, not Cat Bot! 🐉\n"
                f"Make a proper dragon channel! 🔥",

                f"💀 **{interaction.channel.name}**??? For DRAGONS?!\n\n"
                f"Brother... that's literally a cat channel 🐱\n"
                f"Are you lost? This is Dragon Bot! 🐉"
            ]
            await interaction.response.send_message(random.choice(cat_channel_mocks), ephemeral=False)
            return

        set_spawn_channel(interaction.guild_id, interaction.channel_id)
        await interaction.response.send_message(f"✅ Dragon spawn channel set to {interaction.channel.mention}!")

    @app_commands.command(name="serverconfig", description="Configure server settings for raids & black market (Admin only)")
    async def serverconfig(self, interaction: discord.Interaction):
        is_dev = interaction.user.id == DEV_USER_ID
        is_admin = interaction.user.guild_permissions.administrator
        if not is_dev and not is_admin:
            await interaction.response.send_message(
                "❌ Only admins or the bot developer can use this.", ephemeral=True
            )
            return
        embed = _build_config_embed(interaction.guild_id)
        view = ServerConfigView(interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle dev commands in on_message (called from EventsCog)"""
        pass  # Dev command handling is in EventsCog.on_message


async def handle_dev_command(message, command, args):
    """Handle all dev commands with -db prefix"""
    guild_id = message.guild.id

    # -db reset-perks <@user|*> - Reset all Dragon Nest perks (single user or all users in server)
    if command == 'reset-perks':
        # Check if we have any args at all
        if not args:
            await message.channel.send("❌ Usage: `-db reset-perks <@user>` or `-db reset-perks *` (for all users)")
            return

        # Determine if resetting all users or single user
        reset_all = args[0] == '*'

        if reset_all:
            # Reset for ALL users in the server
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            # Get all users who have EVER used Dragon Nest in this server
            c.execute('''SELECT DISTINCT user_id FROM dragon_nest WHERE guild_id = ?''',
                      (guild_id,))
            all_user_ids = [row[0] for row in c.fetchall()]

            if not all_user_ids:
                await message.channel.send("❌ No users with Dragon Nest progress found in this server!")
                conn.close()
                return

            # Delete all perks for all users
            c.execute('DELETE FROM user_perks WHERE guild_id = ?', (guild_id,))
            c.execute('DELETE FROM active_perks WHERE guild_id = ?', (guild_id,))
            c.execute('DELETE FROM pending_perks WHERE guild_id = ?', (guild_id,))

            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ Dragon Nest Perks Reset (All Users)",
                description=f"**Server:** {message.guild.name}\n"
                            f"**Users Affected:** {len(all_user_ids)}\n\n"
                            f"All Dragon Nest perks have been reset for all users!\n\n"
                            f"Users can now use `/dragonnest` → **Claim Missing Perks** to reclaim their perks.",
                color=discord.Color.green()
            )

            await message.channel.send(embed=embed)

            # Send DM to all affected users
            for user_id in all_user_ids:
                try:
                    user = await message.client.fetch_user(user_id)
                    dm_embed = discord.Embed(
                        title="🔄 Dragon Nest Perks Reset",
                        description=f"All your Dragon Nest perks have been reset in **{message.guild.name}**!\n\n"
                                    f"You can now use `/dragonnest` → **Claim Missing Perks** to reclaim your perks.",
                        color=discord.Color.blue()
                    )
                    await user.send(embed=dm_embed)
                except:
                    pass

            return

        else:
            # Reset for single user
            if not message.mentions:
                await message.channel.send("❌ Du musst einen User erwähnen! Verwendung: `-db reset-perks <@user>`")
                return

            user = message.mentions[0]
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            # Get Dragon Nest info if it exists
            c.execute('SELECT level, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            result = c.fetchone()
            current_level = result[0] if result else 0
            upgrade_level = result[1] if result and len(result) > 1 else 0

            # Count perks before deletion
            c.execute('SELECT COUNT(*) FROM user_perks WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            level_perks_count = c.fetchone()[0]

            c.execute('SELECT COUNT(*) FROM active_perks WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            permanent_perks_count = c.fetchone()[0]

            c.execute('SELECT COUNT(*) FROM pending_perks WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            pending_perks_count = c.fetchone()[0]

            total_perks = level_perks_count + permanent_perks_count + pending_perks_count

            # Delete ALL perks
            c.execute('DELETE FROM user_perks WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            c.execute('DELETE FROM active_perks WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))

            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ Dragon Nest Perks Reset",
                description=f"**User:** {user.mention}\n"
                            f"**Dragon Nest Level:** {current_level}\n"
                            f"**Upgrade Level:** Tier {upgrade_level}\n\n"
                            f"**Gelöschte Perks:** {total_perks}\n"
                            f"  • 📖 Level-Perks: {level_perks_count}\n"
                            f"  • ✨ Permanente Perks: {permanent_perks_count}\n"
                            f"  • 🔮 Ausstehende Perks: {pending_perks_count}\n\n"
                            f"Der User kann jetzt `/dragonnest` → **Claim Missing Perks** verwenden!",
                color=discord.Color.green()
            )

            await message.channel.send(embed=embed)

            try:
                dm_embed = discord.Embed(
                    title="🔄 Dragon Nest Perks Reset",
                    description=f"Ein Moderator in **{message.guild.name}** hat alle deine Dragon Nest Perks zurückgesetzt!\n\n"
                                f"Du kannst jetzt `/dragonnest` → **Claim Missing Perks** verwenden um deine Perks neu auszuwählen.",
                    color=discord.Color.blue()
                )
                await user.send(embed=dm_embed)
            except:
                pass

            return

    # -db resetinventory <@user>
    if command == 'resetinventory':
        if not message.mentions:
            await message.channel.send("❌ Usage: `-db resetinventory <@user>`")
            return

        user = message.mentions[0]
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get inventory info before reset
        c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))
        total_dragons = c.fetchone()[0] or 0

        c.execute('SELECT coins FROM users WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))
        user_coins = c.fetchone()[0] if c.fetchone() else 0

        # Reset all dragons
        c.execute('DELETE FROM user_dragons WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))

        # Reset coins to 0
        c.execute('UPDATE users SET coins = 0 WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))

        # Reset packs
        c.execute('DELETE FROM user_packs WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="✅ Inventory Reset Successfully",
            description=f"**User:** {user.mention}\n"
                        f"**Dragons Removed:** {total_dragons}\n"
                        f"**Coins Removed:** {user_coins}\n\n"
                        f"User inventory has been completely cleared!",
            color=discord.Color.green()
        )

        await message.channel.send(embed=embed)

        try:
            dm_embed = discord.Embed(
                title="🔄 Inventory Reset",
                description=f"Your inventory has been reset by a moderator in **{message.guild.name}**!\n\n"
                            f"**Dragons Removed:** {total_dragons}\n"
                            f"**Coins Removed:** {user_coins}",
                color=discord.Color.blue()
            )
            await user.send(embed=dm_embed)
        except:
            pass

        try:
            dm_dev = discord.Embed(
                title="✅ Inventory Reset",
                description=f"**Server:** {message.guild.name}\n**User:** {user.name}\n**Dragons:** {total_dragons}\n**Coins:** {user_coins}",
                color=discord.Color.green()
            )
            await message.author.send(embed=dm_dev)
        except:
            pass
        return

    # -db dragonfest <minutes>
    if command == 'dragonfest':
        if not args or not args[0].isdigit():
            await message.channel.send("❌ Usage: `-db dragonfest <minutes>`")
            return

        minutes = int(args[0])

        if is_raid_boss_active(guild_id):
            await message.channel.send("❌ Cannot start dragonfest during an active raid boss! ⚔️")
            return

        current_time = int(time.time())
        end_time = current_time + (minutes * 60)
        active_dragonfest[guild_id] = {'start': current_time, 'end': end_time}

        await message.channel.send(f"🎉 **DRAGONFEST ACTIVATED!** 🐉\nDragons will spawn frequently for the next {minutes} minutes!")

        await asyncio.sleep(1)
        from cogs.events import spawn_dragon
        await spawn_dragon(guild_id, message.channel, message._state._get_client())

        try:
            dm_embed = discord.Embed(
                title="✅ Dragonfest Started",
                description=f"**Server:** {message.guild.name}\n**Duration:** {minutes} minutes",
                color=discord.Color.green()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db spawnraid [hours]
    if command == 'spawnraid':
        hours = 4
        if args and args[0].isdigit():
            hours = int(args[0])
            if hours < 1 or hours > 24:
                await message.channel.send("❌ Hours must be between 1 and 24!")
                return

        current_time = int(time.time())
        raid_boss_active[guild_id] = {
            'active': True,
            'spawn_time': current_time,
            'despawn_time': current_time + (hours * 60 * 60),
            'manual_spawn': True
        }

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (guild_id,))
        c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))

        c.execute('''SELECT user_id FROM user_dragons
                     WHERE guild_id = ? AND count > 0''', (guild_id,))
        player_ids = [row[0] for row in c.fetchall()]
        active_players = len(set(player_ids)) or 1

        total_potential_damage = 0
        total_dragons_count = 0
        for player_id in set(player_ids):
            c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                     (guild_id, player_id))
            user_dragons_list = c.fetchall()

            player_potential = 0
            for dragon_type, count in user_dragons_list:
                total_dragons_count += count
                dragon_rarity = 'common'
                for rarity, dragons in DRAGON_RARITY_TIERS.items():
                    if dragon_type in dragons:
                        dragon_rarity = rarity
                        break

                from state import RARITY_DAMAGE
                damage_per_dragon = RARITY_DAMAGE[dragon_rarity]
                player_potential += count * damage_per_dragon

            total_potential_damage += player_potential

        avg_damage_per_player = total_potential_damage / active_players if active_players > 0 else 1500

        boss_rarities = ['epic', 'legendary', 'mythic', 'ultra']
        boss_rarity = random.choices(boss_rarities, weights=[50, 30, 15, 5])[0]

        rarity_attack_targets = {
            'epic': 4,
            'legendary': 6,
            'mythic': 8,
            'ultra': 10
        }

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

        easy_hp = int(base_hp * 3.0)
        normal_hp = int(base_hp * 4.0)
        hard_hp = int(base_hp * 6.0)

        hp_limits = {
            'epic': (20000, 100000),
            'legendary': (40000, 200000),
            'mythic': (150000, 300000),
            'ultra': (300000, 800000)
        }

        min_hp, max_hp = hp_limits[boss_rarity]
        easy_hp = max(min_hp // 2, min(easy_hp, max_hp // 3))
        normal_hp = max(min_hp, min(normal_hp, max_hp // 2))
        hard_hp = max(int(min_hp * 2), min(hard_hp, max_hp))

        boss_names = {
            'epic': ['Ancient Wyrm', 'Iron Goliath', 'Storm Titan', 'Frost Giant'],
            'legendary': ['Emerald Overlord', 'Diamond Behemoth', 'Obsidian Terror'],
            'mythic': ['Golden Sovereign', 'Platinum Destroyer', 'Crystal Devourer'],
            'ultra': ['Celestial Avatar', 'Void Incarnate', 'Cosmic Leviathan', 'Primordial Nightmare']
        }

        boss_name = random.choice(boss_names[boss_rarity])
        reward_dragons = DRAGON_RARITY_TIERS[boss_rarity]
        reward_dragon = random.choice(reward_dragons)

        c.execute('''INSERT INTO raid_bosses (guild_id, boss_name, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp,
                                             boss_rarity, reward_dragon, started_at, expires_at, easy_participants, normal_participants, hard_participants)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (guild_id, boss_name, easy_hp, easy_hp, normal_hp, normal_hp, hard_hp, hard_hp,
                   boss_rarity, reward_dragon, current_time, current_time + (hours * 60 * 60), '[]', '[]', '[]'))

        conn.commit()
        conn.close()

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

        embed.add_field(
            name="⏰ Duration",
            value=f"{RAID_DURATION_HOURS} hours",
            inline=True
        )

        embed.set_footer(text="Click a button to choose your tier! You'll be locked in and cannot change.")

        from cogs.raids import RaidTierSelectView
        view = RaidTierSelectView(guild_id, boss_name, boss_rarity, reward_dragon)
        raid_message = await message.channel.send(embed=embed, view=view)

        # Store message ID for live updates
        try:
            conn2 = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c2 = conn2.cursor()
            c2.execute('UPDATE raid_bosses SET message_id = ? WHERE guild_id = ?', (raid_message.id, guild_id))
            conn2.commit()
            conn2.close()
        except:
            pass

        try:
            dm_embed = discord.Embed(
                title="✅ Raid Boss Spawned",
                description=f"**Server:** {message.guild.name}\n**Boss:** {boss_name} ({boss_rarity})\n**Duration:** {format_time_remaining(hours * 3600)}\n\n"
                           f"Easy: {easy_hp:,} HP\nNormal: {normal_hp:,} HP\nHard: {hard_hp:,} HP",
                color=discord.Color.red()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db spawnblackmarket
    if command == 'spawnblackmarket':
        current_time = int(time.time())

        pack_items = ['pack_wooden', 'pack_stone', 'pack_bronze']
        selected_packs = random.sample(pack_items, 2)

        epic_dragons = []
        for rarity in ['epic', 'legendary', 'mythic', 'ultra']:
            epic_dragons.extend(DRAGON_RARITY_TIERS[rarity])

        selected_dragon = random.choice(epic_dragons)
        dragon_data = DRAGON_TYPES[selected_dragon]

        special_items = ['dna_sample', 'lucky_charm', 'lucky_dice', 'night_vision']
        selected_item = random.choice(special_items)

        base_dragon_price = int(dragon_data['value'] * 20)
        black_market_dragon_price = int(base_dragon_price * 0.75)

        items_list = []
        for pack_key in selected_packs:
            items_list.append({
                'key': pack_key,
                'stock': random.randint(3, 8),
                'is_dragon': False
            })

        items_list.append({
            'key': selected_dragon,
            'stock': random.randint(1, 3),
            'price': black_market_dragon_price,
            'is_dragon': True,
            'dragon_data': dragon_data
        })

        items_list.append({
            'key': selected_item,
            'stock': random.randint(2, 5),
            'is_dragon': False
        })

        end_time = current_time + BLACK_MARKET_DURATION
        black_market_active[guild_id] = {
            'end_time': end_time,
            'items': items_list,
            'message_id': None
        }

        items_text = ""
        for item in items_list:
            if item['is_dragon']:
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

                if gid not in black_market_active or black_market_active[gid]['end_time'] < current_time:
                    await interaction.response.send_message("❌ The Black Market has closed!", ephemeral=False)
                    return

                user_data = get_user(gid, interaction.user.id)
                balance = user_data[2]

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
                            item_name = f"{item_info['emoji']} {item_info['name']} Dragon"
                        else:
                            item_info = BLACK_MARKET_ITEMS[item_key]
                            price = item_info['black_price']
                            item_name = f"{item_info['emoji']} {item_info['name']}"

                        user_data = get_user(gid, select_interaction.user.id)
                        balance = user_data[2]

                        if balance < price:
                            await select_interaction.response.send_message(
                                f"❌ You need **{price:,}** 🪙 but only have **{int(balance):,}** 🪙!",
                                ephemeral=False
                            )
                            return

                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()

                        c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                                  (price, gid, select_interaction.user.id))

                        if market_item['is_dragon']:
                            await add_dragons(gid, select_interaction.user.id, item_key, 1)
                        else:
                            if item_key.startswith('pack_'):
                                pack_type = item_key.split('_')[1]
                                c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                             VALUES (?, ?, ?, 1)
                                             ON CONFLICT(guild_id, user_id, pack_type)
                                             DO UPDATE SET count = count + 1''',
                                          (gid, select_interaction.user.id, pack_type))
                            else:
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

                        conn.commit()
                        conn.close()

                        market_item['stock'] -= 1

                        success_embed = discord.Embed(
                            title="✅ Purchase Complete!",
                            description=f"You've acquired **{item_name}** from the Black Market!\n\n"
                                        f"💰 Paid: **{price:,}** 🪙",
                            color=discord.Color.green()
                        )
                        await select_interaction.response.send_message(embed=success_embed, ephemeral=False)

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
                        market_embed.description += f"   💰 Price: **{item['price']:,}** 🪙\n"
                        market_embed.description += f"   Stock: {item['stock']}\n\n"
                    else:
                        item_info = BLACK_MARKET_ITEMS[item['key']]
                        market_embed.description += f"{item_info['emoji']} **{item_info['name']}**\n"
                        market_embed.description += f"   💰 Price: **{item_info['black_price']:,}** 🪙\n"
                        market_embed.description += f"   Stock: {item['stock']}\n\n"

                market_embed.description += f"\n⏰ Closes in **{minutes_left}** minutes!"
                market_embed.set_footer(text="Your balance: " + f"{int(balance):,}🪙")

                await interaction.response.send_message(embed=market_embed, view=BlackMarketView(), ephemeral=False)

        market_message = await message.channel.send(embed=embed, view=BlackMarketAnnounceView())
        black_market_active[guild_id]['message_id'] = market_message.id

        try:
            dm_embed = discord.Embed(title="✅ Black Market Spawned", description=f"**Server:** {message.guild.name}\n**Items:**\n" + "\n".join([f"• {BLACK_MARKET_ITEMS[item['key']]['name']}" if not item['is_dragon'] else f"• {item['dragon_data']['name']} Dragon" for item in items_list]), color=0xFEE75C)
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db spawnstatus
    if command == 'spawnstatus':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        current_time = int(time.time())

        c.execute('SELECT guild_id, spawn_channel_id, last_spawn_time FROM spawn_config WHERE guild_id = ?', (guild_id,))
        spawn_config = c.fetchone()

        is_raid_active = guild_id in raid_boss_active and raid_boss_active[guild_id]['active']

        has_dragonfest = guild_id in active_dragonfest
        has_dragonscale = guild_id in active_dragonscales

        conn.close()

        if not spawn_config:
            embed = discord.Embed(
                title="❌ No Spawn Config",
                description=f"**Guild ID:** {guild_id}\n**Problem:** No spawn channel configured!",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed)
            return

        guild_id_db, channel_id, last_spawn_time = spawn_config

        time_since_last_spawn = current_time - last_spawn_time

        bot_ref = message._state._get_client()
        channel = bot_ref.get_channel(channel_id) if channel_id else None
        channel_name = channel.name if channel else f"Unknown (ID: {channel_id})"

        normal_interval = random.randint(180, 900)
        event_interval = random.randint(2, 5)

        if has_dragonfest or has_dragonscale:
            time_until_spawn = event_interval - time_since_last_spawn
            spawn_mode = "🎉 EVENT MODE (2-5 sec)"
        else:
            time_until_spawn = normal_interval - time_since_last_spawn
            spawn_mode = "🐉 NORMAL MODE (3-15 min)"

        embed = discord.Embed(
            title="🔍 Spawn Status",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Spawn Channel",
            value=f"#{channel_name}" if channel else f"❌ Invalid/Missing (ID: {channel_id})",
            inline=False
        )

        embed.add_field(name="Mode", value=spawn_mode, inline=False)
        embed.add_field(name="Last Spawn", value=f"{time_since_last_spawn}s ago", inline=True)

        if time_until_spawn > 0:
            embed.add_field(name="Next Spawn In", value=f"~{time_until_spawn}s", inline=True)
        else:
            embed.add_field(name="Status", value="✅ Ready to spawn NOW", inline=True)

        embed.add_field(
            name="Active Events",
            value=f"Raid Boss: {'✅ YES' if is_raid_active else '❌ NO'}\n"
                  f"Dragonfest: {'✅ YES' if has_dragonfest else '❌ NO'}\n"
                  f"Dragonscale: {'✅ YES' if has_dragonscale else '❌ NO'}",
            inline=False
        )

        if is_raid_active:
            embed.add_field(
                name="⚠️ WARNING",
                value="Raid boss is active! Dragons won't spawn until raid boss despawns.",
                inline=False
            )

        await message.channel.send(embed=embed)
        return

    # -db resetspawn
    if command == 'resetspawn':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        current_time = int(time.time())
        reset_time = current_time - 1000

        c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?', (reset_time, guild_id))

        rows_updated = c.rowcount

        if rows_updated == 0:
            c.execute('INSERT INTO spawn_config (guild_id, last_spawn_time) VALUES (?, ?)',
                      (guild_id, reset_time))

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="✅ Spawn Timer Reset",
            description=f"Dragons should spawn within the next **30 seconds**!",
            color=discord.Color.green()
        )

        await message.channel.send(embed=embed)
        return

    # -db clearevents
    if command == 'clearevents':
        removed_dragonfests = len(active_dragonfest)
        active_dragonfest.clear()

        removed_dragonscales = len(active_dragonscales)
        active_dragonscales.clear()

        removed_raidbosses = len(raid_boss_active)
        raid_boss_active.clear()

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('DELETE FROM dragonfest_stats')
        c.execute('DELETE FROM dragonscale_stats')
        c.execute('DELETE FROM raid_bosses')
        c.execute('DELETE FROM raid_damage')

        current_time = int(time.time())
        c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?', (current_time, guild_id))

        bot_ref = message._state._get_client()
        for guild in bot_ref.guilds:
            raid_boss_last_spawn[guild.id] = current_time

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🧹 Event Cleanup Complete",
            description=f"✅ Cleared **{removed_dragonfests}** dragonfests\n"
                        f"✅ Cleared **{removed_dragonscales}** dragonscales\n"
                        f"✅ Cleared **{removed_raidbosses}** raid bosses",
            color=discord.Color.green()
        )

        await message.channel.send(embed=embed)

        try:
            dm_embed = discord.Embed(
                title="✅ Events Cleared",
                description=f"**Dragonfests:** {removed_dragonfests}\n**Dragonscales:** {removed_dragonscales}\n**Raid Bosses:** {removed_raidbosses}",
                color=discord.Color.orange()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db wipeserver
    if command == 'wipeserver':
        if not args or args[0].lower() != 'confirm':
            embed = discord.Embed(
                title="⚠️ WIPESERVER - DANGEROUS OPERATION",
                description=f"**This will delete EVERYTHING in this server:**\n"
                           f"• All user dragons\n"
                           f"• All user coins\n"
                           f"• All user items\n"
                           f"• All alpha dragons\n"
                           f"• All battlepass progress\n"
                           f"• All bingo cards\n"
                           f"• All perks\n"
                           f"• All packs\n\n"
                           f"**To confirm, run:** `-db wipeserver confirm`",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed)
            return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT COUNT(*) FROM users WHERE guild_id = ?', (guild_id,))
        user_count = c.fetchone()[0]

        c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ?', (guild_id,))
        dragon_count = c.fetchone()[0] or 0

        c.execute('SELECT SUM(count) FROM user_items WHERE guild_id = ?', (guild_id,))
        item_count = c.fetchone()[0] or 0

        c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ?', (guild_id,))
        alpha_count = c.fetchone()[0]

        tables_to_wipe = [
            'users', 'user_dragons', 'user_alphas', 'user_items', 'user_packs',
            'user_perks', 'active_perks', 'user_luckycharms', 'dragonscales',
            'user_bingo', 'battlepass_progress', 'dragon_nest', 'bounty_progress',
            'breeding_log', 'user_discoveries', 'dragonpass'
        ]

        for table in tables_to_wipe:
            try:
                c.execute(f'DELETE FROM {table} WHERE guild_id = ?', (guild_id,))
            except:
                pass

        for key_dict in [active_dragonfest, active_dragonscales, raid_boss_active,
                         active_luckycharms, active_usable_items, spawn_channels,
                         premium_users, last_spawn_data]:
            if guild_id in key_dict:
                del key_dict[guild_id]

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🧹 SERVER WIPE COMPLETE",
            description=f"**Deleted from {message.guild.name}:**\n"
                       f"✅ **{user_count}** users\n"
                       f"✅ **{dragon_count:,}** dragons\n"
                       f"✅ **{item_count:,}** items\n"
                       f"✅ **{alpha_count}** alpha dragons\n\n"
                       f"⚠️ All data for this server has been permanently deleted!",
            color=discord.Color.green()
        )

        await message.channel.send(embed=embed)

        try:
            dm_embed = discord.Embed(
                title="🧹 Server Wipe Executed",
                description=f"**Server:** {message.guild.name}\n"
                           f"**Users Deleted:** {user_count}\n"
                           f"**Dragons Deleted:** {dragon_count:,}\n"
                           f"**Items Deleted:** {item_count:,}\n"
                           f"**Alpha Dragons Deleted:** {alpha_count}",
                color=discord.Color.orange()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db giveaway
    if command == 'giveaway':
        claimed_users = set()

        embed = discord.Embed(
            title="🎁 Pack Giveaway!",
            description="**Click the button below to claim your reward!**\n\n"
                        "🎁 **Reward:** 3 Random Packs\n"
                        "⏰ **Expires:** Never!",
            color=discord.Color.gold()
        )

        class GiveawayView(discord.ui.View):
            def __init__(self_inner):
                super().__init__(timeout=None)

            @discord.ui.button(label="Claim Packs!", style=discord.ButtonStyle.green, emoji="🎁")
            async def claim_button(self_inner, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id in claimed_users:
                    await interaction.response.send_message("❌ You've already claimed this giveaway!", ephemeral=False)
                    return

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                selected_packs = []
                for _ in range(3):
                    pack_type = random.choice(list(PACK_TYPES.keys()))
                    selected_packs.append(pack_type)
                    c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                 VALUES (?, ?, ?, 1)
                                 ON CONFLICT(guild_id, user_id, pack_type)
                                 DO UPDATE SET count = count + 1''',
                              (interaction.guild_id, interaction.user.id, pack_type))

                conn.commit()
                conn.close()

                claimed_users.add(interaction.user.id)

                pack_text = ", ".join([f"{PACK_TYPES[p]['emoji']} {PACK_TYPES[p]['name']}" for p in selected_packs])

                success_embed = discord.Embed(
                    title="✅ Packs Claimed!",
                    description=f"**You received:**\n{pack_text}\n\n"
                                f"Use `/openpacks` to open them!",
                    color=discord.Color.green()
                )

                await interaction.response.send_message(embed=success_embed, ephemeral=False)

        view = GiveawayView()
        await message.channel.send(embed=embed, view=view)
        return

    # -db givepack <guild_id> <user_id> <type> <amount>
    if command == 'givepack':
        if len(args) < 4:
            await message.channel.send("❌ Usage: `-db givepack <guild_id> <user_id> <type> <amount>`")
            return

        try:
            guild_id_int = int(args[0])
            user_id_int = int(args[1])
            pack_type = args[2].lower()
            amount = int(args[3])
        except ValueError:
            await message.channel.send("❌ Invalid arguments!")
            return

        if pack_type not in PACK_TYPES:
            await message.channel.send(f"❌ Invalid pack type! Valid: {', '.join(PACK_TYPES.keys())}")
            return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(guild_id, user_id, pack_type)
                     DO UPDATE SET count = count + ?''',
                  (guild_id_int, user_id_int, pack_type, amount, amount))
        conn.commit()
        conn.close()

        pack_data = PACK_TYPES[pack_type]
        await message.channel.send(f"✅ Gave {amount}x {pack_data['emoji']} {pack_data['name']} to <@{user_id_int}> in Guild {guild_id_int}!")

        try:
            dm_embed = discord.Embed(
                title="✅ Packs Given",
                description=f"**Guild:** {guild_id_int}\n**User:** <@{user_id_int}>\n**Pack:** {pack_data['emoji']} {pack_data['name']}\n**Amount:** {amount}",
                color=discord.Color.purple()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db givepremium <guild_id> <user_id> <days>
    if command == 'givepremium':
        if len(args) < 3:
            await message.channel.send("❌ Usage: `-db givepremium <guild_id> <user_id> <days>`")
            return

        try:
            guild_id_int = int(args[0])
            user_id_int = int(args[1])
            days = int(args[2])
        except ValueError:
            await message.channel.send("❌ Invalid arguments!")
            return

        current_time = int(time.time())
        premium_end = current_time + (days * 86400)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO premium_users (guild_id, user_id, premium_until)
                     VALUES (?, ?, ?)''',
                  (guild_id_int, user_id_int, premium_end))
        conn.commit()
        conn.close()

        if guild_id_int not in premium_users:
            premium_users[guild_id_int] = {}
        premium_users[guild_id_int][user_id_int] = premium_end

        await message.channel.send(f"✅ Gave {days} days of Premium to <@{user_id_int}> in Guild {guild_id_int}!")

        try:
            dm_embed = discord.Embed(
                title="✅ Premium Given",
                description=f"**Guild:** {guild_id_int}\n**User:** <@{user_id_int}>\n**Days:** {days}",
                color=discord.Color.gold()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db givecoins <@user> <amount>
    if command == 'givecoins':
        if not message.mentions or len(args) < 1:
            await message.channel.send("❌ Usage: `-db givecoins <@user> <amount>`")
            return

        user = message.mentions[0]
        try:
            amount = float(args[0 if not args[0].startswith('<@') else 1])
        except ValueError:
            await message.channel.send("❌ Invalid amount!")
            return

        get_user(guild_id, user.id)
        await asyncio.to_thread(update_balance, guild_id, user.id, amount)

        await message.channel.send(f"✅ Gave {int(amount)} 🪙 to {user.mention}!")

        try:
            dm_embed = discord.Embed(
                title="✅ Coins Given",
                description=f"**Server:** {message.guild.name}\n**User:** {user.name}\n**Amount:** {int(amount)} 🪙",
                color=discord.Color.gold()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db givedragons <@user> <type> <amount>
    if command == 'givedragons':
        if not message.mentions or len(args) < 2:
            await message.channel.send("❌ Usage: `-db givedragons <@user> <type> <amount>`")
            return

        user = message.mentions[0]
        dragon_type = args[0 if not args[0].startswith('<@') else 1]
        try:
            amount = int(args[1 if not args[0].startswith('<@') else 2])
        except ValueError:
            await message.channel.send("❌ Invalid amount!")
            return

        if dragon_type == "*":
            for dragon_key in DRAGON_TYPES.keys():
                await add_dragons(guild_id, user.id, dragon_key, amount)

            await message.channel.send(f"✅ Gave {amount}x of **ALL 22 dragon types** to {user.mention}!")

            try:
                dm_embed = discord.Embed(
                    title="✅ Dragons Given",
                    description=f"**Server:** {message.guild.name}\n**User:** {user.name}\n**Type:** ALL TYPES\n**Amount:** {amount} each",
                    color=discord.Color.blue()
                )
                await message.author.send(embed=dm_embed)
            except:
                pass
            return

        if dragon_type.lower() not in DRAGON_TYPES:
            await message.channel.send(f"❌ Invalid dragon type! Use `*` for all or: {', '.join(list(DRAGON_TYPES.keys())[:5])}...")
            return

        await add_dragons(guild_id, user.id, dragon_type.lower(), amount)
        dragon_data = DRAGON_TYPES[dragon_type.lower()]

        await message.channel.send(f"✅ Gave {amount}x {dragon_data['emoji']} {dragon_data['name']} to {user.mention}!")

        try:
            dm_embed = discord.Embed(
                title="✅ Dragons Given",
                description=f"**Server:** {message.guild.name}\n**User:** {user.name}\n**Dragon:** {dragon_data['emoji']} {dragon_data['name']}\n**Amount:** {amount}",
                color=discord.Color.blue()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db resetquests
    if command == 'resetquests':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        current_time = int(time.time())
        c.execute('UPDATE dragonpass SET quests_active = NULL, quest_refresh_time = ? WHERE guild_id = ?', (current_time + 43200, guild_id))
        affected = c.rowcount
        conn.commit()
        conn.close()

        await message.channel.send(f"✅ Reset quests for **{affected}** users in this server! New quests will generate on next `/dragonpass` use.")
        return

    # -db resetbattlepass
    if command == 'resetbattlepass':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('UPDATE dragonpass SET level = 0, xp = 0, claimed_levels = "[]" WHERE guild_id = ?', (guild_id,))
        affected = c.rowcount
        conn.commit()
        conn.close()

        await message.channel.send(f"✅ Reset battlepass for **{affected}** users in this server!")
        return

    # -db resetbingo
    if command == 'resetbingo':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('DELETE FROM bingo_cards WHERE guild_id = ?', (guild_id,))
        deleted_count = c.rowcount
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="✅ Bingo Reset Complete!",
            description=f"**Deleted {deleted_count} bingo cards**\n\n"
                       f"🎯 All players can now create new bingo cards\n"
                       f"🔄 Everyone starts fresh!",
            color=discord.Color.green()
        )

        await message.channel.send(embed=embed)

        try:
            dm_embed = discord.Embed(
                title="✅ Bingo Reset",
                description=f"**Server:** {message.guild.name}\n**Cards Deleted:** {deleted_count}",
                color=discord.Color.purple()
            )
            await message.author.send(embed=dm_embed)
        except:
            pass
        return

    # -db resetbreeding
    if command == 'resetbreeding':
        active_breeding_sessions.clear()
        await message.channel.send(f"✅ Cleared all breeding sessions! Users can now breed again.")
        return

    # -db restart
    if command == 'restart':
        await message.channel.send("🔄 Restarting bot...")
        bot_ref = message._state._get_client()
        await bot_ref.close()
        return

    # -db resetbreedcooldown <@user>
    if command == 'resetbreedcooldown':
        if not message.mentions:
            await message.channel.send("❌ Usage: `-db resetbreedcooldown <@user>`")
            return

        user = message.mentions[0]
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('DELETE FROM breeding_cooldowns WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))

        affected = c.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            embed = discord.Embed(
                title="✅ Breeding Cooldown Reset",
                description=f"**User:** {user.mention}\n"
                            f"**Status:** Cooldown removed, ready to breed!",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="⚠️ No Cooldown Found",
                description=f"**User:** {user.mention}\n"
                            f"**Status:** User has no active breeding cooldown",
                color=discord.Color.yellow()
            )

        await message.channel.send(embed=embed)
        return

    # -db raidinfo
    if command == 'raidinfo':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('SELECT boss_name, boss_rarity, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, easy_participants, normal_participants, hard_participants, expires_at FROM raid_bosses WHERE guild_id = ?',
                  (guild_id,))
        raid_data = c.fetchone()
        conn.close()

        if not raid_data:
            await message.channel.send("❌ No active raid boss in this server!")
            return

        boss_name, rarity, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp, easy_part, normal_part, hard_part, expires_at = raid_data

        easy_participants = len(eval(easy_part)) if easy_part else 0
        normal_participants = len(eval(normal_part)) if normal_part else 0
        hard_participants = len(eval(hard_part)) if hard_part else 0

        time_left = expires_at - int(time.time())
        hours = max(0, time_left // 3600)
        minutes = max(0, (time_left % 3600) // 60)

        embed = discord.Embed(
            title=f"⚔️ Raid Info: {boss_name}",
            description=f"**Rarity:** {rarity.upper()}\n**Time Left:** {hours}h {minutes}m",
            color=discord.Color.gold()
        )

        embed.add_field(name="🟢 EASY", value=f"HP: {easy_hp:,}/{easy_max_hp:,}\nParticipants: {easy_participants}", inline=True)
        embed.add_field(name="🟡 NORMAL", value=f"HP: {normal_hp:,}/{normal_max_hp:,}\nParticipants: {normal_participants}", inline=True)
        embed.add_field(name="🔴 HARD", value=f"HP: {hard_hp:,}/{hard_max_hp:,}\nParticipants: {hard_participants}", inline=True)

        await message.channel.send(embed=embed)
        return

    # -db raidkill
    if command == 'raidkill':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT boss_name FROM raid_bosses WHERE guild_id = ?', (guild_id,))
        raid_data = c.fetchone()

        if not raid_data:
            conn.close()
            await message.channel.send("❌ No active raid boss!")
            return

        boss_name = raid_data[0]

        c.execute('UPDATE raid_bosses SET easy_hp = 0, normal_hp = 0, hard_hp = 0 WHERE guild_id = ?', (guild_id,))
        c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (guild_id,))
        c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (guild_id,))
        conn.commit()
        conn.close()

        if guild_id in raid_boss_active:
            del raid_boss_active[guild_id]

        embed = discord.Embed(
            title="💀 Raid Boss Defeated!",
            description=f"**{boss_name}** has been slain! All raid data cleared.",
            color=discord.Color.red()
        )
        await message.channel.send(embed=embed)
        return

    # -db dbstatus
    if command == 'dbstatus':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT COUNT(DISTINCT guild_id) FROM users')
        servers = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM user_dragons')
        total_dragons = c.fetchone()[0]

        c.execute('SELECT SUM(balance) FROM users')
        total_coins = c.fetchone()[0] or 0

        c.execute('SELECT COUNT(*) FROM raid_bosses WHERE guild_id = ?', (guild_id,))
        active_raids = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM raid_damage WHERE guild_id = ?', (guild_id,))
        raid_participants = c.fetchone()[0]

        conn.close()

        embed = discord.Embed(
            title="📊 Database Status",
            color=discord.Color.blurple()
        )

        embed.add_field(name="📈 Global Stats", value=(
            f"Servers: **{servers}**\n"
            f"Total Users: **{total_users:,}**\n"
            f"Total Dragons: **{total_dragons:,}**\n"
            f"Total Coins: **{total_coins:,}**"
        ), inline=False)

        embed.add_field(name="⚔️ This Server", value=(
            f"Active Raids: **{active_raids}**\n"
            f"Raid Participants: **{raid_participants}**"
        ), inline=False)

        await message.channel.send(embed=embed)
        return

    # -db passgrant <user_id|*> <level>
    if command == 'passgrant':
        if len(args) < 2:
            await message.channel.send("❌ Usage: `-db passgrant <user_id|*> <level>`\nExample: `-db passgrant 123456789 15` or `-db passgrant * 10`")
            return

        target_user = args[0]
        try:
            level = int(args[1])
        except ValueError:
            await message.channel.send("❌ Level must be a number!")
            return

        if level < 0 or level > 30:
            await message.channel.send("❌ Level must be between 0 and 30!")
            return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        bot_ref = message._state._get_client()

        if target_user == '*':
            updated_count = 0

            guild = None
            for g in bot_ref.guilds:
                if g.id == guild_id:
                    guild = g
                    break

            if guild:
                for member in guild.members:
                    if member.bot:
                        continue

                    c.execute('SELECT user_id FROM users WHERE guild_id = ? AND user_id = ?',
                              (guild_id, member.id))
                    if not c.fetchone():
                        c.execute('INSERT INTO users (guild_id, user_id, balance, daily_last_claimed) VALUES (?, ?, 0, 0)',
                                  (guild_id, member.id))

                    claimed_list = list(range(1, level + 1))

                    c.execute('''INSERT INTO dragonpass (guild_id, user_id, season, level, xp, quests_active, quest_refresh_time, claimed_levels)
                                 VALUES (?, ?, 1, ?, 0, '[]', 0, ?)
                                 ON CONFLICT(guild_id, user_id, season)
                                 DO UPDATE SET level = ?, claimed_levels = ?''',
                              (guild_id, member.id, level, str(claimed_list), level, str(claimed_list)))

                    for lvl in range(1, level + 1):
                        if lvl < 30:
                            if lvl <= 10:
                                pack_type = 'stone' if lvl % 2 == 0 else 'wooden'
                            elif lvl <= 20:
                                pack_type = 'silver' if lvl % 2 == 0 else 'bronze'
                            else:
                                pack_type = 'diamond' if lvl % 2 == 0 else 'gold'

                            c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                         VALUES (?, ?, ?, 1)
                                         ON CONFLICT(guild_id, user_id, pack_type)
                                         DO UPDATE SET count = count + 1''',
                                      (guild_id, member.id, pack_type))
                        elif lvl == 30:
                            c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                         VALUES (?, ?, ?, 2)
                                         ON CONFLICT(guild_id, user_id, item_type)
                                         DO UPDATE SET count = count + 2''',
                                      (guild_id, member.id, 'dragonscale'))

                    updated_count += 1

            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ Dragonpass Granted!",
                description=f"**Level {level}** granted to **{updated_count}** users in this server!",
                color=discord.Color.gold()
            )
            await message.channel.send(embed=embed)
        else:
            try:
                user_id = int(target_user)
            except ValueError:
                await message.channel.send("❌ Invalid user ID! Use a number or `*` for all users.")
                conn.close()
                return

            claimed_list = list(range(1, level + 1))

            c.execute('''INSERT INTO dragonpass (guild_id, user_id, level, xp, quests, quest_refresh_time, claimed_levels)
                         VALUES (?, ?, ?, 0, '[]', 0, ?)
                         ON CONFLICT(guild_id, user_id)
                         DO UPDATE SET level = ?, claimed_levels = ?''',
                      (guild_id, user_id, level, str(claimed_list), level, str(claimed_list)))

            for lvl in range(1, level + 1):
                if lvl < 30:
                    if lvl <= 10:
                        pack_type = 'stone' if lvl % 2 == 0 else 'wooden'
                    elif lvl <= 20:
                        pack_type = 'silver' if lvl % 2 == 0 else 'bronze'
                    else:
                        pack_type = 'diamond' if lvl % 2 == 0 else 'gold'

                    c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                 VALUES (?, ?, ?, 1)
                                 ON CONFLICT(guild_id, user_id, pack_type)
                                 DO UPDATE SET count = count + 1''',
                              (guild_id, user_id, pack_type))
                elif lvl == 30:
                    c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                 VALUES (?, ?, ?, 2)
                                 ON CONFLICT(guild_id, user_id, item_type)
                                 DO UPDATE SET count = count + 2''',
                              (guild_id, user_id, 'dragonscale'))

            conn.commit()
            conn.close()

            target_member = message.guild.get_member(user_id)
            username = target_member.display_name if target_member else f"User {user_id}"

            embed = discord.Embed(
                title="✅ Dragonpass Granted!",
                description=f"**{username}** has been set to **Level {level}** in Dragonpass!",
                color=discord.Color.gold()
            )
            await message.channel.send(embed=embed)

        return

    # -db list-softlock
    if command == 'list-softlock':
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        softlocked_users = []

        c.execute('SELECT guild_id, user_id, balance FROM users WHERE guild_id = ?', (guild_id,))
        users = c.fetchall()

        for user_record in users:
            user_guild_id, user_id, balance = user_record

            c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user_id))
            upgrade_result = c.fetchone()
            upgrade_level = upgrade_result[0] if upgrade_result else 0

            next_level = upgrade_level + 1
            if next_level <= 5:
                upgrade_cost = DRAGONNEST_UPGRADES.get(next_level, {}).get('cost', 0)

                if balance >= upgrade_cost:
                    softlocked_users.append((user_id, balance, upgrade_level, upgrade_cost))

        conn.close()

        if not softlocked_users:
            await message.channel.send("✅ No softlocked users found!")
            return

        softlock_text = ""
        for user_id, balance, upgrade_level, cost in softlocked_users:
            member = message.guild.get_member(user_id)
            username = member.display_name if member else f"User {user_id}"
            softlock_text += f"• **{username}** (ID: {user_id}) - {int(balance):,} coins (needs {int(cost):,} for tier {upgrade_level + 1})\n"

        embed = discord.Embed(
            title=f"🔒 Softlocked Users ({len(softlocked_users)})",
            description=softlock_text,
            color=discord.Color.orange()
        )
        await message.channel.send(embed=embed)
        return

    # -db fix-softlock <@user>
    if command == 'fix-softlock':
        if not message.mentions:
            await message.channel.send("❌ Usage: `-db fix-softlock <@user>`")
            return

        user = message.mentions[0]
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))
        balance_result = c.fetchone()

        if not balance_result:
            await message.channel.send(f"❌ {user.mention} has no account!")
            conn.close()
            return

        balance = balance_result[0]

        c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))
        upgrade_result = c.fetchone()
        upgrade_level = upgrade_result[0] if upgrade_result else 0

        next_level = upgrade_level + 1
        upgrade_cost = DRAGONNEST_UPGRADES.get(next_level, {}).get('cost', 0) if next_level <= 5 else 0

        if balance < upgrade_cost:
            await message.channel.send(f"❌ {user.mention} is not softlocked! Balance: {int(balance):,} coins, Upgrade cost: {int(upgrade_cost):,} coins")
            conn.close()
            return

        new_balance = upgrade_cost - 1
        c.execute('UPDATE users SET balance = ? WHERE guild_id = ? AND user_id = ?',
                  (new_balance, guild_id, user.id))

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="✅ Softlock Removed",
            description=f"**{user.mention}** has been unfrozen!\n\n"
                        f"Old balance: **{int(balance):,}** coins\n"
                        f"New balance: **{int(new_balance):,}** coins\n"
                        f"Upgrade cost: **{int(upgrade_cost):,}** coins",
            color=discord.Color.green()
        )
        await message.channel.send(embed=embed)
        return

    # -db set-dragonnest-level <@user> <level>
    if command == 'set-dragonnest-level':
        if not message.mentions or len(args) < 2:
            await message.channel.send("❌ Usage: `-db set-dragonnest-level <@user> <level>`")
            return

        user = message.mentions[0]
        try:
            new_level = int(args[1])
        except ValueError:
            await message.channel.send("❌ Level must be a number (0-10)!")
            return

        if new_level < 0 or new_level > 10:
            await message.channel.send("❌ Level must be between 0 and 10!")
            return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))
        result = c.fetchone()
        old_level = result[0] if result else 0

        c.execute('UPDATE dragon_nest SET level = ? WHERE guild_id = ? AND user_id = ?',
                  (new_level, guild_id, user.id))

        if new_level > old_level:
            c.execute('SELECT COUNT(*) FROM user_perks WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            perk_count = c.fetchone()[0]

            c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user.id))
            upgrade_result = c.fetchone()
            upgrade_level = upgrade_result[0] if upgrade_result else 0

            perks_needed = new_level - perk_count
            for i in range(perks_needed):
                missing_level = perk_count + i + 1
                if missing_level <= new_level and missing_level <= 10:
                    c.execute('SELECT COUNT(*) FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = ?',
                              (guild_id, user.id, missing_level))
                    if c.fetchone()[0] == 0:
                        try:
                            new_perks = generate_unique_perks(missing_level, 3, upgrade_level)
                            c.execute('''INSERT INTO pending_perks (guild_id, user_id, level, perks_json)
                                         VALUES (?, ?, ?, ?)''',
                                      (guild_id, user.id, missing_level, json.dumps({'selected_perks': new_perks})))
                        except (ValueError, KeyError):
                            pass

        conn.commit()
        conn.close()

        level_name = LEVEL_NAMES.get(new_level, "Unknown")
        embed = discord.Embed(
            title="✅ Dragon Nest Level Set",
            description=f"**{user.mention}** Dragon Nest level has been updated!\n\n"
                        f"Old level: **{old_level}**\n"
                        f"New level: **{new_level}: {level_name}**\n\n"
                        f"✨ {new_level - old_level} perk(s) are waiting to be claimed!",
            color=discord.Color.green()
        )
        await message.channel.send(embed=embed)
        return


# ==================== SERVER CONFIG COMMAND ====================

class RaidTimesSelect(discord.ui.Select):
    def __init__(self, current_times: list):
        options = [
            discord.SelectOption(label=f"{h:02d}:00", value=str(h),
                                 default=(h in current_times))
            for h in range(0, 24)
        ]
        super().__init__(
            placeholder="Select raid spawn times (multi-select)",
            min_values=1,
            max_values=24,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        from database import update_server_config
        selected = sorted([int(v) for v in self.values])
        update_server_config(interaction.guild_id, 'raid_times', selected)
        hours_str = ', '.join(f'{h:02d}:00' for h in selected)
        await interaction.response.edit_message(
            embed=_build_config_embed(interaction.guild_id),
            view=ServerConfigView(interaction.guild_id),
        )


class BlackMarketIntervalModal(discord.ui.Modal, title="Black Market Settings"):
    interval = discord.ui.TextInput(
        label="Minimum interval (hours)", placeholder="e.g. 4", min_length=1, max_length=3
    )
    max_per_day = discord.ui.TextInput(
        label="Max spawns per day", placeholder="e.g. 6", min_length=1, max_length=2
    )

    def __init__(self, current_interval: int, current_max: int):
        super().__init__()
        self.interval.default = str(current_interval)
        self.max_per_day.default = str(current_max)

    async def on_submit(self, interaction: discord.Interaction):
        from database import update_server_config
        try:
            hours = max(1, min(72, int(self.interval.value)))
            max_d = max(1, min(24, int(self.max_per_day.value)))
        except ValueError:
            await interaction.response.send_message("❌ Please enter valid numbers.", ephemeral=True)
            return
        update_server_config(interaction.guild_id, 'blackmarket_interval_hours', hours)
        update_server_config(interaction.guild_id, 'blackmarket_max_per_day', max_d)
        await interaction.response.edit_message(
            embed=_build_config_embed(interaction.guild_id),
            view=ServerConfigView(interaction.guild_id),
        )


class ServerConfigView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        from database import get_server_config
        cfg = get_server_config(guild_id)
        self.add_item(RaidTimesSelect(cfg['raid_times']))

    @discord.ui.button(label="Toggle Raids", style=discord.ButtonStyle.primary, row=1)
    async def toggle_raids(self, interaction: discord.Interaction, button: discord.ui.Button):
        from database import get_server_config, update_server_config
        cfg = get_server_config(self.guild_id)
        new_val = 0 if cfg['raids_enabled'] else 1
        update_server_config(self.guild_id, 'raids_enabled', new_val)
        await interaction.response.edit_message(
            embed=_build_config_embed(self.guild_id),
            view=ServerConfigView(self.guild_id),
        )

    @discord.ui.button(label="Toggle Black Market", style=discord.ButtonStyle.primary, row=1)
    async def toggle_blackmarket(self, interaction: discord.Interaction, button: discord.ui.Button):
        from database import get_server_config, update_server_config
        cfg = get_server_config(self.guild_id)
        new_val = 0 if cfg['blackmarket_enabled'] else 1
        update_server_config(self.guild_id, 'blackmarket_enabled', new_val)
        await interaction.response.edit_message(
            embed=_build_config_embed(self.guild_id),
            view=ServerConfigView(self.guild_id),
        )

    @discord.ui.button(label="Black Market Interval", style=discord.ButtonStyle.secondary, row=2)
    async def bm_interval(self, interaction: discord.Interaction, button: discord.ui.Button):
        from database import get_server_config
        cfg = get_server_config(self.guild_id)
        await interaction.response.send_modal(
            BlackMarketIntervalModal(cfg['blackmarket_interval_hours'], cfg['blackmarket_max_per_day'])
        )


def _build_config_embed(guild_id: int) -> discord.Embed:
    from database import get_server_config
    cfg = get_server_config(guild_id)

    raids_status = "✅ Enabled" if cfg['raids_enabled'] else "❌ Disabled"
    bm_status = "✅ Enabled" if cfg['blackmarket_enabled'] else "❌ Disabled"
    raid_times_str = ', '.join(f'{h:02d}:00' for h in cfg['raid_times']) or '—'

    embed = discord.Embed(
        title="⚙️ Server Configuration",
        color=discord.Color.from_rgb(88, 101, 242),
    )
    embed.add_field(
        name="🗡️ Raid Bosses",
        value=f"Status: **{raids_status}**\nSpawn Times: **{raid_times_str}**",
        inline=False,
    )
    embed.add_field(
        name="🏴‍☠️ Black Market",
        value=(f"Status: **{bm_status}**\n"
               f"Min. Interval: **{cfg['blackmarket_interval_hours']}h**\n"
               f"Max. per Day: **{cfg['blackmarket_max_per_day']}x**"),
        inline=False,
    )
    embed.set_footer(text="Raids and Black Market are disabled by default.")
    return embed


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
