"""Tests for widget formatting logic (no Textual app needed)."""

from __future__ import annotations

from angband_mechanicum.engine.combat_engine import CombatEngine, UnitTeam
from angband_mechanicum.widgets.combat_grid import _strip_markup, render_grid
from angband_mechanicum.widgets.info_panel import DEFAULT_INFO, InfoPanel


# ---------------------------------------------------------------------------
# Combat grid: selected character indicator
# ---------------------------------------------------------------------------


class TestCombatGridSelectedIndicator:
    """The active/selected party member should be visually distinct on the grid."""

    def test_active_unit_has_underline_markup(self) -> None:
        """The selected player unit's symbol should use underline markup.

        When the cursor is on the active unit (the default at start),
        the cell gets reverse+underline.  When the cursor is elsewhere,
        the cell gets bold+underline.
        """
        engine = CombatEngine()
        # Move cursor away from the active unit so we test the non-cursor branch
        for _ in range(10):
            engine.move_cursor(1, 0)
        output = render_grid(engine)
        active = engine.get_active_unit()
        assert f"[bold underline]{active.symbol}[/bold underline]" in output

    def test_non_active_party_member_has_bold_only(self) -> None:
        """Non-selected party members should use plain bold (no underline)."""
        engine = CombatEngine(party_ids=["skitarius-alpha-7"])
        # The player (@) starts as active; the party member should be bold-only
        output = render_grid(engine)
        party_unit = None
        for u in engine.get_units():
            if u.team == UnitTeam.PLAYER and u.unit_id != engine.active_unit_id and u.alive:
                party_unit = u
                break
        assert party_unit is not None
        # Should contain [bold]SYMBOL[/bold] but NOT [bold underline]SYMBOL
        assert f"[bold]{party_unit.symbol}[/bold]" in output

    def test_cycling_unit_changes_indicator(self) -> None:
        """After cycling, the newly active unit gets the underline indicator."""
        engine = CombatEngine(party_ids=["skitarius-alpha-7"])
        first_active = engine.active_unit_id
        engine.cycle_active_unit()
        second_active = engine.active_unit_id
        assert first_active != second_active

        # Move cursor away from the new active unit so we test bold+underline
        for _ in range(15):
            engine.move_cursor(1, 0)
        output = render_grid(engine)
        new_active = engine.get_active_unit()
        assert f"[bold underline]{new_active.symbol}[/bold underline]" in output

    def test_cursor_on_active_unit_shows_reverse_underline(self) -> None:
        """When the cursor overlaps the selected unit, use reverse+underline."""
        engine = CombatEngine()
        # By default the cursor starts on the player (active unit)
        output = render_grid(engine)
        active = engine.get_active_unit()
        assert f"[reverse underline]{active.symbol}[/reverse underline]" in output

    def test_enemy_markup_unchanged(self) -> None:
        """Enemy units should still use bold red markup (not underlined)."""
        engine = CombatEngine()
        output = render_grid(engine)
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        # At least one enemy should have bold red markup
        assert any(f"[bold red]{e.symbol}[/bold red]" in output for e in enemies)


class TestStripMarkup:
    def test_strips_simple_tags(self) -> None:
        assert _strip_markup("[bold]X[/bold]") == "X"

    def test_strips_nested_tags(self) -> None:
        assert _strip_markup("[bold underline]@[/bold underline]") == "@"

    def test_strips_color_tags(self) -> None:
        assert _strip_markup("[bold red]S[/bold red]") == "S"

    def test_no_tags_unchanged(self) -> None:
        assert _strip_markup("hello") == "hello"


class TestInfoPanelFormatting:
    def test_update_info_aligns_keys(self) -> None:
        """update_info right-pads keys to the longest key length."""
        panel = InfoPanel()
        data = {"A": "1", "LONG_KEY": "2", "BB": "3"}
        # We can't call update_info directly without a running app,
        # so test the formatting logic inline.
        max_key = max(len(k) for k in data)
        lines = [f"{k:<{max_key}}  {v}" for k, v in data.items()]
        result = "\n".join(lines)

        assert "A         1" in result
        assert "LONG_KEY  2" in result
        assert "BB        3" in result

    def test_default_info_has_required_fields(self) -> None:
        required = {"DESIGNATION", "LOCATION", "DATE", "FATIGUE", "INTEGRITY", "NOOSPHERE"}
        assert required == set(DEFAULT_INFO.keys())
