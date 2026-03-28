"""Game engine -- processes player input and returns narrative responses via Claude API."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import MessageParam

from angband_mechanicum.assets.placeholder_art import INTRO_NARRATIVE
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
The player is a **Tech-Priest Magos Explorator** of the Adeptus Mechanicus. They are \
stationed on the forge world **Metallica Secundus**, in the great manufactorum-city \
**Angband Mechanicum**. A priority signal has been received — seismic anomalies and \
unidentified energy signatures detected in the deep strata beneath the forge. The \
Fabricator-Locum has assigned the player to investigate.

The player has three acolytes assigned to their expedition:
- **Skitarius Alpha-7** — a battle-scarred ranger with a galvanic rifle
- **Enginseer Volta** — young, eager, still more flesh than machine, carries a power axe
- **Datasmith Kael** — silent, face entirely replaced by a vox-grille and sensor array

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
You MUST respond with a valid JSON object. No text outside the JSON. The schema:

{
  "narrative_text": "The main narrative response to the player (string, required)",
  "scene_art": "ASCII/unicode art for the environment pane (string or null)",
  "info_update": null or { "key": "value" } dict to update status fields,
  "entities": [array of entity references — see Entity Tracking below]
}

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

_STORY_SUFFIX: str = """
## Story So Far
The player has just received this introduction:

""" + INTRO_NARRATIVE.replace("[bold]", "").replace("[/bold]", "").replace("[dim]", "").replace("[/dim]", "")


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


class GameEngine:
    """Processes player input via the Anthropic Claude API and returns narrative responses."""

    # Default party members — entity IDs matching the seeded entities
    DEFAULT_PARTY_IDS: list[str] = [
        "skitarius-alpha-7",
        "enginseer-volta",
        "datasmith-kael",
    ]

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic()
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

    def set_scene_pane_size(self, width: int, height: int) -> None:
        """Update the scene pane dimensions used in LLM prompts.

        Called by the UI whenever the environment pane is mounted or resized.
        """
        self._scene_pane_width = max(width, 20)
        self._scene_pane_height = max(height, 6)

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
        reg("Datasmith Kael", EntityType.CHARACTER,
            "Silent, face entirely replaced by a vox-grille and sensor array")
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
        prompt = _SYSTEM_PROMPT_BASE + _build_scene_art_instructions(
            self._scene_pane_width, self._scene_pane_height
        ) + _STORY_SUFFIX
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

    def to_dict(self) -> dict[str, Any]:
        """Export full engine state for saving."""
        return {
            "conversation_history": list(self._conversation_history),
            "turn_count": self._turn_count,
            "current_scene_art": self._current_scene_art,
            "info_panel": dict(self._info_panel),
            "error_count": self._error_count,
            "history": self._history.to_dict(),
            "party_member_ids": list(self._party_member_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEngine:
        """Restore engine state from a saved dict."""
        engine = cls.__new__(cls)
        engine._client = anthropic.AsyncAnthropic()
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
        history_data = data.get("history")
        if history_data:
            engine._history = GameHistory.from_dict(history_data)
        else:
            # Legacy save without history — initialize fresh with seeds
            engine._history = GameHistory()
            engine._seed_starting_entities()
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
        )
