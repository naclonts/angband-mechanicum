---
id: am-5mdw
status: open
deps: []
links: []
created: 2026-03-29T04:38:27Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, controls]
---
# Fix dungeon look mode toggle and cursor control

Look mode in the dungeon screen is currently buggy: the pointer appears, but after a couple of keys input falls back to normal player movement. Fix look mode so it stays active until explicitly confirmed or cancelled, preserves cursor movement correctly, and behaves as a real modal/toggled state. Add regression coverage for the failure case.

