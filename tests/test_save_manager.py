"""Tests for the save manager."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from angband_mechanicum.engine.save_manager import DeathRecord, SaveManager, SaveMetadata


class TestSaveLoad:
    def test_save_and_load_round_trip(
        self, save_manager: SaveManager, sample_state: dict[str, Any]
    ) -> None:
        path = save_manager.save("slot-1", sample_state)
        assert path.exists()

        loaded = save_manager.load("slot-1")
        assert loaded["turn_count"] == 1
        assert loaded["info_panel"] == {"LOCATION": "Forge-Cathedral Alpha"}
        # save() injects meta
        assert loaded["meta"]["slot_id"] == "slot-1"
        assert loaded["meta"]["save_version"] == 1

    def test_load_nonexistent_raises(self, save_manager: SaveManager) -> None:
        with pytest.raises(FileNotFoundError):
            save_manager.load("does-not-exist")

    def test_save_is_atomic_no_tmp_left(
        self, save_manager: SaveManager, sample_state: dict[str, Any]
    ) -> None:
        save_manager.save("slot-2", sample_state)
        tmp_files = list(save_manager._saves_dir.glob("*.tmp"))
        assert tmp_files == []


class TestListSaves:
    def test_ordering_newest_first(
        self, save_manager: SaveManager, sample_state: dict[str, Any]
    ) -> None:
        # Save two slots; manually set timestamps to control order
        save_manager.save("old", sample_state)
        save_manager.save("new", sample_state)

        # Patch timestamps in saved files for deterministic ordering
        old_path = save_manager._saves_dir / "old.json"
        new_path = save_manager._saves_dir / "new.json"
        old_data = json.loads(old_path.read_text())
        new_data = json.loads(new_path.read_text())
        old_data["meta"]["timestamp"] = 1000.0
        new_data["meta"]["timestamp"] = 2000.0
        old_path.write_text(json.dumps(old_data))
        new_path.write_text(json.dumps(new_data))

        saves = save_manager.list_saves()
        assert len(saves) == 2
        assert saves[0].slot_id == "new"
        assert saves[1].slot_id == "old"

    def test_corrupt_file_skipped(
        self, save_manager: SaveManager, sample_state: dict[str, Any]
    ) -> None:
        save_manager.save("good", sample_state)
        # Write garbage
        (save_manager._saves_dir / "bad.json").write_text("not json{{{")

        saves = save_manager.list_saves()
        assert len(saves) == 1
        assert saves[0].slot_id == "good"


class TestDeleteSave:
    def test_delete_existing(
        self, save_manager: SaveManager, sample_state: dict[str, Any]
    ) -> None:
        save_manager.save("doomed", sample_state)
        assert (save_manager._saves_dir / "doomed.json").exists()

        save_manager.delete_save("doomed")
        assert not (save_manager._saves_dir / "doomed.json").exists()

    def test_delete_nonexistent_is_noop(self, save_manager: SaveManager) -> None:
        # Should not raise
        save_manager.delete_save("ghost")


class TestDeathRecords:
    def test_save_and_list_death_record(
        self, save_manager: SaveManager
    ) -> None:
        record = DeathRecord(
            record_id="death-1",
            timestamp=1_000.0,
            player_name="Magos Explorator",
            location="Lower Forge",
            turns_survived=12,
            enemies_slain=4,
            deepest_level_reached=3,
            cause_of_death="Crushed by a daemon engine",
            summary="The Tech-Priest fell in glorious service.",
            save_slot_id="slot-1",
            story_start_id="forge-escape",
        )

        path = save_manager.save_death_record(record)

        assert path.exists()

        records = save_manager.list_death_records()
        assert len(records) == 1
        loaded = records[0]
        assert loaded.record_id == "death-1"
        assert loaded.player_name == "Magos Explorator"
        assert loaded.location == "Lower Forge"
        assert loaded.turns_survived == 12
        assert loaded.enemies_slain == 4
        assert loaded.deepest_level_reached == 3
        assert loaded.cause_of_death == "Crushed by a daemon engine"
        assert loaded.summary == "The Tech-Priest fell in glorious service."


class TestSaveMetadata:
    def test_display_time_format(self) -> None:
        meta = SaveMetadata(
            slot_id="test",
            timestamp=0.0,  # epoch
            location="Forge",
            turn_count=5,
            file_path=Path("/tmp/test.json"),
        )
        # Should be a string in YYYY-MM-DD HH:MM format
        assert len(meta.display_time.split("-")) == 3
        assert ":" in meta.display_time
