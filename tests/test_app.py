"""Tests for app-level flow helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from angband_mechanicum import app as app_module
from angband_mechanicum.app import AngbandMechanicumApp, DungeonSession
from angband_mechanicum.engine.combat_engine import CombatStats
from angband_mechanicum.engine.dungeon_entities import (
    DungeonDisposition,
    DungeonEntity,
    DungeonEntityRoster,
    DungeonMovementAI,
)
from angband_mechanicum.engine.dungeon_gen import GeneratedFloor
from angband_mechanicum.engine.dungeon_profiles import build_story_dungeon_profile
from angband_mechanicum.engine.dungeon_level import DungeonLevel, DungeonTerrain
from angband_mechanicum.engine.game_engine import DeathNarrative
from angband_mechanicum.engine.story_starts import StoryStart
from angband_mechanicum.engine.save_manager import DeathRecord
from angband_mechanicum.screens.game_screen import GameScreen


@dataclass
class _FakeSaveManager:
    saved_record: DeathRecord | None = None
    deleted_slot: str | None = None

    def save_death_record(self, record: DeathRecord) -> None:
        self.saved_record = record

    def delete_save(self, slot_id: str) -> None:
        self.deleted_slot = slot_id


def _make_floor_with_contacts(
    *,
    level_id: str,
    name: str,
    depth: int,
) -> GeneratedFloor:
    level = DungeonLevel(
        level_id=level_id,
        name=name,
        depth=depth,
        environment="forge",
        width=7,
        height=5,
    )
    for y in range(level.height):
        for x in range(level.width):
            if x in (0, level.width - 1) or y in (0, level.height - 1):
                level.set_terrain(x, y, DungeonTerrain.WALL)
            else:
                level.set_terrain(x, y, DungeonTerrain.FLOOR)
    level.player_pos = (2, 2)
    level.stairs_up = [(2, 1)]
    level.stairs_down = [(4, 2)]
    level.set_terrain(2, 1, DungeonTerrain.STAIRS_UP)
    level.set_terrain(4, 2, DungeonTerrain.STAIRS_DOWN)

    roster = DungeonEntityRoster()
    for index, (entity_id, x, y, disposition, can_talk) in enumerate(
        (
            ("forge-priest", 3, 2, DungeonDisposition.FRIENDLY, True),
            ("rogue-servitor", 4, 1, DungeonDisposition.HOSTILE, False),
        ),
    ):
        entity = DungeonEntity(
            entity_id=entity_id,
            name=f"Contact {index + 1}",
            disposition=disposition,
            movement_ai=(
                DungeonMovementAI.STATIONARY
                if disposition != DungeonDisposition.HOSTILE
                else DungeonMovementAI.AGGRESSIVE
            ),
            can_talk=can_talk,
            portrait_key="mechanicus_adept",
            stats=CombatStats(
                max_hp=6 + index,
                hp=6 + index,
                attack=2 + index,
                armor=index,
                movement=3,
                attack_range=1,
            ),
            description=f"Generated contact {index + 1}",
        )
        roster.add(entity)
        entity.place(level, x, y)

    return GeneratedFloor(
        level=level,
        rooms=[],
        environment="forge",
        entry_room_index=0,
        exit_room_index=0,
        entity_roster=roster,
    )


def _make_travel_floor(
    *,
    level_id: str,
    name: str,
    depth: int,
    environment: str,
) -> GeneratedFloor:
    level = DungeonLevel(
        level_id=level_id,
        name=name,
        depth=depth,
        environment=environment,
        width=7,
        height=5,
    )
    for y in range(level.height):
        for x in range(level.width):
            if x in (0, level.width - 1) or y in (0, level.height - 1):
                level.set_terrain(x, y, DungeonTerrain.WALL)
            else:
                level.set_terrain(x, y, DungeonTerrain.FLOOR)
    level.player_pos = (2, 2)
    level.stairs_up = [(2, 1)]
    level.stairs_down = [(4, 2)]
    level.set_terrain(2, 1, DungeonTerrain.STAIRS_UP)
    level.set_terrain(4, 2, DungeonTerrain.STAIRS_DOWN)

    return GeneratedFloor(
        level=level,
        rooms=[],
        environment=environment,
        entry_room_index=0,
        exit_room_index=0,
        entity_roster=DungeonEntityRoster(),
    )


def test_archive_player_death_saves_record_and_clears_live_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app archives the memorial, deletes the active save, and resets state."""
    fake_manager = _FakeSaveManager()
    monkeypatch.setattr(app_module, "SaveManager", lambda: fake_manager)
    monkeypatch.setattr(app_module, "GameEngine", lambda: object())

    app = AngbandMechanicumApp()
    app.save_slot = "slot-1"
    app.dungeon_session = object()
    returned: list[bool] = []
    app.open_hall_of_dead_view = lambda: returned.append(True)  # type: ignore[assignment]

    record = DeathRecord(
        record_id="death-1",
        timestamp=1_000.0,
        player_name="Magos Explorator",
        location="Lower Forge",
        turns_survived=12,
        enemies_slain=4,
        deepest_level_reached=3,
        cause_of_death="Crushed by a daemon engine",
        summary="The Tech-Priest fell in glorious service.",
        save_slot_id="slot-1",
        story_start_id="forge-escape",
    )

    app.archive_player_death(record)

    assert fake_manager.saved_record == record
    assert fake_manager.deleted_slot == "slot-1"
    assert app.save_slot is None
    assert app.dungeon_session is None
    assert returned == [True]


