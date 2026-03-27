"""Main game screen — composes the four-pane layout."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input
from textual import work

from angband_mechanicum.assets.placeholder_art import (
    FORGE_SCENE,
    INTRO_NARRATIVE,
    TECHPRIEST_PORTRAIT,
)
from angband_mechanicum.widgets.info_panel import DEFAULT_INFO, InfoPanel
from angband_mechanicum.widgets.narrative_pane import NarrativePane
from angband_mechanicum.widgets.portrait_pane import PortraitPane
from angband_mechanicum.widgets.prompt_input import PromptInput
from angband_mechanicum.widgets.scene_pane import ScenePane


class GameScreen(Screen):
    def compose(self) -> ComposeResult:
        yield ScenePane(FORGE_SCENE, id="scene")
        yield PortraitPane(TECHPRIEST_PORTRAIT, id="portrait")
        yield NarrativePane(id="narrative")
        yield Vertical(
            InfoPanel(id="info"),
            PromptInput(id="prompt"),
            id="right-panel",
        )

    def on_mount(self) -> None:
        self.query_one("#scene", ScenePane).border_title = "⛨ ENVIRONMENT"
        self.query_one("#portrait", PortraitPane).border_title = "⛨ OPERATIVE"
        self.query_one("#narrative", NarrativePane).border_title = "⛨ DATALOG"
        self.query_one("#right-panel").border_title = "⛨ STATUS"
        self.query_one("#info", InfoPanel).update_info(DEFAULT_INFO)
        self.query_one("#narrative", NarrativePane).append_narrative(INTRO_NARRATIVE)
        self.query_one("#prompt", PromptInput).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()
        self.handle_command(text)

    @work(exclusive=True)
    async def handle_command(self, text: str) -> None:
        narrative = self.query_one("#narrative", NarrativePane)
        narrative.append_narrative(f"\n[bold]> {text}[/bold]\n")
        response = await self.app.game_engine.process_input(text)
        narrative.append_narrative(response.narrative_text)
        if response.scene_art:
            self.query_one("#scene", ScenePane).update_scene(response.scene_art)
        if response.info_update:
            self.query_one("#info", InfoPanel).update_info(response.info_update)
