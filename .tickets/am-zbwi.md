---
id: am-zbwi
status: open
deps: []
links: []
created: 2026-03-29T20:10:05Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, death, persistence]
---
# Archive dungeon-view deaths into the Hall of the Dead

Dungeon creature AI now deals real integrity damage during map exploration, but the dungeon path still lacks the death-to-memorial flow used by text/legacy combat. When player integrity reaches zero on DungeonScreen, generate the memorial through GameEngine, persist a DeathRecord via SaveManager, clear the live save, and return to the menu consistently. Add regression coverage for dungeon-side death handling and document the intended flow.

