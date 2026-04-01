import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import ast
import time
from config import DRAGON_TYPES
from utils import generate_dragonpass_quests
from achievements import send_quest_notification


class DragonpassCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="dragonpass", description="View your Dragonpass progress")
    async def dragonpass(self, interaction: discord.Interaction):
        """Dragonpass (Battlepass) system"""
        await interaction.response.defer(ephemeral=False)

        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        c.execute('INSERT OR IGNORE INTO dragonpass (guild_id, user_id) VALUES (?, ?)',
                  (interaction.guild_id, interaction.user.id))
        c.execute('SELECT season, level, xp, quests_active, quest_refresh_time, claimed_levels FROM dragonpass WHERE guild_id = ? AND user_id = ?',
                  (interaction.guild_id, interaction.user.id))
        result = c.fetchone()

        current_time = int(time.time())

        season = result[0] if result else 1
        level = result[1] if result else 0
        xp = result[2] if result else 0
        quests_active = result[3] if result else None
        quest_refresh_time = result[4] if result and result[4] else current_time
        claimed_levels_str = result[5] if result and result[5] else '[]'

        if not quest_refresh_time or quest_refresh_time == 0:
            quest_refresh_time = current_time + 43200

        existing_quests = ast.literal_eval(quests_active) if quests_active else []
        completed_count = sum(1 for q in existing_quests if q.get('completed', False))
        claimed_levels = ast.literal_eval(claimed_levels_str) if claimed_levels_str else []

        has_raidboss_quest = any(q.get('type') == 'attack_raidboss' for q in existing_quests)
        has_vote_quest = any(q.get('type') == 'vote_topgg' for q in existing_quests)

        if not quests_active or len(existing_quests) < 4 or not has_vote_quest or current_time >= quest_refresh_time or has_raidboss_quest:
            selected_quests = generate_dragonpass_quests(current_time, interaction.guild_id, interaction.user.id)
            quests_json = str(selected_quests)
            quest_refresh_time = current_time + 43200
            c.execute('UPDATE dragonpass SET quests_active = ?, quest_refresh_time = ? WHERE guild_id = ? AND user_id = ?',
                      (quests_json, quest_refresh_time, interaction.guild_id, interaction.user.id))
            conn.commit()
            quests_active = quests_json

        conn.close()

        # Auto level-up if all 4 quests are complete but level hasn't incremented yet
        quests_check = ast.literal_eval(quests_active) if quests_active else []
        if len(quests_check) == 4 and all(q.get('completed') for q in quests_check) and level < 30:
            new_level = level + 1
            if new_level not in claimed_levels:
                claimed_levels.append(new_level)
            pack_type = None
            if new_level < 30:
                if new_level <= 10:
                    pack_type = 'stone' if new_level % 2 == 0 else 'wooden'
                elif new_level <= 20:
                    pack_type = 'silver' if new_level % 2 == 0 else 'bronze'
                else:
                    pack_type = 'diamond' if new_level % 2 == 0 else 'gold'
            conn2 = sqlite3.connect('dragon_bot.db', timeout=30.0)
            c2 = conn2.cursor()
            c2.execute('UPDATE dragonpass SET level = ?, claimed_levels = ? WHERE guild_id = ? AND user_id = ?',
                       (new_level, str(claimed_levels), interaction.guild_id, interaction.user.id))
            if pack_type:
                c2.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                              VALUES (?, ?, ?, 1) ON CONFLICT(guild_id, user_id, pack_type)
                              DO UPDATE SET count = count + 1''',
                           (interaction.guild_id, interaction.user.id, pack_type))
            elif new_level == 30:
                c2.execute('''INSERT INTO dragonscales (guild_id, user_id, minutes)
                              VALUES (?, ?, 2) ON CONFLICT(guild_id, user_id)
                              DO UPDATE SET minutes = minutes + 2''',
                           (interaction.guild_id, interaction.user.id))
            conn2.commit()
            conn2.close()
            level = new_level

            # Send level-up notification
            quest_info = {
                'newly_completed': quests_check,
                'remaining': [],
                'level_delta': 1,
                'pack_type': pack_type,
                'new_level': new_level,
                'coins': 0,
            }
            await send_quest_notification(self.bot, interaction.guild_id, interaction.user.id, quest_info)

        quests = ast.literal_eval(quests_active) if quests_active else []
        completed_count = sum(1 for q in quests if q.get('completed', False))

        progress_bar = ""
        for i in range(4):
            if i < completed_count:
                progress_bar += "🟩"
            else:
                progress_bar += "🟥"

        embed = discord.Embed(
            title=f"🎫 Dragonpass - Season {season}",
            description=f"### Level {level}/30\n"
                        f"{progress_bar} **{completed_count}/4 Quests**\n\n"
                        f"✨ Complete all 4 quests to level up!\n"
                        f"🎁 Every level = 1 Pack reward!",
            color=discord.Color.gold()
        )

        if level < 30:
            next_level = level + 1
            if next_level == 30:
                next_reward = "<:dragonscale:1446278170998341693> 2 Min Dragonscale"
            elif next_level <= 10:
                next_reward = "🗿 Stone Pack" if next_level % 2 == 0 else "📦 Wooden Pack"
            elif next_level <= 20:
                next_reward = "🥈 Silver Pack" if next_level % 2 == 0 else "🥉 Bronze Pack"
            else:
                next_reward = "💎 Diamond Pack" if next_level % 2 == 0 else "🥇 Gold Pack"
            embed.add_field(name=f"🎯 Level {next_level} Reward", value=next_reward, inline=False)
        else:
            embed.add_field(name="Status", value="✅ COMPLETED", inline=False)

        # Calculate refresh time once for all quests
        global_refresh_time = quest_refresh_time
        if quests:
            global_refresh_time = quests[0].get('refresh_time', quest_refresh_time)
        time_left = max(0, global_refresh_time - current_time)
        hours_left = time_left // 3600
        minutes_left = (time_left % 3600) // 60
        seconds_left = time_left % 60
        if hours_left > 0:
            refresh_str = f"{hours_left}h {minutes_left}m"
        elif minutes_left > 0:
            refresh_str = f"{minutes_left}m {seconds_left}s"
        else:
            refresh_str = f"{seconds_left}s"

        quest_count = 0
        for i, quest in enumerate(quests, 1):
            quest_type = quest['type']
            amount = quest['amount']
            reward = quest['reward']
            progress = quest.get('progress', 0)
            completed = quest.get('completed', False)

            if completed:
                status_icon = "✅"
                status_text = "**COMPLETE**"
            else:
                status_icon = "🔴"
                status_text = f"**{progress}/{amount}**"

            quest_text = ""
            if quest_type == 'vote_topgg':
                quest_text = f"{status_icon} [Vote on top.gg](https://top.gg/bot/1445803895862333592/vote) {status_text}"
            elif quest_type == 'catch_dragons':
                quest_text = f"{status_icon} Catch **{amount}** dragons {status_text}"
            elif quest_type == 'catch_rarity_or_higher':
                dragon_name = quest.get('dragon_name', 'Unknown')
                quest_text = f"{status_icon} Catch **{amount}** {dragon_name}+ Dragons {status_text}"
            elif quest_type == 'earn_coins':
                quest_text = f"{status_icon} Earn **{amount}** coins {status_text}"
            elif quest_type == 'use_casino':
                quest_text = f"{status_icon} Use casino **{amount}** times {status_text}"
            elif quest_type == 'open_packs':
                quest_text = f"{status_icon} Open **{amount}** packs {status_text}"
            elif quest_type == 'use_coinflip':
                quest_text = f"{status_icon} Play coinflip **{amount}** times {status_text}"
            elif quest_type == 'check_bingo':
                quest_text = f"{status_icon} Check your bingo card **{amount}** time {status_text}"
            elif quest_type == 'complete_bingo':
                quest_text = f"{status_icon} Complete a bingo card {status_text}"
            elif quest_type == 'catch_under_10s':
                quest_text = f"{status_icon} Catch **{amount}** dragon(s) within 10 seconds of spawn {status_text}"
            elif quest_type == 'catch_odd_second':
                quest_text = f"{status_icon} Catch **{amount}** dragon(s) on an odd second {status_text}"
            elif quest_type == 'catch_even_second':
                quest_text = f"{status_icon} Catch **{amount}** dragon(s) on an even second {status_text}"
            elif quest_type == 'complete_trade':
                quest_text = f"{status_icon} Complete a **/trade** {status_text}"
            elif quest_type == 'gift_dragon':
                quest_text = f"{status_icon} **/gift** someone {status_text}"
            elif quest_type.startswith('catch_'):
                dragon_key = quest_type.replace('catch_', '')
                dragon_name = DRAGON_TYPES.get(dragon_key, {}).get('name', dragon_key.capitalize())
                quest_text = f"{status_icon} Catch **{amount}** {dragon_name} Dragon {status_text}"

            if quest_text:
                quest_count += 1
                embed.add_field(name=f"📋 Quest {quest_count}", value=quest_text, inline=False)

        embed.add_field(name="🔄 Quest Refresh", value=f"Refreshes in {refresh_str}", inline=False)

        pack_emojis = {
            'wooden': {'closed': '<:woodenchest:1446170002708238476>', 'open': '✅'},
            'stone': {'closed': '<:stonechest:1446169958265389247>', 'open': '✅'},
            'bronze': {'closed': '<:bronzechest:1446169758599745586>', 'open': '✅'},
            'silver': {'closed': '<:silverchest:1446169917996011520>', 'open': '✅'},
            'gold': {'closed': '<:goldchest:1446169876438978681>', 'open': '✅'},
            'diamond': {'closed': '<:diamondchest:1446169830720929985>', 'open': '✅'}
        }

        reward_ranges = {'1-10': (1, 10), '11-20': (11, 20), '21-30': (21, 30)}

        for range_name, (start_lvl, end_lvl) in reward_ranges.items():
            reward_visual = ""
            for lvl in range(start_lvl, end_lvl + 1):
                if lvl == 30:
                    if lvl in claimed_levels:
                        reward_visual += '✅'
                    else:
                        reward_visual += '<:dragonscale:1446278170998341693>'
                else:
                    if lvl <= 10:
                        pack_type = 'stone' if lvl % 2 == 0 else 'wooden'
                    elif lvl <= 20:
                        pack_type = 'silver' if lvl % 2 == 0 else 'bronze'
                    else:
                        pack_type = 'diamond' if lvl % 2 == 0 else 'gold'

                    if lvl in claimed_levels:
                        reward_visual += pack_emojis[pack_type]['open']
                    else:
                        reward_visual += pack_emojis[pack_type]['closed']

            if reward_visual:
                embed.add_field(name=f"🏆 Levels {range_name}", value=reward_visual, inline=False)

        class DragonpassRefreshView(discord.ui.View):
            def __init__(self, user_id):
                super().__init__(timeout=300)
                self.user_id = user_id

            @discord.ui.button(label="Guide", style=discord.ButtonStyle.gray, emoji="📖")
            async def guide_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                guide_embed = discord.Embed(
                    title="📖 Quest Guide",
                    description="**What does the '+' mean in quests?**",
                    color=discord.Color.blue()
                )
                guide_embed.add_field(
                    name="🔹 Plus (+) Quest System",
                    value="When a quest says '*Catch 1 Friendly+ dragons*', you need to catch **Friendly dragons OR ANY RARER dragon**!",
                    inline=False
                )
                guide_embed.add_field(
                    name="✅ Examples that COUNT",
                    value="• Catch a **Friendly** dragon ✅\n"
                          "• Catch a **Mossy** (Rare) dragon ✅\n"
                          "• Catch a **Twilight** (Epic) dragon ✅\n"
                          "• Catch a **Legendary** dragon ✅",
                    inline=False
                )
                guide_embed.add_field(
                    name="❌ Examples that DON'T count",
                    value="• Catch a **Chubby** (Uncommon) dragon ❌\n"
                          "• Catch a **Common** dragon ❌",
                    inline=False
                )
                guide_embed.add_field(
                    name="📊 Rarity Levels (lowest to highest)",
                    value="**Common** < **Uncommon** < **Rare** < **Epic** < **Legendary** < **Mythic** < **Ultra**",
                    inline=False
                )

                _owner_id = self.user_id

                class DragonpassGuideView(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=300)

                    @discord.ui.button(label="Back", style=discord.ButtonStyle.blurple, emoji="◀️")
                    async def back_button(self, back_inter: discord.Interaction, btn: discord.ui.Button):
                        await back_inter.response.defer()
                        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                        c = conn.cursor()
                        c.execute('SELECT season, level, xp, quests_active, quest_refresh_time, claimed_levels FROM dragonpass WHERE guild_id = ? AND user_id = ?',
                                  (back_inter.guild_id, _owner_id))
                        result = c.fetchone()
                        conn.close()

                        season = result[0] if result else 1
                        level = result[1] if result else 0
                        quests_active = result[3] if result else None
                        quest_refresh_time = result[4] if result else int(time.time()) + 43200
                        claimed_levels_str = result[5] if result else '[]'
                        claimed_levels = ast.literal_eval(claimed_levels_str) if claimed_levels_str else []
                        current_time = int(time.time())

                        has_vote_quest = any(q.get('type') == 'vote_topgg' for q in (ast.literal_eval(quests_active) if quests_active else []))
                        existing_quests = ast.literal_eval(quests_active) if quests_active else []
                        has_raidboss_quest = any(q.get('type') == 'attack_raidboss' for q in existing_quests)

                        if not quests_active or len(existing_quests) < 4 or not has_vote_quest or current_time >= quest_refresh_time or has_raidboss_quest:
                            selected_quests = generate_dragonpass_quests(current_time, back_inter.guild_id, _owner_id)
                            quests_active = str(selected_quests)
                            conn2 = sqlite3.connect('dragon_bot.db', timeout=120.0)
                            c2 = conn2.cursor()
                            c2.execute('UPDATE dragonpass SET quests_active = ? WHERE guild_id = ? AND user_id = ?',
                                       (quests_active, back_inter.guild_id, _owner_id))
                            conn2.commit()
                            conn2.close()

                        quests = ast.literal_eval(quests_active) if quests_active else []
                        completed_count = sum(1 for q in quests if q.get('completed', False))
                        progress_bar = "".join("🟩" if i < completed_count else "🟥" for i in range(4))

                        back_embed = discord.Embed(
                            title=f"🎫 Dragonpass - Season {season}",
                            description=f"### Level {level}/30\n"
                                        f"{progress_bar} **{completed_count}/4 Quests**\n\n"
                                        f"✨ Complete all 4 quests to level up!\n"
                                        f"🎁 Every level = 1 Pack reward!",
                            color=discord.Color.gold()
                        )

                        if level < 30:
                            next_level = level + 1
                            if next_level == 30:
                                next_reward = "<:dragonscale:1446278170998341693> 2 Min Dragonscale"
                            elif next_level <= 10:
                                next_reward = "🗿 Stone Pack" if next_level % 2 == 0 else "📦 Wooden Pack"
                            elif next_level <= 20:
                                next_reward = "🥈 Silver Pack" if next_level % 2 == 0 else "🥉 Bronze Pack"
                            else:
                                next_reward = "💎 Diamond Pack" if next_level % 2 == 0 else "🥇 Gold Pack"
                            back_embed.add_field(name=f"🎯 Level {next_level} Reward", value=next_reward, inline=False)
                        else:
                            back_embed.add_field(name="Status", value="✅ COMPLETED", inline=False)

                        time_left = max(0, quest_refresh_time - current_time)
                        h = time_left // 3600
                        m = (time_left % 3600) // 60
                        s = time_left % 60
                        refresh_str = f"{h}h {m}m" if h > 0 else (f"{m}m {s}s" if m > 0 else f"{s}s")

                        quest_count = 0
                        for quest in quests:
                            qt = quest['type']
                            amt = quest['amount']
                            prog = quest.get('progress', 0)
                            done = quest.get('completed', False)
                            icon = "✅" if done else "🔴"
                            status = "**COMPLETE**" if done else f"**{prog}/{amt}**"
                            if qt == 'vote_topgg':
                                txt = f"{icon} [Vote on top.gg](https://top.gg/bot/1445803895862333592/vote) {status}"
                            elif qt == 'catch_dragons':
                                txt = f"{icon} Catch **{amt}** dragons {status}"
                            elif qt == 'catch_rarity_or_higher':
                                txt = f"{icon} Catch **{amt}** {quest.get('dragon_name', 'Unknown')}+ Dragons {status}"
                            elif qt == 'earn_coins':
                                txt = f"{icon} Earn **{amt}** coins {status}"
                            elif qt == 'use_casino':
                                txt = f"{icon} Use casino **{amt}** times {status}"
                            elif qt == 'open_packs':
                                txt = f"{icon} Open **{amt}** packs {status}"
                            elif qt == 'use_coinflip':
                                txt = f"{icon} Play coinflip **{amt}** times {status}"
                            elif qt == 'complete_bingo':
                                txt = f"{icon} Complete a bingo card {status}"
                            elif qt == 'catch_under_10s':
                                txt = f"{icon} Catch **{amt}** dragon(s) within 10 seconds of spawn {status}"
                            elif qt == 'catch_odd_second':
                                txt = f"{icon} Catch **{amt}** dragon(s) on an odd second {status}"
                            elif qt == 'catch_even_second':
                                txt = f"{icon} Catch **{amt}** dragon(s) on an even second {status}"
                            elif qt == 'complete_trade':
                                txt = f"{icon} Complete a **/trade** {status}"
                            elif qt == 'gift_dragon':
                                txt = f"{icon} **/gift** someone {status}"
                            else:
                                continue
                            quest_count += 1
                            back_embed.add_field(name=f"📋 Quest {quest_count}", value=txt, inline=False)

                        back_embed.add_field(name="🔄 Quest Refresh", value=f"Refreshes in {refresh_str}", inline=False)
                        await back_inter.edit_original_response(embed=back_embed, view=DragonpassRefreshView(_owner_id))

                await interaction.response.edit_message(embed=guide_embed, view=DragonpassGuideView())

            @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
            async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ Only the original user can refresh!", ephemeral=False)
                    return

                await interaction.response.defer()

                conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c = conn.cursor()

                c.execute('SELECT season, level, xp, quests_active, quest_refresh_time, claimed_levels FROM dragonpass WHERE guild_id = ? AND user_id = ?',
                          (interaction.guild_id, interaction.user.id))
                result = c.fetchone()

                current_time = int(time.time())

                season = result[0] if result else 1
                level = result[1] if result else 0
                xp = result[2] if result else 0
                quests_active = result[3] if result else None
                quest_refresh_time = result[4] if result and result[4] else current_time
                claimed_levels_str = result[5] if result and result[5] else '[]'

                existing_quests = ast.literal_eval(quests_active) if quests_active else []
                completed_count = sum(1 for q in existing_quests if q.get('completed', False))
                claimed_levels = ast.literal_eval(claimed_levels_str) if claimed_levels_str else []

                has_raidboss_quest = any(q.get('type') == 'attack_raidboss' for q in existing_quests)
                has_vote_quest = any(q.get('type') == 'vote_topgg' for q in existing_quests)

                if len(existing_quests) < 4 or not has_vote_quest or has_raidboss_quest:
                    selected_quests = generate_dragonpass_quests(current_time, interaction.guild_id, interaction.user.id)
                    quests_active = str(selected_quests)
                    c.execute('UPDATE dragonpass SET quests_active = ? WHERE guild_id = ? AND user_id = ?',
                              (quests_active, interaction.guild_id, interaction.user.id))
                    conn.commit()

                conn.close()

                quests = ast.literal_eval(quests_active) if quests_active else []
                completed_count = sum(1 for q in quests if q.get('completed', False))

                progress_bar = ""
                for i in range(3):
                    if i < completed_count:
                        progress_bar += "🟩"
                    else:
                        progress_bar += "🟥"

                updated_embed = discord.Embed(
                    title=f"🎫 Dragonpass - Season {season}",
                    description=f"### Level {level}/30\n"
                                f"{progress_bar} **{completed_count}/4 Quests**\n\n"
                                f"✨ Complete all 4 quests to level up!\n"
                                f"🎁 Every level = 1 Pack reward!",
                    color=discord.Color.gold()
                )

                if level < 30:
                    next_level = level + 1
                    if next_level <= 10:
                        next_reward = "🗿 Stone Pack" if next_level % 2 == 0 else "📦 Wooden Pack"
                    elif next_level <= 20:
                        next_reward = "🥈 Silver Pack" if next_level % 2 == 0 else "🥉 Bronze Pack"
                    else:
                        next_reward = "💎 Diamond Pack" if next_level % 2 == 0 else "🥇 Gold Pack"
                    updated_embed.add_field(name=f"🎯 Level {next_level} Reward", value=next_reward, inline=False)
                else:
                    updated_embed.add_field(name="Status", value="✅ COMPLETED", inline=False)

                # Calculate refresh time once
                global_refresh_time2 = quest_refresh_time
                if quests:
                    global_refresh_time2 = quests[0].get('refresh_time', quest_refresh_time)
                time_left2 = max(0, global_refresh_time2 - current_time)
                hours_left2 = time_left2 // 3600
                minutes_left2 = (time_left2 % 3600) // 60
                seconds_left2 = time_left2 % 60
                if hours_left2 > 0:
                    refresh_str2 = f"{hours_left2}h {minutes_left2}m"
                elif minutes_left2 > 0:
                    refresh_str2 = f"{minutes_left2}m {seconds_left2}s"
                else:
                    refresh_str2 = f"{seconds_left2}s"

                quest_count = 0
                for i, quest in enumerate(quests, 1):
                    quest_type = quest['type']
                    amount = quest['amount']
                    reward = quest['reward']
                    progress = quest.get('progress', 0)
                    completed = quest.get('completed', False)

                    if completed:
                        status_icon = "✅"
                        status_text = "**COMPLETE**"
                    else:
                        status_icon = "🔴"
                        status_text = f"**{progress}/{amount}**"

                    quest_text = ""
                    if quest_type == 'vote_topgg':
                        quest_text = f"{status_icon} [Vote on top.gg](https://top.gg/bot/1445803895862333592/vote) {status_text}"
                    elif quest_type == 'catch_dragons':
                        quest_text = f"{status_icon} Catch **{amount}** dragons {status_text}"
                    elif quest_type == 'catch_rarity_or_higher':
                        dragon_name = quest.get('dragon_name', 'Unknown')
                        quest_text = f"{status_icon} Catch **{amount}** {dragon_name}+ Dragons {status_text}"
                    elif quest_type == 'earn_coins':
                        quest_text = f"{status_icon} Earn **{amount}** coins {status_text}"
                    elif quest_type == 'use_casino':
                        quest_text = f"{status_icon} Use casino **{amount}** times {status_text}"
                    elif quest_type == 'open_packs':
                        quest_text = f"{status_icon} Open **{amount}** packs {status_text}"
                    elif quest_type == 'use_coinflip':
                        quest_text = f"{status_icon} Play coinflip **{amount}** times {status_text}"
                    elif quest_type == 'check_bingo':
                        quest_text = f"{status_icon} Check your bingo card **{amount}** time {status_text}"
                    elif quest_type == 'complete_bingo':
                        quest_text = f"{status_icon} Complete a bingo card {status_text}"
                    elif quest_type == 'catch_under_10s':
                        quest_text = f"{status_icon} Catch **{amount}** dragon(s) within 10 seconds of spawn {status_text}"
                    elif quest_type == 'catch_odd_second':
                        quest_text = f"{status_icon} Catch **{amount}** dragon(s) on an odd second {status_text}"
                    elif quest_type == 'catch_even_second':
                        quest_text = f"{status_icon} Catch **{amount}** dragon(s) on an even second {status_text}"
                    elif quest_type == 'complete_trade':
                        quest_text = f"{status_icon} Complete a **/trade** {status_text}"
                    elif quest_type == 'gift_dragon':
                        quest_text = f"{status_icon} **/gift** someone {status_text}"
                    elif quest_type.startswith('catch_'):
                        dragon_key = quest_type.replace('catch_', '')
                        dragon_name = DRAGON_TYPES.get(dragon_key, {}).get('name', dragon_key.capitalize())
                        quest_text = f"{status_icon} Catch **{amount}** {dragon_name} Dragon {status_text}"

                    if quest_text:
                        quest_count += 1
                        updated_embed.add_field(name=f"📋 Quest {quest_count}", value=quest_text, inline=False)

                updated_embed.add_field(name="🔄 Quest Refresh", value=f"Refreshes in {refresh_str2}", inline=False)

                pack_emojis = {
                    'wooden': {'closed': '<:woodenchest:1446170002708238476>', 'open': '✅'},
                    'stone': {'closed': '<:stonechest:1446169958265389247>', 'open': '✅'},
                    'bronze': {'closed': '<:bronzechest:1446169758599745586>', 'open': '✅'},
                    'silver': {'closed': '<:silverchest:1446169917996011520>', 'open': '✅'},
                    'gold': {'closed': '<:goldchest:1446169876438978681>', 'open': '✅'},
                    'diamond': {'closed': '<:diamondchest:1446169830720929985>', 'open': '✅'}
                }

                reward_ranges = {'1-10': (1, 10), '11-20': (11, 20), '21-30': (21, 30)}
                for range_name, (start_lvl, end_lvl) in reward_ranges.items():
                    reward_visual = ""
                    for lvl in range(start_lvl, end_lvl + 1):
                        if lvl == 30:
                            reward_visual += '<:dragonscale:1446278170998341693>'
                        else:
                            if lvl <= 10:
                                pack_type = 'stone' if lvl % 2 == 0 else 'wooden'
                            elif lvl <= 20:
                                pack_type = 'silver' if lvl % 2 == 0 else 'bronze'
                            else:
                                pack_type = 'diamond' if lvl % 2 == 0 else 'gold'

                            if lvl in claimed_levels:
                                reward_visual += pack_emojis[pack_type]['open']
                            else:
                                reward_visual += pack_emojis[pack_type]['closed']

                    if reward_visual:
                        updated_embed.add_field(name=f"🏆 Levels {range_name}", value=reward_visual, inline=False)

                await interaction.edit_original_response(embed=updated_embed, view=DragonpassRefreshView(interaction.user.id))

        view = DragonpassRefreshView(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(DragonpassCog(bot))
