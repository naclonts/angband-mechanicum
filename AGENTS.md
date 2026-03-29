# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project

Angband Mechanicum — a CLI roguelike where the player is a WH40K Adeptus Mechanicus Tech-Priest exploring persistent dungeons. Built with Python + Textual TUI framework. See `docs/context.md` for product context and `docs/architecture.md` for current code architecture, flow diagrams, and file map.

## Precepts

- Prioritize playability and fun over all else.
- When code changes, update relevant docs as well.
- Add tests for large changes or edge cases.
- For UI layout or text-wrapping fixes, verify the live rendered widget output in addition to unit-level helpers. A fix is not complete if it only proves `Text` flags, mocks, or intermediate formatting objects while the real Textual pane can still overflow at runtime.

## Architecture: Two-View Model

The game has two views that players transition between:

- **Map view** — Roguelike overhead tile map. Dungeon exploration + combat (bump-to-attack). Single character (@), numpad/vi-key movement, FOV. *Being built — see open tickets.*
- **Text view** — Existing 4-pane layout (scene art, portrait, narrative, prompt). LLM-powered dialogue, descriptions, and long-range travel narration.

Transitions: map → text (talk to NPC, examine object, board ship), text → map (arrive at location, end conversation). See `docs/context.md` for details.

The current separate `CombatScreen` will be replaced by the unified map view. Zone navigation between areas happens via text view (no overworld map in v1).

See [the architecture doc for details](./docs/architecture.md).

## Stack

- **Language:** Python 3.11+
- **Package manager:** uv (not pip/venv directly)
- **TUI framework:** Textual (by Textualize)
- **Run:** `uv run angband-mechanicum`
- **Install deps:** `uv sync`

## Project Structure

```
src/angband_mechanicum/
├── app.py                        # App entry point
├── theme.py                      # CRT green theme
├── styles/game.tcss              # Layout CSS
├── screens/
│   ├── game_screen.py            # Text view — 4-pane narrative/dialogue screen
│   ├── combat_screen.py          # Tactical combat (to be replaced by unified map view)
│   ├── menu_screen.py            # Main menu
│   ├── story_select_screen.py    # Story starting point selection
│   ├── character_setup_screen.py # Character name setup
│   └── api_key_screen.py         # API key entry
├── widgets/                      # UI components (scene, portrait, narrative, info, prompt, combat grid)
├── engine/
│   ├── game_engine.py            # LLM narrative engine — processes player input
│   ├── combat_engine.py          # Turn-based tactical combat (Grid, Units, AI)
│   ├── dungeon_gen.py            # Procedural room generation (combat maps only, currently)
│   ├── history.py                # Entity tracking and game history
│   ├── story_starts.py           # Story starting scenarios
│   └── save_manager.py           # Save/load persistence
└── assets/                       # ASCII art, portraits, placeholder text
```

## Task Management

