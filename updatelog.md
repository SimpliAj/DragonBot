🐉 **DragonBot Update** *(2026-04-01)* — Patch 7

⚙️ Admin Panel — New `/adminpanel` Command
→ New command for server admins (Administrator permission) and the bot developer
→ Fully guild-scoped — all actions only affect the server where the command is used
→ **🎁 Give:** Coins, Dragons, Packs, Dragonscale minutes, Giveaway
→ **🔄 Reset:** Quests, Breed Cooldown, Adventure Cooldown, Bingo
→ **⚔️ Spawn:** Dragonfest, Raid Boss, Black Market, Kill Raid Boss
→ **📊 Info:** Spawn Status, Raid Info, Fix Softlock, Clear Events (server-only)

🎫 Dragonpass — Level 30 Bug Fixes
→ Fixed: Level 30 reward notification was missing when completing the pass
→ Fixed: Level 30 reward tile showed Dragonscale emoji instead of ✅ after completion
→ Fixed: Level-up embed in catch channel incorrectly showed "Diamond Pack" for level 30 instead of "2 Minutes Dragonscale"

---

🐉 **DragonBot Update** *(2026-03-25)* — Patch 6

🎫 Dragonpass — Vote Quest Fix
→ Fixed: Vote quest was silently discarded when quests got regenerated during the vote action — vote now always counts regardless

🪙 Coinflip — Stuck Bet Fix
→ Fixed: When the 5-minute accept window expired without a response, the bet stayed as `pending` in the DB forever — blocking future challenges with the same opponent
→ `on_timeout` now marks the bet as `expired` automatically
→ On bot restart, all leftover `pending` bets past their `expires_at` are auto-expired on startup

🐉 Adventure — Dragon Name Fix
→ Fixed: DM after adventure completion showed raw dragon type keys (e.g. `ember`, `iron`) instead of proper names
→ Now shows emoji + full name (e.g. 🔥 Ember Dragon)

🎯 Bingo — Display Fix
→ Fixed: Bingo card was rendered inside a code block, preventing custom emojis from showing
→ Now each cell displays the dragon's Discord emoji correctly

🔔 Setup Reminder — New Daily DM
→ Bot now sends a daily DM to the guild owner and admins if no spawn channel has been configured via `/setchannel`
→ Message explains what to do and how to get started

---

🐉 **DragonBot Update** *(2026-03-22)* — Patch 5

🧬 Breeding — Bug Fixes & Improvements
→ Fixed: Selecting first parent in `/breed` did nothing (broken `response.followup` call)
→ Fixed: Cancel button on confirm embed did nothing (missing interaction response)
→ Fixed: DNA Sample price shown as 5,000🪙 in "no DNA" message — now correctly shows 12,500🪙
→ Removed 🎲 Rolled: X/100 from both fail and success breeding embeds
→ Level-based parent loss protection on breeding fail:
  • Lvl 1–4: 50% chance to lose a parent
  • Lvl 5–9: 35%
  • Lvl 10–14: 20%
  • Lvl 15+: 10%
→ Confirm embed now shows current parent loss % before breeding starts
→ Fail embed shows "✅ Your dragons were protected" if no parent was lost

---

🐉 **DragonBot Update** *(2026-03-22)* — Patch 4

🎫 Dragonpass — Quest Overhaul
→ **4 quests per refresh** — 3 random + 1 permanent Vote on Top.gg quest
→ New quest types added:
  • ⏱️ Catch a dragon within 10 seconds of spawn
  • Catch a dragon on an odd second
  • Catch a dragon on an even second
  • Complete a `/trade`
  • `/gift` someone
→ `check_bingo` quest removed — only `complete_bingo` remains
→ Quest display fix: rarity quests now show correctly (e.g. "Catch 2 Mew+ Dragons" instead of "Catch 2 Mew or higher")

🏆 Dragonpass — Level 30 Reward Changed
→ Level 30 reward is now **2 minutes of Dragonscale** (active spawn boost) instead of a pack
→ Next reward preview at level 29 and reward track both show the Dragonscale emoji correctly

⚙️ Dragonpass — Quest Rewards Toggle
→ New `.env` flag `DRAGONPASS_QUEST_REWARDS=true/false` to enable or disable coin rewards for completing individual quests
→ When disabled, the notification also hides the coin amount

🐉 Catch Embed — Catch Time Display
→ The catch success embed now shows how many seconds since spawn the dragon was caught (e.g. ⏱️ **Catch time: 4.2s**)

---

🐉 **DragonBot Update** *(2026-03-22)* — Patch 3

🎯 Bingo — Auto-Completion Detection
→ Bingo completion is now detected automatically when a dragon is caught — no need to run `/bingo` manually
→ When a line is completed: instant notification in the spawn channel with a ping, +500 🪙 reward granted immediately
→ Running `/bingo` after completion shows "already completed" message — no duplicate reward
→ Dragonpass quest `complete_bingo` is now also tracked automatically on catch

