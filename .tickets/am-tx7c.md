---
id: am-tx7c
status: closed
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


## Notes

**2026-03-29T21:23:49Z**

Implemented room-aware door threshold placement in dungeon generation, added regression coverage for room-boundary threshold selection and generated room-and-connection layouts, and updated context/architecture docs. Verification: uv run pytest tests/test_dungeon_gen.py -q; uv run pytest (full suite still only hits the known ambient panel wrapping failure).
