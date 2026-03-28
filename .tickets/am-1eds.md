---
id: am-1eds
status: closed
deps: []
links: []
created: 2026-03-28T01:21:11Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [combat, engine, state]
---
# Battle outcomes affect integrity in story mode

Integrity (HP/structural integrity of the Tech-Priest) should carry over between modes. When entering combat, the player's current integrity from story mode sets their combat HP. When exiting combat, the resulting integrity carries back to story mode. Battle damage should have narrative consequences. This requires a shared integrity stat tracked in the game state that both GameEngine and CombatEngine read/write.

