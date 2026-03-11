"""
cogs/dragons.py - Dragon info/collection commands for DragonBot.
Contains: info, help_command, pricecheck, inventory, dragonlogue, stats.
Extracted verbatim from bot.py.
"""

import asyncio
import sqlite3
import time
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import (
    DRAGON_TYPES, DRAGON_RARITY_TIERS, DRAGONNEST_UPGRADES, LEVEL_NAMES,
    PACK_TYPES, RARITY_DAMAGE, USABLE_ITEMS
)
from database import (
    get_user, update_balance, get_active_item, activate_item,
    get_db_connection, is_player_softlocked, calculate_item_cost
)
from state import active_dragonscales, active_luckycharms, active_dragonfest, active_usable_items, night_vision_activations, spawn_channels
from utils import format_time_remaining


# ==================== PRICECHECK CLASSES (module-level) ====================

class PricecheckDropdown(discord.ui.Select):
    def __init__(self):
        # Create options for all dragons and items
        options = []

        # Add dragons WITH EMOJI
        for dragon_key, dragon_data in DRAGON_TYPES.items():
            options.append(
                discord.SelectOption(
                    label=dragon_data['name'],
                    value=f"dragon_{dragon_key}",
                    description=f"Rarity: {dragon_data['spawn_chance']:.2f}%",
                    emoji=dragon_data['emoji']
                )
            )

        # Add items (tradeable items)
        item_types = {
            'lucky_charm': ('🍀', 'Lucky Charm'),
            'dna': ('🧬', 'Dragon DNA'),
            'dragonscale': ('<:dragonscale:1446278170998341693>', 'Dragonscale'),
        }
        for item_key, (emoji_str, name) in item_types.items():
            emoji_obj = None
            if emoji_str.startswith('<:') and emoji_str.endswith('>'):
                try:
                    emoji_obj = discord.PartialEmoji.from_str(emoji_str)
                except:
                    emoji_obj = emoji_str
            else:
                emoji_obj = emoji_str

            options.append(
                discord.SelectOption(
                    label=name,
                    value=f"item_{item_key}",
                    description="Check item prices",
                    emoji=emoji_obj
                )
            )

        # Add packs
        pack_types = {
            'wooden': ('<:woodenchest:1446170002708238476>', 'Wooden Pack'),
            'stone': ('<:stonechest:1446169958265389247>', 'Stone Pack'),
            'bronze': ('<:bronzechest:1446169758599745586>', 'Bronze Pack'),
            'silver': ('<:silverchest:1446169917996011520>', 'Silver Pack'),
            'gold': ('<:goldchest:1446169876438978681>', 'Gold Pack'),
            'platinum': ('<:platinumchest:1446169876438978681>', 'Platinum Pack'),
            'diamond': ('<:diamondchest:1446169830720929985>', 'Diamond Pack'),
            'celestial': ('<:celestialchest:1446169830720929985>', 'Celestial Pack'),
        }
        for pack_key, (emoji_str, name) in pack_types.items():
            emoji_obj = None
            try:
                emoji_obj = discord.PartialEmoji.from_str(emoji_str)
            except:
                emoji_obj = emoji_str

            options.append(
                discord.SelectOption(
                    label=name,
                    value=f"item_pack_{pack_key}",
                    description="Check pack prices",
                    emoji=emoji_obj
                )
            )

        # Add usable items
        usable_items = {
            'night_vision': ('🌙', 'Night Vision'),
            'lucky_dice': ('🎰', 'Lucky Dice'),
        }
        for item_key, (emoji_str, name) in usable_items.items():
            emoji_obj = emoji_str if isinstance(emoji_str, str) and not emoji_str.startswith('<') else emoji_str
            options.append(
                discord.SelectOption(
                    label=name,
                    value=f"item_{item_key}",
                    description="Check item prices",
                    emoji=emoji_obj
                )
            )

        # Discord limit: 25 options per dropdown, so we need to limit
        # Priority: items first, then packs, then dragons (dragons are many)
        if len(options) > 25:
            # Keep all items/packs, limit dragons
            items_and_packs = options[len(DRAGON_TYPES):]  # All non-dragon options
            dragons = options[:len(DRAGON_TYPES)]  # All dragon options
            options = items_and_packs + dragons[:25 - len(items_and_packs)]

        super().__init__(
            placeholder="Select a dragon or item...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        if selected.startswith('dragon_'):
            dragon_type = selected.replace('dragon_', '')
            await show_dragon_pricecheck(interaction, dragon_type)
        elif selected.startswith('item_pack_'):
            pack_type = selected.replace('item_pack_', '')
            await show_item_pricecheck(interaction, f'pack_{pack_type}')
        elif selected.startswith('item_'):
            item_type = selected.replace('item_', '')
            await show_item_pricecheck(interaction, item_type)


class PricecheckView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(PricecheckDropdown())


async def show_dragon_pricecheck(interaction: discord.Interaction, dragon_type: str):
    """Show price check for a specific dragon"""
    if dragon_type not in DRAGON_TYPES:
        await interaction.response.send_message("❌ Invalid dragon type!", ephemeral=True)
        return

    dragon_data = DRAGON_TYPES[dragon_type]

    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
    c = conn.cursor()

    # Get last 10 sales
    c.execute('''SELECT price, sold_at FROM market_sales
                 WHERE guild_id = ? AND dragon_type = ?
                 ORDER BY sold_at DESC LIMIT 10''',
              (interaction.guild_id, dragon_type))
    sales = c.fetchall()

    # Get current active listings
    c.execute('''SELECT price FROM market_listings
                 WHERE guild_id = ? AND dragon_type = ?
                 ORDER BY price ASC''',
              (interaction.guild_id, dragon_type))
    listings = c.fetchall()

    conn.close()

    embed = discord.Embed(
        title=f"💰 Price Check: {dragon_data['emoji']} {dragon_data['name']}",
        description=f"**Rarity:** {dragon_data['spawn_chance']:.2f}%\n**Base Value:** {dragon_data['value']:.2f} coins",
        color=0xFEE75C
    )

    if sales:
        # Calculate statistics
        prices = [s[0] for s in sales]
        avg_price = int(sum(prices) / len(prices))
        min_price = min(prices)
        max_price = max(prices)
        last_price = prices[0]

        embed.add_field(
            name="📊 Sales History",
            value=f"**Last Sale:** {last_price} 🪙\n"
                  f"**Average (10):** {avg_price} 🪙\n"
                  f"**Range:** {min_price} - {max_price} 🪙\n"
                  f"**Total Sales:** {len(sales)}",
            inline=True
        )

        # Price trend (compare last 3 to previous 3)
        if len(sales) >= 6:
            recent_avg = sum(prices[:3]) / 3
            older_avg = sum(prices[3:6]) / 3
            trend = "📈 Rising" if recent_avg > older_avg else "📉 Falling" if recent_avg < older_avg else "➡️ Stable"
            embed.add_field(
                name="📈 Trend",
                value=trend,
                inline=True
            )
    else:
        # No sales history - suggest recommended price
        recommended = int(dragon_data['value'] * 4)
        embed.add_field(
            name="💡 Suggested Price",
            value=f"**{recommended}** 🪙\n\n*No sales history yet!*\nBe the first to set the market price.",
            inline=True
        )

    if listings:
        # Show current listings
        listing_prices = [l[0] for l in listings]
        lowest = min(listing_prices)
        highest = max(listing_prices)

        embed.add_field(
            name="🏪 Active Listings",
            value=f"**Count:** {len(listings)}\n"
                  f"**Lowest:** {lowest} 🪙\n"
                  f"**Highest:** {highest} 🪙",
            inline=True
        )
    else:
        embed.add_field(
            name="🏪 Active Listings",
            value="*None currently listed*",
            inline=True
        )

    # Price recommendation
    if sales:
        suggested_sell = int(avg_price * 0.95)  # 5% below average for quick sale
        suggested_buy = int(avg_price * 1.05)  # 5% above average for fair price

        embed.add_field(
            name="💡 Recommendations",
            value=f"**Quick Sell:** ~{suggested_sell} 🪙\n"
                  f"**Fair Price:** ~{avg_price} 🪙\n"
                  f"**Premium Price:** ~{suggested_buy} 🪙",
            inline=False
        )

    embed.set_footer(text="Use /market to browse listings or /marketsell to list yours")

    await interaction.response.send_message(embed=embed, ephemeral=False)


async def show_item_pricecheck(interaction: discord.Interaction, item_type: str):
    """Show price check for a specific item"""
    item_names = {
        'lucky_charm': ('🍀', 'Lucky Charm'),
        'dna': ('🧬', 'Dragon DNA'),
        'dragonscale': ('<:dragonscale:1446278170998341693>', 'Dragonscale'),
        'night_vision': ('🌙', 'Night Vision'),
        'lucky_dice': ('🎰', 'Lucky Dice'),
    }

    # Handle pack types
    pack_types_map = {
        'pack_wooden': ('<:woodenchest:1446170002708238476>', 'Wooden Pack'),
        'pack_stone': ('<:stonechest:1446169958265389247>', 'Stone Pack'),
        'pack_bronze': ('<:bronzechest:1446169758599745586>', 'Bronze Pack'),
        'pack_silver': ('<:silverchest:1446169917996011520>', 'Silver Pack'),
        'pack_gold': ('<:goldchest:1446169876438978681>', 'Gold Pack'),
        'pack_platinum': ('<:platinumchest:1446169876438978681>', 'Platinum Pack'),
        'pack_diamond': ('<:diamondchest:1446169830720929985>', 'Diamond Pack'),
        'pack_celestial': ('<:celestialchest:1446169830720929985>', 'Celestial Pack'),
    }

    if item_type not in item_names and item_type not in pack_types_map:
        await interaction.response.send_message("❌ Invalid item type!", ephemeral=True)
        return

    if item_type in pack_types_map:
        emoji, item_name = pack_types_map[item_type]
    else:
        emoji, item_name = item_names[item_type]

    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
    c = conn.cursor()

    # Get last 10 sales for this item
    c.execute('''SELECT price, sold_at FROM market_sales
                 WHERE guild_id = ? AND item_type = ?
                 ORDER BY sold_at DESC LIMIT 10''',
              (interaction.guild_id, item_type))
    sales = c.fetchall()

    # Get current active listings
    c.execute('''SELECT price FROM market_listings
                 WHERE guild_id = ? AND item_type = ?
                 ORDER BY price ASC''',
              (interaction.guild_id, item_type))
    listings = c.fetchall()

    conn.close()

    embed = discord.Embed(
        title=f"💰 Price Check: {emoji} {item_name}",
        description=f"Market price information for {item_name}",
        color=0xFEE75C
    )

    if sales:
        # Calculate statistics
        prices = [s[0] for s in sales]
        avg_price = int(sum(prices) / len(prices))
        min_price = min(prices)
        max_price = max(prices)
        last_price = prices[0]

        embed.add_field(
            name="📊 Sales History",
            value=f"**Last Sale:** {last_price} 🪙\n"
                  f"**Average (10):** {avg_price} 🪙\n"
                  f"**Range:** {min_price} - {max_price} 🪙\n"
                  f"**Total Sales:** {len(sales)}",
            inline=True
        )

        # Price trend (compare last 3 to previous 3)
        if len(sales) >= 6:
            recent_avg = sum(prices[:3]) / 3
            older_avg = sum(prices[3:6]) / 3
            trend = "📈 Rising" if recent_avg > older_avg else "📉 Falling" if recent_avg < older_avg else "➡️ Stable"
            embed.add_field(
                name="📈 Trend",
                value=trend,
                inline=True
            )
    else:
        embed.add_field(
            name="📊 Sales History",
            value="*No sales history yet!*",
            inline=True
        )

    if listings:
        # Show current listings
        listing_prices = [l[0] for l in listings]
        lowest = min(listing_prices)
        highest = max(listing_prices)

        embed.add_field(
            name="🏪 Active Listings",
            value=f"**Count:** {len(listings)}\n"
                  f"**Lowest:** {lowest} 🪙\n"
                  f"**Highest:** {highest} 🪙",
            inline=True
        )
    else:
        embed.add_field(
            name="🏪 Active Listings",
            value="*None currently listed*",
            inline=True
        )

    embed.set_footer(text="Use /market to browse listings or /marketbuy to purchase items")

    await interaction.response.send_message(embed=embed, ephemeral=False)


# ==================== INVENTORY ITEMS VIEW ====================

class InventoryItemsView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, dragonscale_minutes: int, luckycharm_count: int, usable_items: dict):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.user_id = user_id
        self.dragonscale_minutes = dragonscale_minutes
        self.luckycharm_count = luckycharm_count
        self.usable_items = usable_items  # {'dragon_eye': 2, 'dragon_magnet': 1, etc}

        # Add buttons for existing items
        if dragonscale_minutes > 0:
            self.add_item(self.create_dragonscale_button())
        if luckycharm_count > 0:
            self.add_item(self.create_luckycharm_button())

        # Add buttons for new usable items
        for item_key, count in usable_items.items():
            if count > 0:
                if item_key == 'night_vision':
                    self.add_item(self.create_night_vision_button(count))
                elif item_key == 'lucky_dice':
                    self.add_item(self.create_lucky_dice_button(count))

    def create_dragonscale_button(self):
        button = discord.ui.Button(
            label=f"Activate Dragonscale ({self.dragonscale_minutes}m)",
            style=discord.ButtonStyle.primary,
            emoji="⚡",
            custom_id=f"dragonscale_{self.guild_id}_{self.user_id}"
        )
        button.callback = self.activate_dragonscale
        return button

    def create_luckycharm_button(self):
        button = discord.ui.Button(
            label=f"Activate Lucky Charm ({self.luckycharm_count}x)",
            style=discord.ButtonStyle.success,
            emoji="🍀",
            custom_id=f"luckycharm_{self.guild_id}_{self.user_id}"
        )
        button.callback = self.activate_luckycharm
        return button

    async def activate_dragonscale(self, interaction: discord.Interaction):
        # Check if user is the owner
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your inventory!", ephemeral=False)
            return

        # Check if raid boss is active
        from database import is_raid_boss_active
        if is_raid_boss_active(self.guild_id):
            await interaction.response.send_message("❌ Cannot activate dragonscale during an active raid boss! ⚔️", ephemeral=False)
            return

        # Show modal to ask how many minutes
        modal = DragonscaleMinutesModal(self.guild_id, self.user_id, self.dragonscale_minutes, self, interaction.message)
        await interaction.response.send_modal(modal)

    async def activate_luckycharm(self, interaction: discord.Interaction):
        # Check if user is the owner
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your inventory!", ephemeral=False)
            return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Check if user still has Lucky Charms
        c.execute('SELECT count FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                  (self.guild_id, self.user_id))
        result = c.fetchone()

        if not result or result[0] <= 0:
            await interaction.response.send_message("❌ You don't have any Lucky Charms anymore!", ephemeral=False)
            conn.close()
            return

        available_charms = result[0]

        # Check if already active
        if self.guild_id in active_luckycharms and self.user_id in active_luckycharms[self.guild_id]:
            existing_end = active_luckycharms[self.guild_id][self.user_id]
            if existing_end > int(time.time()):
                # Add to existing boost
                new_end_time = existing_end + 1800  # Add 30 minutes
                active_luckycharms[self.guild_id][self.user_id] = new_end_time

                # Deduct Lucky Charm
                c.execute('UPDATE user_luckycharms SET count = count - 1 WHERE guild_id = ? AND user_id = ?',
                          (self.guild_id, self.user_id))
                conn.commit()
                conn.close()

                new_total = (new_end_time - int(time.time())) // 60

                embed = discord.Embed(
                    title="🍀 Lucky Charm Extended!",
                    description=f"Added **30 minutes** to your active Lucky Charm!\n\n"
                                f"**Total Duration:** {new_total} minutes\n"
                                f"**Effect:** 2x Catch Rate!\n"
                                f"**Remaining Lucky Charms:** {available_charms - 1}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=False)
                return

        # Activate new Lucky Charm
        end_time = int(time.time()) + 1800  # 30 minutes
        if self.guild_id not in active_luckycharms:
            active_luckycharms[self.guild_id] = {}
        active_luckycharms[self.guild_id][self.user_id] = end_time

        # Deduct Lucky Charm
        c.execute('UPDATE user_luckycharms SET count = count - 1 WHERE guild_id = ? AND user_id = ?',
                  (self.guild_id, self.user_id))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🍀 Lucky Charm Activated!",
            description=f"**Duration:** 30 minutes\n"
                        f"**Effect:** 2x Catch Rate! Catch twice as many dragons!\n"
                        f"**Remaining Lucky Charms:** {available_charms - 1}",
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, ephemeral=False)

    def create_night_vision_button(self, count: int):
        button = discord.ui.Button(
            label=f"Night Vision ({count}x)",
            style=discord.ButtonStyle.primary,
            emoji="🌙",
            custom_id=f"nightvision_{self.guild_id}_{self.user_id}"
        )
        button.callback = self.activate_night_vision
        return button

    async def activate_night_vision(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your inventory!", ephemeral=False)
            return

        # Check if Dragonscale or Dragonfest is active
        if self.guild_id in active_dragonscales:
            existing_end = active_dragonscales[self.guild_id]
            if existing_end > int(time.time()):
                await interaction.response.send_message(
                    "❌ Cannot activate Night Vision while Dragonscale is active! ⚡",
                    ephemeral=False
                )
                return

        if self.guild_id in active_dragonfest:
            dragonfest_data = active_dragonfest[self.guild_id]
            if dragonfest_data['end'] > int(time.time()):
                await interaction.response.send_message(
                    "❌ Cannot activate Night Vision while Dragonfest is active! 🎉",
                    ephemeral=False
                )
                return

        # Check if current time is nighttime (20:00 - 08:00)
        current_hour = datetime.now().hour
        is_nighttime = current_hour >= 20 or current_hour < 8

        if not is_nighttime:
            await interaction.response.send_message(
                f"❌ Night Vision can only be activated between 20:00 (8pm) and 08:00 (8am)!\n"
                f"Current time: {datetime.now().strftime('%H:%M')}\n\n"
                f"Come back during nighttime to activate it!",
                ephemeral=False
            )
            return

        # Check if already active for THIS user
        if get_active_item(self.guild_id, self.user_id, 'night_vision'):
            await interaction.response.send_message("⏳ You already have Night Vision active! (60 min)", ephemeral=False)
            return

        # Check if user already activated Night Vision tonight
        today_key = (self.guild_id, self.user_id)
        tonight_date = datetime.now().strftime("%Y-%m-%d")

        if today_key in night_vision_activations:
            activation_date = night_vision_activations[today_key]
            if activation_date == tonight_date:
                await interaction.response.send_message(
                    f"❌ You already activated Night Vision tonight!\n\n"
                    f"You can activate it again tomorrow night after 20:00.",
                    ephemeral=False
                )
                return

        # Activate
        activate_item(self.guild_id, self.user_id, 'night_vision', 60 * 60)  # 60 minutes
        night_vision_activations[today_key] = tonight_date  # Track tonight's activation

        # Deduct item
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (self.guild_id, self.user_id, 'night_vision'))
        conn.commit()
        conn.close()

        # Update usable_items count locally
        self.usable_items['night_vision'] = self.usable_items.get('night_vision', 1) - 1

        embed = discord.Embed(
            title="🌙 Night Vision Activated!",
            description="**Duration:** 60 minutes\n"
                        "**Effect:** +50% higher rarity dragons!\n"
                        "Increased chance for rare dragons during nighttime!\n\n"
                        "⚠️ You can only activate once per night. Come back tomorrow after 20:00!",
            color=discord.Color.dark_blue()
        )

        # Update the original message to remove/hide the button
        await interaction.response.defer()
        if interaction.message:
            # Recreate the view with updated items
            new_view = InventoryItemsView(self.guild_id, self.user_id, self.dragonscale_minutes, self.luckycharm_count, self.usable_items)
            try:
                await interaction.message.edit(view=new_view)
            except:
                pass  # Message might be deleted

        # Send the success message separately
        await interaction.followup.send(embed=embed, ephemeral=False)

    def create_lucky_dice_button(self, count: int):
        button = discord.ui.Button(
            label=f"Lucky Dice ({count}x)",
            style=discord.ButtonStyle.primary,
            emoji="🎰",
            custom_id=f"luckydice_{self.guild_id}_{self.user_id}"
        )
        button.callback = self.activate_lucky_dice
        return button

    async def activate_lucky_dice(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your inventory!", ephemeral=False)
            return

        # Check if already active
        if get_active_item(self.guild_id, self.user_id, 'lucky_dice'):
            await interaction.response.send_message("⏳ You already have Lucky Dice active! (30 min)", ephemeral=False)
            return

        # Activate
        activate_item(self.guild_id, self.user_id, 'lucky_dice', 30 * 60)  # 30 minutes

        # Deduct item
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (self.guild_id, self.user_id, 'lucky_dice'))
        conn.commit()
        conn.close()

        # Update usable_items count locally
        self.usable_items['lucky_dice'] = self.usable_items.get('lucky_dice', 1) - 1

        embed = discord.Embed(
            title="🎰 Lucky Dice Activated!",
            description="**Duration:** 30 minutes\n"
                        "**Effect:** +10% casino/gambling win chance!\n"
                        "Lady luck is on your side during this time!",
            color=discord.Color.red()
        )

        # Update the original message to remove/hide the button
        await interaction.response.defer()
        if interaction.message:
            # Recreate the view with updated items
            new_view = InventoryItemsView(self.guild_id, self.user_id, self.dragonscale_minutes, self.luckycharm_count, self.usable_items)
            try:
                await interaction.message.edit(view=new_view)
            except:
                pass  # Message might be deleted

        # Send the success message separately
        await interaction.followup.send(embed=embed, ephemeral=False)


# ==================== DRAGONSCALE MINUTES MODAL ====================

class DragonscaleMinutesModal(discord.ui.Modal, title="Activate Dragonscale"):
    def __init__(self, guild_id: int, user_id: int, available_minutes: int, inventory_view=None, inventory_message=None):
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.available_minutes = available_minutes
        self.inventory_view = inventory_view
        self.inventory_message = inventory_message

        self.minutes_input = discord.ui.TextInput(
            label=f"Wieviele Minuten aktivieren? (max {available_minutes})",
            placeholder=f"z.B. 5 oder 10",
            required=True,
            max_length=5
        )
        self.add_item(self.minutes_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            minutes = int(self.minutes_input.value)
        except ValueError:
            await interaction.response.send_message("❌ Bitte gib eine Zahl ein!", ephemeral=False)
            return

        if minutes <= 0:
            await interaction.response.send_message("❌ Du musst mindestens 1 Minute aktivieren!", ephemeral=False)
            return

        if minutes > self.available_minutes:
            await interaction.response.send_message(
                f"❌ Du hast nur **{self.available_minutes} Minuten** verfügbar!\n"
                f"Du versuchtest {minutes} Minuten zu aktivieren.",
                ephemeral=False
            )
            return

        # Check if Night Vision is active for ANY user in this guild
        if self.guild_id in active_usable_items:
            current_time = int(time.time())
            for uid, items_dict in active_usable_items[self.guild_id].items():
                if 'night_vision' in items_dict and items_dict['night_vision'] > current_time:
                    await interaction.response.send_message(
                        "❌ Cannot activate Dragonscale while Night Vision is active! 🌙",
                        ephemeral=False
                    )
                    return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Check if already active in server
        if self.guild_id in active_dragonscales:
            existing_end = active_dragonscales[self.guild_id]
            if existing_end > int(time.time()):
                # Add to existing event
                new_end_time = existing_end + (minutes * 60)
                active_dragonscales[self.guild_id] = new_end_time

                # Deduct minutes
                c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?',
                          (minutes, self.guild_id, self.user_id))
                conn.commit()
                conn.close()

                new_total = (new_end_time - int(time.time())) // 60

                embed = discord.Embed(
                    title="⚡ Dragonscale Extended!",
                    description=f"{interaction.user.mention} added **{minutes} minutes** to the server-wide event!\n\n"
                                f"**New Total Duration:** {new_total} minutes\n"
                                f"**Your Remaining Dragonscales:** {self.available_minutes - minutes} minutes",
                    color=discord.Color.gold()
                )
                await interaction.response.send_message(embed=embed, ephemeral=False)

                # Update inventory if available
                if self.inventory_message:
                    new_minutes = self.available_minutes - minutes
                    new_view = InventoryItemsView(self.guild_id, self.user_id, new_minutes, 0, {})
                    try:
                        await self.inventory_message.edit(view=new_view)
                    except:
                        pass
                return

        # Activate new server-wide event
        current_time = int(time.time())
        end_time = current_time + (minutes * 60)
        active_dragonscales[self.guild_id] = end_time
        from state import dragonscale_event_starts
        dragonscale_event_starts[self.guild_id] = current_time  # Store event start time

        # Initialize stats table if needed
        c.execute('''CREATE TABLE IF NOT EXISTS dragonscale_stats
                     (guild_id INTEGER, user_id INTEGER, dragons_caught INTEGER DEFAULT 0,
                      PRIMARY KEY (guild_id, user_id))''')

        # Clear previous stats for new event
        c.execute('DELETE FROM dragonscale_stats WHERE guild_id = ?', (self.guild_id,))

        # Deduct minutes
        c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?',
                  (minutes, self.guild_id, self.user_id))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="⚡ Dragonscale Event Started!",
            description=f"{interaction.user.mention} activated a **SERVER-WIDE** Dragonscale event!\n\n"
                        f"**Duration:** {minutes} minutes\n"
                        f"**Effect:** All players get spawn boosts!\n"
                        f"**Your Remaining Dragonscales:** {self.available_minutes - minutes} minutes\n\n"
                        f"🐉 Everyone can now catch dragons with enhanced spawn rates!",
            color=discord.Color.gold()
        )

        await interaction.response.send_message(embed=embed, ephemeral=False)

        # Update inventory if available
        if self.inventory_message:
            new_minutes = self.available_minutes - minutes
            new_view = InventoryItemsView(self.guild_id, self.user_id, new_minutes, 0, {})
            try:
                await self.inventory_message.edit(view=new_view)
            except:
                pass

        # Instant spawn first dragon
        from cogs.events import spawn_dragon
        channel = interaction.guild.get_channel(spawn_channels.get(self.guild_id)) if self.guild_id in spawn_channels else interaction.channel
        await asyncio.sleep(1)
        await spawn_dragon(self.guild_id, channel)


