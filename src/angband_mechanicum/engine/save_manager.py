"""Save manager -- handles serialization/deserialization of game state to JSON files."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

logger: logging.Logger = logging.getLogger(__name__)


def save_state_allows_resume(state: Mapping[str, Any]) -> bool:
    """Return whether a serialized save still represents a live run."""
    integrity = state.get("integrity")
    if integrity is None:
        return True
    try:
        return int(integrity) > 0
    except (TypeError, ValueError):
        return True


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


@dataclass
class DeathRecord:
    """Persisted summary of a fallen Tech-Priest."""

    record_id: str
    timestamp: float
    player_name: str
    location: str
    turns_survived: int
    enemies_slain: int
    deepest_level_reached: int
    cause_of_death: str
    summary: str
    save_slot_id: str | None = None
    story_start_id: str | None = None

    @property
    def display_time(self) -> str:
        """Human-readable timestamp."""
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.timestamp))

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "player_name": self.player_name,
            "location": self.location,
            "turns_survived": self.turns_survived,
            "enemies_slain": self.enemies_slain,
            "deepest_level_reached": self.deepest_level_reached,
            "cause_of_death": self.cause_of_death,
            "summary": self.summary,
            "save_slot_id": self.save_slot_id,
            "story_start_id": self.story_start_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeathRecord:
        meta: dict[str, Any] = data.get("meta", {})
        record_id = data.get("record_id") or meta.get("record_id") or data.get("id")
        return cls(
            record_id=str(record_id) if record_id is not None else "",
            timestamp=float(data.get("timestamp", meta.get("timestamp", 0.0))),
            player_name=str(data.get("player_name", "Unknown Tech-Priest")),
            location=str(data.get("location", "Unknown Depths")),
            turns_survived=int(data.get("turns_survived", 0)),
            enemies_slain=int(data.get("enemies_slain", 0)),
            deepest_level_reached=int(data.get("deepest_level_reached", 0)),
            cause_of_death=str(data.get("cause_of_death", "Unknown")),
            summary=str(data.get("summary", "")),
            save_slot_id=(
                str(data.get("save_slot_id"))
                if data.get("save_slot_id") is not None
                else None
            ),
            story_start_id=(
                str(data.get("story_start_id"))
                if data.get("story_start_id") is not None
                else None
            ),
        )


class SaveManager:
    """Manages saving and loading game state as JSON files."""

    def __init__(self) -> None:
        self._saves_dir: Path = _saves_dir()
        self._deaths_dir: Path = self._saves_dir.parent / "hall_of_dead"
        self._deaths_dir.mkdir(parents=True, exist_ok=True)

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
        """Return metadata for resumable save files, newest first."""
        saves: list[SaveMetadata] = []
        for path in self._saves_dir.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(path.read_text())
                if not save_state_allows_resume(data):
                    logger.info("Skipping non-resumable save %s", path)
                    continue
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

    def save_death_record(self, record: DeathRecord) -> Path:
        """Persist a death record for the Hall of the Dead."""
        file_path: Path = self._deaths_dir / f"{record.record_id}.json"
        tmp_path: Path = file_path.with_suffix(".json.tmp")
        payload = record.to_dict()
        payload["meta"] = {
            "record_id": record.record_id,
            "timestamp": record.timestamp,
            "save_version": 1,
        }
        try:
            tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            tmp_path.replace(file_path)
            logger.info("Saved death record to %s", file_path)
        except OSError as exc:
            logger.error("Failed to save death record: %s", exc)
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        return file_path

    def list_death_records(self) -> list[DeathRecord]:
        """Return Hall of the Dead entries, newest first."""
        records: list[DeathRecord] = []
        for path in self._deaths_dir.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(path.read_text())
                record = DeathRecord.from_dict(data)
                if not record.record_id:
                    record.record_id = path.stem
                records.append(record)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                logger.warning("Skipping corrupt death record %s: %s", path, exc)
                continue
        records.sort(key=lambda record: record.timestamp, reverse=True)
        return records


def generate_death_record_id() -> str:
    """Generate a unique record ID for the Hall of the Dead."""
    return f"death-{uuid.uuid4().hex}"
