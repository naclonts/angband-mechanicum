---
id: am-ew7z
status: open
deps: []
links: []
created: 2026-03-29T20:12:46Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, los, logging]
---
# Only show field-log events within line of sight

The dungeon field log currently reports events such as enemy movement even when they happen outside the player's current line of sight. Restrict field-log visibility to events the player could plausibly perceive from the current FOV/LOS model, while preserving direct local feedback for nearby visible actions. Add regression tests for hidden-vs-visible movement and document the intended perception rules.

