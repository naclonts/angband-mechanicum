"""Deprecated tactical combat screen.

The live game now routes hostile encounters through the unified dungeon map.
This screen is kept only as a compatibility shell for old imports and now
returns the player to the main menu instead of exposing tactical combat UI.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static


class CombatScreen(Screen[None]):
    """Compatibility shell for the retired tactical combat surface."""

    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("h", "back", "Back", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="combat-retired-panel"):
                yield Static(
                    "++ TACTICAL COMBAT RETIRED ++\n"
                    "[dim]Hostile encounters now resolve through the dungeon map.[/dim]",
                    id="combat-retired-message",
                )
                yield Button("++ RETURN TO MENU ++", id="btn-back", variant="primary")

    def action_back(self) -> None:
        self.app.return_to_menu_view()  # type: ignore[attr-defined]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
