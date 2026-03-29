"""Menu screen -- New Game / Load Game selection on launch."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from angband_mechanicum.engine.save_manager import SaveManager, SaveMetadata
from angband_mechanicum.screens import ARROW_NAV_BINDINGS

TITLE_ART: str = """\
╔═══════════════════════════════════════════════════════╗
║            ⛨  ANGBAND MECHANICUM  ⛨                  ║
║     ++ ADEPTUS MECHANICUS FIELD TERMINAL ++          ║
║     ++ FORGE WORLD: METALLICA SECUNDUS  ++           ║
║     ++ CLEARANCE: MAGOS EXPLORATOR      ++           ║
╚═══════════════════════════════════════════════════════╝"""

FOOTER_TEXT: str = "[dim]++ THE OMNISSIAH PROTECTS ++ FLESH IS WEAK ++ THE MACHINE IS ETERNAL ++[/dim]"


class MenuScreen(Screen[None]):
    """Main menu with New Game and Load Game options."""

    BINDINGS = [*ARROW_NAV_BINDINGS]

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="menu-container"):
                yield Static(TITLE_ART, id="menu-title")
                yield Button("++ NEW GAME ++", id="btn-new", variant="primary")
                yield Button("++ LOAD GAME ++", id="btn-load", variant="default")
                yield Button("++ HALL OF THE DEAD ++", id="btn-hall", variant="default")
                yield Static(FOOTER_TEXT, id="menu-footer")
                yield Vertical(id="save-list")

    def on_mount(self) -> None:
        load_btn: Button = self.query_one("#btn-load", Button)
        saves: list[SaveMetadata] = SaveManager().list_saves()
        if not saves:
            load_btn.disabled = True
            load_btn.label = "++ LOAD GAME ++ [NO SAVES]"
        self._saves: list[SaveMetadata] = saves

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new":
            self._start_new_game()
        elif event.button.id == "btn-load":
            self._show_save_list()
        elif event.button.id == "btn-hall":
            self.app.open_hall_of_dead_view()  # type: ignore[attr-defined]
        elif event.button.id and event.button.id.startswith("save-"):
            slot_id: str = event.button.id.removeprefix("save-")
            self._load_game(slot_id)

    def _start_new_game(self) -> None:
        from angband_mechanicum.screens.character_setup_screen import CharacterSetupScreen

        def on_name_chosen(name: str) -> None:
            from angband_mechanicum.engine.story_starts import StoryStart
            from angband_mechanicum.screens.story_select_screen import StorySelectScreen

            def on_story_selected(story: StoryStart | None) -> None:
                if story is None:
                    return
                self.app.begin_new_game(name, story)  # type: ignore[attr-defined]

            self.app.push_screen(StorySelectScreen(), callback=on_story_selected)

        self.app.push_screen(CharacterSetupScreen(), callback=on_name_chosen)

    def _show_save_list(self) -> None:
        save_list: Vertical = self.query_one("#save-list", Vertical)
        save_list.remove_children()
        if not self._saves:
            return
        save_list.mount(Label("[bold]++ SELECT SESSION TO RESTORE ++[/bold]"))
        for save in self._saves:
            btn: Button = Button(
                f"{save.display_time}  |  {save.location}  |  Turn {save.turn_count}",
                id=f"save-{save.slot_id}",
                variant="default",
                classes="save-entry",
            )
            save_list.mount(btn)

    def _load_game(self, slot_id: str) -> None:
        from angband_mechanicum.engine.game_engine import GameEngine
        from angband_mechanicum.app import DungeonSession

        manager: SaveManager = SaveManager()
        state = manager.load(slot_id)
        engine: GameEngine = GameEngine.from_dict(state)
        self.app.game_engine = engine  # type: ignore[attr-defined]
        self.app.save_slot = slot_id  # type: ignore[attr-defined]
        if state.get("dungeon_session"):
            session = DungeonSession.from_dict(state["dungeon_session"])
            session.story_id = state.get("story_start_id", session.story_id)
            self.app.dungeon_session = session  # type: ignore[attr-defined]
            self.app.open_dungeon_view()  # type: ignore[attr-defined]
            return
        self.app.open_text_view(restored_state=state)  # type: ignore[attr-defined]


def _generate_slot_id() -> str:
    """Generate a unique save slot ID based on timestamp."""
    import time
    return f"save-{int(time.time())}"
