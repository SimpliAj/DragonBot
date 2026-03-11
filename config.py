"""
config.py - All constants and data structures for DragonBot.
Extracted verbatim from bot.py (lines 1-942).
"""

import os
import discord
from dotenv import load_dotenv

load_dotenv()

DEV_USER_ID = int(os.getenv('DEV_USER_ID', '774679828594163802'))
ERROR_WEBHOOK_URL = os.getenv('ERROR_WEBHOOK_URL', "")

# ==================== GLOBAL CONSTANTS ====================
DB_PATH = 'dragon_bot.db'
DB_TIMEOUT_SHORT = 30.0
DB_TIMEOUT_MEDIUM = 60.0
DB_TIMEOUT_LONG = 120.0
DB_BUSY_TIMEOUT = 15000
RETRY_MAX_ATTEMPTS = 5
RETRY_DELAY = 0.2

DRAGON_NEST_UPGRADE_COST = 500_000_000
DAILY_REWARD = 500
DRAGONPASS_MAX_LEVEL = 30
RAID_DURATION_MINUTES = 30
DRAGON_NEST_ACTIVATION_HOURS = 3
BINGO_CARD_DAYS = 7
ENABLE_TOPGG_VOTE_QUEST = False  # Toggle voting quest feature

EMBED_COLOR_SUCCESS = discord.Color.green()
EMBED_COLOR_ERROR = discord.Color.red()
EMBED_COLOR_INFO = discord.Color.blue()
EMBED_COLOR_WARNING = discord.Color.orange()
EMBED_COLOR_PRIMARY = discord.Color.from_rgb(88, 101, 242)
EMBED_COLOR_SECONDARY = discord.Color.gold()

EMBED_MAX_FIELDS = 25
EMBED_MAX_FIELD_VALUE_LENGTH = 4096
EMBED_MAX_DESCRIPTION_LENGTH = 4096
EMBED_MAX_TITLE_LENGTH = 256

# ==================== DRAGON TYPE MAPPING ====================
DRAGON_TYPE_MAPPING = {
    'babyfiredragon': 'stone',
    'babyforrestdragon': 'ember',
    'babyhoneydragon': 'frost',
    'amethyst': 'storm',
    'chubbydragon': 'ocean',
    'skydragon': 'nature',
    'crystal': 'crystal',
    'diamond': 'diamond',
    'emerald': 'emerald',
    'gold': 'gold',
    'iron': 'iron',
    'obsidian': 'obsidian',
    'platinum': 'platinum',
    'primordial': 'primordial',
    'ruby': 'ruby',
    'sapphire': 'sapphire',
    'silver': 'silver',
    'storm': 'storm',
    'topaz': 'topaz',
    'void': 'void',
    'toothless': 'void',
    'lightfury': 'cosmic',
    'ohnezahn': 'primordial',
    'tagschatten': 'cosmic',
}

# ==================== DRAGON TYPES ====================
DRAGON_TYPES = {
    # Common Elements
    'stone': {'name': 'Baby Fire', 'emoji': '<:babyfiredragon:1446205107472564346>', 'image': 'https://i.imgur.com/v09t89A.png', 'spawn_chance': 27.75, 'value': 4.11, 'catch_weight': 1260},
    'ember': {'name': 'Baby Forest', 'emoji': '<:babyforrestdragon:1446205128167260291>', 'image': 'https://i.imgur.com/CZaYIRJ.png', 'spawn_chance': 20.80, 'value': 5.48, 'catch_weight': 942},
    'frost': {'name': 'Baby Honey', 'emoji': '<:babyhoneydragon:1446205149264478399>', 'image': 'https://i.imgur.com/b1EZm1Q.png', 'spawn_chance': 13.87, 'value': 8.22, 'catch_weight': 628},
    # Uncommon Elements
    'storm': {'name': 'Amethyst', 'emoji': '<:amethyst:1446206754139410545>', 'image': 'https://i.imgur.com/c96bACU.png', 'spawn_chance': 9.25, 'value': 11.74, 'catch_weight': 419},
    'ocean': {'name': 'Chubby', 'emoji': '<:chubbydragon:1446206779129335858>', 'image': 'https://i.imgur.com/6LMijx6.png', 'spawn_chance': 7.28, 'value': 14.94, 'catch_weight': 329},
    'nature': {'name': 'Sky', 'emoji': '<:skydragon:1446206801539371108>', 'image': 'https://i.imgur.com/0QGx7vH.png', 'spawn_chance': 6.08, 'value': 17.86, 'catch_weight': 275},
    # Rare Gems
    'amethyst': {'name': 'Friendly', 'emoji': '<:friendly:1446208307080597504>', 'image': 'https://i.imgur.com/Qb5fixC.png', 'spawn_chance': 5.28, 'value': 20.54, 'catch_weight': 450},
    'topaz': {'name': 'Candy', 'emoji': '<:candyd:1446215122228871310>', 'image': 'https://i.imgur.com/7VXLd3F.png', 'spawn_chance': 4.62, 'value': 23.47, 'catch_weight': 390},
    'ruby': {'name': 'Mossy', 'emoji': '<:mossyd:1446215099411992828>', 'image': 'https://i.imgur.com/2jtF596.png', 'spawn_chance': 3.97, 'value': 27.39, 'catch_weight': 330},
    'sapphire': {'name': 'Chinese', 'emoji': '<:cndrag:1446215073583333511>', 'image': 'https://i.imgur.com/FTd3yyD.png', 'spawn_chance': 3.31, 'value': 32.86, 'catch_weight': 275},
    # Epic Metals
    'iron': {'name': 'UwU', 'emoji': '<:uwu:1446211083017912473>', 'image': 'https://i.imgur.com/AlYgTEA.png', 'spawn_chance': 2.43, 'value': 41.08, 'catch_weight': 200},
    'silver': {'name': 'Mew', 'emoji': '<:mewdragon:1446211865956061245>', 'image': 'https://i.imgur.com/8QBL13V.png', 'spawn_chance': 1.94, 'value': 51.35, 'catch_weight': 160},
    # Legendary Gems
    'emerald': {'name': 'E-Girl', 'emoji': '<:egirl:1446210298045403340>', 'image': 'https://i.imgur.com/5UGlWW8.png', 'spawn_chance': 1.10, 'value': 82.16, 'catch_weight': 110},
    'diamond': {'name': 'Hungry', 'emoji': '<:hungry:1446210325014777867>', 'image': 'https://i.imgur.com/efhEn4V.png', 'spawn_chance': 0.77, 'value': 117.37, 'catch_weight': 77},
    'obsidian': {'name': 'Nogard', 'emoji': '<:nogard:1446210350155567174>', 'image': 'https://i.imgur.com/KEYKXmj.png', 'spawn_chance': 0.55, 'value': 164.32, 'catch_weight': 55},
    # Mythic Precious
    'gold': {'name': 'Ember', 'emoji': '<:emberd:1446216735731617904>', 'image': 'https://i.imgur.com/ZpyOgLf.png', 'spawn_chance': 0.31, 'value': 205.4, 'catch_weight': 14},
    'platinum': {'name': 'Emerald', 'emoji': '<:emeraldd:1446217302105264218>', 'image': 'https://i.imgur.com/t8v7K7n.png', 'spawn_chance': 0.25, 'value': 273.87, 'catch_weight': 11},
    'crystal': {'name': 'Shadow', 'emoji': '<:shadwod:1446217327162167477>', 'image': 'https://i.imgur.com/ujpeJpg.png', 'spawn_chance': 0.19, 'value': 410.8, 'catch_weight': 9},
    # Ultra Rare
    'celestial': {'name': 'Lightfury', 'emoji': '<:lightfury:1446213988949168168>', 'image': 'https://i.imgur.com/FAK8Y2E.png', 'spawn_chance': 0.11, 'value': 513.5, 'catch_weight': 5},
    'void': {'name': 'Toothless', 'emoji': '<:toothless:1446213965326844015>', 'image': 'https://i.imgur.com/STFG0fg.png', 'spawn_chance': 0.09, 'value': 821.6, 'catch_weight': 4},
    'cosmic': {'name': 'Tagschatten', 'emoji': '<:tagschatten:1446213943239512147>', 'image': 'https://i.imgur.com/5MQz8j3.png', 'spawn_chance': 0.06, 'value': 1369.33, 'catch_weight': 3},
    'primordial': {'name': 'Ohnezahn', 'emoji': '<:ohnezahn:1446213919654940805>', 'image': 'https://i.imgur.com/MFaIjiM.png', 'spawn_chance': 0.04, 'value': 2054, 'catch_weight': 2}
}

