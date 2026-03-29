---
id: am-9nq0
status: open
deps: []
links: []
created: 2026-03-29T04:39:27Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, engine]
---
# Route dungeon examine into text view

Change dungeon look/examine so it transitions into the text view in the same way bump-driven interactions do, instead of staying entirely inside the dungeon screen. Examining a target should open the narrative/text screen with the generated description and scene art, while preserving enough context to return cleanly to the dungeon afterward. This should build on the existing map-text bridge and examine prompt path.

