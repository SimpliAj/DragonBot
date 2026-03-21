import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import json
import time
from datetime import datetime
from config import ADVENTURE_TYPES


class AdventuresCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def adventure_type_autocomplete(self, interaction: discord.Interaction, current: str):
        all_types = [
            app_commands.Choice(name="Exploration (1h cooldown, 90% success)",      value="exploration"),
            app_commands.Choice(name="Treasure Hunt (2h cooldown, 80% success)",    value="treasure_hunt"),
            app_commands.Choice(name="Dragon Raid (3h cooldown, 70% success)",      value="dragon_raid"),
            app_commands.Choice(name="Legendary Quest (6h cooldown, 60% success)",  value="legendary_quest"),
        ]
        try:
            conn = sqlite3.connect('dragon_bot.db', timeout=10.0)
            c = conn.cursor()
            c.execute('''SELECT adventure_type FROM user_adventures
                         WHERE guild_id = ? AND user_id = ? AND status = 'active' AND returns_at > ?''',
                      (interaction.guild_id, interaction.user.id, int(time.time())))
            active_types = {row[0] for row in c.fetchall()}
            conn.close()
        except Exception:
            active_types = set()
        return [
            ch for ch in all_types
            if ch.value not in active_types and current.lower() in ch.name.lower()
        ]

    @app_commands.command(name="adventure", description="Send dragons on an adventure for rewards!")
    @app_commands.describe(
        adventure_type="Type of adventure (no dragons needed, only cooldown cost)"
    )
    @app_commands.autocomplete(adventure_type=adventure_type_autocomplete)
    async def adventure(self, interaction: discord.Interaction, adventure_type: str):
        """Start an adventure to earn coins and find dragons (risk/reward based on difficulty)"""
        await interaction.response.defer(ephemeral=False)

        adventure_type = adventure_type.lower()

        if adventure_type not in ADVENTURE_TYPES:
            await interaction.followup.send(
                f"❌ Invalid adventure type! Available: {', '.join(ADVENTURE_TYPES.keys())}",
                ephemeral=False
            )
            return

        adventure_config = ADVENTURE_TYPES[adventure_type]

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT COUNT(*) FROM user_adventures WHERE guild_id = ? AND user_id = ? AND adventure_type = ? AND status = "active"',
                  (interaction.guild_id, interaction.user.id, adventure_type))
        active_of_type = c.fetchone()[0]

        if active_of_type >= 1:
            await interaction.followup.send(
                f"❌ You already have an active **{adventure_type.replace('_', ' ').title()}**! Wait for it to complete.",
                ephemeral=False
            )
            conn.close()
            return

        current_time = int(time.time())
        c.execute('SELECT cooldown_until FROM adventure_cooldowns WHERE guild_id = ? AND user_id = ? AND adventure_type = ?',
                  (interaction.guild_id, interaction.user.id, adventure_type))
        cooldown_row = c.fetchone()

        if cooldown_row and cooldown_row[0] > current_time:
            remaining = cooldown_row[0] - current_time
            remaining_hours = remaining // 3600
            remaining_mins = (remaining % 3600) // 60
            await interaction.followup.send(
                f"⏰ You're on cooldown for {remaining_hours}h {remaining_mins}m before you can start another **{adventure_type.replace('_', ' ').title()}**!",
                ephemeral=False
            )
            conn.close()
            return

        current_time = int(time.time())
        duration = adventure_config['duration']
        returns_at = current_time + duration
        dragons_json = json.dumps([])

        c.execute('''SELECT MAX(user_adventure_number) FROM user_adventures
                     WHERE guild_id = ? AND user_id = ?''',
                  (interaction.guild_id, interaction.user.id))
        max_num = c.fetchone()[0]
        user_adventure_number = (max_num or 0) + 1

        c.execute('''INSERT INTO user_adventures
                     (guild_id, user_id, user_adventure_number, dragons_sent, adventure_type, difficulty, started_at, returns_at, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')''',
                  (interaction.guild_id, interaction.user.id, user_adventure_number, dragons_json, adventure_type, 'normal', current_time, returns_at))

        adventure_id = c.lastrowid

        # Check for consumable items
        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (interaction.guild_id, interaction.user.id, 'fast_travel_scroll'))
        fts_row = c.fetchone()
        has_fast_travel = fts_row and fts_row[0] > 0

        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (interaction.guild_id, interaction.user.id, 'double_loot_bag'))
        dlb_row = c.fetchone()
        has_double_loot = dlb_row and dlb_row[0] > 0

        conn.commit()
        conn.close()

        duration_hours = duration // 3600
        duration_mins = (duration % 3600) // 60

        if duration_hours > 0:
            duration_str = f"{duration_hours}h {duration_mins}m"
        else:
            duration_str = f"{duration_mins}m"

        success_rate = int(adventure_config['success_rate'] * 100)

        embed = discord.Embed(
            title=f"{adventure_config['emoji']} Adventure Started!",
            description=f"**Type:** {adventure_type.replace('_', ' ').title()}\n"
                       f"**Cooldown:** {duration_str}\n"
                       f"**Success Rate:** {success_rate}%\n\n"
                       f"Your adventure is underway!",
            color=discord.Color.purple()
        )

        embed.add_field(
            name="Potential Rewards (on success)",
            value=f"💰 {adventure_config['rewards']['coins'][0]:,} - {adventure_config['rewards']['coins'][1]:,} coins\n"
                 f"🐉 {int(adventure_config['rewards']['dragon_chance'] * 100)}% chance to find a dragon\n"
                 f"📦 {int(adventure_config['rewards']['item_chance'] * 100)}% chance to find an item",
            inline=False
        )

        return_timestamp = int(time.time()) + duration
        return_datetime = datetime.fromtimestamp(return_timestamp)
        embed.add_field(
            name="⏰ Returns at",
            value=discord.utils.format_dt(return_datetime, style='t'),
            inline=False
        )

        # Show item-use buttons if user has relevant consumables
        if has_fast_travel or has_double_loot:
            guild_id = interaction.guild_id
            user_id = interaction.user.id

            class AdventureItemsView(discord.ui.View):
                def __init__(self_view):
                    super().__init__(timeout=60)
                    if has_fast_travel:
                        btn = discord.ui.Button(
                            label="Use Fast Travel Scroll (halve time)",
                            style=discord.ButtonStyle.primary,
                            emoji="📜"
                        )
                        btn.callback = self_view.use_fast_travel
                        self_view.add_item(btn)
                    if has_double_loot:
                        btn2 = discord.ui.Button(
                            label="Use Double Loot Bag (2x items)",
                            style=discord.ButtonStyle.success,
                            emoji="🎒"
                        )
                        btn2.callback = self_view.use_double_loot
                        self_view.add_item(btn2)

                async def use_fast_travel(self_view, btn_interaction: discord.Interaction):
                    if btn_interaction.user.id != user_id:
                        await btn_interaction.response.send_message("❌ This is not your adventure!", ephemeral=False)
                        return
                    conn2 = sqlite3.connect('dragon_bot.db', timeout=60.0)
                    c2 = conn2.cursor()
                    c2.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                               (guild_id, user_id, 'fast_travel_scroll'))
                    row = c2.fetchone()
                    if not row or row[0] <= 0:
                        await btn_interaction.response.send_message("❌ No Fast Travel Scrolls left!", ephemeral=False)
                        conn2.close()
                        return
                    new_returns_at = current_time + duration // 2
                    c2.execute('UPDATE user_adventures SET returns_at = ? WHERE adventure_id = ?',
                               (new_returns_at, adventure_id))
                    c2.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                               (guild_id, user_id, 'fast_travel_scroll'))
                    conn2.commit()
                    conn2.close()

                    halved_secs = duration // 2
                    halved_h = halved_secs // 3600
                    halved_m = (halved_secs % 3600) // 60
                    halved_str = f"{halved_h}h {halved_m}m" if halved_h > 0 else f"{halved_m}m"

                    await btn_interaction.response.send_message(
                        f"📜 **Fast Travel Scroll used!** Adventure duration halved to **{halved_str}**.",
                        ephemeral=False
                    )
                    for child in self_view.children:
                        if hasattr(child, 'emoji') and child.emoji and str(child.emoji) == "📜":
                            child.disabled = True
                    try:
                        await btn_interaction.message.edit(view=self_view)
                    except Exception:
                        pass

                async def use_double_loot(self_view, btn_interaction: discord.Interaction):
                    if btn_interaction.user.id != user_id:
                        await btn_interaction.response.send_message("❌ This is not your adventure!", ephemeral=False)
                        return
                    conn2 = sqlite3.connect('dragon_bot.db', timeout=60.0)
                    c2 = conn2.cursor()
                    c2.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                               (guild_id, user_id, 'double_loot_bag'))
                    row = c2.fetchone()
                    if not row or row[0] <= 0:
                        await btn_interaction.response.send_message("❌ No Double Loot Bags left!", ephemeral=False)
                        conn2.close()
                        return
                    c2.execute('UPDATE user_adventures SET double_loot = 1 WHERE adventure_id = ?', (adventure_id,))
                    c2.execute('UPDATE user_items SET count = count - 1 WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                               (guild_id, user_id, 'double_loot_bag'))
                    conn2.commit()
                    conn2.close()

                    await btn_interaction.response.send_message(
                        "🎒 **Double Loot Bag activated!** Item drops from this adventure are doubled.",
                        ephemeral=False
                    )
                    for child in self_view.children:
                        if hasattr(child, 'emoji') and child.emoji and str(child.emoji) == "🎒":
                            child.disabled = True
                    try:
                        await btn_interaction.message.edit(view=self_view)
                    except Exception:
                        pass

            embed.set_footer(text="You have items to use! Buttons expire in 60s.")
            await interaction.followup.send(embed=embed, view=AdventureItemsView(), ephemeral=False)
        else:
            await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="adventures", description="View your active adventures and rewards")
    async def adventures(self, interaction: discord.Interaction):
        """View your active adventures with option to see history"""
        await interaction.response.defer(ephemeral=False)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('''SELECT user_adventure_number, adventure_type, dragons_sent, returns_at, status, rewards_coins, rewards_dragons, claimed
                     FROM user_adventures
                     WHERE guild_id = ? AND user_id = ?
                     ORDER BY adventure_id DESC''',
                  (interaction.guild_id, interaction.user.id))
        adventures_list = c.fetchall()
        conn.close()

        if not adventures_list:
            embed = discord.Embed(
                title="🗺️ Adventures",
                description="You haven't sent any dragons on adventures yet!\n\nUse `/adventure` to get started.",
                color=discord.Color.purple()
            )
            await interaction.followup.send(embed=embed, ephemeral=False)
            return

        current_time = int(time.time())
        active_adventures = []
        completed_adventures = []

        for adv in adventures_list:
            if adv[3] > current_time:
                active_adventures.append(adv)
            else:
                completed_adventures.append(adv)

        if active_adventures:
            embed = discord.Embed(
                title="🗺️ Your Active Adventures",
                color=discord.Color.green()
            )

            for adventure_num, adv_type, dragons_json, returns_at, status, coins, dragons_json_reward, claimed in active_adventures:
                dragons = json.loads(dragons_json)
                dragon_count = sum(count for _, count in dragons)

                adventure_config = ADVENTURE_TYPES.get(adv_type, {})
                emoji = adventure_config.get('emoji', '🗺️')

                time_left = returns_at - current_time
                hours = time_left // 3600
                minutes = (time_left % 3600) // 60

                if hours > 0:
                    time_str = f"⏰ {hours}h {minutes}m remaining"
                else:
                    time_str = f"⏰ {minutes}m remaining"

                field_value = f"{emoji} **{adv_type.replace('_', ' ').title()}**\n"
                field_value += f"Dragons: {dragon_count}\n"
                field_value += f"🟢 Active - {time_str}"

                embed.add_field(
                    name=f"Adventure #{adventure_num}",
                    value=field_value,
                    inline=False
                )

            embed.set_footer(text="Click the button below to view completed adventures")
        else:
            embed = discord.Embed(
                title="🗺️ Your Adventures",
                description="No active adventures right now!\n\nUse `/adventure` to start a new one.",
                color=discord.Color.purple()
            )
            embed.set_footer(text="Click the button below to view your adventure history")

        class HistoryButton(discord.ui.View):
            def __init__(self):
                super().__init__()

            @discord.ui.button(label="📜 History", style=discord.ButtonStyle.secondary)
            async def history_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                await show_adventure_history(button_interaction, completed_adventures, current_time)

        view = HistoryButton()
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)


