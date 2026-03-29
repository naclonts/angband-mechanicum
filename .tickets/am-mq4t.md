---
id: am-mq4t
status: open
deps: [am-6448]
links: []
created: 2026-03-29T02:49:16Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, dungeon]
---
# NPC and creature system for dungeons

System for placing and managing NPCs/creatures on dungeon maps. Each entity has: position, disposition (friendly/hostile/neutral), movement AI (patrol, wander, stationary, aggressive), dialogue capability flag, portrait, stats. Friendly NPCs can be talked to (bump interaction). Hostile creatures can be fought. Neutral creatures ignore the player unless provoked. Integrates with the existing entity tracking system (engine/history.py). Party members (Alpha-7, Volta) become NPCs that follow the player on the dungeon map.

