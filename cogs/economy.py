"""
cogs/economy.py - Economy commands for DragonBot.
Contains: balance, casino, shop, daily, vote, coinflip.
Extracted verbatim from bot.py.
"""

import asyncio
import random
import sqlite3
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import DRAGONNEST_UPGRADES, CONSUMABLE_ITEMS, MYSTERY_BOX_POOL, DICE_OF_FATE_EFFECTS
from database import get_user, update_balance, get_active_item, is_player_softlocked
from state import active_luckycharms, active_usable_items
from utils import format_time_remaining, check_dragonpass_quests


class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==================== BALANCE ====================

    @app_commands.command(name="bal", description="Check your balance")
    async def balance(self, interaction: discord.Interaction, user: discord.User = None):
        target_user = user or interaction.user
        user_data = get_user(interaction.guild_id, target_user.id)

        embed = discord.Embed(
            title=f"💰 {target_user.display_name}'s Balance",
            description=f"**Coins:** {int(user_data[2])} 🪙\n\n"
                        f"**What can I do with coins?**\n"
                        f"• `/casino <amount>` - Gamble (50/50 chance)\n"
                        f"• `/shop` - Buy packs & boosts\n"
                        f"• `/dragonscale <minutes>` - Start server-wide spawn event!\n"
                        f"• `/breed` - Breed dragons for new types\n"
                        f"• Earn from catching dragons!",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    # ==================== CASINO ====================

    @app_commands.command(name="casino", description="Gamble your coins (50/50 chance to double or lose)")
    async def casino(self, interaction: discord.Interaction, amount: int):
        """Casino gambling system"""
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
                            f"You're **softlocked** from gambling until you upgrade.\n"
                            f"Use `/dragonnest` to upgrade!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=softlock_embed, delete_after=5)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=False)
            return

        if amount < 100:
            await interaction.response.send_message("❌ Minimum bet is 100 coins! 🪙", ephemeral=False)
            return

        user_data = get_user(interaction.guild_id, interaction.user.id)
        balance = user_data[2]

        if amount > balance:
            await interaction.response.send_message(f"❌ You don't have enough coins! Balance: {int(balance)} 🪙", ephemeral=False)
            return

        # Animation stages
        stages = [
            ("🎰 Spinning...", "🟥🟥🟥"),
            ("🎰 Spinning...", "🟦🟥🟥"),
            ("🎰 Spinning...", "🟦🟦🟥"),
            ("🎰 Spinning...", "🟦🟦🟦")
        ]

        # Start animation
        embed = discord.Embed(
            title=stages[0][0],
            description=f"**Bet:** {int(amount)} 🪙\n\n{stages[0][1]}",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed)

        # Animate through stages
        for i in range(1, len(stages)):
            await asyncio.sleep(0.7)
            embed.title = stages[i][0]
            embed.description = f"**Bet:** {int(amount)} 🪙\n\n{stages[i][1]}"
            await interaction.edit_original_response(embed=embed)

        await asyncio.sleep(0.7)

        # 50/50 chance, +10% if Lucky Dice active
        has_lucky_dice = get_active_item(interaction.guild_id, interaction.user.id, 'lucky_dice')
        win_chance = 0.5
        if has_lucky_dice:
            win_chance = 0.6  # 60% win chance
        win = random.random() < win_chance

        if win:
            await asyncio.to_thread(update_balance, interaction.guild_id, interaction.user.id, amount)  # Add winnings
            new_balance = balance + amount

            lucky_note = "\n🎰 **Lucky Dice Active!** (+10% bonus win chance)" if has_lucky_dice else ""
            final_embed = discord.Embed(
                title="🎰 Casino - YOU WIN!",
                description=f"🎉🎉🎉\n\n**Bet:** {int(amount)} 🪙\n**Won:** +{int(amount)} 🪙\n\n**New Balance:** {int(new_balance)} 🪙{lucky_note}",
                color=discord.Color.green()
            )
        else:
            await asyncio.to_thread(update_balance, interaction.guild_id, interaction.user.id, -amount)  # Subtract loss
            new_balance = balance - amount

            lucky_note = "\n🎰 **Lucky Dice Active!** (+10% bonus win chance)" if has_lucky_dice else ""
            final_embed = discord.Embed(
                title="🎰 Casino - YOU LOSE!",
                description=f"💀💀💀\n\n**Bet:** {int(amount)} 🪙\n**Lost:** -{int(amount)} 🪙\n\n**New Balance:** {int(new_balance)} 🪙{lucky_note}",
                color=discord.Color.red()
            )

        await interaction.edit_original_response(embed=final_embed)

        # Track for dragonpass quest
        await asyncio.to_thread(check_dragonpass_quests, interaction.guild_id, interaction.user.id, 'use_casino', 1)

    # ==================== SHOP ====================

    @app_commands.command(name="shop", description="Buy packs and boosts with coins")
    async def shop(self, interaction: discord.Interaction):
        """Shop to buy packs and items"""
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
                            f"You're **softlocked** from using the shop until you upgrade.\n"
                            f"Use `/dragonnest` to upgrade!",
                color=discord.Color.red()
            )
            msg = await interaction.followup.send(embed=softlock_embed)
            await asyncio.sleep(5)
            try:
                await msg.delete()
            except:
                pass
            return

        user_data = get_user(interaction.guild_id, interaction.user.id)
        balance = user_data[2]
        guild_id = interaction.guild_id

        # ── All item data (single source of truth) ──────────────────────────
        items_data = {
            'pack_wooden':                   {'name': 'Wooden Pack',        'price': 500,    'emoji': '<:woodenchest:1446170002708238476>'},
            'pack_stone':                    {'name': 'Stone Pack',         'price': 1000,   'emoji': '<:stonechest:1446169958265389247>'},
            'pack_bronze':                   {'name': 'Bronze Pack',        'price': 1500,   'emoji': '<:bronzechest:1446169758599745586>'},
            'boost_dragonscale':             {'name': 'Dragonscale (2min)', 'price': 20000,  'emoji': '<:dragonscale:1446278170998341693>', 'duration': 120},
            'boost_premium':                 {'name': 'Dragonscale (10min)','price': 100000, 'emoji': '<:dragonscale:1446278170998341693>', 'duration': 600},
            'item_luckycharm':               {'name': 'Lucky Charm',        'price': 15000,  'emoji': '🍀'},
            'item_dna':                      {'name': 'DNA Sample',         'price': 12500,  'emoji': '🧬'},
            'usable_night_vision':           {'name': 'Night Vision',       'price': 50000,  'emoji': '🌙'},
            'usable_lucky_dice':             {'name': 'Lucky Dice',         'price': 10000,  'emoji': '🎰'},
            'usable_gold_rush':              {'name': 'Gold Rush',          'price': 8000,   'emoji': '✨'},
            'consumable_mystery_box':        {'name': 'Mystery Box',        'price': 5000,   'emoji': '❓'},
            'consumable_dice_of_fate':       {'name': 'Dice of Fate',       'price': 3000,   'emoji': '🎲'},
            'consumable_fast_travel_scroll': {'name': 'Fast Travel Scroll', 'price': 8000,   'emoji': '📜'},
            'consumable_double_loot_bag':    {'name': 'Double Loot Bag',    'price': 6000,   'emoji': '🎒'},
            'consumable_war_drum':           {'name': 'War Drum',           'price': 4000,   'emoji': '🥁'},
            'consumable_shield_rune':        {'name': 'Shield Rune',        'price': 3500,   'emoji': '🔷'},
            'consumable_server_trophy':      {'name': 'Server Trophy',      'price': 25000,  'emoji': '🥇'},
        }

        # ── Category definitions ─────────────────────────────────────────────
        categories = {
            'packs': {
                'label': 'Dragon Packs', 'emoji': '📦', 'color': 0xA0522D,
                'description': 'Open packs to discover new dragons! Use `/openpacks` to open them.',
                'lines': [
                    '<:woodenchest:1446170002708238476> **Wooden Pack** — 500 🪙',
                    '<:stonechest:1446169958265389247> **Stone Pack** — 1,000 🪙',
                    '<:bronzechest:1446169758599745586> **Bronze Pack** — 1,500 🪙',
                ],
                'options': [
                    discord.SelectOption(label="Wooden Pack", description="500 🪙",   emoji="<:woodenchest:1446170002708238476>", value="pack_wooden"),
                    discord.SelectOption(label="Stone Pack",  description="1,000 🪙", emoji="<:stonechest:1446169958265389247>",  value="pack_stone"),
                    discord.SelectOption(label="Bronze Pack", description="1,500 🪙", emoji="<:bronzechest:1446169758599745586>", value="pack_bronze"),
                ],
            },
            'boosts': {
                'label': 'Spawn Boosts', 'emoji': '⚡', 'color': 0xFFD700,
                'description': 'Trigger server-wide dragon spawn events for everyone!',
                'lines': [
                    '⚡ **Dragonscale (2min)** — 20,000 🪙',
                    '   └─ Server-wide spawn event for 2 minutes',
                    '⚡ **Dragonscale (10min)** — 100,000 🪙',
                    '   └─ Server-wide spawn event for 10 minutes',
                ],
                'options': [
                    discord.SelectOption(label="Dragonscale (2min)",  description="20,000 🪙",  emoji="<:dragonscale:1446278170998341693>", value="boost_dragonscale"),
                    discord.SelectOption(label="Dragonscale (10min)", description="100,000 🪙", emoji="<:dragonscale:1446278170998341693>", value="boost_premium"),
                ],
            },
            'special': {
                'label': 'Special Items', 'emoji': '🎁', 'color': 0x00CC77,
                'description': 'Powerful items that go to your inventory for later use.',
                'lines': [
                    '🍀 **Lucky Charm** — 15,000 🪙',
                    '   └─ 2x Catch Rate for 30 min — activate in `/inventory`',
                    '🧬 **DNA Sample** — 12,500 🪙',
                    '   └─ Clone any dragon you own when breeding',
                ],
                'options': [
                    discord.SelectOption(label="Lucky Charm", description="15,000 🪙 - 2x catch 30min", emoji="🍀", value="item_luckycharm"),
                    discord.SelectOption(label="DNA Sample",  description="12,500 🪙 - Clone a dragon", emoji="🧬", value="item_dna"),
                ],
            },
            'active': {
                'label': 'Active Boosts', 'emoji': '💎', 'color': 0x9B59B6,
                'description': 'Timed personal boosts — activate from `/inventory`.',
                'lines': [
                    '🌙 **Night Vision** — 50,000 🪙',
                    '   └─ +50% spawn rarity (20:00–08:00, once per night)',
                    '🎰 **Lucky Dice** — 10,000 🪙',
                    '   └─ +10% casino win chance for 30 minutes',
                    '✨ **Gold Rush** — 8,000 🪙',
                    '   └─ +50% coin drops when catching dragons for 1 hour',
                ],
                'options': [
                    discord.SelectOption(label="Night Vision", description="50,000 🪙 - +50% rarity (night)", emoji="🌙", value="usable_night_vision"),
                    discord.SelectOption(label="Lucky Dice",   description="10,000 🪙 - +10% casino (30min)", emoji="🎰", value="usable_lucky_dice"),
                    discord.SelectOption(label="Gold Rush",    description="8,000 🪙 - +50% coin drops (1h)", emoji="✨", value="usable_gold_rush"),
                ],
            },
            'raid': {
                'label': 'Raid Items', 'emoji': '⚔️', 'color': 0xE74C3C,
                'description': 'Items that help you in Raid Boss battles.',
                'lines': [
                    '🥁 **War Drum** — 4,000 🪙',
                    '   └─ +10% damage on your next raid attack (auto-consumed)',
                    '🔷 **Shield Rune** — 3,500 🪙',
                    '   └─ 300 🪙 consolation if your raid tier escapes (auto-consumed)',
                ],
                'options': [
                    discord.SelectOption(label="War Drum",    description="4,000 🪙 - +10% next raid attack",    emoji="🥁", value="consumable_war_drum"),
                    discord.SelectOption(label="Shield Rune", description="3,500 🪙 - consolation if raid fails", emoji="🔷", value="consumable_shield_rune"),
                ],
            },
            'consumables': {
                'label': 'Consumables', 'emoji': '🎮', 'color': 0x3498DB,
                'description': 'One-use items with varied effects. Open/roll from `/inventory`.',
                'lines': [
                    '❓ **Mystery Box** — 5,000 🪙',
                    '   └─ Random item inside — open in `/inventory`',
                    '🎲 **Dice of Fate** — 3,000 🪙',
                    '   └─ Random effect (good or bad!) — roll in `/inventory`',
                    '📜 **Fast Travel Scroll** — 8,000 🪙',
                    '   └─ Halves your next adventure duration',
                    '🎒 **Double Loot Bag** — 6,000 🪙',
                    '   └─ Doubles item drops from your next adventure',
                ],
                'options': [
                    discord.SelectOption(label="Mystery Box",        description="5,000 🪙 - Random item",        emoji="❓", value="consumable_mystery_box"),
                    discord.SelectOption(label="Dice of Fate",       description="3,000 🪙 - Random effect",      emoji="🎲", value="consumable_dice_of_fate"),
                    discord.SelectOption(label="Fast Travel Scroll", description="8,000 🪙 - Halve adventure",    emoji="📜", value="consumable_fast_travel_scroll"),
                    discord.SelectOption(label="Double Loot Bag",    description="6,000 🪙 - 2x adventure items", emoji="🎒", value="consumable_double_loot_bag"),
                ],
            },
            'cosmetics': {
                'label': 'Cosmetics', 'emoji': '🥇', 'color': 0xF1C40F,
                'description': 'Purely cosmetic items displayed in your profile.',
                'lines': [
                    '🥇 **Server Trophy** — 25,000 🪙',
                    '   └─ Displayed as trophies in your `/stats` profile',
                ],
                'options': [
                    discord.SelectOption(label="Server Trophy", description="25,000 🪙 - Shown in /stats", emoji="🥇", value="consumable_server_trophy"),
                ],
            },
        }

        # ── Main shop overview embed ─────────────────────────────────────────
        def build_main_embed(bal: float) -> discord.Embed:
            lines = "\n".join(
                f"{cat['emoji']} **{cat['label']}** — {cat['description']}"
                for cat in categories.values()
            )
            e = discord.Embed(
                title="🏪 Dragon Emporium",
                description=f"**Your Balance:** {int(bal):,} 🪙\n\n{lines}",
                color=0x5865F2
            )
            e.set_footer(text="Select a category below to browse items and buy.")
            return e

        # ── Category embed ───────────────────────────────────────────────────
        def build_category_embed(cat_key: str, bal: float) -> discord.Embed:
            cat = categories[cat_key]
            e = discord.Embed(
                title=f"{cat['emoji']} {cat['label']}",
                description=f"**Your Balance:** {int(bal):,} 🪙\n\n{cat['description']}\n\n" + "\n".join(cat['lines']),
                color=cat['color']
            )
            e.set_footer(text="Select an item below to purchase.")
            return e

        # ── Purchase handler (same logic as before, extracted) ───────────────
        async def handle_purchase(sel_interaction: discord.Interaction, selected: str):
            category, item = selected.split('_', 1)
            item_info = items_data[selected]
            price = item_info['price']

            ud = get_user(sel_interaction.guild_id, sel_interaction.user.id)
            bal = ud[2]

            if bal < price:
                await sel_interaction.response.send_message(
                    f"❌ You need **{price:,}** 🪙 but only have **{int(bal):,}** 🪙!",
                    ephemeral=False
                )
                return

            # Create quantity modal
            class QuantityModal(discord.ui.Modal, title="How many do you want to buy?"):
                quantity = discord.ui.TextInput(
                    label="Quantity",
                    placeholder="Enter amount",
                    required=True,
                    min_length=1,
                    max_length=4
                )

                async def on_submit(self, modal_interaction: discord.Interaction):
                    try:
                        qty = int(self.quantity.value)
                        if qty < 1:
                            await modal_interaction.response.send_message("❌ Quantity must be at least 1!", ephemeral=True)
                            return

                        total_price = price * qty
                        user_data = get_user(interaction.guild_id, modal_interaction.user.id)
                        balance = user_data[2]

                        if balance < total_price:
                            await modal_interaction.response.send_message(
                                f"❌ You need **{total_price:,}** 🪙 but only have **{int(balance):,}** 🪙!",
                                ephemeral=True
                            )
                            return

                        # Process purchase based on category
                        if category == 'pack':
                            await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, -total_price)
                            try:
                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()
                                c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                             VALUES (?, ?, ?, ?)
                                             ON CONFLICT(guild_id, user_id, pack_type)
                                             DO UPDATE SET count = count + ?''',
                                          (interaction.guild_id, modal_interaction.user.id, item, qty, qty))
                                conn.commit()
                                conn.close()
                            except Exception as e:
                                await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, total_price)
                                await modal_interaction.response.send_message(f"❌ Failed to add packs: {e}", ephemeral=True)
                                return
                            embed = discord.Embed(
                                title="✅ Packs Purchased!",
                                description=f"{item_info['emoji']} **{qty}x {item_info['name']}** added to inventory!\n\n"
                                            f"**Total Cost:** {total_price:,} 🪙\n"
                                            f"**New Balance:** {int(balance - total_price):,} 🪙\n\n"
                                            f"Use `/openpacks` to open them!",
                                color=discord.Color.green()
                            )
                            await modal_interaction.response.send_message(embed=embed, ephemeral=False)

                        elif category == 'boost':
                            await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, -total_price)
                            minutes_to_add = (item_info['duration'] // 60) * qty
                            try:
                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()
                                c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                                          (interaction.guild_id, modal_interaction.user.id))
                                existing = c.fetchone()
                                if existing:
                                    c.execute('UPDATE dragonscales SET minutes = minutes + ? WHERE guild_id = ? AND user_id = ?',
                                              (minutes_to_add, interaction.guild_id, modal_interaction.user.id))
                                else:
                                    c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?)',
                                              (interaction.guild_id, modal_interaction.user.id, minutes_to_add))
                                conn.commit()
                                conn.close()
                            except Exception as e:
                                await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, total_price)
                                await modal_interaction.response.send_message(f"❌ Failed to add dragonscale: {e}", ephemeral=True)
                                return
                            embed = discord.Embed(
                                title="✅ Dragonscale Minutes Purchased!",
                                description=f"⚡ **{minutes_to_add} minutes** added to your inventory!\n\n"
                                            f"**Total Cost:** {total_price:,} 🪙\n"
                                            f"**New Balance:** {int(balance - total_price):,} 🪙\n\n"
                                            f"💡 Use the button in `/inventory` to activate!",
                                color=discord.Color.green()
                            )
                            await modal_interaction.response.send_message(embed=embed, ephemeral=False)

                        elif category == 'item':
                            await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, -total_price)
                            if item == 'luckycharm':
                                try:
                                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                    c = conn.cursor()
                                    c.execute('''INSERT INTO user_luckycharms (guild_id, user_id, count)
                                                 VALUES (?, ?, ?)
                                                 ON CONFLICT(guild_id, user_id)
                                                 DO UPDATE SET count = count + ?''',
                                              (interaction.guild_id, modal_interaction.user.id, qty, qty))
                                    conn.commit()
                                    conn.close()
                                except Exception as e:
                                    await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, total_price)
                                    await modal_interaction.response.send_message(f"❌ Failed to add Lucky Charm: {e}", ephemeral=True)
                                    return
                                embed = discord.Embed(
                                    title="✅ Lucky Charms Purchased!",
                                    description=f"🍀 **{qty}x Lucky Charm** added to inventory!\n\n"
                                                f"**Effect:** 2x Catch Rate for 30 minutes\n"
                                                f"**Total Cost:** {total_price:,} 🪙\n"
                                                f"**New Balance:** {int(balance - total_price):,} 🪙\n\n"
                                                f"💡 Use the button in `/inventory` to activate!",
                                    color=discord.Color.green()
                                )
                                await modal_interaction.response.send_message(embed=embed, ephemeral=False)
                            elif item == 'dna':
                                try:
                                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                    c = conn.cursor()
                                    c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                                 VALUES (?, ?, ?, ?)
                                                 ON CONFLICT(guild_id, user_id, item_type)
                                                 DO UPDATE SET count = count + ?''',
                                              (interaction.guild_id, modal_interaction.user.id, 'dna', qty, qty))
                                    conn.commit()
                                    conn.close()
                                except Exception as e:
                                    await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, total_price)
                                    await modal_interaction.response.send_message(f"❌ Failed to add DNA Sample: {e}", ephemeral=True)
                                    return
                                embed = discord.Embed(
                                    title="✅ DNA Samples Purchased!",
                                    description=f"🧬 **{qty}x DNA Sample** added to inventory!\n\n"
                                                f"**Effect:** Clone a dragon when breeding\n"
                                                f"**Total Cost:** {total_price:,} 🪙\n"
                                                f"**New Balance:** {int(balance - total_price):,} 🪙\n\n"
                                                f"💡 Use with `/breed` to clone dragons!",
                                    color=discord.Color.green()
                                )
                                await modal_interaction.response.send_message(embed=embed, ephemeral=False)

                        elif category == 'usable':
                            item_type_map = {'night_vision': 'night_vision', 'lucky_dice': 'lucky_dice', 'gold_rush': 'gold_rush'}
                            if item not in item_type_map:
                                await modal_interaction.response.send_message(f"❌ Unknown item: {item}", ephemeral=True)
                                return
                            await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, -total_price)
                            try:
                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()
                                c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                             VALUES (?, ?, ?, ?)
                                             ON CONFLICT(guild_id, user_id, item_type)
                                             DO UPDATE SET count = count + ?''',
                                          (interaction.guild_id, modal_interaction.user.id, item_type_map[item], qty, qty))
                                conn.commit()
                                conn.close()
                            except Exception as e:
                                await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, total_price)
                                await modal_interaction.response.send_message(f"❌ Failed to add item: {e}", ephemeral=True)
                                return
                            embed = discord.Embed(
                                title="✅ Usable Items Purchased!",
                                description=f"{item_info['emoji']} **{qty}x {item_info['name']}** added to inventory!\n\n"
                                            f"**Total Cost:** {total_price:,} 🪙\n"
                                            f"**New Balance:** {int(balance - total_price):,} 🪙\n\n"
                                            f"💡 Use the button in `/inventory` to activate them!",
                                color=discord.Color.green()
                            )
                            await modal_interaction.response.send_message(embed=embed, ephemeral=False)

                        elif category == 'consumable':
                            consumable_hints = {
                                'mystery_box': "Open it in `/inventory` to get a random item!",
                                'dice_of_fate': "Roll it in `/inventory` for a random effect!",
                                'fast_travel_scroll': "Used automatically when starting `/adventure`!",
                                'double_loot_bag': "Used automatically when starting `/adventure`!",
                                'war_drum': "Auto-consumed on your next raid attack for +10% damage!",
                                'shield_rune': "Auto-consumed to give consolation coins if your raid tier escapes!",
                                'server_trophy': "Displayed as trophies in your `/stats` profile!",
                            }
                            hint = consumable_hints.get(item, "Use it from `/inventory`!")
                            await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, -total_price)
                            try:
                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()
                                c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                             VALUES (?, ?, ?, ?)
                                             ON CONFLICT(guild_id, user_id, item_type)
                                             DO UPDATE SET count = count + ?''',
                                          (interaction.guild_id, modal_interaction.user.id, item, qty, qty))
                                conn.commit()
                                conn.close()
                            except Exception as e:
                                await asyncio.to_thread(update_balance, interaction.guild_id, modal_interaction.user.id, total_price)
                                await modal_interaction.response.send_message(f"❌ Failed to add item: {e}", ephemeral=True)
                                return
                            embed = discord.Embed(
                                title="✅ Item Purchased!",
                                description=f"{item_info['emoji']} **{qty}x {item_info['name']}** added to inventory!\n\n"
                                            f"**Total Cost:** {total_price:,} 🪙\n"
                                            f"**New Balance:** {int(balance - total_price):,} 🪙\n\n"
                                            f"💡 {hint}",
                                color=discord.Color.green()
                            )
                            await modal_interaction.response.send_message(embed=embed, ephemeral=False)

                    except ValueError:
                        await modal_interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)

            await sel_interaction.response.send_modal(QuantityModal())

        # ── Views ────────────────────────────────────────────────────────────
        class CategorySelect(discord.ui.Select):
            def __init__(self, cat_key: str):
                self._cat_key = cat_key
                super().__init__(
                    placeholder="Choose an item to buy...",
                    options=categories[cat_key]['options'],
                    row=0
                )

            async def callback(self, cb_interaction: discord.Interaction):
                await handle_purchase(cb_interaction, self.values[0])

        class CategoryView(discord.ui.View):
            def __init__(self, cat_key: str):
                super().__init__(timeout=300)
                self.add_item(CategorySelect(cat_key))

            @discord.ui.button(label="← Back to Categories", style=discord.ButtonStyle.secondary, row=1)
            async def back_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                ud = get_user(btn_interaction.guild_id, btn_interaction.user.id)
                await btn_interaction.response.edit_message(
                    embed=build_main_embed(ud[2]),
                    view=ShopMainView()
                )

        class MainCategorySelect(discord.ui.Select):
            def __init__(self):
                options = [
                    discord.SelectOption(
                        label=cat['label'],
                        emoji=cat['emoji'],
                        description=cat['description'][:50],
                        value=cat_key
                    )
                    for cat_key, cat in categories.items()
                ]
                super().__init__(placeholder="Choose a category...", options=options)

            async def callback(self, cb_interaction: discord.Interaction):
                cat_key = self.values[0]
                ud = get_user(cb_interaction.guild_id, cb_interaction.user.id)
                await cb_interaction.response.edit_message(
                    embed=build_category_embed(cat_key, ud[2]),
                    view=CategoryView(cat_key)
                )

        class ShopMainView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                self.add_item(MainCategorySelect())

        await interaction.followup.send(embed=build_main_embed(balance), view=ShopMainView(), ephemeral=False)

    # ==================== DAILY ====================

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        user_data = get_user(interaction.guild_id, interaction.user.id)
        current_time = int(time.time())
        last_claimed = user_data[3]

        if current_time - last_claimed < 86400:
            time_left = 86400 - (current_time - last_claimed)
            await interaction.response.send_message(f"⏰ Daily already claimed! Come back in {format_time_remaining(time_left)}", ephemeral=False)
            return

        reward = random.randint(50, 200)
        await asyncio.to_thread(update_balance, interaction.guild_id, interaction.user.id, reward)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('UPDATE users SET daily_last_claimed = ? WHERE guild_id = ? AND user_id = ?',
                  (current_time, interaction.guild_id, interaction.user.id))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"🎁 Daily reward claimed! +{reward} 🪙", ephemeral=False)

    # ==================== VOTE ====================

    @app_commands.command(name="vote", description="Vote for the bot on Top.gg and get rewards!")
    async def vote(self, interaction: discord.Interaction):
        """Vote for the bot on Top.gg"""
        await interaction.response.defer(ephemeral=False)

        from database import get_db_connection
        from cogs.topgg import get_vote_reward_for_day, build_vote_schedule_rows, register_vote_guild
        register_vote_guild(interaction.user.id, interaction.guild.id)

        streak_info = {'current_streak': 0, 'total_votes': 0, 'best_streak': 0, 'last_vote_time': 0}
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT current_streak, last_vote_time, total_votes, best_streak FROM vote_streaks WHERE user_id = ?',
                      (interaction.user.id,))
            row = c.fetchone()
            conn.close()
            if row:
                streak_info = {'current_streak': row[0], 'last_vote_time': row[1],
                               'total_votes': row[2], 'best_streak': row[3]}
        except Exception:
            pass

        total = streak_info['total_votes']
        streak = streak_info['current_streak']
        can_vote = int(time.time()) - streak_info['last_vote_time'] >= 12 * 3600

        # Current day in cycle (already collected), next vote = day_in_cycle + 1
        day_in_cycle = ((total - 1) % 30) + 1 if total > 0 else 0
        next_day = (day_in_cycle % 30) + 1
        next_reward = get_vote_reward_for_day(next_day)

        embed = discord.Embed(
            title="🗳️ Vote for Dragon Bot",
            description="Help support the bot by voting on Top.gg!\nEvery vote helps us reach more players and keeps the bot growing.",
            color=discord.Color.gold()
        )

        embed.add_field(
            name=f"🎁 Next Reward — Day {next_day}/30",
            value=(f"**{next_reward['label']}**\n"
                   f"🌟 Weekend bonus: +1 extra Wooden Pack"),
            inline=False
        )

        for row_label, row_visual in build_vote_schedule_rows(day_in_cycle):
            embed.add_field(name=f"📅 {row_label}", value=row_visual, inline=False)

        embed.add_field(
            name="🔥 Your Stats",
            value=(f"Streak: **{streak}** | Total votes: **{total}** | Best: **{streak_info['best_streak']}**\n"
                   f"{'✅ Ready to vote!' if can_vote else '⏳ Already voted recently (12h cooldown)'}"),
            inline=False
        )

        class VoteView(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.add_item(discord.ui.Button(
                    label="Vote on Top.gg",
                    url="https://top.gg/bot/1445803895862333592/vote",
                    style=discord.ButtonStyle.link,
                    emoji="🗳️"
                ))

        embed.set_footer(text="Rewards sent via DM • Resets every 30 votes • Vote every 12h!")
        await interaction.followup.send(embed=embed, view=VoteView(), ephemeral=False)

    # ==================== COINFLIP ====================

    @app_commands.command(name="coinflip", description="Flip a coin for double or nothing! Challenge a player or the bot")
    async def coinflip(self, interaction: discord.Interaction, amount: int, opponent: discord.User = None):
        """Coinflip betting game - player vs player or player vs bot"""
        # IMMEDIATELY defer to claim response slot before any async operations
        await interaction.response.defer(ephemeral=False)

        guild_id = interaction.guild_id
        user_id = interaction.user.id

        # Check softlock
        is_softlocked, _ = await asyncio.to_thread(is_player_softlocked, guild_id, user_id)
        if is_softlocked:
            embed = discord.Embed(
                title="🚫 Softlock Active",
                description="You must upgrade your Dragon Nest before you can use coinflip!",
                color=discord.Color.red()
            )
            embed.set_footer(text="This message will auto-delete in 5 seconds")
            msg = await interaction.followup.send(embed=embed)
            await asyncio.sleep(5)
            try:
                await msg.delete()
            except:
                pass
            return

        # Validate amount
        if amount < 100:
            await interaction.followup.send("❌ Minimum bet is **100 coins**!", ephemeral=False)
            return

        # Check user balance
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        result = c.fetchone()

        if not result or result[0] < amount:
            conn.close()
            await interaction.followup.send(f"❌ You don't have enough coins! You need **{amount}** 🪙", ephemeral=False)
            return

        challenger_balance = result[0]

        # Player vs Bot
        if opponent is None or opponent.id == self.bot.user.id:
            # Deduct bet from challenger
            await asyncio.to_thread(update_balance, guild_id, user_id, -amount)

            # Flip coin
            result = random.choice(['heads', 'tails'])
            challenger_choice = random.choice(['heads', 'tails'])
            won = result == challenger_choice

            if won:
                # Win: get back bet + winnings
                await asyncio.to_thread(update_balance, guild_id, user_id, amount * 2)

                embed = discord.Embed(
                    title="🪙 Coinflip vs Bot",
                    description=f"**{interaction.user.mention}** flipped **{result}**!\n\n"
                                f"🎉 **YOU WIN!**\n"
                                f"💰 Won: **{amount}** coins\n"
                                f"💵 New balance: **{int(challenger_balance + amount)}** 🪙",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="🪙 Coinflip vs Bot",
                    description=f"**{interaction.user.mention}** flipped **{result}**!\n\n"
                                f"💔 **YOU LOSE!**\n"
                                f"💸 Lost: **{amount}** coins\n"
                                f"💵 New balance: **{int(challenger_balance - amount)}** 🪙",
                    color=discord.Color.red()
                )

            # Track coinflip quest
            await asyncio.to_thread(check_dragonpass_quests, guild_id, user_id, 'use_coinflip', 1)

            conn.close()
            await interaction.followup.send(embed=embed)
            return

        # Player vs Player
        if opponent.bot:
            conn.close()
            await interaction.followup.send("❌ You can't challenge a bot! Leave opponent empty to play against the bot.", ephemeral=False)
            return

        if opponent.id == user_id:
            conn.close()
            await interaction.followup.send("❌ You can't challenge yourself!", ephemeral=False)
            return

        # Check if there's already a pending bet between these users
        c.execute('''SELECT bet_id FROM coinflip_bets
                     WHERE guild_id = ? AND ((challenger_id = ? AND opponent_id = ?) OR (challenger_id = ? AND opponent_id = ?))
                     AND status = 'pending' ''',
                  (guild_id, user_id, opponent.id, opponent.id, user_id))

        if c.fetchone():
            conn.close()
            await interaction.followup.send("❌ There's already a pending coinflip bet between you two!", ephemeral=False)
            return

        # Check opponent balance
        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, opponent.id))
        opp_result = c.fetchone()

        if not opp_result or opp_result[0] < amount:
            conn.close()
            await interaction.followup.send(f"❌ {opponent.mention} doesn't have enough coins for this bet!", ephemeral=False)
            return

        # Create bet
        current_time = int(time.time())
        expires_at = current_time + 300  # 5 minutes to accept

        c.execute('''INSERT INTO coinflip_bets (guild_id, challenger_id, opponent_id, amount, created_at, expires_at)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (guild_id, user_id, opponent.id, amount, current_time, expires_at))
        bet_id = c.lastrowid
        conn.commit()
        conn.close()

        # Create accept/decline buttons
        class CoinflipView(discord.ui.View):
            def __init__(self, bet_id, challenger_id, opponent_id, amount):
                super().__init__(timeout=300)
                self.bet_id = bet_id
                self.challenger_id = challenger_id
                self.opponent_id = opponent_id
                self.amount = amount

            @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="✅")
            async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.opponent_id:
                    await interaction.response.send_message("❌ Only the challenged player can accept!", ephemeral=False)
                    return

                try:
                    await interaction.response.defer()
                except discord.errors.NotFound:
                    return  # Interaction already responded

                # Check bet still exists
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('SELECT status FROM coinflip_bets WHERE bet_id = ?', (self.bet_id,))
                bet = c.fetchone()

                if not bet or bet[0] != 'pending':
                    conn.close()
                    try:
                        await interaction.followup.send("❌ This bet is no longer available!", ephemeral=False)
                    except:
                        pass
                    return

                # Check both players still have enough coins
                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (interaction.guild_id, self.challenger_id))
                challenger_bal = c.fetchone()
                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (interaction.guild_id, self.opponent_id))
                opponent_bal = c.fetchone()

                if not challenger_bal or challenger_bal[0] < self.amount:
                    c.execute('UPDATE coinflip_bets SET status = ? WHERE bet_id = ?', ('cancelled', self.bet_id))
                    conn.commit()
                    conn.close()
                    try:
                        await interaction.followup.send("❌ Challenger no longer has enough coins!", ephemeral=False)
                    except:
                        pass
                    return

                if not opponent_bal or opponent_bal[0] < self.amount:
                    conn.close()
                    try:
                        await interaction.followup.send("❌ You don't have enough coins anymore!", ephemeral=False)
                    except:
                        pass
                    return

                # Close connection BEFORE calling async functions to prevent database locked errors
                conn.close()

                # Deduct from both players
                await asyncio.to_thread(update_balance, interaction.guild_id, self.challenger_id, -self.amount)
                await asyncio.to_thread(update_balance, interaction.guild_id, self.opponent_id, -self.amount)

                # Flip coin
                result = random.choice(['heads', 'tails'])
                winner_id = random.choice([self.challenger_id, self.opponent_id])
                loser_id = self.opponent_id if winner_id == self.challenger_id else self.challenger_id

                # Give bet back + winnings to winner (total 2x bet)
                await asyncio.to_thread(update_balance, interaction.guild_id, winner_id, self.amount * 2)

                # Update bet status in DB
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('UPDATE coinflip_bets SET status = ? WHERE bet_id = ?', ('completed', self.bet_id))

                # Get updated balances
                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (interaction.guild_id, winner_id))
                winner_balance = c.fetchone()[0]
                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (interaction.guild_id, loser_id))
                loser_balance = c.fetchone()[0]
                conn.commit()
                conn.close()

                # Track coinflip quest for both players
                await asyncio.to_thread(check_dragonpass_quests, interaction.guild_id, self.challenger_id, 'use_coinflip', 1)
                await asyncio.to_thread(check_dragonpass_quests, interaction.guild_id, self.opponent_id, 'use_coinflip', 1)

                winner = interaction.guild.get_member(winner_id)
                loser = interaction.guild.get_member(loser_id)

                embed = discord.Embed(
                    title="🪙 Coinflip Result",
                    description=f"The coin landed on **{result}**!\n\n"
                                f"🎉 **Winner:** {winner.mention}\n"
                                f"💰 Won: **{self.amount}** coins\n"
                                f"💵 Balance: **{int(winner_balance)}** 🪙\n\n"
                                f"💔 **Loser:** {loser.mention}\n"
                                f"💸 Lost: **{self.amount}** coins\n"
                                f"💵 Balance: **{int(loser_balance)}** 🪙",
                    color=discord.Color.gold()
                )

                # Disable buttons
                for item in self.children:
                    item.disabled = True

                try:
                    await interaction.followup.send(embed=embed)
                except discord.errors.NotFound:
                    pass  # Interaction already deleted

            @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
            async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.opponent_id:
                    await interaction.response.send_message("❌ Only the challenged player can decline!", ephemeral=False)
                    return

                try:
                    await interaction.response.defer()
                except discord.errors.NotFound:
                    return  # Interaction already responded

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('UPDATE coinflip_bets SET status = ? WHERE bet_id = ?', ('declined', self.bet_id))
                conn.commit()
                conn.close()

                embed = discord.Embed(
                    title="🪙 Coinflip Declined",
                    description=f"{interaction.user.mention} declined the coinflip challenge!",
                    color=discord.Color.red()
                )

                # Disable buttons
                for item in self.children:
                    item.disabled = True

                try:
                    await interaction.followup.send(embed=embed)
                except discord.errors.NotFound:
                    pass  # Interaction already deleted

        embed = discord.Embed(
            title="🪙 Coinflip Challenge!",
            description=f"**{interaction.user.mention}** challenges **{opponent.mention}** to a coinflip!\n\n"
                        f"💰 Bet: **{amount}** coins\n"
                        f"🎲 Winner takes all!\n\n"
                        f"⏰ Expires in 5 minutes",
            color=discord.Color.gold()
        )

        view = CoinflipView(bet_id, user_id, opponent.id, amount)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
