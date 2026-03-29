---
id: am-ky9z
status: open
deps: [am-6448, am-v3m4]
links: []
created: 2026-03-29T02:49:13Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [ui, dungeon]
---
# Dungeon exploration + combat screen (unified map view)

Single unified Textual screen for both dungeon exploration AND combat. This replaces the current separate CombatScreen. The player walks around a persistent dungeon map, bumps to melee attack hostiles, casts abilities, picks up items — all on the same map. No screen transitions for combat.

Renders the dungeon in overhead ASCII view: player (@), NPCs, creatures, items, terrain. Numpad movement (1-9) plus vi-keys (hjklyubn). Single character focus — player controls one Tech-Priest.

Side panels: character stats, message log (short combat/exploration messages), dungeon level info. The message log shows combat results, item pickups, etc. inline — no separate combat log screen.

Must handle FOV rendering (visible/explored/hidden tiles). Dungeon levels are persistent — leaving and returning preserves state.

Certain map tiles/objects are "text view triggers" — interacting with them transitions to the text view (e.g., a spaceship, a cogitator terminal, a friendly NPC for conversation). The text view (existing game_screen) handles dialogue, long-range travel narration, and returns to the map view when the player arrives somewhere new.

Reference: TOME/Angband main game view — exploration and combat unified on one map.


## Notes

**2026-03-29T03:09:50Z**

Map rendering should use per-tile colors from dungeon_level.get_terrain_glyph() with environment overrides, not the monochrome CRT green theme. CRT green stays for UI chrome (borders, panels, text) but map tiles get full terminal color palette. TerrainGlyph (char + fg hex) and Environment.color_overrides are defined in engine/dungeon_level.py. FOV dimming: VISIBLE tiles use full color, EXPLORED tiles should be dimmed (e.g. halve brightness or use a grey tint), HIDDEN tiles are not rendered.
