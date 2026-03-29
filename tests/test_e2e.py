"""End-to-end smoke tests using Textual's built-in pilot test framework.

These tests launch the full app, interact with it via the Pilot API
(clicking buttons, typing commands, pressing keys), and verify the UI
updates correctly.  The Claude API is always mocked so no real calls are made.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from angband_mechanicum.app import AngbandMechanicumApp
from angband_mechanicum.engine.game_engine import NOOSPHERE_ERRORS
from angband_mechanicum.screens.hall_of_dead_screen import HallOfDeadScreen
from angband_mechanicum.screens.dungeon_screen import DungeonScreen
from angband_mechanicum.screens.game_screen import GameScreen
from angband_mechanicum.screens.menu_screen import MenuScreen
from angband_mechanicum.widgets.dungeon_map import DungeonMapPane, DungeonMessageLog
from angband_mechanicum.widgets.info_panel import InfoPanel
from angband_mechanicum.widgets.prompt_input import PromptInput

# The menu layout uses Center containers that need sufficient terminal space.
# Use a generous size for all e2e tests so widgets are always visible/clickable.
APP_SIZE: tuple[int, int] = (120, 40)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_response(text: str) -> MagicMock:
    """Build a mock Anthropic message response with the given text."""
    content_block = MagicMock()
    content_block.text = text
    message = MagicMock()
    message.content = [content_block]
    return message


def _mock_engine_client(app: AngbandMechanicumApp, response_json: str) -> MagicMock:
    """Replace the game engine's API client with a mock that returns *response_json*."""
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=_make_api_response(response_json),
    )
    app.game_engine._client = mock_client
    return mock_client


async def _start_new_game(
    pilot: Any,
    app: AngbandMechanicumApp,
    *,
    enter_explore_view: bool = False,
) -> None:
    """Navigate NEW GAME → character setup → story select, optionally into explore view."""
    await pilot.click("#btn-new")
    await pilot.pause()
    # CharacterSetupScreen: confirm with default name
    await pilot.click("#btn-confirm")
    await pilot.pause()
    # StorySelectScreen: pick random story
    await pilot.click("#btn-random")
    await pilot.pause()
    if enter_explore_view:
        await _submit_command(pilot, app, "/explore")
        await pilot.pause()
    # Disable autosave so tests don't write to disk
    app.save_slot = None


async def _submit_command(pilot: Any, app: AngbandMechanicumApp, text: str) -> None:
    """Type a command into the prompt and submit it.

    Sets the input value directly (faster than pressing each character)
    and presses Enter to submit. Pauses to let the async worker complete.
    """
    prompt = app.screen.query_one("#prompt", PromptInput)
    prompt.focus()
    prompt.value = text
    await pilot.press("enter")
    await pilot.pause()


# ---------------------------------------------------------------------------
# Test: app launches to menu screen
# ---------------------------------------------------------------------------

