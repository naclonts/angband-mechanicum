---
id: am-uz2i
status: open
deps: []
links: []
created: 2026-03-29T21:08:17Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [ui, dungeon, text-wrapping, e2e]
---
# Fix ambient/field scan panel text wrapping regression

The ambient/field scan panel still allows prose to overflow instead of wrapping to the visible pane width. This appears to regress despite earlier wrap tickets claiming a fix. Reproduce on the real ambient/show_context path, verify rendered line widths in the live widget, and ensure scene art and prose behavior are both correct.


## Notes

**2026-03-29T21:08:23Z**

Difficulty: medium. Related prior tickets: am-oedz ('Wrap ambient dungeon-panel text to fit pane width') and am-vqvg ('Wrap ambient inspect text without wrapping art'). Those earlier fixes were believed complete but the live ambient/field-scan path still fails the rendered-width assertion in tests/test_e2e.py::TestNewGame::test_ambient_panel_wraps_prose_without_touching_scene_art.

**2026-03-29T21:08:23Z**

Likely reason prior fixes did not fully solve it: the earlier work validated split inspect rendering and Text/no_wrap behavior, but the still-failing path is the real ambient show_context rendering in the widget. Future fix must prove actual rendered line widths in a live widget/pilot run, not only mocked method calls or Text object flags.
