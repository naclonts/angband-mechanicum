"""Main game screen -- composes the four-pane layout."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Input, Static
from textual import work

from angband_mechanicum.assets.npc_portraits import NPCPortraitStore
from angband_mechanicum.assets.placeholder_art import (
    FORGE_SCENE,
    INTRO_NARRATIVE,
    TECHPRIEST_PORTRAIT,
)
from angband_mechanicum.engine.game_engine import DeathNarrative
from angband_mechanicum.engine.combat_engine import CombatResult
from angband_mechanicum.engine.story_starts import StoryStart
from angband_mechanicum.engine.save_manager import SaveManager
from angband_mechanicum.engine.save_manager import DeathRecord, generate_death_record_id
from angband_mechanicum.screens.combat_screen import CombatScreen
from angband_mechanicum.widgets.help_overlay import HelpOverlay
from angband_mechanicum.widgets.info_panel import default_info, InfoPanel
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
        ("/explore", "Return to dungeon exploration"),
        ("/travel <destination>", "Travel to a new location"),
        ("c", "Begin combat (when prompted)"),
        ("/combat", "Enter combat mode (manual)"),
        ("h", "This help"),
    ]

    _TRAVEL_REQUEST_PHRASES: tuple[str, ...] = (
        "/travel",
        "/go",
        "travel to",
        "go to",
        "head to",
        "journey to",
        "take me to",
        "make for",
        "move to",
        "seek out",
        "venture to",
        "return to",
        "fly to",
        "sail to",
        "board",
        "descend to",
        "ascend to",
        "go toward",
        "go towards",
    )

    def __init__(
        self,
        restored_state: dict[str, Any] | None = None,
        story_start: StoryStart | None = None,
        speaking_npc_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._restored_state: dict[str, Any] | None = restored_state
        self._story_start: StoryStart | None = story_start
        self._speaking_npc_id: str | None = speaking_npc_id
        self._save_manager: SaveManager = SaveManager()
        self._narrative_log: list[str] = []
        self._pending_room_hint: dict | None = None
        self._npc_portraits: NPCPortraitStore = NPCPortraitStore()
        self._showing_npc_portrait: bool = False

    def compose(self) -> ComposeResult:
        initial_scene = self._story_start.scene_art if self._story_start else FORGE_SCENE
        yield ScenePane(initial_scene, id="scene")
        yield PortraitPane(TECHPRIEST_PORTRAIT, id="portrait")
        yield NarrativePane(id="narrative")
        yield Vertical(
            InfoPanel(id="info"),
            Static(
                "Type /explore to return to dungeon exploration. Try /travel <destination> for new coordinates.",
                id="prompt-hint",
            ),
            PromptInput(id="prompt"),
            id="right-panel",
        )

    def on_mount(self) -> None:
        self.query_one("#scene", ScenePane).border_title = "⛨ ENVIRONMENT"
        self.query_one("#portrait", PortraitPane).border_title = "⛨ OPERATIVE"
        # NarrativePane manages its own border_title (scroll indicator)
        self.query_one("#right-panel").border_title = "⛨ STATUS"

        self._initialize_info_panel_state()

        if self._restored_state:
            self._restore_ui(self._restored_state)
        else:
            intro = self._story_start.intro_narrative if self._story_start else INTRO_NARRATIVE
            self.query_one("#narrative", NarrativePane).append_narrative(intro)
            self._narrative_log.append(intro)

        self._sync_active_interaction_context()

        # Push deterministic status (integrity + party HP) to the panel
        self._push_status_to_panel()
        if self._speaking_npc_id:
            self._update_speaking_portrait(self._speaking_npc_id)

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

    def _initialize_info_panel_state(self) -> None:
        """Seed engine-side info panel data before the widgets render it."""
        engine = self.app.game_engine  # type: ignore[attr-defined]
        if self._story_start and self._story_start.info_overrides:
            engine._info_panel = dict(self._story_start.info_overrides)
        else:
            engine._info_panel = default_info(engine.player_name)

        if self._restored_state and self._restored_state.get("info_panel"):
            engine._info_panel.update(
                dict(self._restored_state.get("info_panel", {}))
            )
        if self._restored_state and self._restored_state.get("info_update"):
            engine._info_panel.update(
                dict(self._restored_state.get("info_update", {}))
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

    def _build_active_interaction_context(self) -> dict[str, Any] | None:
        """Return the focused dungeon interaction payload for the engine, if any."""
        if not self._restored_state:
            return None
        if not any(
            key in self._restored_state
            for key in (
                "interaction_target",
                "conversation_target",
                "interaction_entity_name",
                "target_entity_name",
                "target_label",
            )
        ):
            return None
        return dict(self._restored_state)

    def _sync_active_interaction_context(self) -> None:
        """Push any focused dungeon interaction into the engine prompt context."""
        engine = self.app.game_engine  # type: ignore[attr-defined]
        interaction_context = self._build_active_interaction_context()
        if interaction_context is None:
            engine.clear_active_interaction_context()
            return
        engine.set_active_interaction_context(interaction_context)

    @classmethod
    def _looks_like_travel_request(cls, text: str) -> bool:
        """Heuristically detect a natural-language travel request."""
        normalized = f" {text.strip().lower()} "
        return any(phrase in normalized for phrase in cls._TRAVEL_REQUEST_PHRASES)

    def _build_travel_transition_text(self, destination: Any) -> str:
        """Build the narrative text shown when the player travels elsewhere."""
        return (
            "\n[bold]++ TRANSIT ROUTE LOCKED ++[/bold]\n"
            f"The noosphere plots a passage toward [bold]{destination.display_name}[/bold].\n"
            f"[dim]The machine spirit accepts the route and shunts the expedition into {destination.environment} depths.[/dim]\n"
        )

    def _enter_travel_mode(self, text: str) -> None:
        """Resolve a travel request and switch into the matching dungeon."""
        narrative: NarrativePane = self.query_one("#narrative", NarrativePane)
        prompt: PromptInput = self.query_one("#prompt", PromptInput)

        narrative.append_narrative(f"\n[bold]> {text}[/bold]\n")
        self._narrative_log.append(f"\n[bold]> {text}[/bold]\n")
        prompt.set_processing(True)
        try:
            destination = self.app.travel_to_destination(text)  # type: ignore[attr-defined]
        finally:
            prompt.set_processing(False)

        travel_text = self._build_travel_transition_text(destination)
        narrative.append_narrative(travel_text)
        self._narrative_log.append(travel_text)
        self.return_to_dungeon(
            [travel_text],
            scene_art=None,
            info_update=None,
        )

    def action_show_help(self) -> None:
        """Push the help overlay with story-mode hotkeys."""
        self.app.push_screen(
            HelpOverlay(
                title="++ COMMAND HOTKEYS ++",
                hotkeys=self.STORY_HOTKEYS,
            )
        )

    def build_dungeon_transition_state(
        self,
        narrative_lines: list[str],
        *,
        scene_art: str | None = None,
        info_update: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build a text-view restore payload that can be passed back to the app."""
        state: dict[str, Any] = {
            "narrative_log": list(narrative_lines),
            "current_scene_art": scene_art,
        }
        if info_update:
            state["info_update"] = dict(info_update)
        return state

    def return_to_dungeon(
        self,
        narrative_lines: list[str] | None = None,
        *,
        scene_art: str | None = None,
        info_update: dict[str, str] | None = None,
    ) -> None:
        """Request the app to switch back to the persistent dungeon view."""
        self.app.game_engine.clear_active_interaction_context()  # type: ignore[attr-defined]
        self.app.return_to_dungeon_view(
            narrative_lines=narrative_lines,
            scene_art=scene_art,
            info_update=info_update,
        )

    def _build_death_context(self, result: CombatResult) -> dict[str, Any]:
        """Collect the structured context used for the Hall of the Dead entry."""
        engine = self.app.game_engine  # type: ignore[attr-defined]
        status = engine.get_status_data()
        companions = status.get("companions", [])
        companion_summary = ", ".join(
            f"{member['name']} ({'DEAD' if not member['alive'] else 'ALIVE'})"
            for member in companions
        )
        enemies = ", ".join(
            f"{enemy.name} ({'defeated' if enemy.defeated else 'survived'})"
            for enemy in result.enemies
        )
        dungeon_session = getattr(self.app, "dungeon_session", None)
        location = getattr(dungeon_session, "location", None) or status.get("info", {}).get("LOCATION", "Unknown Depths")
        deepest_level = 0
        if dungeon_session is not None:
            deepest_level = getattr(dungeon_session.state.level, "depth", 0)
        turns_survived = engine.turn_count + result.turn_count
        return {
            "player_name": engine.player_name,
            "location": location,
            "deepest_level_reached": deepest_level,
            "turns_survived": turns_survived,
            "enemies_slain": result.enemies_defeated,
            "enemy_summary": enemies or "unknown hostiles",
            "cause_of_death": f"Fell in battle against {enemies or 'unknown hostiles'}",
            "recent_narrative": self._narrative_log[-8:],
            "combat_log_summary": result.log_summary,
            "companion_summary": companion_summary or "none",
            "save_slot_id": getattr(self.app, "save_slot", None),
            "story_start_id": getattr(getattr(self.app, "dungeon_session", None), "story_id", None),
            "player_integrity": f"{result.player_hp_remaining}/{result.player_hp_max}",
        }

    @work(exclusive=True)
    async def _handle_player_death(self, result: CombatResult) -> None:
        """Generate the death memorial, persist it, and return to the menu."""
        engine = self.app.game_engine  # type: ignore[attr-defined]
        death_context = self._build_death_context(result)
        memorial: DeathNarrative = await engine.generate_death_narrative(death_context)
        record = DeathRecord(
            record_id=generate_death_record_id(),
            timestamp=time.time(),
            player_name=str(death_context["player_name"]),
            location=str(death_context["location"]),
            turns_survived=int(death_context["turns_survived"]),
            enemies_slain=int(death_context["enemies_slain"]),
            deepest_level_reached=int(death_context["deepest_level_reached"]),
            cause_of_death=memorial.cause_of_death,
            summary=memorial.summary,
            save_slot_id=death_context.get("save_slot_id"),
            story_start_id=death_context.get("story_start_id"),
        )
        self.app.archive_player_death(record)  # type: ignore[attr-defined]

    def _handle_combat_result(self, result: CombatResult | None) -> None:
        """Handle combat resolution, including permadeath."""
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

        # Persist combat result in engine history and LLM conversation
        engine.record_combat_result(result)

        # Update the info panel with the current integrity
        self._update_integrity_display()

        if result.player_hp_remaining <= 0:
            self._handle_player_death(result)
            return

        self.query_one("#prompt", PromptInput).focus()

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
        normalized = text.strip().lower()

        # Intercept /combat command before sending to LLM
        if normalized == "/combat":
            await self._enter_combat()
            return
        if normalized == "/explore":
            self._enter_explore_mode()
            return
        if self._looks_like_travel_request(text):
            self._enter_travel_mode(text)
            self._autosave()
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

        # Swap portrait when an NPC is speaking
        self._update_speaking_portrait(response.speaking_npc)

        # Push deterministic status (integrity + party HP + info fields)
        self._push_status_to_panel()

        # If the LLM signalled combat, enter tactical mode automatically
        if response.combat_trigger:
            self._pending_room_hint = response.room_hint
            self._enter_combat_from_trigger()
        elif self._response_requests_dungeon_return(response.narrative_text, response.info_update):
            self.return_to_dungeon(
                [response.narrative_text],
                scene_art=response.scene_art,
                info_update=response.info_update,
            )

        # Autosave after each successful command
        self._autosave()

    def _enter_explore_mode(self) -> None:
        """Switch back to the persistent dungeon view from text mode."""
        narrative: NarrativePane = self.query_one("#narrative", NarrativePane)
        transition_text = (
            "\n[bold]> /explore[/bold]\n"
            "\n[bold]++ EXPLORATION MODE ENGAGED ++ RETURNING TO THE DUNGEON ++[/bold]\n"
        )
        narrative.append_narrative(transition_text)
        self._narrative_log.append(transition_text)
        self.return_to_dungeon(
            [
                "Exploration resumes.",
            ],
            scene_art=None,
            info_update=None,
        )

    @staticmethod
    def _response_requests_dungeon_return(
        narrative_text: str,
        info_update: dict[str, str] | None,
    ) -> bool:
        """Interpret optional engine hints that ask the UI to re-enter exploration."""
        if info_update:
            for key in ("MODE", "mode", "VIEW", "view", "NEXT_MODE", "next_mode"):
                value = info_update.get(key)
                if isinstance(value, str) and value.strip().lower() in {
                    "explore",
                    "exploration",
                    "dungeon",
                    "map",
                }:
                    return True

        marker_text = narrative_text.lower()
        return any(
            marker in marker_text
            for marker in (
                "[explore]",
                "[return-to-dungeon]",
                "++ exploration mode engaged ++",
            )
        )

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
            self._handle_combat_result(result)

        self.app.push_screen(
            CombatScreen(
                player_hp=engine.integrity,
                player_max_hp=engine.max_integrity,
                party_ids=engine.party_member_ids,
                enemy_roster=enemy_roster if enemy_roster else None,
                map_def=map_def,
                player_name=engine.player_name,
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
            self._handle_combat_result(result)

        # Pass current integrity and generated roster into the combat screen.
        # Companions now remain map-side NPCs instead of direct combat units.
        self.app.push_screen(
            CombatScreen(
                player_hp=engine.integrity,
                player_max_hp=engine.max_integrity,
                enemy_roster=enemy_roster if enemy_roster else None,
                map_def=map_def,
                player_name=engine.player_name,
            ),
            callback=on_combat_result,
        )

    def _update_speaking_portrait(self, speaking_npc: str | None) -> None:
        """Swap the portrait pane to show the speaking NPC or restore the player."""
        portrait_pane: PortraitPane = self.query_one("#portrait", PortraitPane)
        engine = self.app.game_engine  # type: ignore[attr-defined]

        if speaking_npc:
            # Look up entity for name/description
            entity = engine.history.get_entity(speaking_npc)
            if entity:
                art = self._npc_portraits.assign_portrait(
                    entity_id=speaking_npc,
                    name=entity.name,
                    description=entity.description,
                )
                portrait_pane.update_portrait(art)
                portrait_pane.set_border_title(f"⛨ {entity.name.upper()}")
                self._showing_npc_portrait = True
                return

        # No speaking NPC or entity not found -- restore player portrait
        if self._showing_npc_portrait:
            portrait_pane.update_portrait(TECHPRIEST_PORTRAIT)
            portrait_pane.set_border_title("⛨ OPERATIVE")
            self._showing_npc_portrait = False

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
            dungeon_session = getattr(self.app, "dungeon_session", None)
            if dungeon_session is not None:
                state["mode"] = "text"
                state["dungeon_session"] = dungeon_session.to_dict()
                if dungeon_session.story_id is not None:
                    state["story_start_id"] = dungeon_session.story_id
            self._save_manager.save(slot_id, state)
            logger.info(
                "Autosaved turn %d to slot %s", engine.turn_count, slot_id
            )
        except Exception as exc:
            logger.error("Autosave failed: %s", exc)
