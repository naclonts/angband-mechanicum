# Angband Mechanicum

A CLI-based game set in the Warhammer 40K universe. The player is an Adeptus Mechanicus Tech-Priest on a forge world.

## Core Concept

- **Text adventure** with free-text input (type what you want to do, no menu selection)
- **LLM-powered narrative** generates continuations based on player input
- **Terminal green CRT aesthetic** — all unicode/ASCII art in phosphor green
- **Rich TUI layout** with multiple panes: scene art, character portrait, narrative log, info panel, and command prompt

## UI Layout

```
+---------------------------+------------+
|                           |  Portrait  |
|     Scene Image           |  (unicode) |
|     (unicode art)         |            |
+---------------------------+------------+
|                           | Info Panel |
|     Narrative /           | (location, |
|     Game Text             |  date,     |
|                           |  stats)    |
|                           +------------+
|                           | > prompt   |
+---------------------------+------------+
```

## Planned Features (Phase 2+)

- **Roguelike dungeon exploration** (Angband/Rogue-inspired)
- **Turn-based multi-character gameplay** — cycle through a team of 3 characters
- **Subterranean/forge-world environments** — procedurally generated
- **Combat** against Chaos, xenos, and other threats
- **Image generation pipeline** — generate images via AI, convert to unicode for terminal display

## Tech Stack

- Python, managed with uv
- Textual (TUI framework)
- Anthropic Claude API (narrative generation — future)
