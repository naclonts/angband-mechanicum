---
id: am-kfhe
status: open
deps: []
links: []
created: 2026-03-29T05:56:29Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, controls]
---
# Fix look mode Enter confirm regression

Explicit look mode should open the text-view examine flow when the player presses Enter on a visible target. There is a regression where looking at something and hitting Enter does not work reliably. Diagnose input/focus/binding behavior in DungeonScreen and restore the expected examine transition, with regression coverage.

