---
id: am-fjbv
status: open
deps: [am-ky9z, am-mq4t, am-bw0g]
links: []
created: 2026-03-29T02:49:24Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, ui]
---
# Bump interaction system

When the player walks into an entity on the dungeon map, trigger context-appropriate interaction:

- **Hostile creature**: Melee attack on the dungeon map. No separate combat screen — combat is resolved in-place on the unified map view. Bump = attack, damage calculated, message logged. Standard roguelike bump-to-fight.
- **Friendly NPC**: Transition to text view (existing game_screen) scoped to conversation with that NPC. Show their portrait, open text input for dialogue via the existing LLM conversation system. When conversation ends, return to map view.
- **Interactive object** (spaceship, terminal, etc.): Transition to text view with a description of the object. The LLM can narrate what happens (e.g., boarding a ship → travel to new location → new dungeon loads in map view).
- **Neutral entity**: Show a brief description in the message log, no view transition.

The text view transitions are the key bridge between the two modes — map view handles tactical/spatial gameplay, text view handles narrative/dialogue/travel.

