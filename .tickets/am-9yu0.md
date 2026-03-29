---
id: am-9yu0
status: open
deps: []
links: []
created: 2026-03-29T18:04:40Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [story, dungeon, engine, progression, travel]
---
# Let text-view travel select a destination environment and open a matching dungeon

Implement the long-range travel loop described in docs/context.md. From text view, the player should be able to describe where they want to go in natural language. The engine should resolve that request to the closest supported dungeon environment/location type, narrate the trip in text view, and then generate or switch to a dungeon session for that destination so the player can /explore on arrival. This should build on the existing map/text bridge and environment-aware dungeon generation rather than introducing a separate overworld system. Define where the resolved destination type is stored in session state and add tests for destination matching, arrival flow, and save/load continuity.

