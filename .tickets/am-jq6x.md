---
id: am-jq6x
status: closed
deps: []
links: []
created: 2026-03-29T21:06:34Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [ui, debug, logs]
---
# Add debug logs view tab

Add a new UI tab/view for logs so the player can inspect this game's JSON/log history. This is primarily a debug feature. Consider mapping it to F2. The view should surface the current game's relevant structured history without disrupting normal play.


## Notes

**2026-03-29T21:07:46Z**

Difficulty: medium. Debug-oriented feature. F2 is the suggested binding, but exact keymap can be adjusted if it conflicts with existing screen bindings.

**2026-03-29T23:59:57Z**

Implemented F2 debug logs view in GameScreen, added engine debug snapshot API, added debug widget/styles, updated docs, and verified with app/engine/e2e tests. Broader suite still shows unrelated ambient inspect wrapping failure in tests/test_e2e.py::TestNewGame::test_ambient_panel_wraps_prose_without_touching_scene_art.
