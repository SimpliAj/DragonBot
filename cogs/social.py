import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
import random
import time
import logging
from config import (
    LEVEL_NAMES, DRAGON_TYPES, DRAGON_RARITY_TIERS, ACHIEVEMENTS
)
from utils import format_time_remaining, safe_json_loads
from achievements import check_and_award_achievements
from database import update_balance
from utils import check_dragonpass_quests

logger = logging.getLogger(__name__)


class SocialCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="View server leaderboards")
    @app_commands.describe(category="Choose leaderboard category")
    @app_commands.choices(category=[
        app_commands.Choice(name="💰 Richest Players", value="coins"),
        app_commands.Choice(name="🐉 Most Dragons", value="dragons"),
        app_commands.Choice(name="🏆 Dragon Nest Level", value="level"),
        app_commands.Choice(name="✨ Alpha Dragons", value="alphas"),
        app_commands.Choice(name="💎 Most Ultra Dragons", value="ultra"),
        app_commands.Choice(name="🌟 Most Unique Dragons", value="unique")
    ])
    async def leaderboard(self, interaction: discord.Interaction, category: str = "coins"):
        """Shows server leaderboards"""
        guild_id = interaction.guild_id

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        if category == "coins":
            c.execute('''SELECT user_id, balance FROM users
                         WHERE guild_id = ?
                         ORDER BY balance DESC LIMIT 10''', (guild_id,))
            results = c.fetchall()
            title = "💰 Richest Players"
            description = ""
            medals = ["🥇", "🥈", "🥉"]

            for idx, (user_id, balance) in enumerate(results, 1):
                member = interaction.guild.get_member(user_id)
                if member:
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                    description += f"{medal} **{member.display_name}** - {int(balance):,} coins\n"

        elif category == "dragons":
            c.execute('''SELECT user_id, SUM(count) as total FROM user_dragons
                         WHERE guild_id = ?
                         GROUP BY user_id
                         ORDER BY total DESC LIMIT 10''', (guild_id,))
            results = c.fetchall()
            title = "🐉 Most Dragons Caught"
            description = ""
            medals = ["🥇", "🥈", "🥉"]

            for idx, (user_id, total) in enumerate(results, 1):
                member = interaction.guild.get_member(user_id)
                if member:
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                    description += f"{medal} **{member.display_name}** - {total:,} dragons\n"

        elif category == "level":
            c.execute('''SELECT user_id, level, xp FROM dragon_nest
                         WHERE guild_id = ?
                         ORDER BY level DESC, xp DESC LIMIT 10''', (guild_id,))
            results = c.fetchall()
            title = "🏆 Dragon Nest Masters"
            description = ""
            medals = ["🥇", "🥈", "🥉"]

            for idx, (user_id, level, xp) in enumerate(results, 1):
                member = interaction.guild.get_member(user_id)
                if member:
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                    level_name = LEVEL_NAMES.get(level, "Unknown")
                    description += f"{medal} **{member.display_name}** - Level {level} ({level_name}) - {xp:,} XP\n"

        elif category == "alphas":
            c.execute('''SELECT user_id, COUNT(*) as alpha_count FROM user_alphas
                         WHERE guild_id = ?
                         GROUP BY user_id
                         ORDER BY alpha_count DESC LIMIT 10''', (guild_id,))
            results = c.fetchall()
            title = "✨ Alpha Dragon Owners"
            description = ""
            medals = ["🥇", "🥈", "🥉"]

            for idx, (user_id, alpha_count) in enumerate(results, 1):
                member = interaction.guild.get_member(user_id)
                if member:
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                    description += f"{medal} **{member.display_name}** - {alpha_count} Alpha Dragon{'s' if alpha_count > 1 else ''}\n"

        elif category == "ultra":
            ultra_dragons = DRAGON_RARITY_TIERS.get('ultra', [])
            if ultra_dragons:
                c.execute('''SELECT user_id, SUM(count) as ultra_count FROM user_dragons
                             WHERE guild_id = ? AND dragon_type IN ({})
                             GROUP BY user_id
                             ORDER BY ultra_count DESC LIMIT 10'''.format(
                                 ','.join(['?' for _ in ultra_dragons])),
                          (guild_id, *ultra_dragons))
                results = c.fetchall()
            else:
                results = []

            title = "💎 Most Ultra Dragons"
            description = ""
            medals = ["🥇", "🥈", "🥉"]

            if not results:
                description = "No Ultra Dragons caught yet!"
            else:
                for idx, (user_id, ultra_count) in enumerate(results, 1):
                    member = interaction.guild.get_member(user_id)
                    if member:
                        medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                        description += f"{medal} **{member.display_name}** - {ultra_count:,} Ultra Dragon{'s' if ultra_count > 1 else ''}\n"

        elif category == "unique":
            c.execute('''SELECT user_id, COUNT(DISTINCT dragon_type) as unique_count FROM user_dragons
                         WHERE guild_id = ? AND count > 0
                         GROUP BY user_id
                         ORDER BY unique_count DESC LIMIT 10''', (guild_id,))
            results = c.fetchall()

            title = "🌟 Most Unique Dragons"
            description = ""
            medals = ["🥇", "🥈", "🥉"]

            for idx, (user_id, unique_count) in enumerate(results, 1):
                member = interaction.guild.get_member(user_id)
                if member:
                    medal = medals[idx-1] if idx <= 3 else f"#{idx}"
                    description += f"{medal} **{member.display_name}** - {unique_count}/{len(DRAGON_TYPES)} unique types\n"

        conn.close()

        if not description:
            description = "No data available yet!"

        embed = discord.Embed(
            title=f"🏆 {title}",
            description=description,
            color=0xFEE75C
        )
        embed.set_footer(text=f"🎮 Server: {interaction.guild.name} | 🔄 Updates in real-time")
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="bingo", description="Play dragon bingo! Catch dragons to mark your card")
    async def bingo(self, interaction: discord.Interaction):
        """Dragon bingo card system - 5x5 grid of dragon types"""
        await interaction.response.defer(ephemeral=False)

        guild_id = interaction.guild_id
        user_id = interaction.user.id

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        current_time = int(time.time())
        c.execute('''SELECT card_data, marked_positions, created_at, expires_at, completed
                     FROM bingo_cards WHERE guild_id = ? AND user_id = ?''',
                  (guild_id, user_id))
        existing_card = c.fetchone()

        if existing_card:
            card_data, marked_str, created_at, expires_at, completed = existing_card

            if current_time > expires_at:
                c.execute('DELETE FROM bingo_cards WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
                conn.commit()
                existing_card = None
            elif completed:
                conn.close()
                time_remaining = expires_at - current_time
                time_str = format_time_remaining(time_remaining)
                await interaction.followup.send(f"✅ You already completed this bingo card! It will expire in **{time_str}** and you can start a new one.", ephemeral=False)
                return

        if not existing_card:
            weighted_dragons = []
            for dragon, data in DRAGON_TYPES.items():
                rarity = next((r for r, dragons in DRAGON_RARITY_TIERS.items() if dragon in dragons), 'common')
                weight = {'common': 40, 'uncommon': 25, 'rare': 15, 'epic': 10, 'legendary': 6, 'mythic': 3, 'ultra': 1}
                weighted_dragons.extend([dragon] * weight.get(rarity, 10))

            card = []
            for i in range(25):
                if i == 12:
                    card.append('FREE')
                else:
                    card.append(random.choice(weighted_dragons))

            card_data = ','.join(card)
            marked_positions = '[]'
            created_at = current_time
            expires_at = current_time + (48 * 60 * 60)

            c.execute('''INSERT OR REPLACE INTO bingo_cards
                         (guild_id, user_id, card_data, marked_positions, created_at, expires_at)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (guild_id, user_id, card_data, marked_positions, created_at, expires_at))
            conn.commit()
            marked_str = marked_positions
        else:
            card_data, marked_str, created_at, expires_at, completed = existing_card

        card = card_data.split(',')
        marked = safe_json_loads(marked_str, [])

        if 12 not in marked:
            marked.append(12)
            c.execute('UPDATE bingo_cards SET marked_positions = ? WHERE guild_id = ? AND user_id = ?',
                      (str(marked), guild_id, user_id))
            conn.commit()

        def check_bingo(marked_positions, card_size=5):
            lines = []
            for row in range(card_size):
                lines.append([row * card_size + col for col in range(card_size)])
            for col in range(card_size):
                lines.append([row * card_size + col for row in range(card_size)])
            lines.append([i * card_size + i for i in range(card_size)])
            lines.append([i * card_size + (card_size - 1 - i) for i in range(card_size)])
            for line in lines:
                if all(pos in marked_positions for pos in line):
                    return True, line
            return False, []

        has_bingo, bingo_line = check_bingo(marked)

        completed_before = existing_card[4] if existing_card else False

        conn.close()

        await asyncio.to_thread(check_dragonpass_quests, guild_id, user_id, 'check_bingo', 1)

        card_display = ""
        for row in range(5):
            row_text = ""
            for col in range(5):
                pos = row * 5 + col
                dragon_type = card[pos]

                if dragon_type == 'FREE':
                    row_text += "⭐ "
                elif pos in marked:
                    row_text += "✅ "
                else:
                    row_text += "❌ "

                if dragon_type != 'FREE':
                    dragon_data = DRAGON_TYPES.get(dragon_type, {})
                    row_text += f"{dragon_data.get('name', dragon_type)[:5]:<5} "
                else:
                    row_text += "FREE  "

            card_display += row_text + "\n"

        marked_count = len(marked)
        expires_in = expires_at - current_time

        embed = discord.Embed(
            title="🎯 Dragon Bingo Card",
            description=f"**Catch dragons to mark your card!**\n\n"
                        f"```\n{card_display}```\n"
                        f"**Progress:** {marked_count}/25 marked\n"
                        f"⏰ Expires in: **{format_time_remaining(expires_in)}**\n\n"
                        f"💡 Get 5 in a row (horizontal, vertical, or diagonal) to win **500** 🪙!",
            color=discord.Color.blue()
        )

        await interaction.followup.send(embed=embed, ephemeral=False)

        if has_bingo and not completed_before:
            reward = 500
            try:
                await asyncio.to_thread(update_balance, guild_id, user_id, reward)
            except Exception as e:
                logger.error(f"Error updating balance for bingo: {e}")

            try:
                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()
                c.execute('UPDATE bingo_cards SET completed = 1 WHERE guild_id = ? AND user_id = ?',
                          (guild_id, user_id))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Error marking bingo as completed: {e}")

            try:
                await asyncio.to_thread(check_dragonpass_quests, guild_id, user_id, 'complete_bingo', 1)
            except Exception as e:
                logger.error(f"Error tracking bingo completion quest: {e}")

            bingo_embed = discord.Embed(
                title="🎉 BINGO! 🎉",
                description=f"**Congratulations {interaction.user.mention}!**\n\n"
                            f"You completed a line!\n"
                            f"🏆 Reward: **{reward}** 🪙",
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=bingo_embed)

    @app_commands.command(name="achievements", description="View your achievements and track your progress")
    @app_commands.describe(user="User to view achievements for")
    async def achievements(self, interaction: discord.Interaction, user: discord.User = None):
        """Display achievements for a user"""
        await interaction.response.defer(ephemeral=False)
        target_user = user or interaction.user
        guild_id = interaction.guild_id
        user_id = target_user.id

        if interaction.user.id == user_id:
            await check_and_award_achievements(guild_id, user_id, bot=self.bot, interaction=interaction)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        balance_result = c.fetchone()
        balance = balance_result[0] if balance_result else 0

        c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        total_caught_result = c.fetchone()
        total_caught = total_caught_result[0] if total_caught_result and total_caught_result[0] else 0

        c.execute('SELECT COUNT(*) FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0', (guild_id, user_id))
        unique_types = c.fetchone()[0]

        legendary_caught = 0
        mythic_caught = 0
        ultra_caught = 0

        for dragon_type in DRAGON_RARITY_TIERS['legendary']:
            c.execute('SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                      (guild_id, user_id, dragon_type))
            result = c.fetchone()
            if result and result[0] > 0:
                legendary_caught += 1
                break

        for dragon_type in DRAGON_RARITY_TIERS['mythic']:
            c.execute('SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                      (guild_id, user_id, dragon_type))
            result = c.fetchone()
            if result and result[0] > 0:
                mythic_caught += 1
                break

        for dragon_type in DRAGON_RARITY_TIERS['ultra']:
            c.execute('SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                      (guild_id, user_id, dragon_type))
            result = c.fetchone()
            if result and result[0] > 0:
                ultra_caught += 1
                break

        c.execute('''SELECT COUNT(*) FROM trade_offers
                     WHERE guild_id = ? AND (sender_id = ? OR receiver_id = ?) AND status = 'completed' ''',
                  (guild_id, user_id, user_id))
        trades_completed = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM bred_dragons WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        breeds_completed = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        alphas_crafted = c.fetchone()[0]

        unlocked_achievements = []
        locked_achievements = []

        achievement_progress = {
            'first_catch': total_caught,
            'catch_10': total_caught,
            'catch_50': total_caught,
            'catch_100': total_caught,
            'catch_500': total_caught,
            'first_legendary': legendary_caught,
            'first_mythic': mythic_caught,
            'first_ultra': ultra_caught,
            'collector_10': unique_types,
            'collector_all': unique_types,
            'rich_1000': balance,
            'rich_10000': balance,
            'trader': trades_completed,
            'breeder': breeds_completed,
            'alpha_crafter': alphas_crafted,
        }

        for ach_id, ach_data in ACHIEVEMENTS.items():
            progress = achievement_progress.get(ach_id, 0)
            requirement = ach_data['requirement']

            c.execute('SELECT unlocked FROM user_achievements WHERE guild_id = ? AND user_id = ? AND achievement_id = ?',
                      (guild_id, user_id, ach_id))
            unlocked_result = c.fetchone()
            is_unlocked = unlocked_result[0] if unlocked_result else False

            ach_display = {
                'id': ach_id,
                'name': ach_data['name'],
                'description': ach_data['description'],
                'icon': ach_data['icon'],
                'reward': ach_data['reward_coins'],
                'progress': progress,
                'requirement': requirement
            }

            if is_unlocked:
                unlocked_achievements.append(ach_display)
            else:
                locked_achievements.append(ach_display)

        conn.close()

        achievements_by_category = {}
        for ach_id, ach_data in ACHIEVEMENTS.items():
            category = ach_data.get('category', 'Other')
            if category not in achievements_by_category:
                achievements_by_category[category] = {'unlocked': [], 'locked': []}

        for ach in unlocked_achievements:
            ach_data = ACHIEVEMENTS.get(ach['id'], {})
            category = ach_data.get('category', 'Other')
            achievements_by_category[category]['unlocked'].append(ach)

        for ach in locked_achievements:
            ach_data = ACHIEVEMENTS.get(ach['id'], {})
            category = ach_data.get('category', 'Other')
            achievements_by_category[category]['locked'].append(ach)

        categories = sorted(achievements_by_category.keys())

        class AchievementsNavigationView(discord.ui.View):
            def __init__(self, categories_list, achievements_dict, target, guild, user):
                super().__init__(timeout=300)
                self.categories_list = categories_list
                self.achievements_dict = achievements_dict
                self.target_user = target
                self.guild_id = guild
                self.user_id = user
                self.current_category_index = 0

            def get_category_embed(self):
                category = self.categories_list[self.current_category_index]
                cat_data = self.achievements_dict[category]
                unlocked_in_cat = len(cat_data['unlocked'])
                total_in_cat = len(cat_data['unlocked']) + len(cat_data['locked'])

                embed = discord.Embed(
                    title=f"🏆 {self.target_user.display_name}'s Achievements",
                    description=f"{category}\n**{unlocked_in_cat}/{total_in_cat} unlocked**",
                    color=discord.Color.gold()
                )

                if cat_data['unlocked']:
                    unlocked_text = ""
                    for ach in cat_data['unlocked']:
                        unlocked_text += f"✅ {ach['icon']} **{ach['name']}**\n   _{ach['description']}_\n    💰 +{ach['reward']} coins\n\n"
                    embed.add_field(name="✅ Unlocked", value=unlocked_text, inline=False)

                if cat_data['locked']:
                    locked_text = ""
                    for ach in cat_data['locked']:
                        progress_pct = int((ach['progress'] / ach['requirement']) * 100) if ach['requirement'] > 0 else 0
                        progress_bar = "▓" * int(progress_pct / 5) + "░" * (20 - int(progress_pct / 5))
                        locked_text += f"🔒 {ach['icon']} **{ach['name']}**\n   _{ach['description']}_\n   {progress_bar} {ach['progress']}/{ach['requirement']} ({progress_pct}%)\n   💰 +{ach['reward']} coins\n\n"
                    embed.add_field(name="🔒 Locked", value=locked_text, inline=False)

                embed.set_footer(text=f"Category {self.current_category_index + 1}/{len(self.categories_list)}")
                return embed

            @discord.ui.button(label="◀", style=discord.ButtonStyle.blurple, emoji="⬅️")
            async def previous_category(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("This is not your achievements!", ephemeral=True)
                    return
                self.current_category_index = (self.current_category_index - 1) % len(self.categories_list)
                await interaction.response.edit_message(embed=self.get_category_embed())

            @discord.ui.button(label="▶", style=discord.ButtonStyle.blurple, emoji="➡️")
            async def next_category(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("This is not your achievements!", ephemeral=True)
                    return
                self.current_category_index = (self.current_category_index + 1) % len(self.categories_list)
                await interaction.response.edit_message(embed=self.get_category_embed())

        view = AchievementsNavigationView(categories, achievements_by_category, target_user, guild_id, interaction.user.id)
        embed = view.get_category_embed()
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialCog(bot))
