---
id: am-ukcl
status: open
deps: []
links: []
created: 2026-03-28T07:04:14Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [engine, llm]
---
# Pass party status (alive/dead/HP) to LLM context

After combat, the LLM has no awareness of party member status. A downed party member (Volta) was not mentioned when looking around, and then spoke dialogue despite being dead. The engine must include current party status (alive/dead, HP) in the context sent to the LLM so it can reflect casualties in narrative and prevent dead characters from acting.