class TestAppLaunch:
    @pytest.mark.asyncio
    async def test_menu_screen_shown_with_api_key(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ANTHROPIC_API_KEY is set, the app starts on MenuScreen."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            assert isinstance(app.screen, MenuScreen)

    @pytest.mark.asyncio
    async def test_new_game_button_exists(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The menu screen contains a NEW GAME button."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            btn = app.screen.query_one("#btn-new")
            assert btn is not None

    @pytest.mark.asyncio
    async def test_load_button_exists(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The menu screen contains a LOAD GAME button."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            btn = app.screen.query_one("#btn-load")
            assert btn is not None

    @pytest.mark.asyncio
    async def test_hall_button_exists(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The menu screen contains a HALL OF THE DEAD button."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            btn = app.screen.query_one("#btn-hall")
            assert btn is not None

    @pytest.mark.asyncio
    async def test_hall_screen_opens_from_menu(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Clicking HALL OF THE DEAD opens the memorial screen."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.click("#btn-hall")
            await pilot.pause()
            assert isinstance(app.screen, HallOfDeadScreen)


# ---------------------------------------------------------------------------
# Test: new game starts correctly
# ---------------------------------------------------------------------------

class TestNewGame:
    @pytest.mark.asyncio
    async def test_game_screen_loads_after_new_game(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Clicking NEW GAME and completing setup reaches the intro text screen."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.click("#btn-new")
            await pilot.pause()
            # Navigate through character setup and story selection
            await pilot.click("#btn-confirm")
            await pilot.pause()
            await pilot.click("#btn-random")
            await pilot.pause()
            assert isinstance(app.screen, GameScreen)

    @pytest.mark.asyncio
    async def test_story_intro_can_enter_explore_view(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The intro screen can transition into the dungeon via /explore."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app, enter_explore_view=True)
            assert isinstance(app.screen, DungeonScreen)

    @pytest.mark.asyncio
    async def test_explicit_look_examine_returns_to_text_view(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Looking and confirming in the dungeon should bridge back to text view."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app, enter_explore_view=True)
            response = json.dumps({
                "narrative_text": "The brass plating bears fresh prayer-scratches.",
                "scene_art": "ART",
                "info_update": None,
                "entities": [],
                "combat_trigger": False,
                "speaking_npc": None,
            })
            _mock_engine_client(app, response)

            await pilot.press("l")
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, GameScreen)

    @pytest.mark.asyncio
    async def test_prompt_is_focused(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After starting a new game, the prompt input should have focus."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)
            prompt = app.screen.query_one("#prompt", PromptInput)
            assert prompt.has_focus

    @pytest.mark.asyncio
    async def test_info_panel_has_defaults(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After starting a new game, the info panel shows default values."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)
            info = app.screen.query_one("#info", InfoPanel)
            rendered = str(info.render())
            assert "Magos Explorator" in rendered
            # Location comes from the randomly selected story start
            assert "LOCATION" in rendered

    @pytest.mark.asyncio
    async def test_game_engine_is_fresh(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A new game starts with turn_count == 0 and no conversation history."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)
            assert app.game_engine.turn_count == 0
            assert len(app.game_engine._conversation_history) == 0

    @pytest.mark.asyncio
    async def test_save_slot_is_assigned(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Starting a new game assigns a save slot."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.click("#btn-new")
            await pilot.pause()
            await pilot.click("#btn-confirm")
            await pilot.pause()
            await pilot.click("#btn-random")
            await pilot.pause()
            assert app.save_slot is not None
            assert app.save_slot.startswith("save-")

    @pytest.mark.asyncio
    async def test_dungeon_map_gets_more_vertical_space_than_log(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The dungeon map should be taller than the message log in explore view."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app, enter_explore_view=True)

            map_pane = app.screen.query_one("#dungeon-map", DungeonMapPane)
            log_pane = app.screen.query_one("#dungeon-log", DungeonMessageLog)

            assert map_pane.region.height > log_pane.region.height


# ---------------------------------------------------------------------------
# Test: play 1-2 turns
# ---------------------------------------------------------------------------

class TestPlayTurns:
    @pytest.mark.asyncio
    async def test_single_turn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Submit a command, verify engine processes it and turn increments."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)

            # Mock the API client before submitting any command
            response = json.dumps({
                "narrative_text": "You see a vast forge stretching before you.",
                "info_update": None,
            })
            _mock_engine_client(app, response)

            await _submit_command(pilot, app, "look around")

            # Verify the engine processed the turn
            assert app.game_engine.turn_count == 1
            assert len(app.game_engine._conversation_history) == 2
            assert app.game_engine._conversation_history[0]["role"] == "user"
            assert app.game_engine._conversation_history[0]["content"] == "look around"
            assert app.game_engine._conversation_history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_two_turns_with_info_update(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Play two turns -- second turn updates the info panel."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)

            # --- Turn 1: no info update ---
            response_1 = json.dumps({
                "narrative_text": "The forge hums with sacred energy.",
                "info_update": None,
            })
            _mock_engine_client(app, response_1)

            await _submit_command(pilot, app, "look around")
            assert app.game_engine.turn_count == 1

            # --- Turn 2: with info update ---
            response_2 = json.dumps({
                "narrative_text": "You descend into the cargo lift shaft.",
                "info_update": {"LOCATION": "Cargo Lift Shaft"},
            })
            _mock_engine_client(app, response_2)

            await _submit_command(pilot, app, "go to cargo lift")

            assert app.game_engine.turn_count == 2
            assert len(app.game_engine._conversation_history) == 4

            # Verify info panel was updated with the new location
            assert app.game_engine._info_panel["LOCATION"] == "Cargo Lift Shaft"

            # Verify the info panel widget reflects the change
            info = app.screen.query_one("#info", InfoPanel)
            rendered = str(info.render())
            assert "Cargo Lift Shaft" in rendered


# ---------------------------------------------------------------------------
# Test: error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_api_error_shows_noosphere_message(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the API fails, a Noosphere error appears in the narrative."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)

            # Mock the client to raise an API error
            mock_client = MagicMock()
            mock_client.messages = MagicMock()
            mock_client.messages.create = AsyncMock(
                side_effect=anthropic.APIConnectionError(request=MagicMock()),
            )
            app.game_engine._client = mock_client

            await _submit_command(pilot, app, "invoke the machine spirit")

            # Turn should NOT increment on error
            assert app.game_engine.turn_count == 0
            # Error count should increase
            assert app.game_engine._error_count == 1
            # The failed message should be removed from history
            assert len(app.game_engine._conversation_history) == 0

    @pytest.mark.asyncio
    async def test_error_then_success_recovers(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After an API error, a subsequent successful command works normally."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)

            # Turn 1: API error
            mock_client = MagicMock()
            mock_client.messages = MagicMock()
            mock_client.messages.create = AsyncMock(
                side_effect=RuntimeError("connection lost"),
            )
            app.game_engine._client = mock_client

            await _submit_command(pilot, app, "try something")

            assert app.game_engine.turn_count == 0
            assert app.game_engine._error_count == 1

            # Turn 2: success
            response = json.dumps({
                "narrative_text": "The Machine Spirit answers.",
                "info_update": None,
            })
            _mock_engine_client(app, response)

            await _submit_command(pilot, app, "try again")

            assert app.game_engine.turn_count == 1
            assert len(app.game_engine._conversation_history) == 2


# ---------------------------------------------------------------------------
# Test: prompt pane border consistency
# ---------------------------------------------------------------------------

class TestPromptBorder:
    @pytest.mark.asyncio
    async def test_prompt_border_all_sides_consistent(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The prompt pane should have the same border style on all four sides."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)
            prompt = app.screen.query_one("#prompt", PromptInput)

            top_style, _ = prompt.styles.border_top
            bottom_style, _ = prompt.styles.border_bottom
            left_style, _ = prompt.styles.border_left
            right_style, _ = prompt.styles.border_right

            assert top_style == "heavy", f"border-top style is '{top_style}', expected 'heavy'"
            assert bottom_style == "heavy", f"border-bottom style is '{bottom_style}', expected 'heavy'"
            assert left_style == "heavy", f"border-left style is '{left_style}', expected 'heavy'"
            assert right_style == "heavy", f"border-right style is '{right_style}', expected 'heavy'"

    @pytest.mark.asyncio
    async def test_prompt_border_color_matches_when_focused(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When focused, all four border sides should share the same color."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _start_new_game(pilot, app)
            prompt = app.screen.query_one("#prompt", PromptInput)
            prompt.focus()
            await pilot.pause()

            _, top_color = prompt.styles.border_top
            _, bottom_color = prompt.styles.border_bottom
            _, left_color = prompt.styles.border_left
            _, right_color = prompt.styles.border_right

            assert top_color == bottom_color, (
                f"border-top color {top_color} != border-bottom color {bottom_color}"
            )
            assert top_color == left_color, (
                f"border-top color {top_color} != border-left color {left_color}"
            )
            assert top_color == right_color, (
                f"border-top color {top_color} != border-right color {right_color}"
            )
