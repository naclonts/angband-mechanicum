---
id: am-jkg3
status: closed
deps: []
links: []
created: 2026-03-28T01:51:05Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [ui, party]
---
# Show party and player stats in STATUS panel

Add deterministic party and player health info to the STATUS panel (InfoPanel widget). Keep existing info fields (DESIGNATION, LOCATION, DATE, NOOSPHERE). Add:

- Player INTEGRITY (HP bar — already shown but currently LLM-driven; make it deterministic from engine state)
- PARTY section listing each member with abbreviated name + HP status (e.g. `Alpha-7 [████----] 8/12`)

Party data is in engine (`party_member_ids` + `PARTY_TEMPLATES`). Panel is ~25 chars wide so abbreviate names as needed. Goal: persistent squad visibility outside combat without relying on LLM to update health.

