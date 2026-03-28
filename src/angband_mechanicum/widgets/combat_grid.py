"""Combat grid widget -- renders the tactical map with units and cursor."""

from __future__ import annotations

import re

from textual.widgets import Static

from angband_mechanicum.engine.combat_engine import (
    CombatEngine,
    CombatPhase,
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

# Extended terrain glyphs (added by dungeon_gen module if loaded)
def _extend_terrain_chars() -> None:
    """Add glyph mappings for terrain types from dungeon_gen, if available."""
    for name, char in [("COLUMN", "○"), ("WATER", "≈"), ("GROWTH", "♣"), ("COVER", "▬")]:
        member = getattr(Terrain, name, None)
        if member is not None and member not in _TERRAIN_CHARS:
            _TERRAIN_CHARS[member] = char

_extend_terrain_chars()

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
    - The currently selected party member is shown with a prominent
      background highlight (``on #1a3a1a``) so the player always knows
      which character they are controlling.  When the cursor overlaps
      the active unit the cell uses ``reverse`` instead.
    - When a unit is selected and hasn't moved yet, reachable floor
      tiles are highlighted with a subtle brighter green.
    """
    grid = engine.grid
    cx, cy = engine.cursor
    active_id = engine.active_unit_id
    units_by_pos: dict[tuple[int, int], CombatUnit] = {}
    for u in engine.get_units():
        if u.alive:
            units_by_pos[(u.x, u.y)] = u

    # Compute movement range overlay for the active unit
    reachable: set[tuple[int, int]] = set()
    if engine.phase == CombatPhase.PLAYER_TURN:
        active_unit = engine.get_active_unit()
        if active_unit.alive and not active_unit.has_moved:
            reachable = engine.get_reachable_tiles(active_unit)

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
                        # Selected unit: bright text on a dark-green
                        # background so the player always sees which
                        # character is active, even across the map.
                        char = f"[bold #00ff41 on #1a3a1a]{unit.symbol}[/bold #00ff41 on #1a3a1a]"
                    else:
                        char = f"[bold]{unit.symbol}[/bold]"
                else:
                    char = f"[bold red]{unit.symbol}[/bold red]"
            else:
                tile = grid.get_tile(x, y)
                raw = _TERRAIN_CHARS.get(tile.terrain, "?")
                in_range = (x, y) in reachable
                terrain_name = tile.terrain.name
                if tile.terrain == Terrain.WALL:
                    char = f"[dim]{raw}[/dim]"
                elif tile.terrain == Terrain.TERMINAL:
                    char = f"[bold]{raw}[/bold]"
                elif terrain_name == "COLUMN":
                    char = f"[bold]{raw}[/bold]"
                elif terrain_name == "WATER":
                    char = f"[blue]{raw}[/blue]" if not in_range else f"[#55cc55]{raw}[/#55cc55]"
                elif terrain_name == "GROWTH":
                    char = f"[green]{raw}[/green]" if not in_range else f"[#55cc55]{raw}[/#55cc55]"
                elif terrain_name == "COVER":
                    char = f"[dim]{raw}[/dim]" if not in_range else f"[#55cc55]{raw}[/#55cc55]"
                elif in_range:
                    # Subtle movement range highlight: brighter green
                    char = f"[#55cc55]{raw}[/#55cc55]"
                else:
                    char = f"[dim]{raw}[/dim]"

            if is_cursor:
                # Highlight cursor position.  When the cursor sits on the
                # active party member use ``reverse bold`` so the cell
                # stands out even more than a regular cursor cell.
                raw_char = _strip_markup(char)
                is_selected = (
                    unit is not None
                    and unit.team == UnitTeam.PLAYER
                    and unit.unit_id == active_id
                )
                if is_selected:
                    char = f"[reverse bold]{raw_char}[/reverse bold]"
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
