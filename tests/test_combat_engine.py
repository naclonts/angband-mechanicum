"""Tests for the deterministic combat engine."""

from __future__ import annotations

from angband_mechanicum.engine.combat_engine import (
    CombatEngine,
    CombatPhase,
    CombatStats,
    CombatUnit,
    Grid,
    Terrain,
    Tile,
    UnitTeam,
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
        for key in ("servitor", "gunner", "brute"):
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

    def test_player_cannot_move_twice(self) -> None:
        engine = CombatEngine()
        player = engine.get_player()
        reachable = list(engine.get_reachable_tiles(player))
        if len(reachable) >= 2:
            engine.player_move(reachable[0][0], reachable[0][1])
            result = engine.player_move(reachable[1][0], reachable[1][1])
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
