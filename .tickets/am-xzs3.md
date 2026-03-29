---
id: am-xzs3
status: closed
deps: [am-6448]
links: []
created: 2026-03-29T02:49:38Z
type: task
priority: 2
assignee: Nathan Clonts
tags: [engine, refactor]
---
# Single character focus refactor

Refactor from party-based gameplay to single character focus. The player controls one Tech-Priest. Current party members (Alpha-7, Volta) become NPC companions that follow the player on the dungeon map and can be talked to. In combat, only the player acts directly (companions act via AI or simple commands). This affects: game_engine.py (remove party cycling), combat_engine.py (companions as AI-controlled allies), combat_screen.py (simplified controls), info_panel (show player stats primarily). Companion NPCs can still die, be recruited, dismissed, etc.


## Notes

**2026-03-29T04:20:17Z**

Refactored the dungeon-first flow toward single-character focus: combat now launches without party_ids, combat UI no longer exposes unit cycling, status data renders companions instead of implying a direct party, and tests were added for the revised assumptions. Verified with: uv run pytest tests/test_game_engine.py tests/test_widgets.py tests/test_dungeon_screen.py and uv run pytest tests/test_e2e.py
