---
id: am-vqvg
status: open
deps: []
links: []
created: 2026-03-29T05:56:29Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, layout]
---
# Wrap ambient inspect text without wrapping art

The dungeon ambient inspect panel currently lets text spill past the right edge. Update rendering so prose wraps to panel width while ASCII scene art stays unwrapped if possible. Current ambient response format already separates scene_art and narrative_text in GameEngine/GameResponse; keep that split and fix panel rendering accordingly.

