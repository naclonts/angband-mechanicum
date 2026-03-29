"""Tests for the dungeon screen shell and rendering helpers."""

from __future__ import annotations

from rich.text import Text

from angband_mechanicum.app import AngbandMechanicumApp
from angband_mechanicum.engine.dungeon_level import DungeonLevel, DungeonTerrain, FogState
from angband_mechanicum.engine.story_starts import StoryStart
from angband_mechanicum.screens.game_screen import GameScreen
from angband_mechanicum.screens.dungeon_screen import DungeonMapState
from angband_mechanicum.widgets.dungeon_map import render_dungeon_map, render_dungeon_status


def _make_level() -> DungeonLevel:
    level = DungeonLevel(
        level_id="test-floor",
        name="Test Floor",
        depth=1,
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
    level.set_terrain(5, 2, DungeonTerrain.WALL)
    level.player_pos = (2, 2)
    level.compute_fov((2, 2), 1)
    return level


class TestDungeonMapRendering:
    def test_render_includes_player_and_visible_terrain(self) -> None:
        level = _make_level()
        rendered = render_dungeon_map(level, (2, 2))
        Text.from_markup(rendered)
        assert "[bold #00ff41]@[/bold #00ff41]" in rendered
        assert "#6e4b1e" in rendered

    def test_render_hides_unseen_tiles(self) -> None:
        level = _make_level()
        level.reset_visible()
        level.set_visible(2, 2)
        rendered = render_dungeon_map(level, (2, 2))
        assert rendered.count(" ") > 0

    def test_status_panel_reports_fov_and_tile(self) -> None:
        level = _make_level()
        status = render_dungeon_status(level, (2, 2), message_count=3)
        assert "LEVEL: Test Floor" in status
        assert "FOV:" in status
        assert "TILE:  floor" in status


class TestDungeonMapState:
    def test_move_player_updates_position_and_fov(self) -> None:
        level = _make_level()
        state = DungeonMapState(level=level, player_pos=(2, 2), fov_radius=1)
        assert state.move_player(1, 0) is True
        assert state.player_pos == (3, 2)
        assert level.get_tile(3, 2).fog == FogState.VISIBLE
        assert state.move_player(1, 0) is True
        assert state.player_pos == (4, 2)
        assert level.get_tile(2, 2).fog == FogState.EXPLORED
        assert len(state.messages) >= 2

    def test_blocked_move_adds_message(self) -> None:
        level = _make_level()
        state = DungeonMapState(level=level, player_pos=(2, 2), fov_radius=1)
        assert state.move_player(1, 0) is True
        assert state.move_player(1, 0) is True
        assert state.move_player(1, 0) is False
        assert state.messages[-1].startswith("Wall")

    def test_wait_recomputes_visibility_and_logs(self) -> None:
        level = _make_level()
        state = DungeonMapState(level=level, player_pos=(2, 2), fov_radius=1)
        state.wait()
        assert state.messages[-1] == "You hold position and scan the chamber."
        assert level.get_tile(2, 2).fog == FogState.VISIBLE

    def test_state_round_trips_through_dict(self) -> None:
        level = _make_level()
        state = DungeonMapState(
            level=level,
            player_pos=(2, 2),
            fov_radius=2,
            messages=["First contact"],
        )
        restored = DungeonMapState.from_dict(state.to_dict())
        assert restored.player_pos == (2, 2)
        assert restored.fov_radius == 2
        assert restored.messages == ["First contact"]
        assert restored.level.name == "Test Floor"


class TestTransitionHelpers:
    def test_app_builds_dungeon_session_from_story_start(self) -> None:
        app = AngbandMechanicumApp()
        story = StoryStart(
            id="test-story",
            title="The Silent Forge",
            description="A forge goes silent.",
            location="Forge-Cathedral Alpha",
            intro_narrative="The forge awaits.",
            scene_art="ART",
        )
        session = app.build_dungeon_session(story)

        assert session.story_id == "test-story"
        assert session.location == "Forge-Cathedral Alpha"
        assert session.intro_narrative == "The forge awaits."
        assert session.state.level.name == "Forge-Cathedral Alpha"
        assert session.state.messages == ["The forge awaits."]
        assert session.state.player_pos is not None

    def test_game_screen_can_build_dungeon_transition_state(self) -> None:
        screen = GameScreen()
        payload = screen.build_dungeon_transition_state(
            ["Conversation ended."],
            scene_art="SCENE",
            info_update={"LOCATION": "Vault"},
        )

        assert payload["narrative_log"] == ["Conversation ended."]
        assert payload["current_scene_art"] == "SCENE"
        assert payload["info_update"] == {"LOCATION": "Vault"}
