"""Tests for app-level flow helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from angband_mechanicum import app as app_module
from angband_mechanicum.app import AngbandMechanicumApp, DungeonSession
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
    app.return_to_menu_view = lambda: returned.append(True)  # type: ignore[assignment]

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
