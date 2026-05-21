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

        conn = get_db_connection()
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
                conn = get_db_connection()
                c = conn.cursor()
                try:
                    c.execute('''SELECT listing_id, seller_id, dragon_type, price, listed_at, item_type
                                 FROM market_listings
                                 WHERE listing_id = ? AND guild_id = ?''',
                              (listing_id, interaction.guild_id))
                    db_listing = c.fetchone()

                    if not db_listing:
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
                        return

                    # Check if buyer is trying to buy their own listing
                    if seller_id == interaction.user.id:
                        await interaction.followup.send("❌ You can't buy your own listing!", ephemeral=False)
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
                            await interaction.followup.send("❌ Unknown item type in listing. Listing removed.", ephemeral=False)
                            return

                    # Remove listing BEFORE updating balance
                    c.execute('DELETE FROM market_listings WHERE listing_id = ?', (listing_id,))
                    conn.commit()
                finally:
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

        conn = get_db_connection()
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

                conn = get_db_connection()
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
                                        conn = get_db_connection()
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

        conn = get_db_connection()
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
                    conn = get_db_connection()
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
        conn = get_db_connection()
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

        # ─── NEW TRADE FLOW ────────────────────────────────────────────────
        # Step 1: A selects item + amount → sends offer to B
        # Step 2: B selects what THEY offer back + amount → proposes
        # Step 3: A confirms or cancels the final deal
        # ───────────────────────────────────────────────────────────────

        def _build_item_options(items_list, prefix=""):
            opts = []
            for item in items_list[:25]:
                opts.append(discord.SelectOption(
                    label=f"{item['name']} (Have: {item['count']})",
                    value=f"{prefix}{item['type']}|{item['key']}",
                    emoji=item['emoji']
                ))
            return opts

        def _parse_item_val(val, prefix=""):
            clean = val[len(prefix):]
            itype, ikey = clean.split("|", 1)
            return itype, ikey

        def _find_item(items_list, item_type, item_key):
            return next((i for i in items_list if i['type'] == item_type and i['key'] == item_key), None)

        async def _execute_trade(acc_inter, s_item, s_amount, r_item, r_amount):
            """Transfer items between sender (A) and receiver (B)."""
            def _do_db():
                conn = get_db_connection()
                try:
                    c = conn.cursor()

                    def _transfer(itype, ikey, from_uid, to_uid, amt):
                        if itype == 'lucky_charm':
                            c.execute('UPDATE user_luckycharms SET count = count - ? WHERE guild_id = ? AND user_id = ?', (amt, guild_id, from_uid))
                            c.execute('INSERT INTO user_luckycharms (guild_id, user_id, count) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + ?', (guild_id, to_uid, amt, amt))
                        elif itype == 'dragonscale':
                            c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?', (amt, guild_id, from_uid))
                            c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET minutes = minutes + ?', (guild_id, to_uid, amt, amt))
                        elif itype in ('dna', 'lucky_dice', 'night_vision'):
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?', (amt, guild_id, from_uid, itype))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?', (guild_id, to_uid, itype, amt, amt))
                        elif itype == 'pack':
                            c.execute('UPDATE user_packs SET count = count - ? WHERE guild_id = ? AND user_id = ? AND pack_type = ?', (amt, guild_id, from_uid, ikey))
                            c.execute('INSERT INTO user_packs (guild_id, user_id, pack_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, pack_type) DO UPDATE SET count = count + ?', (guild_id, to_uid, ikey, amt, amt))

                    if s_item['type'] != 'dragon':
                        _transfer(s_item['type'], s_item['key'], interaction.user.id, user.id, s_amount)
                    if r_item['type'] != 'dragon':
                        _transfer(r_item['type'], r_item['key'], user.id, interaction.user.id, r_amount)
                    conn.commit()
                finally:
                    conn.close()

            try:
                await asyncio.to_thread(_do_db)
                if s_item['type'] == 'dragon':
                    await add_dragons(guild_id, interaction.user.id, s_item['key'], -s_amount)
                    await add_dragons(guild_id, user.id, s_item['key'], s_amount)
                if r_item['type'] == 'dragon':
                    await add_dragons(guild_id, user.id, r_item['key'], -r_amount)
                    await add_dragons(guild_id, interaction.user.id, r_item['key'], r_amount)

                for _uid in (interaction.user.id, user.id):
                    _qr = await asyncio.to_thread(check_dragonpass_quests, guild_id, _uid, 'complete_trade')
                    if _qr and _qr[3]:
                        await send_quest_notification(acc_inter.client, guild_id, _uid, _qr[3])

                await acc_inter.response.edit_message(
                    content=f"✅ **Trade Completed!**\n{interaction.user.mention} gave **{s_amount}×** {s_item['emoji']} {s_item['name']} → {user.mention}\n{user.mention} gave **{r_amount}×** {r_item['emoji']} {r_item['name']} → {interaction.user.mention}",
                    embed=None, view=None
                )
            except Exception as e:
                try:
                    await acc_inter.response.send_message(f"❌ Trade failed: {e}", ephemeral=False)
                except Exception:
                    pass

        # ── Step 3: A confirms the final deal ──────────────────────────
        def _make_confirm_view(s_item, s_amount, r_item, r_amount):
            class TradeConfirmView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=180)
                    self.done = False

                @discord.ui.button(label="✅ Confirm Trade", style=discord.ButtonStyle.green)
                async def confirm_btn(self, conf_inter: discord.Interaction, button: discord.ui.Button):
                    if conf_inter.user.id != interaction.user.id:
                        await conf_inter.response.send_message("❌ Only the trade initiator can confirm!", ephemeral=True)
                        return
                    if self.done:
                        await conf_inter.response.send_message("❌ Already processed.", ephemeral=True)
                        return
                    self.done = True
                    self.stop()
                    await _execute_trade(conf_inter, s_item, s_amount, r_item, r_amount)

                @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
                async def cancel_btn(self, cancel_inter: discord.Interaction, button: discord.ui.Button):
                    if cancel_inter.user.id != interaction.user.id:
                        await cancel_inter.response.send_message("❌ Only the trade initiator can cancel!", ephemeral=True)
                        return
                    self.done = True
                    self.stop()
                    await cancel_inter.response.edit_message(content="❌ Trade cancelled.", embed=None, view=None)

            return TradeConfirmView()

        # ── Step 2: B selects their offer + amount + submits ───────────
        def _make_receiver_view(s_item, s_amount):
            class ReceiverItemView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=300)
                    opts = _build_item_options(their_items, "r_")
                    sel = discord.ui.Select(placeholder="What will you offer in return?", options=opts, min_values=1, max_values=1)
                    sel.callback = self.item_selected
                    self.add_item(sel)
                    self.r_item = None

                async def item_selected(self, inter3: discord.Interaction):
                    if inter3.user.id != user.id:
                        await inter3.response.send_message("❌ Only the trade recipient can respond!", ephemeral=True)
                        return
                    val = inter3.data['values'][0]
                    itype, ikey = _parse_item_val(val, "r_")
                    r_item = _find_item(their_items, itype, ikey)
                    if not r_item:
                        await inter3.response.send_message("❌ Item not found!", ephemeral=True)
                        return
                    self.r_item = r_item
                    max_amt = min(r_item['count'], 10)
                    amt_opts = [discord.SelectOption(label=str(i), value=str(i)) for i in range(1, max_amt + 1)]

                    class ReceiverAmountView(discord.ui.View):
                        def __init__(self_):
                            super().__init__(timeout=300)
                            sel2 = discord.ui.Select(placeholder="How many?", options=amt_opts, min_values=1, max_values=1)
                            sel2.callback = self_.amount_selected
                            self_.add_item(sel2)

                        async def amount_selected(self_, inter4: discord.Interaction):
                            if inter4.user.id != user.id:
                                await inter4.response.send_message("❌ Only the trade recipient can respond!", ephemeral=True)
                                return
                            r_amount = int(inter4.data['values'][0])
                            confirm_embed = discord.Embed(
                                title="🤝 Trade Proposal",
                                description=f"{user.mention} has made an offer! {interaction.user.mention}, do you accept?",
                                color=discord.Color.gold()
                            )
                            confirm_embed.add_field(name=f"{interaction.user.display_name} gives", value=f"**{s_amount}×** {s_item['emoji']} {s_item['name']}", inline=True)
                            confirm_embed.add_field(name=f"{user.display_name} gives", value=f"**{r_amount}×** {r_item['emoji']} {r_item['name']}", inline=True)
                            confirm_embed.set_footer(text="Expires in 3 minutes")
                            await inter4.response.send_message(
                                content=interaction.user.mention,
                                embed=confirm_embed,
                                view=_make_confirm_view(s_item, s_amount, r_item, r_amount)
                            )

                    amt_embed = discord.Embed(
                        title="📦 How many?",
                        description=f"You have **{r_item['count']}** {r_item['emoji']} {r_item['name']}",
                        color=discord.Color.blue()
                    )
                    await inter3.response.send_message(embed=amt_embed, view=ReceiverAmountView(), ephemeral=False)

                @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red, row=1)
                async def decline_btn(self, dec_inter: discord.Interaction, button: discord.ui.Button):
                    if dec_inter.user.id != user.id:
                        await dec_inter.response.send_message("❌ Only the trade recipient can decline!", ephemeral=True)
                        return
                    self.stop()
                    await dec_inter.response.edit_message(
                        content=f"❌ {user.display_name} declined the trade.",
                        embed=None, view=None
                    )

            return ReceiverItemView()

        # ── Step 1: A selects their item ────────────────────────────────
        class SenderItemView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                opts = _build_item_options(your_items, "s_")
                sel = discord.ui.Select(placeholder="What do you want to offer?", options=opts, min_values=1, max_values=1)
                sel.callback = self.item_selected
                self.add_item(sel)

            async def item_selected(self, inter1: discord.Interaction):
                if inter1.user.id != interaction.user.id:
                    await inter1.response.send_message("❌ This is not your trade!", ephemeral=True)
                    return
                val = inter1.data['values'][0]
                itype, ikey = _parse_item_val(val, "s_")
                s_item = _find_item(your_items, itype, ikey)
                if not s_item:
                    await inter1.response.send_message("❌ Item not found!", ephemeral=True)
                    return
                max_amt = min(s_item['count'], 10)
                amt_opts = [discord.SelectOption(label=str(i), value=str(i)) for i in range(1, max_amt + 1)]

                class SenderAmountView(discord.ui.View):
                    def __init__(self_):
                        super().__init__(timeout=300)
                        sel2 = discord.ui.Select(placeholder="How many?", options=amt_opts, min_values=1, max_values=1)
                        sel2.callback = self_.amount_selected
                        self_.add_item(sel2)

                    async def amount_selected(self_, inter2: discord.Interaction):
                        if inter2.user.id != interaction.user.id:
                            await inter2.response.send_message("❌ This is not your trade!", ephemeral=True)
                            return
                        s_amount = int(inter2.data['values'][0])
                        offer_embed = discord.Embed(
                            title="🤝 Trade Request",
                            description=f"{interaction.user.mention} wants to trade with you, {user.mention}!",
                            color=discord.Color.blue()
                        )
                        offer_embed.add_field(name=f"{interaction.user.display_name} offers", value=f"**{s_amount}×** {s_item['emoji']} {s_item['name']}", inline=False)
                        offer_embed.add_field(name="Your response", value="Select what you want to offer in return:", inline=False)
                        offer_embed.set_footer(text="Expires in 5 minutes")
                        await inter2.response.send_message(
                            content=user.mention,
                            embed=offer_embed,
                            view=_make_receiver_view(s_item, s_amount)
                        )

                amt_embed = discord.Embed(
                    title="📦 How many?",
                    description=f"You have **{s_item['count']}** {s_item['emoji']} {s_item['name']}",
                    color=discord.Color.blue()
                )
                await inter1.response.send_message(embed=amt_embed, view=SenderAmountView(), ephemeral=False)

        setup_embed = discord.Embed(
            title="🤝 Trade Setup",
            description=f"Select what you want to offer {user.mention}",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=setup_embed, view=SenderItemView(), ephemeral=False)

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
        conn = get_db_connection()
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
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                                          (amount, guild_id, interaction.user.id))
                                c.execute('INSERT INTO users (guild_id, user_id, balance) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = balance + ?',
                                          (guild_id, user.id, amount, amount))
                                conn.commit()
                                conn.close()

                                _gq = await asyncio.to_thread(check_dragonpass_quests, guild_id, interaction.user.id, 'gift_dragon')
                                if _gq and _gq[3]:
                                    await send_quest_notification(modal_interaction.client, guild_id, interaction.user.id, _gq[3])

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
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute('UPDATE user_luckycharms SET count = count - ? WHERE guild_id = ? AND user_id = ?',
                                      (amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO user_luckycharms (guild_id, user_id, count) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'dragonscale':
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute('UPDATE dragonscales SET minutes = minutes - ? WHERE guild_id = ? AND user_id = ?',
                                      (amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET minutes = minutes + ?',
                                      (guild_id, user.id, amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'dna':
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (amount, guild_id, interaction.user.id, 'dna'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'dna', amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'lucky_dice':
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (amount, guild_id, interaction.user.id, 'lucky_dice'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'lucky_dice', amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'night_vision':
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute('UPDATE user_items SET count = count - ? WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                      (amount, guild_id, interaction.user.id, 'night_vision'))
                            c.execute('INSERT INTO user_items (guild_id, user_id, item_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, item_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, 'night_vision', amount, amount))
                            conn.commit()
                            conn.close()
                        elif self.sel_item['type'] == 'pack':
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute('UPDATE user_packs SET count = count - ? WHERE guild_id = ? AND user_id = ? AND pack_type = ?',
                                      (amount, guild_id, interaction.user.id, self.sel_item['key']))
                            c.execute('INSERT INTO user_packs (guild_id, user_id, pack_type, count) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, pack_type) DO UPDATE SET count = count + ?',
                                      (guild_id, user.id, self.sel_item['key'], amount, amount))
                            conn.commit()
                            conn.close()

                        _gq = await asyncio.to_thread(check_dragonpass_quests, guild_id, interaction.user.id, 'gift_dragon')
                        if _gq and _gq[3]:
                            await send_quest_notification(btn_interaction.client, guild_id, interaction.user.id, _gq[3])

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
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute('UPDATE users SET balance = balance - ? WHERE guild_id = ? AND user_id = ?',
                                      (amount, guild_id, interaction.user.id))
                            c.execute('INSERT INTO users (guild_id, user_id, balance) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = balance + ?',
                                      (guild_id, user.id, amount, amount))
                            conn.commit()
                            conn.close()

                            _gq = await asyncio.to_thread(check_dragonpass_quests, guild_id, interaction.user.id, 'gift_dragon')
                            if _gq and _gq[3]:
                                await send_quest_notification(modal_interaction.client, guild_id, interaction.user.id, _gq[3])

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

        conn = get_db_connection()
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
                    conn = get_db_connection()
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
