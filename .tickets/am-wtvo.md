---
id: am-wtvo
status: open
deps: [am-msgy]
links: []
created: 2026-03-28T01:30:51Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [combat, engine, llm]
---
# LLM-driven combat encounter generation

Combat scenarios should have enemies determined by the LLM based on story context, not always the same hardcoded set. The LLM should choose from predefined enemy templates (servitors, gun servitors, ogryn, chaos cultists, heretics, tyranid hormagaunts, chaos marines, thugs, etc.) and optionally define new enemy types relevant to the current narrative. The encounter composition, enemy count, and map should reflect what makes sense for the story — a hive underbelly encounter has thugs and mutants, a Chaos-tainted area has cultists and marines, a xenos incursion has hormagaunts, etc. Approach: when /combat is triggered (or combat is narratively triggered), ask the LLM to return a structured combat_encounter field with enemy roster and optional map hint. Expand the ENEMY_TEMPLATES dict with more variety. Wire the encounter data into CombatEngine initialization.

