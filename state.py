"""
state.py - Global in-memory state variables and lock management.
Extracted verbatim from bot.py (lines 943-978 and related lock functions lines 65-84).
"""

import threading
import asyncio

# ==================== THREAD-SAFE LOCKING ====================
dragonpass_locks = {}   # {(guild_id, user_id): threading.Lock()}
spawn_locks = {}        # {guild_id: asyncio.Lock()}

def get_quest_lock(guild_id: int, user_id: int):
    """Get or create a threading.Lock for this user's quest tracking."""
    key = (guild_id, user_id)
    if key not in dragonpass_locks:
        dragonpass_locks[key] = threading.Lock()
    return dragonpass_locks[key]

def get_spawn_lock(guild_id: int):
    """Get or create an asyncio.Lock for this guild's dragon spawns."""
    if guild_id not in spawn_locks:
        spawn_locks[guild_id] = asyncio.Lock()
    return spawn_locks[guild_id]

# Track last catch attempt for mock messaging
last_catch_attempts = {}  # {guild_id: {'user_id': user_id, 'timestamp': time, 'username': name}}

# ==================== ACTIVE EVENTS ====================
# Dragonscale events (server-wide spawn boosts)
active_dragonscales = {}        # {guild_id: end_timestamp}
dragonscale_event_starts = {}   # {guild_id: start_timestamp}

# Dragonfest events
active_dragonfest = {}          # {guild_id: {'end': timestamp, 'multiplier': float}}

# Lucky Charms (per-user)
active_luckycharms = {}         # {guild_id: {user_id: end_timestamp}}

# Usable item timers (Night Vision, Lucky Dice, Dragon Magnet)
active_usable_items = {}        # {guild_id: {user_id: {item_type: end_timestamp}}}

# Track night vision activations to prevent daily abuse
night_vision_activations = {}   # {(guild_id, user_id): date_string}

# Dragon spawns currently active (waiting to be caught)
active_spawns = {}              # {guild_id: {'dragon_type': str, 'message': Message, ...}}

# Black market state
black_market_active = {}        # {guild_id: {'end_time': ts, 'items': list, 'message_id': int}}

# Spawn channels per guild
spawn_channels = {}             # {guild_id: channel_id}

# Premium users dict: {guild_id: {user_id: end_timestamp}}
premium_users = {}              # {guild_id: {user_id: end_timestamp}}

# Active raid bosses
raid_boss_active = {}           # {guild_id: bool}

# Active breeding sessions (prevents duplicate breed calls)
active_breeding_sessions = {}   # {(guild_id, user_id): timestamp}

# Ritual state
ritual_active = {}              # {guild_id: bool}

# Last spawn data (for debugging / dev commands)
last_spawn_data = {}            # {guild_id: {...}}

# ==================== RAID BOSS CONFIG ====================
RARITY_DAMAGE = {
    'common': 10,
    'uncommon': 25,
    'rare': 60,
    'epic': 150,
    'legendary': 400,
    'mythic': 1000,
    'ultra': 2500,
}

RAID_SPAWN_TIMES = [8, 14, 20]   # Hours (UTC) when raid bosses can spawn
RAID_DURATION_HOURS = 2           # How long each raid lasts
raid_boss_last_spawn = {}         # {guild_id: timestamp}

ENABLE_TOPGG_VOTE_QUEST = True
