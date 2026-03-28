"""Narrative pane -- scrolling game text log with scroll indicator."""

from __future__ import annotations

from textual.binding import Binding
from textual.timer import Timer
from textual.widgets import RichLog

_TITLE_DEFAULT: str = "\u26e8 DATALOG"
_TITLE_MORE: str = "\u25b2 more \u2502 \u26e8 DATALOG"

_LOADING_FRAMES: list[str] = [
    "++ COMMUNING WITH THE MACHINE SPIRIT .   ++",
    "++ COMMUNING WITH THE MACHINE SPIRIT ..  ++",
    "++ COMMUNING WITH THE MACHINE SPIRIT ... ++",
    "++ COMMUNING WITH THE MACHINE SPIRIT ..  ++",
]


class NarrativePane(RichLog):
    """Scrollable datalog that shows a visual indicator when content is above."""

    BINDINGS = [
        Binding("escape", "return_focus", "Back to prompt", show=False),
    ]

    can_focus = True

    def __init__(self, **kwargs: object) -> None:
        super().__init__(markup=True, wrap=True, auto_scroll=True, **kwargs)  # type: ignore[arg-type]
        self._user_scrolled: bool = False
        self._loading: bool = False
        self._loading_frame: int = 0
        self._loading_timer: Timer | None = None

    def on_mount(self) -> None:
        self.border_title = _TITLE_DEFAULT

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        """Track scroll position to update title indicator and auto-scroll."""
        super().watch_scroll_y(old_value, new_value)
        has_content_above = round(new_value) > 0
        self.border_title = _TITLE_MORE if has_content_above else _TITLE_DEFAULT

        # If the user scrolled away from the bottom, pause auto-scroll.
        # Re-enable when they reach the bottom again.
        at_bottom = self.is_vertical_scroll_end
        if at_bottom:
            self._user_scrolled = False
            self.auto_scroll = True
        elif round(new_value) < round(old_value):
            # Scrolled upward -- user is reviewing history.
            self._user_scrolled = True
            self.auto_scroll = False

    def append_narrative(self, text: str) -> None:
        """Write narrative text, respecting user scroll position."""
        self.write(text)

    def show_loading(self) -> None:
        """Display an animated loading indicator in the border subtitle."""
        self._loading = True
        self._loading_frame = 0
        self.border_subtitle = _LOADING_FRAMES[0]
        self._loading_timer = self.set_interval(
            0.4, self._tick_loading, pause=False
        )

    def hide_loading(self) -> None:
        """Remove the loading indicator from the border subtitle."""
        self._loading = False
        if self._loading_timer is not None:
            self._loading_timer.stop()
            self._loading_timer = None
        self.border_subtitle = ""

    def _tick_loading(self) -> None:
        """Advance the loading animation by one frame."""
        self._loading_frame = (self._loading_frame + 1) % len(_LOADING_FRAMES)
        self.border_subtitle = _LOADING_FRAMES[self._loading_frame]

    def action_return_focus(self) -> None:
        """Return focus to the prompt input."""
        prompt = self.screen.query_one("#prompt")
        prompt.focus()
