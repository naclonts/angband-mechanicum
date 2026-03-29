---
id: am-pcs9
status: closed
deps: []
links: []
created: 2026-03-29T20:14:51Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, combat, movement]
---
# Keep player in place after killing with bump attack

When the player attacks an adjacent enemy by moving into them and the attack kills the target, the player currently steps into the enemy's tile. Change bump-to-attack resolution so killing an enemy does not also move the player into that space unless an explicit follow-through mechanic is later added. Add regression tests for kill, non-kill, and blocked movement cases.

