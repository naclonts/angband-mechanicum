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
Holding Ctrl while moving engages travel mode and keeps stepping in that direction until something notable appears or the route becomes blocked. Diagonal ctrl-travel covers the vi, numpad, and navigation-key aliases where supported.
The dungeon viewport follows the player so large levels stay centered in the terminal instead of rendering from a fixed top-left corner.
Transition tiles are part of the dungeon itself: stairs, lifts, elevators, gates, and portals move the player between persistent levels or themed areas while preserving the session stack.
The bottom-right inspect panel now also surfaces occasional ambient line-of-sight discoveries for nearby characters, objects, and notable features while explicit look/examine still routes into text view.
When text view is opened from a dungeon interaction, the active target and current dungeon context are carried into the prompt so follow-up dialogue stays anchored to the addressed character or object.
When ambient responses include both `scene_art` and `narrative_text`, the art is kept unwrapped and the prose wraps cleanly to the panel width.
The dungeon status pane shows gameplay-relevant player status, especially HP/integrity, instead of a log-entry count.
Tab cycles focus between the map, field log, and side panels so the non-map panes can be scrolled without losing movement controls.

### Text View (narrative + dialogue + travel)
The existing 4-pane layout: scene art, character portrait, narrative log, and command prompt. Used for NPC conversations, examining things in detail, and long-range travel ("board the ship and fly to Mars"). LLM generates narrative responses.
When the player is directly speaking to or closely examining a specific character, the scene art can center that character instead of only showing the broader surroundings.
Travel requests entered in text view are resolved to the closest supported dungeon environment, then a matching dungeon session is generated and mounted on arrival.
Curated story starts now seed explicit dungeon-generation profiles instead of relying on free-text environment inference. Those profiles carry canonical environment identity, faction bias, landmark/set-piece preferences, and content exclusions across story intro, `/explore`, save/load, and later floor transitions.

### Transitions Between Views
- **Map → Text**: Bump a friendly NPC (conversation), interact with a special object (spaceship, terminal), or look/examine something in detail
- **Text → Map**: `/explore` returns to the live dungeon session, travel requests can resolve to a new destination dungeon, and narrative responses can also hint that play should resume on the map. New games begin in text view and transition into exploration when the player is ready.

Zone navigation between different areas (forge worlds, different dungeons) happens via text view — no overworld map in v1.
The destination vocabulary is built around an expandable environment catalog, so future travel matching can resolve natural-language destinations onto the closest supported dungeon type.
Story-specific dungeon profiles sit above that coarse environment layer so authored starts like titan recovery, necron tomb delves, or STC vault breaches keep their faction and landmark identity instead of collapsing into generic biome content.
Dungeon floors can also include reusable themed set-pieces that combine room dressing, grouped hostiles, and optional NPCs to create more memorable encounters than plain procedural geometry alone.

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
- **Dungeon generation** (dungeon_gen.py) — procedural multi-room dungeon floors with seeded, environment-specific contact rosters, still expanding toward the full exploration loop
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
