"""
utils.py - Utility and helper functions for DragonBot.
Extracted verbatim from bot.py (lines 1958-2799).
"""

import sqlite3
import time
import json
import asyncio
import random
import math
import logging

from config import (
    DB_PATH, DB_TIMEOUT_SHORT, DB_TIMEOUT_LONG,
    DRAGON_TYPES, DRAGON_RARITY_TIERS, BREEDING_LEVEL_THRESHOLDS, BREEDING_XP_COSTS,
    PERKS_POOL, ENABLE_TOPGG_VOTE_QUEST,
)
from state import (
    spawn_channels, active_spawns, active_dragonscales, active_luckycharms,
    active_usable_items, raid_boss_active,
)
from database import (
    get_db_connection, safe_db_operation, validate_dragon_count, validate_dragon_type,
    safe_json_loads, get_user, get_quest_lock,
)

logger = logging.getLogger(__name__)


# ==================== TIME FORMATTING ====================
def format_time_remaining(seconds: int) -> str:
    """Format time remaining as Xd Xh Xm or Xh Xm Xs based on duration."""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


# ==================== DRAGON RARITY HELPERS ====================
def get_dragon_rarity(dragon_type: str) -> str:
    """Get the rarity tier of a dragon."""
    for rarity, dragons in DRAGON_RARITY_TIERS.items():
        if dragon_type in dragons:
            return rarity
    return 'common'


def sort_dragons_by_rarity(dragons: list) -> list:
    """Sort dragon list by rarity tier order."""
    rarity_order = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'ultra']

    def rarity_sort_key(item):
        dragon_type, count = item
        rarity = get_dragon_rarity(dragon_type)
        rarity_index = rarity_order.index(rarity) if rarity in rarity_order else 0
        return (rarity_index, dragon_type)

    return sorted(dragons, key=rarity_sort_key)


# ==================== DRAGON MANAGEMENT ====================
async def add_dragons(guild_id: int, user_id: int, dragon_type: str, count: int):
    """Add dragons to user inventory with retry logic."""
    if not validate_dragon_count(count) or not validate_dragon_type(dragon_type):
        logger.error(f"Invalid input: count={count}, dragon_type={dragon_type}")
        return False

    lock = get_quest_lock(guild_id, user_id)

    def _add_dragons_sync():
        with lock:
            conn = get_db_connection(DB_TIMEOUT_SHORT)
            try:
                c = conn.cursor()
                current_time = int(time.time())
                c.execute('''INSERT INTO user_dragons (guild_id, user_id, dragon_type, count, last_caught_at)
                             VALUES (?, ?, ?, ?, ?)
                             ON CONFLICT(guild_id, user_id, dragon_type)
                             DO UPDATE SET count = count + ?, last_caught_at = ?''',
                          (guild_id, user_id, dragon_type, count, current_time, count, current_time))
                conn.commit()
                return True
            finally:
                conn.close()

    try:
        return await asyncio.to_thread(safe_db_operation, _add_dragons_sync)
    except Exception as e:
        logger.error(f"Failed to add dragons for {user_id}: {str(e)[:100]}")
        return False


def update_bingo_on_catch(guild_id: int, user_id: int, dragon_type: str):
    """Update bingo card when a dragon is caught."""
    if not validate_dragon_type(dragon_type):
        return

    lock = get_quest_lock(guild_id, user_id)

    def _update_bingo():
        with lock:
            conn = get_db_connection(DB_TIMEOUT_SHORT)
            try:
                c = conn.cursor()
                current_time = int(time.time())
                c.execute('''SELECT card_data, marked_positions, created_at, expires_at, completed
                             FROM bingo_cards WHERE guild_id = ? AND user_id = ?''',
                          (guild_id, user_id))
                card_data = c.fetchone()

                if not card_data:
                    return

                card_str, marked_str, created_at, expires_at, completed = card_data

                if current_time > expires_at or completed:
                    return

                card = card_str.split(',')
                marked = safe_json_loads(marked_str, [])

                card_updated = False
                for i, card_dragon in enumerate(card):
                    if card_dragon == dragon_type and i not in marked:
                        marked.append(i)
                        card_updated = True

                if card_updated:
                    c.execute('UPDATE bingo_cards SET marked_positions = ? WHERE guild_id = ? AND user_id = ?',
                              (json.dumps(marked), guild_id, user_id))
                    conn.commit()
            finally:
                conn.close()

    try:
        safe_db_operation(_update_bingo)
    except Exception as e:
        logger.error(f"Bingo update failed: {str(e)[:100]}")


