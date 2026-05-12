"""
database.py - Database initialization, migrations, and helper functions.
Extracted verbatim from bot.py (lines 979-1873).
"""

import sqlite3
import time
import json
import asyncio
import logging

import discord

from config import (
    DB_PATH, DB_TIMEOUT_SHORT, DB_TIMEOUT_MEDIUM, DB_TIMEOUT_LONG,
    DB_BUSY_TIMEOUT, RETRY_MAX_ATTEMPTS, RETRY_DELAY,
    DRAGON_TYPES, DRAGON_RARITY_TIERS, DRAGONNEST_UPGRADES,
    EMBED_MAX_FIELDS, EMBED_MAX_FIELD_VALUE_LENGTH,
    EMBED_MAX_DESCRIPTION_LENGTH, EMBED_MAX_TITLE_LENGTH,
    ACHIEVEMENTS,
)
from state import spawn_channels, get_quest_lock

logger = logging.getLogger(__name__)


# ==================== DATABASE CONNECTION ====================
def get_db_connection(timeout: float = DB_TIMEOUT_SHORT):
    """Get a database connection with WAL mode and busy timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=timeout, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute(f'PRAGMA busy_timeout={DB_BUSY_TIMEOUT}')
    return conn


def safe_db_operation(func, max_retries: int = RETRY_MAX_ATTEMPTS, retry_delay: float = RETRY_DELAY):
    """Execute a database operation with automatic retry logic."""
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))
            else:
                logger.error(f"Database operation failed after {attempt+1} attempts: {e}")
                raise Exception(f"Database operation failed: {str(e)[:100]}")
    return None


# ==================== DRAGON NEST HELPERS ====================
def get_dragonnest_upgrade_level(guild_id: int, user_id: int) -> int:
    """Get the Dragon Nest upgrade level for a user."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SHORT)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute(f'PRAGMA busy_timeout={DB_BUSY_TIMEOUT}')
        c = conn.cursor()
        c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user_id))
        result = c.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception:
        return 0


def is_player_softlocked(guild_id: int, user_id: int) -> tuple:
    """
    Check if a player has enough coins to upgrade Dragon Nest.
    Returns (is_softlocked, current_upgrade_level).
    """
    try:
        conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SHORT)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute(f'PRAGMA busy_timeout={DB_BUSY_TIMEOUT}')
        c = conn.cursor()

        c.execute('SELECT upgrade_level FROM dragon_nest WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user_id))
        upgrade_result = c.fetchone()
        current_upgrade_level = upgrade_result[0] if upgrade_result else 0

        if current_upgrade_level >= 5:
            conn.close()
            return False, current_upgrade_level

        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?',
                  (guild_id, user_id))
        balance_result = c.fetchone()
        balance = balance_result[0] if balance_result else 0

        conn.close()

        next_upgrade_level = current_upgrade_level + 1
        upgrade_cost = DRAGONNEST_UPGRADES.get(next_upgrade_level, {}).get('cost', 0)
        is_softlocked = balance >= upgrade_cost
        return is_softlocked, current_upgrade_level
    except Exception:
        return False, 0


