---
id: am-d97w
status: closed
deps: []
links: []
created: 2026-03-28T02:09:46Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [engine, combat]
---
# Fix LLM never returning combat_trigger

The LLM consistently omits combat_trigger from JSON responses despite system prompt instructions. Every logged response is missing the field, so combat never triggers automatically. Fix: include combat_trigger with default value in the JSON schema example, and add a few-shot example showing it in use.

