"""Game engine -- processes player input and returns narrative responses via Claude API."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import MessageParam

from angband_mechanicum.assets.placeholder_art import INTRO_NARRATIVE as DEFAULT_INTRO_NARRATIVE
from angband_mechanicum.engine.combat_engine import (
    CombatResult,
    ENEMY_TEMPLATES,
    HARDCODED_MAPS,
    PARTY_TEMPLATES,
    auto_place_enemies,
)
from angband_mechanicum.engine.dungeon_gen import (
    GeneratedMap,
    RoomHint,
    generate_map_from_hint,
)
from angband_mechanicum.engine.history import EntityType, GameHistory

logger: logging.Logger = logging.getLogger(__name__)


def _log_dir() -> Path:
    """Return the log directory next to saves, respecting XDG_DATA_HOME."""
    xdg_data: str = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    log_path: Path = Path(xdg_data) / "angband-mechanicum" / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    return log_path

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from LLM output, stripping markdown code fences if present."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try stripping markdown code fences
    match = _JSON_FENCE_RE.search(text)
    if match:
        return json.loads(match.group(1))
    # Try extracting from first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("No JSON found in response", text, 0)

MODEL: str = "claude-sonnet-4-20250514"
MAX_TOKENS: int = 2048

DEFAULT_ART_WIDTH: int = 56
DEFAULT_ART_HEIGHT: int = 16


def _build_scene_art_instructions(width: int, height: int) -> str:
    """Build the scene art section of the system prompt with dynamic pane dimensions."""
    return f"""\

## Scene Art
You MUST also provide ASCII/unicode art for the scene_art field that depicts the \
current environment or location. This art is displayed in the "ENVIRONMENT" pane of \
the game UI.

Rules for scene art:
- Use box-drawing characters (╔═╗║╚╝┌─┐│└┘├┤┬┴┼), blocks (█▓▒░), and symbols \
(⚙⛨◉▬╬) to create atmospheric scenes.
- Art MUST be no wider than {width} characters per line (to fit the scene pane).
- Art should be {max(height - 4, 4)}-{height} lines tall to fill the pane vertically.
- Depict the physical environment: rooms, corridors, machinery, doorways, ruins, etc.
- Match the scene to what is happening in the narrative — if the player enters a \
corridor, show a corridor; if they are in a forge, show forge equipment.
- Keep a dark, industrial, gothic sci-fi aesthetic.
- Do NOT use Rich markup in scene_art — plain text/unicode only.
- Always provide scene_art when the location or environment changes. If the player \
stays in the same place and nothing visually changes, set scene_art to null.
"""

_SYSTEM_PROMPT_BASE: str = """\
You are the narrative engine for Angband Mechanicum, a text-based dungeon-crawling \
RPG set in the Warhammer 40,000 universe. You narrate the world and respond to the \
player's actions.

## Setting
The player is a **Tech-Priest {player_name}** of the Adeptus Mechanicus. They are \
stationed on the forge world **Metallica Secundus**, in the great manufactorum-city \
**Angband Mechanicum**. A priority signal has been received — seismic anomalies and \
unidentified energy signatures detected in the deep strata beneath the forge. The \
Fabricator-Locum has assigned the player to investigate.

The player has two acolytes assigned to their expedition:
- **Skitarius Alpha-7** — a battle-scarred ranger with a galvanic rifle
- **Enginseer Volta** — young, eager, still more flesh than machine, carries a power axe

A servo-skull hovers nearby. The cargo lift to the underhive awaits.

## Tone & Style
- Dark, atmospheric, gothic sci-fi. The Imperium is vast and decaying; technology is \
sacred and poorly understood.
- Use Adeptus Mechanicus terminology naturally: mechadendrites, binary cant, \
Noosphere, Machine God / Omnissiah, data-hymns, etc.
- Responses are 2-4 short paragraphs. Keep them punchy and evocative.
- Use Textual Rich markup for emphasis: [bold]...[/bold] for important things, \
[dim]...[/dim] for atmospheric asides or whispered machine-cant.
- Never break character. You ARE the world.

