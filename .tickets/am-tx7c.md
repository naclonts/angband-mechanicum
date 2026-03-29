---
id: am-tx7c
status: open
deps: []
links: []
created: 2026-03-29T20:14:51Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, generation, doors]
---
# Place generated doors only on wall boundaries

Dungeon floor generation currently allows doors to appear in the middle of open floor instead of only where corridors or rooms meet through wall boundaries. Tighten door placement so generated doors only occur on valid threshold tiles between separated spaces, never as free-standing floor artifacts. Add regression tests around candidate detection and generated-room layouts.

