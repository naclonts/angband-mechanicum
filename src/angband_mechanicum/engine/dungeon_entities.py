"""Dungeon NPC / creature model and placement helpers.

This module keeps the dungeon-entity layer engine-side so map rendering can
consume a small, practical API without pulling UI concerns into the model.
"""

from __future__ import annotations

import enum
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from angband_mechanicum.engine.combat_engine import CombatStats, PARTY_TEMPLATES
from angband_mechanicum.engine.dungeon_level import DungeonLevel
from angband_mechanicum.engine.history import EntityType, GameHistory


class DungeonDisposition(enum.Enum):
    """How a dungeon entity should behave toward the player."""

    FRIENDLY = "friendly"
    HOSTILE = "hostile"
    NEUTRAL = "neutral"


class DungeonMovementAI(enum.Enum):
    """High-level movement behavior for a dungeon entity."""

    STATIONARY = "stationary"
    WANDER = "wander"
    PATROL = "patrol"
    AGGRESSIVE = "aggressive"
    FOLLOW_PLAYER = "follow_player"


_DEFAULT_PORTRAIT_KEYS: dict[str, str] = {
    "servo-skull": "cyber_cherub",
    "servo": "cyber_cherub",
    "skull": "cyber_cherub",
    "alpha": "skitarii",
    "skitarii": "skitarii",
    "volta": "enginseer",
    "enginseer": "enginseer",
    "servitor": "servitor",
    "magos": "magos",
    "adept": "mechanicus_adept",
    "mechanicus": "mechanicus_adept",
    "assassin": "tech_assassin",
    "cherub": "cyber_cherub",
    "slave": "pit_slave",
    "priest": "electro_priest",
}

_DEFAULT_PARTY_DESCRIPTIONS: dict[str, str] = {
    "servo-skull": "A hovering servo-skull fitted with auspex lenses and a crackling vox-grille",
    "skitarius-alpha-7": "A battle-scarred ranger with a galvanic rifle",
    "enginseer-volta": "Young, eager, still more flesh than machine, carries a power axe",
}


def infer_portrait_key(name: str, description: str) -> str:
    """Pick a portrait template key from the entity name and description."""
    combined = f"{name} {description}".lower()
    for keyword, portrait_key in _DEFAULT_PORTRAIT_KEYS.items():
        if keyword in combined:
            return portrait_key
    return "mechanicus_adept"


