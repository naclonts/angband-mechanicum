"""Angband Mechanicum -- main application."""

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from textual.app import App

from angband_mechanicum.engine.game_engine import GameEngine
from angband_mechanicum.engine.story_starts import StoryStart
from angband_mechanicum.screens.api_key_screen import ApiKeyScreen
from angband_mechanicum.screens.dungeon_screen import DungeonMapState, DungeonScreen
from angband_mechanicum.screens.game_screen import GameScreen
from angband_mechanicum.screens.menu_screen import MenuScreen
from angband_mechanicum.engine.dungeon_gen import generate_dungeon_floor
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
    pending_text_context: dict[str, Any] = field(default_factory=dict)

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

    @staticmethod
    def _infer_dungeon_environment(story_start: StoryStart | None) -> str:
        if story_start is None:
            return "forge"

        text = " ".join(
            [
                story_start.id,
                story_start.title,
                story_start.description,
                story_start.location,
            ]
        ).lower()
        if any(keyword in text for keyword in ("sewer", "drain", "sludge", "filth")):
            return "sewer"
        if any(keyword in text for keyword in ("cathedral", "chapel", "shrine", "faith")):
            return "cathedral"
        if any(keyword in text for keyword in ("hive", "underhive", "hab", "stacks")):
            return "hive"
        if any(keyword in text for keyword in ("warp", "chaos", "corrupt", "daemon")):
            return "corrupted"
        if any(keyword in text for keyword in ("overgrow", "fungal", "vine", "jungle")):
            return "overgrown"
        if any(keyword in text for keyword in ("tomb", "crypt", "necron", "burial")):
            return "tomb"
        if any(keyword in text for keyword in ("manufactorum", "factory", "assembly", "hull", "hulk")):
            return "manufactorum"
        return "forge"

    def build_dungeon_session(self, story_start: StoryStart | None = None) -> DungeonSession:
        """Create a fresh dungeon session for the active story."""
        environment = self._infer_dungeon_environment(story_start)
        source = story_start.id if story_start else "default"
        seed = zlib.adler32(source.encode("utf-8"))
        location = story_start.location if story_start else "Unknown Depths"
        floor = generate_dungeon_floor(
            level_id=source,
            depth=1,
            environment=environment,
            name=location,
            seed=seed,
        )
        messages = [story_start.intro_narrative] if story_start else []
        return DungeonSession(
            state=DungeonMapState(
                level=floor.level,
                player_pos=floor.level.player_pos,
                entities=[],
                messages=messages,
            ),
            story_id=story_start.id if story_start else None,
            location=location,
            intro_narrative=story_start.intro_narrative if story_start else None,
        )

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
    ) -> None:
        """Switch to the narrative screen with optional restored UI state."""
        self.switch_screen(GameScreen(restored_state=restored_state, story_start=story_start))

    def begin_new_game(self, player_name: str, story_start: StoryStart) -> None:
        """Create engine and dungeon state for a new game, then enter the dungeon."""
        engine = GameEngine(player_name=player_name)
        engine.apply_story_start(story_start)
        self.game_engine = engine
        self.save_slot = _generate_slot_id()
        self._story_start = story_start
        self.dungeon_session = self.build_dungeon_session(story_start)
        self.open_dungeon_view()

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
            self.dungeon_session.pending_text_context.update(info_update)
        self.open_dungeon_view()

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
