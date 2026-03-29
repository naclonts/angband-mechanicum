"""Story selection screen -- lets the player choose a starting scenario."""

from __future__ import annotations

import random
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from angband_mechanicum.engine.story_starts import STORY_STARTS, StoryStart
from angband_mechanicum.screens import ARROW_NAV_BINDINGS, MenuNavigationMixin


HEADER_ART: str = """\
╔═══════════════════════════════════════════════════════╗
║          ⛨  SELECT YOUR MISSION, TECH-PRIEST  ⛨      ║
║      ++ EXPLORATOR ASSIGNMENT TERMINAL ++             ║
╚═══════════════════════════════════════════════════════╝"""

FOOTER_TEXT: str = (
    "[dim]++ SELECT A MISSION OR PRESS R FOR RANDOM ASSIGNMENT "
    "++ THE OMNISSIAH GUIDES YOUR HAND ++[/dim]"
)


class StorySelectScreen(MenuNavigationMixin, Screen[StoryStart | None]):
    """Screen for selecting a story starting scenario.

    Dismisses with the chosen :class:`StoryStart`, or ``None`` if the
    player backs out (currently not wired — always selects something).
    """

    BINDINGS = [
        *ARROW_NAV_BINDINGS,
        Binding("r", "random_select", "Random", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="story-select-container"):
                yield Static(HEADER_ART, id="story-header")
                yield Button(
                    "++ RANDOM ASSIGNMENT ++",
                    id="btn-random",
                    variant="primary",
                )
                with VerticalScroll(id="story-list"):
                    for start in STORY_STARTS:
                        yield Button(
                            f"{start.title}\n[dim]{start.description}[/dim]",
                            id=f"story-{start.id}",
                            classes="story-entry",
                        )
                yield Static(FOOTER_TEXT, id="story-footer")

    def on_mount(self) -> None:
        self.focus_default_menu_control()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-random":
            self.dismiss(random.choice(STORY_STARTS))
        elif event.button.id and event.button.id.startswith("story-"):
            story_id = event.button.id.removeprefix("story-")
            for start in STORY_STARTS:
                if start.id == story_id:
                    self.dismiss(start)
                    return

    def action_random_select(self) -> None:
        """Select a random scenario."""
        self.dismiss(random.choice(STORY_STARTS))

    def action_back(self) -> None:
        """Go back to the menu without selecting."""
        self.dismiss(None)
