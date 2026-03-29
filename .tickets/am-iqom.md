---
id: am-iqom
status: open
deps: []
links: []
created: 2026-03-29T21:06:34Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [dungeon, terrain, combat]
---
# Make acid and lava traversable hazardous terrain

Acid and lava tiles should allow walking over them instead of fully blocking movement, but they should inflict damage on traversal. Lava should deal more damage than acid. Update deterministic dungeon movement/combat rules, UI/log feedback, tests, and docs.


## Notes

**2026-03-29T21:07:46Z**

Difficulty: medium. Hazard values should be asymmetric: lava deals more damage than acid. Update movement, feedback, tests, and docs only; no blocking traversal.
