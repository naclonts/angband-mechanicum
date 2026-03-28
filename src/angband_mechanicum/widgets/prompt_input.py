"""Prompt input -- free-text command entry."""

from __future__ import annotations

from typing import Any

from textual.widgets import Input

_PLACEHOLDER_DEFAULT: str = "Enter command, Tech-Priest..."
_PLACEHOLDER_LOADING: str = "++ AWAITING MACHINE SPIRIT RESPONSE ++"


class PromptInput(Input):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(placeholder=_PLACEHOLDER_DEFAULT, **kwargs)
        self._processing: bool = False

    @property
    def is_processing(self) -> bool:
        """Whether the engine is currently processing a command."""
        return self._processing

    def set_processing(self, processing: bool) -> None:
        """Toggle the input between processing and ready states.

        Uses read-only mode instead of disabling so the widget stays
        in the focus chain and tab navigation continues to work.
        """
        self._processing = processing
        self.placeholder = _PLACEHOLDER_LOADING if processing else _PLACEHOLDER_DEFAULT
        if processing:
            self.add_class("-processing")
        else:
            self.remove_class("-processing")
