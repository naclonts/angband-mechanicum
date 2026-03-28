"""Game engine -- processes player input and returns narrative responses via Claude API."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import anthropic
from anthropic.types import MessageParam

from angband_mechanicum.assets.placeholder_art import INTRO_NARRATIVE

logger: logging.Logger = logging.getLogger(__name__)

MODEL: str = "claude-sonnet-4-20250514"
MAX_TOKENS: int = 2048

SCENE_ART_INSTRUCTIONS: str = """\

## Scene Art
You MUST also provide ASCII/unicode art for the scene_art field that depicts the \
current environment or location. This art is displayed in the "ENVIRONMENT" pane of \
the game UI.

Rules for scene art:
- Use box-drawing characters (╔═╗║╚╝┌─┐│└┘├┤┬┴┼), blocks (█▓▒░), and symbols \
(⚙⛨◉▬╬) to create atmospheric scenes.
- Art MUST be no wider than 56 characters per line (to fit the scene pane).
- Art should be 12-20 lines tall.
- Depict the physical environment: rooms, corridors, machinery, doorways, ruins, etc.
- Match the scene to what is happening in the narrative — if the player enters a \
corridor, show a corridor; if they are in a forge, show forge equipment.
- Keep a dark, industrial, gothic sci-fi aesthetic.
- Do NOT use Rich markup in scene_art — plain text/unicode only.
- Always provide scene_art when the location or environment changes. If the player \
stays in the same place and nothing visually changes, set scene_art to null.
"""

SYSTEM_PROMPT: str = """\
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
  "info_update": null or { "key": "value" } dict to update status fields
}

The scene_art field should contain ASCII/unicode art depicting the current environment. \
Provide it when the scene or location changes; set to null if the environment has not \
visually changed since the last response.

The info_update field is optional (null if nothing changed). Use it when something \
meaningful changes, for example:
- {"Location": "Cargo Lift Shaft"} when the player moves
- {"Threat Level": "ELEVATED"} when danger increases
- {"Objective": "Investigate seismic anomaly"} for quest updates
""" + SCENE_ART_INSTRUCTIONS + """
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

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic()
        self._conversation_history: list[MessageParam] = []
        self._error_count: int = 0
        self._turn_count: int = 0
        self._current_scene_art: str | None = None
        self._info_panel: dict[str, str] = {}

    @property
    def turn_count(self) -> int:
        return self._turn_count

    def to_dict(self) -> dict[str, Any]:
        """Export full engine state for saving."""
        return {
            "conversation_history": list(self._conversation_history),
            "turn_count": self._turn_count,
            "current_scene_art": self._current_scene_art,
            "info_panel": dict(self._info_panel),
            "error_count": self._error_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEngine:
        """Restore engine state from a saved dict."""
        engine = cls()
        engine._conversation_history = data.get("conversation_history", [])
        engine._turn_count = data.get("turn_count", 0)
        engine._current_scene_art = data.get("current_scene_art")
        engine._info_panel = data.get("info_panel", {})
        engine._error_count = data.get("error_count", 0)
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

        try:
            message = await self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=self._conversation_history,
            )

            raw_text = message.content[0].text  # type: ignore[union-attr]

            # Parse the structured JSON response
            response_data: dict[str, Any] = json.loads(raw_text)
            narrative_text = response_data.get("narrative_text", raw_text)
            scene_art = response_data.get("scene_art")
            info_update = response_data.get("info_update")

        except json.JSONDecodeError:
            # LLM returned non-JSON -- use the raw text as narrative
            logger.warning("Claude returned non-JSON response, using raw text")
            narrative_text = raw_text
            info_update = None

        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            # Remove the failed user message so history stays consistent
            self._conversation_history.pop()
            error_msg: str = NOOSPHERE_ERRORS[self._error_count % len(NOOSPHERE_ERRORS)]
            self._error_count += 1
            return GameResponse(narrative_text=error_msg)

        except Exception as exc:
            logger.error("Unexpected error in game engine: %s", exc)
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
