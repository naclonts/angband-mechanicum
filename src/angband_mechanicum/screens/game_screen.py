"""Main game screen — composes the four-pane layout."""

from __future__ import annotations

import logging

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
from angband_mechanicum.engine.save_manager import SaveManager
from angband_mechanicum.widgets.info_panel import DEFAULT_INFO, InfoPanel
from angband_mechanicum.widgets.narrative_pane import NarrativePane
from angband_mechanicum.widgets.portrait_pane import PortraitPane
from angband_mechanicum.widgets.prompt_input import PromptInput
from angband_mechanicum.widgets.scene_pane import ScenePane

logger = logging.getLogger(__name__)


class GameScreen(Screen):
    def __init__(self, restored_state: dict | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._restored_state = restored_state
        self._save_manager = SaveManager()

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
        # NarrativePane manages its own border_title (scroll indicator)
        self.query_one("#right-panel").border_title = "⛨ STATUS"

        if self._restored_state:
            self._restore_ui(self._restored_state)
        else:
            self.query_one("#info", InfoPanel).update_info(DEFAULT_INFO)
            self.query_one("#narrative", NarrativePane).append_narrative(INTRO_NARRATIVE)
            # Initialize engine info panel with defaults for save tracking
            self.app.game_engine._info_panel = dict(DEFAULT_INFO)

        self.query_one("#prompt", PromptInput).focus()

    def _restore_ui(self, state: dict) -> None:
        """Restore UI panes from saved state."""
        info_data = state.get("info_panel", DEFAULT_INFO)
        self.query_one("#info", InfoPanel).update_info(info_data)

        scene_art = state.get("current_scene_art")
        if scene_art:
            self.query_one("#scene", ScenePane).update_scene(scene_art)

        narrative_history = state.get("narrative_log", [])
        narrative_pane = self.query_one("#narrative", NarrativePane)
        for entry in narrative_history:
            narrative_pane.append_narrative(entry)
        if not narrative_history:
            narrative_pane.append_narrative(
                "[dim]++ SESSION RESTORED ++ MACHINE SPIRIT APPEASED ++[/dim]"
            )

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

        # Track narrative log entries for save state
        if not hasattr(self, "_narrative_log"):
            self._narrative_log: list[str] = []
            if self._restored_state:
                self._narrative_log = list(
                    self._restored_state.get("narrative_log", [])
                )
            else:
                self._narrative_log.append(INTRO_NARRATIVE)
        self._narrative_log.append(f"\n[bold]> {text}[/bold]\n")

        response = await self.app.game_engine.process_input(text)
        narrative.append_narrative(response.narrative_text)
        self._narrative_log.append(response.narrative_text)

        if response.scene_art:
            self.query_one("#scene", ScenePane).update_scene(response.scene_art)
        if response.info_update:
            self.query_one("#info", InfoPanel).update_info(response.info_update)

        # Autosave after each successful command
        self._autosave()

    def _autosave(self) -> None:
        """Save current game state to the session's save slot."""
        try:
            slot_id = getattr(self.app, "save_slot", None)
            if not slot_id:
                return
            engine = self.app.game_engine
            state = engine.to_dict()
            state["narrative_log"] = list(
                getattr(self, "_narrative_log", [])
            )
            self._save_manager.save(slot_id, state)
            logger.info(
                "Autosaved turn %d to slot %s", engine.turn_count, slot_id
            )
        except Exception as exc:
            logger.error("Autosave failed: %s", exc)
