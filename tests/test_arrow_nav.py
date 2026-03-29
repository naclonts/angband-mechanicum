"""Tests for the shared menu-navigation contract."""

from __future__ import annotations

from typing import Any

import pytest

from angband_mechanicum.app import AngbandMechanicumApp
from angband_mechanicum.screens.api_key_screen import ApiKeyScreen
from angband_mechanicum.screens.character_setup_screen import CharacterSetupScreen
from angband_mechanicum.screens.game_screen import GameScreen
from angband_mechanicum.screens.hall_of_dead_screen import HallOfDeadScreen
from angband_mechanicum.screens.menu_screen import MenuScreen
from angband_mechanicum.screens.story_select_screen import StorySelectScreen
from textual.widgets import Button, Input

APP_SIZE: tuple[int, int] = (120, 40)


async def _open_new_game_flow(
    pilot: Any,
    app: AngbandMechanicumApp,
) -> None:
    await pilot.click("#btn-new")
    await pilot.pause()
    assert isinstance(app.screen, CharacterSetupScreen)


async def _reach_story_select(
    pilot: Any,
    app: AngbandMechanicumApp,
    *,
    player_name: str = "Magos Test",
) -> None:
    await _open_new_game_flow(pilot, app)

    name_input = app.screen.query_one("#charsetup-input", Input)
    name_input.value = player_name
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, StorySelectScreen)


class TestMenuScreenArrowNav:
    """Menu screens should focus actionable controls in DOM order."""

    @pytest.mark.asyncio
    async def test_default_focus_and_arrow_cycle(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            assert isinstance(app.screen, MenuScreen)
            btn_new = app.screen.query_one("#btn-new", Button)
            btn_load = app.screen.query_one("#btn-load", Button)
            btn_hall = app.screen.query_one("#btn-hall", Button)

            await pilot.pause()
            assert app.screen.focused is btn_new

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is btn_load

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is btn_hall

            await pilot.press("up")
            await pilot.pause()
            assert app.screen.focused is btn_load

    @pytest.mark.asyncio
    async def test_enter_activates_the_focused_primary_button(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            assert isinstance(app.screen, MenuScreen)
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, CharacterSetupScreen)


class TestCharacterSetupArrowNav:
    """Character setup should treat the input and buttons as one nav list."""

    @pytest.mark.asyncio
    async def test_default_focus_arrow_cycle_and_enter_submission(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _open_new_game_flow(pilot, app)

            name_input = app.screen.query_one("#charsetup-input", Input)
            btn_confirm = app.screen.query_one("#btn-confirm", Button)
            btn_suggest = app.screen.query_one("#btn-suggest-0", Button)

            await pilot.pause()
            assert app.screen.focused is name_input

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is btn_confirm

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is btn_suggest

            await pilot.press("up")
            await pilot.pause()
            assert app.screen.focused is btn_confirm

            name_input.value = "Magos Test"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, StorySelectScreen)


class TestStorySelectArrowNav:
    """Story selection should skip the scroll container and focus buttons."""

    @pytest.mark.asyncio
    async def test_default_focus_and_arrow_cycle(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _reach_story_select(pilot, app)

            btn_random = app.screen.query_one("#btn-random", Button)
            story_one = app.screen.query_one("#story-silent-forge", Button)
            story_two = app.screen.query_one("#story-xenos-incursion", Button)

            await pilot.pause()
            assert app.screen.focused is btn_random

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is story_one

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is story_two

            await pilot.press("up")
            await pilot.pause()
            assert app.screen.focused is story_one

    @pytest.mark.asyncio
    async def test_enter_activates_the_focused_story_choice(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _reach_story_select(pilot, app)

            await pilot.pause()
            assert isinstance(app.screen.focused, Button)

            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, GameScreen)


class TestApiKeyArrowNav:
    """API-key setup should keep the input first and Enter should submit it."""

    @pytest.mark.asyncio
    async def test_default_focus_and_enter_submission(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            assert isinstance(app.screen, ApiKeyScreen)
            key_input = app.screen.query_one("#apikey-input", Input)
            btn_session = app.screen.query_one("#btn-session", Button)
            btn_save = app.screen.query_one("#btn-save-env", Button)

            await pilot.pause()
            assert app.screen.focused is key_input

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is btn_session

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is btn_save

            await pilot.press("up")
            await pilot.pause()
            assert app.screen.focused is btn_session

            key_input.focus()
            key_input.value = "sk-test-key"
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, MenuScreen)


class TestHallOfDeadArrowNav:
    """The hall should keep focus on the single actionable control."""

    @pytest.mark.asyncio
    async def test_default_focus_and_single_control_navigation(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            assert isinstance(app.screen, MenuScreen)
            await pilot.click("#btn-hall")
            await pilot.pause()

            assert isinstance(app.screen, HallOfDeadScreen)
            btn_back = app.screen.query_one("#btn-back", Button)

            await pilot.pause()
            assert app.screen.focused is btn_back

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.focused is btn_back

            await pilot.press("up")
            await pilot.pause()
            assert app.screen.focused is btn_back
