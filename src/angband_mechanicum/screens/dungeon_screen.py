"""Unified dungeon exploration screen."""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual import work

from angband_mechanicum.engine.dungeon_entities import (
    DungeonDisposition,
    DungeonEntity,
    DungeonEntityRoster,
    DungeonMovementAI,
    DungeonTurnResult,
)
from angband_mechanicum.engine.combat_engine import CombatStats
from angband_mechanicum.engine.dungeon_gen import (
    EnvironmentDebugEntry,
    GeneratedFloor,
    build_environment_debug_catalog,
    generate_dungeon_floor,
)
from angband_mechanicum.engine.dungeon_items import DungeonItem, build_item_instance
from angband_mechanicum.engine.dungeon_level import (
    DungeonLevel,
    DungeonTerrain,
    FogState,
    hazard_damage_for_terrain,
    is_transition_terrain,
    transition_terrain_label,
)
from angband_mechanicum.engine.history import EntityType
from angband_mechanicum.engine.save_manager import SaveManager
from angband_mechanicum.widgets.dungeon_map import (
    DungeonMapEntity,
    DungeonMapPane,
    DungeonMessageLog,
    DungeonTransitionPane,
    DungeonStatusPane,
)
from angband_mechanicum.widgets.help_overlay import HelpOverlay

logger = logging.getLogger(__name__)


def _comma_list(items: Sequence[str], *, limit: int = 4) -> str:
    if not items:
        return "none"
    visible = list(items[:limit])
    suffix = "" if len(items) <= limit else f", +{len(items) - limit} more"
    return ", ".join(visible) + suffix


def _symbol_for_dungeon_entity(entity: DungeonEntity) -> str:
    for char in entity.name:
        if char.isalnum():
            return char.upper()
    return "?"


def build_map_entities_from_roster(roster: DungeonEntityRoster) -> list[DungeonMapEntity]:
    """Convert generated dungeon contacts into the lightweight map overlay model."""
    entities: list[DungeonMapEntity] = []
    for entity in roster.values():
        if entity.position is None:
            continue
        x, y = entity.position
        entities.append(
            DungeonMapEntity(
                entity_id=entity.entity_id,
                name=entity.name,
                x=x,
                y=y,
                symbol=_symbol_for_dungeon_entity(entity),
                disposition=entity.disposition.value,
                can_talk=entity.can_talk,
                entity_type="character",
                hp=entity.stats.hp,
                max_hp=entity.stats.max_hp,
                attack=entity.stats.attack,
                movement=entity.stats.movement,
                attack_range=entity.stats.attack_range,
                armor=entity.stats.armor,
                description=entity.description,
                history_entity_id=entity.history_entity_id,
                movement_ai=entity.movement_ai.value,
                home_position=entity.home_position or (x, y),
                alert_state=entity.alert_state,
                alert_turns=entity.alert_turns,
                last_seen_player_position=entity.last_seen_player_position,
                preferred_range=entity.preferred_range,
                patrol_route=list(entity.patrol_route),
                patrol_index=entity.patrol_index,
            )
        )
    return entities


class DungeonInteractionKind(enum.Enum):
    """High-level outcomes of trying to step into a tile."""

    MOVE = "move"
    DOOR = "door"
    ATTACK = "attack"
    CONVERSATION = "conversation"
    OBJECT = "object"
    TRANSITION = "transition"
    NEUTRAL = "neutral"
    ITEM = "item"
    BLOCKED = "blocked"


