"""Tests for the exploration-scale dungeon level FOV model."""

from __future__ import annotations

import pytest

from angband_mechanicum.engine.dungeon_level import (
    ENVIRONMENTS,
    DungeonLevel,
    DungeonTerrain,
    FogState,
    DungeonTile,
    hazard_damage_for_terrain,
)


def make_level(width: int = 7, height: int = 7) -> DungeonLevel:
    """Create a small all-floor level for visibility tests."""
    return DungeonLevel(
        level_id="test-level",
        name="Test Level",
        depth=1,
        environment="forge",
        width=width,
        height=height,
    )


class TestDungeonLevelFov:
    def test_compute_fov_marks_visible_tiles(self) -> None:
        level = make_level()

        visible = level.compute_fov((3, 3), radius=2)

        assert (3, 3) in visible
        assert level.is_visible(3, 3)
        assert level.is_visible(3, 5)
        assert level.is_hidden(0, 0)
        assert level.get_tile(0, 0).fog == FogState.HIDDEN
        assert set(level.visible_tiles()) == visible

    def test_compute_fov_promotes_previous_visibility_to_explored(self) -> None:
        level = make_level()

        level.compute_fov((2, 2), radius=1)
        assert level.is_visible(2, 2)
        assert level.is_visible(2, 1)

        level.compute_fov((4, 2), radius=1)

        assert level.is_visible(4, 2)
        assert level.is_explored(2, 2)
        assert level.get_tile(2, 2).fog == FogState.EXPLORED
        assert level.is_hidden(0, 0)

    def test_line_of_sight_blocks_by_wall(self) -> None:
        level = make_level(width=7, height=3)
        level.set_terrain(4, 1, DungeonTerrain.WALL)

        visible = level.compute_fov((2, 1), radius=5)

        assert level.line_of_sight((2, 1), (4, 1)) is True
        assert level.line_of_sight((2, 1), (5, 1)) is False
        assert (4, 1) in visible
        assert (5, 1) not in visible
        assert level.get_tile(4, 1).fog == FogState.VISIBLE
        assert level.get_tile(5, 1).fog == FogState.HIDDEN

    def test_fog_round_trips_through_serialization(self) -> None:
        level = make_level()
        level.compute_fov((3, 3), radius=2)
        level.compute_fov((4, 3), radius=1)

        restored = DungeonLevel.from_dict(level.to_dict())

        assert restored.get_tile(4, 3).fog == FogState.VISIBLE
        assert restored.get_tile(2, 3).fog == FogState.EXPLORED
        assert restored.get_tile(0, 0).fog == FogState.HIDDEN

    def test_item_placements_round_trip_through_serialization(self) -> None:
        level = make_level()
        level.place_item(2, 2, "data-slate")
        level.place_item(2, 2, "toolkit")
        level.place_item(4, 1, "vox-beacon")

        restored = DungeonLevel.from_dict(level.to_dict())

        assert restored.get_items(2, 2) == ["data-slate", "toolkit"]
        assert restored.get_items(4, 1) == ["vox-beacon"]

    def test_negative_radius_is_rejected(self) -> None:
        level = make_level()

        with pytest.raises(ValueError):
            level.compute_fov((3, 3), radius=-1)


class TestTransitionTerrains:
    @pytest.mark.parametrize(
        "terrain",
        [
            DungeonTerrain.ELEVATOR,
            DungeonTerrain.GATE,
            DungeonTerrain.PORTAL,
            DungeonTerrain.LIFT,
        ],
    )
    def test_transition_tiles_round_trip_and_stay_passable(self, terrain: DungeonTerrain) -> None:
        tile = DungeonTile(terrain=terrain)
        restored = DungeonTile.from_dict(tile.to_dict())

        assert restored.terrain == terrain
        assert restored.passable is True
        assert restored.transparent is True


class TestHazardTerrains:
    @pytest.mark.parametrize(
        ("terrain", "expected_damage"),
        [
            (DungeonTerrain.ACID_POOL, 2),
            (DungeonTerrain.LAVA, 5),
        ],
    )
    def test_hazard_tiles_are_passable_and_damage_on_traversal(
        self,
        terrain: DungeonTerrain,
        expected_damage: int,
    ) -> None:
        tile = DungeonTile(terrain=terrain)

        assert tile.passable is True
        assert tile.movement_cost == 2
        assert hazard_damage_for_terrain(terrain) == expected_damage

    def test_lava_deals_more_damage_than_acid(self) -> None:
        assert hazard_damage_for_terrain(DungeonTerrain.LAVA) > hazard_damage_for_terrain(
            DungeonTerrain.ACID_POOL
        )


class TestEnvironmentCatalog:
    def test_environment_catalog_includes_expanded_set(self) -> None:
        expected = {
            "forge",
            "cathedral",
            "hive",
            "sewer",
            "corrupted",
            "overgrown",
            "tomb",
            "manufactorum",
            "voidship",
            "reliquary",
            "radwastes",
            "data_vault",
            "xenos_ruin",
            "ice_crypt",
            "sump_market",
            "plasma_reactorum",
            "penal_oubliette",
            "ash_dune_outpost",
        }

        assert expected.issubset(ENVIRONMENTS.keys())
        assert len(ENVIRONMENTS) >= len(expected)

    def test_new_environments_have_prompt_matching_metadata(self) -> None:
        new_names = (
            "voidship",
            "reliquary",
            "radwastes",
            "data_vault",
            "xenos_ruin",
            "ice_crypt",
            "sump_market",
            "plasma_reactorum",
            "penal_oubliette",
            "ash_dune_outpost",
        )

        for name in new_names:
            env = ENVIRONMENTS[name]
            assert env.description
            assert env.feature_terrains
            assert env.room_types
            assert env.aliases
            assert all(isinstance(alias, str) and alias for alias in env.aliases)
            assert all(isinstance(terrain, DungeonTerrain) for terrain in env.feature_terrains)
            assert all(isinstance(room_type, str) and room_type for room_type in env.room_types)
