---
id: am-c73o
status: closed
deps: []
links: []
created: 2026-03-28T01:18:11Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [ui, css]
---
# Prompt pane top border misaligned and persists when unfocused

Two related border issues on the prompt/text input pane:

1. The top border of the prompt pane is a different style/color than the left/right/bottom borders — it doesn't visually align with the rest of the pane border.

2. When focus moves away from the prompt (e.g. to the datalog), the top border of the prompt remains visible but the other borders disappear. All borders should behave consistently — either all visible or all styled the same way regardless of focus state.

Likely a TCSS issue in styles/game.tcss — check the PromptInput and PromptInput:focus rules. The top border may be defined separately (border-top vs border) causing the mismatch.

