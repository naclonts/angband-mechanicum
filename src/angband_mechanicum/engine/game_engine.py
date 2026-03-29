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
    ENVIRONMENTS,
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


def _assistant_history_text(content: str) -> str:
    """Return safe assistant history text for prompts and UI surfaces.

    Raw JSON responses should stay in the JSONL debug log, but conversation
    history that can later be restored or surfaced in the UI should only retain
    the narrative text players are meant to see.
    """
    try:
        response_data = _extract_json(content)
    except json.JSONDecodeError:
        return content
    narrative_text = response_data.get("narrative_text")
    return narrative_text if isinstance(narrative_text, str) and narrative_text else content


def _normalize_conversation_history(messages: list[MessageParam]) -> list[MessageParam]:
    """Normalize restored conversation history to avoid leaking raw JSON."""
    normalized: list[MessageParam] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role == "assistant" and isinstance(content, str):
            normalized.append({"role": role, "content": _assistant_history_text(content)})
            continue
        normalized.append(dict(message))
    return normalized

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
- When the player is directly speaking to or examining a specific character, make \
the character the visual subject of scene_art. Use a close-up, conversational \
tableau, or character-centric composition rather than only the surrounding room.
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

The player is not assumed to have a standing humanoid party with them unless the \
current scene explicitly establishes one.

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


@dataclass
class DeathNarrative:
    """Structured memorial text generated when the player dies."""

    summary: str
    cause_of_death: str


@dataclass(frozen=True)
class TravelDestination:
    """Resolved destination for a text-view travel request."""

    request_text: str
    environment: str
    display_name: str
    matched_terms: tuple[str, ...] = ()


def _tokenize_destination_text(text: str) -> set[str]:
    """Tokenize a travel request into comparable lowercase words."""
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token}


def _environment_display_name(environment_name: str, description: str) -> str:
    """Return a compact label for a destination environment."""
    prefix = description.split(" — ", 1)[0].strip()
    if prefix:
        return prefix
    return environment_name.replace("_", " ").title()


def _score_destination_match(
    query: str,
    query_tokens: set[str],
    environment_name: str,
    environment_description: str,
    environment_aliases: tuple[str, ...] = (),
) -> tuple[int, tuple[str, ...]]:
    """Score how well a destination request matches an environment."""
    env_tokens = _tokenize_destination_text(environment_name)
    desc_tokens = _tokenize_destination_text(environment_description)
    matched_terms: set[str] = set()
    score = 0

    if environment_name in query:
        score += 5
        matched_terms.add(environment_name)
    name_phrase = environment_name.replace("_", " ")
    if name_phrase != environment_name and name_phrase in query:
        score += 4
        matched_terms.add(name_phrase)

    for alias in environment_aliases:
        alias = alias.strip().lower()
        if not alias or alias in {environment_name, name_phrase}:
            continue
        alias_tokens = _tokenize_destination_text(alias)
        if alias in query:
            score += 3
            matched_terms.add(alias)
        alias_overlap = query_tokens & alias_tokens
        score += len(alias_overlap) * 2
        matched_terms.update(alias_overlap)

    env_overlap = query_tokens & env_tokens
    desc_overlap = query_tokens & desc_tokens
    score += len(env_overlap) * 4
    score += len(desc_overlap) * 2
    matched_terms.update(env_overlap)
    matched_terms.update(desc_overlap)

    if query.startswith(environment_name):
        score += 2

    return score, tuple(sorted(matched_terms))


