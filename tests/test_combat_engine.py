"""Tests for the deterministic combat engine."""

from __future__ import annotations

from angband_mechanicum.engine.combat_engine import (
    CombatEngine,
    CombatPhase,
    CombatStats,
    CombatUnit,
    ENEMY_TEMPLATES,
    Grid,
    Terrain,
    Tile,
    UnitTeam,
    _astar_path,
    auto_place_enemies,
    has_line_of_sight,
    make_enemy,
    make_player,
    manhattan_distance,
)


# ---------------------------------------------------------------------------
# Tile & Grid basics
# ---------------------------------------------------------------------------


class TestTile:
    def test_floor_passable(self) -> None:
        t = Tile(Terrain.FLOOR)
        assert t.passable is True
        assert t.movement_cost == 1

    def test_wall_impassable(self) -> None:
        t = Tile(Terrain.WALL)
        assert t.passable is False

    def test_debris_passable_costly(self) -> None:
        t = Tile(Terrain.DEBRIS)
        assert t.passable is True
        assert t.movement_cost == 2

    def test_tile_roundtrip(self) -> None:
        t = Tile(Terrain.TERMINAL)
        restored = Tile.from_dict(t.to_dict())
        assert restored.terrain == Terrain.TERMINAL


class TestGrid:
    def test_default_grid_all_floor(self) -> None:
        g = Grid(width=5, height=3)
        for y in range(3):
            for x in range(5):
                assert g.get_tile(x, y).terrain == Terrain.FLOOR

    def test_in_bounds(self) -> None:
        g = Grid(width=5, height=3)
        assert g.in_bounds(0, 0) is True
        assert g.in_bounds(4, 2) is True
        assert g.in_bounds(5, 0) is False
        assert g.in_bounds(-1, 0) is False

    def test_set_terrain(self) -> None:
        g = Grid(width=5, height=3)
        g.set_terrain(2, 1, Terrain.WALL)
        assert g.get_tile(2, 1).terrain == Terrain.WALL

    def test_grid_roundtrip(self) -> None:
        g = Grid(width=4, height=4)
        g.set_terrain(1, 1, Terrain.WALL)
        g.set_terrain(2, 2, Terrain.DEBRIS)
        restored = Grid.from_dict(g.to_dict())
        assert restored.width == 4
        assert restored.height == 4
        assert restored.get_tile(1, 1).terrain == Terrain.WALL
        assert restored.get_tile(2, 2).terrain == Terrain.DEBRIS
        assert restored.get_tile(0, 0).terrain == Terrain.FLOOR


# ---------------------------------------------------------------------------
# CombatUnit basics
# ---------------------------------------------------------------------------


class TestCombatUnit:
    def test_take_damage_with_armor(self) -> None:
        stats = CombatStats(max_hp=10, hp=10, attack=3, armor=2, movement=3, attack_range=1)
        unit = CombatUnit(
            unit_id="test", name="Test", entity_id=None,
            team=UnitTeam.ENEMY, stats=stats, x=0, y=0,
        )
        actual = unit.take_damage(5)
        assert actual == 3  # 5 - 2 armor
        assert unit.stats.hp == 7

    def test_minimum_damage_is_one(self) -> None:
        stats = CombatStats(max_hp=10, hp=10, attack=3, armor=10, movement=3, attack_range=1)
        unit = CombatUnit(
            unit_id="test", name="Test", entity_id=None,
            team=UnitTeam.ENEMY, stats=stats, x=0, y=0,
        )
        actual = unit.take_damage(1)
        assert actual == 1  # min 1 damage
        assert unit.stats.hp == 9

    def test_unit_dies_at_zero_hp(self) -> None:
        stats = CombatStats(max_hp=5, hp=3, attack=3, armor=0, movement=3, attack_range=1)
        unit = CombatUnit(
            unit_id="test", name="Test", entity_id=None,
            team=UnitTeam.ENEMY, stats=stats, x=0, y=0,
        )
        unit.take_damage(10)
        assert unit.stats.hp == 0
        assert unit.alive is False

    def test_unit_roundtrip(self) -> None:
        unit = make_player(3, 4, entity_id="tech-priest")
        data = unit.to_dict()
        restored = CombatUnit.from_dict(data)
        assert restored.unit_id == "player"
        assert restored.name == "Magos Explorator"
        assert restored.entity_id == "tech-priest"
        assert restored.x == 3
        assert restored.y == 4
        assert restored.stats.max_hp == 20


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


