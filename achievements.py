# achievements.py
import sqlite3
import time
import logging
import discord

from config import ACHIEVEMENTS, DRAGON_RARITY_TIERS, EARNED_TROPHIES, TROPHY_EMOJIS, DRAGONPASS_QUEST_REWARDS

logger = logging.getLogger(__name__)


async def award_trophy(bot: discord.Client, guild_id: int, user_id: int, trophy_id: str):
    """Award an earned trophy if not already owned. Sends notification to spawn channel."""
    trophy = EARNED_TROPHIES.get(trophy_id)
    if not trophy:
        return

    try:
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute(
            'SELECT 1 FROM user_trophies WHERE guild_id = ? AND user_id = ? AND trophy_id = ?',
            (guild_id, user_id, trophy_id),
        )
        if c.fetchone():
            conn.close()
            return  # already earned

        c.execute(
            'INSERT INTO user_trophies (guild_id, user_id, trophy_id, earned_at) VALUES (?, ?, ?, ?)',
            (guild_id, user_id, trophy_id, int(time.time())),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f'award_trophy DB error: {e}')
        return

    if not bot:
        return

    try:
        conn2 = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c2 = conn2.cursor()
        c2.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
        row = c2.fetchone()
        conn2.close()
        if not row or not row[0]:
            return

        channel = bot.get_channel(row[0])
        if not channel:
            return

        member = channel.guild.get_member(user_id)
        display_name = member.display_name if member else f'<@{user_id}>'
        emoji = trophy['icon']

        embed = discord.Embed(
            title=f'{emoji} Trophy Unlocked!',
            description=f'**{display_name}** earned the **{trophy["name"]}** trophy!\n\n_{trophy["description"]}_',
            color=0xF1C40F,
        )
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f'award_trophy notification error: {e}')


async def send_quest_notification(bot: discord.Client, guild_id: int, user_id: int, quest_info: dict):
    """Send a quest completion notification to the guild's spawn channel."""
    if not bot or not quest_info or not quest_info.get('newly_completed'):
        return

    try:
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()
        c.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
        row = c.fetchone()
        conn.close()
        if not row or not row[0]:
            return

        channel = bot.get_channel(row[0])
        if not channel:
            return

        member = channel.guild.get_member(user_id)
        display_name = member.mention if member else f'<@{user_id}>'

        def _quest_label(q):
            qt = q.get('type', '')
            amt = q.get('amount', 1)
            rarity = q.get('rarity', 'common')
            labels = {
                'catch_dragons': f'Catch {amt} Dragons',
                'catch_rarity_or_higher': f'Catch {amt} {rarity.capitalize()}+ Dragons',
                'earn_coins': f'Earn {amt:,} Coins',
                'use_casino': f'Use Casino {amt}x',
                'open_packs': f'Open {amt} Packs',
                'use_coinflip': f'Coinflip {amt}x',
                'check_bingo': f'Check Bingo {amt}x',
                'complete_bingo': f'Complete Bingo {amt}x',
                'vote_topgg': f'Vote on Top.gg {amt}x',
                'attack_raidboss': f'Attack Raid Boss {amt}x',
                'catch_under_10s': f'Catch {amt} Dragon(s) within 10s',
                'catch_odd_second': f'Catch {amt} Dragon(s) on odd second',
                'catch_even_second': f'Catch {amt} Dragon(s) on even second',
                'complete_trade': f'Complete a Trade',
                'gift_dragon': f'Gift someone',
            }
            return labels.get(qt, qt)

        newly = quest_info['newly_completed']
        remaining = quest_info['remaining']
        level_delta = quest_info.get('level_delta', 0)
        pack_type = quest_info.get('pack_type')
        new_level = quest_info.get('new_level', 0)
        all_done = len(remaining) == 0

        if all_done:
            title = '🏆 All Quests Completed!'
            color = 0xF1C40F
        else:
            title = f'🎯 Quest{"s" if len(newly) > 1 else ""} Completed!'
            color = 0x57F287

        desc_lines = [f'{display_name} completed {len(newly)} Dragonpass quest{"s" if len(newly) > 1 else ""}!\n']
        for q in newly:
            reward_str = f' (+{q.get("reward", 0):,} 🪙)' if DRAGONPASS_QUEST_REWARDS else ''
            desc_lines.append(f'✅ {_quest_label(q)}{reward_str}')

        if remaining:
            desc_lines.append('\n📋 **Remaining Quests:**')
            for q in remaining:
                prog = q.get('progress', 0)
                tgt = q.get('amount', 1)
                desc_lines.append(f'• {_quest_label(q)} — {prog}/{tgt}')

        if level_delta > 0:
            desc_lines.append(f'\n🎁 **Level Up!** Dragonpass Level **{new_level}**')
            if new_level == 30:
                desc_lines.append(f'<:dragonscale:1446278170998341693> Reward: **2 Minutes Dragonscale**')
            elif pack_type:
                desc_lines.append(f'📦 Reward: **{pack_type.capitalize()} Pack**')
        elif all_done and not level_delta:
            desc_lines.append('\n⏳ Next level requires all quests again after refresh.')

        embed = discord.Embed(
            title=title,
            description='\n'.join(desc_lines),
            color=color,
        )
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f'send_quest_notification error: {e}')


