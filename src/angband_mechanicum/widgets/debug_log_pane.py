"""Debug log pane for inspecting the live game state and raw log history."""

from __future__ import annotations

import json
from typing import Any

from textual.widgets import RichLog

_TITLE = "\u26e8 DEBUG LOGS"
_SUBTITLE = "F2 returns to play | PgUp/PgDn scroll"


def format_debug_snapshot(snapshot: dict[str, Any]) -> str:
    """Render a stable JSON dump for the in-game debug surface."""
    return json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True)


class DebugLogPane(RichLog):
    """Read-only view of the current game's structured debug data."""

    can_focus = True

    def __init__(self, **kwargs: object) -> None:
        super().__init__(markup=False, wrap=False, auto_scroll=False, **kwargs)  # type: ignore[arg-type]

    def on_mount(self) -> None:
        self.border_title = _TITLE
        self.border_subtitle = _SUBTITLE

    def show_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Replace the visible debug dump with a fresh snapshot."""
        self.clear()
        self.write(format_debug_snapshot(snapshot))
        self.scroll_home(animate=False)
