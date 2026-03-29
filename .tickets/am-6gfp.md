---
id: am-6gfp
status: open
deps: []
links: []
created: 2026-03-29T20:21:38Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [e2e, dungeon, text-view, state]
---
# Add E2E coverage for dungeon/text location transitions

The latest session log shows a dungeon->text transition bug where talking to the Signal Scout from an ashland dungeon leaves the bottom-right location panel showing Forge-Cathedral Alpha instead of the active dungeon location. Add thorough E2E coverage around dungeon-to-text and text-to-dungeon transitions so this case is reproduced in tests first, then fixed, and similar state-sync regressions are caught going forward. Reference log: /home/nathan/.local/share/angband-mechanicum/logs/convo_1774814999.jsonl.


## Notes

**2026-03-29T20:37:48Z**

First-wave text-bridge work landed on main with coverage for pending info/scene context across text->dungeon returns, but the specific Signal Scout location-sync regression still needs a targeted reproduction against the reference log before closing.
