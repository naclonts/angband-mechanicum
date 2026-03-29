"""Hall of the Dead screen -- persistent memorial list for fallen Tech-Priests."""

from __future__ import annotations

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from angband_mechanicum.engine.save_manager import DeathRecord, SaveManager
from angband_mechanicum.screens import ARROW_NAV_BINDINGS, MenuNavigationMixin


class HallOfDeadScreen(MenuNavigationMixin, Screen[None]):
    """Display the persistent death records from fallen runs."""

    BINDINGS = [
        *ARROW_NAV_BINDINGS,
        Binding("escape", "back", "Back", show=True),
        Binding("h", "back", "Back", show=False),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._save_manager: SaveManager = SaveManager()

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="hall-container"):
                yield Static("⛨ HALL OF THE DEAD ⛨", id="hall-title")
                yield Static(
                    "[dim]Memorial records of fallen Tech-Priests are etched here.[/dim]",
                    id="hall-subtitle",
                )
                with VerticalScroll(id="hall-records"):
                    yield Static("", id="hall-empty")
                yield Button("++ RETURN TO MENU ++", id="btn-back", variant="primary")

    def on_mount(self) -> None:
        self.title = "HALL OF THE DEAD"
        self._refresh_records()
        self.focus_default_menu_control()

    def _refresh_records(self) -> None:
        records_container = self.query_one("#hall-records", VerticalScroll)
        records_container.remove_children()
        records = self._save_manager.list_death_records()
        if not records:
            records_container.mount(
                Static("[dim]No fallen Tech-Priests are recorded yet.[/dim]", id="hall-empty")
            )
            return
        for record in records:
            records_container.mount(
                Static(Text.from_markup(self._format_record(record)), classes="hall-record")
            )

    def _format_record(self, record: DeathRecord) -> str:
        """Render a memorial card for a single fallen Tech-Priest."""
        lines = [
            f"[bold]{escape(record.player_name)}[/bold]  [dim]{escape(record.display_time)}[/dim]",
            f"[bold]{escape(record.location)}[/bold]",
            (
                f"Turns survived: [bold]{record.turns_survived}[/bold]  "
                f"Enemies slain: [bold]{record.enemies_slain}[/bold]  "
                f"Deepest level: [bold]{record.deepest_level_reached}[/bold]"
            ),
            f"Cause: [italic]{escape(record.cause_of_death)}[/italic]",
            escape(record.summary),
        ]
        if record.save_slot_id:
            lines.insert(2, f"[dim]Save slot: {escape(record.save_slot_id)}[/dim]")
        return "\n".join(lines)

    def action_back(self) -> None:
        self.app.return_to_menu_view()  # type: ignore[attr-defined]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
