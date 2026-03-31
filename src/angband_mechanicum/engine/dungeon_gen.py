"""Procedural dungeon and room generation for the unified dungeon view.

Generates Grid instances with varied room archetypes, terrain features,
and spawn points, then also builds persistent exploration floors with live
contacts, loose items, discoveries, and transition tiles.

No LLM calls -- pure deterministic (seeded) generation.
"""

from __future__ import annotations

import random
from collections import deque
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


@dataclass(frozen=True)
class EnvironmentDebugEntry:
    """Debug-facing snapshot of preset environment generation data."""

    environment_id: str
    description: str
    feature_terrains: tuple[str, ...]
    room_types: tuple[str, ...]
    hostile_contacts: tuple[str, ...]
    friendly_contacts: tuple[str, ...]
    neutral_contacts: tuple[str, ...]
    item_names: tuple[str, ...]
    object_templates: tuple[str, ...]
    themed_rooms: tuple[str, ...]
    discovery_titles: tuple[str, ...] = ()
    variant_names: tuple[str, ...] = ()
    reactive_rule: str | None = None


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
    "swamp": ["water", "growths", "cover"],
    "forest": ["growths", "cover", "debris"],
    "mountains": ["debris", "cover"],
}

_THEME_TRANSITIONS: dict[str, DungeonTerrain] = {
    "forge": DungeonTerrain.LIFT,
    "manufactorum": DungeonTerrain.LIFT,
    "hive": DungeonTerrain.ELEVATOR,
    "cathedral": DungeonTerrain.GATE,
    "tomb": DungeonTerrain.GATE,
    "corrupted": DungeonTerrain.PORTAL,
    "swamp": DungeonTerrain.GATE,
    "forest": DungeonTerrain.GATE,
    "mountains": DungeonTerrain.GATE,
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
    placed_objects: list["PlacedEnvironmentObject"] = field(default_factory=list)
    entity_roster: DungeonEntityRoster = field(default_factory=DungeonEntityRoster)
    themed_rooms: list["ThemedRoomInstance"] = field(default_factory=list)
    placed_discoveries: list["PlacedDiscovery"] = field(default_factory=list)
    content_variant_id: str = "standard"
    content_variant_name: str = "Standard"
    floor_band: str = "descent"
    ambience_lines: tuple[str, ...] = ()
    reactive_rule: str | None = None


@dataclass(frozen=True)
class EnvironmentObjectTemplate:
    """A reusable environment dressing template."""

    object_id: str
    terrain: DungeonTerrain | None = None
    footprint: tuple[tuple[int, int], ...] = ((0, 0),)
    blocking: bool = False
    focus: str = "center"
    item_id: str | None = None


@dataclass(frozen=True)
class PlacedEnvironmentObject:
    """A concrete placed environment object on the generated floor."""

    object_id: str
    anchor: tuple[int, int]
    footprint: tuple[tuple[int, int], ...]
    blocking: bool


@dataclass(frozen=True)
class DiscoveryTemplate:
    """Ambient discovery snippet anchored to a floor position."""

    title: str
    summary: str
    environments: tuple[str, ...]
    min_depth: int = 1
    max_depth: int = 999
    weight: int = 1
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlacedDiscovery:
    """A concrete lore/scenery discovery placed on a generated floor."""

    title: str
    summary: str
    position: tuple[int, int]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FloorBandProfile:
    """Depth-sensitive profile for entry, reveal, descent, and climax floors."""

    band_id: str
    room_count_delta: int = 0
    set_piece_bonus: int = 0
    preferred_themed_room_tags: tuple[str, ...] = ()
    hostile_tags: tuple[str, ...] = ()
    friendly_tags: tuple[str, ...] = ()
    neutral_tags: tuple[str, ...] = ()
    ambience_lines: tuple[str, ...] = ()
    discovery_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnvironmentVariantProfile:
    """Environment-specific rare variant that biases content selection."""

    variant_id: str
    name: str
    weight: int = 1
    preferred_themed_room_tags: tuple[str, ...] = ()
    required_themed_room_names: tuple[str, ...] = ()
    hostile_tags: tuple[str, ...] = ()
    friendly_tags: tuple[str, ...] = ()
    neutral_tags: tuple[str, ...] = ()
    ambience_lines: tuple[str, ...] = ()
    discovery_tags: tuple[str, ...] = ()
    reactive_rule: str | None = None


@dataclass(frozen=True)
class EnvironmentContentPlan:
    """Resolved generation plan for a specific floor."""

    variant: EnvironmentVariantProfile
    floor_band: FloorBandProfile
    profile: DungeonGenerationProfile
    ambience_lines: tuple[str, ...]
    discovery_tags: tuple[str, ...]
    reactive_rule: str | None = None


@dataclass(frozen=True)
class FloorLayoutPlan:
    """Geometry plan for a generated floor before content placement."""

    rooms: tuple[DungeonRoom, ...]
    secret_passages: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = ()
    protected_feature_tiles: frozenset[tuple[int, int]] = frozenset()
    allow_doors: bool = True


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


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _room_from_center(
    center_x: int,
    center_y: int,
    width: int,
    height: int,
    *,
    level_width: int,
    level_height: int,
    room_type: str,
) -> DungeonRoom:
    x = _clamp(center_x - width // 2, 1, max(1, level_width - width - 1))
    y = _clamp(center_y - height // 2, 1, max(1, level_height - height - 1))
    return DungeonRoom(x=x, y=y, width=width, height=height, room_type=room_type)


def _carve_blob(
    level: DungeonLevel,
    center: tuple[int, int],
    radius_x: int,
    radius_y: int,
    rng: random.Random,
    *,
    terrain: DungeonTerrain = DungeonTerrain.FLOOR,
    protected: set[tuple[int, int]] | None = None,
    jitter: float = 0.18,
) -> set[tuple[int, int]]:
    carved: set[tuple[int, int]] = set()
    cx, cy = center
    for y in range(max(1, cy - radius_y - 1), min(level.height - 1, cy + radius_y + 2)):
        for x in range(max(1, cx - radius_x - 1), min(level.width - 1, cx + radius_x + 2)):
            if protected is not None and (x, y) in protected:
                continue
            dx = (x - cx) / max(1, radius_x)
            dy = (y - cy) / max(1, radius_y)
            threshold = 1.0 + rng.uniform(-jitter, jitter)
            if (dx * dx) + (dy * dy) > threshold:
                continue
            if terrain == DungeonTerrain.FLOOR:
                level.set_terrain(x, y, terrain)
                carved.add((x, y))
                continue
            _set_feature_tile(level, x, y, terrain)
            if level.get_terrain(x, y) == terrain:
                carved.add((x, y))
    return carved


def _carve_polyline(
    level: DungeonLevel,
    points: Sequence[tuple[int, int]],
    *,
    brush_radius: int,
    rng: random.Random,
) -> set[tuple[int, int]]:
    carved: set[tuple[int, int]] = set()
    if len(points) < 2:
        return carved

    for start, end in zip(points, points[1:]):
        x, y = start
        target_x, target_y = end
        carved.update(
            _carve_blob(level, (x, y), brush_radius + 1, brush_radius + 1, rng, jitter=0.08)
        )
        while (x, y) != (target_x, target_y):
            dx = target_x - x
            dy = target_y - y
            if dx and dy:
                if abs(dx) > abs(dy):
                    x += 1 if dx > 0 else -1
                    if rng.random() < 0.35:
                        y += 1 if dy > 0 else -1
                else:
                    y += 1 if dy > 0 else -1
                    if rng.random() < 0.35:
                        x += 1 if dx > 0 else -1
            elif dx:
                x += 1 if dx > 0 else -1
                if brush_radius >= 2 and rng.random() < 0.2:
                    y = _clamp(y + rng.choice((-1, 1)), 1, level.height - 2)
            elif dy:
                y += 1 if dy > 0 else -1
            carved.update(
                _carve_blob(level, (x, y), brush_radius + 1, brush_radius + 1, rng, jitter=0.08)
            )
    return carved


def _build_outdoor_room_on_level(
    level: DungeonLevel,
    room: DungeonRoom,
    rng: random.Random,
) -> None:
    center = room.center
    radius_x = max(3, room.width // 2)
    radius_y = max(3, room.height // 2)
    _carve_blob(level, center, radius_x, radius_y, rng)

    if room.room_type in {"l_shaped", "cross_room", "pillared_hall"}:
        horizontal_offset = max(2, room.width // 4)
        vertical_offset = max(2, room.height // 4)
        if room.room_type == "l_shaped":
            extra_center = (center[0] + horizontal_offset, center[1] - vertical_offset)
            _carve_blob(level, extra_center, max(2, radius_x - 2), max(2, radius_y - 1), rng)
        else:
            _carve_blob(level, (center[0] - horizontal_offset, center[1]), max(2, radius_x - 2), max(2, radius_y - 1), rng)
            _carve_blob(level, (center[0] + horizontal_offset, center[1]), max(2, radius_x - 2), max(2, radius_y - 1), rng)
            if room.room_type == "cross_room":
                _carve_blob(level, (center[0], center[1] - vertical_offset), max(2, radius_x - 2), max(2, radius_y - 1), rng)
                _carve_blob(level, (center[0], center[1] + vertical_offset), max(2, radius_x - 2), max(2, radius_y - 1), rng)


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
    "swamp": ("reed-kit", "filter-pack", "bog-map", "anti-toxin"),
    "forest": ("field-rations", "waystone-charm", "survival-knife", "water-flask"),
    "mountains": ("piton-bundle", "cliff-map", "cold-weather-pack", "signal-flare"),
    "default": ("supply-crate", "cogitator-slate", "field-kit"),
}

_FLOOR_BANDS: tuple[FloorBandProfile, ...] = (
    FloorBandProfile(
        band_id="entry",
        room_count_delta=-1,
        preferred_themed_room_tags=("entry", "survey", "checkpoint", "watchpost"),
        friendly_tags=("crew", "survivor", "attendant", "custodian", "guide"),
        neutral_tags=("clerk", "scribe", "broker", "surveyor"),
        ambience_lines=(
            "Entry strata still carry signs of recent passage and half-secured thresholds.",
            "The machine spirit feels watchful here, as though the first rooms were prepared for witnesses.",
        ),
        discovery_tags=("entry", "warning", "cache"),
    ),
    FloorBandProfile(
        band_id="reveal",
        room_count_delta=1,
        set_piece_bonus=1,
        preferred_themed_room_tags=("vault", "reliquary", "breach", "ritual", "market"),
        hostile_tags=("intruder", "cult", "warden", "gang", "scavenger"),
        neutral_tags=("scribe", "broker", "guide", "surveyor"),
        ambience_lines=(
            "Mid-depth routes peel back enough of the environ's agenda to reveal who really owns the place.",
            "The floor plan opens into spaces built for transactions, rites, or organized predation.",
        ),
        discovery_tags=("lore", "ritual", "stash"),
    ),
    FloorBandProfile(
        band_id="descent",
        room_count_delta=0,
        preferred_themed_room_tags=("machine_cult", "underhive", "wastes", "forge", "necron"),
        hostile_tags=("predator", "raider", "mutant", "guardian"),
        ambience_lines=(
            "The deeper route settles into a hostile routine of scavengers, patrols, and half-ruined infrastructure.",
        ),
        discovery_tags=("remains", "machinery"),
    ),
    FloorBandProfile(
        band_id="climax",
        room_count_delta=-1,
        set_piece_bonus=1,
        preferred_themed_room_tags=("titan", "reactor", "warp", "vault", "command", "breach"),
        hostile_tags=("guardian", "daemon", "ork", "reactor", "boarding", "sentinel"),
        ambience_lines=(
            "This depth compresses toward a defended heart-space where the environ's strongest idea is forced on the player.",
            "Routes narrow and converge around a chamber that feels deliberate rather than incidental.",
        ),
        discovery_tags=("climax", "command", "relic"),
    ),
)

_STANDARD_VARIANT = EnvironmentVariantProfile(
    variant_id="standard",
    name="Standard Profile",
    weight=0,
)

_ENVIRONMENT_VARIANTS: dict[str, tuple[EnvironmentVariantProfile, ...]] = {
    "forge": (
        EnvironmentVariantProfile(
            variant_id="smelter_lockdown",
            name="Smelter Lockdown",
            weight=1,
            preferred_themed_room_tags=("forge", "reactor", "machine_cult"),
            hostile_tags=("reactor", "heretek", "forge"),
            friendly_tags=("engineer", "adept"),
            ambience_lines=(
                "Blast shutters and emergency rites have turned the forge into a corridor of sealed heat-traps.",
            ),
            discovery_tags=("reactor", "warning", "machinery"),
            reactive_rule="Noise or prolonged fighting can draw additional forge-servitors from maintenance shafts.",
        ),
    ),
    "manufactorum": (
        EnvironmentVariantProfile(
            variant_id="union_strike",
            name="Union Strike",
            weight=1,
            preferred_themed_room_tags=("assembly", "freight", "machine_cult"),
            hostile_tags=("saboteur", "cult", "machine"),
            neutral_tags=("clerk", "broker", "overseer"),
            ambience_lines=(
                "Production lines stand half-abandoned, with sabotage scars and barricaded tool cages between stations.",
            ),
            discovery_tags=("stash", "machinery", "warning"),
            reactive_rule="Once an alarmed line is entered, adjacent halls can wake dormant labor units.",
        ),
    ),
    "voidship": (
        EnvironmentVariantProfile(
            variant_id="silent_bulkhead_breach",
            name="Silent Bulkhead Breach",
            weight=1,
            preferred_themed_room_tags=("breach", "boarding", "command"),
            hostile_tags=("boarding", "intruder", "mutiny"),
            friendly_tags=("crew", "pilot"),
            ambience_lines=(
                "Vacuum-sealed decks alternate with improvised breach barricades and blood-slick companionways.",
            ),
            discovery_tags=("breach", "command", "cache"),
            reactive_rule="Unsealed bulkheads can convert nearby quiet rooms into active boarding fronts.",
        ),
    ),
    "cathedral": (
        EnvironmentVariantProfile(
            variant_id="pilgrim_purge",
            name="Pilgrim Purge",
            weight=1,
            preferred_themed_room_tags=("chapel", "ritual", "reliquary"),
            hostile_tags=("faith", "penitent", "heretic"),
            friendly_tags=("custodian", "faith"),
            neutral_tags=("attendant", "scribe"),
            ambience_lines=(
                "Improvised confession lines and hurried purgation rites have overtaken the nave-side chambers.",
            ),
            discovery_tags=("ritual", "warning", "relic"),
            reactive_rule="Disturbed shrines can turn nearby penitents from passive observers into zealots.",
        ),
    ),
    "reliquary": (
        EnvironmentVariantProfile(
            variant_id="sealed_translation",
            name="Sealed Translation Vault",
            weight=1,
            preferred_themed_room_tags=("vault", "reliquary", "archive"),
            friendly_tags=("custodian", "guardian"),
            neutral_tags=("scribe", "attendant"),
            ambience_lines=(
                "Transit locks stand open around chambers prepared for the movement of saint-bones and forbidden texts.",
            ),
            discovery_tags=("relic", "archive", "warning"),
            reactive_rule="Breaking the silence around caskets can propagate a warding response along the vault chain.",
        ),
    ),
    "hive": (
        EnvironmentVariantProfile(
            variant_id="gang_territory_war",
            name="Gang Territory War",
            weight=1,
            preferred_themed_room_tags=("underhive", "gang", "stash"),
            hostile_tags=("gang", "criminal", "riot"),
            neutral_tags=("broker", "warden", "scout"),
            ambience_lines=(
                "Fresh gang marks, looted hab-stacks, and lookout fires turn the hive into overlapping kill-boxes.",
            ),
            discovery_tags=("stash", "warning", "remains"),
            reactive_rule="Visible combat can escalate into roaming reinforcements from adjacent claim rooms.",
        ),
    ),
    "sewer": (
        EnvironmentVariantProfile(
            variant_id="overflow_blackwater",
            name="Overflow Blackwater",
            weight=1,
            preferred_themed_room_tags=("sump", "underhive", "filtration"),
            hostile_tags=("rat", "mutant", "sewer"),
            neutral_tags=("broker", "guide"),
            ambience_lines=(
                "Flood surges have redistributed corpses, contraband, and vermin nests through the drainage lattice.",
            ),
            discovery_tags=("warning", "remains", "cache"),
            reactive_rule="Crossing contaminated channels can stir hidden vermin clusters into pursuit.",
        ),
    ),
    "corrupted": (
        EnvironmentVariantProfile(
            variant_id="daemon_bloom",
            name="Daemon Bloom",
            weight=1,
            preferred_themed_room_tags=("warp", "ritual", "chapel"),
            hostile_tags=("warp", "daemon", "cult"),
            neutral_tags=("victim", "remnant"),
            ambience_lines=(
                "The corruption here behaves like a spreading ecosystem, knotting chambers together with fresh growth.",
            ),
            discovery_tags=("ritual", "warning", "climax"),
            reactive_rule="Activated shrines or warp scars can spread contamination into neighboring rooms.",
        ),
    ),
    "overgrown": (
        EnvironmentVariantProfile(
            variant_id="reclaimed_greenhouse",
            name="Reclaimed Greenhouse",
            weight=1,
            preferred_themed_room_tags=("growth", "reclaimed", "garden"),
            hostile_tags=("growth", "predator"),
            friendly_tags=("survivor", "guide"),
            ambience_lines=(
                "Ancient irrigation systems have revived whole chambers into fungal gardens and root-choked sanctuaries.",
            ),
            discovery_tags=("garden", "cache", "lore"),
            reactive_rule="Cut through enough overgrowth and nearby nests can wake as a coordinated defense.",
        ),
    ),
    "tomb": (
        EnvironmentVariantProfile(
            variant_id="funerary_wake",
            name="Funerary Wake",
            weight=1,
            preferred_themed_room_tags=("tomb", "reliquary", "guardian"),
            hostile_tags=("guardian", "tomb", "bone"),
            neutral_tags=("scribe", "guardian"),
            ambience_lines=(
                "A chain of opened sarcophagi and ward-lit side chambers suggests the dead were only recently disturbed.",
            ),
            discovery_tags=("relic", "warning", "remains"),
            reactive_rule="Disturbing burial clusters can wake dormant sentinels on the same floor.",
        ),
    ),
    "radwastes": (
        EnvironmentVariantProfile(
            variant_id="scrap_storm_front",
            name="Scrap Storm Front",
            weight=1,
            preferred_themed_room_tags=("wastes", "wreck", "titan"),
            hostile_tags=("scavenger", "marauder", "ork"),
            neutral_tags=("trader", "surveyor", "guide"),
            ambience_lines=(
                "Shifting scrap drifts and rad-burned wreckage have remade the outskirts into a moving salvage front.",
            ),
            discovery_tags=("wreck", "warning", "cache"),
            reactive_rule="Gunfire or beacon use can pull scavenger packs toward the strongest signal source.",
        ),
    ),
    "data_vault": (
        EnvironmentVariantProfile(
            variant_id="archive_purge",
            name="Archive Purge",
            weight=1,
            preferred_themed_room_tags=("vault", "archive", "cipher"),
            hostile_tags=("vault", "saboteur", "warden"),
            friendly_tags=("adept", "guardian"),
            neutral_tags=("scribe", "clerk"),
            ambience_lines=(
                "Index halls are marked for emergency deletion, with sealed stacks and half-purged logic shrines.",
            ),
            discovery_tags=("archive", "warning", "relic"),
            reactive_rule="Accessing sealed stacks can awaken deeper counter-intrusion patrols.",
        ),
    ),
    "xenos_ruin": (
        EnvironmentVariantProfile(
            variant_id="phase_shifted_sanctum",
            name="Phase-Shifted Sanctum",
            weight=1,
            preferred_themed_room_tags=("xenos", "glyph", "sanctum"),
            hostile_tags=("xenos", "sentinel", "predator"),
            neutral_tags=("observer", "guide"),
            ambience_lines=(
                "Some chambers no longer seem to agree on geometry, forcing the route through unstable alien nodes.",
            ),
            discovery_tags=("glyph", "lore", "climax"),
            reactive_rule="Crossing activated glyph nodes can reorient nearby patrols and access lanes.",
        ),
    ),
    "ice_crypt": (
        EnvironmentVariantProfile(
            variant_id="thawing_crypt",
            name="Thawing Crypt",
            weight=1,
            preferred_themed_room_tags=("ice", "cryo", "tomb"),
            hostile_tags=("guardian", "frozen"),
            neutral_tags=("scribe", "attendant"),
            ambience_lines=(
                "Cracked cryo-seals and meltwater channels expose chambers that were meant to stay frozen forever.",
            ),
            discovery_tags=("warning", "relic", "remains"),
            reactive_rule="Breaking cryo seals can wake preserved guardians in nearby burial aisles.",
        ),
    ),
    "sump_market": (
        EnvironmentVariantProfile(
            variant_id="contraband_auction",
            name="Contraband Auction",
            weight=1,
            preferred_themed_room_tags=("market", "underhive", "stash"),
            hostile_tags=("criminal", "broker", "gang"),
            neutral_tags=("broker", "guide", "trader"),
            ambience_lines=(
                "Stalls have condensed into defended auction rings where information and salvage change hands fast.",
            ),
            discovery_tags=("stash", "cache", "lore"),
            reactive_rule="Violence near stalls can flip neutral traders into runners who alert nearby gangs.",
        ),
    ),
    "plasma_reactorum": (
        EnvironmentVariantProfile(
            variant_id="meltdown_containment",
            name="Meltdown Containment",
            weight=1,
            preferred_themed_room_tags=("reactor", "machine_cult", "containment"),
            hostile_tags=("reactor", "cult", "warden"),
            friendly_tags=("engineer", "tech"),
            ambience_lines=(
                "Containment shutters and scorched maintenance galleries have turned the reactorum into a deliberate gauntlet.",
            ),
            discovery_tags=("reactor", "warning", "machinery"),
            reactive_rule="Disrupting control banks can open hotter routes and invite reinforced reactor guardians.",
        ),
    ),
    "penal_oubliette": (
        EnvironmentVariantProfile(
            variant_id="riot_transfer",
            name="Riot Transfer",
            weight=1,
            preferred_themed_room_tags=("penal", "execution", "cellblock"),
            hostile_tags=("convict", "warden", "riot"),
            neutral_tags=("confessor", "witness"),
            ambience_lines=(
                "Cells stand open and transfer chains hang loose, leaving the oubliette between riot and purge.",
            ),
            discovery_tags=("warning", "remains", "stash"),
            reactive_rule="Once one cell block is disturbed, neighboring wings can spill convicts into the route.",
        ),
    ),
    "ash_dune_outpost": (
        EnvironmentVariantProfile(
            variant_id="dust_siege",
            name="Dust Siege",
            weight=1,
            preferred_themed_room_tags=("wreck", "titan", "watchpost"),
            hostile_tags=("ork", "loota", "scavenger"),
            neutral_tags=("survivor", "surveyor", "reclaimator"),
            ambience_lines=(
                "Signal masts and sandbag nests have been reoriented for a prolonged siege under ash-choked skies.",
            ),
            discovery_tags=("wreck", "warning", "command"),
            reactive_rule="Beacon activation can draw rival scavengers or defenders toward the same redoubt.",
        ),
    ),
    "swamp": (
        EnvironmentVariantProfile(
            variant_id="sump_tide_uprising",
            name="Sump Tide Uprising",
            weight=1,
            preferred_themed_room_tags=("marsh", "sump", "shrine"),
            hostile_tags=("mutant", "bog", "predator"),
            neutral_tags=("guide", "survivor"),
            ambience_lines=(
                "The blackwater has crept across old causeways, leaving only reed-choked islands and desperate camps.",
            ),
            discovery_tags=("warning", "remains", "cache"),
            reactive_rule="Crossing fresh blackwater can disturb nearby predators and flush them toward the driest route.",
        ),
    ),
    "forest": (
        EnvironmentVariantProfile(
            variant_id="machine_hunt_canopy",
            name="Machine Hunt Canopy",
            weight=1,
            preferred_themed_room_tags=("glade", "waystone", "hunt"),
            hostile_tags=("stalker", "predator", "forest"),
            friendly_tags=("scout", "survivor"),
            ambience_lines=(
                "The tree line watches back, with fresh kill-sign and machine prayers tied to trunks around the glades.",
            ),
            discovery_tags=("lore", "warning", "garden"),
            reactive_rule="Violence in one glade can send hunters ghosting through adjacent cover belts.",
        ),
    ),
    "mountains": (
        EnvironmentVariantProfile(
            variant_id="avalanche_watch",
            name="Avalanche Watch",
            weight=1,
            preferred_themed_room_tags=("pass", "watchpost", "shrine"),
            hostile_tags=("raider", "guardian", "mountain"),
            neutral_tags=("surveyor", "guide"),
            ambience_lines=(
                "Fresh rockfall and warning braziers have turned every shelf into a guarded approach to the high pass.",
            ),
            discovery_tags=("warning", "command", "relic"),
            reactive_rule="Disturbing loose scree on one shelf can alert lookouts or collapse a neighboring approach.",
        ),
    ),
}

_DISCOVERY_TEMPLATES: dict[str, tuple[DiscoveryTemplate, ...]] = {
    "default": (
        DiscoveryTemplate(
            title="Warning Sigils",
            summary="Fresh caution marks and coded warnings show that someone still expects traffic through these halls.",
            environments=tuple(ENVIRONMENTS.keys()),
            weight=3,
            tags=("warning", "entry"),
        ),
        DiscoveryTemplate(
            title="Survivor Cache",
            summary="A hidden cache of ration tins, spent cells, and hurried notes suggests recent desperation.",
            environments=tuple(ENVIRONMENTS.keys()),
            weight=2,
            tags=("cache", "stash"),
        ),
        DiscoveryTemplate(
            title="Corpse Tableau",
            summary="The dead have been left in a configuration that reads like a message, ritual, or warning.",
            environments=tuple(ENVIRONMENTS.keys()),
            weight=2,
            tags=("remains", "warning"),
        ),
    ),
    "forge": (
        DiscoveryTemplate(
            title="Machine Debris",
            summary="Sheared cog-teeth and sanctified wiring lie where a machine spirit was stripped for parts.",
            environments=("forge", "manufactorum", "plasma_reactorum"),
            tags=("machinery", "warning"),
        ),
    ),
    "cathedral": (
        DiscoveryTemplate(
            title="Pilgrim Petition Wall",
            summary="Wax-sealed petitions and blood-marked vows cover the wall in overlapping layers of devotion and fear.",
            environments=("cathedral", "reliquary"),
            tags=("lore", "ritual"),
        ),
    ),
    "hive": (
        DiscoveryTemplate(
            title="Claim Marker Shrine",
            summary="Scrap icons, gang glyphs, and spent casings mark an improvised shrine to local ownership.",
            environments=("hive", "sump_market", "penal_oubliette"),
            tags=("stash", "warning"),
        ),
    ),
    "sewer": (
        DiscoveryTemplate(
            title="Blackwater Shrine",
            summary="Oil lamps and floating bones drift around a sump-side devotional marker.",
            environments=("sewer", "sump_market"),
            tags=("ritual", "warning"),
        ),
    ),
    "corrupted": (
        DiscoveryTemplate(
            title="Warp Scar",
            summary="Reality here has puckered around a wound of heat, static, and whispered machine-cant.",
            environments=("corrupted",),
            tags=("ritual", "climax"),
        ),
    ),
    "overgrown": (
        DiscoveryTemplate(
            title="Seed Vault",
            summary="A moss-swallowed locker still protects seed tubes and patient notes from a forgotten caretaker.",
            environments=("overgrown",),
            tags=("garden", "cache"),
        ),
    ),
    "tomb": (
        DiscoveryTemplate(
            title="Funerary Register",
            summary="Ceremonial inventory strips list the dead, their watch-rotations, and the seals that failed them.",
            environments=("tomb", "ice_crypt"),
            tags=("relic", "lore"),
        ),
    ),
    "radwastes": (
        DiscoveryTemplate(
            title="Survey Beacon Ring",
            summary="A circle of burnt-out beacons marks where salvage crews once measured the edge of a kill-zone.",
            environments=("radwastes", "ash_dune_outpost"),
            tags=("wreck", "command"),
        ),
    ),
    "swamp": (
        DiscoveryTemplate(
            title="Reedbound Effigy",
            summary="An idol of reeds, bone, and brass wire marks a path someone feared would vanish with the tide.",
            environments=("swamp",),
            tags=("ritual", "warning"),
        ),
    ),
    "forest": (
        DiscoveryTemplate(
            title="Waystone Clearing",
            summary="A mossed standing stone and a ring of bootprints show that this glade still guides travellers.",
            environments=("forest",),
            tags=("lore", "garden"),
        ),
    ),
    "mountains": (
        DiscoveryTemplate(
            title="Prayer Cairn",
            summary="Stacked stones, wax drippings, and wind-torn purity seals mark the last safe halt before the climb.",
            environments=("mountains",),
            tags=("warning", "relic"),
        ),
    ),
    "data_vault": (
        DiscoveryTemplate(
            title="Purge Ledger",
            summary="A torn ledger records entire stacks scheduled for deletion, quarantine, or private removal.",
            environments=("data_vault",),
            tags=("archive", "warning"),
        ),
    ),
    "xenos_ruin": (
        DiscoveryTemplate(
            title="Glyph Constellation",
            summary="Alien sigils repeat across broken angles, as if the ruin is trying to remember its own sky.",
            environments=("xenos_ruin",),
            tags=("glyph", "lore"),
        ),
    ),
}


def _dedupe_tuple(*parts: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for value in part:
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            values.append(value)
    return tuple(values)


def _select_floor_band(depth: int) -> FloorBandProfile:
    if depth <= 1:
        return _FLOOR_BANDS[0]
    if depth % 5 == 0:
        return _FLOOR_BANDS[3]
    if depth % 3 == 0:
        return _FLOOR_BANDS[1]
    return _FLOOR_BANDS[2]


def _select_environment_variant(
    environment: str,
    rng: random.Random,
) -> EnvironmentVariantProfile:
    variants = _ENVIRONMENT_VARIANTS.get(environment, ())
    if not variants:
        return _STANDARD_VARIANT
    total_weight = 12 + sum(max(1, variant.weight) for variant in variants)
    roll = rng.randint(1, total_weight)
    if roll <= 12:
        return _STANDARD_VARIANT
    roll -= 12
    for variant in variants:
        roll -= max(1, variant.weight)
        if roll <= 0:
            return variant
    return variants[-1]


def _merge_generation_profile(
    environment: str,
    base_profile: DungeonGenerationProfile | None,
    variant: EnvironmentVariantProfile,
    floor_band: FloorBandProfile,
) -> DungeonGenerationProfile:
    profile = base_profile or DungeonGenerationProfile(environment=environment)
    return DungeonGenerationProfile(
        environment=profile.environment,
        profile_id=profile.profile_id,
        location_name=profile.location_name,
        hostile_tags=_dedupe_tuple(profile.hostile_tags, variant.hostile_tags, floor_band.hostile_tags),
        friendly_tags=_dedupe_tuple(profile.friendly_tags, variant.friendly_tags, floor_band.friendly_tags),
        neutral_tags=_dedupe_tuple(profile.neutral_tags, variant.neutral_tags, floor_band.neutral_tags),
        preferred_themed_room_tags=_dedupe_tuple(
            profile.preferred_themed_room_tags,
            variant.preferred_themed_room_tags,
            floor_band.preferred_themed_room_tags,
        ),
        required_themed_room_names=_dedupe_tuple(
            profile.required_themed_room_names,
            variant.required_themed_room_names,
        ),
        excluded_contact_tags=profile.excluded_contact_tags,
        excluded_contact_names=profile.excluded_contact_names,
        excluded_themed_room_names=profile.excluded_themed_room_names,
        excluded_themed_room_tags=profile.excluded_themed_room_tags,
    )


def _resolve_environment_content_plan(
    environment: str,
    depth: int,
    rng: random.Random,
    profile: DungeonGenerationProfile | None,
) -> EnvironmentContentPlan:
    floor_band = _select_floor_band(depth)
    variant = _select_environment_variant(environment, rng)
    merged_profile = _merge_generation_profile(environment, profile, variant, floor_band)
    ambience_lines = _dedupe_tuple(floor_band.ambience_lines, variant.ambience_lines)
    discovery_tags = _dedupe_tuple(floor_band.discovery_tags, variant.discovery_tags)
    return EnvironmentContentPlan(
        variant=variant,
        floor_band=floor_band,
        profile=merged_profile,
        ambience_lines=ambience_lines,
        discovery_tags=discovery_tags,
        reactive_rule=variant.reactive_rule,
    )


def _discovery_templates_for_environment(environment: str) -> tuple[DiscoveryTemplate, ...]:
    return _DISCOVERY_TEMPLATES.get(environment, ()) + _DISCOVERY_TEMPLATES["default"]

_LINE_2 = ((0, 0), (1, 0))
_LINE_3 = ((0, 0), (1, 0), (2, 0))
_BLOCK_2 = ((0, 0), (1, 0), (0, 1), (1, 1))
_L_SHAPE = ((0, 0), (1, 0), (0, 1))
_PILLAR_RING = ((0, 0), (1, 0), (0, 1), (1, 1), (2, 1))

_DEFAULT_ENVIRONMENT_OBJECTS: tuple[EnvironmentObjectTemplate, ...] = (
    EnvironmentObjectTemplate("supply-crate-cluster", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
    EnvironmentObjectTemplate("collapsed-column", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="edge"),
    EnvironmentObjectTemplate("machine-bank", DungeonTerrain.TERMINAL, _LINE_2, focus="edge"),
    EnvironmentObjectTemplate("rubble-drift", DungeonTerrain.RUBBLE, _LINE_3, focus="corner"),
    EnvironmentObjectTemplate("maintenance-grate", DungeonTerrain.GRATE, _LINE_2, focus="center"),
)

_ENVIRONMENT_OBJECTS: dict[str, tuple[EnvironmentObjectTemplate, ...]] = {
    "forge": (
        EnvironmentObjectTemplate("cogitator-bank", DungeonTerrain.TERMINAL, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("smelter-cradle", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("slag-baffles", DungeonTerrain.COVER, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("anchored-press", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("tool-rack", DungeonTerrain.TERMINAL, _LINE_2, focus="edge"),
    ),
    "manufactorum": (
        EnvironmentObjectTemplate("assembly-line", DungeonTerrain.GRATE, _LINE_3, focus="center"),
        EnvironmentObjectTemplate("servo-arm-nest", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("control-pit", DungeonTerrain.TERMINAL, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("freight-pallets", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("machine-spindle", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="center"),
    ),
    "voidship": (
        EnvironmentObjectTemplate("bulkhead-console", DungeonTerrain.TERMINAL, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("breach-barrier", DungeonTerrain.COVER, _LINE_3, focus="center"),
        EnvironmentObjectTemplate("hull-fragment", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="corner"),
        EnvironmentObjectTemplate("stasis-cradle", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("reactor-plinth", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="edge"),
    ),
    "cathedral": (
        EnvironmentObjectTemplate("choir-stalls", DungeonTerrain.COVER, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("shrine-clutter", DungeonTerrain.SHRINE, _BLOCK_2, focus="center"),
        EnvironmentObjectTemplate("broken-statue", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="corner"),
        EnvironmentObjectTemplate("votive-line", DungeonTerrain.SHRINE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("censer-rack", DungeonTerrain.COVER, _LINE_2, focus="edge"),
    ),
    "reliquary": (
        EnvironmentObjectTemplate("saint-casket", DungeonTerrain.SHRINE, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("seal-plinths", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("votive-alcove", DungeonTerrain.SHRINE, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("archive-bank", DungeonTerrain.TERMINAL, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("reliquary-cradle", DungeonTerrain.COVER, _L_SHAPE, focus="center"),
    ),
    "hive": (
        EnvironmentObjectTemplate("scrap-barricade", DungeonTerrain.COVER, _LINE_3, focus="center"),
        EnvironmentObjectTemplate("hab-shrine", DungeonTerrain.SHRINE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("junk-pile", DungeonTerrain.RUBBLE, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("collapsed-walkway", DungeonTerrain.GRATE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("stacked-lockers", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="edge"),
    ),
    "sewer": (
        EnvironmentObjectTemplate("pipe-cluster", DungeonTerrain.GRATE, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("corrosion-pit", DungeonTerrain.ACID_POOL, _BLOCK_2, focus="center"),
        EnvironmentObjectTemplate("service-bridge", DungeonTerrain.GRATE, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("filtration-rack", DungeonTerrain.COVER, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("collapsed-drain", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="corner"),
    ),
    "corrupted": (
        EnvironmentObjectTemplate("warp-growth", DungeonTerrain.GROWTH, _BLOCK_2, focus="center"),
        EnvironmentObjectTemplate("rift-scar", DungeonTerrain.CHASM, _LINE_3, focus="center"),
        EnvironmentObjectTemplate("blasphemous-altar", DungeonTerrain.SHRINE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("fused-bones", DungeonTerrain.RUBBLE, _LINE_2, focus="corner"),
        EnvironmentObjectTemplate("daemon-pillar", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="center"),
    ),
    "overgrown": (
        EnvironmentObjectTemplate("fungal-bloom", DungeonTerrain.GROWTH, _BLOCK_2, focus="center"),
        EnvironmentObjectTemplate("vine-choked-arch", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("reed-patch", DungeonTerrain.WATER, _LINE_2, focus="corner"),
        EnvironmentObjectTemplate("fallen-monolith", DungeonTerrain.RUBBLE, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("root-tangle", DungeonTerrain.GROWTH, _L_SHAPE, focus="corner"),
    ),
    "tomb": (
        EnvironmentObjectTemplate("sarcophagus-row", DungeonTerrain.SHRINE, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("canopic-cluster", DungeonTerrain.SHRINE, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("fallen-obelisk", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="center"),
        EnvironmentObjectTemplate("burial-rubble", DungeonTerrain.RUBBLE, _LINE_2, focus="corner"),
        EnvironmentObjectTemplate("warding-pillars", DungeonTerrain.COLUMN, _PILLAR_RING, blocking=True, focus="center"),
    ),
    "radwastes": (
        EnvironmentObjectTemplate("rock-formation", DungeonTerrain.COLUMN, _BLOCK_2, blocking=True, focus="corner"),
        EnvironmentObjectTemplate("wreckage-spine", DungeonTerrain.RUBBLE, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("acid-runoff", DungeonTerrain.ACID_POOL, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("titan-debris", DungeonTerrain.COLUMN, _PILLAR_RING, blocking=True, focus="corner"),
        EnvironmentObjectTemplate("survey-shelter", DungeonTerrain.COVER, _BLOCK_2, focus="edge"),
    ),
    "data_vault": (
        EnvironmentObjectTemplate("archive-stack", DungeonTerrain.TERMINAL, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("logic-pillar", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="center"),
        EnvironmentObjectTemplate("cache-rack", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("sealed-terminal", DungeonTerrain.TERMINAL, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("cipher-dais", DungeonTerrain.SHRINE, _LINE_2, focus="edge"),
    ),
    "xenos_ruin": (
        EnvironmentObjectTemplate("alien-monolith", DungeonTerrain.COLUMN, _LINE_3, blocking=True, focus="center"),
        EnvironmentObjectTemplate("glyph-platform", DungeonTerrain.SHRINE, _BLOCK_2, focus="center"),
        EnvironmentObjectTemplate("fractured-geometry", DungeonTerrain.CHASM, _LINE_2, focus="corner"),
        EnvironmentObjectTemplate("spore-cluster", DungeonTerrain.GROWTH, _L_SHAPE, focus="corner"),
        EnvironmentObjectTemplate("collapsed-arch", DungeonTerrain.RUBBLE, _LINE_2, focus="edge"),
    ),
    "ice_crypt": (
        EnvironmentObjectTemplate("frozen-sarcophagus", DungeonTerrain.SHRINE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("ice-spires", DungeonTerrain.COLUMN, _L_SHAPE, blocking=True, focus="corner"),
        EnvironmentObjectTemplate("cryo-pool", DungeonTerrain.WATER, _BLOCK_2, focus="center"),
        EnvironmentObjectTemplate("shattered-coffin", DungeonTerrain.RUBBLE, _LINE_2, focus="corner"),
        EnvironmentObjectTemplate("ward-pylons", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="center"),
    ),
    "sump_market": (
        EnvironmentObjectTemplate("crooked-stalls", DungeonTerrain.COVER, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("blackwater-trench", DungeonTerrain.WATER, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("crate-heaps", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("collapsed-awning", DungeonTerrain.GRATE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("trader-shrine", DungeonTerrain.SHRINE, _LINE_2, focus="center"),
    ),
    "plasma_reactorum": (
        EnvironmentObjectTemplate("plasma-coils", DungeonTerrain.LAVA, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("shielding-gantry", DungeonTerrain.COLUMN, _LINE_3, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("control-bank", DungeonTerrain.TERMINAL, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("coolant-baffles", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("reactor-breach", DungeonTerrain.LAVA, _BLOCK_2, focus="center"),
    ),
    "penal_oubliette": (
        EnvironmentObjectTemplate("chain-rack", DungeonTerrain.GRATE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("execution-dais", DungeonTerrain.SHRINE, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("cell-block", DungeonTerrain.COLUMN, _LINE_3, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("confession-booth", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("bone-pile", DungeonTerrain.RUBBLE, _L_SHAPE, focus="corner"),
    ),
    "ash_dune_outpost": (
        EnvironmentObjectTemplate("signal-mast", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("sandbag-redoubt", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("crashed-skiff", DungeonTerrain.COLUMN, _LINE_3, blocking=True, focus="center"),
        EnvironmentObjectTemplate("field-beacon", DungeonTerrain.TERMINAL, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("dust-wreckage", DungeonTerrain.RUBBLE, _LINE_2, focus="corner"),
    ),
    "swamp": (
        EnvironmentObjectTemplate("reed-blind", DungeonTerrain.GROWTH, _LINE_3, focus="edge"),
        EnvironmentObjectTemplate("sunken-jetty", DungeonTerrain.WATER, _LINE_2, focus="center"),
        EnvironmentObjectTemplate("bog-hut", DungeonTerrain.COVER, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("rotted-pylon", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="edge"),
        EnvironmentObjectTemplate("sump-idol", DungeonTerrain.SHRINE, _LINE_2, focus="center"),
    ),
    "forest": (
        EnvironmentObjectTemplate("thorn-thicket", DungeonTerrain.GROWTH, _BLOCK_2, focus="corner"),
        EnvironmentObjectTemplate("hunter-hide", DungeonTerrain.COVER, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("fallen-waystone", DungeonTerrain.RUBBLE, _LINE_3, focus="center"),
        EnvironmentObjectTemplate("standing-stones", DungeonTerrain.COLUMN, _LINE_2, blocking=True, focus="center"),
        EnvironmentObjectTemplate("glade-shrine", DungeonTerrain.SHRINE, _LINE_2, focus="edge"),
    ),
    "mountains": (
        EnvironmentObjectTemplate("prayer-cairn", DungeonTerrain.SHRINE, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("rock-spur", DungeonTerrain.COLUMN, _BLOCK_2, blocking=True, focus="corner"),
        EnvironmentObjectTemplate("scree-field", DungeonTerrain.RUBBLE, _LINE_3, focus="center"),
        EnvironmentObjectTemplate("windbreak", DungeonTerrain.COVER, _LINE_2, focus="edge"),
        EnvironmentObjectTemplate("broken-span", DungeonTerrain.CHASM, _LINE_2, focus="center"),
    ),
    "default": _DEFAULT_ENVIRONMENT_OBJECTS,
}


def _environment_object_templates(environment: str) -> tuple[EnvironmentObjectTemplate, ...]:
    return _ENVIRONMENT_OBJECTS.get(environment, _ENVIRONMENT_OBJECTS["default"])


def _object_footprint_positions(
    anchor: tuple[int, int],
    template: EnvironmentObjectTemplate,
) -> tuple[tuple[int, int], ...]:
    ax, ay = anchor
    return tuple((ax + dx, ay + dy) for dx, dy in template.footprint)


def _reachable_floor_tiles(
    level: DungeonLevel,
    start: tuple[int, int],
) -> set[tuple[int, int]]:
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


def _anchor_positions_for_template(
    level: DungeonLevel,
    room: DungeonRoom,
    template: EnvironmentObjectTemplate,
    occupied: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    max_dx = max(dx for dx, _ in template.footprint)
    max_dy = max(dy for _, dy in template.footprint)
    for y in range(room.y + 1, room.y + room.height - 1 - max_dy):
        for x in range(room.x + 1, room.x + room.width - 1 - max_dx):
            footprint = _object_footprint_positions((x, y), template)
            if any(pos in occupied for pos in footprint):
                continue
            if any(not room.contains(px, py) for px, py in footprint):
                continue
            if any(not level.in_bounds(px, py) or not level.get_tile(px, py).passable for px, py in footprint):
                continue
            candidates.append((x, y))

    def focus_key(anchor: tuple[int, int]) -> tuple[float, float]:
        ax, ay = anchor
        center_x = ax + sum(dx for dx, _ in template.footprint) / len(template.footprint)
        center_y = ay + sum(dy for _, dy in template.footprint) / len(template.footprint)
        room_distance = abs(center_x - room.center[0]) + abs(center_y - room.center[1])
        edge_distance = min(
            abs(center_x - room.x),
            abs(center_x - (room.x + room.width - 1)),
            abs(center_y - room.y),
            abs(center_y - (room.y + room.height - 1)),
        )
        if template.focus == "edge":
            return (edge_distance, room_distance)
        if template.focus == "corner":
            corners = (
                (room.x + 1, room.y + 1),
                (room.x + room.width - 2, room.y + 1),
                (room.x + 1, room.y + room.height - 2),
                (room.x + room.width - 2, room.y + room.height - 2),
            )
            corner_distance = min(abs(center_x - cx) + abs(center_y - cy) for cx, cy in corners)
            return (corner_distance, room_distance)
        return (room_distance, edge_distance)

    candidates.sort(key=focus_key)
    return candidates


def _blocking_placement_preserves_routes(
    level: DungeonLevel,
    footprint: tuple[tuple[int, int], ...],
    terrain: DungeonTerrain,
) -> bool:
    if level.player_pos is None:
        return True

    before_reachable = _reachable_floor_tiles(level, level.player_pos)
    original_terrains = {position: level.get_terrain(*position) for position in footprint}
    removed_tiles = sum(1 for position in footprint if position in before_reachable)

    try:
        for x, y in footprint:
            level.set_terrain(x, y, terrain)
        after_reachable = _reachable_floor_tiles(level, level.player_pos)
    finally:
        for (x, y), original in original_terrains.items():
            level.set_terrain(x, y, original)

    expected_reachable = len(before_reachable) - removed_tiles
    if len(after_reachable) != expected_reachable:
        return False
    if level.stairs_down:
        return all(destination in after_reachable for destination in level.stairs_down)
    return True


def _scatter_environment_objects(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    environment: str,
    depth: int,
    reserved: set[tuple[int, int]],
    rng: random.Random,
) -> tuple[list[tuple[str, tuple[int, int]]], list[PlacedEnvironmentObject]]:
    item_pool = _FLOOR_OBJECTS.get(environment, _FLOOR_OBJECTS["default"])
    object_pool = list(_environment_object_templates(environment))
    if (not item_pool and not object_pool) or not rooms:
        return [], []

    candidate_rooms = [
        (index, room)
        for index, room in enumerate(rooms)
        if index not in {0, len(rooms) - 1} and room.room_type != "corridor"
    ]
    if not candidate_rooms:
        candidate_rooms = list(enumerate(rooms))
    if not candidate_rooms:
        return [], []

    rng.shuffle(candidate_rooms)
    target_item_count = max(1, min(3, len(candidate_rooms) // 3 + (1 if depth >= 6 else 0)))
    target_object_count = max(2, min(len(object_pool), len(candidate_rooms) // 2 + 2 + (1 if depth >= 6 else 0)))

    placements: list[tuple[str, tuple[int, int]]] = []
    placed_objects: list[PlacedEnvironmentObject] = []

    for _, room in candidate_rooms:
        if len(placements) >= target_item_count:
            break
        room_tiles = _room_tiles_by_focus(level, room, reserved, focus="center")
        if not room_tiles:
            continue
        item_id = rng.choice(item_pool)
        position = room_tiles[0]
        level.place_item(position[0], position[1], item_id)
        reserved.add(position)
        placements.append((item_id, position))

    if not object_pool:
        return placements, placed_objects

    shuffled_templates = object_pool[:]
    rng.shuffle(shuffled_templates)
    for template in shuffled_templates:
        if len(placed_objects) >= target_object_count:
            break

        room_pool = candidate_rooms[:]
        rng.shuffle(room_pool)
        for _, room in room_pool:
            anchors = _anchor_positions_for_template(level, room, template, reserved)
            shortlist = anchors[: min(8, len(anchors))]
            if not shortlist:
                continue
            rng.shuffle(shortlist)
            for anchor in shortlist:
                footprint = _object_footprint_positions(anchor, template)
                if template.blocking and template.terrain is not None:
                    if not _blocking_placement_preserves_routes(level, footprint, template.terrain):
                        continue
                for x, y in footprint:
                    if template.terrain is not None:
                        if template.blocking:
                            level.set_terrain(x, y, template.terrain)
                        else:
                            _set_feature_tile(level, x, y, template.terrain)
                if template.item_id is not None:
                    level.place_item(anchor[0], anchor[1], template.item_id)
                    placements.append((template.item_id, anchor))
                reserved.update(footprint)
                placed_objects.append(
                    PlacedEnvironmentObject(
                        object_id=template.object_id,
                        anchor=anchor,
                        footprint=footprint,
                        blocking=template.blocking,
                    )
                )
                break
            else:
                continue
            break

    return placements, placed_objects


def _scatter_environment_discoveries(
    level: DungeonLevel,
    rooms: list[DungeonRoom],
    environment: str,
    depth: int,
    reserved: set[tuple[int, int]],
    rng: random.Random,
    plan: EnvironmentContentPlan,
) -> list[PlacedDiscovery]:
    templates = [
        template
        for template in _discovery_templates_for_environment(environment)
        if template.min_depth <= depth <= template.max_depth
    ]
    if not templates or not rooms:
        return []

    matched = [
        template
        for template in templates
        if not plan.discovery_tags or _matches_any_tag(template.tags, plan.discovery_tags)
    ]
    if matched:
        templates = matched + [template for template in templates if template not in matched]

    candidate_rooms = [
        room
        for index, room in enumerate(rooms)
        if index not in {0, len(rooms) - 1} and room.room_type != "corridor"
    ]
    if not candidate_rooms:
        candidate_rooms = list(rooms)
    if not candidate_rooms:
        return []

    rng.shuffle(candidate_rooms)
    target_count = max(1, min(3, 1 + depth // 4))
    discoveries: list[PlacedDiscovery] = []
    used_titles: set[str] = set()

    for room in candidate_rooms:
        if len(discoveries) >= target_count:
            break
        room_tiles = _room_tiles_by_focus(level, room, reserved, focus="edge")
        if not room_tiles:
            continue
        available = [
            template
            for template in templates
            if template.title not in used_titles
        ]
        if not available:
            break
        total_weight = sum(max(1, template.weight) for template in available)
        roll = rng.randint(1, total_weight)
        choice = available[-1]
        for template in available:
            roll -= max(1, template.weight)
            if roll <= 0:
                choice = template
                break
        position = room_tiles[0]
        reserved.add(position)
        used_titles.add(choice.title)
        discoveries.append(
            PlacedDiscovery(
                title=choice.title,
                summary=choice.summary,
                position=position,
                tags=choice.tags,
            )
        )

    return discoveries


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


def _generate_interior_layout(
    level: DungeonLevel,
    env: "Environment",
    room_count: int,
    rng: random.Random,
) -> FloorLayoutPlan:
    rooms = _place_rooms(level.width, level.height, env.room_types, room_count, rng)
    for room in rooms:
        _build_room_on_level(level, room, rng)

    for room_a, room_b in zip(rooms, rooms[1:]):
        _carve_connection(level, room_a.center, room_b.center, rng)

    extra_connections = min(3, max(1, len(rooms) // 3))
    for _ in range(extra_connections):
        room_a, room_b = rng.sample(rooms, 2)
        _carve_connection(level, room_a.center, room_b.center, rng)

    _add_doors(level, rng, rooms)
    secret_passages = tuple(_add_secret_passage(level, rooms, set(), rng))
    return FloorLayoutPlan(rooms=tuple(rooms), secret_passages=secret_passages)


def _generate_swamp_layout(
    level: DungeonLevel,
    env: "Environment",
    room_count: int,
    rng: random.Random,
) -> FloorLayoutPlan:
    main_count = max(5, min(7, room_count))
    rooms: list[DungeonRoom] = []
    centers: list[tuple[int, int]] = []
    y = level.height // 2
    for index in range(main_count):
        progress = index / max(1, main_count - 1)
        center_x = int(4 + progress * (level.width - 8)) + rng.randint(-2, 2)
        y = _clamp(y + rng.randint(-4, 4), 5, level.height - 6)
        center = (_clamp(center_x, 4, level.width - 5), y)
        centers.append(center)
        rooms.append(
            _room_from_center(
                center[0],
                center[1],
                width=rng.randint(10, 16),
                height=rng.randint(8, 12),
                level_width=level.width,
                level_height=level.height,
                room_type=rng.choice(env.room_types),
            )
        )

    for room in rooms:
        _build_outdoor_room_on_level(level, room, rng)

    protected: set[tuple[int, int]] = set()
    for start, end in zip(centers, centers[1:]):
        mid = (
            (start[0] + end[0]) // 2,
            _clamp((start[1] + end[1]) // 2 + rng.randint(-2, 2), 2, level.height - 3),
        )
        protected.update(_carve_polyline(level, (start, mid, end), brush_radius=1, rng=rng))

    side_rooms = max(1, min(2, room_count - main_count))
    for _ in range(side_rooms):
        anchor_index = rng.randint(1, max(1, len(rooms) - 2))
        anchor = rooms[anchor_index].center
        side_center = (
            _clamp(anchor[0] + rng.randint(-5, 5), 4, level.width - 5),
            _clamp(anchor[1] + rng.choice((-6, -5, 5, 6)), 4, level.height - 5),
        )
        side_room = _room_from_center(
            side_center[0],
            side_center[1],
            width=rng.randint(8, 12),
            height=rng.randint(7, 10),
            level_width=level.width,
            level_height=level.height,
            room_type=rng.choice(env.room_types),
        )
        rooms.append(side_room)
        _build_outdoor_room_on_level(level, side_room, rng)
        protected.update(_carve_polyline(level, (anchor, side_room.center), brush_radius=1, rng=rng))

    return FloorLayoutPlan(
        rooms=tuple(sorted(rooms, key=lambda room: (room.center[0], room.center[1]))),
        protected_feature_tiles=frozenset(protected),
        allow_doors=False,
    )


def _generate_forest_layout(
    level: DungeonLevel,
    env: "Environment",
    room_count: int,
    rng: random.Random,
) -> FloorLayoutPlan:
    core_count = max(5, min(8, room_count + 1))
    rooms: list[DungeonRoom] = []
    centers: list[tuple[int, int]] = []
    for index in range(core_count):
        progress = index / max(1, core_count - 1)
        center = (
            _clamp(int(4 + progress * (level.width - 8)) + rng.randint(-3, 3), 4, level.width - 5),
            _clamp(level.height // 2 + rng.randint(-6, 6), 4, level.height - 5),
        )
        centers.append(center)
        rooms.append(
            _room_from_center(
                center[0],
                center[1],
                width=rng.randint(11, 18),
                height=rng.randint(9, 14),
                level_width=level.width,
                level_height=level.height,
                room_type=rng.choice(env.room_types),
            )
        )

    for room in rooms:
        _build_outdoor_room_on_level(level, room, rng)

    protected: set[tuple[int, int]] = set()
    for start, end in zip(centers, centers[1:]):
        mid = (
            (start[0] + end[0]) // 2,
            _clamp((start[1] + end[1]) // 2 + rng.randint(-4, 4), 2, level.height - 3),
        )
        protected.update(_carve_polyline(level, (start, mid, end), brush_radius=2, rng=rng))

    canopy_glades = max(2, min(4, room_count // 2))
    for _ in range(canopy_glades):
        center = (
            rng.randint(5, level.width - 6),
            rng.randint(4, level.height - 5),
        )
        glade = _room_from_center(
            center[0],
            center[1],
            width=rng.randint(9, 14),
            height=rng.randint(7, 11),
            level_width=level.width,
            level_height=level.height,
            room_type="open_room",
        )
        rooms.append(glade)
        _build_outdoor_room_on_level(level, glade, rng)
        target = min(centers, key=lambda candidate: abs(candidate[0] - center[0]) + abs(candidate[1] - center[1]))
        protected.update(_carve_polyline(level, (target, center), brush_radius=2, rng=rng))

    return FloorLayoutPlan(
        rooms=tuple(sorted(rooms, key=lambda room: (room.center[0], room.center[1]))),
        protected_feature_tiles=frozenset(protected),
        allow_doors=False,
    )


def _generate_mountain_layout(
    level: DungeonLevel,
    env: "Environment",
    room_count: int,
    rng: random.Random,
) -> FloorLayoutPlan:
    shelf_count = max(4, min(6, room_count))
    rooms: list[DungeonRoom] = []
    protected: set[tuple[int, int]] = set()
    centers: list[tuple[int, int]] = []
    current_y = rng.randint(5, level.height - 6)

    for index in range(shelf_count):
        progress = index / max(1, shelf_count - 1)
        center_x = _clamp(int(4 + progress * (level.width - 8)) + rng.randint(-1, 1), 4, level.width - 5)
        if index > 0:
            direction = -1 if index % 2 else 1
            current_y = _clamp(current_y + (direction * rng.randint(4, 6)), 4, level.height - 5)
        center = (center_x, current_y)
        centers.append(center)
        plateau = _room_from_center(
            center[0],
            center[1],
            width=rng.randint(8, 13),
            height=rng.randint(6, 9),
            level_width=level.width,
            level_height=level.height,
            room_type=rng.choice(env.room_types),
        )
        rooms.append(plateau)
        _build_outdoor_room_on_level(level, plateau, rng)

    for start, end in zip(centers, centers[1:]):
        bend_x = _clamp((start[0] + end[0]) // 2 + rng.randint(-2, 2), 3, level.width - 4)
        protected.update(
            _carve_polyline(
                level,
                (start, (bend_x, start[1]), (bend_x, end[1]), end),
                brush_radius=1,
                rng=rng,
            )
        )

    ledge_count = max(1, min(2, room_count - shelf_count))
    for _ in range(ledge_count):
        anchor = rooms[rng.randint(1, max(1, len(rooms) - 2))].center
        ledge_center = (
            _clamp(anchor[0] + rng.randint(-4, 4), 4, level.width - 5),
            _clamp(anchor[1] + rng.choice((-4, 4)), 4, level.height - 5),
        )
        ledge = _room_from_center(
            ledge_center[0],
            ledge_center[1],
            width=rng.randint(7, 10),
            height=rng.randint(5, 8),
            level_width=level.width,
            level_height=level.height,
            room_type="open_room",
        )
        rooms.append(ledge)
        _build_outdoor_room_on_level(level, ledge, rng)
        protected.update(_carve_polyline(level, (anchor, ledge.center), brush_radius=1, rng=rng))

    return FloorLayoutPlan(
        rooms=tuple(sorted(rooms, key=lambda room: (room.center[0], room.center[1]))),
        protected_feature_tiles=frozenset(protected),
        allow_doors=False,
    )


def _generate_floor_layout(
    level: DungeonLevel,
    env: "Environment",
    room_count: int,
    rng: random.Random,
) -> FloorLayoutPlan:
    if env.topology != "outdoor":
        return _generate_interior_layout(level, env, room_count, rng)
    if env.name == "swamp":
        return _generate_swamp_layout(level, env, room_count, rng)
    if env.name == "forest":
        return _generate_forest_layout(level, env, room_count, rng)
    if env.name == "mountains":
        return _generate_mountain_layout(level, env, room_count, rng)
    return _generate_forest_layout(level, env, room_count, rng)


def _candidate_floor_tiles(
    level: DungeonLevel,
    *,
    protected: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    return [
        (x, y)
        for y in range(1, level.height - 1)
        for x in range(1, level.width - 1)
        if level.get_terrain(x, y) == DungeonTerrain.FLOOR
        and (protected is None or (x, y) not in protected)
    ]


def _paint_environment_clusters(
    level: DungeonLevel,
    *,
    candidates: list[tuple[int, int]],
    terrain: DungeonTerrain,
    cluster_count: int,
    radius_range: tuple[int, int],
    rng: random.Random,
    protected: set[tuple[int, int]],
) -> None:
    if not candidates:
        return
    sample_count = min(cluster_count, len(candidates))
    for origin in rng.sample(candidates, sample_count):
        radius_x = rng.randint(radius_range[0], radius_range[1])
        radius_y = rng.randint(max(1, radius_range[0] - 1), radius_range[1])
        _carve_blob(
            level,
            origin,
            radius_x,
            radius_y,
            rng,
            terrain=terrain,
            protected=protected,
            jitter=0.12,
        )


def _shape_outdoor_environment(
    level: DungeonLevel,
    environment: str,
    protected: set[tuple[int, int]],
    rng: random.Random,
) -> None:
    candidates = _candidate_floor_tiles(level, protected=protected)
    if not candidates:
        return

    if environment == "swamp":
        _paint_environment_clusters(
            level,
            candidates=candidates,
            terrain=DungeonTerrain.WATER,
            cluster_count=5,
            radius_range=(2, 4),
            rng=rng,
            protected=protected,
        )
        growth_candidates = _candidate_floor_tiles(level, protected=protected)
        _paint_environment_clusters(
            level,
            candidates=growth_candidates,
            terrain=DungeonTerrain.GROWTH,
            cluster_count=6,
            radius_range=(1, 3),
            rng=rng,
            protected=protected,
        )
        acid_candidates = _candidate_floor_tiles(level, protected=protected)
        _paint_environment_clusters(
            level,
            candidates=acid_candidates,
            terrain=DungeonTerrain.ACID_POOL,
            cluster_count=2,
            radius_range=(1, 2),
            rng=rng,
            protected=protected,
        )
        return

    if environment == "forest":
        _paint_environment_clusters(
            level,
            candidates=candidates,
            terrain=DungeonTerrain.GROWTH,
            cluster_count=8,
            radius_range=(2, 4),
            rng=rng,
            protected=protected,
        )
        cover_candidates = _candidate_floor_tiles(level, protected=protected)
        _paint_environment_clusters(
            level,
            candidates=cover_candidates,
            terrain=DungeonTerrain.COVER,
            cluster_count=5,
            radius_range=(1, 2),
            rng=rng,
            protected=protected,
        )
        shrine_candidates = _candidate_floor_tiles(level, protected=protected)
        _paint_environment_clusters(
            level,
            candidates=shrine_candidates,
            terrain=DungeonTerrain.SHRINE,
            cluster_count=2,
            radius_range=(1, 1),
            rng=rng,
            protected=protected,
        )
        return

    if environment == "mountains":
        _paint_environment_clusters(
            level,
            candidates=candidates,
            terrain=DungeonTerrain.CHASM,
            cluster_count=4,
            radius_range=(1, 2),
            rng=rng,
            protected=protected,
        )
        rubble_candidates = _candidate_floor_tiles(level, protected=protected)
        _paint_environment_clusters(
            level,
            candidates=rubble_candidates,
            terrain=DungeonTerrain.RUBBLE,
            cluster_count=6,
            radius_range=(1, 3),
            rng=rng,
            protected=protected,
        )
        shrine_candidates = _candidate_floor_tiles(level, protected=protected)
        _paint_environment_clusters(
            level,
            candidates=shrine_candidates,
            terrain=DungeonTerrain.SHRINE,
            cluster_count=2,
            radius_range=(1, 1),
            rng=rng,
            protected=protected,
        )


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
    if environment in {"swamp", "forest"} and kind in {"swarm", "pack"}:
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
    "swamp": {
        "hostile": (
            _ContactArchetype(
                name="Bog Skulker",
                description="A half-submerged killer moving where the water deepens without warning.",
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
                tags=("bog", "predator", "swamp"),
            ),
            _ContactArchetype(
                name="Marsh Leech-Swarm",
                description="A writhing blackwater nest eager for warm blood and exposed augmetics.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=4,
                attack=2,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="servo-skull",
                weight=3,
                tags=("swarm", "bog", "vermin"),
            ),
            _ContactArchetype(
                name="Fen Mutant",
                description="A sump-scarred brute that knows every drowned path by instinct.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=4,
                armor=0,
                movement=3,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("mutant", "swamp", "bog"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Reed Guide",
                description="A wary local who can still read the causeways through the mist.",
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
                tags=("guide", "swamp", "survivor"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Mire Prospector",
                description="A scavenger probing the waterline for relics and safe footing.",
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
                tags=("prospector", "swamp", "bog"),
            ),
        ),
    },
    "forest": {
        "hostile": (
            _ContactArchetype(
                name="Canopy Stalker",
                description="A hunter ghosting between trunks and shrine-stones with patient intent.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=5,
                attack_range=1,
                portrait_hint="assassin",
                weight=3,
                tags=("forest", "stalker", "predator"),
            ),
            _ContactArchetype(
                name="Rootbound Hound",
                description="A feral beast trained to run glade paths faster than prey can react.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=5,
                attack=3,
                armor=0,
                movement=5,
                attack_range=1,
                portrait_hint="servitor",
                weight=2,
                tags=("beast", "forest", "hunt"),
            ),
            _ContactArchetype(
                name="Thorn Cultist",
                description="A shrine-keeper gone feral, daubed in sap, ash, and machine prayers.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=7,
                attack=3,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("cult", "forest", "shrine"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Wayfinder",
                description="A path-reader who keeps the glades connected with wards and patience.",
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
                tags=("guide", "forest", "scout"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Shrine Warden",
                description="A solitary keeper watching the old stones and weighing every stranger.",
                disposition=DungeonDisposition.NEUTRAL,
                movement_ai=DungeonMovementAI.STATIONARY,
                can_talk=True,
                max_hp=6,
                attack=2,
                armor=0,
                movement=2,
                attack_range=1,
                portrait_hint="priest",
                weight=2,
                tags=("warden", "forest", "shrine"),
            ),
        ),
    },
    "mountains": {
        "hostile": (
            _ContactArchetype(
                name="Cliff Raider",
                description="A high-pass brigand striking where the trail narrows and footing fails.",
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
                tags=("raider", "mountain", "pass"),
            ),
            _ContactArchetype(
                name="Scree Ambusher",
                description="A scavenger using loose rock and blind corners as a weapon.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=6,
                attack=3,
                armor=0,
                movement=4,
                attack_range=1,
                portrait_hint="pit_slave",
                weight=2,
                tags=("ambusher", "mountain", "scree"),
            ),
            _ContactArchetype(
                name="Pass Guardian",
                description="A shrine-armed sentinel holding the approach with stubborn discipline.",
                disposition=DungeonDisposition.HOSTILE,
                movement_ai=DungeonMovementAI.AGGRESSIVE,
                can_talk=False,
                max_hp=8,
                attack=4,
                armor=1,
                movement=3,
                attack_range=1,
                portrait_hint="skitarii",
                weight=2,
                tags=("guardian", "mountain", "shrine"),
            ),
        ),
        "friendly": (
            _ContactArchetype(
                name="Peak Surveyor",
                description="A wind-burned surveyor mapping which shelves still hold underfoot.",
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
                tags=("survey", "mountain", "guide"),
            ),
        ),
        "neutral": (
            _ContactArchetype(
                name="Cairn Keeper",
                description="A solitary attendant tending prayer cairns and warning travellers away from bad stone.",
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
                tags=("keeper", "mountain", "shrine"),
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
    set_piece_bonus: int = 0,
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
    max_set_pieces += max(0, set_piece_bonus)
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
    total_contacts = max(1, min(high, max(low, 2 + depth // 2 + len(rooms) // 4)))
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


def build_environment_debug_catalog() -> tuple[EnvironmentDebugEntry, ...]:
    """Return a stable debug view of the preset environment content tables."""
    entries: list[EnvironmentDebugEntry] = []
    for environment_id, environment in ENVIRONMENTS.items():
        contacts = _contacts_for_environment(environment_id)
        themed_rooms = tuple(
            template.name for template in _themed_room_templates_for_environment(environment_id)
        )
        discoveries = tuple(
            template.title for template in _discovery_templates_for_environment(environment_id)
        )
        variants = tuple(
            variant.name for variant in (_STANDARD_VARIANT,) + _ENVIRONMENT_VARIANTS.get(environment_id, ())
        )
        reactive_rule = next(
            (
                variant.reactive_rule
                for variant in _ENVIRONMENT_VARIANTS.get(environment_id, ())
                if variant.reactive_rule
            ),
            None,
        )
        entries.append(
            EnvironmentDebugEntry(
                environment_id=environment_id,
                description=environment.description,
                feature_terrains=tuple(terrain.value for terrain in environment.feature_terrains),
                room_types=environment.room_types,
                hostile_contacts=tuple(archetype.name for archetype in contacts.get("hostile", ())),
                friendly_contacts=tuple(archetype.name for archetype in contacts.get("friendly", ())),
                neutral_contacts=tuple(archetype.name for archetype in contacts.get("neutral", ())),
                item_names=_FLOOR_OBJECTS.get(environment_id, _FLOOR_OBJECTS["default"]),
                object_templates=tuple(
                    template.object_id for template in _environment_object_templates(environment_id)
                ),
                themed_rooms=themed_rooms,
                discovery_titles=discoveries,
                variant_names=variants,
                reactive_rule=reactive_rule,
            )
        )
    return tuple(entries)


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
    "forge": (3, 5),
    "cathedral": (2, 5),
    "hive": (4, 7),
    "sewer": (4, 7),
    "corrupted": (3, 6),
    "overgrown": (3, 6),
    "tomb": (2, 4),
    "manufactorum": (3, 6),
    "voidship": (4, 7),
    "reliquary": (2, 5),
    "radwastes": (3, 6),
    "data_vault": (3, 5),
    "xenos_ruin": (3, 6),
    "ice_crypt": (2, 5),
    "sump_market": (3, 6),
    "plasma_reactorum": (3, 6),
    "penal_oubliette": (3, 6),
    "ash_dune_outpost": (3, 6),
    "swamp": (3, 6),
    "forest": (3, 6),
    "mountains": (3, 5),
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
    "swamp": (70, 10, 20),
    "forest": (60, 20, 20),
    "mountains": (65, 15, 20),
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
    "swamp": (
        ThemedRoomTemplate(
            name="Drowned Causeway",
            description="A half-submerged shrine road where scavengers and predators stalk the last dry stones.",
            environments=("swamp",),
            room_types=("open_room", "cross_room", "arena"),
            min_depth=1,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.WATER, DungeonTerrain.SHRINE),
            props=(ThemedRoomPropSpec(DungeonTerrain.GROWTH, (1, 3), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 6),
                    preferred_tags=("bog", "mutant", "predator", "swarm"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("guide", "prospector"),
                    optional=True,
                ),
            ),
            tags=("marsh", "sump", "shrine"),
        ),
    ),
    "forest": (
        ThemedRoomTemplate(
            name="Waystone Glade",
            description="A sacred glade where broken stones, hunter signs, and hidden paths converge.",
            environments=("forest",),
            room_types=("open_room", "pillared_hall", "cross_room"),
            min_depth=1,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.GROWTH),
            props=(ThemedRoomPropSpec(DungeonTerrain.COVER, (1, 2), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 5),
                    preferred_tags=("forest", "stalker", "cult", "predator"),
                ),
                ThemedRoomEncounterSpec(
                    category="friendly",
                    count_range=(0, 1),
                    preferred_tags=("guide", "scout"),
                    optional=True,
                ),
            ),
            tags=("glade", "waystone", "hunt"),
        ),
    ),
    "mountains": (
        ThemedRoomTemplate(
            name="High Pass Redoubt",
            description="A cliffside hold with prayer cairns, windbreaks, and a killing field over the switchback.",
            environments=("mountains",),
            room_types=("open_room", "arena", "l_shaped"),
            min_depth=1,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.COVER),
            props=(ThemedRoomPropSpec(DungeonTerrain.RUBBLE, (1, 3), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 5),
                    preferred_tags=("mountain", "raider", "guardian", "ambusher"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("guide", "keeper", "survey"),
                    optional=True,
                ),
            ),
            tags=("pass", "watchpost", "shrine"),
        ),
    ),
    "overgrown": (
        ThemedRoomTemplate(
            name="Spore Nursery",
            description="A reclaimed chamber where fungal blooms and cocooned prey are cultivated in damp heat.",
            environments=("overgrown",),
            room_types=("open_room", "arena", "pillared_hall"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.GROWTH, DungeonTerrain.WATER),
            props=(ThemedRoomPropSpec(DungeonTerrain.RUBBLE, (1, 2), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 5),
                    preferred_tags=("growth", "predator"),
                ),
                ThemedRoomEncounterSpec(
                    category="friendly",
                    count_range=(0, 1),
                    preferred_tags=("survivor", "guide"),
                    optional=True,
                ),
            ),
            tags=("growth", "garden", "reclaimed"),
        ),
    ),
    "tomb": (
        ThemedRoomTemplate(
            name="Waking Sepulchre",
            description="A burial chamber where broken seals and half-raised guardians imply a recent disturbance.",
            environments=("tomb", "ice_crypt"),
            room_types=("small_chamber", "cross_room", "pillared_hall"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.COLUMN),
            props=(ThemedRoomPropSpec(DungeonTerrain.RUBBLE, (1, 2), room_focus="center"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 4),
                    preferred_tags=("guardian", "tomb", "bone"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("scribe",),
                    optional=True,
                ),
            ),
            tags=("tomb", "guardian", "relic"),
        ),
    ),
    "data_vault": (
        ThemedRoomTemplate(
            name="Cipher Stack",
            description="A sealed archive cluster where stacked cogitators and recovery racks hide a deeper cache.",
            environments=("data_vault", "manufactorum"),
            room_types=("small_chamber", "pillared_hall", "cross_room"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            feature_terrains=(DungeonTerrain.TERMINAL, DungeonTerrain.COVER),
            props=(ThemedRoomPropSpec(DungeonTerrain.COLUMN, (1, 2), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 4),
                    preferred_tags=("vault", "warden", "saboteur"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("scribe", "clerk"),
                    optional=True,
                ),
            ),
            tags=("vault", "archive", "cipher"),
        ),
    ),
    "xenos_ruin": (
        ThemedRoomTemplate(
            name="Glyph Nexus",
            description="An alien junction chamber where repeating sigils align around an impossible focal point.",
            environments=("xenos_ruin",),
            room_types=("maze", "cross_room", "arena"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.SHRINE, DungeonTerrain.CHASM),
            props=(ThemedRoomPropSpec(DungeonTerrain.COLUMN, (1, 2), room_focus="center"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 4),
                    preferred_tags=("xenos", "predator", "sentinel"),
                ),
            ),
            tags=("glyph", "xenos", "sanctum"),
        ),
    ),
    "sump_market": (
        ThemedRoomTemplate(
            name="Contraband Exchange",
            description="A defended market ring where smugglers barter amid blackwater trenches and hidden weapons.",
            environments=("sump_market", "hive"),
            room_types=("open_room", "l_shaped", "cross_room"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            feature_terrains=(DungeonTerrain.COVER, DungeonTerrain.WATER),
            props=(ThemedRoomPropSpec(DungeonTerrain.SHRINE, (1, 1), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(2, 5),
                    preferred_tags=("criminal", "gang", "broker"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("broker", "guide"),
                    optional=True,
                ),
            ),
            tags=("market", "stash", "underhive"),
        ),
    ),
    "plasma_reactorum": (
        ThemedRoomTemplate(
            name="Containment Choir",
            description="A reactor ward where acolytes chant containment rites over failing plasma shielding.",
            environments=("plasma_reactorum", "forge"),
            room_types=("open_room", "arena", "pillared_hall"),
            min_depth=3,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            requires_spacious_room=True,
            feature_terrains=(DungeonTerrain.LAVA, DungeonTerrain.TERMINAL),
            props=(ThemedRoomPropSpec(DungeonTerrain.COVER, (1, 2), room_focus="edge"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 5),
                    preferred_tags=("reactor", "cult", "warden"),
                ),
                ThemedRoomEncounterSpec(
                    category="friendly",
                    count_range=(0, 1),
                    preferred_tags=("engineer", "tech"),
                    optional=True,
                ),
            ),
            tags=("reactor", "containment", "machine_cult"),
        ),
    ),
    "penal_oubliette": (
        ThemedRoomTemplate(
            name="Punishment Circuit",
            description="A circular punishment hall where chained routes funnel prisoners past shrines and execution gear.",
            environments=("penal_oubliette",),
            room_types=("cross_room", "arena", "l_shaped"),
            min_depth=2,
            max_depth=999,
            weight=4,
            max_per_floor=1,
            feature_terrains=(DungeonTerrain.GRATE, DungeonTerrain.SHRINE),
            props=(ThemedRoomPropSpec(DungeonTerrain.COVER, (1, 2), room_focus="center"),),
            encounter_groups=(
                ThemedRoomEncounterSpec(
                    category="hostile",
                    count_range=(3, 6),
                    preferred_tags=("convict", "warden", "riot"),
                ),
                ThemedRoomEncounterSpec(
                    category="neutral",
                    count_range=(0, 1),
                    preferred_tags=("confessor", "warden"),
                    optional=True,
                ),
            ),
            tags=("penal", "execution", "cellblock"),
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
    content_plan = _resolve_environment_content_plan(env.name, depth, rng, profile)
    width = max(FLOOR_MIN_WIDTH, min(FLOOR_MAX_WIDTH, width))
    height = max(FLOOR_MIN_HEIGHT, min(FLOOR_MAX_HEIGHT, height))
    resolved_room_count = room_count if room_count is not None else max(6, (width * height) // 260)
    resolved_room_count += content_plan.floor_band.room_count_delta
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

    layout = _generate_floor_layout(level, env, resolved_room_count, rng)
    rooms = list(layout.rooms)

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
    protected_feature_tiles = set(layout.protected_feature_tiles)
    protected_feature_tiles.update(reserved)
    if env.topology == "outdoor":
        _shape_outdoor_environment(level, env.name, protected_feature_tiles, rng)

    secret_passages = list(layout.secret_passages)
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
        content_plan.profile,
        set_piece_bonus=content_plan.floor_band.set_piece_bonus,
    )
    feature_reserved = reserved if env.topology != "outdoor" else reserved | protected_feature_tiles
    _scatter_environment_features(level, rooms, env.name, feature_reserved, rng)
    placed_items, placed_objects = _scatter_environment_objects(level, rooms, env.name, depth, reserved, rng)
    placed_discoveries = _scatter_environment_discoveries(
        level,
        rooms,
        env.name,
        depth,
        reserved,
        rng,
        content_plan,
    )
    entity_roster = _generate_contacts(
        level,
        rooms,
        env.name,
        depth,
        rng,
        reserved_positions=reserved,
        # Themed rooms should add pressure instead of fully consuming the
        # baseline contact budget, so only trim part of their roster impact.
        budget_offset=themed_contact_count // 2,
        roster=entity_roster,
        profile=content_plan.profile,
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
        placed_objects=placed_objects,
        entity_roster=entity_roster,
        themed_rooms=themed_rooms,
        placed_discoveries=placed_discoveries,
        content_variant_id=content_plan.variant.variant_id,
        content_variant_name=content_plan.variant.name,
        floor_band=content_plan.floor_band.band_id,
        ambience_lines=content_plan.ambience_lines,
        reactive_rule=content_plan.reactive_rule,
    )
