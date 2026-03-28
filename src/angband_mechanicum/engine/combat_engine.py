"""Turn-based tactical combat engine.

Deterministic combat logic -- NO LLM API calls. Handles grid state,
unit positions, HP/stats, turn order, action resolution, and enemy AI.
Fully serializable via to_dict()/from_dict() for save compatibility.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Terrain & Grid
# ---------------------------------------------------------------------------


class Terrain(enum.Enum):
    """Tile terrain types."""

    FLOOR = "floor"
    WALL = "wall"
    DEBRIS = "debris"  # passable but costs +1 movement
    TERMINAL = "terminal"  # passable, interactive flavour


@dataclass
class Tile:
    """A single cell on the tactical grid."""

    terrain: Terrain = Terrain.FLOOR

    @property
    def passable(self) -> bool:
        return self.terrain != Terrain.WALL

    @property
    def movement_cost(self) -> int:
        if self.terrain == Terrain.DEBRIS:
            return 2
        return 1

    def to_dict(self) -> dict[str, Any]:
        return {"terrain": self.terrain.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tile:
        return cls(terrain=Terrain(data["terrain"]))


@dataclass
class Grid:
    """2-D tactical map of Tiles, origin top-left."""

    width: int
    height: int
    tiles: list[list[Tile]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tiles:
            self.tiles = [
                [Tile() for _ in range(self.width)] for _ in range(self.height)
            ]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get_tile(self, x: int, y: int) -> Tile:
        return self.tiles[y][x]

    def set_terrain(self, x: int, y: int, terrain: Terrain) -> None:
        self.tiles[y][x].terrain = terrain

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "tiles": [[t.to_dict() for t in row] for row in self.tiles],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Grid:
        width: int = data["width"]
        height: int = data["height"]
        tiles = [
            [Tile.from_dict(td) for td in row] for row in data["tiles"]
        ]
        grid = cls(width=width, height=height, tiles=tiles)
        return grid


# ---------------------------------------------------------------------------
# Combat Units
# ---------------------------------------------------------------------------


class UnitTeam(enum.Enum):
    PLAYER = "player"
    ENEMY = "enemy"


@dataclass
class CombatStats:
    """Tactical-layer stats for a unit in combat."""

    max_hp: int
    hp: int
    attack: int
    armor: int
    movement: int
    attack_range: int  # 1 = melee only, >1 = ranged

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_hp": self.max_hp,
            "hp": self.hp,
            "attack": self.attack,
            "armor": self.armor,
            "movement": self.movement,
            "attack_range": self.attack_range,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CombatStats:
        return cls(
            max_hp=data["max_hp"],
            hp=data["hp"],
            attack=data["attack"],
            armor=data["armor"],
            movement=data["movement"],
            attack_range=data["attack_range"],
        )


@dataclass
class CombatUnit:
    """Wraps a narrative-layer entity with tactical combat state.

    ``entity_id`` links back to an Entity in the history system.
    ``unit_id`` is a unique key within a single combat instance.
    """

    unit_id: str
    name: str
    entity_id: str | None  # None for ad-hoc enemies without history entities
    team: UnitTeam
    stats: CombatStats
    x: int
    y: int
    alive: bool = True
    symbol: str = "?"
    has_moved: bool = False
    has_attacked: bool = False

    @property
    def hp(self) -> int:
        return self.stats.hp

    def take_damage(self, raw_damage: int) -> int:
        """Apply damage after armor. Returns actual damage dealt."""
        actual = max(1, raw_damage - self.stats.armor)
        self.stats.hp -= actual
        if self.stats.hp <= 0:
            self.stats.hp = 0
            self.alive = False
        return actual

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "entity_id": self.entity_id,
            "team": self.team.value,
            "stats": self.stats.to_dict(),
            "x": self.x,
            "y": self.y,
            "alive": self.alive,
            "symbol": self.symbol,
            "has_moved": self.has_moved,
            "has_attacked": self.has_attacked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CombatUnit:
        return cls(
            unit_id=data["unit_id"],
            name=data["name"],
            entity_id=data.get("entity_id"),
            team=UnitTeam(data["team"]),
            stats=CombatStats.from_dict(data["stats"]),
            x=data["x"],
            y=data["y"],
            alive=data.get("alive", True),
            symbol=data.get("symbol", "?"),
            has_moved=data.get("has_moved", False),
            has_attacked=data.get("has_attacked", False),
        )


# ---------------------------------------------------------------------------
# Pre-defined enemy templates
# ---------------------------------------------------------------------------

ENEMY_TEMPLATES: dict[str, dict[str, Any]] = {
    "servitor": {
        "name": "Rogue Servitor",
        "symbol": "S",
        "stats": {"max_hp": 8, "hp": 8, "attack": 3, "armor": 1, "movement": 3, "attack_range": 1},
    },
    "gunner": {
        "name": "Gun Servitor",
        "symbol": "G",
        "stats": {"max_hp": 5, "hp": 5, "attack": 4, "armor": 0, "movement": 2, "attack_range": 4},
    },
    "brute": {
        "name": "Corrupted Ogryn",
        "symbol": "O",
        "stats": {"max_hp": 15, "hp": 15, "attack": 5, "armor": 2, "movement": 2, "attack_range": 1},
    },
}


def make_enemy(template_key: str, x: int, y: int, unit_id: str | None = None) -> CombatUnit:
    """Create an enemy CombatUnit from a template."""
    tpl = ENEMY_TEMPLATES[template_key]
    uid = unit_id or f"enemy-{template_key}-{x}-{y}"
    return CombatUnit(
        unit_id=uid,
        name=tpl["name"],
        entity_id=None,
        team=UnitTeam.ENEMY,
        stats=CombatStats(**tpl["stats"]),
        x=x,
        y=y,
        symbol=tpl["symbol"],
    )


def make_player(x: int, y: int, entity_id: str | None = None) -> CombatUnit:
    """Create the player Tech-Priest unit."""
    return CombatUnit(
        unit_id="player",
        name="Magos Explorator",
        entity_id=entity_id,
        team=UnitTeam.PLAYER,
        stats=CombatStats(max_hp=20, hp=20, attack=5, armor=2, movement=4, attack_range=1),
        x=x,
        y=y,
        symbol="@",
    )


# ---------------------------------------------------------------------------
# Combat phase tracking
# ---------------------------------------------------------------------------


class CombatPhase(enum.Enum):
    PLAYER_TURN = "player_turn"
    ENEMY_TURN = "enemy_turn"
    VICTORY = "victory"
    DEFEAT = "defeat"


# ---------------------------------------------------------------------------
# Action log entry
# ---------------------------------------------------------------------------


@dataclass
class CombatLogEntry:
    """A single line in the combat action log."""

    text: str
    turn: int

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "turn": self.turn}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CombatLogEntry:
        return cls(text=data["text"], turn=data["turn"])


# ---------------------------------------------------------------------------
# Combat result (returned when combat ends)
# ---------------------------------------------------------------------------


@dataclass
class CombatResult:
    """Summary returned to the caller (GameScreen) when combat ends."""

    victory: bool
    player_hp_remaining: int
    player_hp_max: int
    enemies_defeated: int
    enemies_total: int
    turn_count: int
    log_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "victory": self.victory,
            "player_hp_remaining": self.player_hp_remaining,
            "player_hp_max": self.player_hp_max,
            "enemies_defeated": self.enemies_defeated,
            "enemies_total": self.enemies_total,
            "turn_count": self.turn_count,
            "log_summary": self.log_summary,
        }


# ---------------------------------------------------------------------------
# Hardcoded maps
# ---------------------------------------------------------------------------


def _build_corridor_map() -> Grid:
    """A small 20x15 corridor map with rooms and cover."""
    grid = Grid(width=20, height=15)
    # Walls around the border
    for x in range(20):
        grid.set_terrain(x, 0, Terrain.WALL)
        grid.set_terrain(x, 14, Terrain.WALL)
    for y in range(15):
        grid.set_terrain(0, y, Terrain.WALL)
        grid.set_terrain(19, y, Terrain.WALL)

    # Internal walls creating a corridor layout
    # Left room walls
    for y in range(1, 6):
        grid.set_terrain(8, y, Terrain.WALL)
    # Door opening at y=6
    for y in range(7, 10):
        grid.set_terrain(8, y, Terrain.WALL)
    # Right room walls
    for y in range(5, 10):
        grid.set_terrain(13, y, Terrain.WALL)
    # Door opening at y=10
    for y in range(11, 14):
        grid.set_terrain(13, y, Terrain.WALL)

    # Some debris for cover
    grid.set_terrain(3, 3, Terrain.DEBRIS)
    grid.set_terrain(4, 7, Terrain.DEBRIS)
    grid.set_terrain(10, 4, Terrain.DEBRIS)
    grid.set_terrain(15, 8, Terrain.DEBRIS)
    grid.set_terrain(16, 12, Terrain.DEBRIS)

    # Terminal flavour
    grid.set_terrain(2, 1, Terrain.TERMINAL)
    grid.set_terrain(17, 13, Terrain.TERMINAL)

    return grid


HARDCODED_MAPS: dict[str, dict[str, Any]] = {
    "corridor": {
        "name": "Sub-Level Corridor",
        "build": _build_corridor_map,
        "player_start": (2, 7),
        "enemies": [
            ("servitor", 10, 3),
            ("gunner", 16, 6),
            ("brute", 15, 11),
        ],
    },
}


# ---------------------------------------------------------------------------
# Pathfinding helpers
# ---------------------------------------------------------------------------


def manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    return abs(x2 - x1) + abs(y2 - y1)


def _step_toward(
    grid: Grid,
    sx: int,
    sy: int,
    tx: int,
    ty: int,
    occupied: set[tuple[int, int]],
) -> tuple[int, int]:
    """Return the best adjacent cell that moves (sx,sy) toward (tx,ty).

    Uses greedy Manhattan distance. Returns (sx,sy) if stuck.
    """
    best: tuple[int, int] = (sx, sy)
    best_dist = manhattan_distance(sx, sy, tx, ty)
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = sx + dx, sy + dy
        if not grid.in_bounds(nx, ny):
            continue
        if not grid.get_tile(nx, ny).passable:
            continue
        if (nx, ny) in occupied:
            continue
        dist = manhattan_distance(nx, ny, tx, ty)
        if dist < best_dist:
            best_dist = dist
            best = (nx, ny)
    return best


# ---------------------------------------------------------------------------
# CombatEngine
# ---------------------------------------------------------------------------


class CombatEngine:
    """Deterministic turn-based tactical combat engine.

    Manages the grid, units, turn structure, action resolution, and enemy AI.
    No LLM API calls -- all logic is local computation.
    """

    def __init__(self, map_key: str = "corridor") -> None:
        map_def = HARDCODED_MAPS[map_key]
        self._map_name: str = map_def["name"]
        self._map_key: str = map_key
        self._grid: Grid = map_def["build"]()
        self._units: dict[str, CombatUnit] = {}
        self._phase: CombatPhase = CombatPhase.PLAYER_TURN
        self._turn: int = 1
        self._log: list[CombatLogEntry] = []
        self._total_enemies: int = 0
        self._cursor_x: int = 0
        self._cursor_y: int = 0

        # Place player
        px, py = map_def["player_start"]
        player = make_player(px, py)
        self._units[player.unit_id] = player
        self._cursor_x = px
        self._cursor_y = py

        # Place enemies
        for template_key, ex, ey in map_def["enemies"]:
            enemy = make_enemy(template_key, ex, ey)
            self._units[enemy.unit_id] = enemy
            self._total_enemies += 1

        self._add_log(f"++ TACTICAL MODE: {self._map_name.upper()} ++")
        self._add_log("Your turn. Select action: move / attack / end_turn")

    # -- Properties ----------------------------------------------------------

    @property
    def grid(self) -> Grid:
        return self._grid

    @property
    def phase(self) -> CombatPhase:
        return self._phase

    @property
    def turn(self) -> int:
        return self._turn

    @property
    def log(self) -> list[CombatLogEntry]:
        return list(self._log)

    @property
    def map_name(self) -> str:
        return self._map_name

    @property
    def cursor(self) -> tuple[int, int]:
        return (self._cursor_x, self._cursor_y)

    @property
    def is_over(self) -> bool:
        return self._phase in (CombatPhase.VICTORY, CombatPhase.DEFEAT)

    # -- Unit queries --------------------------------------------------------

    def get_player(self) -> CombatUnit:
        return self._units["player"]

    def get_units(self) -> list[CombatUnit]:
        return list(self._units.values())

    def get_alive_units(self, team: UnitTeam | None = None) -> list[CombatUnit]:
        return [
            u for u in self._units.values()
            if u.alive and (team is None or u.team == team)
        ]

    def get_unit_at(self, x: int, y: int) -> CombatUnit | None:
        for u in self._units.values():
            if u.alive and u.x == x and u.y == y:
                return u
        return None

    def _occupied_positions(self) -> set[tuple[int, int]]:
        return {(u.x, u.y) for u in self._units.values() if u.alive}

    # -- Logging -------------------------------------------------------------

    def _add_log(self, text: str) -> None:
        self._log.append(CombatLogEntry(text=text, turn=self._turn))

    # -- Movement validation -------------------------------------------------

    def get_reachable_tiles(self, unit: CombatUnit) -> set[tuple[int, int]]:
        """BFS to find all tiles reachable by ``unit`` within its movement range."""
        occupied = self._occupied_positions()
        occupied.discard((unit.x, unit.y))
        reachable: set[tuple[int, int]] = set()
        # (x, y, remaining_movement)
        frontier: list[tuple[int, int, int]] = [(unit.x, unit.y, unit.stats.movement)]
        visited: dict[tuple[int, int], int] = {(unit.x, unit.y): unit.stats.movement}

        while frontier:
            cx, cy, remaining = frontier.pop(0)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if not self._grid.in_bounds(nx, ny):
                    continue
                tile = self._grid.get_tile(nx, ny)
                if not tile.passable:
                    continue
                if (nx, ny) in occupied:
                    continue
                cost = tile.movement_cost
                new_remaining = remaining - cost
                if new_remaining < 0:
                    continue
                prev = visited.get((nx, ny), -1)
                if new_remaining > prev:
                    visited[(nx, ny)] = new_remaining
                    reachable.add((nx, ny))
                    frontier.append((nx, ny, new_remaining))

        return reachable

    def get_attackable_units(self, unit: CombatUnit) -> list[CombatUnit]:
        """Return enemy units within attack range of ``unit``."""
        targets: list[CombatUnit] = []
        for other in self._units.values():
            if not other.alive or other.team == unit.team:
                continue
            dist = manhattan_distance(unit.x, unit.y, other.x, other.y)
            if dist <= unit.stats.attack_range:
                targets.append(other)
        return targets

    # -- Player actions ------------------------------------------------------

    def move_cursor(self, dx: int, dy: int) -> None:
        """Move the selection cursor."""
        nx = self._cursor_x + dx
        ny = self._cursor_y + dy
        if self._grid.in_bounds(nx, ny):
            self._cursor_x = nx
            self._cursor_y = ny

    def player_move(self, target_x: int, target_y: int) -> bool:
        """Move the player unit to (target_x, target_y). Returns True on success."""
        if self._phase != CombatPhase.PLAYER_TURN:
            return False
        player = self.get_player()
        if not player.alive or player.has_moved:
            self._add_log("Already moved this turn.")
            return False
        reachable = self.get_reachable_tiles(player)
        if (target_x, target_y) not in reachable:
            self._add_log("Cannot reach that tile.")
            return False
        player.x = target_x
        player.y = target_y
        player.has_moved = True
        self._add_log(f"Moved to ({target_x},{target_y}).")
        self._cursor_x = target_x
        self._cursor_y = target_y
        return True

    def player_attack(self, target_unit_id: str) -> bool:
        """Player attacks the specified unit. Returns True on success."""
        if self._phase != CombatPhase.PLAYER_TURN:
            return False
        player = self.get_player()
        if not player.alive or player.has_attacked:
            self._add_log("Already attacked this turn.")
            return False
        target = self._units.get(target_unit_id)
        if not target or not target.alive:
            self._add_log("Invalid target.")
            return False
        dist = manhattan_distance(player.x, player.y, target.x, target.y)
        if dist > player.stats.attack_range:
            self._add_log(f"{target.name} is out of range (dist={dist}, range={player.stats.attack_range}).")
            return False
        actual = target.take_damage(player.stats.attack)
        self._add_log(f"Attacked {target.name} for {actual} damage! (HP: {target.stats.hp}/{target.stats.max_hp})")
        player.has_attacked = True
        if not target.alive:
            self._add_log(f"{target.name} destroyed!")
        self._check_end_conditions()
        return True

    def end_player_turn(self) -> None:
        """End the player's turn and begin enemy phase."""
        if self._phase != CombatPhase.PLAYER_TURN:
            return
        self._add_log("-- End of player turn --")
        self._phase = CombatPhase.ENEMY_TURN
        self._run_enemy_turn()

    # -- Enemy AI ------------------------------------------------------------

    def _run_enemy_turn(self) -> None:
        """Execute AI for all living enemy units."""
        self._add_log(f"[Turn {self._turn}] Enemy phase")
        player = self.get_player()
        if not player.alive:
            self._check_end_conditions()
            return

        occupied = self._occupied_positions()

        for enemy in self.get_alive_units(UnitTeam.ENEMY):
            dist = manhattan_distance(enemy.x, enemy.y, player.x, player.y)

            # Attack if in range
            if dist <= enemy.stats.attack_range:
                actual = player.take_damage(enemy.stats.attack)
                self._add_log(
                    f"{enemy.name} attacks you for {actual} damage! "
                    f"(HP: {player.stats.hp}/{player.stats.max_hp})"
                )
                if not player.alive:
                    self._add_log("++ CRITICAL FAILURE: SYSTEMS OFFLINE ++")
                    self._check_end_conditions()
                    return
            else:
                # Move toward player
                occupied.discard((enemy.x, enemy.y))
                steps_remaining = enemy.stats.movement
                while steps_remaining > 0:
                    nx, ny = _step_toward(
                        self._grid, enemy.x, enemy.y,
                        player.x, player.y, occupied,
                    )
                    if (nx, ny) == (enemy.x, enemy.y):
                        break  # stuck
                    cost = self._grid.get_tile(nx, ny).movement_cost
                    if cost > steps_remaining:
                        break
                    enemy.x = nx
                    enemy.y = ny
                    steps_remaining -= cost
                occupied.add((enemy.x, enemy.y))

                # Check if now in attack range after moving
                dist = manhattan_distance(enemy.x, enemy.y, player.x, player.y)
                if dist <= enemy.stats.attack_range:
                    actual = player.take_damage(enemy.stats.attack)
                    self._add_log(
                        f"{enemy.name} advances and attacks for {actual} damage! "
                        f"(HP: {player.stats.hp}/{player.stats.max_hp})"
                    )
                    if not player.alive:
                        self._add_log("++ CRITICAL FAILURE: SYSTEMS OFFLINE ++")
                        self._check_end_conditions()
                        return
                else:
                    self._add_log(f"{enemy.name} moves toward you.")

        self._check_end_conditions()
        if not self.is_over:
            self._begin_player_turn()

    def _begin_player_turn(self) -> None:
        """Reset player unit flags and start a new player turn."""
        self._turn += 1
        self._phase = CombatPhase.PLAYER_TURN
        player = self.get_player()
        player.has_moved = False
        player.has_attacked = False
        self._add_log(f"[Turn {self._turn}] Your turn. move / attack / end_turn")

    # -- Win/loss checks -----------------------------------------------------

    def _check_end_conditions(self) -> None:
        """Check for victory or defeat."""
        player = self.get_player()
        if not player.alive:
            self._phase = CombatPhase.DEFEAT
            self._add_log("++ DEFEAT -- THE MACHINE SPIRIT FADES ++")
            return
        enemies_alive = self.get_alive_units(UnitTeam.ENEMY)
        if not enemies_alive:
            self._phase = CombatPhase.VICTORY
            self._add_log("++ VICTORY -- THE OMNISSIAH IS PLEASED ++")

    # -- Result construction -------------------------------------------------

    def get_result(self) -> CombatResult:
        """Build a CombatResult summary. Only meaningful when ``is_over`` is True."""
        player = self.get_player()
        enemies_defeated = sum(
            1 for u in self._units.values()
            if u.team == UnitTeam.ENEMY and not u.alive
        )
        log_lines = [e.text for e in self._log[-10:]]
        return CombatResult(
            victory=self._phase == CombatPhase.VICTORY,
            player_hp_remaining=player.stats.hp,
            player_hp_max=player.stats.max_hp,
            enemies_defeated=enemies_defeated,
            enemies_total=self._total_enemies,
            turn_count=self._turn,
            log_summary="\n".join(log_lines),
        )

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "map_key": self._map_key,
            "map_name": self._map_name,
            "grid": self._grid.to_dict(),
            "units": {uid: u.to_dict() for uid, u in self._units.items()},
            "phase": self._phase.value,
            "turn": self._turn,
            "log": [e.to_dict() for e in self._log],
            "total_enemies": self._total_enemies,
            "cursor_x": self._cursor_x,
            "cursor_y": self._cursor_y,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CombatEngine:
        engine = cls.__new__(cls)
        engine._map_key = data["map_key"]
        engine._map_name = data["map_name"]
        engine._grid = Grid.from_dict(data["grid"])
        engine._units = {
            uid: CombatUnit.from_dict(ud) for uid, ud in data["units"].items()
        }
        engine._phase = CombatPhase(data["phase"])
        engine._turn = data["turn"]
        engine._log = [CombatLogEntry.from_dict(e) for e in data["log"]]
        engine._total_enemies = data["total_enemies"]
        engine._cursor_x = data.get("cursor_x", 0)
        engine._cursor_y = data.get("cursor_y", 0)
        return engine
