"""Combat info widget -- displays unit stats and phase information."""

from __future__ import annotations

from textual.widgets import Static

from angband_mechanicum.engine.combat_engine import (
    CombatEngine,
    CombatPhase,
    CombatUnit,
    PowerType,
    UnitTeam,
    has_line_of_sight,
    manhattan_distance,
)


def _hp_bar(hp: int, max_hp: int, width: int = 10) -> str:
    """Render a text HP bar like [====------]."""
    filled = round(hp / max_hp * width) if max_hp > 0 else 0
    return "[" + "=" * filled + "-" * (width - filled) + "]"


def _render_unit_block(
    unit: CombatUnit,
    is_active: bool,
    reference_unit: CombatUnit | None = None,
) -> list[str]:
    """Render a stat block for a single player-team unit.

    ``reference_unit`` is used for distance calculations (enemies only).
    """
    lines: list[str] = []
    if not unit.alive:
        lines.append(f"[dim]{unit.symbol} {unit.name} -- DOWN[/dim]")
        return lines

    marker = " <<" if is_active else ""
    lines.append(f"[bold]{unit.symbol} {unit.name}{marker}[/bold]")
    lines.append(f"  HP:   {_hp_bar(unit.stats.hp, unit.stats.max_hp)} {unit.stats.hp}/{unit.stats.max_hp}")
    lines.append(f"  ATK:  {unit.stats.attack}  ARM: {unit.stats.armor}")
    lines.append(f"  MOVE: {unit.stats.movement}  RNG: {unit.stats.attack_range}")
    lines.append(f"  POS:  ({unit.x},{unit.y})")

    # Active buffs
    if unit.active_buffs:
        buff_strs = [
            f"+{b.amount}{b.stat[0:3]}({b.remaining_turns}t)"
            for b in unit.active_buffs
        ]
        lines.append(f"  BUFF: {' '.join(buff_strs)}")

    status_parts: list[str] = []
    if unit.has_moved:
        status_parts.append("moved")
    if unit.has_attacked:
        status_parts.append("attacked")
    if unit.has_used_power:
        status_parts.append("power")
    if status_parts:
        lines.append(f"  DONE: {', '.join(status_parts)}")

    # Powers
    if unit.powers:
        for p in unit.powers:
            cd = unit.power_cooldowns.get(p.name)
            if cd:
                lines.append(f"  [dim]  {p.name} (CD:{cd}t)[/dim]")
            else:
                type_tag = {"offensive": "DMG", "healing": "HEAL", "buff": "BUFF"}[p.power_type.value]
                lines.append(f"    {p.name} [{type_tag}:{p.amount} R:{p.range}]")
    return lines


def render_combat_info(engine: CombatEngine) -> str:
    """Build the info text for the combat sidebar."""
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

    # Single-character focus: show the player Tech-Priest first and foremost.
    player = engine.get_player()
    lines.append("[bold]-- PLAYER --[/bold]")
    lines.extend(_render_unit_block(player, True))
    lines.append("")

    companions = [
        engine._units[uid]
        for uid in engine.player_unit_ids
        if uid != "player"
    ]
    if companions:
        lines.append(f"[bold]-- COMPANIONS ({len(companions)}) --[/bold]")
        for unit in companions:
            lines.extend(_render_unit_block(unit, False))
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
        # Show targeting info for enemy at cursor relative to active unit
        if unit_at.team == UnitTeam.ENEMY:
            active = engine.get_active_unit()
            if active.alive:
                dist = manhattan_distance(active.x, active.y, unit_at.x, unit_at.y)
                rng = active.stats.attack_range
                in_range = dist <= rng
                los = has_line_of_sight(
                    engine.grid, active.x, active.y, unit_at.x, unit_at.y
                )
                range_str = (
                    f"[bold]IN RANGE[/bold]" if in_range
                    else f"[dim]OUT OF RANGE[/dim]"
                )
                los_str = (
                    "[bold]CLEAR[/bold]" if los
                    else "[dim]BLOCKED[/dim]"
                )
                lines.append(f"  DIST: {dist}  RNG: {rng}  {range_str}")
                lines.append(f"  LoS: {los_str}")
                if in_range and (dist <= 1 or los):
                    lines.append("  [bold]>> PRESS 'a' TO ATTACK <<[/bold]")
                elif in_range and not los:
                    lines.append("  [dim]No line of sight[/dim]")

    # Commands help
    lines.append("")
    lines.append("[dim]-- COMMANDS --[/dim]")
    lines.append("[dim]Arrow keys: move cursor[/dim]")
    lines.append("[dim]m: move to cursor[/dim]")
    lines.append("[dim]a/s: attack/shoot at cursor[/dim]")
    lines.append("[dim]p: cast power at cursor[/dim]")
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
