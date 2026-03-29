---
id: am-i3ia
status: closed
deps: []
links: []
created: 2026-03-29T20:14:51Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, doors, input, ui]
---
# Support opening and closing doors in dungeon view

Add interactive door handling to the unified dungeon view so the player can open and close doors during exploration and combat. Define practical controls, update movement/pathing and creature interaction rules, surface state changes in the field log/UI, and add tests for both opening and closing behavior including blocked or invalid cases.


## Notes

**2026-03-29T23:24:33Z**

Implemented adjacent door interaction in dungeon view: closed doors now open on bump, explicit o/c controls were added, door state changes recompute FOV and surface in the log, and pathing/LOS tests now cover open, closed, and blocked cases.
