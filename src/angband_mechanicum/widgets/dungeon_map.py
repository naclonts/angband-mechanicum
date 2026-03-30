"""Dungeon map widgets and rendering helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

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
    movement: int = 1
    attack_range: int = 1
    armor: int = 0
    description: str = ""
    scene_art: str | None = None
    history_entity_id: str | None = None
    movement_ai: str = "stationary"
    home_position: tuple[int, int] | None = None
    alert_state: str = "idle"
    alert_turns: int = 0
    last_seen_player_position: tuple[int, int] | None = None
    preferred_range: int | None = None
    patrol_route: list[tuple[int, int]] = field(default_factory=list)
    patrol_index: int = 0
    sight_radius: int = 6
    leash_distance: int = 8

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def position(self) -> tuple[int, int] | None:
        return (self.x, self.y)

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
            "movement": self.movement,
            "attack_range": self.attack_range,
            "armor": self.armor,
            "description": self.description,
            "scene_art": self.scene_art,
            "history_entity_id": self.history_entity_id,
            "movement_ai": self.movement_ai,
            "home_position": list(self.home_position) if self.home_position is not None else None,
            "alert_state": self.alert_state,
            "alert_turns": self.alert_turns,
            "last_seen_player_position": (
                list(self.last_seen_player_position)
                if self.last_seen_player_position is not None
                else None
            ),
            "preferred_range": self.preferred_range,
            "patrol_route": [list(pos) for pos in self.patrol_route],
            "patrol_index": self.patrol_index,
            "sight_radius": self.sight_radius,
            "leash_distance": self.leash_distance,
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
            movement=int(data.get("movement", 1)),
            attack_range=int(data.get("attack_range", 1)),
            armor=int(data.get("armor", 0)),
            description=str(data.get("description", "")),
            scene_art=data.get("scene_art") if data.get("scene_art") is not None else None,
            history_entity_id=(
                str(data.get("history_entity_id"))
                if data.get("history_entity_id") is not None
                else None
            ),
            movement_ai=str(data.get("movement_ai", "stationary")),
            home_position=(
                tuple(data["home_position"])
                if data.get("home_position") is not None
                else None
            ),
            alert_state=str(data.get("alert_state", "idle")),
            alert_turns=int(data.get("alert_turns", 0)),
            last_seen_player_position=(
                tuple(data["last_seen_player_position"])
                if data.get("last_seen_player_position") is not None
                else None
            ),
            preferred_range=(
                int(data["preferred_range"])
                if data.get("preferred_range") is not None
                else None
            ),
            patrol_route=[tuple(pos) for pos in data.get("patrol_route", [])],
            patrol_index=int(data.get("patrol_index", 0)),
            sight_radius=int(data.get("sight_radius", 6)),
            leash_distance=int(data.get("leash_distance", 8)),
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
    target_width = viewport_size[0] if viewport_size is not None else None
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
    if target_width is not None:
        padded_lines: list[str] = []
        for line in lines:
            visible_width = len(Text.from_markup(line).plain)
            if visible_width < target_width:
                line = f"{line}{' ' * (target_width - visible_width)}"
            padded_lines.append(line)
        lines = padded_lines
    return "\n".join(lines)


def render_dungeon_status(
    level: DungeonLevel,
    player_pos: tuple[int, int],
    integrity: tuple[int, int] | None,
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
    ]
    if integrity is not None:
        hp, max_hp = integrity
        hp_bar_width = 8
        filled = 0 if max_hp <= 0 else round(hp_bar_width * hp / max_hp)
        empty = hp_bar_width - filled
        lines.extend(
            [
                f"HP:    [{'═' * filled}{'─' * empty}] {hp}/{max_hp}",
            ]
        )
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
            "[dim]. / 5 / space: wait[/dim]",
            "[dim]F1: help[/dim]",
        ]
    )
    return "\n".join(lines)


class DungeonMapPane(Static):
    """Widget that renders the dungeon floor."""

    can_focus = True
    expand = True

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

    def on_resize(self) -> None:
        self.refresh_map()


class DungeonTransitionPane(RichLog):
    """Small helper used for future map/text transition previews."""

    can_focus = True

    def __init__(self, **kwargs: object) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=False, **kwargs)  # type: ignore[arg-type]
        self._title: str | None = None
        self._context_lines: list[str] = []
        self._scene_art: str | None = None
        self._narrative_text: str | None = None
        self._pending_width_refresh: bool = False

    def _current_render_width(self) -> int | None:
        """Return the live content width when layout is ready."""
        try:
            width = self.scrollable_content_region.width or self.content_region.width
        except RuntimeError:
            return None
        return width if width > 0 else None

    def _queue_width_refresh(self) -> None:
        """Replay the current payload once layout has a usable width."""
        if getattr(self, "_pending_width_refresh", False):
            return
        try:
            self._pending_width_refresh = True
            self.call_after_refresh(self._rerender_current_payload)
        except (AttributeError, RuntimeError):
            self._pending_width_refresh = False

    def _rerender_current_payload(self) -> None:
        self._pending_width_refresh = False
        if getattr(self, "_title", None) is None:
            return
        self._render_current_payload()

    def _write_wrapped(self, content: Text) -> None:
        """Render wrapped prose against the pane's current width."""
        width = self._current_render_width()
        if width is None:
            self.write(content)
            self._queue_width_refresh()
            return
        self.write(content, width=width)

    def show_context(self, title: str, lines: Sequence[str]) -> None:
        self._title = title
        self._context_lines = list(lines)
        self._scene_art = None
        self._narrative_text = None
        self._render_current_payload()

    def show_inspect(
        self,
        title: str,
        scene_art: str | None = None,
        narrative_text: str | None = None,
    ) -> None:
        """Display an inspect result with unwrapped art and wrapped prose.

        Scene art is written with ``no_wrap`` so ASCII layouts are preserved.
        Narrative text is written normally and will word-wrap to the panel width.
        """
        self._title = title
        self._context_lines = []
        self._scene_art = scene_art
        self._narrative_text = narrative_text
        self._render_current_payload()

    def _render_current_payload(self) -> None:
        """Repaint the pane from the stored payload."""
        title = self._title
        if title is None:
            return
        self.clear()
        self._write_wrapped(Text.from_markup(f"[bold]{title}[/bold]"))
        if self._scene_art is not None or self._narrative_text is not None:
            if self._scene_art:
                for art_line in self._scene_art.splitlines():
                    self.write(Text(art_line, no_wrap=True, overflow="ignore"))
                if self._narrative_text:
                    self.write(Text(""))
            if self._narrative_text:
                self._write_wrapped(Text.from_markup(self._narrative_text))
        else:
            for line in self._context_lines:
                self._write_wrapped(Text.from_markup(line))
        self.scroll_home()

    def on_resize(self) -> None:
        self._rerender_current_payload()