@pytest.mark.asyncio
async def test_handle_player_death_generates_and_archives_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Death orchestration should build a record, archive it, and show the hall."""
    fake_manager = _FakeSaveManager()
    monkeypatch.setattr(app_module, "SaveManager", lambda: fake_manager)
    monkeypatch.setattr(app_module, "GameEngine", lambda: object())

    class _FakeEngine:
        player_name = "Magos Explorator"
        turn_count = 17

        async def generate_death_narrative(
            self, death_context: dict[str, object]
        ) -> DeathNarrative:
            return DeathNarrative(
                summary=f"{death_context['location']} remembers the final stand.",
                cause_of_death="crushed by a daemon engine",
            )

    app = AngbandMechanicumApp()
    app.game_engine = _FakeEngine()  # type: ignore[assignment]
    app.save_slot = "slot-2"
    app._story_start = StoryStart(  # type: ignore[attr-defined]
        id="forge-escape",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    hall_opened: list[bool] = []
    app.open_hall_of_dead_view = lambda: hall_opened.append(True)  # type: ignore[assignment]

    record = await app.handle_player_death(
        {
            "location": "Lower Forge",
            "turns_survived": 17,
            "enemies_slain": 3,
            "deepest_level_reached": 4,
            "enemy_summary": "rogue servitors",
        }
    )

    assert fake_manager.saved_record == record
    assert record.player_name == "Magos Explorator"
    assert record.location == "Lower Forge"
    assert record.turns_survived == 17
    assert record.enemies_slain == 3
    assert record.deepest_level_reached == 4
    assert record.cause_of_death == "crushed by a daemon engine"
    assert "Lower Forge remembers" in record.summary
    assert hall_opened == [True]


def test_return_to_dungeon_view_keeps_pending_text_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text-view bridge data should survive the round-trip back to dungeon mode."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="bridge-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    app.dungeon_session = app.build_dungeon_session(story)

    opened: list[bool] = []
    monkeypatch.setattr(app, "open_dungeon_view", lambda **kwargs: opened.append(True))

    app.return_to_dungeon_view(
        narrative_lines=["The machine spirit points the way."],
        scene_art="BRIDGE ART",
        info_update={"LOCATION": "Cargo Lift Shaft", "OBJECTIVE": "Proceed below"},
    )

    assert opened == [True]
    assert app.game_engine._info_panel["LOCATION"] == "Cargo Lift Shaft"
    assert app.dungeon_session is not None
    assert app.dungeon_session.pending_text_context["scene_art"] == "BRIDGE ART"
    assert app.dungeon_session.pending_text_context["LOCATION"] == "Cargo Lift Shaft"
    assert app.dungeon_session.pending_text_context["OBJECTIVE"] == "Proceed below"


def test_open_text_view_keeps_live_dungeon_location_on_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dungeon-to-text bridges should not fall back to the story-start location."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="bridge-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    app.dungeon_session = app.build_dungeon_session(story)
    assert app.dungeon_session is not None
    app.dungeon_session.location = "Ashland Expanse"
    app.dungeon_session.pending_text_context.update(
        {
            "scene_art": "PENDING ART",
            "LOCATION": "Forge-Cathedral Alpha",
            "OBJECTIVE": "Proceed below",
        }
    )

    captured: dict[str, object] = {}

    def _capture_switch_screen(screen: object) -> None:
        captured["screen"] = screen

    monkeypatch.setattr(app, "switch_screen", _capture_switch_screen)

    app.open_text_view(
        restored_state={
            "narrative_log": ["The machine spirit points the way."],
            "current_scene_art": "BRIDGE ART",
            "info_panel": {"LOCATION": "Ashland Expanse"},
        },
        story_start=story,
    )

    screen = captured["screen"]
    assert isinstance(screen, GameScreen)
    assert screen._restored_state is not None
    assert screen._restored_state["info_panel"] == {"LOCATION": "Ashland Expanse"}
    assert screen._restored_state["current_scene_art"] == "BRIDGE ART"
    assert "OBJECTIVE" not in screen._restored_state.get("info_update", {})
    assert app.dungeon_session.pending_text_context == {}


def test_open_text_view_prefers_target_art_when_bridge_scene_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit examine bridges should not fall back to stale story art."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="bridge-art-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="STORY ART",
    )
    app.dungeon_session = app.build_dungeon_session(story)
    assert app.dungeon_session is not None
    app.dungeon_session.pending_text_context.update(
        {
            "scene_art": "PENDING ART",
            "LOCATION": "Forge-Cathedra Alpha",
        }
    )

    captured: dict[str, object] = {}

    def _capture_switch_screen(screen: object) -> None:
        captured["screen"] = screen

    monkeypatch.setattr(app, "switch_screen", _capture_switch_screen)

    app.open_text_view(
        restored_state={
            "narrative_log": ["You study the relic closely."],
            "current_scene_art": "",
            "target_scene_art": "TARGET ART",
        },
        story_start=story,
    )

    screen = captured["screen"]
    assert isinstance(screen, GameScreen)
    assert screen._restored_state is not None
    assert screen._restored_state["current_scene_art"] == "TARGET ART"
    assert app.dungeon_session.pending_text_context == {}


def test_open_text_view_keeps_live_dungeon_location_on_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dungeon-to-text bridges should not fall back to the story-start location."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="bridge-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    app.dungeon_session = app.build_dungeon_session(story)
    assert app.dungeon_session is not None
    app.dungeon_session.location = "Ashland Expanse"
    app.dungeon_session.pending_text_context.update(
        {
            "scene_art": "PENDING ART",
            "LOCATION": "Forge-Cathedral Alpha",
            "OBJECTIVE": "Proceed below",
        }
    )

    captured: dict[str, object] = {}

    def _capture_switch_screen(screen: object) -> None:
        captured["screen"] = screen

    monkeypatch.setattr(app, "switch_screen", _capture_switch_screen)

    app.open_text_view(
        restored_state={
            "narrative_log": ["The machine spirit points the way."],
            "current_scene_art": "BRIDGE ART",
            "info_panel": {"LOCATION": "Ashland Expanse"},
        },
        story_start=story,
    )

    screen = captured["screen"]
    assert isinstance(screen, GameScreen)
    assert screen._restored_state is not None
    assert screen._restored_state["info_panel"] == {"LOCATION": "Ashland Expanse"}
    assert screen._restored_state["current_scene_art"] == "BRIDGE ART"
    assert "OBJECTIVE" not in screen._restored_state.get("info_update", {})
    assert app.dungeon_session.pending_text_context == {}


def test_travel_dungeon_transition_descends_and_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dungeon transitions should preserve and restore prior floor state."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="forge-transition-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    session = app.build_dungeon_session(story)
    app.dungeon_session = session
    opened: list[str] = []
    monkeypatch.setattr(
        app,
        "open_dungeon_view",
        lambda *args, **kwargs: opened.append(session.state.level.level_id),
    )

    down_pos = session.state.level.stairs_down[0]
    session.state.player_pos = down_pos
    session.state.level.player_pos = down_pos

    app.travel_dungeon_transition()

    assert session.state.level.depth == 2
    assert session.level_stack == [story.id]
    assert session.state.player_pos == session.state.level.stairs_up[0]
    assert opened == [session.state.level.level_id]

    descended_state = session.state
    up_pos = descended_state.level.stairs_up[0]
    descended_state.player_pos = up_pos
    descended_state.level.player_pos = up_pos

    app.travel_dungeon_transition()

    assert session.state.level.depth == 1
    assert session.level_stack == []
    assert session.state.level.level_id == story.id
    assert session.state is session.level_states[story.id]
    assert session.state.messages[-1].startswith("You return via the")


def test_dungeon_session_round_trip_preserves_level_stack() -> None:
    """Transition history should survive serialization and restoration."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="forge-stack-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    session = app.build_dungeon_session(story)
    session.level_stack.append("previous-level")
    session.snapshot_current_state()

    restored = DungeonSession.from_dict(session.to_dict())

    assert restored.level_stack == ["previous-level"]
    assert restored.state.level.level_id == session.state.level.level_id
    assert restored.level_states[session.state.level.level_id].level.name == session.state.level.name


