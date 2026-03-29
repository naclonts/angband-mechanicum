---
id: am-glv3
status: open
deps: []
links: []
created: 2026-03-29T20:10:05Z
type: task
priority: 2
assignee: Nathan Clonts
tags: [cleanup, combat, architecture]
---
# Remove or fully quarantine legacy tactical combat code

Live combat now routes into dungeon encounters and no longer uses CombatScreen or CombatEngine, but the legacy tactical modules, styles, and tests still remain as deprecated reference surface. Decide whether to remove them entirely or quarantine them behind explicit non-live references only. Update docs, tests, and code comments so the repository no longer presents the tactical path as an active subsystem.

