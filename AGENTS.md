# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project

Angband Mechanicum — a CLI game where the player is a WH40K Adeptus Mechanicus Tech-Priest. Built with Python + Textual TUI framework. See `docs/context.md` for full context.

## Stack

- **Language:** Python 3.11+
- **Package manager:** uv (not pip/venv directly)
- **TUI framework:** Textual (by Textualize)
- **Run:** `uv run angband-mechanicum`
- **Install deps:** `uv sync`

## Project Structure

```
src/angband_mechanicum/
├── app.py                    # App entry point
├── theme.py                  # CRT green theme
├── styles/game.tcss          # Layout CSS
├── screens/game_screen.py    # Main 4-pane screen
├── widgets/                  # UI components (scene, portrait, narrative, info, prompt)
├── engine/game_engine.py     # Game logic — LLM integration seam
└── assets/placeholder_art.py # ASCII art and placeholder text
```

## Task Management

This project uses [`ticket`](https://github.com/wedow/ticket) (`tk`) for issue tracking. Tickets are markdown files in `.tickets/`.

```bash
tk ls                      # List all open tickets
tk ready                   # Tickets ready to work on (deps resolved)
tk blocked                 # Tickets waiting on dependencies
tk show <id>               # View ticket details
tk start <id>              # Mark as in progress before working
tk close <id>              # Mark done when finished
tk create "title" -d "description" -t feature  # Create new ticket
tk add-note <id> "text"    # Add progress notes
tk dep <id> <dep-id>       # Declare id depends on dep-id
```

### Agent Workflow

1. Run `tk ready` to see available tickets.
2. Run `tk start <id>` before working on a ticket.
3. **Always use a worktree** for implementation work (`isolation: "worktree"` on the Agent tool). Multiple agents may be working on the codebase concurrently in separate worktrees — never assume you have exclusive access to the main working directory.
4. Do the work. Use `tk add-note <id> "text"` to leave context for other agents.
5. Run `tk close <id>` when done.
6. Reference ticket IDs in commit messages (e.g., `am-hsdv: wire up LLM engine`).
7. Parent agent merges the worktree branch back to main after subagent completes.

### Parallel Work with Worktrees

This project uses **git worktrees** for parallel agent isolation. Each subagent works in its own worktree (separate branch + working directory), avoiding filesystem conflicts. Work merges back via branch merge or PR.

**How it works:**

1. **Parent agent** decomposes work into tickets with dependencies.
2. **Parent spawns subagents** each in an isolated worktree (Claude Code: `isolation: "worktree"` on the Agent tool).
3. Each subagent gets its own branch and full repo copy. No shared mutable state.
4. Subagent does `tk start <id>`, works, commits, `tk close <id>`.
5. Parent merges branches back to main (or opens PRs for review).

**Why this works with `tk`:** Each ticket is its own `.md` file in `.tickets/`. Agents working different tickets edit different files, so git merges cleanly. No locking or coordination primitives needed.

**Example — parent agent orchestrating two parallel tasks:**

```bash
# Create tickets
tk create "Add strict typing" -t task --tags quality
# → am-pyqp
tk create "Scrollable datalog" -t feature --tags ui
# → am-1ohi

# Spawn subagents (pseudocode — actual syntax depends on agent platform)
# Agent A: works am-pyqp in worktree, branch: typing
# Agent B: works am-1ohi in worktree, branch: scrollable-datalog

# After both complete, merge branches
git merge typing
git merge scrollable-datalog
```

**Subagent checklist (run these in your worktree):**

1. `uv sync` — install deps in worktree's venv
2. `tk start <id>` — claim your ticket
3. Do the work, commit with ticket ID in message (e.g., `am-pyqp: add mypy strict config`)
4. `tk close <id>`
5. Exit — parent agent handles the merge

**Concurrency awareness:** Assume other agents may be active in other worktrees at any time. Do not modify files outside your worktree. The parent agent is responsible for merge coordination.

**Dependency chains:** If ticket B depends on ticket A (`tk dep B A`), do NOT run them in parallel. Run A first, merge it, then spawn B. Use `tk ready` to check what's unblocked.

### Creating Good Tickets

```bash
# Feature with description and tags
tk create "Add combat system" -d "Turn-based combat for dungeon encounters" -t feature --tags combat,engine

# Bug
tk create "Scene art overflows pane" -d "Art wider than 70 chars breaks layout" -t bug --tags ui

# With dependency
tk create "Add enemy AI" -d "Enemies act on their turn" -t feature --tags combat
tk dep <new-id> <combat-system-id>
```

## Code Conventions

- Keep widgets in separate files under `widgets/`
- Game logic goes in `engine/`, UI logic in `screens/` and `widgets/`
- All terminal aesthetics are CRT phosphor green — maintain this in any new UI
- ASCII/unicode art in `assets/`
- TCSS styling in `styles/`
- Use `@work(exclusive=True)` for async operations in Textual screens
- Engine is the LLM seam: `engine/game_engine.py` processes player input. UI code should not call LLM APIs directly.
- Widgets are dumb: they display data. Game logic lives in `engine/`.
