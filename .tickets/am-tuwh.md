---
id: am-tuwh
status: in_progress
deps: []
links: []
created: 2026-03-29T05:14:12Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, save, persistence]
---
# Autosave during dungeon exploration turns

The game currently autosaves from text mode but not reliably while the player is moving around in dungeon mode. Add save behavior during dungeon exploration so player actions in the map view persist regularly, ideally after each meaningful turn or movement/action, while preserving the current dungeon session state.


## Notes

**2026-03-29T05:18:48Z**

Added dungeon-view autosave after movement, wait, and transition-triggered actions; blocked moves do not save. Verified with targeted dungeon/app/save tests.
