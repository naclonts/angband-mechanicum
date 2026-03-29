"""Tests for dungeon NPC / creature placement and management."""

from __future__ import annotations

import random

from angband_mechanicum.engine.combat_engine import CombatStats
from angband_mechanicum.engine.dungeon_entities import (
    DungeonDisposition,
    DungeonEntity,
    DungeonEntityRoster,
    DungeonMovementAI,
    make_dungeon_party_member,
    make_dungeon_party_roster,
)
from angband_mechanicum.engine.dungeon_level import DungeonLevel, DungeonTerrain
from angband_mechanicum.engine.history import EntityType, GameHistory


def _make_open_level(width: int = 7, height: int = 7) -> DungeonLevel:
    level = DungeonLevel(
        level_id="test",
        name="Test Level",
        depth=1,
        environment="forge",
        width=width,
        height=height,
    )
    for y in range(height):
        for x in range(width):
            level.set_terrain(x, y, DungeonTerrain.FLOOR)
    return level


def test_default_party_members_have_expected_metadata() -> None:
    servo_skull = make_dungeon_party_member("servo-skull")

    assert servo_skull.disposition == DungeonDisposition.FRIENDLY
    assert servo_skull.movement_ai == DungeonMovementAI.FOLLOW_PLAYER
    assert servo_skull.can_talk is False
    assert servo_skull.portrait_key == "cyber_cherub"
    assert servo_skull.stats == CombatStats(max_hp=6, hp=6, attack=2, armor=0, movement=5, attack_range=6)


def test_roster_places_followers_near_player() -> None:
    level = _make_open_level()
    level.player_pos = (3, 3)
    roster = make_dungeon_party_roster()

    placed = roster.place_followers(level, level.player_pos)

    assert len(placed) == 1
    positions = {entity.position for entity in placed}
    assert level.player_pos not in positions
    for entity in placed:
        assert entity.position is not None
        assert level.get_creature(*entity.position) == entity.entity_id


def test_roster_move_updates_level_state() -> None:
    level = _make_open_level()
    roster = DungeonEntityRoster()
    entity = DungeonEntity(
        entity_id="servitor-1",
        name="Rogue Servitor",
        disposition=DungeonDisposition.HOSTILE,
        movement_ai=DungeonMovementAI.WANDER,
        can_talk=False,
        portrait_key="servitor",
        stats=CombatStats(max_hp=8, hp=8, attack=3, armor=0, movement=3, attack_range=1),
    )
    roster.add(entity)

    assert roster.place(level, entity.entity_id, 2, 2) is True
    assert roster.move(level, entity.entity_id, 3, 2) is True
    assert level.get_creature(2, 2) is None
    assert level.get_creature(3, 2) == entity.entity_id


def test_step_entity_honors_ai_modes() -> None:
    level = _make_open_level()
    roster = DungeonEntityRoster()
    stationary = DungeonEntity(
        entity_id="statue",
        name="Silent Statue",
        disposition=DungeonDisposition.NEUTRAL,
        movement_ai=DungeonMovementAI.STATIONARY,
        can_talk=False,
        portrait_key="magos",
        stats=CombatStats(max_hp=1, hp=1, attack=0, armor=0, movement=0, attack_range=0),
    )
    aggressive = DungeonEntity(
        entity_id="hunter",
        name="Hunter",
        disposition=DungeonDisposition.HOSTILE,
        movement_ai=DungeonMovementAI.AGGRESSIVE,
        can_talk=False,
        portrait_key="servitor",
        stats=CombatStats(max_hp=5, hp=5, attack=2, armor=0, movement=4, attack_range=1),
    )
    roster.add(stationary)
    roster.add(aggressive)
    assert roster.place(level, stationary.entity_id, 1, 1) is True
    assert roster.place(level, aggressive.entity_id, 5, 5) is True

    assert stationary.intended_step(level, player_position=(3, 3)) is None
    assert aggressive.intended_step(level, player_position=(3, 3), rng=random.Random(1)) is not None


def test_patrol_route_advances_toward_next_point() -> None:
    level = _make_open_level()
    patrol = DungeonEntity(
        entity_id="patrol-1",
        name="Patrol Servitor",
        disposition=DungeonDisposition.NEUTRAL,
        movement_ai=DungeonMovementAI.PATROL,
        can_talk=False,
        portrait_key="servitor",
        stats=CombatStats(max_hp=5, hp=5, attack=1, armor=0, movement=3, attack_range=1),
        patrol_route=[(2, 1), (4, 1)],
    )
    patrol.place(level, 2, 1)

    step = patrol.intended_step(level)
    assert step == (3, 1)


def test_history_registration_uses_character_entities() -> None:
    history = GameHistory()
    roster = make_dungeon_party_roster()

    history_ids = roster.register_with_history(history)

    assert len(history_ids) == 1
    servo_skull_source = roster.get("servo-skull")
    assert servo_skull_source is not None
    assert servo_skull_source.description
    assert servo_skull_source.description == (
        "A hovering servo-skull fitted with auspex lenses and a crackling vox-grille"
    )

    servo_skull = history.get_entity("servo-skull")
    assert servo_skull is not None
    assert servo_skull.type == EntityType.CHARACTER
    assert servo_skull.description == servo_skull_source.description
