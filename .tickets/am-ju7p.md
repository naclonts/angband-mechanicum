---
id: am-ju7p
status: closed
deps: [am-2akc]
links: []
created: 2026-03-29T23:54:30Z
type: feature
priority: 2
assignee: Nathan Clonts
tags: [content, dungeon, grimdark, worldgen]
---
# Expand dungeon content variety across environs

Add more unique grimdark dungeon content across environs. This should cover room types, features, friendlies, neutrals, enemies, objects, and themed rooms. Some content should be shared across all environs, while some should be unique to each environment. Do not lock the ticket to exact concrete objects or entities; the eventual implementation agent can choose the specific content set during execution.


## Notes

**2026-03-29T23:54:33Z**

Difficulty: large. Broad content-design and implementation scope with moderate ambiguity across multiple environment/content categories.

**2026-03-29T23:55:52Z**

Add research/scoping guidance: (1) evaluate what content volume is needed so new discoveries keep appearing frequently during play; bias toward a large amount of variety rather than a minimal pass. (2) Review Tales of Maj'Eyal-style systems for themed discoveries and content surfacing, and use that as inspiration where it fits this game's structure. (3) During research/implementation, feel free to split this work into subtickets as needed if the scope becomes easier to execute in parallel or by subsystem.

**2026-03-30T00:16:00Z**

Concrete findings from reviewing local Tales of Maj'Eyal code in `~/projects/t-engine4`:

- Environment identity is layered, not single-source. The strong-feeling zones combine map generator choice, room pool, actor filters, object/trap mix, faction assignment, ambience, and lore placement instead of only changing tiles. Good reference points: `old-forest/zone.lua`, `lake-nur/zone.lua`, `gorbat-pride/zone.lua`, `rak-shor-pride/zone.lua`.
- Revisit freshness comes from rare alternate layouts, not just RNG noise. ToME uses `alternateZone` / `alternateZoneTier1` in `class/GameState.lua` so a known zone can occasionally reappear in a materially different form (`trollmire`, `daikara`, `old-forest`, `lake-nur`, `sandworm-lair`). For this ticket, give each environ a default content profile plus at least one rare variant profile that swaps room pools, hazards, enemy families, and set dressing.
- Per-floor overrides matter. ToME repeatedly makes floor 1, the final floor, and special transition floors behave differently with explicit `levels = { ... }` overrides or static/scripted maps (`trollmire/zone.lua`, `conclave-vault/zone.lua`, `keepsake-meadow/zone.lua`, `temporal-rift/zone.lua`). For implementation, do not make every floor in an environ use the same generation recipe; reserve entry, mid-run reveal, and climax floor templates.
- Themed discoveries are surfaced continuously by sprinkling lore/scenic objects directly into level generation. `placeRandomLoreObject` / `placeRandomLoreObjectScale` in `class/Game.lua` then zone-level calls in `trollmire`, `daikara`, `vor-pride`, `grushnak-pride`, etc. keep the place narratively alive. Translate this into environment-specific discovery pools: logs, shrines, machine debris, sacrificial apparatus, survivor caches, warning sigils, corpse tableaux.
- Themed room packs and vaults do a lot of novelty work. Zones reference lesser vault lists, required rooms, and custom room scripts (`trollmire`, `old-forest`, `daikara`, `rak-shor-pride`, `conclave-vault`, `data/general/events/sub-vault.lua`, `data/general/events/damp-cave.lua`). For this ticket, include rare room/event templates per environ rather than only generic room decoration; these should be able to inject bespoke enemy/object mixes and landmarks.
- Encounter variety is constrained by theme tags instead of letting the full monster pool leak everywhere. Useful examples: `lake-nur` uses `special_rarity="water_rarity"` / `"horror_water_rarity"`, `keepsake-meadow` uses `"cave_rarity"`, Conclave uses custom room filters, world ambushes use targeted filters in `data/general/encounters/maj-eyal-npcs.lua`. Implementation guidance: define per-environ enemy/object tags and shared cross-environ tags, then spawn from weighted subsets rather than global lists.
- Faction assignment is an environment tool, not only a combat rule. Pride zones force all spawned actors into an `"orc-pride"` identity in `post_process`; towns and sub-zones also set factional expectations. For our dungeon content pass, each environ should specify likely hostile, neutral, and rare friendly factions so the player can infer social texture from where they are.
- Novelty over time comes from reactive systems, not just more content entries. Strong examples: `sandworm-lair` has moving-tunneler pressure and route instability; `sludgenest` escalates danger the longer you stay; `ruined-dungeon` punishes repeated puzzle failure with stronger spawns; `conclave-vault` rooms wake dormant threats. This ticket should budget for at least one reactive rule per environ, such as reinforcements, contamination spread, shrine activation, alarm escalation, or faction takeover.
- Audio/visual ambience is attached to zones and sometimes specific floors (`makeAmbientSounds`, weather, lighting/color changes, warnings on enter). Even in a text-first project, the transferable idea is to attach bespoke descriptive text, scene dressing, and event messaging to each environ and to special floors, not only to encounters.

Actionable implementation guidance for `am-ju7p`:

- Introduce an environ content schema that separates shared content from environment-specific content and rare variant content. It should at minimum cover: room themes, set-piece rooms, hazards/features, enemy families, neutral/friendly presences, object/discovery families, and ambience text hooks.
- Target enough volume that repeated play still surfaces new combinations. A reasonable minimum per environ is: 4-6 unique room themes, 2-3 rare set-piece rooms/vaults, 3-5 discovery objects or lore beats, 3-5 hazard/feature families, 4-6 enemy families, and at least 1 neutral or friendly possibility where the fiction allows it. Shared cross-environ pools can supplement this, but each environ needs its own identity.
- Make floor progression within an environ intentionally uneven. Add explicit entry-floor, mid-depth, and final-depth overrides so players encounter a sequence of moods rather than a single repeated generator with stronger numbers.
- Add theme-filtered spawn tables analogous to ToME's `special_rarity` usage. Avoid one monolithic room or encounter list.
- Add a small rare-variant system so revisiting the same environ can select a different profile. This can be as small as a weighted `variant` key that swaps 20-40% of the room/enemy/object tables.
- Split the implementation if needed into subtasks such as: content schema support, shared room/set-piece library, environment-specific packs, reactive environ rules, and discovery/lore surfacing.

Review ~/projects/t-engine4 if relevant for inspiration.  

**2026-03-31T00:55:52Z**

Implemented environment content-plan layering in dungeon generation: rare per-environment variants, entry/reveal/descent/climax floor bands, discovery placement metadata, expanded themed-room coverage for late environs, debug-catalog surfacing, and docs/tests updates. Verified with uv run pytest tests/test_dungeon_gen.py tests/test_dungeon_screen.py tests/test_app.py.