---

🐉 **DragonBot Update** *(2026-03-22)* — Patch 2

🏆 Trophy System
→ New trophy system separate from achievements — rare milestones displayed in `/stats`
→ 2 shop trophies (each limited to 1x purchase):
  • 🥇 Server Trophy — 25,000 🪙 (now limited to 1x)
  • 🎖️ Supporter Trophy — 50,000 🪙 (new)
→ 9 earned trophies awarded automatically when conditions are met:
  • Quest Master — Complete all 3 active Dragonpass quests in one refresh
  • Nest Master — Reach Dragon Nest level 10
  • Dragonpass Legend — Complete Dragonpass level 30
  • Dragon Scholar — Catch every dragon type at least once
  • Raid Destroyer — Land the killing blow on a raid boss
  • Dragon Millionaire — Reach 1,000,000 coins
  • Breeding Master — Reach breeding level 10
  • Alpha Lord — Create 10 Alpha Dragons
  • Mythic Hunter — Catch a Mythic or Ultra dragon
→ Trophy notification embed sent to spawn channel when earned
→ Trophies displayed on `/stats` Page 1 with custom emojis

🐉 Dragon Spawn — Persistence After Restart
→ Active dragon spawns now survive bot restarts
→ After restart, the last spawned dragon stays catchable immediately
→ No more waiting for a new spawn after a restart

---

🐉 **DragonBot Update** *(2026-03-22)*

📊 `/stats` - New Paginated Layout
→ 3 pages with ◀️ ▶️ navigation instead of one large embed
→ Page 1: Economy, Dragon Nest, Dragonpass, Alpha Dragons
→ Page 2: Raids, Adventures, Breeding (hidden if 0)
→ Page 3: Rarest Dragon, Catch Times, Achievements, Votes (hidden if 0)

🏆 Achievements - Automatic Notifications
→ Achievements now instantly notify in the spawn channel when unlocked
→ Coin rewards are granted immediately — no need to run `/achievements` anymore
→ 36 new achievements added across 7 categories:
  • ⚔️ Raids (7): Raid Initiate, Raid Fighter, Raid Veteran, Raid Legend, Attack Spree, Battle Hardened, War Machine
  • 🗺️ Adventures (4): Adventure Begins, Explorer, Adventurer, Legend of the Land
  • 🥚 Breeding (3): Master Breeder (50x), Breeding Expert (Lvl 5), Breeding Master (Lvl 10)
  • 🏰 Dragon Nest (5): Nest Upgraded, Nest Reinforced, Nest Perfected, Bounty Hunter (50), Elite Bounty Hunter (100)
  • 🎫 Dragonpass (4): Pass Graduate, Pass Veteran, Pass Legend, Pass Master (complete 1/3/5/10 times)
  • ✨ Alpha (2): Alpha Collector (3x), Alpha Overlord (10x)
  • 🗳️ Voting (6): First Vote, Regular Voter, Dedicated Voter, Top Voter, Weekly Supporter (7-day streak), Monthly Supporter (30-day streak)

🎲 Dice of Fate - Rebalanced
→ Coins: 2,000–6,000 (was 1,000–5,000)
→ Dragonscale: 1–5 min (was 3–10 min, now rarer)
→ Double Loot Bag: same drop chance as Lucky Charm

🏰 Dragon Nest - Bug Fixes
→ Perk now correctly awarded when reaching max level 10
→ "Claim Missing Perks" button works again
→ Help button now edits the current embed instead of sending a new one

---

🐉 **DragonBot Update**

✨ **New Commands & Features:**

🏪 `/market` - Unified Marketplace Command
→ Consolidated `/market`, `/marketsell`, and `/mylistings` into one command
→ Actions: browse, sell, mylistings
→ `/marketsell` command removed (replaced by `/market action:sell`)

🗺️ `/adventure` - Improved Adventure System
→ 2-step process: Choose adventure type, then select items to use
→ Buttons only show if you have the items (📜 Fast Travel, 🎒 Double Loot)
→ 3 New Long-Duration Adventures:
  • ✨ Mythical Expedition (12h) - 4,000-8,000 coins, 60% dragon chance
  • 👑 Ancient Awakening (24h) - 8,000-15,000 coins, 70% dragon chance
  • 🌑 Dark Abyss (48h) - 15,000-30,000 coins, 80% dragon chance
→ Rebalanced success rates for better progression

⚙️ `/devpanel` - New Reset Feature
→ Reset Adventure Cooldowns for users in the dev panel
→ Located in the "Reset" category

🔧 **Improvements:**

📊 Adventure Display
→ Removed success rate from adventure embed (now only shows cooldown)
→ Cleaner UI for better readability

🎮 Game Balance
→ Adventure success rates rebalanced across all difficulty levels
→ Short adventures (1-3h): 60-70% success
→ Medium adventures (6-12h): 68-75% success
→ Long adventures (24-48h): 80-85% success 