# ==================== DRAGONS COG ====================

class DragonsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==================== INFO ====================

    @app_commands.command(name="info", description="View bot information and statistics")
    async def info(self, interaction: discord.Interaction):
        """Show bot statistics"""
        await interaction.response.defer(ephemeral=False)
        # Get bot stats
        total_servers = len(self.bot.guilds)
        total_users = sum(guild.member_count for guild in self.bot.guilds)

        # Get latency
        latency = round(self.bot.latency * 1000)

        # Count total dragons in database
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT COUNT(DISTINCT guild_id || user_id) FROM users')
        unique_users = c.fetchone()[0]

        c.execute('SELECT SUM(count) FROM user_dragons')
        total_dragons_caught = c.fetchone()[0] or 0

        c.execute('SELECT COUNT(*) FROM alpha_dragons')
        total_alphas = c.fetchone()[0]

        conn.close()

        embed = discord.Embed(
            title="🐉 Dragon Bot Information",
            description="A comprehensive dragon catching and collection bot!",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="📊 Bot Statistics",
            value=f"🌐 **Servers:** {total_servers}\n"
                  f"👥 **Total Users:** {total_users:,}\n"
                  f"🎮 **Active Players:** {unique_users:,}\n"
                  f"📡 **Ping:** {latency}ms",
            inline=True
        )

        embed.add_field(
            name="🐉 Game Statistics",
            value=f"🎯 **Dragons Caught:** {total_dragons_caught:,}\n"
                  f"✨ **Alpha Dragons:** {total_alphas}\n"
                  f"🗂️ **Dragon Types:** 22\n"
                  f"🎁 **Pack Types:** 8",
            inline=True
        )

        embed.add_field(
            name="ℹ️ Features",
            value="• Dragon Catching & Trading\n"
                  "• Dragon Nest Progression\n"
                  "• Dragonpass System\n"
                  "• Alpha Dragons\n"
                  "• Pack Opening & Upgrades\n"
                  "• Lucky Charms & Boosts\n"
                  "• Leaderboards & Stats",
            inline=False
        )

        embed.set_footer(text="Use /help to see all commands!")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await interaction.followup.send(embed=embed, ephemeral=False)

    # ==================== HELP ====================

    @app_commands.command(name="help", description="View all available commands and how to use them")
    async def help_command(self, interaction: discord.Interaction):
        """Comprehensive help menu with all commands"""

        HELP_CATEGORIES = {
            "home": discord.Embed(
                title="🐉 Dragon Bot — Help",
                description=(
                    "Welcome to **Dragon Bot**! Catch, breed, trade and battle dragons with your server.\n\n"
                    "**Select a category below to explore commands.**\n\n"
                    "─────────────────────────────\n"
                    "🪙 **Economy** — Coins, balance, daily rewards\n"
                    "🐲 **Dragons** — Inventory, catching, dragonlogue\n"
                    "🛒 **Shop & Items** — Packs, shop, skills\n"
                    "🎯 **Progression** — Nest, Dragonpass, Breed, Adventures\n"
                    "⚔️ **Raids** — Ritual, raid boss, raid status\n"
                    "🏪 **Market** — Buy, sell, trade, gift\n"
                    "📊 **Community** — Leaderboard, achievements, bingo\n"
                    "⚙️ **Setup** — Admin & bot config\n"
                    "─────────────────────────────\n"
                    "💬 Need help? Join our [Support Server](https://discord.gg/X5YKZBh9xV)!"
                ),
                color=0x5865F2
            ),
            "economy": discord.Embed(
                title="🪙 Economy Commands",
                description=(
                    "> Manage your coins and rewards.\n\n"
                    "**`/bal [user]`**\n┗ Check your or another user's coin balance\n\n"
                    "**`/daily`**\n┗ Claim your daily reward (500 coins)\n\n"
                    "**`/coinflip <amount> [user]`**\n┗ Bet coins on a coin flip — PvP or vs bot\n\n"
                    "**`/stats [user]`**\n┗ View detailed player profile & stats\n\n"
                    "─────────────────────────────\n"
                    "💬 [Support Server](https://discord.gg/X5YKZBh9xV)"
                ),
                color=0xF1C40F
            ),
            "dragons": discord.Embed(
                title="🐲 Dragon Commands",
                description=(
                    "> Catch and manage your dragon collection.\n\n"
                    "**`/inv [user]`**\n┗ View your or another user's dragon inventory\n\n"
                    "**`/dragonlogue`**\n┗ Browse all dragons discovered in this server\n\n"
                    "**`/alphadragons`**\n┗ View craftable Alpha Dragons and their requirements\n\n"
                    "**`/skill`**\n┗ Check your passive item bonuses (Knowledge Book, Precision Stone)\n\n"
                    "💡 *Type `dragon` in chat to catch a spawned dragon!*\n\n"
                    "─────────────────────────────\n"
                    "💬 [Support Server](https://discord.gg/X5YKZBh9xV)"
                ),
                color=0x2ECC71
            ),
            "shop": discord.Embed(
                title="🛒 Shop & Items Commands",
                description=(
                    "> Spend your coins on packs and powerful items.\n\n"
                    "**`/shop`**\n┗ Browse the shop — packs, items & upgrades\n\n"
                    "**`/openpacks`**\n┗ Open your dragon packs to reveal new dragons\n\n"
                    "**`/inventory`**\n┗ View all your items and activate usable ones\n\n"
                    "**`/skill`**\n┗ See your active passive bonuses\n\n"
                    "💡 *Passive items stack — Knowledge Book (+2% catch) & Precision Stone (+5% raid)*\n"
                    "💡 *Night Vision is server-wide: +50% catches for 30 min*\n\n"
                    "─────────────────────────────\n"
                    "💬 [Support Server](https://discord.gg/X5YKZBh9xV)"
                ),
                color=0xE67E22
            ),
            "progression": discord.Embed(
                title="🎯 Progression Commands",
                description=(
                    "> Level up, breed dragons and go on adventures.\n\n"
                    "**`/dragonnest`**\n┗ Activate Dragon Nest bounties and manage upgrades\n\n"
                    "**`/dragonpass`**\n┗ Complete quests to level up (every 3 quests = 1 level, Level 30 = 2× Dragonscale)\n\n"
                    "**`/breed`**\n┗ Cross-breed two dragons (dynamic cooldowns based on rarity)\n\n"
                    "**`/breedcalc`**\n┗ Preview possible breeding outcomes before committing\n\n"
                    "**`/breedqueue`**\n┗ Schedule automatic breedings in a queue\n\n"
                    "**`/adventure`**\n┗ Send dragons on timed adventures for bonus rewards\n\n"
                    "**`/adventures`**\n┗ View your active adventures and collect rewards\n\n"
                    "💡 *Use `/breedcalc` before breeding — higher rarity = longer cooldowns (30m–3h)*\n\n"
                    "─────────────────────────────\n"
                    "💬 [Support Server](https://discord.gg/X5YKZBh9xV)"
                ),
                color=0x9B59B6
            ),
            "raids": discord.Embed(
                title="⚔️ Raid Commands",
                description=(
                    "> Team up with your server to take down powerful bosses.\n\n"
                    "**`/ritual <rarity>`**\n┗ Start a community ritual to summon a raid boss\n\n"
                    "**`/raidstatus`**\n┗ View the current raid boss and deal damage\n\n"
                    "💡 *Precision Stone increases your raid damage by +5%*\n\n"
                    "─────────────────────────────\n"
                    "💬 [Support Server](https://discord.gg/X5YKZBh9xV)"
                ),
                color=0xE74C3C
            ),
            "market": discord.Embed(
                title="🏪 Market & Trading Commands",
                description=(
                    "> Buy, sell, trade and gift dragons with other players.\n\n"
                    "**`/market`**\n┗ Browse all current marketplace listings\n\n"
                    "**`/marketsell`**\n┗ List one of your dragons for sale on the market\n\n"
                    "**`/mylistings`**\n┗ View and cancel your active market listings\n\n"
                    "**`/pricecheck`**\n┗ Check historical market prices for dragons or items\n\n"
                    "**`/trade`**\n┗ Initiate a direct dragon trade with another player\n\n"
                    "**`/gift`**\n┗ Gift a dragon to another user for free\n\n"
                    "💡 *Market prices update dynamically based on recent sales history*\n\n"
                    "─────────────────────────────\n"
                    "💬 [Support Server](https://discord.gg/X5YKZBh9xV)"
                ),
                color=0x1ABC9C
            ),
            "community": discord.Embed(
                title="📊 Community Commands",
                description=(
                    "> Compete, collect achievements and have fun.\n\n"
                    "**`/leaderboard [type]`**\n┗ Server rankings — `coins`, `dragons`, `level`, `alphas`\n\n"
                    "**`/achievements`**\n┗ View and track your personal achievement progress\n\n"
                    "**`/bingo`**\n┗ Get a dragon bingo card — complete any row, column or diagonal to win\n\n"
                    "─────────────────────────────\n"
                    "💬 [Support Server](https://discord.gg/X5YKZBh9xV)"
                ),
                color=0x3498DB
            ),
            "setup": discord.Embed(
                title="⚙️ Setup & Info Commands",
                description=(
                    "> Configure the bot for your server.\n\n"
                    "**`/setchannel`** *(Admin only)*\n┗ Set the channel where dragons will spawn\n\n"
                    "**`/info`**\n┗ View bot statistics and server info\n\n"
                    "**`/help`**\n┗ Show this help menu\n\n"
                    "─────────────────────────────\n"
                    "💬 Need help? Join our [Support Server](https://discord.gg/X5YKZBh9xV)!"
                ),
                color=0x95A5A6
            ),
        }

        SELECT_OPTIONS = [
            discord.SelectOption(label="🏠 Overview",    value="home"),
            discord.SelectOption(label="🪙 Economy",     value="economy"),
            discord.SelectOption(label="🐲 Dragons",      value="dragons"),
            discord.SelectOption(label="🛒 Shop & Items", value="shop"),
            discord.SelectOption(label="🎯 Progression",  value="progression"),
            discord.SelectOption(label="⚔️ Raids",            value="raids"),
            discord.SelectOption(label="🏪 Market",       value="market"),
            discord.SelectOption(label="📊 Community",    value="community"),
            discord.SelectOption(label="⚙️ Setup",           value="setup"),
        ]

        for embed in HELP_CATEGORIES.values():
            embed.set_footer(text="🐉 Dragon Bot  •  Use the menu below to navigate")

        class HelpSelect(discord.ui.Select):
            def __init__(self_inner):
                super().__init__(
                    placeholder="📖 Choose a category...",
                    min_values=1,
                    max_values=1,
                    options=SELECT_OPTIONS
                )

            async def callback(self_inner, select_interaction: discord.Interaction):
                selected = self_inner.values[0]
                embed = HELP_CATEGORIES[selected]
                await select_interaction.response.edit_message(embed=embed, view=self_inner.view)

        class HelpView(discord.ui.View):
            def __init__(self_inner):
                super().__init__(timeout=120)
                self_inner.add_item(HelpSelect())

        view = HelpView()
        await interaction.response.send_message(embed=HELP_CATEGORIES["home"], view=view)


    # ==================== PRICECHECK ====================

    @app_commands.command(name="pricecheck", description="Check market prices for a dragon or item")
    async def pricecheck(self, interaction: discord.Interaction):
        """Check market price history for dragons or items using a dropdown menu"""
        await interaction.response.defer(ephemeral=False)

        # Create a view with dropdown for dragons and items
        view = PricecheckView()
        embed = discord.Embed(
            title="💰 Price Check",
            description="Select a dragon or item to check prices for",
            color=0xFEE75C
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    # ==================== INVENTORY ====================

    @app_commands.command(name="inventory", description="View your dragon inventory")
    async def inventory(self, interaction: discord.Interaction, user: discord.User = None):
        target_user = user or interaction.user

        # Check if player is softlocked (only check own inventory, not others)
        if target_user.id == interaction.user.id:
            is_softlocked, upgrade_level = is_player_softlocked(interaction.guild_id, interaction.user.id)
            if is_softlocked:
                next_upgrade_level = upgrade_level + 1
                upgrade_cost = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('cost', 0)
                softlock_embed = discord.Embed(
                    title="🔒 Dragon Nest Upgrade Required!",
                    description=f"You have enough coins to upgrade your Dragon Nest!\n\n"
                                f"**Current Level:** {upgrade_level}\n"
                                f"**Upgrade Cost:** {upgrade_cost:,} 🪙\n\n"
                                f"You're **softlocked** from using items until you upgrade.\n"
                                f"Use `/dragonnest` to upgrade!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=softlock_embed, delete_after=5)
                return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0 ORDER BY count DESC',
                  (interaction.guild_id, target_user.id))
        dragons = c.fetchall()

        # Get dragonscales
        c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                  (interaction.guild_id, target_user.id))
        dragonscale_result = c.fetchone()
        dragonscale_minutes = dragonscale_result[0] if dragonscale_result else 0

        # Get Lucky Charms
        c.execute('SELECT count FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                  (interaction.guild_id, target_user.id))
        luckycharm_result = c.fetchone()
        luckycharm_count = luckycharm_result[0] if luckycharm_result else 0

        # Get new usable items counts
        c.execute('SELECT item_type, count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type IN (?, ?, ?, ?)',
                  (interaction.guild_id, target_user.id, 'dragon_magnet', 'night_vision', 'lucky_dice', 'dna'))
        usable_items_db = {item_type: count for item_type, count in c.fetchall()}

        # Get Packs
        c.execute('SELECT pack_type, count FROM user_packs WHERE guild_id = ? AND user_id = ? AND count > 0',
                  (interaction.guild_id, target_user.id))
        packs = c.fetchall()

        # Get Raid Boss Damage (keep connection open for this)
        c.execute('SELECT damage_dealt FROM raid_damage WHERE guild_id = ? AND user_id = ?',
                  (interaction.guild_id, target_user.id))
        raid_damage_result = c.fetchone()
        raid_damage = raid_damage_result[0] if raid_damage_result else 0

        # Get precision stones for raid damage buff
        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (interaction.guild_id, target_user.id, 'precision_stone'))
        precision_stone_result = c.fetchone()
        precision_stone_count = precision_stone_result[0] if precision_stone_result else 0

        conn.close()

        if not dragons:
            # Check if user has items or packs before saying "no dragons"
            has_items = dragonscale_minutes > 0 or luckycharm_count > 0 or any(usable_items_db.values()) or packs
            if not has_items:
                await interaction.response.send_message(f"📦 {target_user.display_name} has no dragons yet!", ephemeral=False)
                return
            # If they have items, continue to show them

        # Calculate stats with market values
        total_dragons = 0
        total_value = 0
        unique_types = 0

        if dragons:
            # Filter out invalid dragon types
            valid_dragons = [(dtype, count) for dtype, count in dragons if dtype in DRAGON_TYPES]
            total_dragons = sum(count for _, count in valid_dragons)
            unique_types = len(valid_dragons)

            # Calculate total market value (using marketplace prices if available, else base value)
            conn_market = get_db_connection(timeout=60.0)
            c_market = conn_market.cursor()

            for dragon_type, count in valid_dragons:
                if dragon_type not in DRAGON_TYPES:
                    continue

                # Get average market listing price for this dragon type in this server (active listings only)
                c_market.execute('''SELECT AVG(price) FROM market_listings
                                   WHERE guild_id = ? AND dragon_type = ?''',
                                (interaction.guild_id, dragon_type))
                market_result = c_market.fetchone()

                # Use market price if available, else base value
                if market_result and market_result[0]:
                    dragon_price = market_result[0]
                else:
                    dragon_price = DRAGON_TYPES[dragon_type]['value']

                total_value += dragon_price * count

            conn_market.close()

        embed = discord.Embed(
            title=f"🐉 {target_user.display_name}'s Dragon Collection",
            color=0x5865F2
        )

        # Stats section
        stats_text = f"🐉 **Total Dragons:** `{total_dragons:,}`\n"
        stats_text += f"🎯 **Unique Types:** `{unique_types}/22`\n"
        stats_text += f"💰 **Market Value:** `{int(total_value):,}` 🪙"
        embed.add_field(name="📊 Collection Stats", value=stats_text, inline=False)

        # Items section
        dragonscale_time_str = format_time_remaining(dragonscale_minutes * 60) if dragonscale_minutes > 0 else "0m"
        items_text = f"⚡ Dragonscale: {dragonscale_time_str}\n"
        items_text += f"🍀 Lucky Charms: {luckycharm_count}\n"
        items_text += f"🧬 DNA Samples: {usable_items_db.get('dna', 0)}\n"

        # Add new usable items
        for item_key, data in USABLE_ITEMS.items():
            count = usable_items_db.get(item_key, 0)
            if count > 0:
                items_text += f"{data['emoji']} {data['name']}: {count}\n"

        if packs:
            pack_text = "\n".join([f"{PACK_TYPES.get(pt, {'emoji': '📦'})['emoji']} `x{c:2}`" for pt, c in packs[:5]])
            items_text += f"\n**Packs:**\n{pack_text}"
        embed.add_field(name="🎁 Items", value=items_text, inline=True)

        # Raid Boss Max Damage section (only if user has dragons)
        valid_dragons_list = []
        if dragons:
            # Filter out invalid dragon types
            valid_dragons_list = [(dtype, count) for dtype, count in dragons if dtype in DRAGON_TYPES]

        if valid_dragons_list:
            # Calculate max damage potential
            max_damage = 0
            for dragon_type, count in valid_dragons_list:
                # Find rarity of this dragon
                dragon_rarity = 'common'
                for rarity, dragon_list in DRAGON_RARITY_TIERS.items():
                    if dragon_type in dragon_list:
                        dragon_rarity = rarity
                        break

                damage_per_dragon = RARITY_DAMAGE[dragon_rarity]
                max_damage += count * damage_per_dragon

            # Apply precision stone buff (+5% per stone, max 30%)
            precision_bonus = min(precision_stone_count * 0.05, 0.30)
            max_damage_with_buff = int(max_damage * (1 + precision_bonus))

            if precision_stone_count > 0:
                raid_text = f"💥 **Max Damage:** `{max_damage_with_buff:,}` 🎯\n"
                raid_text += f"(Base: `{max_damage:,}` + {int(precision_bonus*100)}% Buff)"
            else:
                raid_text = f"💥 **Max Damage:** `{max_damage:,}`"

            embed.add_field(name="🐲 Raid Potential", value=raid_text, inline=True)

        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer

        # Group by rarity using DRAGON_RARITY_TIERS (only if user has dragons)
        if valid_dragons_list:
            common_dragons = []
            uncommon_dragons = []
            rare_dragons = []
            epic_dragons = []
            legendary_dragons = []
            mythic_dragons = []
            ultra_dragons = []

            for dragon_type, count in valid_dragons_list:
                if dragon_type not in DRAGON_TYPES:
                    continue

                dragon_data = DRAGON_TYPES[dragon_type]
                dragon_text = f"{dragon_data['emoji']} **{dragon_data['name']}** x{count}"

                # Determine rarity from DRAGON_RARITY_TIERS
                rarity = None
                for r, dragon_list in DRAGON_RARITY_TIERS.items():
                    if dragon_type in dragon_list:
                        rarity = r
                        break

                if rarity == 'common':
                    common_dragons.append(dragon_text)
                elif rarity == 'uncommon':
                    uncommon_dragons.append(dragon_text)
                elif rarity == 'rare':
                    rare_dragons.append(dragon_text)
                elif rarity == 'epic':
                    epic_dragons.append(dragon_text)
                elif rarity == 'legendary':
                    legendary_dragons.append(dragon_text)
                elif rarity == 'mythic':
                    mythic_dragons.append(dragon_text)
                elif rarity == 'ultra':
                    ultra_dragons.append(dragon_text)

            # Add fields by rarity
            if common_dragons:
                embed.add_field(name="⚪ Common", value="\n".join(common_dragons[:10]), inline=False)
            if uncommon_dragons:
                embed.add_field(name="🟢 Uncommon", value="\n".join(uncommon_dragons[:10]), inline=False)
            if rare_dragons:
                embed.add_field(name="🔵 Rare", value="\n".join(rare_dragons[:10]), inline=False)
            if epic_dragons:
                embed.add_field(name="🟣 Epic", value="\n".join(epic_dragons[:10]), inline=False)
            if legendary_dragons:
                embed.add_field(name="🟡 Legendary", value="\n".join(legendary_dragons[:10]), inline=False)
            if mythic_dragons:
                embed.add_field(name="🌟 Mythic", value="\n".join(mythic_dragons[:10]), inline=False)
            if ultra_dragons:
                embed.add_field(name="💎 Ultra", value="\n".join(ultra_dragons[:10]), inline=False)

        embed.set_footer(text=f"Use /bal to see your coins")

        # Create buttons view if user has items to activate
        if target_user.id == interaction.user.id and (dragonscale_minutes > 0 or luckycharm_count > 0 or any(usable_items_db.values()) or packs):
            view = InventoryItemsView(interaction.guild_id, interaction.user.id, dragonscale_minutes, luckycharm_count, usable_items_db)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=False)

    # ==================== DRAGONLOGUE ====================

    @app_commands.command(name="dragonlogue", description="View all discovered dragons in this server")
    async def dragonlogue(self, interaction: discord.Interaction):
        """Shows all dragons discovered in the server with stats"""
        await interaction.response.defer(ephemeral=False)
        guild_id = interaction.guild_id

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get all discovered dragons
        c.execute('''SELECT dragon_type, first_discovered_by, first_discovered_at, total_caught
                     FROM server_discoveries WHERE guild_id = ?
                     ORDER BY first_discovered_at ASC''', (guild_id,))
        discoveries = c.fetchall()
        conn.close()

        if not discoveries:
            await interaction.followup.send("📖 No dragons have been discovered in this server yet! Start catching to fill the Dragonlogue!", ephemeral=False)
            return

        # Create pages (10 dragons per page)
        dragons_per_page = 10
        total_pages = (len(discoveries) + dragons_per_page - 1) // dragons_per_page

        class DragonlogueView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                self.current_page = 0

            def create_embed(self):
                start_idx = self.current_page * dragons_per_page
                end_idx = min(start_idx + dragons_per_page, len(discoveries))
                page_discoveries = discoveries[start_idx:end_idx]

                embed = discord.Embed(
                    title=f"📖 Dragonlogue - Server Dragon Catalog",
                    description=f"**{len(discoveries)}/{len(DRAGON_TYPES)} Dragons Discovered**\n\n",
                    color=discord.Color.gold()
                )

                for dragon_key, discoverer_id, discovered_at, total_caught in page_discoveries:
                    dragon_data = DRAGON_TYPES[dragon_key]
                    discoverer = interaction.guild.get_member(discoverer_id)
                    discoverer_name = discoverer.display_name if discoverer else "Unknown"

                    embed.description += f"{dragon_data['emoji']} **{dragon_data['name']}**\n"
                    embed.description += f"├ Value: **{dragon_data['value']:.2f}** coins\n"
                    embed.description += f"├ Spawn Rate: **{dragon_data['spawn_chance']:.2f}%**\n"
                    embed.description += f"├ Times Caught: **{total_caught:,}**\n"
                    embed.description += f"└ First Discovery: {discoverer_name}\n\n"

                embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages} • {len(discoveries)} discovered")
                return embed

            @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.gray)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page > 0:
                    self.current_page -= 1
                await interaction.response.edit_message(embed=self.create_embed(), view=self)

            @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.gray)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                await interaction.response.edit_message(embed=self.create_embed(), view=self)

        view = DragonlogueView()
        await interaction.followup.send(embed=view.create_embed(), view=view, ephemeral=False)

    # ==================== STATS ====================

    @app_commands.command(name="stats", description="View detailed statistics for a user")
    @app_commands.describe(user="User to check stats for (leave empty for yourself)")
    async def stats(self, interaction: discord.Interaction, user: discord.Member = None):
        """Shows detailed user statistics"""
        await interaction.response.defer(ephemeral=False)
        if user is None:
            user = interaction.user

        guild_id = interaction.guild_id
        user_id = user.id

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get balance
        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        balance_result = c.fetchone()
        balance = balance_result[0] if balance_result else 0

        # Get total dragons
        c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        total_dragons = c.fetchone()[0] or 0

        # Get unique dragon types
        c.execute('SELECT COUNT(DISTINCT dragon_type) FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                  (guild_id, user_id))
        unique_dragons = c.fetchone()[0] or 0

        # Get Dragon Nest level
        c.execute('SELECT level, xp, bounties_completed FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user_id))
        nest_result = c.fetchone()
        nest_level = nest_result[0] if nest_result else 0
        nest_xp = nest_result[1] if nest_result else 0
        bounties_completed = nest_result[2] if nest_result else 0

        # Get Dragonpass level and XP
        c.execute('SELECT level, xp FROM dragonpass WHERE guild_id = ? AND user_id = ? AND season = 1',
                  (guild_id, user_id))
        pass_result = c.fetchone()
        pass_level = pass_result[0] if pass_result else 0
        pass_xp = pass_result[1] if pass_result else 0

        # Get Alpha Dragons
        c.execute('SELECT COUNT(*), SUM(catch_boost) FROM user_alphas WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user_id))
        alpha_result = c.fetchone()
        alpha_count = alpha_result[0] or 0
        total_catch_boost = alpha_result[1] or 0

        # Get rarest dragon
        c.execute('''SELECT dragon_type, count FROM user_dragons
                     WHERE guild_id = ? AND user_id = ? AND count > 0
                     ORDER BY count DESC''', (guild_id, user_id))
        all_user_dragons = c.fetchall()

        rarest_dragon = None
        if all_user_dragons:
            # Find rarest by spawn chance
            rarest_dragon = min(all_user_dragons, key=lambda x: DRAGON_TYPES[x[0]]['spawn_chance'])[0]

        # Get fastest and slowest catch times
        c.execute('''SELECT dragon_type, fastest_catch FROM user_dragons
                     WHERE guild_id = ? AND user_id = ? AND fastest_catch > 0
                     ORDER BY fastest_catch ASC LIMIT 1''', (guild_id, user_id))
        fastest_result = c.fetchone()

        c.execute('''SELECT dragon_type, slowest_catch FROM user_dragons
                     WHERE guild_id = ? AND user_id = ? AND slowest_catch > 0
                     ORDER BY slowest_catch DESC LIMIT 1''', (guild_id, user_id))
        slowest_result = c.fetchone()

        conn.close()

        embed = discord.Embed(
            title=f"📊 {user.display_name}'s Profile",
            color=0x5865F2
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        # General Stats
        embed.add_field(
            name="💰 Economy",
            value=f"Balance: **{balance:,.2f}** coins\nTotal Dragons: **{total_dragons:,}**\nUnique Types: **{unique_dragons}/{len(DRAGON_TYPES)}**",
            inline=True
        )

        # Dragon Nest Stats
        level_name = LEVEL_NAMES.get(nest_level, "Hatchling")
        embed.add_field(
            name="🏆 Dragon Nest",
            value=f"Level: **{nest_level}** ({level_name})\nBounties: **{bounties_completed}**",
            inline=True
        )

        # Dragonpass Stats
        embed.add_field(
            name="🎁 Dragonpass",
            value=f"Level: **{pass_level}**/30\nSeason: **1**",
            inline=True
        )

        # Alpha Dragons
        embed.add_field(
            name="✨ Alpha Dragons",
            value=f"Count: **{alpha_count}**\nCatch Boost: **+{total_catch_boost*100:.1f}%**",
            inline=True
        )

        # Rarest Dragon
        if rarest_dragon:
            rarest_data = DRAGON_TYPES[rarest_dragon]
            embed.add_field(
                name="🌟 Rarest Dragon Owned",
                value=f"{rarest_data['emoji']} **{rarest_data['name']}**\n(Spawn Rate: {rarest_data['spawn_chance']:.2f}%)",
                inline=False
            )

        # Catch Times
        if fastest_result or slowest_result:
            catch_times_text = ""
            if fastest_result:
                fastest_dragon = DRAGON_TYPES[fastest_result[0]]
                fastest_time = fastest_result[1]
                catch_times_text += f"⚡ **Fastest:** {fastest_time:.2f}s ({fastest_dragon['emoji']} {fastest_dragon['name']})\n"
            if slowest_result:
                slowest_dragon = DRAGON_TYPES[slowest_result[0]]
                slowest_time = slowest_result[1]
                catch_times_text += f"🐢 **Slowest:** {slowest_time:.2f}s ({slowest_dragon['emoji']} {slowest_dragon['name']})"

            if catch_times_text:
                embed.add_field(
                    name="⏱️ Catch Times",
                    value=catch_times_text,
                    inline=False
                )

        await interaction.followup.send(embed=embed, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(DragonsCog(bot))
