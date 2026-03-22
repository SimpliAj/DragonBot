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


class MarketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="market", description="Marketplace - browse, sell, and manage listings")
    @app_commands.describe(
        action="What do you want to do?",
        category="Browse dragons or items (for browse action)",
        rarity="Filter by dragon rarity (for browse action)",
        sort_by="Sort listings (for browse action)"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Browse Marketplace", value="browse"),
            app_commands.Choice(name="Sell Item/Dragon", value="sell"),
            app_commands.Choice(name="My Listings", value="mylistings"),
        ],
        category=[
            app_commands.Choice(name="Dragons", value="dragon"),
            app_commands.Choice(name="Items", value="item"),
            app_commands.Choice(name="All Listings", value="all"),
        ],
        rarity=[
            app_commands.Choice(name="Common", value="common"),
            app_commands.Choice(name="Uncommon", value="uncommon"),
            app_commands.Choice(name="Rare", value="rare"),
            app_commands.Choice(name="Epic", value="epic"),
            app_commands.Choice(name="Legendary", value="legendary"),
            app_commands.Choice(name="Mythic", value="mythic"),
            app_commands.Choice(name="Ultra", value="ultra"),
        ],
        sort_by=[
            app_commands.Choice(name="Lowest Price", value="price_low"),
            app_commands.Choice(name="Highest Price", value="price_high"),
            app_commands.Choice(name="Newest First", value="newest"),
            app_commands.Choice(name="Oldest First", value="oldest"),
        ]
    )
    async def market(self, interaction: discord.Interaction, action: str, category: str = "all", rarity: str = None, sort_by: str = None):
        """Main marketplace command with browse, sell, and listing management"""
        if action == "browse":
            await self.market_browse(interaction, category, rarity, sort_by)
        elif action == "sell":
            await self.market_sell(interaction)
        elif action == "mylistings":
            await self.market_mylistings(interaction)
        else:
            await interaction.response.send_message("❌ Invalid action!", ephemeral=True)

    async def market_browse(self, interaction: discord.Interaction, category: str = "all", rarity: str = None, sort_by: str = None):
        """Browse marketplace listings with category filters"""
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
                            f"You're **softlocked** from using the market until you upgrade.\n"
                            f"Use `/dragonnest` to upgrade!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=softlock_embed, delete_after=5)
            return

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        try:
            # Get all active listings for this server
            c.execute('''SELECT listing_id, seller_id, dragon_type, price, listed_at, item_type
                         FROM market_listings
                         WHERE guild_id = ?''',
                      (interaction.guild_id,))
            all_listings = c.fetchall()
        except sqlite3.Error as e:
            conn.close()
            await interaction.followup.send(f"❌ Database error: {e}", ephemeral=False)
            return

        # Handle null item_type (convert to 'dragon')
        all_listings = [(lid, sid, dt, p, la, it if it is not None else 'dragon') for lid, sid, dt, p, la, it in all_listings]

        # Filter by category
        if category == "dragon":
            listings = [l for l in all_listings if l[5] in ['dragon', 'dragonscale']]
        elif category == "item":
            listings = [l for l in all_listings if l[5] not in ['dragon', 'dragonscale']]
        else:
            listings = all_listings

        # Filter by rarity if specified
        if rarity:
            filtered_listings = []
            for listing in listings:
                listing_id, seller_id, dragon_type, price, listed_at, item_type = listing
                if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                    # Check rarity
                    dragon_rarity = None
                    for r, dragons in DRAGON_RARITY_TIERS.items():
                        if dragon_type in dragons:
                            dragon_rarity = r
                            break
                    if dragon_rarity == rarity:
                        filtered_listings.append(listing)
            listings = filtered_listings
        else:
            listings = listings

        if not listings:
            conn.close()
            cat_text = " dragons" if category == "dragon" else " items" if category == "item" else ""
            filter_text = f" with **{rarity}** rarity" if rarity else ""
            embed = discord.Embed(
                title="🏪 Marketplace",
                description=f"No {cat_text} listed{filter_text}!\n\nUse `/market sell` to list dragons or items for sale.",
                color=0x5865F2
            )
            await interaction.followup.send(embed=embed)
            return

        # Sort listings
        if sort_by == "price_low":
            listings.sort(key=lambda x: x[3])
        elif sort_by == "price_high":
            listings.sort(key=lambda x: x[3], reverse=True)
        elif sort_by == "newest":
            listings.sort(key=lambda x: x[4], reverse=True)
        elif sort_by == "oldest":
            listings.sort(key=lambda x: x[4])

        # Limit to 25 most relevant
        listings = listings[:25]

        # Build marketplace embed
        filter_info = ""
        if category != "all":
            filter_info = f"\n**Category:** {category.title()}"
        if rarity:
            filter_info += f"\n**Rarity:** {rarity.title()}"
        if sort_by:
            sort_labels = {
                "price_low": "Lowest Price First", "price_high": "Highest Price First",
                "newest": "Newest First", "oldest": "Oldest First"
            }
            filter_info += f"\n**Sort:** {sort_labels.get(sort_by, '')}"

        embed = discord.Embed(
            title="🏪 Marketplace",
            description=f"Browse and buy listings!{filter_info}\n\n**📊 Available:** {len(listings)} listing{'s' if len(listings) != 1 else ''}",
            color=0x5865F2
        )

        embed.add_field(
            name="💡 How to Buy",
            value="Click a button below to purchase an item instantly!",
            inline=False
        )

        # Get price statistics for unique dragon types in listings
        unique_types = list(set(l[2] for l in listings if l[5] == 'dragon'))
        price_info = {}

        for dtype in unique_types:
            if dtype not in DRAGON_TYPES:
                continue

            # Get last 5 sales for this dragon type
            c.execute('''SELECT price FROM market_sales
                         WHERE guild_id = ? AND dragon_type = ?
                         ORDER BY sold_at DESC LIMIT 5''',
                      (interaction.guild_id, dtype))
            recent_sales = c.fetchall()

            if recent_sales:
                last_sale = recent_sales[0][0]
                avg_price = int(sum(s[0] for s in recent_sales) / len(recent_sales))
                price_info[dtype] = {'last': last_sale, 'avg': avg_price}
            else:
                recommended = int(DRAGON_TYPES[dtype]['value'] * 4)
                price_info[dtype] = {'last': None, 'avg': recommended}

        conn.close()

        # Build listing display in embed
        listings_by_type = {}
        for listing in listings:
            listing_id, seller_id, dragon_type, price, listed_at, item_type = listing
            seller = interaction.guild.get_member(seller_id)
            seller_name = seller.display_name if seller else "Unknown"

            key = f"{item_type}_{dragon_type}" if item_type == 'dragon' else item_type
            if key not in listings_by_type:
                listings_by_type[key] = []
            listings_by_type[key].append({
                'id': listing_id, 'seller': seller_name, 'price': price,
                'dragon_type': dragon_type, 'item_type': item_type
            })

        # Add listings to embed
        listings_text = ""
        for key, items in listings_by_type.items():
            item_type = items[0]['item_type']
            if item_type == 'dragon':
                dragon_type = items[0]['dragon_type']
                dragon_data = DRAGON_TYPES[dragon_type]
                listings_text += f"\n**{dragon_data['emoji']} {dragon_data['name']}**\n"
            elif item_type == 'lucky_charm':
                listings_text += f"\n**🍀 Lucky Charm**\n"
            elif item_type == 'dna':
                listings_text += f"\n**🧬 Dragon DNA**\n"
            elif item_type == 'dragonscale':
                listings_text += f"\n**<:dragonscale:1446278170998341693> Dragonscale**\n"
            elif item_type.startswith('pack_'):
                pack_type = item_type.replace('pack_', '')
                pack_names_map = {
                    'wooden': ('Wooden Pack', '<:woodenchest:1446170002708238476>'),
                    'stone': ('Stone Pack', '<:stonechest:1446169958265389247>'),
                    'bronze': ('Bronze Pack', '<:bronzechest:1446169758599745586>'),
                    'silver': ('Silver Pack', '<:silverchest:1446169917996011520>'),
                    'gold': ('Gold Pack', '<:goldchest:1446169876438978681>'),
                    'platinum': ('Platinum Pack', '<:platinumchest:1446169876438978681>'),
                    'diamond': ('Diamond Pack', '<:diamondchest:1446169830720929985>'),
                    'celestial': ('Celestial Pack', '<:celestialchest:1446169830720929985>'),
                }
                if pack_type in pack_names_map:
                    name, emoji = pack_names_map[pack_type]
                    listings_text += f"\n**{emoji} {name}**\n"
            elif item_type == 'night_vision':
                listings_text += f"\n**🌙 Night Vision**\n"
            elif item_type == 'lucky_dice':
                listings_text += f"\n**🎰 Lucky Dice**\n"

            for item in items[:5]:  # Show max 5 per type
                listings_text += f"└ {item['price']:,}🪙 by {item['seller']}\n"

            if len(items) > 5:
                listings_text += f"└ +{len(items) - 5} more\n"

        embed.add_field(name="📦 Active Listings", value=listings_text or "No items available", inline=False)

        # Create view with buttons for purchasing
        class MarketView(discord.ui.View):
            def __init__(self, listings, guild):
                super().__init__(timeout=300)
                self.listings = listings
                self.guild = guild

                # Add a button for each listing
                for idx, listing in enumerate(listings[:5]):  # Limit to 5 buttons per row
                    listing_id, seller_id, dragon_type, price, listed_at, item_type = listing
                    seller = guild.get_member(seller_id)
                    seller_name = seller.display_name if seller else "Unknown"

                    # Create button label
                    if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                        dragon_data = DRAGON_TYPES[dragon_type]
                        btn_label = f"{dragon_data['name'][:15]}-{price}"
                    elif item_type == 'lucky_charm':
                        btn_label = f"Charm-{price}"
                    elif item_type == 'dna':
                        btn_label = f"DNA-{price}"
                    elif item_type == 'dragonscale':
                        btn_label = f"Scale-{price}"
                    elif item_type == 'night_vision':
                        btn_label = f"Vision-{price}"
                    elif item_type == 'lucky_dice':
                        btn_label = f"Dice-{price}"
                    else:
                        btn_label = f"Item-{price}"

                    btn_label = btn_label[:80]

                    button = discord.ui.Button(
                        label=btn_label,
                        style=discord.ButtonStyle.primary,
                        custom_id=f"buy_{idx}"
                    )

                    button.callback = lambda i, lid=listing_id: self.process_purchase(i, lid)
                    self.add_item(button)

            async def process_purchase(self, interaction: discord.Interaction, listing_id: int):
                """Process the purchase"""
                await interaction.response.defer()

                # Re-fetch listing from database to ensure it's still available
                conn = get_db_connection(timeout=60.0)
                c = conn.cursor()
                c.execute('''SELECT listing_id, seller_id, dragon_type, price, listed_at, item_type
                             FROM market_listings
                             WHERE listing_id = ? AND guild_id = ?''',
                          (listing_id, interaction.guild_id))
                db_listing = c.fetchone()

                if not db_listing:
                    conn.close()
                    await interaction.followup.send("❌ This listing is no longer available!", ephemeral=False)
                    return

                listing_id, seller_id, dragon_type, price, listed_at, item_type = db_listing

                # Handle null item_type (default to 'dragon')
                if item_type is None:
                    item_type = 'dragon'

                seller = self.guild.get_member(seller_id)
                seller_name = seller.display_name if seller else "Unknown"

                # Check if buyer has enough coins
                buyer_data = get_user(interaction.guild_id, interaction.user.id)
                buyer_balance = buyer_data[2]

                if buyer_balance < price:
                    await interaction.followup.send(
                        f"❌ You need {price} 🪙 but only have {int(buyer_balance)} 🪙!",
                        ephemeral=False
                    )
                    conn.close()
                    return

                # Check if buyer is trying to buy their own listing
                if seller_id == interaction.user.id:
                    await interaction.followup.send("❌ You can't buy your own listing!", ephemeral=False)
                    conn.close()
                    return

                # Process transaction based on item type
                item_desc = ""

                if item_type == 'lucky_charm':
                    c.execute('SELECT count FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                              (interaction.guild_id, seller_id))
                    seller_item = c.fetchone()

                    if not seller_item or seller_item[0] < 1:
                        c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                        conn.commit()
                        conn.close()
                        await interaction.followup.send("❌ Seller no longer has this item! Listing removed.", ephemeral=False)
                        return

                    c.execute('UPDATE user_luckycharms SET count = count - 1 WHERE guild_id = ? AND user_id = ?',
                              (interaction.guild_id, seller_id))
                    c.execute('INSERT INTO user_luckycharms (guild_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + 1',
                              (interaction.guild_id, interaction.user.id))
                    item_desc = "🍀 Lucky Charm"

                elif item_type == 'dna':
                    c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                              (interaction.guild_id, seller_id, 'dna'))
                    seller_item = c.fetchone()

                    if not seller_item or seller_item[0] < 1:
                        c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                        conn.commit()
                        conn.close()
                        await interaction.followup.send("❌ Seller no longer has this item! Listing removed.", ephemeral=False)
                        return

                    c.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                              (interaction.guild_id, seller_id, 'dna'))
                    c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, 1) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + 1',
                              (interaction.guild_id, interaction.user.id, 'dna'))
                    item_desc = "🧬 Dragon DNA"

                elif item_type == 'dragonscale':
                    c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                              (interaction.guild_id, seller_id))
                    seller_item = c.fetchone()

                    if not seller_item or seller_item[0] < 1:
                        c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                        conn.commit()
                        conn.close()
                        await interaction.followup.send("❌ Seller no longer has this item! Listing removed.", ephemeral=False)
                        return

                    c.execute('UPDATE dragonscales SET minutes = minutes - 1 WHERE guild_id = ? AND user_id = ?',
                              (interaction.guild_id, seller_id))
                    c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, 1) ON CONFLICT(guild_id, user_id) DO UPDATE SET minutes = minutes + 1',
                              (interaction.guild_id, interaction.user.id))
                    item_desc = "<:dragonscale:1446278170998341693> Dragonscale"

                elif item_type.startswith('pack_'):
                    pack_type = item_type.replace('pack_', '')
                    pack_names_map = {
                        'wooden': 'Wooden Pack', 'stone': 'Stone Pack', 'bronze': 'Bronze Pack', 'silver': 'Silver Pack',
                        'gold': 'Gold Pack', 'platinum': 'Platinum Pack', 'diamond': 'Diamond Pack', 'celestial': 'Celestial Pack'
                    }
                    pack_emojis_map = {
                        'wooden': '<:woodenchest:1446170002708238476>', 'stone': '<:stonechest:1446169958265389247>',
                        'bronze': '<:bronzechest:1446169758599745586>', 'silver': '<:silverchest:1446169917996011520>',
                        'gold': '<:goldchest:1446169876438978681>', 'platinum': '<:platinumchest:1446169876438978681>',
                        'diamond': '<:diamondchest:1446169830720929985>', 'celestial': '<:celestialchest:1446169830720929985>'
                    }

                    c.execute('SELECT count FROM user_packs WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                              (interaction.guild_id, seller_id, pack_type))
                    seller_item = c.fetchone()

                    if not seller_item or seller_item[0] < 1:
                        c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                        conn.commit()
                        conn.close()
                        await interaction.followup.send("❌ Seller no longer has this item! Listing removed.", ephemeral=False)
                        return

                    c.execute('UPDATE user_packs SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                              (interaction.guild_id, seller_id, pack_type))
                    c.execute('INSERT INTO user_packs (guild_id, user_id, pack_type, count) VALUES (?, ?, ?, 1) ON CONFLICT(guild_id, user_id, pack_type) DO UPDATE SET count = count + 1',
                              (interaction.guild_id, interaction.user.id, pack_type))
                    item_desc = f"{pack_emojis_map[pack_type]} {pack_names_map[pack_type]}"

                elif item_type in ['night_vision', 'lucky_dice']:
                    c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                              (interaction.guild_id, seller_id, item_type))
                    seller_item = c.fetchone()

                    if not seller_item or seller_item[0] < 1:
                        c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                        conn.commit()
                        conn.close()
                        await interaction.followup.send("❌ Seller no longer has this item! Listing removed.", ephemeral=False)
                        return

                    c.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                              (interaction.guild_id, seller_id, item_type))
                    c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, 1) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + 1',
                              (interaction.guild_id, interaction.user.id, item_type))

                    item_emoji_map = {'night_vision': '🌙', 'lucky_dice': '🎰'}
                    item_name_map = {'night_vision': 'Night Vision', 'lucky_dice': 'Lucky Dice'}
                    item_desc = f"{item_emoji_map[item_type]} {item_name_map[item_type]}"

                else:  # It's a dragon or unknown item
                    if dragon_type:
                        c.execute('SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                  (interaction.guild_id, seller_id, dragon_type))
                        seller_count = c.fetchone()

                        if not seller_count or seller_count[0] < 1:
                            c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                            conn.commit()
                            conn.close()
                            await interaction.followup.send("❌ Seller no longer has this dragon! Listing removed.", ephemeral=False)
                            return

                        # Transfer dragon from seller to buyer
                        await add_dragons(interaction.guild_id, seller_id, dragon_type, -1)
                        await add_dragons(interaction.guild_id, interaction.user.id, dragon_type, 1)

                        if dragon_type in DRAGON_TYPES:
                            dragon_data = DRAGON_TYPES[dragon_type]
                            item_desc = f"{dragon_data['emoji']} {dragon_data['name']}"
                        else:
                            item_desc = f"🐉 Dragon ({dragon_type})"

                        # Record sale for price history
                        c.execute('INSERT INTO market_sales (guild_id, dragon_type, price, sold_at) VALUES (?, ?, ?, ?)',
                                  (interaction.guild_id, dragon_type, price, int(time.time())))
                    else:
                        c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                        conn.commit()
                        conn.close()
                        await interaction.followup.send("❌ Unknown item type in listing. Listing removed.", ephemeral=False)
                        return

                # Remove listing BEFORE updating balance
                c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                conn.commit()
                conn.close()

                # Transfer coins from buyer to seller
                try:
                    await asyncio.to_thread(update_balance, interaction.guild_id, interaction.user.id, -price)
                    await asyncio.to_thread(update_balance, interaction.guild_id, seller_id, price)
                except Exception as e:
                    await interaction.followup.send(f"❌ Error processing payment: {e}", ephemeral=False)
                    return

                # Send confirmation
                embed = discord.Embed(
                    title="✅ Purchase Successful!",
                    description=f"You bought **{item_desc}** from **{seller_name}** for **{price}** 🪙",
                    color=discord.Color.green()
                )

                await interaction.followup.send(embed=embed, ephemeral=False)

        # Show the market view
        try:
            embed.set_footer(text="💰 Use /market sell to list your items | 🔄 Use /market browse for more options")
            view = MarketView(listings, interaction.guild)
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)
        except Exception as e:
            await interaction.followup.send(f"❌ Error displaying marketplace: {e}", ephemeral=False)


    async def market_sell(self, interaction: discord.Interaction):
        """List a dragon or item for sale - 2 step process"""
        await interaction.response.defer()

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Check if user has any listing slots available
        c.execute('SELECT COUNT(*) FROM market_listings WHERE guild_id = ? AND seller_id = ?',
                  (interaction.guild_id, interaction.user.id))
        listing_count = c.fetchone()[0]

        if listing_count >= 5:
            await interaction.followup.send("❌ You can only have 5 active listings at once!", ephemeral=False)
            conn.close()
            return

        # Step 1: Check what categories user has items in
        has_dragons = False
        has_items = False

        c.execute('SELECT COUNT(*) FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                  (interaction.guild_id, interaction.user.id))
        if c.fetchone()[0] > 0:
            has_dragons = True

        # Check all item types
        c.execute('SELECT COUNT(*) FROM user_luckycharms WHERE guild_id = ? AND user_id = ? AND count > 0',
                  (interaction.guild_id, interaction.user.id))
        if c.fetchone()[0] > 0:
            has_items = True

        if not has_items:
            c.execute('SELECT COUNT(*) FROM user_items WHERE guild_id = ? AND user_id = ? AND count > 0',
                      (interaction.guild_id, interaction.user.id))
            if c.fetchone()[0] > 0:
                has_items = True

        if not has_items:
            c.execute('SELECT COUNT(*) FROM dragonscales WHERE guild_id = ? AND user_id = ? AND minutes > 0',
                      (interaction.guild_id, interaction.user.id))
            if c.fetchone()[0] > 0:
                has_items = True

        if not has_items:
            c.execute('SELECT COUNT(*) FROM user_packs WHERE guild_id = ? AND user_id = ? AND count > 0',
                      (interaction.guild_id, interaction.user.id))
            if c.fetchone()[0] > 0:
                has_items = True

        conn.close()

        if not has_dragons and not has_items:
            await interaction.followup.send(
                "❌ You don't have any dragons or items to sell!",
                ephemeral=False
            )
            return

        # Show category selection
        class CategoryView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)

            @discord.ui.button(label="🐉 Dragons", style=discord.ButtonStyle.primary)
            async def dragons_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if not has_dragons:
                    await btn_interaction.response.send_message("❌ You don't have any dragons to sell!", ephemeral=True)
                    return
                await self.show_item_select(btn_interaction, 'dragon')

            @discord.ui.button(label="📦 Items", style=discord.ButtonStyle.primary)
            async def items_button(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if not has_items:
                    await btn_interaction.response.send_message("❌ You don't have any items to sell!", ephemeral=True)
                    return
                await self.show_item_select(btn_interaction, 'items')

            async def show_item_select(self, interaction: discord.Interaction, category: str):
                """Show item selection for chosen category"""
                await interaction.response.defer()
                sellable_items = []

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                if category == 'dragon':
                    # Get dragons
                    c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0',
                              (interaction.guild_id, interaction.user.id))
                    for dragon_type, count in c.fetchall():
                        if dragon_type in DRAGON_TYPES:
                            dragon_data = DRAGON_TYPES[dragon_type]
                            sellable_items.append({
                                'type': 'dragon', 'key': dragon_type,
                                'label': f"{dragon_data['name']} Dragon (x{count})", 'emoji': dragon_data['emoji']
                            })
                else:
                    # Get all items
                    # Lucky charms
                    c.execute('SELECT count FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                              (interaction.guild_id, interaction.user.id))
                    result = c.fetchone()
                    if result and result[0] > 0:
                        sellable_items.append({'type': 'lucky_charm', 'key': 'lucky_charm', 'label': f"Lucky Charm (x{result[0]})", 'emoji': '🍀'})

                    # DNA
                    c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                              (interaction.guild_id, interaction.user.id, 'dna'))
                    result = c.fetchone()
                    if result and result[0] > 0:
                        sellable_items.append({'type': 'dna', 'key': 'dna', 'label': f"DNA Sample (x{result[0]})", 'emoji': '🧬'})

                    # Dragonscales
                    c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                              (interaction.guild_id, interaction.user.id))
                    result = c.fetchone()
                    if result and result[0] > 0:
                        sellable_items.append({'type': 'dragonscale', 'key': 'dragonscale', 'label': f"Dragonscale (x{result[0]})", 'emoji': '<:dragonscale:1446278170998341693>'})

                    # Packs
                    pack_types = ['wooden', 'stone', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'celestial']
                    pack_names = {
                        'wooden': 'Wooden Pack', 'stone': 'Stone Pack', 'bronze': 'Bronze Pack', 'silver': 'Silver Pack',
                        'gold': 'Gold Pack', 'platinum': 'Platinum Pack', 'diamond': 'Diamond Pack', 'celestial': 'Celestial Pack'
                    }
                    pack_emojis = {
                        'wooden': '<:woodenchest:1446170002708238476>', 'stone': '<:stonechest:1446169958265389247>',
                        'bronze': '<:bronzechest:1446169758599745586>', 'silver': '<:silverchest:1446169917996011520>',
                        'gold': '<:goldchest:1446169876438978681>', 'platinum': '<:platinumchest:1446169876438978681>',
                        'diamond': '<:diamondchest:1446169830720929985>', 'celestial': '<:celestialchest:1446169830720929985>'
                    }

                    for pack_type in pack_types:
                        c.execute('SELECT count FROM user_packs WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                                  (interaction.guild_id, interaction.user.id, pack_type))
                        result = c.fetchone()
                        if result and result[0] > 0:
                            sellable_items.append({'type': 'pack', 'key': pack_type, 'label': f"{pack_names[pack_type]} (x{result[0]})", 'emoji': pack_emojis[pack_type]})

                    # Usable items
                    for usable_item in ['night_vision', 'lucky_dice']:
                        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                  (interaction.guild_id, interaction.user.id, usable_item))
                        result = c.fetchone()
                        if result and result[0] > 0:
                            emoji_map = {'night_vision': '🌙', 'lucky_dice': '🎰'}
                            name_map = {'night_vision': 'Night Vision', 'lucky_dice': 'Lucky Dice'}
                            sellable_items.append({'type': 'usable', 'key': usable_item, 'label': f"{name_map[usable_item]} (x{result[0]})", 'emoji': emoji_map[usable_item]})

                conn.close()

                if not sellable_items:
                    await interaction.followup.send("❌ No items in this category!", ephemeral=False)
                    return

                # Create dropdown for specific items
                class ItemSelect(discord.ui.Select):
                    def __init__(self, items):
                        self.items_data = items
                        options = []
                        for item in items:
                            emoji_str = item['emoji']
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
                                    label=item['label'][:100],
                                    value=item['key'],
                                    emoji=emoji_obj
                                )
                            )

                        super().__init__(placeholder="Select item to sell...", options=options, min_values=1, max_values=1)

                    async def callback(self, select_interaction: discord.Interaction):
                        await self.handle_selection(select_interaction, self.values[0])

                    async def handle_selection(self, select_interaction: discord.Interaction, selected_key: str):
                        """Handle item selection and show amount/price"""
                        # Find amount available
                        amount_available = 0
                        for item in self.items_data:
                            if item['key'] == selected_key:
                                label = item['label']
                                if '(x' in label:
                                    amount_available = int(label.split('(x')[1].split(')')[0])
                                else:
                                    amount_available = 1
                                break

                        # Show amount selection
                        amount_options = [discord.SelectOption(label="1", value="1")]
                        for i in range(2, min(amount_available + 1, 11)):
                            amount_options.append(discord.SelectOption(label=str(i), value=str(i)))

                        if amount_available > 10:
                            amount_options.append(discord.SelectOption(label=f"All ({amount_available})", value=str(amount_available)))

                        class AmountSelect(discord.ui.Select):
                            async def callback(self, amount_inter: discord.Interaction):
                                amount = int(self.values[0])
                                await self.show_price(amount_inter, selected_key, amount)

                            async def show_price(self, amount_inter: discord.Interaction, item_key: str, amount: int):
                                """Show price input modal"""
                                class PriceModal(discord.ui.Modal, title="Set Sell Price"):
                                    price_input = discord.ui.TextInput(
                                        label="Price per unit (coins)",
                                        placeholder="Enter price (1-1000000)",
                                        required=True,
                                        min_length=1,
                                        max_length=7
                                    )

                                    async def on_submit(self, modal_inter: discord.Interaction):
                                        try:
                                            price = int(self.price_input.value)
                                        except ValueError:
                                            await modal_inter.response.send_message("❌ Price must be a number!", ephemeral=True)
                                            return

                                        if price <= 0 or price > 1000000:
                                            await modal_inter.response.send_message("❌ Price must be between 1 and 1,000,000!", ephemeral=True)
                                            return

                                        # Insert listing
                                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                        c = conn.cursor()

                                        item_type = None
                                        dragon_type_to_store = None
                                        pack_type_to_store = None

                                        if item_key in DRAGON_TYPES:
                                            item_type = 'dragon'
                                            dragon_type_to_store = item_key
                                        elif item_key in ['wooden', 'stone', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'celestial']:
                                            item_type = 'pack'
                                            pack_type_to_store = item_key
                                        else:
                                            item_type = item_key
                                            dragon_type_to_store = None

                                        c.execute('''INSERT INTO market_listings
                                                     (guild_id, seller_id, dragon_type, price, listed_at, item_type)
                                                     VALUES (?, ?, ?, ?, ?, ?)''',
                                                  (modal_inter.guild_id, modal_inter.user.id,
                                                   dragon_type_to_store,
                                                   price, int(time.time()), item_type if item_type != 'pack' else f'pack_{pack_type_to_store}'))

                                        # Remove from inventory
                                        if item_key in DRAGON_TYPES:
                                            c.execute('UPDATE user_dragons SET count = count - ? WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                                      (amount, modal_inter.guild_id, modal_inter.user.id, item_key))
                                        elif item_key == 'lucky_charm':
                                            c.execute('UPDATE user_luckycharms SET count = count - ? WHERE guild_id = ? AND user_id = ?',
                                                      (amount, modal_inter.guild_id, modal_inter.user.id))
                                        elif item_key == 'dna':
                                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                                      (amount, modal_inter.guild_id, modal_inter.user.id, 'dna'))
                                        elif item_key == 'dragonscale':
                                            c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?',
                                                      (amount, modal_inter.guild_id, modal_inter.user.id))
                                        elif item_key in ['wooden', 'stone', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'celestial']:
                                            c.execute('UPDATE user_packs SET count = count - ? WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                                                      (amount, modal_inter.guild_id, modal_inter.user.id, item_key))
                                        elif item_key in ['night_vision', 'lucky_dice']:
                                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                                      (amount, modal_inter.guild_id, modal_inter.user.id, item_key))

                                        conn.commit()
                                        conn.close()

                                        # Get item name for response
                                        item_name = ""
                                        emoji = ""
                                        if item_key in DRAGON_TYPES:
                                            dragon_data = DRAGON_TYPES[item_key]
                                            item_name = dragon_data['name'] + " Dragon"
                                            emoji = dragon_data['emoji']
                                        elif item_key == 'lucky_charm':
                                            item_name = "Lucky Charm"
                                            emoji = "🍀"
                                        elif item_key == 'dna':
                                            item_name = "Dragon DNA"
                                            emoji = "🧬"
                                        elif item_key == 'dragonscale':
                                            item_name = "Dragonscale"
                                            emoji = "<:dragonscale:1446278170998341693>"
                                        elif item_key == 'night_vision':
                                            item_name = "Night Vision"
                                            emoji = "🌙"
                                        elif item_key == 'lucky_dice':
                                            item_name = "Lucky Dice"
                                            emoji = "🎰"
                                        elif item_key in ['wooden', 'stone', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'celestial']:
                                            pack_names_map = {
                                                'wooden': 'Wooden Pack', 'stone': 'Stone Pack', 'bronze': 'Bronze Pack',
                                                'silver': 'Silver Pack', 'gold': 'Gold Pack', 'platinum': 'Platinum Pack',
                                                'diamond': 'Diamond Pack', 'celestial': 'Celestial Pack'
                                            }
                                            pack_emojis_map = {
                                                'wooden': '<:woodenchest:1446170002708238476>', 'stone': '<:stonechest:1446169958265389247>',
                                                'bronze': '<:bronzechest:1446169758599745586>', 'silver': '<:silverchest:1446169917996011520>',
                                                'gold': '<:goldchest:1446169876438978681>', 'platinum': '<:platinumchest:1446169876438978681>',
                                                'diamond': '<:diamondchest:1446169830720929985>', 'celestial': '<:celestialchest:1446169830720929985>'
                                            }
                                            item_name = pack_names_map[item_key]
                                            emoji = pack_emojis_map[item_key]

                                        embed = discord.Embed(
                                            title="✅ Listed for Sale!",
                                            description=f"Listed {amount}x {emoji} **{item_name}** for **{price}** 🪙 each\n\nUse `/market action:mylistings` to manage your listings.",
                                            color=discord.Color.green()
                                        )
                                        await modal_inter.response.send_message(embed=embed, ephemeral=False)

                                await amount_inter.response.send_modal(PriceModal())

                        amount_select = AmountSelect(
                            placeholder="Select quantity...",
                            options=amount_options,
                            min_values=1,
                            max_values=1
                        )

                        amount_view = discord.ui.View()
                        amount_view.add_item(amount_select)

                        embed = discord.Embed(
                            title="📦 Select Quantity",
                            description=f"You have **{amount_available}** available\n\nHow many to list?",
                            color=0x5865F2
                        )
                        await select_interaction.response.send_message(embed=embed, view=amount_view, ephemeral=False)

                item_select = ItemSelect(sellable_items)
                item_view = discord.ui.View()
                item_view.add_item(item_select)

                embed = discord.Embed(
                    title="🏪 Select Item to Sell",
                    description="Choose which item you want to list:",
                    color=0x5865F2
                )
                await interaction.followup.send(embed=embed, view=item_view, ephemeral=False)

        embed = discord.Embed(
            title="🏪 What do you want to sell?",
            description="Choose a category:",
            color=0x5865F2
        )
        view = CategoryView()
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)


    async def market_mylistings(self, interaction: discord.Interaction):
        """View user's active listings"""
        await interaction.response.defer(ephemeral=False)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('''SELECT listing_id, dragon_type, price, listed_at, item_type
                     FROM market_listings
                     WHERE guild_id = ? AND seller_id = ?
                     ORDER BY listed_at DESC''',
                  (interaction.guild_id, interaction.user.id))
        listings = c.fetchall()
        conn.close()

        # Handle null item_type
        listings = [(lid, dt, p, la, it if it is not None else 'dragon') for lid, dt, p, la, it in listings]

        if not listings:
            embed = discord.Embed(
                title="📋 Your Listings",
                description="You have no active listings.\n\nUse `/market sell` to list dragons for sale!",
                color=0x5865F2
            )
            await interaction.followup.send(embed=embed)
            return

        # Build embed
        embed = discord.Embed(
            title="📋 Your Listings",
            description="Click a button to cancel a listing",
            color=0x5865F2
        )

        # Create view with cancel buttons
        class MyListingsView(discord.ui.View):
            def __init__(self, listings, message=None):
                super().__init__(timeout=300)
                self.listings = listings
                self.message = message

                for listing_id, dragon_type, price, listed_at, item_type in listings:
                    # Get label based on type
                    if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                        dragon_data = DRAGON_TYPES[dragon_type]
                        label = f"Cancel: {dragon_data['name']} - {price}🪙"
                    elif item_type == 'lucky_charm':
                        label = f"Cancel: Lucky Charm - {price}🪙"
                    elif item_type == 'dna':
                        label = f"Cancel: Dragon DNA - {price}🪙"
                    elif item_type == 'dragonscale':
                        label = f"Cancel: Dragonscale - {price}🪙"
                    else:
                        label = f"Cancel listing #{listing_id}"

                    button = discord.ui.Button(
                        label=label[:80],
                        style=discord.ButtonStyle.danger,
                        custom_id=f"cancel_{listing_id}"
                    )
                    button.callback = self.create_cancel_callback(listing_id, dragon_type, price, item_type)
                    self.add_item(button)

            def create_cancel_callback(self, listing_id, dragon_type, price, item_type):
                async def callback(interaction: discord.Interaction):
                    # Remove listing
                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('DELETE FROM market_listings WHERE listing_id = ? AND seller_id = ?',
                              (listing_id, interaction.user.id))
                    conn.commit()

                    # Get updated listings
                    c.execute('''SELECT listing_id, dragon_type, price, listed_at, COALESCE(item_type, 'dragon')
                                 FROM market_listings
                                 WHERE guild_id = ? AND seller_id = ?
                                 ORDER BY listed_at DESC''',
                              (interaction.guild_id, interaction.user.id))
                    updated_listings = c.fetchall()
                    conn.close()

                    # Get item name for response
                    if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                        dragon_data = DRAGON_TYPES[dragon_type]
                        item_name = f"{dragon_data['emoji']} **{dragon_data['name']} Dragon**"
                    elif item_type == 'lucky_charm':
                        item_name = "🍀 **Lucky Charm**"
                    elif item_type == 'dna':
                        item_name = "🧬 **Dragon DNA**"
                    elif item_type == 'dragonscale':
                        item_name = "<:dragonscale:1446278170998341693> **Dragonscale**"
                    else:
                        item_name = "Item"

                    await interaction.response.send_message(
                        f"✅ Cancelled listing: {item_name} ({price}🪙)",
                        ephemeral=False
                    )

                    # Update the message with new listings
                    if self.message:
                        if not updated_listings:
                            updated_embed = discord.Embed(
                                title="📋 Your Listings",
                                description="You have no active listings.\n\nUse `/market sell` to list dragons for sale!",
                                color=0x5865F2
                            )
                            await self.message.edit(embed=updated_embed, view=None)
                        else:
                            updated_embed = discord.Embed(
                                title="📋 Your Listings",
                                description="Click a button to cancel a listing",
                                color=0x5865F2
                            )

                            listing_text = ""
                            for lid, dtype, prc, lat, itype in updated_listings:
                                if itype == 'dragon' and dtype in DRAGON_TYPES:
                                    dragon_data = DRAGON_TYPES[dtype]
                                    listing_text += f"{dragon_data['emoji']} **{dragon_data['name']}** - {prc}🪙\n"
                                elif itype == 'lucky_charm':
                                    listing_text += f"🍀 **Lucky Charm** - {prc}🪙\n"
                                elif itype == 'dna':
                                    listing_text += f"🧬 **Dragon DNA** - {prc}🪙\n"
                                elif itype == 'dragonscale':
                                    listing_text += f"<:dragonscale:1446278170998341693> **Dragonscale** - {prc}🪙\n"

                            updated_embed.add_field(name="Your Active Listings", value=listing_text, inline=False)

                            new_view = MyListingsView(updated_listings, self.message)
                            await self.message.edit(embed=updated_embed, view=new_view)

                return callback

        listing_text = ""
        for listing_id, dragon_type, price, listed_at, item_type in listings:
            if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                dragon_data = DRAGON_TYPES[dragon_type]
                listing_text += f"{dragon_data['emoji']} **{dragon_data['name']}** - {price}🪙\n"
            elif item_type == 'lucky_charm':
                listing_text += f"🍀 **Lucky Charm** - {price}🪙\n"
            elif item_type == 'dna':
                listing_text += f"🧬 **Dragon DNA** - {price}🪙\n"
            elif item_type == 'dragonscale':
                listing_text += f"<:dragonscale:1446278170998341693> **Dragonscale** - {price}🪙\n"

        embed.add_field(name="Your Active Listings", value=listing_text, inline=False)

        view = MyListingsView(listings)
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message

    @app_commands.command(name="trade", description="Trade dragons/items with another user - select from inventory")
    @app_commands.describe(user="User to trade with")
    async def trade(self, interaction: discord.Interaction, user: discord.Member):
        """Trade with another user - interactive inventory selection"""
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
                            f"You're **softlocked** from trading until you upgrade.\n"
                            f"Use `/dragonnest` to upgrade!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=softlock_embed, delete_after=5)
            return

        if user.bot:
            await interaction.followup.send("❌ You can't trade with bots!", ephemeral=False)
            return

        if user.id == interaction.user.id:
            await interaction.followup.send("❌ You can't trade with yourself!", ephemeral=False)
            return

        guild_id = interaction.guild_id
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get your inventory - Dragons
        c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0 ORDER BY dragon_type',
                  (guild_id, interaction.user.id))
        your_dragons = c.fetchall()

        # Get your inventory - Special items
        c.execute('SELECT count FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                  (guild_id, interaction.user.id))
        your_lucky_charm = c.fetchone()

        c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                  (guild_id, interaction.user.id))
        your_dragonscale = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, interaction.user.id, 'dna'))
        your_dna = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, interaction.user.id, 'lucky_dice'))
        your_lucky_dice = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, interaction.user.id, 'night_vision'))
        your_night_vision = c.fetchone()

        # Get your packs
        pack_types = ['wooden', 'stone', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'celestial']
        your_packs = {}
        for pack_type in pack_types:
            c.execute('SELECT count FROM user_packs WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                      (guild_id, interaction.user.id, pack_type))
            result = c.fetchone()
            if result and result[0] > 0:
                your_packs[pack_type] = result[0]

        # Get their inventory - Dragons
        c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0 ORDER BY dragon_type',
                  (guild_id, user.id))
        their_dragons = c.fetchall()

        # Get their inventory - Special items
        c.execute('SELECT count FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))
        their_lucky_charm = c.fetchone()

        c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user.id))
        their_dragonscale = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, user.id, 'dna'))
        their_dna = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, user.id, 'lucky_dice'))
        their_lucky_dice = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, user.id, 'night_vision'))
        their_night_vision = c.fetchone()

        # Get their packs
        their_packs = {}
        for pack_type in pack_types:
            c.execute('SELECT count FROM user_packs WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                      (guild_id, user.id, pack_type))
            result = c.fetchone()
            if result and result[0] > 0:
                their_packs[pack_type] = result[0]

        conn.close()

        # Pack names and emojis
        pack_names = {
            'wooden': 'Wooden Pack', 'stone': 'Stone Pack', 'bronze': 'Bronze Pack', 'silver': 'Silver Pack',
            'gold': 'Gold Pack', 'platinum': 'Platinum Pack', 'diamond': 'Diamond Pack', 'celestial': 'Celestial Pack'
        }
        pack_emojis = {
            'wooden': '<:woodenchest:1446170002708238476>', 'stone': '<:stonechest:1446169958265389247>',
            'bronze': '<:bronzechest:1446169758599745586>', 'silver': '<:silverchest:1446169917996011520>',
            'gold': '<:goldchest:1446169876438978681>', 'platinum': '<:platinumchest:1446169876438978681>',
            'diamond': '<:diamondchest:1446169830720929985>', 'celestial': '<:celestialchest:1446169830720929985>'
        }

        # Build your items list
        your_items = []
        for dragon_type, count in your_dragons:
            if dragon_type not in DRAGON_TYPES:
                continue
            dragon_data = DRAGON_TYPES[dragon_type]
            your_items.append({'type': 'dragon', 'key': dragon_type, 'name': dragon_data['name'], 'emoji': dragon_data['emoji'], 'count': count})

        if your_lucky_charm and your_lucky_charm[0] > 0:
            your_items.append({'type': 'lucky_charm', 'key': 'lucky_charm', 'name': 'Lucky Charm', 'emoji': '🍀', 'count': your_lucky_charm[0]})
        if your_dragonscale and your_dragonscale[0] > 0:
            your_items.append({'type': 'dragonscale', 'key': 'dragonscale', 'name': 'Dragonscale', 'emoji': '<:dragonscale:1446278170998341693>', 'count': your_dragonscale[0]})
        if your_dna and your_dna[0] > 0:
            your_items.append({'type': 'dna', 'key': 'dna', 'name': 'DNA Sample', 'emoji': '🧬', 'count': your_dna[0]})
        if your_lucky_dice and your_lucky_dice[0] > 0:
            your_items.append({'type': 'lucky_dice', 'key': 'lucky_dice', 'name': 'Lucky Dice', 'emoji': '🎰', 'count': your_lucky_dice[0]})
        if your_night_vision and your_night_vision[0] > 0:
            your_items.append({'type': 'night_vision', 'key': 'night_vision', 'name': 'Night Vision', 'emoji': '🌙', 'count': your_night_vision[0]})
        for pack_type, count in your_packs.items():
            your_items.append({'type': 'pack', 'key': pack_type, 'name': pack_names[pack_type], 'emoji': pack_emojis[pack_type], 'count': count})

        # Build their items list
        their_items = []
        for dragon_type, count in their_dragons:
            if dragon_type not in DRAGON_TYPES:
                continue
            dragon_data = DRAGON_TYPES[dragon_type]
            their_items.append({'type': 'dragon', 'key': dragon_type, 'name': dragon_data['name'], 'emoji': dragon_data['emoji'], 'count': count})

        if their_lucky_charm and their_lucky_charm[0] > 0:
            their_items.append({'type': 'lucky_charm', 'key': 'lucky_charm', 'name': 'Lucky Charm', 'emoji': '🍀', 'count': their_lucky_charm[0]})
        if their_dragonscale and their_dragonscale[0] > 0:
            their_items.append({'type': 'dragonscale', 'key': 'dragonscale', 'name': 'Dragonscale', 'emoji': '<:dragonscale:1446278170998341693>', 'count': their_dragonscale[0]})
        if their_dna and their_dna[0] > 0:
            their_items.append({'type': 'dna', 'key': 'dna', 'name': 'DNA Sample', 'emoji': '🧬', 'count': their_dna[0]})
        if their_lucky_dice and their_lucky_dice[0] > 0:
            their_items.append({'type': 'lucky_dice', 'key': 'lucky_dice', 'name': 'Lucky Dice', 'emoji': '🎰', 'count': their_lucky_dice[0]})
        if their_night_vision and their_night_vision[0] > 0:
            their_items.append({'type': 'night_vision', 'key': 'night_vision', 'name': 'Night Vision', 'emoji': '🌙', 'count': their_night_vision[0]})
        for pack_type, count in their_packs.items():
            their_items.append({'type': 'pack', 'key': pack_type, 'name': pack_names[pack_type], 'emoji': pack_emojis[pack_type], 'count': count})

        if not your_items:
            await interaction.followup.send("❌ You don't have anything to trade!", ephemeral=False)
            return

        if not their_items:
            await interaction.followup.send(f"❌ {user.mention} doesn't have anything to trade!", ephemeral=False)
            return

        # Create selection view
        class TradeSetupView(discord.ui.View):
            def __init__(self, your_items_list, their_items_list):
                super().__init__(timeout=300)
                self.your_items_list = your_items_list
                self.their_items_list = their_items_list
                self.selected_yours = None
                self.your_amount = 1

                # Your items dropdown
                options = []
                for item in your_items_list:
                    options.append(discord.SelectOption(
                        label=f"{item['name']} (Have: {item['count']})",
                        value=f"yours_{item['key']}",
                        emoji=item['emoji']
                    ))

                select_yours = discord.ui.Select(
                    placeholder="What do you want to trade?",
                    options=options,
                    min_values=1,
                    max_values=1
                )
                select_yours.callback = self.select_yours_callback
                self.add_item(select_yours)

            async def select_yours_callback(self, interaction: discord.Interaction):
                await interaction.response.defer()
                try:
                    self.selected_yours = interaction.values[0].split('_')[1] if hasattr(interaction, 'values') and interaction.values else None
                    if not self.selected_yours:
                        await interaction.followup.send("❌ Please select an item!", ephemeral=True)
                        return
                except (IndexError, AttributeError):
                    await interaction.followup.send("❌ Invalid selection!", ephemeral=True)
                    return

                # Find selected item
                selected_item = None
                for item in self.your_items_list:
                    if item['key'] == self.selected_yours:
                        selected_item = item
                        break

                if not selected_item:
                    await interaction.response.send_message("❌ Item not found!", ephemeral=False)
                    return

                # Show amount selection
                embed = discord.Embed(
                    title="📦 Select Amount",
                    description=f"You have: **{selected_item['count']}** {selected_item['emoji']} {selected_item['name']}",
                    color=discord.Color.blue()
                )

                amount_options = [discord.SelectOption(label=f"{i}", value=str(i)) for i in range(1, min(selected_item['count'] + 1, 11))]

                class AmountSelect(discord.ui.Select):
                    async def callback(self, amount_interaction: discord.Interaction):
                        self.parent_view.your_amount = int(self.values[0])

                        # Now show their items to select what you want
                        embed2 = discord.Embed(
                            title="🤝 What do you want in return?",
                            description=f"Select what {user.display_name} should trade",
                            color=discord.Color.blue()
                        )

                        their_options = []
                        for item in self.parent_view.their_items_list:
                            their_options.append(discord.SelectOption(
                                label=f"{item['name']} (They Have: {item['count']})",
                                value=f"theirs_{item['key']}",
                                emoji=item['emoji']
                            ))

                        select_theirs = discord.ui.Select(
                            placeholder="What do they trade back?",
                            options=their_options,
                            min_values=1,
                            max_values=1
                        )
                        select_theirs.callback = lambda i: self.parent_view.select_theirs_callback(i, selected_item)

                        their_view = discord.ui.View()
                        their_view.add_item(select_theirs)

                        await amount_interaction.response.send_message(embed=embed2, view=their_view, ephemeral=False)

                amount_select = AmountSelect(
                    placeholder="Select amount...",
                    options=amount_options,
                    min_values=1,
                    max_values=1
                )
                amount_select.parent_view = self

                amount_view = discord.ui.View()
                amount_view.add_item(amount_select)

                await interaction.response.send_message(embed=embed, view=amount_view, ephemeral=False)

            async def select_theirs_callback(self, interaction: discord.Interaction, your_item):
                await interaction.response.defer()
                try:
                    selected_theirs_key = interaction.values[0].split('_')[1] if hasattr(interaction, 'values') and interaction.values else None
                    if not selected_theirs_key:
                        await interaction.followup.send("❌ Please select an item!", ephemeral=True)
                        return
                except (IndexError, AttributeError):
                    await interaction.followup.send("❌ Invalid selection!", ephemeral=True)
                    return

                # Find selected item
                selected_theirs = None
                for item in self.their_items_list:
                    if item['key'] == selected_theirs_key:
                        selected_theirs = item
                        break

                if not selected_theirs:
                    await interaction.response.send_message("❌ Item not found!", ephemeral=False)
                    return

                # Show amount selection for their item
                embed = discord.Embed(
                    title="📦 How much?",
                    description=f"They have: **{selected_theirs['count']}** {selected_theirs['emoji']} {selected_theirs['name']}",
                    color=discord.Color.blue()
                )

                their_amount_options = [discord.SelectOption(label=f"{i}", value=str(i)) for i in range(1, min(selected_theirs['count'] + 1, 11))]

                class TheirAmountSelect(discord.ui.Select):
                    async def callback(self, their_amount_interaction: discord.Interaction):
                        their_amount = int(self.values[0])

                        # Now create the trade offer
                        await create_trade_offer(interaction, your_item['key'], self.parent_view.your_amount,
                                               selected_theirs['key'], their_amount, your_item, selected_theirs)

                their_amount_select = TheirAmountSelect(
                    placeholder="Select amount...",
                    options=their_amount_options,
                    min_values=1,
                    max_values=1
                )
                their_amount_select.parent_view = self

                their_amount_view = discord.ui.View()
                their_amount_view.add_item(their_amount_select)

                await interaction.response.send_message(embed=embed, view=their_amount_view, ephemeral=False)

        async def create_trade_offer(init_inter, your_key, your_amount, their_key, their_amount, your_item_data, their_item_data):
            """Create and send the trade offer"""
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            # Store trade data
            sender_data = f"{your_item_data['type']}:{your_key}:{your_amount}"
            receiver_data = f"{their_item_data['type']}:{their_key}:{their_amount}"

            c.execute('''INSERT INTO trade_offers (guild_id, sender_id, receiver_id, sender_dragons, receiver_dragons, status, created_at)
                         VALUES (?, ?, ?, ?, ?, 'pending', ?)''',
                      (guild_id, interaction.user.id, user.id, sender_data, receiver_data, int(time.time())))
            trade_id = c.lastrowid
            conn.commit()
            conn.close()

            # Create accept/decline view
            class FinalTradeView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=300)

                @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
                async def accept_button(self, accept_inter: discord.Interaction, button: discord.ui.Button):
                    if accept_inter.user.id != user.id:
                        await accept_inter.response.send_message("❌ You can't accept this trade!", ephemeral=False)
                        return

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()

                    # Verify trade still exists
                    c.execute('SELECT sender_dragons, receiver_dragons FROM trade_offers WHERE trade_id = ? AND status = "pending"',
                              (trade_id,))
                    trade = c.fetchone()

                    if not trade:
                        await accept_inter.response.send_message("❌ Trade no longer available!", ephemeral=False)
                        conn.close()
                        return

                    sender_parts = trade[0].split(':')
                    receiver_parts = trade[1].split(':')

                    sender_type, sender_key, sender_amount = sender_parts[0], sender_parts[1], int(sender_parts[2])
                    receiver_type, receiver_key, receiver_amount = receiver_parts[0], receiver_parts[1], int(receiver_parts[2])

                    try:
                        # Execute trade for sender (remove from sender, add to receiver)
                        if sender_type == 'dragon':
                            await add_dragons(guild_id, interaction.user.id, sender_key, -sender_amount)
                            await add_dragons(guild_id, user.id, sender_key, sender_amount)
                        elif sender_type == 'lucky_charm':
                            c.execute('UPDATE user_luckycharms SET count = count - ? WHERE guild_id = ? AND user_id = ?',
                                      (sender_amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO user_luckycharms (guild_id, user_id, count) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, sender_amount, sender_amount))
                        elif sender_type == 'dragonscale':
                            c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?',
                                      (sender_amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET minutes = minutes + ?',
                                      (guild_id, user.id, sender_amount, sender_amount))
                        elif sender_type == 'dna':
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (sender_amount, guild_id, interaction.user.id, 'dna'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'dna', sender_amount, sender_amount))
                        elif sender_type == 'lucky_dice':
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (sender_amount, guild_id, interaction.user.id, 'lucky_dice'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'lucky_dice', sender_amount, sender_amount))
                        elif sender_type == 'night_vision':
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (sender_amount, guild_id, interaction.user.id, 'night_vision'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'night_vision', sender_amount, sender_amount))
                        elif sender_type == 'pack':
                            c.execute('UPDATE user_packs SET count = count - ? WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                                      (sender_amount, guild_id, interaction.user.id, sender_key))
                            c.execute('INSERT INTO user_packs (guild_id, user_id, pack_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, pack_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, sender_key, sender_amount, sender_amount))

                        # Execute trade for receiver (remove from receiver, add to sender)
                        if receiver_type == 'dragon':
                            await add_dragons(guild_id, user.id, receiver_key, -receiver_amount)
                            await add_dragons(guild_id, interaction.user.id, receiver_key, receiver_amount)
                        elif receiver_type == 'lucky_charm':
                            c.execute('UPDATE user_luckycharms SET count = count - ? WHERE guild_id = ? AND user_id = ?',
                                      (receiver_amount, guild_id, user.id))
                            c.execute('INSERT INTO user_luckycharms (guild_id, user_id, count) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + ?',
                                      (guild_id, interaction.user.id, receiver_amount, receiver_amount))
                        elif receiver_type == 'dragonscale':
                            c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?',
                                      (receiver_amount, guild_id, user.id))
                            c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET minutes = minutes + ?',
                                      (guild_id, interaction.user.id, receiver_amount, receiver_amount))
                        elif receiver_type == 'dna':
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (receiver_amount, guild_id, user.id, 'dna'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, interaction.user.id, 'dna', receiver_amount, receiver_amount))
                        elif receiver_type == 'lucky_dice':
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (receiver_amount, guild_id, user.id, 'lucky_dice'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, interaction.user.id, 'lucky_dice', receiver_amount, receiver_amount))
                        elif receiver_type == 'night_vision':
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (receiver_amount, guild_id, user.id, 'night_vision'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, interaction.user.id, 'night_vision', receiver_amount, receiver_amount))
                        elif receiver_type == 'pack':
                            c.execute('UPDATE user_packs SET count = count - ? WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                                      (receiver_amount, guild_id, user.id, receiver_key))
                            c.execute('INSERT INTO user_packs (guild_id, user_id, pack_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, pack_type) DO UPDATE SET count = count + ?',
                                      (guild_id, interaction.user.id, receiver_key, receiver_amount, receiver_amount))

                        c.execute('UPDATE trade_offers SET status = "completed" WHERE trade_id = ?', (trade_id,))
                        conn.commit()

                        # Get display names
                        your_emoji = your_item_data['emoji']
                        your_name = your_item_data['name']
                        their_emoji = their_item_data['emoji']
                        their_name = their_item_data['name']

                        await accept_inter.response.edit_message(
                            content=f"✅ **Trade Completed!**\n\n"
                                   f"{interaction.user.mention} gave {sender_amount}x {your_emoji} {your_name}\n"
                                   f"{user.mention} gave {receiver_amount}x {their_emoji} {their_name}",
                            view=None
                        )
                    except Exception as e:
                        await accept_inter.response.send_message(f"❌ Trade failed: {e}", ephemeral=False)
                    finally:
                        conn.close()

                @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
                async def decline_button(self, decline_inter: discord.Interaction, button: discord.ui.Button):
                    if decline_inter.user.id != user.id:
                        await decline_inter.response.send_message("❌ You can't decline this trade!", ephemeral=False)
                        return

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('UPDATE trade_offers SET status = "declined" WHERE trade_id = ?', (trade_id,))
                    conn.commit()
                    conn.close()

                    await decline_inter.response.edit_message(
                        content=f"❌ Trade declined",
                        view=None
                    )

            embed = discord.Embed(
                title="🤝 Trade Offer",
                description=f"{interaction.user.mention} wants to trade with {user.mention}!",
                color=discord.Color.blue()
            )
            embed.add_field(
                name=f"{interaction.user.display_name} Offers",
                value=f"{your_amount}x {your_item_data['emoji']} {your_item_data['name']}",
                inline=True
            )
            embed.add_field(
                name=f"{user.display_name} Offers",
                value=f"{their_amount}x {their_item_data['emoji']} {their_item_data['name']}",
                inline=True
            )
            embed.set_footer(text="Trade expires in 5 minutes")

            view = FinalTradeView()
            await init_inter.followup.send(content=user.mention, embed=embed, view=view, ephemeral=False)

        embed = discord.Embed(
            title="🤝 Trade Setup",
            description=f"Start your trade with {user.mention}",
            color=discord.Color.blue()
        )

        view = TradeSetupView(your_items, their_items)
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="gift", description="Gift dragons to another user")
    @app_commands.describe(user="User to gift dragons to")
    async def gift(self, interaction: discord.Interaction, user: discord.Member):
        """Gift dragons or items to another user"""
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
                            f"You're **softlocked** from gifting until you upgrade.\n"
                            f"Use `/dragonnest` to upgrade!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=softlock_embed, delete_after=5)
            return

        if user.bot:
            await interaction.followup.send("❌ You can't gift to bots!", ephemeral=False)
            return

        if user.id == interaction.user.id:
            await interaction.followup.send("❌ You can't gift to yourself!", ephemeral=False)
            return

        guild_id = interaction.guild_id

        # Get user's inventory
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Get user's balance (coins)
        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                  (guild_id, interaction.user.id))
        balance_result = c.fetchone()
        user_balance = balance_result[0] if balance_result else 0

        # Get dragons
        c.execute('SELECT dragon_type, count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0 ORDER BY dragon_type',
                  (guild_id, interaction.user.id))
        user_dragons = c.fetchall()

        # Get items
        c.execute('SELECT count FROM user_luckycharms WHERE guild_id = ? AND user_id = ?',
                  (guild_id, interaction.user.id))
        lucky_charm_count = c.fetchone()

        c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                  (guild_id, interaction.user.id))
        dragonscale_count = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, interaction.user.id, 'dna'))
        dna_count = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, interaction.user.id, 'lucky_dice'))
        lucky_dice_count = c.fetchone()

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, interaction.user.id, 'night_vision'))
        night_vision_count = c.fetchone()

        # Get packs
        pack_types = ['wooden', 'stone', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'celestial']
        user_packs = {}
        for pack_type in pack_types:
            c.execute('SELECT count FROM user_packs WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                      (guild_id, interaction.user.id, pack_type))
            result = c.fetchone()
            if result and result[0] > 0:
                user_packs[pack_type] = result[0]

        conn.close()

        pack_names = {
            'wooden': 'Wooden Pack', 'stone': 'Stone Pack', 'bronze': 'Bronze Pack', 'silver': 'Silver Pack',
            'gold': 'Gold Pack', 'platinum': 'Platinum Pack', 'diamond': 'Diamond Pack', 'celestial': 'Celestial Pack'
        }
        pack_emojis = {
            'wooden': '<:woodenchest:1446170002708238476>', 'stone': '<:stonechest:1446169958265389247>',
            'bronze': '<:bronzechest:1446169758599745586>', 'silver': '<:silverchest:1446169917996011520>',
            'gold': '<:goldchest:1446169876438978681>', 'platinum': '<:platinumchest:1446169876438978681>',
            'diamond': '<:diamondchest:1446169830720929985>', 'celestial': '<:celestialchest:1446169830720929985>'
        }

        # Build dragon and other items lists
        dragon_items = []
        for dragon_type, count in user_dragons:
            if dragon_type not in DRAGON_TYPES:
                continue
            dragon_data = DRAGON_TYPES[dragon_type]
            dragon_items.append({'type': 'dragon', 'key': dragon_type, 'name': dragon_data['name'], 'emoji': dragon_data['emoji'], 'count': count})

        other_items = []
        if lucky_charm_count and lucky_charm_count[0] > 0:
            other_items.append({'type': 'lucky_charm', 'key': 'lucky_charm', 'name': 'Lucky Charm', 'emoji': '🍀', 'count': lucky_charm_count[0]})
        if dragonscale_count and dragonscale_count[0] > 0:
            other_items.append({'type': 'dragonscale', 'key': 'dragonscale', 'name': 'Dragonscale', 'emoji': '<:dragonscale:1446278170998341693>', 'count': dragonscale_count[0]})
        if dna_count and dna_count[0] > 0:
            other_items.append({'type': 'dna', 'key': 'dna', 'name': 'DNA Sample', 'emoji': '🧬', 'count': dna_count[0]})
        if lucky_dice_count and lucky_dice_count[0] > 0:
            other_items.append({'type': 'lucky_dice', 'key': 'lucky_dice', 'name': 'Lucky Dice', 'emoji': '🎰', 'count': lucky_dice_count[0]})
        if night_vision_count and night_vision_count[0] > 0:
            other_items.append({'type': 'night_vision', 'key': 'night_vision', 'name': 'Night Vision', 'emoji': '🌙', 'count': night_vision_count[0]})
        for pack_type, count in user_packs.items():
            other_items.append({'type': 'pack', 'key': pack_type, 'name': pack_names[pack_type], 'emoji': pack_emojis[pack_type], 'count': count})

        # Check if user has anything to gift
        has_dragons = len(dragon_items) > 0
        has_items = len(other_items) > 0
        coins_available = user_balance > 0

        if not has_dragons and not has_items and not coins_available:
            await interaction.followup.send("❌ You don't have any dragons, items, or coins to gift!", ephemeral=False)
            return

        # Define GiftSelectView first
        class GiftSelectView(discord.ui.View):
            def __init__(self, items):
                super().__init__(timeout=60)
                self.items = items

                options = []
                for item in items:
                    options.append(
                        discord.SelectOption(
                            label=f"{item['name']} (Have: {item['count']})",
                            value=item['key'],
                            emoji=item['emoji']
                        )
                    )

                self.select = discord.ui.Select(
                    placeholder="Select item to gift...",
                    options=options,
                    min_values=1,
                    max_values=1
                )
                self.select.callback = self.select_callback
                self.add_item(self.select)

            async def select_callback(self, interaction: discord.Interaction):
                selected_key = self.select.values[0]

                # Find selected item
                selected_item = None
                for item in self.items:
                    if item['key'] == selected_key:
                        selected_item = item
                        break

                if not selected_item:
                    await interaction.response.send_message("❌ Item not found!", ephemeral=False)
                    return

                max_amount = selected_item['count']

                # If it's coins, show a modal instead of buttons
                if selected_item['type'] == 'coins':
                    class CoinGiftModal(discord.ui.Modal, title="Gift Coins"):
                        amount_input = discord.ui.TextInput(
                            label="Amount to gift",
                            placeholder=f"Enter amount (max: {max_amount:,})",
                            required=True
                        )

                        async def on_submit(self, modal_interaction: discord.Interaction):
                            try:
                                amount = int(self.amount_input.value)
                                if amount <= 0:
                                    await modal_interaction.response.send_message("❌ Amount must be greater than 0!", ephemeral=True)
                                    return
                                if amount > max_amount:
                                    await modal_interaction.response.send_message(f"❌ You can only gift up to {max_amount:,} coins!", ephemeral=True)
                                    return

                                # Transfer coins
                                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                                c = conn.cursor()
                                c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                                          (amount, guild_id, interaction.user.id))
                                c.execute('INSERT INTO users (guild_id, user_id, balance) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = balance + ?',
                                          (guild_id, user.id, amount, amount))
                                conn.commit()
                                conn.close()

                                # Confirm message
                                embed = discord.Embed(
                                    title="🎁 Gift Sent!",
                                    description=f"{interaction.user.mention} gifted {amount:,} 💰 coins to {user.mention}!",
                                    color=discord.Color.green()
                                )
                                await modal_interaction.response.send_message(embed=embed, ephemeral=False)
                            except ValueError:
                                await modal_interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)

                    await interaction.response.send_modal(CoinGiftModal())
                    return

                embed = discord.Embed(
                    title="🎁 How many to gift?",
                    description=f"You selected: {selected_item['emoji']} **{selected_item['name']}**\nYou have: **{max_amount}**",
                    color=discord.Color.blue()
                )

                class AmountView(discord.ui.View):
                    def __init__(self, max_amt, sel_item):
                        super().__init__(timeout=60)
                        self.max_amount = max_amt
                        self.sel_item = sel_item

                    @discord.ui.button(label="1", style=discord.ButtonStyle.primary)
                    async def btn_1(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                        await self.gift_item(btn_interaction, 1)

                    @discord.ui.button(label="5", style=discord.ButtonStyle.primary)
                    async def btn_5(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                        await self.gift_item(btn_interaction, min(5, self.max_amount))

                    @discord.ui.button(label="10", style=discord.ButtonStyle.primary)
                    async def btn_10(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                        await self.gift_item(btn_interaction, min(10, self.max_amount))

                    @discord.ui.button(label="All", style=discord.ButtonStyle.success)
                    async def btn_all(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                        await self.gift_item(btn_interaction, self.max_amount)

                    async def gift_item(self, btn_interaction: discord.Interaction, amount: int):
                        # Transfer based on type
                        if self.sel_item['type'] == 'dragon':
                            await add_dragons(guild_id, interaction.user.id, self.sel_item['key'], -amount)
                            await add_dragons(guild_id, user.id, self.sel_item['key'], amount)
                        elif self.sel_item['type'] == 'lucky_charm':
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()
                            c.execute('UPDATE user_luckycharms SET count = count - ? WHERE guild_id = ? AND user_id = ?',
                                      (amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO user_luckycharms (guild_id, user_id, count) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'dragonscale':
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()
                            c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?',
                                      (amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET minutes = minutes + ?',
                                      (guild_id, user.id, amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'dna':
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (amount, guild_id, interaction.user.id, 'dna'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'dna', amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'lucky_dice':
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (amount, guild_id, interaction.user.id, 'lucky_dice'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'lucky_dice', amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'night_vision':
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (amount, guild_id, interaction.user.id, 'night_vision'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'night_vision', amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'pack':
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()
                            c.execute('UPDATE user_packs SET count = count - ? WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                                      (amount, guild_id, interaction.user.id, self.sel_item['key']))
                            c.execute('INSERT INTO user_packs (guild_id, user_id, pack_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, pack_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, self.sel_item['key'], amount, amount))
                            conn.commit()
                            conn.close()

                        item_data = self.sel_item
                        embed = discord.Embed(
                            title="🎁 Item Gift",
                            description=f"{interaction.user.mention} gifted {amount}x {item_data['emoji']} **{item_data['name']}** to {user.mention}!",
                            color=discord.Color.green()
                        )

                        await btn_interaction.response.send_message(embed=embed)

                await interaction.response.send_message(embed=embed, view=AmountView(max_amount, selected_item), ephemeral=False)

        # Create category selection view
        class GiftCategoryView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)

            @discord.ui.button(label="🐉 Dragons", style=discord.ButtonStyle.primary)
            async def btn_dragons(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if not has_dragons:
                    await btn_interaction.response.send_message("❌ You don't have any dragons to gift!", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="🎁 Gift Dragon",
                    description=f"Select a dragon to gift to {user.mention}",
                    color=discord.Color.blue()
                )

                view = GiftSelectView(dragon_items)
                await btn_interaction.response.send_message(embed=embed, view=view, ephemeral=False)

            @discord.ui.button(label="📦 Items", style=discord.ButtonStyle.primary)
            async def btn_items(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if not has_items:
                    await btn_interaction.response.send_message("❌ You don't have any items to gift!", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="🎁 Gift Item",
                    description=f"Select an item to gift to {user.mention}",
                    color=discord.Color.blue()
                )

                view = GiftSelectView(other_items)
                await btn_interaction.response.send_message(embed=embed, view=view, ephemeral=False)

            @discord.ui.button(label="💰 Coins", style=discord.ButtonStyle.success)
            async def btn_coins(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if not coins_available:
                    await btn_interaction.response.send_message("❌ You don't have any coins to gift!", ephemeral=True)
                    return

                class CoinGiftModal(discord.ui.Modal, title="Gift Coins"):
                    amount_input = discord.ui.TextInput(
                        label="Amount to gift",
                        placeholder=f"Enter amount (max: {user_balance:,})",
                        required=True
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        try:
                            amount = int(self.amount_input.value)
                            if amount <= 0:
                                await modal_interaction.response.send_message("❌ Amount must be greater than 0!", ephemeral=True)
                                return
                            if amount > user_balance:
                                await modal_interaction.response.send_message(f"❌ You can only gift up to {user_balance:,} coins!", ephemeral=True)
                                return

                            # Transfer coins
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()
                            c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                                      (amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO users (guild_id, user_id, balance) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = balance + ?',
                                      (guild_id, user.id, amount, amount))
                            conn.commit()
                            conn.close()

                            # Confirm message
                            embed = discord.Embed(
                                title="🎁 Gift Sent!",
                                description=f"{interaction.user.mention} gifted {amount:,} 💰 coins to {user.mention}!",
                                color=discord.Color.green()
                            )
                            await modal_interaction.response.send_message(embed=embed, ephemeral=False)
                        except ValueError:
                            await modal_interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)

                await btn_interaction.response.send_modal(CoinGiftModal())

        # Show category selection
        embed = discord.Embed(
            title="🎁 What do you want to gift?",
            description=f"Recipient: {user.mention}",
            color=discord.Color.blue()
        )

        await interaction.followup.send(embed=embed, view=GiftCategoryView(), ephemeral=False)
        return

    @app_commands.command(name="mylistings", description="View and cancel your marketplace listings")
    async def mylistings(self, interaction: discord.Interaction):
        """View user's active listings"""
        await interaction.response.defer(ephemeral=False)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('''SELECT listing_id, dragon_type, price, listed_at, item_type
                     FROM market_listings
                     WHERE guild_id = ? AND seller_id = ?
                     ORDER BY listed_at DESC''',
                  (interaction.guild_id, interaction.user.id))
        listings = c.fetchall()
        conn.close()

        # Handle null item_type
        listings = [(lid, dt, p, la, it if it is not None else 'dragon') for lid, dt, p, la, it in listings]

        if not listings:
            embed = discord.Embed(
                title="📋 Your Listings",
                description="You have no active listings.\n\nUse `/marketsell` to list dragons for sale!",
                color=0x5865F2
            )
            await interaction.followup.send(embed=embed)
            return

        # Build embed
        embed = discord.Embed(
            title="📋 Your Listings",
            description="Click a button to cancel a listing",
            color=0x5865F2
        )

        # Create view with cancel buttons
        class MyListingsView(discord.ui.View):
            def __init__(self, listings, message=None):
                super().__init__(timeout=300)
                self.listings = listings
                self.message = message

                for listing_id, dragon_type, price, listed_at, item_type in listings:
                    # Get label based on type
                    if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                        dragon_data = DRAGON_TYPES[dragon_type]
                        label = f"Cancel: {dragon_data['name']} - {price}🪙"
                    elif item_type == 'lucky_charm':
                        label = f"Cancel: Lucky Charm - {price}🪙"
                    elif item_type == 'dna':
                        label = f"Cancel: Dragon DNA - {price}🪙"
                    elif item_type == 'dragonscale':
                        label = f"Cancel: Dragonscale - {price}🪙"
                    else:
                        label = f"Cancel listing #{listing_id}"

                    button = discord.ui.Button(
                        label=label[:80],
                        style=discord.ButtonStyle.danger,
                        custom_id=f"cancel_{listing_id}"
                    )
                    button.callback = self.create_cancel_callback(listing_id, dragon_type, price, item_type)
                    self.add_item(button)

            def create_cancel_callback(self, listing_id, dragon_type, price, item_type):
                async def callback(interaction: discord.Interaction):
                    # Remove listing
                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('DELETE FROM market_listings WHERE listing_id = ? AND seller_id = ?',
                              (listing_id, interaction.user.id))
                    conn.commit()

                    # Get updated listings
                    c.execute('''SELECT listing_id, dragon_type, price, listed_at, COALESCE(item_type, 'dragon')
                                 FROM market_listings
                                 WHERE guild_id = ? AND seller_id = ?
                                 ORDER BY listed_at DESC''',
                              (interaction.guild_id, interaction.user.id))
                    updated_listings = c.fetchall()
                    conn.close()

                    # Get item name for response
                    if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                        dragon_data = DRAGON_TYPES[dragon_type]
                        item_name = f"{dragon_data['emoji']} **{dragon_data['name']} Dragon**"
                    elif item_type == 'lucky_charm':
                        item_name = "🍀 **Lucky Charm**"
                    elif item_type == 'dna':
                        item_name = "🧬 **Dragon DNA**"
                    elif item_type == 'dragonscale':
                        item_name = "<:dragonscale:1446278170998341693> **Dragonscale**"
                    else:
                        item_name = "Item"

                    await interaction.response.send_message(
                        f"✅ Cancelled listing: {item_name} ({price}🪙)",
                        ephemeral=False
                    )

                    # Update the message with new listings
                    if self.message:
                        if not updated_listings:
                            updated_embed = discord.Embed(
                                title="📋 Your Listings",
                                description="You have no active listings.\n\nUse `/marketsell` to list dragons for sale!",
                                color=0x5865F2
                            )
                            await self.message.edit(embed=updated_embed, view=None)
                        else:
                            updated_embed = discord.Embed(
                                title="📋 Your Listings",
                                description="Click a button to cancel a listing",
                                color=0x5865F2
                            )

                            listing_text = ""
                            for lid, dtype, prc, lat, itype in updated_listings:
                                if itype == 'dragon' and dtype in DRAGON_TYPES:
                                    dragon_data = DRAGON_TYPES[dtype]
                                    listing_text += f"{dragon_data['emoji']} **{dragon_data['name']}** - {prc}🪙\n"
                                elif itype == 'lucky_charm':
                                    listing_text += f"🍀 **Lucky Charm** - {prc}🪙\n"
                                elif itype == 'dna':
                                    listing_text += f"🧬 **Dragon DNA** - {prc}🪙\n"
                                elif itype == 'dragonscale':
                                    listing_text += f"<:dragonscale:1446278170998341693> **Dragonscale** - {prc}🪙\n"

                            updated_embed.add_field(name="Your Active Listings", value=listing_text, inline=False)

                            new_view = MyListingsView(updated_listings, self.message)
                            await self.message.edit(embed=updated_embed, view=new_view)

                return callback

        listing_text = ""
        for listing_id, dragon_type, price, listed_at, item_type in listings:
            if item_type == 'dragon' and dragon_type in DRAGON_TYPES:
                dragon_data = DRAGON_TYPES[dragon_type]
                listing_text += f"{dragon_data['emoji']} **{dragon_data['name']}** - {price}🪙\n"
            elif item_type == 'lucky_charm':
                listing_text += f"🍀 **Lucky Charm** - {price}🪙\n"
            elif item_type == 'dna':
                listing_text += f"🧬 **Dragon DNA** - {price}🪙\n"
            elif item_type == 'dragonscale':
                listing_text += f"<:dragonscale:1446278170998341693> **Dragonscale** - {price}🪙\n"

        embed.add_field(name="Your Active Listings", value=listing_text, inline=False)

        view = MyListingsView(listings)
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(MarketCog(bot))