@dataclass
class DungeonActionResult:
    """Result of a move or bump interaction."""

    kind: DungeonInteractionKind
    message: str
    door_position: tuple[int, int] | None = None
    door_state: str | None = None
    target_entity_id: str | None = None
    target_entity_name: str | None = None
    target_entity_type: str | None = None
    target_disposition: str | None = None
    attack_damage: int = 0
    target_defeated: bool = False
    ranged_attack: bool = False
    player_damage: int = 0
    moved_to: tuple[int, int] | None = None
    scene_art: str | None = None
    speaking_npc_id: str | None = None
    item_instance_id: str | None = None
    item_display_name: str | None = None
    player_healing: int = 0
    interaction_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class DungeonMapState:
    """Mutable dungeon exploration state owned by the screen."""

    level: DungeonLevel
    player_pos: tuple[int, int] | None = None
    fov_radius: int = 8
    player_attack: int = 4
    player_attack_range: int = 8
    entities: list[DungeonMapEntity] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    item_entities: dict[str, DungeonItem] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.player_pos is None:
            self.player_pos = self.level.player_pos
        if self.player_pos is None and self.level.stairs_up:
            self.player_pos = self.level.stairs_up[0]
        if self.player_pos is None:
            self.player_pos = self._first_passable_tile()
        self._apply_position()
        self._hydrate_item_entities()
        self.recompute_fov()

    def _first_passable_tile(self) -> tuple[int, int]:
        for y in range(self.level.height):
            for x in range(self.level.width):
                if self.level.get_tile(x, y).passable:
                    return (x, y)
        return (0, 0)

    def _apply_position(self) -> None:
        assert self.player_pos is not None
        self.level.player_pos = self.player_pos

    def append_message(self, text: str) -> None:
        self.messages.append(text)

    def _hydrate_item_entities(self) -> None:
        known_ids = set(self.item_entities)
        for y in range(self.level.height):
            for x in range(self.level.width):
                tile = self.level.get_tile(x, y)
                resolved_ids: list[str] = []
                for slot, raw_item_id in enumerate(list(tile.items)):
                    item_id = str(raw_item_id)
                    if item_id in self.item_entities:
                        resolved_ids.append(item_id)
                        known_ids.add(item_id)
                        continue
                    instance_id = f"{self.level.level_id}:{x}:{y}:{slot}:{item_id}"
                    counter = 1
                    while instance_id in known_ids:
                        counter += 1
                        instance_id = f"{self.level.level_id}:{x}:{y}:{slot}:{item_id}:{counter}"
                    self.item_entities[instance_id] = build_item_instance(
                        item_id,
                        instance_id=instance_id,
                    )
                    known_ids.add(instance_id)
                    resolved_ids.append(instance_id)
                tile.items = resolved_ids

    def item_at_id(self, item_id: str) -> DungeonItem | None:
        return self.item_entities.get(item_id)

    def item_display_name(self, item_id: str) -> str:
        item = self.item_at_id(item_id)
        if item is None:
            return item_id.replace("_", " ").replace("-", " ").title()
        return item.display_name

    def item_names_at(self, position: tuple[int, int]) -> list[str]:
        x, y = position
        return [self.item_display_name(item_id) for item_id in self.level.get_items(x, y)]

    def inventory_items(self) -> list[DungeonItem]:
        items: list[DungeonItem] = []
        for item_id in self.inventory:
            item = self.item_at_id(item_id)
            if item is not None:
                items.append(item)
        return items

    def next_usable_inventory_item(self) -> DungeonItem | None:
        for item in self.inventory_items():
            if item.usable:
                return item
        return None

    def _tile_is_visible(self, position: tuple[int, int] | None) -> bool:
        if position is None:
            return False
        x, y = position
        return self.level.in_bounds(x, y) and self.level.get_tile(x, y).fog == FogState.VISIBLE

    def _should_log_turn_result(
        self,
        current_position: tuple[int, int] | None,
        result: DungeonTurnResult,
    ) -> bool:
        if self._tile_is_visible(current_position):
            return True
        return self._tile_is_visible(result.moved_to)

    def build_examine_context(self, position: tuple[int, int]) -> dict[str, Any]:
        """Build a structured context payload for a look/examine action."""
        x, y = position
        tile = self.level.get_tile(x, y)
        entity = self.entity_at(position)
        terrain = self.level.get_terrain(x, y)
        visible = tile.fog == FogState.VISIBLE

        surroundings: dict[str, str] = {}
        for dx, dy, label in ((0, -1, "north"), (0, 1, "south"), (-1, 0, "west"), (1, 0, "east")):
            nx, ny = x + dx, y + dy
            if self.level.in_bounds(nx, ny):
                surroundings[label] = self.level.get_terrain(nx, ny).value

        context: dict[str, Any] = {
            "target_position": [x, y],
            "player_position": list(self.player_pos) if self.player_pos is not None else None,
            "distance_from_player": (
                abs(self.player_pos[0] - x) + abs(self.player_pos[1] - y)
                if self.player_pos is not None
                else None
            ),
            "target_visible": visible,
            "terrain": terrain.value,
            "terrain_passable": tile.passable,
            "terrain_transparent": tile.transparent,
            "item_instance_ids": list(tile.items),
            "items": self.item_names_at(position),
            "creature_id": tile.creature_id,
            "surroundings": surroundings,
        }
        if entity is not None:
            context.update(
                {
                    "target_kind": entity.entity_type,
                    "target_label": entity.name,
                    "target_entity_id": entity.entity_id,
                    "target_entity_name": entity.name,
                    "target_entity_type": entity.entity_type,
                    "target_disposition": entity.disposition,
                    "target_can_talk": entity.can_talk,
                    "target_description": entity.description,
                    "target_scene_art": entity.scene_art,
                    "target_hp": entity.hp,
                    "target_max_hp": entity.max_hp,
                }
            )
        else:
            context["target_kind"] = "terrain"
            context["target_label"] = terrain.value.replace("_", " ").title()
        item_names = self.item_names_at(position)
        if item_names:
            context["item_summary"] = _comma_list(item_names)
            if entity is None and len(item_names) == 1:
                context["target_kind"] = "item"
                context["target_label"] = item_names[0]
                item = self.item_at_id(tile.items[0])
                if item is not None:
                    context["target_description"] = item.description
            elif entity is None:
                context["target_kind"] = "item"
                context["target_label"] = f"{len(item_names)} cached items"
            else:
                context["target_label"] = (
                    f"{context.get('target_label', terrain.value)} with {_comma_list(item_names, limit=2)}"
                )
        if tile.creature_id and entity is None:
            context["target_kind"] = "creature"
            context["target_label"] = f"Creature marker at {x},{y}"
        return context

    def get_look_summary(self, position: tuple[int, int]) -> str:
        """Return a short one-line summary for the current look target."""
        context = self.build_examine_context(position)
        label = str(context.get("target_label", "Unknown"))
        if not context.get("target_visible", False):
            return f"{label} is not currently visible."
        if context.get("target_kind") == "character":
            disposition = context.get("target_disposition", "neutral")
            return f"{label} ({disposition})"
        if context.get("target_kind") == "object":
            return f"{label} (object)"
        return label

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.to_dict(),
            "player_pos": list(self.player_pos) if self.player_pos is not None else None,
            "fov_radius": self.fov_radius,
            "player_attack": self.player_attack,
            "player_attack_range": self.player_attack_range,
            "entities": [entity.to_dict() for entity in self.entities],
            "inventory": list(self.inventory),
            "item_entities": {
                item_id: item.to_dict() for item_id, item in self.item_entities.items()
            },
            "messages": list(self.messages),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DungeonMapState:
        from angband_mechanicum.engine.dungeon_level import DungeonLevel

        level = DungeonLevel.from_dict(data["level"])
        player_pos_raw = data.get("player_pos")
        player_pos = tuple(player_pos_raw) if player_pos_raw is not None else None
        return cls(
            level=level,
            player_pos=player_pos,
            fov_radius=int(data.get("fov_radius", 8)),
            player_attack=int(data.get("player_attack", 4)),
            player_attack_range=int(data.get("player_attack_range", 8)),
            entities=[
                DungeonMapEntity.from_dict(entity_data)
                for entity_data in data.get("entities", [])
            ],
            inventory=[str(item_id) for item_id in data.get("inventory", [])],
            item_entities={
                str(item_id): DungeonItem.from_dict(item_data)
                for item_id, item_data in data.get("item_entities", {}).items()
            },
            messages=[str(message) for message in data.get("messages", [])],
        )

    def entity_at(self, position: tuple[int, int]) -> DungeonMapEntity | None:
        for entity in self.entities:
            if entity.alive and (entity.x, entity.y) == position:
                return entity
        return None

    def remove_entity(self, entity_id: str) -> bool:
        for index, entity in enumerate(self.entities):
            if entity.entity_id == entity_id:
                del self.entities[index]
                return True
        return False

    def recompute_fov(self) -> None:
        assert self.player_pos is not None
        self.level.compute_fov(self.player_pos, self.fov_radius)

    def _move_player_to(self, position: tuple[int, int]) -> None:
        self.player_pos = position
        self._apply_position()
        self.recompute_fov()

    def _is_adjacent_to_player(self, position: tuple[int, int]) -> bool:
        assert self.player_pos is not None
        px, py = self.player_pos
        return abs(position[0] - px) + abs(position[1] - py) == 1

    def _door_action_result(
        self,
        position: tuple[int, int],
        *,
        open_door: bool,
    ) -> DungeonActionResult:
        assert self.player_pos is not None
        x, y = position
        if not self.level.in_bounds(x, y):
            message = "The doorway is beyond the map edge."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        if not self._is_adjacent_to_player(position):
            message = "That door is out of reach."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        if self.entity_at(position) is not None or self.level.get_creature(x, y) is not None:
            message = "A contact blocks the doorway."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)

        terrain = self.level.get_terrain(x, y)
        if open_door:
            if terrain == DungeonTerrain.DOOR_OPEN:
                message = "The door is already open."
                self.append_message(message)
                return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
            if terrain != DungeonTerrain.DOOR_CLOSED:
                message = "That is not a closed door."
                self.append_message(message)
                return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
            self.level.open_door(x, y)
            self.recompute_fov()
            message = "You open the door."
            self.append_message(message)
            return DungeonActionResult(
                kind=DungeonInteractionKind.DOOR,
                message=message,
                door_position=position,
                door_state="open",
                moved_to=self.player_pos,
            )

        if terrain == DungeonTerrain.DOOR_CLOSED:
            message = "The door is already closed."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        if terrain != DungeonTerrain.DOOR_OPEN:
            message = "That is not an open door."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        self.level.close_door(x, y)
        self.recompute_fov()
        message = "You close the door."
        self.append_message(message)
        return DungeonActionResult(
            kind=DungeonInteractionKind.DOOR,
            message=message,
            door_position=position,
            door_state="closed",
            moved_to=self.player_pos,
        )

    def open_door_at(self, position: tuple[int, int]) -> DungeonActionResult:
        """Open a closed door adjacent to the player."""
        return self._door_action_result(position, open_door=True)

    def close_door_at(self, position: tuple[int, int]) -> DungeonActionResult:
        """Close an open door adjacent to the player."""
        return self._door_action_result(position, open_door=False)

    def distance_from_player(self, position: tuple[int, int]) -> int:
        assert self.player_pos is not None
        return abs(self.player_pos[0] - position[0]) + abs(self.player_pos[1] - position[1])

    def move_player(self, dx: int, dy: int) -> bool:
        return self.attempt_step(dx, dy).kind != DungeonInteractionKind.BLOCKED

    def _attack_entity(self, entity: DungeonMapEntity) -> DungeonActionResult:
        assert self.player_pos is not None
        damage = max(1, self.player_attack - entity.armor)
        entity.hp = max(0, entity.hp - damage)
        message = f"You strike {entity.name} for {damage} damage."
        target_defeated = entity.hp == 0
        if target_defeated:
            self.remove_entity(entity.entity_id)
            self.level.remove_creature(entity.x, entity.y)
            message = f"{message} {entity.name} is destroyed."
        else:
            message = (
                f"{message} {entity.name} reels with "
                f"{entity.hp}/{entity.max_hp} integrity remaining."
            )
        self.append_message(message)
        return DungeonActionResult(
            kind=DungeonInteractionKind.ATTACK,
            message=message,
            target_entity_id=entity.entity_id,
            target_entity_name=entity.name,
            target_entity_type=entity.entity_type,
            target_disposition=entity.disposition,
            attack_damage=damage,
            target_defeated=target_defeated,
            moved_to=self.player_pos if target_defeated else None,
        )

    def attempt_ranged_attack(self, position: tuple[int, int]) -> DungeonActionResult:
        assert self.player_pos is not None
        x, y = position
        if not self.level.in_bounds(x, y):
            message = "The targeting reticle cannot leave the map."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        if self.level.get_tile(x, y).fog != FogState.VISIBLE:
            message = "That target is not visible."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)

        entity = self.entity_at(position)
        if entity is None or entity.disposition != "hostile":
            message = "No hostile target is locked there."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)

        distance = self.distance_from_player(position)
        if distance > self.player_attack_range:
            message = f"Target out of range ({distance}/{self.player_attack_range})."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        if not self.level.line_of_sight(self.player_pos, position):
            message = "No line of sight to target."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)

        damage = max(1, self.player_attack - entity.armor)
        entity.hp = max(0, entity.hp - damage)
        message = f"You shoot {entity.name} for {damage} damage."
        target_defeated = entity.hp == 0
        if target_defeated:
            self.remove_entity(entity.entity_id)
            self.level.remove_creature(entity.x, entity.y)
            message = f"{message} {entity.name} is destroyed."
        else:
            message = (
                f"{message} {entity.name} staggers with "
                f"{entity.hp}/{entity.max_hp} integrity remaining."
            )
        self.append_message(message)
        result = DungeonActionResult(
            kind=DungeonInteractionKind.ATTACK,
            message=message,
            target_entity_id=entity.entity_id,
            target_entity_name=entity.name,
            target_entity_type=entity.entity_type,
            target_disposition=entity.disposition,
            attack_damage=damage,
            target_defeated=target_defeated,
            ranged_attack=True,
        )
        result.interaction_context = self._register_interaction_context(
            entity,
            DungeonInteractionKind.ATTACK,
        )
        return result

    def _conversation_result(self, entity: DungeonMapEntity) -> DungeonActionResult:
        message = f"You address {entity.name}."
        self.append_message(message)
        return DungeonActionResult(
            kind=DungeonInteractionKind.CONVERSATION,
            message=message,
            target_entity_id=entity.entity_id,
            target_entity_name=entity.name,
            target_entity_type=entity.entity_type,
            target_disposition=entity.disposition,
            scene_art=entity.scene_art,
        )

    def _object_result(self, entity: DungeonMapEntity) -> DungeonActionResult:
        message = f"You inspect {entity.name}."
        self.append_message(message)
        return DungeonActionResult(
            kind=DungeonInteractionKind.OBJECT,
            message=message,
            target_entity_id=entity.entity_id,
            target_entity_name=entity.name,
            target_entity_type=entity.entity_type,
            target_disposition=entity.disposition,
            scene_art=entity.scene_art,
        )

    def _neutral_result(self, entity: DungeonMapEntity) -> DungeonActionResult:
        message = f"You note {entity.name} but leave it undisturbed."
        self.append_message(message)
        return DungeonActionResult(
            kind=DungeonInteractionKind.NEUTRAL,
            message=message,
            target_entity_id=entity.entity_id,
            target_entity_name=entity.name,
            target_entity_type=entity.entity_type,
            target_disposition=entity.disposition,
        )

    def _register_interaction_context(
        self,
        entity: DungeonMapEntity,
        kind: DungeonInteractionKind,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "interaction_kind": kind.value,
            "interaction_entity_id": entity.entity_id,
            "interaction_entity_name": entity.name,
            "interaction_entity_type": entity.entity_type,
            "interaction_entity_disposition": entity.disposition,
        }
        if entity.description:
            context["interaction_entity_description"] = entity.description
        if entity.scene_art:
            context["interaction_scene_art"] = entity.scene_art
        if self.player_pos is not None:
            context["map_return_pos"] = list(self.player_pos)
        return context

    def attempt_step(self, dx: int, dy: int) -> DungeonActionResult:
        assert self.player_pos is not None
        nx = self.player_pos[0] + dx
        ny = self.player_pos[1] + dy
        if not self.level.in_bounds(nx, ny):
            message = "The void lies beyond the map edge."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        entity = self.entity_at((nx, ny))
        if entity is None and self.level.get_creature(nx, ny) is not None:
            message = "Contact at the destination blocks movement."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        if entity is not None:
            if entity.disposition == "hostile":
                result = self._attack_entity(entity)
                result.interaction_context = self._register_interaction_context(
                    entity,
                    DungeonInteractionKind.ATTACK,
                )
                return result
            if entity.entity_type == "object":
                result = self._object_result(entity)
                result.interaction_context = self._register_interaction_context(
                    entity,
                    DungeonInteractionKind.OBJECT,
                )
                return result
            if entity.can_talk or entity.disposition == "friendly":
                result = self._conversation_result(entity)
                result.speaking_npc_id = entity.history_entity_id
                result.interaction_context = self._register_interaction_context(
                    entity,
                    DungeonInteractionKind.CONVERSATION,
                )
                return result
            result = self._neutral_result(entity)
            result.interaction_context = self._register_interaction_context(
                entity,
                DungeonInteractionKind.NEUTRAL,
            )
            return result
        terrain_type = self.level.get_terrain(nx, ny)
        if terrain_type == DungeonTerrain.DOOR_CLOSED:
            return self.open_door_at((nx, ny))
        if not self.level.get_tile(nx, ny).passable:
            if terrain_type == DungeonTerrain.DOOR_OPEN:
                terrain_name = "Open door"
            else:
                terrain_name = terrain_type.value.replace("_", " ").title()
            message = f"{terrain_name} blocks the route."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        self._move_player_to((nx, ny))
        if is_transition_terrain(terrain_type):
            direction = "deeper" if (nx, ny) in self.level.stairs_down else "upward"
            message = (
                f"You step onto the {transition_terrain_label(terrain_type)} "
                f"and feel it carry you {direction}."
            )
            self.append_message(message)
            return DungeonActionResult(
                kind=DungeonInteractionKind.TRANSITION,
                message=message,
                moved_to=(nx, ny),
            )
        terrain = terrain_type.value.replace("_", " ").title()
        hazard_damage = hazard_damage_for_terrain(terrain_type)
        if terrain_type == DungeonTerrain.ACID_POOL:
            hazard_text = f" Corrosive acid burns you for {hazard_damage} damage."
        elif terrain_type == DungeonTerrain.LAVA:
            hazard_text = f" Molten lava scorches you for {hazard_damage} damage."
        else:
            hazard_text = ""
        item_names = self.item_names_at((nx, ny))
        item_text = ""
        if item_names:
            item_text = f" You spot {_comma_list(item_names)} here."
        message = f"You move to {nx},{ny} across {terrain}.{hazard_text}{item_text}"
        self.append_message(message)
        return DungeonActionResult(
            kind=DungeonInteractionKind.MOVE,
            message=message,
            player_damage=hazard_damage,
            moved_to=(nx, ny),
        )

    def visible_entity_positions(self) -> set[tuple[int, int]]:
        """Return positions of all alive entities currently visible."""
        positions: set[tuple[int, int]] = set()
        for entity in self.entities:
            if not entity.alive:
                continue
            if self.level.get_tile(entity.x, entity.y).fog == FogState.VISIBLE:
                positions.add((entity.x, entity.y))
        return positions

    def visible_item_positions(self) -> set[tuple[int, int]]:
        """Return positions of tiles with items currently visible."""
        positions: set[tuple[int, int]] = set()
        for y in range(self.level.height):
            for x in range(self.level.width):
                tile = self.level.get_tile(x, y)
                if tile.fog == FogState.VISIBLE and tile.items:
                    positions.add((x, y))
        return positions

    def _count_open_neighbors(self, x: int, y: int) -> int:
        """Count passable cardinal+diagonal neighbors around a tile."""
        count = 0
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = x + ddx, y + ddy
                if self.level.in_bounds(nx, ny) and self.level.get_tile(nx, ny).passable:
                    count += 1
        return count

    def travel_step(self, dx: int, dy: int) -> tuple[DungeonActionResult, bool]:
        """Attempt one travel step and report whether travel should continue.

        Travel uses the same action resolution as normal movement, then stops
        when the new position reveals something worth handing back to the player.
        """
        assert self.player_pos is not None

        entities_before = self.visible_entity_positions()
        items_before = self.visible_item_positions()
        openness_before = self._count_open_neighbors(*self.player_pos)

        result = self.attempt_step(dx, dy)
        if result.kind != DungeonInteractionKind.MOVE:
            return result, False

        assert self.player_pos is not None

        entities_after = self.visible_entity_positions()
        new_entity_positions = entities_after - entities_before
        if new_entity_positions:
            new_entities = [
                entity
                for entity in self.entities
                if entity.alive and (entity.x, entity.y) in new_entity_positions
            ]
            if any(entity.entity_type == "object" for entity in new_entities):
                self.append_message("You notice an interactable ahead.")
            elif any(entity.disposition == "hostile" for entity in new_entities):
                self.append_message("You spot movement ahead.")
            else:
                self.append_message("Something catches your attention.")
            return result, False

        items_after = self.visible_item_positions()
        if items_after - items_before:
            self.append_message("You notice something on the ground.")
            return result, False

        openness_after = self._count_open_neighbors(*self.player_pos)
        if openness_after >= 5 and openness_after > openness_before:
            self.append_message("You emerge into a more open area.")
            return result, False

        return result, True

    def wait(self) -> None:
        assert self.player_pos is not None
        self.recompute_fov()
        self.append_message("You hold position and scan the chamber.")

    def pickup_items(self) -> DungeonActionResult:
        assert self.player_pos is not None
        x, y = self.player_pos
        item_ids = self.level.get_items(x, y)
        if not item_ids:
            message = "Nothing here can be stowed."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        self.level.get_tile(x, y).items = []
        self.inventory.extend(item_ids)
        item_names = [self.item_display_name(item_id) for item_id in item_ids]
        if len(item_names) == 1:
            message = f"You secure {item_names[0]}."
        else:
            message = f"You secure {_comma_list(item_names)}."
        self.append_message(message)
        return DungeonActionResult(
            kind=DungeonInteractionKind.ITEM,
            message=message,
            moved_to=self.player_pos,
            item_instance_id=item_ids[0] if len(item_ids) == 1 else None,
            item_display_name=item_names[0] if len(item_names) == 1 else None,
        )

    def use_inventory_item(
        self,
        current_integrity: int,
        max_integrity: int,
    ) -> DungeonActionResult:
        item = self.next_usable_inventory_item()
        if item is None:
            message = "No ready-use item is stowed."
            self.append_message(message)
            return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
        if item.use_kind == "heal":
            if current_integrity >= max_integrity:
                message = "Your integrity is already at maximum."
                self.append_message(message)
                return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
            healing = min(item.use_amount, max_integrity - current_integrity)
            if item.consumable:
                self.inventory.remove(item.instance_id)
                self.item_entities.pop(item.instance_id, None)
            message = f"You use {item.display_name} and recover {healing} integrity."
            self.append_message(message)
            return DungeonActionResult(
                kind=DungeonInteractionKind.ITEM,
                message=message,
                moved_to=self.player_pos,
                item_instance_id=item.instance_id,
                item_display_name=item.display_name,
                player_healing=healing,
            )
        message = f"{item.display_name} has no field-use effect yet."
        self.append_message(message)
        return DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)

    def advance_creature_turns(self) -> list[DungeonTurnResult]:
        """Advance all living dungeon actors once and report their actions."""
        reports: list[DungeonTurnResult] = []
        player_position = self.player_pos
        occupied: set[tuple[int, int]] = {
            entity.position
            for entity in self.entities
            if entity.alive and entity.position is not None
        }
        if player_position is not None:
            occupied.add(player_position)

        for entity in self.entities:
            if not entity.alive or entity.position is None:
                continue
            actor = DungeonEntity(
                entity_id=entity.entity_id,
                name=entity.name,
                disposition=DungeonDisposition(entity.disposition),
                movement_ai=DungeonMovementAI(entity.movement_ai),
                can_talk=entity.can_talk,
                portrait_key="mechanicus_adept",
                stats=CombatStats(
                    max_hp=entity.max_hp,
                    hp=entity.hp,
                    attack=entity.attack,
                    armor=entity.armor,
                    movement=entity.movement,
                    attack_range=entity.attack_range,
                ),
                description=entity.description,
                x=entity.x,
                y=entity.y,
                home_position=entity.home_position,
                alert_state=entity.alert_state,
                alert_turns=entity.alert_turns,
                last_seen_player_position=entity.last_seen_player_position,
                preferred_range=entity.preferred_range,
                history_entity_id=entity.history_entity_id,
                patrol_route=list(entity.patrol_route),
                patrol_index=entity.patrol_index,
            )
            plan = actor.turn_action(
                self.level,
                player_position=player_position,
                occupied=occupied,
            )
            entity.alert_state = actor.alert_state
            entity.alert_turns = actor.alert_turns
            entity.last_seen_player_position = actor.last_seen_player_position
            entity.home_position = actor.home_position
            entity.patrol_index = actor.patrol_index
            entity.preferred_range = actor.preferred_range

            current_position = entity.position
            if current_position is not None:
                occupied.discard(current_position)
            if plan.moved_to is not None and plan.moved_to != current_position:
                if current_position is not None:
                    self.level.remove_creature(*current_position)
                entity.x, entity.y = plan.moved_to
                self.level.place_creature(entity.x, entity.y, entity.entity_id)
                occupied.add(plan.moved_to)
            elif current_position is not None:
                occupied.add(current_position)

            if plan.message and self._should_log_turn_result(current_position, plan):
                self.append_message(plan.message)
            reports.append(plan)

        return reports


