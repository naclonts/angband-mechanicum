"""Combat screen -- full-screen tactical combat mode.

Pushed on top of GameScreen when combat starts, popped when it ends.
Returns a CombatResult to the caller.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from angband_mechanicum.engine.combat_engine import (
    CombatEngine,
    CombatPhase,
    CombatResult,
    EnemyRecord,
    PowerType,
    UnitTeam,
)
from angband_mechanicum.widgets.combat_grid import CombatGrid
from angband_mechanicum.widgets.combat_info import CombatInfo
from angband_mechanicum.widgets.combat_log import CombatLog
from angband_mechanicum.widgets.help_overlay import HelpOverlay


class CombatScreen(Screen[CombatResult]):
    """Tactical combat screen.

    The screen is parameterised on CombatResult -- when combat ends,
    the screen is dismissed with a result that the caller can handle.
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Cursor up", show=False),
        Binding("down", "cursor_down", "Cursor down", show=False),
        Binding("left", "cursor_left", "Cursor left", show=False),
        Binding("right", "cursor_right", "Cursor right", show=False),
        Binding("m", "move_unit", "Move to cursor", show=True),
        Binding("a", "attack_target", "Attack/Shoot", show=True),
        Binding("s", "attack_target", "Shoot (alias)", show=False),
        Binding("p", "cast_power", "Cast power", show=True),
        Binding("e", "end_turn", "End turn", show=True),
        Binding("q", "retreat", "Retreat", show=True),
        Binding("h", "show_help", "Help", show=True),
    ]

    COMBAT_HOTKEYS: list[tuple[str, str]] = [
        ("Arrow keys", "Move cursor"),
        ("m", "Move to cursor"),
        ("a / s", "Attack/Shoot at cursor"),
        ("p", "Cast power at cursor"),
        ("e", "End turn"),
        ("q", "Retreat"),
        ("h", "This help"),
    ]

    def __init__(
        self,
        map_key: str = "corridor",
        player_hp: int | None = None,
        player_max_hp: int | None = None,
        party_ids: list[str] | None = None,
        enemy_roster: list[tuple[str, int, int]] | None = None,
        map_def: dict | None = None,
        player_name: str = "Magos Explorator",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._engine: CombatEngine = CombatEngine(
            map_key=map_key,
            player_hp=player_hp,
            player_max_hp=player_max_hp,
            party_ids=party_ids,
            enemy_roster=enemy_roster,
            map_def=map_def,
            player_name=player_name,
        )

    @property
    def engine(self) -> CombatEngine:
        return self._engine

    def compose(self) -> ComposeResult:
        with Horizontal(id="combat-layout"):
            with Vertical(id="combat-left"):
                yield CombatGrid(self._engine, id="combat-grid")
                yield CombatLog(self._engine, id="combat-log")
            yield CombatInfo(self._engine, id="combat-info")

    def on_mount(self) -> None:
        self.title = f"TACTICAL: {self._engine.map_name.upper()}"
        self.query_one("#combat-grid", CombatGrid).focus()

    # -- Refresh helpers -----------------------------------------------------

    def _refresh_all(self) -> None:
        """Update all combat widgets from current engine state."""
        self.query_one("#combat-grid", CombatGrid).refresh_grid()
        self.query_one("#combat-info", CombatInfo).refresh_info()
        self.query_one("#combat-log", CombatLog).sync_log()
        self._check_combat_end()

    def _check_combat_end(self) -> None:
        """If combat is over, dismiss the screen with a result after a beat."""
        if self._engine.is_over:
            # Let the player see the result before dismissing
            self.set_timer(1.5, self._dismiss_with_result)

    def _dismiss_with_result(self) -> None:
        """Dismiss the screen with the combat result."""
        result = self._engine.get_result()
        self.dismiss(result)

    # -- Help overlay --------------------------------------------------------

    def action_show_help(self) -> None:
        """Push the help overlay with combat-specific hotkeys."""
        self.app.push_screen(
            HelpOverlay(
                title="++ COMBAT HOTKEYS ++",
                hotkeys=self.COMBAT_HOTKEYS,
            )
        )

    # -- Cursor movement -----------------------------------------------------

    def action_cursor_up(self) -> None:
        self._engine.move_cursor(0, -1)
        self._refresh_all()

    def action_cursor_down(self) -> None:
        self._engine.move_cursor(0, 1)
        self._refresh_all()

    def action_cursor_left(self) -> None:
        self._engine.move_cursor(-1, 0)
        self._refresh_all()

    def action_cursor_right(self) -> None:
        self._engine.move_cursor(1, 0)
        self._refresh_all()

    # -- Player actions ------------------------------------------------------

    def action_move_unit(self) -> None:
        """Move the active player unit to the cursor position."""
        if self._engine.phase != CombatPhase.PLAYER_TURN:
            return
        cx, cy = self._engine.cursor
        self._engine.player_move(cx, cy)
        self._refresh_all()

    def action_attack_target(self) -> None:
        """Attack the unit at the cursor position with the active unit.

        Works for both melee and ranged attacks -- the engine handles
        range and line-of-sight validation, providing appropriate log
        feedback if the shot is blocked or the target is out of range.
        """
        if self._engine.phase != CombatPhase.PLAYER_TURN:
            return
        cx, cy = self._engine.cursor
        target = self._engine.get_unit_at(cx, cy)
        if target and target.team == UnitTeam.ENEMY:
            self._engine.player_attack(target.unit_id)
        self._refresh_all()

    def action_cast_power(self) -> None:
        """Cast the first available power on the unit/cursor target.

        The active unit's first off-cooldown power is selected automatically.
        If the cursor is over an enemy, offensive powers are used.
        If the cursor is over an ally (or self), healing/buff powers are used.
        """
        if self._engine.phase != CombatPhase.PLAYER_TURN:
            return
        unit = self._engine.get_active_unit()
        available = self._engine.get_available_powers(unit)
        if not available:
            self._engine._add_log(f"{unit.name} has no powers available.")
            self._refresh_all()
            return
        if unit.has_used_power:
            self._engine._add_log(f"{unit.name} already used a power this turn.")
            self._refresh_all()
            return

        cx, cy = self._engine.cursor
        target = self._engine.get_unit_at(cx, cy)

        # Determine which power to use based on target
        power_to_use = None
        target_id = None

        if target and target.team == UnitTeam.ENEMY:
            # Look for an offensive power
            for p in available:
                if p.power_type == PowerType.OFFENSIVE:
                    power_to_use = p
                    target_id = target.unit_id
                    break
        elif target and target.team == UnitTeam.PLAYER:
            # Look for a healing or buff power
            for p in available:
                if p.power_type in (PowerType.HEALING, PowerType.BUFF):
                    power_to_use = p
                    target_id = target.unit_id
                    break
        else:
            # No unit at cursor -- try self-targeting healing/buff
            for p in available:
                if p.power_type in (PowerType.HEALING, PowerType.BUFF):
                    power_to_use = p
                    target_id = unit.unit_id
                    break

        if power_to_use is None:
            self._engine._add_log(
                f"No suitable power for this target. "
                f"Available: {', '.join(p.name for p in available)}"
            )
            self._refresh_all()
            return

        self._engine.player_cast_power(power_to_use.name, target_id)
        self._refresh_all()

    def action_end_turn(self) -> None:
        """End the player's turn."""
        if self._engine.phase != CombatPhase.PLAYER_TURN:
            return
        self._engine.end_player_turn()
        self._refresh_all()

    def action_retreat(self) -> None:
        """Forfeit the combat and dismiss."""
        units = self._engine.get_units()
        enemy_records = [
            EnemyRecord(
                name=u.name,
                template_key=u.template_key,
                defeated=not u.alive,
                max_hp=u.stats.max_hp,
                damage_dealt=u.total_damage_dealt,
            )
            for u in units
            if u.team == UnitTeam.ENEMY
        ]
        total_enemy_damage = sum(
            u.total_damage_dealt for u in units if u.team == UnitTeam.ENEMY
        )
        result = CombatResult(
            victory=False,
            player_hp_remaining=self._engine.get_player().stats.hp,
            player_hp_max=self._engine.get_player().stats.max_hp,
            enemies_defeated=sum(
                1 for u in units
                if u.team == UnitTeam.ENEMY and not u.alive
            ),
            enemies_total=self._engine._total_enemies,
            turn_count=self._engine.turn,
            log_summary="Tech-Priest retreated from combat.",
            enemies=enemy_records,
            total_player_damage_taken=total_enemy_damage,
        )
        self.dismiss(result)
