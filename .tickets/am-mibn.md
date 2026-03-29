---
id: am-mibn
status: in_progress
deps: []
links: []
created: 2026-03-29T18:04:48Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, engine, content, worldbuilding]
---
# Add more Warhammer 40K environment types for dungeon generation

Expand the environment catalogue with roughly 10 additional 40K-flavored environment types beyond the current forge/cathedral/hive/sewer/corrupted/overgrown/tomb/manufactorum set. Examples could include voidship, shrine-world reliquary, rad-wastes, data-vault, xenos ruin, ice crypt, sump market, plasma reactorum, penal oubliette, and ash-dune outpost, but final choices should fit the game's tone and generation constraints. Each new environment should define its description, room-type affinities, feature terrain mix, color overrides, and any prompt-facing metadata needed for text-view travel matching.


## Notes

**2026-03-29T18:08:11Z**

Expanded the environment catalog with 10 new 40K-flavored environments and added alias metadata for future destination matching. Verified with uv run pytest tests/test_dungeon_level.py tests/test_dungeon_gen.py -q (112 passed).
