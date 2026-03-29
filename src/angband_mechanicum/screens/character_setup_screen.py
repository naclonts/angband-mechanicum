"""Character setup screen -- name your Tech-Priest before starting a new game."""

from __future__ import annotations

import random

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from angband_mechanicum.screens import ARROW_NAV_BINDINGS

HEADER_ART: str = """\
 +============================================================+
 |     ++ TECH-PRIEST DESIGNATION PROTOCOL ++                  |
 |                                                             |
 |     The Fabricator-Locum requires formal identification     |
 |     before expedition clearance is granted.                 |
 |                                                             |
 |     State your designation, Magos.                          |
 +============================================================+"""

FOOTER_TEXT: str = (
    "[dim]++ DESIGNATION IS IDENTITY ++ IDENTITY IS PURPOSE "
    "++ THE OMNISSIAH KNOWS ALL NAMES ++[/dim]"
)

NAME_SUGGESTIONS: list[str] = [
    "Magos Vex-9",
    "Artisan Kael-Omega",
    "Logis Theron-4",
    "Magos Dravek-XI",
    "Explorator Syn-Rho",
    "Genetor Halex-3",
    "Magos Corvane-VII",
    "Logis Nyx-Theta",
]

DEFAULT_NAME: str = "Magos Explorator"


class CharacterSetupScreen(Screen[str]):
    """Screen for the player to enter their Tech-Priest's name.

    Dismissed with the chosen name string.
    """

    BINDINGS = [*ARROW_NAV_BINDINGS]

    def compose(self) -> ComposeResult:
        # Pick 3 random suggestions to show
        suggestions = random.sample(NAME_SUGGESTIONS, min(3, len(NAME_SUGGESTIONS)))

        with Center():
            with Vertical(id="charsetup-container"):
                yield Static(HEADER_ART, id="charsetup-header")
                yield Static(
                    "[dim]Enter your designation or select one below.[/dim]",
                    id="charsetup-instructions",
                )
                yield Input(
                    placeholder=DEFAULT_NAME,
                    id="charsetup-input",
                )
                yield Button(
                    "++ CONFIRM DESIGNATION ++",
                    id="btn-confirm",
                    variant="primary",
                )
                yield Label("[bold]++ SUGGESTED DESIGNATIONS ++[/bold]", id="charsetup-suggestions-label")
                for i, name in enumerate(suggestions):
                    yield Button(
                        name,
                        id=f"btn-suggest-{i}",
                        variant="default",
                        classes="suggest-entry",
                    )
                yield Static(FOOTER_TEXT, id="charsetup-footer")

    def on_mount(self) -> None:
        self.query_one("#charsetup-header").border_title = "++ DESIGNATION PROTOCOL ++"
        self.query_one("#charsetup-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self._confirm_name()
        elif event.button.id and event.button.id.startswith("btn-suggest-"):
            # Use the suggestion button's label as the name
            name = str(event.button.label)
            self.query_one("#charsetup-input", Input).value = name
            self._confirm_name(name)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Allow pressing Enter in the input to confirm."""
        self._confirm_name()

    def _confirm_name(self, override: str | None = None) -> None:
        """Dismiss the screen with the chosen name."""
        if override:
            name = override.strip()
        else:
            name = self.query_one("#charsetup-input", Input).value.strip()
        if not name:
            name = DEFAULT_NAME
        self.dismiss(name)
