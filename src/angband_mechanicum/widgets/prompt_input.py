"""Prompt input -- free-text command entry."""

from __future__ import annotations

from typing import Any

from textual.widgets import Input


class PromptInput(Input):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(placeholder="Enter command, Tech-Priest...", **kwargs)
