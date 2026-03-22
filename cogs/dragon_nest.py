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
from database import is_player_softlocked, update_balance, get_user
from utils import *
from achievements import check_and_award_achievements, award_trophy


class DragonNestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="skill", description="View your active passive item skills")
    async def skill(self, interaction: discord.Interaction):
        """Show passive items and their effects"""
        await interaction.response.defer(ephemeral=False)

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
                            f"You're **softlocked** from using skills until you upgrade.\n"
                            f"Use `/dragonnest` to upgrade!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=softlock_embed, delete_after=5)
            return

        guild_id = interaction.guild_id
        user_id = interaction.user.id

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get user balance for purchase checks
        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        user_result = c.fetchone()
        user_balance = user_result[0] if user_result else 0

        # Get passive items (knowledge_book, precision_stone)
        c.execute('SELECT item_type, count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type IN (?, ?)',
                  (guild_id, user_id, 'knowledge_book', 'precision_stone'))
        passive_items = c.fetchall()
        conn.close()

        if not passive_items:
            embed = discord.Embed(
                title="📚 Your Skills",
                description="You don't have any passive skill items yet!\n\n"
                            "Passive items are always active when you own them:\n"
                            "📚 Knowledge Book      -   5,000 🪙 base (+10% per owned)\n"
                    "   └─ +2% Catch (stacking)\n"
                    "🎯 Precision Stone     -   12,500 🪙 base (+10% per owned)\n"
                    "   └─ +5% Raid Damage (max 30% = 6 stones)",
                color=discord.Color.blue()
            )

            # Create upgrade view with buttons
            class SkillUpgradeNoItems(discord.ui.View):
                def __init__(self, guild_id, user_id, balance):
                    super().__init__(timeout=300)
                    self.guild_id = guild_id
                    self.user_id = user_id
                    self.balance = balance

                @discord.ui.button(label="Buy Knowledge Book (5,000 🪙)", style=discord.ButtonStyle.primary, emoji="📚")
                async def buy_knowledge(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.user_id:
                        await interaction.response.send_message("❌ This is not your skill menu!", ephemeral=True)
                        return

                    cost = 5000
                    if self.balance < cost:
                        await interaction.response.send_message(f"❌ Need {cost:,} 🪙, you have {int(self.balance):,} 🪙", ephemeral=True)
                        return

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                 VALUES (?, ?, 'knowledge_book', 1)
                                 ON CONFLICT(guild_id, user_id, item_type)
                                 DO UPDATE SET count = count + 1''',
                              (self.guild_id, self.user_id))
                    conn.commit()
                    conn.close()

                    await asyncio.to_thread(update_balance, self.guild_id, self.user_id, -cost)

                    await interaction.response.send_message(
                        f"✅ Purchased Knowledge Book!\n📚 +2% Catch Bonus\n💰 Cost: 5,000 🪙",
                        ephemeral=False
                    )

                @discord.ui.button(label="Buy Precision Stone (12,500 🪙)", style=discord.ButtonStyle.primary, emoji="🎯")
                async def buy_precision(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.user_id:
                        await interaction.response.send_message("❌ This is not your skill menu!", ephemeral=True)
                        return

                    cost = 12500
                    if self.balance < cost:
                        await interaction.response.send_message(f"❌ Need {cost:,} 🪙, you have {int(self.balance):,} 🪙", ephemeral=True)
                        return

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                 VALUES (?, ?, 'precision_stone', 1)
                                 ON CONFLICT(guild_id, user_id, item_type)
                                 DO UPDATE SET count = count + 1''',
                              (self.guild_id, self.user_id))
                    conn.commit()
                    conn.close()

                    await asyncio.to_thread(update_balance, self.guild_id, self.user_id, -cost)

                    await interaction.response.send_message(
                        f"✅ Purchased Precision Stone!\n🎯 +5% Raid Damage Bonus\n💰 Cost: 12,500 🪙",
                        ephemeral=False
                    )

            view = SkillUpgradeNoItems(guild_id, user_id, user_balance)
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)
            return

        embed = discord.Embed(
            title="📚 Your Passive Items",
            description="These items are always active and provide continuous bonuses:",
            color=discord.Color.blue()
        )

        total_catch_bonus = 0
        total_raid_bonus = 0
        items_dict = {}

        for item_type, count in passive_items:
            items_dict[item_type] = count
            if item_type == 'knowledge_book':
                bonus = count * 2  # 2% per book
                total_catch_bonus += bonus
                next_cost = calculate_item_cost(count, 5000)
                embed.add_field(
                    name=f"📚 Knowledge Book x{count}",
                    value=f"+{bonus}% Catch Success Rate\n(+2% per book, stacking)\n💰 Next: {next_cost:,} 🪙",
                    inline=False
                )
            elif item_type == 'precision_stone':
                bonus = min(count * 5, 30)  # 5% per stone, max 30%
                total_raid_bonus += bonus
                next_cost = calculate_item_cost(count, 12500)
                cap_note = " (MAX)" if count * 5 >= 30 else ""
                embed.add_field(
                    name=f"🎯 Precision Stone x{count}{cap_note}",
                    value=f"+{bonus}% Raid Boss Damage\n(+5% per stone, max 30%)\n💰 Next: {next_cost:,} 🪙",
                    inline=False
                )

        # Summary
        summary = ""
        if total_catch_bonus > 0:
            summary += f"✅ **Catch Bonus:** +{total_catch_bonus}%\n"
        if total_raid_bonus > 0:
            summary += f"✅ **Raid Damage Bonus:** +{total_raid_bonus}%\n"

        embed.add_field(
            name="📊 Current Bonuses",
            value=summary if summary else "No bonuses active",
            inline=False
        )

        embed.set_footer(text="Passive items are always active as long as you own them!")

        # Create upgrade buttons view
        class SkillUpgradeView(discord.ui.View):
            def __init__(self, guild_id, user_id, balance, items_dict):
                super().__init__(timeout=300)
                self.guild_id = guild_id
                self.user_id = user_id
                self.balance = balance
                self.items_dict = items_dict

            @discord.ui.button(label="Upgrade Knowledge Book", style=discord.ButtonStyle.success, emoji="📚")
            async def upgrade_knowledge(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ This is not your skill menu!", ephemeral=True)
                    return

                # Re-fetch balance fresh from DB to avoid stale cache
                user_data = get_user(self.guild_id, self.user_id)
                current_balance = user_data[2] if user_data else 0

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                          (self.guild_id, self.user_id, 'knowledge_book'))
                row = c.fetchone()
                current_count = row[0] if row else 0
                cost = calculate_item_cost(current_count, 5000)

                if current_balance < cost:
                    conn.close()
                    await interaction.response.send_message(
                        f"❌ Need {cost:,} 🪙, you have {int(current_balance):,} 🪙",
                        ephemeral=True
                    )
                    return

                c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                             VALUES (?, ?, 'knowledge_book', 1)
                             ON CONFLICT(guild_id, user_id, item_type)
                             DO UPDATE SET count = count + 1''',
                          (self.guild_id, self.user_id))
                conn.commit()
                conn.close()

                await asyncio.to_thread(update_balance, self.guild_id, self.user_id, -cost)

                new_count = current_count + 1
                new_bonus = new_count * 2

                await interaction.response.send_message(
                    f"✅ Upgraded Knowledge Book!\n📚 Now: +{new_bonus}% Catch\n💰 Cost: {cost:,} 🪙",
                    ephemeral=False
                )

            @discord.ui.button(label="Upgrade Precision Stone", style=discord.ButtonStyle.success, emoji="🎯")
            async def upgrade_precision(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ This is not your skill menu!", ephemeral=True)
                    return

                # Re-fetch balance fresh from DB to avoid stale cache
                user_data = get_user(self.guild_id, self.user_id)
                current_balance = user_data[2] if user_data else 0

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                          (self.guild_id, self.user_id, 'precision_stone'))
                row = c.fetchone()
                current_count = row[0] if row else 0
                cost = calculate_item_cost(current_count, 12500)

                if current_balance < cost:
                    conn.close()
                    await interaction.response.send_message(
                        f"❌ Need {cost:,} 🪙, you have {int(current_balance):,} 🪙",
                        ephemeral=True
                    )
                    return

                if current_count >= 6:  # Already at max 30%
                    conn.close()
                    await interaction.response.send_message(
                        f"⚠️ Already at maximum (30% bonus)!",
                        ephemeral=True
                    )
                    return

                c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                             VALUES (?, ?, 'precision_stone', 1)
                             ON CONFLICT(guild_id, user_id, item_type)
                             DO UPDATE SET count = count + 1''',
                          (self.guild_id, self.user_id))
                conn.commit()
                conn.close()

                await asyncio.to_thread(update_balance, self.guild_id, self.user_id, -cost)

                new_count = current_count + 1
                new_bonus = min(new_count * 5, 30)

                await interaction.response.send_message(
                    f"✅ Upgraded Precision Stone!\n🎯 Now: +{new_bonus}% Raid Damage\n💰 Cost: {cost:,} 🪙",
                    ephemeral=False
                )

        view = SkillUpgradeView(guild_id, user_id, user_balance, items_dict)
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="dragonnest", description="Access the Dragon Nest leveling system")
    async def dragonnest(self, interaction: discord.Interaction):
        """Dragon Nest leveling system"""
        await interaction.response.defer(ephemeral=False)

        try:
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            # Get or create nest data
            c.execute('INSERT OR IGNORE INTO dragon_nest (guild_id, user_id) VALUES (?, ?)',
                      (interaction.guild_id, interaction.user.id))
            c.execute('SELECT level, xp, bounties_completed, bounties_active FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                      (interaction.guild_id, interaction.user.id))
            result = c.fetchone()

            # Check if there's a pending level up (sacrifice waiting)
            c.execute('SELECT level, perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ?',
                      (interaction.guild_id, interaction.user.id))
            pending_result = c.fetchone()

            conn.commit()
            conn.close()

        except sqlite3.OperationalError as e:
            await interaction.followup.send("⚠️ Database integrity issue detected. Please try again in a moment.")
            return

        # If there's a pending data, handle appropriately
        if pending_result:
            pending_level, perks_json = pending_result
            pending_data = json.loads(perks_json)

            # Check what type of pending action this is
            if 'sacrifice_list' in pending_data:
                sacrifice_list = pending_data['sacrifice_list']
                new_level = pending_data['new_level']

                # Handle both old format (list of tuples) and new format (dict)
                if isinstance(sacrifice_list, list):
                    sacrifice_list = {dragon_type: count for dragon_type, count in sacrifice_list}

                # Build sacrifice display
                sacrifice_display = ""
                for dragon_type, count in sacrifice_list.items():
                    dragon_data = DRAGON_TYPES[dragon_type]
                    sacrifice_display += f"{dragon_data['emoji']} {count}x {dragon_data['name']}\n"

                embed = discord.Embed(
                    title="🎉 Dragon Nest Level Complete!",
                    description=f"You completed all bounties and reached **Level {new_level}: {LEVEL_NAMES.get(new_level, 'Unknown')}**!\n\n"
                                f"🐉 **Dragons to Sacrifice:**\n{sacrifice_display}\n"
                                f"Click **Submit Dragons** to confirm and unlock your perk reward!",
                    color=discord.Color.green()
                )

                class DragonSacrificeViewInstance(discord.ui.View):
                    def __init__(self, guild_id, user_id, sac_list, level):
                        super().__init__(timeout=300)
                        self.guild_id = guild_id
                        self.user_id = user_id
                        self.sacrifice_list = sac_list
                        self.level = level

                        submit_button = discord.ui.Button(
                            label="💾 Submit Dragons",
                            style=discord.ButtonStyle.success,
                            custom_id=f"submit_dragons_{guild_id}_{user_id}_{level}"
                        )
                        submit_button.callback = self.submit_dragons
                        self.add_item(submit_button)

                    async def submit_dragons(self, btn_interaction: discord.Interaction):
                        if btn_interaction.user.id != self.user_id:
                            await btn_interaction.response.send_message("This is not your action!", ephemeral=True)
                            return

                        await btn_interaction.response.defer()

                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()

                        # Remove dragons and level up
                        for dragon_type, count in self.sacrifice_list.items():
                            c.execute('UPDATE user_dragons SET count = count - ? WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                      (count, self.guild_id, self.user_id, dragon_type))

                        # Update level
                        c.execute('UPDATE dragon_nest SET level = ? WHERE guild_id = ? AND user_id = ?',
                                  (self.level, self.guild_id, self.user_id))

                        # Delete pending perks entry
                        c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ?',
                                  (self.guild_id, self.user_id))

                        # Check if player reached max level (10)
                        c.execute('SELECT level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                  (self.guild_id, self.user_id))
                        current_level = c.fetchone()[0]

                        conn.commit()
                        conn.close()

                        if current_level == 10:
                            await award_trophy(btn_interaction.client, self.guild_id, self.user_id, 'nest_master')

                        await check_and_award_achievements(self.guild_id, self.user_id, bot=btn_interaction.client)

                        perk_store_level = current_level + 1 if current_level < 10 else 10
                        new_selected_perks = generate_unique_perks(perk_store_level, 3, 0)
                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()
                        c.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                     VALUES (?, ?, ?, ?)''',
                                  (self.guild_id, self.user_id, perk_store_level, json.dumps({'selected_perks': new_selected_perks})))
                        conn.commit()
                        conn.close()

                        if current_level < 10:
                            await btn_interaction.followup.send(
                                f"✨ **Level {self.level} Unlocked!**\n"
                                f"🎁 A new perk is waiting for you! Use `/dragonnest` to claim it.",
                                ephemeral=False
                            )
                        else:
                            await btn_interaction.followup.send(
                                f"🏆 **Max Level Reached!**\n"
                                f"You've reached the maximum Dragon Nest level!\n"
                                f"🎁 Your final perk is waiting! Use `/dragonnest` to claim it.",
                                ephemeral=False
                            )

                view = DragonSacrificeViewInstance(interaction.guild_id, interaction.user.id, sacrifice_list, new_level)
                await interaction.followup.send(embed=embed, view=view, ephemeral=False)
                return

            elif 'selected_perks' in pending_data:
                selected_perks = pending_data['selected_perks']

                # Build perk selection view
                perks_list = []
                for rarity, perk in selected_perks:
                    perks_list.append((rarity, perk))

                rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                perk_text = ""
                for i, (r, p) in enumerate(perks_list, 1):
                    perk_text += f"{i}. {rarity_emoji.get(r, '⚪')} **{p.get('name', 'Unknown')}** ({r.capitalize()})\n   *{p.get('effect', '')}*\n\n"

                embed = discord.Embed(
                    title=f"🎁 Claim Missing Perk - Level {pending_level}",
                    description=perk_text + "Select a perk to claim!",
                    color=discord.Color.gold()
                )

                # Get remaining missing perks count
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('SELECT COUNT(*) FROM user_perks WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                perk_count = c.fetchone()[0]

                c.execute('SELECT level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                current_level = c.fetchone()[0]
                conn.close()

                total_missing = current_level - perk_count
                embed.set_footer(text=f"Missing perks: {total_missing}")

                class MissingPerkSelectionView(discord.ui.View):
                    def __init__(self, guild_id, user_id, perks, level, total_missing):
                        super().__init__(timeout=180)
                        self.guild_id = guild_id
                        self.user_id = user_id
                        self.perks = perks
                        self.level = level
                        self.total_missing = total_missing

                        rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                        for i, (rarity, perk) in enumerate(perks, 1):
                            button = discord.ui.Button(
                                label=f"{i}",
                                style=discord.ButtonStyle.primary if rarity in ['common', 'uncommon'] else discord.ButtonStyle.success if rarity == 'rare' else discord.ButtonStyle.danger if rarity == 'epic' else discord.ButtonStyle.blurple,
                                custom_id=f"claim_perk_{guild_id}_{user_id}_{level}_{i}"
                            )
                            button.callback = self.create_callback(i-1, rarity, perk)
                            self.add_item(button)

                    def create_callback(self, index, rarity, perk):
                        async def callback(btn_interaction: discord.Interaction):
                            if btn_interaction.user.id != self.user_id:
                                await btn_interaction.response.send_message("This is not your selection!", ephemeral=False)
                                return

                            try:
                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()

                                # Add perk to collection (not activated yet)
                                c.execute('''INSERT OR IGNORE INTO user_perks (guild_id, user_id, perk_id, perk_name, perk_effect, perk_value, rarity)
                                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                          (self.guild_id, self.user_id, perk['id'], perk['name'],
                                           perk['effect'], perk.get('value', 0), rarity))

                                # Delete the pending perk for this level
                                c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = ?',
                                          (self.guild_id, self.user_id, self.level))

                                # Check if there are more missing perks
                                c.execute('SELECT COUNT(*) FROM user_perks WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                                new_count = c.fetchone()[0]

                                c.execute('SELECT level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                                current_level = c.fetchone()[0]

                                conn.commit()
                                conn.close()

                                remaining = current_level - new_count

                                rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}

                                if remaining > 0:
                                    next_level = new_count + 1

                                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                    c = conn.cursor()
                                    c.execute('SELECT perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = ?',
                                              (self.guild_id, self.user_id, next_level))
                                    stored_next = c.fetchone()

                                    c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                              (self.guild_id, self.user_id))
                                    upg_res_sel = c.fetchone()
                                    upg_level_sel = upg_res_sel[0] if upg_res_sel else 0
                                    conn.close()

                                    if stored_next:
                                        stored_data = json.loads(stored_next[0])
                                        if isinstance(stored_data, dict) and 'selected_perks' in stored_data:
                                            next_perks = stored_data['selected_perks']
                                        else:
                                            next_perks = stored_data if isinstance(stored_data, list) else []
                                    else:
                                        next_perks = generate_unique_perks(next_level, 3, upg_level_sel)
                                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                        c = conn.cursor()
                                        c.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                                     VALUES (?, ?, ?, ?)''',
                                                  (self.guild_id, self.user_id, next_level, json.dumps({'selected_perks': next_perks})))
                                        conn.commit()
                                        conn.close()

                                    perk_text = ""
                                    for i, (r, p) in enumerate(next_perks, 1):
                                        perk_text += f"{i}. {rarity_emoji.get(r, '⚪')} **{p['name']}** ({r.capitalize()})\n   *{p['effect']}*\n\n"

                                    next_embed = discord.Embed(
                                        title=f"🎁 Claim Missing Perk - Level {next_level}",
                                        description=perk_text + "Select a perk to claim!",
                                        color=discord.Color.gold()
                                    )
                                    next_embed.set_footer(text=f"Missing perks: {remaining - 1}")

                                    await btn_interaction.response.send_message(embed=next_embed, view=MissingPerkSelectionView(self.guild_id, self.user_id, next_perks, next_level, remaining - 1), ephemeral=False)
                                else:
                                    await btn_interaction.response.send_message("🎉 You've claimed all missing perks!", ephemeral=False)
                            except Exception as e:
                                await btn_interaction.response.send_message(f"❌ Error claiming perk: {str(e)}", ephemeral=True)
                                traceback.print_exc()

                        return callback

                view = MissingPerkSelectionView(interaction.guild_id, interaction.user.id, perks_list, pending_level, total_missing)
                await interaction.followup.send(embed=embed, view=view)
                return

            else:
                c = sqlite3.connect('dragon_bot.db', timeout=120.0)
                cursor = c.cursor()
                c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                c.commit()
                c.close()

                perks_list = []
                new_level = 0

            class PerkSelectionView(discord.ui.View):
                def __init__(self, guild_id, user_id, perks, level):
                    super().__init__(timeout=300)
                    self.guild_id = guild_id
                    self.user_id = user_id
                    self.perks = perks
                    self.level = level

                    for i, (rarity, perk) in enumerate(perks, 1):
                        button = discord.ui.Button(
                            label=f"{i}. {perk['name']}",
                            style=discord.ButtonStyle.primary if rarity in ['common', 'uncommon'] else discord.ButtonStyle.success if rarity == 'rare' else discord.ButtonStyle.danger if rarity == 'epic' else discord.ButtonStyle.blurple,
                            custom_id=f"perk_lvlup_{guild_id}_{user_id}_{perk['id']}"
                        )
                        button.callback = self.create_callback(i-1, rarity, perk)
                        self.add_item(button)

                def create_callback(self, index, rarity, perk):
                    async def callback(interaction: discord.Interaction):
                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()

                        c.execute('UPDATE user_perks SET selected = 1 WHERE guild_id = ? AND user_id = ? AND perk_id = ?',
                                  (self.guild_id, self.user_id, perk['id']))

                        c.execute('UPDATE dragon_nest SET level = ?, perks_activated_at_current_level = 0 WHERE guild_id = ? AND user_id = ?',
                                  (self.level, self.guild_id, self.user_id))

                        c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ?',
                                  (self.guild_id, self.user_id))

                        conn.commit()
                        conn.close()

                        await interaction.response.send_message(
                            f"🎉 **Level {self.level} Unlocked!**\n"
                            f"✨ You selected: **{perk['name']}**\n"
                            f"Your perk is now available to activate!",
                            ephemeral=False
                        )

                    return callback

            if perks_list:
                view = PerkSelectionView(interaction.guild_id, interaction.user.id, perks_list, new_level)
                await interaction.followup.send(embed=embed, view=view, ephemeral=False)
                return

        # Normal Dragon Nest display
        c = sqlite3.connect('dragon_bot.db', timeout=120.0)
        cursor = c.cursor()

        cursor.execute('SELECT active_until FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                       (interaction.guild_id, interaction.user.id))
        active_result = cursor.fetchone()

        cursor.execute('SELECT expires_at FROM raid_bosses WHERE guild_id = ? AND expires_at > ?',
                       (interaction.guild_id, int(time.time())))
        raid_active = cursor.fetchone()

        cursor.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                       (interaction.guild_id, interaction.user.id))
        upgrade_result = cursor.fetchone()

        c.close()

        level = result[0] if result else 0
        xp = result[1] if result else 0
        bounties_completed = result[2] if result else 0
        bounties_active = result[3] if result else None
        upgrade_level = upgrade_result[0] if upgrade_result else 0

        level_name = LEVEL_NAMES.get(level, "Unknown")
        character = LEVEL_CHARACTERS.get(level, "None")
        lore_text = LEVEL_LORE.get(level, "Your journey continues...")

        is_active = active_result and active_result[0] > int(time.time())
        time_left = (active_result[0] - int(time.time())) if is_active else 0

        is_paused = is_active and raid_active

        embed = discord.Embed(
            title=f"🏰 {interaction.user.display_name}'s Dragon Nest",
            description=f"**Level {level}: {level_name}** | Upgrade Tier: {upgrade_level}/5\n*{character}*\n\n✨ {lore_text}",
            color=discord.Color.red() if is_paused else discord.Color.green() if is_active else discord.Color.purple()
        )

        thumbnail_url = LEVEL_THUMBNAILS.get(level)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        embed.add_field(name="Total Bounties Completed", value=str(bounties_completed), inline=True)
        embed.add_field(name="Current Level", value=f"{level}/10", inline=True)

        if is_paused:
            embed.add_field(
                name="⏸️ PAUSED - Raid Boss Active!",
                value="Dragon Nest is paused while a raid boss is active.\nNo normal dragons are spawning.",
                inline=False
            )

        if is_active and bounties_active and not is_paused:
            bounties = ast.literal_eval(bounties_active)
            bounty_text = ""
            for i, bounty in enumerate(bounties, 1):
                progress = bounty['progress']
                target = bounty['target']
                if bounty['type'] == 'catch_any':
                    bounty_text += f"📋 **Bounty {i}:** Catch {target} dragons ({progress}/{target})\n"
                elif bounty['type'] == 'catch_type':
                    dragon_name = DRAGON_TYPES[bounty['dragon_type']]['name']
                    dragon_emoji = DRAGON_TYPES[bounty['dragon_type']]['emoji']
                    bounty_text += f"📋 **Bounty {i}:** Catch {target}x {dragon_emoji} {dragon_name} ({progress}/{target})\n"
                elif bounty['type'] == 'catch_rarity_or_higher':
                    rarity_names = {1: 'Uncommon', 2: 'Rare', 3: 'Epic', 4: 'Legendary', 5: 'Mythic'}
                    rarity_name = rarity_names.get(bounty.get('rarity_level'), 'Rare')
                    bounty_text += f"📋 **Bounty {i}:** Catch {target} {rarity_name}+ dragons ({progress}/{target})\n"

            embed.add_field(name="🎯 Active Bounties", value=bounty_text, inline=False)
            embed.add_field(name="⏰ Time Remaining", value=format_time_remaining(time_left), inline=False)

        embed.set_footer(text="Activate Dragon Nest to start bounties!")

        # Create button view
        class DragonNestView(discord.ui.View):
            def __init__(self, is_active=False, guild_id=None, user_id=None, current_level=0):
                super().__init__(timeout=180)
                self.is_active = is_active
                self.guild_id = guild_id
                self.user_id = user_id
                self.current_level = current_level

                if not is_active:
                    activate_button = discord.ui.Button(
                        label="Activate Dragon Nest",
                        style=discord.ButtonStyle.green,
                        emoji="🔥",
                        custom_id="activate_nest"
                    )
                    activate_button.callback = self.activate_nest
                    self.add_item(activate_button)

                view_perks_button = discord.ui.Button(
                    label="View Perks",
                    style=discord.ButtonStyle.blurple,
                    emoji="✨",
                    custom_id="view_perks"
                )
                view_perks_button.callback = self.view_perks
                self.add_item(view_perks_button)

                help_btn = discord.ui.Button(
                    label="Help",
                    style=discord.ButtonStyle.gray,
                    emoji="❓",
                    custom_id="help"
                )
                help_btn.callback = self.help_button
                self.add_item(help_btn)

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (guild_id, user_id))
                result = c.fetchone()
                upgrade_level_val = result[0] if result else 0

                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                          (guild_id, user_id))
                bal_row = c.fetchone()
                balance_val = bal_row[0] if bal_row else 0

                c.execute('SELECT COUNT(*) FROM active_perks WHERE guild_id = ? AND user_id = ?',
                          (guild_id, user_id))
                active_perks_count = c.fetchone()[0]

                conn.close()

                next_upgrade_level = upgrade_level_val + 1
                upgrade_cost = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('cost', 0)
                can_afford_upgrade = upgrade_level_val < 5 and upgrade_cost > 0 and balance_val >= upgrade_cost

                if can_afford_upgrade:
                    upgrade_button = discord.ui.Button(
                        label="Upgrade Dragon Nest",
                        style=discord.ButtonStyle.primary,
                        emoji="⬆️",
                        custom_id="upgrade_nest"
                    )
                    upgrade_button.callback = self.upgrade_nest
                    self.add_item(upgrade_button)

                if upgrade_level_val > 0 and active_perks_count == 0:
                    select_perk_button = discord.ui.Button(
                        label="Claim Missing Perks",
                        style=discord.ButtonStyle.blurple,
                        emoji="🎁",
                        custom_id="select_perk"
                    )
                    select_perk_button.callback = self.claim_missing_perks
                    self.add_item(select_perk_button)

            async def claim_missing_perks(self, interaction: discord.Interaction):
                """Allow users to claim their missing perks"""
                await interaction.response.defer()

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                c.execute('SELECT level, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                result = c.fetchone()
                current_level = result[0] if result else 0
                upgrade_level = result[1] if result and len(result) > 1 else 0

                c.execute('SELECT COUNT(*) FROM active_perks WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                active_perks_count = c.fetchone()[0]

                conn.close()

                if upgrade_level > 0 and active_perks_count == 0:
                    await self.show_tier_perk_selection(interaction, interaction.guild_id, interaction.user.id, tier=1, upgrade_level=upgrade_level)
                    return

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                c.execute('SELECT level, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                result = c.fetchone()
                current_level = result[0] if result else 0
                upgrade_level = result[1] if result and len(result) > 1 else 0

                c.execute('SELECT COUNT(*) FROM user_perks WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                perks_count = c.fetchone()[0]

                expected_perks = min(current_level, 10)
                missing_level_perks = expected_perks - perks_count

                c.execute('SELECT perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = 0',
                          (interaction.guild_id, interaction.user.id))
                upgrade_perks_result = c.fetchone()

                c.execute('SELECT level, perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level < 0 ORDER BY level DESC',
                          (interaction.guild_id, interaction.user.id))
                old_upgrade_results = c.fetchall()

                conn.close()

                has_upgrade_perks = False
                upgrade_tiers_available = {}
                use_old_format = False

                if upgrade_perks_result:
                    try:
                        upgrade_data = json.loads(upgrade_perks_result[0])
                        upgrade_tiers_available = upgrade_data.get('upgrade_tiers', {})
                        has_upgrade_perks = len(upgrade_tiers_available) > 0
                    except:
                        has_upgrade_perks = False

                if not has_upgrade_perks and len(old_upgrade_results) > 0:
                    has_upgrade_perks = True
                    use_old_format = True
                    for level_val, perks_json in old_upgrade_results:
                        actual_tier = abs(level_val)
                        try:
                            stored_data = json.loads(perks_json)
                            if isinstance(stored_data, dict) and 'selected_perks' in stored_data:
                                upgrade_tiers_available[str(actual_tier)] = {
                                    'perks': stored_data['selected_perks'],
                                    'level_marker': level_val
                                }
                            else:
                                upgrade_tiers_available[str(actual_tier)] = {
                                    'perks': stored_data if isinstance(stored_data, list) else [],
                                    'level_marker': level_val
                                }
                        except:
                            pass

                if has_upgrade_perks:
                    earliest_unclaimed_tier = None
                    for tier_str in ['1', '2', '3', '4', '5']:
                        if tier_str in upgrade_tiers_available:
                            earliest_unclaimed_tier = tier_str
                            break

                    if earliest_unclaimed_tier:
                        tier_data = upgrade_tiers_available[earliest_unclaimed_tier]
                        selected_perks = tier_data.get('perks', [])

                        if not selected_perks:
                            await interaction.followup.send("❌ Error loading upgrade perks. Please try again later.", ephemeral=True)
                            return

                        rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                        perk_text = ""
                        for i, (rarity, perk) in enumerate(selected_perks, 1):
                            perk_text += f"{i}. {rarity_emoji.get(rarity, '⚪')} **{perk['name']}** ({rarity.capitalize()})\n   *{perk['effect']}*\n\n"

                        remaining_tiers = sum(1 for t in ['1', '2', '3', '4', '5'] if t in upgrade_tiers_available)

                        embed = discord.Embed(
                            title=f"🎁 Claim Upgrade Tier {earliest_unclaimed_tier} Perks",
                            description=perk_text + "Select a perk to claim!",
                            color=discord.Color.gold()
                        )
                        embed.set_footer(text=f"Upgrade perks remaining: {remaining_tiers}")

                        class UpgradePerkSelectionView(discord.ui.View):
                            def __init__(self, guild_id, user_id, perks, upgrade_tier_str, missing_level_perks_val):
                                super().__init__(timeout=180)
                                self.guild_id = guild_id
                                self.user_id = user_id
                                self.perks = perks
                                self.upgrade_tier_str = upgrade_tier_str
                                self.missing_level_perks = missing_level_perks_val

                                rarity_emoji_local = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                                for i, (rarity, perk) in enumerate(perks, 1):
                                    button = discord.ui.Button(
                                        label=f"{i}",
                                        style=discord.ButtonStyle.primary if rarity in ['common', 'uncommon'] else discord.ButtonStyle.success if rarity == 'rare' else discord.ButtonStyle.danger if rarity == 'epic' else discord.ButtonStyle.blurple,
                                        custom_id=f"claim_upgrade_perk_{guild_id}_{user_id}_{upgrade_tier_str}_{i}"
                                    )
                                    button.callback = self.create_callback(i-1, rarity, perk)
                                    self.add_item(button)

                            def create_callback(self, index, rarity, perk):
                                async def callback(btn_interaction: discord.Interaction):
                                    if btn_interaction.user.id != self.user_id:
                                        await btn_interaction.response.send_message("This is not your selection!", ephemeral=False)
                                        return

                                    try:
                                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                        c = conn.cursor()

                                        expires_at = int(datetime(2099, 12, 31).timestamp())
                                        c.execute(
                                            '''INSERT OR REPLACE INTO active_perks
                                               (guild_id, user_id, perk_id, perk_name, perk_effect, perk_value, perk_type, expires_at)
                                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                            (self.guild_id, self.user_id, perk['id'], perk['name'], perk['effect'], perk.get('value', 0), perk.get('type', 'upgrade'), expires_at)
                                        )

                                        c.execute('SELECT perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = 0',
                                                  (self.guild_id, self.user_id))
                                        existing_result = c.fetchone()

                                        level_marker = None
                                        c.execute('SELECT level FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level < 0',
                                                  (self.guild_id, self.user_id))
                                        level_results = c.fetchall()
                                        if level_results:
                                            for level_val, in level_results:
                                                if abs(level_val) == int(self.upgrade_tier_str):
                                                    level_marker = level_val
                                                    break

                                        if existing_result:
                                            existing_data = json.loads(existing_result[0])
                                            upgrade_tiers = existing_data.get('upgrade_tiers', {})

                                            if self.upgrade_tier_str in upgrade_tiers:
                                                del upgrade_tiers[self.upgrade_tier_str]

                                            if upgrade_tiers:
                                                c.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                                             VALUES (?, ?, ?, ?)''',
                                                          (self.guild_id, self.user_id, 0, json.dumps({'upgrade_tiers': upgrade_tiers})))
                                            else:
                                                c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = 0',
                                                          (self.guild_id, self.user_id))
                                        elif level_marker:
                                            c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = ?',
                                                      (self.guild_id, self.user_id, level_marker))

                                        conn.commit()
                                        conn.close()

                                        success_msg = f"✅ You claimed **{perk['name']}** from Upgrade Tier {self.upgrade_tier_str}!\n\n"

                                        remaining_tiers = 0
                                        if existing_result:
                                            try:
                                                existing_data = json.loads(existing_result[0])
                                                remaining_tiers = len(existing_data.get('upgrade_tiers', {})) - 1
                                            except:
                                                pass

                                        if remaining_tiers > 0:
                                            success_msg += f"You have **{remaining_tiers}** more upgrade tier(s) to claim!"
                                        elif self.missing_level_perks > 0:
                                            success_msg += f"You still have **{self.missing_level_perks}** level-up perks to claim!"
                                        else:
                                            success_msg += "🎉 All your perks are now claimed!"

                                        await btn_interaction.response.send_message(success_msg, ephemeral=False)
                                    except Exception as e:
                                        await btn_interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                                        traceback.print_exc()

                                return callback

                        view = UpgradePerkSelectionView(interaction.guild_id, interaction.user.id, selected_perks, earliest_unclaimed_tier, missing_level_perks)
                        await interaction.followup.send(embed=embed, view=view, ephemeral=False)
                        return

                elif missing_level_perks > 0:
                    first_missing_level = perks_count + 1

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('SELECT perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = ?',
                              (interaction.guild_id, interaction.user.id, first_missing_level))
                    stored = c.fetchone()
                    conn.close()

                    if stored:
                        stored_data = json.loads(stored[0])
                        if isinstance(stored_data, dict) and 'selected_perks' in stored_data:
                            selected_perks = stored_data['selected_perks']
                        else:
                            selected_perks = stored_data if isinstance(stored_data, list) else []
                    else:
                        selected_perks = generate_unique_perks(first_missing_level, 3, upgrade_level)
                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()
                        c.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                     VALUES (?, ?, ?, ?)''',
                                  (interaction.guild_id, interaction.user.id, first_missing_level, json.dumps({'selected_perks': selected_perks})))
                        conn.commit()
                        conn.close()

                    rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                    perk_text = ""
                    for i, (rarity, perk) in enumerate(selected_perks, 1):
                        perk_text += f"{i}. {rarity_emoji.get(rarity, '⚪')} **{perk['name']}** ({rarity.capitalize()})\n   *{perk['effect']}*\n\n"

                    embed = discord.Embed(
                        title=f"🎁 Claim Missing Perk - Level {first_missing_level}",
                        description=perk_text + "Select a perk to claim!",
                        color=discord.Color.gold()
                    )
                    embed.set_footer(text=f"Missing perks: {missing_level_perks}")

                    class MissingPerkSelectionView(discord.ui.View):
                        def __init__(self, guild_id, user_id, perks, level, total_missing):
                            super().__init__(timeout=180)
                            self.guild_id = guild_id
                            self.user_id = user_id
                            self.perks = perks
                            self.level = level
                            self.total_missing = total_missing

                            rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                            for i, (rarity, perk) in enumerate(perks, 1):
                                button = discord.ui.Button(
                                    label=f"{i}",
                                    style=discord.ButtonStyle.primary if rarity in ['common', 'uncommon'] else discord.ButtonStyle.success if rarity == 'rare' else discord.ButtonStyle.danger if rarity == 'epic' else discord.ButtonStyle.blurple,
                                    custom_id=f"claim_perk_r_{guild_id}_{user_id}_{level}_{i}"
                                )
                                button.callback = self.create_callback(i-1, rarity, perk)
                                self.add_item(button)

                        def create_callback(self, index, rarity, perk):
                            async def callback(btn_interaction: discord.Interaction):
                                if btn_interaction.user.id != self.user_id:
                                    await btn_interaction.response.send_message("This is not your selection!", ephemeral=False)
                                    return

                                try:
                                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                    c = conn.cursor()

                                    c.execute('''INSERT OR IGNORE INTO user_perks (guild_id, user_id, perk_id, perk_name, perk_effect, perk_value, rarity)
                                                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                              (self.guild_id, self.user_id, perk['id'], perk['name'],
                                               perk['effect'], perk.get('value', 0), rarity))

                                    c.execute('DELETE FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = ?',
                                              (self.guild_id, self.user_id, self.level))

                                    c.execute('SELECT COUNT(*) FROM user_perks WHERE guild_id = ? AND user_id = ?',
                                              (self.guild_id, self.user_id))
                                    new_count = c.fetchone()[0]

                                    c.execute('SELECT level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                              (self.guild_id, self.user_id))
                                    current_level = c.fetchone()[0]

                                    c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                              (self.guild_id, self.user_id))
                                    upg_res = c.fetchone()
                                    upg_level = upg_res[0] if upg_res else 0

                                    conn.commit()
                                    conn.close()

                                    remaining = current_level - new_count
                                    rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}

                                    if remaining > 0:
                                        next_level = new_count + 1

                                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                        c = conn.cursor()
                                        c.execute('SELECT perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = ?',
                                                  (self.guild_id, self.user_id, next_level))
                                        stored_next = c.fetchone()
                                        conn.close()

                                        if stored_next:
                                            stored_data = json.loads(stored_next[0])
                                            if isinstance(stored_data, dict) and 'selected_perks' in stored_data:
                                                next_perks = stored_data['selected_perks']
                                            else:
                                                next_perks = stored_data if isinstance(stored_data, list) else []
                                        else:
                                            next_perks = generate_unique_perks(next_level, 3, upg_level)
                                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                            c = conn.cursor()
                                            c.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                                         VALUES (?, ?, ?, ?)''',
                                                      (self.guild_id, self.user_id, next_level, json.dumps({'selected_perks': next_perks})))
                                            conn.commit()
                                            conn.close()

                                        perk_text = ""
                                        for i, (r, p) in enumerate(next_perks, 1):
                                            perk_text += f"{i}. {rarity_emoji.get(r, '⚪')} **{p['name']}** ({r.capitalize()})\n   *{p['effect']}*\n\n"

                                        next_embed = discord.Embed(
                                            title=f"🎁 Claim Missing Perk - Level {next_level}",
                                            description=perk_text + "Select a perk to claim!",
                                            color=discord.Color.gold()
                                        )
                                        next_embed.set_footer(text=f"Missing perks: {remaining - 1}")

                                        await btn_interaction.response.send_message(embed=next_embed, view=MissingPerkSelectionView(self.guild_id, self.user_id, next_perks, next_level, remaining - 1), ephemeral=False)
                                    else:
                                        await btn_interaction.response.send_message("🎉 You've claimed all missing perks!", ephemeral=False)
                                except Exception as e:
                                    await btn_interaction.response.send_message(f"❌ Error claiming perk: {str(e)}", ephemeral=True)
                                    traceback.print_exc()

                            return callback

                    view = MissingPerkSelectionView(interaction.guild_id, interaction.user.id, selected_perks, first_missing_level, missing_level_perks)
                    await interaction.followup.send(embed=embed, view=view, ephemeral=False)
                    return

                else:
                    await interaction.followup.send(
                        "✅ You don't have any missing perks!\n\n"
                        f"You've collected **{perks_count}** perks for your **Level {current_level}** account.",
                        ephemeral=False
                    )
                    return

            async def show_tier_perk_selection(self, interaction: discord.Interaction, guild_id: int, user_id: int, tier: int, upgrade_level: int):
                """Show tier-specific perk selection for upgrade recovery"""
                try:
                    allowed_rarities = DRAGONNEST_UPGRADES.get(tier, {}).get('allowed_rarities', [])
                    available_perks = []
                    for rarity in allowed_rarities:
                        available_perks.extend(PERKS_POOL.get(rarity, []))

                    random.shuffle(available_perks)
                    selected_perks = available_perks[:10]

                    perk_list = ""
                    for i, perk in enumerate(selected_perks, 1):
                        perk_list += f"{i}. **{perk['name']}** - {perk['effect']}\n"

                    embed = discord.Embed(
                        title=f"🎁 Upgrade Tier {tier}: Select 2 Starting Perks",
                        description=f"Choose 2 perks that will be permanently active for Tier {tier}:\n\n{perk_list}",
                        color=discord.Color.gold()
                    )

                    class TierPerkSelectionView(discord.ui.View):
                        def __init__(self, guild_id, user_id, perks, tier, total_tiers, outer_self):
                            super().__init__(timeout=300)
                            self.guild_id = guild_id
                            self.user_id = user_id
                            self.perks = perks
                            self.tier = tier
                            self.total_tiers = total_tiers
                            self.selected_perks = []
                            self.outer_self = outer_self

                            perk_options = [
                                discord.SelectOption(
                                    label=perk['name'][:100],
                                    value=str(i),
                                    description=perk['effect'][:100]
                                )
                                for i, perk in enumerate(perks)
                            ]

                            self.perk_select.options = perk_options
                            self.perk_select.min_values = 2
                            self.perk_select.max_values = 2
                            self.perk_select.placeholder = f"Select 2 perks for Tier {tier}..."

                        @discord.ui.select(placeholder="Select 2 perks...")
                        async def perk_select(self, interaction_select: discord.Interaction, select: discord.ui.Select):
                            self.selected_perks = [int(idx) for idx in select.values]
                            selected_names = ", ".join([self.perks[idx]['name'] for idx in self.selected_perks])
                            await interaction_select.response.send_message(f"✅ You selected: **{selected_names}**\n\nNow click **Confirm** to proceed!", ephemeral=True)

                        @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
                        async def confirm_tier_perks(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                            try:
                                if btn_interaction.user.id != self.user_id:
                                    await btn_interaction.response.send_message("This is not your selection!", ephemeral=True)
                                    return

                                if len(self.selected_perks) != 2:
                                    await btn_interaction.response.send_message("You must select exactly 2 perks!", ephemeral=True)
                                    return

                                await btn_interaction.response.defer()

                                conn_perk = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c_perk = conn_perk.cursor()

                                expires_at = int(datetime(2099, 12, 31).timestamp())

                                for perk_idx in self.selected_perks:
                                    perk = self.perks[perk_idx]
                                    c_perk.execute(
                                        '''INSERT OR IGNORE INTO active_perks
                                           (guild_id, user_id, perk_id, perk_name, perk_effect, perk_value, perk_type, expires_at)
                                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                        (self.guild_id, self.user_id, perk['id'], perk['name'], perk['effect'], perk['value'], perk['type'], expires_at)
                                    )

                                conn_perk.commit()
                                conn_perk.close()

                                selected_names = ", ".join([self.perks[idx]['name'] for idx in self.selected_perks])

                                if self.tier < self.total_tiers:
                                    confirm_embed = discord.Embed(
                                        title=f"✅ Tier {self.tier} Complete!",
                                        description=f"**Perks for Tier {self.tier}:**\n{selected_names}\n\n"
                                                    f"Get ready for **Tier {self.tier + 1}**...",
                                        color=discord.Color.green()
                                    )
                                    await btn_interaction.followup.send(embed=confirm_embed, ephemeral=False)

                                    try:
                                        if self.outer_self is None:
                                            await btn_interaction.followup.send("❌ Internal error: outer_self is None", ephemeral=True)
                                            return

                                        await asyncio.sleep(0.5)
                                        await self.outer_self.show_tier_perk_selection(interaction, self.guild_id, self.user_id, self.tier + 1, self.total_tiers)
                                    except AttributeError as ae:
                                        await btn_interaction.followup.send(f"❌ Method error: {str(ae)}", ephemeral=True)
                                    except Exception as e:
                                        await btn_interaction.followup.send(f"❌ Error continuing to next tier: {str(e)}", ephemeral=True)
                                else:
                                    final_embed = discord.Embed(
                                        title="🎉 Dragon Nest Setup Complete!",
                                        description=f"You've successfully recovered all your perks from Tiers 1-{self.total_tiers}!\n\n"
                                                    f"You're ready to continue your Dragon Nest journey!",
                                        color=discord.Color.gold()
                                    )
                                    await btn_interaction.followup.send(embed=final_embed, ephemeral=False)
                            except Exception as e:
                                await btn_interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
                                traceback.print_exc()

                    view = TierPerkSelectionView(guild_id, user_id, selected_perks, tier, upgrade_level, self)
                    await interaction.followup.send(embed=embed, view=view, ephemeral=False)

                except Exception as e:
                    await interaction.followup.send(f"❌ Error loading tier perks: {str(e)}", ephemeral=True)
                    traceback.print_exc()

            async def activate_nest(self, interaction: discord.Interaction):
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                c.execute('SELECT expires_at FROM raid_bosses WHERE guild_id = ? AND expires_at > ?',
                          (interaction.guild_id, int(time.time())))
                raid_active = c.fetchone()

                if raid_active:
                    await interaction.response.send_message(
                        f"❌ Dragon Nest is paused during Raid Boss battles!\n\n"
                        f"⚔️ A raid boss is currently active. Normal dragons aren't spawning.\n"
                        f"Focus on defeating the boss and try Dragon Nest afterwards!",
                        ephemeral=False
                    )
                    conn.close()
                    return

                c.execute('SELECT level, bounties_active, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                result = c.fetchone()
                current_level = result[0] if result else 0
                bounties_active = result[1] if result else None
                upgrade_level = result[2] if result else 0

                c.execute('SELECT active_until FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                active_result = c.fetchone()

                if active_result and active_result[0] > int(time.time()):
                    time_left = active_result[0] - int(time.time())
                    await interaction.response.send_message(
                        f"✅ Dragon Nest is already active!\n"
                        f"⏰ Time remaining: {format_time_remaining(time_left)}",
                        ephemeral=False
                    )
                    conn.close()
                    return

                c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                total_result = c.fetchone()
                total_dragons = total_result[0] if total_result and total_result[0] else 0

                if total_dragons < 100:
                    await interaction.response.send_message(
                        f"❌ You need at least **100 total dragons** to activate Dragon Nest!\n"
                        f"You currently have: **{total_dragons}** dragons\n\n"
                        f"Catch more dragons and try again!",
                        ephemeral=False
                    )
                    conn.close()
                    return

                bounties = []
                difficulty = LEVEL_BOUNTY_DIFFICULTY.get(current_level, 3)

                used_rarity_levels = set()
                used_targets = set()

                target_1 = max(2, int(difficulty * random.uniform(0.9, 1.1)))
                bounties.append({'type': 'catch_any', 'target': target_1, 'progress': 0, 'rarity_level': None})
                used_targets.add(target_1)

                target_2 = max(1, int((difficulty / 2.5) * random.uniform(0.9, 1.1)))
                rarity_level_1 = random.randint(1, 4)
                used_rarity_levels.add(rarity_level_1)
                bounties.append({'type': 'catch_rarity_or_higher', 'target': target_2, 'progress': 0, 'rarity_level': rarity_level_1})

                target_3 = max(1, int((difficulty / 2.5) * random.uniform(0.9, 1.1)))
                available_rarities = [r for r in range(1, 5) if r not in used_rarity_levels]
                if available_rarities:
                    rarity_level_2 = random.choice(available_rarities)
                else:
                    rarity_level_2 = (rarity_level_1 % 4) + 1
                bounties.append({'type': 'catch_rarity_or_higher', 'target': target_3, 'progress': 0, 'rarity_level': rarity_level_2})

                c.execute('UPDATE dragon_nest SET bounties_active = ? WHERE guild_id = ? AND user_id = ?',
                          (str(bounties), interaction.guild_id, interaction.user.id))

                duration_hours = 2
                duration = duration_hours * 3600
                end_time = int(time.time()) + duration

                c.execute('''INSERT INTO dragon_nest_active (guild_id, user_id, active_until)
                             VALUES (?, ?, ?)
                             ON CONFLICT(guild_id, user_id)
                             DO UPDATE SET active_until = ?''',
                          (interaction.guild_id, interaction.user.id, end_time, end_time))

                conn.commit()
                conn.close()

                rarity_names = {1: 'Uncommon', 2: 'Rare', 3: 'Epic', 4: 'Legendary', 5: 'Mythic'}
                bounty_list = ""
                for i, bounty in enumerate(bounties, 1):
                    target = bounty['target']
                    if bounty['type'] == 'catch_any':
                        bounty_list += f"📋 **Bounty {i}:** Catch {target} dragons\n"
                    elif bounty['type'] == 'catch_rarity_or_higher':
                        rarity_name = rarity_names.get(bounty['rarity_level'], 'Rare')
                        bounty_list += f"📋 **Bounty {i}:** Catch {target} {rarity_name} or higher dragons\n"

                c = sqlite3.connect('dragon_bot.db', timeout=120.0)
                cursor = c.cursor()
                cursor.execute('SELECT xp, bounties_completed FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                               (interaction.guild_id, interaction.user.id))
                nest_info = cursor.fetchone()
                bounties_completed = nest_info[1] if nest_info else 0
                c.close()

                level_name = LEVEL_NAMES.get(current_level, "Unknown")
                character = LEVEL_CHARACTERS.get(current_level, "None")
                lore_text = LEVEL_LORE.get(current_level, "Your journey continues...")

                updated_embed = discord.Embed(
                    title=f"🏰 {interaction.user.display_name}'s Dragon Nest",
                    description=f"**Level {current_level}: {level_name}** | Upgrade Tier: {upgrade_level}/5\n*{character}*\n\n✨ {lore_text}",
                    color=discord.Color.green()
                )

                thumbnail_url = LEVEL_THUMBNAILS.get(current_level)
                if thumbnail_url:
                    updated_embed.set_thumbnail(url=thumbnail_url)

                updated_embed.add_field(name="Total Bounties Completed", value=str(bounties_completed), inline=True)
                updated_embed.add_field(name="Current Level", value=f"{current_level}/10", inline=True)

                updated_embed.add_field(
                    name="🎯 Active Bounties",
                    value=f"✨ Complete all bounties to level up and choose a perk!\n"
                          f"⚠️ If you fail, you will be demoted!\n\n{bounty_list}",
                    inline=False
                )

                updated_embed.add_field(
                    name="⏰ Time Remaining",
                    value=format_time_remaining(duration),
                    inline=False
                )

                updated_embed.set_footer(text="Activate Dragon Nest to start bounties!")

                active_view = DragonNestView(is_active=True, guild_id=interaction.guild_id, user_id=interaction.user.id, current_level=current_level)
                await interaction.response.edit_message(embed=updated_embed, view=active_view)

            async def upgrade_nest(self, interaction: discord.Interaction):
                """Upgrade Dragon Nest"""
                await interaction.response.defer(ephemeral=False)

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                balance_result = c.fetchone()
                balance = balance_result[0] if balance_result else 0

                c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                upgrade_result = c.fetchone()
                current_upgrade_level = upgrade_result[0] if upgrade_result else 0

                conn.close()

                if current_upgrade_level >= 5:
                    embed = discord.Embed(
                        title="🏰 Dragon Nest Fully Upgraded",
                        description="Your Dragon Nest is already at **Maximum Level (V)**!\n\n"
                                    "✨ You have unlocked all perk rarities!\n"
                                    "Only **Legendary perks** will appear now.",
                        color=discord.Color.gold()
                    )

                    conn_check = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c_check = conn_check.cursor()

                    c_check.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                    (interaction.guild_id, interaction.user.id))
                    result = c_check.fetchone()
                    check_upgrade_level = result[0] if result else 0

                    c_check.execute('SELECT COUNT(*) FROM active_perks WHERE guild_id = ? AND user_id = ?',
                                    (interaction.guild_id, interaction.user.id))
                    check_active_perks = c_check.fetchone()[0]

                    conn_check.close()

                    has_missing_perks = check_upgrade_level > 0 and check_active_perks == 0

                    if has_missing_perks:
                        class MaxLevelView(discord.ui.View):
                            def __init__(self):
                                super().__init__(timeout=300)

                            @discord.ui.button(label="Claim Missing Perks", style=discord.ButtonStyle.blurple, emoji="🎁")
                            async def claim_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                                await btn_interaction.response.defer()

                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()

                                c.execute('SELECT level, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                          (btn_interaction.guild_id, btn_interaction.user.id))
                                result = c.fetchone()
                                current_level = result[0] if result else 0
                                upgrade_level = result[1] if result and len(result) > 1 else 0

                                c.execute('SELECT COUNT(*) FROM active_perks WHERE guild_id = ? AND user_id = ?',
                                          (btn_interaction.guild_id, btn_interaction.user.id))
                                active_perks_count = c.fetchone()[0]

                                conn.close()

                                if upgrade_level > 0 and active_perks_count == 0:
                                    allowed_rarities = DRAGONNEST_UPGRADES.get(upgrade_level, {}).get('allowed_rarities', [])
                                    available_perks = []
                                    for rarity in allowed_rarities:
                                        available_perks.extend(PERKS_POOL.get(rarity, []))

                                    random.shuffle(available_perks)
                                    selected_perks = available_perks[:10]

                                    perk_list = ""
                                    for i, perk in enumerate(selected_perks, 1):
                                        perk_list += f"{i}. **{perk['name']}** - {perk['effect']}\n"

                                    embed_recovery = discord.Embed(
                                        title="🎁 Recover Your Starting Perks",
                                        description=f"You have Upgrade Tier {upgrade_level} but no starting perks!\n\n"
                                                    f"Select **2 perks** that will be permanently active:\n\n{perk_list}",
                                        color=discord.Color.gold()
                                    )

                                    perk_options = [
                                        discord.SelectOption(
                                            label=perk['name'][:100],
                                            value=str(i),
                                            description=perk['effect'][:100]
                                        )
                                        for i, perk in enumerate(selected_perks)
                                    ]

                                    select_menu = discord.ui.Select(
                                        placeholder="Select 2 perks...",
                                        min_values=2,
                                        max_values=2,
                                        options=perk_options
                                    )

                                    selected_perk_list = []

                                    async def select_callback(select_interaction: discord.Interaction):
                                        nonlocal selected_perk_list
                                        selected_perk_list = [int(idx) for idx in select_interaction.data['values']]
                                        selected_names = ", ".join([selected_perks[idx]['name'] for idx in selected_perk_list])
                                        await select_interaction.response.send_message(f"✅ You selected: **{selected_names}**\n\nNow click **Confirm Selection** to activate your perks!", ephemeral=True)

                                    select_menu.callback = select_callback

                                    class RecoveryView(discord.ui.View):
                                        def __init__(self):
                                            super().__init__(timeout=300)
                                            self.add_item(select_menu)
                                            self.selected = selected_perk_list

                                        @discord.ui.button(label="Confirm Selection", style=discord.ButtonStyle.success, emoji="✅")
                                        async def confirm(self, confirm_interaction: discord.Interaction, button: discord.ui.Button):
                                            if confirm_interaction.user.id != btn_interaction.user.id:
                                                await confirm_interaction.response.send_message("This is not your selection!", ephemeral=True)
                                                return

                                            if len(selected_perk_list) != 2:
                                                await confirm_interaction.response.send_message("You must select exactly 2 perks!", ephemeral=True)
                                                return

                                            await confirm_interaction.response.defer()

                                            conn_perk = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                            c_perk = conn_perk.cursor()

                                            expires_at = int(datetime(2099, 12, 31).timestamp())

                                            for idx in selected_perk_list:
                                                perk = selected_perks[idx]
                                                c_perk.execute(
                                                    '''INSERT OR REPLACE INTO active_perks
                                                       (guild_id, user_id, perk_id, perk_name, perk_effect, perk_value, perk_type, expires_at)
                                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                                    (btn_interaction.guild_id, btn_interaction.user.id, perk['id'], perk['name'], perk['effect'], perk.get('value', 0), perk.get('type', 'upgrade'), expires_at)
                                                )

                                            conn_perk.commit()
                                            conn_perk.close()

                                            selected_names = ", ".join([selected_perks[idx]['name'] for idx in selected_perk_list])
                                            success_embed = discord.Embed(
                                                title="🎉 Perks Recovered!",
                                                description=f"Your starting perks are now permanently active:\n\n**{selected_names}**",
                                                color=discord.Color.green()
                                            )

                                            await confirm_interaction.followup.send(embed=success_embed, ephemeral=False)
                                            self.stop()

                                    recovery_view = RecoveryView()
                                    await btn_interaction.followup.send(embed=embed_recovery, view=recovery_view, ephemeral=False)

                        view = MaxLevelView()
                        await interaction.followup.send(embed=embed, view=view, ephemeral=False)
                    else:
                        await interaction.followup.send(embed=embed, ephemeral=False)
                    return

                next_upgrade_level = current_upgrade_level + 1
                upgrade_cost = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('cost', 0)
                next_upgrade_name = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('name', 'Unknown')

                if balance < upgrade_cost:
                    coins_needed = upgrade_cost - balance
                    embed = discord.Embed(
                        title="❌ Not Enough Coins",
                        description=f"You need **{upgrade_cost:,}** coins to upgrade your Dragon Nest.\n\n"
                                    f"💰 You have: **{int(balance):,}** coins\n"
                                    f"💸 You need: **{int(coins_needed):,}** more coins",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=False)
                    return

                current_rarities = DRAGONNEST_UPGRADES.get(current_upgrade_level, {}).get('allowed_rarities', [])
                next_rarities = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('allowed_rarities', [])

                rarity_emoji = {
                    "common": "⚪", "uncommon": "🟢", "rare": "🔵",
                    "epic": "🟣", "legendary": "🟡", "mythic": "🌟", "ultra": "✨"
                }

                current_perks = " ".join([rarity_emoji.get(r, r) + f" {r.capitalize()}" for r in current_rarities])
                next_perks = " ".join([rarity_emoji.get(r, r) + f" {r.capitalize()}" for r in next_rarities])

                embed = discord.Embed(
                    title=f"⬆️ Upgrade to {next_upgrade_name}",
                    description=f"Ready to upgrade your Dragon Nest?\n\n"
                                f"**Current Level:** Level {current_upgrade_level} ({DRAGONNEST_UPGRADES.get(current_upgrade_level, {}).get('name', 'Unknown')})\n"
                                f"**Current Perks:** {current_perks}\n\n"
                                f"**Next Level:** Level {next_upgrade_level} ({next_upgrade_name})\n"
                                f"**New Perks:** {next_perks}\n\n"
                                f"💰 **Cost:** {upgrade_cost:,} coins\n"
                                f"✅ **You have:** {int(balance):,} coins\n\n"
                                f"⚠️ **WARNING - COMPLETE HARD RESET ON UPGRADE:**\n"
                                f"When you upgrade, ALL of the following will be PERMANENTLY DELETED:\n"
                                f"🐉 All dragons\n"
                                f"📊 All market listings\n"
                                f"✨ All lucky charms\n"
                                f"📚 All skills (reset to Level 0)\n"
                                f"🏰 Dragon Nest level (reset to 0)\n"
                                f"📖 All collected perks\n"
                                f"💰 ALL COINS (balance will be 0)\n"
                                f"⏰ All dragonscales\n\n"
                                f"🔷 **Alpha Dragons WILL BE KEPT!**\n"
                                f"Please make sure this is intentional! This is a hard reset to start fresh with better perks.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="⚠️ This action CANNOT be undone! Click 'Confirm Upgrade' to proceed.")

                class UpgradeConfirmView(discord.ui.View):
                    def __init__(self, guild_id, user_id, next_level, cost):
                        super().__init__(timeout=180)
                        self.guild_id = guild_id
                        self.user_id = user_id
                        self.next_level = next_level
                        self.cost = cost

                    @discord.ui.button(label="Confirm Upgrade", style=discord.ButtonStyle.success, emoji="✅")
                    async def confirm_upgrade(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                        if btn_interaction.user.id != self.user_id:
                            await btn_interaction.response.send_message("This is not your upgrade!", ephemeral=True)
                            return

                        await btn_interaction.response.defer()

                        conn_upgrade = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c_upgrade = conn_upgrade.cursor()

                        c_upgrade.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        balance_check = c_upgrade.fetchone()
                        current_balance = balance_check[0] if balance_check else 0

                        if current_balance < self.cost:
                            await btn_interaction.followup.send(
                                "❌ Your balance has changed! You no longer have enough coins.",
                                ephemeral=False
                            )
                            conn_upgrade.close()
                            return

                        c_upgrade.execute('UPDATE users SET balance = 0 WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('UPDATE dragon_nest SET upgrade_level = ? WHERE guild_id = ? AND user_id = ?',
                                          (self.next_level, self.guild_id, self.user_id))
                        c_upgrade.execute('DELETE FROM user_dragons WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute(
                            'DELETE FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type NOT IN (?, ?)',
                            (self.guild_id, self.user_id, 'server_trophy', 'supporter_trophy')
                        )
                        c_upgrade.execute('DELETE FROM active_items WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('DELETE FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('DELETE FROM user_packs WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('DELETE FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('DELETE FROM dragonscale_event_log WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('DELETE FROM market_listings WHERE guild_id = ? AND seller_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('UPDATE dragon_nest SET level = 0, xp = 0 WHERE guild_id = ? AND user_id = ?',
                                          (self.guild_id, self.user_id))
                        c_upgrade.execute('DELETE FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type IN (?, ?)',
                                          (self.guild_id, self.user_id, 'knowledge_book', 'precision_stone'))

                        conn_upgrade.commit()
                        conn_upgrade.close()

                        await check_and_award_achievements(self.guild_id, self.user_id, bot=btn_interaction.client)

                        upgrade_name = DRAGONNEST_UPGRADES.get(self.next_level, {}).get('name', 'Unknown')
                        new_rarities = DRAGONNEST_UPGRADES.get(self.next_level, {}).get('allowed_rarities', [])
                        new_perks_str = " ".join([rarity_emoji.get(r, r) + f" {r.capitalize()}" for r in new_rarities])

                        success_embed = discord.Embed(
                            title="✨ Dragon Nest Upgraded!",
                            description=f"Your Dragon Nest has been upgraded to **{upgrade_name} (Level {self.next_level})**!\n\n"
                                        f"🎁 **New Available Perks:**\n{new_perks_str}\n\n"
                                        f"💰 Upgrade Cost: **{self.cost:,}** coins\n\n"
                                        f"⚠️ **COMPLETE HARD RESET APPLIED:**\n"
                                        f"🐉 All dragons deleted\n"
                                        f"📊 All market listings deleted\n"
                                        f"✨ All lucky charms deleted\n"
                                        f"📚 All skills reset to Level 0\n"
                                        f"🔷 **Alpha dragons KEPT!**\n"
                                        f"🏰 Dragon Nest level reset to 0\n"
                                        f"💰 Balance reset to 0 coins\n"
                                        f"⏰ All dragonscales deleted\n"
                                        f"🎉 Lower rarity perks will no longer appear in new selections!\n\n"
                                        f"You're starting fresh with better perks! 🚀",
                            color=discord.Color.green()
                        )

                        await btn_interaction.followup.send(embed=success_embed, ephemeral=False)

                        allowed_rarities = DRAGONNEST_UPGRADES.get(self.next_level, {}).get('allowed_rarities', [])
                        available_perks = []
                        for rarity in allowed_rarities:
                            available_perks.extend(PERKS_POOL.get(rarity, []))

                        random.shuffle(available_perks)
                        selected_perks = available_perks[:10]

                        conn_store = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c_store = conn_store.cursor()

                        c_store.execute('SELECT perks_json FROM pending_perks WHERE guild_id = ? AND user_id = ? AND level = 0',
                                        (self.guild_id, self.user_id))
                        existing_result = c_store.fetchone()

                        existing_upgrades = {}
                        if existing_result:
                            try:
                                existing_data = json.loads(existing_result[0])
                                existing_upgrades = existing_data.get('upgrade_tiers', {})
                            except:
                                existing_upgrades = {}

                        perks_to_store = [(rarity, perk) for rarity in allowed_rarities for perk in PERKS_POOL.get(rarity, []) if perk in selected_perks]

                        existing_upgrades[str(self.next_level)] = {
                            'perks': perks_to_store,
                            'rarity': allowed_rarities
                        }

                        c_store.execute('''INSERT OR REPLACE INTO pending_perks (guild_id, user_id, level, perks_json)
                                           VALUES (?, ?, ?, ?)''',
                                        (self.guild_id, self.user_id, 0, json.dumps({'upgrade_tiers': existing_upgrades})))
                        conn_store.commit()
                        conn_store.close()

                        perk_list = ""
                        for i, perk in enumerate(selected_perks, 1):
                            perk_list += f"{i}. **{perk['name']}** - {perk['effect']}\n"

                        perk_embed = discord.Embed(
                            title="🎁 Choose Your Starting Perks",
                            description=f"Select **2 perks** that will be permanently active!\n\n{perk_list}",
                            color=discord.Color.gold()
                        )
                        perk_embed.set_footer(text="You can choose 2 perks that will stay with you forever.")

                        class PerkSelectionView(discord.ui.View):
                            def __init__(self, guild_id, user_id, perks):
                                super().__init__(timeout=300)
                                self.guild_id = guild_id
                                self.user_id = user_id
                                self.perks = perks
                                self.selected_perks = []

                                perk_options = [
                                    discord.SelectOption(
                                        label=perk['name'][:100],
                                        value=str(i),
                                        description=perk['effect'][:100]
                                    )
                                    for i, perk in enumerate(perks)
                                ]

                                self.perk_select.options = perk_options

                            @discord.ui.select(placeholder="Select 2 perks...", min_values=2, max_values=2)
                            async def perk_select(self, interaction: discord.Interaction, select: discord.ui.Select):
                                self.selected_perks = [int(idx) for idx in select.values]
                                selected_names = ", ".join([self.perks[idx]['name'] for idx in self.selected_perks])
                                await interaction.response.send_message(f"✅ You selected: **{selected_names}**\n\nNow click **Confirm Selection** to activate your perks!", ephemeral=True)

                            @discord.ui.button(label="Confirm Selection", style=discord.ButtonStyle.success, emoji="✅")
                            async def confirm_perks(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                                try:
                                    if btn_interaction.user.id != self.user_id:
                                        await btn_interaction.response.send_message("This is not your selection!", ephemeral=True)
                                        return

                                    if len(self.selected_perks) != 2:
                                        await btn_interaction.response.send_message("You must select exactly 2 perks!", ephemeral=True)
                                        return

                                    await btn_interaction.response.defer()

                                    conn_perk = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                    c_perk = conn_perk.cursor()

                                    for perk_idx in self.selected_perks:
                                        perk = self.perks[perk_idx]
                                        expires_at = int(datetime(2099, 12, 31).timestamp())
                                        c_perk.execute(
                                            '''INSERT OR IGNORE INTO active_perks
                                               (guild_id, user_id, perk_id, perk_name, perk_effect, perk_value, perk_type, expires_at)
                                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                            (self.guild_id, self.user_id, perk['id'], perk['name'], perk['effect'], perk['value'], perk['type'], expires_at)
                                        )

                                    conn_perk.commit()
                                    conn_perk.close()

                                    selected_names = ", ".join([self.perks[idx]['name'] for idx in self.selected_perks])
                                    confirm_embed = discord.Embed(
                                        title="🎉 Perks Activated!",
                                        description=f"Your starting perks are now permanently active:\n\n**{selected_names}**",
                                        color=discord.Color.green()
                                    )

                                    await btn_interaction.followup.send(embed=confirm_embed, ephemeral=False)
                                    self.stop()
                                except Exception as e:
                                    await btn_interaction.followup.send(f"❌ Error confirming perks: {str(e)}", ephemeral=True)
                                    traceback.print_exc()

                        perk_view = PerkSelectionView(btn_interaction.guild_id, btn_interaction.user.id, selected_perks)
                        await btn_interaction.followup.send(embed=perk_embed, view=perk_view, ephemeral=False)

                    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
                    async def cancel_upgrade(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                        if btn_interaction.user.id != self.user_id:
                            await btn_interaction.response.send_message("This is not your upgrade!", ephemeral=True)
                            return

                        await btn_interaction.response.defer()

                        cancel_embed = discord.Embed(
                            title="Upgrade Cancelled",
                            description="Your Dragon Nest upgrade has been cancelled.",
                            color=discord.Color.red()
                        )

                        await btn_interaction.followup.send(embed=cancel_embed, ephemeral=False)

                view = UpgradeConfirmView(interaction.guild_id, interaction.user.id, next_upgrade_level, upgrade_cost)
                await interaction.followup.send(embed=embed, view=view, ephemeral=False)

            async def view_perks(self, interaction: discord.Interaction):
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                current_time = int(time.time())

                c.execute('''SELECT perk_name, perk_effect, expires_at FROM active_perks
                             WHERE guild_id = ? AND user_id = ? AND expires_at > ?''',
                          (interaction.guild_id, interaction.user.id, current_time))
                active_perks = c.fetchall()

                c.execute('''SELECT perk_name, perk_effect, rarity FROM user_perks
                             WHERE guild_id = ? AND user_id = ?''',
                          (interaction.guild_id, interaction.user.id))
                collected_perks = c.fetchall()

                c.execute('SELECT level, perks_activated_at_current_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                result = c.fetchone()
                current_level = result[0] if result else 0
                last_activation_level = result[1] if result and result[1] else 0

                perks_count = len(collected_perks)
                expected_perks = current_level
                missing_perks = expected_perks - perks_count

                conn.close()

                perk_embed = discord.Embed(
                    title="✨ Your Dragon Nest Perks",
                    color=discord.Color.purple()
                )

                if active_perks:
                    active_text = ""
                    for perk_name, perk_effect, expires_at in active_perks:
                        time_left = expires_at - current_time
                        is_permanent = time_left > (70 * 365.25 * 24 * 3600)
                        if is_permanent:
                            duration_str = "✨ PERMANENT"
                        else:
                            duration_str = f"⏰ {format_time_remaining(time_left)} remaining"
                        active_text += f"🔥 **{perk_name}**\n   *{perk_effect}*\n   {duration_str}\n\n"
                    perk_embed.add_field(name="🔥 Active Perks", value=active_text, inline=False)
                else:
                    perk_embed.add_field(name="🔥 Active Perks", value="No active perks", inline=False)

                if collected_perks:
                    collection_text = ""
                    rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                    for perk_name, perk_effect, rarity in collected_perks[:10]:
                        collection_text += f"{rarity_emoji.get(rarity, '⚪')} **{perk_name}**\n   *{perk_effect}*\n\n"
                    if len(collected_perks) > 10:
                        collection_text += f"*...and {len(collected_perks) - 10} more*"
                    perk_embed.add_field(name="📚 Collection", value=collection_text, inline=False)

                class ViewPerksActionsView(discord.ui.View):
                    def __init__(self, guild_id, user_id, current_level, last_activation_level, missing_perks, has_perks, original_view):
                        super().__init__(timeout=180)
                        self.guild_id = guild_id
                        self.user_id = user_id
                        self.current_level = current_level
                        self.last_activation_level = last_activation_level
                        self.missing_perks = missing_perks
                        self.has_perks = has_perks
                        self.original_view = original_view

                        if has_perks:
                            self._add_activate_button()
                        if missing_perks > 0:
                            self._add_claim_button()

                        self._add_back_button()

                    def _add_activate_button(self):
                        button = discord.ui.Button(label="Activate Perks", style=discord.ButtonStyle.green, emoji="🔥")
                        button.callback = self.activate_perks_button
                        self.add_item(button)

                    def _add_claim_button(self):
                        button = discord.ui.Button(label="Claim Missing Perks", style=discord.ButtonStyle.blurple, emoji="🎁")
                        button.callback = self.claim_missing_button
                        self.add_item(button)

                    def _add_back_button(self):
                        button = discord.ui.Button(label="Back", style=discord.ButtonStyle.gray, emoji="◀️")
                        button.callback = self.back_button
                        self.add_item(button)

                    async def activate_perks_button(self, btn_interaction: discord.Interaction):
                        if btn_interaction.user.id != self.user_id:
                            await btn_interaction.response.send_message("This is not your perk menu!", ephemeral=False)
                            return

                        if self.current_level == self.last_activation_level and self.current_level > 0:
                            await btn_interaction.response.send_message(
                                f"❌ You've already activated your perks at this level!\n\nLevel up or down and reach another level to activate them again.",
                                ephemeral=False
                            )
                            return

                        if not self.has_perks:
                            await btn_interaction.response.send_message(
                                "❌ You haven't collected any perks yet!\n\nComplete Dragon Nest bounties to earn perks!",
                                ephemeral=False
                            )
                            return

                        await btn_interaction.response.defer()

                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()

                        c.execute('''SELECT perk_id, perk_name, perk_effect, perk_value, rarity FROM user_perks
                                     WHERE guild_id = ? AND user_id = ?
                                     ORDER BY rarity DESC, perk_name''',
                                  (self.guild_id, self.user_id))
                        all_perks = c.fetchall()
                        conn.close()

                        if not all_perks:
                            await btn_interaction.followup.send("❌ No perks found!", ephemeral=False)
                            return

                        rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                        perk_list = ""
                        for perk_id, perk_name, perk_effect, perk_value, rarity in all_perks[:10]:
                            perk_list += f"{rarity_emoji.get(rarity, '⚪')} **{perk_name}**\n   *{perk_effect}*\n\n"

                        if len(all_perks) > 10:
                            perk_list += f"*...and {len(all_perks) - 10} more perks*"

                        preview_embed = discord.Embed(
                            title="✨ Your Collected Perks",
                            description=f"You have **{len(all_perks)}** perk(s) ready to activate:\n\n{perk_list}",
                            color=discord.Color.purple()
                        )
                        preview_embed.set_footer(text="Click 'Activate Now' to activate all perks for 3 hours!")

                        class ActivateNowView(discord.ui.View):
                            def __init__(self, guild_id, user_id, perks, current_level):
                                super().__init__(timeout=180)
                                self.guild_id = guild_id
                                self.user_id = user_id
                                self.perks = perks
                                self.current_level = current_level

                            @discord.ui.button(label="Activate Now", style=discord.ButtonStyle.green, emoji="🔥")
                            async def activate_now(self, act_interaction: discord.Interaction, button: discord.ui.Button):
                                if act_interaction.user.id != self.user_id:
                                    await act_interaction.response.send_message("This is not your perk selection!", ephemeral=False)
                                    return

                                await act_interaction.response.defer()

                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()

                                expires_at = int(time.time()) + 10800
                                activated_count = 0

                                for perk_id, perk_name, perk_effect, perk_value, rarity in self.perks:
                                    actual_perk_type = 'lucky'
                                    for _rarity_tier, _perk_list in PERKS_POOL.items():
                                        for _p in _perk_list:
                                            if _p['id'] == perk_id:
                                                actual_perk_type = _p.get('type', 'lucky')
                                                break
                                    c.execute('''INSERT INTO active_perks (guild_id, user_id, perk_id, perk_name, perk_effect, perk_value, perk_type, expires_at)
                                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                                 ON CONFLICT(guild_id, user_id, perk_id)
                                                 DO UPDATE SET expires_at = ?''',
                                              (self.guild_id, self.user_id, perk_id, perk_name,
                                               perk_effect, perk_value, actual_perk_type, expires_at, expires_at))
                                    activated_count += 1

                                c.execute('UPDATE dragon_nest SET perks_activated_at_current_level = ? WHERE guild_id = ? AND user_id = ?',
                                          (self.current_level, self.guild_id, self.user_id))

                                conn.commit()
                                conn.close()

                                rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
                                perk_list = ""
                                for perk_id, perk_name, perk_effect, perk_value, rarity in self.perks[:10]:
                                    perk_list += f"{rarity_emoji.get(rarity, '⚪')} **{perk_name}**\n   *{perk_effect}*\n\n"

                                if len(self.perks) > 10:
                                    perk_list += f"*...and {len(self.perks) - 10} more perks*"

                                success_embed = discord.Embed(
                                    title="✨ All Perks Activated!",
                                    description=f"You activated **{activated_count}** perk(s) for the next **3 hours**!\n\n{perk_list}",
                                    color=discord.Color.gold()
                                )
                                success_embed.set_footer(text="⏰ All perks will expire in 3 hours")

                                class SuccessBackView(discord.ui.View):
                                    def __init__(self, guild_id, user_id):
                                        super().__init__(timeout=180)
                                        self.guild_id = guild_id
                                        self.user_id = user_id

                                    @discord.ui.button(label="Back to Dragon Nest", style=discord.ButtonStyle.gray, emoji="🔙")
                                    async def back_to_dragon(self, back_interaction: discord.Interaction, button: discord.ui.Button):
                                        if back_interaction.user.id != self.user_id:
                                            await back_interaction.response.send_message("This is not your menu!", ephemeral=True)
                                            return

                                        await back_interaction.response.defer()

                                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                        c = conn.cursor()
                                        c.execute('SELECT level, xp, bounties_completed, bounties_active, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                                  (self.guild_id, self.user_id))
                                        result = c.fetchone()

                                        c.execute('SELECT active_until FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                                                  (self.guild_id, self.user_id))
                                        active_result = c.fetchone()
                                        conn.close()

                                        level = result[0] if result else 0
                                        bounties_completed = result[2] if result else 0
                                        bounties_active_data = result[3] if result else None
                                        upgrade_level = result[4] if result else 0

                                        level_name = LEVEL_NAMES.get(level, "Unknown")
                                        character = LEVEL_CHARACTERS.get(level, "None")
                                        lore_text = LEVEL_LORE.get(level, "Your journey continues...")

                                        current_time = int(time.time())
                                        is_active = active_result and active_result[0] > current_time
                                        time_left = (active_result[0] - current_time) if is_active else 0

                                        user = await back_interaction.client.fetch_user(self.user_id)
                                        username = user.display_name if user else "Unknown"

                                        embed = discord.Embed(
                                            title=f"🏰 {username}'s Dragon Nest",
                                            description=f"**Level {level}: {level_name}** | Upgrade Tier: {upgrade_level}/5\n*{character}*\n\n✨ {lore_text}",
                                            color=discord.Color.green() if is_active else discord.Color.purple()
                                        )

                                        thumbnail_url = LEVEL_THUMBNAILS.get(level)
                                        if thumbnail_url:
                                            embed.set_thumbnail(url=thumbnail_url)

                                        embed.add_field(name="Total Bounties Completed", value=str(bounties_completed), inline=True)
                                        embed.add_field(name="Current Level", value=f"{level}/10", inline=True)

                                        if is_active and bounties_active_data:
                                            bounties = ast.literal_eval(bounties_active_data)
                                            bounty_text = ""
                                            for i, bounty in enumerate(bounties, 1):
                                                progress = bounty['progress']
                                                target = bounty['target']
                                                if bounty['type'] == 'catch_any':
                                                    bounty_text += f"📋 **Bounty {i}:** Catch {target} dragons ({progress}/{target})\n"
                                                elif bounty['type'] == 'catch_rarity_or_higher':
                                                    rarity_names = {1: 'Uncommon', 2: 'Rare', 3: 'Epic', 4: 'Legendary', 5: 'Mythic'}
                                                    rarity_name = rarity_names.get(bounty.get('rarity_level'), 'Rare')
                                                    bounty_text += f"📋 **Bounty {i}:** Catch {target} {rarity_name}+ dragons ({progress}/{target})\n"

                                            embed.add_field(name="🎯 Active Bounties", value=bounty_text, inline=False)
                                            embed.add_field(name="⏰ Time Remaining", value=format_time_remaining(time_left), inline=False)

                                        embed.set_footer(text="Activate Dragon Nest to start bounties!")

                                        new_view = DragonNestView(is_active=is_active, guild_id=self.guild_id, user_id=self.user_id, current_level=level)
                                        await back_interaction.followup.edit_message(
                                            message_id=back_interaction.message.id,
                                            embed=embed,
                                            view=new_view
                                        )

                                success_view = SuccessBackView(self.guild_id, self.user_id)
                                await act_interaction.followup.edit_message(
                                    message_id=btn_interaction.message.id,
                                    embed=success_embed,
                                    view=success_view
                                )

                        activate_view = ActivateNowView(self.guild_id, self.user_id, all_perks, self.current_level)
                        await btn_interaction.followup.edit_message(
                            message_id=btn_interaction.message.id,
                            embed=preview_embed,
                            view=activate_view
                        )

                    async def claim_missing_button(self, btn_interaction: discord.Interaction):
                        if btn_interaction.user.id != self.user_id:
                            await btn_interaction.response.send_message("This is not your perk menu!", ephemeral=False)
                            return

                        if self.missing_perks <= 0:
                            await btn_interaction.response.send_message(
                                "✅ You don't have any missing perks!\n\n"
                                f"You've collected all perks for your **Level {self.current_level}** account.",
                                ephemeral=False
                            )
                            return

                        temp_view = DragonNestView(is_active=False, guild_id=self.guild_id, user_id=self.user_id, current_level=self.current_level)
                        await temp_view.claim_missing_perks(btn_interaction)

                    async def back_button(self, btn_interaction: discord.Interaction):
                        if btn_interaction.user.id != self.user_id:
                            await btn_interaction.response.send_message("This is not your menu!", ephemeral=False)
                            return

                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()
                        c.execute('SELECT level, xp, bounties_completed, bounties_active, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                  (self.guild_id, self.user_id))
                        result = c.fetchone()

                        c.execute('SELECT active_until FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                                  (self.guild_id, self.user_id))
                        active_result = c.fetchone()
                        conn.close()

                        level = result[0] if result else 0
                        bounties_completed = result[2] if result else 0
                        bounties_active_data = result[3] if result else None
                        upgrade_level = result[4] if result else 0

                        level_name = LEVEL_NAMES.get(level, "Unknown")
                        character = LEVEL_CHARACTERS.get(level, "None")
                        lore_text = LEVEL_LORE.get(level, "Your journey continues...")

                        current_time = int(time.time())
                        is_active = active_result and active_result[0] > current_time
                        time_left = (active_result[0] - current_time) if is_active else 0

                        user = await btn_interaction.client.fetch_user(self.user_id)
                        username = user.display_name if user else "Unknown"

                        embed = discord.Embed(
                            title=f"🏰 {username}'s Dragon Nest",
                            description=f"**Level {level}: {level_name}** | Upgrade Tier: {upgrade_level}/5\n*{character}*\n\n✨ {lore_text}",
                            color=discord.Color.green() if is_active else discord.Color.purple()
                        )

                        thumbnail_url = LEVEL_THUMBNAILS.get(level)
                        if thumbnail_url:
                            embed.set_thumbnail(url=thumbnail_url)

                        embed.add_field(name="Total Bounties Completed", value=str(bounties_completed), inline=True)
                        embed.add_field(name="Current Level", value=f"{level}/10", inline=True)

                        if is_active and bounties_active_data:
                            bounties = ast.literal_eval(bounties_active_data)
                            bounty_text = ""
                            for i, bounty in enumerate(bounties, 1):
                                progress = bounty['progress']
                                target = bounty['target']
                                if bounty['type'] == 'catch_any':
                                    bounty_text += f"📋 **Bounty {i}:** Catch {target} dragons ({progress}/{target})\n"
                                elif bounty['type'] == 'catch_rarity_or_higher':
                                    rarity_names = {1: 'Uncommon', 2: 'Rare', 3: 'Epic', 4: 'Legendary', 5: 'Mythic'}
                                    rarity_name = rarity_names.get(bounty.get('rarity_level'), 'Rare')
                                    bounty_text += f"📋 **Bounty {i}:** Catch {target} {rarity_name}+ dragons ({progress}/{target})\n"

                            embed.add_field(name="🎯 Active Bounties", value=bounty_text, inline=False)
                            embed.add_field(name="⏰ Time Remaining", value=format_time_remaining(time_left), inline=False)

                        embed.set_footer(text="Activate Dragon Nest to start bounties!")

                        new_view = DragonNestView(is_active=is_active, guild_id=self.guild_id, user_id=self.user_id, current_level=level)
                        await btn_interaction.response.edit_message(embed=embed, view=new_view)

                view = ViewPerksActionsView(interaction.guild_id, interaction.user.id, current_level, last_activation_level, missing_perks, len(collected_perks) > 0, self)
                await interaction.response.edit_message(embed=perk_embed, view=view)

            async def help_button(self, interaction: discord.Interaction):
                help_embed = discord.Embed(
                    title="🏰 Dragon Nest Help",
                    description="**What is Dragon Nest?**\n"
                                "Your Dragon Nest levels up separately from Dragonpass!\n\n"
                                "**Nest Levels (0-10):**\n"
                                "• Progress through bounties and challenges\n"
                                "• Each level unlocks new perks and features\n"
                                "• Max Level: 10 (Primordial)\n\n"
                                "**Upgrade Tiers (0-5):**\n"
                                "• Separate from Nest Level\n"
                                "• Unlock better perk rarities\n"
                                "• Tier 0: Common/Uncommon\n"
                                "• Tier 1-4: Progressively rarer perks\n"
                                "• Tier 5: Access to Legendary perks!\n\n"
                                "**Perks:**\n"
                                "• Unlock powerful perks as you level up\n"
                                "• Each level gives you a random perk\n"
                                "• Higher upgrade tiers = Better perk options!\n\n"
                                "**Progression:**\n"
                                "• Complete bounties to level up your nest\n"
                                "• Gather resources to upgrade your nest tier",
                    color=discord.Color.blue()
                )

                outer_view = self

                class HelpBackView(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=180)

                    @discord.ui.button(label="Back", style=discord.ButtonStyle.gray, emoji="◀️")
                    async def back_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                        if btn_interaction.user.id != outer_view.user_id:
                            await btn_interaction.response.send_message("This is not your menu!", ephemeral=True)
                            return

                        await btn_interaction.response.defer()

                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()
                        c.execute('SELECT level, xp, bounties_completed, bounties_active, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                                  (outer_view.guild_id, outer_view.user_id))
                        result = c.fetchone()
                        c.execute('SELECT active_until FROM dragon_nest_active WHERE guild_id = ? AND user_id = ?',
                                  (outer_view.guild_id, outer_view.user_id))
                        active_result = c.fetchone()
                        conn.close()

                        level = result[0] if result else 0
                        bounties_completed = result[2] if result else 0
                        bounties_active_data = result[3] if result else None
                        upgrade_level = result[4] if result else 0

                        current_time = int(time.time())
                        is_active = active_result and active_result[0] > current_time
                        time_left = (active_result[0] - current_time) if is_active else 0

                        level_name = LEVEL_NAMES.get(level, "Unknown")
                        character = LEVEL_CHARACTERS.get(level, "None")
                        lore_text = LEVEL_LORE.get(level, "Your journey continues...")

                        user = await btn_interaction.client.fetch_user(outer_view.user_id)
                        username = user.display_name if user else "Unknown"

                        embed = discord.Embed(
                            title=f"🏰 {username}'s Dragon Nest",
                            description=f"**Level {level}: {level_name}** | Upgrade Tier: {upgrade_level}/5\n*{character}*\n\n✨ {lore_text}",
                            color=discord.Color.green() if is_active else discord.Color.purple()
                        )

                        thumbnail_url = LEVEL_THUMBNAILS.get(level)
                        if thumbnail_url:
                            embed.set_thumbnail(url=thumbnail_url)

                        embed.add_field(name="Total Bounties Completed", value=str(bounties_completed), inline=True)
                        embed.add_field(name="Current Level", value=f"{level}/10", inline=True)

                        if is_active and bounties_active_data:
                            bounties = ast.literal_eval(bounties_active_data)
                            bounty_text = ""
                            for i, bounty in enumerate(bounties, 1):
                                progress = bounty['progress']
                                target = bounty['target']
                                if bounty['type'] == 'catch_any':
                                    bounty_text += f"📋 **Bounty {i}:** Catch {target} dragons ({progress}/{target})\n"
                                elif bounty['type'] == 'catch_rarity_or_higher':
                                    rarity_names = {1: 'Uncommon', 2: 'Rare', 3: 'Epic', 4: 'Legendary', 5: 'Mythic'}
                                    rarity_name = rarity_names.get(bounty.get('rarity_level'), 'Rare')
                                    bounty_text += f"📋 **Bounty {i}:** Catch {target} {rarity_name}+ dragons ({progress}/{target})\n"
                            embed.add_field(name="🎯 Active Bounties", value=bounty_text, inline=False)
                            embed.add_field(name="⏰ Time Remaining", value=format_time_remaining(time_left), inline=False)

                        embed.set_footer(text="Activate Dragon Nest to start bounties!")

                        new_view = DragonNestView(is_active=is_active, guild_id=outer_view.guild_id, user_id=outer_view.user_id, current_level=level)
                        await btn_interaction.followup.edit_message(message_id=btn_interaction.message.id, embed=embed, view=new_view)

                await interaction.response.edit_message(embed=help_embed, view=HelpBackView())

        view = DragonNestView(is_active=is_active, guild_id=interaction.guild_id, user_id=interaction.user.id, current_level=level)
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(DragonNestCog(bot))