class GameEngine:
    """Processes player input via the Anthropic Claude API and returns narrative responses."""

    # Default companion followers — the opening expedition only includes the servo-skull.
    DEFAULT_PARTY_IDS: list[str] = [
        "servo-skull",
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
        self._current_environment_id: str = "forge"
        self._current_location_profile_id: str | None = None
        self._current_location_label: str | None = None
        self._active_interaction_context: dict[str, Any] | None = None

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
            self._current_location_label = story.info_overrides.get("LOCATION")

    def set_environment_context(
        self,
        *,
        environment_id: str,
        profile_id: str | None = None,
        location_name: str | None = None,
    ) -> None:
        """Persist the canonical world environment shared by text and map views."""
        self._current_environment_id = environment_id
        self._current_location_profile_id = profile_id
        self._current_location_label = location_name
        if location_name:
            self._info_panel["LOCATION"] = location_name

    def resolve_travel_destination(self, request_text: str) -> TravelDestination:
        """Resolve a natural-language travel request to the closest environment."""
        cleaned_request = request_text.strip()
        query = cleaned_request.lower()
        query_tokens = _tokenize_destination_text(query)

        best_environment = "forge"
        best_score = -1
        best_terms: tuple[str, ...] = ()
        for environment_name, environment in ENVIRONMENTS.items():
            score, matched_terms = _score_destination_match(
                query=query,
                query_tokens=query_tokens,
                environment_name=environment_name,
                environment_description=environment.description,
                environment_aliases=environment.aliases,
            )
            if score > best_score:
                best_environment = environment_name
                best_score = score
                best_terms = matched_terms

        resolved_environment = ENVIRONMENTS.get(best_environment, ENVIRONMENTS["forge"])
        return TravelDestination(
            request_text=cleaned_request,
            environment=resolved_environment.name,
            display_name=_environment_display_name(
                resolved_environment.name, resolved_environment.description
            ),
            matched_terms=best_terms,
        )

    @property
    def party_hp(self) -> dict[str, tuple[int, int]]:
        """Per-party-member HP: {entity_id: (current_hp, max_hp)}."""
        return dict(self._party_hp)

    def get_status_data(self) -> dict[str, Any]:
        """Return structured data for the STATUS panel.

        Returns a dict with:
          - info: dict of key-value info fields (DESIGNATION, LOCATION, etc.)
          - integrity: (current, max) player HP
          - companions: list of {id, name, hp, max_hp, alive} dicts
        """
        companions: list[dict[str, Any]] = []
        for pid in self._party_member_ids:
            if pid in PARTY_TEMPLATES:
                tpl = PARTY_TEMPLATES[pid]
                hp, max_hp = self._party_hp.get(
                    pid, (tpl["stats"]["hp"], tpl["stats"]["max_hp"])
                )
                companions.append({
                    "id": pid,
                    "name": tpl["name"],
                    "hp": hp,
                    "max_hp": max_hp,
                    "alive": hp > 0,
                })
        return {
            "info": dict(self._info_panel),
            "integrity": (self._integrity, self._max_integrity),
            "companions": companions,
            "party": list(companions),
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
        # Places
        reg("Metallica Secundus", EntityType.PLACE,
            "Forge world where the game is set")
        reg("Angband Mechanicum", EntityType.PLACE,
            "The great manufactorum-city on Metallica Secundus")
        # Items
        reg("Servo-skull", EntityType.ITEM,
            "A hovering skull drone that accompanies the player's expedition")

    def clear_active_interaction_context(self) -> None:
        """Forget any focused dungeon conversation/examine target."""
        self._active_interaction_context = None

    def set_active_interaction_context(self, context: dict[str, Any] | None) -> None:
        """Track the currently addressed dungeon target for prompt grounding."""
        if not context:
            self._active_interaction_context = None
            return
        allowed_keys = {
            "interaction_kind",
            "interaction_target",
            "interaction_entity_id",
            "interaction_entity_name",
            "interaction_entity_type",
            "interaction_entity_disposition",
            "interaction_entity_description",
            "interaction_entity_history_id",
            "conversation_target",
            "target_entity_id",
            "target_entity_name",
            "target_entity_type",
            "target_disposition",
            "target_description",
            "target_kind",
            "target_label",
            "terrain",
            "target_position",
            "player_position",
            "map_return_pos",
            "look_mode",
            "look_summary",
            "speaking_npc_id",
        }
        sanitized = {
            key: value for key, value in context.items()
            if key in allowed_keys and value is not None
        }
        self._active_interaction_context = sanitized or None

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
        active_interaction = self._build_active_interaction_prompt_context()
        if active_interaction:
            prompt += "\n\n" + active_interaction
        companion_context = self._build_companion_status_context()
        if companion_context:
            prompt += "\n\n" + companion_context
        environment_context = self._build_environment_prompt_context()
        if environment_context:
            prompt += "\n\n" + environment_context
        return prompt

    def _build_environment_prompt_context(self) -> str:
        """Describe the canonical environment shared by travel and dungeon play."""
        lines = [
            "## Canonical Environment State",
            f"- Environment id: {self._current_environment_id}",
        ]
        if self._current_location_profile_id:
            lines.append(f"- Location profile id: {self._current_location_profile_id}")
        if self._current_location_label:
            lines.append(f"- Current location label: {self._current_location_label}")
        return "\n".join(lines)

    def _build_active_interaction_prompt_context(self) -> str:
        """Describe the currently addressed dungeon target for the next replies."""
        if not self._active_interaction_context:
            return ""

        context = self._active_interaction_context
        target_name = (
            context.get("interaction_entity_name")
            or context.get("target_entity_name")
            or context.get("target_label")
            or "Unknown target"
        )
        location = self._info_panel.get("LOCATION", "Unknown location")
        lines = [
            "## Current Interaction Focus",
            "The player is addressing or examining a specific dungeon target right now.",
            "Keep responses anchored to this target and the current dungeon environment.",
            "Do not substitute a different known character, companion, or prior scene.",
            f"- Current location: {location}",
            f"- Focus target: {target_name}",
        ]

        speaking_npc_id = context.get("speaking_npc_id")
        character_target = (
            context.get("interaction_entity_type") == "character"
            or context.get("target_kind") == "character"
            or context.get("interaction_kind") == "conversation"
            or context.get("conversation_target") is not None
            or isinstance(speaking_npc_id, str)
        )
        if character_target:
            lines.append(
                "- Scene focus: character-centric; show the addressed speaker or examine target, not just the surrounding room."
            )
            if isinstance(speaking_npc_id, str):
                lines.append(f"- Speaking NPC id: {speaking_npc_id}")

        for source_key, label in (
            ("interaction_kind", "Interaction kind"),
            ("interaction_entity_type", "Target type"),
            ("interaction_entity_disposition", "Disposition"),
            ("interaction_entity_description", "Target description"),
            ("target_kind", "Look target kind"),
            ("terrain", "Terrain"),
        ):
            value = context.get(source_key)
            if value is not None:
                lines.append(f"- {label}: {value}")

        target_position = context.get("target_position")
        if isinstance(target_position, list) and len(target_position) == 2:
            lines.append(f"- Target position: {target_position[0]},{target_position[1]}")

        history_id = context.get("conversation_target") or context.get("interaction_target")
        if isinstance(history_id, str):
            entity_context = self._history.get_entity_context(history_id)
            if entity_context:
                lines.extend(["", entity_context])

        return "\n".join(lines)

    def _build_companion_status_context(self) -> str:
        """Build a compact prompt block describing companion survival state."""
        lines: list[str] = ["## Companion Status"]
        companions_added = False
        for pid in self._party_member_ids:
            tpl = PARTY_TEMPLATES.get(pid)
            if tpl is None:
                continue
            hp, max_hp = self._party_hp.get(
                pid, (tpl["stats"]["hp"], tpl["stats"]["max_hp"])
            )
            state = "DEAD" if hp <= 0 else "ALIVE"
            lines.append(
                f"- {pid} ({tpl['name']}): {state}, HP {hp}/{max_hp}"
            )
            companions_added = True

        if not companions_added:
            return ""

        lines.append("")
        lines.append(
            "Dead companions must not speak, act, or be narrated as active unless "
            "explicitly revived."
        )
        return "\n".join(lines)

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

    def _fallback_death_narrative(self, death_context: dict[str, Any]) -> DeathNarrative:
        """Build a deterministic memorial when the LLM cannot answer."""
        player_name = str(death_context.get("player_name", self._player_name))
        location = str(death_context.get("location", "the depths"))
        enemy_summary = str(death_context.get("enemy_summary", "unknown hostiles"))
        turns_survived = int(death_context.get("turns_survived", self._turn_count))
        enemies_slain = int(death_context.get("enemies_slain", 0))
        deepest_level = int(death_context.get("deepest_level_reached", 0))
        companion_summary = str(death_context.get("companion_summary", "")).strip()
        cause_of_death = str(
            death_context.get("cause_of_death", f"fell against {enemy_summary}")
        )
        lines = [
            f"{player_name} descended into {location} and did not return.",
            f"After {turns_survived} turns, {enemies_slain} enemies lay broken, and the faith of the Omnissiah held until the end.",
            f"The final battle came on depth {deepest_level} against {enemy_summary}.",
        ]
        if companion_summary:
            lines.append(f"Companions at their side: {companion_summary}.")
        lines.append("Their last rites are now etched into the Hall of the Dead.")
        return DeathNarrative(summary=" ".join(lines), cause_of_death=cause_of_death)

    async def examine_dungeon_target(self, target_context: dict[str, Any]) -> GameResponse:
        """Ask the LLM to narrate a close examination of a dungeon target."""
        prompt_lines: list[str] = [
            "Examine the following dungeon target in the voice of the narrative engine.",
            "Return valid JSON with narrative_text, scene_art, info_update, entities, combat_trigger, room_hint, and speaking_npc.",
            "combat_trigger must be false.",
            "scene_art should depict the target or surrounding environment.",
            "",
            "Target context:",
        ]
        for key in sorted(target_context):
            value = target_context[key]
            if isinstance(value, (dict, list)):
                value_text = json.dumps(value, ensure_ascii=False)
            else:
                value_text = str(value)
            prompt_lines.append(f"- {key}: {value_text}")

        prompt_lines.extend(
            [
                "",
                "Describe what the player learns or notices by looking closely.",
            ]
        )
        return await self._generate_dungeon_target_response(prompt_lines, max_tokens=768)

    async def describe_ambient_dungeon_target(
        self,
        target_context: dict[str, Any],
    ) -> GameResponse:
        """Ask the LLM to narrate an ambient line-of-sight discovery."""
        prompt_lines: list[str] = [
            "Describe a noteworthy dungeon discovery that has entered the player's line of sight.",
            "This is for a compact ambient inspect panel, not a full examine sequence.",
            "Return valid JSON with narrative_text, scene_art, info_update, entities, combat_trigger, room_hint, and speaking_npc.",
            "combat_trigger must be false.",
            "Keep narrative_text concise: 1-2 short sentences.",
            "scene_art should be a compact vignette suitable for a small side panel.",
            "Do not introduce new combat, and do not treat this as a conversation.",
            "",
            "Target context:",
        ]
        for key in sorted(target_context):
            value = target_context[key]
            if isinstance(value, (dict, list)):
                value_text = json.dumps(value, ensure_ascii=False)
            else:
                value_text = str(value)
            prompt_lines.append(f"- {key}: {value_text}")

        prompt_lines.extend(
            [
                "",
                "Render a brief atmospheric discovery that rewards noticing the target.",
            ]
        )
        return await self._generate_dungeon_target_response(prompt_lines, max_tokens=512)

    async def _generate_dungeon_target_response(
        self,
        prompt_lines: list[str],
        *,
        max_tokens: int,
    ) -> GameResponse:
        """Run a target-focused LLM prompt without mutating turn state."""
        system_prompt = self._build_system_prompt()
        raw_text: str = ""
        try:
            message = await self._client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": "\n".join(prompt_lines),
                    },
                ],
            )
            raw_text = message.content[0].text  # type: ignore[union-attr]
            response_data = _extract_json(raw_text)
            narrative_text = str(response_data.get("narrative_text", raw_text)).strip()
            scene_art = response_data.get("scene_art")
            info_update = response_data.get("info_update")
            if not isinstance(info_update, dict):
                info_update = None
            combat_trigger = bool(response_data.get("combat_trigger", False))
            room_hint = response_data.get("room_hint") if combat_trigger else None
            speaking_npc = response_data.get("speaking_npc") or None
            return GameResponse(
                narrative_text=narrative_text,
                scene_art=scene_art if isinstance(scene_art, str) else None,
                info_update=info_update,
                combat_trigger=combat_trigger,
                room_hint=room_hint if isinstance(room_hint, dict) else None,
                speaking_npc=speaking_npc if isinstance(speaking_npc, str) else None,
            )
        except json.JSONDecodeError:
            logger.warning("Dungeon target narration returned non-JSON, using raw text")
            return GameResponse(narrative_text=raw_text.strip())
        except anthropic.APIError as exc:
            logger.warning("Dungeon target narration failed (%s)", exc)
            return GameResponse(narrative_text="")
        except Exception as exc:
            logger.warning("Unexpected dungeon target narration error: %s", exc)
            return GameResponse(narrative_text="")

    async def generate_death_narrative(
        self,
        death_context: dict[str, Any],
    ) -> DeathNarrative:
        """Ask the LLM to chronicle the death of the current Tech-Priest."""
        prompt_lines: list[str] = [
            "Write an epic memorial chronicle for the fallen Tech-Priest of Angband Mechanicum.",
            "Return valid JSON with keys summary and cause_of_death.",
            "summary should be 3-6 sentences: gothic, reverent, and specific to the final stand.",
            "cause_of_death should be a short phrase suitable for a hall record.",
            "",
            "Death context:",
        ]
        for key in sorted(death_context):
            value = death_context[key]
            if isinstance(value, (dict, list)):
                value_text = json.dumps(value, ensure_ascii=False)
            else:
                value_text = str(value)
            prompt_lines.append(f"- {key}: {value_text}")

        system_prompt = self._build_system_prompt()
        try:
            message = await self._client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": "\n".join(prompt_lines),
                    },
                ],
            )
            raw_text = message.content[0].text  # type: ignore[union-attr]
            response_data = _extract_json(raw_text)
            summary = str(response_data.get("summary") or raw_text).strip()
            cause = str(
                response_data.get("cause_of_death")
                or death_context.get("cause_of_death")
                or "Unknown"
            ).strip()
            if not summary:
                return self._fallback_death_narrative(death_context)
            return DeathNarrative(summary=summary, cause_of_death=cause or "Unknown")
        except Exception as exc:
            logger.warning("Death narrative generation failed (%s), using fallback", exc)
            return self._fallback_death_narrative(death_context)

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
            "current_environment_id": self._current_environment_id,
            "current_location_profile_id": self._current_location_profile_id,
            "current_location_label": self._current_location_label,
            "active_interaction_context": (
                dict(self._active_interaction_context)
                if self._active_interaction_context is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEngine:
        """Restore engine state from a saved dict."""
        engine = cls.__new__(cls)
        engine._client = anthropic.AsyncAnthropic()
        engine._player_name = data.get("player_name", "Magos Explorator")
        engine._conversation_history = _normalize_conversation_history(
            data.get("conversation_history", [])
        )
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
        engine._current_environment_id = data.get("current_environment_id", "forge")
        engine._current_location_profile_id = data.get("current_location_profile_id")
        engine._current_location_label = data.get("current_location_label")
        interaction_context = data.get("active_interaction_context")
        engine._active_interaction_context = (
            dict(interaction_context) if isinstance(interaction_context, dict) else None
        )
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
            "content": _assistant_history_text(raw_text),
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
