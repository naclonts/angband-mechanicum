"""Prompt input -- free-text command entry."""

from __future__ import annotations

from typing import Any

from textual.widgets import Input

_PLACEHOLDER_DEFAULT: str = "Enter command, Tech-Priest..."
_PLACEHOLDER_LOADING: str = "++ AWAITING MACHINE SPIRIT RESPONSE ++"


class PromptInput(Input):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(placeholder=_PLACEHOLDER_DEFAULT, **kwargs)

    def set_processing(self, processing: bool) -> None:
        """Toggle the input between processing and ready states."""
        self.disabled = processing
        self.placeholder = _PLACEHOLDER_LOADING if processing else _PLACEHOLDER_DEFAULT