# ==================== LEVEL SYSTEM ====================
LEVEL_NAMES = {
    0: "Hatchling", 1: "Wyrmling", 2: "Drake", 3: "Wyvern", 4: "Guardian",
    5: "Elder", 6: "Ancient", 7: "Wyrm Lord", 8: "Dragon King",
    9: "Overlord", 10: "Primordial"
}

LEVEL_CHARACTERS = {
    0: "None",
    1: "Ember (Young Fire Drake)",
    2: "Frostbite (Ice Wyrmling)",
    3: "Thunderclaw (Storm Guardian)",
    4: "Ironscale (Metal Warden)",
    5: "Obsidiana (Shadow Elder)",
    6: "Crystalwing (Ancient Sage)",
    7: "Voidheart (Wyrm of Darkness)",
    8: "Solarius (Golden King)",
    9: "Cosmothor (Celestial Overlord)",
    10: "Azathoth (The First Dragon)"
}

LEVEL_LORE = {
    0: ("Your journey begins in silence. An empty nest awaits your touch, bare stone walls echoing with potential. "
         "The ancient magic that once flowed through this place has faded, leaving behind only whispers of forgotten power. "
         "You stand at the threshold between the mundane world and the realm of dragons. "
         "Your task is simple yet monumental: seek out dragons, understand them, and bring them to this sanctuary. "
         "Every catch, every encounter will breathe life back into these hollow walls."),

    1: ("Your first dragon arrives in a burst of golden flame. Ember, a Wyrmling of pure fire and innocence, touches down "
         "in your nest. The moment is transcendent—this small, warm creature fills the empty space with unprecedented vitality. "
         "Ember's presence rekindles the ancient bonds between dragon and keeper. Your nest is no longer silent; it hums with "
         "newfound warmth and purpose. You have taken your first step on the path of the Dragon Keeper, and Ember will be your "
         "faithful companion through the trials to come. Together, you will learn the language of dragons."),

    2: ("A second dragon joins your growing family. Frostbite arrives in a swirl of crystalline ice and ancient mystery. "
         "Where Ember brings fire and passion, Frostbite brings calm, logic, and the weight of winters past. Together, these two "
         "dragons teach you a fundamental truth: balance is the key to power. Ember's warmth tempers Frostbite's cold, and "
         "Frostbite's wisdom guides Ember's wild nature. Your nest transforms into a place of harmony, where elemental forces dance "
         "in perfect equilibrium. The walls begin to glow faintly, responding to the dragon energy within."),

    3: ("The Drake stage awakens. Thunderclaw arrives with the fury of a thousand storms, his scales crackling with barely contained "
         "electricity. This is no longer a gentle journey—you have attracted a dragon of formidable power and volatile nature. "
         "Thunderclaw teaches you the price of ambition and the responsibility that comes with commanding such forces. His presence "
         "energizes your entire nest, causing the very air to buzz with potential. You are no longer a novice keeper; you are beginning "
         "to understand the true scope of what you are building. Your nest has become a sanctum of power."),

    4: ("A Guardian manifests. Ironscale emerges not with fanfare or fury, but with quiet, immovable strength. This ancient dragon "
         "has witnessed ages pass and carries the weight of eons in every scale. Ironscale's presence settles over your nest like "
         "an impenetrable fortress, protecting all within from harm. Your nest is now fortified beyond measure—no external force can "
         "shake what you have built. Ironscale becomes the anchor of your sanctuary, the foundation upon which all other dragons rest. "
         "You understand now that true power is not about dominance, but protection."),

    5: ("You transcend into the Elder stage. Obsidiana appears, not in daylight, but when shadows grow long and secrets stir. "
         "This dragon of shadow and forbidden knowledge unlocks pathways in your mind you never knew existed. Obsidiana does not teach "
         "through warmth or strength, but through revelation and understanding of hidden truths. Your nest transforms, becoming a place "
         "where the boundary between worlds grows thin. You feel ancient knowledge flowing through your veins, and your perceptions expand "
         "to encompass realms few mortals ever perceive. You have become something more than mortal—you are an Elder Keeper, privy to "
         "mysteries most would fear to know."),

    6: ("Wisdom takes form in Crystalwing, a dragon whose very existence is ancient magic given shape. Her crystalline wings refract "
         "light in impossible ways, revealing pathways through the aether itself. Crystalwing guides you through secrets lost since the "
         "Age of Creation, teaching you languages spoken only by gods and dragons. Your nest becomes a beacon, visible to creatures of "
         "magic from across all realms. You begin to understand your true role—you are not merely a keeper, but a keeper of keepers, a "
         "guardian of knowledge itself. The distinction between your consciousness and your nest's energy grows blurred, until you cannot "
         "tell where one ends and the other begins."),

    7: ("The Wyrm Lord stage is attained. From the spaces between stars and the depths of cosmic voids, Voidheart manifests. "
         "This being is less dragon than force of nature—a fragment of the void made flesh. Voidheart's presence expands your nest beyond "
         "physical dimensions, creating pockets of space where reality itself bends. You understand now that time and distance are merely "
         "suggestions. Your nest exists in multiple places simultaneously, a nexus point where all worlds touch. Voidheart teaches you to "
         "fear nothing, for you have already gazed into the abyss and found it familiar. Your power rivals that of legendary heroes."),

    8: ("Coronation. Solarius descends upon your nest in a pillar of pure golden light, and as his radiance spreads, you are crowned "
         "Dragon King. This is no ordinary honor—it is a fundamental shift in the order of the world. Solarius's light burns away all "
         "doubt and weakness, leaving only clarity and divine purpose. Your nest becomes a kingdom, recognized and revered by all who see it. "
         "Mortals speak your name in hushed tones. Dragons from distant lands journey to pledge their loyalty. You are no longer a seeker "
         "of dragons—you are their sovereign, their absolute ruler, their destiny made manifest."),

    9: ("You rise to the rank of Overlord as Cosmothor descends from realms beyond imagination. This celestial being bends the very fabric "
         "of reality around you, granting you dominion over forces that casual mortals cannot comprehend. Stars orbit your nest. Galaxies "
         "dance at your command. You have transcended the limitations of mortality itself. Cosmothor shows you visions of infinite possibility—"
         "futures you can shape, timelines you can reshape. The distinction between your will and fate itself dissolves. You are becoming "
         "something divine, something eternal, something fundamentally different from what you once were."),

    10: ("The Primordial stage is reached. Azathoth, The First Dragon, the ancient being from which all dragonkind descended, finally "
          "recognizes you as worthy. This dragon, older than mountains, deeper than oceans, more vast than the sky itself, bows before you. "
          "In that moment, you understand everything—the origin of dragons, the purpose of creation, the fundamental nature of existence. "
          "Your nest is no longer a structure of stone and magic; it is a living embodiment of creation itself. You have achieved what no "
          "mortal was meant to achieve. You are the Primordial Keeper, eternal and infinite, forever changed by the touch of Azathoth. "
          "Your legend will endure until the stars grow cold and the worlds crumble to dust.")
}

