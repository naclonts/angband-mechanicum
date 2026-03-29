---
id: am-htx8
status: closed
deps: []
links: []
created: 2026-03-29T04:38:55Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, camera]
---
# Make dungeon camera follow the player

The current dungeon viewport behaves like a fixed top-left window. When the player moves away from the origin, they can disappear from view. Implement a scrolling camera or viewport that keeps the player visible as they move through large levels, with the surrounding map shifting appropriately around them. Add regression coverage for movement near viewport edges.


## Notes

**2026-03-29T04:46:32Z**

Implemented viewport-aware dungeon map cropping centered on the player, added content-size accessors on DungeonMapPane, and added regression tests for camera clamping and cropped rendering.
