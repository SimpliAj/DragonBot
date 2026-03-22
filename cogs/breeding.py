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
from achievements import award_trophy


class BreedingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="breed", description="Cross-breed two dragons for a chance at higher rarity!")
    async def breed(self, interaction: discord.Interaction):
        """Cross-breeding system - combine 2 dragons for higher rarity offspring"""
        await interaction.response.defer(ephemeral=False)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # Check breeding cooldown
        c.execute('SELECT last_breed, last_breed_rarity FROM breeding_cooldowns WHERE guild_id = ? AND user_id = ?',
                  (interaction.guild_id, interaction.user.id))
        cooldown_result = c.fetchone()

        if cooldown_result:
            last_breed = cooldown_result[0]
            last_rarity = cooldown_result[1] if len(cooldown_result) > 1 and cooldown_result[1] else 'common'
            current_time = int(time.time())
            time_passed = current_time - last_breed
            cooldown_duration = BREEDING_COOLDOWNS.get(last_rarity, BREEDING_COOLDOWNS['common'])

            if time_passed < cooldown_duration:
                time_left = cooldown_duration - time_passed
                embed = discord.Embed(
                    title="⏰ Breeding Cooldown",
                    description=f"Your breeding lab needs to rest!\n\n"
                                f"Last breed: **{last_rarity.title()}** rarity\n"
                                f"Time remaining: **{format_time_remaining(time_left)}**\n\n"
                                f"💡 **Tip:** Higher rarity breeds = longer cooldowns\n"
                                f"• Common: 30min | Rare: 1h | Legendary: 2h | Ultra: 3h",
                    color=0xFF6B6B
                )
                await interaction.followup.send(embed=embed, ephemeral=False)
                conn.close()
                return

        # Get user's dragons
        c.execute('''SELECT dragon_type, count FROM user_dragons
                     WHERE guild_id = ? AND user_id = ? AND count > 0
                     ORDER BY dragon_type''',
                  (interaction.guild_id, interaction.user.id))
        raw_dragons = c.fetchall()

        # Check DNA Sample
        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (interaction.guild_id, interaction.user.id, 'dna'))
        dna_result = c.fetchone()
        dna_count = dna_result[0] if dna_result else 0

        conn.close()

        # Normalize dragons immediately
        user_dragons = []
        for db_type, count in raw_dragons:
            normalized = normalize_dragon_type(db_type)
            if normalized in DRAGON_TYPES:
                user_dragons.append((normalized, count))

        # Check requirements
        if not user_dragons or sum(count for _, count in user_dragons) < 2:
            embed = discord.Embed(
                title="🧬 Dragon Cross-Breeding",
                description="You need at least 2 dragons to breed!\n\nCatch some dragons first, then come back.",
                color=0x9B59B6
            )
            await interaction.followup.send(embed=embed)
            return

        if dna_count < 1:
            embed = discord.Embed(
                title="🧬 DNA Sample Required",
                description="You need a **DNA Sample** to breed dragons!\n\n"
                            "Get one in the `/shop` for 5,000🪙\n\n"
                            "**DNA Break Chances by Rarity:**\n"
                            "🟢 Common: 5% | 🔵 Uncommon: 10% | 🟣 Rare: 15%\n"
                            "🟠 Epic: 25% | 🟡 Legendary: 35% | 🌟 Mythic: 42% | ✨ Ultra: 50%",
                color=0xFF6B6B
            )
            await interaction.followup.send(embed=embed)
            return

        def get_rarity(dragon_type):
            for rarity, dragons in DRAGON_RARITY_TIERS.items():
                if dragon_type in dragons:
                    return rarity
            return 'common'

        # Get breeding info
        breeding_info = get_breeding_level_info(interaction.guild_id, interaction.user.id)
        max_queue_slots = get_breeding_queue_slots(breeding_info['level'])

        # Build main embed
        embed = discord.Embed(
            title="🧬 Dragon Cross-Breeding Laboratory",
            description="**How Cross-Breeding Works:**\n"
                        "🔬 Select 2 dragons from your collection\n"
                        "✨ Combine them for chance at higher rarity!\n"
                        "🎲 High chance for upgrade, low chance for fail\n"
                        "📈 Higher rarity parents = Better offspring!\n"
                        "⏰ Dynamic cooldowns (30min-3h based on rarity)\n\n"
                        "**Requirements:**\n"
                        "🧬 1x DNA Sample (Break Chance: 5%-50% based on parent rarity)\n"
                        "💰 Cost: 1,000🪙 (parents stay!)\n\n"
                        "**Breeding XP System:**\n"
                        f"Your Level: **{breeding_info['level']}** | XP: **{breeding_info['xp']}**\n"
                        f"Queue Slots: **{max_queue_slots}**\n"
                        "Level 5: +1 Queue Slot | Level 10: +2 Slots | Level 15: +3 Slots\n\n"
                        "**Examples:**\n"
                        "• Common + Common → 50% uncommon, 25% common, 15% rare\n"
                        "• Rare + Rare → 55% epic, 17% rare, 20% legendary\n"
                        "• Legendary + Mythic → 77% ultra, 20% mythic\n"
                        "• Ultra + Ultra → 100% ultra (guaranteed!)\n\n"
                        "⚠️ If breeding fails, one random parent is consumed!\n\n"
                        "**Cooldowns by Rarity:**\n"
                        "Common: 30m | Uncommon: 45m | Rare: 1h | Epic: 1.5h\n"
                        "Legendary: 2h | Mythic: 2.5h | Ultra: 3h",
            color=0x9B59B6
        )

        # Rarity info
        rarity_info = ""
        for rarity, dragons in DRAGON_RARITY_TIERS.items():
            rarity_info += f"**{rarity.title()}:** {len(dragons)} types\n"
        embed.add_field(name="🌟 Rarity Tiers", value=rarity_info, inline=True)

        # Collection info
        rarity_counts = {}
        for dragon_type, count in user_dragons:
            rarity = get_rarity(dragon_type)
            rarity_counts[rarity] = rarity_counts.get(rarity, 0) + count

        collection_info = ""
        for rarity in ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra']:
            if rarity in rarity_counts:
                collection_info += f"**{rarity.title()}:** {rarity_counts[rarity]}\n"
        embed.add_field(name="📦 Your Collection", value=collection_info or "No dragons", inline=True)

        # Create button view
        class BreedView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)

            @discord.ui.button(label="Start Cross-Breeding", style=discord.ButtonStyle.primary, emoji="🧬")
            async def start(self, inter: discord.Interaction, button: discord.ui.Button):
                session_key = (inter.guild_id, inter.user.id)
                if session_key in active_breeding_sessions:
                    await inter.response.send_message("❌ Breeding session in progress!", ephemeral=True)
                    return

                active_breeding_sessions[session_key] = int(time.time())
                await inter.response.defer()

                # Parent 1 view
                class Parent1View(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=60)
                        options = []
                        seen = set()

                        for dragon_type, count in sort_dragons_by_rarity(user_dragons)[:25]:
                            if dragon_type in seen or dragon_type not in DRAGON_TYPES:
                                continue
                            seen.add(dragon_type)

                            data = DRAGON_TYPES[dragon_type]
                            rarity = get_rarity(dragon_type)
                            options.append(discord.SelectOption(
                                label=f"{data['name']} ({count} owned)",
                                description=f"Rarity: {rarity.title()}",
                                emoji=data['emoji'],
                                value=str(dragon_type)
                            ))

                        if options:
                            select = discord.ui.Select(placeholder="Select first parent dragon...", options=options)
                            select.callback = self.select_parent1
                            self.add_item(select)

                    async def select_parent1(self, inter2: discord.Interaction):
                        await inter2.response.defer()

                        # Get selected values from inter.data (discord.py v2 style)
                        selected_values = inter2.data.get("values", []) if inter2.data else []

                        if not selected_values:
                            await inter2.followup.send("❌ Please select a dragon from the dropdown!", ephemeral=True)
                            return

                        p1 = selected_values[0]

                        if p1 not in DRAGON_TYPES:
                            await inter2.followup.send(f"❌ Invalid dragon: {p1}", ephemeral=True)
                            return

                        # Parent 2 view
                        class Parent2View(discord.ui.View):
                            def __init__(self):
                                super().__init__(timeout=60)
                                options = []
                                seen = set()

                                for dragon_type, count in sort_dragons_by_rarity(user_dragons)[:25]:
                                    if dragon_type in seen or dragon_type == p1 or dragon_type not in DRAGON_TYPES:
                                        continue
                                    seen.add(dragon_type)

                                    data = DRAGON_TYPES[dragon_type]
                                    rarity = get_rarity(dragon_type)
                                    options.append(discord.SelectOption(
                                        label=f"{data['name']} ({count} owned)",
                                        description=f"Rarity: {rarity.title()}",
                                        emoji=data['emoji'],
                                        value=str(dragon_type)
                                    ))

                                if options:
                                    select = discord.ui.Select(placeholder="Select second parent dragon...", options=options)
                                    select.callback = self.select_parent2
                                    self.add_item(select)

                            async def select_parent2(self, inter3: discord.Interaction):
                                await inter3.response.defer()

                                # Get selected values from inter.data
                                selected_values = inter3.data.get("values", []) if inter3.data else []

                                if not selected_values:
                                    await inter3.followup.send("❌ Please select a dragon!", ephemeral=True)
                                    return

                                p2 = selected_values[0]
                                if p2 not in DRAGON_TYPES:
                                    await inter3.followup.send("❌ Invalid dragon!", ephemeral=True)
                                    return

                                r1 = get_rarity(p1)
                                r2 = get_rarity(p2)

                                breeding_key = (r1, r2)
                                if breeding_key not in BREEDING_CHANCES:
                                    breeding_key = (r2, r1)
                                chances = BREEDING_CHANCES.get(breeding_key, {'common': 100})

                                p1_data = DRAGON_TYPES[p1]
                                p2_data = DRAGON_TYPES[p2]
                                chances_text = "\n".join([f"**{r.title()}:** {p}%" for r, p in chances.items()])

                                confirm_embed = discord.Embed(
                                    title="🧬 Confirm Cross-Breeding",
                                    description=f"**Parent 1:** {p1_data['emoji']} {p1_data['name']} ({r1})\n"
                                               f"**Parent 2:** {p2_data['emoji']} {p2_data['name']} ({r2})\n\n"
                                               f"**Cost:** 1,000🪙\n**Parents:** Both stay in your inventory\n\n"
                                               f"**Offspring Chances:**\n{chances_text}",
                                    color=0xFFD700
                                )

                                class ConfirmView(discord.ui.View):
                                    def __init__(self):
                                        super().__init__(timeout=30)

                                    @discord.ui.button(label="Breed!", style=discord.ButtonStyle.success, emoji="✨")
                                    async def confirm(self, inter4: discord.Interaction, button: discord.ui.Button):
                                        button.disabled = True
                                        await inter4.response.defer()

                                        def breed_logic():
                                            conn = sqlite3.connect('dragon_bot.db', timeout=60.0)
                                            c = conn.cursor()

                                            try:
                                                # Check balance
                                                c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                                                          (inter4.guild_id, inter4.user.id))
                                                bal = c.fetchone()
                                                balance = bal[0] if bal else 0

                                                if balance < 1000:
                                                    conn.close()
                                                    return {'error': "❌ You need 1,000🪙!"}

                                                # Check dragons
                                                c.execute('SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                                          (inter4.guild_id, inter4.user.id, p1))
                                                c1 = c.fetchone()
                                                c.execute('SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                                          (inter4.guild_id, inter4.user.id, p2))
                                                c2 = c.fetchone()

                                                if not c1 or c1[0] < 1 or not c2 or c2[0] < 1:
                                                    conn.close()
                                                    return {'error': "❌ Dragons missing!"}

                                                # Check DNA
                                                c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                                          (inter4.guild_id, inter4.user.id, 'dna'))
                                                dna = c.fetchone()
                                                if not dna or dna[0] < 1:
                                                    conn.close()
                                                    return {'error': "❌ No DNA Sample!"}

                                                # Deduct cost
                                                c.execute('UPDATE users SET balance = balance - 1000 WHERE guild_id = ? AND user_id = ?',
                                                          (inter4.guild_id, inter4.user.id))
                                                c.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                                                          (inter4.guild_id, inter4.user.id, 'dna'))

                                                # Roll
                                                rarity_order = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra']
                                                hr = r1 if rarity_order.index(r1) >= rarity_order.index(r2) else r2
                                                dna_break = random.randint(1, 100) <= DNA_BREAK_CHANCES.get(hr, 50)

                                                roll = random.randint(1, 100)
                                                cumulative = 0
                                                result_rarity = 'fail'
                                                for rarity, chance in chances.items():
                                                    cumulative += chance
                                                    if roll <= cumulative:
                                                        result_rarity = rarity
                                                        break

                                                # Set cooldown
                                                c.execute('''INSERT INTO breeding_cooldowns (guild_id, user_id, last_breed, last_breed_rarity)
                                                             VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id)
                                                             DO UPDATE SET last_breed = ?, last_breed_rarity = ?''',
                                                          (inter4.guild_id, inter4.user.id, int(time.time()), hr, int(time.time()), hr))

                                                if result_rarity == 'fail':
                                                    consumed = random.choice([p1, p2])
                                                    c.execute('UPDATE user_dragons SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                                              (inter4.guild_id, inter4.user.id, consumed))
                                                    xp_result = add_breeding_xp(inter4.guild_id, inter4.user.id, BREEDING_XP_GAINS['fail'], cursor=c, conn=conn)
                                                    conn.commit()
                                                    conn.close()
                                                    return {'status': 'failed', 'roll': roll, 'consumed': consumed, 'dna': dna_break, 'new_level': xp_result.get('new_level') if xp_result else None}

                                                # Success
                                                offspring = random.choice(DRAGON_RARITY_TIERS[result_rarity])
                                                c.execute('''INSERT OR IGNORE INTO user_dragons (guild_id, user_id, dragon_type, count)
                                                             VALUES (?, ?, ?, 1)''',
                                                          (inter4.guild_id, inter4.user.id, offspring))
                                                c.execute('UPDATE user_dragons SET count = count + 1 WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                                                          (inter4.guild_id, inter4.user.id, offspring))
                                                xp_result = add_breeding_xp(inter4.guild_id, inter4.user.id, BREEDING_XP_GAINS['success'], cursor=c, conn=conn)
                                                conn.commit()
                                                conn.close()

                                                return {'status': 'success', 'roll': roll, 'rarity': result_rarity, 'offspring': offspring, 'dna': dna_break, 'hr': hr, 'new_level': xp_result.get('new_level') if xp_result else None}
                                            except Exception as e:
                                                conn.close()
                                                return {'error': f"❌ Error: {str(e)}"}

                                        result = await asyncio.to_thread(breed_logic)

                                        if 'error' in result:
                                            await inter4.followup.send(result['error'], ephemeral=False)
                                            return

                                        if result['status'] == 'failed':
                                            consumed_data = DRAGON_TYPES[result['consumed']]
                                            result_embed = discord.Embed(
                                                title="💔 Breeding Failed!",
                                                description=f"**Parents:**\n"
                                                           f"{p1_data['emoji']} {p1_data['name']} + "
                                                           f"{p2_data['emoji']} {p2_data['name']}\n\n"
                                                           f"⚠️ The breeding experiment failed!\n"
                                                           f"One dragon was consumed...\n\n"
                                                           f"**Lost:** {consumed_data['emoji']} {consumed_data['name']}\n\n"
                                                           f"🎲 Rolled: {result['roll']}/100\n"
                                                           f"⏰ Cooldown: Initiated",
                                                color=discord.Color.red()
                                            )
                                            await inter4.followup.send(embed=result_embed)
                                            if result.get('new_level') == 10:
                                                await award_trophy(inter4.client, inter4.guild_id, inter4.user.id, 'breeding_master')
                                            if session_key in active_breeding_sessions:
                                                del active_breeding_sessions[session_key]
                                            return

                                        # Success
                                        offspring_data = DRAGON_TYPES[result['offspring']]
                                        cooldown_time = BREEDING_COOLDOWNS.get(result['hr'], BREEDING_COOLDOWNS['common'])
                                        cd_h = cooldown_time // 3600
                                        cd_m = (cooldown_time % 3600) // 60

                                        result_embed = discord.Embed(
                                            title="✨ Breeding Successful!",
                                            description=f"**Parents:**\n"
                                                       f"{p1_data['emoji']} {p1_data['name']} + "
                                                       f"{p2_data['emoji']} {p2_data['name']}\n\n"
                                                       f"**Offspring:**\n"
                                                       f"{offspring_data['emoji']} **{offspring_data['name']}**\n"
                                                       f"Rarity: **{result['rarity'].upper()}**\n"
                                                       f"Value: **{offspring_data['value']}🪙**\n\n"
                                                       f"✅ Parents remain in your inventory!\n"
                                                       f"**Cost:** 1,000🪙\n"
                                                       f"🧬 DNA: {'✅ Survived' if not result['dna'] else '❌ Destroyed'}\n\n"
                                                       f"🎲 Rolled: {result['roll']}/100\n"
                                                       f"⏰ Cooldown: {cd_h}h {cd_m}m ({result['hr'].title()} tier)",
                                            color=discord.Color.gold()
                                        )
                                        await inter4.followup.send(embed=result_embed)
                                        if result.get('new_level') == 10:
                                            await award_trophy(inter4.client, inter4.guild_id, inter4.user.id, 'breeding_master')
                                        if session_key in active_breeding_sessions:
                                            del active_breeding_sessions[session_key]

                                    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                                    async def cancel(self, inter4: discord.Interaction, button: discord.ui.Button):
                                        await inter4.response.followup.send(content="❌ Cancelled", ephemeral=False)
                                        if session_key in active_breeding_sessions:
                                            del active_breeding_sessions[session_key]

                                await inter3.response.followup.send(embed=confirm_embed, view=ConfirmView())

                        await inter2.response.followup.send(content="Now select the second parent:", view=Parent2View())

                await inter.followup.send("Select the first parent dragon:", view=Parent1View(), ephemeral=False)

        await interaction.followup.send(embed=embed, view=BreedView())

    @app_commands.command(name="breedcalc", description="Calculate breeding outcomes - select dragons from your inventory!")
    async def breedcalc(self, interaction: discord.Interaction):
        """Breeding calculator with inventory selection"""
        await interaction.response.defer(ephemeral=False)

        # Get user's dragons
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('''SELECT dragon_type, count FROM user_dragons
                     WHERE guild_id = ? AND user_id = ? AND count > 0
                     ORDER BY dragon_type''',
                  (interaction.guild_id, interaction.user.id))
        raw_dragons = c.fetchall()
        conn.close()

        if not raw_dragons or sum(count for _, count in raw_dragons) < 2:
            await interaction.followup.send(
                "❌ You need at least 2 dragons to check breeding outcomes!\n\nCatch some dragons first with `/dragon`",
                ephemeral=False
            )
            return

        # NORMALIZE all dragon types from DB
        user_dragons = []
        for db_type, count in raw_dragons:
            normalized = normalize_dragon_type(db_type)
            if normalized in DRAGON_TYPES:
                user_dragons.append((normalized, count))

        if not user_dragons or sum(count for _, count in user_dragons) < 2:
            await interaction.followup.send(
                "❌ Could not load your dragons properly. Try again!",
                ephemeral=False
            )
            return

        # Helper to get rarity
        def get_rarity(dragon_type):
            for rarity, dragons in DRAGON_RARITY_TIERS.items():
                if dragon_type in dragons:
                    return rarity
            return 'common'

        # Parent 1 selection
        class Parent1SelectView(discord.ui.View):
            def __init__(self, dragons):
                super().__init__(timeout=60)
                # Sort by rarity
                sorted_dragons = sort_dragons_by_rarity(dragons)
                self.dragons = sorted_dragons

                options = []
                seen = set()
                for dragon_type, count in sorted_dragons[:25]:
                    if dragon_type in seen:
                        continue
                    seen.add(dragon_type)

                    if dragon_type not in DRAGON_TYPES:
                        continue

                    dragon_data = DRAGON_TYPES[dragon_type]
                    rarity = get_rarity(dragon_type)
                    options.append(discord.SelectOption(
                        label=f"{dragon_data['name']} ({count}x)",
                        description=f"Rarity: {rarity.title()}",
                        emoji=dragon_data['emoji'],
                        value=str(dragon_type)
                    ))

                select = discord.ui.Select(placeholder="Select first parent...", options=options, row=0)
                select.callback = self.parent1_selected
                self.add_item(select)

            async def parent1_selected(self, inter: discord.Interaction):
                await inter.response.defer()

                # Get selected values from inter.data (discord.py v2 style)
                selected_values = inter.data.get("values", []) if inter.data else []

                if not selected_values:
                    await inter.followup.send("❌ Please select a dragon from the dropdown!", ephemeral=True)
                    return

                parent1 = selected_values[0]

                if parent1 not in DRAGON_TYPES:
                    await inter.followup.send(f"❌ Invalid dragon: {parent1}", ephemeral=True)
                    return

                # Parent 2 selection
                class Parent2SelectView(discord.ui.View):
                    def __init__(self, dragons, p1):
                        super().__init__(timeout=60)
                        self.parent1 = p1
                        sorted_dragons = sort_dragons_by_rarity(dragons)
                        self.dragons = sorted_dragons

                        options = []
                        seen = set()
                        for dragon_type, count in sorted_dragons[:25]:
                            # Skip duplicates and parent1
                            if dragon_type in seen or dragon_type == p1:
                                continue

                            if dragon_type not in DRAGON_TYPES:
                                continue

                            seen.add(dragon_type)
                            dragon_data = DRAGON_TYPES[dragon_type]
                            rarity = get_rarity(dragon_type)
                            options.append(discord.SelectOption(
                                label=f"{dragon_data['name']} ({count}x)",
                                description=f"Rarity: {rarity.title()}",
                                emoji=dragon_data['emoji'],
                                value=str(dragon_type)
                            ))

                        select = discord.ui.Select(placeholder="Select second parent...", options=options, row=0)
                        select.callback = self.parent2_selected
                        self.add_item(select)

                    async def parent2_selected(self, inter2: discord.Interaction):
                        await inter2.response.defer()

                        # Get selected values from inter.data (discord.py v2 style)
                        selected_values = inter2.data.get("values", []) if inter2.data else []

                        if not selected_values:
                            await inter2.followup.send("❌ Please select a dragon from the dropdown!", ephemeral=True)
                            return

                        parent2 = selected_values[0]

                        if parent2 not in DRAGON_TYPES:
                            await inter2.followup.send(f"❌ Invalid dragon: {parent2}", ephemeral=True)
                            return

                        # Get rarities
                        rarity1 = get_rarity(self.parent1)
                        rarity2 = get_rarity(parent2)

                        # Get breeding chances (using tuple keys)
                        breeding_key = (rarity1, rarity2)
                        if breeding_key not in BREEDING_CHANCES:
                            breeding_key = (rarity2, rarity1)

                        chances = BREEDING_CHANCES.get(breeding_key, {'common': 100})

                        # Build calculation embed
                        parent1_data = DRAGON_TYPES[self.parent1]
                        parent2_data = DRAGON_TYPES[parent2]

                        embed = discord.Embed(
                            title="🧬 Breeding Calculator",
                            description=f"**Parents:**\n{parent1_data['emoji']} **{parent1_data['name']}** ({rarity1.title()})\n"
                                        f"{parent2_data['emoji']} **{parent2_data['name']}** ({rarity2.title()})\n\n"
                                        f"**Possible Outcomes:**",
                            color=0x9B59B6
                        )

                        # Show all possible outcomes sorted by chance
                        sorted_outcomes = sorted(chances.items(), key=lambda x: x[1], reverse=True)

                        outcomes_text = ""
                        for result_rarity, chance in sorted_outcomes:
                            if result_rarity == 'fail':
                                outcomes_text += f"❌ **Fail** - {chance}% (consume 1 parent)\n"
                            else:
                                # Get example dragon from that rarity
                                example_dragons = DRAGON_RARITY_TIERS[result_rarity]
                                example = random.choice(example_dragons)
                                example_data = DRAGON_TYPES[example]
                                outcomes_text += f"{example_data['emoji']} **{result_rarity.title()}** - {chance}% chance\n"

                        embed.add_field(name="📊 Outcome Probabilities", value=outcomes_text, inline=False)

                        # Show rarity pool counts
                        rarity_counts = {}
                        for rarity, dragons_list in DRAGON_RARITY_TIERS.items():
                            rarity_counts[rarity] = len(dragons_list)

                        pools_text = ""
                        for result_rarity, chance in sorted_outcomes:
                            if result_rarity != 'fail':
                                count = rarity_counts.get(result_rarity, 0)
                                pools_text += f"**{result_rarity.title()}**: {count} dragons\n"

                        embed.add_field(name="🎲 Dragon Pool Sizes", value=pools_text or "No pools", inline=True)

                        # Show breeding cost & cooldown
                        rarity_order = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra']
                        higher_rarity = rarity1 if rarity_order.index(rarity1) >= rarity_order.index(rarity2) else rarity2
                        cooldown_duration = BREEDING_COOLDOWNS.get(higher_rarity, BREEDING_COOLDOWNS['common'])
                        cooldown_mins = cooldown_duration // 60
                        breeding_cost = BREEDING_XP_COSTS.get(higher_rarity, 500)

                        embed.add_field(
                            name="💰 Breeding Cost",
                            value=f"✅ Success: {breeding_cost:,}🪙 (parents stay)\n❌ Fail (3%): 1 parent consumed\n⏰ Cooldown: {cooldown_mins}min ({higher_rarity.title()})",
                            inline=True
                        )

                        # Get inventory counts
                        parent1_count = next((cnt for dtype, cnt in self.dragons if dtype == self.parent1), 0)
                        parent2_count = next((cnt for dtype, cnt in self.dragons if dtype == parent2), 0)

                        # Add inventory section
                        inventory_text = f"{parent1_data['emoji']} **{parent1_data['name']}**: {parent1_count}\n"
                        inventory_text += f"{parent2_data['emoji']} **{parent2_data['name']}**: {parent2_count}\n\n"

                        # Check if user can breed
                        can_breed = True
                        if parent1_count < 1 or parent2_count < 1:
                            can_breed = False
                        if self.parent1 == parent2 and parent1_count < 2:
                            can_breed = False

                        if can_breed:
                            inventory_text += "✅ **Ready to breed!** Use `/breed` to start."
                        else:
                            if self.parent1 == parent2:
                                inventory_text += f"❌ You need 2x {parent1_data['name']} (have {parent1_count})"
                            else:
                                inventory_text += f"❌ You need at least 1 of each type to breed"

                        embed.add_field(name="📦 Your Inventory", value=inventory_text, inline=False)
                        embed.set_footer(text="Use /breed to start breeding with these dragons!")

                        await inter2.followup.send(embed=embed)

                view = Parent2SelectView(self.dragons, parent1)
                await inter.followup.send(content="Now select the second parent:", view=view)

        # Start with parent 1 selection
        embed = discord.Embed(
            title="🧬 Breeding Calculator",
            description="Select your dragons to see breeding outcomes!",
            color=0x9B59B6
        )
        view = Parent1SelectView(user_dragons)
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="breedqueue", description="Schedule automatic breeding or view your queue")
    @app_commands.describe(
        action="'schedule' to queue a breeding, 'view' to see your queue, 'cancel' to remove from queue"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Schedule new breeding", value="schedule"),
        app_commands.Choice(name="View my queue", value="view"),
        app_commands.Choice(name="Cancel queued breeding", value="cancel")
    ])
    async def breedqueue(self, interaction: discord.Interaction, action: str):
        """Schedule automatic breedings (max 3 queued at once)"""
        await interaction.response.defer(ephemeral=False)

        if action == "view":
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            c.execute('''SELECT queue_id, parent1_type, parent2_type, scheduled_for, created_at
                         FROM breeding_queue
                         WHERE guild_id = ? AND user_id = ? AND status = 'pending'
                         ORDER BY scheduled_for ASC''',
                      (interaction.guild_id, interaction.user.id))
            queued = c.fetchall()
            conn.close()

            if not queued:
                embed = discord.Embed(
                    title="📋 Breeding Queue",
                    description="Your queue is empty!\n\nUse `/breedqueue action:schedule` to schedule automatic breedings.",
                    color=0x9B59B6
                )
                await interaction.followup.send(embed=embed)
                return

            embed = discord.Embed(
                title="📋 Your Breeding Queue",
                description=f"You have {len(queued)} breedings scheduled",
                color=0x9B59B6
            )

            current_time = int(time.time())
            queue_text = ""

            # Get breeding level
            breeding_info = get_breeding_level_info(interaction.guild_id, interaction.user.id)
            max_slots = get_breeding_queue_slots(breeding_info['level'])

            # Get user's current cooldown status
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()
            c.execute('SELECT last_breed, last_breed_rarity FROM breeding_cooldowns WHERE guild_id = ? AND user_id = ?',
                      (interaction.guild_id, interaction.user.id))
            cooldown_result = c.fetchone()
            conn.close()

            cooldown_status = "✅ Ready to breed!"
            if cooldown_result:
                last_breed = cooldown_result[0]
                last_rarity = cooldown_result[1] if len(cooldown_result) > 1 else 'common'
                cooldown_duration = BREEDING_COOLDOWNS.get(last_rarity, BREEDING_COOLDOWNS['common'])
                time_since = current_time - last_breed

                if time_since < cooldown_duration:
                    time_left = cooldown_duration - time_since
                    hours = time_left // 3600
                    mins = (time_left % 3600) // 60
                    if hours > 0:
                        cooldown_status = f"⏳ Cooldown: {hours}h {mins}m remaining"
                    else:
                        cooldown_status = f"⏳ Cooldown: {mins}m {time_left % 60}s remaining"

            queue_text += f"**Your Status:** {cooldown_status}\n"
            queue_text += f"**Breeding Level:** {breeding_info['level']} | **Queue Slots:** {len(queued)}/{max_slots}\n\n"

            for idx, (queue_id, p1, p2, scheduled_for, created_at) in enumerate(queued, 1):
                # NORMALIZE dragons from DB
                p1_normalized = normalize_dragon_type(p1)
                p2_normalized = normalize_dragon_type(p2)

                p1_data = DRAGON_TYPES.get(p1_normalized, {})
                p2_data = DRAGON_TYPES.get(p2_normalized, {})

                # Calculate cost for this breeding using NORMALIZED dragons
                p1_rarity = get_dragon_rarity(p1_normalized)
                p2_rarity = get_dragon_rarity(p2_normalized)
                cost = get_breeding_cost(p1_rarity, p2_rarity)

                queue_text += f"**#{idx}** - {p1_data.get('emoji', '🐉')} {p1_data.get('name', 'Unknown')} + {p2_data.get('emoji', '🐉')} {p2_data.get('name', 'Unknown')}\n"
                queue_text += f"└─ 💰 {cost:,}🪙 + 1x DNA | ⚡ Auto-starts when ready\n\n"

            embed.add_field(name="Scheduled Breedings", value=queue_text, inline=False)
            embed.set_footer(text="Breedings execute automatically when cooldown expires and you have coins. Use /breedqueue action:cancel to remove.")
            await interaction.followup.send(embed=embed)
            return

        if action == "cancel":
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()

            c.execute('''SELECT queue_id, parent1_type, parent2_type FROM breeding_queue
                         WHERE guild_id = ? AND user_id = ? AND status = 'pending'
                         ORDER BY scheduled_for ASC''',
                      (interaction.guild_id, interaction.user.id))
            queued = c.fetchall()
            conn.close()

            if not queued:
                await interaction.followup.send("❌ You have no queued breedings to cancel!", ephemeral=False)
                return

            if len(queued) == 1:
                # Only one item, cancel it directly
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('DELETE FROM breeding_queue WHERE queue_id = ?', (queued[0][0],))
                conn.commit()
                conn.close()

                p1_data = DRAGON_TYPES.get(queued[0][1], {})
                p2_data = DRAGON_TYPES.get(queued[0][2], {})

                await interaction.followup.send(
                    f"✅ Cancelled: {p1_data.get('emoji', '🐉')} {p1_data.get('name')} + {p2_data.get('emoji', '🐉')} {p2_data.get('name')}",
                    ephemeral=False
                )
                return

            # Multiple items - show selection
            class CancelQueueView(discord.ui.View):
                def __init__(self, queue_items):
                    super().__init__(timeout=60)
                    self.queue_items = queue_items

                    options = []
                    for queue_id, p1, p2 in queue_items:
                        # NORMALIZE dragons from DB
                        p1_normalized = normalize_dragon_type(p1)
                        p2_normalized = normalize_dragon_type(p2)

                        p1_data = DRAGON_TYPES.get(p1_normalized, {})
                        p2_data = DRAGON_TYPES.get(p2_normalized, {})
                        options.append(discord.SelectOption(
                            label=f"{p1_data.get('name', p1_normalized)} + {p2_data.get('name', p2_normalized)}",
                            emoji="🗑️",
                            value=str(queue_id)
                        ))

                    select = discord.ui.Select(
                        placeholder="Choose which breeding to cancel...",
                        options=options
                    )
                    select.callback = self.cancel_selected
                    self.add_item(select)

                async def cancel_selected(self, inter: discord.Interaction):
                    try:
                        queue_id = int(inter.values[0] if hasattr(inter, 'values') and inter.values else 0)
                    except (ValueError, IndexError):
                        await inter.followup.send("❌ Please select a valid queue item!", ephemeral=True)
                        return

                    conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                    c = conn.cursor()
                    c.execute('DELETE FROM breeding_queue WHERE queue_id = ?', (queue_id,))
                    conn.commit()
                    conn.close()

                    await inter.response.send_message("✅ Breeding cancelled from queue!", ephemeral=False)

            embed = discord.Embed(
                title="🗑️ Cancel Breeding",
                description="Select which breeding to remove from your queue:",
                color=0xFF6B6B
            )
            view = CancelQueueView(queued)
            await interaction.followup.send(embed=embed, view=view)
            return

        if action == "schedule":
            # Get user's dragons
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()
            c.execute('''SELECT dragon_type, count FROM user_dragons
                         WHERE guild_id = ? AND user_id = ? AND count > 0
                         ORDER BY dragon_type''',
                      (interaction.guild_id, interaction.user.id))
            raw_dragons = c.fetchall()
            conn.close()

            # NORMALIZE all dragon types from DB
            user_dragons = []
            for db_type, count in raw_dragons:
                normalized = normalize_dragon_type(db_type)
                if normalized in DRAGON_TYPES:
                    user_dragons.append((normalized, count))

            if not user_dragons or sum(count for _, count in user_dragons) < 2:
                await interaction.followup.send(
                    "❌ You need at least 2 dragons to schedule breeding!",
                    ephemeral=False
                )
                return

            # Helper to get rarity
            def get_rarity(dragon_type):
                for rarity, dragons in DRAGON_RARITY_TIERS.items():
                    if dragon_type in dragons:
                        return rarity
                return 'common'

            # Parent 1 selection
            class Parent1SelectView(discord.ui.View):
                def __init__(self, dragons):
                    super().__init__(timeout=60)
                    # Sort by rarity
                    sorted_dragons = sort_dragons_by_rarity(dragons)
                    self.dragons = sorted_dragons

                    options = []
                    seen = set()
                    for dragon_type, count in sorted_dragons[:25]:
                        if dragon_type in seen or dragon_type not in DRAGON_TYPES:
                            continue
                        seen.add(dragon_type)

                        dragon_data = DRAGON_TYPES[dragon_type]
                        rarity = get_rarity(dragon_type)
                        options.append(discord.SelectOption(
                            label=f"{dragon_data['name']} ({count}x)",
                            description=f"Rarity: {rarity.title()}",
                            emoji=dragon_data['emoji'],
                            value=str(dragon_type)
                        ))

                    select = discord.ui.Select(placeholder="Select first parent...", options=options, row=0)
                    select.callback = self.parent1_selected
                    self.add_item(select)

                async def parent1_selected(self, inter: discord.Interaction):
                    await inter.response.defer()

                    # Get selected values from inter.data (discord.py v2 style)
                    selected_values = inter.data.get("values", []) if inter.data else []

                    if not selected_values:
                        await inter.followup.send("❌ Please select a dragon from the dropdown!", ephemeral=True)
                        return

                    parent1 = selected_values[0]

                    if parent1 not in DRAGON_TYPES:
                        await inter.followup.send(f"❌ Invalid dragon: {parent1}", ephemeral=True)
                        return

                    # Parent 2 selection
                    class Parent2SelectView(discord.ui.View):
                        def __init__(self, dragons, p1):
                            super().__init__(timeout=60)
                            self.parent1 = p1
                            sorted_dragons = sort_dragons_by_rarity(dragons)
                            self.dragons = sorted_dragons

                            options = []
                            seen = set()
                            for dragon_type, count in sorted_dragons[:25]:
                                if dragon_type in seen or dragon_type == p1 or dragon_type not in DRAGON_TYPES:
                                    continue
                                seen.add(dragon_type)

                                dragon_data = DRAGON_TYPES[dragon_type]
                                rarity = get_rarity(dragon_type)
                                options.append(discord.SelectOption(
                                    label=f"{dragon_data['name']} ({count}x)",
                                    description=f"Rarity: {rarity.title()}",
                                    emoji=dragon_data['emoji'],
                                    value=str(dragon_type)
                                ))

                            select = discord.ui.Select(placeholder="Select second parent...", options=options, row=0)
                            select.callback = self.parent2_selected
                            self.add_item(select)

                        async def parent2_selected(self, inter2: discord.Interaction):
                            await inter2.response.defer()

                            # Get selected values from inter.data (discord.py v2 style)
                            selected_values = inter2.data.get("values", []) if inter2.data else []

                            if not selected_values:
                                await inter2.followup.send("❌ Please select a dragon from the dropdown!", ephemeral=True)
                                return

                            parent2 = selected_values[0]

                            if parent2 not in DRAGON_TYPES:
                                await inter2.followup.send(f"❌ Invalid dragon: {parent2}", ephemeral=True)
                                return

                            # Check queue limit based on breeding level
                            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c = conn.cursor()

                            # Get breeding level
                            breeding_info = get_breeding_level_info(interaction.guild_id, interaction.user.id)
                            max_slots = get_breeding_queue_slots(breeding_info['level'])

                            c.execute('SELECT COUNT(*) FROM breeding_queue WHERE guild_id = ? AND user_id = ? AND status = "pending"',
                                      (interaction.guild_id, interaction.user.id))
                            queue_count = c.fetchone()[0]

                            if queue_count >= max_slots:
                                conn.close()
                                await inter2.followup.send(
                                    f"❌ Your queue is full! Max slots: {max_slots}\n"
                                    f"Level 5+: +1 slot | Level 10+: +2 slots | Level 15+: +3 slots",
                                    ephemeral=False
                                )
                                return

                            # Get rarities for cost calculation
                            p1_rarity = get_rarity(self.parent1)
                            p2_rarity = get_rarity(parent2)

                            # Add to queue
                            current_time = int(time.time())

                            try:
                                c.execute('''INSERT INTO breeding_queue (guild_id, user_id, parent1_type, parent2_type, scheduled_for, created_at)
                                             VALUES (?, ?, ?, ?, ?, ?)''',
                                          (interaction.guild_id, interaction.user.id, self.parent1, parent2, current_time, current_time))
                                conn.commit()
                                conn.close()

                                p1_data = DRAGON_TYPES[self.parent1]
                                p2_data = DRAGON_TYPES[parent2]

                                # Calculate breeding cost based on rarity
                                breeding_cost = get_breeding_cost(p1_rarity, p2_rarity)

                                embed = discord.Embed(
                                    title="✅ Breeding Added to Queue!",
                                    description=f"{p1_data['emoji']} **{p1_data['name']}** + {p2_data['emoji']} **{p2_data['name']}**\n\n"
                                               f"⚡ Will start automatically when cooldown is ready!\n"
                                               f"💰 Required: {breeding_cost:,}🪙 + 1x DNA Sample\n\n"
                                               f"Queue: {queue_count + 1}/{max_slots}",
                                    color=0x9B59B6
                                )
                                embed.set_footer(text="Use /breedqueue action:view to see all scheduled breedings")
                                await inter2.followup.send(embed=embed, ephemeral=False)

                            except sqlite3.IntegrityError:
                                conn.close()
                                await inter2.followup.send(
                                    "❌ This breeding is already in your queue!",
                                    ephemeral=False
                                )

                    view = Parent2SelectView(self.dragons, parent1)
                    await inter.followup.send(content="Now select the second parent:", view=view)

            embed = discord.Embed(
                title="🧬 Schedule Breeding",
                description="Select your dragons to add to the breeding queue!\n\nBreedings will start automatically when your cooldown expires.",
                color=0x9B59B6
            )
            view = Parent1SelectView(user_dragons)
            await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(BreedingCog(bot))
