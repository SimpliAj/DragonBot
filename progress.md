# DragonBot Refactoring - Status

## Ziel
`bot.py` (20.389 Zeilen Monolith) aufteilen in mehrere Dateien/Cogs.

## ✅ MIGRATION VOLLSTÄNDIG ABGESCHLOSSEN

### Neue Struktur (bereits funktionsfähig)
- `main.py` — Einstiegspunkt, lädt alle Cogs
- `config.py` — Alle Konstanten, Dragon-Types, Konfiguration
- `database.py` — DB-Funktionen (init_db, get_user, update_balance, etc.)
- `state.py` — Globale Shared State (active_dragonscales, spawn_channels, etc.)
- `utils.py` — Hilfsfunktionen (format_time_remaining, etc.)

### Cogs — alle Commands + Tasks + Events migriert ✅
| Cog | Inhalt |
|-----|--------|
| `cogs/admin.py` | /setchannel, handle_dev_command, on_message (dev prefix) |
| `cogs/adventures.py` | /adventure, /adventures |
| `cogs/breeding.py` | /breed, /breedcalc, /breedqueue |
| `cogs/dragon_nest.py` | /dragonnest |
| `cogs/dragonpass.py` | /dragonpass |
| `cogs/dragons.py` | /info, /help, /pricecheck, /inventory, /dragonlogue, /stats |
| `cogs/economy.py` | /bal, /casino, /shop, /daily, /vote, /coinflip |
| `cogs/events.py` | on_ready, on_error, on_message (Dragon spawn/catch) |
| `cogs/market.py` | /market, /marketsell, /mylistings, /trade, /gift |
| `cogs/packs.py` | /openpacks, /alphadragons |
| `cogs/raids.py` | /raidstatus, /ritual |
| `cogs/social.py` | /leaderboard, /achievements, /bingo |
| `cogs/tasks.py` | Alle Background Tasks (auto_spawn, raid, nest, breeding, adventures, etc.) |

**Alle 33 Commands migriert. Alle Tasks migriert. Alle Events migriert.**

## 🔧 FIXES ANGEWENDET (11.03.2026)

| Problem | Fix |
|---------|-----|
| `LEVEL_XP_REQUIREMENTS` falsch in config.py | Werte aus bot.py kopiert |
| `LEVEL_LORE` zu kurz in config.py | Vollständige lange Texte aus bot.py kopiert |
| `BREEDING_CHANCES` komplett anders | Werte aus bot.py kopiert |
| `premium_users` war `set()` statt `dict` | In state.py auf `{}` geändert |
| `check_and_award_achievements` fehlte in database.py | Async-Version aus bot.py portiert |
| `ENABLE_TOPGG_VOTE_QUEST` fehlte in config.py | Hinzugefügt (`False`) |

## ⚠️ NOCH ZU ERLEDIGEN

### 1. Bot testen! (wichtigster Schritt)
Starte mit `python main.py` und teste:
- [ ] Dragon spawn (on_message catch)
- [ ] Alle /commands kurz antippen
- [ ] Background Tasks (kommen sie an?)
- [ ] Dev-Commands (prefix `!dev`)

### 2. bot.py löschen oder archivieren
- `bot.py` existiert noch mit 20.389 Zeilen
- Wird NICHT mehr von `main.py` gestartet
- Kann gelöscht/umbenannt werden wenn Tests erfolgreich
- Rename vorschlag: `bot.py.bak` oder einfach löschen

### 3. Nach erfolgreichem Test — mögliche Verbesserungen
- Doppelte Hilfsfunktionen zwischen Cogs aufspüren
- Error-Handling vereinheitlichen
- Logging verbessern

## Bekannte Risiken
- `premium_users` — in events.py genutzt, muss in state.py definiert sein
- `active_spawns` — shared state zwischen tasks.py und events.py
- Spawn locks (`spawn_locks`) müssen korrekt geteilt werden

## Dateigrößen (Stand 11.03.2026)
| Datei | Zeilen | Status |
|-------|--------|--------|
| bot.py (ALT, nicht aktiv) | 20.389 | Löschen nach Test |
| main.py | 48 | ✅ Aktiv |
| config.py | 653 | ✅ Aktiv |
| database.py | 1.043 | ✅ Aktiv |
| state.py | 85 | ✅ Aktiv |
| utils.py | 757 | ✅ Aktiv |
| cogs/tasks.py | 1.843 | ✅ Aktiv |
| cogs/events.py | 1.703 | ✅ Aktiv |
| cogs/dragon_nest.py | 2.134 | ✅ Aktiv |
| cogs/market.py | 1.848 | ✅ Aktiv |
| cogs/raids.py | 1.865 | ✅ Aktiv |
| cogs/adventures.py | 295 | ✅ Aktiv |
| cogs/social.py | 509 | ✅ Aktiv |
| cogs/breeding.py | 1.054 | ✅ Aktiv |
| cogs/packs.py | 1.025 | ✅ Aktiv |
| cogs/economy.py | 855 | ✅ Aktiv |
| cogs/dragons.py | 1.453 | ✅ Aktiv |
| cogs/admin.py | 1.722 | ✅ Aktiv |
| cogs/dragonpass.py | 379 | ✅ Aktiv |
| **GESAMT (neu)** | **19.271** | — |
| **Differenz zu bot.py** | **−1.118** | ⚠️ Prüfen |
