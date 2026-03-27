"""Game engine — processes player input and returns narrative responses."""

from dataclasses import dataclass

from angband_mechanicum.assets.placeholder_art import CANNED_RESPONSES


@dataclass
class GameResponse:
    narrative_text: str
    scene_art: str | None = None
    info_update: dict | None = None


class GameEngine:
    def __init__(self) -> None:
        self._response_index = 0

    async def process_input(self, text: str) -> GameResponse:
        response_text = CANNED_RESPONSES[self._response_index % len(CANNED_RESPONSES)]
        self._response_index += 1
        return GameResponse(narrative_text=response_text)
