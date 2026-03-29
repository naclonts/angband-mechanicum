---
id: am-g2z7
status: in_progress
deps: []
links: []
created: 2026-03-29T04:38:55Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, engine, ui, progression]
---
# Support traversing stairs, elevators, gates, and portals

Implement moving through dungeon transitions to new levels or areas. This should cover classic stairs up and down, but also support themed transitions such as elevators, gates, portals, lifts, or similar traversal objects depending on the environment. Preserve dungeon session state and define how the player arrives at the destination level or area.


## Notes

**2026-03-29T04:59:02Z**

Implemented environment-flavored dungeon transitions with persistent session stack/cached level states. Floors now place themed traversal tiles (lift/elevator/gate/portal) where appropriate, and the dungeon screen hands traversal off to the app when the player steps on a transition tile. Added save/load serialization for the dungeon session stack plus tests for generator, session round-trip, and traversal behavior.
