"""Unified dungeon exploration screen."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual import work

from angband_mechanicum.engine.dungeon_gen import GeneratedFloor, generate_dungeon_floor
from angband_mechanicum.engine.dungeon_level import (
    DungeonLevel,
    DungeonTerrain,
    FogState,
    is_transition_terrain,
    transition_terrain_label,
)
from angband_mechanicum.engine.history import EntityType
from angband_mechanicum.widgets.dungeon_map import (
    DungeonMapEntity,
    DungeonMapPane,
    DungeonMessageLog,
    DungeonTransitionPane,
    DungeonStatusPane,
)
from angband_mechanicum.widgets.help_overlay import HelpOverlay


class DungeonInteractionKind(enum.Enum):
    """High-level outcomes of trying to step into a tile."""

    MOVE = "move"
    ATTACK = "attack"
    CONVERSATION = "conversation"
    OBJECT = "object"
    TRANSITION = "transition"
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
            "items": list(tile.items),
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
        if tile.items:
            context["target_label"] = context.get("target_label", terrain.value)
            if len(tile.items) == 1:
                context["target_kind"] = "item"
                context["target_label"] = f"{context['target_label']} with 1 item"
            else:
                context["target_label"] = f"{context['target_label']} with {len(tile.items)} items"
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
        terrain_type = self.level.get_terrain(nx, ny)
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
        message = f"You move to {nx},{ny} across {terrain}."
        self.append_message(message)
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
        Binding("l", "look", "Look", show=True),
        Binding("enter", "confirm_look", "Inspect", show=False),
        Binding("escape", "cancel_look", "Cancel look", show=False),
        Binding("space", "wait", "Wait", show=True),
        Binding("f1", "show_help", "Help", show=True),
    ]

    HOTKEYS: list[tuple[str, str]] = [
        ("Arrow keys", "Move"),
        ("HJK", "Cardinal movement"),
        ("L", "Look"),
        ("Y / U / B / N", "Vi diagonals"),
        ("7 / Home", "Move northwest"),
        ("9 / PgUp", "Move northeast"),
        ("1 / End", "Move southwest"),
        ("3 / PgDn", "Move southeast"),
        ("Enter", "Inspect target"),
        ("Esc", "Cancel look mode"),
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
        self._look_mode: bool = False
        self._look_cursor_pos: tuple[int, int] | None = None
        self._last_look_summary: str | None = None
        self._last_examine_title: str | None = None
        self._last_examine_lines: list[str] = []
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
                    self._get_look_cursor,
                    id="dungeon-map",
                )
                yield DungeonMessageLog(self._get_messages, id="dungeon-log")
            with Vertical(id="dungeon-right"):
                yield DungeonStatusPane(
                    self._state.level,
                    self._get_player_pos,
                    self._get_entities,
                    self._get_message_count,
                    self._get_look_cursor,
                    self._get_look_summary,
                    id="dungeon-status",
                )
                yield DungeonTransitionPane(id="dungeon-inspect")

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

    def _get_look_cursor(self) -> tuple[int, int] | None:
        return self._look_cursor_pos

    def _get_look_summary(self) -> str | None:
        if self._look_cursor_pos is None:
            return self._last_look_summary
        return self._state.get_look_summary(self._look_cursor_pos)

    def _refresh_all(self) -> None:
        self.query_one("#dungeon-map", DungeonMapPane).refresh_map()
        self.query_one("#dungeon-log", DungeonMessageLog).sync_log()
        self.query_one("#dungeon-status", DungeonStatusPane).refresh_status()
        self._refresh_inspect_pane()

    def _refresh_inspect_pane(self) -> None:
        pane = self.query_one("#dungeon-inspect", DungeonTransitionPane)
        if self._last_examine_title is None:
            pane.show_context(
                "⛨ EXAMINATION",
                [
                    "Press L to enter look mode.",
                    "Use arrows or HJK to move the cursor.",
                    "Enter inspects the highlighted target.",
                    "Esc cancels look mode.",
                ],
            )
            return
        pane.show_context(self._last_examine_title, self._last_examine_lines)

    def _step(self, dx: int, dy: int) -> None:
        if self._look_mode:
            self._move_look_cursor(dx, dy)
            return
        result = self._state.attempt_step(dx, dy)
        self._refresh_all()
        if result.kind in {
            DungeonInteractionKind.CONVERSATION,
            DungeonInteractionKind.OBJECT,
        }:
            self._open_text_view_for_interaction(result)
        elif result.kind == DungeonInteractionKind.TRANSITION:
            self.app.travel_dungeon_transition()  # type: ignore[attr-defined]

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
        title = str(context.get("target_label", "Examination"))
        self._last_examine_title = f"⛨ {title.upper()}"
        self._last_examine_lines = []
        if response.scene_art:
            self._last_examine_lines.extend(response.scene_art.splitlines())
            self._last_examine_lines.append("")
        self._last_examine_lines.append(response.narrative_text)
        self._state.append_message(response.narrative_text)
        self._refresh_all()

    def _begin_look_mode(self) -> None:
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

    def action_look(self) -> None:
        if self._look_mode:
            self._cancel_look_mode()
            return
        self._begin_look_mode()

    def action_confirm_look(self) -> None:
        if not self._look_mode or self._look_cursor_pos is None:
            return
        if self._state.level.get_tile(*self._look_cursor_pos).fog != FogState.VISIBLE:
            self._state.append_message("That target is not visible.")
            self._refresh_all()
            return
        self._look_mode = False
        self._run_examine(self._look_cursor_pos)

    def action_cancel_look(self) -> None:
        self._cancel_look_mode()

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