def test_begin_new_game_opens_story_intro_in_text_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """New games should start in the narrative screen instead of the dungeon map."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="intro-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
        info_overrides={"LOCATION": "Forge-Cathedral Alpha"},
    )
    captured: dict[str, object] = {}

    def _capture_open_text_view(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(app, "open_text_view", _capture_open_text_view)
    monkeypatch.setattr(app, "open_dungeon_view", lambda **kwargs: captured.setdefault("opened_dungeon", True))

    app.begin_new_game("Magos Explorator", story)

    assert app.dungeon_session is not None
    assert app.save_slot is not None
    assert "opened_dungeon" not in captured
    assert captured["story_start"] == story
    restored_state = captured["restored_state"]
    assert isinstance(restored_state, dict)
    assert restored_state["narrative_log"] == ["The forge awaits."]
    assert restored_state["current_scene_art"] == "ART"
    assert restored_state["info_update"] == {"LOCATION": "Forge-Cathedral Alpha"}


def test_build_dungeon_session_includes_generated_contacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh dungeon sessions should carry generated contacts into live state."""
    floor = _make_floor_with_contacts(
        level_id="forge-session",
        name="Forge Session",
        depth=1,
    )
    monkeypatch.setattr(app_module, "generate_dungeon_floor", lambda **kwargs: floor)

    app = AngbandMechanicumApp()
    story = StoryStart(
        id="forge-session",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )

    session = app.build_dungeon_session(story)

    assert [entity.entity_id for entity in session.state.entities] == [
        "forge-priest",
        "rogue-servitor",
    ]
    assert [entity.name for entity in session.state.entities] == [
        "Contact 1",
        "Contact 2",
    ]
    assert session.state.entities[0].disposition == "friendly"
    assert session.state.entities[1].disposition == "hostile"
    assert (session.state.entities[0].x, session.state.entities[0].y) == (3, 2)
    assert (session.state.entities[1].x, session.state.entities[1].y) == (4, 1)


