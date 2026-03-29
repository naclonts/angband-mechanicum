---
id: am-5mdw
status: closed
deps: []
links: []
created: 2026-03-29T04:38:27Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, controls]
---
# Fix dungeon look mode toggle and cursor control

Look mode in the dungeon screen is currently buggy: the pointer appears, but after a couple of keys input falls back to normal player movement. Fix look mode so it stays active until explicitly confirmed or cancelled, preserves cursor movement correctly, and behaves as a real modal/toggled state. Add regression coverage for the failure case.


## Notes

**2026-03-29T04:45:28Z**

Confirmed look mode currently auto-confirms after the first cursor move via _look_primed in _move_look_cursor(). Fix will keep look mode modal until explicit confirm/cancel and add a regression test around repeated movement staying in look mode.

**2026-03-29T04:45:59Z**

Removed the _look_primed auto-confirm path from dungeon look cursor movement. Added regression tests proving repeated cursor movement stays in look mode until explicit confirm/cancel, and confirm still exits modal look state.
