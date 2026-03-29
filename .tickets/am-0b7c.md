---
id: am-0b7c
status: open
deps: []
links: []
created: 2026-03-29T20:18:41Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, generation, environments, objects]
---
# Add environment-specific multi-tile objects to dungeon generation

Expand dungeon environments so each environment type spawns 5-10 objects/features that are specifically relevant to that environment instead of relying on a thin generic terrain palette. Examples: terminals and cogitator banks in high-tech spaces, broken machinery and weird rock formations in ash lands, shrine clutter in cathedral spaces, wreckage and hull fragments in void/ship spaces. Support both single-tile and multi-tile placed objects, including blocking footprints such as rock formations, titan wreckage, or ships. Blocking multi-tile objects must be placed so they do not fully seal rooms, corridors, or required traversal routes. Add regression coverage for object variety, footprint placement, and path preservation, and update docs to reflect the richer environment dressing system.

