---
id: am-ifnp
status: closed
deps: []
links: []
created: 2026-03-29T20:12:46Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, items, inventory, persistence]
---
# Add usable items to dungeon view

Introduce item support in the dungeon view, covering item representation, pickup/storage, and using items during exploration/combat. Define a practical first slice for item interactions in the map UI and engine state, wire persistence/save-load, and add tests for inventory state plus at least one usable item effect. Update docs so items are part of the unified dungeon roadmap rather than the old tactical subsystem.


## Notes

**2026-03-31T01:11:49Z**

Implemented a first dungeon-item slice: live item instances, floor pickup/inventory, quick-use healing consumables, save-load persistence, map/status UI hooks, and coverage for pickup/use/session round-trips.