class DungeonStatusPane(RichLog):
    """Widget that renders dungeon floor metadata."""

    def __init__(
        self,
        level: DungeonLevel,
        get_player_pos: Callable[[], tuple[int, int]],
        get_entities: Callable[[], Sequence[DungeonMapEntity]],
        get_integrity: Callable[[], tuple[int, int] | None],
        get_look_cursor: Callable[[], tuple[int, int] | None] | None = None,
        get_look_summary: Callable[[], str | None] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=False, **kwargs)  # type: ignore[arg-type]
        self._level = level
        self._get_player_pos = get_player_pos
        self._get_entities = get_entities
        self._get_integrity = get_integrity
        self._get_look_cursor = get_look_cursor
        self._get_look_summary = get_look_summary

    def refresh_status(self) -> None:
        look_cursor = self._get_look_cursor() if self._get_look_cursor is not None else None
        look_summary = (
            self._get_look_summary() if self._get_look_summary is not None else None
        )
        self.clear()
        self.write(
            render_dungeon_status(
                self._level,
                self._get_player_pos(),
                self._get_integrity(),
                self._get_entities(),
                look_cursor=look_cursor,
                look_summary=look_summary,
            )
        )
        self.scroll_home()

    def on_mount(self) -> None:
        self.border_title = "⛨ EXPLORATION STATUS"
        self.refresh_status()


class DungeonMessageLog(RichLog):
    """Scrollback log for map actions."""

    can_focus = True

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
