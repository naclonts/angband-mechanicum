"""Portrait pane -- displays ASCII art of the player character."""

from __future__ import annotations

from textual.widgets import Static


class PortraitPane(Static):
    def update_portrait(self, art: str) -> None:
        self.update(art)
