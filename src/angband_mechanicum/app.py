"""Angband Mechanicum -- main application."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import App

from angband_mechanicum.engine.game_engine import GameEngine
from angband_mechanicum.screens.api_key_screen import ApiKeyScreen
from angband_mechanicum.screens.menu_screen import MenuScreen
from angband_mechanicum.theme import CRT_GREEN


def _load_env_file() -> None:
    """Load key=value pairs from a .env file in cwd, if it exists."""
    env_path: Path = Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


class AngbandMechanicumApp(App[None]):
    CSS_PATH = "styles/game.tcss"
    TITLE = "Angband Mechanicum"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        _load_env_file()
        self.game_engine: GameEngine = GameEngine()
        self.save_slot: str | None = None

    def on_mount(self) -> None:
        self.register_theme(CRT_GREEN)
        self.theme = "crt-green"
        self.install_screen(MenuScreen(), name="menu")
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.push_screen("menu")
        else:
            self.push_screen(ApiKeyScreen())


def main() -> None:
    app = AngbandMechanicumApp()
    app.run()


if __name__ == "__main__":
    main()