async def check_and_award_achievements(
    guild_id: int,
    user_id: int,
    bot: discord.Client = None,
    interaction: discord.Interaction = None,
):
    """
    Check all achievements for a user, award any newly earned ones, and send notifications.

    Notification targets (both optional, both used when provided):
    - interaction: sends a combined followup embed listing all newly unlocked achievements
    - bot: sends one embed per achievement to the guild's spawn channel
    """
    try:
        conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
        c = conn.cursor()

        # --- Gather stats ---

        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        balance = row[0] if row else 0

        c.execute('SELECT SUM(count) FROM user_dragons WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        total_caught = row[0] if row and row[0] else 0

        c.execute('SELECT COUNT(*) FROM user_dragons WHERE guild_id = ? AND user_id = ? AND count > 0', (guild_id, user_id))
        unique_types = c.fetchone()[0]

        # Rarity flags (1 if user owns any dragon of that rarity)
        rarity_flags = {r: 0 for r in ('uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra')}
        for rarity_tier, dragons in DRAGON_RARITY_TIERS.items():
            if rarity_tier not in rarity_flags:
                continue
            for dragon_type in dragons:
                c.execute(
                    'SELECT count FROM user_dragons WHERE guild_id = ? AND user_id = ? AND dragon_type = ?',
                    (guild_id, user_id, dragon_type),
                )
                r = c.fetchone()
                if r and r[0] > 0:
                    rarity_flags[rarity_tier] = 1
                    break

        c.execute(
            '''SELECT COUNT(*) FROM trade_offers
               WHERE guild_id = ? AND (sender_id = ? OR receiver_id = ?) AND status = 'completed' ''',
            (guild_id, user_id, user_id),
        )
        trades_completed = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM bred_dragons WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        breeds_completed = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        alphas_crafted = c.fetchone()[0]

        c.execute('SELECT level, bounties_completed, upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        nest_level = row[0] if row else 0
        nest_bounties = row[1] if row else 0
        nest_upgrade = row[2] if row else 0

        # Breeding level
        c.execute('SELECT level FROM breeding_xp WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        breeding_level = row[0] if row else 1

        # Raid stats
        c.execute(
            'SELECT SUM(damage_dealt), SUM(attacks_made) FROM raid_damage WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        row = c.fetchone()
        raid_damage = row[0] if row and row[0] else 0
        raid_attacks = row[1] if row and row[1] else 0

        # Adventures completed
        c.execute(
            'SELECT COUNT(*) FROM user_adventures WHERE guild_id = ? AND user_id = ? AND claimed = 1',
            (guild_id, user_id),
        )
        adventures_done = c.fetchone()[0]

        # Dragonpass completions
        c.execute(
            'SELECT COUNT(*) FROM dragonpass_completions WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        dragonpass_completions = c.fetchone()[0]

        # Vote stats (user_id only, no guild_id column in vote_streaks)
        c.execute(
            'SELECT total_votes, current_streak FROM vote_streaks WHERE user_id = ?',
            (user_id,),
        )
        row = c.fetchone()
        total_votes = row[0] if row else 0
        vote_streak = row[1] if row else 0

        # --- Build progress map ---
        achievement_progress = {
            # Catching
            'catch_1': total_caught,
            'catch_10': total_caught,
            'catch_50': total_caught,
            'catch_100': total_caught,
            'catch_250': total_caught,
            'catch_500': total_caught,
            'catch_1000': total_caught,
            # Rarity
            'first_uncommon': rarity_flags['uncommon'],
            'first_rare': rarity_flags['rare'],
            'first_epic': rarity_flags['epic'],
            'first_legendary': rarity_flags['legendary'],
            'first_mythic': rarity_flags['mythic'],
            'first_ultra': rarity_flags['ultra'],
            # Collection
            'collector_5': unique_types,
            'collector_10': unique_types,
            'collector_15': unique_types,
            'collector_all': unique_types,
            # Wealth
            'rich_1k': balance,
            'rich_10k': balance,
            'rich_100k': balance,
            'rich_1m': balance,
            'rich_10m': balance,
            'rich_100m': balance,
            'rich_500m': balance,
            # Breeding (count)
            'breeder_1': breeds_completed,
            'breeder_5': breeds_completed,
            'breeder_10': breeds_completed,
            'breeder_50': breeds_completed,
            # Breeding level
            'breeding_level_5': breeding_level,
            'breeding_level_10': breeding_level,
            # Alpha
            'alpha_1': alphas_crafted,
            'alpha_3': alphas_crafted,
            'alpha_5': alphas_crafted,
            'alpha_10': alphas_crafted,
            # Trading
            'trader_1': trades_completed,
            'trader_5': trades_completed,
            'trader_10': trades_completed,
            # Dragon Nest
            'nest_level_5': nest_level,
            'nest_level_10': nest_level,
            'nest_upgrade_1': nest_upgrade,
            'nest_upgrade_3': nest_upgrade,
            'nest_upgrade_5': nest_upgrade,
            'nest_bounties_50': nest_bounties,
            'nest_bounties_100': nest_bounties,
            # Daily (placeholder — tracking not yet implemented)
            'daily_7': 0,
            'daily_14': 0,
            'daily_30': 0,
            'daily_100': 0,
            # Raids
            'raid_first': raid_damage,
            'raid_damage_10k': raid_damage,
            'raid_damage_100k': raid_damage,
            'raid_damage_1m': raid_damage,
            'raid_attacks_10': raid_attacks,
            'raid_attacks_50': raid_attacks,
            'raid_attacks_100': raid_attacks,
            # Adventures
            'adventure_first': adventures_done,
            'adventure_10': adventures_done,
            'adventure_50': adventures_done,
            'adventure_100': adventures_done,
            # Dragonpass
            'dragonpass_1': dragonpass_completions,
            'dragonpass_3': dragonpass_completions,
            'dragonpass_5': dragonpass_completions,
            'dragonpass_10': dragonpass_completions,
            # Voting
            'vote_first': total_votes,
            'vote_10': total_votes,
            'vote_50': total_votes,
            'vote_100': total_votes,
            'vote_streak_7': vote_streak,
            'vote_streak_30': vote_streak,
        }

        # --- Check and award ---
        newly_unlocked = []
        total_coins_awarded = 0

        for ach_id, ach_data in ACHIEVEMENTS.items():
            progress = achievement_progress.get(ach_id, 0)
            requirement = ach_data['requirement']

            c.execute(
                'SELECT unlocked FROM user_achievements WHERE guild_id = ? AND user_id = ? AND achievement_id = ?',
                (guild_id, user_id, ach_id),
            )
            row = c.fetchone()
            is_unlocked = bool(row[0]) if row else False

            if progress >= requirement and not is_unlocked:
                c.execute(
                    '''INSERT OR REPLACE INTO user_achievements
                       (guild_id, user_id, achievement_id, progress, unlocked, unlocked_at)
                       VALUES (?, ?, ?, ?, 1, ?)''',
                    (guild_id, user_id, ach_id, progress, int(time.time())),
                )
                c.execute(
                    'UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
                    (ach_data['reward_coins'], guild_id, user_id),
                )
                newly_unlocked.append({
                    'id': ach_id,
                    'name': ach_data['name'],
                    'description': ach_data['description'],
                    'icon': ach_data['icon'],
                    'reward': ach_data['reward_coins'],
                    'category': ach_data.get('category', 'Other'),
                })
                total_coins_awarded += ach_data['reward_coins']
            else:
                # Update progress only — use upsert that won't touch unlocked_at on existing rows
                c.execute(
                    '''INSERT INTO user_achievements (guild_id, user_id, achievement_id, progress, unlocked)
                       VALUES (?, ?, ?, ?, 0)
                       ON CONFLICT(guild_id, user_id, achievement_id)
                       DO UPDATE SET progress = excluded.progress WHERE unlocked = 0''',
                    (guild_id, user_id, ach_id, progress),
                )

        conn.commit()
        conn.close()

        if not newly_unlocked:
            return

        # --- Notify via interaction followup (existing behaviour) ---
        if interaction:
            try:
                embed = discord.Embed(
                    title="🎉 Achievement(s) Unlocked!",
                    description=f"You've earned {len(newly_unlocked)} new achievement(s)!",
                    color=discord.Color.gold(),
                )
                for ach in newly_unlocked:
                    embed.add_field(
                        name=f"{ach['icon']} {ach['name']}",
                        value=f"_{ach['description']}_\n+**{ach['reward']}** 🪙",
                        inline=False,
                    )
                embed.set_footer(text=f"Total earned: +{total_coins_awarded} 🪙")
                await interaction.followup.send(embed=embed, ephemeral=False)
            except Exception as e:
                logger.error(f"Achievement interaction notify error: {e}")

        # --- Notify via spawn channel (new behaviour) ---
        if bot:
            try:
                conn2 = sqlite3.connect('dragon_bot.db', timeout=120.0)
                c2 = conn2.cursor()
                c2.execute(
                    'SELECT spawn_channel FROM guild_settings WHERE guild_id = ?',
                    (guild_id,),
                )
                row = c2.fetchone()
                conn2.close()
                channel_id = row[0] if row else None

                if channel_id:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        guild = bot.get_guild(guild_id)
                        member = guild.get_member(user_id) if guild else None
                        username = member.display_name if member else str(user_id)

                        for ach in newly_unlocked:
                            notify_embed = discord.Embed(
                                title="🏆 Achievement Unlocked!",
                                color=discord.Color.gold(),
                            )
                            notify_embed.add_field(
                                name=f"{ach['icon']} {ach['name']}",
                                value=f"{ach['description']}\n💰 Reward: **+{ach['reward']:,}** coins",
                                inline=False,
                            )
                            notify_embed.set_footer(text=username)
                            await channel.send(embed=notify_embed)
            except Exception as e:
                logger.error(f"Achievement spawn-channel notify error: {e}")

    except Exception as e:
        logger.error(f"check_and_award_achievements error for user {user_id}: {e}")
