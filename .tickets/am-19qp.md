---
id: am-19qp
status: open
deps: []
links: []
created: 2026-03-31T01:20:15Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, rest, healing, ui]
---
# Add dungeon rest action on r

Feature: add a rest action bound to r in the unified dungeon view. Rest should pass turns to recover HP/integrity automatically until the player is fully healed or an enemy enters line of sight/FOV and interrupts the rest loop. The implementation should fit the existing dungeon turn loop, autosave behavior, and creature-turn processing. Add tests for healing progression plus interruption when a hostile becomes visible. Difficulty: medium.

