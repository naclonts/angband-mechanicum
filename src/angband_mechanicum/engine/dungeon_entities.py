"""Dungeon NPC / creature model and placement helpers.

This module keeps the dungeon-entity layer engine-side so map rendering can
consume a small, practical API without pulling UI concerns into the model.
"""

from __future__ import annotations

import enum
import heapq
import random
import zlib
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


@dataclass
class DungeonTurnResult:
    """Structured result of one creature's dungeon turn."""

    entity_id: str
    entity_name: str
    movement_ai: str
    alert_state: str
    action: str
    moved_to: tuple[int, int] | None = None
    attack_damage: int = 0
    attack_range: int = 0
    attacked_player: bool = False
    target_position: tuple[int, int] | None = None
    message: str = ""


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


def _astar_path(
    level: DungeonLevel,
    start: tuple[int, int],
    goal: tuple[int, int],
    occupied: set[tuple[int, int]] | None = None,
    *,
    max_cost: int | None = None,
) -> list[tuple[int, int]]:
    """Return a cheapest path from start to goal, excluding the start tile."""
    if start == goal:
        return []

    occupied = set(occupied or set())
    open_heap: list[tuple[int, int, int, int]] = []
    counter = 0
    heapq.heappush(
        open_heap,
        (abs(goal[0] - start[0]) + abs(goal[1] - start[1]), counter, start[0], start[1]),
    )
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    best_cost: dict[tuple[int, int], int] = {start: 0}

    while open_heap:
        _priority, _count, cx, cy = heapq.heappop(open_heap)
        current = (cx, cy)
        if current == goal:
            path: list[tuple[int, int]] = []
            while current != start:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path

        current_cost = best_cost[current]
        for nx, ny in level.get_passable_neighbors(cx, cy):
            if (nx, ny) in occupied and (nx, ny) != goal:
                continue
            step_cost = max(1, level.get_tile(nx, ny).movement_cost)
            next_cost = current_cost + step_cost
            if max_cost is not None and next_cost > max_cost:
                continue
            seen_cost = best_cost.get((nx, ny))
            if seen_cost is not None and next_cost >= seen_cost:
                continue
            best_cost[(nx, ny)] = next_cost
            came_from[(nx, ny)] = current
            counter += 1
            heuristic = abs(goal[0] - nx) + abs(goal[1] - ny)
            heapq.heappush(open_heap, (next_cost + heuristic, counter, nx, ny))

    return []


def _count_open_neighbors(level: DungeonLevel, position: tuple[int, int]) -> int:
    x, y = position
    count = 0
    for nx, ny in level.get_passable_neighbors(x, y):
        if level.get_tile(nx, ny).passable:
            count += 1
    return count


