"""Procedural dungeon / room generation for tactical combat maps.

Generates Grid instances with varied room archetypes, terrain features,
and spawn points.  Designed to fit visible terminal dimensions (60-80 wide,
20-30 tall) and integrate with the existing combat engine.

No LLM calls -- pure deterministic (seeded) generation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Sequence

from angband_mechanicum.engine.combat_engine import CombatStats, Grid, Terrain
from angband_mechanicum.engine.dungeon_entities import (
    DungeonDisposition,
    DungeonEntity,
    DungeonEntityRoster,
    DungeonMovementAI,
    infer_portrait_key,
)
from angband_mechanicum.engine.dungeon_profiles import DungeonGenerationProfile
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

_THEME_TRANSITIONS: dict[str, DungeonTerrain] = {
    "forge": DungeonTerrain.LIFT,
    "manufactorum": DungeonTerrain.LIFT,
    "hive": DungeonTerrain.ELEVATOR,
    "cathedral": DungeonTerrain.GATE,
    "tomb": DungeonTerrain.GATE,
    "corrupted": DungeonTerrain.PORTAL,
}


def _features_for_theme(theme: str | None) -> list[str]:
    """Derive feature list from a theme string."""
    if theme and theme in _THEME_FEATURES:
        return list(_THEME_FEATURES[theme])
    return []


def _transition_terrain_for_environment(environment: str) -> DungeonTerrain | None:
    """Return the terrain used to represent traversal points on a floor."""
    return _THEME_TRANSITIONS.get(environment)


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
    placed_items: list[tuple[str, tuple[int, int]]] = field(default_factory=list)
    entity_roster: DungeonEntityRoster = field(default_factory=DungeonEntityRoster)
    themed_rooms: list["ThemedRoomInstance"] = field(default_factory=list)


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


def _room_index_at(rooms: Sequence[DungeonRoom], x: int, y: int) -> int | None:
    for index, room in enumerate(rooms):
        if room.x <= x < room.x + room.width and room.y <= y < room.y + room.height:
            return index
    return None


def _is_room_threshold(
    rooms: Sequence[DungeonRoom],
    near_side: tuple[int, int],
    far_side: tuple[int, int],
) -> bool:
    near_room = _room_index_at(rooms, *near_side)
    far_room = _room_index_at(rooms, *far_side)
    if near_room is None and far_room is None:
        return False
    return near_room != far_room


def _add_doors(
    level: DungeonLevel,
    rng: random.Random,
    rooms: Sequence[DungeonRoom] | None = None,
) -> None:
    candidates: list[tuple[int, int]] = []
    for y in range(1, level.height - 1):
        for x in range(1, level.width - 1):
            if level.get_terrain(x, y) != DungeonTerrain.FLOOR:
                continue
            north = level.get_tile(x, y - 1).passable
            south = level.get_tile(x, y + 1).passable
            east = level.get_tile(x + 1, y).passable
            west = level.get_tile(x - 1, y).passable
            is_vertical_doorway = north and south and not east and not west
            is_horizontal_doorway = east and west and not north and not south
            if is_vertical_doorway:
                if rooms is not None and not _is_room_threshold(rooms, (x, y - 1), (x, y + 1)):
                    continue
                candidates.append((x, y))
            elif is_horizontal_doorway:
                if rooms is not None and not _is_room_threshold(rooms, (x - 1, y), (x + 1, y)):
                    continue
                candidates.append((x, y))

    if len(candidates) < 4:
        return

    door_rng = random.Random(f"{level.level_id}:{level.depth}:doors")
    door_rng.shuffle(candidates)
    door_target = max(1, len(candidates) // 10)
    if len(candidates) >= 12:
        door_target = max(door_target, 2)

    selected: list[tuple[int, int]] = []
    for x, y in candidates:
        if any(abs(existing_x - x) <= 1 and abs(existing_y - y) <= 1 for existing_x, existing_y in selected):
            continue
        selected.append((x, y))
        if len(selected) >= door_target:
            break

    for x, y in selected:
        level.set_terrain(x, y, DungeonTerrain.DOOR_OPEN)


_FLOOR_OBJECTS: dict[str, tuple[str, ...]] = {
    "forge": ("data-slate", "toolkit", "power-cell", "oil-canister"),
    "manufactorum": ("toolkit", "machine-spare", "cogitator-node", "power-cell"),
    "voidship": ("breach-kit", "vox-beacon", "ammo-crate", "sealant-foam"),
    "cathedral": ("prayer-scroll", "candela", "reliquary-key", "votive"),
    "reliquary": ("reliquary-key", "prayer-scroll", "sealed-lamp"),
    "hive": ("scrap-cache", "lockpick", "stimm-pack", "ration-crate"),
    "sewer": ("filter-pack", "drain-key", "scrap-cache", "anti-toxin"),
    "corrupted": ("sanctioned-ward", "warp-sample", "purity-seal", "scrap-cache"),
    "overgrown": ("field-knife", "seed-bundle", "water-canteen", "rations"),
    "tomb": ("funerary-token", "seal-stone", "prayer-scroll", "relic"),
    "radwastes": ("survey-beacon", "rad-shield", "scrap-cache", "water-flask"),
    "ash_dune_outpost": ("beacon", "ration-crate", "survey-map", "repair-kit"),
    "default": ("supply-crate", "cogitator-slate", "field-kit"),
}


def _scatter_environment_objects(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    environment: str,
    depth: int,
    reserved: set[tuple[int, int]],
    rng: random.Random,
) -> list[tuple[str, tuple[int, int]]]:
    item_pool = _FLOOR_OBJECTS.get(environment, _FLOOR_OBJECTS["default"])
    if not item_pool or not rooms:
        return []

    candidate_rooms = [
        (index, room)
        for index, room in enumerate(rooms)
        if index not in {0, len(rooms) - 1} and room.room_type != "corridor"
    ]
    if not candidate_rooms:
        candidate_rooms = list(enumerate(rooms))
    if not candidate_rooms:
        return []

    rng.shuffle(candidate_rooms)
    target_count = max(1, min(3, len(candidate_rooms) // 3 + (1 if depth >= 6 else 0)))

    placements: list[tuple[str, tuple[int, int]]] = []
    for _, room in candidate_rooms:
        if len(placements) >= target_count:
            break
        room_tiles = _room_tiles_by_focus(level, room, reserved, focus="center")
        if not room_tiles:
            continue
        item_id = rng.choice(item_pool)
        position = room_tiles[0]
        level.place_item(position[0], position[1], item_id)
        reserved.add(position)
        placements.append((item_id, position))

    return placements


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


@dataclass(frozen=True)
class _ContactArchetype:
    name: str
    description: str
    disposition: DungeonDisposition
    movement_ai: DungeonMovementAI
    can_talk: bool
    max_hp: int
    attack: int
    armor: int
    movement: int
    attack_range: int
    portrait_hint: str = ""
    weight: int = 1
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ContactSpawnPlan:
    """Internal plan for a group or single contact spawn."""

    category: str
    archetype: _ContactArchetype
    count: int
    room_index: int | None
    group_kind: str


@dataclass(frozen=True)
class ThemedRoomPropSpec:
    """Terrain dressing that should be placed inside a themed room."""

    terrain: DungeonTerrain
    count_range: tuple[int, int] = (1, 1)
    room_focus: str = "center"


@dataclass(frozen=True)
class ThemedRoomEncounterSpec:
    """A grouped encounter or NPC placement within a themed room."""

    category: str
    count_range: tuple[int, int] = (1, 1)
    preferred_tags: tuple[str, ...] = ()
    preferred_names: tuple[str, ...] = ()
    optional: bool = False
    group_kind: str | None = None


@dataclass(frozen=True)
class ThemedRoomTemplate:
    """Reusable composition template for a set-piece room."""

    name: str
    description: str
    environments: tuple[str, ...]
    room_types: tuple[str, ...] = ()
    min_depth: int = 1
    max_depth: int = 999
    weight: int = 1
    max_per_floor: int = 1
    requires_spacious_room: bool = False
    feature_terrains: tuple[DungeonTerrain, ...] = ()
    props: tuple[ThemedRoomPropSpec, ...] = ()
    encounter_groups: tuple[ThemedRoomEncounterSpec, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass
class ThemedRoomInstance:
    """A themed room that has been materialized on a generated floor."""

    template_name: str
    room_index: int
    room_type: str
    feature_tiles: list[tuple[int, int]] = field(default_factory=list)
    prop_tiles: list[tuple[DungeonTerrain, tuple[int, int]]] = field(default_factory=list)
    encounter_ids: list[str] = field(default_factory=list)


def _weighted_choice(options: tuple[_ContactArchetype, ...], rng: random.Random) -> _ContactArchetype:
    """Choose an archetype using its explicit weight, falling back to uniform choice."""
    if not options:
        raise ValueError("cannot choose from an empty contact pool")
    total_weight = sum(max(1, option.weight) for option in options)
    roll = rng.randint(1, total_weight)
    for option in options:
        roll -= max(1, option.weight)
        if roll <= 0:
            return option
    return options[-1]


def _choose_category(
    categories: list[str],
    weights: dict[str, int],
    rng: random.Random,
) -> str:
    """Choose a contact category from the available ones using weighted bias."""
    filtered = [category for category in categories if weights.get(category, 0) > 0]
    if not filtered:
        return rng.choice(categories)
    total_weight = sum(weights[category] for category in filtered)
    roll = rng.randint(1, total_weight)
    for category in filtered:
        roll -= weights[category]
        if roll <= 0:
            return category
    return filtered[-1]


def _group_kind_for_archetype(archetype: _ContactArchetype) -> str:
    """Classify an archetype into a spawn grouping style."""
    text = f"{archetype.name} {' '.join(archetype.tags)}".lower()
    if any(keyword in text for keyword in ("rat", "vermin", "swarm")):
        return "swarm"
    if any(keyword in text for keyword in ("guardian", "sentinel", "automaton", "drone", "servitor", "custodian")):
        return "pair"
    if any(keyword in text for keyword in ("cult", "crew", "criminal", "raider", "boarding", "mutiny", "riot", "thief", "intruder", "marauder", "husk", "predator", "beast")):
        return "pack"
    return "cell"


def _group_size_for_archetype(
    archetype: _ContactArchetype,
    environment: str,
    depth: int,
    rng: random.Random,
) -> int:
    """Pick a group size for an archetype, biased by its style and environment."""
    if archetype.disposition != DungeonDisposition.HOSTILE:
        return 1

    kind = _group_kind_for_archetype(archetype)
    if kind == "swarm":
        low = 4
        high = min(10, 6 + depth // 3)
    elif kind == "pack":
        low = 2
        high = min(8, 4 + depth // 4)
    elif kind == "pair":
        low = 1
        high = min(4, 2 + depth // 6)
    else:
        low = 2
        high = min(5, 2 + depth // 5)

    if environment in {"sewer", "radwastes"} and kind in {"swarm", "pack"}:
        high = min(10, high + 1)
    if environment in {"corrupted", "hive", "voidship"} and kind == "pack":
        high = min(10, high + 1)

    high = max(low, high)
    return rng.randint(low, high)


_ENVIRONMENT_CONTACTS: dict[str, dict[str, tuple[_ContactArchetype, ...]]] = {
    "forge": {
        "hostile": (
            _ContactArchetype(
                name="Rogue Servitor",
                description="A corrupted labor automaton driven by broken directives.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
            ),
            _ContactArchetype(
                name="Rivet Skirmisher",
                description="A scrap-clad scavenger warding the machine halls.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
            ),
            _ContactArchetype(
                name="Circuit Heretek",
                description="A whispering saboteur carrying forbidden machine-cants.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="magos",
                weight=1,
                tags=("heretek", "saboteur", "forge"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Enginseer Volta",
                description="An industrious tech-priest maintaining the machine spirit.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=10,
                attack=3,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="enginseer",
            ),
            _ContactArchetype(
                name="Maintenance Adept",
                description="A nervous data-adept keeping the forges in ritual order.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=8,
                attack=2,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Silent Data-Clerk",
                description="An augmetic archivist silently recording production rites.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=1,
                attack_range=1,
                portrait_hint="mechanicus",
            ),
        ),
    },
    "cathedral": {
        "hostile": (
            _ContactArchetype(
                name="Heretic Acolyte",
                description="A zealot twisted by whispered blasphemies.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="priest",
            ),
            _ContactArchetype(
                name="Penitent Zealot",
                description="A brutal self-flagellating penitent just barely in control.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=3,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="priest",
                weight=1,
                tags=("penitent", "faith", "cathedral"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Confessor",
                description="A stern priest offering warning and absolution.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=8,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="priest",
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Reliquary Acolyte",
                description="A watcher tending sealed relics and sacred lamps.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=1,
                movement=1,
                attack_range=1,
                portrait_hint="adept",
            ),
        ),
    },
    "hive": {
        "hostile": (
            _ContactArchetype(
                name="Hive Ganger",
                description="A knife-armed ganger defending a scrap-fed claim.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
            ),
            _ContactArchetype(
                name="Rogue Enforcer Drone",
                description="A security construct gone brutally off-script.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
            ),
            _ContactArchetype(
                name="Sump Cutthroat",
                description="A hard-eyed underhive thug waiting to ambush rivals.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("criminal", "hive"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Hab Steward",
                description="A weary quartermaster trying to keep the levels supplied.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=7,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
            ),
            _ContactArchetype(
                name="Medicae Drudge",
                description="A patch-burnt helper keeping the hab-blocks from collapsing.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="mechanicus",
                weight=1,
                tags=("medicae", "civilian"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Smuggler",
                description="A watchful trader weighing allies against hazard pay.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=2,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="assassin",
            ),
        ),
    },
    "sewer": {
        "hostile": (
            _ContactArchetype(
                name="Sump Rat",
                description="A diseased rat large enough to worry an unprepared traveller.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=3,
                attack=2,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="servo-skull",
                weight=4,
                tags=("vermin", "sewer", "rat"),
            ),
            _ContactArchetype(
                name="Sump Mutant",
                description="A blighted creature lurks in the runoff tunnels.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=5,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
            ),
            _ContactArchetype(
                name="Drain Cutpurse",
                description="A sewer-born thief with toxin blades and no conscience.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=5,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("criminal", "sewer"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Drain Warden",
                description="A grim sanitation adept keeping the lower levels clear.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=7,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="enginseer",
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Pipe Hermit",
                description="A reclusive scavenger who knows the sewer routes.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="mechanicus",
            ),
            _ContactArchetype(
                name="Blackwater Broker",
                description="A small-time fixer trading in contraband and information.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="assassin",
                weight=1,
                tags=("criminal", "broker"),
            ),
        ),
    },
    "corrupted": {
        "hostile": (
            _ContactArchetype(
                name="Warp Spawn",
                description="A fractured thing that claws at reality itself.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=9,
                attack=5,
                armor=1,
                movement=4,
                attack_range=1,
                portrait_hint="magos",
            ),
            _ContactArchetype(
                name="Blight Hound",
                description="A vicious warped hound trailing scentless smoke.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("warp", "beast"),
            ),
            _ContactArchetype(
                name="Cult Husk",
                description="A corrupted disciple still whispering liturgy through cracked lips.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("cult", "corrupted"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Tainted Remnant",
                description="A lost soul clinging to enough sanity to answer questions.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=4,
                attack=1,
                armor=0,
                movement=1,
                attack_range=1,
                portrait_hint="adept",
            ),
        ),
    },
    "overgrown": {
        "hostile": (
            _ContactArchetype(
                name="Spore-Host",
                description="A fungi-ridden predator hidden in the growths.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
            ),
            _ContactArchetype(
                name="Vine Strangler",
                description="A lashing mass of roots and knives of bark.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("growth", "predator"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Lost Acolyte",
                description="A survivor tending the living ruins and their hidden paths.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=2,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="priest",
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Feral Scout",
                description="A wary guide watching from the green shadows.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="assassin",
            ),
        ),
    },
    "tomb": {
        "hostile": (
            _ContactArchetype(
                name="Awakened Sentinel",
                description="An ancient guardian stirred from its sarcophagus vigil.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=2,
                movement=2,
                attack_range=1,
                portrait_hint="servitor",
            ),
            _ContactArchetype(
                name="Bone-Chain Custodian",
                description="A skeletal guardian bound by old vow-sigils.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=3,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("guardian", "bone"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Dormant Scribe",
                description="A half-awake archivist bound to the crypt's records.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=1,
                movement=1,
                attack_range=1,
                portrait_hint="mechanicus",
            ),
        ),
    },
    "manufactorum": {
        "hostile": (
            _ContactArchetype(
                name="Rogue Labor-Automaton",
                description="A production drone that has learned to kill instead of work.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
            ),
            _ContactArchetype(
                name="Forge Riot Worker",
                description="A union-broken laborer wielding tools as weapons.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="pit_slave",
                weight=2,
                tags=("worker", "riot"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Overseer Servitor",
                description="An overseer unit still clinging to its maintenance directives.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=7,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="enginseer",
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Maintenance Drone",
                description="A patient repair drone hovering over broken machinery.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=4,
                attack=1,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="mechanicus",
            ),
            _ContactArchetype(
                name="Assembly Clerk",
                description="A ledger-obsessed overseer tallying machine output and defects.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=1,
                tags=("clerk", "manufactorum"),
            ),
        ),
    },
    "voidship": {
        "hostile": (
            _ContactArchetype(
                name="Void Raider",
                description="A boarding pirate moving through the ship's guts.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=3,
                tags=("void", "raider", "boarding"),
            ),
            _ContactArchetype(
                name="Mutinous Armsman",
                description="A deckhand turned killer under bad orders and worse omens.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="pit_slave",
                weight=2,
                tags=("mutiny", "crew"),
            ),
            _ContactArchetype(
                name="Breach Ghast",
                description="A half-suffocated wretch shaped by the ship's dead corridors.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=5,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="magos",
                weight=1,
                tags=("void", "haunt"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Boatswain",
                description="A practical ship hand maintaining the deck routes.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=7,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("crew", "voidship"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Void Pilgrim",
                description="A masked traveller keeping to the ship's quiet margins.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("pilgrim", "void"),
            ),
        ),
    },
    "reliquary": {
        "hostile": (
            _ContactArchetype(
                name="Relic Thief",
                description="A grave robber prying open sacred vaults for profit.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=3,
                tags=("thief", "relic"),
            ),
            _ContactArchetype(
                name="Desecrator",
                description="A blasphemer smashing sigils and scattering remains.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("blasphemy", "reliquary"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Sanctum Custodian",
                description="A stoic keeper guarding devotional records and relics.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=8,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("custodian", "faith"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Lampbearer",
                description="A quiet attendant carrying censers and votive lamps.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("attendant", "reliquary"),
            ),
        ),
    },
    "radwastes": {
        "hostile": (
            _ContactArchetype(
                name="Rad Mutant",
                description="A radiation-scarred killer wandering the ash flats.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="servitor",
                weight=3,
                tags=("mutant", "rad", "waste"),
            ),
            _ContactArchetype(
                name="Ash Scavenger",
                description="A desperate survivor who abandoned mercy long ago.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=5,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("scavenger", "waste"),
            ),
            _ContactArchetype(
                name="Dust Reaver",
                description="A hard-bitten marauder prowling for fuel and flesh.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=1,
                tags=("marauder", "radwastes"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Survey Adept",
                description="A cautious surveyor mapping safe paths through the wastes.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="mechanicus",
                weight=2,
                tags=("survey", "explorer"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Water Trader",
                description="A trader who measures every exchange in survival odds.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("trader", "waste"),
            ),
        ),
    },
    "data_vault": {
        "hostile": (
            _ContactArchetype(
                name="Scrap-Code Intruder",
                description="A feral code-thief chewing through archive locks.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="magos",
                weight=3,
                tags=("data", "intruder"),
            ),
            _ContactArchetype(
                name="Archive Heretek",
                description="A corrupted savant breaking the vault's logic seals.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="magos",
                weight=2,
                tags=("heretek", "archive"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Logister",
                description="A meticulous record keeper who speaks in index codes.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=7,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("logister", "archive"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Data Servitor",
                description="A patient clerk-machine still awaiting a proper command.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=4,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("servitor", "data"),
            ),
        ),
    },
    "xenos_ruin": {
        "hostile": (
            _ContactArchetype(
                name="Xenos Stalker",
                description="An alien hunter gliding between broken glyph-arches.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=3,
                tags=("xenos", "stalker"),
            ),
            _ContactArchetype(
                name="Relic Defiler",
                description="A raider stripping the ruin for trophies and tech.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("xenos", "defiler"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Xenologist",
                description="A cautious scholar cataloguing impossible architecture.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("scholar", "xenos"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Survey Drone",
                description="A flickering auspex drone following old pathing orders.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=4,
                attack=1,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="mechanicus",
                weight=2,
                tags=("drone", "survey"),
            ),
        ),
    },
    "ice_crypt": {
        "hostile": (
            _ContactArchetype(
                name="Cryo-ghoul",
                description="A frozen corpse that should have stayed sealed.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
                weight=3,
                tags=("cold", "crypt"),
            ),
            _ContactArchetype(
                name="Frost Warden",
                description="An eternal guard still enforcing the chamber's long silence.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("warden", "cold"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Cryo-Apothecary",
                description="A careful technician monitoring the stasis coffers.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="enginseer",
                weight=2,
                tags=("medical", "cold"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Stasis Keeper",
                description="A masked attendant tending the crypt's frozen seals.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("attendant", "stasis"),
            ),
        ),
    },
    "sump_market": {
        "hostile": (
            _ContactArchetype(
                name="Market Knife",
                description="A cutthroat who treats every stall as a kill zone.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=3,
                tags=("criminal", "market"),
            ),
            _ContactArchetype(
                name="Extortionist",
                description="A protection racketeer enforcing payments in blood.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("criminal", "sump"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Fence",
                description="A cautious broker who can source almost anything.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("broker", "market"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Market Broker",
                description="A measured trader watching the foot traffic and the knives.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("broker", "trade"),
            ),
        ),
    },
    "plasma_reactorum": {
        "hostile": (
            _ContactArchetype(
                name="Reactor Thrall",
                description="A scorched worker driven half-mad by heat and doctrine.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="pit_slave",
                weight=3,
                tags=("reactor", "thrall"),
            ),
            _ContactArchetype(
                name="Plasma Cultist",
                description="A zealot who worships the reactor's dangerous glow.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("cult", "reactor"),
            ),
            _ContactArchetype(
                name="Scorched Servitor",
                description="A ruined service automaton still carrying out catastrophic orders.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
                weight=1,
                tags=("machine", "heat"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Reactor Tech",
                description="A disciplined engineer balancing heat, pressure, and prayer.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=7,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="enginseer",
                weight=2,
                tags=("engineer", "reactor"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Heat Clerk",
                description="A clerk verifying heat output against sanctified tolerances.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("clerk", "heat"),
            ),
        ),
    },
    "penal_oubliette": {
        "hostile": (
            _ContactArchetype(
                name="Chain Ganger",
                description="A brutal convict still shackled to their old violence.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="pit_slave",
                weight=3,
                tags=("convict", "penal"),
            ),
            _ContactArchetype(
                name="Penal Bruiser",
                description="A warden's enforcer armed to smash riot lines.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("warden", "enforcer"),
            ),
            _ContactArchetype(
                name="Riot Convict",
                description="A desperate prisoner who knows the oubliette's weak points.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=5,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("riot", "convict"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Warden",
                description="A severe jailer maintaining the oubliette's failing order.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=8,
                attack=2,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("warden", "penal"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Penitent Scribe",
                description="A record keeper who speaks softly and expects little mercy.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=1,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("scribe", "penal"),
            ),
        ),
    },
    "ash_dune_outpost": {
        "hostile": (
            _ContactArchetype(
                name="Ork Loota",
                description="A roaring greenskin scavenger hefting a stolen deffgun.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=9,
                attack=5,
                armor=1,
                movement=3,
                attack_range=4,
                portrait_hint="pit_slave",
                weight=3,
                tags=("ork", "loota", "ash"),
            ),
            _ContactArchetype(
                name="Scrap Grot",
                description="A wiry grot darting between wreckage with stolen charges.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=4,
                attack=2,
                armor=0,
                movement=5,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("ork", "grot", "scavenger"),
            ),
            _ContactArchetype(
                name="Ash Raider",
                description="A wind-scoured marauder ambushing from the dunes.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=3,
                tags=("raider", "ash", "scavenger"),
            ),
            _ContactArchetype(
                name="Dune Marauder",
                description="A scavenger with a respirator mask and a mean streak.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="assassin",
                weight=2,
                tags=("marauder", "dune", "scavenger"),
            ),
            _ContactArchetype(
                name="Dust Jackal",
                description="A scavenger-beast trained to chase stragglers across the ash.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=5,
                attack=3,
                armor=0,
                movement=5,
                attack_range=1,
                portrait_hint="servitor",
                weight=1,
                tags=("beast", "ash", "scavenger"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Signal Scout",
                description="A lookout keeping the outpost's vox mast alive.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="mechanicus",
                weight=2,
                tags=("scout", "outpost", "survivor"),
            ),
            _ContactArchetype(
                name="Titan Secutor",
                description="A grim survivor from the titan recovery cohort guarding the breach.",
                disposition=DungeonDisposition.FRIENDLY,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=8,
                attack=3,
                armor=1,
                movement=2,
                attack_range=1,
                portrait_hint="skitarii",
                weight=1,
                tags=("titan", "survivor"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Surveyor",
                description="A dust-caked surveyor charting the safe ridges.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=5,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=2,
                tags=("survey", "outpost", "surveyor"),
            ),
            _ContactArchetype(
                name="Wreck Reclaimator",
                description="A soot-caked reclaimator searching the graveyard for salvage and survivors.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=1,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="adept",
                weight=1,
                tags=("reclaimator", "scavenger", "titan"),
            ),
        ),
    },
}


def _build_contact_entity(
    archetype: _ContactArchetype,
    entity_id: str,
) -> DungeonEntity:
    return DungeonEntity(
        entity_id=entity_id,
        name=archetype.name,
        disposition=archetype.disposition,
        movement_ai=archetype.movement_ai,
        can_talk=archetype.can_talk,
        portrait_key=archetype.portrait_hint or infer_portrait_key(archetype.name, archetype.description),
        stats=CombatStats(
            max_hp=archetype.max_hp,
            hp=archetype.max_hp,
            attack=archetype.attack,
            armor=archetype.armor,
            movement=archetype.movement,
            attack_range=archetype.attack_range,
        ),
        description=archetype.description,
    )


def _room_floor_tiles(level: DungeonLevel, room: DungeonRoom) -> list[tuple[int, int]]:
    tiles: list[tuple[int, int]] = []
    for y in range(room.y + 1, room.y + room.height - 1):
        for x in range(room.x + 1, room.x + room.width - 1):
            if level.in_bounds(x, y) and level.get_terrain(x, y) == DungeonTerrain.FLOOR:
                tiles.append((x, y))
    return tiles


def _pick_contact_position(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    occupied: set[tuple[int, int]],
    rng: random.Random,
) -> tuple[int, int] | None:
    candidate_rooms = [room for room in rooms if room.center not in occupied]
    rng.shuffle(candidate_rooms)
    for room in candidate_rooms:
        room_tiles = [pos for pos in _room_floor_tiles(level, room) if pos not in occupied]
        if not room_tiles:
            continue
        room_tiles.sort(
            key=lambda pos: (
                abs(pos[0] - room.center[0]) + abs(pos[1] - room.center[1]),
                abs(pos[0] - level.player_pos[0]) + abs(pos[1] - level.player_pos[1]) if level.player_pos else 0,
            )
        )
        if room_tiles:
            return rng.choice(room_tiles[: max(1, min(3, len(room_tiles)))])

    fallback_tiles = [
        (x, y)
        for y in range(1, level.height - 1)
        for x in range(1, level.width - 1)
        if level.get_terrain(x, y) == DungeonTerrain.FLOOR and (x, y) not in occupied
    ]
    if not fallback_tiles:
        return None
    return rng.choice(fallback_tiles)


def _pick_group_positions(
    level: DungeonLevel,
    room: DungeonRoom,
    count: int,
    occupied: set[tuple[int, int]],
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Pick clustered spawn positions inside a single room."""
    room_tiles = [pos for pos in _room_floor_tiles(level, room) if pos not in occupied]
    if not room_tiles:
        return []

    room_tiles.sort(
        key=lambda pos: (
            abs(pos[0] - room.center[0]) + abs(pos[1] - room.center[1]),
            abs(pos[0] - level.player_pos[0]) + abs(pos[1] - level.player_pos[1]) if level.player_pos else 0,
        )
    )
    anchor = room_tiles[0]
    positions = [anchor]
    remaining = [pos for pos in room_tiles if pos != anchor]
    rng.shuffle(remaining)
    remaining.sort(
        key=lambda pos: (
            abs(pos[0] - anchor[0]) + abs(pos[1] - anchor[1]),
            abs(pos[0] - room.center[0]) + abs(pos[1] - room.center[1]),
        )
    )

    for pos in remaining:
        if len(positions) >= count:
            break
        distance = abs(pos[0] - anchor[0]) + abs(pos[1] - anchor[1])
        if distance <= 3 or len(room_tiles) <= count + 1:
            positions.append(pos)

    if len(positions) < count:
        for pos in remaining:
            if len(positions) >= count:
                break
            if pos not in positions:
                positions.append(pos)

    return positions[:count]


