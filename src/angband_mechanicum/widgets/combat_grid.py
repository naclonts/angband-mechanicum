"""Combat grid widget -- renders the tactical map with units and cursor."""

from __future__ import annotations

import re

from textual.widgets import Static

from angband_mechanicum.engine.combat_engine import (
    CombatEngine,
    CombatUnit,
    Terrain,
    UnitTeam,
)

# Terrain rendering glyphs
_TERRAIN_CHARS: dict[Terrain, str] = {
    Terrain.FLOOR: "·",
    Terrain.WALL: "█",
    Terrain.DEBRIS: "░",
    Terrain.TERMINAL: "▪",
}

# Regex to strip all Rich markup tags from a string.
_MARKUP_RE = re.compile(r"\[/?[^\]]*\]")


def _strip_markup(text: str) -> str:
    """Remove all Rich markup tags from *text*."""
    return _MARKUP_RE.sub("", text)


def render_grid(engine: CombatEngine) -> str:
    """Render the tactical grid as a Unicode string.

    Layout:
    - Top/bottom border with box-drawing
    - Terrain tiles with unit symbols overlaid
    - Cursor marked with brackets: [X]
    - Column/row numbers for reference
    - The currently selected party member is shown with an underline
      indicator so the player always knows who they are controlling.
    """
    grid = engine.grid
    cx, cy = engine.cursor
    active_id = engine.active_unit_id
    units_by_pos: dict[tuple[int, int], CombatUnit] = {}
    for u in engine.get_units():
        if u.alive:
            units_by_pos[(u.x, u.y)] = u

    lines: list[str] = []

    # Column header (tens digit only shown if >= 10)
    col_header = "   "
    for x in range(grid.width):
        if x % 5 == 0:
            col_header += f"{x:<3d}"[0]
        else:
            col_header += " "
    lines.append(col_header)

    # Top border
    lines.append("  ╔" + "═" * grid.width + "╗")

    for y in range(grid.height):
        row_str = f"{y:2d}║"
        for x in range(grid.width):
            unit = units_by_pos.get((x, y))
            is_cursor = (x == cx and y == cy)

            if unit is not None:
                if unit.team == UnitTeam.PLAYER:
                    char = unit.symbol
                else:
                    char = unit.symbol
            else:
                tile = grid.get_tile(x, y)
                char = _TERRAIN_CHARS.get(tile.terrain, "?")

            row_str += char

        row_str += "║"
        lines.append(row_str)

    # Bottom border
    lines.append("  ╚" + "═" * grid.width + "╝")

    # Now overlay the cursor using Rich markup
    # We rebuild with markup: the cursor cell gets highlighted
    # Re-render with Rich markup for cursor highlighting
    marked_lines: list[str] = []
    marked_lines.append(col_header)
    marked_lines.append("  ╔" + "═" * grid.width + "╗")

    for y in range(grid.height):
        row_parts: list[str] = [f"{y:2d}║"]
        for x in range(grid.width):
            unit = units_by_pos.get((x, y))
            is_cursor = (x == cx and y == cy)

            if unit is not None:
                if unit.team == UnitTeam.PLAYER:
                    if unit.unit_id == active_id:
                        # Selected unit: bold + underline to distinguish
                        char = f"[bold underline]{unit.symbol}[/bold underline]"
                    else:
                        char = f"[bold]{unit.symbol}[/bold]"
                else:
                    char = f"[bold red]{unit.symbol}[/bold red]"
            else:
                tile = grid.get_tile(x, y)
                raw = _TERRAIN_CHARS.get(tile.terrain, "?")
                if tile.terrain == Terrain.WALL:
                    char = f"[dim]{raw}[/dim]"
                elif tile.terrain == Terrain.DEBRIS:
                    char = f"[dim]{raw}[/dim]"
                elif tile.terrain == Terrain.TERMINAL:
                    char = f"[bold]{raw}[/bold]"
                else:
                    char = f"[dim]{raw}[/dim]"

            if is_cursor:
                # Highlight cursor position.  Preserve underline for the
                # selected unit so the indicator remains visible even when
                # the cursor sits on the active party member.
                raw_char = _strip_markup(char)
                is_selected = (
                    unit is not None
                    and unit.team == UnitTeam.PLAYER
                    and unit.unit_id == active_id
                )
                if is_selected:
                    char = f"[reverse underline]{raw_char}[/reverse underline]"
                else:
                    char = f"[reverse]{raw_char}[/reverse]"

            row_parts.append(char)
        row_parts.append("║")
        marked_lines.append("".join(row_parts))

    marked_lines.append("  ╚" + "═" * grid.width + "╝")

    return "\n".join(marked_lines)


class CombatGrid(Static):
    """Widget that renders the tactical combat grid."""

    can_focus = True  # Grid should hold focus so arrow keys reach screen bindings

    def __init__(self, engine: CombatEngine, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._engine: CombatEngine = engine

    def refresh_grid(self) -> None:
        """Re-render the grid from current engine state."""
        self.update(render_grid(self._engine))

    def on_mount(self) -> None:
        self.refresh_grid()