# ==================== BREEDING XP SYSTEM ====================
def get_breeding_level_info(guild_id: int, user_id: int):
    """Get breeding level and XP info for user."""
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    c = conn.cursor()
    c.execute('SELECT level, xp FROM breeding_xp WHERE guild_id = ? AND user_id = ?',
              (guild_id, user_id))
    result = c.fetchone()
    conn.close()

    if result:
        level, xp = result
    else:
        level, xp = 1, 0
    return {'level': level, 'xp': xp}


def add_breeding_xp(guild_id: int, user_id: int, xp_amount: int, cursor=None, conn=None):
    """Add XP to user's breeding level and handle level-ups."""
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH, timeout=60.0)
        c = conn.cursor()
    else:
        c = cursor

    c.execute('SELECT level, xp FROM breeding_xp WHERE guild_id = ? AND user_id = ?',
              (guild_id, user_id))
    result = c.fetchone()

    if result:
        current_level, current_xp = result
    else:
        current_level, current_xp = 1, 0
        c.execute('INSERT INTO breeding_xp (guild_id, user_id, level, xp) VALUES (?, ?, 1, 0)',
                  (guild_id, user_id))

    new_xp = current_xp + xp_amount
    new_level = current_level

    while True:
        next_level = new_level + 1
        if next_level in BREEDING_LEVEL_THRESHOLDS:
            threshold = BREEDING_LEVEL_THRESHOLDS[next_level]
            if new_xp >= threshold:
                new_level = next_level
                continue
        break

    c.execute('UPDATE breeding_xp SET level = ?, xp = ? WHERE guild_id = ? AND user_id = ?',
              (new_level, new_xp, guild_id, user_id))

    if own_conn:
        conn.commit()
        conn.close()

    level_up = new_level > current_level
    return {'old_level': current_level, 'new_level': new_level, 'xp': new_xp, 'level_up': level_up}


def get_breeding_queue_slots(breeding_level: int) -> int:
    """Get max queue slots based on breeding level."""
    if breeding_level >= 15:
        return 4
    elif breeding_level >= 10:
        return 3
    elif breeding_level >= 5:
        return 2
    else:
        return 1


def get_breeding_cost(parent1_rarity: str, parent2_rarity: str) -> int:
    """Calculate breeding cost based on parent rarities."""
    rarities = [parent1_rarity, parent2_rarity]
    max_rarity = max(rarities, key=lambda r: list(BREEDING_XP_COSTS.keys()).index(r) if r in BREEDING_XP_COSTS else 0)
    return BREEDING_XP_COSTS.get(max_rarity, BREEDING_XP_COSTS['common'])


