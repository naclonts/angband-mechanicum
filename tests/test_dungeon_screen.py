"""Tests for the dungeon screen shell and rendering helpers."""

from __future__ import annotations

from rich.text import Text

from angband_mechanicum.engine.dungeon_level import DungeonLevel, DungeonTerrain, FogState
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
