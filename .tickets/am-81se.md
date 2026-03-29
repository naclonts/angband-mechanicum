---
id: am-81se
status: closed
deps: []
links: []
created: 2026-03-29T05:11:02Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, llm, atmosphere]
---
# Add occasional ambient LOS discoveries to dungeon inspect panel

Keep the bottom-right dungeon inspect panel as an ambient discovery surface. When the player is walking around and an interesting object, feature, or character enters line of sight, occasionally update that panel with an LLM-generated image/description of the noteworthy thing. Do not spam updates every turn; tune cadence heuristically, for example every few rooms, turns, or meaningful discoveries. Explicit look/examine should still route into full text view instead of using only the panel.


## Notes

**2026-03-29T05:11:42Z**

Related ticket: am-9nq0 covers explicit player examine. Keep the split clear: ambient panel updates are occasional atmospheric discoveries while explicit l + Enter examine should route into full text view.

**2026-03-29T05:26:31Z**

Implemented ambient LOS discoveries for the dungeon inspect panel. Added a no-turn ambient narration helper in GameEngine, cooldown/dedup candidate selection in DungeonScreen, and tests covering candidate prioritization plus panel updates. Verified with uv run pytest tests/test_dungeon_screen.py tests/test_game_engine.py -q and compileall.
