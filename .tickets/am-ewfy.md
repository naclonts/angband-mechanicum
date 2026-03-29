---
id: am-ewfy
status: closed
deps: []
links: []
created: 2026-03-29T05:06:02Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, engine, content]
---
# Generate environment-appropriate dungeon enemies and NPCs

During dungeon generation, seed enemies or NPCs appropriate to the current environment/theme instead of leaving floors largely empty. Reuse the existing dungeon/session/entity models and distinguish hostile vs friendly/neutral contacts where relevant.


## Notes

**2026-03-29T05:18:48Z**

Added environment-aware dungeon contact generation: generated floors now carry a seeded DungeonEntityRoster with hostile and non-hostile entities placed on passable floor tiles. Covered by reproducibility and placement tests.
