---
id: am-djpw
status: closed
deps: []
links: []
created: 2026-03-29T03:23:19Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [combat, engine, ui]
---
# Permadeath with Hall of the Dead

Death in combat ends the game. Before exiting to menu, the LLM generates an epic summary of the character's life and deeds — their battles, discoveries, companions, and final moments. This death narrative is saved persistently. A new 'Hall of the Dead' view accessible from the main menu displays past fallen Tech-Priests with their death summaries, stats (turns survived, enemies slain, deepest level reached), and cause of death. Permadeath means the save file is deleted on death — no reloading.


## Notes

**2026-03-29T04:51:23Z**

Implemented permadeath archive flow: added DeathRecord persistence in SaveManager, Hall of the Dead screen and menu entry, GameEngine death narrative helper, GameScreen defeat handling, and regression tests/docs. Verified with pytest tests/test_save_manager.py tests/test_game_engine.py tests/test_app.py -q and pytest tests/test_e2e.py -q.
