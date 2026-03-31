---
id: am-ukl0
status: closed
deps: []
links: []
created: 2026-03-30T00:00:46Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, persistence, new-game]
---
# Reset dungeon state for each new game

Bug: dungeon state is persisting between separate new games. Starting a new game should recreate dungeons from scratch for that game/character. Dungeon persistence should exist only within the context of the current save/game state, not leak across different new characters or fresh runs.


## Notes

**2026-03-30T00:00:52Z**

Difficulty: medium. State-lifecycle bug touching new-game setup and dungeon persistence boundaries; verify that persistence remains per save/game while fresh games always get fresh dungeon state.
