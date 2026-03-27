"""Prompt input — free-text command entry."""

from textual.widgets import Input


class PromptInput(Input):
    def __init__(self, **kwargs) -> None:
        super().__init__(placeholder="Enter command, Tech-Priest...", **kwargs)
