"""API key entry screen -- shown when ANTHROPIC_API_KEY is not configured."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from angband_mechanicum.screens import ARROW_NAV_BINDINGS, MenuNavigationMixin

HEADER_ART: str = """\
 ╔═══════════════════════════════════════════════════════════╗
 ║       ++ AUTHENTICATION RITE REQUIRED ++                 ║
 ║                                                          ║
 ║    Your cogitator lacks the sacred cipher-key to         ║
 ║    commune with the Machine Spirit.                      ║
 ║                                                          ║
 ║    Supply the ANTHROPIC_API_KEY to proceed.              ║
 ╚═══════════════════════════════════════════════════════════╝"""

INSTRUCTIONS: str = (
    "[dim]Provide the API key below. You may use it for this session only,\n"
    "or consecrate it to a .env file for future communions.[/dim]"
)

FOOTER_TEXT: str = (
    "[dim]++ THE MACHINE SPIRIT DEMANDS AUTHENTICATION "
    "++ KNOWLEDGE IS POWER ++[/dim]"
)


class ApiKeyScreen(MenuNavigationMixin, Screen[None]):
    """Prompts the user for an Anthropic API key when one is not set."""

    BINDINGS = [*ARROW_NAV_BINDINGS]

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="apikey-container"):
                yield Static(HEADER_ART, id="apikey-header")
                yield Static(INSTRUCTIONS, id="apikey-instructions")
                yield Input(
                    placeholder="sk-ant-...",
                    password=True,
                    id="apikey-input",
                )
                yield Button(
                    "++ USE FOR THIS SESSION ++",
                    id="btn-session",
                    variant="primary",
                )
                yield Button(
                    "++ SAVE TO .env FILE ++",
                    id="btn-save-env",
                    variant="default",
                )
                yield Static("", id="apikey-status")
                yield Static(FOOTER_TEXT, id="apikey-footer")

    def on_mount(self) -> None:
        self.query_one("#apikey-header").border_title = "++ CIPHER-KEY REQUIRED ++"
        self.focus_default_menu_control()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        key: str = self.query_one("#apikey-input", Input).value.strip()
        status: Static = self.query_one("#apikey-status", Static)

        if not key:
            status.update("[bold]++ ERROR: No cipher-key supplied ++[/bold]")
            return

        if not key.startswith("sk-"):
            status.update(
                "[bold]++ WARNING: Key does not begin with 'sk-' "
                "— verify and retry ++[/bold]"
            )
            return

        if event.button.id == "btn-session":
            self._apply_key(key)
        elif event.button.id == "btn-save-env":
            self._save_and_apply_key(key)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Allow pressing Enter in the input to trigger session-only use."""
        key: str = event.value.strip()
        status: Static = self.query_one("#apikey-status", Static)

        if not key:
            status.update("[bold]++ ERROR: No cipher-key supplied ++[/bold]")
            return

        if not key.startswith("sk-"):
            status.update(
                "[bold]++ WARNING: Key does not begin with 'sk-' "
                "— verify and retry ++[/bold]"
            )
            return

        self._apply_key(key)

    def _apply_key(self, key: str) -> None:
        """Set the key in the environment and proceed to menu."""
        os.environ["ANTHROPIC_API_KEY"] = key
        self._proceed()

    def _save_and_apply_key(self, key: str) -> None:
        """Write the key to a .env file and set it in the environment."""
        env_path: Path = Path.cwd() / ".env"
        status: Static = self.query_one("#apikey-status", Static)

        # Read existing content to avoid duplicating the key
        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text().splitlines()

        # Remove any existing ANTHROPIC_API_KEY line
        lines = [
            line for line in lines
            if not line.strip().startswith("ANTHROPIC_API_KEY=")
        ]
        lines.append(f"ANTHROPIC_API_KEY={key}")

        env_path.write_text("\n".join(lines) + "\n")
        status.update(
            f"[dim]++ Cipher-key consecrated to {env_path} ++[/dim]"
        )

        os.environ["ANTHROPIC_API_KEY"] = key
        self._proceed()

    def _proceed(self) -> None:
        """Reinitialize the game engine with the new key and go to menu."""
        from angband_mechanicum.engine.game_engine import GameEngine

        self.app.game_engine = GameEngine()  # type: ignore[attr-defined]
        self.app.switch_screen("menu")
