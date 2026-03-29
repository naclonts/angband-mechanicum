"""Angband Mechanicum -- main application."""

from __future__ import annotations

import logging
import os
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from textual.app import App

from angband_mechanicum.engine.dungeon_profiles import (
    DungeonGenerationProfile,
    build_story_dungeon_profile,
    build_travel_dungeon_profile,
)
from angband_mechanicum.engine.game_engine import GameEngine, TravelDestination
from angband_mechanicum.engine.save_manager import (
    DeathRecord,
    SaveManager,
    generate_death_record_id,
)
from angband_mechanicum.engine.dungeon_level import transition_terrain_label
from angband_mechanicum.engine.story_starts import StoryStart
from angband_mechanicum.screens.api_key_screen import ApiKeyScreen
from angband_mechanicum.screens.dungeon_screen import (
    DungeonMapState,
    DungeonScreen,
    build_map_entities_from_roster,
)
from angband_mechanicum.screens.hall_of_dead_screen import HallOfDeadScreen
from angband_mechanicum.screens.game_screen import GameScreen
from angband_mechanicum.screens.menu_screen import MenuScreen
from angband_mechanicum.engine.dungeon_gen import GeneratedFloor, generate_dungeon_floor
from angband_mechanicum.theme import CRT_GREEN

logger: logging.Logger = logging.getLogger(__name__)


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


def _generate_slot_id() -> str:
    """Generate a unique save slot ID based on timestamp."""
    import time

    return f"save-{int(time.time())}"


