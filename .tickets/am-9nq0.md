---
id: am-9nq0
status: closed
deps: []
links: []
created: 2026-03-29T04:39:27Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, engine]
---
# Route dungeon examine into text view

Change dungeon look/examine so it transitions into the text view in the same way bump-driven interactions do, instead of staying entirely inside the dungeon screen. Examining a target should open the narrative/text screen with the generated description and scene art, while preserving enough context to return cleanly to the dungeon afterward. This should build on the existing map-text bridge and examine prompt path.

## Notes

**2026-03-29T05:00:00Z**

Look mode still has a residual cursor bug even after the modal fix: if the player presses `l`, moves the cursor a few times, then presses `Enter`, the look marker remains visible after look mode exits and normal movement resumes. `action_confirm_look()` clears `_look_mode` but does not clear `_look_cursor_pos`, so this ticket should absorb that cleanup as part of routing examine into text mode.

**2026-03-29T05:00:01Z**

Clarify intended UX split: explicit player look/examine (`l` then `Enter`) should transition into the full text view with the selected subject as the focus. The bottom-right dungeon panel should remain in the game, but as a separate ambient/atmospheric surface rather than the primary explicit examine path.

**2026-03-29T05:11:42Z**

Related ticket: am-81se covers ambient bottom-right LOS discoveries. This ticket is the explicit player-driven path: l + Enter should open full text view for the selected subject, while ambient panel updates remain occasional and separate.

**2026-03-29T05:22:27Z**

Explicit look examine now bridges into text view and clears the lingering look cursor state; added unit/e2e tests for the path.
