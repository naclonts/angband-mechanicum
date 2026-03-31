---
id: am-tnbb
status: closed
deps: []
links: []
created: 2026-03-31T01:23:09Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [dungeon, input, ui, focus, death, save]
---
# Fix dungeon movement lockup and black-screen load transition

Bug: after moving around in the dungeon for a short time, movement input can stop responding while Tab focus cycling still works. After a few seconds the screen can go black, and pressing Escape then lands on the new/load game menu. Investigate recent save/autosave, death handling, focus/input routing, and any async dungeon turn or transition path that could leave the screen in a broken state. Reproduce against the most recent save if available. Add a regression test if the failure can be covered deterministically. Difficulty: medium.

