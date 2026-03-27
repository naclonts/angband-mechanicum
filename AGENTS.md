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
3. Do the work. Use `tk add-note <id> "text"` to leave context for other agents.
4. Run `tk close <id>` when done.
5. Reference ticket IDs in commit messages (e.g., `am-hsdv: wire up LLM engine`).

### Orchestrating Subagents

1. **Parent agent** breaks work into tickets with dependencies (`tk create`, `tk dep`).
2. **Subagents** each pick a `tk ready` ticket, `tk start` it, do the work, and `tk close` it.
3. Downstream tickets become `tk ready` as their dependencies close.
4. Use `tk add-note <id> "text"` to pass context between agents.

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
