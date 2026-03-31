---
id: am-u71l
status: closed
deps: []
links: []
created: 2026-03-29T20:12:46Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, combat, powers, abilities]
---
# Add powers to dungeon view combat

Support activated powers in the unified dungeon view, including Mechanicum abilities and psyker abilities. Define how powers are selected, targeted, resolved, and surfaced in the UI, and ensure they fit the deterministic dungeon combat loop rather than the removed tactical screen. Include tests for at least one self-targeted and one ranged/area power path, and document the extensibility model for adding more powers later.


## Notes

**2026-03-31T01:14:08Z**

Implemented first dungeon power slice in unified dungeon combat: persistent player powers/cooldowns in DungeonMapState, p-driven power targeting mode, self-cast Rite of Repair, Electro-Shock area blast, autosave/save-load coverage, and updated docs/tests.
