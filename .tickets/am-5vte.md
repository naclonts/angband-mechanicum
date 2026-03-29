---
id: am-5vte
status: in_progress
deps: []
links: []
created: 2026-03-29T21:06:34Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [ui, debug, environments]
---
# Add debug environment catalog tab

Add a new UI tab/view listing the preset dungeon environment options. Selecting an environment should show its unique data such as monsters, objects, and other relevant generation content. This is primarily a debug feature. Consider mapping it to F3.


## Notes

**2026-03-29T21:07:46Z**

Difficulty: medium. Debug-oriented feature. F3 is the suggested binding. Environment detail view should enumerate environment-specific generation content such as monsters, objects, and other preset data.

**2026-03-29T23:35:38Z**

Added F3 environment debug catalog in the dungeon inspect pane. The view reads live generation tables for each preset environment and supports selection cycling without moving the player. Added dungeon screen tests and documented the debug overlay in architecture.
