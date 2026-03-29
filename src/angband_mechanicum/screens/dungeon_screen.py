"""Unified dungeon exploration screen."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from angband_mechanicum.engine.dungeon_gen import GeneratedFloor, generate_dungeon_floor
from angband_mechanicum.engine.dungeon_level import DungeonLevel, DungeonTerrain
from angband_mechanicum.widgets.dungeon_map import (
    DungeonMapEntity,
    DungeonMapPane,
    DungeonMessageLog,
    DungeonStatusPane,
)
from angband_mechanicum.widgets.help_overlay import HelpOverlay


@dataclass
class DungeonMapState:
    """Mutable dungeon exploration state owned by the screen."""

    level: DungeonLevel
    player_pos: tuple[int, int] | None = None
    fov_radius: int = 8
    entities: list[DungeonMapEntity] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.player_pos is None:
            self.player_pos = self.level.player_pos
        if self.player_pos is None and self.level.stairs_up:
            self.player_pos = self.level.stairs_up[0]
        if self.player_pos is None:
            self.player_pos = self._first_passable_tile()
        self._apply_position()
        self.recompute_fov()

    def _first_passable_tile(self) -> tuple[int, int]:
        for y in range(self.level.height):
            for x in range(self.level.width):
                if self.level.get_tile(x, y).passable:
                    return (x, y)
        return (0, 0)

    def _apply_position(self) -> None:
        assert self.player_pos is not None
        self.level.player_pos = self.player_pos

    def append_message(self, text: str) -> None:
        self.messages.append(text)

    def entity_at(self, position: tuple[int, int]) -> DungeonMapEntity | None:
        for entity in self.entities:
            if (entity.x, entity.y) == position:
                return entity
        return None

    def recompute_fov(self) -> None:
        assert self.player_pos is not None
        self.level.compute_fov(self.player_pos, self.fov_radius)

    def move_player(self, dx: int, dy: int) -> bool:
        assert self.player_pos is not None
        nx = self.player_pos[0] + dx
        ny = self.player_pos[1] + dy
        if not self.level.in_bounds(nx, ny):
            self.append_message("The void lies beyond the map edge.")
            return False
        if not self.level.get_tile(nx, ny).passable:
            self.append_message(f"{self.level.get_terrain(nx, ny).value.title()} blocks the route.")
            return False
        if self.entity_at((nx, ny)) is not None or self.level.get_creature(nx, ny):
            self.append_message("Contact at the destination blocks movement.")
            return False
        self.player_pos = (nx, ny)
        self._apply_position()
        self.recompute_fov()
        terrain = self.level.get_terrain(nx, ny).value.replace("_", " ").title()
        self.append_message(f"You move to {nx},{ny} across {terrain}.")
        if self.level.get_terrain(nx, ny) == DungeonTerrain.STAIRS_DOWN:
            self.append_message("Downward stairs descend deeper.")
        elif self.level.get_terrain(nx, ny) == DungeonTerrain.STAIRS_UP:
            self.append_message("Upward stairs lead back toward the surface.")
        return True

    def wait(self) -> None:
        assert self.player_pos is not None
        self.recompute_fov()
        self.append_message("You hold position and scan the chamber.")


class DungeonScreen(Screen[None]):
    """Unified dungeon screen shell for exploration and future combat."""

    BINDINGS = [
        Binding("up", "move_north", "Move north", show=False),
        Binding("down", "move_south", "Move south", show=False),
        Binding("left", "move_west", "Move west", show=False),
        Binding("right", "move_east", "Move east", show=False),
        Binding("h", "move_west", "Move west", show=False),
        Binding("j", "move_south", "Move south", show=False),
        Binding("k", "move_north", "Move north", show=False),
        Binding("l", "move_east", "Move east", show=False),
        Binding("y", "move_northwest", "Move northwest", show=False),
        Binding("u", "move_northeast", "Move northeast", show=False),
        Binding("b", "move_southwest", "Move southwest", show=False),
        Binding("n", "move_southeast", "Move southeast", show=False),
        Binding("space", "wait", "Wait", show=True),
        Binding("f1", "show_help", "Help", show=True),
    ]

    HOTKEYS: list[tuple[str, str]] = [
        ("Arrow keys", "Move"),
        ("HJKL", "Cardinal movement"),
        ("YUBN", "Diagonal movement"),
        ("Space", "Wait / rescan"),
        ("F1", "Help"),
    ]

    def __init__(
        self,
        level: DungeonLevel | None = None,
        floor: GeneratedFloor | None = None,
        player_pos: tuple[int, int] | None = None,
        fov_radius: int = 8,
        entities: Sequence[DungeonMapEntity] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        if floor is None and level is None:
            floor = generate_dungeon_floor(level_id="demo-floor", depth=1, environment="forge", seed=1)
        resolved_level = floor.level if floor is not None else level
        assert resolved_level is not None
        self._state = DungeonMapState(
            level=resolved_level,
            player_pos=player_pos,
            fov_radius=fov_radius,
            entities=list(entities or []),
        )

    @property
    def state(self) -> DungeonMapState:
        return self._state

    def compose(self) -> ComposeResult:
        with Horizontal(id="dungeon-layout"):
            with Vertical(id="dungeon-left"):
                yield DungeonMapPane(
                    self._state.level,
                    self._get_player_pos,
                    self._get_entities,
                    id="dungeon-map",
                )
                yield DungeonMessageLog(self._get_messages, id="dungeon-log")
            yield DungeonStatusPane(
                self._state.level,
                self._get_player_pos,
                self._get_entities,
                self._get_message_count,
                id="dungeon-status",
            )

    def on_mount(self) -> None:
        self.title = f"DUNGEON: {self._state.level.name.upper()}"
        self._refresh_all()
        self.query_one("#dungeon-map", DungeonMapPane).focus()

    def _get_player_pos(self) -> tuple[int, int]:
        assert self._state.player_pos is not None
        return self._state.player_pos

    def _get_entities(self) -> Sequence[DungeonMapEntity]:
        return list(self._state.entities)

    def _get_messages(self) -> Sequence[str]:
        return list(self._state.messages)

    def _get_message_count(self) -> int:
        return len(self._state.messages)

    def _refresh_all(self) -> None:
        self.query_one("#dungeon-map", DungeonMapPane).refresh_map()
        self.query_one("#dungeon-log", DungeonMessageLog).sync_log()
        self.query_one("#dungeon-status", DungeonStatusPane).refresh_status()

    def _step(self, dx: int, dy: int) -> None:
        self._state.move_player(dx, dy)
        self._refresh_all()

    def action_move_north(self) -> None:
        self._step(0, -1)

    def action_move_south(self) -> None:
        self._step(0, 1)

    def action_move_west(self) -> None:
        self._step(-1, 0)

    def action_move_east(self) -> None:
        self._step(1, 0)

    def action_move_northwest(self) -> None:
        self._step(-1, -1)

    def action_move_northeast(self) -> None:
        self._step(1, -1)

    def action_move_southwest(self) -> None:
        self._step(-1, 1)

    def action_move_southeast(self) -> None:
        self._step(1, 1)

    def action_wait(self) -> None:
        self._state.wait()
        self._refresh_all()

    def action_show_help(self) -> None:
        self.app.push_screen(
            HelpOverlay(
                title="++ DUNGEON HOTKEYS ++",
                hotkeys=self.HOTKEYS,
            )
        )