# ==================== DRAGONPASS QUEST SYSTEM ====================
def generate_dragonpass_quests(current_time: int, guild_id: int = None, user_id: int = None):
    """Generate 3 random quests from the quest pool."""
    has_bingo_cooldown = False
    if guild_id and user_id:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=120.0)
            c = conn.cursor()
            c.execute('SELECT cooldown_expires FROM bingo WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
            bingo_result = c.fetchone()
            conn.close()
            if bingo_result and bingo_result[0] and bingo_result[0] > current_time:
                has_bingo_cooldown = True
        except Exception:
            pass

    dragon_rarity_map = {}
    rarity_levels = {'common': 0, 'uncommon': 1, 'rare': 2, 'epic': 3, 'legendary': 4, 'mythic': 5, 'ultra': 6}
    for rarity, dragons in DRAGON_RARITY_TIERS.items():
        for dragon_key in dragons:
            dragon_rarity_map[dragon_key] = rarity_levels.get(rarity, 0)

    dragon_keys_list = list(DRAGON_TYPES.keys())
    rare_dragons = [k for k in dragon_keys_list if dragon_rarity_map.get(k, 0) == 2]
    epic_dragons = [k for k in dragon_keys_list if dragon_rarity_map.get(k, 0) == 3]
    legendary_dragons = [k for k in dragon_keys_list if dragon_rarity_map.get(k, 0) == 4]

    quest_types = [
        {'type': 'catch_dragons', 'amount': 2, 'reward': 50},
        {'type': 'catch_dragons', 'amount': 3, 'reward': 75},
        {'type': 'catch_dragons', 'amount': 5, 'reward': 100},
        {'type': 'catch_dragons', 'amount': 7, 'reward': 125},
        {'type': 'catch_dragons', 'amount': 10, 'reward': 150},
    ]

    if rare_dragons:
        base_rare = random.choice(rare_dragons)
        base_rare_name = DRAGON_TYPES[base_rare]['name']
        quest_types.extend([
            {'type': 'catch_rarity_or_higher', 'dragon_name': base_rare_name, 'rarity': 'rare', 'amount': 1, 'reward': 100},
            {'type': 'catch_rarity_or_higher', 'dragon_name': base_rare_name, 'rarity': 'rare', 'amount': 2, 'reward': 150},
        ])

    if epic_dragons:
        base_epic = random.choice(epic_dragons)
        base_epic_name = DRAGON_TYPES[base_epic]['name']
        quest_types.extend([
            {'type': 'catch_rarity_or_higher', 'dragon_name': base_epic_name, 'rarity': 'epic', 'amount': 1, 'reward': 150},
            {'type': 'catch_rarity_or_higher', 'dragon_name': base_epic_name, 'rarity': 'epic', 'amount': 2, 'reward': 200},
        ])

    if legendary_dragons:
        base_legendary = random.choice(legendary_dragons)
        base_legendary_name = DRAGON_TYPES[base_legendary]['name']
        quest_types.extend([
            {'type': 'catch_rarity_or_higher', 'dragon_name': base_legendary_name, 'rarity': 'legendary', 'amount': 1, 'reward': 250},
        ])

    quest_types.extend([
        {'type': 'earn_coins', 'amount': 10, 'reward': 50},
        {'type': 'earn_coins', 'amount': 25, 'reward': 75},
        {'type': 'earn_coins', 'amount': 50, 'reward': 100},
        {'type': 'earn_coins', 'amount': 75, 'reward': 125},
        {'type': 'earn_coins', 'amount': 100, 'reward': 150},
        {'type': 'use_casino', 'amount': 1, 'reward': 40},
        {'type': 'use_casino', 'amount': 2, 'reward': 60},
        {'type': 'use_casino', 'amount': 3, 'reward': 80},
        {'type': 'use_casino', 'amount': 5, 'reward': 125},
        {'type': 'open_packs', 'amount': 1, 'reward': 100},
        {'type': 'open_packs', 'amount': 2, 'reward': 175},
        {'type': 'open_packs', 'amount': 3, 'reward': 250},
        {'type': 'use_coinflip', 'amount': 1, 'reward': 50},
        {'type': 'use_coinflip', 'amount': 3, 'reward': 100},
        {'type': 'use_coinflip', 'amount': 5, 'reward': 150},
    ])

    if not has_bingo_cooldown:
        quest_types.extend([
            {'type': 'check_bingo', 'amount': 1, 'reward': 75},
            {'type': 'complete_bingo', 'amount': 1, 'reward': 300},
        ])

    selected_quests = []
    seen_types = set()

    if ENABLE_TOPGG_VOTE_QUEST:
        selected_quests = [{'type': 'vote_topgg', 'amount': 1, 'reward': 100}]
        seen_types.add('vote_topgg')

    quest_types_copy = quest_types.copy()
    random.shuffle(quest_types_copy)

    for quest in quest_types_copy:
        if len(selected_quests) >= 3:
            break

        quest_type = quest['type']
        amount = quest['amount']

        if quest_type == 'catch_rarity_or_higher':
            type_key = (quest_type, quest.get('dragon_name', ''), amount)
        else:
            type_key = (quest_type, amount)

        if type_key not in seen_types:
            selected_quests.append(quest)
            seen_types.add(type_key)

    return selected_quests


def check_dragonpass_quests(guild_id: int, user_id: int, action_type: str, amount: int = 1, dragon_type: str = None):
    """Check and update Dragonpass quest progress."""
    lock = get_quest_lock(guild_id, user_id)

    with lock:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=120.0)
            c = conn.cursor()
            current_time = int(time.time())
            import ast

            c.execute('INSERT OR IGNORE INTO dragonpass (guild_id, user_id, quest_refresh_time) VALUES (?, ?, ?)',
                      (guild_id, user_id, current_time + 43200))

            c.execute('SELECT quests_active, level, claimed_levels, quest_refresh_time FROM dragonpass WHERE guild_id = ? AND user_id = ?',
                      (guild_id, user_id))
            result = c.fetchone()

            quests = None
            current_level = 0
            claimed_levels = []
            quest_refresh_time = current_time + 43200
            needs_quest_regen = False

            if result:
                quests_active = result[0]
                current_level = result[1] if result[1] else 0
                claimed_levels = ast.literal_eval(result[2]) if result[2] else []
                quest_refresh_time = result[3] if result[3] else current_time + 43200

                if not quests_active or (current_time >= quest_refresh_time):
                    quests = generate_dragonpass_quests(current_time, guild_id, user_id)
                    quest_refresh_time = current_time + 43200
                    needs_quest_regen = True
                else:
                    quests = ast.literal_eval(quests_active)
                    if len(quests) < 3:
                        quests = generate_dragonpass_quests(current_time, guild_id, user_id)
                        quest_refresh_time = current_time + 43200
                        needs_quest_regen = True

            if not quests:
                quests = generate_dragonpass_quests(current_time, guild_id, user_id)
                quest_refresh_time = current_time + 43200
                needs_quest_regen = True

            coins_gained = 0
            updated_quests = []

            dragon_rarity_map = {}
            rarity_levels = {'common': 0, 'uncommon': 1, 'rare': 2, 'epic': 3, 'legendary': 4, 'mythic': 5, 'ultra': 6}
            for rarity, dragons in DRAGON_RARITY_TIERS.items():
                for dragon_key in dragons:
                    dragon_rarity_map[dragon_key] = rarity_levels.get(rarity, 0)

            caught_dragon_rarity = dragon_rarity_map.get(dragon_type, 0) if dragon_type else 0

            if needs_quest_regen:
                c.execute('UPDATE dragonpass SET quests_active = ?, quest_refresh_time = ? WHERE guild_id = ? AND user_id = ?',
                          (str(quests), quest_refresh_time, guild_id, user_id))
                conn.commit()
                conn.close()
                return 0, 0

            for quest in quests:
                quest_type = quest['type']
                target_amount = quest['amount']
                reward = quest['reward']
                current_progress = quest.get('progress', 0)

                if action_type == 'vote_topgg' and quest_type == 'vote_topgg':
                    current_progress += amount
                elif action_type == 'catch_dragon' and quest_type == 'catch_dragons':
                    current_progress += amount
                elif action_type == 'catch_dragon' and quest_type == 'catch_rarity_or_higher':
                    quest_rarity = quest.get('rarity', 'common')
                    quest_rarity_level = rarity_levels.get(quest_rarity, 0)
                    if caught_dragon_rarity >= quest_rarity_level:
                        current_progress += amount
                elif action_type == 'earn_coins' and quest_type == 'earn_coins':
                    current_progress += amount
                elif action_type == 'use_casino' and quest_type == 'use_casino':
                    current_progress += amount
                elif action_type == 'open_pack' and quest_type == 'open_packs':
                    current_progress += amount
                elif action_type == 'use_coinflip' and quest_type == 'use_coinflip':
                    current_progress += amount
                elif action_type == 'check_bingo' and quest_type == 'check_bingo':
                    current_progress += amount
                elif action_type == 'complete_bingo' and quest_type == 'complete_bingo':
                    current_progress += amount

                if current_progress >= target_amount and quest.get('completed') is not True:
                    coins_gained += reward
                    quest['completed'] = True

                quest['progress'] = current_progress
                updated_quests.append(quest)

            if coins_gained > 0:
                c.execute('UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
                          (coins_gained, guild_id, user_id))

            completed_count = sum(1 for q in updated_quests if q.get('completed', False))
            new_level = current_level

            if completed_count >= 3 and coins_gained > 0 and new_level < 30:
                new_level += 1

                if new_level not in claimed_levels:
                    claimed_levels.append(new_level)

                if new_level < 30:
                    if new_level <= 10:
                        pack_type = 'stone' if new_level % 2 == 0 else 'wooden'
                    elif new_level <= 20:
                        pack_type = 'silver' if new_level % 2 == 0 else 'bronze'
                    else:
                        pack_type = 'diamond' if new_level % 2 == 0 else 'gold'

                    c.execute('''INSERT INTO user_packs (guild_id, user_id, pack_type, count)
                                 VALUES (?, ?, ?, 1)
                                 ON CONFLICT(guild_id, user_id, pack_type)
                                 DO UPDATE SET count = count + 1''',
                              (guild_id, user_id, pack_type))

                if new_level == 30:
                    c.execute('''INSERT INTO user_items (guild_id, user_id, item_type, count)
                                 VALUES (?, ?, ?, 2)
                                 ON CONFLICT(guild_id, user_id, item_type)
                                 DO UPDATE SET count = count + 2''',
                              (guild_id, user_id, 'dragonscale'))

            c.execute('UPDATE dragonpass SET quests_active = ?, level = ?, claimed_levels = ?, quest_refresh_time = ? WHERE guild_id = ? AND user_id = ?',
                      (str(updated_quests), new_level, str(claimed_levels), quest_refresh_time, guild_id, user_id))

            conn.commit()
            conn.close()
            return coins_gained, new_level - current_level

        except sqlite3.OperationalError as e:
            logger.error(f"Database error in check_dragonpass_quests for user {user_id} in guild {guild_id}: {e}")
            return None


