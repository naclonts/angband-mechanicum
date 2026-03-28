"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from angband_mechanicum.engine.game_engine import GameEngine
from angband_mechanicum.engine.save_manager import SaveManager


@pytest.fixture()
def sample_state() -> dict[str, Any]:
    """A minimal valid game state dict."""
    return {
        "conversation_history": [
            {"role": "user", "content": "look around"},
            {"role": "assistant", "content": '{"narrative_text": "You see a forge."}'},
        ],
        "turn_count": 1,
        "current_scene_art": None,
        "info_panel": {"LOCATION": "Forge-Cathedral Alpha"},
        "error_count": 0,
    }


@pytest.fixture()
def engine_with_mock_client() -> GameEngine:
    """A GameEngine whose Anthropic client is mocked out."""
    engine = GameEngine()
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock()
    engine._client = mock_client
    return engine


def _make_api_response(text: str) -> MagicMock:
    """Build a mock Anthropic message response with the given text."""
    content_block = MagicMock()
    content_block.text = text
    message = MagicMock()
    message.content = [content_block]
    return message


@pytest.fixture()
def save_manager(tmp_path: Path) -> SaveManager:
    """A SaveManager that writes to a temp directory."""
    mgr = SaveManager()
    mgr._saves_dir = tmp_path
    return mgr
