---
id: am-5vkd
status: closed
deps: [am-mibn]
links: []
created: 2026-03-29T18:04:56Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, engine, content, encounters]
---
# Make dungeon enemy rosters fit each environment

Rework dungeon enemy/contact generation so the hostile populations match the current environment much more closely. For example, sewer levels should skew toward rats, sump-mutants, scavengers, or criminal underhive types instead of generic hostiles. Review the existing _ENVIRONMENT_CONTACTS and generation path in dungeon_gen.py and make the roster system scale to both the current environments and the planned new ones. The result should choose enemy types and relative quantities in a way that feels lore-appropriate per environment, while still allowing occasional out-of-place exceptions when justified.


## Notes

**2026-03-29T18:12:46Z**

Expanded dungeon contact generation to use environment-weighted category selection, added thematic hostile/friendly/neutral rosters for the current and newly added environments, and updated the dungeon generation docs/test coverage. Verification: uv run pytest tests/test_dungeon_gen.py -q (108 passed).