## Response Format
You MUST respond with a valid JSON object. No text outside the JSON. Every response \
MUST include ALL five fields shown below — do not omit any.

{
  "narrative_text": "Your narrative response (string, required)",
  "scene_art": "ASCII/unicode art or null if unchanged",
  "info_update": null or {"key": "value"} dict,
  "entities": [],
  "combat_trigger": false,
  "room_hint": null or { room_type, features, theme, name } (optional, only when combat_trigger is true),
  "speaking_npc": null or "entity_id_of_speaking_character"
}

### combat_trigger (REQUIRED — must appear in every response)
Set to true when hostiles attack, ambush, or the player initiates combat. \
Set to false for all other situations (exploration, dialogue, tension without violence). \
When true, describe enemies appearing in narrative_text but do NOT narrate the \
fight — the game has a separate tactical combat system.

Example — exploration (no combat):
{"narrative_text": "The corridor stretches ahead...", "scene_art": null, \
"info_update": null, "entities": [], "combat_trigger": false}

Example — combat begins:
{"narrative_text": "Corrupted servitors lurch from the shadows, weapons raised!", \
"scene_art": null, "info_update": {"Threat Level": "EXTREME"}, \
"entities": [{"name": "Corrupted Servitor", "type": "character", \
"description": "A servitor twisted by dark tech-heresy"}], "combat_trigger": true}

When combat_trigger is true, you may also provide a "room_hint" object to influence \
the tactical map layout. This is optional — if omitted, a random map is generated. \
The room_hint schema:

{
  "room_hint": {
    "room_type": "open_room" | "small_chamber" | "corridor" | "pillared_hall" | "l_shaped" | "cross_room" | "maze" | "arena",
    "features": ["columns", "water", "debris", "growths", "cover", "terminals"],
    "theme": "forge" | "sewer" | "corrupted" | "overgrown" | "industrial" | "hive",
    "name": "Optional evocative name for the combat location"
  }
}

Choose room_type and features that match the narrative environment. For example, \
a fight in a flooded sewer would use room_type "corridor" with features ["water", \
"debris"] and theme "sewer". A battle in a forge would use "pillared_hall" or \
"open_room" with theme "forge". A chaotic ambush in overgrown ruins might use \
"l_shaped" with features ["growths", "cover"] and theme "overgrown".

### speaking_npc (REQUIRED — must appear in every response)
Set to the entity id of the character who is primarily speaking or being directly \
interacted with in this response. This is used to show that character's portrait \
in the UI. Set to null when no specific NPC is speaking or the scene is general \
exploration/narration. Only use entity ids from the Known Entities list or from \
new entities introduced in the same response's entities array.

Example — NPC dialogue:
{"narrative_text": "Alpha-7 turns to you...", "speaking_npc": "skitarius-alpha-7", ...}

Example — exploration (no speaker):
{"narrative_text": "The corridor stretches ahead...", "speaking_npc": null, ...}

The scene_art field should contain ASCII/unicode art depicting the current environment. \
Provide it when the scene or location changes; set to null if the environment has not \
visually changed since the last response.

The info_update field is optional (null if nothing changed). Use it when something \
meaningful changes, for example:
- {"Location": "Cargo Lift Shaft"} when the player moves
- {"Threat Level": "ELEVATED"} when danger increases
- {"Objective": "Investigate seismic anomaly"} for quest updates


