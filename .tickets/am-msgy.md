---
id: am-msgy
status: open
deps: []
links: []
created: 2026-03-28T01:30:58Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [combat, engine, llm, state]
---
# Persist combat results in history and LLM context

After combat ends, the structured CombatResult (victory/defeat, enemies fought, damage taken, turns elapsed) should be stored in the game history system and injected into the LLM conversation so the narrator knows what happened. Currently the LLM has no awareness that combat occurred. Wire the combat summary into conversation_history as a system-style message and record it as a history step with entity references for enemies encountered.

