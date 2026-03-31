"""Tests for the game engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from angband_mechanicum.engine.history import EntityType
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
        assert exported["conversation_history"][1]["content"] == "You see a forge."
        assert exported["error_count"] == 0
        assert exported["current_scene_art"] is None

    def test_from_dict_missing_keys_uses_defaults(self) -> None:
        engine = GameEngine.from_dict({})
        assert engine.turn_count == 0
        assert engine.to_dict()["conversation_history"] == []
        assert engine.to_dict()["info_panel"] == {}


class TestStatusData:
    def test_companions_are_exposed_in_status_data(self) -> None:
        engine = GameEngine()
        status = engine.get_status_data()
        assert "companions" in status
        assert status["companions"] == status["party"]
        assert [member["name"] for member in status["companions"]] == ["Servo-skull"]
        assert all("alive" in member for member in status["companions"])

    def test_dead_companion_is_marked_dead(self) -> None:
        engine = GameEngine()
        engine._party_hp["servo-skull"] = (0, 6)
        status = engine.get_status_data()
        servo_skull = next(member for member in status["companions"] if member["id"] == "servo-skull")
        assert servo_skull["alive"] is False
        assert servo_skull["hp"] == 0


class TestDebugSnapshot:
    def test_build_debug_snapshot_includes_history_and_jsonl_entries(
        self, tmp_path: Path
    ) -> None:
        engine = GameEngine()
        entity = engine.history.register_entity(
            "Cogitator Shrine",
            EntityType.PLACE,
            "A shrine of sputtering logic engines.",
        )
        engine.history.add_step(
            "inspect shrine",
            "The shrine vents old incense.",
            [entity.id],
            {"LOCATION": "Relay Vault"},
        )
        engine._turn_count = 1
        engine._log_path = tmp_path / "debug.jsonl"
        engine._log_path.write_text(
            "\n".join(
                [
                    json.dumps({"turn": 1, "raw_response": "{\"ok\": true}"}),
                    "not-json",
                ]
            ),
            encoding="utf-8",
        )

        snapshot = engine.build_debug_snapshot()

        assert snapshot["turn_count"] == 1
        assert snapshot["history"]["steps"][0]["player_input"] == "inspect shrine"
        assert snapshot["history"]["steps"][0]["entity_ids"] == [entity.id]
        assert snapshot["jsonl_log_entries"][0]["turn"] == 1
        assert snapshot["jsonl_log_entries"][1]["parse_error"] == "JSONDecodeError"
        assert snapshot["jsonl_log_path"] == str(engine._log_path)


class TestTravelDestinationResolution:
    @pytest.mark.parametrize(
        ("request_text", "expected_environment", "expected_label"),
        [
            ("Take me to the sewer drains beneath the underhive.", "sewer", "Sub-hive drainage"),
            ("Lead me to the cathedral reliquary and shrine.", "reliquary", "Sacred reliquary"),
            ("Lead me into the cathedral nave and pillar hall.", "cathedral", "Imperial cathedral"),
            ("Take me through the marsh and blackwater swamp.", "swamp", "Swamp lowlands"),
            ("Lead me to the machine-haunted forest glades.", "forest", "Machine-haunted forest"),
            ("Take me up the mountain pass and cliff trail.", "mountains", "Mountain approaches"),
        ],
    )
    def test_resolve_travel_destination_matches_supported_environment(
        self,
        request_text: str,
        expected_environment: str,
        expected_label: str,
    ) -> None:
        engine = GameEngine()

        destination = engine.resolve_travel_destination(request_text)

        assert destination.request_text == request_text
        assert destination.environment == expected_environment
        assert destination.display_name == expected_label
        assert destination.matched_terms


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
        assert engine._conversation_history[1]["content"] == "You descend into the forge."

    @pytest.mark.asyncio
    async def test_success_stores_narrative_text_in_assistant_history(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "narrative_text": "The machine spirit answers in static.",
            "scene_art": "╔═╗",
            "info_update": {"LOCATION": "Relay Vault"},
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        await engine.process_input("listen")

        assert engine._conversation_history[1]["role"] == "assistant"
        assert engine._conversation_history[1]["content"] == "The machine spirit answers in static."

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

    @pytest.mark.asyncio
    async def test_system_prompt_includes_companion_status(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        engine._party_hp["servo-skull"] = (0, 6)
        response_json = json.dumps({
            "narrative_text": "The machine spirit hums.",
            "info_update": None,
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        await engine.process_input("look around")

        system_prompt = engine._client.messages.create.call_args.kwargs["system"]
        assert "## Companion Status" in system_prompt
        assert "servo-skull (Servo-skull): DEAD, HP 0/6" in system_prompt
        assert "Dead companions must not speak" in system_prompt
        assert "Enginseer Volta" not in system_prompt

    @pytest.mark.asyncio
    async def test_process_input_includes_active_interaction_context(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        engine.set_active_interaction_context(
            {
                "interaction_kind": "conversation",
                "interaction_entity_name": "Dormant Scribe",
                "interaction_entity_type": "character",
                "interaction_entity_description": "A dust-covered scribe-servitor rousing from standby.",
                "interaction_entity_disposition": "friendly",
                "terrain": "forge",
                "target_position": [12, 4],
                "speaking_npc_id": "dormant-scribe",
            }
        )
        response_json = json.dumps({
            "narrative_text": "The scribe emits a cautious vox-click.",
            "info_update": None,
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        await engine.process_input("Hello, what are you doing?")

        system_prompt = engine._client.messages.create.call_args.kwargs["system"]
        assert "## Current Interaction Focus" in system_prompt
        assert "Dormant Scribe" in system_prompt
        assert "A dust-covered scribe-servitor rousing from standby." in system_prompt
        assert "Do not substitute a different known character" in system_prompt
        assert "Scene focus: character-centric" in system_prompt
        assert "Speaking NPC id: dormant-scribe" in system_prompt

    @pytest.mark.asyncio
    async def test_process_input_with_object_focus_keeps_scene_environmental(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        engine.set_active_interaction_context(
            {
                "interaction_kind": "examine",
                "interaction_entity_name": "Cogitator Terminal",
                "interaction_entity_type": "object",
                "interaction_entity_description": "A humming machine shrine of data.",
                "terrain": "forge",
            }
        )
        response_json = json.dumps({
            "narrative_text": "The terminal flickers with old data.",
            "info_update": None,
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        await engine.process_input("inspect terminal")

        system_prompt = engine._client.messages.create.call_args.kwargs["system"]
        assert "Scene focus: character-centric" not in system_prompt

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


class TestDeathNarrative:
    @pytest.mark.asyncio
    async def test_generate_death_narrative(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps(
            {
                "summary": "The Tech-Priest fell beneath the forge in a blaze of incense and steel.",
                "cause_of_death": "cut down by a rogue servitor",
            }
        )
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.generate_death_narrative(
            {
                "player_name": "Magos Explorator",
                "location": "Lower Forge",
                "turns_survived": 12,
                "enemies_slain": 4,
                "deepest_level_reached": 3,
                "enemy_summary": "rogue servitors",
                "cause_of_death": "cut down by a rogue servitor",
            }
        )

        assert result.summary == (
            "The Tech-Priest fell beneath the forge in a blaze of incense and steel."
        )
        assert result.cause_of_death == "cut down by a rogue servitor"


# ---------------------------------------------------------------------------
# Ambient dungeon discovery
# ---------------------------------------------------------------------------

class TestAmbientDungeonDiscovery:
    @pytest.mark.asyncio
    async def test_ambient_discovery_does_not_advance_turn_state(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "narrative_text": "A data shrine hums softly in the gloom.",
            "scene_art": "╔═══╗\n║†║\n╚═══╝",
            "info_update": None,
            "entities": [],
            "combat_trigger": False,
            "speaking_npc": None,
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.describe_ambient_dungeon_target(
            {
                "target_label": "Data Shrine",
                "target_kind": "object",
                "terrain": "shrine",
                "target_position": [3, 2],
            }
        )

        assert result.narrative_text == "A data shrine hums softly in the gloom."
        assert result.scene_art == "╔═══╗\n║†║\n╚═══╝"
        assert engine.turn_count == 0
        assert engine._conversation_history == []


# ---------------------------------------------------------------------------
# generate_encounter
# ---------------------------------------------------------------------------

class TestGenerateEncounter:
    @pytest.mark.asyncio
    async def test_success_returns_roster(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "encounter_description": "Rogue servitors lurch from the shadows.",
            "enemies": [
                {"template_key": "servitor", "count": 2},
                {"template_key": "gunner", "count": 1},
            ],
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.generate_encounter()

        assert "encounter_description" in result
        assert "enemy_roster" in result
        assert result["encounter_description"] == "Rogue servitors lurch from the shadows."
        # 2 servitors + 1 gunner = 3 enemies
        assert len(result["enemy_roster"]) == 3
        keys = [r[0] for r in result["enemy_roster"]]
        assert keys.count("servitor") == 2
        assert keys.count("gunner") == 1

    @pytest.mark.asyncio
    async def test_invalid_template_filtered(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "encounter_description": "Unknown foes.",
            "enemies": [
                {"template_key": "nonexistent_enemy", "count": 3},
                {"template_key": "servitor", "count": 1},
            ],
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.generate_encounter()

        # Only the valid servitor should be placed
        assert len(result["enemy_roster"]) == 1
        assert result["enemy_roster"][0][0] == "servitor"

    @pytest.mark.asyncio
    async def test_api_failure_uses_fallback(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        engine._client.messages.create.side_effect = RuntimeError("connection lost")

        result = await engine.generate_encounter()

        # Should still return a valid encounter from the fallback
        assert "encounter_description" in result
        assert "enemy_roster" in result
        assert len(result["enemy_roster"]) > 0

    @pytest.mark.asyncio
    async def test_empty_enemies_uses_fallback(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "encounter_description": "Nothing here.",
            "enemies": [],
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.generate_encounter()

        # Fallback should kick in for empty enemy list
        assert len(result["enemy_roster"]) > 0

    @pytest.mark.asyncio
    async def test_count_capped_at_five(
        self, engine_with_mock_client: GameEngine
    ) -> None:
        engine = engine_with_mock_client
        response_json = json.dumps({
            "encounter_description": "A horde!",
            "enemies": [
                {"template_key": "hormagaunt", "count": 99},
            ],
        })
        engine._client.messages.create.return_value = _make_api_response(response_json)

        result = await engine.generate_encounter()

        # Count should be capped at 5
        assert len(result["enemy_roster"]) <= 5
