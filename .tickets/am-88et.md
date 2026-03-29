---
id: am-88et
status: open
deps: []
links: []
created: 2026-03-29T21:06:34Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [ui, logging, llm]
---
# Fix datalog leaking raw LLM JSON into player-visible output

Sometimes the datalog/player-visible output prints raw LLM JSON. Investigate formatting/parsing failures, prevent raw JSON leakage in the UI, and use the latest available log example with the latest couple of offending messages as a regression reference in the ticket notes.


## Notes

**2026-03-29T21:07:46Z**

Difficulty: medium. Latest log example: ~/.local/share/angband-mechanicum/logs/convo_1774817971.jsonl. Latest couple messages in the final logged turn were: assistant message begins with raw JSON object '{ "narrative_text": "The combat subsystem disengages...'; next user message was '/eplore'. Use this file as the first regression artifact when reproducing player-visible JSON leakage in the datalog.
