"""Help overlay -- modal screen showing context-appropriate hotkeys."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpOverlay(ModalScreen[None]):
    """A modal overlay that displays a list of hotkeys.

    Accepts a title and a list of (key, description) pairs.
    Dismisses on Escape, Enter, or h.
    """

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=False),
        Binding("enter", "dismiss_help", "Close", show=False),
        Binding("h", "dismiss_help", "Close", show=False),
    ]

    def __init__(
        self,
        title: str,
        hotkeys: list[tuple[str, str]],
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._title = title
        self._hotkeys = hotkeys

    def compose(self) -> ComposeResult:
        # Build the key listing with Rich markup
        lines: list[str] = []
        lines.append(f"[bold]{self._title}[/bold]")
        lines.append("")
        for key, desc in self._hotkeys:
            lines.append(f"  [bold]{key:<14}[/bold] {desc}")
        lines.append("")
        lines.append("[dim]Press ESC / Enter / h to close[/dim]")
        content = "\n".join(lines)

        with Center():
            with Vertical(id="help-panel"):
                yield Static(content, id="help-content")

    def action_dismiss_help(self) -> None:
        self.dismiss(None)
