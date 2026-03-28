---
id: am-clj1
status: closed
deps: []
links: []
created: 2026-03-28T00:36:45Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [ui, engine, art]
---
# Scene art should fit environment pane dimensions

LLM-generated ASCII art often overflows the environment pane vertically. The art should approximately fill the pane — wider and less tall than current output. Ideally the engine should know the pane dimensions and instruct the LLM accordingly, so art adapts if the terminal or layout is resized. Investigate passing pane width/height from the UI to the engine so the scene art instructions use dynamic dimensions rather than hardcoded values.