def _stable_rng(entity: DungeonEntity, *, salt: str = "") -> random.Random:
    seed = zlib.adler32(
        f"{entity.entity_id}:{entity.alert_state}:{entity.alert_turns}:{salt}".encode("utf-8")
    )
    return random.Random(seed)


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
    home_position: tuple[int, int] | None = None
    alert_state: str = "idle"
    alert_turns: int = 0
    last_seen_player_position: tuple[int, int] | None = None
    preferred_range: int | None = None
    history_entity_id: str | None = None
    patrol_route: list[tuple[int, int]] = field(default_factory=list)
    patrol_index: int = 0

    def __post_init__(self) -> None:
        if self.home_position is None and self.position is not None:
            self.home_position = self.position

    @property
    def position(self) -> tuple[int, int] | None:
        if self.x is None or self.y is None:
            return None
        return (self.x, self.y)

    @property
    def follows_player(self) -> bool:
        return self.movement_ai == DungeonMovementAI.FOLLOW_PLAYER

    @property
    def attack_range(self) -> int:
        return self.stats.attack_range

    @property
    def is_ranged(self) -> bool:
        return self.stats.attack_range > 1

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
            "home_position": list(self.home_position) if self.home_position is not None else None,
            "alert_state": self.alert_state,
            "alert_turns": self.alert_turns,
            "last_seen_player_position": (
                list(self.last_seen_player_position)
                if self.last_seen_player_position is not None
                else None
            ),
            "preferred_range": self.preferred_range,
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
            home_position=(
                tuple(data["home_position"])
                if data.get("home_position") is not None
                else None
            ),
            alert_state=str(data.get("alert_state", "idle")),
            alert_turns=int(data.get("alert_turns", 0)),
            last_seen_player_position=(
                tuple(data["last_seen_player_position"])
                if data.get("last_seen_player_position") is not None
                else None
            ),
            preferred_range=(
                int(data["preferred_range"])
                if data.get("preferred_range") is not None
                else None
            ),
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
        if self.home_position is None:
            self.home_position = (x, y)
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
        if self.home_position is None:
            self.home_position = (x, y)
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

    def _update_awareness(
        self,
        level: DungeonLevel,
        player_position: tuple[int, int] | None,
    ) -> bool:
        """Refresh alert state and return whether the player is currently sensed."""
        if self.position is None or player_position is None:
            return False

        current = self.position
        assert current is not None
        player_visible = level.line_of_sight(current, player_position)
        distance = abs(current[0] - player_position[0]) + abs(current[1] - player_position[1])
        sensed = player_visible and distance <= max(6, self.stats.attack_range + 2)

        if self.disposition == DungeonDisposition.HOSTILE:
            if sensed:
                self.alert_state = "engaged"
                self.alert_turns = 0
                self.last_seen_player_position = player_position
            elif self.alert_state == "engaged":
                self.alert_state = "searching"
                self.alert_turns = 1
            elif self.alert_state == "searching":
                self.alert_turns += 1
                if self.alert_turns >= 3:
                    self.alert_state = "idle"
            else:
                self.alert_state = "idle"
        elif self.disposition == DungeonDisposition.FRIENDLY:
            if sensed:
                self.alert_state = "attending"
                self.last_seen_player_position = player_position
            elif self.alert_state == "attending":
                self.alert_state = "idle"
        else:
            if sensed:
                self.alert_state = "observing"
                self.last_seen_player_position = player_position
            elif self.alert_state == "observing":
                self.alert_state = "idle"

        return sensed

    def _choose_wander_step(
        self,
        level: DungeonLevel,
        occupied: set[tuple[int, int]],
        rng: random.Random,
    ) -> tuple[int, int] | None:
        current = self.position
        if current is None:
            return None
        options = [
            pos for pos in level.get_passable_neighbors(*current)
            if pos not in occupied
        ]
        if not options:
            return None

        home = self.home_position or current
        options.sort(
            key=lambda pos: (
                abs(pos[0] - home[0]) + abs(pos[1] - home[1]),
                -_count_open_neighbors(level, pos),
                abs(pos[0] - current[0]) + abs(pos[1] - current[1]),
            )
        )
        if self.movement_ai == DungeonMovementAI.WANDER:
            return rng.choice(options[: min(3, len(options))])
        return options[0]

    def _choose_aggressive_step(
        self,
        level: DungeonLevel,
        player_position: tuple[int, int],
        occupied: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        current = self.position
        if current is None:
            return None
        preferred_range = self.preferred_range
        if preferred_range is None:
            preferred_range = max(2, self.stats.attack_range - 1) if self.is_ranged else 1

        candidates = [
            pos for pos in level.get_passable_neighbors(*current)
            if pos not in occupied
        ]
        if not candidates:
            return None

        best_score = -10_000
        best_positions: list[tuple[int, int]] = []
        for pos in candidates:
            distance = abs(pos[0] - player_position[0]) + abs(pos[1] - player_position[1])
            line_of_sight = level.line_of_sight(pos, player_position)
            score = -abs(distance - preferred_range) * 4
            score += _count_open_neighbors(level, pos)
            if line_of_sight:
                score += 8
            if self.is_ranged and distance > self.stats.attack_range:
                score += 2
            if not self.is_ranged and distance <= 1:
                score += 12
            if self.home_position is not None:
                score -= abs(pos[0] - self.home_position[0]) + abs(pos[1] - self.home_position[1])
            if score > best_score:
                best_score = score
                best_positions = [pos]
            elif score == best_score:
                best_positions.append(pos)

        rng = _stable_rng(self, salt=f"{player_position[0]}:{player_position[1]}")
        return rng.choice(best_positions) if best_positions else None

    def turn_action(
        self,
        level: DungeonLevel,
        *,
        player_position: tuple[int, int] | None,
        occupied: set[tuple[int, int]] | None = None,
        rng: random.Random | None = None,
    ) -> DungeonTurnResult:
        """Resolve the creature's full exploration turn."""
        current = self.position
        if current is None:
            return DungeonTurnResult(
                entity_id=self.entity_id,
                entity_name=self.name,
                movement_ai=self.movement_ai.value,
                alert_state=self.alert_state,
                action="idle",
                message=f"{self.name} is not on the map.",
            )

        occupied = set(occupied or set())
        occupied.discard(current)

        if rng is None:
            rng = _stable_rng(self, salt=f"{current[0]}:{current[1]}")

        sensed = self._update_awareness(level, player_position)
        position_before = current
        action = "idle"
        moved_to: tuple[int, int] | None = None
        attack_damage = 0
        attacked_player = False
        target_position = player_position

        if player_position is None:
            step = self._choose_wander_step(level, occupied, rng)
            if step is not None and step != current:
                moved_to = step
                action = "wander"
        elif self.disposition == DungeonDisposition.HOSTILE:
            distance = abs(current[0] - player_position[0]) + abs(current[1] - player_position[1])
            line_of_sight = level.line_of_sight(current, player_position)
            in_range = distance <= self.stats.attack_range and line_of_sight
            if in_range:
                action = "attack"
                attack_damage = max(1, self.stats.attack)
                attacked_player = True
            else:
                if self.alert_state == "searching" and self.last_seen_player_position is not None:
                    target = self.last_seen_player_position
                else:
                    target = player_position
                if self.is_ranged:
                    moved_to = self._choose_aggressive_step(level, target, occupied)
                    action = "advance" if moved_to is not None else "hold"
                else:
                    path = _astar_path(level, current, target, occupied, max_cost=30)
                    if path and path[0] != player_position:
                        moved_to = path[0]
                        action = "advance"
                    else:
                        moved_to = self._choose_aggressive_step(level, target, occupied)
                        action = "advance" if moved_to is not None else "hold"
        elif self.movement_ai == DungeonMovementAI.FOLLOW_PLAYER:
            distance = abs(current[0] - player_position[0]) + abs(current[1] - player_position[1])
            if distance > 1:
                path = _astar_path(level, current, player_position, occupied, max_cost=20)
                if path:
                    moved_to = path[0]
                    action = "follow"
                else:
                    moved_to = self._choose_aggressive_step(level, player_position, occupied)
                    action = "follow" if moved_to is not None else "hold"
            else:
                action = "guard"
        elif self.movement_ai == DungeonMovementAI.PATROL:
            route = self.patrol_route or ([self.home_position] if self.home_position is not None else [])
            route = [pos for pos in route if pos is not None]
            if route:
                target = route[self.patrol_index % len(route)]
                if current == target:
                    self.patrol_index = (self.patrol_index + 1) % len(route)
                    target = route[self.patrol_index % len(route)]
                path = _astar_path(level, current, target, occupied, max_cost=20)
                if path:
                    moved_to = path[0]
                    action = "patrol"
                else:
                    moved_to = self._choose_wander_step(level, occupied, rng)
                    action = "patrol" if moved_to is not None else "hold"
            else:
                moved_to = self._choose_wander_step(level, occupied, rng)
                action = "patrol" if moved_to is not None else "hold"
        elif self.movement_ai == DungeonMovementAI.WANDER:
            moved_to = self._choose_wander_step(level, occupied, rng)
            action = "wander" if moved_to is not None else "hold"
        else:
            action = "hold"

        message: str
        if attacked_player:
            message = f"{self.name} attacks from {distance} tiles away."
        elif moved_to is not None and moved_to != position_before:
            message = f"{self.name} moves to {moved_to[0]},{moved_to[1]}."
        elif sensed:
            if self.alert_state == "engaged":
                message = f"{self.name} locks onto the player."
            elif self.alert_state == "searching":
                message = f"{self.name} searches the shadows."
            elif self.alert_state == "attending":
                message = f"{self.name} watches the player warily."
            else:
                message = f"{self.name} holds position."
        elif self.movement_ai == DungeonMovementAI.PATROL:
            message = f"{self.name} continues patrol."
        elif self.movement_ai == DungeonMovementAI.FOLLOW_PLAYER:
            message = f"{self.name} keeps pace with the player."
        elif self.movement_ai == DungeonMovementAI.WANDER:
            message = f"{self.name} drifts through the chamber."
        else:
            message = f"{self.name} waits."

        if self.alert_state == "searching" and self.alert_turns >= 3:
            self.alert_state = "idle"

        if moved_to is not None and moved_to != current:
            self.move_to(level, moved_to[0], moved_to[1])
        elif attacked_player:
            # Attack-only turns still refresh the actor's anchor in place.
            self.home_position = self.home_position or current

        return DungeonTurnResult(
            entity_id=self.entity_id,
            entity_name=self.name,
            movement_ai=self.movement_ai.value,
            alert_state=self.alert_state,
            action=action,
            moved_to=moved_to,
            attack_damage=attack_damage,
            attack_range=self.stats.attack_range,
            attacked_player=attacked_player,
            target_position=target_position,
            message=message,
        )

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

        if self.movement_ai == DungeonMovementAI.STATIONARY:
            return None

        if player_position is None:
            if self.movement_ai == DungeonMovementAI.WANDER:
                return self._choose_wander_step(level, occupied, rng or _stable_rng(self))
            if self.movement_ai == DungeonMovementAI.PATROL and self.patrol_route:
                target = self.patrol_route[self.patrol_index % len(self.patrol_route)]
                if current == target:
                    self.patrol_index = (self.patrol_index + 1) % len(self.patrol_route)
                    target = self.patrol_route[self.patrol_index % len(self.patrol_route)]
                return _step_towards(level, current, target, occupied)
            return None

        if self.disposition == DungeonDisposition.HOSTILE:
            if self.is_ranged:
                step = self._choose_aggressive_step(level, player_position, occupied)
                if step is not None and step != current:
                    return step
                return None
            step = _step_towards(level, current, player_position, occupied)
            return None if step == player_position else step

        if self.movement_ai == DungeonMovementAI.FOLLOW_PLAYER:
            distance = abs(current[0] - player_position[0]) + abs(current[1] - player_position[1])
            if distance <= 1:
                return None
            step = _step_towards(level, current, player_position, occupied)
            return None if step == player_position else step

        if self.movement_ai == DungeonMovementAI.PATROL and self.patrol_route:
            target = self.patrol_route[self.patrol_index % len(self.patrol_route)]
            if current == target:
                self.patrol_index = (self.patrol_index + 1) % len(self.patrol_route)
                target = self.patrol_route[self.patrol_index % len(self.patrol_route)]
            return _step_towards(level, current, target, occupied)

        if self.movement_ai == DungeonMovementAI.WANDER:
            return self._choose_wander_step(level, occupied, rng or _stable_rng(self))

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
