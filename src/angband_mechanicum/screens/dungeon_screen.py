"""Unified dungeon exploration screen."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from angband_mechanicum.engine.dungeon_gen import GeneratedFloor, generate_dungeon_floor
from angband_mechanicum.engine.dungeon_level import DungeonLevel, DungeonTerrain
from angband_mechanicum.engine.history import EntityType
from angband_mechanicum.widgets.dungeon_map import (
    DungeonMapEntity,
    DungeonMapPane,
    DungeonMessageLog,
    DungeonStatusPane,
)
from angband_mechanicum.widgets.help_overlay import HelpOverlay


class DungeonInteractionKind(enum.Enum):
    """High-level outcomes of trying to step into a tile."""

    MOVE = "move"
    ATTACK = "attack"
    CONVERSATION = "conversation"
    OBJECT = "object"
    NEUTRAL = "neutral"
    BLOCKED = "blocked"


@dataclass
class DungeonActionResult:
    """Result of a move or bump interaction."""

    kind: DungeonInteractionKind
    message: str
    target_entity_id: str | None = None
    target_entity_name: str | None = None
    target_entity_type: str | None = None
    target_disposition: str | None = None
    attack_damage: int = 0
    target_defeated: bool = False
    moved_to: tuple[int, int] | None = None
    scene_art: str | None = None
    speaking_npc_id: str | None = None
    interaction_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class DungeonMapState:
    """Mutable dungeon exploration state owned by the screen."""

    level: DungeonLevel
    player_pos: tuple[int, int] | None = None
    fov_radius: int = 8
    player_attack: int = 4
    entities: list[DungeonMapEntity] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.player_pos is None:
            self.player_pos = self.level.player_pos
        if self.player_pos is None and self.level.stairs_up:
            self.player_pos = self.level.stairs_up[0]
        if self.player_pos is None:
            self.player_pos = self._first_passable_tile()
        self._apply_position()
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.to_dict(),
            "player_pos": list(self.player_pos) if self.player_pos is not None else None,
            "fov_radius": self.fov_radius,
            "player_attack": self.player_attack,
            "entities": [entity.to_dict() for entity in self.entities],
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
            entities=[
                DungeonMapEntity.from_dict(entity_data)
                for entity_data in data.get("entities", [])
            ],
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
            self._move_player_to((entity.x, entity.y))
            message = f"{message} {entity.name} is destroyed and the way is clear."
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
        if not self.level.get_tile(nx, ny).passable:
            terrain_name = self.level.get_terrain(nx, ny).value.replace("_", " ").title()
            message = f"{terrain_name} blocks the route."
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
        self._move_player_to((nx, ny))
        terrain = self.level.get_terrain(nx, ny).value.replace("_", " ").title()
        message = f"You move to {nx},{ny} across {terrain}."
        self.append_message(message)
        if self.level.get_terrain(nx, ny) == DungeonTerrain.STAIRS_DOWN:
            self.append_message("Downward stairs descend deeper.")
        elif self.level.get_terrain(nx, ny) == DungeonTerrain.STAIRS_UP:
            self.append_message("Upward stairs lead back toward the surface.")
        return DungeonActionResult(
            kind=DungeonInteractionKind.MOVE,
            message=message,
            moved_to=(nx, ny),
        )

    def wait(self) -> None:
        assert self.player_pos is not None
        self.recompute_fov()
        self.append_message("You hold position and scan the chamber.")


class DungeonScreen(Screen[None]):
    """Unified dungeon screen shell for exploration and future combat."""

    BINDINGS = [
        Binding("up", "move_north", "Move north", show=False),
        Binding("down", "move_south", "Move south", show=False),
        Binding("left", "move_west", "Move west", show=False),
        Binding("right", "move_east", "Move east", show=False),
        Binding("h", "move_west", "Move west", show=False),
        Binding("j", "move_south", "Move south", show=False),
        Binding("k", "move_north", "Move north", show=False),
        Binding("l", "move_east", "Move east", show=False),
        Binding("y", "move_northwest", "Move northwest", show=False),
        Binding("u", "move_northeast", "Move northeast", show=False),
        Binding("b", "move_southwest", "Move southwest", show=False),
        Binding("n", "move_southeast", "Move southeast", show=False),
        Binding("space", "wait", "Wait", show=True),
        Binding("f1", "show_help", "Help", show=True),
    ]

    HOTKEYS: list[tuple[str, str]] = [
        ("Arrow keys", "Move"),
        ("HJKL", "Cardinal movement"),
        ("YUBN", "Diagonal movement"),
        ("Space", "Wait / rescan"),
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
        self._state = DungeonMapState(
            level=resolved_level,
            player_pos=player_pos,
            fov_radius=fov_radius,
            entities=list(entities or []),
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

    def compose(self) -> ComposeResult:
        with Horizontal(id="dungeon-layout"):
            with Vertical(id="dungeon-left"):
                yield DungeonMapPane(
                    self._state.level,
                    self._get_player_pos,
                    self._get_entities,
                    id="dungeon-map",
                )
                yield DungeonMessageLog(self._get_messages, id="dungeon-log")
            yield DungeonStatusPane(
                self._state.level,
                self._get_player_pos,
                self._get_entities,
                self._get_message_count,
                id="dungeon-status",
            )

    def on_mount(self) -> None:
        self.title = f"DUNGEON: {self._state.level.name.upper()}"
        self._refresh_all()
        self.query_one("#dungeon-map", DungeonMapPane).focus()

    def _get_player_pos(self) -> tuple[int, int]:
        assert self._state.player_pos is not None
        return self._state.player_pos

    def _get_entities(self) -> Sequence[DungeonMapEntity]:
        return list(self._state.entities)

    def _get_messages(self) -> Sequence[str]:
        return list(self._state.messages)

    def _get_message_count(self) -> int:
        return len(self._state.messages)

    def _refresh_all(self) -> None:
        self.query_one("#dungeon-map", DungeonMapPane).refresh_map()
        self.query_one("#dungeon-log", DungeonMessageLog).sync_log()
        self.query_one("#dungeon-status", DungeonStatusPane).refresh_status()

    def _step(self, dx: int, dy: int) -> None:
        result = self._state.attempt_step(dx, dy)
        self._refresh_all()
        if result.kind in {
            DungeonInteractionKind.CONVERSATION,
            DungeonInteractionKind.OBJECT,
        }:
            self._open_text_view_for_interaction(result)

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
        restored_state = self.build_text_view_context(
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

    def action_wait(self) -> None:
        self._state.wait()
        self._refresh_all()

    def action_show_help(self) -> None:
        self.app.push_screen(
            HelpOverlay(
                title="++ DUNGEON HOTKEYS ++",
                hotkeys=self.HOTKEYS,
            )
        )
