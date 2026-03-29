---
id: am-gkzn
status: closed
deps: [am-ky9z]
links: []
created: 2026-03-29T02:49:27Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, ui]
---
# Look/examine command in dungeon

In the dungeon exploration screen, the player can look at any visible tile, creature, item, or environmental feature. Triggers an LLM call that generates: (1) a text description shown in the message log/narrative pane, (2) ASCII art of the thing being examined shown in the scene/environment pane. Uses the existing LLM integration pattern from game_engine.py. Keybinding: 'l' (look) then move cursor to target, or 'l' + direction. Should also work when bumping into environmental features (terminals, statues, machinery).


## Notes

**2026-03-29T04:31:27Z**

Implemented look/examine mode in the dungeon screen with a movable look cursor, LLM-backed examine prompt, an inspection pane, and visible-target rendering. Verified with: uv run pytest tests/test_dungeon_screen.py tests/test_game_engine.py tests/test_widgets.py and uv run pytest tests/test_e2e.py