LEVEL_THUMBNAILS = {
    0: "https://i.imgur.com/v09t89A.png",
    1: "https://i.imgur.com/CZaYIRJ.png",
    2: "https://i.imgur.com/b1EZm1Q.png",
    3: "https://i.imgur.com/c96bACU.png",
    4: "https://i.imgur.com/6LMijx6.png",
    5: "https://i.imgur.com/0QGx7vH.png",
    6: "https://i.imgur.com/Qb5fixC.png",
    7: "https://i.imgur.com/7VXLd3F.png",
    8: "https://i.imgur.com/ZpyOgLf.png",
    9: "https://i.imgur.com/t8v7K7n.png",
    10: "https://i.imgur.com/MFaIjiM.png"
}

LEVEL_XP_REQUIREMENTS = {
    1: 0, 2: 100, 3: 250, 4: 500, 5: 1000,
    6: 2000, 7: 3500, 8: 5500, 9: 8000, 10: 12000
}

# ==================== RARITY TIERS ====================
DRAGON_RARITY_TIERS = {
    'common': ['stone', 'ember', 'frost'],
    'uncommon': ['storm', 'ocean', 'nature'],
    'rare': ['amethyst', 'topaz', 'ruby', 'sapphire'],
    'epic': ['iron', 'silver'],
    'legendary': ['emerald', 'diamond', 'obsidian'],
    'mythic': ['gold', 'platinum', 'crystal'],
    'ultra': ['celestial', 'void', 'cosmic', 'primordial']
}

# ==================== BREEDING SYSTEM ====================
BREEDING_CHANCES = {
    # (parent1_rarity, parent2_rarity): {result_rarity: chance%}
    # Fail % scales UP with rarity (higher rarity = higher risk)
    ('common', 'common'):         {'fail':  5, 'common': 25, 'uncommon': 55, 'rare': 15},
    ('common', 'uncommon'):       {'fail':  8, 'uncommon': 20, 'rare': 57, 'epic': 15},
    ('common', 'rare'):           {'fail': 10, 'rare': 20, 'epic': 55, 'legendary': 15},
    ('common', 'epic'):           {'fail': 12, 'epic': 15, 'legendary': 53, 'mythic': 20},
    ('common', 'legendary'):      {'fail': 15, 'legendary': 10, 'mythic': 38, 'ultra': 37},
    ('common', 'mythic'):         {'fail': 18, 'mythic': 10, 'ultra': 72},
    ('common', 'ultra'):          {'fail': 20, 'ultra': 80},
    ('uncommon', 'uncommon'):     {'fail': 10, 'uncommon': 20, 'rare': 55, 'epic': 15},
    ('uncommon', 'rare'):         {'fail': 12, 'rare': 20, 'epic': 53, 'legendary': 15},
    ('uncommon', 'epic'):         {'fail': 15, 'epic': 15, 'legendary': 48, 'mythic': 22},
    ('uncommon', 'legendary'):    {'fail': 18, 'legendary': 10, 'mythic': 42, 'ultra': 30},
    ('uncommon', 'mythic'):       {'fail': 22, 'mythic': 12, 'ultra': 66},
    ('uncommon', 'ultra'):        {'fail': 25, 'ultra': 75},
    ('rare', 'rare'):             {'fail': 15, 'rare': 17, 'epic': 48, 'legendary': 20},
    ('rare', 'epic'):             {'fail': 18, 'epic': 20, 'legendary': 47, 'mythic': 15},
    ('rare', 'legendary'):        {'fail': 20, 'legendary': 15, 'mythic': 45, 'ultra': 20},
    ('rare', 'mythic'):           {'fail': 25, 'mythic': 15, 'ultra': 60},
    ('rare', 'ultra'):            {'fail': 28, 'ultra': 72},
    ('epic', 'epic'):             {'fail': 20, 'epic': 15, 'legendary': 45, 'mythic': 20},
    ('epic', 'legendary'):        {'fail': 22, 'legendary': 15, 'mythic': 43, 'ultra': 20},
    ('epic', 'mythic'):           {'fail': 25, 'mythic': 18, 'ultra': 57},
    ('epic', 'ultra'):            {'fail': 30, 'ultra': 70},
    ('legendary', 'legendary'):   {'fail': 25, 'legendary': 15, 'mythic': 35, 'ultra': 25},
    ('legendary', 'mythic'):      {'fail': 28, 'mythic': 20, 'ultra': 52},
    ('legendary', 'ultra'):       {'fail': 32, 'ultra': 68},
    ('mythic', 'mythic'):         {'fail': 30, 'mythic': 17, 'ultra': 53},
    ('mythic', 'ultra'):          {'fail': 35, 'mythic': 10, 'ultra': 55},
    ('ultra', 'ultra'):           {'fail': 40, 'ultra': 60},
}

BREEDING_COOLDOWNS = {
    'common': 30 * 60,      # 30 minutes
    'uncommon': 45 * 60,    # 45 minutes
    'rare': 60 * 60,        # 1 hour
    'epic': 90 * 60,        # 1.5 hours
    'legendary': 120 * 60,  # 2 hours
    'mythic': 150 * 60,     # 2.5 hours
    'ultra': 180 * 60       # 3 hours
}

BREEDING_XP_COSTS = {
    'common': 500,
    'uncommon': 1000,
    'rare': 1500,
    'epic': 2500,
    'legendary': 4000,
    'mythic': 6000,
    'ultra': 10000
}

BREEDING_LEVEL_THRESHOLDS = {
    1: 0, 2: 500, 3: 1500, 4: 3000, 5: 5000,
    6: 7500, 7: 10500, 8: 14000, 9: 18000, 10: 23000,
    11: 28000, 12: 34000, 13: 41000, 14: 49000, 15: 58000,
    20: 100000
}

BREEDING_QUEUE_SLOTS = {
    1: 1,    # Levels 1-4: 1 slot
    5: 2,    # Levels 5-9: 2 slots
    10: 3,   # Levels 10-14: 3 slots
    15: 4    # Levels 15+: 4 slots
}

BREEDING_XP_GAINS = {
    'success': 50,
    'fail': 20
}

DNA_BREAK_CHANCES = {
    'common': 5,        # 5% break chance
    'uncommon': 10,     # 10% break chance
    'rare': 15,         # 15% break chance
    'epic': 25,         # 25% break chance
    'legendary': 35,    # 35% break chance
    'mythic': 42,       # 42% break chance
    'ultra': 50         # 50% break chance
}

def normalize_dragon_type(dragon_input: str) -> str:
    """Convert old dragon names or emoji IDs to standard dragon type keys."""
    if dragon_input in DRAGON_TYPES:
        return dragon_input
    if dragon_input in DRAGON_TYPE_MAPPING:
        return DRAGON_TYPE_MAPPING[dragon_input]
    for key, data in DRAGON_TYPES.items():
        if dragon_input in data.get('emoji', ''):
            return key
    return dragon_input

