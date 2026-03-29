---
id: am-bw0g
status: open
deps: [am-ky9z]
links: []
created: 2026-03-29T02:53:27Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, ui]
---
# Map-text view transition system

The bridge between the two game views. Map view (dungeon exploration/combat) and text view (existing game_screen for narrative/dialogue/travel) need to transition cleanly between each other.

Map → Text triggers:
- Bump friendly NPC → text view scoped to conversation with that NPC (portrait shown, LLM dialogue)
- Interact with special object (spaceship, terminal, shrine) → text view with description, LLM narration
- 'l' (look) at something complex → text view with generated description + art

Text → Map triggers:
- LLM narrates arrival at a new location → load/generate dungeon, switch to map view
- Player ends conversation → return to map view at same position
- Game start (after story selection) → initial dungeon loads in map view

Must handle: passing context between views (which NPC is being talked to, what dungeon to load, player position persistence). The existing game_screen becomes the text view; the new unified map screen is the map view. App manages which is active.

