---
id: am-b89n
status: closed
deps: []
links: []
created: 2026-03-29T19:30:20Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, combat, ui, engine, cleanup]
---
# Route LLM combat triggers into dungeon exploration instead of legacy tactical combat

When text mode returns a combat trigger from the LLM, the game should no longer push the legacy CombatScreen. Instead, it should transition into the unified dungeon exploration/combat flow with an environment-appropriate hostile roster already present on the map. Reuse existing dungeon generation, environment matching, and encounter population systems so the triggered enemies fit the current narrative context. Audit the remaining CombatScreen / combat-engine path: if any parts are still useful as future reference, mark them clearly deprecated and remove live call paths; otherwise remove the obsolete legacy combat code and tests entirely. Update docs/tests so the intended map-view combat architecture is unambiguous.