# ==================== RANDOM DRAGON SELECTION ====================
def get_random_dragon():
    """Get random dragon based on catch_weight."""
    dragons = list(DRAGON_TYPES.items())
    weights = [d[1]['catch_weight'] for d in dragons]
    dragon_key = random.choices(dragons, weights=weights)[0][0]
    return dragon_key, DRAGON_TYPES[dragon_key]


def get_higher_rarity_dragon(min_value: float = 0):
    """Get a random dragon from rare+ tiers with value >= min_value."""
    higher_rarity_dragons = []
    for rarity in ['rare', 'epic', 'legendary', 'mythic', 'ultra']:
        if rarity in DRAGON_RARITY_TIERS:
            for dragon_type in DRAGON_RARITY_TIERS[rarity]:
                dragon_data = DRAGON_TYPES[dragon_type]
                if dragon_data['value'] >= min_value:
                    higher_rarity_dragons.append((dragon_type, dragon_data))

    if not higher_rarity_dragons:
        return get_random_dragon()

    dragon_key, dragon_data = random.choice(higher_rarity_dragons)
    return dragon_key, dragon_data


# ==================== PERK SYSTEM ====================
def get_user_perks(guild_id: int, user_id: int):
    """Get all active perks for a user (only non-expired ones)."""
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    c = conn.cursor()
    current_time = int(time.time())

    c.execute('SELECT * FROM active_perks WHERE guild_id = ? AND user_id = ? AND expires_at > ?',
              (guild_id, user_id, current_time))
    perks = c.fetchall()

    c.execute('DELETE FROM active_perks WHERE expires_at <= ?', (current_time,))
    conn.commit()
    conn.close()
    return perks


