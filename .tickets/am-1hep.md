---
id: am-1hep
status: closed
deps: []
links: []
created: 2026-03-29T19:33:02Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ai, combat, engine]
---
# Implement full dungeon creature AI for exploration combat

Dungeon creatures currently have limited or shallow behavior in exploration mode. Build a solid dungeon-side AI system comparable in quality to the existing legacy combat AI: hostile creatures should pursue, flank or close intelligently, respect line of sight and obstacles, use ranged attacks or abilities when appropriate, patrol or wander when idle, and react to the player in ways that fit their archetype. Friendly and neutral dungeon actors should also support purposeful non-hostile behavior where relevant. Reuse ideas and heuristics from combat_engine.py where appropriate, but keep the runtime model native to dungeon exploration rather than reviving the legacy tactical screen. Add regression coverage for pathing, engagement, ranged behavior, and idle-state transitions.