def _select_contact_room(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    occupied: set[tuple[int, int]],
    count: int,
    rng: random.Random,
) -> tuple[int, DungeonRoom] | None:
    """Choose a room that can reasonably hold a contact group."""
    scored_rooms: list[tuple[int, int, int, DungeonRoom]] = []
    for index, room in enumerate(rooms):
        if index in {0, len(rooms) - 1} and len(rooms) > 1:
            continue
        available = len([pos for pos in _room_floor_tiles(level, room) if pos not in occupied])
        if available <= 0:
            continue
        center_distance = abs(room.center[0] - level.width // 2) + abs(room.center[1] - level.height // 2)
        scored_rooms.append((available, -center_distance, -index, room))

    if not scored_rooms:
        return None

    scored_rooms.sort(reverse=True)
    viable = [entry for entry in scored_rooms if entry[0] >= count]
    pool = viable or scored_rooms
    shortlist = pool[: min(3, len(pool))]
    _, _, neg_index, room = rng.choice(shortlist)
    return -neg_index, room


def _room_tiles_by_focus(
    level: DungeonLevel,
    room: DungeonRoom,
    occupied: set[tuple[int, int]],
    focus: str = "center",
) -> list[tuple[int, int]]:
    """Return room tiles ordered by a placement focus."""
    room_tiles = [pos for pos in _room_floor_tiles(level, room) if pos not in occupied]
    if focus == "edge":
        room_tiles.sort(
            key=lambda pos: (
                min(
                    abs(pos[0] - room.x),
                    abs(pos[0] - (room.x + room.width - 1)),
                    abs(pos[1] - room.y),
                    abs(pos[1] - (room.y + room.height - 1)),
                ),
                abs(pos[0] - room.center[0]) + abs(pos[1] - room.center[1]),
            )
        )
    elif focus == "corner":
        corners = (
            (room.x + 1, room.y + 1),
            (room.x + room.width - 2, room.y + 1),
            (room.x + 1, room.y + room.height - 2),
            (room.x + room.width - 2, room.y + room.height - 2),
        )
        room_tiles.sort(
            key=lambda pos: (
                min(abs(pos[0] - cx) + abs(pos[1] - cy) for cx, cy in corners),
                abs(pos[0] - room.center[0]) + abs(pos[1] - room.center[1]),
            )
        )
    else:
        room_tiles.sort(
            key=lambda pos: (
                abs(pos[0] - room.center[0]) + abs(pos[1] - room.center[1]),
                abs(pos[0] - level.player_pos[0]) + abs(pos[1] - level.player_pos[1]) if level.player_pos else 0,
            )
        )
    return room_tiles


def _pick_room_tiles(
    level: DungeonLevel,
    room: DungeonRoom,
    count: int,
    occupied: set[tuple[int, int]],
    rng: random.Random,
    focus: str = "center",
) -> list[tuple[int, int]]:
    room_tiles = _room_tiles_by_focus(level, room, occupied, focus=focus)
    if not room_tiles or count <= 0:
        return []
    anchor = room_tiles[0]
    positions = [anchor]
    remaining = [pos for pos in room_tiles if pos != anchor]
    rng.shuffle(remaining)
    remaining.sort(
        key=lambda pos: (
            abs(pos[0] - anchor[0]) + abs(pos[1] - anchor[1]),
            abs(pos[0] - room.center[0]) + abs(pos[1] - room.center[1]),
        )
    )
    for pos in remaining:
        if len(positions) >= count:
            break
        if abs(pos[0] - anchor[0]) + abs(pos[1] - anchor[1]) <= 3 or len(room_tiles) <= count + 1:
            positions.append(pos)
    if len(positions) < count:
        for pos in remaining:
            if len(positions) >= count:
                break
            if pos not in positions:
                positions.append(pos)
    return positions[:count]


def _match_theme_archetypes(
    category_pool: tuple[_ContactArchetype, ...],
    spec: ThemedRoomEncounterSpec,
) -> tuple[_ContactArchetype, ...]:
    if not category_pool:
        return ()
    if not spec.preferred_tags and not spec.preferred_names:
        return category_pool

    preferred_tags = {tag.lower() for tag in spec.preferred_tags}
    preferred_names = {name.lower() for name in spec.preferred_names}
    scored: list[tuple[int, _ContactArchetype]] = []
    for archetype in category_pool:
        score = 0
        name = archetype.name.lower()
        description = archetype.description.lower()
        text = f"{name} {description} {' '.join(archetype.tags)}"
        if name in preferred_names:
            score += 8
        if any(tag in text for tag in preferred_tags):
            score += 4
        if score > 0:
            scored.append((score, archetype))
    if not scored:
        return category_pool
    scored.sort(key=lambda item: (item[0], item[1].weight), reverse=True)
    return tuple(archetype for _, archetype in scored)


def _select_template_room_index(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    template: ThemedRoomTemplate,
    occupied: set[tuple[int, int]],
    required_tiles: int,
    rng: random.Random,
) -> int | None:
    if not rooms:
        return None

    scored: list[tuple[int, int, int, int]] = []
    for index, room in enumerate(rooms):
        if len(rooms) > 1 and index in {0, len(rooms) - 1}:
            continue
        if template.room_types and room.room_type not in template.room_types:
            continue
        available = len([pos for pos in _room_floor_tiles(level, room) if pos not in occupied])
        if available <= 0:
            continue
        if template.requires_spacious_room and available < required_tiles + 2:
            continue
        center_distance = abs(room.center[0] - level.width // 2) + abs(room.center[1] - level.height // 2)
        scored.append((available, -center_distance, -index, index))

    if not scored:
        for index, room in enumerate(rooms):
            if len(rooms) > 1 and index in {0, len(rooms) - 1}:
                continue
            available = len([pos for pos in _room_floor_tiles(level, room) if pos not in occupied])
            if available <= 0:
                continue
            center_distance = abs(room.center[0] - level.width // 2) + abs(room.center[1] - level.height // 2)
            scored.append((available, -center_distance, -index, index))
    if not scored:
        return None
    scored.sort(reverse=True)
    shortlist = scored[: min(3, len(scored))]
    return rng.choice(shortlist)[-1]


def _select_themed_archetype(
    contacts: dict[str, tuple[_ContactArchetype, ...]],
    spec: ThemedRoomEncounterSpec,
    rng: random.Random,
) -> _ContactArchetype | None:
    pool = contacts.get(spec.category, ())
    if not pool:
        return None
    filtered = _match_theme_archetypes(pool, spec)
    return _weighted_choice(filtered, rng)


def _apply_themed_room_template(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    room_index: int,
    template: ThemedRoomTemplate,
    environment: str,
    depth: int,
    rng: random.Random,
    occupied: set[tuple[int, int]],
    roster: DungeonEntityRoster,
    profile: DungeonGenerationProfile | None = None,
) -> tuple[ThemedRoomInstance | None, int]:
    room = rooms[room_index]
    room_area = room.width * room.height
    required_tiles = max(
        len(template.feature_terrains),
        sum(max(1, spec.count_range[0]) for spec in template.props),
        sum(max(1, spec.count_range[0]) for spec in template.encounter_groups),
    )
    room_tiles = _room_tiles_by_focus(level, room, occupied, focus="center")
    if len(room_tiles) < max(4, required_tiles):
        return None, 0

    instance = ThemedRoomInstance(
        template_name=template.name,
        room_index=room_index,
        room_type=room.room_type,
    )
    themed_contact_count = 0

    for terrain in template.feature_terrains:
        feature_count = max(1, min(3, room_area // 40))
        if terrain in (DungeonTerrain.SHRINE, DungeonTerrain.TERMINAL) and room_area >= 40:
            feature_count = max(feature_count, 2)
        positions = _pick_room_tiles(level, room, feature_count, occupied, rng, focus="center")
        for pos in positions:
            level.set_terrain(pos[0], pos[1], terrain)
            occupied.add(pos)
            instance.feature_tiles.append(pos)

    for prop_spec in template.props:
        count = rng.randint(prop_spec.count_range[0], prop_spec.count_range[1])
        positions = _pick_room_tiles(level, room, count, occupied, rng, focus=prop_spec.room_focus)
        for pos in positions:
            level.set_terrain(pos[0], pos[1], prop_spec.terrain)
            occupied.add(pos)
            instance.prop_tiles.append((prop_spec.terrain, pos))

    contacts = _contacts_for_generation(environment, profile)
    for encounter_spec in template.encounter_groups:
        archetype = _select_themed_archetype(contacts, encounter_spec, rng)
        if archetype is None:
            continue
        count = rng.randint(encounter_spec.count_range[0], encounter_spec.count_range[1])
        if encounter_spec.optional and count <= 1 and rng.random() < 0.35:
            continue
        count = max(1, count)
        positions = _pick_group_positions(level, room, count, occupied, rng)
        if len(positions) < count:
            positions = _pick_room_tiles(level, room, count, occupied, rng)
        if not positions:
            continue
        for member_index, position in enumerate(positions[:count]):
            entity_id = f"{environment}-theme-{depth}-{room_index}-{len(instance.encounter_ids)}-{member_index}"
            entity = _build_contact_entity(archetype, entity_id)
            roster.add(entity)
            entity.place(level, position[0], position[1])
            occupied.add(position)
            instance.encounter_ids.append(entity_id)
        themed_contact_count += count

    if not instance.feature_tiles and not instance.prop_tiles and not instance.encounter_ids:
        return None, 0
    return instance, themed_contact_count


def _themed_room_templates_for_environment(
    environment: str,
    profile: DungeonGenerationProfile | None = None,
) -> tuple[ThemedRoomTemplate, ...]:
    templates = tuple(
        template
        for template_group in _THEMED_ROOM_TEMPLATES.values()
        for template in template_group
        if environment in template.environments
    ) or _THEMED_ROOM_TEMPLATES["default"]
    if profile is None:
        return templates

    excluded_names = {name.lower() for name in profile.excluded_themed_room_names}
    excluded_tags = {tag.lower() for tag in profile.excluded_themed_room_tags}
    filtered = tuple(
        template
        for template in templates
        if template.name.lower() not in excluded_names
        and not any(tag.lower() in excluded_tags for tag in template.tags)
    )
    return filtered or templates


def _generate_themed_rooms(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    environment: str,
    depth: int,
    rng: random.Random,
    entity_roster: DungeonEntityRoster,
    occupied: set[tuple[int, int]],
    profile: DungeonGenerationProfile | None = None,
) -> tuple[list[ThemedRoomInstance], int]:
    templates = list(_themed_room_templates_for_environment(environment, profile))
    if not templates or len(rooms) < 2:
        return [], 0

    eligible = [
        template
        for template in templates
        if template.min_depth <= depth <= template.max_depth
    ]
    if not eligible:
        return [], 0

    themed_instances: list[ThemedRoomInstance] = []
    themed_contact_count = 0
    room_indices_used: set[int] = set()
    template_usage: dict[str, int] = {}
    max_set_pieces = 0
    if depth >= 3 and len(rooms) >= 4:
        max_set_pieces = 1
    if depth >= 8 and len(rooms) >= 6 and rng.random() < 0.5:
        max_set_pieces += 1
    if profile is not None and (
        profile.required_themed_room_names or profile.preferred_themed_room_tags
    ):
        max_set_pieces = max(1, max_set_pieces)

    if max_set_pieces <= 0:
        return [], 0

    weighted_templates = sorted(eligible, key=lambda template: template.weight, reverse=True)
    required_names = {
        name.lower() for name in (profile.required_themed_room_names if profile is not None else ())
    }
    preferred_tags = profile.preferred_themed_room_tags if profile is not None else ()

    ordered_templates: list[ThemedRoomTemplate] = []
    for template in weighted_templates:
        if template.name.lower() in required_names:
            ordered_templates.append(template)
    for template in weighted_templates:
        if template.name.lower() in required_names:
            continue
        if preferred_tags and _matches_any_tag(template.tags, preferred_tags):
            ordered_templates.append(template)
    for template in weighted_templates:
        if template not in ordered_templates:
            ordered_templates.append(template)

    for _ in range(max_set_pieces):
        candidates = [
            template
            for template in ordered_templates
            if template_usage.get(template.name, 0) < template.max_per_floor
        ]
        if not candidates:
            break
        total_weight = sum(max(1, template.weight) for template in candidates)
        roll = rng.randint(1, total_weight)
        template = candidates[-1]
        for candidate in candidates:
            roll -= max(1, candidate.weight)
            if roll <= 0:
                template = candidate
                break

        required_tiles = max(
            len(template.feature_terrains),
            sum(max(1, spec.count_range[0]) for spec in template.props),
            sum(max(1, spec.count_range[0]) for spec in template.encounter_groups),
        )
        room_index = _select_template_room_index(
            level,
            rooms,
            template,
            occupied,
            required_tiles,
            rng,
        )
        if room_index is None or room_index in room_indices_used:
            continue

        instance, count = _apply_themed_room_template(
            level,
            rooms,
            room_index,
            template,
            environment,
            depth,
            rng,
            occupied,
            entity_roster,
            profile,
        )
        if instance is None:
            continue
        room_indices_used.add(room_index)
        template_usage[template.name] = template_usage.get(template.name, 0) + 1
        themed_instances.append(instance)
        themed_contact_count += count

    return themed_instances, themed_contact_count


def _plan_contact_spawns(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    environment: str,
    depth: int,
    rng: random.Random,
    profile: DungeonGenerationProfile | None = None,
) -> list[_ContactSpawnPlan]:
    """Plan contact groups before actual placement.

    This keeps spawn selection separate from geometry so future themed-room
    generation can reuse the same planning seam.
    """
    contacts = _contacts_for_generation(environment, profile)
    hostile_pool = contacts.get("hostile", ())
    friendly_pool = contacts.get("friendly", ())
    neutral_pool = contacts.get("neutral", ())
    low, high = _ENVIRONMENT_CONTACT_RANGES.get(environment, (2, 5))
    total_contacts = max(1, min(high, max(low, 1 + depth // 2 + len(rooms) // 5)))
    if hostile_pool:
        total_contacts = max(3, total_contacts)

    category_pools: dict[str, tuple[_ContactArchetype, ...]] = {
        "hostile": hostile_pool,
        "friendly": friendly_pool,
        "neutral": neutral_pool,
    }
    available_categories = [name for name, pool in category_pools.items() if pool]
    if not available_categories:
        return []

    weights = _ENVIRONMENT_CONTACT_WEIGHTS.get(environment, (60, 20, 20))
    category_weights = {
        "hostile": weights[0],
        "friendly": weights[1],
        "neutral": weights[2],
    }

    plans: list[_ContactSpawnPlan] = []
    support_target = 1 if total_contacts > 1 and (friendly_pool or neutral_pool) else 0
    hostile_target = max(2, total_contacts - support_target) if hostile_pool else 0
    hostile_target = min(total_contacts, hostile_target)
    support_remaining = total_contacts - hostile_target
    hostile_remaining = hostile_target

    while hostile_remaining > 0 and hostile_pool:
        archetype = _weighted_choice(hostile_pool, rng)
        count = min(
            hostile_remaining,
            _group_size_for_archetype(archetype, environment, depth, rng),
        )
        room_choice = _select_contact_room(level, rooms, set(level.stairs_up) | set(level.stairs_down), count, rng)
        plans.append(
            _ContactSpawnPlan(
                category="hostile",
                archetype=archetype,
                count=count,
                room_index=room_choice[0] if room_choice is not None else None,
                group_kind=_group_kind_for_archetype(archetype),
            )
        )
        hostile_remaining -= count

    support_categories = [name for name in ("friendly", "neutral") if category_pools[name]]
    while support_remaining > 0 and support_categories:
        category = _choose_category(support_categories, category_weights, rng)
        archetype = _weighted_choice(category_pools[category], rng)
        room_choice = _select_contact_room(level, rooms, set(level.stairs_up) | set(level.stairs_down), 1, rng)
        plans.append(
            _ContactSpawnPlan(
                category=category,
                archetype=archetype,
                count=1,
                room_index=room_choice[0] if room_choice is not None else None,
                group_kind="solo",
            )
        )
        support_remaining -= 1

    while len(plans) < total_contacts:
        category = _choose_category(available_categories, category_weights, rng)
        archetype = _weighted_choice(category_pools[category], rng)
        count = 1 if category != "hostile" else min(
            _group_size_for_archetype(archetype, environment, depth, rng),
            total_contacts - len(plans),
        )
        room_choice = _select_contact_room(level, rooms, set(level.stairs_up) | set(level.stairs_down), count, rng)
        plans.append(
            _ContactSpawnPlan(
                category=category,
                archetype=archetype,
                count=count,
                room_index=room_choice[0] if room_choice is not None else None,
                group_kind=_group_kind_for_archetype(archetype) if category == "hostile" else "solo",
            )
        )

    rng.shuffle(plans)
    return plans


def _contacts_for_environment(environment: str) -> dict[str, tuple[_ContactArchetype, ...]]:
    return _ENVIRONMENT_CONTACTS.get(environment, _ENVIRONMENT_CONTACTS["forge"])


def _matches_any_tag(tags: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    if not expected:
        return True
    available = {tag.lower() for tag in tags}
    return any(tag.lower() in available for tag in expected)


def _filter_contact_pool(
    pool: tuple[_ContactArchetype, ...],
    *,
    preferred_tags: tuple[str, ...] = (),
    excluded_tags: tuple[str, ...] = (),
    excluded_names: tuple[str, ...] = (),
) -> tuple[_ContactArchetype, ...]:
    excluded_tag_set = {tag.lower() for tag in excluded_tags}
    excluded_name_set = {name.lower() for name in excluded_names}
    filtered = tuple(
        archetype
        for archetype in pool
        if archetype.name.lower() not in excluded_name_set
        and not any(tag.lower() in excluded_tag_set for tag in archetype.tags)
    )
    if not preferred_tags:
        return filtered
    preferred = tuple(
        archetype for archetype in filtered if _matches_any_tag(archetype.tags, preferred_tags)
    )
    return preferred or filtered


def _contacts_for_generation(
    environment: str,
    profile: DungeonGenerationProfile | None = None,
) -> dict[str, tuple[_ContactArchetype, ...]]:
    contacts = _contacts_for_environment(environment)
    if profile is None:
        return contacts
    return {
        "hostile": _filter_contact_pool(
            contacts.get("hostile", ()),
            preferred_tags=profile.hostile_tags,
            excluded_tags=profile.excluded_contact_tags,
            excluded_names=profile.excluded_contact_names,
        ),
        "friendly": _filter_contact_pool(
            contacts.get("friendly", ()),
            preferred_tags=profile.friendly_tags,
            excluded_tags=profile.excluded_contact_tags,
            excluded_names=profile.excluded_contact_names,
        ),
        "neutral": _filter_contact_pool(
            contacts.get("neutral", ()),
            preferred_tags=profile.neutral_tags,
            excluded_tags=profile.excluded_contact_tags,
            excluded_names=profile.excluded_contact_names,
        ),
    }


_ENVIRONMENT_CONTACT_RANGES: dict[str, tuple[int, int]] = {
    "forge": (2, 4),
    "cathedral": (1, 4),
    "hive": (3, 6),
    "sewer": (3, 6),
    "corrupted": (2, 5),
    "overgrown": (2, 5),
    "tomb": (1, 3),
    "manufactorum": (2, 5),
    "voidship": (3, 6),
    "reliquary": (1, 4),
    "radwastes": (2, 5),
    "data_vault": (2, 4),
    "xenos_ruin": (2, 5),
    "ice_crypt": (1, 4),
    "sump_market": (2, 5),
    "plasma_reactorum": (2, 5),
    "penal_oubliette": (2, 5),
    "ash_dune_outpost": (2, 5),
}

_ENVIRONMENT_CONTACT_WEIGHTS: dict[str, tuple[int, int, int]] = {
    "forge": (50, 30, 20),
    "cathedral": (30, 45, 25),
    "hive": (55, 20, 25),
    "sewer": (75, 5, 20),
    "corrupted": (90, 0, 10),
    "overgrown": (55, 25, 20),
    "tomb": (60, 0, 40),
    "manufactorum": (60, 25, 15),
    "voidship": (55, 25, 20),
    "reliquary": (30, 45, 25),
    "radwastes": (75, 5, 20),
    "data_vault": (45, 35, 20),
    "xenos_ruin": (70, 10, 20),
    "ice_crypt": (50, 10, 40),
    "sump_market": (50, 20, 30),
    "plasma_reactorum": (70, 20, 10),
    "penal_oubliette": (80, 10, 10),
    "ash_dune_outpost": (65, 10, 25),
}


_THEMED_ROOM_TEMPLATES: dict[str, tuple[ThemedRoomTemplate, ...]] = {
    "default": (
        ThemedRoomTemplate(
            name="Sanctified Conclave",
            description="A generic ritual chamber with a marker, a pair of guards, and a focal feature.",
            environments=("forge", "cathedral", "hive", "reliquary", "manufactorum", "voidship"),
            room_types=("open_room", "pillared_hall", "cross_room"),
            min_depth=3,
            max_depth=999,
            weight=2,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.TERMINAL),
            props=(ThemedRoomPropSpec(DungeonTerrain.COVER, (1, 2), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 4),
                    preferred_tags=("cult", "heretek", "warden", "board", "guard"),
                    optional=False,
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("scribe", "attendant", "clerk"),
                    optional=True,
                ),
            ),
            tags=("ritual", "conclave"),
        ),
    ),
    "forge": (
        ThemedRoomTemplate(
            name="Heretek Workshop",
            description="A machine cult workshop with chanting operators and a central machine shrine.",
            environments=("forge", "manufactorum", "data_vault", "plasma_reactorum"),
            room_types=("pillared_hall", "open_room", "l_shaped"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.TERMINAL, DungeonTerrain.COLUMN),
            props=(ThemedRoomPropSpec(DungeonTerrain.SHRINE, (1, 1)),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 5),
                    preferred_tags=("heretek", "reactor", "cult", "machine"),
                ),
                ThemedRoomEncounterSpec(
                    category="friendly",
                    count_range=(0, 1),
                    preferred_tags=("engineer", "overseer", "clerk", "adept"),
                    optional=True,
                ),
            ),
            tags=("machine_cult", "forge"),
        ),
        ThemedRoomTemplate(
            name="Reactor Cult Cell",
            description="A risk-prone shrine where zealots have gathered around dangerous machinery.",
            environments=("plasma_reactorum", "forge", "manufactorum"),
            room_types=("arena", "open_room", "cross_room"),
            min_depth=4,
            max_depth=999,
            weight=3,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.COVER),
            props=(ThemedRoomPropSpec(DungeonTerrain.TERMINAL, (1, 2), room_focus="center"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 6),
                    preferred_tags=("cult", "reactor", "thrall"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("heat", "clerk", "tech"),
                    optional=True,
                ),
            ),
            tags=("machine_cult", "reactor"),
        ),
    ),
    "cathedral": (
        ThemedRoomTemplate(
            name="Blooded Chapel",
            description="An illicit rite chamber built around a cracked altar and hidden victims.",
            environments=("cathedral", "reliquary", "corrupted", "tomb"),
            room_types=("open_room", "pillared_hall", "cross_room"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.COLUMN),
            props=(ThemedRoomPropSpec(DungeonTerrain.RUBBLE, (1, 2), room_focus="center"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 6),
                    preferred_tags=("cult", "faith", "heretic", "penitent"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(1, 1),
                    preferred_tags=("attendant", "scribe", "victim", "lamp"),
                    optional=True,
                ),
            ),
            tags=("chapel", "ritual", "warp"),
        ),
        ThemedRoomTemplate(
            name="Reliquary Vault",
            description="A sealed devotional vault with warded displays and a restrained custodian.",
            environments=("reliquary", "cathedral", "ice_crypt", "tomb"),
            room_types=("small_chamber", "pillared_hall", "cross_room"),
            min_depth=1,
            max_depth=999,
            weight=3,
            max_per_floor=1,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.COLUMN),
            props=(ThemedRoomPropSpec(DungeonTerrain.TERMINAL, (1, 1), room_focus="center"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="friendly",
                    count_range=(0, 1),
                    preferred_tags=("custodian", "faith", "guardian"),
                    optional=True,
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("lamp", "scribe", "attendant"),
                    optional=True,
                ),
            ),
            tags=("vault", "reliquary"),
        ),
    ),
    "hive": (
        ThemedRoomTemplate(
            name="Underhive Den",
            description="A cramped gang hideout with a stash pile, lookout post, and ambush points.",
            environments=("hive", "sewer", "sump_market", "penal_oubliette"),
            room_types=("small_chamber", "l_shaped", "maze"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=False,
            feature_terrains=(DungeonTerrain.COVER, DungeonTerrain.RUBBLE),
            props=(ThemedRoomPropSpec(DungeonTerrain.TERMINAL, (1, 1), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 7),
                    preferred_tags=("gang", "criminal", "convict", "cutthroat", "rat"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("broker", "warden", "scout"),
                    optional=True,
                ),
            ),
            tags=("underhive", "gang"),
        ),
        ThemedRoomTemplate(
            name="Sump Shrine",
            description="A filthy altar room where the underhive has built a warped devotional shrine.",
            environments=("sewer", "hive", "sump_market", "corrupted"),
            room_types=("open_room", "cross_room", "arena"),
            min_depth=3,
            max_depth=999,
            weight=3,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.WATER, DungeonTerrain.COVER),
            props=(ThemedRoomPropSpec(DungeonTerrain.SHRINE, (1, 2), room_focus="center"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 6),
                    preferred_tags=("cult", "criminal", "sump", "rat"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("guide", "broker", "warden"),
                    optional=True,
                ),
            ),
            tags=("underhive", "chapel"),
        ),
    ),
    "voidship": (
        ThemedRoomTemplate(
            name="Boarding Action",
            description="A breach-side room where boarders clash with ship crew around a blown-out hatch.",
            environments=("voidship", "ash_dune_outpost", "data_vault"),
            room_types=("corridor", "l_shaped", "cross_room", "open_room"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=False,
            feature_terrains=(DungeonTerrain.TERMINAL, DungeonTerrain.COVER),
            props=(ThemedRoomPropSpec(DungeonTerrain.DOOR_CLOSED, (1, 2), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 6),
                    preferred_tags=("boarding", "raider", "mutiny", "intruder"),
                ),
                ThemedRoomEncounterSpec(
                    category="friendly",
                    count_range=(0, 1),
                    preferred_tags=("crew", "pilot", "boatswain", "scout"),
                    optional=True,
                ),
            ),
            tags=("breach", "boarding"),
        ),
    ),
    "radwastes": (
        ThemedRoomTemplate(
            name="Ash Pit",
            description="A blasted kill-zone where scavengers and mutants circle a toxic hollow.",
            environments=("radwastes", "ash_dune_outpost", "xenos_ruin"),
            room_types=("arena", "open_room", "maze"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.RUBBLE, DungeonTerrain.ACID_POOL),
            props=(ThemedRoomPropSpec(DungeonTerrain.COVER, (1, 2), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(4, 8),
                    preferred_tags=("mutant", "scavenger", "marauder", "beast"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("survey", "trader", "guide"),
                    optional=True,
                ),
            ),
            tags=("ash", "wastes", "scavenger"),
        ),
        ThemedRoomTemplate(
            name="Titan Hull Breach",
            description="A breached god-engine compartment littered with wreckage and sacred machinery.",
            environments=("radwastes", "ash_dune_outpost"),
            room_types=("open_room", "arena", "cross_room"),
            min_depth=1,
            max_depth=999,
            weight=5,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.RUBBLE, DungeonTerrain.TERMINAL),
            props=(
                ThemedRoomPropSpec(DungeonTerrain.COLUMN, (2, 4), room_focus="edge"),
                ThemedRoomPropSpec(DungeonTerrain.COVER, (1, 2), room_focus="center"),
            ),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 4),
                    preferred_tags=("ork", "loota", "scavenger"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("reclaimator", "survivor", "surveyor"),
                    optional=True,
                ),
            ),
            tags=("titan", "wreck", "breach"),
        ),
        ThemedRoomTemplate(
            name="Ork Scrap Redoubt",
            description="A looter fortification built from titan plating, barricades, and stolen gear.",
            environments=("radwastes", "ash_dune_outpost"),
            room_types=("arena", "maze", "open_room"),
            min_depth=1,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.COVER, DungeonTerrain.RUBBLE),
            props=(ThemedRoomPropSpec(DungeonTerrain.COVER, (2, 4), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 6),
                    preferred_tags=("ork", "loota", "grot"),
                ),
            ),
            tags=("ork", "fortification", "scrap"),
        ),
    ),
}


