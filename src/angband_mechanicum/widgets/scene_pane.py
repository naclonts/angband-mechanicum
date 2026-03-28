"""Scene pane -- displays ASCII art of the current environment."""

from __future__ import annotations

from textual.widgets import Static


class ScenePane(Static):
    def update_scene(self, art: str) -> None:
        self.update(art)

    @property
    def content_width(self) -> int:
        """Return the usable width inside the pane (excluding border + padding)."""
        region = self.content_region
        return region.width if region.width > 0 else 56

    @property
    def content_height(self) -> int:
        """Return the usable height inside the pane (excluding border + padding)."""
        region = self.content_region
        return region.height if region.height > 0 else 16
