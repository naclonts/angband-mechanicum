"""Scene pane — displays ASCII art of the current environment."""

from textual.widgets import Static


class ScenePane(Static):
    def update_scene(self, art: str) -> None:
        self.update(art)
