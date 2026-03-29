---
id: am-ry4a
status: open
deps: []
links: []
created: 2026-03-29T21:06:34Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [ui, dungeon, text-view]
---
# Fix look-mode dungeon-to-text environment panel art

When transitioning from dungeon to text after using look, the Environment panel can show the stale default image (for example Forge-Cathedra Alpha) instead of the appropriate art/context for the viewed object or environment. Preserve and surface the look target's correct scene/environment art during the dungeon->text bridge.


## Notes

**2026-03-29T21:07:46Z**

Difficulty: medium. Repro reported: after dungeon -> text transition triggered from look/examine, the Environment panel can show stale Forge-Cathedra Alpha art instead of art for the viewed target/environment.