def apply_perks(guild_id: int, user_id: int, base_amount: int, dragon_type: str):
    """Apply all active perks to a catch. Returns (final_amount, pack_rewards, time_bonus, perks_applied)."""
    perks = get_user_perks(guild_id, user_id)
    final_amount = base_amount
    pack_rewards = []
    time_bonus = 0
    perks_applied = []

    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    c = conn.cursor()
    c.execute('SELECT speedrun_catches FROM dragon_nest WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
    result = c.fetchone()
    speedrun_count = result[0] if result else 0

    c.execute('SELECT COUNT(*) FROM user_alphas WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
    alpha_count = c.fetchone()[0]
    conn.close()

    if alpha_count > 0:
        alpha_boost = 0.06 * math.log(2 * alpha_count + 1)
        if random.random() < alpha_boost:
            final_amount += 1

    for perk in perks:
        perk_id = perk[2]
        perk_name = perk[3]
        perk_effect = perk[4]
        perk_value = perk[5]
        perk_type = perk[6]

        perk_data = None
        for rarity, perk_list in PERKS_POOL.items():
            for p in perk_list:
                if p['id'] == perk_id:
                    perk_data = p
                    break

        if not perk_data:
            perk_data = {'type': perk_type, 'value': perk_value}

        if perk_type == 'lucky':
            if random.random() < perk_value:
                final_amount *= 2
                perks_applied.append(f"🍀 {perk_name} (doubled!)")
        elif perk_type == 'gambling':
            roll = random.random()
            if roll < perk_value:
                final_amount *= 3
                perks_applied.append(f"🎰 {perk_name} (tripled!)")
            elif roll < perk_value + perk_data.get('penalty', 0):
                final_amount = 0
                perks_applied.append(f"💔 {perk_name} (lost all)")
        elif perk_type == 'pack':
            if random.random() < perk_value:
                pack_tier = perk_data.get('pack_tier', 'bronze')
                pack_rewards.append(pack_tier)
                perks_applied.append(f"📦 {perk_name}")
        elif perk_type == 'time':
            if random.random() < perk_value:
                time_bonus += 5
                perks_applied.append(f"⏰ {perk_name}")
        elif perk_type == 'speedrun':
            if speedrun_count < perk_value:
                final_amount *= 2
                perks_applied.append(f"⚡ {perk_name}")
        elif perk_type == 'rarity':
            if random.random() < perk_value:
                perks_applied.append(f"✨ {perk_name} (triggered)")
        elif perk_type == 'coins':
            if perk_value > 0:
                perks_applied.append(f"💰 {perk_name} (active)")
        elif perk_type == 'steal':
            if random.random() < perk_value:
                perks_applied.append(f"🎯 {perk_name} (triggered)")
        elif perk_type == 'fusion':
            if random.random() < perk_value:
                perks_applied.append(f"🔗 {perk_name} (triggered)")
        elif perk_type == 'mimic':
            if random.random() < perk_value:
                perks_applied.append(f"🪞 {perk_name} (triggered)")
        elif perk_type == 'echo':
            if random.random() < perk_value:
                perks_applied.append(f"📢 {perk_name} (triggered)")
        elif perk_type == 'counter':
            if perk_value > 0:
                perks_applied.append(f"📊 {perk_name} (active)")
        elif perk_type == 'streak':
            if perk_value > 0:
                perks_applied.append(f"🔥 {perk_name} (active)")
        elif perk_type == 'collector':
            if perk_value > 0:
                perks_applied.append(f"🏆 {perk_name} (active)")
        elif perk_type == 'master':
            if random.random() < perk_value:
                perks_applied.append(f"👑 {perk_name} (triggered)")
        elif perk_type == 'perfect':
            if random.random() < perk_value:
                perks_applied.append(f"💎 {perk_name} (triggered)")

    if speedrun_count < 60:
        conn = sqlite3.connect(DB_PATH, timeout=120.0)
        c = conn.cursor()
        c.execute('UPDATE dragon_nest SET speedrun_catches = speedrun_catches + 1 WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user_id))
        conn.commit()
        conn.close()

    return final_amount, pack_rewards, time_bonus, perks_applied


def apply_items(guild_id: int, user_id: int, base_amount: int) -> tuple:
    """Apply active usable items to a catch. Returns (final_amount,)."""
    return base_amount


# ==================== SPAWN CHANNEL ====================
def get_spawn_channel(guild_id: int):
    """Get configured spawn channel for guild."""
    if guild_id in spawn_channels:
        return spawn_channels[guild_id]

    try:
        conn = sqlite3.connect(DB_PATH, timeout=120.0)
        c = conn.cursor()
        c.execute('SELECT spawn_channel FROM guild_settings WHERE guild_id = ?', (guild_id,))
        result = c.fetchone()
        conn.close()

        if result and result[0]:
            spawn_channels[guild_id] = result[0]
            return result[0]
    except sqlite3.OperationalError as e:
        logger.warning(f"Failed to get spawn channel: {e}")

    return None


def set_spawn_channel(guild_id: int, channel_id: int):
    """Set spawn channel for guild."""
    spawn_channels[guild_id] = channel_id
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO guild_settings (guild_id, spawn_channel) VALUES (?, ?)',
              (guild_id, channel_id))
    conn.commit()
    conn.close()


# ==================== RAID BOSS ====================
def is_raid_boss_active(guild_id: int) -> bool:
    """Check if raid boss is currently active in guild."""
    current_time = int(time.time())

    if guild_id in raid_boss_active:
        raid_data = raid_boss_active[guild_id]
        if isinstance(raid_data, dict) and raid_data.get('active') and current_time < raid_data.get('despawn_time', 0):
            return True

    try:
        conn = sqlite3.connect(DB_PATH, timeout=120.0)
        c = conn.cursor()
        c.execute('SELECT expires_at FROM raid_bosses WHERE guild_id = ? AND expires_at > ?',
                  (guild_id, current_time))
        result = c.fetchone()
        conn.close()
        if result:
            return True
    except sqlite3.OperationalError as e:
        logger.warning(f"Database error checking raid boss: {e}")

    return False


# ==================== USABLE ITEMS ====================
def get_active_item(guild_id: int, user_id: int, item_type: str) -> bool:
    """Check if user has an active usable item (time-based)."""
    if guild_id not in active_usable_items:
        return False
    if user_id not in active_usable_items[guild_id]:
        return False

    current_time = int(time.time())
    expires_at = active_usable_items[guild_id][user_id].get(item_type)

    if expires_at is None:
        return False

    if current_time >= expires_at:
        del active_usable_items[guild_id][user_id][item_type]
        return False

    return True


def activate_item(guild_id: int, user_id: int, item_type: str, duration_seconds: int):
    """Activate a time-based item for a user."""
    if guild_id not in active_usable_items:
        active_usable_items[guild_id] = {}
    if user_id not in active_usable_items[guild_id]:
        active_usable_items[guild_id][user_id] = {}

    current_time = int(time.time())
    active_usable_items[guild_id][user_id][item_type] = current_time + duration_seconds


def get_passive_bonus(guild_id: int, user_id: int, bonus_type: str) -> float:
    """Get passive item bonus."""
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    c = conn.cursor()

    if bonus_type == 'catch':
        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, user_id, 'knowledge_book'))
        result = c.fetchone()
        conn.close()
        return (result[0] * 2 / 100) if result else 0.0

    elif bonus_type == 'raid_crit':
        c.execute('SELECT count FROM user_items WHERE guild_id = ? AND user_id = ? AND item_type = ?',
                  (guild_id, user_id, 'precision_stone'))
        result = c.fetchone()
        conn.close()
        if result and result[0] > 0:
            bonus = result[0] * 0.05
            return min(bonus, 0.30)
        return 0.0

    conn.close()
    return 0.0
