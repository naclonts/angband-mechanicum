"""Save manager -- handles serialization/deserialization of game state to JSON files."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)


def _saves_dir() -> Path:
    """Return the save directory, respecting XDG_DATA_HOME."""
    xdg_data: str = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    save_path: Path = Path(xdg_data) / "angband-mechanicum" / "saves"
    save_path.mkdir(parents=True, exist_ok=True)
    return save_path


@dataclass
class SaveMetadata:
    """Summary info about a save file for display in the load menu."""

    slot_id: str
    timestamp: float
    location: str
    turn_count: int
    file_path: Path

    @property
    def display_time(self) -> str:
        """Human-readable timestamp."""
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.timestamp))


class SaveManager:
    """Manages saving and loading game state as JSON files."""

    def __init__(self) -> None:
        self._saves_dir: Path = _saves_dir()

    def save(self, slot_id: str, state: dict[str, Any]) -> Path:
        """Write game state to a JSON save file. Returns the file path."""
        state["meta"] = {
            "slot_id": slot_id,
            "timestamp": time.time(),
            "save_version": 1,
        }
        file_path: Path = self._saves_dir / f"{slot_id}.json"
        tmp_path: Path = file_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
            tmp_path.replace(file_path)
            logger.info("Game saved to %s", file_path)
        except OSError as exc:
            logger.error("Failed to save game: %s", exc)
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        return file_path

    def load(self, slot_id: str) -> dict[str, Any]:
        """Load game state from a JSON save file."""
        file_path: Path = self._saves_dir / f"{slot_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"No save file found: {file_path}")
        text: str = file_path.read_text()
        state: dict[str, Any] = json.loads(text)
        logger.info("Game loaded from %s", file_path)
        return state

    def list_saves(self) -> list[SaveMetadata]:
        """Return metadata for all save files, newest first."""
        saves: list[SaveMetadata] = []
        for path in self._saves_dir.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(path.read_text())
                meta: dict[str, Any] = data.get("meta", {})
                info: dict[str, str] = data.get("info_panel", {})
                saves.append(SaveMetadata(
                    slot_id=meta.get("slot_id", path.stem),
                    timestamp=meta.get("timestamp", path.stat().st_mtime),
                    location=info.get("LOCATION", "Unknown"),
                    turn_count=data.get("turn_count", 0),
                    file_path=path,
                ))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping corrupt save %s: %s", path, exc)
                continue
        saves.sort(key=lambda s: s.timestamp, reverse=True)
        return saves

    def delete_save(self, slot_id: str) -> None:
        """Delete a save file."""
        file_path: Path = self._saves_dir / f"{slot_id}.json"
        if file_path.exists():
            file_path.unlink()
            logger.info("Deleted save %s", file_path)