class DungeonScreen(Screen[None]):
    """Unified dungeon screen shell for exploration and future combat."""

    AMBIENT_DISCOVERY_COOLDOWN = 6
    AMBIENT_DISCOVERY_TERRAINS = {
        DungeonTerrain.TERMINAL,
        DungeonTerrain.SHRINE,
        DungeonTerrain.STAIRS_UP,
        DungeonTerrain.STAIRS_DOWN,
        DungeonTerrain.ELEVATOR,
        DungeonTerrain.GATE,
        DungeonTerrain.PORTAL,
        DungeonTerrain.LIFT,
        DungeonTerrain.COLUMN,
        DungeonTerrain.RUBBLE,
        DungeonTerrain.WATER,
        DungeonTerrain.LAVA,
        DungeonTerrain.CHASM,
        DungeonTerrain.GROWTH,
        DungeonTerrain.COVER,
        DungeonTerrain.GRATE,
        DungeonTerrain.ACID_POOL,
    }
    PANEL_IDS = (
        "dungeon-map",
        "dungeon-log",
        "dungeon-status",
        "dungeon-inspect",
    )

    TRAVEL_INTERVAL: float = 0.05  # seconds between travel steps

    BINDINGS = [
        Binding("up", "move_north", "Move north", show=False),
        Binding("down", "move_south", "Move south", show=False),
        Binding("left", "move_west", "Move west", show=False),
        Binding("right", "move_east", "Move east", show=False),
        Binding("h", "move_west", "Move west", show=False),
        Binding("j", "move_south", "Move south", show=False),
        Binding("k", "move_north", "Move north", show=False),
        Binding("y", "move_northwest", "Move northwest", show=False),
        Binding("u", "move_northeast", "Move northeast", show=False),
        Binding("b", "move_southwest", "Move southwest", show=False),
        Binding("n", "move_southeast", "Move southeast", show=False),
        Binding("7", "move_northwest", "Move northwest", show=False),
        Binding("9", "move_northeast", "Move northeast", show=False),
        Binding("1", "move_southwest", "Move southwest", show=False),
        Binding("3", "move_southeast", "Move southeast", show=False),
        Binding("home", "move_northwest", "Move northwest", show=False),
        Binding("pageup", "move_northeast", "Move northeast", show=False),
        Binding("end", "move_southwest", "Move southwest", show=False),
        Binding("pagedown", "move_southeast", "Move southeast", show=False),
        Binding("ctrl+up", "travel_north", "Travel north", show=False),
        Binding("ctrl+down", "travel_south", "Travel south", show=False),
        Binding("ctrl+left", "travel_west", "Travel west", show=False),
        Binding("ctrl+right", "travel_east", "Travel east", show=False),
        Binding("ctrl+h", "travel_west", "Travel west", show=False),
        Binding("ctrl+j", "travel_south", "Travel south", show=False),
        Binding("ctrl+k", "travel_north", "Travel north", show=False),
        Binding("ctrl+y", "travel_northwest", "Travel northwest", show=False),
        Binding("ctrl+u", "travel_northeast", "Travel northeast", show=False),
        Binding("ctrl+b", "travel_southwest", "Travel southwest", show=False),
        Binding("ctrl+n", "travel_southeast", "Travel southeast", show=False),
        Binding("ctrl+7", "travel_northwest", "Travel northwest", show=False),
        Binding("ctrl+9", "travel_northeast", "Travel northeast", show=False),
        Binding("ctrl+1", "travel_southwest", "Travel southwest", show=False),
        Binding("ctrl+3", "travel_southeast", "Travel southeast", show=False),
        Binding("ctrl+home", "travel_northwest", "Travel northwest", show=False),
        Binding("ctrl+pageup", "travel_northeast", "Travel northeast", show=False),
        Binding("ctrl+end", "travel_southwest", "Travel southwest", show=False),
        Binding("ctrl+pagedown", "travel_southeast", "Travel southeast", show=False),
        Binding("tab", "cycle_panel", "Cycle panels", show=True, priority=True),
        Binding("g", "pickup", "Pick up", show=True),
        Binding("i", "use_item", "Use item", show=True),
        Binding("o", "open_door", "Open door", show=True),
        Binding("c", "close_door", "Close door", show=True),
        Binding("f", "fire", "Fire", show=True),
        Binding("f3", "show_environment_catalog", "Env debug", show=True),
        Binding("l", "look", "Look", show=True),
        Binding("enter", "confirm_look", "Inspect", show=False),
        Binding("escape", "cancel_look", "Cancel look", show=False),
        Binding("5", "wait", "Wait", show=False),
        Binding("space", "wait", "Wait", show=True),
        Binding("f1", "show_help", "Help", show=True),
    ]

    HOTKEYS: list[tuple[str, str]] = [
        ("Arrow keys", "Move"),
        ("HJK", "Cardinal movement"),
        ("G", "Pick up items on the current tile"),
        ("I", "Use the next ready inventory item"),
        ("F", "Fire at a visible hostile"),
        ("F3", "Debug environment catalog"),
        ("L", "Look"),
        ("Tab", "Cycle focus between dungeon panels"),
        ("Y / U / B / N", "Vi diagonals"),
        ("7 / Home", "Move northwest"),
        ("9 / PgUp", "Move northeast"),
        ("1 / End", "Move southwest"),
        ("3 / PgDn", "Move southeast"),
        ("Ctrl + arrows / HJKYUBN / 7-9-1-3 / Home-PgUp-End-PgDn", "Travel until something interesting happens"),
        ("O", "Open adjacent door"),
        ("C", "Close adjacent door"),
        ("Enter", "Inspect target"),
        ("Esc", "Cancel look mode"),
        ("5 / Space", "Wait / rescan"),
        ("F1", "Help"),
    ]

    def __init__(
        self,
        level: DungeonLevel | None = None,
        floor: GeneratedFloor | None = None,
        state: DungeonMapState | None = None,
        player_pos: tuple[int, int] | None = None,
        fov_radius: int = 8,
        entities: Sequence[DungeonMapEntity] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._save_manager: SaveManager = SaveManager()
        self._look_mode: bool = False
        self._fire_mode: bool = False
        self._environment_catalog_open: bool = False
        self._environment_catalog: tuple[EnvironmentDebugEntry, ...] = build_environment_debug_catalog()
        current_environment = (
            state.level.environment if state is not None else (
                floor.level.environment if floor is not None else (
                    level.environment if level is not None else "forge"
                )
            )
        )
        self._environment_catalog_index = self._resolve_environment_catalog_index(current_environment)
        self._look_cursor_pos: tuple[int, int] | None = None
        self._last_look_summary: str | None = None
        self._last_examine_title: str | None = None
        self._last_examine_lines: list[str] = []
        self._ambient_discovery_title: str | None = None
        self._ambient_discovery_lines: list[str] = []
        self._ambient_discovery_art: str | None = None
        self._ambient_discovery_narrative: str | None = None
        self._ambient_seen_keys: set[str] = set()
        self._ambient_seen_terrain_types: set[str] = set()
        self._ambient_last_subject: str | None = None
        self._ambient_action_index: int = 0
        self._ambient_last_trigger_index: int = -999
        self._ambient_discovery_busy: bool = False
        self._death_in_progress: bool = False
        if state is not None:
            self._state = state
            return
        if floor is None and level is None:
            floor = generate_dungeon_floor(
                level_id="demo-floor",
                depth=1,
                environment="forge",
                seed=1,
            )
        resolved_level = floor.level if floor is not None else level
        assert resolved_level is not None
        resolved_entities = list(entities) if entities is not None else []
        if entities is None and floor is not None:
            resolved_entities = build_map_entities_from_roster(floor.entity_roster)
        self._state = DungeonMapState(
            level=resolved_level,
            player_pos=player_pos,
            fov_radius=fov_radius,
            entities=resolved_entities,
        )

    @property
    def state(self) -> DungeonMapState:
        return self._state

    def snapshot_state(self) -> DungeonMapState:
        """Return the live state object for app-level transitions."""
        return self._state

    def build_text_view_context(self, narrative_text: str, *, scene_art: str | None = None) -> dict[str, Any]:
        """Build a minimal text-view restore payload for later bridge calls."""
        payload: dict[str, Any] = {
            "narrative_log": [narrative_text],
            "current_scene_art": scene_art,
        }
        if self._state.player_pos is not None:
            payload["map_return_pos"] = list(self._state.player_pos)
        return payload

    def _build_text_bridge_state(
        self,
        narrative_text: str,
        *,
        scene_art: str | None = None,
        info_update: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build a restore payload that preserves the active dungeon location."""
        session = getattr(self.app, "dungeon_session", None)
        if session is not None:
            restored_state = session.to_text_restore_state(
                [narrative_text],
                scene_art=scene_art,
                info_update=info_update,
            )
        else:
            restored_state = self.build_text_view_context(
                narrative_text,
                scene_art=scene_art,
            )
            if info_update:
                restored_state["info_update"] = dict(info_update)
        return restored_state

    def compose(self) -> ComposeResult:
        with Horizontal(id="dungeon-layout"):
            with Vertical(id="dungeon-left"):
                yield DungeonMapPane(
                    self._state.level,
                    self._get_player_pos,
                    self._get_entities,
                    self._get_look_cursor,
                    id="dungeon-map",
                )
                yield DungeonMessageLog(self._get_messages, id="dungeon-log")
            with Vertical(id="dungeon-right"):
                yield DungeonStatusPane(
                    self._state.level,
                    self._get_player_pos,
                    self._get_entities,
                    self._get_integrity,
                    self._get_inventory_count,
                    self._get_ready_item,
                    self._get_look_cursor,
                    self._get_look_summary,
                    self._get_target_mode,
                    self._get_target_details,
                    id="dungeon-status",
                )
                yield DungeonTransitionPane(id="dungeon-inspect")

    def on_mount(self) -> None:
        self.title = f"DUNGEON: {self._state.level.name.upper()}"
        self._refresh_all()
        self.query_one("#dungeon-map", DungeonMapPane).focus()
        self._maybe_start_player_death_sequence()

    def action_cycle_panel(self) -> None:
        focused = self.focused
        focused_id = getattr(focused, "id", None)
        try:
            current_index = self.PANEL_IDS.index(str(focused_id))
        except ValueError:
            current_index = -1
        next_panel_id = self.PANEL_IDS[(current_index + 1) % len(self.PANEL_IDS)]
        self.query_one(f"#{next_panel_id}").focus()

    def _get_player_pos(self) -> tuple[int, int]:
        assert self._state.player_pos is not None
        return self._state.player_pos

    def _get_entities(self) -> Sequence[DungeonMapEntity]:
        return list(self._state.entities)

    def _get_messages(self) -> Sequence[str]:
        return list(self._state.messages)

    def _get_integrity(self) -> tuple[int, int] | None:
        engine = getattr(self.app, "game_engine", None)
        if engine is None:
            return None
        return (engine.integrity, engine.max_integrity)

    def _get_look_cursor(self) -> tuple[int, int] | None:
        return self._look_cursor_pos

    def _get_inventory_count(self) -> int:
        return len(self._state.inventory)

    def _get_ready_item(self) -> str | None:
        item = self._state.next_usable_inventory_item()
        if item is None:
            return None
        return item.display_name

    def _get_look_summary(self) -> str | None:
        if self._look_cursor_pos is None:
            return self._last_look_summary
        if self._fire_mode:
            return self._get_fire_target_summary(self._look_cursor_pos)
        return self._state.get_look_summary(self._look_cursor_pos)

    def _get_target_mode(self) -> str | None:
        if self._fire_mode:
            return "fire"
        if self._look_mode:
            return "look"
        return None

    def _get_target_details(self) -> Sequence[str]:
        if not self._fire_mode or self._look_cursor_pos is None:
            return ()
        return self._build_fire_target_details(self._look_cursor_pos)

    def _resolve_environment_catalog_index(self, environment_id: str) -> int:
        for index, entry in enumerate(self._environment_catalog):
            if entry.environment_id == environment_id:
                return index
        return 0

    def _selected_environment_debug_entry(self) -> EnvironmentDebugEntry:
        return self._environment_catalog[self._environment_catalog_index]

    def _build_environment_catalog_lines(self) -> list[str]:
        selected = self._selected_environment_debug_entry()
        lines = [
            "[dim]F3 closes. Up/Down or J/K changes selection.[/dim]",
            "",
            "[bold]ENVIRONMENTS[/bold]",
        ]
        current_environment = self._state.level.environment
        for index, entry in enumerate(self._environment_catalog):
            marker = ">" if index == self._environment_catalog_index else " "
            current = " [dim](current)[/dim]" if entry.environment_id == current_environment else ""
            lines.append(f"{marker} {entry.environment_id}{current}")
        lines.extend(
            [
                "",
                f"[bold]{selected.environment_id.upper()}[/bold]",
                selected.description,
                f"Features: {_comma_list(selected.feature_terrains)}",
                f"Rooms: {_comma_list(selected.room_types)}",
                f"Hostiles: {_comma_list(selected.hostile_contacts)}",
                f"Friendlies: {_comma_list(selected.friendly_contacts)}",
                f"Neutrals: {_comma_list(selected.neutral_contacts)}",
                f"Objects: {_comma_list(selected.object_templates)}",
                f"Loose items: {_comma_list(selected.item_names)}",
                f"Themed rooms: {_comma_list(selected.themed_rooms, limit=3)}",
                f"Discoveries: {_comma_list(selected.discovery_titles, limit=3)}",
                f"Variants: {_comma_list(selected.variant_names, limit=2)}",
            ]
        )
        if selected.reactive_rule:
            lines.append(f"Reactive rule: {selected.reactive_rule}")
        return lines

    def _open_environment_catalog(self) -> None:
        self._look_mode = False
        self._look_cursor_pos = None
        self._last_look_summary = None
        self._environment_catalog_open = True
        self._environment_catalog_index = self._resolve_environment_catalog_index(
            self._state.level.environment
        )
        self._refresh_all()

    def _close_environment_catalog(self) -> None:
        if not self._environment_catalog_open:
            return
        self._environment_catalog_open = False
        self._refresh_all()

    def _move_environment_catalog(self, delta: int) -> None:
        if not self._environment_catalog_open:
            return
        count = len(self._environment_catalog)
        self._environment_catalog_index = (self._environment_catalog_index + delta) % count
        self._refresh_all()

    def _refresh_all(self) -> None:
        self.query_one("#dungeon-map", DungeonMapPane).refresh_map()
        self.query_one("#dungeon-log", DungeonMessageLog).sync_log()
        self.query_one("#dungeon-status", DungeonStatusPane).refresh_status()
        self._refresh_inspect_pane()

    def _refresh_inspect_pane(self) -> None:
        pane = self.query_one("#dungeon-inspect", DungeonTransitionPane)
        if self._environment_catalog_open:
            pane.show_context(
                "⛨ DEBUG ENVIRONMENT CATALOG",
                self._build_environment_catalog_lines(),
            )
            return
        if self._ambient_discovery_title is not None:
            if self._ambient_discovery_art is not None or self._ambient_discovery_narrative is not None:
                pane.show_inspect(
                    self._ambient_discovery_title,
                    scene_art=self._ambient_discovery_art,
                    narrative_text=self._ambient_discovery_narrative,
                )
            else:
                pane.show_context(self._ambient_discovery_title, self._ambient_discovery_lines)
            return
        pane.show_context(
            "⛨ FIELD SCAN",
            [
                "Ambient discoveries surface here when something notable enters view.",
                "Move through the dungeon to reveal contacts, relics, and terrain features.",
                "Press L to enter look mode for a full examine.",
            ],
        )

    def _ambient_candidate_key(self, context: dict[str, Any]) -> str:
        target_kind = str(context.get("target_kind", "terrain"))
        if target_kind == "character" and context.get("target_entity_id"):
            return f"entity:{context['target_entity_id']}"
        if target_kind == "object" and context.get("target_entity_id"):
            return f"object:{context['target_entity_id']}"
        position = context.get("target_position", [0, 0])
        if isinstance(position, list) and len(position) == 2:
            x, y = position
        else:
            x = y = 0
        terrain = str(context.get("terrain", "unknown"))
        return f"{target_kind}:{terrain}:{x}:{y}"

    def _ambient_subject_key(self, context: dict[str, Any]) -> str:
        """Derive a coarse subject key for back-to-back and terrain-type dedupe.

        For entities this is ``"entity_type:name"`` (e.g. ``"character:Relay Priest"``).
        For terrain discoveries this is ``"terrain:column"`` — intentionally ignoring
        position so that e.g. two columns in the same room collapse to one subject.
        """
        target_kind = str(context.get("target_kind", "terrain"))
        if target_kind in {"character", "object"} and context.get("target_entity_id"):
            return f"{target_kind}:{context.get('target_label', 'unknown')}"
        terrain = str(context.get("terrain", "unknown"))
        return f"terrain:{terrain}"

    def _ambient_candidate_priority(self, context: dict[str, Any]) -> tuple[int, int, str]:
        target_kind = str(context.get("target_kind", "terrain"))
        if target_kind == "character":
            kind_priority = 0
        elif target_kind == "object":
            kind_priority = 1
        elif target_kind in {"terrain", "creature"}:
            kind_priority = 2
        else:
            kind_priority = 3
        distance = int(context.get("distance_from_player") or 0)
        label = str(context.get("target_label", "Unknown"))
        return kind_priority, distance, label

    def _is_ambient_terrain(self, terrain: DungeonTerrain) -> bool:
        return terrain in self.AMBIENT_DISCOVERY_TERRAINS

    def _find_ambient_discovery_context(self) -> dict[str, Any] | None:
        player_pos = self._state.player_pos
        if player_pos is None:
            return None

        candidates: list[dict[str, Any]] = []
        for entity in self._state.entities:
            if not entity.alive:
                continue
            if entity.entity_type not in {"character", "object"} and not entity.can_talk:
                continue
            if self._state.level.get_tile(entity.x, entity.y).fog != FogState.VISIBLE:
                continue
            context = self._state.build_examine_context((entity.x, entity.y))
            context["ambient_key"] = self._ambient_candidate_key(context)
            candidates.append(context)

        for y in range(self._state.level.height):
            for x in range(self._state.level.width):
                tile = self._state.level.get_tile(x, y)
                if tile.fog != FogState.VISIBLE:
                    continue
                if not self._is_ambient_terrain(tile.terrain):
                    continue
                context = self._state.build_examine_context((x, y))
                if context.get("target_kind") not in {"terrain", "creature"}:
                    continue
                if context.get("target_kind") == "terrain" and not context.get("target_visible", False):
                    continue
                context["ambient_key"] = self._ambient_candidate_key(context)
                candidates.append(context)

        # Annotate each candidate with its subject key for dedupe filtering.
        for ctx in candidates:
            ctx["ambient_subject"] = self._ambient_subject_key(ctx)

        # Primary filter: exact position/entity key never shown before.
        candidates = [
            ctx for ctx in candidates
            if str(ctx.get("ambient_key")) not in self._ambient_seen_keys
        ]

        # Terrain-type dedupe: suppress terrain discoveries whose type
        # (e.g. "column") was already announced — prevents column → column
        # re-announcements even at different positions.
        candidates = [
            ctx for ctx in candidates
            if (
                str(ctx.get("target_kind")) in {"character", "object"}
                or str(ctx.get("ambient_subject")) not in self._ambient_seen_terrain_types
            )
        ]

        # Back-to-back subject dedupe: never announce the same subject
        # category (e.g. "terrain:column") twice in a row.
        if self._ambient_last_subject is not None:
            non_repeat = [
                ctx for ctx in candidates
                if str(ctx.get("ambient_subject")) != self._ambient_last_subject
            ]
            # Only apply the filter when there are alternatives; if the
            # only remaining candidate is a repeat we still prefer silence.
            if non_repeat:
                candidates = non_repeat
            else:
                candidates = []

        if not candidates:
            return None
        candidates.sort(key=self._ambient_candidate_priority)
        return candidates[0]

    def _set_ambient_discovery(
        self,
        title: str,
        lines: Sequence[str],
        *,
        scene_art: str | None = None,
        narrative_text: str | None = None,
    ) -> None:
        self._ambient_discovery_title = title
        self._ambient_discovery_lines = list(lines)
        self._ambient_discovery_art = scene_art
        self._ambient_discovery_narrative = narrative_text
        self._refresh_all()

    def _maybe_trigger_ambient_discovery(self) -> None:
        if self._ambient_discovery_busy:
            return
        if self._ambient_action_index - self._ambient_last_trigger_index < self.AMBIENT_DISCOVERY_COOLDOWN:
            return
        context = self._find_ambient_discovery_context()
        if context is None:
            return
        ambient_key = str(context.get("ambient_key"))
        ambient_subject = str(context.get("ambient_subject", ""))
        self._ambient_seen_keys.add(ambient_key)
        if ambient_subject.startswith("terrain:"):
            self._ambient_seen_terrain_types.add(ambient_subject)
        self._ambient_last_subject = ambient_subject
        self._ambient_last_trigger_index = self._ambient_action_index
        self._ambient_discovery_busy = True
        self._run_ambient_discovery(context)

    @work(exclusive=True)
    async def _run_ambient_discovery(self, context: dict[str, Any]) -> None:
        try:
            engine = self.app.game_engine  # type: ignore[attr-defined]
            response = await engine.describe_ambient_dungeon_target(context)
            if not response.narrative_text and not response.scene_art:
                return
            lines: list[str] = []
            if response.scene_art:
                lines.extend(response.scene_art.splitlines())
                if response.narrative_text:
                    lines.append("")
            if response.narrative_text:
                lines.extend(response.narrative_text.splitlines())
            title = f"⛨ AMBIENT: {str(context.get('target_label', 'Discovery')).upper()}"
            self._set_ambient_discovery(
                title,
                lines,
                scene_art=response.scene_art,
                narrative_text=response.narrative_text,
            )
        finally:
            self._ambient_discovery_busy = False

    def _autosave(self) -> None:
        """Persist the current dungeon session after a meaningful turn."""
        try:
            if self._death_in_progress:
                return
            slot_id: str | None = getattr(self.app, "save_slot", None)  # type: ignore[attr-defined]
            dungeon_session = getattr(self.app, "dungeon_session", None)  # type: ignore[attr-defined]
            if not slot_id or dungeon_session is None:
                return
            state: dict[str, Any] = self.app.game_engine.to_dict()  # type: ignore[attr-defined]
            state["mode"] = "dungeon"
            state["dungeon_session"] = dungeon_session.to_dict()
            if dungeon_session.story_id is not None:
                state["story_start_id"] = dungeon_session.story_id
            self._save_manager.save(slot_id, state)
            logger.info("Autosaved dungeon turn to slot %s", slot_id)
        except Exception as exc:
            logger.error("Dungeon autosave failed: %s", exc)

    def _player_has_fallen(self) -> bool:
        engine = getattr(self.app, "game_engine", None)
        return engine is not None and engine.integrity <= 0

    def _summarize_hostile_contacts(self) -> str:
        hostiles = [
            entity.name
            for entity in self._state.entities
            if entity.disposition == DungeonDisposition.HOSTILE
        ]
        if not hostiles:
            return "unknown hostiles"
        return ", ".join(hostiles[:4])

    def _summarize_companions(self) -> str:
        engine = getattr(self.app, "game_engine", None)
        if engine is None:
            return "no surviving companions"
        companions = engine.get_status_data().get("companions", [])
        alive_companions = [
            companion
            for companion in companions
            if isinstance(companion, dict) and companion.get("alive")
        ]
        if not alive_companions:
            return "no surviving companions"
        return ", ".join(
            f"{companion.get('name', 'Unknown')} "
            f"({companion.get('hp', 0)}/{companion.get('max_hp', 0)})"
            for companion in alive_companions
        )

    def _build_death_context(self, reports: Sequence[DungeonTurnResult]) -> dict[str, Any]:
        session = getattr(self.app, "dungeon_session", None)  # type: ignore[attr-defined]
        deepest_level = self._state.level.depth
        if session is not None and session.level_states:
            deepest_level = max(state.level.depth for state in session.level_states.values())
        fallen_hostiles = sum(
            1
            for entity in self._state.entities
            if entity.disposition == DungeonDisposition.HOSTILE and not entity.alive
        )
        striking_enemies = [
            report.entity_name
            for report in reports
            if report.attacked_player
        ]
        enemy_summary = ", ".join(striking_enemies[:4]) or self._summarize_hostile_contacts()
        location = session.location if session is not None and session.location else self._state.level.name
        return {
            "player_name": getattr(self.app.game_engine, "player_name", "Magos Explorator"),  # type: ignore[attr-defined]
            "location": location,
            "turns_survived": getattr(self.app.game_engine, "turn_count", 0),  # type: ignore[attr-defined]
            "enemies_slain": fallen_hostiles,
            "deepest_level_reached": deepest_level,
            "enemy_summary": enemy_summary,
            "companion_summary": self._summarize_companions(),
            "cause_of_death": f"succumbed to {enemy_summary}",
            "report_count": len(list(reports)),
            "timestamp": time.time(),
        }

    def _maybe_start_player_death_sequence(self) -> None:
        if self._death_in_progress or not self._player_has_fallen():
            return
        self._death_in_progress = True
        self._handle_player_death([])

    @work(exclusive=True)
    async def _handle_player_death(self, reports: Sequence[DungeonTurnResult]) -> None:
        if not self._death_in_progress:
            self._death_in_progress = True
        death_context = self._build_death_context(reports)
        app = self.app
        await app.handle_player_death(death_context)  # type: ignore[attr-defined]

    def _step(self, dx: int, dy: int) -> None:
        if self._death_in_progress:
            return
        if self._environment_catalog_open:
            delta = -1 if dx < 0 or dy < 0 else 1 if dx > 0 or dy > 0 else 0
            if delta != 0:
                self._move_environment_catalog(delta)
            return
        if self._look_mode or self._fire_mode:
            self._move_look_cursor(dx, dy)
            return
        result = self._state.attempt_step(dx, dy)
        self._process_step_result(result)

    def _process_step_result(self, result: DungeonActionResult) -> None:
        if self._death_in_progress:
            return
        if result.kind in {
            DungeonInteractionKind.MOVE,
            DungeonInteractionKind.DOOR,
            DungeonInteractionKind.ITEM,
        }:
            self._ambient_action_index += 1
        engine = getattr(self.app, "game_engine", None)
        if result.player_damage > 0 and engine is not None:
            engine.take_damage(result.player_damage)
        if result.player_healing > 0 and engine is not None:
            if hasattr(engine, "set_integrity"):
                engine.set_integrity(engine.integrity + result.player_healing)
            else:
                engine.integrity = min(engine.max_integrity, engine.integrity + result.player_healing)
        self._refresh_all()
        if result.player_damage > 0 and self._player_has_fallen():
            self._death_in_progress = True
            self._handle_player_death([])
            return
        if result.kind in {
            DungeonInteractionKind.CONVERSATION,
            DungeonInteractionKind.OBJECT,
        }:
            self._open_text_view_for_interaction(result)
            self._autosave()
        elif result.kind == DungeonInteractionKind.TRANSITION:
            self.app.travel_dungeon_transition()  # type: ignore[attr-defined]
            self._autosave()
        elif result.kind in {
            DungeonInteractionKind.MOVE,
            DungeonInteractionKind.DOOR,
            DungeonInteractionKind.ATTACK,
            DungeonInteractionKind.NEUTRAL,
            DungeonInteractionKind.ITEM,
        }:
            if self._apply_creature_turns():
                return
            self._maybe_trigger_ambient_discovery()
            self._autosave()
        elif result.kind != DungeonInteractionKind.BLOCKED:
            self._autosave()

    def _apply_creature_turns(self) -> bool:
        """Advance the local AI after a player action."""
        reports = self._state.advance_creature_turns()
        if not reports:
            return False
        engine = getattr(self.app, "game_engine", None)
        total_damage = sum(report.attack_damage for report in reports if report.attacked_player)
        if engine is not None and total_damage > 0:
            engine.take_damage(total_damage)
        self._refresh_all()
        if self._player_has_fallen():
            self._death_in_progress = True
            self._handle_player_death(reports)
            return True
        return False

    @work(exclusive=True)
    async def _run_travel(self, dx: int, dy: int) -> None:
        while True:
            result, should_continue = self._state.travel_step(dx, dy)
            self._process_step_result(result)
            if self._death_in_progress:
                return
            if not should_continue:
                return
            await asyncio.sleep(self.TRAVEL_INTERVAL)

    def _move_look_cursor(self, dx: int, dy: int) -> None:
        if self._look_cursor_pos is None:
            self._look_cursor_pos = self._state.player_pos
        assert self._look_cursor_pos is not None
        nx = self._look_cursor_pos[0] + dx
        ny = self._look_cursor_pos[1] + dy
        if not self._state.level.in_bounds(nx, ny):
            self._state.append_message("The cursor cannot move beyond the map edge.")
            self._refresh_all()
            return
        if self._state.level.get_tile(nx, ny).fog != FogState.VISIBLE:
            self._state.append_message("That target is not visible.")
            self._refresh_all()
            return
        self._look_cursor_pos = (nx, ny)
        self._last_look_summary = self._state.get_look_summary(self._look_cursor_pos)
        self._refresh_all()

    def _open_text_view_for_interaction(self, result: DungeonActionResult) -> None:
        if result.target_entity_id is None:
            return
        target_context = dict(result.interaction_context)
        if not target_context:
            target_context = {
                "interaction_kind": result.kind.value,
                "interaction_entity_id": result.target_entity_id,
                "interaction_entity_name": result.target_entity_name,
                "interaction_entity_type": result.target_entity_type,
                "interaction_entity_disposition": result.target_disposition,
            }
        if result.scene_art is not None:
            target_context["interaction_scene_art"] = result.scene_art
        restored_state = self._build_text_bridge_state(
            result.message,
            scene_art=result.scene_art,
        )
        restored_state.update(target_context)
        app = self.app
        history = app.game_engine.history  # type: ignore[attr-defined]
        target_name = result.target_entity_name or result.target_entity_id
        target_description = target_context.get("interaction_entity_description", target_name)
        if result.kind == DungeonInteractionKind.CONVERSATION:
            entity_id = result.speaking_npc_id
            if entity_id is None:
                history_entity = history.register_entity(
                    name=target_name,
                    entity_type=EntityType.CHARACTER,
                    description=str(target_description),
                )
                entity_id = history_entity.id
            else:
                history_entity = history.get_entity(entity_id)
                if history_entity is None:
                    history_entity = history.register_entity(
                        name=target_name,
                        entity_type=EntityType.CHARACTER,
                        description=str(target_description),
                    )
                    entity_id = history_entity.id
            if entity_id is not None:
                target_context["conversation_target"] = entity_id
                if result.target_entity_id:
                    target_context["interaction_entity_history_id"] = entity_id
            self._sync_entity_history_id(result.target_entity_id, entity_id)
            restored_state["conversation_target"] = entity_id
            restored_state["interaction_target"] = entity_id
            app.open_text_view(
                restored_state=restored_state,
                speaking_npc_id=entity_id,
            )  # type: ignore[attr-defined]
            return
        history_entity = history.register_entity(
            name=target_name,
            entity_type=EntityType.PLACE,
            description=str(target_description),
        )
        self._sync_entity_history_id(result.target_entity_id, history_entity.id)
        restored_state["interaction_target"] = history_entity.id
        restored_state["interaction_entity_history_id"] = history_entity.id
        app.open_text_view(  # type: ignore[attr-defined]
            restored_state=restored_state,
        )

    def _register_examine_history(self, context: dict[str, Any]) -> tuple[str | None, str | None]:
        """Return history IDs and speaking context for an explicit examine action."""
        target_entity_id = context.get("target_entity_id")
        target_name = str(context.get("target_entity_name") or context.get("target_label") or "Unknown")
        target_description = str(context.get("target_description") or target_name)
        target_kind = str(context.get("target_kind", "terrain"))
        app = self.app
        history = app.game_engine.history  # type: ignore[attr-defined]

        if target_kind == "character":
            history_id = context.get("target_entity_history_id") or context.get("target_history_id")
            if isinstance(history_id, str):
                history_entity = history.get_entity(history_id)
                if history_entity is None:
                    history_id = None
            if not isinstance(history_id, str):
                existing_entity = self._state.entity_at(
                    tuple(context.get("target_position", self._state.player_pos or (0, 0)))
                )
                history_id = existing_entity.history_entity_id if existing_entity is not None else None
            if isinstance(history_id, str):
                history_entity = history.get_entity(history_id)
                if history_entity is None:
                    history_id = None
            if not isinstance(history_id, str):
                history_entity = history.register_entity(
                    name=target_name,
                    entity_type=EntityType.CHARACTER,
                    description=target_description,
                )
                history_id = history_entity.id
            if isinstance(target_entity_id, str):
                self._sync_entity_history_id(target_entity_id, history_id)
            speaking_npc_id = history_id if context.get("target_can_talk") else None
            return history_id, speaking_npc_id

        history_entity = history.register_entity(
            name=target_name,
            entity_type=EntityType.PLACE,
            description=target_description,
        )
        if isinstance(target_entity_id, str):
            self._sync_entity_history_id(target_entity_id, history_entity.id)
        return history_entity.id, None

    @work(exclusive=True)
    async def _run_examine(self, position: tuple[int, int]) -> None:
        context = self._state.build_examine_context(position)
        context["look_mode"] = True
        context["look_cursor"] = list(position)
        context["look_summary"] = self._state.get_look_summary(position)
        context["look_instructions"] = (
            "The player is examining a visible dungeon target. "
            "Provide a vivid short description and accompanying scene art."
        )
        self._last_look_summary = str(context.get("look_summary", ""))
        engine = self.app.game_engine  # type: ignore[attr-defined]
        response = await engine.examine_dungeon_target(context)
        scene_art = response.scene_art.strip() if isinstance(response.scene_art, str) else None
        if not scene_art:
            target_scene_art = context.get("target_scene_art")
            if isinstance(target_scene_art, str) and target_scene_art.strip():
                scene_art = target_scene_art
        interaction_target, speaking_npc_id = self._register_examine_history(context)
        restored_state = self._build_text_bridge_state(
            response.narrative_text,
            scene_art=scene_art,
            info_update=response.info_update,
        )
        restored_state.update(context)
        restored_state["interaction_kind"] = "examine"
        if interaction_target is not None:
            restored_state["interaction_target"] = interaction_target
            restored_state["interaction_entity_history_id"] = interaction_target
        self.app.open_text_view(  # type: ignore[attr-defined]
            restored_state=restored_state,
            speaking_npc_id=speaking_npc_id,
        )

    def _begin_look_mode(self) -> None:
        self._fire_mode = False
        self._look_mode = True
        self._look_cursor_pos = self._state.player_pos
        self._last_look_summary = self._state.get_look_summary(self._look_cursor_pos)
        self._state.append_message("Look mode engaged. Move the cursor to a visible target.")
        self._refresh_all()

    def _cancel_look_mode(self) -> None:
        if not self._look_mode:
            return
        self._look_mode = False
        self._look_cursor_pos = None
        self._last_look_summary = None
        self._state.append_message("Look mode cancelled.")
        self._refresh_all()

    def _visible_hostile_targets(self) -> list[DungeonMapEntity]:
        hostiles = [
            entity
            for entity in self._state.entities
            if entity.alive
            and entity.disposition == "hostile"
            and self._state.level.get_tile(entity.x, entity.y).fog == FogState.VISIBLE
        ]
        hostiles.sort(
            key=lambda entity: (
                self._state.distance_from_player((entity.x, entity.y)),
                entity.name,
            )
        )
        return hostiles

    def _get_fire_target_summary(self, position: tuple[int, int]) -> str:
        entity = self._state.entity_at(position)
        distance = self._state.distance_from_player(position)
        if entity is None:
            return f"No hostile target at ({position[0]},{position[1]})."
        if entity.disposition != "hostile":
            return f"{entity.name} is not a hostile target."
        locked = (
            distance <= self._state.player_attack_range
            and self._state.level.line_of_sight(self._state.player_pos, position)
        )
        status = "locked" if locked else "invalid"
        return f"{entity.name} ({status})"

    def _build_fire_target_details(self, position: tuple[int, int]) -> list[str]:
        entity = self._state.entity_at(position)
        distance = self._state.distance_from_player(position)
        details = [f"RANGE: {distance}/{self._state.player_attack_range}"]
        if entity is None:
            details.append("[dim]No hostile contact on this tile[/dim]")
            return details
        if entity.disposition != "hostile":
            details.append("[dim]Target must be hostile[/dim]")
            return details
        if not self._state.level.line_of_sight(self._state.player_pos, position):
            details.append("[dim]No line of sight[/dim]")
        elif distance > self._state.player_attack_range:
            details.append("[dim]Target out of range[/dim]")
        else:
            details.append("[dim]Target lock confirmed[/dim]")
        details.append(f"HP: {entity.hp}/{entity.max_hp}  ARM: {entity.armor}")
        return details

    def _begin_fire_mode(self) -> None:
        hostiles = self._visible_hostile_targets()
        if not hostiles:
            self._state.append_message("No hostile target is visible.")
            self._refresh_all()
            return
        self._look_mode = False
        self._fire_mode = True
        self._look_cursor_pos = (hostiles[0].x, hostiles[0].y)
        self._last_look_summary = self._get_fire_target_summary(self._look_cursor_pos)
        self._state.append_message("Fire mode engaged. Move the cursor to a visible hostile.")
        self._refresh_all()

    def _cancel_fire_mode(self) -> None:
        if not self._fire_mode:
            return
        self._fire_mode = False
        self._look_cursor_pos = None
        self._last_look_summary = None
        self._state.append_message("Fire mode cancelled.")
        self._refresh_all()

    def _confirm_fire_mode(self) -> None:
        if not self._fire_mode or self._look_cursor_pos is None:
            return
        result = self._state.attempt_ranged_attack(self._look_cursor_pos)
        if result.kind != DungeonInteractionKind.ATTACK:
            self._last_look_summary = self._get_fire_target_summary(self._look_cursor_pos)
            self._refresh_all()
            return
        self._fire_mode = False
        self._look_cursor_pos = None
        self._last_look_summary = None
        self._process_step_result(result)

    def _sync_entity_history_id(self, entity_id: str, history_entity_id: str | None) -> None:
        if history_entity_id is None:
            return
        for entity in self._state.entities:
            if entity.entity_id == entity_id:
                entity.history_entity_id = history_entity_id
                return

    def action_move_north(self) -> None:
        self._step(0, -1)

    def action_move_south(self) -> None:
        self._step(0, 1)

    def action_move_west(self) -> None:
        self._step(-1, 0)

    def action_move_east(self) -> None:
        self._step(1, 0)

    def action_move_northwest(self) -> None:
        self._step(-1, -1)

    def action_move_northeast(self) -> None:
        self._step(1, -1)

    def action_move_southwest(self) -> None:
        self._step(-1, 1)

    def action_move_southeast(self) -> None:
        self._step(1, 1)

    def _door_target(self, terrain: DungeonTerrain) -> tuple[int, int] | None:
        assert self._state.player_pos is not None
        px, py = self._state.player_pos
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = px + dx, py + dy
            if not self._state.level.in_bounds(nx, ny):
                continue
            if self._state.level.get_terrain(nx, ny) == terrain:
                return (nx, ny)
        return None

    def action_open_door(self) -> None:
        if self._death_in_progress:
            return
        target = self._door_target(DungeonTerrain.DOOR_CLOSED)
        if target is None:
            message = "No closed door is adjacent."
            self._state.append_message(message)
            self._process_step_result(
                DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
            )
            return
        self._process_step_result(self._state.open_door_at(target))

    def action_close_door(self) -> None:
        if self._death_in_progress:
            return
        target = self._door_target(DungeonTerrain.DOOR_OPEN)
        if target is None:
            message = "No open door is adjacent."
            self._state.append_message(message)
            self._process_step_result(
                DungeonActionResult(kind=DungeonInteractionKind.BLOCKED, message=message)
            )
            return
        self._process_step_result(self._state.close_door_at(target))

    def action_pickup(self) -> None:
        if self._death_in_progress:
            return
        self._process_step_result(self._state.pickup_items())

    def action_use_item(self) -> None:
        if self._death_in_progress:
            return
        integrity = self._get_integrity()
        if integrity is None:
            self._state.append_message("No integrity track is available for item use.")
            self._refresh_all()
            return
        current_integrity, max_integrity = integrity
        self._process_step_result(
            self._state.use_inventory_item(current_integrity, max_integrity)
        )

    def _travel_or_step(self, dx: int, dy: int) -> None:
        if self._look_mode or self._fire_mode:
            self._step(dx, dy)
            return
        self._run_travel(dx, dy)

    def action_travel_north(self) -> None:
        self._travel_or_step(0, -1)

    def action_travel_south(self) -> None:
        self._travel_or_step(0, 1)

    def action_travel_west(self) -> None:
        self._travel_or_step(-1, 0)

    def action_travel_east(self) -> None:
        self._travel_or_step(1, 0)

    def action_travel_northwest(self) -> None:
        self._travel_or_step(-1, -1)

    def action_travel_northeast(self) -> None:
        self._travel_or_step(1, -1)

    def action_travel_southwest(self) -> None:
        self._travel_or_step(-1, 1)

    def action_travel_southeast(self) -> None:
        self._travel_or_step(1, 1)

    def action_look(self) -> None:
        if self._environment_catalog_open:
            self._close_environment_catalog()
        if self._look_mode:
            self._cancel_look_mode()
            return
        self._begin_look_mode()

    def action_fire(self) -> None:
        if self._fire_mode:
            self._cancel_fire_mode()
            return
        self._begin_fire_mode()

    def action_show_environment_catalog(self) -> None:
        if self._environment_catalog_open:
            self._close_environment_catalog()
            return
        self._open_environment_catalog()

    def action_confirm_look(self) -> None:
        if self._fire_mode:
            self._confirm_fire_mode()
            return
        if not self._look_mode or self._look_cursor_pos is None:
            return
        position = self._look_cursor_pos
        if self._state.level.get_tile(*position).fog != FogState.VISIBLE:
            self._state.append_message("That target is not visible.")
            self._refresh_all()
            return
        position = self._look_cursor_pos
        self._look_mode = False
        self._look_cursor_pos = None
        self._last_look_summary = None
        self._run_examine(position)

    def action_cancel_look(self) -> None:
        if self._fire_mode:
            self._cancel_fire_mode()
            return
        if self._environment_catalog_open:
            self._close_environment_catalog()
            return
        self._cancel_look_mode()

    def on_key(self, event: Key) -> None:
        """Ensure look-mode confirmation still works even if focus changes."""
        if (self._look_mode or self._fire_mode) and event.key in {"enter", "return"}:
            self.action_confirm_look()
            event.stop()
            return

    def action_wait(self) -> None:
        if self._death_in_progress:
            return
        self._state.wait()
        self._ambient_action_index += 1
        if self._apply_creature_turns():
            return
        self._refresh_all()
        self._maybe_trigger_ambient_discovery()
        self._autosave()

    def action_show_help(self) -> None:
        self.app.push_screen(
            HelpOverlay(
                title="++ DUNGEON HOTKEYS ++",
                hotkeys=self.HOTKEYS,
            )
        )
