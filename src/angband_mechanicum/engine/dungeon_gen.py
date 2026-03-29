"""Procedural dungeon / room generation for tactical combat maps.

Generates Grid instances with varied room archetypes, terrain features,
and spawn points.  Designed to fit visible terminal dimensions (60-80 wide,
20-30 tall) and integrate with the existing combat engine.

No LLM calls -- pure deterministic (seeded) generation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from angband_mechanicum.engine.combat_engine import Grid, Terrain
from angband_mechanicum.engine.dungeon_level import (
    ENVIRONMENTS,
    DungeonLevel,
    DungeonTerrain,
)


# ---------------------------------------------------------------------------
# Extended terrain helpers
# ---------------------------------------------------------------------------
# The combat engine already has FLOOR, WALL, DEBRIS, TERMINAL.
# We add higher-level "feature" placement that maps onto existing Terrain
# values plus new ones we define here.

# New terrain types for richer maps -- extend the Terrain enum at import time
# so the rest of the engine can serialise/deserialise them.

def _ensure_terrain_members() -> None:
    """Extend the Terrain enum with new members if not already present."""
    new_members = {
        "COLUMN": "column",        # impassable decorative pillar
        "WATER": "water",          # passable, +1 movement cost
        "GROWTH": "growth",        # passable vegetation, +1 movement cost
        "COVER": "cover",          # passable low cover, +1 movement cost
    }
    for name, value in new_members.items():
        if not hasattr(Terrain, name):
            # Dynamically add enum members -- Python enum hack
            obj = object.__new__(Terrain)
            obj._value_ = value
            obj._name_ = name
            Terrain._member_map_[name] = obj  # type: ignore[attr-defined]
            Terrain._value2member_map_[value] = obj  # type: ignore[attr-defined]


_ensure_terrain_members()


def _patch_tile_properties() -> None:
    """Patch Tile.passable and Tile.movement_cost to handle new terrain types."""
    from angband_mechanicum.engine.combat_engine import Tile

    original_passable = Tile.passable.fget  # type: ignore[union-attr]
    original_cost = Tile.movement_cost.fget  # type: ignore[union-attr]

    def passable(self: Tile) -> bool:  # type: ignore[override]
        if self.terrain == Terrain.COLUMN:
            return False
        if self.terrain in (Terrain.WATER, Terrain.GROWTH, Terrain.COVER):
            return True
        return original_passable(self)  # type: ignore[misc]

    def movement_cost(self: Tile) -> int:  # type: ignore[override]
        if self.terrain in (Terrain.WATER, Terrain.GROWTH, Terrain.COVER):
            return 2
        if self.terrain == Terrain.COLUMN:
            return 999  # impassable, but just in case
        return original_cost(self)  # type: ignore[misc]

    Tile.passable = property(passable)  # type: ignore[assignment]
    Tile.movement_cost = property(movement_cost)  # type: ignore[assignment]


_patch_tile_properties()


# ---------------------------------------------------------------------------
# Room archetype enum
# ---------------------------------------------------------------------------

ROOM_TYPES: list[str] = [
    "open_room",        # Large open rectangular room
    "small_chamber",    # Compact square room
    "corridor",         # Long narrow passage
    "pillared_hall",    # Room with columns in a regular grid
    "l_shaped",         # L-shaped room
    "cross_room",       # Cross / plus-shaped room
    "maze",             # Maze-like passages
    "arena",            # Open arena with scattered cover
]

# Feature types that can be requested
FEATURE_TYPES: list[str] = [
    "columns",
    "water",
    "debris",
    "growths",
    "cover",
    "terminals",
]


# ---------------------------------------------------------------------------
# Spawn point data
# ---------------------------------------------------------------------------

@dataclass
class SpawnPoints:
    """Spawn positions for player party and enemies."""

    player_start: tuple[int, int]
    party_starts: list[tuple[int, int]]
    enemy_zone: list[tuple[int, int]]  # candidate tiles for enemy placement


# ---------------------------------------------------------------------------
# Generation result
# ---------------------------------------------------------------------------

@dataclass
class GeneratedMap:
    """Result of procedural map generation."""

    grid: Grid
    name: str
    room_type: str
    spawn: SpawnPoints

    def to_map_def(self) -> dict[str, Any]:
        """Convert to a map definition dict compatible with HARDCODED_MAPS / CombatEngine."""
        return {
            "name": self.name,
            "build": lambda: self.grid,
            "player_start": self.spawn.player_start,
            "party_starts": self.spawn.party_starts,
            "enemies": [],  # caller uses auto_place_enemies or explicit roster
        }


# ---------------------------------------------------------------------------
# Room hint (from LLM combat trigger)
# ---------------------------------------------------------------------------

@dataclass
class RoomHint:
    """Hints from the LLM narrative about what kind of room to generate."""

    room_type: str | None = None
    width: int | None = None
    height: int | None = None
    features: list[str] = field(default_factory=list)
    theme: str | None = None  # e.g. "forge", "sewer", "corrupted", "overgrown"
    name: str | None = None  # e.g. "Collapsed Forge Chamber"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RoomHint:
        if data is None:
            return cls()
        return cls(
            room_type=data.get("room_type"),
            width=data.get("width"),
            height=data.get("height"),
            features=data.get("features", []),
            theme=data.get("theme"),
            name=data.get("name"),
        )


# ---------------------------------------------------------------------------
# Map name generation
# ---------------------------------------------------------------------------

_NAME_PREFIXES: dict[str, list[str]] = {
    "forge": ["Ruined", "Abandoned", "Smouldering", "Ancient", "Sacred"],
    "sewer": ["Flooded", "Toxic", "Crumbling", "Dark", "Corroded"],
    "corrupted": ["Tainted", "Blighted", "Warp-Touched", "Defiled", "Twisted"],
    "overgrown": ["Overgrown", "Vine-Choked", "Fungal", "Spore-Laden", "Reclaimed"],
    "default": ["Sub-Level", "Deep Strata", "Underhive", "Mechanicum", "Forgotten"],
}

_NAME_SUFFIXES: dict[str, list[str]] = {
    "open_room": ["Hall", "Chamber", "Sanctum", "Vault"],
    "small_chamber": ["Cell", "Alcove", "Closet", "Bay"],
    "corridor": ["Corridor", "Passage", "Conduit", "Tunnel"],
    "pillared_hall": ["Colonnade", "Pillared Hall", "Gallery", "Nave"],
    "l_shaped": ["Junction", "Turning", "Annex", "Wing"],
    "cross_room": ["Crossroads", "Intersection", "Nexus", "Hub"],
    "maze": ["Labyrinth", "Warren", "Maze", "Catacomb"],
    "arena": ["Arena", "Pit", "Fighting Ground", "Kill-Zone"],
}


def _generate_name(room_type: str, theme: str | None, rng: random.Random) -> str:
    """Generate an evocative map name."""
    theme_key = theme if theme in _NAME_PREFIXES else "default"
    prefix = rng.choice(_NAME_PREFIXES[theme_key])
    suffix = rng.choice(_NAME_SUFFIXES.get(room_type, ["Chamber"]))
    return f"{prefix} {suffix}"


# ---------------------------------------------------------------------------
# Core generation functions
# ---------------------------------------------------------------------------

def _fill_walls(grid: Grid) -> None:
    """Fill entire grid with walls."""
    for y in range(grid.height):
        for x in range(grid.width):
            grid.set_terrain(x, y, Terrain.WALL)


def _carve_rect(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    """Carve a rectangular floor area (inclusive bounds)."""
    for y in range(max(0, y1), min(grid.height, y2 + 1)):
        for x in range(max(0, x1), min(grid.width, x2 + 1)):
            grid.set_terrain(x, y, Terrain.FLOOR)


def _carve_border_walls(grid: Grid) -> None:
    """Ensure the outermost ring is walls."""
    for x in range(grid.width):
        grid.set_terrain(x, 0, Terrain.WALL)
        grid.set_terrain(x, grid.height - 1, Terrain.WALL)
    for y in range(grid.height):
        grid.set_terrain(0, y, Terrain.WALL)
        grid.set_terrain(grid.width - 1, y, Terrain.WALL)


def _floor_tiles(grid: Grid) -> list[tuple[int, int]]:
    """Return all floor-type (passable, non-wall) tile positions."""
    result: list[tuple[int, int]] = []
    for y in range(grid.height):
        for x in range(grid.width):
            if grid.get_tile(x, y).passable:
                result.append((x, y))
    return result


# ---------------------------------------------------------------------------
# Room archetype builders
# ---------------------------------------------------------------------------

def _build_open_room(width: int, height: int, rng: random.Random) -> Grid:
    """Large open rectangular room with walls around the border."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)
    _carve_rect(grid, 1, 1, width - 2, height - 2)
    return grid


