---
id: am-vnnp
status: in_progress
deps: []
links: []
created: 2026-03-29T05:08:08Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, controls]
---
# Allow tab focus and scrolling for dungeon side panels

In dungeon mode, let the player Tab between the dungeon map, the field log, and the bottom-right inspect/status pane(s), scroll the non-map panels up and down while focused, and Tab back to the dungeon map without breaking movement controls.


## Notes

**2026-03-29T05:19:46Z**

Made dungeon side panels focusable/scrollable via Tab cycling and RichLog-backed panes; verified focus order and page scrolling in tests.
