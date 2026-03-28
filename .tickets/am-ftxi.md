---
id: am-ftxi
status: closed
deps: []
links: []
created: 2026-03-28T00:29:08Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [engine, history, entities]
---
# History and entity tracking system

Build a structured history and entity tracking layer on top of game state. Requirements:

1. **Step history**: Every player turn is saved as a step with full interaction data (input, narrative response, scene state). Steps are indexed and searchable.

2. **Entity registries**: Maintain indexed registries for Places, Characters, and Items. Each entity has an id, short description, and links to steps where it appeared.

3. **Entity history chains**: For any entity (place, character, item), be able to reconstruct a chronological chain of all interactions involving it — which steps, what happened, who/what else was involved.

4. **Context construction for agents**: Provide an API that, given an entity id, returns a summary suitable for LLM context — short descriptions from history, with the ability to expand to full interaction text for steps relevant to the current scenario.

5. **Cross-references**: Steps link to entity ids; entities link to steps and to each other (e.g. a character was at a place, an item was held by a character). This enables queries like 'last time the player visited this place' or 'everything that happened with this NPC'.

This is foundational infrastructure for giving the roleplay agent rich, structured memory of the game world.


## Notes

**2026-03-28T00:45:28Z**

Implemented history.py with Step, Entity, EntityType, GameHistory classes. Integrated into GameEngine: LLM prompt extended with entity tracking schema, entity registry injected dynamically, entities parsed from LLM response each turn, steps recorded with cross-references. Seed entities pre-registered for game start. Save/load includes history. All 33 existing tests pass.