# ==================== ADVENTURE SYSTEM ====================
ADVENTURE_TYPES = {
    'exploration': {
        'duration': 1 * 3600,  # 1 hour cooldown
        'success_rate': 0.90,  # 90% success, 10% fail
        'rewards': {'coins': (100, 300), 'dragon_chance': 0.15, 'item_chance': 0.08},
        'emoji': '🗺️'
    },
    'treasure_hunt': {
        'duration': 2 * 3600,  # 2 hour cooldown
        'success_rate': 0.80,  # 80% success, 20% fail
        'rewards': {'coins': (400, 800), 'dragon_chance': 0.25, 'item_chance': 0.12},
        'emoji': '💰'
    },
    'dragon_raid': {
        'duration': 3 * 3600,  # 3 hour cooldown
        'success_rate': 0.70,  # 70% success, 30% fail
        'rewards': {'coins': (1000, 2000), 'dragon_chance': 0.35, 'item_chance': 0.15},
        'emoji': '⚔️'
    },
    'legendary_quest': {
        'duration': 6 * 3600,  # 6 hour cooldown
        'success_rate': 0.60,  # 60% success, 40% fail
        'rewards': {'coins': (2000, 4000), 'dragon_chance': 0.50, 'item_chance': 0.20},
        'emoji': '🏆'
    }
}

# Adventure item rewards
ADVENTURE_ITEMS = {
    'dragonscale': {'name': 'Dragonscale', 'emoji': '🟪', 'min_duration': 1, 'max_duration': 5},  # 1-5 minutes
    'lucky_charm': {'name': 'Lucky Charm', 'emoji': '🍀', 'min_duration': 30, 'max_duration': 30},  # 30 minutes
}

# New Usable Items (Active use, time-based)
USABLE_ITEMS = {
    'night_vision': {'name': 'Night Vision', 'emoji': '🌙', 'rarity': 'legendary', 'duration': 30 * 60, 'effect': '+50% rarity (20:00-08:00 only, once per night)', 'shop_cost': 750},
    'lucky_dice': {'name': 'Lucky Dice', 'emoji': '🎰', 'rarity': 'rare', 'duration': 30 * 60, 'effect': '+10% casino/gamble win chance', 'shop_cost': 300},
}

# Passive Enchanter Items (Always active when owned)
PASSIVE_ITEMS = {
    'knowledge_book': {'name': 'Knowledge Book', 'emoji': '📚', 'rarity': 'rare', 'effect': '+2% catch success per book', 'stack': True, 'base_cost': 5000},
    'precision_stone': {'name': 'Precision Stone', 'emoji': '🎯', 'rarity': 'legendary', 'effect': '+5% raid boss damage per stone (stackable)', 'stack': True, 'base_cost': 12500},
}

def calculate_item_cost(user_owned_count: int, base_cost: int) -> int:
    """Calculate shop cost based on how many user already owns"""
    multiplier = (1.10 ** user_owned_count)
    return int(base_cost * multiplier)

# Black Market settings
BLACK_MARKET_SPAWN_INTERVAL = 4 * 60 * 60  # 4 hours
BLACK_MARKET_DURATION = 30 * 60  # 30 minutes
BLACK_MARKET_ITEMS = {
    'pack_wooden': {'name': 'Wooden Pack', 'shop_price': 500, 'black_price': 375, 'emoji': '<:woodenchest:1446170002708238476>', 'type': 'pack'},
    'pack_stone': {'name': 'Stone Pack', 'shop_price': 1000, 'black_price': 750, 'emoji': '<:stonechest:1446169958265389247>', 'type': 'pack'},
    'pack_bronze': {'name': 'Bronze Pack', 'shop_price': 1500, 'black_price': 1125, 'emoji': '<:bronzechest:1446169758599745586>', 'type': 'pack'},
    'dna_sample': {'name': 'DNA Sample', 'shop_price': 12500, 'black_price': 9375, 'emoji': '🧬', 'type': 'item'},
    'lucky_charm': {'name': 'Lucky Charm', 'shop_price': 15000, 'black_price': 11250, 'emoji': '🍀', 'type': 'item'},
    'lucky_dice': {'name': 'Lucky Dice', 'shop_price': 10000, 'black_price': 7500, 'emoji': '🎰', 'type': 'item'},
    'night_vision': {'name': 'Night Vision', 'shop_price': 50000, 'black_price': 37500, 'emoji': '🌙', 'type': 'item'},
}

LEVEL_BOUNTY_DIFFICULTY = {
    0: 1, 1: 1, 2: 1, 3: 2, 4: 2, 5: 2,
    6: 3, 7: 3, 8: 3, 9: 3, 10: 3
}