def test_travel_dungeon_transition_preserves_generated_contacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Descended floors should also mount generated contacts into live state."""
    first_floor = _make_floor_with_contacts(
        level_id="forge-root",
        name="Forge Root",
        depth=1,
    )
    second_floor = _make_floor_with_contacts(
        level_id="forge-root:depth-2",
        name="Forge Root Depth 2",
        depth=2,
    )
    second_floor.entity_roster.entities["rogue-servitor"].name = "Depth Two Contact"

    def _fake_generate_dungeon_floor(**kwargs: object) -> GeneratedFloor:
        depth = int(kwargs["depth"])
        return first_floor if depth == 1 else second_floor

    monkeypatch.setattr(app_module, "generate_dungeon_floor", _fake_generate_dungeon_floor)

    app = AngbandMechanicumApp()
    story = StoryStart(
        id="forge-root",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    session = app.build_dungeon_session(story)
    app.dungeon_session = session
    app.open_dungeon_view = lambda **kwargs: None  # type: ignore[assignment]

    down_pos = session.state.level.stairs_down[0]
    session.state.player_pos = down_pos
    session.state.level.player_pos = down_pos

    app.travel_dungeon_transition()

    assert session.state.level.depth == 2
    assert [entity.entity_id for entity in session.state.entities] == [
        "forge-priest",
        "rogue-servitor",
    ]
    assert session.state.entities[1].name == "Depth Two Contact"
    assert (session.state.entities[1].x, session.state.entities[1].y) == (4, 1)


def test_dungeon_session_round_trip_preserves_generated_contacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serialized dungeon sessions should retain generated live contacts."""
    floor = _make_floor_with_contacts(
        level_id="forge-persist",
        name="Forge Persist",
        depth=1,
    )
    monkeypatch.setattr(app_module, "generate_dungeon_floor", lambda **kwargs: floor)

    app = AngbandMechanicumApp()
    story = StoryStart(
        id="forge-persist",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    session = app.build_dungeon_session(story)
    restored = DungeonSession.from_dict(session.to_dict())

    assert [entity.entity_id for entity in restored.state.entities] == [
        "forge-priest",
        "rogue-servitor",
    ]
    assert restored.state.entities[0].description == "Generated contact 1"
    assert restored.state.entities[1].hp == 7


def test_travel_to_destination_builds_environment_specific_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text-view travel should mount a session for the resolved destination."""
    request_text = "Take me to the sewer drains beneath the underhive."

    def _fake_generate_dungeon_floor(**kwargs: object) -> GeneratedFloor:
        return _make_travel_floor(
            level_id=str(kwargs["level_id"]),
            name=str(kwargs["name"]),
            depth=int(kwargs["depth"]),
            environment=str(kwargs["environment"]),
        )

    monkeypatch.setattr(app_module, "generate_dungeon_floor", _fake_generate_dungeon_floor)

    app = AngbandMechanicumApp()
    session, destination = app.build_destination_session(request_text)

    assert destination.environment == "sewer"
    assert destination.display_name == "Sub-hive drainage"
    assert app.dungeon_session is session
    assert session.destination_query == request_text
    assert session.destination_environment == "sewer"
    assert session.destination_label == "Sub-hive drainage"
    assert session.location == "Sub-hive drainage"
    assert session.state.level.environment == "sewer"
    assert session.state.level.name == "Sub-hive drainage"
    assert session.state.level.level_id.startswith("travel:sewer:")

    restored = DungeonSession.from_dict(session.to_dict())
    assert restored.destination_query == request_text
    assert restored.destination_environment == "sewer"
    assert restored.destination_label == "Sub-hive drainage"


def test_enter_dungeon_combat_view_replaces_session_with_encounter_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Combat routing should stay inside the dungeon bridge instead of tactical combat."""
    floor = _make_floor_with_contacts(
        level_id="forge-combat",
        name="Forge Combat",
        depth=1,
    )

    def _fake_generate_dungeon_floor(**kwargs: object) -> GeneratedFloor:
        floor.level.name = str(kwargs["name"])
        floor.level.environment = str(kwargs["environment"])
        floor.level.level_id = str(kwargs["level_id"])
        return floor

    monkeypatch.setattr(app_module, "generate_dungeon_floor", _fake_generate_dungeon_floor)

    app = AngbandMechanicumApp()
    story = StoryStart(
        id="forge-combat-test",
        title="The Silent Forge",
        description="A forge goes silent.",
        location="Forge-Cathedral Alpha",
        intro_narrative="The forge awaits.",
        scene_art="ART",
    )
    session = app.build_dungeon_session(story)
    app.dungeon_session = session

    captured: dict[str, object] = {}
    app.return_to_dungeon_view = lambda **kwargs: captured.update(kwargs)  # type: ignore[assignment]

    app.enter_dungeon_combat_view(
        room_hint={"name": "Engagement Cell", "theme": "forge", "room_type": "arena"},
        narrative_lines=["Hostiles manifest in the chamber."],
        scene_art="SCENE",
        info_update={"MODE": "dungeon"},
        source_label="combat-trigger",
    )

    assert session.state.level.name == "Engagement Cell"
    assert session.current_environment_id == "forge"
    assert [entity.entity_id for entity in session.state.entities] == [
        "forge-priest",
        "rogue-servitor",
    ]
    assert session.state.messages[0] == "The forge awaits."
    assert captured["narrative_lines"] == ["Hostiles manifest in the chamber."]
    assert captured["scene_art"] == "SCENE"
    assert captured["info_update"] == {"MODE": "dungeon"}


def test_game_screen_recognizes_structured_explore_hints() -> None:
    """Text responses can request a dungeon return without a hard-coded slash command."""
    assert GameScreen._response_requests_dungeon_return(
        "The path opens before you.",
        {"NEXT_MODE": "explore"},
    ) is True
    assert GameScreen._response_requests_dungeon_return(
        "Remain in conversation.",
        None,
    ) is False


def test_build_dungeon_session_uses_story_generation_profile() -> None:
    """Curated story starts should seed an explicit dungeon profile immediately."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="titan-recovery",
        title="The Fallen God-Machine",
        description="Recover the crippled titan before the greenskins strip it bare.",
        location="Ash Wastes — Titan Graveyard",
        intro_narrative="The titan waits in agony.",
        scene_art="ART",
    )

    session = app.build_dungeon_session(story)

    assert session.generation_profile is not None
    assert session.generation_profile.environment == "ash_dune_outpost"
    assert session.generation_profile.profile_id == "story:titan-recovery"
    assert session.current_environment_id == "ash_dune_outpost"
    assert app.game_engine.to_dict()["current_environment_id"] == "ash_dune_outpost"
    assert app.game_engine.to_dict()["current_location_profile_id"] == "story:titan-recovery"


def test_dungeon_session_round_trip_preserves_generation_profile() -> None:
    """Story profile metadata should survive save/load round trips."""
    app = AngbandMechanicumApp()
    story = StoryStart(
        id="titan-recovery",
        title="The Fallen God-Machine",
        description="Recover the crippled titan before the greenskins strip it bare.",
        location="Ash Wastes — Titan Graveyard",
        intro_narrative="The titan waits in agony.",
        scene_art="ART",
    )
    session = app.build_dungeon_session(story)

    restored = DungeonSession.from_dict(session.to_dict())

    assert restored.generation_profile is not None
    assert restored.generation_profile.environment == "ash_dune_outpost"
    assert restored.generation_profile.required_themed_room_names == ("Titan Hull Breach",)
    assert restored.current_environment_id == "ash_dune_outpost"


def test_story_profile_builder_uses_explicit_story_metadata() -> None:
    """Story profiles should prefer explicit mappings over brittle keyword inference."""
    story = StoryStart(
        id="titan-recovery",
        title="The Fallen God-Machine",
        description="A titan graveyard mission in the ash wastes.",
        location="Ash Wastes — Titan Graveyard",
        intro_narrative="The titan waits in agony.",
        scene_art="ART",
    )

    profile = build_story_dungeon_profile(story)

    assert profile.environment == "ash_dune_outpost"
    assert profile.hostile_tags == ("ork", "loota", "scavenger", "ash")
