---
id: am-oedz
status: closed
deps: []
links: []
created: 2026-03-29T20:23:17Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, text-wrapping, e2e]
---
# Wrap ambient dungeon-panel text to fit pane width

In dungeon mode, the ambient/inspect panel should wrap narrative text to the available pane width instead of overflowing or rendering awkwardly. Preserve unwrapped scene-art lines where applicable, add end-to-end coverage for the wrapped ambient panel behavior, and update docs if the panel behavior contract changes.


## Notes

**2026-03-29T20:37:48Z**

Ambient panel wrapping ticket added. No implementation merged yet; fold into the next text/UI pass alongside the remaining map<->text restore/render bugs.