This project uses [`ticket`](https://github.com/wedow/ticket) (`tk`) for issue tracking. Tickets are markdown files in `.tickets/`.

```bash
tk ls                      # List all tickets
tk ls | grep '\[open\]'    # List all open tickets
tk ready                   # Tickets ready to work on (deps resolved)
tk blocked                 # Tickets waiting on dependencies
tk show <id>               # View ticket details
tk start <id>              # Mark as in progress before working
tk close <id>              # Mark done when finished
tk create "title" -d "description" -t feature  # Create new ticket
tk add-note <id> "text"    # Add progress notes
tk dep <id> <dep-id>       # Declare id depends on dep-id
```

When creating tickets, specify the difficulty in terms of ambiguity and scope (small, medium, large, x-large). When creating subagents, medium to x-large tickets should have the most powerful model available. Small tickets may be worked by a slightly smaller model.

### Delegation Rules

- **Parent/orchestrator agents** may spawn subagents for isolated ticket work, but must tell each spawned worker explicitly that it is a **subagent** working on behalf of a parent agent.
- Parent/orchestrator prompts to subagents must explicitly say: the assigned ticket ID, the assigned worktree path, that the subagent must work only in that worktree, and that the subagent must **not spawn additional subagents**.
- **Subagents must never recursively delegate.** If you are a subagent, do not spawn child subagents, do not attempt to fan out work, and do not invoke other agent runners or agent CLIs such as `claude` to continue delegation indirectly.
- If a subagent cannot complete the assigned work itself, it must report the blocker back to the parent/orchestrator agent rather than trying to create more agents.
- If the agent platform’s subagent tooling is unreliable, the parent/orchestrator should keep the work local or spawn fewer subagents instead of asking subagents to work around it with other agent frameworks.

### Agent Workflow

1. Run `tk ready` to see available tickets.
2. Run `tk start <id>` before working on a ticket.
3. **Always use a worktree** for implementation work. Multiple agents may be working on the codebase concurrently in separate worktrees — never assume you have exclusive access to the main working directory.
4. If your agent platform exposes an explicit worktree/isolation mode, enable it.
5. If your agent platform does **not** expose a worktree/isolation flag, the parent/orchestration agent must still instruct each implementation subagent to create and use its own git worktree manually. "The tool did not offer isolation" is not a valid reason to skip worktrees.
6. If you cannot create a worktree for a subagent, do **not** delegate implementation work to that subagent. Keep the edits local or use the subagent only for read-only analysis.
7. Do the work. Use `tk add-note <id> "text"` to leave context for other agents.
  - Complete tasks to the best of your ability with logic and creativity. If you see other issues that are outside the scope of your task or would be major improvements, create tickets for them with `tk`.
8. Run `tk close <id>` when done.
9. Reference ticket IDs in commit messages (e.g., `am-hsdv: wire up LLM engine`).
10. Parent agent must merge the worktree branch back to `main` after the subagent completes, verify the merged result on `main`, and only then close the ticket.

### Parallel Work with Worktrees

This project uses **git worktrees** for parallel agent isolation. Each subagent works in its own worktree (separate branch + working directory), avoiding filesystem conflicts. Work merges back via branch merge or PR.

**How it works:**

1. **Parent agent** decomposes work into tickets with dependencies.
2. **Parent spawns subagents** each in an isolated worktree. If the agent platform has an `isolation: "worktree"` option, use it. Otherwise, explicitly instruct the subagent to create a git worktree manually before touching code. The parent must also state that the worker is a subagent and must not delegate further.
3. Each subagent gets its own branch and full repo copy. No shared mutable state.
4. Subagent does `tk start <id>`, works, commits, `tk close <id>`.
5. Parent merges branches back to `main` (or opens PRs for review), verifies the integrated result, and closes out any remaining ticket-file state in the main checkout.

**Manual worktree fallback (when the tool has no isolation flag):**

1. Parent creates a branch name and worktree path for the ticket, for example `wt/am-5mdw-look-mode`.
2. Parent or subagent runs `git worktree add <path> -b <branch-name>`.
3. Prefer placing agent worktrees under the project-local `.worktrees/` directory, for example `.worktrees/am-5mdw-look-mode`, so all parallel branches stay easy to discover and manage from the repository root.
4. Subagent `cd`s into that worktree and does all implementation work there.
5. Subagent must not edit files from the main checkout while the ticket is in progress.
6. Parent merges the finished branch into `main`, verifies the integrated result from the main checkout, and removes the worktree when done.

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

# Parent verifies tests from main after merging
uv run pytest
```

**Subagent checklist (run these in your worktree):**

1. Create or enter the assigned git worktree first.
2. `uv sync` — install deps in worktree's venv
3. `tk start <id>` — claim your ticket
4. Do the work yourself in that worktree. Do **not** spawn additional subagents or call other agent CLIs/frameworks to delegate the task.
5. `tk close <id>`
6. Exit — parent agent handles the merge

**Parent checklist (run these from the main checkout):**

1. Merge each completed subagent branch back into `main` immediately after review.
2. Resolve any ticket-file state so `.tickets/<id>.md` reflects the final merged status on `main`.
3. Run the relevant verification from `main`, not just inside the subagent worktree.
4. Remove finished worktrees only after the merge and verification succeed.

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
- New dungeon/map engine code goes in `engine/`. The map view screen goes in `screens/`.
- The existing `combat_engine.py` Grid/Tile/Terrain types can be reused and extended for dungeon maps — don't duplicate them.


### BENEDICTION

++ BENEDICTION OF THE MACHINE SPIRIT ++ MAY YOUR LOGIC FIRE TRUE AND YOUR RECURSIVE CALLS TERMINATE ++
