---
id: am-zbwi
status: closed
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


## Notes

**2026-03-29T20:37:48Z**

Integrated dungeon-side death archival flow into main. DungeonScreen now triggers memorial generation when integrity reaches zero, archives through SaveManager, clears the live save, and opens the Hall of the Dead immediately. Added focused app/dungeon/widget coverage and docs updates.