# ==================== ACHIEVEMENTS ====================
ACHIEVEMENTS = {
    # ===== CATCHING ACHIEVEMENTS =====
    'catch_1': {'name': 'First Steps', 'description': 'Catch your first dragon', 'category': '🐉 Catching', 'requirement': 1, 'reward_coins': 10, 'icon': '🥚'},
    'catch_10': {'name': 'Dragon Hunter', 'description': 'Catch 10 dragons', 'category': '🐉 Catching', 'requirement': 10, 'reward_coins': 50, 'icon': '🐉'},
    'catch_50': {'name': 'Dragon Master', 'description': 'Catch 50 dragons', 'category': '🐉 Catching', 'requirement': 50, 'reward_coins': 200, 'icon': '🔥'},
    'catch_100': {'name': 'Dragon Lord', 'description': 'Catch 100 dragons', 'category': '🐉 Catching', 'requirement': 100, 'reward_coins': 500, 'icon': '👑'},
    'catch_250': {'name': 'Dragon God', 'description': 'Catch 250 dragons', 'category': '🐉 Catching', 'requirement': 250, 'reward_coins': 1500, 'icon': '⚡'},
    'catch_500': {'name': 'Dragon Deity', 'description': 'Catch 500 dragons', 'category': '🐉 Catching', 'requirement': 500, 'reward_coins': 3000, 'icon': '👹'},
    'catch_1000': {'name': 'Dragon Legend', 'description': 'Catch 1000 dragons', 'category': '🐉 Catching', 'requirement': 1000, 'reward_coins': 5000, 'icon': '✨'},

    # ===== RARITY ACHIEVEMENTS =====
    'first_uncommon': {'name': 'Uncommon Finder', 'description': 'Catch your first Uncommon dragon', 'category': '⭐ Rarity', 'requirement': 1, 'reward_coins': 30, 'icon': '🟢'},
    'first_rare': {'name': 'Rare Hunter', 'description': 'Catch your first Rare dragon', 'category': '⭐ Rarity', 'requirement': 1, 'reward_coins': 100, 'icon': '🔵'},
    'first_epic': {'name': 'Epic Seeker', 'description': 'Catch your first Epic dragon', 'category': '⭐ Rarity', 'requirement': 1, 'reward_coins': 200, 'icon': '🟣'},
    'first_legendary': {'name': 'Legendary Hunter', 'description': 'Catch your first Legendary dragon', 'category': '⭐ Rarity', 'requirement': 1, 'reward_coins': 300, 'icon': '💎'},
    'first_mythic': {'name': 'Mythic Seeker', 'description': 'Catch your first Mythic dragon', 'category': '⭐ Rarity', 'requirement': 1, 'reward_coins': 500, 'icon': '🌟'},
    'first_ultra': {'name': 'Cosmic Explorer', 'description': 'Catch your first Ultra Rare dragon', 'category': '⭐ Rarity', 'requirement': 1, 'reward_coins': 1000, 'icon': '🌌'},

    # ===== COLLECTION ACHIEVEMENTS =====
    'collector_5': {'name': 'Collector Starter', 'description': 'Collect 5 different dragon types', 'category': '📚 Collection', 'requirement': 5, 'reward_coins': 50, 'icon': '📖'},
    'collector_10': {'name': 'Rookie Collector', 'description': 'Collect 10 different dragon types', 'category': '📚 Collection', 'requirement': 10, 'reward_coins': 150, 'icon': '📚'},
    'collector_15': {'name': 'Dragon Scholar', 'description': 'Collect 15 different dragon types', 'category': '📚 Collection', 'requirement': 15, 'reward_coins': 300, 'icon': '🎓'},
    'collector_all': {'name': 'Master Collector', 'description': 'Collect all 22 dragon types', 'category': '📚 Collection', 'requirement': 22, 'reward_coins': 1000, 'icon': '🏆'},

    # ===== WEALTH ACHIEVEMENTS =====
    'rich_1k': {'name': 'Getting Rich', 'description': 'Accumulate 1,000 coins', 'category': '💰 Wealth', 'requirement': 1000, 'reward_coins': 50, 'icon': '💰'},
    'rich_10k': {'name': 'Dragon Tycoon', 'description': 'Accumulate 10,000 coins', 'category': '💰 Wealth', 'requirement': 10000, 'reward_coins': 300, 'icon': '💵'},
    'rich_100k': {'name': 'Millionaire Wannabe', 'description': 'Accumulate 100,000 coins', 'category': '💰 Wealth', 'requirement': 100000, 'reward_coins': 1000, 'icon': '💎'},
    'rich_1m': {'name': 'Dragon Millionaire', 'description': 'Accumulate 1,000,000 coins', 'category': '💰 Wealth', 'requirement': 1000000, 'reward_coins': 3000, 'icon': '👑'},
    'rich_10m': {'name': 'Mega Millionaire', 'description': 'Accumulate 10,000,000 coins', 'category': '💰 Wealth', 'requirement': 10000000, 'reward_coins': 5000, 'icon': '🤑'},
    'rich_100m': {'name': 'Ultra Billionaire', 'description': 'Accumulate 100,000,000 coins', 'category': '💰 Wealth', 'requirement': 100000000, 'reward_coins': 10000, 'icon': '💸'},
    'rich_500m': {'name': 'Supreme Dragon Lord', 'description': 'Accumulate 500,000,000 coins', 'category': '💰 Wealth', 'requirement': 500000000, 'reward_coins': 15000, 'icon': '🏰'},

    # ===== BREEDING ACHIEVEMENTS =====
    'breeder_1': {'name': 'First Breeder', 'description': 'Breed your first dragon', 'category': '🥚 Breeding', 'requirement': 1, 'reward_coins': 100, 'icon': '🥚'},
    'breeder_5': {'name': 'Experienced Breeder', 'description': 'Breed 5 dragons', 'category': '🥚 Breeding', 'requirement': 5, 'reward_coins': 300, 'icon': '🐣'},
    'breeder_10': {'name': 'Dragon Breeder', 'description': 'Breed 10 dragons', 'category': '🥚 Breeding', 'requirement': 10, 'reward_coins': 500, 'icon': '🐉🥚'},

    # ===== ALPHA ACHIEVEMENTS =====
    'alpha_1': {'name': 'Alpha Creator', 'description': 'Craft your first Alpha Dragon', 'category': '✨ Alpha', 'requirement': 1, 'reward_coins': 300, 'icon': '✨'},
    'alpha_5': {'name': 'Alpha Master', 'description': 'Craft 5 Alpha Dragons', 'category': '✨ Alpha', 'requirement': 5, 'reward_coins': 1000, 'icon': '🌟'},

    # ===== TRADING ACHIEVEMENTS =====
    'trader_1': {'name': 'First Trade', 'description': 'Complete your first trade', 'category': '🤝 Trading', 'requirement': 1, 'reward_coins': 50, 'icon': '🤝'},
    'trader_5': {'name': 'Merchant', 'description': 'Complete 5 trades', 'category': '🤝 Trading', 'requirement': 5, 'reward_coins': 200, 'icon': '🏪'},
    'trader_10': {'name': 'Trade Master', 'description': 'Complete 10 trades', 'category': '🤝 Trading', 'requirement': 10, 'reward_coins': 500, 'icon': '💼'},

    # ===== DRAGON NEST ACHIEVEMENTS =====
    'nest_level_5': {'name': 'Nest Guardian', 'description': 'Reach Dragon Nest Level 5', 'category': '🏰 Dragon Nest', 'requirement': 5, 'reward_coins': 300, 'icon': '🏰'},
    'nest_level_10': {'name': 'Nest Master', 'description': 'Reach Dragon Nest Level 10 (Max)', 'category': '🏰 Dragon Nest', 'requirement': 10, 'reward_coins': 1500, 'icon': '👑'},

    # ===== DAILY REWARDS ACHIEVEMENTS =====
    'daily_7': {'name': 'Dedicated', 'description': 'Claim daily reward 7 days in a row', 'category': '📅 Dedication', 'requirement': 7, 'reward_coins': 150, 'icon': '📅'},
    'daily_14': {'name': 'Very Dedicated', 'description': 'Claim daily reward 14 days in a row', 'category': '📅 Dedication', 'requirement': 14, 'reward_coins': 300, 'icon': '📆'},
    'daily_30': {'name': 'Devoted', 'description': 'Claim daily reward 30 days in a row', 'category': '📅 Dedication', 'requirement': 30, 'reward_coins': 1000, 'icon': '🗓️'},
    'daily_100': {'name': 'Loyal Companion', 'description': 'Claim daily reward 100 days in a row', 'category': '📅 Dedication', 'requirement': 100, 'reward_coins': 2000, 'icon': '💝'},
}

# ==================== DRAGON NEST UPGRADE SYSTEM ====================
LEVEL_COSTS = {
    1: 2, 2: 2, 3: 3, 4: 3, 5: 3,
    6: 4, 7: 6, 8: 8, 9: 12, 10: 24
}

PERK_RARITY_WEIGHTS = {
    1: {'common': 0.70, 'uncommon': 0.25, 'rare': 0.05, 'epic': 0, 'legendary': 0},
    2: {'common': 0.64, 'uncommon': 0.25, 'rare': 0.10, 'epic': 0.01, 'legendary': 0},
    3: {'common': 0.57, 'uncommon': 0.25, 'rare': 0.15, 'epic': 0.02, 'legendary': 0.01},
    4: {'common': 0.48, 'uncommon': 0.30, 'rare': 0.15, 'epic': 0.05, 'legendary': 0.02},
    5: {'common': 0.40, 'uncommon': 0.30, 'rare': 0.20, 'epic': 0.06, 'legendary': 0.04},
    6: {'common': 0.30, 'uncommon': 0.30, 'rare': 0.20, 'epic': 0.12, 'legendary': 0.08},
    7: {'common': 0.20, 'uncommon': 0.30, 'rare': 0.25, 'epic': 0.15, 'legendary': 0.10},
    8: {'common': 0.15, 'uncommon': 0.20, 'rare': 0.30, 'epic': 0.20, 'legendary': 0.15},
    9: {'common': 0.05, 'uncommon': 0.10, 'rare': 0.35, 'epic': 0.30, 'legendary': 0.20},
    10: {'common': 0, 'uncommon': 0.05, 'rare': 0.35, 'epic': 0.35, 'legendary': 0.25}
}

