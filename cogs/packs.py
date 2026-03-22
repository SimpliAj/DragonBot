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
from database import is_player_softlocked, update_balance
from utils import *
from achievements import send_quest_notification


class PacksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="openpacks", description="Open your packs to get dragons")
    async def openpacks(self, interaction: discord.Interaction):
        """Open packs with 30% chance to upgrade to next tier"""

        # Check if player is softlocked
        is_softlocked, upgrade_level = is_player_softlocked(interaction.guild_id, interaction.user.id)
        if is_softlocked:
            next_upgrade_level = upgrade_level + 1
            upgrade_cost = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('cost', 0)
            softlock_embed = discord.Embed(
                title="🔒 Dragon Nest Upgrade Required!",
                description=f"You have enough coins to upgrade your Dragon Nest!\n\n"
                            f"**Current Level:** {upgrade_level}\n"
                            f"**Upgrade Cost:** {upgrade_cost:,} 🪙\n\n"
                            f"You're **softlocked** from opening packs until you upgrade.\n"
                            f"Use `/dragonnest` to upgrade!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=softlock_embed, delete_after=5)
            return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('SELECT pack_type, count FROM user_packs WHERE guild_id = ? AND user_id = ? AND count > 0',
                  (interaction.guild_id, interaction.user.id))
        packs = c.fetchall()
        conn.close()

        if not packs:
            await interaction.response.send_message("📦 You don't have any packs to open!", ephemeral=False)
            return

        # Filter to only include packs with count > 0
        packs = [(pack_type, count) for pack_type, count in packs if count > 0]

        # Create pack opening buttons
        class OpenPackView(discord.ui.View):
            def __init__(self, guild_id, user_id, available_packs=None):
                super().__init__(timeout=180)
                self.guild_id = guild_id
                self.user_id = user_id

                # Use provided packs list or fetch from database
                if available_packs is None:
                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('SELECT pack_type, count FROM user_packs WHERE guild_id = ? AND user_id = ? AND count > 0',
                              (guild_id, user_id))
                    available_packs = c.fetchall()
                    conn.close()

                # Add button for each pack type user has
                for pack_type, count in available_packs:
                    pack_data = PACK_TYPES.get(pack_type)
                    if pack_data and count > 0:
                        button = discord.ui.Button(
                            label=f"{pack_data['name']} (x{count})",
                            emoji=pack_data['emoji'],
                            style=discord.ButtonStyle.primary,
                            custom_id=f"open_{pack_type}"
                        )
                        button.callback = self.create_callback(pack_type)
                        self.add_item(button)

                # Add bulk open button if user has multiple packs
                total_packs = sum(count for _, count in available_packs)
                if total_packs >= 5:
                    bulk_button = discord.ui.Button(
                        label="Bulk Open",
                        emoji="📦",
                        style=discord.ButtonStyle.green,
                        custom_id="bulk_open"
                    )
                    bulk_button.callback = self.bulk_open_callback
                    self.add_item(bulk_button)

            async def bulk_open_callback(self, interaction: discord.Interaction):
                """Handle bulk opening packs"""
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ This is not your pack menu!", ephemeral=False)
                    return

                # Get available packs
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('SELECT pack_type, count FROM user_packs WHERE guild_id = ? AND user_id = ? AND count > 0',
                          (self.guild_id, self.user_id))
                available_packs = c.fetchall()
                conn.close()

                if not available_packs:
                    await interaction.response.send_message("❌ You don't have any packs!", ephemeral=False)
                    return

                # Create select menu for pack type and amount
                class BulkOpenView(discord.ui.View):
                    def __init__(self, guild_id, user_id, packs):
                        super().__init__(timeout=60)
                        self.guild_id = guild_id
                        self.user_id = user_id
                        self.packs = packs

                        # Pack type select
                        options = []
                        for pack_type, count in packs:
                            pack_data = PACK_TYPES.get(pack_type)
                            if pack_data:
                                options.append(
                                    discord.SelectOption(
                                        label=f"{pack_data['name']} (x{count})",
                                        emoji=pack_data['emoji'],
                                        value=pack_type,
                                        description=f"Open multiple {pack_data['name']}s"
                                    )
                                )

                        class PackSelect(discord.ui.Select):
                            def __init__(inner_self):
                                super().__init__(
                                    placeholder="Select pack type to bulk open...",
                                    options=options
                                )

                            async def callback(inner_self, interaction: discord.Interaction):
                                await interaction.response.defer()
                                pack_type = inner_self.values[0] if inner_self.values else None
                                if not pack_type:
                                    await interaction.followup.send("❌ Please select a pack!", ephemeral=True)
                                    return

                                # Get count for this pack
                                pack_count = next((count for pt, count in self.packs if pt == pack_type), 0)
                                pack_data = PACK_TYPES[pack_type]

                                # Create amount select (5, 10, 25, 50, or max)
                                amount_options = []
                                for amount in [5, 10, 25, 50]:
                                    if amount <= pack_count:
                                        amount_options.append(
                                            discord.SelectOption(
                                                label=f"Open {amount}x",
                                                value=str(amount)
                                            )
                                        )
                                if pack_count not in [5, 10, 25, 50]:
                                    amount_options.append(
                                        discord.SelectOption(
                                            label=f"Open All ({pack_count}x)",
                                            value=str(pack_count)
                                        )
                                    )

                                class AmountSelect(discord.ui.Select):
                                    def __init__(inner_self2):
                                        super().__init__(
                                            placeholder=f"How many {pack_data['name']}s?",
                                            options=amount_options
                                        )

                                    async def callback(inner_self2, interaction2: discord.Interaction):
                                        await interaction2.response.defer()
                                        try:
                                            amount = int(inner_self2.values[0] if inner_self2.values else 0)
                                        except (ValueError, IndexError):
                                            await interaction2.followup.send("❌ Please select a valid amount!", ephemeral=True)
                                            return

                                        # Process bulk opening
                                        await interaction2.followup.send(
                                            f"📦 Opening {amount}x {pack_data['emoji']} {pack_data['name']}...",
                                            ephemeral=False
                                        )

                                        # Open all packs at once (no animation)
                                        total_dragons = {}
                                        total_coins = 0
                                        total_luckycharms = 0
                                        total_dragonscales = 0
                                        total_upgrades = 0

                                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                        c = conn.cursor()

                                        # Get pack tier for rarity-based drop chances
                                        pack_tier_idx = PACK_UPGRADE_ORDER.index(pack_type)
                                        # Determine drop chances based on pack rarity
                                        if pack_tier_idx <= 1:  # Wooden, Stone
                                            lucky_charm_chance = 0.01  # 1%
                                            dragonscale_chance = 0.0001  # 0.01%
                                        elif pack_tier_idx <= 3:  # Bronze, Silver
                                            lucky_charm_chance = 0.02  # 2%
                                            dragonscale_chance = 0.0002  # 0.02%
                                        elif pack_tier_idx <= 5:  # Gold, Platinum
                                            lucky_charm_chance = 0.03  # 3%
                                            dragonscale_chance = 0.0005  # 0.05%
                                        else:  # Diamond, Celestial
                                            lucky_charm_chance = 0.05  # 5%
                                            dragonscale_chance = 0.001  # 0.1%

                                        for i in range(amount):
                                            # Deduct pack
                                            c.execute('UPDATE user_packs SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                                                      (self.guild_id, self.user_id, pack_type))

                                            # Check for upgrade
                                            current_pack = pack_type
                                            while current_pack != 'celestial':
                                                if random.random() < 0.30:
                                                    current_index = PACK_UPGRADE_ORDER.index(current_pack)
                                                    current_pack = PACK_UPGRADE_ORDER[current_index + 1]
                                                    total_upgrades += 1
                                                else:
                                                    break

                                            # Get dragons from pack
                                            # Use weighted selection based on pack tier
                                            pack_tier_index = PACK_UPGRADE_ORDER.index(current_pack)

                                            # Build weights for dragons
                                            dragon_weights = []
                                            for dragon_key_option in DRAGON_TYPES.keys():
                                                dragon_spawn_chance = DRAGON_TYPES[dragon_key_option]['spawn_chance']
                                                inverse_chance = 1.0 / (dragon_spawn_chance + 0.001)

                                                # Get dragon rarity
                                                dragon_rarity = None
                                                for rarity, dragons in DRAGON_RARITY_TIERS.items():
                                                    if dragon_key_option in dragons:
                                                        dragon_rarity = rarity
                                                        break

                                                # Weight based on pack tier
                                                if pack_tier_index <= 1:
                                                    weight = dragon_spawn_chance ** 0.3 if dragon_rarity == 'common' else 0.0
                                                elif pack_tier_index == 2:
                                                    weight = dragon_spawn_chance ** 0.4 if dragon_rarity in ['common', 'uncommon'] else 0.0
                                                elif pack_tier_index <= 4:
                                                    if dragon_rarity == 'common':
                                                        weight = 0.0
                                                    elif dragon_rarity in ['uncommon', 'rare']:
                                                        weight = inverse_chance ** 0.2
                                                    elif dragon_rarity == 'epic':
                                                        weight = inverse_chance ** 0.1
                                                    else:
                                                        weight = 0.0
                                                elif pack_tier_index <= 6:
                                                    if dragon_rarity in ['common', 'uncommon']:
                                                        weight = 0.0
                                                    elif dragon_rarity == 'rare':
                                                        weight = inverse_chance ** 0.2
                                                    elif dragon_rarity in ['epic', 'legendary']:
                                                        weight = inverse_chance ** 0.5
                                                    else:
                                                        weight = inverse_chance ** 0.3
                                                else:
                                                    weight = 0.0 if dragon_rarity in ['common', 'uncommon', 'rare', 'epic'] else inverse_chance ** 0.6
                                                dragon_weights.append(weight)

                                            dragon_key = random.choices(list(DRAGON_TYPES.keys()), weights=dragon_weights)[0]

                                            # Check for lucky charm/dragonscale bonus
                                            if random.random() < lucky_charm_chance:
                                                total_luckycharms += 1
                                            if random.random() < dragonscale_chance:
                                                total_dragonscales += 1

                                            # Check for coin bonus
                                            if random.random() < 0.02:  # 2% chance
                                                bonus_coins = random.randint(100, 1000)
                                                total_coins += bonus_coins

                                            # Add dragon directly to database
                                            c.execute('''INSERT INTO user_dragons (guild_id, user_id, dragon_type, count, last_caught_at)
                                                         VALUES (?, ?, ?, 1, ?)
                                                         ON CONFLICT(guild_id, user_id, dragon_type)
                                                         DO UPDATE SET count = count + 1, last_caught_at = ?''',
                                                      (self.guild_id, self.user_id, dragon_key, int(time.time()), int(time.time())))
                                            if dragon_key not in total_dragons:
                                                total_dragons[dragon_key] = 0
                                            total_dragons[dragon_key] += 1

                                        # Apply bonuses
                                        if total_coins > 0:
                                            c.execute('UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
                                                      (total_coins, self.guild_id, self.user_id))
                                        if total_luckycharms > 0:
                                            c.execute('''INSERT INTO user_luckycharms (guild_id, user_id, count)
                                                         VALUES (?, ?, ?)
                                                         ON CONFLICT(guild_id, user_id)
                                                         DO UPDATE SET count = count + ?''',
                                                      (self.guild_id, self.user_id, total_luckycharms, total_luckycharms))

                                        conn.commit()
                                        conn.close()

                                        # Build result message
                                        result_text = f"🎉 **Opened {amount}x {pack_data['emoji']} {pack_data['name']}!**\n\n"
                                        result_text += f"**Dragons obtained:**\n"
                                        for dragon_key, count in sorted(total_dragons.items()):
                                            dragon_info = DRAGON_TYPES[dragon_key]
                                            result_text += f"{dragon_info['emoji']} {dragon_info['name']}: **x{count}**\n"

                                        if total_upgrades > 0:
                                            result_text += f"\n⭐ **{total_upgrades}** pack upgrades!\n"
                                        if total_coins > 0:
                                            result_text += f"💰 **+{total_coins:,}** bonus coins!\n"
                                        if total_luckycharms > 0:
                                            result_text += f"🍀 **+{total_luckycharms}** lucky charms!\n"
                                        if total_dragonscales > 0:
                                            result_text += f"<:dragonscale:1446278170998341693> **+{total_dragonscales}** dragonscales!\n"

                                        result_embed = discord.Embed(
                                            title="📦 Bulk Open Results",
                                            description=result_text,
                                            color=discord.Color.gold()
                                        )
                                        await interaction2.followup.send(embed=result_embed, ephemeral=False)

                                # Show amount select
                                amount_view = discord.ui.View(timeout=60)
                                amount_view.add_item(AmountSelect())
                                await interaction.followup.send("How many packs would you like to open?", view=amount_view, ephemeral=False)

                        self.add_item(PackSelect())

                view = BulkOpenView(self.guild_id, self.user_id, available_packs)
                await interaction.response.send_message("Select pack type for bulk opening:", view=view, ephemeral=False)

            def create_callback(self, pack_type_param):
                async def callback(interaction: discord.Interaction):
                    pack_type = pack_type_param  # Capture the parameter
                    if interaction.user.id != self.user_id:
                        await interaction.response.send_message("❌ This is not your pack menu!", ephemeral=False)
                        return

                    # Check if user still has pack
                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('SELECT count FROM user_packs WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                              (self.guild_id, self.user_id, pack_type))
                    result = c.fetchone()

                    if not result or result[0] <= 0:
                        await interaction.response.send_message("❌ You don't have this pack anymore!", ephemeral=False)
                        conn.close()
                        return

                    # Deduct pack
                    c.execute('UPDATE user_packs SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                              (self.guild_id, self.user_id, pack_type))
                    conn.commit()

                    pack_data = PACK_TYPES[pack_type]

                    # Animation stages
                    stages = [
                        ("📦 Opening pack...", f"{pack_data['emoji']} **{pack_data['name']}**\n\n🔒 Locked"),
                        ("📦 Opening pack...", f"{pack_data['emoji']} **{pack_data['name']}**\n\n🔓 Unlocking..."),
                        ("📦 Opening pack...", f"{pack_data['emoji']} **{pack_data['name']}**\n\n🎉 Opening...")
                    ]

                    # Start animation
                    embed = discord.Embed(
                        title=stages[0][0],
                        description=stages[0][1],
                        color=discord.Color.blue()
                    )
                    await interaction.response.send_message(embed=embed)

                    # Animate through stages
                    for i in range(1, len(stages)):
                        await asyncio.sleep(0.8)
                        embed.title = stages[i][0]
                        embed.description = stages[i][1]
                        await interaction.edit_original_response(embed=embed)

                    await asyncio.sleep(0.5)

                    # 0.5% chance to get dragonscales (1-3 minutes)
                    dragonscale_dropped = False
                    dragonscale_minutes = 0
                    if random.random() < 0.005:  # 0.5% chance
                        dragonscale_minutes = random.randint(1, 3)
                        dragonscale_dropped = True
                        c.execute('''INSERT INTO dragonscales (guild_id, user_id, minutes)
                                     VALUES (?, ?, ?)
                                     ON CONFLICT(guild_id, user_id)
                                     DO UPDATE SET minutes = minutes + ?''',
                                  (self.guild_id, self.user_id, dragonscale_minutes, dragonscale_minutes))
                        conn.commit()

                    # 30% upgrade chance loop
                    current_pack = pack_type
                    upgrades = []
                    while current_pack != 'celestial':
                        if random.random() < 0.30:  # 30% chance
                            current_index = PACK_UPGRADE_ORDER.index(current_pack)
                            current_pack = PACK_UPGRADE_ORDER[current_index + 1]
                            upgrades.append(current_pack)
                        else:
                            break

                    # Show upgrade animation if upgraded
                    if upgrades:
                        upgrade_text = f"{pack_data['emoji']} **{pack_data['name']}**\n\n"
                        for upgrade in upgrades:
                            upgrade_data = PACK_TYPES[upgrade]
                            upgrade_text += f"⬆️ Upgraded to {upgrade_data['emoji']} **{upgrade_data['name']}**!\n"

                        embed.title = "✨ Pack Upgraded!"
                        embed.description = upgrade_text
                        embed.color = discord.Color.gold()
                        await interaction.edit_original_response(embed=embed)
                        await asyncio.sleep(1.5)

                    # 0.025% chance to get dragonscales (1-3 minutes)
                    dragonscale_dropped = False
                    dragonscale_minutes = 0
                    if random.random() < 0.00025:  # 0.025% chance
                        dragonscale_minutes = random.randint(1, 3)
                        dragonscale_dropped = True
                        c.execute('''INSERT INTO dragonscales (guild_id, user_id, minutes)
                                     VALUES (?, ?, ?)
                                     ON CONFLICT(guild_id, user_id)
                                     DO UPDATE SET minutes = minutes + ?''',
                                  (self.guild_id, self.user_id, dragonscale_minutes, dragonscale_minutes))
                        conn.commit()

                    # Get final pack value
                    final_pack_data = PACK_TYPES[current_pack]
                    pack_config = PACK_BASE_VALUES[current_pack]
                    base_value = pack_config['base_value']
                    coin_base = pack_config['coin_base']
                    coin_variance = pack_config['coin_variance']

                    # Variable coin reward: base ± variance
                    variance_amount = coin_base * coin_variance
                    coin_value = coin_base + random.uniform(-variance_amount, variance_amount)
                    coin_value = int(coin_value)

                    # Get 2-3 dragons with HIGH RARITY PRIORITY (not filling with cheap dragons)
                    pack_tier_index = PACK_UPGRADE_ORDER.index(current_pack)
                    dragons_received = {}
                    value_filled = 0
                    dragons_count = 0
                    max_dragons_types = 3  # Max 3 different dragon types per pack

                    # Pre-calculate dragon weights once
                    dragon_weights = []
                    for dragon_key_option in DRAGON_TYPES.keys():
                        dragon_spawn_chance = DRAGON_TYPES[dragon_key_option]['spawn_chance']
                        inverse_chance = 1.0 / (dragon_spawn_chance + 0.001)

                        # Get dragon rarity tier
                        dragon_rarity = None
                        for rarity, dragons in DRAGON_RARITY_TIERS.items():
                            if dragon_key_option in dragons:
                                dragon_rarity = rarity
                                break

                        # Assign weight based on pack tier and dragon rarity
                        if pack_tier_index <= 1:  # Wooden, Stone - ONLY COMMON
                            if dragon_rarity in ['common']:
                                weight = dragon_spawn_chance ** 0.3  # Heavily favor common
                            else:
                                weight = 0.0  # Block everything else
                        elif pack_tier_index == 2:  # Bronze - COMMON + UNCOMMON
                            if dragon_rarity in ['common', 'uncommon']:
                                weight = dragon_spawn_chance ** 0.4
                            else:
                                weight = 0.0  # Block rare+
                        elif pack_tier_index <= 4:  # Silver, Gold - NO COMMON, focus UNCOMMON/RARE/EPIC
                            if dragon_rarity in ['common']:
                                weight = 0.0  # BLOCK all baby dragons
                            elif dragon_rarity in ['uncommon', 'rare']:
                                weight = inverse_chance ** 0.2
                            elif dragon_rarity == 'epic':
                                weight = inverse_chance ** 0.1
                            else:
                                weight = 0.0
                        elif pack_tier_index <= 6:  # Platinum, Diamond - NO COMMON/UNCOMMON, focus RARE/EPIC/LEGENDARY
                            if dragon_rarity in ['common', 'uncommon']:
                                weight = 0.0  # BLOCK baby dragons and uncommon
                            elif dragon_rarity in ['rare']:
                                weight = inverse_chance ** 0.2
                            elif dragon_rarity in ['epic', 'legendary']:
                                weight = inverse_chance ** 0.5
                            else:
                                weight = inverse_chance ** 0.3
                        else:  # Celestial - ONLY LEGENDARY/MYTHIC/ULTRA
                            if dragon_rarity in ['common', 'uncommon', 'rare', 'epic']:
                                weight = 0.0  # BLOCK all common dragons
                            else:  # legendary, mythic, ultra
                                weight = inverse_chance ** 0.6

                        dragon_weights.append(weight)

                    dragon_keys_list = list(DRAGON_TYPES.keys())

                    # Get dragons: prioritize high rarity, limit to 3 types, stop at base_value
                    while value_filled < base_value and len(dragons_received) < max_dragons_types:
                        dragon_key = random.choices(dragon_keys_list, weights=dragon_weights)[0]
                        dragon_data = DRAGON_TYPES[dragon_key]

                        if dragon_key not in dragons_received:
                            dragons_received[dragon_key] = 0
                        dragons_received[dragon_key] += 1
                        value_filled += dragon_data['value']

                    # For display, show the rarest dragon received
                    rarest_dragon_key = None
                    rarest_rarity_idx = -1
                    rarity_order = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra']

                    for dragon_key in dragons_received.keys():
                        for rarity, dragons in DRAGON_RARITY_TIERS.items():
                            if dragon_key in dragons:
                                rarity_idx = rarity_order.index(rarity) if rarity in rarity_order else -1
                                if rarity_idx > rarest_rarity_idx:
                                    rarest_rarity_idx = rarity_idx
                                    rarest_dragon_key = dragon_key
                                break

                    dragon_key = rarest_dragon_key if rarest_dragon_key else list(dragons_received.keys())[0]
                    dragon_data = DRAGON_TYPES[dragon_key]
                    final_amount = dragons_received[dragon_key]  # Only show count of THIS dragon, not total
                    total_dragons_count = sum(dragons_received.values())
                    guaranteed = 1

                    # Special cutscene for rare dragon from common pack (<1 guaranteed)
                    if guaranteed < 1:
                        embed.title = "✨ Something special..."
                        embed.description = f"{final_pack_data['emoji']} **{final_pack_data['name']}**\n\n✨ ✨ ✨\n*A rare energy emanates from the pack...*"
                        embed.color = discord.Color.purple()
                        await interaction.edit_original_response(embed=embed)
                        await asyncio.sleep(2.0)

                    # Add dragons to user
                    for drag_key, drag_amount in dragons_received.items():
                        await add_dragons(self.guild_id, self.user_id, drag_key, drag_amount)

                    # Update Dragon Nest bounties if active
                    nest_conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    nest_c = nest_conn.cursor()
                    nest_active_check = nest_c.execute('SELECT active_until FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                                                        (self.guild_id, self.user_id)).fetchone()
                    if nest_active_check and nest_active_check[0] > int(time.time()):
                        bounties_result = nest_c.execute('SELECT bounties_active FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                                           (self.guild_id, self.user_id)).fetchone()
                        if bounties_result and bounties_result[0]:
                            import ast
                            pack_bounties = ast.literal_eval(bounties_result[0])
                            # Get dragon rarity level
                            dragon_rarity_level_pack = 0
                            for idx, dragon_key_check in enumerate(DRAGON_TYPES.keys()):
                                if dragon_key_check == dragon_key:
                                    if idx >= 5: dragon_rarity_level_pack = 1  # Uncommon+
                                    if idx >= 9: dragon_rarity_level_pack = 2  # Rare+
                                    if idx >= 14: dragon_rarity_level_pack = 3  # Epic+
                                    if idx >= 18: dragon_rarity_level_pack = 4  # Legendary+
                                    if idx >= 20: dragon_rarity_level_pack = 5  # Mythic+
                                    break

                            # Update bounties
                            for bounty in pack_bounties:
                                if bounty['type'] == 'catch_any':
                                    bounty['progress'] = min(bounty['progress'] + final_amount, bounty['target'])
                                elif bounty['type'] == 'catch_rarity_or_higher' and bounty.get('rarity_level'):
                                    if dragon_rarity_level_pack >= bounty['rarity_level']:
                                        bounty['progress'] = min(bounty['progress'] + final_amount, bounty['target'])

                            # Save updated bounties
                            nest_c.execute('UPDATE dragon_nest SET bounties_active = ? WHERE guild_id = ? AND user_id = ?',
                                          (str(pack_bounties), self.guild_id, self.user_id))
                            nest_conn.commit()
                    nest_conn.close()

                    # Determine drop chances based on pack rarity (tier index)
                    pack_tier_idx = PACK_UPGRADE_ORDER.index(current_pack)  # Current pack after potential upgrades
                    if pack_tier_idx <= 1:  # Wooden, Stone
                        lucky_charm_chance = 0.01  # 1%
                        dragonscale_chance = 0.0001  # 0.01%
                    elif pack_tier_idx <= 3:  # Bronze, Silver
                        lucky_charm_chance = 0.02  # 2%
                        dragonscale_chance = 0.0002  # 0.02%
                    elif pack_tier_idx <= 5:  # Gold, Platinum
                        lucky_charm_chance = 0.03  # 3%
                        dragonscale_chance = 0.0005  # 0.05%
                    else:  # Diamond, Celestial
                        lucky_charm_chance = 0.05  # 5%
                        dragonscale_chance = 0.001  # 0.1%

                    # Lucky Charm drop (rarity-based)
                    luckycharm_dropped = False
                    if random.random() < lucky_charm_chance:
                        luckycharm_dropped = True
                        conn_charm = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c_charm = conn_charm.cursor()
                        c_charm.execute('''INSERT INTO user_luckycharms (guild_id, user_id, count)
                                           VALUES (?, ?, 1)
                                           ON CONFLICT(guild_id, user_id)
                                           DO UPDATE SET count = count + 1''',
                                        (self.guild_id, self.user_id))
                        conn_charm.commit()
                        conn_charm.close()

                    # Dragonscale drop (rarity-based)
                    dragonscale_dropped = False
                    dragonscale_minutes = 0
                    if random.random() < dragonscale_chance:
                        dragonscale_minutes = random.randint(1, 3)
                        dragonscale_dropped = True
                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()
                        c.execute('''INSERT INTO dragonscales (guild_id, user_id, minutes)
                                     VALUES (?, ?, ?)
                                     ON CONFLICT(guild_id, user_id)
                                     DO UPDATE SET minutes = minutes + ?''',
                                  (self.guild_id, self.user_id, dragonscale_minutes, dragonscale_minutes))
                        conn.commit()
                        conn.close()

                    # Calculate coin value (variable reward)
                    await asyncio.to_thread(update_balance, self.guild_id, self.user_id, coin_value)

                    # Build bonus text with drop rates shown
                    # Map pack index to correct pack tier name
                    pack_names_by_tier = {
                        0: 'Wooden', 1: 'Stone', 2: 'Bronze', 3: 'Silver',
                        4: 'Gold', 5: 'Platinum', 6: 'Diamond', 7: 'Celestial'
                    }
                    pack_tier_name = pack_names_by_tier.get(pack_tier_idx, 'Unknown')
                    bonus_text = ""

                    if luckycharm_dropped:
                        bonus_text = "\n🍀 **+1 Lucky Charm!**"
                    if dragonscale_dropped:
                        bonus_text = f"\n⚡ **+{dragonscale_minutes} Dragonscale Minutes!**" + bonus_text

                    # Build reward text showing all dragons
                    reward_text = "**Reward:**\n"
                    for drag_key, drag_count in sorted(dragons_received.items(), key=lambda x: -DRAGON_TYPES[x[0]]['value']):
                        drag_data = DRAGON_TYPES[drag_key]
                        reward_text += f"{drag_data['emoji']} **{drag_count}x {drag_data['name']}**\n"
                    reward_text += f"💰 **{int(coin_value)} 🪙**"

                    # Final result
                    final_embed = discord.Embed(
                        title="🎁 Pack Opened!",
                        description=f"{final_pack_data['emoji']} **{final_pack_data['name']}**\n\n"
                                    f"{reward_text}{bonus_text}\n\n"
                                    f"*Added to your collection!*",
                        color=discord.Color.gold()
                    )

                    if upgrades:
                        final_embed.set_footer(text=f"Upgraded {len(upgrades)} time(s)! 🎉")

                    await interaction.edit_original_response(embed=final_embed)

                    # Track for dragonpass quest
                    _qr = await asyncio.to_thread(check_dragonpass_quests, self.guild_id, self.user_id, 'open_pack', 1)
                    if _qr and _qr[3]:
                        await send_quest_notification(interaction.client, self.guild_id, self.user_id, _qr[3])

                    # Update the original pack list message
                    await asyncio.sleep(2)

                    # Fetch updated pack counts
                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('SELECT pack_type, count FROM user_packs WHERE guild_id = ? AND user_id = ? AND count > 0',
                              (self.guild_id, self.user_id))
                    updated_packs = c.fetchall()
                    conn.close()

                    # Create updated embed
                    if not updated_packs:
                        updated_embed = discord.Embed(
                            title="📦 Your Packs",
                            description="✅ All packs opened! You don't have any packs left.",
                            color=discord.Color.green()
                        )
                        # Remove all buttons
                        await interaction.message.edit(embed=updated_embed, view=None)
                    else:
                        updated_embed = discord.Embed(
                            title="📦 Your Packs",
                            description="Click a button to open a pack!",
                            color=discord.Color.blue()
                        )

                        for pack_type, count in updated_packs:
                            pack_data = PACK_TYPES.get(pack_type)
                            if pack_data:
                                updated_embed.add_field(
                                    name=f"{pack_data['emoji']} {pack_data['name']}",
                                    value=f"Count: {count}",
                                    inline=True
                                )

                        # Create new view with updated buttons
                        new_view = OpenPackView(self.guild_id, self.user_id, updated_packs)
                        await interaction.message.edit(embed=updated_embed, view=new_view)

                return callback

        # Create embed showing available packs
        embed = discord.Embed(
            title="📦 Your Packs",
            description="Click a button to open a pack!",
            color=discord.Color.blue()
        )

        for pack_type, count in packs:
            pack_data = PACK_TYPES.get(pack_type)
            if pack_data:
                embed.add_field(
                    name=f"{pack_data['emoji']} {pack_data['name']}",
                    value=f"Count: {count}",
                    inline=True
                )

        view = OpenPackView(interaction.guild_id, interaction.user.id, packs)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="alphadragons", description="View and craft Alpha Dragons")
    async def alphadragons(self, interaction: discord.Interaction):
        """Alpha Dragon system (like Prisms)"""
        await interaction.response.defer(ephemeral=False)
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Count total server alphas
        c.execute('''SELECT COUNT(*) FROM user_alphas
                     WHERE guild_id = ?''',
                  (interaction.guild_id,))
        total_server_alphas = c.fetchone()[0]

        # Get first alpha creator info
        c.execute('''SELECT user_id, name, created_at FROM user_alphas
                     WHERE guild_id = ?
                     ORDER BY created_at ASC LIMIT 1''',
                  (interaction.guild_id,))
        first_alpha = c.fetchone()

        # Count user's alpha dragons
        c.execute('''SELECT COUNT(*) FROM user_alphas
                     WHERE guild_id = ? AND user_id = ?''',
                  (interaction.guild_id, interaction.user.id))
        user_alpha_count = c.fetchone()[0]

        # Get all user's alpha dragons
        c.execute('''SELECT name, catch_boost, created_at FROM user_alphas
                     WHERE guild_id = ? AND user_id = ?
                     ORDER BY created_at ASC''',
                  (interaction.guild_id, interaction.user.id))
        user_alphas = c.fetchall()

        # Check if user has all 22 dragon types
        c.execute('''SELECT dragon_type, SUM(count) as total FROM user_dragons
                     WHERE guild_id = ? AND user_id = ?
                     GROUP BY dragon_type
                     HAVING total > 0''',
                  (interaction.guild_id, interaction.user.id))
        raw_dragons = c.fetchall()

        # Filter out invalid dragon types
        user_dragons = {}
        for dragon_type, count in raw_dragons:
            if dragon_type in DRAGON_TYPES:
                user_dragons[dragon_type] = count

        # Get all unique Alpha owners (before closing connection)
        c.execute('''SELECT DISTINCT user_id FROM user_alphas WHERE guild_id = ? ORDER BY created_at ASC''', (interaction.guild_id,))
        all_owner_ids = [row[0] for row in c.fetchall()]

        conn.close()

        has_all_types = len(user_dragons) == 22 and all(count > 0 for count in user_dragons.values())

        # Calculate boosts
        # Catch boost (logarithmic): 6% * log(2 * count + 1)
        server_catch_boost = 0.06 * math.log(2 * total_server_alphas + 1) * 100 if total_server_alphas > 0 else 0
        user_catch_boost = 0.06 * math.log(2 * user_alpha_count + 1) * 100 if user_alpha_count > 0 else 0
        personal_catch_boost = server_catch_boost + user_catch_boost

        # Coin boost (linear): 2% per Alpha for server, +2% per own Alpha for owner
        server_coin_boost = total_server_alphas * 2.0  # +2% per server Alpha
        user_coin_boost = user_alpha_count * 2.0  # +2% additional per own Alpha
        personal_coin_boost = server_coin_boost + user_coin_boost

        # Build embed
        embed = discord.Embed(
            title="✨ Alpha Dragons",
            description="Alpha Dragons are a tradeable power-up with two powerful benefits:\n"
                        "• **Catch Boost:** Increased chance to catch extra dragons (logarithmic)\n"
                        "• **Coin Boost:** +2% coins per Alpha for everyone, +2% extra for owner\n\n"
                        "Each Alpha gives the entire server a boost, plus additional benefits for the owner.",
            color=0xFEE75C
        )

        # Alpha owner info - show all unique owners
        if first_alpha:
            # Format owner list (using all_owner_ids fetched earlier)
            owner_mentions = []
            for owner_id in all_owner_ids[:5]:  # Show up to 5 owners
                member = interaction.guild.get_member(owner_id)
                if member:
                    owner_mentions.append(member.mention)

            if len(all_owner_ids) > 5:
                owner_text = ", ".join(owner_mentions) + f" *...and {len(all_owner_ids) - 5} more*"
            else:
                owner_text = ", ".join(owner_mentions) if owner_mentions else "Unknown"

            alpha_info = f"✨ **Alpha Owners:** {owner_text}\n\n"
            server_coin_boost = total_server_alphas * 2  # +2% per Alpha
            personal_coin_boost = server_coin_boost + (user_alpha_count * 2)  # +2% additional per personal Alpha
            alpha_info += f"**{total_server_alphas}** Total Alphas | Catch: **{server_catch_boost:.1f}%** | Coins: **+{server_coin_boost}%**\n\n"
            alpha_info += f"**{interaction.user.display_name}'s alphas** | Owned: **{user_alpha_count}**\n"
            alpha_info += f"Catch boost: **{personal_catch_boost:.1f}%** | Coin boost: **+{personal_coin_boost}%**"
        else:
            alpha_info = f"No Alpha Dragons have been crafted yet!\n\n"
            alpha_info += f"Be the first to craft one by collecting all 22 dragon types.\n\n"
            alpha_info += f"**{interaction.user.display_name}'s progress:** {len(user_dragons)}/22 types collected"

        embed.add_field(name="", value=alpha_info, inline=False)

        # Show user's alphas if they have any
        if user_alphas:
            alpha_list = "\n".join([f"✨ **{name}** (crafted {discord.utils.format_dt(datetime.fromtimestamp(created_at), style='R')})"
                                    for name, _, created_at in user_alphas[:5]])
            if len(user_alphas) > 5:
                alpha_list += f"\n*... and {len(user_alphas) - 5} more*"
            embed.add_field(
                name="Your Alpha Dragons",
                value=alpha_list,
                inline=False
            )

        # Show missing types or ready to craft
        if has_all_types:
            embed.add_field(
                name="✅ Ready to Craft!",
                value="Click the button below to craft an Alpha Dragon!\n"
                      "*Costs 1 of each dragon type (22 total)*",
                inline=False
            )
        else:
            missing_types = []
            for dragon_type in DRAGON_TYPES.keys():
                if dragon_type not in user_dragons or user_dragons[dragon_type] <= 0:
                    missing_types.append(DRAGON_TYPES[dragon_type]['name'])

            missing_count = len(missing_types)
            missing_text = f"**Missing {missing_count} types:**\n"

            if missing_count <= 10:
                missing_text += ", ".join(missing_types)
            else:
                missing_text += ", ".join(missing_types[:10])
                missing_text += f"\n*...and {missing_count - 10} more*"

            embed.add_field(
                name="❌ Not Ready",
                value=missing_text,
                inline=False
            )

        embed.set_footer(text="Alpha Dragons use NATO phonetic names: Alpha, Bravo, Charlie, Delta...")

        # Create craft button view
        class AlphaDragonView(discord.ui.View):
            def __init__(self, can_craft: bool):
                super().__init__(timeout=180)
                if can_craft:
                    craft_button = discord.ui.Button(
                        label="Craft Alpha Dragon",
                        style=discord.ButtonStyle.green,
                        emoji="🌟",
                        custom_id="craft_alpha"
                    )
                    craft_button.callback = self.craft_alpha
                    self.add_item(craft_button)

            async def craft_alpha(self, interaction: discord.Interaction):
                """Craft an Alpha Dragon"""
                try:
                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()

                    # Re-check if user still has all types - must have at least 1 of EACH dragon type
                    required_types = set(DRAGON_TYPES.keys())

                    # First, check what dragons the user actually has
                    c.execute('''SELECT dragon_type, count FROM user_dragons
                                 WHERE guild_id = ? AND user_id = ? AND count > 0''',
                              (interaction.guild_id, interaction.user.id))
                    user_dragon_data = c.fetchall()
                    user_dragon_types = set(row[0] for row in user_dragon_data if row[1] > 0)

                    # Debug: log what we found
                    print(f"[CRAFT_ALPHA] User {interaction.user.id}: Found {len(user_dragon_types)} types, has {len(user_dragon_data)} rows")
                    print(f"[CRAFT_ALPHA] Required: {len(required_types)}, User has: {len(user_dragon_types)}")

                    # Check for invalid dragon types (not in DRAGON_TYPES) and delete them
                    invalid_types = user_dragon_types - required_types
                    if invalid_types:
                        print(f"[CRAFT_ALPHA] Found invalid types, deleting: {invalid_types}")
                        for invalid_type in invalid_types:
                            c.execute('''DELETE FROM user_dragons
                                         WHERE guild_id = ? AND user_id = ? AND dragon_type = ?''',
                                      (interaction.guild_id, interaction.user.id, invalid_type))
                        conn.commit()
                        # Recalculate user_dragon_types after cleanup
                        user_dragon_types = user_dragon_types - invalid_types

                    # Check if user has all 22 types
                    if user_dragon_types != required_types:
                        missing = required_types - user_dragon_types
                        missing_count = len(missing)
                        missing_list = list(missing)[:5]  # Show first 5
                        missing_names = [DRAGON_TYPES[d]['name'] for d in missing_list]
                        print(f"[CRAFT_ALPHA] Missing types: {missing}")
                        await interaction.response.send_message(
                            f"❌ You need at least 1 of each dragon type to craft an Alpha Dragon!\n"
                            f"Missing {missing_count} type(s): {', '.join(missing_names)}" +
                            (f"\n...and {missing_count - 5} more" if missing_count > 5 else ""),
                            ephemeral=False
                        )
                        conn.close()
                        return

                    # All checks passed - deduct 1 of each dragon type
                    for dragon_type in DRAGON_TYPES.keys():
                        c.execute('''UPDATE user_dragons
                                     SET count = count - 1
                                     WHERE guild_id = ? AND user_id = ? AND dragon_type = ?''',
                                  (interaction.guild_id, interaction.user.id, dragon_type))

                    # Get next NATO name
                    c.execute('''SELECT COUNT(*) FROM user_alphas
                                 WHERE guild_id = ? AND user_id = ?''',
                              (interaction.guild_id, interaction.user.id))

                    alpha_count = c.fetchone()[0]

                    nato_name = NATO_NAMES[alpha_count % len(NATO_NAMES)]

                    # Calculate catch boost value
                    new_count = alpha_count + 1
                    catch_boost = 0.06 * math.log(2 * new_count + 1)

                    # Create Alpha Dragon
                    c.execute('''INSERT INTO alpha_dragons (name, catch_boost)
                                 VALUES (?, ?)''',
                              (nato_name, catch_boost))
                    alpha_id = c.lastrowid

                    # Link to user
                    c.execute('''INSERT INTO user_alphas (guild_id, user_id, alpha_id, name, catch_boost, created_at)
                                 VALUES (?, ?, ?, ?, ?, ?)''',
                              (interaction.guild_id, interaction.user.id, alpha_id, nato_name, catch_boost, int(time.time())))

                    conn.commit()
                    conn.close()

                    # Success message
                    success_embed = discord.Embed(
                        title="✨ Alpha Dragon Crafted!",
                        description=f"**Name:** 🌟 {nato_name}\n"
                                    f"**Catch Boost:** +{round(catch_boost * 100, 1)}%\n"
                                    f"**Total Alpha Dragons:** {new_count}\n\n"
                                    f"*Your Alpha Dragons now grant +{round(catch_boost * 100, 1)}% catch rate!*",
                        color=discord.Color.gold()
                    )

                    await interaction.response.edit_message(embed=success_embed, view=None)

                except Exception as e:
                    print(f"[CRAFT_ALPHA ERROR] {e}")
                    import traceback
                    traceback.print_exc()
                    try:
                        conn.close()
                    except:
                        pass
                    try:
                        await interaction.response.send_message(
                            f"❌ Error crafting Alpha Dragon: {str(e)}",
                            ephemeral=False
                        )
                    except:
                        pass

        view = AlphaDragonView(can_craft=has_all_types)
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(PacksCog(bot))
