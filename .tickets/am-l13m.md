---
id: am-l13m
status: open
deps: []
links: []
created: 2026-03-29T18:04:35Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [ui, llm, story, interaction]
---
# Show speaking character in environment pane during focused dialogue

When the player is speaking to or closely examining a specific character in text view, the left scene/environment pane should prefer art of that addressed character instead of only the surrounding location. This is distinct from the OPERATIVE portrait pane: the scene pane should be able to show a full character-focused tableau or close-up when the active interaction context is character-centric, while still falling back to surroundings for travel and general narration. Build on the existing active interaction context in GameScreen/GameEngine and update prompting/tests so scene_art reliably follows the addressed target when appropriate.