PERKS_POOL = {
    'common': [
        {'id': 'lucky_catcher_1', 'name': 'Lucky Catcher', 'effect': '5% chance of doubling dragons on catch', 'value': 0.05, 'type': 'lucky'},
        {'id': 'gambling_catcher_1', 'name': 'Gambling Catcher', 'effect': '3% triple, 1.5% lose all', 'value': 0.03, 'penalty': 0.015, 'type': 'gambling'},
        {'id': 'pack_wooden_1', 'name': 'Pack Catcher - Wooden', 'effect': '1.5% chance wooden pack on catch', 'value': 0.015, 'type': 'pack', 'pack_tier': 'wooden'},
        {'id': 'pack_stone_1', 'name': 'Pack Catcher - Stone', 'effect': '1% chance stone pack on catch', 'value': 0.01, 'type': 'pack', 'pack_tier': 'stone'},
        {'id': 'pack_bronze_1', 'name': 'Pack Catcher - Bronze', 'effect': '0.75% chance bronze pack on catch', 'value': 0.0075, 'type': 'pack', 'pack_tier': 'bronze'},
        {'id': 'pack_silver_1', 'name': 'Pack Catcher - Silver', 'effect': '0.5% chance silver pack on catch', 'value': 0.005, 'type': 'pack', 'pack_tier': 'silver'},
        {'id': 'pack_gold_1', 'name': 'Pack Catcher - Gold', 'effect': '0.25% chance gold pack on catch', 'value': 0.0025, 'type': 'pack', 'pack_tier': 'gold'},
        {'id': 'pack_platinum_1', 'name': 'Pack Catcher - Platinum', 'effect': '0.125% chance platinum pack on catch', 'value': 0.00125, 'type': 'pack', 'pack_tier': 'platinum'},
        {'id': 'purrcise_catcher', 'name': 'Purrcise Catcher', 'effect': '2% chance to catch +1 extra dragon', 'value': 0.02, 'type': 'perfect'},
        {'id': 'time_manip_1', 'name': 'Time Manipulator', 'effect': '1% chance +5min dragonscale', 'value': 0.01, 'type': 'time'},
        {'id': 'speedrunner_1', 'name': 'Speedrunner', 'effect': 'First 8 dragons per level always double', 'value': 8, 'type': 'speedrun'},
        {'id': 'coin_grinder_1', 'name': 'Coin Grinder', 'effect': '+2% coins from catch', 'value': 0.02, 'type': 'coins'},
        {'id': 'rarity_boost_1', 'name': 'Rarity Booster', 'effect': '3% chance rarity +1', 'value': 0.03, 'type': 'rarity'},
        {'id': 'dragon_counter_1', 'name': 'Dragon Counter', 'effect': '+3 bonus dragons every 10 catches', 'value': 3, 'type': 'counter'},
        {'id': 'lucky_streak_1', 'name': 'Lucky Streak', 'effect': '2x bonus on streaks of 5+ same dragon', 'value': 0.02, 'type': 'streak'},
    ],
    'uncommon': [
        {'id': 'lucky_catcher_2', 'name': 'Lucky Catcher II', 'effect': '7.5% chance of doubling dragons', 'value': 0.075, 'type': 'lucky'},
        {'id': 'gambling_catcher_2', 'name': 'Gambling Catcher II', 'effect': '4.5% triple, 2.25% lose all', 'value': 0.045, 'penalty': 0.0225, 'type': 'gambling'},
        {'id': 'pack_wooden_2', 'name': 'Pack Catcher - Wooden II', 'effect': '2.25% chance wooden pack', 'value': 0.0225, 'type': 'pack', 'pack_tier': 'wooden'},
        {'id': 'pack_stone_2', 'name': 'Pack Catcher - Stone II', 'effect': '1.5% chance stone pack', 'value': 0.015, 'type': 'pack', 'pack_tier': 'stone'},
        {'id': 'pack_bronze_2', 'name': 'Pack Catcher - Bronze II', 'effect': '1.125% chance bronze pack', 'value': 0.01125, 'type': 'pack', 'pack_tier': 'bronze'},
        {'id': 'pack_silver_2', 'name': 'Pack Catcher - Silver II', 'effect': '0.75% chance silver pack', 'value': 0.0075, 'type': 'pack', 'pack_tier': 'silver'},
        {'id': 'pack_gold_2', 'name': 'Pack Catcher - Gold II', 'effect': '0.375% chance gold pack', 'value': 0.00375, 'type': 'pack', 'pack_tier': 'gold'},
        {'id': 'pack_platinum_2', 'name': 'Pack Catcher - Platinum II', 'effect': '0.1875% chance platinum pack', 'value': 0.001875, 'type': 'pack', 'pack_tier': 'platinum'},
        {'id': 'purrcise_catcher_2', 'name': 'Purrcise Catcher II', 'effect': '3% chance to catch +1 extra dragon', 'value': 0.03, 'type': 'perfect'},
        {'id': 'time_manip_2', 'name': 'Time Manipulator II', 'effect': '1.5% chance +5min dragonscale', 'value': 0.015, 'type': 'time'},
        {'id': 'speedrunner_2', 'name': 'Speedrunner II', 'effect': 'First 12 dragons always double', 'value': 12, 'type': 'speedrun'},
        {'id': 'coin_grinder_2', 'name': 'Coin Grinder II', 'effect': '+4% coins from catch', 'value': 0.04, 'type': 'coins'},
        {'id': 'rarity_boost_2', 'name': 'Rarity Booster II', 'effect': '5% chance rarity +1', 'value': 0.05, 'type': 'rarity'},
        {'id': 'steal_catcher', 'name': 'Steal Catcher', 'effect': '5% chance to steal from other dragons', 'value': 0.05, 'type': 'steal'},
        {'id': 'fusion_master', 'name': 'Fusion Master', 'effect': '3% chance to fuse 2 dragons into 1 stronger', 'value': 0.03, 'type': 'fusion'},
        {'id': 'dragon_counter_2', 'name': 'Dragon Counter II', 'effect': '+6 bonus dragons every 10 catches', 'value': 6, 'type': 'counter'},
        {'id': 'lucky_streak_2', 'name': 'Lucky Streak II', 'effect': '4x bonus on streaks of 5+ same dragon', 'value': 0.04, 'type': 'streak'},
        {'id': 'collector_bonus', 'name': "Collector's Bonus", 'effect': '10% extra coins per unique dragon type', 'value': 0.10, 'type': 'collector'},
    ],
    'rare': [
        {'id': 'lucky_catcher_3', 'name': 'Lucky Catcher III', 'effect': '12.5% chance doubling dragons', 'value': 0.125, 'type': 'lucky'},
        {'id': 'gambling_catcher_3', 'name': 'Gambling Catcher III', 'effect': '7.5% triple, 3.75% lose all', 'value': 0.075, 'penalty': 0.0375, 'type': 'gambling'},
        {'id': 'pack_wooden_3', 'name': 'Pack Catcher - Wooden III', 'effect': '3.75% chance wooden pack', 'value': 0.0375, 'type': 'pack', 'pack_tier': 'wooden'},
        {'id': 'pack_stone_3', 'name': 'Pack Catcher - Stone III', 'effect': '2.5% chance stone pack', 'value': 0.025, 'type': 'pack', 'pack_tier': 'stone'},
        {'id': 'pack_bronze_3', 'name': 'Pack Catcher - Bronze III', 'effect': '1.875% chance bronze pack', 'value': 0.01875, 'type': 'pack', 'pack_tier': 'bronze'},
        {'id': 'pack_silver_3', 'name': 'Pack Catcher - Silver III', 'effect': '1.25% chance silver pack', 'value': 0.0125, 'type': 'pack', 'pack_tier': 'silver'},
        {'id': 'pack_gold_3', 'name': 'Pack Catcher - Gold III', 'effect': '0.625% chance gold pack', 'value': 0.00625, 'type': 'pack', 'pack_tier': 'gold'},
        {'id': 'pack_platinum_3', 'name': 'Pack Catcher - Platinum III', 'effect': '0.3125% chance platinum pack', 'value': 0.003125, 'type': 'pack', 'pack_tier': 'platinum'},
        {'id': 'time_manip_3', 'name': 'Time Manipulator III', 'effect': '2.5% chance +5min dragonscale', 'value': 0.025, 'type': 'time'},
        {'id': 'speedrunner_3', 'name': 'Speedrunner III', 'effect': 'First 20 dragons always double', 'value': 20, 'type': 'speedrun'},
        {'id': 'coin_grinder_3', 'name': 'Coin Grinder III', 'effect': '+8% coins from catch', 'value': 0.08, 'type': 'coins'},
        {'id': 'rarity_boost_3', 'name': 'Rarity Booster III', 'effect': '8% chance rarity +1', 'value': 0.08, 'type': 'rarity'},
        {'id': 'steal_catcher_3', 'name': 'Steal Catcher III', 'effect': '8% chance to steal from other dragons', 'value': 0.08, 'type': 'steal'},
        {'id': 'fusion_master_3', 'name': 'Fusion Master III', 'effect': '6% chance to fuse 2 dragons into 1 stronger', 'value': 0.06, 'type': 'fusion'},
        {'id': 'mimic_dragon', 'name': 'Mimic Dragon', 'effect': '4% chance to mimic last caught dragon type', 'value': 0.04, 'type': 'mimic'},
        {'id': 'echo_catcher', 'name': 'Echo Catcher', 'effect': '3% chance to echo-catch previous dragon', 'value': 0.03, 'type': 'echo'},
        {'id': 'dragon_counter_3', 'name': 'Dragon Counter III', 'effect': '+12 bonus dragons every 10 catches', 'value': 12, 'type': 'counter'},
        {'id': 'lucky_streak_3', 'name': 'Lucky Streak III', 'effect': '8x bonus on streaks of 5+ same dragon', 'value': 0.08, 'type': 'streak'},
        {'id': 'collector_bonus_3', 'name': "Collector's Bonus III", 'effect': '20% extra coins per unique dragon type', 'value': 0.20, 'type': 'collector'},
    ],
    'epic': [
        {'id': 'lucky_catcher_4', 'name': 'Lucky Catcher IV', 'effect': '25% chance doubling dragons', 'value': 0.25, 'type': 'lucky'},
        {'id': 'gambling_catcher_4', 'name': 'Gambling Catcher IV', 'effect': '15% triple, 7.5% lose all', 'value': 0.15, 'penalty': 0.075, 'type': 'gambling'},
        {'id': 'pack_wooden_4', 'name': 'Pack Catcher - Wooden IV', 'effect': '7.5% chance wooden pack', 'value': 0.075, 'type': 'pack', 'pack_tier': 'wooden'},
        {'id': 'pack_stone_4', 'name': 'Pack Catcher - Stone IV', 'effect': '5% chance stone pack', 'value': 0.05, 'type': 'pack', 'pack_tier': 'stone'},
        {'id': 'pack_bronze_4', 'name': 'Pack Catcher - Bronze IV', 'effect': '3.75% chance bronze pack', 'value': 0.0375, 'type': 'pack', 'pack_tier': 'bronze'},
        {'id': 'pack_silver_4', 'name': 'Pack Catcher - Silver IV', 'effect': '2.5% chance silver pack', 'value': 0.025, 'type': 'pack', 'pack_tier': 'silver'},
        {'id': 'pack_gold_4', 'name': 'Pack Catcher - Gold IV', 'effect': '1.25% chance gold pack', 'value': 0.0125, 'type': 'pack', 'pack_tier': 'gold'},
        {'id': 'pack_platinum_4', 'name': 'Pack Catcher - Platinum IV', 'effect': '0.625% chance platinum pack', 'value': 0.00625, 'type': 'pack', 'pack_tier': 'platinum'},
        {'id': 'time_manip_4', 'name': 'Time Manipulator IV', 'effect': '5% chance +5min dragonscale', 'value': 0.05, 'type': 'time'},
        {'id': 'speedrunner_4', 'name': 'Speedrunner IV', 'effect': 'First 40 dragons always double', 'value': 40, 'type': 'speedrun'},
        {'id': 'coin_grinder_4', 'name': 'Coin Grinder IV', 'effect': '+15% coins from catch', 'value': 0.15, 'type': 'coins'},
        {'id': 'rarity_boost_4', 'name': 'Rarity Booster IV', 'effect': '12% chance rarity +1', 'value': 0.12, 'type': 'rarity'},
        {'id': 'steal_catcher_4', 'name': 'Steal Catcher IV', 'effect': '15% chance to steal from other dragons', 'value': 0.15, 'type': 'steal'},
        {'id': 'fusion_master_4', 'name': 'Fusion Master IV', 'effect': '10% chance to fuse 2 dragons into 1 stronger', 'value': 0.10, 'type': 'fusion'},
        {'id': 'mimic_dragon_4', 'name': 'Mimic Dragon IV', 'effect': '8% chance to mimic last caught dragon type', 'value': 0.08, 'type': 'mimic'},
        {'id': 'echo_catcher_4', 'name': 'Echo Catcher IV', 'effect': '7% chance to echo-catch previous dragon', 'value': 0.07, 'type': 'echo'},
        {'id': 'dragon_counter_4', 'name': 'Dragon Counter IV', 'effect': '+20 bonus dragons every 10 catches', 'value': 20, 'type': 'counter'},
        {'id': 'lucky_streak_4', 'name': 'Lucky Streak IV', 'effect': '16x bonus on streaks of 5+ same dragon', 'value': 0.16, 'type': 'streak'},
        {'id': 'collector_bonus_4', 'name': "Collector's Bonus IV", 'effect': '35% extra coins per unique dragon type', 'value': 0.35, 'type': 'collector'},
        {'id': 'dragon_master', 'name': 'Dragon Master', 'effect': '5% chance to catch rare dragons', 'value': 0.05, 'type': 'master'},
    ],
    'legendary': [
        {'id': 'lucky_catcher_5', 'name': 'Lucky Catcher V', 'effect': '37.5% chance doubling dragons', 'value': 0.375, 'type': 'lucky'},
        {'id': 'gambling_catcher_5', 'name': 'Gambling Catcher V', 'effect': '22.5% triple, 11.25% lose all', 'value': 0.225, 'penalty': 0.1125, 'type': 'gambling'},
        {'id': 'pack_wooden_5', 'name': 'Pack Catcher - Wooden V', 'effect': '11.5% chance wooden pack', 'value': 0.115, 'type': 'pack', 'pack_tier': 'wooden'},
        {'id': 'pack_stone_5', 'name': 'Pack Catcher - Stone V', 'effect': '7.5% chance stone pack', 'value': 0.075, 'type': 'pack', 'pack_tier': 'stone'},
        {'id': 'pack_bronze_5', 'name': 'Pack Catcher - Bronze V', 'effect': '5.625% chance bronze pack', 'value': 0.05625, 'type': 'pack', 'pack_tier': 'bronze'},
        {'id': 'pack_silver_5', 'name': 'Pack Catcher - Silver V', 'effect': '3.75% chance silver pack', 'value': 0.0375, 'type': 'pack', 'pack_tier': 'silver'},
        {'id': 'pack_gold_5', 'name': 'Pack Catcher - Gold V', 'effect': '1.875% chance gold pack', 'value': 0.01875, 'type': 'pack', 'pack_tier': 'gold'},
        {'id': 'pack_platinum_5', 'name': 'Pack Catcher - Platinum V', 'effect': '0.9375% chance platinum pack', 'value': 0.009375, 'type': 'pack', 'pack_tier': 'platinum'},
        {'id': 'voting_booster', 'name': 'Voting Booster', 'effect': 'Vote streak boosts dragonscale duration', 'value': 1.0, 'type': 'voting'},
        {'id': 'time_manip_5', 'name': 'Time Manipulator V', 'effect': '7.5% chance +5min dragonscale', 'value': 0.075, 'type': 'time'},
        {'id': 'speedrunner_5', 'name': 'Speedrunner V', 'effect': 'First 60 dragons always double', 'value': 60, 'type': 'speedrun'},
        {'id': 'coin_grinder_5', 'name': 'Coin Grinder V', 'effect': '+25% coins from catch', 'value': 0.25, 'type': 'coins'},
        {'id': 'rarity_boost_5', 'name': 'Rarity Booster V', 'effect': '20% chance rarity +1', 'value': 0.20, 'type': 'rarity'},
        {'id': 'steal_catcher_5', 'name': 'Steal Catcher V', 'effect': '25% chance to steal from other dragons', 'value': 0.25, 'type': 'steal'},
        {'id': 'fusion_master_5', 'name': 'Fusion Master V', 'effect': '15% chance to fuse 2 dragons into 1 stronger', 'value': 0.15, 'type': 'fusion'},
        {'id': 'mimic_dragon_5', 'name': 'Mimic Dragon V', 'effect': '12% chance to mimic last caught dragon type', 'value': 0.12, 'type': 'mimic'},
        {'id': 'echo_catcher_5', 'name': 'Echo Catcher V', 'effect': '10% chance to echo-catch previous dragon', 'value': 0.10, 'type': 'echo'},
        {'id': 'dragon_counter_5', 'name': 'Dragon Counter V', 'effect': '+30 bonus dragons every 10 catches', 'value': 30, 'type': 'counter'},
        {'id': 'lucky_streak_5', 'name': 'Lucky Streak V', 'effect': '32x bonus on streaks of 5+ same dragon', 'value': 0.32, 'type': 'streak'},
        {'id': 'collector_bonus_5', 'name': "Collector's Bonus V", 'effect': '50% extra coins per unique dragon type', 'value': 0.50, 'type': 'collector'},
        {'id': 'dragon_master_5', 'name': 'Dragon Master V', 'effect': '15% chance to catch ultra-rare dragons', 'value': 0.15, 'type': 'master'},
        {'id': 'immortal_dragon', 'name': 'Immortal Dragon', 'effect': '3% chance to resurrect caught dragons', 'value': 0.03, 'type': 'immortal'},
    ]
}

