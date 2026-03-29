---
id: am-mapo
status: open
deps: []
links: []
created: 2026-03-29T05:56:29Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, ui, llm, atmosphere]
---
# Tighten ambient discovery dedupe and cadence

Ambient LOS updates should not repeat the same subject back-to-back or re-announce effectively identical terrain discoveries such as column -> column in the same room. Strengthen dedupe semantics so the inspect panel only updates when something meaningfully new enters view, and reduce update frequency to roughly half the current cadence. Preserve explicit look/examine routing into text view.