def _step_towards(
    level: DungeonLevel,
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: set[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    """Return the next step on a shortest path from start to goal."""
    if start == goal:
        return start

    blocked = blocked or set()
    queue: deque[tuple[int, int]] = deque([start])
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while queue:
        current = queue.popleft()
        if current == goal:
            break
        for neighbor in level.get_passable_neighbors(*current):
            if neighbor in came_from:
                continue
            if neighbor in blocked and neighbor != goal:
                continue
            came_from[neighbor] = current
            queue.append(neighbor)

    if goal not in came_from:
        return None

    current = goal
    while came_from[current] != start:
        parent = came_from[current]
        if parent is None:
            return None
        current = parent
    return current


@dataclass
class DungeonEntity:
    """A creature or NPC that can occupy a dungeon level tile."""

    entity_id: str
    name: str
    disposition: DungeonDisposition
    movement_ai: DungeonMovementAI
    can_talk: bool
    portrait_key: str
    stats: CombatStats
    description: str = ""
    x: int | None = None
    y: int | None = None
    history_entity_id: str | None = None
    patrol_route: list[tuple[int, int]] = field(default_factory=list)
    patrol_index: int = 0

    @property
    def position(self) -> tuple[int, int] | None:
        if self.x is None or self.y is None:
            return None
        return (self.x, self.y)

    @property
    def follows_player(self) -> bool:
        return self.movement_ai == DungeonMovementAI.FOLLOW_PLAYER

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "disposition": self.disposition.value,
            "movement_ai": self.movement_ai.value,
            "can_talk": self.can_talk,
            "portrait_key": self.portrait_key,
            "stats": self.stats.to_dict(),
            "description": self.description,
            "x": self.x,
            "y": self.y,
            "history_entity_id": self.history_entity_id,
            "patrol_route": [list(pos) for pos in self.patrol_route],
            "patrol_index": self.patrol_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DungeonEntity:
        return cls(
            entity_id=data["entity_id"],
            name=data["name"],
            disposition=DungeonDisposition(data["disposition"]),
            movement_ai=DungeonMovementAI(data["movement_ai"]),
            can_talk=data["can_talk"],
            portrait_key=data["portrait_key"],
            stats=CombatStats.from_dict(data["stats"]),
            description=data.get("description", ""),
            x=data.get("x"),
            y=data.get("y"),
            history_entity_id=data.get("history_entity_id"),
            patrol_route=[tuple(pos) for pos in data.get("patrol_route", [])],
            patrol_index=data.get("patrol_index", 0),
        )

    def place(self, level: DungeonLevel, x: int, y: int) -> None:
        """Place the entity on the level and remember its coordinates."""
        level.place_creature(x, y, self.entity_id)
        self.x = x
        self.y = y

    def remove_from_level(self, level: DungeonLevel) -> None:
        """Remove the entity from its current tile, if any."""
        if self.position is None:
            return
        x = self.x
        y = self.y
        if x is None or y is None:
            return
        level.remove_creature(x, y)
        self.x = None
        self.y = None

    def move_to(self, level: DungeonLevel, x: int, y: int) -> None:
        """Move the entity to a new tile, updating the level reference."""
        if self.position is not None:
            old_x = self.x
            old_y = self.y
            if old_x is not None and old_y is not None:
                level.remove_creature(old_x, old_y)
        level.place_creature(x, y, self.entity_id)
        self.x = x
        self.y = y

    def register_with_history(self, history: GameHistory) -> str:
        """Register or update the matching history entity."""
        entity = history.register_entity(
            name=self.name,
            entity_type=EntityType.CHARACTER,
            description=self.description or self.name,
        )
        self.history_entity_id = entity.id
        return entity.id

    def intended_step(
        self,
        level: DungeonLevel,
        *,
        player_position: tuple[int, int] | None = None,
        occupied: set[tuple[int, int]] | None = None,
        rng: random.Random | None = None,
    ) -> tuple[int, int] | None:
        """Return the next tile the entity intends to move to."""
        current = self.position
        if current is None:
            return None

        occupied = set(occupied or set())
        occupied.discard(current)
        if player_position is not None:
            occupied.discard(player_position)

        if self.movement_ai == DungeonMovementAI.STATIONARY:
            return None

        if self.movement_ai == DungeonMovementAI.WANDER:
            rng = rng or random.Random()
            options = [
                pos for pos in level.get_passable_neighbors(*current)
                if pos not in occupied
            ]
            if not options:
                return None
            return rng.choice(options)

        if self.movement_ai == DungeonMovementAI.PATROL:
            if not self.patrol_route:
                return None
            target = self.patrol_route[self.patrol_index % len(self.patrol_route)]
            if current == target:
                self.patrol_index = (self.patrol_index + 1) % len(self.patrol_route)
                target = self.patrol_route[self.patrol_index % len(self.patrol_route)]
            return _step_towards(level, current, target, occupied)

        if self.movement_ai in (DungeonMovementAI.AGGRESSIVE, DungeonMovementAI.FOLLOW_PLAYER):
            if player_position is None:
                return None
            return _step_towards(level, current, player_position, occupied)

        return None


@dataclass
class DungeonEntityRoster:
    """Mutable collection of dungeon entities and placement helpers."""

    entities: dict[str, DungeonEntity] = field(default_factory=dict)

    def add(self, entity: DungeonEntity) -> DungeonEntity:
        self.entities[entity.entity_id] = entity
        return entity

    def get(self, entity_id: str) -> DungeonEntity | None:
        return self.entities.get(entity_id)

    def values(self) -> list[DungeonEntity]:
        return list(self.entities.values())

    def to_dict(self) -> dict[str, Any]:
        return {"entities": [entity.to_dict() for entity in self.values()]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DungeonEntityRoster:
        roster = cls()
        for entry in data.get("entities", []):
            roster.add(DungeonEntity.from_dict(entry))
        return roster

    def register_with_history(self, history: GameHistory) -> list[str]:
        """Ensure all roster entities exist in the history registry."""
        history_ids: list[str] = []
        for entity in self.values():
            history_ids.append(entity.register_with_history(history))
        return history_ids

    def place(self, level: DungeonLevel, entity_id: str, x: int, y: int) -> bool:
        entity = self.get(entity_id)
        if entity is None or not level.in_bounds(x, y):
            return False
        if not level.get_tile(x, y).passable or level.get_creature(x, y) is not None:
            return False
        if entity.position is not None:
            entity.remove_from_level(level)
        entity.place(level, x, y)
        return True

    def remove(self, level: DungeonLevel, entity_id: str) -> bool:
        entity = self.get(entity_id)
        if entity is None or entity.position is None:
            return False
        entity.remove_from_level(level)
        return True

    def move(
        self,
        level: DungeonLevel,
        entity_id: str,
        x: int,
        y: int,
    ) -> bool:
        entity = self.get(entity_id)
        if entity is None or entity.position is None:
            return False
        if not level.in_bounds(x, y):
            return False
        if not level.get_tile(x, y).passable:
            return False
        occupant = level.get_creature(x, y)
        if occupant is not None and occupant != entity_id:
            return False
        entity.move_to(level, x, y)
        return True

    def place_near_player(
        self,
        level: DungeonLevel,
        entity_id: str,
        player_position: tuple[int, int],
        occupied: set[tuple[int, int]] | None = None,
    ) -> bool:
        """Place an entity adjacent to the player if possible."""
        entity = self.get(entity_id)
        if entity is None:
            return False

        blocked = set(occupied or set())
        blocked.add(player_position)

        candidates = [
            pos for pos in level.get_passable_neighbors(*player_position)
            if pos not in blocked and level.get_creature(*pos) is None
        ]
        if not candidates:
            candidates = [
                (x, y)
                for y in range(level.height)
                for x in range(level.width)
                if level.get_tile(x, y).passable and (x, y) not in blocked and level.get_creature(x, y) is None
            ]
        if not candidates:
            return False

        rng = random.Random(entity.entity_id)
        target = rng.choice(candidates)
        return self.place(level, entity_id, target[0], target[1])

    def place_followers(
        self,
        level: DungeonLevel,
        player_position: tuple[int, int],
        entity_ids: list[str] | None = None,
        occupied: set[tuple[int, int]] | None = None,
    ) -> list[DungeonEntity]:
        """Place a list of follower entities around the player."""
        placed: list[DungeonEntity] = []
        ids = entity_ids or [eid for eid in self.entities if self.entities[eid].follows_player]
        used = set(occupied or set())
        used.add(player_position)
        for entity_id in ids:
            if self.place_near_player(level, entity_id, player_position, used):
                entity = self.entities[entity_id]
                if entity.position is not None:
                    used.add(entity.position)
                placed.append(entity)
        return placed

    def step_entity(
        self,
        level: DungeonLevel,
        entity_id: str,
        *,
        player_position: tuple[int, int] | None = None,
        occupied: set[tuple[int, int]] | None = None,
        rng: random.Random | None = None,
    ) -> bool:
        """Advance one entity according to its movement AI."""
        entity = self.get(entity_id)
        if entity is None:
            return False
        target = entity.intended_step(
            level,
            player_position=player_position,
            occupied=occupied,
            rng=rng,
        )
        if target is None:
            return False
        return self.move(level, entity_id, target[0], target[1])


def make_dungeon_party_member(entity_id: str) -> DungeonEntity:
    """Build a dungeon entity for a seeded party member."""
    tpl = PARTY_TEMPLATES[entity_id]
    description = _DEFAULT_PARTY_DESCRIPTIONS.get(entity_id, tpl["name"])
    return DungeonEntity(
        entity_id=entity_id,
        name=tpl["name"],
        disposition=DungeonDisposition.FRIENDLY,
        movement_ai=DungeonMovementAI.FOLLOW_PLAYER,
        can_talk=entity_id != "servo-skull",
        portrait_key=infer_portrait_key(tpl["name"], description),
        stats=CombatStats(**tpl["stats"]),
        description=description,
    )


def make_dungeon_party_roster() -> DungeonEntityRoster:
    """Create a roster containing the default party followers."""
    roster = DungeonEntityRoster()
    for entity_id in ("servo-skull",):
        roster.add(make_dungeon_party_member(entity_id))
    return roster
