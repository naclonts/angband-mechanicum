---
id: am-v3m4
status: closed
deps: [am-6448]
links: []
created: 2026-03-29T02:49:05Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, dungeon]
---
# FOV and visibility system

Field-of-view / line-of-sight system for dungeon exploration. Shadowcasting or similar algorithm. Three tile states: hidden (never seen), explored (previously seen, dimmed), visible (currently in FOV, full brightness). FOV radius based on character/light source. Walls block LOS. Must integrate with the dungeon level data model and render correctly in the exploration screen. Reference: TOME/Angband FOV systems.


## Notes

**2026-03-29T03:28:22Z**

Implemented DungeonLevel FOV/visibility helpers: Bresenham LOS, compute_fov, fog-state promotion, and visibility convenience methods. Added focused tests for LOS, explored/visible transitions, and serialization. Verified with: uv run pytest tests/test_dungeon_level.py tests/test_dungeon_gen.py
