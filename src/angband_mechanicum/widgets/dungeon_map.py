"""Dungeon map widgets and rendering helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from rich.text import Text
from textual.widgets import RichLog, Static

from angband_mechanicum.engine.dungeon_level import DungeonLevel, FogState, TerrainGlyph, get_terrain_glyph


@dataclass
class DungeonMapEntity:
    """A lightweight overlay for later dungeon NPC integration."""

    entity_id: str
    name: str
    x: int
    y: int
    symbol: str = "?"
    fg: str = "#00ff41"
    disposition: str = "neutral"
    can_talk: bool = False
    entity_type: str = "character"
    hp: int = 1
    max_hp: int = 1
    attack: int = 1
    armor: int = 0
    description: str = ""
    scene_art: str | None = None
    history_entity_id: str | None = None

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "symbol": self.symbol,
            "fg": self.fg,
            "disposition": self.disposition,
            "can_talk": self.can_talk,
            "entity_type": self.entity_type,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "attack": self.attack,
            "armor": self.armor,
            "description": self.description,
            "scene_art": self.scene_art,
            "history_entity_id": self.history_entity_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "DungeonMapEntity":
        return cls(
            entity_id=str(data["entity_id"]),
            name=str(data["name"]),
            x=int(data["x"]),
            y=int(data["y"]),
            symbol=str(data.get("symbol", "?")),
            fg=str(data.get("fg", "#00ff41")),
            disposition=str(data.get("disposition", "neutral")),
            can_talk=bool(data.get("can_talk", False)),
            entity_type=str(data.get("entity_type", "character")),
            hp=int(data.get("hp", 1)),
            max_hp=int(data.get("max_hp", 1)),
            attack=int(data.get("attack", 1)),
            armor=int(data.get("armor", 0)),
            description=str(data.get("description", "")),
            scene_art=data.get("scene_art") if data.get("scene_art") is not None else None,
            history_entity_id=(
                str(data.get("history_entity_id"))
                if data.get("history_entity_id") is not None
                else None
            ),
        )


def _render_glyph(glyph: TerrainGlyph, visible: bool) -> str:
    if visible:
        return f"[{glyph.fg}]{glyph.char}[/{glyph.fg}]"
    return f"[dim][{glyph.fg}]{glyph.char}[/{glyph.fg}][/dim]"


def _render_cursor() -> str:
    """Render the look cursor."""
    return "[bold #ff66ff]◉[/bold #ff66ff]"


def _tile_visible(level: DungeonLevel, x: int, y: int) -> bool:
    return level.in_bounds(x, y) and level.get_tile(x, y).fog == FogState.VISIBLE


def _resolve_viewport_window(
    level: DungeonLevel,
    player_pos: tuple[int, int],
    viewport_size: tuple[int, int] | None,
) -> tuple[int, int, int, int]:
    """Return the camera window anchored around the player.

    The rendered map reserves a few columns for row labels and a border, so
    the usable tile area is smaller than the raw widget content region.
    """
    if viewport_size is None:
        return 0, 0, level.width, level.height

    viewport_width, viewport_height = viewport_size
    row_label_width = max(2, len(str(level.height - 1)))
    visible_cols = min(level.width, max(1, viewport_width - row_label_width - 2))
    visible_rows = min(level.height, max(1, viewport_height - 3))

    px, py = player_pos
    max_left = max(0, level.width - visible_cols)
    max_top = max(0, level.height - visible_rows)
    left = min(max(px - visible_cols // 2, 0), max_left)
    top = min(max(py - visible_rows // 2, 0), max_top)
    return left, top, visible_cols, visible_rows


def render_dungeon_map(
    level: DungeonLevel,
    player_pos: tuple[int, int],
    entities: Sequence[DungeonMapEntity] = (),
    cursor_pos: tuple[int, int] | None = None,
    viewport_size: tuple[int, int] | None = None,
) -> str:
    """Render a dungeon floor as a rich-text map."""
    left, top, visible_cols, visible_rows = _resolve_viewport_window(
        level,
        player_pos,
        viewport_size,
    )
    right = left + visible_cols
    bottom = top + visible_rows
    row_label_width = max(2, len(str(level.height - 1)))
    entity_by_pos = {
        (entity.x, entity.y): entity
        for entity in entities
        if entity.alive
    }
    lines: list[str] = []

    header = " " * (row_label_width + 1)
    for x in range(left, right):
        header += f"{x % 10}" if x % 5 == 0 else " "
    lines.append(header)
    lines.append(" " * row_label_width + "╔" + "═" * visible_cols + "╗")

    for y in range(top, bottom):
        row: list[str] = [f"{y:>{row_label_width}}║"]
        for x in range(left, right):
            if cursor_pos is not None and (x, y) == cursor_pos:
                row.append(_render_cursor())
                continue
            if (x, y) == player_pos:
                row.append("[bold #00ff41]@[/bold #00ff41]")
                continue

            tile = level.get_tile(x, y)
            if tile.fog == FogState.HIDDEN:
                row.append(" ")
                continue

            entity = entity_by_pos.get((x, y))
            if entity is not None and tile.fog == FogState.VISIBLE:
                row.append(f"[bold {entity.fg}]{entity.symbol}[/bold {entity.fg}]")
                continue

            glyph = get_terrain_glyph(tile.terrain, level.environment)
            row.append(_render_glyph(glyph, tile.fog == FogState.VISIBLE))
        row.append("║")
        lines.append("".join(row))

    lines.append(" " * row_label_width + "╚" + "═" * visible_cols + "╝")
    return "\n".join(lines)


def render_dungeon_status(
    level: DungeonLevel,
    player_pos: tuple[int, int],
    message_count: int,
    entities: Sequence[DungeonMapEntity] = (),
    look_cursor: tuple[int, int] | None = None,
    look_summary: str | None = None,
) -> str:
    """Render the side panel for the dungeon screen."""
    px, py = player_pos
    tile = level.get_tile(px, py)
    visible = sum(1 for row in level.tiles for cell in row if cell.fog == FogState.VISIBLE)
    explored = sum(1 for row in level.tiles for cell in row if cell.fog in {FogState.VISIBLE, FogState.EXPLORED})
    entities_here = [
        entity.name
        for entity in entities
        if entity.alive and (entity.x, entity.y) == player_pos
    ]
    lines = [
        f"LEVEL: {level.name}",
        f"DEPTH: {level.depth}",
        f"ENV:   {level.environment}",
        f"POS:   ({px},{py})",
        f"TILE:  {tile.terrain.value}",
        f"FOV:   {visible} visible / {explored} seen",
        f"LOG:   {message_count} entries",
    ]
    if look_cursor is not None:
        lx, ly = look_cursor
        lines.extend(
            [
                "",
                "LOOK MODE:",
                f"  TARGET: ({lx},{ly})",
            ]
        )
        if look_summary:
            lines.append(f"  {look_summary}")
    else:
        lines.extend(
            [
                "",
                "[dim]l: look / Enter: inspect / Esc: cancel[/dim]",
            ]
        )
    if entities_here:
        lines.append("")
        lines.append("CONTACT:")
        for name in entities_here:
            lines.append(f"  {name}")
    lines.extend(
        [
            "",
            "[dim]ARROWS / HJKL: move[/dim]",
            "[dim]. or space: wait[/dim]",
            "[dim]F1: help[/dim]",
        ]
    )
    return "\n".join(lines)


class DungeonMapPane(Static):
    """Widget that renders the dungeon floor."""

    can_focus = True

    def __init__(
        self,
        level: DungeonLevel,
        get_player_pos: Callable[[], tuple[int, int]],
        get_entities: Callable[[], Sequence[DungeonMapEntity]],
        get_cursor_pos: Callable[[], tuple[int, int] | None] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._level = level
        self._get_player_pos = get_player_pos
        self._get_entities = get_entities
        self._get_cursor_pos = get_cursor_pos

    def refresh_map(self) -> None:
        cursor_pos = self._get_cursor_pos() if self._get_cursor_pos is not None else None
        self.update(
            Text.from_markup(
                render_dungeon_map(
                    self._level,
                    self._get_player_pos(),
                    self._get_entities(),
                    cursor_pos=cursor_pos,
                    viewport_size=(self.content_width, self.content_height),
                )
            )
        )

    @property
    def content_width(self) -> int:
        """Return the usable width inside the pane (excluding border + padding)."""
        region = self.content_region
        return region.width if region.width > 0 else 56

    @property
    def content_height(self) -> int:
        """Return the usable height inside the pane (excluding border + padding)."""
        region = self.content_region
        return region.height if region.height > 0 else 16

    def on_mount(self) -> None:
        self.refresh_map()


class DungeonTransitionPane(Static):
    """Small helper used for future map/text transition previews."""

    def show_context(self, title: str, lines: Sequence[str]) -> None:
        body = "\n".join(lines)
        self.update(Text.from_markup(f"[bold]{title}[/bold]\n{body}"))


class DungeonStatusPane(Static):
    """Widget that renders dungeon floor metadata."""

    def __init__(
        self,
        level: DungeonLevel,
        get_player_pos: Callable[[], tuple[int, int]],
        get_entities: Callable[[], Sequence[DungeonMapEntity]],
        get_message_count: Callable[[], int],
        get_look_cursor: Callable[[], tuple[int, int] | None] | None = None,
        get_look_summary: Callable[[], str | None] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._level = level
        self._get_player_pos = get_player_pos
        self._get_entities = get_entities
        self._get_message_count = get_message_count
        self._get_look_cursor = get_look_cursor
        self._get_look_summary = get_look_summary

    def refresh_status(self) -> None:
        look_cursor = self._get_look_cursor() if self._get_look_cursor is not None else None
        look_summary = (
            self._get_look_summary() if self._get_look_summary is not None else None
        )
        self.update(
            Text.from_markup(
                render_dungeon_status(
                    self._level,
                    self._get_player_pos(),
                    self._get_message_count(),
                    self._get_entities(),
                    look_cursor=look_cursor,
                    look_summary=look_summary,
                )
            )
        )

    def on_mount(self) -> None:
        self.border_title = "⛨ EXPLORATION STATUS"
        self.refresh_status()


class DungeonMessageLog(RichLog):
    """Scrollback log for map actions."""

    can_focus = False

    def __init__(
        self,
        get_messages: Callable[[], Sequence[str]],
        **kwargs: object,
    ) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=True, **kwargs)  # type: ignore[arg-type]
        self._get_messages = get_messages
        self._displayed_count = 0

    def sync_log(self) -> None:
        messages = self._get_messages()
        new_messages = messages[self._displayed_count :]
        for message in new_messages:
            self.write(message)
        self._displayed_count = len(messages)

    def on_mount(self) -> None:
        self.border_title = "⛨ FIELD LOG"
        self.sync_log()
