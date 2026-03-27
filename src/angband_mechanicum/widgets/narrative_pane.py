"""Narrative pane — scrolling game text log."""

from textual.widgets import RichLog


class NarrativePane(RichLog):
    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=True, **kwargs)

    def append_narrative(self, text: str) -> None:
        self.write(text)
