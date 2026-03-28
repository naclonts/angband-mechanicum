---
id: am-pp6h
status: in_progress
deps: []
links: []
created: 2026-03-28T00:39:20Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [combat, engine, ui]
---
# Turn-based tactical combat mode

Add a new game mode for turn-based tactical combat and exploration, separate from the narrative/roleplay mode.

**Inspiration:** Angband roguelike visuals (but full Unicode, not just ASCII), Kill Team / Mechanicus turn-based tactics gameplay.

**Core mechanics:**
- Grid-based tactical map rendered in Unicode (box-drawing, blocks, symbols — richer than classic ASCII roguelikes)
- Player controls one or more units (Tech-Priest + possible allies)
- Turn structure: player moves units up to {movement} tiles, then targets enemies for attack (ranged or melee)
- Enemy AI turn: enemies move intelligently — charge into melee, shoot at range, take cover, etc.
- Combat resolution with stats (HP, damage, armor, range, movement)

**Scope for v1 (start simple):**
- Single tactical map screen with Unicode tile rendering
- One player unit, a few enemy types
- Basic move → attack → enemy turn loop
- Simple enemy AI (advance toward player, attack when in range)
- Win/lose conditions (clear enemies / player dies)

**Future iterations (not v1):**
- Multiple player units with different loadouts
- Cover/terrain effects
- Abilities and wargear
- Procedural map generation
- Integration with narrative mode (combat encounters triggered by story)
- Loot and progression between encounters


## Notes

**2026-03-28T00:40:56Z**

**Open design questions — mode transitions and state integration:**

1. **Entering combat:** How does the player transition from narrative mode to tactical combat? Options: triggered by narrative events (LLM decides a combat encounter begins), player-initiated (explore command), or both. Should there be a transition screen / briefing?

2. **Exiting combat:** What happens when combat ends? Victory → return to narrative with results summary? Defeat → death/retreat narrative? Should the LLM narrate the aftermath based on combat outcomes?

3. **Combat results → game state:** What from the battle should be persisted? Candidates: casualties (units killed/wounded), resources expended (ammo, abilities used), loot acquired, enemies defeated, territory cleared. How granular should this be?

4. **Story state → combat setup:** The narrative mode state must inform what goes into battle. Examples: if a team member died or was injured in story mode, they should NOT be placed into combat (or placed with reduced stats). NPCs recruited in story mode become available units. Wargear/items acquired in narrative should be equipped in combat. The combat roster must be derived from current narrative game state, not a separate inventory.

5. **Shared entity tracking:** This connects to am-ftxi (history/entity tracking system) — combat events should be recorded as steps in the entity history so the narrative agent knows what happened in battle and can reference it.

**2026-03-28T00:43:09Z**

**Architectural scoping — how combat fits the existing system:**

## Current Architecture Summary
- **Screens:** Textual Screen-based app: MenuScreen → GameScreen. Each screen composes widgets.
- **Engine:** `GameEngine` is the LLM seam. It processes text input, calls Claude, returns `GameResponse(narrative_text, scene_art, info_update)`. Holds conversation history, turn count, info panel state.
- **History/Entities:** `GameHistory` (engine/history.py) tracks every turn as a `Step` (player_input, narrative_text, entity_ids, info_update, timestamp). Maintains `Entity` registries (id, name, type=place|character|item, description, step_ids). Supports entity chains, co-occurrence queries, and LLM context construction. Already wired into GameEngine — entities are parsed from LLM responses and cross-referenced with steps.
- **Saves:** `SaveManager` persists engine.to_dict() + narrative_log as JSON. Autosaves after each turn.
- **App:** Single `GameEngine` instance on `app.game_engine`. Save slot on `app.save_slot`.

## Proposed Architecture for Combat Mode

### New Screen: CombatScreen
- A new Textual Screen, analogous to GameScreen but for the tactical grid view.
- Compose a grid map widget (the main tactical view), a unit info sidebar, a turn/action log, and an input/command area.
- App pushes CombatScreen when combat starts, pops back to GameScreen when it ends.

### New Engine: CombatEngine (separate from GameEngine)
- Combat logic should be **deterministic, not LLM-driven**. Movement, line-of-sight, attack resolution, damage — all computed locally. No API calls per combat turn.
- `CombatEngine` manages: grid state, unit positions, HP/stats, turn order, action points, AI decisions.
- Separate from GameEngine but shares entity references (Characters are the same Entity objects).
- Could optionally use LLM for flavor text (combat narration) but core mechanics must not depend on it.

### Grid & Rendering
- Grid is a 2D array of tiles. Each tile has terrain type + optional occupant (unit).
- Unicode rendering: use full Unicode suite — box-drawing for walls, block elements for terrain, custom symbols for units/enemies. Richer than classic ASCII roguelikes.
- The grid widget renders visible portion of the map. Consider fog of war.
- Input: arrow keys / WASD for cursor, number keys or hotkeys for actions (move, attack, end turn).

### Entity Integration (connects to am-ftxi / history.py)
- Characters in combat ARE entities from the history system. When combat starts, pull the player's party from the entity registry.
- A new EntityType may be needed, or combat-specific metadata on existing entities (HP, movement, weapon stats). Consider either:
  - (a) Extending Entity with optional combat stats fields, or
  - (b) A separate CombatUnit dataclass that wraps/references an Entity
  - Option (b) is probably cleaner — keeps Entity as the narrative-layer concept, CombatUnit as the tactical-layer concept, linked by entity_id.
- Combat events should be recorded as Steps in GameHistory so the narrative agent can reference them. e.g. a Step with player_input='[COMBAT]' and narrative_text summarizing what happened.

### Mode Transitions
- **Entering combat:** GameEngine (LLM) response could include a new field like `"combat_trigger": {"enemies": [...], "terrain": "corridor", ...}` — structured data that GameScreen detects and uses to initialize CombatScreen. Alternatively, a special narrative tag or a separate transition mechanism.
- **Exiting combat:** CombatScreen resolves to a combat result dict (who survived, loot, etc). GameScreen receives this when CombatScreen is popped, feeds it back into GameEngine as context for the next LLM turn (e.g. 'The player just won a battle against 3 servitors; Alpha-7 was wounded').
- **State flow:** narrative state → combat setup → combat resolution → narrative state. One-directional per encounter.

### Save System
- CombatEngine state needs to be serializable (to_dict/from_dict) just like GameEngine.
- If the player saves mid-combat, both GameEngine state AND CombatEngine state must be persisted.
- SaveManager may need a `mode` field ('narrative' | 'combat') so the app knows which screen to restore.

### v1 Simplifications
- Single player unit (the Tech-Priest). Party members can be added later.
- Hardcoded small maps (10x15 or similar). Procedural generation later.
- 2-3 enemy types with simple stat blocks.
- No inventory/loadout management — fixed stats.
- Combat triggered by a simple command or narrative keyword, not full LLM integration.
- Combat results summarized as a single string fed back to GameEngine.