# ==================== PACK SYSTEM ====================
PACK_BASE_VALUES = {
    'wooden':   {'base_value': 40,   'coin_base': 50,   'coin_variance': 0.15},
    'stone':    {'base_value': 70,   'coin_base': 100,  'coin_variance': 0.15},
    'bronze':   {'base_value': 130,  'coin_base': 225,  'coin_variance': 0.15},
    'silver':   {'base_value': 250,  'coin_base': 375,  'coin_variance': 0.15},
    'gold':     {'base_value': 500,  'coin_base': 750,  'coin_variance': 0.15},
    'platinum': {'base_value': 1200, 'coin_base': 1750, 'coin_variance': 0.15},
    'diamond':  {'base_value': 2500, 'coin_base': 4000, 'coin_variance': 0.15},
    'celestial':{'base_value': 3500, 'coin_base': 7000, 'coin_variance': 0.15},
}

PACK_UPGRADE_ORDER = ['wooden', 'stone', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'celestial']

PACK_TYPES = {
    'wooden':   {'name': 'Wooden Pack',   'emoji': '<:woodenchest:1446170002708238476>'},
    'stone':    {'name': 'Stone Pack',    'emoji': '<:stonechest:1446169958265389247>'},
    'bronze':   {'name': 'Bronze Pack',   'emoji': '<:bronzechest:1446169758599745586>'},
    'silver':   {'name': 'Silver Pack',   'emoji': '<:silverchest:1446169917996011520>'},
    'gold':     {'name': 'Gold Pack',     'emoji': '<:goldchest:1446169876438978681>'},
    'platinum': {'name': 'Platinum Pack', 'emoji': '<:platinumchest:1446169876438978681>'},
    'diamond':  {'name': 'Diamond Pack',  'emoji': '<:diamondchest:1446169830720929985>'},
    'celestial':{'name': 'Celestial Pack','emoji': '<:celestialchest:1446169830720929985>'},
}

