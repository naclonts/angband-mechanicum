---
id: am-v3m4
status: open
deps: [am-6448]
links: []
created: 2026-03-29T02:49:05Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, dungeon]
---
# FOV and visibility system

Field-of-view / line-of-sight system for dungeon exploration. Shadowcasting or similar algorithm. Three tile states: hidden (never seen), explored (previously seen, dimmed), visible (currently in FOV, full brightness). FOV radius based on character/light source. Walls block LOS. Must integrate with the dungeon level data model and render correctly in the exploration screen. Reference: TOME/Angband FOV systems.

