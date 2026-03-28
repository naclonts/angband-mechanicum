---
id: am-gurh
status: closed
deps: [am-pp6h]
links: []
created: 2026-03-28T01:25:58Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [combat, engine, ui]
---
# Transition from story to combat based on LLM output

When the LLM narrative indicates combat should begin, show a prompt at the end of the response (e.g. 'Press C to begin combat') so the player can transition naturally. Keep /combat as a manual override, but the primary flow should be LLM-driven: the engine signals combat in its JSON response, the UI displays the narrative then prompts the player to enter combat mode.

