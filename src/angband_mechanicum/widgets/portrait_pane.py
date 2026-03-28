"""Portrait pane -- displays ASCII art of the player character or NPCs."""

from __future__ import annotations

from textual.widgets import Static

from angband_mechanicum.assets.portraits import get_portrait


class PortraitPane(Static):
    def update_portrait(self, art: str) -> None:
        self.update(art)

    def set_portrait_by_id(self, portrait_id: str) -> None:
        """Load and display a portrait by its id from the portraits catalog."""
        art = get_portrait(portrait_id)
        self.update(art)

    def set_border_title(self, title: str) -> None:
        """Update the pane's border title (e.g. NPC name or 'OPERATIVE')."""
        self.border_title = title
