"""Persistent tile-map data model for exploration-scale dungeons.

Defines terrain types, fog-of-war state, and a ``DungeonLevel`` grid that
supports item/creature placement, FOV helpers, and full serialization.

This is a **data model** -- no generation or rendering logic lives here.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, NamedTuple


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------


class DungeonTerrain(enum.Enum):
    """Terrain types for exploration-scale dungeon maps.

    Superset of the combat ``Terrain`` enum -- includes doors, stairs,
    hazards, and interactive objects appropriate to a WH40K forge-world
    setting.
    """

    # Basic
    FLOOR = "floor"
    WALL = "wall"

    # Doors
    DOOR_OPEN = "door_open"
    DOOR_CLOSED = "door_closed"

    # Vertical transitions
    STAIRS_UP = "stairs_up"
    STAIRS_DOWN = "stairs_down"

    # Hazards / difficult terrain
    WATER = "water"
    LAVA = "lava"
    CHASM = "chasm"
    RUBBLE = "rubble"

    # Features
    TERMINAL = "terminal"
    COLUMN = "column"
    GROWTH = "growth"
    COVER = "cover"
    GRATE = "grate"
    ACID_POOL = "acid_pool"
    SHRINE = "shrine"


# Terrain property look-up tables.
# Each terrain maps to (passable, transparent, movement_cost).
# For impassable terrains movement_cost is irrelevant but stored as 0.

_TERRAIN_PROPS: dict[DungeonTerrain, tuple[bool, bool, int]] = {
    DungeonTerrain.FLOOR:       (True,  True,  1),
    DungeonTerrain.WALL:        (False, False, 0),
    DungeonTerrain.DOOR_OPEN:   (True,  True,  1),
    DungeonTerrain.DOOR_CLOSED: (False, False, 0),
    DungeonTerrain.STAIRS_UP:   (True,  True,  1),
    DungeonTerrain.STAIRS_DOWN: (True,  True,  1),
    DungeonTerrain.WATER:       (True,  True,  2),
    DungeonTerrain.LAVA:        (False, True,  0),
    DungeonTerrain.CHASM:       (False, True,  0),
    DungeonTerrain.RUBBLE:      (True,  True,  2),
    DungeonTerrain.TERMINAL:    (True,  True,  1),
    DungeonTerrain.COLUMN:      (False, False, 0),
    DungeonTerrain.GROWTH:      (True,  True,  2),
    DungeonTerrain.COVER:       (True,  True,  2),
    DungeonTerrain.GRATE:       (True,  True,  1),
    DungeonTerrain.ACID_POOL:   (False, True,  0),
    DungeonTerrain.SHRINE:      (True,  True,  1),
}


# ---------------------------------------------------------------------------
# Terrain rendering
# ---------------------------------------------------------------------------


class TerrainGlyph(NamedTuple):
    """Display character and foreground color for a terrain type."""

    char: str
    fg: str


_TERRAIN_GLYPHS: dict[DungeonTerrain, TerrainGlyph] = {
    DungeonTerrain.FLOOR:       TerrainGlyph("·", "#585858"),
    DungeonTerrain.WALL:        TerrainGlyph("#", "#a0a0a0"),
    DungeonTerrain.DOOR_OPEN:   TerrainGlyph("'", "#c89632"),
    DungeonTerrain.DOOR_CLOSED: TerrainGlyph("+", "#c89632"),
    DungeonTerrain.STAIRS_UP:   TerrainGlyph("<", "#ffffff"),
    DungeonTerrain.STAIRS_DOWN: TerrainGlyph(">", "#ffffff"),
    DungeonTerrain.WATER:       TerrainGlyph("~", "#4488ff"),
    DungeonTerrain.LAVA:        TerrainGlyph("~", "#ff4400"),
    DungeonTerrain.CHASM:       TerrainGlyph("·", "#222222"),
    DungeonTerrain.RUBBLE:      TerrainGlyph(":", "#808080"),
    DungeonTerrain.TERMINAL:    TerrainGlyph("¤", "#00ff41"),
    DungeonTerrain.COLUMN:      TerrainGlyph("O", "#b0b0b0"),
    DungeonTerrain.GROWTH:      TerrainGlyph('"', "#22aa22"),
    DungeonTerrain.COVER:       TerrainGlyph("%", "#808060"),
    DungeonTerrain.GRATE:       TerrainGlyph("≡", "#708090"),
    DungeonTerrain.ACID_POOL:   TerrainGlyph("~", "#88ff00"),
    DungeonTerrain.SHRINE:      TerrainGlyph("†", "#ffd700"),
}


# ---------------------------------------------------------------------------
# Fog of war
# ---------------------------------------------------------------------------


class FogState(enum.Enum):
    """Per-tile visibility state for fog-of-war."""

    HIDDEN = "hidden"        # Never seen
    EXPLORED = "explored"    # Seen before, not currently visible
    VISIBLE = "visible"      # In current field-of-view


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Environment:
    """Defines the character of a dungeon environment.

    The LLM narrative determines which environment applies (cathedral,
    swamp, forge, etc.).  The generator uses ``feature_terrains`` and
    ``room_types`` to shape the level layout.  The renderer uses
    ``color_overrides`` layered on top of ``_TERRAIN_GLYPHS`` to tint
    terrain to match the setting.
    """

    name: str
    description: str
    feature_terrains: tuple[DungeonTerrain, ...]
    room_types: tuple[str, ...]
    color_overrides: dict[DungeonTerrain, str] = field(default_factory=dict)


ENVIRONMENTS: dict[str, Environment] = {
    "forge": Environment(
        name="forge",
        description="Mechanicus forge — industrial metalwork, molten slag, cogitator banks",
        feature_terrains=(
            DungeonTerrain.TERMINAL, DungeonTerrain.RUBBLE,
            DungeonTerrain.COLUMN, DungeonTerrain.COVER,
            DungeonTerrain.GRATE,
        ),
        room_types=("open_room", "pillared_hall", "corridor", "l_shaped"),
        color_overrides={
            DungeonTerrain.FLOOR: "#6e4b1e",
            DungeonTerrain.WALL:  "#8b6914",
        },
    ),
    "cathedral": Environment(
        name="cathedral",
        description="Imperial cathedral — vaulted stone, pillars, sacred shrines",
        feature_terrains=(
            DungeonTerrain.COLUMN, DungeonTerrain.SHRINE,
            DungeonTerrain.RUBBLE,
        ),
        room_types=("pillared_hall", "open_room", "cross_room", "corridor"),
        color_overrides={
            DungeonTerrain.FLOOR:  "#707070",
            DungeonTerrain.WALL:   "#c0b090",
            DungeonTerrain.COLUMN: "#d0c0a0",
        },
    ),
    "hive": Environment(
        name="hive",
        description="Underhive — cramped hab-stacks, scrap barricades, rusted grating",
        feature_terrains=(
            DungeonTerrain.COVER, DungeonTerrain.RUBBLE,
            DungeonTerrain.GRATE, DungeonTerrain.TERMINAL,
        ),
        room_types=("small_chamber", "corridor", "l_shaped", "maze"),
        color_overrides={
            DungeonTerrain.FLOOR: "#4a4036",
            DungeonTerrain.WALL:  "#6b5b4a",
        },
    ),
    "sewer": Environment(
        name="sewer",
        description="Sub-hive drainage — stagnant water, corroded pipes, toxic runoff",
        feature_terrains=(
            DungeonTerrain.WATER, DungeonTerrain.GRATE,
            DungeonTerrain.GROWTH, DungeonTerrain.ACID_POOL,
        ),
        room_types=("corridor", "cross_room", "l_shaped", "open_room"),
        color_overrides={
            DungeonTerrain.FLOOR: "#3a4a3a",
            DungeonTerrain.WALL:  "#556655",
            DungeonTerrain.WATER: "#336655",
        },
    ),
    "corrupted": Environment(
        name="corrupted",
        description="Warp-tainted zone — mutated growths, reality fractures, daemonic residue",
        feature_terrains=(
            DungeonTerrain.GROWTH, DungeonTerrain.LAVA,
            DungeonTerrain.RUBBLE, DungeonTerrain.CHASM,
        ),
        room_types=("open_room", "cross_room", "maze", "arena"),
        color_overrides={
            DungeonTerrain.FLOOR:  "#3a1a3a",
            DungeonTerrain.WALL:   "#6a2a4a",
            DungeonTerrain.GROWTH: "#aa22aa",
            DungeonTerrain.LAVA:   "#ff2266",
        },
    ),
    "overgrown": Environment(
        name="overgrown",
        description="Reclaimed ruins — vines, fungal blooms, pooling water",
        feature_terrains=(
            DungeonTerrain.GROWTH, DungeonTerrain.WATER,
            DungeonTerrain.RUBBLE, DungeonTerrain.COLUMN,
        ),
        room_types=("open_room", "pillared_hall", "l_shaped", "arena"),
        color_overrides={
            DungeonTerrain.FLOOR:  "#3a5a2a",
            DungeonTerrain.WALL:   "#5a7a4a",
            DungeonTerrain.GROWTH: "#44cc44",
        },
    ),
    "tomb": Environment(
        name="tomb",
        description="Ancient crypt — sealed chambers, sarcophagi, engraved stone",
        feature_terrains=(
            DungeonTerrain.COLUMN, DungeonTerrain.SHRINE,
            DungeonTerrain.RUBBLE,
        ),
        room_types=("small_chamber", "corridor", "pillared_hall", "cross_room"),
        color_overrides={
            DungeonTerrain.FLOOR:  "#505050",
            DungeonTerrain.WALL:   "#787878",
            DungeonTerrain.SHRINE: "#b8b8ff",
        },
    ),
    "manufactorum": Environment(
        name="manufactorum",
        description="Imperial factory — assembly lines, conveyor gantries, cogitator stacks",
        feature_terrains=(
            DungeonTerrain.TERMINAL, DungeonTerrain.COVER,
            DungeonTerrain.RUBBLE, DungeonTerrain.COLUMN,
            DungeonTerrain.GRATE,
        ),
        room_types=("open_room", "corridor", "pillared_hall", "l_shaped"),
        color_overrides={
            DungeonTerrain.FLOOR:    "#4a4a50",
            DungeonTerrain.WALL:     "#6a6a70",
            DungeonTerrain.TERMINAL: "#00ccff",
        },
    ),
}


# ---------------------------------------------------------------------------
# DungeonTile
# ---------------------------------------------------------------------------


@dataclass
class DungeonTile:
    """A single cell in a dungeon level."""

    terrain: DungeonTerrain = DungeonTerrain.FLOOR
    fog: FogState = FogState.HIDDEN
    items: list[str] = field(default_factory=list)
    creature_id: str | None = None

    # -- derived properties --------------------------------------------------

    @property
    def passable(self) -> bool:
        """Whether a creature can walk onto this tile."""
        return _TERRAIN_PROPS[self.terrain][0]

    @property
    def transparent(self) -> bool:
        """Whether this tile allows line-of-sight (for FOV calculations)."""
        return _TERRAIN_PROPS[self.terrain][1]

    @property
    def blocks_sight(self) -> bool:
        """Inverse of *transparent* -- convenience for FOV code."""
        return not self.transparent

    @property
    def movement_cost(self) -> int:
        """Movement cost to enter this tile (0 means impassable)."""
        return _TERRAIN_PROPS[self.terrain][2]

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "terrain": self.terrain.value,
            "fog": self.fog.value,
        }
        if self.items:
            data["items"] = list(self.items)
        if self.creature_id is not None:
            data["creature_id"] = self.creature_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DungeonTile:
        return cls(
            terrain=DungeonTerrain(data["terrain"]),
            fog=FogState(data["fog"]),
            items=list(data.get("items", [])),
            creature_id=data.get("creature_id"),
        )


# ---------------------------------------------------------------------------
# FOV helpers
# ---------------------------------------------------------------------------


def _bresenham_line(
    start: tuple[int, int],
    end: tuple[int, int],
) -> list[tuple[int, int]]:
    """Return the grid cells on a Bresenham line from *start* to *end*."""
    x0, y0 = start
    x1, y1 = end

    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        double_err = 2 * err
        if double_err > -dy:
            err -= dy
            x0 += sx
        if double_err < dx:
            err += dx
            y0 += sy

    return points


# ---------------------------------------------------------------------------
# DungeonLevel
# ---------------------------------------------------------------------------


@dataclass
class DungeonLevel:
    """Persistent tile map for one dungeon floor.

    Supports large maps (80x50+), item/creature placement, fog-of-war,
    and full ``to_dict`` / ``from_dict`` round-trip serialization.
    """

    level_id: str
    name: str
    depth: int
    environment: str
    width: int
    height: int
    tiles: list[list[DungeonTile]] = field(default_factory=list)
    player_pos: tuple[int, int] | None = None
    stairs_up: list[tuple[int, int]] = field(default_factory=list)
    stairs_down: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tiles:
            self.tiles = [
                [DungeonTile() for _ in range(self.width)]
                for _ in range(self.height)
            ]

    # -- basic accessors -----------------------------------------------------

    def in_bounds(self, x: int, y: int) -> bool:
        """Return True if (x, y) is within the level grid."""
        return 0 <= x < self.width and 0 <= y < self.height

    def get_tile(self, x: int, y: int) -> DungeonTile:
        """Return the tile at (x, y).  Caller must ensure in-bounds."""
        return self.tiles[y][x]

    def get_terrain(self, x: int, y: int) -> DungeonTerrain:
        """Return the terrain type at (x, y)."""
        return self.tiles[y][x].terrain

    def set_terrain(self, x: int, y: int, terrain: DungeonTerrain) -> None:
        """Set the terrain type at (x, y)."""
        self.tiles[y][x].terrain = terrain

    # -- FOV helpers ---------------------------------------------------------

    def reset_visible(self) -> None:
        """Demote all VISIBLE tiles to EXPLORED.

        Call this at the start of each FOV recalculation.
        """
        for row in self.tiles:
            for tile in row:
                if tile.fog == FogState.VISIBLE:
                    tile.fog = FogState.EXPLORED

    def set_visible(self, x: int, y: int) -> None:
        """Mark a tile as currently visible (in the player's FOV)."""
        if self.in_bounds(x, y):
            self.tiles[y][x].fog = FogState.VISIBLE

    def is_visible(self, x: int, y: int) -> bool:
        """Return True if the tile is currently visible."""
        return self.in_bounds(x, y) and self.tiles[y][x].fog == FogState.VISIBLE

    def is_explored(self, x: int, y: int) -> bool:
        """Return True if the tile has been seen before."""
        return self.in_bounds(x, y) and self.tiles[y][x].fog in {
            FogState.EXPLORED,
            FogState.VISIBLE,
        }

    def is_hidden(self, x: int, y: int) -> bool:
        """Return True if the tile has never been seen."""
        return self.in_bounds(x, y) and self.tiles[y][x].fog == FogState.HIDDEN

    def line_of_sight(
        self,
        origin: tuple[int, int],
        target: tuple[int, int],
    ) -> bool:
        """Return True if there is unobstructed LOS from origin to target."""
        ox, oy = origin
        tx, ty = target
        if not self.in_bounds(ox, oy) or not self.in_bounds(tx, ty):
            return False
        if origin == target:
            return True

        line = _bresenham_line(origin, target)
        for x, y in line[1:-1]:
            if self.tiles[y][x].blocks_sight:
                return False
        return True

    def compute_fov(
        self,
        origin: tuple[int, int],
        radius: int,
    ) -> set[tuple[int, int]]:
        """Recompute fog-of-war from an origin and radius.

        Previously visible tiles become explored, and tiles in LOS within the
        radius are marked visible.
        """
        if radius < 0:
            raise ValueError("radius must be non-negative")

        self.reset_visible()
        ox, oy = origin
        if not self.in_bounds(ox, oy):
            return set()

        visible: set[tuple[int, int]] = set()
        radius_sq = radius * radius
        x_min = max(0, ox - radius)
        x_max = min(self.width - 1, ox + radius)
        y_min = max(0, oy - radius)
        y_max = min(self.height - 1, oy + radius)

        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                dx = x - ox
                dy = y - oy
                if dx * dx + dy * dy > radius_sq:
                    continue
                if self.line_of_sight(origin, (x, y)):
                    self.set_visible(x, y)
                    visible.add((x, y))

        return visible

    def visible_tiles(self) -> list[tuple[int, int]]:
        """Return all currently visible tile coordinates."""
        visible: list[tuple[int, int]] = []
        for y in range(self.height):
            for x in range(self.width):
                if self.tiles[y][x].fog == FogState.VISIBLE:
                    visible.append((x, y))
        return visible

    # -- creature helpers ----------------------------------------------------

    def place_creature(self, x: int, y: int, creature_id: str) -> None:
        """Place a creature reference on the tile at (x, y)."""
        self.tiles[y][x].creature_id = creature_id

    def remove_creature(self, x: int, y: int) -> None:
        """Remove any creature reference from the tile at (x, y)."""
        self.tiles[y][x].creature_id = None

    def get_creature(self, x: int, y: int) -> str | None:
        """Return the creature ID at (x, y), or None."""
        return self.tiles[y][x].creature_id

    # -- item helpers --------------------------------------------------------

    def place_item(self, x: int, y: int, item_id: str) -> None:
        """Add an item reference to the tile at (x, y)."""
        self.tiles[y][x].items.append(item_id)

    def remove_item(self, x: int, y: int, item_id: str) -> None:
        """Remove an item reference from the tile at (x, y).

        Silently ignores the request if the item is not present.
        """
        try:
            self.tiles[y][x].items.remove(item_id)
        except ValueError:
            pass

    def get_items(self, x: int, y: int) -> list[str]:
        """Return the list of item IDs on the tile at (x, y)."""
        return list(self.tiles[y][x].items)

    # -- querying ------------------------------------------------------------

    def find_terrain(self, terrain: DungeonTerrain) -> list[tuple[int, int]]:
        """Return all (x, y) positions that have the given terrain type."""
        result: list[tuple[int, int]] = []
        for y in range(self.height):
            for x in range(self.width):
                if self.tiles[y][x].terrain == terrain:
                    result.append((x, y))
        return result

    def get_passable_neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        """Return passable cardinal-adjacent positions from (x, y)."""
        neighbors: list[tuple[int, int]] = []
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny) and self.tiles[ny][nx].passable:
                neighbors.append((nx, ny))
        return neighbors

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire level to a JSON-compatible dict."""
        data: dict[str, Any] = {
            "level_id": self.level_id,
            "name": self.name,
            "depth": self.depth,
            "environment": self.environment,
            "width": self.width,
            "height": self.height,
            "tiles": [[t.to_dict() for t in row] for row in self.tiles],
            "stairs_up": [list(pos) for pos in self.stairs_up],
            "stairs_down": [list(pos) for pos in self.stairs_down],
        }
        if self.player_pos is not None:
            data["player_pos"] = list(self.player_pos)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DungeonLevel:
        """Reconstruct a DungeonLevel from a serialized dict."""
        tiles = [
            [DungeonTile.from_dict(td) for td in row]
            for row in data["tiles"]
        ]
        player_pos_raw = data.get("player_pos")
        player_pos = tuple(player_pos_raw) if player_pos_raw is not None else None

        level = cls(
            level_id=data["level_id"],
            name=data["name"],
            depth=data["depth"],
            environment=data.get("environment", ""),
            width=data["width"],
            height=data["height"],
            tiles=tiles,
            player_pos=player_pos,  # type: ignore[arg-type]
            stairs_up=[tuple(p) for p in data.get("stairs_up", [])],  # type: ignore[misc]
            stairs_down=[tuple(p) for p in data.get("stairs_down", [])],  # type: ignore[misc]
        )
        return level


# ---------------------------------------------------------------------------
# Combat terrain bridge
# ---------------------------------------------------------------------------


def dungeon_terrain_to_combat(dt: DungeonTerrain) -> "Terrain":
    """Map a DungeonTerrain value to the combat engine's Terrain enum.

    Returns the closest equivalent combat terrain.  Import is deferred to
    avoid a hard dependency at module level.
    """
    from angband_mechanicum.engine.combat_engine import Terrain

    _MAP: dict[DungeonTerrain, Terrain] = {
        DungeonTerrain.FLOOR:       Terrain.FLOOR,
        DungeonTerrain.WALL:        Terrain.WALL,
        DungeonTerrain.DOOR_OPEN:   Terrain.FLOOR,
        DungeonTerrain.DOOR_CLOSED: Terrain.WALL,
        DungeonTerrain.STAIRS_UP:   Terrain.FLOOR,
        DungeonTerrain.STAIRS_DOWN: Terrain.FLOOR,
        DungeonTerrain.WATER:       Terrain.FLOOR,   # combat Terrain lacks WATER
        DungeonTerrain.LAVA:        Terrain.WALL,
        DungeonTerrain.CHASM:       Terrain.WALL,
        DungeonTerrain.RUBBLE:      Terrain.DEBRIS,
        DungeonTerrain.TERMINAL:    Terrain.TERMINAL,
        DungeonTerrain.COLUMN:      Terrain.WALL,
        DungeonTerrain.GROWTH:      Terrain.FLOOR,
        DungeonTerrain.COVER:       Terrain.DEBRIS,
        DungeonTerrain.GRATE:       Terrain.FLOOR,
        DungeonTerrain.ACID_POOL:   Terrain.WALL,
        DungeonTerrain.SHRINE:      Terrain.TERMINAL,
    }
    return _MAP.get(dt, Terrain.FLOOR)


# ---------------------------------------------------------------------------
# Rendering helper
# ---------------------------------------------------------------------------


def get_terrain_glyph(
    terrain: DungeonTerrain,
    environment: str = "",
) -> TerrainGlyph:
    """Return the display glyph and color for a terrain type.

    If *environment* names a known environment with a color override for
    this terrain, the override color is used with the default character.
    """
    base = _TERRAIN_GLYPHS[terrain]
    if environment and environment in ENVIRONMENTS:
        override_fg = ENVIRONMENTS[environment].color_overrides.get(terrain)
        if override_fg is not None:
            return TerrainGlyph(base.char, override_fg)
    return base
