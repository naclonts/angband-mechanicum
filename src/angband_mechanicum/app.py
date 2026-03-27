"""Angband Mechanicum — main application."""

from textual.app import App

from angband_mechanicum.engine.game_engine import GameEngine
from angband_mechanicum.screens.game_screen import GameScreen
from angband_mechanicum.theme import CRT_GREEN


class AngbandMechanicumApp(App):
    CSS_PATH = "styles/game.tcss"
    TITLE = "Angband Mechanicum"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.game_engine = GameEngine()

    def on_mount(self) -> None:
        self.register_theme(CRT_GREEN)
        self.theme = "crt-green"
        self.push_screen(GameScreen())


def main() -> None:
    app = AngbandMechanicumApp()
    app.run()


if __name__ == "__main__":
    main()
