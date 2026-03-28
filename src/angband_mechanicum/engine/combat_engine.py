"""Turn-based tactical combat engine.

Deterministic combat logic -- NO LLM API calls. Handles grid state,
unit positions, HP/stats, turn order, action resolution, and enemy AI.
Fully serializable via to_dict()/from_dict() for save compatibility.
"""

from __future__ import annotations

import enum
import heapq
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
    template_key: str = ""  # enemy template key (e.g. "servitor"); empty for player/party
    total_damage_dealt: int = 0  # accumulated damage this unit has inflicted

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
            "template_key": self.template_key,
            "total_damage_dealt": self.total_damage_dealt,
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
            template_key=data.get("template_key", ""),
            total_damage_dealt=data.get("total_damage_dealt", 0),
        )


# ---------------------------------------------------------------------------
# Pre-defined enemy templates
# ---------------------------------------------------------------------------

ENEMY_TEMPLATES: dict[str, dict[str, Any]] = {
    # -- Mechanicum threats --
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
    # -- Hive scum --
    "thug": {
        "name": "Underhive Thug",
        "symbol": "T",
        "stats": {"max_hp": 6, "hp": 6, "attack": 2, "armor": 0, "movement": 4, "attack_range": 1},
    },
    "ganger": {
        "name": "Hive Ganger",
        "symbol": "g",
        "stats": {"max_hp": 7, "hp": 7, "attack": 3, "armor": 0, "movement": 3, "attack_range": 3},
    },
    # -- Chaos --
    "cultist": {
        "name": "Chaos Cultist",
        "symbol": "c",
        "stats": {"max_hp": 6, "hp": 6, "attack": 3, "armor": 0, "movement": 3, "attack_range": 1},
    },
    "berserker": {
        "name": "Khorne Berserker",
        "symbol": "B",
        "stats": {"max_hp": 14, "hp": 14, "attack": 7, "armor": 2, "movement": 3, "attack_range": 1},
    },
    "sorcerer": {
        "name": "Chaos Sorcerer",
        "symbol": "Z",
        "stats": {"max_hp": 8, "hp": 8, "attack": 5, "armor": 1, "movement": 2, "attack_range": 5},
    },
    "marine": {
        "name": "Chaos Marine",
        "symbol": "M",
        "stats": {"max_hp": 18, "hp": 18, "attack": 6, "armor": 3, "movement": 3, "attack_range": 3},
    },
    # -- Tyranid --
    "hormagaunt": {
        "name": "Hormagaunt",
        "symbol": "h",
        "stats": {"max_hp": 5, "hp": 5, "attack": 3, "armor": 0, "movement": 5, "attack_range": 1},
    },
    "termagant": {
        "name": "Termagant",
        "symbol": "t",
        "stats": {"max_hp": 5, "hp": 5, "attack": 2, "armor": 0, "movement": 4, "attack_range": 3},
    },
    "warrior": {
        "name": "Tyranid Warrior",
        "symbol": "W",
        "stats": {"max_hp": 16, "hp": 16, "attack": 6, "armor": 2, "movement": 4, "attack_range": 2},
    },
    # -- Ork --
    "ork_boy": {
        "name": "Ork Boy",
        "symbol": "o",
        "stats": {"max_hp": 10, "hp": 10, "attack": 4, "armor": 1, "movement": 3, "attack_range": 1},
    },
    "ork_shoota": {
        "name": "Ork Shoota Boy",
        "symbol": "s",
        "stats": {"max_hp": 9, "hp": 9, "attack": 3, "armor": 1, "movement": 3, "attack_range": 4},
    },
    # -- Generic / misc --
    "heretic": {
        "name": "Heretek",
        "symbol": "H",
        "stats": {"max_hp": 10, "hp": 10, "attack": 4, "armor": 1, "movement": 3, "attack_range": 2},
    },
    "mutant": {
        "name": "Warp Mutant",
        "symbol": "m",
        "stats": {"max_hp": 12, "hp": 12, "attack": 5, "armor": 1, "movement": 2, "attack_range": 1},
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
        template_key=template_key,
    )


def auto_place_enemies(
    grid: Grid,
    enemy_counts: list[tuple[str, int]],
    occupied: set[tuple[int, int]] | None = None,
) -> list[tuple[str, int, int]]:
    """Auto-place enemies on valid floor tiles in the right half of the map.

    *enemy_counts* is a list of (template_key, count) pairs.
    Returns a list of (template_key, x, y) tuples suitable for ``CombatEngine(enemy_roster=...)``.
    """
    placed: list[tuple[str, int, int]] = []
    used: set[tuple[int, int]] = set(occupied) if occupied else set()
    mid_x = grid.width // 2

    # Collect candidate positions — right half of the map, floor only
    candidates: list[tuple[int, int]] = []
    for y in range(grid.height):
        for x in range(mid_x, grid.width):
            tile = grid.get_tile(x, y)
            if tile.passable and (x, y) not in used:
                candidates.append((x, y))

    idx = 0
    for template_key, count in enemy_counts:
        if template_key not in ENEMY_TEMPLATES:
            continue
        for _ in range(count):
            # Find the next unoccupied candidate
            while idx < len(candidates) and candidates[idx] in used:
                idx += 1
            if idx >= len(candidates):
                break  # no more room
            ex, ey = candidates[idx]
            used.add((ex, ey))
            placed.append((template_key, ex, ey))
            idx += 1

    return placed


def make_player(
    x: int,
    y: int,
    entity_id: str | None = None,
    hp: int | None = None,
    max_hp: int | None = None,
) -> CombatUnit:
    """Create the player Tech-Priest unit.

    *hp* and *max_hp* default to 20 when not supplied, allowing the caller
    to inject the current story-mode integrity.
    """
    actual_max_hp = max_hp if max_hp is not None else 20
    actual_hp = hp if hp is not None else actual_max_hp
    return CombatUnit(
        unit_id="player",
        name="Magos Explorator",
        entity_id=entity_id,
        team=UnitTeam.PLAYER,
        stats=CombatStats(max_hp=actual_max_hp, hp=actual_hp, attack=5, armor=2, movement=4, attack_range=1),
        x=x,
        y=y,
        symbol="@",
    )


# ---------------------------------------------------------------------------
# Party member templates (allies derived from narrative game state)
# ---------------------------------------------------------------------------

PARTY_TEMPLATES: dict[str, dict[str, Any]] = {
    "skitarius-alpha-7": {
        "name": "Skitarius Alpha-7",
        "symbol": "A",
        "stats": {"max_hp": 12, "hp": 12, "attack": 4, "armor": 1, "movement": 4, "attack_range": 5},
    },
    "enginseer-volta": {
        "name": "Enginseer Volta",
        "symbol": "V",
        "stats": {"max_hp": 14, "hp": 14, "attack": 6, "armor": 1, "movement": 3, "attack_range": 1},
    },
}


def make_party_member(entity_id: str, x: int, y: int) -> CombatUnit:
    """Create a party member CombatUnit from PARTY_TEMPLATES.

    The entity_id must exist in PARTY_TEMPLATES. The unit_id is set to
    the entity_id for straightforward lookup.
    """
    tpl = PARTY_TEMPLATES[entity_id]
    return CombatUnit(
        unit_id=entity_id,
        name=tpl["name"],
        entity_id=entity_id,
        team=UnitTeam.PLAYER,
        stats=CombatStats(**tpl["stats"]),
        x=x,
        y=y,
        symbol=tpl["symbol"],
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
class EnemyRecord:
    """Record of an enemy encountered during combat.

    Captures enough detail for LLM context and future encounter generation.
    """

    name: str
    template_key: str  # e.g. "servitor", "gunner", "brute"
    defeated: bool
    max_hp: int
    damage_dealt: int  # total damage this enemy inflicted on player-team units

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template_key": self.template_key,
            "defeated": self.defeated,
            "max_hp": self.max_hp,
            "damage_dealt": self.damage_dealt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnemyRecord:
        return cls(
            name=data["name"],
            template_key=data["template_key"],
            defeated=data["defeated"],
            max_hp=data.get("max_hp", 0),
            damage_dealt=data.get("damage_dealt", 0),
        )


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
    enemies: list[EnemyRecord] = field(default_factory=list)
    total_player_damage_taken: int = 0  # aggregate damage the player-team absorbed
    # Per-party-member HP after combat: {entity_id: (hp, max_hp)}
    party_hp: dict[str, tuple[int, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "victory": self.victory,
            "player_hp_remaining": self.player_hp_remaining,
            "player_hp_max": self.player_hp_max,
            "enemies_defeated": self.enemies_defeated,
            "enemies_total": self.enemies_total,
            "turn_count": self.turn_count,
            "log_summary": self.log_summary,
            "enemies": [e.to_dict() for e in self.enemies],
            "total_player_damage_taken": self.total_player_damage_taken,
            "party_hp": {k: list(v) for k, v in self.party_hp.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CombatResult:
        enemies_data = data.get("enemies", [])
        raw_party_hp = data.get("party_hp", {})
        party_hp = {k: (v[0], v[1]) for k, v in raw_party_hp.items()}
        return cls(
            victory=data["victory"],
            player_hp_remaining=data["player_hp_remaining"],
            player_hp_max=data["player_hp_max"],
            enemies_defeated=data["enemies_defeated"],
            enemies_total=data["enemies_total"],
            turn_count=data["turn_count"],
            log_summary=data["log_summary"],
            enemies=[EnemyRecord.from_dict(e) for e in enemies_data],
            total_player_damage_taken=data.get("total_player_damage_taken", 0),
            party_hp=party_hp,
        )


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
        "party_starts": [(3, 6), (3, 8)],  # near the player
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


def has_line_of_sight(
    grid: Grid, x1: int, y1: int, x2: int, y2: int
) -> bool:
    """Check whether a clear line exists between two points on the grid.

    Uses Bresenham's line algorithm.  Returns False if any WALL tile lies
    on the line between (x1, y1) and (x2, y2) (exclusive of endpoints).
    """
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy
    cx, cy = x1, y1

    while True:
        # Advance one step
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy

        # Reached the target -- line is clear
        if cx == x2 and cy == y2:
            return True

        # Check intermediate tile
        if not grid.in_bounds(cx, cy):
            return False
        if not grid.get_tile(cx, cy).passable:
            return False


def _astar_path(
    grid: Grid,
    sx: int,
    sy: int,
    tx: int,
    ty: int,
    occupied: set[tuple[int, int]],
    max_cost: int | None = None,
) -> list[tuple[int, int]]:
    """A* pathfinding from (sx,sy) to (tx,ty), respecting terrain costs.

    *occupied* contains positions blocked by other units.  The target
    position is treated as passable so melee units can path toward an
    occupied target square (the caller will stop one step short).

    Returns a list of (x,y) steps **excluding** the start.  An empty list
    means the target is unreachable (or the unit is already there).

    When *max_cost* is given the search prunes branches whose g-cost
    exceeds the budget, keeping the search cheap for AI movement.
    """
    if (sx, sy) == (tx, ty):
        return []

    # Priority queue entries: (f_cost, counter, x, y)
    counter = 0
    open_set: list[tuple[int, int, int, int]] = []
    heapq.heappush(open_set, (manhattan_distance(sx, sy, tx, ty), counter, sx, sy))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_cost: dict[tuple[int, int], int] = {(sx, sy): 0}

    while open_set:
        _f, _cnt, cx, cy = heapq.heappop(open_set)

        if (cx, cy) == (tx, ty):
            # Reconstruct path
            path: list[tuple[int, int]] = []
            cur = (tx, ty)
            while cur != (sx, sy):
                path.append(cur)
                cur = came_from[cur]
            path.reverse()
            return path

        current_g = g_cost[(cx, cy)]

        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if not grid.in_bounds(nx, ny):
                continue
            tile = grid.get_tile(nx, ny)
            if not tile.passable:
                continue
            # Other units block passage, except the target square itself
            if (nx, ny) in occupied and (nx, ny) != (tx, ty):
                continue
            new_g = current_g + tile.movement_cost
            if max_cost is not None and new_g > max_cost:
                continue
            prev_g = g_cost.get((nx, ny))
            if prev_g is None or new_g < prev_g:
                g_cost[(nx, ny)] = new_g
                f = new_g + manhattan_distance(nx, ny, tx, ty)
                counter += 1
                heapq.heappush(open_set, (f, counter, nx, ny))
                came_from[(nx, ny)] = (cx, cy)

    return []  # no path found


def _step_toward(
    grid: Grid,
    sx: int,
    sy: int,
    tx: int,
    ty: int,
    occupied: set[tuple[int, int]],
) -> tuple[int, int]:
    """Return the best adjacent cell that moves (sx,sy) toward (tx,ty).

    Uses A* pathfinding so units navigate around obstacles instead of
    getting stuck against walls.  Falls back to (sx, sy) when truly stuck.
    """
    path = _astar_path(grid, sx, sy, tx, ty, occupied, max_cost=30)
    if path:
        return path[0]
    # Fallback: greedy single step (handles edge cases where A* finds no path)
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

    def __init__(
        self,
        map_key: str = "corridor",
        player_hp: int | None = None,
        player_max_hp: int | None = None,
        party_ids: list[str] | None = None,
        enemy_roster: list[tuple[str, int, int]] | None = None,
    ) -> None:
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

        # Place player (use story-mode integrity when provided)
        px, py = map_def["player_start"]
        player = make_player(px, py, hp=player_hp, max_hp=player_max_hp)
        self._units[player.unit_id] = player
        self._cursor_x = px
        self._cursor_y = py

        # Place party members near the player
        party_starts: list[tuple[int, int]] = map_def.get("party_starts", [])
        effective_party = party_ids or []
        for i, pid in enumerate(effective_party):
            if pid not in PARTY_TEMPLATES:
                continue
            if i < len(party_starts):
                mx, my = party_starts[i]
            else:
                # Fallback: offset from player start
                mx, my = px + 1 + i, py
            member = make_party_member(pid, mx, my)
            self._units[member.unit_id] = member

        # Track player unit ordering for multi-unit turns
        self._player_unit_ids: list[str] = [
            u.unit_id for u in self._units.values()
            if u.team == UnitTeam.PLAYER
        ]
        self._active_unit_index: int = 0
        self._active_unit_id: str = self._player_unit_ids[0]

        # Place enemies — use roster if provided, else fall back to map defaults
        enemies_to_place = enemy_roster if enemy_roster is not None else map_def["enemies"]
        for template_key, ex, ey in enemies_to_place:
            if template_key not in ENEMY_TEMPLATES:
                continue
            enemy = make_enemy(template_key, ex, ey)
            self._units[enemy.unit_id] = enemy
            self._total_enemies += 1

        self._add_log(f"++ TACTICAL MODE: {self._map_name.upper()} ++")
        active = self._units[self._active_unit_id]
        self._add_log(f"Your turn. Active: {active.name}. move / attack / end_turn / Tab:next")

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

    # -- Active unit management -----------------------------------------------

    @property
    def active_unit_id(self) -> str:
        """The unit_id of the currently selected player unit."""
        return self._active_unit_id

    def get_active_unit(self) -> CombatUnit:
        """Return the currently active player unit."""
        return self._units[self._active_unit_id]

    def select_unit(self, unit_id: str) -> bool:
        """Switch active unit to the given unit_id. Returns True on success."""
        if unit_id not in self._player_unit_ids:
            return False
        unit = self._units[unit_id]
        if not unit.alive:
            return False
        self._active_unit_id = unit_id
        self._active_unit_index = self._player_unit_ids.index(unit_id)
        self._cursor_x = unit.x
        self._cursor_y = unit.y
        self._add_log(f"Selected {unit.name}.")
        return True

    def cycle_active_unit(self) -> str:
        """Cycle to the next living player unit. Returns the new active unit_id."""
        alive_ids = [
            uid for uid in self._player_unit_ids
            if self._units[uid].alive
        ]
        if not alive_ids:
            return self._active_unit_id
        # Find current position in alive list
        try:
            idx = alive_ids.index(self._active_unit_id)
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(alive_ids)
        next_id = alive_ids[next_idx]
        self._active_unit_id = next_id
        self._active_unit_index = self._player_unit_ids.index(next_id)
        unit = self._units[next_id]
        self._cursor_x = unit.x
        self._cursor_y = unit.y
        self._add_log(f"Selected {unit.name}.")
        return next_id

    @property
    def player_unit_ids(self) -> list[str]:
        """Ordered list of all player-team unit IDs (alive or dead)."""
        return list(self._player_unit_ids)

    # -- Unit queries --------------------------------------------------------

    def get_player(self) -> CombatUnit:
        """Return the player Tech-Priest unit (always unit_id='player')."""
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
        """Move the active player unit to (target_x, target_y). Returns True on success."""
        if self._phase != CombatPhase.PLAYER_TURN:
            return False
        unit = self.get_active_unit()
        if not unit.alive or unit.has_moved:
            self._add_log(f"{unit.name} already moved this turn.")
            return False
        reachable = self.get_reachable_tiles(unit)
        if (target_x, target_y) not in reachable:
            self._add_log("Cannot reach that tile.")
            return False
        unit.x = target_x
        unit.y = target_y
        unit.has_moved = True
        self._add_log(f"{unit.name} moved to ({target_x},{target_y}).")
        self._cursor_x = target_x
        self._cursor_y = target_y
        return True

    def player_attack(self, target_unit_id: str) -> bool:
        """Active player unit attacks the specified unit. Returns True on success."""
        if self._phase != CombatPhase.PLAYER_TURN:
            return False
        unit = self.get_active_unit()
        if not unit.alive or unit.has_attacked:
            self._add_log(f"{unit.name} already attacked this turn.")
            return False
        target = self._units.get(target_unit_id)
        if not target or not target.alive:
            self._add_log("Invalid target.")
            return False
        dist = manhattan_distance(unit.x, unit.y, target.x, target.y)
        if dist > unit.stats.attack_range:
            self._add_log(f"{target.name} is out of range (dist={dist}, range={unit.stats.attack_range}).")
            return False
        actual = target.take_damage(unit.stats.attack)
        unit.total_damage_dealt += actual
        self._add_log(f"{unit.name} attacks {target.name} for {actual} damage! (HP: {target.stats.hp}/{target.stats.max_hp})")
        unit.has_attacked = True
        if not target.alive:
            self._add_log(f"{target.name} destroyed!")
        self._check_end_conditions()
        return True

    def _all_player_units_done(self) -> bool:
        """Check if all living player units have used their actions."""
        for uid in self._player_unit_ids:
            unit = self._units[uid]
            if unit.alive and (not unit.has_moved or not unit.has_attacked):
                return False
        return True

    def end_player_turn(self) -> None:
        """End the player's turn and begin enemy phase.

        Only proceeds when called explicitly -- the player decides when
        all party members have acted (or chooses to end early).
        """
        if self._phase != CombatPhase.PLAYER_TURN:
            return
        self._add_log("-- End of player turn --")
        self._phase = CombatPhase.ENEMY_TURN
        self._run_enemy_turn()

    # -- Enemy AI ------------------------------------------------------------

    def _find_nearest_player_unit(
        self, enemy: CombatUnit
    ) -> CombatUnit | None:
        """Find the nearest living player-team unit to the given enemy."""
        best: CombatUnit | None = None
        best_dist = 9999
        for u in self.get_alive_units(UnitTeam.PLAYER):
            dist = manhattan_distance(enemy.x, enemy.y, u.x, u.y)
            if dist < best_dist:
                best_dist = dist
                best = u
        return best

    def _find_best_ranged_target(
        self, enemy: CombatUnit
    ) -> CombatUnit | None:
        """Find the best target for a ranged enemy: in range AND has LoS.

        Prefers the nearest target with clear line of sight within attack
        range.  Returns None if no valid ranged target exists.
        """
        best: CombatUnit | None = None
        best_dist = 9999
        for u in self.get_alive_units(UnitTeam.PLAYER):
            dist = manhattan_distance(enemy.x, enemy.y, u.x, u.y)
            if dist > enemy.stats.attack_range:
                continue
            if not has_line_of_sight(self._grid, enemy.x, enemy.y, u.x, u.y):
                continue
            if dist < best_dist:
                best_dist = dist
                best = u
        return best

    def _enemy_attack(
        self, enemy: CombatUnit, target: CombatUnit, prefix: str = ""
    ) -> bool:
        """Resolve an enemy attack on *target*.  Returns True if combat ended."""
        actual = target.take_damage(enemy.stats.attack)
        enemy.total_damage_dealt += actual
        msg_prefix = f"{prefix}" if prefix else ""
        self._add_log(
            f"{msg_prefix}{enemy.name} attacks {target.name} for {actual} damage! "
            f"(HP: {target.stats.hp}/{target.stats.max_hp})"
        )
        if not target.alive:
            if target.unit_id == "player":
                self._add_log("++ CRITICAL FAILURE: SYSTEMS OFFLINE ++")
            else:
                self._add_log(f"{target.name} is down!")
            self._check_end_conditions()
        return self.is_over

    def _run_enemy_turn(self) -> None:
        """Execute AI for all living enemy units.

        Decision priority for each enemy:
        1. **Ranged with LoS** -- If the enemy has attack_range > 1, a target
           is within range, AND has clear line of sight, fire without moving.
        2. **Melee in range** -- If already adjacent to a target, attack.
        3. **Move then attack** -- Use A*-based pathfinding to navigate toward
           the nearest player unit, then attack if now in range with LoS.
        """
        self._add_log(f"[Turn {self._turn}] Enemy phase")
        player_units = self.get_alive_units(UnitTeam.PLAYER)
        if not player_units:
            self._check_end_conditions()
            return

        occupied = self._occupied_positions()

        for enemy in self.get_alive_units(UnitTeam.ENEMY):
            is_ranged = enemy.stats.attack_range > 1

            # --- Priority 1: Ranged attack with line of sight ---------------
            if is_ranged:
                ranged_target = self._find_best_ranged_target(enemy)
                if ranged_target is not None:
                    if self._enemy_attack(enemy, ranged_target):
                        return
                    continue  # Ranged enemy fired; turn done for this unit

            # --- Priority 2: Melee attack if already adjacent ---------------
            nearest = self._find_nearest_player_unit(enemy)
            if nearest is None:
                continue
            dist = manhattan_distance(enemy.x, enemy.y, nearest.x, nearest.y)

            if dist <= enemy.stats.attack_range:
                # Melee (or short-range) unit already in range -- attack
                if self._enemy_attack(enemy, nearest):
                    return
                continue

            # --- Priority 3: Move toward target, then try to attack ---------
            occupied.discard((enemy.x, enemy.y))

            # Use A* to compute a full path, then walk along it
            path = _astar_path(
                self._grid, enemy.x, enemy.y,
                nearest.x, nearest.y, occupied,
                max_cost=30,
            )
            steps_remaining = enemy.stats.movement
            if path:
                for px, py in path:
                    # Don't walk onto the target's square
                    if (px, py) in occupied:
                        break
                    cost = self._grid.get_tile(px, py).movement_cost
                    if cost > steps_remaining:
                        break
                    enemy.x = px
                    enemy.y = py
                    steps_remaining -= cost
            else:
                # A* found no path -- try greedy single steps as fallback
                while steps_remaining > 0:
                    nx, ny = _step_toward(
                        self._grid, enemy.x, enemy.y,
                        nearest.x, nearest.y, occupied,
                    )
                    if (nx, ny) == (enemy.x, enemy.y):
                        break
                    cost = self._grid.get_tile(nx, ny).movement_cost
                    if cost > steps_remaining:
                        break
                    enemy.x = nx
                    enemy.y = ny
                    steps_remaining -= cost

            occupied.add((enemy.x, enemy.y))

            # After moving, check whether we can now attack
            # For ranged enemies: need LoS; for melee: need adjacency
            attack_target: CombatUnit | None = None
            if is_ranged:
                attack_target = self._find_best_ranged_target(enemy)
            else:
                dist = manhattan_distance(enemy.x, enemy.y, nearest.x, nearest.y)
                if dist <= enemy.stats.attack_range:
                    attack_target = nearest

            if attack_target is not None:
                if self._enemy_attack(enemy, attack_target, prefix=""):
                    return
            else:
                self._add_log(f"{enemy.name} moves toward {nearest.name}.")

        self._check_end_conditions()
        if not self.is_over:
            self._begin_player_turn()

    def _begin_player_turn(self) -> None:
        """Reset all player unit flags and start a new player turn."""
        self._turn += 1
        self._phase = CombatPhase.PLAYER_TURN
        for uid in self._player_unit_ids:
            unit = self._units[uid]
            if unit.alive:
                unit.has_moved = False
                unit.has_attacked = False
        # Select the first living player unit
        for uid in self._player_unit_ids:
            if self._units[uid].alive:
                self._active_unit_id = uid
                self._active_unit_index = self._player_unit_ids.index(uid)
                break
        active = self._units[self._active_unit_id]
        self._cursor_x = active.x
        self._cursor_y = active.y
        self._add_log(f"[Turn {self._turn}] Your turn. Active: {active.name}. move / attack / end_turn / Tab:next")

    # -- Win/loss checks -----------------------------------------------------

    def _check_end_conditions(self) -> None:
        """Check for victory or defeat.

        Defeat occurs when the player Tech-Priest (unit_id='player') falls.
        Party members can be downed without ending the battle.
        """
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

        # Build detailed enemy roster
        enemy_records: list[EnemyRecord] = []
        for u in self._units.values():
            if u.team == UnitTeam.ENEMY:
                enemy_records.append(
                    EnemyRecord(
                        name=u.name,
                        template_key=u.template_key,
                        defeated=not u.alive,
                        max_hp=u.stats.max_hp,
                        damage_dealt=u.total_damage_dealt,
                    )
                )

        # Total damage absorbed by player-team units
        total_player_damage = sum(
            u.total_damage_dealt
            for u in self._units.values()
            if u.team == UnitTeam.ENEMY
        )

        # Collect per-party-member HP (non-player allies)
        party_hp: dict[str, tuple[int, int]] = {}
        for u in self._units.values():
            if u.team == UnitTeam.PLAYER and u.entity_id and u.unit_id != "player":
                party_hp[u.entity_id] = (u.stats.hp, u.stats.max_hp)

        return CombatResult(
            victory=self._phase == CombatPhase.VICTORY,
            player_hp_remaining=player.stats.hp,
            player_hp_max=player.stats.max_hp,
            enemies_defeated=enemies_defeated,
            enemies_total=self._total_enemies,
            turn_count=self._turn,
            log_summary="\n".join(log_lines),
            enemies=enemy_records,
            total_player_damage_taken=total_player_damage,
            party_hp=party_hp,
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
            "player_unit_ids": list(self._player_unit_ids),
            "active_unit_id": self._active_unit_id,
            "active_unit_index": self._active_unit_index,
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
        # Multi-unit state (backwards-compatible with old saves)
        engine._player_unit_ids = data.get("player_unit_ids", ["player"])
        engine._active_unit_id = data.get("active_unit_id", "player")
        engine._active_unit_index = data.get("active_unit_index", 0)
        return engine
