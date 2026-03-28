"""Main game screen -- composes the four-pane layout."""

from __future__ import annotations

import logging
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Input
from textual import work

from angband_mechanicum.assets.placeholder_art import (
    FORGE_SCENE,
    INTRO_NARRATIVE,
    TECHPRIEST_PORTRAIT,
)
from angband_mechanicum.engine.combat_engine import CombatResult
from angband_mechanicum.engine.save_manager import SaveManager
from angband_mechanicum.screens.combat_screen import CombatScreen
from angband_mechanicum.widgets.help_overlay import HelpOverlay
from angband_mechanicum.widgets.info_panel import DEFAULT_INFO, InfoPanel
from angband_mechanicum.widgets.narrative_pane import NarrativePane
from angband_mechanicum.widgets.portrait_pane import PortraitPane
from angband_mechanicum.widgets.prompt_input import PromptInput
from angband_mechanicum.widgets.scene_pane import ScenePane

logger: logging.Logger = logging.getLogger(__name__)


class GameScreen(Screen[None]):
    BINDINGS = [
        Binding("h", "show_help", "Help", show=True, priority=True),
    ]

    STORY_HOTKEYS: list[tuple[str, str]] = [
        ("Enter", "Submit command"),
        ("Tab", "Cycle panes"),
        ("c", "Begin combat (when prompted)"),
        ("/combat", "Enter combat mode (manual)"),
        ("h", "This help"),
    ]

    def __init__(
        self,
        restored_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._restored_state: dict[str, Any] | None = restored_state
        self._save_manager: SaveManager = SaveManager()
        self._narrative_log: list[str] = []
        self._pending_room_hint: dict | None = None

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
            self.query_one("#narrative", NarrativePane).append_narrative(INTRO_NARRATIVE)
            self._narrative_log.append(INTRO_NARRATIVE)
            # Initialize engine info panel with defaults for save tracking
            self.app.game_engine._info_panel = dict(DEFAULT_INFO)  # type: ignore[attr-defined]

        # Push deterministic status (integrity + party HP) to the panel
        self._push_status_to_panel()

        self.query_one("#prompt", PromptInput).focus()
        # Push initial pane dimensions to the engine after layout
        self.call_after_refresh(self._sync_scene_pane_size)

    def on_resize(self, event: Resize) -> None:
        """Re-sync scene pane dimensions when the terminal is resized."""
        self._sync_scene_pane_size()

    def _sync_scene_pane_size(self) -> None:
        """Tell the engine the current scene pane content dimensions."""
        scene: ScenePane = self.query_one("#scene", ScenePane)
        self.app.game_engine.set_scene_pane_size(  # type: ignore[attr-defined]
            width=scene.content_width,
            height=scene.content_height,
        )

    def _restore_ui(self, state: dict[str, Any]) -> None:
        """Restore UI panes from saved state."""
        # Info panel data is restored into the engine; _push_status_to_panel
        # will render it after this method returns (called in on_mount).

        scene_art: str | None = state.get("current_scene_art")
        if scene_art:
            self.query_one("#scene", ScenePane).update_scene(scene_art)

        narrative_history: list[str] = state.get("narrative_log", [])
        narrative_pane: NarrativePane = self.query_one("#narrative", NarrativePane)
        for entry in narrative_history:
            narrative_pane.append_narrative(entry)
        self._narrative_log = list(narrative_history)
        if not narrative_history:
            narrative_pane.append_narrative(
                "[dim]++ SESSION RESTORED ++ MACHINE SPIRIT APPEASED ++[/dim]"
            )

    def action_show_help(self) -> None:
        """Push the help overlay with story-mode hotkeys."""
        self.app.push_screen(
            HelpOverlay(
                title="++ COMMAND HOTKEYS ++",
                hotkeys=self.STORY_HOTKEYS,
            )
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt: PromptInput = self.query_one("#prompt", PromptInput)
        if prompt.is_processing:
            return
        text: str = event.value.strip()
        if not text:
            return
        event.input.clear()
        self.handle_command(text)

    @work(exclusive=True)
    async def handle_command(self, text: str) -> None:

        # Intercept /combat command before sending to LLM
        if text.strip().lower() == "/combat":
            await self._enter_combat()
            return

        narrative: NarrativePane = self.query_one("#narrative", NarrativePane)
        prompt: PromptInput = self.query_one("#prompt", PromptInput)
        narrative.append_narrative(f"\n[bold]> {text}[/bold]\n")

        self._narrative_log.append(f"\n[bold]> {text}[/bold]\n")

        # Show loading state while the engine processes
        narrative.show_loading()
        prompt.set_processing(True)

        # Sync pane dimensions right before calling the LLM so the prompt
        # always reflects the current terminal size.
        self._sync_scene_pane_size()

        try:
            response = await self.app.game_engine.process_input(text)  # type: ignore[attr-defined]
        finally:
            # Always clear loading state, even on error
            narrative.hide_loading()
            prompt.set_processing(False)
            prompt.focus()

        narrative.append_narrative(response.narrative_text)
        self._narrative_log.append(response.narrative_text)

        if response.scene_art:
            self.query_one("#scene", ScenePane).update_scene(response.scene_art)

        # Push deterministic status (integrity + party HP + info fields)
        self._push_status_to_panel()

        # If the LLM signalled combat, enter tactical mode automatically
        if response.combat_trigger:
            self._pending_room_hint = response.room_hint
            self._enter_combat_from_trigger()

        # Autosave after each successful command
        self._autosave()

    @work(exclusive=True)
    async def _enter_combat_from_trigger(self) -> None:
        """Enter combat automatically when the LLM signals a combat trigger."""
        narrative: NarrativePane = self.query_one("#narrative", NarrativePane)
        prompt: PromptInput = self.query_one("#prompt", PromptInput)
        engine = self.app.game_engine  # type: ignore[attr-defined]

        narrative.append_narrative(
            "\n[bold]++ TACTICAL MODE ENGAGED ++ COMBAT PROTOCOLS ACTIVE ++[/bold]\n"
        )
        self._narrative_log.append(
            "\n[bold]++ TACTICAL MODE ENGAGED ++ COMBAT PROTOCOLS ACTIVE ++[/bold]\n"
        )

        # Generate encounter via the LLM (with loading indicator)
        narrative.show_loading()
        prompt.set_processing(True)
        room_hint = self._pending_room_hint
        self._pending_room_hint = None

        try:
            encounter = await engine.generate_encounter(room_hint=room_hint)
        finally:
            narrative.hide_loading()
            prompt.set_processing(False)

        # Show the encounter description
        desc = encounter.get("encounter_description", "Hostile contacts detected.")
        narrative.append_narrative(f"\n[dim]{desc}[/dim]\n")
        self._narrative_log.append(f"\n[dim]{desc}[/dim]\n")

        enemy_roster: list[tuple[str, int, int]] = encounter.get("enemy_roster", [])
        map_def = encounter.get("map_def")

        def on_combat_result(result: CombatResult | None) -> None:
            """Handle combat result when CombatScreen is dismissed."""
            if result is None:
                return

            engine = self.app.game_engine  # type: ignore[attr-defined]
            engine.set_integrity(result.player_hp_remaining)

            narrative_pane: NarrativePane = self.query_one("#narrative", NarrativePane)
            if result.victory:
                summary = (
                    f"\n[bold]++ COMBAT RESOLVED: VICTORY ++[/bold]\n"
                    f"Hostiles neutralised: {result.enemies_defeated}/{result.enemies_total}\n"
                    f"Integrity remaining: {result.player_hp_remaining}/{result.player_hp_max}\n"
                    f"Turns elapsed: {result.turn_count}\n"
                    f"[dim]++ THE OMNISSIAH IS PLEASED ++[/dim]\n"
                )
            else:
                summary = (
                    f"\n[bold]++ COMBAT RESOLVED: {'RETREAT' if result.player_hp_remaining > 0 else 'DEFEAT'} ++[/bold]\n"
                    f"Hostiles neutralised: {result.enemies_defeated}/{result.enemies_total}\n"
                    f"Integrity remaining: {result.player_hp_remaining}/{result.player_hp_max}\n"
                    f"Turns elapsed: {result.turn_count}\n"
                    f"[dim]++ THE MACHINE SPIRIT ENDURES ++[/dim]\n"
                )
            narrative_pane.append_narrative(summary)
            self._narrative_log.append(summary)

            engine.record_combat_result(result)
            self._update_integrity_display()
            self.query_one("#prompt", PromptInput).focus()

        self.app.push_screen(
            CombatScreen(
                player_hp=engine.integrity,
                player_max_hp=engine.max_integrity,
                party_ids=engine.party_member_ids,
                enemy_roster=enemy_roster if enemy_roster else None,
                map_def=map_def,
            ),
            callback=on_combat_result,
        )

    async def _enter_combat(self) -> None:
        """Generate an encounter via the LLM, then push the CombatScreen."""
        narrative: NarrativePane = self.query_one("#narrative", NarrativePane)
        prompt: PromptInput = self.query_one("#prompt", PromptInput)
        engine = self.app.game_engine  # type: ignore[attr-defined]

        narrative.append_narrative(
            "\n[bold]> /combat[/bold]\n"
            "\n[bold]++ TACTICAL MODE ENGAGED ++ COMBAT PROTOCOLS ACTIVE ++[/bold]\n"
        )
        self._narrative_log.append(
            "\n[bold]> /combat[/bold]\n"
            "\n[bold]++ TACTICAL MODE ENGAGED ++ COMBAT PROTOCOLS ACTIVE ++[/bold]\n"
        )

        # Generate encounter via the LLM (with loading indicator)
        narrative.show_loading()
        prompt.set_processing(True)
        try:
            encounter = await engine.generate_encounter()
        finally:
            narrative.hide_loading()
            prompt.set_processing(False)

        # Show the encounter description
        desc = encounter.get("encounter_description", "Hostile contacts detected.")
        narrative.append_narrative(f"\n[dim]{desc}[/dim]\n")
        self._narrative_log.append(f"\n[dim]{desc}[/dim]\n")

        enemy_roster: list[tuple[str, int, int]] = encounter.get("enemy_roster", [])
        map_def = encounter.get("map_def")

        def on_combat_result(result: CombatResult | None) -> None:
            """Handle combat result when CombatScreen is dismissed."""
            if result is None:
                return

            # Carry combat HP back to story-mode integrity
            engine = self.app.game_engine  # type: ignore[attr-defined]
            engine.set_integrity(result.player_hp_remaining)

            narrative_pane: NarrativePane = self.query_one("#narrative", NarrativePane)
            if result.victory:
                summary = (
                    f"\n[bold]++ COMBAT RESOLVED: VICTORY ++[/bold]\n"
                    f"Hostiles neutralised: {result.enemies_defeated}/{result.enemies_total}\n"
                    f"Integrity remaining: {result.player_hp_remaining}/{result.player_hp_max}\n"
                    f"Turns elapsed: {result.turn_count}\n"
                    f"[dim]++ THE OMNISSIAH IS PLEASED ++[/dim]\n"
                )
            else:
                summary = (
                    f"\n[bold]++ COMBAT RESOLVED: {'RETREAT' if result.player_hp_remaining > 0 else 'DEFEAT'} ++[/bold]\n"
                    f"Hostiles neutralised: {result.enemies_defeated}/{result.enemies_total}\n"
                    f"Integrity remaining: {result.player_hp_remaining}/{result.player_hp_max}\n"
                    f"Turns elapsed: {result.turn_count}\n"
                    f"[dim]++ THE MACHINE SPIRIT ENDURES ++[/dim]\n"
                )
            narrative_pane.append_narrative(summary)
            self._narrative_log.append(summary)

            # Persist combat result in engine history and LLM conversation
            engine.record_combat_result(result)

            # Update the info panel with the current integrity
            self._update_integrity_display()

            self.query_one("#prompt", PromptInput).focus()

        # Pass current integrity, party, and generated roster into the combat screen
        self.app.push_screen(
            CombatScreen(
                player_hp=engine.integrity,
                player_max_hp=engine.max_integrity,
                party_ids=engine.party_member_ids,
                enemy_roster=enemy_roster if enemy_roster else None,
                map_def=map_def,
            ),
            callback=on_combat_result,
        )

    def _update_integrity_display(self) -> None:
        """Push the current integrity value into the info panel."""
        self._push_status_to_panel()

    def _push_status_to_panel(self) -> None:
        """Push deterministic status data (info fields + integrity + party HP) to the InfoPanel."""
        engine = self.app.game_engine  # type: ignore[attr-defined]
        status = engine.get_status_data()
        self.query_one("#info", InfoPanel).update_status(status)

    def _autosave(self) -> None:
        """Save current game state to the session's save slot."""
        try:
            slot_id: str | None = getattr(self.app, "save_slot", None)
            if not slot_id:
                return
            engine = self.app.game_engine  # type: ignore[attr-defined]
            state: dict[str, Any] = engine.to_dict()
            state["narrative_log"] = list(self._narrative_log)
            self._save_manager.save(slot_id, state)
            logger.info(
                "Autosaved turn %d to slot %s", engine.turn_count, slot_id
            )
        except Exception as exc:
            logger.error("Autosave failed: %s", exc)