NATO_NAMES = [
    'Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel',
    'India', 'Juliett', 'Kilo', 'Lima', 'Mike', 'November', 'Oscar', 'Papa',
    'Quebec', 'Romeo', 'Sierra', 'Tango', 'Uniform', 'Victor', 'Whiskey',
    'X-ray', 'Yankee', 'Zulu'
]

# ==================== DRAGON NEST UPGRADE TIERS ====================
DRAGONNEST_UPGRADES = {
    0: {'name': 'Base',       'cost': 0,             'min_rarity': 'common',    'allowed_rarities': ['common', 'uncommon', 'rare', 'epic', 'legendary']},
    1: {'name': 'Upgrade I',  'cost': 500_000,       'min_rarity': 'uncommon',  'allowed_rarities': ['uncommon', 'rare', 'epic', 'legendary']},
    2: {'name': 'Upgrade II', 'cost': 5_000_000,     'min_rarity': 'rare',      'allowed_rarities': ['rare', 'epic', 'legendary']},
    3: {'name': 'Upgrade III','cost': 20_000_000,    'min_rarity': 'epic',      'allowed_rarities': ['epic', 'legendary']},
    4: {'name': 'Upgrade IV', 'cost': 500_000_000,   'min_rarity': 'legendary', 'allowed_rarities': ['legendary']},
    5: {'name': 'Upgrade V',  'cost': 1_000_000_000, 'min_rarity': 'legendary', 'allowed_rarities': ['legendary']},
}

# ==================== RAID SYSTEM ====================
RARITY_DAMAGE = {
    'common': 10,
    'uncommon': 25,
    'rare': 60,
    'epic': 150,
    'legendary': 400,
    'mythic': 1000,
    'ultra': 2500,
}
RAID_SPAWN_TIMES = [8, 16, 20]   # 08:00, 16:00, 20:00
RAID_DURATION_HOURS = 2           # Boss despawns after 2 hours if not defeated

def generate_unique_perks(level, count=3, upgrade_level=0):
    """Generate unique random perks for a given level (no duplicates)."""
    import random
    weights = PERK_RARITY_WEIGHTS.get(level, PERK_RARITY_WEIGHTS[2])
    allowed_rarities = DRAGONNEST_UPGRADES.get(upgrade_level, DRAGONNEST_UPGRADES[0])['allowed_rarities']

    selected_perks = []
    used_perk_ids = set()

    max_attempts = 50
    attempts = 0

    while len(selected_perks) < count and attempts < max_attempts:
        attempts += 1
        available_rarities = {k: v for k, v in weights.items() if k in allowed_rarities}
        if not available_rarities:
            break
        rarity = random.choices(list(available_rarities.keys()), weights=list(available_rarities.values()))[0]
        if rarity in PERKS_POOL and len(PERKS_POOL[rarity]) > 0:
            perk = random.choice(PERKS_POOL[rarity])
            if perk['id'] not in used_perk_ids:
                selected_perks.append((rarity, perk))
                used_perk_ids.add(perk['id'])

    return selected_perks
