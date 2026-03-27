"""Menu screen — New Game / Load Game selection on launch."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from angband_mechanicum.engine.save_manager import SaveManager, SaveMetadata

TITLE_ART = """\
 ╔═══════════════════════════════════════════════════════════╗
 ║              ⛨  ANGBAND MECHANICUM  ⛨                    ║
 ║                                                          ║
 ║       ++ ADEPTUS MECHANICUS FIELD TERMINAL ++            ║
 ║       ++ FORGE WORLD: METALLICA SECUNDUS  ++             ║
 ║       ++ CLEARANCE: MAGOS EXPLORATOR      ++             ║
 ╚═══════════════════════════════════════════════════════════╝"""

FOOTER_TEXT = "[dim]++ THE OMNISSIAH PROTECTS ++ FLESH IS WEAK ++ THE MACHINE IS ETERNAL ++[/dim]"


class MenuScreen(Screen):
    """Main menu with New Game and Load Game options."""

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="menu-container"):
                yield Static(TITLE_ART, id="menu-title")
                yield Button("++ NEW GAME ++", id="btn-new", variant="primary")
                yield Button("++ LOAD GAME ++", id="btn-load", variant="default")
                yield Static(FOOTER_TEXT, id="menu-footer")
                yield Vertical(id="save-list")

    def on_mount(self) -> None:
        self.query_one("#menu-title").border_title = "⛨ TERMINAL"
        load_btn = self.query_one("#btn-load", Button)
        saves = SaveManager().list_saves()
        if not saves:
            load_btn.disabled = True
            load_btn.label = "++ LOAD GAME ++ [NO SAVES]"
        self._saves = saves

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new":
            self._start_new_game()
        elif event.button.id == "btn-load":
            self._show_save_list()
        elif event.button.id and event.button.id.startswith("save-"):
            slot_id = event.button.id.removeprefix("save-")
            self._load_game(slot_id)

    def _start_new_game(self) -> None:
        from angband_mechanicum.engine.game_engine import GameEngine
        from angband_mechanicum.screens.game_screen import GameScreen

        self.app.game_engine = GameEngine()
        self.app.save_slot = _generate_slot_id()
        self.app.switch_screen(GameScreen())

    def _show_save_list(self) -> None:
        save_list = self.query_one("#save-list", Vertical)
        save_list.remove_children()
        if not self._saves:
            return
        save_list.mount(Label("[bold]++ SELECT SESSION TO RESTORE ++[/bold]"))
        for save in self._saves:
            btn = Button(
                f"{save.display_time}  |  {save.location}  |  Turn {save.turn_count}",
                id=f"save-{save.slot_id}",
                variant="default",
                classes="save-entry",
            )
            save_list.mount(btn)

    def _load_game(self, slot_id: str) -> None:
        from angband_mechanicum.engine.game_engine import GameEngine
        from angband_mechanicum.screens.game_screen import GameScreen

        manager = SaveManager()
        state = manager.load(slot_id)
        engine = GameEngine.from_dict(state)
        self.app.game_engine = engine
        self.app.save_slot = slot_id
        self.app.switch_screen(GameScreen(restored_state=state))


def _generate_slot_id() -> str:
    """Generate a unique save slot ID based on timestamp."""
    import time
    return f"save-{int(time.time())}"
