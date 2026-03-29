---
id: am-wgdn
status: closed
deps: []
links: []
created: 2026-03-29T04:38:27Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, layout]
---
# Expand dungeon map viewport and shrink explore log

In dungeon exploration mode, reduce the vertical space used by the bottom-left message log and give that space back to the main map viewport. The map should occupy more of the screen vertically so exploration feels less cramped. Update layout/styles and any screen/widget assumptions or tests.


## Notes

**2026-03-29T04:55:07Z**

In worktree /tmp/am-wgdn-viewport: increased DungeonMapPane height share from 2fr to 4fr and added an e2e regression asserting the mounted map pane is taller than the dungeon log.
