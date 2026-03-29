# Real-Time ARPG Mode

**Status:** Future — not ready to work on. Spec draft only.

**Inspiration:** Shadowrun for Sega Genesis — isometric real-time action RPG with dialogue, exploration, and combat in the same view.

## Open Questions

- Tech stack: stay Python (pygame/arcade) or move to a game engine (Godot, Bevy)?
- How much of the existing TUI codebase carries over vs. becomes a separate project?
- Real-time combat system: pause-and-play (Baldur's Gate), full real-time (Diablo), or hybrid?
- Does the LLM narrative system adapt to real-time, or does it stay turn-based in dialogue?
- Art pipeline: ASCII → pixel art → 3D? At what point?

## What to Preserve from Current Game

- LLM-powered narrative and dialogue
- Entity tracking and game history system
- Dungeon generation algorithms (adapt from tile-based to graphical)
- WH40K Adeptus Mechanicus theme and tone
- Conversation system with NPC portraits

## Notes

See ticket `am-12uy` for tracking.
