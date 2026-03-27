---
id: am-pyqp
status: closed
deps: []
links: []
created: 2026-03-27T20:42:59Z
type: task
priority: 2
assignee: Nathan Clonts
tags: [quality, tooling]
---
# Add strict typing and type-checking linter

Add type annotations to all existing code. Configure mypy (or pyright) in strict mode via pyproject.toml. Ensure CI/pre-commit enforces type checking. Audit all functions, dataclasses, and method signatures for complete annotations.

