---
id: am-tt9t
status: closed
deps: []
links: []
created: 2026-03-29T20:12:46Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, combat, ranged, ui]
---
# Add ranged attacks to dungeon view combat

Dungeon combat currently centers on movement and bump-to-attack. Add shooting and other ranged attacks directly to the unified dungeon view, including target selection/range rules, LOS checks, hit resolution, and UI feedback in the map/log panes. Reuse existing combat stats/models where appropriate, add tests for targeting and LOS behavior, and update docs to reflect the expanded map-view combat loop.


## Notes

**2026-03-29T23:31:29Z**

Implemented cursor-based fire mode on DungeonScreen with f/Enter/Esc controls, persistent player attack range, ranged-hit resolution in DungeonMapState, status-pane targeting feedback, docs updates, and focused tests for range, LOS, modal cursor behavior, and save compatibility.
