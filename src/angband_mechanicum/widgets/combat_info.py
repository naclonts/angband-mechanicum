"""Combat info widget -- displays unit stats and phase information."""

from __future__ import annotations

from textual.widgets import Static

from angband_mechanicum.engine.combat_engine import (
    CombatEngine,
    CombatPhase,
    UnitTeam,
)


def _hp_bar(hp: int, max_hp: int, width: int = 10) -> str:
    """Render a text HP bar like [====------]."""
    filled = round(hp / max_hp * width) if max_hp > 0 else 0
    return "[" + "=" * filled + "-" * (width - filled) + "]"


def render_combat_info(engine: CombatEngine) -> str:
    """Build the info text for the combat sidebar."""
    player = engine.get_player()
    lines: list[str] = []

    # Phase
    phase_labels: dict[CombatPhase, str] = {
        CombatPhase.PLAYER_TURN: "[bold]YOUR TURN[/bold]",
        CombatPhase.ENEMY_TURN: "[dim]ENEMY TURN[/dim]",
        CombatPhase.VICTORY: "[bold]VICTORY[/bold]",
        CombatPhase.DEFEAT: "[bold red]DEFEAT[/bold red]",
    }
    lines.append(f"PHASE: {phase_labels.get(engine.phase, '?')}")
    lines.append(f"TURN:  {engine.turn}")
    lines.append(f"MAP:   {engine.map_name}")
    lines.append("")

    # Player stats
    lines.append("[bold]-- MAGOS EXPLORATOR --[/bold]")
    lines.append(f"HP:    {_hp_bar(player.stats.hp, player.stats.max_hp)} {player.stats.hp}/{player.stats.max_hp}")
    lines.append(f"ATK:   {player.stats.attack}  ARM: {player.stats.armor}")
    lines.append(f"MOVE:  {player.stats.movement}  RNG: {player.stats.attack_range}")
    lines.append(f"POS:   ({player.x},{player.y})")

    status_parts: list[str] = []
    if player.has_moved:
        status_parts.append("moved")
    if player.has_attacked:
        status_parts.append("attacked")
    if status_parts:
        lines.append(f"DONE:  {', '.join(status_parts)}")
    lines.append("")

    # Enemies
    enemies = engine.get_alive_units(UnitTeam.ENEMY)
    lines.append(f"[bold]-- HOSTILES ({len(enemies)}) --[/bold]")
    for e in enemies:
        dist = abs(e.x - player.x) + abs(e.y - player.y)
        lines.append(f"  {e.symbol} {e.name}")
        lines.append(f"    HP: {_hp_bar(e.stats.hp, e.stats.max_hp)} {e.stats.hp}/{e.stats.max_hp}  dist:{dist}")
    if not enemies:
        lines.append("  [dim]None remaining[/dim]")

    lines.append("")

    # Cursor
    cx, cy = engine.cursor
    lines.append(f"CURSOR: ({cx},{cy})")
    unit_at = engine.get_unit_at(cx, cy)
    if unit_at:
        lines.append(f"  -> {unit_at.name} ({unit_at.team.value})")

    # Commands help
    lines.append("")
    lines.append("[dim]-- COMMANDS --[/dim]")
    lines.append("[dim]Arrow keys: move cursor[/dim]")
    lines.append("[dim]m: move to cursor[/dim]")
    lines.append("[dim]a: attack at cursor[/dim]")
    lines.append("[dim]e: end turn[/dim]")
    lines.append("[dim]q: retreat (forfeit)[/dim]")

    return "\n".join(lines)


class CombatInfo(Static):
    """Sidebar displaying combat state and unit info."""

    def __init__(self, engine: CombatEngine, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._engine: CombatEngine = engine

    def refresh_info(self) -> None:
        """Re-render from current engine state."""
        self.update(render_combat_info(self._engine))

    def on_mount(self) -> None:
        self.border_title = "⛨ TACTICAL STATUS"
        self.refresh_info()