@dataclass
class DungeonSession:
    """Persistent dungeon bridge state owned by the app."""

    state: DungeonMapState
    story_id: str | None = None
    location: str | None = None
    intro_narrative: str | None = None
    generation_profile: DungeonGenerationProfile | None = None
    current_environment_id: str | None = None
    destination_query: str | None = None
    destination_environment: str | None = None
    destination_label: str | None = None
    pending_text_context: dict[str, Any] = field(default_factory=dict)
    level_stack: list[str] = field(default_factory=list)
    level_states: dict[str, DungeonMapState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.level_states.setdefault(self.state.level.level_id, self.state)
        if self.current_environment_id is None:
            self.current_environment_id = self.state.level.environment
        if self.location is None:
            self.location = self.destination_label or self.state.level.name

    def snapshot_current_state(self) -> None:
        """Remember the live dungeon state under its level ID."""
        self.level_states[self.state.level.level_id] = self.state
        self.location = self.state.level.name

    def to_dict(self) -> dict[str, Any]:
        """Serialize the current dungeon session for persistence."""
        return {
            "state": self.state.to_dict(),
            "story_id": self.story_id,
            "location": self.location,
            "intro_narrative": self.intro_narrative,
            "generation_profile": (
                self.generation_profile.to_dict()
                if self.generation_profile is not None
                else None
            ),
            "current_environment_id": self.current_environment_id,
            "destination_query": self.destination_query,
            "destination_environment": self.destination_environment,
            "destination_label": self.destination_label,
            "pending_text_context": dict(self.pending_text_context),
            "level_stack": list(self.level_stack),
            "level_states": {
                level_id: level_state.to_dict()
                for level_id, level_state in self.level_states.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DungeonSession:
        """Reconstruct a dungeon session from serialized data."""
        if "state" in data:
            state_data = data["state"]
        else:
            state_data = data
        state = DungeonMapState.from_dict(state_data)
        level_states_raw = data.get("level_states", {})
        level_states = {
            level_id: DungeonMapState.from_dict(level_state)
            for level_id, level_state in level_states_raw.items()
        }
        level_states[state.level.level_id] = state
        return cls(
            state=state,
            story_id=data.get("story_id"),
            location=data.get("location") or data.get("destination_label") or state.level.name,
            intro_narrative=data.get("intro_narrative"),
            generation_profile=DungeonGenerationProfile.from_dict(
                data.get("generation_profile")
            ),
            current_environment_id=data.get("current_environment_id")
            or state.level.environment,
            destination_query=data.get("destination_query"),
            destination_environment=data.get("destination_environment"),
            destination_label=data.get("destination_label"),
            pending_text_context=dict(data.get("pending_text_context", {})),
            level_stack=[str(level_id) for level_id in data.get("level_stack", [])],
            level_states=level_states,
        )

    def to_text_restore_state(
        self,
        narrative_lines: list[str],
        *,
        scene_art: str | None = None,
        info_update: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build a GameScreen restore payload for a map->text transition."""
        restored: dict[str, Any] = {
            "narrative_log": list(narrative_lines),
            "current_scene_art": scene_art,
        }
        if info_update:
            restored["info_update"] = dict(info_update)
        if self.location:
            restored["info_panel"] = {"LOCATION": self.location}
        return restored


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
        self.dungeon_session: DungeonSession | None = None
        self._story_start: StoryStart | None = None

    # ------------------------------------------------------------------
    # View bridge helpers
    # ------------------------------------------------------------------

    def _build_session_from_floor(
        self,
        floor: GeneratedFloor,
        *,
        story_id: str | None = None,
        location: str | None = None,
        intro_narrative: str | None = None,
        destination_query: str | None = None,
        destination_environment: str | None = None,
        destination_label: str | None = None,
        generation_profile: DungeonGenerationProfile | None = None,
        messages: list[str] | None = None,
    ) -> DungeonSession:
        """Create a DungeonSession from a generated floor."""
        return DungeonSession(
            state=DungeonMapState(
                level=floor.level,
                player_pos=floor.level.player_pos,
                entities=build_map_entities_from_roster(floor.entity_roster),
                messages=list(messages or []),
            ),
            story_id=story_id,
            location=location or floor.level.name,
            intro_narrative=intro_narrative,
            generation_profile=generation_profile,
            current_environment_id=floor.level.environment,
            destination_query=destination_query,
            destination_environment=destination_environment,
            destination_label=destination_label,
        )

    def _sync_engine_environment_context(
        self,
        profile: DungeonGenerationProfile | None,
        *,
        fallback_location: str | None = None,
    ) -> None:
        """Keep the narrative engine aligned with the canonical session environment."""
        environment = profile.environment if profile is not None else "forge"
        profile_id = profile.profile_id if profile is not None else None
        location_name = (
            profile.location_name if profile is not None and profile.location_name else fallback_location
        )
        self.game_engine.set_environment_context(
            environment_id=environment,
            profile_id=profile_id,
            location_name=location_name,
        )

    def build_dungeon_session(self, story_start: StoryStart | None = None) -> DungeonSession:
        """Create a fresh dungeon session for the active story."""
        profile = build_story_dungeon_profile(story_start)
        source = story_start.id if story_start else "default"
        seed = zlib.adler32(source.encode("utf-8"))
        location = story_start.location if story_start else "Unknown Depths"
        floor = generate_dungeon_floor(
            level_id=source,
            depth=1,
            environment=profile.environment,
            name=location,
            seed=seed,
            profile=profile,
        )
        messages = [story_start.intro_narrative] if story_start else []
        session = self._build_session_from_floor(
            floor,
            story_id=story_start.id if story_start else None,
            location=floor.level.name,
            intro_narrative=story_start.intro_narrative if story_start else None,
            generation_profile=profile,
            messages=messages,
        )
        self._sync_engine_environment_context(profile, fallback_location=floor.level.name)
        return session

    def build_destination_session(self, request_text: str) -> tuple[DungeonSession, TravelDestination]:
        """Create a dungeon session for a requested travel destination."""
        destination = self.game_engine.resolve_travel_destination(request_text)
        profile = build_travel_dungeon_profile(
            environment=destination.environment,
            location_name=destination.display_name,
        )
        existing_story_id = None
        if self.dungeon_session is not None:
            existing_story_id = self.dungeon_session.story_id
        if existing_story_id is None:
            existing_story_id = self._story_start.id if self._story_start else None

        level_id = f"travel:{destination.environment}:{zlib.adler32(request_text.encode('utf-8'))}"
        seed = zlib.adler32(f"{destination.environment}:{request_text}".encode("utf-8"))
        floor = generate_dungeon_floor(
            level_id=level_id,
            depth=1,
            environment=destination.environment,
            name=destination.display_name,
            seed=seed,
            profile=profile,
        )
        session = self._build_session_from_floor(
            floor,
            story_id=existing_story_id,
            location=destination.display_name,
            generation_profile=profile,
            destination_query=request_text,
            destination_environment=destination.environment,
            destination_label=destination.display_name,
        )
        self.dungeon_session = session
        self._sync_engine_environment_context(profile, fallback_location=destination.display_name)
        return session, destination

    def enter_dungeon_combat_view(
        self,
        *,
        room_hint: dict[str, Any] | None = None,
        narrative_lines: list[str] | None = None,
        scene_art: str | None = None,
        info_update: dict[str, str] | None = None,
        source_label: str = "combat",
    ) -> None:
        """Mount a combat-heavy dungeon encounter without using the legacy tactical screen."""
        if self.dungeon_session is None:
            self.dungeon_session = self.build_dungeon_session(self._story_start)

        session = self.dungeon_session
        profile = session.generation_profile or build_story_dungeon_profile(self._story_start)
        environment = session.current_environment_id or session.state.level.environment or profile.environment
        location_name = session.location or session.state.level.name
        encounter_name = location_name
        if room_hint and isinstance(room_hint.get("name"), str) and room_hint["name"].strip():
            encounter_name = room_hint["name"].strip()

        seed_components = [
            source_label,
            environment,
            location_name,
            session.state.level.level_id,
            encounter_name,
        ]
        if room_hint and isinstance(room_hint.get("theme"), str):
            seed_components.append(room_hint["theme"])
        if room_hint and isinstance(room_hint.get("room_type"), str):
            seed_components.append(room_hint["room_type"])

        seed = zlib.adler32(":".join(seed_components).encode("utf-8"))
        floor = generate_dungeon_floor(
            level_id=f"{session.state.level.level_id}:combat:{seed}",
            depth=session.state.level.depth,
            environment=environment,
            name=encounter_name,
            seed=seed,
            profile=profile,
        )

        prior_messages = list(session.state.messages)
        session.snapshot_current_state()
        combat_state = DungeonMapState(
            level=floor.level,
            player_pos=floor.level.player_pos,
            entities=build_map_entities_from_roster(floor.entity_roster),
            messages=prior_messages,
        )
        session.state = combat_state
        session.level_states[floor.level.level_id] = combat_state
        session.location = encounter_name
        session.current_environment_id = floor.level.environment
        session.generation_profile = profile

        self._sync_engine_environment_context(profile, fallback_location=encounter_name)
        self.return_to_dungeon_view(
            narrative_lines=narrative_lines,
            scene_art=scene_art,
            info_update=info_update,
        )

    def travel_to_destination(self, request_text: str) -> TravelDestination:
        """Resolve a travel request and mount a matching dungeon session."""
        session, destination = self.build_destination_session(request_text)
        self.dungeon_session = session
        return destination

    def open_dungeon_view(self, *, seed_story: StoryStart | None = None) -> None:
        """Switch to the dungeon screen, creating a session if needed."""
        if seed_story is not None or self.dungeon_session is None:
            self.dungeon_session = self.build_dungeon_session(seed_story or self._story_start)
        self.switch_screen(DungeonScreen(state=self.dungeon_session.state))

    def open_text_view(
        self,
        *,
        restored_state: dict[str, Any] | None = None,
        story_start: StoryStart | None = None,
        speaking_npc_id: str | None = None,
    ) -> None:
        """Switch to the narrative screen with optional restored UI state."""
        if restored_state is not None and self.dungeon_session is not None:
            merged_state = dict(restored_state)
            pending_context = self.dungeon_session.pending_text_context
            scene_art = pending_context.get("scene_art")
            if scene_art is not None and not merged_state.get("current_scene_art"):
                merged_state["current_scene_art"] = scene_art
            pending_info_update = {
                key: value
                for key, value in pending_context.items()
                if key != "scene_art"
            }
            if pending_info_update and "info_panel" not in merged_state:
                merged_info_update = dict(merged_state.get("info_update") or {})
                for key, value in pending_info_update.items():
                    merged_info_update.setdefault(key, value)
                if merged_info_update:
                    merged_state["info_update"] = merged_info_update
            restored_state = merged_state
            self.dungeon_session.pending_text_context.clear()
        self.switch_screen(
            GameScreen(
                restored_state=restored_state,
                story_start=story_start,
                speaking_npc_id=speaking_npc_id,
            )
        )

    def open_hall_of_dead_view(self) -> None:
        """Switch to the Hall of the Dead screen."""
        self.switch_screen(HallOfDeadScreen())

    def return_to_menu_view(self) -> None:
        """Return to the main menu."""
        self.switch_screen(MenuScreen())

    def begin_new_game(self, player_name: str, story_start: StoryStart) -> None:
        """Create engine and dungeon state for a new game, then enter text view."""
        engine = GameEngine(player_name=player_name)
        engine.apply_story_start(story_start)
        self.game_engine = engine
        self.save_slot = _generate_slot_id()
        self._story_start = story_start
        self.dungeon_session = self.build_dungeon_session(story_start)
        restored_state = self.dungeon_session.to_text_restore_state(
            [story_start.intro_narrative],
            scene_art=story_start.scene_art,
            info_update=story_start.info_overrides,
        )
        self.open_text_view(
            restored_state=restored_state,
            story_start=story_start,
        )

    def return_to_dungeon_view(
        self,
        *,
        narrative_lines: list[str] | None = None,
        scene_art: str | None = None,
        info_update: dict[str, str] | None = None,
    ) -> None:
        """Return from text view to the persistent dungeon session."""
        if self.dungeon_session is None:
            self.dungeon_session = self.build_dungeon_session(self._story_start)
        if narrative_lines:
            self.dungeon_session.state.messages.extend(narrative_lines)
        if scene_art:
            self.dungeon_session.pending_text_context["scene_art"] = scene_art
        if info_update:
            self.game_engine._info_panel.update(dict(info_update))
            self.dungeon_session.pending_text_context.update(info_update)
        self.open_dungeon_view()

    def travel_dungeon_transition(self) -> None:
        """Traverse a dungeon transition tile into a new or previous level."""
        if self.dungeon_session is None:
            self.dungeon_session = self.build_dungeon_session(self._story_start)
        session = self.dungeon_session
        current = session.state
        if current.player_pos is None:
            return

        session.snapshot_current_state()
        current_pos = current.player_pos
        current_terrain = current.level.get_terrain(*current_pos)
        transition_label = transition_terrain_label(current_terrain)

        if current_pos in current.level.stairs_up and session.level_stack:
            previous_level_id = session.level_stack.pop()
            previous_state = session.level_states.get(previous_level_id)
            if previous_state is None:
                current.append_message("The route above is lost to static.")
                return
            previous_state.append_message(
                f"You return via the {transition_label} to {previous_state.level.name}."
            )
            session.state = previous_state
            session.location = previous_state.level.name
            session.current_environment_id = previous_state.level.environment
            self.open_dungeon_view()
            return

        if current_pos in current.level.stairs_down:
            session.level_stack.append(current.level.level_id)
            next_depth = current.level.depth + 1
            next_level_id = f"{current.level.level_id}:depth-{next_depth}"
            next_state = session.level_states.get(next_level_id)
            if next_state is None:
                profile = session.generation_profile
                floor = generate_dungeon_floor(
                    level_id=next_level_id,
                    depth=next_depth,
                    environment=session.current_environment_id or current.level.environment,
                    name=f"{session.location or current.level.name} Depth {next_depth}",
                    seed=zlib.adler32(next_level_id.encode("utf-8")),
                    profile=profile,
                )
                next_state = DungeonMapState(
                    level=floor.level,
                    player_pos=floor.level.player_pos,
                    entities=build_map_entities_from_roster(floor.entity_roster),
                    messages=[
                        f"You travel via the {transition_label} to {floor.level.name}.",
                    ],
                )
                session.level_states[next_level_id] = next_state
            else:
                next_state.append_message(
                    f"You travel via the {transition_label} to {next_state.level.name}."
                )
            session.state = next_state
            session.location = next_state.level.name
            session.current_environment_id = next_state.level.environment
            self.open_dungeon_view()
            return

        current.append_message(f"The {transition_label} does not respond.")

    def archive_player_death(self, record: DeathRecord) -> None:
        """Persist a death record, delete the live save, and open the memorial hall."""
        manager = SaveManager()
        try:
            manager.save_death_record(record)
            if self.save_slot:
                manager.delete_save(self.save_slot)
        except Exception as exc:
            logger.error("Failed to archive player death: %s", exc)
        finally:
            self.save_slot = None
            self.dungeon_session = None
            self.game_engine = GameEngine()
            self.open_hall_of_dead_view()

    async def handle_player_death(self, death_context: dict[str, Any]) -> DeathRecord:
        """Generate, archive, and display the memorial for a fallen run."""
        narrative = await self.game_engine.generate_death_narrative(death_context)
        location = str(death_context.get("location", "Unknown Depths"))
        turns_survived = int(death_context.get("turns_survived", self.game_engine.turn_count))
        enemies_slain = int(death_context.get("enemies_slain", 0))
        deepest_level_reached = int(death_context.get("deepest_level_reached", 0))
        cause_of_death = narrative.cause_of_death or str(
            death_context.get("cause_of_death", "Unknown")
        )
        record = DeathRecord(
            record_id=generate_death_record_id(),
            timestamp=time.time(),
            player_name=self.game_engine.player_name,
            location=location,
            turns_survived=turns_survived,
            enemies_slain=enemies_slain,
            deepest_level_reached=deepest_level_reached,
            cause_of_death=cause_of_death,
            summary=narrative.summary,
            save_slot_id=self.save_slot,
            story_start_id=self._story_start.id if self._story_start else None,
        )
        self.archive_player_death(record)
        return record

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
