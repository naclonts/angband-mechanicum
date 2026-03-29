---
id: am-apbj
status: closed
deps: []
links: []
created: 2026-03-29T06:05:24Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, engine, ui, content]
---
# Wire generated dungeon contacts into live map state

Dungeon floor generation now creates an environment-appropriate entity_roster in generate_dungeon_floor(), but the app currently discards it when constructing DungeonMapState for both new sessions and newly generated transition floors. Use floor.entity_roster to populate DungeonMapState.entities so hostile, friendly, and neutral contacts actually appear in live exploration. Cover both new-game/session creation and descent-generated floors with tests, and verify persistence still serializes/deserializes those contacts correctly.