def _build_small_chamber(width: int, height: int, rng: random.Random) -> Grid:
    """Compact room, roughly centered in the grid."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)
    # Chamber fills most of the grid
    pad_x = max(1, width // 6)
    pad_y = max(1, height // 6)
    _carve_rect(grid, pad_x, pad_y, width - pad_x - 1, height - pad_y - 1)
    return grid


def _build_corridor(width: int, height: int, rng: random.Random) -> Grid:
    """Long corridor with optional widening in spots."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)

    # Main corridor through the middle
    mid_y = height // 2
    corridor_half = max(1, height // 6)
    _carve_rect(grid, 1, mid_y - corridor_half, width - 2, mid_y + corridor_half)

    # Add 1-2 alcoves/widenings
    num_alcoves = rng.randint(1, 3)
    for _ in range(num_alcoves):
        ax = rng.randint(3, width - 4)
        direction = rng.choice([-1, 1])
        ay_start = mid_y + direction * (corridor_half + 1)
        ay_end = ay_start + direction * rng.randint(1, 3)
        _carve_rect(
            grid,
            ax - rng.randint(1, 2),
            min(ay_start, ay_end),
            ax + rng.randint(1, 2),
            max(ay_start, ay_end),
        )

    _carve_border_walls(grid)
    return grid


def _build_pillared_hall(width: int, height: int, rng: random.Random) -> Grid:
    """Room with a regular grid of columns."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)
    _carve_rect(grid, 1, 1, width - 2, height - 2)

    # Place columns in a grid pattern
    col_spacing_x = max(3, width // 5)
    col_spacing_y = max(3, height // 4)
    for y in range(col_spacing_y, height - 1, col_spacing_y):
        for x in range(col_spacing_x, width - 1, col_spacing_x):
            if grid.in_bounds(x, y):
                grid.set_terrain(x, y, Terrain.COLUMN)

    return grid


def _build_l_shaped(width: int, height: int, rng: random.Random) -> Grid:
    """L-shaped room created by carving two overlapping rectangles."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)

    mid_x = width // 2
    mid_y = height // 2

    # Choose L orientation
    orientation = rng.randint(0, 3)
    if orientation == 0:
        # Bottom-left L
        _carve_rect(grid, 1, mid_y, mid_x + 2, height - 2)  # horizontal arm
        _carve_rect(grid, 1, 1, mid_x - 2, height - 2)  # vertical arm
    elif orientation == 1:
        # Bottom-right L
        _carve_rect(grid, mid_x - 2, mid_y, width - 2, height - 2)
        _carve_rect(grid, mid_x + 2, 1, width - 2, height - 2)
    elif orientation == 2:
        # Top-left L
        _carve_rect(grid, 1, 1, mid_x + 2, mid_y)
        _carve_rect(grid, 1, 1, mid_x - 2, height - 2)
    else:
        # Top-right L
        _carve_rect(grid, mid_x - 2, 1, width - 2, mid_y)
        _carve_rect(grid, mid_x + 2, 1, width - 2, height - 2)

    _carve_border_walls(grid)
    return grid


def _build_cross_room(width: int, height: int, rng: random.Random) -> Grid:
    """Plus/cross-shaped room."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)

    # Horizontal bar
    bar_h = max(3, height // 3)
    mid_y = height // 2
    _carve_rect(grid, 1, mid_y - bar_h // 2, width - 2, mid_y + bar_h // 2)

    # Vertical bar
    bar_w = max(3, width // 3)
    mid_x = width // 2
    _carve_rect(grid, mid_x - bar_w // 2, 1, mid_x + bar_w // 2, height - 2)

    _carve_border_walls(grid)
    return grid


def _build_maze(width: int, height: int, rng: random.Random) -> Grid:
    """Maze-like passages using a simple recursive-ish carver."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)

    # Start with a grid of narrow passages
    # Carve passages on odd coordinates
    for y in range(1, height - 1, 2):
        for x in range(1, width - 1, 2):
            grid.set_terrain(x, y, Terrain.FLOOR)

    # Connect cells with random passages
    cells: list[tuple[int, int]] = []
    for y in range(1, height - 1, 2):
        for x in range(1, width - 1, 2):
            cells.append((x, y))

    rng.shuffle(cells)
    visited: set[tuple[int, int]] = set()

    def _carve_from(cx: int, cy: int) -> None:
        visited.add((cx, cy))
        directions = [(0, -2), (0, 2), (-2, 0), (2, 0)]
        rng.shuffle(directions)
        for dx, dy in directions:
            nx, ny = cx + dx, cy + dy
            if (nx, ny) not in visited and 0 < nx < width - 1 and 0 < ny < height - 1:
                # Carve the wall between cells
                grid.set_terrain(cx + dx // 2, cy + dy // 2, Terrain.FLOOR)
                grid.set_terrain(nx, ny, Terrain.FLOOR)
                _carve_from(nx, ny)

    if cells:
        start = cells[0]
        _carve_from(start[0], start[1])

    # Widen some passages for playability (combat needs room to manoeuvre)
    widen_count = max(3, (width * height) // 40)
    floor_positions = _floor_tiles(grid)
    if floor_positions:
        for _ in range(widen_count):
            fx, fy = rng.choice(floor_positions)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = fx + dx, fy + dy
                if grid.in_bounds(nx, ny) and 0 < nx < width - 1 and 0 < ny < height - 1:
                    grid.set_terrain(nx, ny, Terrain.FLOOR)

    _carve_border_walls(grid)
    return grid


def _build_arena(width: int, height: int, rng: random.Random) -> Grid:
    """Open arena with scattered cover objects."""
    grid = Grid(width=width, height=height)
    _fill_walls(grid)
    _carve_rect(grid, 1, 1, width - 2, height - 2)

    # Scatter cover objects
    num_cover = max(3, (width * height) // 30)
    for _ in range(num_cover):
        cx = rng.randint(2, width - 3)
        cy = rng.randint(2, height - 3)
        cover_type = rng.choice([Terrain.COVER, Terrain.DEBRIS])
        grid.set_terrain(cx, cy, cover_type)

    return grid


_BUILDERS: dict[str, Any] = {
    "open_room": _build_open_room,
    "small_chamber": _build_small_chamber,
    "corridor": _build_corridor,
    "pillared_hall": _build_pillared_hall,
    "l_shaped": _build_l_shaped,
    "cross_room": _build_cross_room,
    "maze": _build_maze,
    "arena": _build_arena,
}


# ---------------------------------------------------------------------------
# Feature scattering
# ---------------------------------------------------------------------------

_FEATURE_TERRAIN: dict[str, Terrain] = {
    "columns": Terrain.COLUMN,
    "water": Terrain.WATER,
    "debris": Terrain.DEBRIS,
    "growths": Terrain.GROWTH,
    "cover": Terrain.COVER,
    "terminals": Terrain.TERMINAL,
}


def _scatter_features(
    grid: Grid,
    features: list[str],
    rng: random.Random,
    reserved: set[tuple[int, int]] | None = None,
) -> None:
    """Scatter terrain features onto existing floor tiles.

    *reserved* tiles (spawn points etc.) will not be overwritten.
    """
    floor = _floor_tiles(grid)
    if reserved:
        floor = [p for p in floor if p not in reserved]
    if not floor:
        return

    for feat_name in features:
        terrain = _FEATURE_TERRAIN.get(feat_name)
        if terrain is None:
            continue

        # Number of features scales with map area
        count = max(2, len(floor) // 20)
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 4:
            attempts += 1
            pos = rng.choice(floor)
            x, y = pos
            # Don't overwrite non-floor terrain (e.g., another feature)
            if grid.get_tile(x, y).terrain != Terrain.FLOOR:
                continue
            grid.set_terrain(x, y, terrain)
            placed += 1


# ---------------------------------------------------------------------------
# Theme-based feature inference
# ---------------------------------------------------------------------------

_THEME_FEATURES: dict[str, list[str]] = {
    "forge": ["debris", "terminals", "cover"],
    "sewer": ["water", "debris"],
    "corrupted": ["growths", "debris", "cover"],
    "overgrown": ["growths", "water"],
    "industrial": ["columns", "debris", "terminals"],
    "hive": ["cover", "debris"],
}


def _features_for_theme(theme: str | None) -> list[str]:
    """Derive feature list from a theme string."""
    if theme and theme in _THEME_FEATURES:
        return list(_THEME_FEATURES[theme])
    return []


# ---------------------------------------------------------------------------
# Spawn point calculation
# ---------------------------------------------------------------------------

def _compute_spawns(grid: Grid, rng: random.Random) -> SpawnPoints:
    """Compute player and enemy spawn zones on the generated grid.

    Player spawns in the left portion, enemies in the right portion.
    """
    floor = _floor_tiles(grid)
    if not floor:
        # Degenerate -- shouldn't happen but be safe
        return SpawnPoints(
            player_start=(1, 1),
            party_starts=[(2, 1), (1, 2)],
            enemy_zone=[(grid.width - 2, grid.height - 2)],
        )

    mid_x = grid.width // 2

    left_tiles = [(x, y) for x, y in floor if x < mid_x]
    right_tiles = [(x, y) for x, y in floor if x >= mid_x]

    # Fallback: if one side has no tiles, split differently
    if not left_tiles:
        left_tiles = floor[: len(floor) // 2]
    if not right_tiles:
        right_tiles = floor[len(floor) // 2 :]

    # Player start: prefer left side, roughly centered vertically
    left_tiles.sort(key=lambda p: (abs(p[1] - grid.height // 2), p[0]))
    player_start = left_tiles[0]

    # Party starts: 2 tiles adjacent or near the player
    party_starts: list[tuple[int, int]] = []
    px, py = player_start
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0), (1, -1), (1, 1)]:
        candidate = (px + dx, py + dy)
        if candidate in left_tiles and candidate != player_start and candidate not in party_starts:
            party_starts.append(candidate)
            if len(party_starts) >= 2:
                break

    # If adjacency failed, pick closest left tiles
    if len(party_starts) < 2:
        remaining = [t for t in left_tiles if t != player_start and t not in party_starts]
        remaining.sort(key=lambda p: abs(p[0] - px) + abs(p[1] - py))
        for t in remaining:
            party_starts.append(t)
            if len(party_starts) >= 2:
                break

    return SpawnPoints(
        player_start=player_start,
        party_starts=party_starts,
        enemy_zone=right_tiles,
    )


# ---------------------------------------------------------------------------
# Main generation API
# ---------------------------------------------------------------------------

DEFAULT_WIDTH: int = 24
DEFAULT_HEIGHT: int = 17
MIN_WIDTH: int = 12
MIN_HEIGHT: int = 10
MAX_WIDTH: int = 80
MAX_HEIGHT: int = 30


def generate_map(
    room_type: str | None = None,
    width: int | None = None,
    height: int | None = None,
    features: list[str] | None = None,
    theme: str | None = None,
    name: str | None = None,
    seed: int | None = None,
) -> GeneratedMap:
    """Generate a procedural combat map.

    Parameters
    ----------
    room_type:
        One of ROOM_TYPES.  If None, chosen at random.
    width, height:
        Dimensions.  Clamped to [MIN, MAX] range.
    features:
        List of feature strings to scatter (e.g. ["columns", "water"]).
        If None and a theme is given, derived from the theme.
    theme:
        Narrative theme hint (e.g. "forge", "sewer").
    name:
        Override map name.  If None, generated from theme + room_type.
    seed:
        Random seed for reproducibility.

    Returns
    -------
    GeneratedMap with grid, spawn points, and metadata.
    """
    rng = random.Random(seed)

    # Resolve room type
    if room_type is None or room_type not in _BUILDERS:
        room_type = rng.choice(ROOM_TYPES)

    # Resolve dimensions
    w = width if width is not None else DEFAULT_WIDTH
    h = height if height is not None else DEFAULT_HEIGHT
    w = max(MIN_WIDTH, min(MAX_WIDTH, w))
    h = max(MIN_HEIGHT, min(MAX_HEIGHT, h))

    # Build base room
    builder = _BUILDERS[room_type]
    grid: Grid = builder(w, h, rng)

    # Compute spawn points before scattering features
    spawn = _compute_spawns(grid, rng)

    # Determine features
    effective_features = features if features is not None else _features_for_theme(theme)

    # Reserve spawn tiles from feature placement
    reserved: set[tuple[int, int]] = {spawn.player_start}
    reserved.update(spawn.party_starts)

    # Scatter terrain features
    if effective_features:
        _scatter_features(grid, effective_features, rng, reserved)

    # Generate name
    map_name = name or _generate_name(room_type, theme, rng)

    return GeneratedMap(
        grid=grid,
        name=map_name,
        room_type=room_type,
        spawn=spawn,
    )


def generate_map_from_hint(hint: RoomHint | dict[str, Any] | None = None, seed: int | None = None) -> GeneratedMap:
    """Generate a map from a RoomHint (typically from LLM combat trigger data).

    Convenience wrapper around generate_map() that accepts a RoomHint dataclass
    or a raw dict.
    """
    if hint is None:
        return generate_map(seed=seed)

    if isinstance(hint, dict):
        hint = RoomHint.from_dict(hint)

    return generate_map(
        room_type=hint.room_type,
        width=hint.width,
        height=hint.height,
        features=hint.features if hint.features else None,
        theme=hint.theme,
        name=hint.name,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Exploration-scale dungeon floor generation
# ---------------------------------------------------------------------------

FLOOR_DEFAULT_WIDTH: int = 80
FLOOR_DEFAULT_HEIGHT: int = 50
FLOOR_MIN_WIDTH: int = 40
FLOOR_MIN_HEIGHT: int = 25
FLOOR_MAX_WIDTH: int = 160
FLOOR_MAX_HEIGHT: int = 100


@dataclass(frozen=True)
class DungeonRoom:
    """A placed room footprint on an exploration-scale dungeon floor."""

    x: int
    y: int
    width: int
    height: int
    room_type: str

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def intersects(self, other: "DungeonRoom", padding: int = 1) -> bool:
        return not (
            self.x + self.width + padding <= other.x
            or other.x + other.width + padding <= self.x
            or self.y + self.height + padding <= other.y
            or other.y + other.height + padding <= self.y
        )

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


@dataclass
class GeneratedFloor:
    """Result of exploration-scale dungeon floor generation."""

    level: DungeonLevel
    rooms: list[DungeonRoom]
    environment: str
    entry_room_index: int
    exit_room_index: int
    secret_passages: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)


def _fill_level(level: DungeonLevel, terrain: DungeonTerrain) -> None:
    for y in range(level.height):
        for x in range(level.width):
            level.set_terrain(x, y, terrain)


def _carve_level_rect(
    level: DungeonLevel,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    terrain: DungeonTerrain = DungeonTerrain.FLOOR,
) -> None:
    for y in range(max(1, y1), min(level.height - 1, y2 + 1)):
        for x in range(max(1, x1), min(level.width - 1, x2 + 1)):
            level.set_terrain(x, y, terrain)


def _set_feature_tile(
    level: DungeonLevel,
    x: int,
    y: int,
    terrain: DungeonTerrain,
) -> None:
    if not level.in_bounds(x, y):
        return
    if terrain in (DungeonTerrain.STAIRS_UP, DungeonTerrain.STAIRS_DOWN):
        return
    current = level.get_terrain(x, y)
    if current == DungeonTerrain.FLOOR:
        level.set_terrain(x, y, terrain)


def _build_room_on_level(level: DungeonLevel, room: DungeonRoom, rng: random.Random) -> None:
    """Carve a room footprint into a DungeonLevel."""
    x1 = room.x
    y1 = room.y
    x2 = room.x + room.width - 1
    y2 = room.y + room.height - 1

    if room.room_type in {"open_room", "small_chamber", "corridor"}:
        _carve_level_rect(level, x1, y1, x2, y2)
        return

    if room.room_type == "pillared_hall":
        _carve_level_rect(level, x1, y1, x2, y2)
        for y in range(y1 + 2, y2, 3):
            for x in range(x1 + 2, x2, 4):
                level.set_terrain(x, y, DungeonTerrain.COLUMN)
        return

    if room.room_type == "l_shaped":
        _carve_level_rect(level, x1, y1, x1 + room.width // 2, y2)
        _carve_level_rect(level, x1, y1 + room.height // 2, x2, y2)
        return

    if room.room_type == "cross_room":
        mid_x = x1 + room.width // 2
        mid_y = y1 + room.height // 2
        _carve_level_rect(level, x1, mid_y - 1, x2, mid_y + 1)
        _carve_level_rect(level, mid_x - 1, y1, mid_x + 1, y2)
        return

    if room.room_type == "maze":
        _carve_level_rect(level, x1, y1, x2, y2)
        for y in range(y1 + 1, y2):
            for x in range(x1 + 1, x2):
                if (x + y) % 2 == 0 and rng.random() < 0.55:
                    level.set_terrain(x, y, DungeonTerrain.WALL)
        for _ in range(max(4, (room.width * room.height) // 16)):
            carve_x = rng.randint(x1 + 1, x2 - 1)
            carve_y = rng.randint(y1 + 1, y2 - 1)
            level.set_terrain(carve_x, carve_y, DungeonTerrain.FLOOR)
        return

    if room.room_type == "arena":
        _carve_level_rect(level, x1, y1, x2, y2)
        scatter_count = max(3, (room.width * room.height) // 18)
        for _ in range(scatter_count):
            fx = rng.randint(x1 + 1, x2 - 1)
            fy = rng.randint(y1 + 1, y2 - 1)
            level.set_terrain(
                fx,
                fy,
                rng.choice((DungeonTerrain.COVER, DungeonTerrain.RUBBLE)),
            )
        return

    _carve_level_rect(level, x1, y1, x2, y2)


def _random_room(
    level_width: int,
    level_height: int,
    room_type: str,
    rng: random.Random,
) -> DungeonRoom:
    if room_type == "corridor":
        horizontal = rng.random() < 0.6
        if horizontal:
            width = rng.randint(10, 18)
            height = rng.randint(4, 6)
        else:
            width = rng.randint(4, 6)
            height = rng.randint(10, 16)
    else:
        width = rng.randint(7, 15)
        height = rng.randint(6, 12)
        if room_type == "small_chamber":
            width = rng.randint(6, 10)
            height = rng.randint(5, 8)
        elif room_type == "arena":
            width = rng.randint(10, 18)
            height = rng.randint(8, 14)
        elif room_type == "pillared_hall":
            width = rng.randint(10, 16)
            height = rng.randint(8, 12)
        elif room_type == "maze":
            width = rng.randint(9, 15)
            height = rng.randint(8, 12)

    width = min(width, max(6, level_width - 4))
    height = min(height, max(5, level_height - 4))
    x = rng.randint(1, max(1, level_width - width - 2))
    y = rng.randint(1, max(1, level_height - height - 2))
    return DungeonRoom(x=x, y=y, width=width, height=height, room_type=room_type)


def _place_rooms(
    level_width: int,
    level_height: int,
    room_types: tuple[str, ...],
    room_count: int,
    rng: random.Random,
) -> list[DungeonRoom]:
    rooms: list[DungeonRoom] = []
    attempts = max(80, room_count * 12)
    for _ in range(attempts):
        if len(rooms) >= room_count:
            break
        room_type = rng.choice(room_types)
        candidate = _random_room(level_width, level_height, room_type, rng)
        if any(candidate.intersects(existing) for existing in rooms):
            continue
        rooms.append(candidate)

    if not rooms:
        fallback = DungeonRoom(
            x=2,
            y=2,
            width=max(8, level_width - 4),
            height=max(6, level_height - 4),
            room_type="open_room",
        )
        rooms.append(fallback)

    rooms.sort(key=lambda room: (room.center[0], room.center[1]))
    return rooms


def _carve_h_tunnel(level: DungeonLevel, x1: int, x2: int, y: int) -> None:
    for x in range(min(x1, x2), max(x1, x2) + 1):
        level.set_terrain(x, y, DungeonTerrain.FLOOR)


def _carve_v_tunnel(level: DungeonLevel, y1: int, y2: int, x: int) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        level.set_terrain(x, y, DungeonTerrain.FLOOR)


def _carve_connection(
    level: DungeonLevel,
    a: tuple[int, int],
    b: tuple[int, int],
    rng: random.Random,
) -> None:
    ax, ay = a
    bx, by = b
    if rng.random() < 0.5:
        _carve_h_tunnel(level, ax, bx, ay)
        _carve_v_tunnel(level, ay, by, bx)
    else:
        _carve_v_tunnel(level, ay, by, ax)
        _carve_h_tunnel(level, ax, bx, by)


def _add_doors(level: DungeonLevel, rng: random.Random) -> None:
    candidates: list[tuple[int, int]] = []
    for y in range(1, level.height - 1):
        for x in range(1, level.width - 1):
            if level.get_terrain(x, y) != DungeonTerrain.FLOOR:
                continue
            north = level.get_tile(x, y - 1).passable
            south = level.get_tile(x, y + 1).passable
            east = level.get_tile(x + 1, y).passable
            west = level.get_tile(x - 1, y).passable
            if north and south and not east and not west:
                candidates.append((x, y))
            elif east and west and not north and not south:
                candidates.append((x, y))

    rng.shuffle(candidates)
    door_target = max(2, len(candidates) // 12)
    for x, y in candidates[:door_target]:
        level.set_terrain(x, y, DungeonTerrain.DOOR_OPEN)


def _scatter_environment_features(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    environment: str,
    reserved: set[tuple[int, int]],
    rng: random.Random,
) -> None:
    env = ENVIRONMENTS.get(environment)
    if env is None:
        return

    feature_pool = [
        terrain
        for terrain in env.feature_terrains
        if terrain not in (DungeonTerrain.COLUMN, DungeonTerrain.TERMINAL)
    ]

    for room in rooms:
        if room.room_type == "corridor" or not feature_pool:
            continue
        placements = max(1, (room.width * room.height) // 30)
        for _ in range(placements):
            x = rng.randint(room.x + 1, room.x + room.width - 2)
            y = rng.randint(room.y + 1, room.y + room.height - 2)
            if (x, y) in reserved:
                continue
            terrain = rng.choice(feature_pool)
            _set_feature_tile(level, x, y, terrain)

    if DungeonTerrain.TERMINAL in env.feature_terrains:
        for room in rooms[: max(1, len(rooms) // 4)]:
            x = room.center[0]
            y = room.center[1]
            if (x, y) not in reserved:
                _set_feature_tile(level, x, y, DungeonTerrain.TERMINAL)


def _find_room_index(rooms: list[DungeonRoom], position: tuple[int, int]) -> int:
    x, y = position
    for index, room in enumerate(rooms):
        if room.contains(x, y):
            return index
    return 0


def _add_secret_passage(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    reserved: set[tuple[int, int]],
    rng: random.Random,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    if len(rooms) < 3:
        return []

    candidates = [
        (rooms[index], rooms[index + 2])
        for index in range(len(rooms) - 2)
    ]
    start_room, end_room = rng.choice(candidates)
    start = start_room.center
    end = end_room.center
    _carve_connection(level, start, end, rng)

    for position in (start, end):
        if position not in reserved:
            level.set_terrain(position[0], position[1], DungeonTerrain.DOOR_CLOSED)

    return [(start, end)]


def _find_nearest_floor(level: DungeonLevel, origin: tuple[int, int]) -> tuple[int, int]:
    ox, oy = origin
    best = origin
    best_distance = 10**9
    for y in range(max(1, oy - 2), min(level.height - 1, oy + 3)):
        for x in range(max(1, ox - 2), min(level.width - 1, ox + 3)):
            if not level.get_tile(x, y).passable:
                continue
            distance = abs(x - ox) + abs(y - oy)
            if distance < best_distance:
                best = (x, y)
                best_distance = distance
    return best


def generate_dungeon_floor(
    *,
    level_id: str,
    depth: int,
    environment: str = "forge",
    width: int = FLOOR_DEFAULT_WIDTH,
    height: int = FLOOR_DEFAULT_HEIGHT,
    room_count: int | None = None,
    name: str | None = None,
    seed: int | None = None,
) -> GeneratedFloor:
    """Generate an exploration-scale persistent dungeon floor."""
    rng = random.Random(seed)
    env = ENVIRONMENTS.get(environment, ENVIRONMENTS["forge"])
    width = max(FLOOR_MIN_WIDTH, min(FLOOR_MAX_WIDTH, width))
    height = max(FLOOR_MIN_HEIGHT, min(FLOOR_MAX_HEIGHT, height))
    resolved_room_count = room_count if room_count is not None else max(6, (width * height) // 260)
    resolved_room_count = max(4, min(18, resolved_room_count))

    level = DungeonLevel(
        level_id=level_id,
        name=name or f"{env.name.title()} Depth {depth}",
        depth=depth,
        environment=env.name,
        width=width,
        height=height,
    )
    _fill_level(level, DungeonTerrain.WALL)

    rooms = _place_rooms(width, height, env.room_types, resolved_room_count, rng)
    for room in rooms:
        _build_room_on_level(level, room, rng)

    for room_a, room_b in zip(rooms, rooms[1:]):
        _carve_connection(level, room_a.center, room_b.center, rng)

    extra_connections = min(3, max(1, len(rooms) // 3))
    for _ in range(extra_connections):
        room_a, room_b = rng.sample(rooms, 2)
        _carve_connection(level, room_a.center, room_b.center, rng)

    entry_room = rooms[0]
    exit_room = max(rooms, key=lambda room: abs(room.center[0] - entry_room.center[0]) + abs(room.center[1] - entry_room.center[1]))
    stairs_up = _find_nearest_floor(level, entry_room.center)
    stairs_down = _find_nearest_floor(level, exit_room.center)
    if stairs_down == stairs_up and len(rooms) > 1:
        stairs_down = _find_nearest_floor(level, rooms[-1].center)

    level.set_terrain(stairs_up[0], stairs_up[1], DungeonTerrain.STAIRS_UP)
    level.set_terrain(stairs_down[0], stairs_down[1], DungeonTerrain.STAIRS_DOWN)
    level.stairs_up = [stairs_up]
    level.stairs_down = [stairs_down]
    level.player_pos = stairs_up

    reserved = {stairs_up, stairs_down}
    _scatter_environment_features(level, rooms, env.name, reserved, rng)
    _add_doors(level, rng)
    secret_passages = _add_secret_passage(level, rooms, reserved, rng)

    return GeneratedFloor(
        level=level,
        rooms=rooms,
        environment=env.name,
        entry_room_index=_find_room_index(rooms, stairs_up),
        exit_room_index=_find_room_index(rooms, stairs_down),
        secret_passages=secret_passages,
    )
