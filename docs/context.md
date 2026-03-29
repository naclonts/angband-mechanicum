# Angband Mechanicum

A CLI roguelike set in the Warhammer 40K universe. The player is an Adeptus Mechanicus Tech-Priest exploring persistent dungeons beneath forge worlds.

## Core Concept

- **Two-view architecture**: the game switches between a **map view** and a **text view**
- **LLM-powered narrative** for dialogue, descriptions, and travel narration
- **Terminal green CRT aesthetic** — all unicode/ASCII art in phosphor green
- **Single character focus** — player controls one Tech-Priest; other characters are NPCs

## Two-View Architecture

### Map View (dungeon exploration + combat)
Roguelike overhead tile map. The player (@) moves through persistent dungeon levels using numpad/vi-keys. Combat is Angband-style bump-to-attack on the same map — no separate combat screen. FOV/line-of-sight determines visibility. NPCs, items, and terrain features populate the dungeon.
The dungeon viewport follows the player so large levels stay centered in the terminal instead of rendering from a fixed top-left corner.

### Text View (narrative + dialogue + travel)
The existing 4-pane layout: scene art, character portrait, narrative log, and command prompt. Used for NPC conversations, examining things in detail, and long-range travel ("board the ship and fly to Mars"). LLM generates narrative responses.

### Transitions Between Views
- **Map → Text**: Bump a friendly NPC (conversation), interact with a special object (spaceship, terminal), or look/examine something in detail
- **Text → Map**: LLM narrates arrival at a new location (new dungeon loads), conversation ends (return to map at same position)

Zone navigation between different areas (forge worlds, different dungeons) happens via text view — no overworld map in v1.

## UI Layout

### Text View
```
+---------------------------+------------+
|                           |  Portrait  |
|     Scene Image           |  (unicode) |
|     (unicode art)         |            |
+---------------------------+------------+
|                           | Info Panel |
|     Narrative /           | (location, |
|     Game Text             |  date,     |
|                           |  stats)    |
|                           +------------+
|                           | > prompt   |
+---------------------------+------------+
```

### Map View
```
+------------------------------------------+
|                                          |
|     Dungeon Map (ASCII tiles)            |
|     @ player, NPCs, terrain, items       |
|     FOV: visible / explored / hidden     |
|                                          |
+------------------------------------------+
| Message Log  | Stats    |
| (combat hits,| (HP, etc)|
|  pickups)    |          |
+--------------+----------+
```

## What Exists Today

- **Text view** (game_screen.py) — fully functional with LLM narrative, portraits, entity tracking
- **Tactical combat** (combat_screen.py + combat_engine.py) — separate XCOM-style grid combat screen. Will be replaced by unified map view with bump-to-attack
- **Dungeon generation** (dungeon_gen.py) — procedural rooms for combat. Needs to be extended to full multi-room dungeon floors
- **Save/load** (save_manager.py) — game state persistence
- **Entity/history tracking** (history.py) — structured world memory for LLM context

## Design References

- **TOME (Tales of Maj'Eyal)** / T-Engine4 — primary reference for dungeon exploration, overworld-to-dungeon structure, varied dungeon environments. Source: https://git.net-core.org/tome/t-engine4
- **Angband** — classic roguelike dungeon crawling, bump-to-attack combat
- **Shadowrun (Genesis)** — future reference for real-time ARPG mode (see docs/plans/realtime-arpg.md)

## Tech Stack

- Python 3.11+, managed with uv
- Textual (TUI framework)
- Anthropic Claude API (narrative generation)