def _generate_contacts(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    environment: str,
    depth: int,
    rng: random.Random,
    reserved_positions: set[tuple[int, int]] | None = None,
    budget_offset: int = 0,
    roster: DungeonEntityRoster | None = None,
    profile: DungeonGenerationProfile | None = None,
) -> DungeonEntityRoster:
    roster = roster or DungeonEntityRoster()
    occupied: set[tuple[int, int]] = set(level.stairs_up) | set(level.stairs_down)
    if reserved_positions:
        occupied.update(reserved_positions)
    rooms_for_contacts = [room for index, room in enumerate(rooms) if index not in {0, len(rooms) - 1}]
    if not rooms_for_contacts:
        rooms_for_contacts = list(rooms)

    plans = _plan_contact_spawns(level, rooms_for_contacts, environment, depth, rng, profile)
    if budget_offset > 0 and plans:
        trimmed: list[_ContactSpawnPlan] = []
        remaining_trim = budget_offset
        for plan in sorted(plans, key=lambda item: (item.category != "hostile", item.count), reverse=True):
            if remaining_trim <= 0:
                trimmed.append(plan)
                continue
            if plan.category == "hostile" and plan.count > 1:
                take = min(plan.count - 1, remaining_trim)
                trimmed.append(
                    _ContactSpawnPlan(
                        category=plan.category,
                        archetype=plan.archetype,
                        count=plan.count - take,
                        room_index=plan.room_index,
                        group_kind=plan.group_kind,
                    )
                )
                remaining_trim -= take
            else:
                trimmed.append(plan)
        plans = trimmed

    for index, plan in enumerate(plans):
        room_index = plan.room_index
        positions: list[tuple[int, int]] = []
        if room_index is not None and 0 <= room_index < len(rooms_for_contacts):
            positions = _pick_group_positions(
                level,
                rooms_for_contacts[room_index],
                plan.count,
                occupied,
                rng,
            )

        if len(positions) < plan.count:
            fallback_pool = [
                pos
                for pos in _floor_tiles(level)
                if pos not in occupied and pos not in set(level.stairs_up) | set(level.stairs_down)
            ]
            if fallback_pool:
                fallback_pool.sort(
                    key=lambda pos: (
                        abs(pos[0] - level.player_pos[0]) + abs(pos[1] - level.player_pos[1]) if level.player_pos else 0,
                        abs(pos[0] - level.width // 2) + abs(pos[1] - level.height // 2),
                    )
                )
                for pos in fallback_pool:
                    if len(positions) >= plan.count:
                        break
                    if pos not in positions:
                        positions.append(pos)

        if not positions:
            continue

        for member_index, position in enumerate(positions[:plan.count]):
            entity_id = f"{environment}-contact-{depth}-{index}-{member_index}"
            entity = _build_contact_entity(plan.archetype, entity_id)
            roster.add(entity)
            entity.place(level, position[0], position[1])
            occupied.add(position)

    return roster


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
    profile: DungeonGenerationProfile | None = None,
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

    transition_terrain = _transition_terrain_for_environment(env.name)
    if transition_terrain is None:
        level.set_terrain(stairs_up[0], stairs_up[1], DungeonTerrain.STAIRS_UP)
        level.set_terrain(stairs_down[0], stairs_down[1], DungeonTerrain.STAIRS_DOWN)
    else:
        level.set_terrain(stairs_up[0], stairs_up[1], transition_terrain)
        level.set_terrain(stairs_down[0], stairs_down[1], transition_terrain)
    level.stairs_up = [stairs_up]
    level.stairs_down = [stairs_down]
    level.player_pos = stairs_up

    reserved = {stairs_up, stairs_down}
    _add_doors(level, rng, rooms)
    secret_passages = _add_secret_passage(level, rooms, reserved, rng)
    reserved.update(pos for passage in secret_passages for pos in passage)
    entity_roster = DungeonEntityRoster()
    themed_rooms, themed_contact_count = _generate_themed_rooms(
        level,
        rooms,
        env.name,
        depth,
        rng,
        entity_roster,
        reserved,
        profile,
    )
    _scatter_environment_features(level, rooms, env.name, reserved, rng)
    placed_items = _scatter_environment_objects(level, rooms, env.name, depth, reserved, rng)
    entity_roster = _generate_contacts(
        level,
        rooms,
        env.name,
        depth,
        rng,
        reserved_positions=reserved,
        budget_offset=themed_contact_count,
        roster=entity_roster,
        profile=profile,
    )

    # Late carving steps can brush over traversal tiles, so reapply them last.
    if transition_terrain is None:
        level.set_terrain(stairs_up[0], stairs_up[1], DungeonTerrain.STAIRS_UP)
        level.set_terrain(stairs_down[0], stairs_down[1], DungeonTerrain.STAIRS_DOWN)
    else:
        level.set_terrain(stairs_up[0], stairs_up[1], transition_terrain)
        level.set_terrain(stairs_down[0], stairs_down[1], transition_terrain)
        level.player_pos = stairs_up

    return GeneratedFloor(
        level=level,
        rooms=rooms,
        environment=env.name,
        entry_room_index=_find_room_index(rooms, stairs_up),
        exit_room_index=_find_room_index(rooms, stairs_down),
        secret_passages=secret_passages,
        placed_items=placed_items,
        entity_roster=entity_roster,
        themed_rooms=themed_rooms,
    )
