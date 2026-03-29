---
id: am-uhok
status: open
deps: []
links: []
created: 2026-03-29T05:57:25Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, layout, e2e]
---
# Fix dungeon map pane width fill regression

The dungeon map still does not visually expand to fill the available width of its panel in the running app, even though ticket am-422f added renderer-level padding. Diagnose the mounted DungeonMapPane/layout behavior, fix the real width-fill regression, and add an end-to-end test that exercises the actual dungeon screen in-app rather than only render_dungeon_map() in isolation.

