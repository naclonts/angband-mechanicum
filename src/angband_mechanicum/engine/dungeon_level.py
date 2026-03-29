"""Persistent tile-map data model for exploration-scale dungeons.

Defines terrain types, fog-of-war state, and a ``DungeonLevel`` grid that
supports item/creature placement, FOV helpers, and full serialization.

This is a **data model** -- no generation or rendering logic lives here.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


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
# Fog of war
# ---------------------------------------------------------------------------


class FogState(enum.Enum):
    """Per-tile visibility state for fog-of-war."""

    HIDDEN = "hidden"        # Never seen
    EXPLORED = "explored"    # Seen before, not currently visible
    VISIBLE = "visible"      # In current field-of-view


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