class TestFactories:
    def test_make_player(self) -> None:
        p = make_player(5, 5)
        assert p.team == UnitTeam.PLAYER
        assert p.symbol == "@"
        assert p.stats.hp > 0

    def test_make_enemy(self) -> None:
        e = make_enemy("servitor", 3, 4)
        assert e.team == UnitTeam.ENEMY
        assert e.name == "Rogue Servitor"
        assert e.symbol == "S"

    def test_make_enemy_all_templates(self) -> None:
        for key in ENEMY_TEMPLATES:
            e = make_enemy(key, 0, 0)
            assert e.alive is True
            assert e.stats.hp > 0


# ---------------------------------------------------------------------------
# Manhattan distance
# ---------------------------------------------------------------------------


class TestManhattan:
    def test_same_point(self) -> None:
        assert manhattan_distance(3, 4, 3, 4) == 0

    def test_adjacent(self) -> None:
        assert manhattan_distance(0, 0, 1, 0) == 1
        assert manhattan_distance(0, 0, 0, 1) == 1

    def test_diagonal(self) -> None:
        assert manhattan_distance(0, 0, 3, 4) == 7


# ---------------------------------------------------------------------------
# CombatEngine: initialization and basics
# ---------------------------------------------------------------------------


class TestCombatEngineInit:
    def test_creates_with_default_map(self) -> None:
        engine = CombatEngine()
        assert engine.phase == CombatPhase.PLAYER_TURN
        assert engine.turn == 1
        assert engine.get_player().alive is True

    def test_units_placed(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        assert player is not None
        assert len(enemies) == 3  # corridor map has 3 enemies

    def test_no_units_overlap(self) -> None:
        engine = CombatEngine()
        positions = [(u.x, u.y) for u in engine.get_units()]
        assert len(positions) == len(set(positions))

    def test_log_has_entries(self) -> None:
        engine = CombatEngine()
        assert len(engine.log) >= 1


# ---------------------------------------------------------------------------
# CombatEngine: movement
# ---------------------------------------------------------------------------


class TestCombatEngineMovement:
    def test_reachable_tiles_excludes_walls(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        reachable = engine.get_reachable_tiles(player)
        for x, y in reachable:
            tile = engine.grid.get_tile(x, y)
            assert tile.passable

    def test_reachable_tiles_within_movement_range(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        reachable = engine.get_reachable_tiles(player)
        for x, y in reachable:
            # Manhattan distance is a lower bound (actual path may be longer)
            # but reachable tiles should be within a reasonable range
            dist = manhattan_distance(player.x, player.y, x, y)
            assert dist <= player.stats.movement * 2  # generous bound

    def test_player_move_success(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        reachable = engine.get_reachable_tiles(player)
        if reachable:
            target = next(iter(reachable))
            result = engine.player_move(target[0], target[1])
            assert result is True
            assert player.x == target[0]
            assert player.y == target[1]
            assert player.has_moved is True

    def test_player_can_reposition_within_range(self) -> None:
        """After moving, the player can move again if the target is still
        within movement range of the original turn-start position."""
        engine = CombatEngine()
        player = engine.get_player()
        start_x, start_y = player.x, player.y
        reachable = list(engine.get_reachable_tiles(player))
        if len(reachable) >= 2:
            # First move
            engine.player_move(reachable[0][0], reachable[0][1])
            assert player.has_moved is True
            # Second move to another tile reachable from start
            result = engine.player_move(reachable[1][0], reachable[1][1])
            assert result is True
            assert player.x == reachable[1][0]
            assert player.y == reachable[1][1]
            # turn_start should still record the original position
            assert player.turn_start_x == start_x
            assert player.turn_start_y == start_y

    def test_player_cannot_move_beyond_total_range(self) -> None:
        """Moving beyond the unit's movement range from its turn-start
        position should be rejected, even if the target is close to the
        unit's current position."""
        # Use a simple open grid to make distances predictable
        grid = Grid(width=20, height=5)
        map_def = {
            "name": "Test Arena",
            "build": lambda: grid,
            "player_start": (1, 2),
            "party_starts": [],
            "enemies": [],
        }
        engine = CombatEngine(map_def=map_def, enemy_roster=[])
        player = engine.get_player()
        movement = player.stats.movement  # 4

        # Move to exactly the movement limit (east)
        engine.player_move(1 + movement, 2)
        assert player.x == 1 + movement

        # Now try to move 1 tile further east -- exceeds range from start
        result = engine.player_move(1 + movement + 1, 2)
        assert result is False

    def test_player_cannot_move_to_wall(self) -> None:
        engine = CombatEngine()
        # Find a wall tile
        grid = engine.grid
        for y in range(grid.height):
            for x in range(grid.width):
                if grid.get_tile(x, y).terrain == Terrain.WALL:
                    result = engine.player_move(x, y)
                    assert result is False
                    return

    def test_cursor_movement(self) -> None:
        engine = CombatEngine()
        cx, cy = engine.cursor
        engine.move_cursor(1, 0)
        assert engine.cursor == (cx + 1, cy)
        engine.move_cursor(0, 1)
        assert engine.cursor == (cx + 1, cy + 1)

    def test_cursor_stays_in_bounds(self) -> None:
        engine = CombatEngine()
        # Move cursor far left/up -- should clamp
        for _ in range(100):
            engine.move_cursor(-1, 0)
        for _ in range(100):
            engine.move_cursor(0, -1)
        assert engine.cursor == (0, 0)


# ---------------------------------------------------------------------------
# CombatEngine: attack
# ---------------------------------------------------------------------------


class TestCombatEngineAttack:
    def _setup_adjacent_combat(self) -> CombatEngine:
        """Create an engine and move player adjacent to an enemy."""
        engine = CombatEngine()
        player = engine.get_player()
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        # Find nearest enemy
        closest = min(enemies, key=lambda e: manhattan_distance(player.x, player.y, e.x, e.y))
        # Teleport player next to enemy for test purposes
        player.x = closest.x - 1 if closest.x > 0 else closest.x + 1
        player.y = closest.y
        return engine

    def test_attack_in_range(self) -> None:
        engine = self._setup_adjacent_combat()
        player = engine.get_player()
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        attackable = engine.get_attackable_units(player)
        if attackable:
            target = attackable[0]
            initial_hp = target.stats.hp
            result = engine.player_attack(target.unit_id)
            assert result is True
            assert target.stats.hp < initial_hp
            assert player.has_attacked is True

    def test_cannot_attack_out_of_range(self) -> None:
        engine = CombatEngine()
        # Player starts far from enemies; don't move. Try to attack.
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        player = engine.get_player()
        for enemy in enemies:
            dist = manhattan_distance(player.x, player.y, enemy.x, enemy.y)
            if dist > player.stats.attack_range:
                result = engine.player_attack(enemy.unit_id)
                assert result is False
                return

    def test_cannot_attack_twice(self) -> None:
        engine = self._setup_adjacent_combat()
        player = engine.get_player()
        attackable = engine.get_attackable_units(player)
        if attackable:
            engine.player_attack(attackable[0].unit_id)
            result = engine.player_attack(attackable[0].unit_id)
            assert result is False


# ---------------------------------------------------------------------------
# CombatEngine: player ranged attacks
# ---------------------------------------------------------------------------


class TestPlayerRangedAttack:
    def test_player_has_ranged_attack(self) -> None:
        """The Tech-Priest should have attack_range > 1."""
        player = make_player(5, 5)
        assert player.stats.attack_range > 1, (
            "Tech-Priest should have ranged capability"
        )

    def test_player_can_shoot_at_range_with_los(self) -> None:
        """Player should be able to attack an enemy at range with clear LoS."""
        engine = CombatEngine(enemy_roster=[])
        player = engine.get_player()
        player.x = 2
        player.y = 7

        # Place an enemy within range and with clear LoS (same row, no walls)
        enemy = make_enemy("servitor", 4, 7)
        engine._units[enemy.unit_id] = enemy
        engine._total_enemies = 1

        initial_hp = enemy.stats.hp
        result = engine.player_attack(enemy.unit_id)
        assert result is True
        assert enemy.stats.hp < initial_hp
        # Check for ranged shot flavour in log
        shot_logs = [e.text for e in engine.log if "shoots" in e.text]
        assert len(shot_logs) > 0, "Ranged attack should use 'shoots' in log"

    def test_player_cannot_shoot_without_los(self) -> None:
        """Player ranged attack should fail when LoS is blocked by a wall."""
        engine = CombatEngine(enemy_roster=[])
        player = engine.get_player()
        # Player on left side of corridor map's internal wall at x=8
        player.x = 6
        player.y = 3

        # Enemy on other side of wall at x=8 (wall runs y=1..5)
        enemy = make_enemy("servitor", 10, 3)
        engine._units[enemy.unit_id] = enemy
        engine._total_enemies = 1

        # Distance is 4, player range is 3 -- but let's set up within range
        # Move player closer so range is satisfied but LoS is still blocked
        player.x = 7
        player.y = 3
        # Wall at (8,3) blocks LoS from (7,3) to (10,3)
        assert not has_line_of_sight(engine.grid, 7, 3, 10, 3)

        result = engine.player_attack(enemy.unit_id)
        assert result is False
        # Check for LoS failure message in log
        los_logs = [e.text for e in engine.log if "line of sight" in e.text.lower()]
        assert len(los_logs) > 0, "Should log LoS failure message"

    def test_melee_attack_ignores_los(self) -> None:
        """Adjacent (melee) attacks should work regardless of LoS."""
        engine = CombatEngine(enemy_roster=[])
        player = engine.get_player()
        player.x = 3
        player.y = 7

        enemy = make_enemy("servitor", 4, 7)
        engine._units[enemy.unit_id] = enemy
        engine._total_enemies = 1

        # Distance is 1 -- melee should always work
        initial_hp = enemy.stats.hp
        result = engine.player_attack(enemy.unit_id)
        assert result is True
        assert enemy.stats.hp < initial_hp
        # Check for melee flavour in log (should say "attacks" not "shoots")
        attack_logs = [e.text for e in engine.log if "attacks" in e.text]
        assert len(attack_logs) > 0

    def test_get_attackable_units_respects_los(self) -> None:
        """get_attackable_units should exclude targets without LoS."""
        engine = CombatEngine(enemy_roster=[])
        player = engine.get_player()
        player.x = 7
        player.y = 3

        # Enemy behind wall (x=8 wall from y=1..5)
        enemy_blocked = make_enemy("servitor", 10, 3)
        engine._units[enemy_blocked.unit_id] = enemy_blocked

        # Enemy with clear LoS
        enemy_clear = make_enemy("gunner", 5, 3)
        engine._units[enemy_clear.unit_id] = enemy_clear
        engine._total_enemies = 2

        attackable = engine.get_attackable_units(player)
        attackable_ids = {u.unit_id for u in attackable}

        # The enemy with clear LoS should be attackable (if in range)
        dist_clear = manhattan_distance(player.x, player.y, enemy_clear.x, enemy_clear.y)
        if dist_clear <= player.stats.attack_range:
            assert enemy_clear.unit_id in attackable_ids

        # The enemy behind the wall should NOT be attackable
        assert enemy_blocked.unit_id not in attackable_ids

    def test_party_member_ranged_attack(self) -> None:
        """Alpha-7 (ranged party member) should be able to shoot at range."""
        engine = CombatEngine(
            party_ids=["skitarius-alpha-7"],
            enemy_roster=[],
        )
        # Place an enemy within Alpha-7's range (attack_range=15)
        enemy = make_enemy("servitor", 6, 6)
        engine._units[enemy.unit_id] = enemy
        engine._total_enemies = 1

        # Select Alpha-7
        alpha7 = engine._units.get("skitarius-alpha-7")
        assert alpha7 is not None
        assert alpha7.stats.attack_range == 15

        engine.select_unit("skitarius-alpha-7")
        assert engine.active_unit_id == "skitarius-alpha-7"

        dist = manhattan_distance(alpha7.x, alpha7.y, enemy.x, enemy.y)
        los = has_line_of_sight(engine.grid, alpha7.x, alpha7.y, enemy.x, enemy.y)

        if dist <= alpha7.stats.attack_range and (dist <= 1 or los):
            initial_hp = enemy.stats.hp
            result = engine.player_attack(enemy.unit_id)
            assert result is True
            assert enemy.stats.hp < initial_hp


# ---------------------------------------------------------------------------
# CombatEngine: turn flow
# ---------------------------------------------------------------------------


class TestCombatEngineTurnFlow:
    def test_end_turn_switches_to_enemy_then_back(self) -> None:
        engine = CombatEngine()
        assert engine.phase == CombatPhase.PLAYER_TURN
        assert engine.turn == 1
        engine.end_player_turn()
        # After enemy turn completes, should be back to player turn
        if not engine.is_over:
            assert engine.phase == CombatPhase.PLAYER_TURN
            assert engine.turn == 2

    def test_turn_increments(self) -> None:
        engine = CombatEngine()
        for i in range(3):
            if engine.is_over:
                break
            engine.end_player_turn()
        if not engine.is_over:
            assert engine.turn >= 4  # started at 1, ended 3 turns

    def test_player_flags_reset_each_turn(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        player.has_moved = True
        player.has_attacked = True
        engine.end_player_turn()
        if not engine.is_over:
            assert player.has_moved is False
            assert player.has_attacked is False


# ---------------------------------------------------------------------------
# CombatEngine: win/loss
# ---------------------------------------------------------------------------


class TestCombatEngineEndConditions:
    def test_victory_when_all_enemies_dead(self) -> None:
        engine = CombatEngine()
        # Kill all enemies directly
        for unit in engine.get_alive_units(UnitTeam.ENEMY):
            unit.take_damage(9999)
        engine._check_end_conditions()
        assert engine.phase == CombatPhase.VICTORY
        assert engine.is_over is True

    def test_defeat_when_player_dies(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        player.take_damage(9999)
        engine._check_end_conditions()
        assert engine.phase == CombatPhase.DEFEAT
        assert engine.is_over is True

    def test_result_after_victory(self) -> None:
        engine = CombatEngine()
        for unit in engine.get_alive_units(UnitTeam.ENEMY):
            unit.take_damage(9999)
        engine._check_end_conditions()
        result = engine.get_result()
        assert result.victory is True
        assert result.enemies_defeated == result.enemies_total
        assert result.player_hp_remaining > 0

    def test_result_after_defeat(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        player.take_damage(9999)
        engine._check_end_conditions()
        result = engine.get_result()
        assert result.victory is False
        assert result.player_hp_remaining == 0


# ---------------------------------------------------------------------------
# CombatEngine: serialization roundtrip
# ---------------------------------------------------------------------------


class TestCombatEngineSerialization:
    def test_full_roundtrip(self) -> None:
        engine = CombatEngine()
        # Do some actions
        player = engine.get_player()
        reachable = engine.get_reachable_tiles(player)
        if reachable:
            target = next(iter(reachable))
            engine.player_move(target[0], target[1])

        data = engine.to_dict()
        restored = CombatEngine.from_dict(data)

        assert restored.turn == engine.turn
        assert restored.phase == engine.phase
        assert restored.map_name == engine.map_name
        assert restored.grid.width == engine.grid.width
        assert restored.grid.height == engine.grid.height

        # Check player state preserved
        rp = restored.get_player()
        op = engine.get_player()
        assert rp.x == op.x
        assert rp.y == op.y
        assert rp.stats.hp == op.stats.hp
        assert rp.has_moved == op.has_moved

        # Check enemy count preserved
        assert len(restored.get_alive_units(UnitTeam.ENEMY)) == len(
            engine.get_alive_units(UnitTeam.ENEMY)
        )

    def test_roundtrip_after_combat(self) -> None:
        engine = CombatEngine()
        # Kill an enemy
        enemy = engine.get_alive_units(UnitTeam.ENEMY)[0]
        enemy.take_damage(9999)

        data = engine.to_dict()
        restored = CombatEngine.from_dict(data)

        # The killed enemy should still be dead
        restored_enemy = restored._units[enemy.unit_id]
        assert restored_enemy.alive is False
        assert restored_enemy.stats.hp == 0

    def test_log_preserved(self) -> None:
        engine = CombatEngine()
        engine.end_player_turn()
        data = engine.to_dict()
        restored = CombatEngine.from_dict(data)
        assert len(restored.log) == len(engine.log)
        for orig, rest in zip(engine.log, restored.log):
            assert orig.text == rest.text
            assert orig.turn == rest.turn


# ---------------------------------------------------------------------------
# auto_place_enemies
# ---------------------------------------------------------------------------


class TestAutoPlaceEnemies:
    def test_places_correct_count(self) -> None:
        grid = Grid(width=20, height=15)
        roster = auto_place_enemies(grid, [("servitor", 2), ("gunner", 1)])
        assert len(roster) == 3
        keys = [r[0] for r in roster]
        assert keys.count("servitor") == 2
        assert keys.count("gunner") == 1

    def test_positions_in_right_half(self) -> None:
        grid = Grid(width=20, height=15)
        roster = auto_place_enemies(grid, [("servitor", 3)])
        for _, x, _y in roster:
            assert x >= 10  # right half of a 20-wide grid

    def test_no_overlap(self) -> None:
        grid = Grid(width=20, height=15)
        roster = auto_place_enemies(grid, [("thug", 5)])
        positions = [(x, y) for _, x, y in roster]
        assert len(positions) == len(set(positions))

    def test_respects_occupied(self) -> None:
        grid = Grid(width=20, height=15)
        occupied = {(10, 0), (11, 0), (12, 0)}
        roster = auto_place_enemies(grid, [("servitor", 3)], occupied)
        placed_positions = {(x, y) for _, x, y in roster}
        assert not placed_positions & occupied

    def test_skips_unknown_template(self) -> None:
        grid = Grid(width=20, height=15)
        roster = auto_place_enemies(grid, [("nonexistent", 2), ("servitor", 1)])
        assert len(roster) == 1
        assert roster[0][0] == "servitor"


# ---------------------------------------------------------------------------
# CombatEngine: enemy_roster override
# ---------------------------------------------------------------------------


class TestCombatEngineEnemyRoster:
    def test_roster_overrides_map_enemies(self) -> None:
        roster = [("cultist", 15, 5), ("berserker", 16, 8)]
        engine = CombatEngine(enemy_roster=roster)
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        assert len(enemies) == 2
        names = {e.name for e in enemies}
        assert "Chaos Cultist" in names
        assert "Khorne Berserker" in names

    def test_empty_roster_means_no_enemies(self) -> None:
        engine = CombatEngine(enemy_roster=[])
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        assert len(enemies) == 0

    def test_invalid_template_in_roster_skipped(self) -> None:
        roster = [("servitor", 15, 5), ("nonexistent", 16, 8)]
        engine = CombatEngine(enemy_roster=roster)
        enemies = engine.get_alive_units(UnitTeam.ENEMY)
        assert len(enemies) == 1
        assert enemies[0].template_key == "servitor"


# ---------------------------------------------------------------------------
# Line of sight
# ---------------------------------------------------------------------------


class TestLineOfSight:
    def test_clear_line_open_grid(self) -> None:
        grid = Grid(width=10, height=10)
        assert has_line_of_sight(grid, 0, 0, 5, 5) is True

    def test_blocked_by_wall(self) -> None:
        grid = Grid(width=10, height=10)
        grid.set_terrain(3, 3, Terrain.WALL)
        # Line from (0,0) to (6,6) passes through (3,3)
        assert has_line_of_sight(grid, 0, 0, 6, 6) is False

    def test_wall_not_on_line(self) -> None:
        grid = Grid(width=10, height=10)
        grid.set_terrain(3, 0, Terrain.WALL)
        # Straight horizontal: (0,5) to (8,5) should be clear
        assert has_line_of_sight(grid, 0, 5, 8, 5) is True

    def test_adjacent_always_visible(self) -> None:
        grid = Grid(width=10, height=10)
        assert has_line_of_sight(grid, 5, 5, 6, 5) is True
        assert has_line_of_sight(grid, 5, 5, 5, 6) is True

    def test_wall_between_horizontal(self) -> None:
        grid = Grid(width=10, height=10)
        grid.set_terrain(3, 5, Terrain.WALL)
        assert has_line_of_sight(grid, 1, 5, 6, 5) is False

    def test_debris_does_not_block(self) -> None:
        grid = Grid(width=10, height=10)
        grid.set_terrain(3, 3, Terrain.DEBRIS)
        assert has_line_of_sight(grid, 0, 0, 6, 6) is True


# ---------------------------------------------------------------------------
# A* pathfinding
# ---------------------------------------------------------------------------


class TestAstarPath:
    def test_straight_path_open_grid(self) -> None:
        grid = Grid(width=10, height=10)
        path = _astar_path(grid, 0, 0, 4, 0, set())
        assert len(path) == 4
        assert path[-1] == (4, 0)

    def test_path_around_wall(self) -> None:
        """A* should find a path around a wall that greedy would get stuck on."""
        grid = Grid(width=10, height=10)
        # Vertical wall from y=0 to y=4 at x=3
        for y in range(5):
            grid.set_terrain(3, y, Terrain.WALL)
        # Path from (1,2) to (5,2) must go around the wall
        path = _astar_path(grid, 1, 2, 5, 2, set())
        assert len(path) > 0
        assert path[-1] == (5, 2)
        # Verify no step goes through a wall
        for px, py in path:
            assert grid.get_tile(px, py).passable

    def test_no_path_completely_blocked(self) -> None:
        """Returns empty list when target is unreachable."""
        grid = Grid(width=5, height=5)
        # Box the target in with walls
        for x in range(5):
            grid.set_terrain(x, 2, Terrain.WALL)
        path = _astar_path(grid, 0, 0, 0, 4, set())
        assert path == []

    def test_path_avoids_occupied(self) -> None:
        grid = Grid(width=10, height=10)
        occupied = {(2, 0), (3, 0)}
        path = _astar_path(grid, 0, 0, 5, 0, occupied)
        for px, py in path:
            assert (px, py) not in occupied or (px, py) == (5, 0)

    def test_same_start_and_end(self) -> None:
        grid = Grid(width=5, height=5)
        path = _astar_path(grid, 2, 2, 2, 2, set())
        assert path == []

    def test_max_cost_limits_search(self) -> None:
        grid = Grid(width=20, height=1)
        # With max_cost=3, should not reach a target 10 tiles away
        path = _astar_path(grid, 0, 0, 10, 0, set(), max_cost=3)
        assert path == []


# ---------------------------------------------------------------------------
# Enemy AI: pathfinding around obstacles
# ---------------------------------------------------------------------------


class TestEnemyAIPathfinding:
    def test_enemy_navigates_around_wall(self) -> None:
        """Enemies should navigate around walls instead of getting stuck."""
        # Build a custom map with a wall between enemy and player
        engine = CombatEngine(enemy_roster=[])
        grid = engine.grid
        player = engine.get_player()

        # Place player on left side, enemy on right side with wall between
        player.x = 2
        player.y = 7

        # Place a melee enemy behind the internal wall at (8, y)
        # The corridor map has walls at x=8 from y=1..5 and y=7..9
        enemy = make_enemy("servitor", 10, 3)
        engine._units[enemy.unit_id] = enemy
        engine._total_enemies = 1

        initial_x, initial_y = enemy.x, enemy.y

        # Run an enemy turn
        engine._phase = CombatPhase.PLAYER_TURN
        engine.end_player_turn()

        # The enemy should have moved (not stayed stuck)
        if not engine.is_over:
            moved = (enemy.x != initial_x) or (enemy.y != initial_y)
            assert moved, "Enemy should move toward player via pathfinding"

    def test_ranged_enemy_shoots_with_los(self) -> None:
        """A ranged enemy with LoS should shoot instead of moving."""
        engine = CombatEngine(enemy_roster=[])
        player = engine.get_player()

        # Place player and ranged enemy with clear LoS
        player.x = 3
        player.y = 7
        # gunner has attack_range=4
        enemy = make_enemy("gunner", 6, 7)
        engine._units[enemy.unit_id] = enemy
        engine._total_enemies = 1

        initial_hp = player.stats.hp
        initial_x, initial_y = enemy.x, enemy.y

        engine._phase = CombatPhase.PLAYER_TURN
        engine.end_player_turn()

        if not engine.is_over:
            # Enemy should have attacked (player HP decreased)
            assert player.stats.hp < initial_hp, "Ranged enemy should shoot with LoS"
            # Enemy should NOT have moved (it had LoS from current position)
            assert enemy.x == initial_x and enemy.y == initial_y, (
                "Ranged enemy should stay put when it has LoS and range"
            )

    def test_ranged_enemy_moves_when_no_los(self) -> None:
        """A ranged enemy without LoS should move to get it."""
        engine = CombatEngine(enemy_roster=[])
        player = engine.get_player()

        # Place player at (2,7) and ranged enemy behind a wall
        player.x = 2
        player.y = 7
        # gunner behind the x=8 wall with no clear LoS
        enemy = make_enemy("gunner", 10, 3)
        engine._units[enemy.unit_id] = enemy
        engine._total_enemies = 1

        initial_x, initial_y = enemy.x, enemy.y

        engine._phase = CombatPhase.PLAYER_TURN
        engine.end_player_turn()

        if not engine.is_over:
            # Enemy should have moved (no LoS from starting position)
            moved = (enemy.x != initial_x) or (enemy.y != initial_y)
            assert moved, "Ranged enemy should move when it has no LoS"
