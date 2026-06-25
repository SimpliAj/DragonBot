# DragonBot - Changelog

## Session 11.03.2026

### ✅ Refactoring verifiziert
- bot.py (20.389 Zeilen) vollständig in modulare Struktur migriert
- Alle 30+ Commands, 11 Background Tasks, 4 Events in Cogs aufgeteilt
- Differenz von −1.118 Zeilen = Duplikate in bot.py die bereinigt wurden
- `main.py` ist der neue Einstiegspunkt

### ✅ /serverconfig Command (cogs/admin.py)
- Slash Command nur für Server-Admins und DEV_USER_ID
- Toggle für Raids (Ein/Aus)
- Toggle für Black Market (Ein/Aus)
- Dropdown für Raid-Spawn-Zeiten (alle 24h wählbar)
- Modal für Black Market Intervall (Stunden) + Max pro Tag
- **Raids und Black Market sind standardmäßig deaktiviert**
- Einstellungen werden in `guild_settings` Tabelle gespeichert (dragon_bot.db)

### ✅ Neue DB-Spalten in guild_settings
| Spalte | Default |
|---|---|
| raids_enabled | 0 |
| raid_times | [8, 16, 20] |
| blackmarket_enabled | 0 |
| blackmarket_interval_hours | 4 |
| blackmarket_max_per_day | 6 |

### ✅ Top.gg Vote Rewards (cogs/topgg.py)
- Webhook-Server auf Port 5000 (aiohttp)
- 30-Tage rotierendes Reward-System (wie Dragonpass)
- Gleiche custom Emojis wie Dragonpass
- Reward-Anzeige in 3 Reihen (1-10, 11-20, 21-30)
- Weekend-Bonus: +1 Wooden Pack extra
- Vote-Streak Tracking (48h Fenster)
- DM-Benachrichtigung nach jedem Vote (fallback: Spawn-Channel)
- `/vote` Command zeigt kompletten Schedule + nächsten Reward

**30-Tage Schedule:**
- Days 1-10: Wooden/Stone Packs (300-400 coins)
- Days 11-20: Bronze/Silver Packs (600-800 coins)
- Days 21-29: Gold/Diamond Packs (1200-1500 coins)
- Day 30 ⭐: Dragonscale + 3000 coins

**Top.gg Webhook URL:** `http://138.199.198.80:5000/topgg-webhook`

### ✅ Breeding Chances überarbeitet (config.py)
- Fail % skaliert jetzt mit Rarity (höher = mehr Risiko)
- Common+Common: 5% Fail → Ultra+Ultra: **40% Fail**
- Alle 30 Kombinationen auf 100% geprüft

| Kombination | Fail % |
|---|---|
| Common + Common | 5% |
| Uncommon + Uncommon | 10% |
| Rare + Rare | 15% |
| Epic + Epic | 20% |
| Legendary + Legendary | 25% |
| Mythic + Mythic | 30% |
| Mythic + Ultra | 35% |
| Ultra + Ultra | 40% |

### ✅ /devpanel Command (cogs/devpanel.py)
- Ersetzt alle `-db` Prefix-Commands durch ein interaktives Panel
- Nur DEV_USER_ID hat Zugriff
- Ephemeral (nur für den Dev sichtbar)
- 5 Kategorien mit Buttons und Modals für Input

| Kategorie | Funktionen |
|---|---|
| 🎁 Give | Coins, Dragons, Pack, Premium, Pass Level, Giveaway |
| 🔄 Reset | Perks, Inventory, Breeding, Breed CD, Quests, Battlepass, Bingo, Spawn |
| ⚔️ Spawn | Raid Boss, Black Market, Dragonfest, Kill Raid |
| 📊 Info | Spawn Status, DB Status, Raid Info, Softlocks, Fix Softlock, Nest Level |
| ⚠️ Danger | Clear Events, Wipe Server, Restart |

### ✅ progress.md aktualisiert
- Alle echten Zeilenzahlen eingetragen
- Fehlende Cogs ergänzt
- Differenz zu bot.py dokumentiert

---

## Dateistruktur (Stand 11.03.2026)

| Datei | Zeilen | Beschreibung |
|---|---|---|
| main.py | 50 | Einstiegspunkt |
| config.py | 653 | Konstanten, Dragon-Types, Breeding-Chances |
| database.py | ~1.120 | DB-Funktionen, server_config helpers |
| state.py | 85 | Globaler Shared State |
| utils.py | 757 | Hilfsfunktionen |
| cogs/admin.py | ~1.740 | Admin Commands + /serverconfig |
| cogs/events.py | 1.703 | Events + Dragon Spawn |
| cogs/tasks.py | ~1.860 | Background Tasks |
| cogs/economy.py | ~870 | /bal, /casino, /shop, /vote, /coinflip |
| cogs/dragons.py | 1.453 | /info, /inventory, /dragonlogue, /stats |
| cogs/dragon_nest.py | 2.134 | Dragon Nest System |
| cogs/dragonpass.py | 379 | Dragonpass/Quests |
| cogs/breeding.py | 1.054 | Zucht-System |
| cogs/raids.py | 1.865 | Raid Bosse |
| cogs/market.py | 1.848 | Markt & Trading |
| cogs/packs.py | 1.025 | Packs & Alpha Dragons |
| cogs/adventures.py | 295 | Abenteuer |
| cogs/social.py | 509 | Leaderboard, Bingo, Achievements |
| cogs/topgg.py | ~200 | Top.gg Webhook + Vote Rewards |
| cogs/devpanel.py | ~280 | Dev Control Panel |
| bot.py | 20.389 | ALT – nicht mehr aktiv |
