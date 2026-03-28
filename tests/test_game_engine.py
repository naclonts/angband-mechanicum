"""Tests for the game engine."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from angband_mechanicum.engine.game_engine import GameEngine, GameResponse, NOOSPHERE_ERRORS
from tests.conftest import _make_api_response


# ---------------------------------------------------------------------------
# GameResponse dataclass
# ---------------------------------------------------------------------------

class TestGameResponse:
    def test_defaults(self) -> None:
        r = GameResponse(narrative_text="hello")
        assert r.narrative_text == "hello"
        assert r.scene_art is None
        assert r.info_update is None

    def test_with_all_fields(self) -> None:
        r = GameResponse(
            narrative_text="text",
            scene_art="art",
            info_update={"LOCATION": "somewhere"},
        )
        assert r.scene_art == "art"
        assert r.info_update == {"LOCATION": "somewhere"}


# ---------------------------------------------------------------------------
# Serialization round-trip: to_dict / from_dict
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_round_trip(self, sample_state: dict[str, Any]) -> None:
        engine = GameEngine.from_dict(sample_state)
        exported = engine.to_dict()
        assert exported["turn_count"] == 1
        assert exported["info_panel"] == {"LOCATION": "Forge-Cathedral Alpha"}
        assert len(exported["conversation_history"]) == 2
        assert exported["error_count"] == 0
        assert exported["current_scene_art"] is None

    def test_from_dict_missing_keys_uses_defaults(self) -> None:
        engine = GameEngine.from_dict({})
        assert engine.turn_count == 0
        assert engine.to_dict()["conversation_history"] == []
        assert engine.to_dict()["info_panel"] == {}


# ---------------------------------------------------------------------------
# process_input — success path
# ---------------------------------------------------------------------------

class TestProcessInput:
    @pytest.mark.asyncio
    async def test_success_with_info_update(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "narrative_text": "You descend into the forge.",
            "info_update": {"LOCATION": "Lower Forge"},
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.process_input("go down")

        assert result.narrative_text == "You descend into the forge."
        assert result.info_update == {"LOCATION": "Lower Forge"}
        assert engine.turn_count == 1
        assert engine._info_panel == {"LOCATION": "Lower Forge"}
        # Conversation history should have user + assistant
        assert len(engine._conversation_history) == 2
        assert engine._conversation_history[0]["role"] == "user"
        assert engine._conversation_history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_success_with_scene_art(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        scene = "╔══════╗\n║ HALL ║\n╚══════╝"
        response_json = json.dumps({
            "narrative_text": "You enter the great hall.",
            "scene_art": scene,
            "info_update": {"LOCATION": "Great Hall"},
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.process_input("enter hall")

        assert result.narrative_text == "You enter the great hall."
        assert result.scene_art == scene
        assert result.info_update == {"LOCATION": "Great Hall"}
        assert engine._current_scene_art == scene
        assert engine.turn_count == 1

    @pytest.mark.asyncio
    async def test_scene_art_null_preserves_previous(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        # First response sets scene art
        scene = "╔══════╗\n║ ROOM ║\n╚══════╝"
        engine._client.messages.create.return_value = _make_api_response(
            json.dumps({"narrative_text": "A room.", "scene_art": scene, "info_update": None})
        )
        await engine.process_input("look")
        assert engine._current_scene_art == scene

        # Second response has null scene_art -- previous art preserved in engine state
        engine._client.messages.create.return_value = _make_api_response(
            json.dumps({"narrative_text": "Nothing changes.", "scene_art": None, "info_update": None})
        )
        result = await engine.process_input("wait")
        assert result.scene_art is None
        assert engine._current_scene_art == scene  # preserved

    @pytest.mark.asyncio
    async def test_success_no_info_update(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "narrative_text": "Nothing happens.",
            "info_update": None,
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.process_input("wait")

        assert result.narrative_text == "Nothing happens."
        assert result.info_update is None
        assert engine.turn_count == 1

    # -----------------------------------------------------------------------
    # Edge case: non-JSON response from LLM
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_non_json_falls_back_to_raw_text(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        raw = "The machine spirit refuses to parse."
        engine._client.messages.create.return_value = _make_api_response(raw)

        result = await engine.process_input("break things")

        assert result.narrative_text == raw
        assert result.info_update is None
        # Turn still counts (JSON parse failure is not an API error)
        assert engine.turn_count == 1

    # -----------------------------------------------------------------------
    # Edge case: API error
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_api_error_returns_noosphere_error(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        engine._client.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock()
        )

        result = await engine.process_input("try something")

        assert result.narrative_text == NOOSPHERE_ERRORS[0]
        # Failed message should be removed from history
        assert len(engine._conversation_history) == 0
        # Turn should NOT increment on error
        assert engine.turn_count == 0
        assert engine._error_count == 1

    @pytest.mark.asyncio
    async def test_error_cycles_through_messages(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        engine._client.messages.create.side_effect = RuntimeError("boom")

        r1 = await engine.process_input("a")
        r2 = await engine.process_input("b")
        r3 = await engine.process_input("c")
        r4 = await engine.process_input("d")

        assert r1.narrative_text == NOOSPHERE_ERRORS[0]
        assert r2.narrative_text == NOOSPHERE_ERRORS[1]
        assert r3.narrative_text == NOOSPHERE_ERRORS[2]
        # Wraps around
        assert r4.narrative_text == NOOSPHERE_ERRORS[0]
