---
id: am-ol13
status: closed
deps: [am-6448]
links: []
created: 2026-03-29T02:49:01Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, dungeon]
---
# Large dungeon floor generator

Procedural generation of exploration-scale dungeon floors (80x50+ tiles). Multiple interconnected rooms of varied types connected by corridors. Doors, stairs between levels, secret passages. Themed environments (forge, hive, sewer, corrupted, etc.) building on existing dungeon_gen.py theme system. Reference: TOME dungeon generation — rooms + corridors + varied level feelings. Different from existing dungeon_gen.py which only produces single combat rooms.


## Notes

**2026-03-29T03:20:43Z**

Investigating current dungeon model and implementing exploration-scale floor generation on top of DungeonLevel.

**2026-03-29T03:24:21Z**

Implemented exploration-scale dungeon floor generation on DungeonLevel with themed room placement, corridor connectivity, doors, stairs, environment feature scattering, and regression coverage in tests/test_dungeon_gen.py. Verified with: uv run pytest tests/test_dungeon_gen.py
