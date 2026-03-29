---
id: am-1up6
status: in_progress
deps: []
links: []
created: 2026-03-29T06:25:19Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [ui, map, controls, dungeon]
---
# Fix ctrl-move travel for diagonal directions

Ctrl-move travel currently works for cardinal directions but not for diagonals. In dungeon map view, ctrl+diagonal movement keys should trigger the same travel/run behavior as ctrl+up/down/left/right, including vi-key, numpad, and navigation-key aliases where supported. Add regression coverage for diagonal ctrl-travel bindings and behavior.

