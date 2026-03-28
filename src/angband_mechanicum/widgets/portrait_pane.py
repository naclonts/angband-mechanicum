"""Portrait pane -- displays ASCII art of the player character or NPCs."""

from __future__ import annotations

from textual.widgets import Static


class PortraitPane(Static):
    def update_portrait(self, art: str) -> None:
        self.update(art)

    def set_border_title(self, title: str) -> None:
        """Update the pane's border title (e.g. NPC name or 'OPERATIVE')."""
        self.border_title = title
