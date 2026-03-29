---
id: am-9cyf
status: open
deps: []
links: []
created: 2026-03-29T20:18:49Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, text-view, llm, rendering]
---
# Fix look-to-text transition rendering raw LLM JSON

Bug: when the player looks at an object in dungeon view and transitions into text view, the initial LLM response is rendered as raw JSON in the narrative pane instead of routing  to the narrative pane and  to the environment pane. After the player submits another prompt, rendering behaves correctly. Reproduce against the most recent session log artifact at /home/nathan/.local/share/angband-mechanicum/logs/convo_1774814999.jsonl and use that path as the reference when debugging. Fix the initial map->text restore/render path so the first response is parsed and displayed through the normal structured response flow. Add regression coverage for object-look transitions into text view.


## Notes

**2026-03-29T20:18:58Z**

Structured fields involved: narrative_text must render in the narrative pane and scene_art must render in the environment pane. Repro/reference log: /home/nathan/.local/share/angband-mechanicum/logs/convo_1774814999.jsonl. The initial map->text response is being shown as raw JSON; after the next user prompt the same response path renders correctly.
