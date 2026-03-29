---
id: am-z9ei
status: closed
deps: []
links: []
created: 2026-03-29T19:30:26Z
type: bug
priority: 2
assignee: Nathan Clonts
tags: [ui, menus, input, regression]
---
# Fix arrow-key navigation in story selection and all menu-style screens

Arrow keys currently do not work reliably when selecting a story starting point, and similar regressions have happened across other menus where Tab is the only usable navigation path. Fix keyboard navigation for story selection and every menu-style screen so up/down arrow keys move the active selection consistently, Enter activates the focused choice, and focus defaults are sane. In addition to the immediate bug fix, add a reusable test/helper/system-level guard so future menu screens are covered by the same navigation contract and this class of regression is caught automatically.