async def show_adventure_history(interaction: discord.Interaction, completed_adventures, current_time):
    """Display completed adventure history"""
    await interaction.response.defer(ephemeral=False)

    if not completed_adventures:
        embed = discord.Embed(
            title="📜 Adventure History",
            description="No completed adventures yet!",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=False)
        return

    page_size = 5
    pages = []

    for i in range(0, len(completed_adventures), page_size):
        page_advs = completed_adventures[i:i+page_size]
        embed = discord.Embed(
            title="📜 Adventure History",
            color=discord.Color.blue()
        )

        for adventure_num, adv_type, dragons_json, returns_at, status, coins, dragons_json_reward, claimed in page_advs:
            dragons = json.loads(dragons_json)
            dragon_count = sum(count for _, count in dragons)

            adventure_config = ADVENTURE_TYPES.get(adv_type, {})
            emoji = adventure_config.get('emoji', '🗺️')

            if claimed:
                status_text = "✅ Claimed"
            else:
                status_text = "✅ Ready to Claim"

            field_value = f"{emoji} **{adv_type.replace('_', ' ').title()}**\n"
            field_value += f"Dragons: {dragon_count}\n"
            field_value += status_text
            field_value += f"\n💰 {coins:,} coins | 🐉 {len(json.loads(dragons_json_reward)) if dragons_json_reward != '[]' else 0} dragons"

            embed.add_field(
                name=f"Adventure #{adventure_num}",
                value=field_value,
                inline=False
            )

        total_pages = (len(completed_adventures) + page_size - 1) // page_size
        embed.set_footer(text=f"Page {(i // page_size) + 1} of {total_pages}")
        pages.append(embed)

    if len(pages) == 1:
        await interaction.followup.send(embed=pages[0], ephemeral=False)
    else:
        class HistoryPaginator(discord.ui.View):
            def __init__(self, pages):
                super().__init__()
                self.pages = pages
                self.current_page = 0

            @discord.ui.button(label="◀️", style=discord.ButtonStyle.gray)
            async def prev_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page > 0:
                    self.current_page -= 1
                    await button_interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
                else:
                    await button_interaction.response.defer()

            @discord.ui.button(label="▶️", style=discord.ButtonStyle.gray)
            async def next_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page < len(self.pages) - 1:
                    self.current_page += 1
                    await button_interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
                else:
                    await button_interaction.response.defer()

        view = HistoryPaginator(pages)
        await interaction.followup.send(embed=pages[0], view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdventuresCog(bot))
