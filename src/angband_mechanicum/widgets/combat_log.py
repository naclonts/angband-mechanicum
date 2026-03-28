"""Combat log widget -- scrolling action log for tactical combat."""

from __future__ import annotations

from textual.widgets import RichLog

from angband_mechanicum.engine.combat_engine import CombatEngine


class CombatLog(RichLog):
    """Scrollable log of combat actions and events."""

    def __init__(self, engine: CombatEngine, **kwargs: object) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=True, **kwargs)  # type: ignore[arg-type]
        self._engine: CombatEngine = engine
        self._displayed_count: int = 0

    def on_mount(self) -> None:
        self.border_title = "⛨ COMBAT LOG"
        self.sync_log()

    def sync_log(self) -> None:
        """Write any new log entries since last sync."""
        entries = self._engine.log
        new_entries = entries[self._displayed_count:]
        for entry in new_entries:
            self.write(f"[dim]T{entry.turn}>[/dim] {entry.text}")
        self._displayed_count = len(entries)
