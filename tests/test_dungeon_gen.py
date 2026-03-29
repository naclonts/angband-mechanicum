"""Tests for the procedural dungeon/room generation system."""

from __future__ import annotations

from collections import Counter
from collections import deque
import random

import pytest

from angband_mechanicum.engine.combat_engine import Grid, Terrain, Tile, auto_place_enemies
from angband_mechanicum.engine.dungeon_level import ENVIRONMENTS, DungeonLevel, DungeonTerrain
from angband_mechanicum.engine.dungeon_entities import DungeonDisposition, DungeonMovementAI
from angband_mechanicum.engine.dungeon_entities import DungeonEntityRoster
from angband_mechanicum.engine.dungeon_gen import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    FEATURE_TYPES,
    FLOOR_DEFAULT_HEIGHT,
    FLOOR_DEFAULT_WIDTH,
    MAX_HEIGHT,
    MAX_WIDTH,
    MIN_HEIGHT,
    MIN_WIDTH,
    ROOM_TYPES,
    DungeonRoom,
    GeneratedFloor,
    GeneratedMap,
    RoomHint,
    SpawnPoints,
    generate_dungeon_floor,
    generate_map,
    generate_map_from_hint,
    _add_doors,
    _BUILDERS,
    _compute_spawns,
    _floor_tiles,
    _contacts_for_environment,
    _group_size_for_archetype,
    _apply_themed_room_template,
    _pick_group_positions,
    _scatter_features,
    _themed_room_templates_for_environment,
)
from angband_mechanicum.engine.dungeon_profiles import DungeonGenerationProfile