# ==================== DATABASE INITIALIZATION ====================
def init_db():
    """Initialize SQLite database with all tables."""
    conn = get_db_connection(timeout=DB_TIMEOUT_LONG)
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        guild_id INTEGER,
        user_id INTEGER,
        balance REAL DEFAULT 0,
        daily_last_claimed INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # User dragons inventory
    c.execute('''CREATE TABLE IF NOT EXISTS user_dragons (
        guild_id INTEGER,
        user_id INTEGER,
        dragon_type TEXT,
        count INTEGER DEFAULT 0,
        fastest_catch REAL DEFAULT 0,
        slowest_catch REAL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, dragon_type)
    )''')

    # Dragon Nest progression
    c.execute('''CREATE TABLE IF NOT EXISTS dragon_nest (
        guild_id INTEGER,
        user_id INTEGER,
        level INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        bounties_active TEXT,
        bounties_completed INTEGER DEFAULT 0,
        speedrun_catches INTEGER DEFAULT 0,
        perks_activated_at INTEGER DEFAULT 0,
        perks_activated_at_current_level INTEGER DEFAULT 0,
        upgrade_level INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # Dragon Nest active status
    c.execute('''CREATE TABLE IF NOT EXISTS dragon_nest_active (
        guild_id INTEGER,
        user_id INTEGER,
        active_until INTEGER,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # User perks
    c.execute('''CREATE TABLE IF NOT EXISTS user_perks (
        guild_id INTEGER,
        user_id INTEGER,
        perk_id TEXT,
        perk_name TEXT,
        perk_effect TEXT,
        perk_value REAL,
        rarity TEXT,
        PRIMARY KEY (guild_id, user_id, perk_id)
    )''')

    # Active perks with expiration
    c.execute('''CREATE TABLE IF NOT EXISTS active_perks (
        guild_id INTEGER,
        user_id INTEGER,
        perk_id TEXT,
        perk_name TEXT,
        perk_effect TEXT,
        perk_value REAL,
        perk_type TEXT,
        expires_at INTEGER,
        PRIMARY KEY (guild_id, user_id, perk_id)
    )''')

    # Pending perk selections
    c.execute('''CREATE TABLE IF NOT EXISTS pending_perks (
        guild_id INTEGER,
        user_id INTEGER,
        level INTEGER,
        perks_json TEXT,
        PRIMARY KEY (guild_id, user_id, level)
    )''')

    # Dragonscales
    c.execute('''CREATE TABLE IF NOT EXISTS dragonscales (
        guild_id INTEGER,
        user_id INTEGER,
        minutes INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # Bounty progress tracking
    c.execute('''CREATE TABLE IF NOT EXISTS bounty_progress (
        guild_id INTEGER,
        user_id INTEGER,
        bounty_type TEXT,
        target_amount INTEGER,
        current_progress INTEGER DEFAULT 0,
        target_dragon_type TEXT,
        PRIMARY KEY (guild_id, user_id, bounty_type)
    )''')

    # User packs inventory
    c.execute('''CREATE TABLE IF NOT EXISTS user_packs (
        guild_id INTEGER,
        user_id INTEGER,
        pack_type TEXT,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, pack_type)
    )''')

    # Alpha Dragons
    c.execute('''CREATE TABLE IF NOT EXISTS alpha_dragons (
        alpha_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        catch_boost REAL
    )''')

    # User alpha dragon ownership
    c.execute('''CREATE TABLE IF NOT EXISTS user_alphas (
        guild_id INTEGER,
        user_id INTEGER,
        alpha_id INTEGER,
        name TEXT,
        catch_boost REAL,
        created_at INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, alpha_id)
    )''')

    # Spawn configuration per server
    c.execute('''CREATE TABLE IF NOT EXISTS spawn_config (
        guild_id INTEGER PRIMARY KEY,
        spawn_channel_id INTEGER,
        last_spawn_time INTEGER DEFAULT 0
    )''')

    # Dragonpass system
    c.execute('''CREATE TABLE IF NOT EXISTS dragonpass (
        guild_id INTEGER,
        user_id INTEGER,
        season INTEGER DEFAULT 1,
        level INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        quests_active TEXT,
        quest_refresh_time INTEGER,
        claimed_levels TEXT DEFAULT '[]',
        PRIMARY KEY (guild_id, user_id, season)
    )''')

    try:
        c.execute('ALTER TABLE dragonpass ADD COLUMN claimed_levels TEXT DEFAULT "[]"')
    except sqlite3.OperationalError:
        pass

    # Achievements
    c.execute('''CREATE TABLE IF NOT EXISTS achievements (
        guild_id INTEGER,
        user_id INTEGER,
        achievement_id TEXT,
        unlocked_at INTEGER,
        PRIMARY KEY (guild_id, user_id, achievement_id)
    )''')

    # Premium users
    c.execute('''CREATE TABLE IF NOT EXISTS premium_users (
        guild_id INTEGER,
        user_id INTEGER,
        premium_until INTEGER,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # Server dragon discoveries
    c.execute('''CREATE TABLE IF NOT EXISTS server_discoveries (
        guild_id INTEGER,
        dragon_type TEXT,
        first_discovered_by INTEGER,
        first_discovered_at INTEGER,
        total_caught INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, dragon_type)
    )''')

    # Trade offers
    c.execute('''CREATE TABLE IF NOT EXISTS trade_offers (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        sender_id INTEGER,
        receiver_id INTEGER,
        sender_dragons TEXT,
        receiver_dragons TEXT,
        status TEXT DEFAULT 'pending',
        created_at INTEGER
    )''')

    # User lucky charms
    c.execute('''CREATE TABLE IF NOT EXISTS user_luckycharms (
        guild_id INTEGER,
        user_id INTEGER,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # User items
    c.execute('''CREATE TABLE IF NOT EXISTS user_items (
        guild_id INTEGER,
        user_id INTEGER,
        item_type TEXT,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, item_type)
    )''')

    # Active usable items
    c.execute('''CREATE TABLE IF NOT EXISTS active_items (
        guild_id INTEGER,
        user_id INTEGER,
        item_type TEXT,
        activated_at INTEGER,
        expires_at INTEGER,
        PRIMARY KEY (guild_id, user_id, item_type)
    )''')

    # Market listings
    c.execute('''CREATE TABLE IF NOT EXISTS market_listings (
        listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        seller_id INTEGER,
        dragon_id INTEGER,
        dragon_type TEXT,
        price INTEGER,
        listed_at INTEGER,
        item_type TEXT DEFAULT NULL,
        FOREIGN KEY (dragon_id) REFERENCES user_dragons (dragon_id)
    )''')

    try:
        c.execute('PRAGMA table_info(market_listings)')
        columns = [col[1] for col in c.fetchall()]
        if 'item_type' not in columns:
            c.execute('ALTER TABLE market_listings ADD COLUMN item_type TEXT DEFAULT NULL')
            conn.commit()
    except sqlite3.OperationalError as e:
        if 'duplicate column name' not in str(e):
            print(f"Migration error: {e}")

    # Guild settings
    c.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id INTEGER PRIMARY KEY,
        spawn_channel INTEGER
    )''')

    try:
        c.execute('SELECT guild_id, spawn_channel_id FROM spawn_config')
        old_configs = c.fetchall()
        for guild_id, channel_id in old_configs:
            c.execute('INSERT OR IGNORE INTO guild_settings (guild_id, spawn_channel) VALUES (?, ?)',
                     (guild_id, channel_id))
        if old_configs:
            print(f"Migrated {len(old_configs)} spawn channels from spawn_config to guild_settings")
    except sqlite3.OperationalError:
        pass

    conn.commit()

    # Dragonfest stats
    try:
        c.execute('PRAGMA table_info(dragonfest_stats)')
        columns = [col[1] for col in c.fetchall()]
        has_dragon_type = 'dragon_type' in columns
        if not has_dragon_type:
            print("Migrating dragonfest_stats to new schema...")
            c.execute('DROP TABLE dragonfest_stats')
            c.execute('''CREATE TABLE dragonfest_stats (
                guild_id INTEGER,
                user_id INTEGER,
                event_start INTEGER,
                dragon_type TEXT,
                count INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, event_start, dragon_type)
            )''')
            conn.commit()
    except sqlite3.OperationalError as e:
        if 'no such table' in str(e):
            c.execute('''CREATE TABLE dragonfest_stats (
                guild_id INTEGER,
                user_id INTEGER,
                event_start INTEGER,
                dragon_type TEXT,
                count INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, event_start, dragon_type)
            )''')
            conn.commit()

    # Dragonscale stats
    try:
        c.execute('PRAGMA table_info(dragonscale_stats)')
        columns = [col[1] for col in c.fetchall()]
        has_dragon_type = 'dragon_type' in columns
        if not has_dragon_type:
            print("Migrating dragonscale_stats to new schema...")
            c.execute('DROP TABLE dragonscale_stats')
            c.execute('''CREATE TABLE dragonscale_stats (
                guild_id INTEGER,
                user_id INTEGER,
                event_start INTEGER,
                dragon_type TEXT,
                count INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, event_start, dragon_type)
            )''')
            conn.commit()
    except sqlite3.OperationalError as e:
        if 'no such table' in str(e):
            c.execute('''CREATE TABLE dragonscale_stats (
                guild_id INTEGER,
                user_id INTEGER,
                event_start INTEGER,
                dragon_type TEXT,
                count INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, event_start, dragon_type)
            )''')
            conn.commit()

    # Dragonscale event log
    c.execute('''CREATE TABLE IF NOT EXISTS dragonscale_event_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        event_start INTEGER,
        dragon_type TEXT,
        amount INTEGER,
        caught_at INTEGER
    )''')

    # Dragonfest event log
    c.execute('''CREATE TABLE IF NOT EXISTS dragonfest_event_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        event_start INTEGER,
        dragon_type TEXT,
        amount INTEGER,
        caught_at INTEGER
    )''')

    # Market sales history
    c.execute('''CREATE TABLE IF NOT EXISTS market_sales (
        sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        dragon_type TEXT,
        item_type TEXT DEFAULT NULL,
        price INTEGER,
        sold_at INTEGER
    )''')

    try:
        c.execute('PRAGMA table_info(market_sales)')
        columns = [col[1] for col in c.fetchall()]
        if 'item_type' not in columns:
            c.execute('ALTER TABLE market_sales ADD COLUMN item_type TEXT DEFAULT NULL')
    except Exception as e:
        print(f"Migration check for market_sales failed: {e}")

    # Breeding system
    c.execute('''CREATE TABLE IF NOT EXISTS bred_dragons (
        bred_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        dragon_type TEXT,
        tier INTEGER DEFAULT 0,
        bred_at INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS breeding_cooldowns (
        guild_id INTEGER,
        user_id INTEGER,
        last_breed INTEGER,
        last_breed_rarity TEXT DEFAULT 'common',
        PRIMARY KEY (guild_id, user_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS breeding_queue (
        queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        parent1_type TEXT,
        parent2_type TEXT,
        scheduled_for INTEGER,
        created_at INTEGER,
        status TEXT DEFAULT 'pending',
        UNIQUE(guild_id, user_id, parent1_type, parent2_type)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS breeding_xp (
        guild_id INTEGER,
        user_id INTEGER,
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # Adventure system
    c.execute('''CREATE TABLE IF NOT EXISTS user_adventures (
        adventure_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        user_adventure_number INTEGER,
        dragons_sent TEXT,
        adventure_type TEXT,
        difficulty TEXT,
        started_at INTEGER,
        returns_at INTEGER,
        status TEXT DEFAULT 'active',
        result TEXT,
        rewards_coins INTEGER DEFAULT 0,
        rewards_dragons TEXT DEFAULT '[]',
        claimed INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS adventure_cooldowns (
        guild_id INTEGER,
        user_id INTEGER,
        adventure_type TEXT,
        cooldown_until INTEGER,
        UNIQUE(guild_id, user_id, adventure_type)
    )''')

    # Migrate guild_settings: add setup_reminder_ignored_until if missing
    c.execute("PRAGMA table_info(guild_settings)")
    gs_columns = [col[1] for col in c.fetchall()]
    if 'setup_reminder_ignored_until' not in gs_columns:
        c.execute('ALTER TABLE guild_settings ADD COLUMN setup_reminder_ignored_until INTEGER DEFAULT 0')
        conn.commit()

    # Migrate user_adventures: add double_loot column if missing
    c.execute("PRAGMA table_info(user_adventures)")
    adv_columns = [col[1] for col in c.fetchall()]
    if 'double_loot' not in adv_columns:
        c.execute('ALTER TABLE user_adventures ADD COLUMN double_loot INTEGER DEFAULT 0')
        conn.commit()

    # Migrate alpha_dragons if needed
    c.execute("PRAGMA table_info(alpha_dragons)")
    columns = [col[1] for col in c.fetchall()]
    if 'name' not in columns:
        c.execute('DROP TABLE IF EXISTS alpha_dragons')
        c.execute('''CREATE TABLE alpha_dragons (
            alpha_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            catch_boost REAL
        )''')

    # Migrate user_alphas if needed
    c.execute("PRAGMA table_info(user_alphas)")
    columns = [col[1] for col in c.fetchall()]
    if 'name' not in columns or 'catch_boost' not in columns:
        c.execute('DROP TABLE IF EXISTS user_alphas')
        c.execute('''CREATE TABLE user_alphas (
            guild_id INTEGER,
            user_id INTEGER,
            alpha_id INTEGER,
            name TEXT,
            catch_boost REAL,
            created_at INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, alpha_id)
        )''')

    # Add catch time tracking columns to user_dragons
    c.execute("PRAGMA table_info(user_dragons)")
    columns = [col[1] for col in c.fetchall()]
    if 'fastest_catch' not in columns or 'slowest_catch' not in columns:
        try:
            c.execute('ALTER TABLE user_dragons ADD COLUMN fastest_catch REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass
        try:
            c.execute('ALTER TABLE user_dragons ADD COLUMN slowest_catch REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass

    # Add last_caught_at column
    c.execute("PRAGMA table_info(user_dragons)")
    columns = [col[1] for col in c.fetchall()]
    if 'last_caught_at' not in columns:
        try:
            c.execute('ALTER TABLE user_dragons ADD COLUMN last_caught_at INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

    # Bingo cards
    c.execute('''CREATE TABLE IF NOT EXISTS bingo_cards (
        guild_id INTEGER,
        user_id INTEGER,
        card_data TEXT,
        marked_positions TEXT DEFAULT '[]',
        created_at INTEGER,
        expires_at INTEGER,
        completed INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )''')

    # Vote streaks
    c.execute('''CREATE TABLE IF NOT EXISTS vote_streaks (
        user_id INTEGER PRIMARY KEY,
        current_streak INTEGER DEFAULT 0,
        last_vote_time INTEGER DEFAULT 0,
        total_votes INTEGER DEFAULT 0,
        best_streak INTEGER DEFAULT 0
    )''')

    # Migrate vote_streaks: add last_reminder_date if missing
    c.execute("PRAGMA table_info(vote_streaks)")
    vs_columns = [col[1] for col in c.fetchall()]
    if 'last_reminder_date' not in vs_columns:
        c.execute('ALTER TABLE vote_streaks ADD COLUMN last_reminder_date TEXT DEFAULT NULL')
        conn.commit()
    if 'reminder_sent_at' not in vs_columns:
        c.execute('ALTER TABLE vote_streaks ADD COLUMN reminder_sent_at INTEGER DEFAULT NULL')
        conn.commit()

    # Raid boss table
    c.execute('''CREATE TABLE IF NOT EXISTS raid_bosses (
        guild_id INTEGER PRIMARY KEY,
        boss_name TEXT,
        easy_hp INTEGER DEFAULT 0,
        easy_max_hp INTEGER DEFAULT 0,
        normal_hp INTEGER DEFAULT 0,
        normal_max_hp INTEGER DEFAULT 0,
        hard_hp INTEGER DEFAULT 0,
        hard_max_hp INTEGER DEFAULT 0,
        boss_rarity TEXT,
        started_at INTEGER,
        expires_at INTEGER,
        reward_dragon TEXT,
        easy_participants TEXT DEFAULT '[]',
        normal_participants TEXT DEFAULT '[]',
        hard_participants TEXT DEFAULT '[]'
    )''')

    try:
        c.execute("PRAGMA table_info(raid_bosses)")
        columns = {row[1] for row in c.fetchall()}
        if 'boss_hp' in columns and 'easy_hp' not in columns:
            print("Migrating raid_bosses table to new tier system...")
            c.execute("ALTER TABLE raid_bosses RENAME TO raid_bosses_old")
            c.execute('''CREATE TABLE raid_bosses (
                guild_id INTEGER PRIMARY KEY,
                boss_name TEXT,
                easy_hp INTEGER DEFAULT 0,
                easy_max_hp INTEGER DEFAULT 0,
                normal_hp INTEGER DEFAULT 0,
                normal_max_hp INTEGER DEFAULT 0,
                hard_hp INTEGER DEFAULT 0,
                hard_max_hp INTEGER DEFAULT 0,
                boss_rarity TEXT,
                started_at INTEGER,
                expires_at INTEGER,
                reward_dragon TEXT,
                easy_participants TEXT DEFAULT '[]',
                normal_participants TEXT DEFAULT '[]',
                hard_participants TEXT DEFAULT '[]'
            )''')
            c.execute('''INSERT INTO raid_bosses
                        (guild_id, boss_name, easy_hp, easy_max_hp, normal_hp, normal_max_hp, hard_hp, hard_max_hp,
                         boss_rarity, started_at, expires_at, reward_dragon, easy_participants, normal_participants, hard_participants)
                        SELECT guild_id, boss_name,
                               CAST(boss_hp * 0.5 AS INTEGER), CAST(boss_max_hp * 0.5 AS INTEGER),
                               boss_hp, boss_max_hp,
                               CAST(boss_hp * 1.5 AS INTEGER), CAST(boss_max_hp * 1.5 AS INTEGER),
                               boss_rarity, started_at, expires_at, reward_dragon, '[]', '[]', '[]'
                        FROM raid_bosses_old''')
            c.execute("DROP TABLE raid_bosses_old")
            print("raid_bosses table migrated successfully!")
    except Exception as e:
        print(f"Migration check result: {e}")

    # Raid damage tracking
    c.execute('''CREATE TABLE IF NOT EXISTS raid_damage (
        guild_id INTEGER,
        user_id INTEGER,
        tier TEXT DEFAULT 'normal',
        damage_dealt INTEGER DEFAULT 0,
        attacks_made INTEGER DEFAULT 0,
        last_attack_time INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )''')

    try:
        c.execute('ALTER TABLE raid_damage ADD COLUMN tier TEXT DEFAULT "normal"')
        conn.commit()
    except Exception as e:
        if "duplicate column" not in str(e) and "already exists" not in str(e):
            print(f"Migration attempt: {e}")

    try:
        c.execute('ALTER TABLE raid_bosses ADD COLUMN message_id INTEGER DEFAULT 0')
        conn.commit()
    except Exception as e:
        if "duplicate column" not in str(e) and "already exists" not in str(e):
            print(f"Migration attempt: {e}")

    # User achievements
    c.execute('''CREATE TABLE IF NOT EXISTS user_achievements (
        guild_id INTEGER,
        user_id INTEGER,
        achievement_key TEXT,
        tier_name TEXT,
        earned_at INTEGER,
        PRIMARY KEY (guild_id, user_id, achievement_key, tier_name)
    )''')

    # Coinflip bets
    c.execute('''CREATE TABLE IF NOT EXISTS coinflip_bets (
        bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        challenger_id INTEGER,
        opponent_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        created_at INTEGER,
        expires_at INTEGER
    )''')

    # Dragonpass completions
    c.execute('''CREATE TABLE IF NOT EXISTS dragonpass_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        completed_at INTEGER NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_trophies (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        trophy_id TEXT NOT NULL,
        earned_at INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id, trophy_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS active_dragon_spawns (
        guild_id INTEGER PRIMARY KEY,
        dragon_type TEXT NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        spawn_timestamp INTEGER NOT NULL,
        night_vision_activator INTEGER
    )''')

    conn.commit()
    conn.close()

    # Load spawn channels into memory
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    c = conn.cursor()
    c.execute('SELECT guild_id, spawn_channel FROM guild_settings WHERE spawn_channel IS NOT NULL')
    for guild_id, channel_id in c.fetchall():
        spawn_channels[guild_id] = channel_id

    # Migrate guild_settings to add server config columns
    c.execute("PRAGMA table_info(guild_settings)")
    gs_columns = {row[1] for row in c.fetchall()}
    new_columns = [
        ('raids_enabled', 'INTEGER DEFAULT 0'),
        ('raid_times', "TEXT DEFAULT '[8, 16, 20]'"),
        ('blackmarket_enabled', 'INTEGER DEFAULT 0'),
        ('blackmarket_interval_hours', 'INTEGER DEFAULT 4'),
        ('blackmarket_max_per_day', 'INTEGER DEFAULT 6'),
    ]
    for col_name, col_def in new_columns:
        if col_name not in gs_columns:
            try:
                conn.execute(f'ALTER TABLE guild_settings ADD COLUMN {col_name} {col_def}')
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()

    migrate_database()


def migrate_database():
    """Run any necessary database schema migrations."""
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    c = conn.cursor()

    dragon_nest_columns = {
        'upgrade_level': 'INTEGER DEFAULT 0',
        'xp': 'INTEGER DEFAULT 0',
        'level': 'INTEGER DEFAULT 0',
        'bounties_completed': 'INTEGER DEFAULT 0',
        'speedrun_catches': 'INTEGER DEFAULT 0',
        'perks_activated_at': 'INTEGER DEFAULT 0',
        'perks_activated_at_current_level': 'INTEGER DEFAULT 0',
    }

    for column_name, column_def in dragon_nest_columns.items():
        try:
            c.execute(f'SELECT {column_name} FROM dragon_nest LIMIT 1')
        except sqlite3.OperationalError as e:
            if f'no such column: {column_name}' in str(e):
                try:
                    c.execute(f'ALTER TABLE dragon_nest ADD COLUMN {column_name} {column_def}')
                    conn.commit()
                except sqlite3.OperationalError as e2:
                    if 'duplicate column name' not in str(e2):
                        print(f"Migration error for {column_name}: {e2}")

    conn.close()


# ==================== USER MANAGEMENT ====================
def get_user(guild_id: int, user_id: int):
    """Get or create user with retry logic."""
    lock = get_quest_lock(guild_id, user_id)

    def _get_user():
        with lock:
            conn = get_db_connection(DB_TIMEOUT_SHORT)
            try:
                c = conn.cursor()
                c.execute('INSERT OR IGNORE INTO users (guild_id, user_id) VALUES (?, ?)', (guild_id, user_id))
                c.execute('SELECT * FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
                user = c.fetchone()
                conn.commit()
                return user
            finally:
                conn.close()

    return safe_db_operation(_get_user, max_retries=RETRY_MAX_ATTEMPTS)


async def get_user_async(guild_id: int, user_id: int):
    """Async wrapper for get_user to prevent event loop blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_user, guild_id, user_id)


def update_balance(guild_id: int, user_id: int, amount: float):
    """Update user balance with retry logic."""
    max_retries = 3
    retry_delay = 0.1

    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=60.0, check_same_thread=False)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=60000')
            c = conn.cursor()
            c.execute('UPDATE users SET balance = balance + ? WHERE guild_id = ? AND user_id = ?',
                      (amount, guild_id, user_id))
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            if 'conn' in locals():
                conn.close()
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))
            else:
                logger.error(f"Failed to update balance after {max_retries} retries: {e}")
                raise


async def update_balance_and_check_trophies(bot, guild_id: int, user_id: int, amount: float):
    """Update balance then check dragon_millionaire trophy on gains."""
    import asyncio
    await asyncio.to_thread(update_balance, guild_id, user_id, amount)
    if amount <= 0:
        return
    try:
        conn = sqlite3.connect(DB_PATH, timeout=60.0)
        c = conn.cursor()
        c.execute('SELECT balance FROM users WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        row = c.fetchone()
        conn.close()
        if row and row[0] >= 1_000_000:
            from achievements import award_trophy
            await award_trophy(bot, guild_id, user_id, 'dragon_millionaire')
    except Exception:
        pass


# ==================== EMBED HELPERS ====================
def validate_embed(embed) -> bool:
    """Validate that an embed meets Discord's limits."""
    if len(embed.fields) > EMBED_MAX_FIELDS:
        return False
    if embed.description and len(embed.description) > EMBED_MAX_DESCRIPTION_LENGTH:
        return False
    if embed.title and len(embed.title) > EMBED_MAX_TITLE_LENGTH:
        return False
    for field in embed.fields:
        if len(field.value) > EMBED_MAX_FIELD_VALUE_LENGTH:
            return False
    return True


def truncate_embed_field(text: str, max_length: int = EMBED_MAX_FIELD_VALUE_LENGTH) -> str:
    """Truncate text to embed limits, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 4] + "..."


# ==================== INPUT VALIDATION ====================
def validate_dragon_count(count: int) -> bool:
    """Validate that a dragon count is positive."""
    return isinstance(count, int) and count > 0


def validate_amount(amount: float) -> bool:
    """Validate that an amount is positive and valid."""
    try:
        return float(amount) > 0 and float(amount) < 999_999_999_999
    except (ValueError, TypeError):
        return False


def validate_dragon_type(dragon_type: str) -> bool:
    """Validate that a dragon type exists."""
    return dragon_type in DRAGON_TYPES


def safe_json_loads(json_str: str, default=None):
    """Safely parse JSON string, return default if invalid."""
    try:
        return json.loads(json_str) if json_str else default
    except (json.JSONDecodeError, TypeError):
        return default


# ==================== ACHIEVEMENTS ====================
from achievements import check_and_award_achievements  # noqa: F401 — re-exported for importers


# ==================== ITEM COST CALCULATION ====================
def calculate_item_cost(user_owned_count: int, base_cost: int) -> int:
    """Calculate shop cost based on how many user already owns (10% increase per item)."""
    multiplier = (1.10 ** user_owned_count)
    return int(base_cost * multiplier)


# ==================== USABLE ITEMS (duplicated from utils to avoid circular import) ====================
from state import active_usable_items as _active_usable_items

def get_active_item(guild_id: int, user_id: int, item_type: str) -> bool:
    """Check if user has an active usable item (time-based)."""
    import time as _time
    if guild_id not in _active_usable_items:
        return False
    if user_id not in _active_usable_items[guild_id]:
        return False
    current_time = int(_time.time())
    expires_at = _active_usable_items[guild_id][user_id].get(item_type)
    if expires_at is None:
        return False
    if current_time >= expires_at:
        del _active_usable_items[guild_id][user_id][item_type]
        return False
    return True


def activate_item(guild_id: int, user_id: int, item_type: str, duration_seconds: int):
    """Activate a time-based item for a user."""
    import time as _time
    if guild_id not in _active_usable_items:
        _active_usable_items[guild_id] = {}
    if user_id not in _active_usable_items[guild_id]:
        _active_usable_items[guild_id][user_id] = {}
    current_time = int(_time.time())
    _active_usable_items[guild_id][user_id][item_type] = current_time + duration_seconds


# ==================== SERVER CONFIG ====================
_SERVER_CONFIG_DEFAULTS = {
    'raids_enabled': 0,
    'raid_times': [8, 16, 20],
    'blackmarket_enabled': 0,
    'blackmarket_interval_hours': 4,
    'blackmarket_max_per_day': 6,
}

def get_server_config(guild_id: int) -> dict:
    """Return server config dict for a guild. Falls back to defaults."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SHORT)
        conn.execute('PRAGMA journal_mode=WAL')
        c = conn.cursor()
        c.execute('''SELECT raids_enabled, raid_times, blackmarket_enabled,
                            blackmarket_interval_hours, blackmarket_max_per_day
                     FROM guild_settings WHERE guild_id = ?''', (guild_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return dict(_SERVER_CONFIG_DEFAULTS)
        import json as _json
        return {
            'raids_enabled': row[0] if row[0] is not None else 0,
            'raid_times': _json.loads(row[1]) if row[1] else [8, 16, 20],
            'blackmarket_enabled': row[2] if row[2] is not None else 0,
            'blackmarket_interval_hours': row[3] if row[3] is not None else 4,
            'blackmarket_max_per_day': row[4] if row[4] is not None else 6,
        }
    except Exception:
        return dict(_SERVER_CONFIG_DEFAULTS)


def update_server_config(guild_id: int, key: str, value) -> bool:
    """Update a single server config value. Creates row if missing."""
    allowed = set(_SERVER_CONFIG_DEFAULTS.keys())
    if key not in allowed:
        return False
    try:
        import json as _json
        if isinstance(value, (list, dict)):
            value = _json.dumps(value)
        conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SHORT)
        conn.execute('PRAGMA journal_mode=WAL')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)', (guild_id,))
        c.execute(f'UPDATE guild_settings SET {key} = ? WHERE guild_id = ?', (value, guild_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"update_server_config error: {e}")
        return False
