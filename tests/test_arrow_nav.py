"""Tests for arrow-key navigation on menu screens.

Verifies that Up/Down arrow keys cycle focus between buttons, matching
the existing Tab / Shift+Tab behaviour.
"""

from __future__ import annotations

import pytest

from angband_mechanicum.app import AngbandMechanicumApp
from angband_mechanicum.screens.menu_screen import MenuScreen
from angband_mechanicum.screens.story_select_screen import StorySelectScreen
from angband_mechanicum.screens.character_setup_screen import CharacterSetupScreen
from angband_mechanicum.screens.api_key_screen import ApiKeyScreen
from textual.widgets import Button, Input

APP_SIZE: tuple[int, int] = (120, 40)


class TestMenuScreenArrowNav:
    """Arrow keys cycle focus on the main menu."""

    @pytest.mark.asyncio
    async def test_down_arrow_moves_to_next_button(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            assert isinstance(app.screen, MenuScreen)
            btn_new = app.screen.query_one("#btn-new", Button)
            btn_load = app.screen.query_one("#btn-load", Button)
            btn_new.focus()
            await pilot.pause()
            assert btn_new.has_focus

            await pilot.press("down")
            await pilot.pause()
            assert btn_load.has_focus

    @pytest.mark.asyncio
    async def test_up_arrow_moves_to_previous_button(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            assert isinstance(app.screen, MenuScreen)
            btn_new = app.screen.query_one("#btn-new", Button)
            btn_load = app.screen.query_one("#btn-load", Button)
            btn_load.focus()
            await pilot.pause()
            assert btn_load.has_focus

            await pilot.press("up")
            await pilot.pause()
            assert btn_new.has_focus

    @pytest.mark.asyncio
    async def test_down_arrow_cycles_through_all_menu_buttons(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            btn_new = app.screen.query_one("#btn-new", Button)
            btn_load = app.screen.query_one("#btn-load", Button)
            btn_hall = app.screen.query_one("#btn-hall", Button)
            btn_new.focus()
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()
            assert btn_load.has_focus

            await pilot.press("down")
            await pilot.pause()
            assert btn_hall.has_focus


class TestStorySelectArrowNav:
    """Arrow keys cycle focus on the story select screen."""

    @pytest.mark.asyncio
    async def test_down_arrow_navigates_story_buttons(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            # Navigate to story select screen
            await pilot.click("#btn-new")
            await pilot.pause()
            await pilot.click("#btn-confirm")
            await pilot.pause()
            assert isinstance(app.screen, StorySelectScreen)

            btn_random = app.screen.query_one("#btn-random", Button)
            btn_random.focus()
            await pilot.pause()
            assert btn_random.has_focus

            await pilot.press("down")
            await pilot.pause()
            # Should move to the first story entry
            focused = app.screen.focused
            assert focused is not None
            assert focused is not btn_random


class TestCharacterSetupArrowNav:
    """Arrow keys cycle focus on the character setup screen."""

    @pytest.mark.asyncio
    async def test_down_from_input_to_confirm(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.click("#btn-new")
            await pilot.pause()
            assert isinstance(app.screen, CharacterSetupScreen)

            name_input = app.screen.query_one("#charsetup-input", Input)
            btn_confirm = app.screen.query_one("#btn-confirm", Button)
            name_input.focus()
            await pilot.pause()
            assert name_input.has_focus

            await pilot.press("down")
            await pilot.pause()
            assert btn_confirm.has_focus

    @pytest.mark.asyncio
    async def test_up_from_confirm_to_input(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.click("#btn-new")
            await pilot.pause()
            assert isinstance(app.screen, CharacterSetupScreen)

            name_input = app.screen.query_one("#charsetup-input", Input)
            btn_confirm = app.screen.query_one("#btn-confirm", Button)
            btn_confirm.focus()
            await pilot.pause()
            assert btn_confirm.has_focus

            await pilot.press("up")
            await pilot.pause()
            assert name_input.has_focus