def _reachable_tiles(level: DungeonLevel, start: tuple[int, int]) -> set[tuple[int, int]]:
    seen = {start}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in level.get_passable_neighbors(x, y):
            if (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return seen


# ---------------------------------------------------------------------------
# Terrain extension tests
# ---------------------------------------------------------------------------


class TestTerrainExtensions:
    """Verify new terrain types are registered on the Terrain enum."""

    def test_column_exists(self) -> None:
        assert hasattr(Terrain, "COLUMN")
        assert Terrain.COLUMN.value == "column"

    def test_water_exists(self) -> None:
        assert hasattr(Terrain, "WATER")
        assert Terrain.WATER.value == "water"

    def test_growth_exists(self) -> None:
        assert hasattr(Terrain, "GROWTH")
        assert Terrain.GROWTH.value == "growth"

    def test_cover_exists(self) -> None:
        assert hasattr(Terrain, "COVER")
        assert Terrain.COVER.value == "cover"

    def test_column_impassable(self) -> None:
        tile = Tile(Terrain.COLUMN)
        assert tile.passable is False

    def test_water_passable_costly(self) -> None:
        tile = Tile(Terrain.WATER)
        assert tile.passable is True
        assert tile.movement_cost == 2

    def test_growth_passable_costly(self) -> None:
        tile = Tile(Terrain.GROWTH)
        assert tile.passable is True
        assert tile.movement_cost == 2

    def test_cover_passable_costly(self) -> None:
        tile = Tile(Terrain.COVER)
        assert tile.passable is True
        assert tile.movement_cost == 2

    def test_original_terrain_unchanged(self) -> None:
        """Existing terrain types still work correctly after patching."""
        assert Tile(Terrain.FLOOR).passable is True
        assert Tile(Terrain.FLOOR).movement_cost == 1
        assert Tile(Terrain.WALL).passable is False
        assert Tile(Terrain.DEBRIS).passable is True
        assert Tile(Terrain.DEBRIS).movement_cost == 2
        assert Tile(Terrain.TERMINAL).passable is True

    def test_terrain_serialisation_roundtrip(self) -> None:
        """New terrain values survive to_dict/from_dict."""
        for terrain in [Terrain.COLUMN, Terrain.WATER, Terrain.GROWTH, Terrain.COVER]:
            tile = Tile(terrain)
            restored = Tile.from_dict(tile.to_dict())
            assert restored.terrain == terrain


# ---------------------------------------------------------------------------
# RoomHint tests
# ---------------------------------------------------------------------------


class TestRoomHint:
    def test_from_none(self) -> None:
        hint = RoomHint.from_dict(None)
        assert hint.room_type is None
        assert hint.features == []
        assert hint.theme is None

    def test_from_dict_full(self) -> None:
        data = {
            "room_type": "arena",
            "width": 30,
            "height": 20,
            "features": ["water", "debris"],
            "theme": "sewer",
            "name": "Flooded Cistern",
        }
        hint = RoomHint.from_dict(data)
        assert hint.room_type == "arena"
        assert hint.width == 30
        assert hint.height == 20
        assert hint.features == ["water", "debris"]
        assert hint.theme == "sewer"
        assert hint.name == "Flooded Cistern"

    def test_from_dict_partial(self) -> None:
        hint = RoomHint.from_dict({"room_type": "corridor"})
        assert hint.room_type == "corridor"
        assert hint.width is None
        assert hint.features == []


# ---------------------------------------------------------------------------
# GeneratedMap tests
# ---------------------------------------------------------------------------


class TestGeneratedMap:
    def test_to_map_def_structure(self) -> None:
        gm = generate_map(room_type="open_room", seed=42)
        md = gm.to_map_def()
        assert "name" in md
        assert "build" in md
        assert "player_start" in md
        assert "party_starts" in md
        assert "enemies" in md
        # build should return a Grid
        grid = md["build"]()
        assert isinstance(grid, Grid)


# ---------------------------------------------------------------------------
# Generation: every room type
# ---------------------------------------------------------------------------


class TestAllRoomTypes:
    """Ensure every room type generates a valid map."""

    @pytest.mark.parametrize("room_type", ROOM_TYPES)
    def test_generates_valid_grid(self, room_type: str) -> None:
        gm = generate_map(room_type=room_type, seed=123)
        assert isinstance(gm.grid, Grid)
        assert gm.grid.width >= MIN_WIDTH
        assert gm.grid.height >= MIN_HEIGHT
        assert gm.room_type == room_type

    @pytest.mark.parametrize("room_type", ROOM_TYPES)
    def test_has_walls_on_border(self, room_type: str) -> None:
        """Border tiles should be walls (for all standard room types)."""
        gm = generate_map(room_type=room_type, width=24, height=17, seed=999)
        grid = gm.grid
        # Top and bottom rows
        for x in range(grid.width):
            assert grid.get_tile(x, 0).terrain == Terrain.WALL, f"Top border open at x={x}"
            assert grid.get_tile(x, grid.height - 1).terrain == Terrain.WALL, f"Bottom border open at x={x}"
        # Left and right columns
        for y in range(grid.height):
            assert grid.get_tile(0, y).terrain == Terrain.WALL, f"Left border open at y={y}"
            assert grid.get_tile(grid.width - 1, y).terrain == Terrain.WALL, f"Right border open at y={y}"

    @pytest.mark.parametrize("room_type", ROOM_TYPES)
    def test_has_floor_tiles(self, room_type: str) -> None:
        """Every map must have some floor (passable) tiles."""
        gm = generate_map(room_type=room_type, seed=456)
        floor = _floor_tiles(gm.grid)
        assert len(floor) > 0, f"{room_type} produced no floor tiles"

    @pytest.mark.parametrize("room_type", ROOM_TYPES)
    def test_spawn_points_on_passable_tiles(self, room_type: str) -> None:
        gm = generate_map(room_type=room_type, seed=789)
        grid = gm.grid
        px, py = gm.spawn.player_start
        assert grid.get_tile(px, py).passable, "Player spawn on impassable tile"
        for sx, sy in gm.spawn.party_starts:
            assert grid.get_tile(sx, sy).passable, "Party spawn on impassable tile"
        for ex, ey in gm.spawn.enemy_zone:
            assert grid.get_tile(ex, ey).passable, "Enemy zone tile not passable"

    @pytest.mark.parametrize("room_type", ROOM_TYPES)
    def test_enemy_zone_not_empty(self, room_type: str) -> None:
        gm = generate_map(room_type=room_type, seed=101)
        assert len(gm.spawn.enemy_zone) > 0, f"{room_type} has no enemy zone tiles"


# ---------------------------------------------------------------------------
# Dimension clamping
# ---------------------------------------------------------------------------


class TestDimensionClamping:
    def test_min_width_clamped(self) -> None:
        gm = generate_map(width=5, height=10, seed=1)
        assert gm.grid.width >= MIN_WIDTH

    def test_min_height_clamped(self) -> None:
        gm = generate_map(width=20, height=3, seed=2)
        assert gm.grid.height >= MIN_HEIGHT

    def test_max_width_clamped(self) -> None:
        gm = generate_map(width=200, height=20, seed=3)
        assert gm.grid.width <= MAX_WIDTH

    def test_max_height_clamped(self) -> None:
        gm = generate_map(width=20, height=100, seed=4)
        assert gm.grid.height <= MAX_HEIGHT

    def test_default_dimensions(self) -> None:
        gm = generate_map(seed=5)
        assert gm.grid.width == DEFAULT_WIDTH
        assert gm.grid.height == DEFAULT_HEIGHT


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


class TestFeatureScattering:
    def test_scatter_debris(self) -> None:
        gm = generate_map(room_type="open_room", features=["debris"], seed=10)
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        assert Terrain.DEBRIS in terrains

    def test_scatter_water(self) -> None:
        gm = generate_map(room_type="open_room", features=["water"], seed=11)
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        assert Terrain.WATER in terrains

    def test_scatter_columns(self) -> None:
        gm = generate_map(room_type="open_room", features=["columns"], seed=12)
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        assert Terrain.COLUMN in terrains

    def test_scatter_growths(self) -> None:
        gm = generate_map(room_type="open_room", features=["growths"], seed=13)
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        assert Terrain.GROWTH in terrains

    def test_scatter_cover(self) -> None:
        gm = generate_map(room_type="open_room", features=["cover"], seed=14)
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        assert Terrain.COVER in terrains

    def test_reserved_tiles_not_overwritten(self) -> None:
        """Player/party spawn tiles should remain floor after feature scatter."""
        gm = generate_map(
            room_type="open_room",
            features=["columns", "water", "debris", "growths", "cover"],
            seed=42,
        )
        px, py = gm.spawn.player_start
        assert gm.grid.get_tile(px, py).terrain == Terrain.FLOOR
        for sx, sy in gm.spawn.party_starts:
            assert gm.grid.get_tile(sx, sy).terrain == Terrain.FLOOR

    def test_unknown_feature_ignored(self) -> None:
        """Unknown feature names should not cause errors."""
        gm = generate_map(room_type="open_room", features=["unknown_stuff"], seed=99)
        assert isinstance(gm.grid, Grid)


class TestStoryProfiles:
    def test_titan_recovery_profile_filters_contacts_and_landmarks(self) -> None:
        profile = DungeonGenerationProfile(
            environment="ash_dune_outpost",
            profile_id="story:titan-recovery",
            hostile_tags=("ork", "loota"),
            preferred_themed_room_tags=("titan", "wreck", "ork"),
            required_themed_room_names=("Titan Hull Breach",),
            excluded_contact_tags=("clerk", "scribe"),
        )

        floor = generate_dungeon_floor(
            level_id="titan-test",
            depth=1,
            environment="ash_dune_outpost",
            seed=42,
            profile=profile,
        )

        hostile_names = [
            entity.name
            for entity in floor.entity_roster.values()
            if entity.disposition == DungeonDisposition.HOSTILE
        ]
        assert hostile_names
        assert all(name in {"Ork Loota", "Scrap Grot"} for name in hostile_names)
        assert any(instance.template_name == "Titan Hull Breach" for instance in floor.themed_rooms)
        assert all("Clerk" not in name for name in hostile_names)

    def test_profile_filtered_templates_exclude_unwanted_tags(self) -> None:
        profile = DungeonGenerationProfile(
            environment="ash_dune_outpost",
            excluded_themed_room_tags=("chapel", "vault"),
        )

        templates = _themed_room_templates_for_environment("ash_dune_outpost", profile)

        assert templates
        assert all("chapel" not in template.tags for template in templates)
        assert all("vault" not in template.tags for template in templates)


# ---------------------------------------------------------------------------
# Theme-based feature inference
# ---------------------------------------------------------------------------


class TestThemeFeatures:
    def test_forge_theme_adds_features(self) -> None:
        gm = generate_map(room_type="open_room", theme="forge", seed=20)
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        # Forge theme should add debris and/or terminals
        assert Terrain.DEBRIS in terrains or Terrain.TERMINAL in terrains

    def test_sewer_theme_adds_water(self) -> None:
        gm = generate_map(room_type="open_room", theme="sewer", seed=21)
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        assert Terrain.WATER in terrains

    def test_unknown_theme_no_crash(self) -> None:
        gm = generate_map(theme="alien_dimension", seed=22)
        assert isinstance(gm.grid, Grid)

    @pytest.mark.parametrize(
        ("environment", "expected_terrain"),
        [
            ("forge", DungeonTerrain.LIFT),
            ("manufactorum", DungeonTerrain.LIFT),
            ("hive", DungeonTerrain.ELEVATOR),
            ("cathedral", DungeonTerrain.GATE),
            ("tomb", DungeonTerrain.GATE),
            ("corrupted", DungeonTerrain.PORTAL),
        ],
    )
    def test_exploration_floors_use_thematic_transition_tiles(
        self,
        environment: str,
        expected_terrain: DungeonTerrain,
    ) -> None:
        floor = generate_dungeon_floor(
            level_id=f"{environment}-transition-test",
            depth=1,
            environment=environment,
            seed=77,
        )

        assert floor.level.get_terrain(*floor.level.stairs_up[0]) == expected_terrain
        assert floor.level.get_terrain(*floor.level.stairs_down[0]) == expected_terrain

    def test_fallback_environment_keeps_standard_stairs(self) -> None:
        floor = generate_dungeon_floor(
            level_id="sewer-transition-test",
            depth=1,
            environment="sewer",
            seed=78,
        )

        assert floor.level.get_terrain(*floor.level.stairs_up[0]) == DungeonTerrain.STAIRS_UP
        assert floor.level.get_terrain(*floor.level.stairs_down[0]) == DungeonTerrain.STAIRS_DOWN


# ---------------------------------------------------------------------------
# Map naming
# ---------------------------------------------------------------------------


class TestMapNaming:
    def test_custom_name_used(self) -> None:
        gm = generate_map(name="My Custom Arena", seed=30)
        assert gm.name == "My Custom Arena"

    def test_auto_name_generated(self) -> None:
        gm = generate_map(room_type="corridor", seed=31)
        assert len(gm.name) > 0
        # Name should contain one of the corridor suffixes
        assert any(s in gm.name for s in ["Corridor", "Passage", "Conduit", "Tunnel"])


# ---------------------------------------------------------------------------
# Seed reproducibility
# ---------------------------------------------------------------------------


class TestSeedReproducibility:
    def test_same_seed_same_map(self) -> None:
        gm1 = generate_map(room_type="maze", seed=42)
        gm2 = generate_map(room_type="maze", seed=42)
        for y in range(gm1.grid.height):
            for x in range(gm1.grid.width):
                assert gm1.grid.get_tile(x, y).terrain == gm2.grid.get_tile(x, y).terrain
        assert gm1.spawn.player_start == gm2.spawn.player_start
        assert gm1.spawn.party_starts == gm2.spawn.party_starts
        assert gm1.name == gm2.name

    def test_different_seeds_different_maps(self) -> None:
        gm1 = generate_map(room_type="arena", seed=1)
        gm2 = generate_map(room_type="arena", seed=2)
        # At least some tiles should differ
        diffs = sum(
            1 for y in range(gm1.grid.height) for x in range(gm1.grid.width)
            if gm1.grid.get_tile(x, y).terrain != gm2.grid.get_tile(x, y).terrain
        )
        assert diffs > 0


# ---------------------------------------------------------------------------
# generate_map_from_hint
# ---------------------------------------------------------------------------


class TestGenerateMapFromHint:
    def test_none_hint(self) -> None:
        gm = generate_map_from_hint(None, seed=50)
        assert isinstance(gm, GeneratedMap)

    def test_dict_hint(self) -> None:
        gm = generate_map_from_hint(
            {"room_type": "pillared_hall", "theme": "forge", "name": "The Forge"},
            seed=51,
        )
        assert gm.room_type == "pillared_hall"
        assert gm.name == "The Forge"

    def test_roomhint_object(self) -> None:
        hint = RoomHint(room_type="cross_room", features=["water"])
        gm = generate_map_from_hint(hint, seed=52)
        assert gm.room_type == "cross_room"
        terrains = {gm.grid.get_tile(x, y).terrain
                    for y in range(gm.grid.height)
                    for x in range(gm.grid.width)}
        assert Terrain.WATER in terrains


# ---------------------------------------------------------------------------
# Integration with auto_place_enemies
# ---------------------------------------------------------------------------


class TestEnemyPlacementIntegration:
    def test_enemies_placeable_on_generated_map(self) -> None:
        """Enemies should be auto-placeable on any generated map."""
        for room_type in ROOM_TYPES:
            gm = generate_map(room_type=room_type, seed=60)
            occupied = {gm.spawn.player_start}
            occupied.update(gm.spawn.party_starts)
            placed = auto_place_enemies(
                gm.grid,
                [("servitor", 2), ("gunner", 1)],
                occupied,
            )
            assert len(placed) > 0, f"No enemies placed on {room_type} map"

    def test_to_map_def_works_with_combat_engine(self) -> None:
        """Generated map_def should be accepted by CombatEngine."""
        from angband_mechanicum.engine.combat_engine import CombatEngine

        gm = generate_map(room_type="open_room", seed=70)
        md = gm.to_map_def()
        # Add enemies for the map_def
        occupied = {gm.spawn.player_start}
        occupied.update(gm.spawn.party_starts)
        enemies = auto_place_enemies(
            gm.grid,
            [("servitor", 2)],
            occupied,
        )
        md["enemies"] = enemies

        engine = CombatEngine(
            map_def=md,
            enemy_roster=enemies,
        )
        assert engine.grid.width == gm.grid.width
        assert engine.grid.height == gm.grid.height
        player = engine.get_player()
        assert player.alive


# ---------------------------------------------------------------------------
# Environment contact rosters
# ---------------------------------------------------------------------------


class TestEnvironmentContactRosters:
    def test_contact_roster_exists_for_every_environment(self) -> None:
        for environment in ENVIRONMENTS:
            roster = _contacts_for_environment(environment)
            assert roster["hostile"], f"{environment} has no hostile contact roster"

    @pytest.mark.parametrize(
        ("environment", "expected_keywords"),
        [
            ("sewer", {"rat", "cutpurse", "warden"}),
            ("voidship", {"raider", "armsman", "pilgrim"}),
            ("radwastes", {"mutant", "scavenger", "trader"}),
            ("data_vault", {"intruder", "heretek", "logister"}),
            ("penal_oubliette", {"convict", "warden", "scribe"}),
            ("plasma_reactorum", {"reactor", "cultist", "servitor"}),
        ],
    )
    def test_environment_rosters_are_thematic(self, environment: str, expected_keywords: set[str]) -> None:
        roster = _contacts_for_environment(environment)
        names = " ".join(
            archetype.name.lower()
            for group in roster.values()
            for archetype in group
        )
        assert any(keyword in names for keyword in expected_keywords)


class TestEnvironmentContactGrouping:
    def test_group_size_rules_bias_swarm_and_pack_hostiles(self) -> None:
        rat = next(
            archetype
            for archetype in _contacts_for_environment("sewer")["hostile"]
            if "rat" in archetype.name.lower()
        )
        cult = next(
            archetype
            for archetype in _contacts_for_environment("corrupted")["hostile"]
            if "cult" in archetype.name.lower()
        )

        rat_size = _group_size_for_archetype(rat, "sewer", 8, random.Random(1))
        cult_size = _group_size_for_archetype(cult, "corrupted", 8, random.Random(2))

        assert 4 <= rat_size <= 10
        assert 2 <= cult_size <= 10

    def test_group_positions_cluster_within_a_single_room(self) -> None:
        floor = generate_dungeon_floor(
            level_id="group-cluster-test",
            depth=5,
            environment="forge",
            seed=211,
        )
        room = max(floor.rooms, key=lambda candidate: candidate.width * candidate.height)
        positions = _pick_group_positions(
            floor.level,
            room,
            4,
            set(),
            random.Random(7),
        )

        assert len(positions) == 4
        assert all(room.contains(x, y) for x, y in positions)
        assert max(
            abs(x - room.center[0]) + abs(y - room.center[1])
            for x, y in positions
        ) <= 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_minimum_size_map(self) -> None:
        """Minimum size map should still be playable."""
        gm = generate_map(width=MIN_WIDTH, height=MIN_HEIGHT, seed=80)
        assert gm.grid.width == MIN_WIDTH
        assert gm.grid.height == MIN_HEIGHT
        floor = _floor_tiles(gm.grid)
        assert len(floor) >= 3  # at least player + 2 party members fit

    def test_maximum_size_map(self) -> None:
        gm = generate_map(width=MAX_WIDTH, height=MAX_HEIGHT, seed=81)
        assert gm.grid.width == MAX_WIDTH
        assert gm.grid.height == MAX_HEIGHT

    def test_all_builders_registered(self) -> None:
        """Every ROOM_TYPE should have a corresponding builder."""
        for rt in ROOM_TYPES:
            assert rt in _BUILDERS, f"No builder for room type: {rt}"

    def test_random_room_type_when_none(self) -> None:
        """None room_type should pick randomly (not crash)."""
        gm = generate_map(room_type=None, seed=82)
        assert gm.room_type in ROOM_TYPES

    def test_invalid_room_type_falls_back(self) -> None:
        """Invalid room_type should fall back to a random choice."""
        gm = generate_map(room_type="nonexistent_type", seed=83)
        assert gm.room_type in ROOM_TYPES

    def test_party_starts_at_least_two(self) -> None:
        """Should always produce at least 2 party start positions."""
        for room_type in ROOM_TYPES:
            gm = generate_map(room_type=room_type, width=24, height=17, seed=84)
            assert len(gm.spawn.party_starts) >= 2, (
                f"{room_type} has only {len(gm.spawn.party_starts)} party starts"
            )

    def test_player_not_in_party_starts(self) -> None:
        """Player start should not be the same as any party start."""
        for room_type in ROOM_TYPES:
            gm = generate_map(room_type=room_type, seed=85)
            assert gm.spawn.player_start not in gm.spawn.party_starts


# ---------------------------------------------------------------------------
# Exploration-scale dungeon floors
# ---------------------------------------------------------------------------


class TestDungeonFloorGeneration:
    def test_generate_floor_returns_level_and_rooms(self) -> None:
        floor = generate_dungeon_floor(level_id="floor-1", depth=1, seed=101)
        assert isinstance(floor, GeneratedFloor)
        assert isinstance(floor.level, DungeonLevel)
        assert floor.level.width == FLOOR_DEFAULT_WIDTH
        assert floor.level.height == FLOOR_DEFAULT_HEIGHT
        assert len(floor.rooms) >= 4
        assert all(isinstance(room, DungeonRoom) for room in floor.rooms)

    def test_floor_has_stairs_and_player_position(self) -> None:
        floor = generate_dungeon_floor(level_id="floor-2", depth=2, seed=102)
        assert len(floor.level.stairs_up) == 1
        assert len(floor.level.stairs_down) == 1
        assert floor.level.player_pos == floor.level.stairs_up[0]
        up_x, up_y = floor.level.stairs_up[0]
        down_x, down_y = floor.level.stairs_down[0]
        assert floor.level.get_terrain(up_x, up_y) == DungeonTerrain.LIFT
        assert floor.level.get_terrain(down_x, down_y) == DungeonTerrain.LIFT

    def test_floor_is_connected_between_stairs(self) -> None:
        floor = generate_dungeon_floor(level_id="floor-3", depth=3, seed=103)
        stairs_up = floor.level.stairs_up[0]
        stairs_down = floor.level.stairs_down[0]
        reachable = _reachable_tiles(floor.level, stairs_up)
        assert stairs_down in reachable

    def test_floor_places_doors(self) -> None:
        floor = generate_dungeon_floor(level_id="floor-4", depth=4, seed=104)
        door_count = sum(
            1
            for y in range(floor.level.height)
            for x in range(floor.level.width)
            if floor.level.get_terrain(x, y)
            in (DungeonTerrain.DOOR_OPEN, DungeonTerrain.DOOR_CLOSED)
        )
        assert door_count >= 2

    def test_floor_records_object_placements(self) -> None:
        floor = generate_dungeon_floor(
            level_id="floor-4-objects",
            depth=4,
            environment="forge",
            seed=104,
        )

        assert floor.placed_items
        for item_id, position in floor.placed_items:
            x, y = position
            assert item_id in floor.level.get_items(x, y)
            assert floor.level.get_tile(x, y).passable

    def test_valid_door_threshold_skips_sparse_candidates(self) -> None:
        level = DungeonLevel(
            level_id="door-threshold-test",
            name="Door Threshold Test",
            depth=1,
            environment="forge",
            width=7,
            height=5,
        )
        for y in range(level.height):
            for x in range(level.width):
                level.set_terrain(x, y, DungeonTerrain.WALL)
        for x in range(1, 6):
            level.set_terrain(x, 2, DungeonTerrain.FLOOR)

        _add_doors(level, random.Random(123))

        door_count = sum(
            1
            for y in range(level.height)
            for x in range(level.width)
            if level.get_terrain(x, y) in {DungeonTerrain.DOOR_OPEN, DungeonTerrain.DOOR_CLOSED}
        )
        assert door_count == 0

    def test_floor_uses_environment_features(self) -> None:
        floor = generate_dungeon_floor(
            level_id="floor-5",
            depth=5,
            environment="sewer",
            seed=105,
        )
        terrains = {
            floor.level.get_terrain(x, y)
            for y in range(floor.level.height)
            for x in range(floor.level.width)
        }
        assert DungeonTerrain.WATER in terrains or DungeonTerrain.ACID_POOL in terrains

    def test_floor_seed_reproducibility(self) -> None:
        first = generate_dungeon_floor(level_id="floor-6", depth=6, seed=106)
        second = generate_dungeon_floor(level_id="floor-6", depth=6, seed=106)
        assert [(room.x, room.y, room.width, room.height, room.room_type) for room in first.rooms] == [
            (room.x, room.y, room.width, room.height, room.room_type) for room in second.rooms
        ]
        for y in range(first.level.height):
            for x in range(first.level.width):
                assert first.level.get_terrain(x, y) == second.level.get_terrain(x, y)

    def test_floor_dimensions_are_clamped(self) -> None:
        floor = generate_dungeon_floor(
            level_id="floor-7",
            depth=7,
            width=999,
            height=5,
            seed=107,
        )
        assert floor.level.width <= 160
        assert floor.level.height >= 25

    def test_floor_populates_environment_contacts(self) -> None:
        floor = generate_dungeon_floor(
            level_id="floor-8",
            depth=8,
            environment="manufactorum",
            seed=108,
        )

        contacts = floor.entity_roster.values()
        assert len(contacts) >= 2
        assert any(entity.disposition == DungeonDisposition.HOSTILE for entity in contacts)
        assert any(entity.disposition in {DungeonDisposition.FRIENDLY, DungeonDisposition.NEUTRAL} for entity in contacts)
        assert any(entity.movement_ai == DungeonMovementAI.AGGRESSIVE for entity in contacts)
        for entity in contacts:
            assert entity.position is not None
            x, y = entity.position
            assert floor.level.in_bounds(x, y)
            assert floor.level.get_tile(x, y).passable
            assert floor.level.get_creature(x, y) == entity.entity_id
            assert floor.level.get_terrain(x, y) == DungeonTerrain.FLOOR

    def test_floor_hostile_contacts_spawn_in_groups(self) -> None:
        floor = generate_dungeon_floor(
            level_id="floor-8-grouped",
            depth=8,
            environment="sewer",
            seed=109,
        )

        contacts = floor.entity_roster.values()
        hostile_counts = Counter(
            entity.name
            for entity in contacts
            if entity.disposition == DungeonDisposition.HOSTILE
        )
        assert len(contacts) >= 3
        assert hostile_counts
        assert any(count > 1 for count in hostile_counts.values())

    def test_floor_contacts_are_seed_reproducible(self) -> None:
        first = generate_dungeon_floor(level_id="floor-9", depth=9, environment="forge", seed=109)
        second = generate_dungeon_floor(level_id="floor-9", depth=9, environment="forge", seed=109)

        first_contacts = [
            (
                entity.entity_id,
                entity.name,
                entity.disposition.value,
                entity.movement_ai.value,
                entity.position,
            )
            for entity in first.entity_roster.values()
        ]
        second_contacts = [
            (
                entity.entity_id,
                entity.name,
                entity.disposition.value,
                entity.movement_ai.value,
                entity.position,
            )
            for entity in second.entity_roster.values()
        ]

        assert first_contacts == second_contacts

    def test_floor_records_themed_rooms(self) -> None:
        floor = generate_dungeon_floor(
            level_id="floor-themed",
            depth=6,
            environment="forge",
            seed=110,
        )

        assert floor.themed_rooms
        themed = floor.themed_rooms[0]
        assert themed.template_name in {template.name for template in _themed_room_templates_for_environment("forge")}
        assert themed.feature_tiles or themed.prop_tiles or themed.encounter_ids
        assert len(themed.encounter_ids) >= 1

    def test_floor_object_placements_are_seed_reproducible(self) -> None:
        first = generate_dungeon_floor(
            level_id="floor-objects-seeded",
            depth=4,
            environment="forge",
            seed=111,
        )
        second = generate_dungeon_floor(
            level_id="floor-objects-seeded",
            depth=4,
            environment="forge",
            seed=111,
        )

        assert first.placed_items == second.placed_items


class TestThemedRoomComposition:
    def test_themed_room_catalog_is_scoped_by_environment(self) -> None:
        forge_templates = _themed_room_templates_for_environment("forge")
        fallback_templates = _themed_room_templates_for_environment("unknown")

        assert any(template.name == "Heretek Workshop" for template in forge_templates)
        assert len(fallback_templates) >= 1
        assert all("forge" in template.environments or "manufactorum" in template.environments or "data_vault" in template.environments or "plasma_reactorum" in template.environments for template in forge_templates)

    def test_apply_themed_room_template_places_dressing_and_contacts(self) -> None:
        level = DungeonLevel(
            level_id="themed-room-test",
            name="Themed Room Test",
            depth=6,
            environment="forge",
            width=18,
            height=14,
        )
        for y in range(level.height):
            for x in range(level.width):
                if x in (0, level.width - 1) or y in (0, level.height - 1):
                    level.set_terrain(x, y, DungeonTerrain.WALL)
                else:
                    level.set_terrain(x, y, DungeonTerrain.FLOOR)

        room = DungeonRoom(x=1, y=1, width=16, height=12, room_type="open_room")
        rooms = [room]
        roster = DungeonEntityRoster()
        template = next(template for template in _themed_room_templates_for_environment("forge") if template.name == "Heretek Workshop")
        occupied: set[tuple[int, int]] = set()

        instance, themed_contact_count = _apply_themed_room_template(
            level,
            rooms,
            0,
            template,
            "forge",
            6,
            random.Random(19),
            occupied,
            roster,
        )

        assert instance is not None
        assert themed_contact_count >= 1
        assert instance.feature_tiles
        assert instance.prop_tiles
        assert instance.encounter_ids
        assert len(roster.values()) == themed_contact_count
        assert any(entity.disposition == DungeonDisposition.HOSTILE for entity in roster.values())
        for terrain, position in instance.prop_tiles:
            assert level.get_terrain(*position) == terrain
        for position in instance.feature_tiles:
            assert level.get_tile(*position).terrain != DungeonTerrain.FLOOR