### Entity Tracking
The entities array tracks places, characters, and items that appear in your narrative \
response. This builds the game's structured memory of the world.
- For known entities (listed in the Known Entities section below): reference by id \
only, e.g. {"id": "skitarius-alpha-7"}
- For NEW entities not yet tracked: provide full details, e.g. \
{"name": "Ancient Cogitator", "type": "item", "description": "A pre-Imperial data terminal, still humming with power"}
- Valid types: "place", "character", "item"
- Include all entities meaningfully involved in the scene — not passing mentions, but \
characters who act, places the player is in or moves to, and items that are used or discovered
- Return an empty array [] if no entities are relevant to this response
"""

def _strip_rich_markup(text: str) -> str:
    """Strip Rich markup tags from text for use in LLM prompts."""
    return (
        text.replace("[bold]", "")
        .replace("[/bold]", "")
        .replace("[dim]", "")
        .replace("[/dim]", "")
    )


_DEFAULT_STORY_SUFFIX: str = """
## Story So Far
The player has just received this introduction:

""" + _strip_rich_markup(DEFAULT_INTRO_NARRATIVE)


NOOSPHERE_ERRORS: list[str] = [
    "The Noosphere connection falters... static floods your cognition buffers. "
    "[dim]++ RETRY WHEN THE MACHINE SPIRIT IS WILLING ++[/dim]",
    "A cascade of corrupt data-packets disrupts the link. Your servo-skull emits "
    "a distressed bleat as the connection drops. [dim]++ SIGNAL LOST ++[/dim]",
    "Your communion with the datasphere is severed — a momentary lapse in the "
    "sacred frequencies. [dim]++ THE OMNISSIAH TESTS YOUR PATIENCE ++[/dim]",
]


@dataclass
class GameResponse:
    narrative_text: str
    scene_art: str | None = None
    info_update: dict[str, str] | None = None
    combat_trigger: bool = False
    room_hint: dict[str, Any] | None = None
    speaking_npc: str | None = None


class GameEngine:
    """Processes player input via the Anthropic Claude API and returns narrative responses."""

    # Default party members — entity IDs matching the seeded entities
    DEFAULT_PARTY_IDS: list[str] = [
        "skitarius-alpha-7",
        "enginseer-volta",
    ]

    def __init__(self, player_name: str = "Magos Explorator") -> None:
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic()
        self._player_name: str = player_name
        self._conversation_history: list[MessageParam] = []
        self._error_count: int = 0
        self._turn_count: int = 0
        self._current_scene_art: str | None = None
        self._info_panel: dict[str, str] = {}
        self._history: GameHistory = GameHistory()
        self._seed_starting_entities()
        self._party_member_ids: list[str] = list(self.DEFAULT_PARTY_IDS)
        self._log_path: Path = (
            _log_dir() / f"convo_{int(time.time())}.jsonl"
        )
        self._scene_pane_width: int = DEFAULT_ART_WIDTH
        self._scene_pane_height: int = DEFAULT_ART_HEIGHT
        self._integrity: int = 20
        self._max_integrity: int = 20
        self._party_hp: dict[str, tuple[int, int]] = self._init_party_hp()
        self._story_suffix: str = _DEFAULT_STORY_SUFFIX
        self._story_start_id: str | None = None

    def set_scene_pane_size(self, width: int, height: int) -> None:
        """Update the scene pane dimensions used in LLM prompts.

        Called by the UI whenever the environment pane is mounted or resized.
        """
        self._scene_pane_width = max(width, 20)
        self._scene_pane_height = max(height, 6)

    @property
    def player_name(self) -> str:
        return self._player_name

    @property
    def integrity(self) -> int:
        return self._integrity

    @property
    def max_integrity(self) -> int:
        return self._max_integrity

    def set_integrity(self, hp: int) -> None:
        """Set the current integrity (clamped to [0, max_integrity])."""
        self._integrity = max(0, min(hp, self._max_integrity))

    def take_damage(self, amount: int) -> None:
        """Reduce integrity by *amount* (minimum 0)."""
        self._integrity = max(0, self._integrity - amount)

    def _init_party_hp(self) -> dict[str, tuple[int, int]]:
        """Initialize party member HP from PARTY_TEMPLATES."""
        result: dict[str, tuple[int, int]] = {}
        for pid in self._party_member_ids:
            if pid in PARTY_TEMPLATES:
                s = PARTY_TEMPLATES[pid]["stats"]
                result[pid] = (s["hp"], s["max_hp"])
        return result

    def apply_story_start(self, story: Any) -> None:
        """Configure the engine for a specific story starting scenario.

        Parameters
        ----------
        story:
            A :class:`~angband_mechanicum.engine.story_starts.StoryStart`
            instance. Uses ``Any`` type to avoid circular import at
            module level.
        """
        self._story_start_id = story.id
        self._story_suffix = (
            "\n## Story So Far\nThe player has just received this introduction:\n\n"
            + _strip_rich_markup(story.intro_narrative)
        )
        if story.info_overrides:
            self._info_panel = dict(story.info_overrides)

    @property
    def party_hp(self) -> dict[str, tuple[int, int]]:
        """Per-party-member HP: {entity_id: (current_hp, max_hp)}."""
        return dict(self._party_hp)

    def get_status_data(self) -> dict[str, Any]:
        """Return structured data for the STATUS panel.

        Returns a dict with:
          - info: dict of key-value info fields (DESIGNATION, LOCATION, etc.)
          - integrity: (current, max) player HP
          - party: list of {id, name, hp, max_hp} dicts
        """
        party: list[dict[str, Any]] = []
        for pid in self._party_member_ids:
            if pid in PARTY_TEMPLATES:
                tpl = PARTY_TEMPLATES[pid]
                hp, max_hp = self._party_hp.get(
                    pid, (tpl["stats"]["hp"], tpl["stats"]["max_hp"])
                )
                party.append({
                    "id": pid,
                    "name": tpl["name"],
                    "hp": hp,
                    "max_hp": max_hp,
                })
        return {
            "info": dict(self._info_panel),
            "integrity": (self._integrity, self._max_integrity),
            "party": party,
        }

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def party_member_ids(self) -> list[str]:
        """Entity IDs of current party members (excluding the player Tech-Priest)."""
        return list(self._party_member_ids)

    @property
    def history(self) -> GameHistory:
        return self._history

    def _seed_starting_entities(self) -> None:
        """Pre-register entities from the game's opening scenario."""
        reg = self._history.register_entity
        # Characters
        reg("Skitarius Alpha-7", EntityType.CHARACTER,
            "A battle-scarred ranger with a galvanic rifle")
        reg("Enginseer Volta", EntityType.CHARACTER,
            "Young, eager, still more flesh than machine, carries a power axe")
        # Places
        reg("Metallica Secundus", EntityType.PLACE,
            "Forge world where the game is set")
        reg("Angband Mechanicum", EntityType.PLACE,
            "The great manufactorum-city on Metallica Secundus")
        # Items
        reg("Servo-skull", EntityType.ITEM,
            "A hovering skull drone that accompanies the player's expedition")

    def _build_system_prompt(self) -> str:
        """Build the full system prompt with dynamic entity registry and scene dimensions."""
        prompt = _SYSTEM_PROMPT_BASE.replace(
            "{player_name}", self._player_name
        ) + _build_scene_art_instructions(
            self._scene_pane_width, self._scene_pane_height
        ) + self._story_suffix
        registry_context = self._history.get_registry_context()
        if registry_context:
            prompt += "\n\n" + registry_context
        return prompt

    def _log_turn(
        self,
        system_prompt: str,
        messages: list[MessageParam],
        raw_response: str,
        error: str | None = None,
    ) -> None:
        """Append a turn's raw request/response to the JSONL log file."""
        entry: dict[str, Any] = {
            "timestamp": time.time(),
            "turn": self._turn_count,
            "system_prompt": system_prompt,
            "messages": messages,
            "raw_response": raw_response,
        }
        if error:
            entry["error"] = error
        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to write convo log: %s", exc)

    def _process_entities(self, entities_data: list[dict[str, Any]]) -> list[str]:
        """Process entity references from the LLM response, returning resolved IDs."""
        entity_ids: list[str] = []
        for entry in entities_data:
            if "id" in entry:
                # Known entity reference
                if self._history.get_entity(entry["id"]):
                    entity_ids.append(entry["id"])
                else:
                    logger.warning("LLM referenced unknown entity id: %s", entry["id"])
            elif "name" in entry and "type" in entry:
                # New entity introduction
                try:
                    etype = EntityType(entry["type"])
                except ValueError:
                    logger.warning("LLM returned invalid entity type: %s", entry["type"])
                    continue
                entity = self._history.register_entity(
                    name=entry["name"],
                    entity_type=etype,
                    description=entry.get("description", ""),
                )
                entity_ids.append(entity.id)
            else:
                logger.warning("Malformed entity entry from LLM: %s", entry)
        return entity_ids

    # -- Encounter generation --------------------------------------------------

    _ENCOUNTER_SYSTEM_PROMPT: str = """\
You are the encounter designer for Angband Mechanicum, a WH40K dungeon-crawling RPG.
Given the current story context, select enemies for a tactical combat encounter.

Available enemy templates (template_key -> name, max_hp, attack, armor):
{template_list}

Rules:
- Choose 2-5 enemies appropriate to the narrative context.
- Use template_key values EXACTLY as listed above.
- Mix weaker fodder with occasional elites for interesting encounters.
- Match enemy faction to the narrative where possible (e.g., Chaos cultists in a
  corrupted area, Tyranids in an infested zone, servitors in a manufactorum).
- If nothing in the story strongly suggests a faction, pick from Mechanicum threats
  or generic enemies.

You MUST respond with ONLY a valid JSON object, no other text:
{{
    "encounter_description": "A short evocative sentence describing the enemies appearing",
    "enemies": [
        {{"template_key": "key_here", "count": N}},
        ...
    ]
}}
"""

    def _build_encounter_prompt(self) -> str:
        """Build the system prompt for encounter generation with template list."""
        lines: list[str] = []
        for key, tpl in ENEMY_TEMPLATES.items():
            s = tpl["stats"]
            lines.append(
                f"  {key}: {tpl['name']} (HP:{s['max_hp']} ATK:{s['attack']} "
                f"ARM:{s['armor']} RNG:{s['attack_range']})"
            )
        template_list = "\n".join(lines)
        return self._ENCOUNTER_SYSTEM_PROMPT.format(template_list=template_list)

    def _default_encounter(self) -> dict[str, Any]:
        """Return a fallback encounter when LLM generation fails."""
        fodder_keys = [
            k for k, t in ENEMY_TEMPLATES.items()
            if t["stats"]["max_hp"] <= 10
        ]
        elite_keys = [
            k for k, t in ENEMY_TEMPLATES.items()
            if t["stats"]["max_hp"] > 10
        ]
        enemies: list[dict[str, Any]] = []
        if fodder_keys:
            pick = random.choice(fodder_keys)
            enemies.append({"template_key": pick, "count": random.randint(2, 3)})
        if elite_keys:
            pick = random.choice(elite_keys)
            enemies.append({"template_key": pick, "count": 1})
        if not enemies:
            # Absolute fallback
            enemies = [
                {"template_key": "servitor", "count": 2},
                {"template_key": "gunner", "count": 1},
            ]
        return {
            "encounter_description": "Hostile contacts detected on auspex.",
            "enemies": enemies,
        }

    async def generate_encounter(
        self,
        map_key: str = "corridor",
        room_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a combat encounter via the LLM based on current narrative context.

        Parameters
        ----------
        map_key:
            Fallback hardcoded map key (used only when room_hint is None and
            procedural generation is bypassed).
        room_hint:
            Optional room generation hints from the LLM combat trigger.
            When provided, a procedural map is generated instead of using
            a hardcoded map.

        Returns a dict with:
          - encounter_description: str
          - enemy_roster: list of (template_key, x, y) tuples ready for CombatEngine
          - map_def: dict compatible with CombatEngine(map_def=...) -- present
            when a procedural map was generated
        """
        encounter_system = self._build_encounter_prompt()

        # Build a condensed context message from recent conversation
        context_messages: list[MessageParam] = []
        # Include last few exchanges for narrative context (up to 6 messages)
        recent = self._conversation_history[-6:]
        if recent:
            summary_parts: list[str] = []
            for msg in recent:
                content = msg.get("content", "")
                if isinstance(content, str):
                    # Truncate long assistant responses to just narrative
                    if msg["role"] == "assistant":
                        try:
                            parsed = _extract_json(content)
                            summary_parts.append(
                                f"[narrator]: {parsed.get('narrative_text', content[:200])}"
                            )
                        except (json.JSONDecodeError, ValueError):
                            summary_parts.append(f"[narrator]: {content[:200]}")
                    else:
                        summary_parts.append(f"[player]: {content}")
            context_messages.append({
                "role": "user",
                "content": (
                    "Here is the recent story context:\n\n"
                    + "\n".join(summary_parts)
                    + "\n\nNow generate a combat encounter appropriate to this context."
                ),
            })
        else:
            context_messages.append({
                "role": "user",
                "content": "The Tech-Priest is exploring the deep strata beneath the forge. Generate a combat encounter.",
            })

        encounter_data: dict[str, Any]
        try:
            message = await self._client.messages.create(
                model=MODEL,
                max_tokens=512,
                system=encounter_system,
                messages=context_messages,
            )
            raw_text: str = message.content[0].text  # type: ignore[union-attr]
            encounter_data = _extract_json(raw_text)

            # Validate the response structure
            if "enemies" not in encounter_data or not encounter_data["enemies"]:
                logger.warning("LLM encounter response missing enemies, using fallback")
                encounter_data = self._default_encounter()
            else:
                # Filter out invalid template keys
                valid_enemies: list[dict[str, Any]] = []
                for entry in encounter_data["enemies"]:
                    key = entry.get("template_key", "")
                    count = entry.get("count", 1)
                    if key in ENEMY_TEMPLATES and isinstance(count, int) and count > 0:
                        valid_enemies.append({"template_key": key, "count": min(count, 5)})
                if not valid_enemies:
                    logger.warning("No valid enemies in LLM response, using fallback")
                    encounter_data = self._default_encounter()
                else:
                    encounter_data["enemies"] = valid_enemies

        except Exception as exc:
            logger.warning("Encounter generation failed (%s), using fallback", exc)
            encounter_data = self._default_encounter()

        # Generate map -- procedural or hardcoded
        generated_map: GeneratedMap | None = None
        if room_hint is not None:
            generated_map = generate_map_from_hint(room_hint)
            map_def_dict = generated_map.to_map_def()
            grid = generated_map.grid
            px, py = generated_map.spawn.player_start
            occupied: set[tuple[int, int]] = {(px, py)}
            for pos in generated_map.spawn.party_starts:
                occupied.add(pos)
        else:
            # Try procedural generation with no hints (random map)
            generated_map = generate_map_from_hint(None)
            map_def_dict = generated_map.to_map_def()
            grid = generated_map.grid
            px, py = generated_map.spawn.player_start
            occupied = {(px, py)}
            for pos in generated_map.spawn.party_starts:
                occupied.add(pos)

        enemy_counts: list[tuple[str, int]] = [
            (e["template_key"], e["count"]) for e in encounter_data["enemies"]
        ]
        enemy_roster = auto_place_enemies(grid, enemy_counts, occupied)

        # Fallback if placement yielded nothing (tiny map edge case)
        if not enemy_roster:
            fallback_map = HARDCODED_MAPS.get(map_key, HARDCODED_MAPS["corridor"])
            enemy_roster = list(fallback_map["enemies"])

        result: dict[str, Any] = {
            "encounter_description": encounter_data.get(
                "encounter_description", "Hostile contacts detected."
            ),
            "enemy_roster": enemy_roster,
        }

        if map_def_dict is not None:
            result["map_def"] = map_def_dict

        return result

    def record_combat_result(self, result: CombatResult) -> None:
        """Persist a combat result into conversation history and game history.

        Injects a system-style message into the LLM conversation so the narrator
        knows what happened, and records a step in the structured history.
        """
        # Build a concise structured summary for the LLM
        if result.victory:
            outcome = "VICTORY"
        elif result.player_hp_remaining > 0:
            outcome = "RETREAT"
        else:
            outcome = "DEFEAT"

        enemy_details: list[str] = []
        for e in result.enemies:
            status = "destroyed" if e.defeated else "survived"
            enemy_details.append(f"{e.name} ({e.template_key}, {status})")
        enemies_str = ", ".join(enemy_details) if enemy_details else "unknown hostiles"

        system_msg = (
            f"[SYSTEM: Combat resolved — {outcome}. "
            f"Enemies encountered: {enemies_str}. "
            f"Hostiles neutralised: {result.enemies_defeated}/{result.enemies_total}. "
            f"Turns elapsed: {result.turn_count}. "
            f"Integrity: {result.player_hp_remaining}/{result.player_hp_max}. "
            f"Total damage absorbed: {result.total_player_damage_taken}.]"
        )

        # Inject into LLM conversation as a user message + assistant ack
        self._conversation_history.append({
            "role": "user",
            "content": system_msg,
        })
        ack = (
            f"Acknowledged. Combat outcome: {outcome}. "
            f"The Tech-Priest {'triumphed over' if result.victory else 'faced'} "
            f"{enemies_str}. Integrity at {result.player_hp_remaining}/{result.player_hp_max}."
        )
        self._conversation_history.append({
            "role": "assistant",
            "content": ack,
        })

        # Record in structured history (no entity IDs needed — enemies are ad-hoc)
        narrative_summary = (
            f"Combat {outcome}: fought {enemies_str}. "
            f"{result.enemies_defeated}/{result.enemies_total} hostiles neutralised "
            f"over {result.turn_count} turns. "
            f"Integrity: {result.player_hp_remaining}/{result.player_hp_max}."
        )
        self._history.add_step(
            player_input="[combat]",
            narrative_text=narrative_summary,
            entity_ids=[],
            info_update=None,
        )

        # Sync party member HP from combat results
        for pid, (hp, max_hp) in result.party_hp.items():
            self._party_hp[pid] = (hp, max_hp)

    def to_dict(self) -> dict[str, Any]:
        """Export full engine state for saving."""
        return {
            "player_name": self._player_name,
            "conversation_history": list(self._conversation_history),
            "turn_count": self._turn_count,
            "current_scene_art": self._current_scene_art,
            "info_panel": dict(self._info_panel),
            "error_count": self._error_count,
            "history": self._history.to_dict(),
            "integrity": self._integrity,
            "max_integrity": self._max_integrity,
            "party_member_ids": list(self._party_member_ids),
            "party_hp": {k: list(v) for k, v in self._party_hp.items()},
            "story_start_id": self._story_start_id,
            "story_suffix": self._story_suffix,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEngine:
        """Restore engine state from a saved dict."""
        engine = cls.__new__(cls)
        engine._client = anthropic.AsyncAnthropic()
        engine._player_name = data.get("player_name", "Magos Explorator")
        engine._conversation_history = data.get("conversation_history", [])
        engine._turn_count = data.get("turn_count", 0)
        engine._current_scene_art = data.get("current_scene_art")
        engine._info_panel = data.get("info_panel", {})
        engine._error_count = data.get("error_count", 0)
        engine._party_member_ids = data.get(
            "party_member_ids", list(cls.DEFAULT_PARTY_IDS)
        )
        engine._log_path = _log_dir() / f"convo_{int(time.time())}.jsonl"
        engine._scene_pane_width = DEFAULT_ART_WIDTH
        engine._scene_pane_height = DEFAULT_ART_HEIGHT
        engine._max_integrity = data.get("max_integrity", 20)
        engine._integrity = data.get("integrity", engine._max_integrity)
        engine._story_start_id = data.get("story_start_id")
        engine._story_suffix = data.get("story_suffix", _DEFAULT_STORY_SUFFIX)
        history_data = data.get("history")
        if history_data:
            engine._history = GameHistory.from_dict(history_data)
        else:
            # Legacy save without history — initialize fresh with seeds
            engine._history = GameHistory()
            engine._seed_starting_entities()
        # Restore party HP (fall back to template defaults for legacy saves)
        raw_party_hp = data.get("party_hp", {})
        if raw_party_hp:
            engine._party_hp = {k: (v[0], v[1]) for k, v in raw_party_hp.items()}
        else:
            engine._party_hp = engine._init_party_hp()
        return engine

    async def process_input(self, text: str) -> GameResponse:
        """Send player input to Claude and return a structured GameResponse."""
        self._conversation_history.append({
            "role": "user",
            "content": text,
        })

        raw_text: str = ""
        narrative_text: str
        scene_art: str | None = None
        info_update: dict[str, str] | None
        entities_data: list[dict[str, Any]] = []
        combat_trigger: bool = False
        room_hint: dict[str, Any] | None = None
        speaking_npc: str | None = None
        system_prompt = self._build_system_prompt()

        try:
            message = await self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=self._conversation_history,
            )

            raw_text = message.content[0].text  # type: ignore[union-attr]

            # Parse the structured JSON response (handles markdown fences)
            response_data: dict[str, Any] = _extract_json(raw_text)
            narrative_text = response_data.get("narrative_text", raw_text)
            scene_art = response_data.get("scene_art")
            info_update = response_data.get("info_update")
            entities_data = response_data.get("entities", [])
            combat_trigger = bool(response_data.get("combat_trigger", False))
            if combat_trigger:
                room_hint = response_data.get("room_hint")
            speaking_npc = response_data.get("speaking_npc") or None

            self._log_turn(system_prompt, list(self._conversation_history), raw_text)

        except json.JSONDecodeError:
            # LLM returned non-JSON -- use the raw text as narrative
            logger.warning("Claude returned non-JSON response, using raw text")
            self._log_turn(
                system_prompt, list(self._conversation_history), raw_text,
                error="JSONDecodeError",
            )
            narrative_text = raw_text
            info_update = None

        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            self._log_turn(
                system_prompt, list(self._conversation_history), "",
                error=str(exc),
            )
            # Remove the failed user message so history stays consistent
            self._conversation_history.pop()
            error_msg: str = NOOSPHERE_ERRORS[self._error_count % len(NOOSPHERE_ERRORS)]
            self._error_count += 1
            return GameResponse(narrative_text=error_msg)

        except Exception as exc:
            logger.error("Unexpected error in game engine: %s", exc)
            self._log_turn(
                system_prompt, list(self._conversation_history), "",
                error=str(exc),
            )
            self._conversation_history.pop()
            error_msg = NOOSPHERE_ERRORS[self._error_count % len(NOOSPHERE_ERRORS)]
            self._error_count += 1
            return GameResponse(narrative_text=error_msg)

        # Store assistant reply in conversation history for context
        self._conversation_history.append({
            "role": "assistant",
            "content": raw_text,
        })

        self._turn_count += 1

        # Process entity tracking from LLM response
        entity_ids = self._process_entities(entities_data)

        # Record step in history
        self._history.add_step(
            player_input=text,
            narrative_text=narrative_text,
            entity_ids=entity_ids,
            info_update=info_update,
        )

        # Track latest info/scene for save state
        if scene_art:
            self._current_scene_art = scene_art
        if info_update:
            self._info_panel.update(info_update)

        return GameResponse(
            narrative_text=narrative_text,
            scene_art=scene_art,
            info_update=info_update,
            combat_trigger=combat_trigger,
            room_hint=room_hint,
            speaking_npc=speaking_npc,
        )
