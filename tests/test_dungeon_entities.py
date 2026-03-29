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


def _make_bordered_level(width: int = 7, height: int = 7) -> DungeonLevel:
    level = _make_open_level(width, height)
    for y in range(height):
        for x in range(width):
            if x in (0, width - 1) or y in (0, height - 1):
                level.set_terrain(x, y, DungeonTerrain.WALL)
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


def test_melee_hostile_paths_around_walls() -> None:
    level = _make_bordered_level(7, 5)
    for x in range(2, 5):
        level.set_terrain(x, 1, DungeonTerrain.WALL)
    level.player_pos = (5, 1)
    level.compute_fov((5, 1), 5)

    raider = DungeonEntity(
        entity_id="raider-1",
        name="Tunnel Raider",
        disposition=DungeonDisposition.HOSTILE,
        movement_ai=DungeonMovementAI.AGGRESSIVE,
        can_talk=False,
        portrait_key="assassin",
        stats=CombatStats(max_hp=6, hp=6, attack=3, armor=0, movement=3, attack_range=1),
        x=1,
        y=1,
    )

    plan = raider.turn_action(level, player_position=(5, 1), occupied={(5, 1)})

    assert plan.attacked_player is False
    assert plan.moved_to in {(2, 1), (1, 2)}
    assert raider.position == (1, 2)


def test_ranged_hostile_attacks_from_line_of_sight() -> None:
    level = _make_bordered_level(7, 5)
    level.player_pos = (4, 2)
    level.compute_fov((4, 2), 5)

    loota = DungeonEntity(
        entity_id="loota-1",
        name="Loota",
        disposition=DungeonDisposition.HOSTILE,
        movement_ai=DungeonMovementAI.AGGRESSIVE,
        can_talk=False,
        portrait_key="assassin",
        stats=CombatStats(max_hp=9, hp=9, attack=5, armor=1, movement=2, attack_range=6),
        x=1,
        y=2,
    )

    plan = loota.turn_action(level, player_position=(4, 2), occupied={(4, 2)})

    assert plan.attacked_player is True
    assert plan.attack_damage == 5
    assert plan.moved_to is None
    assert loota.position == (1, 2)


def test_ranged_hostile_flanks_to_restore_line_of_sight() -> None:
    level = _make_bordered_level(7, 5)
    level.set_terrain(2, 2, DungeonTerrain.WALL)
    level.set_terrain(3, 2, DungeonTerrain.WALL)
    level.set_terrain(4, 2, DungeonTerrain.WALL)
    level.set_terrain(1, 3, DungeonTerrain.WALL)
    level.player_pos = (5, 2)
    level.compute_fov((5, 2), 5)

    loota = DungeonEntity(
        entity_id="loota-2",
        name="Loota",
        disposition=DungeonDisposition.HOSTILE,
        movement_ai=DungeonMovementAI.AGGRESSIVE,
        can_talk=False,
        portrait_key="assassin",
        stats=CombatStats(max_hp=9, hp=9, attack=5, armor=1, movement=2, attack_range=6),
        x=1,
        y=2,
    )

    plan = loota.turn_action(level, player_position=(5, 2), occupied={(5, 2)})

    assert plan.attacked_player is False
    assert plan.moved_to == (1, 1)
    assert plan.moved_to is not None


def test_hostile_state_transitions_from_engaged_to_idle_after_lost_contact() -> None:
    level = _make_bordered_level(7, 5)
    level.player_pos = (3, 2)
    level.compute_fov((3, 2), 5)

    sentry = DungeonEntity(
        entity_id="sentry-1",
        name="Sentry",
        disposition=DungeonDisposition.HOSTILE,
        movement_ai=DungeonMovementAI.AGGRESSIVE,
        can_talk=False,
        portrait_key="servitor",
        stats=CombatStats(max_hp=8, hp=8, attack=3, armor=1, movement=3, attack_range=1),
        x=1,
        y=2,
    )

    first = sentry.turn_action(level, player_position=(3, 2), occupied={(3, 2)})
    assert first.moved_to is not None
    assert sentry.alert_state == "engaged"

    for y in range(0, 5):
        level.set_terrain(3, y, DungeonTerrain.WALL)
    level.player_pos = (5, 2)
    level.compute_fov((5, 2), 5)

    second = sentry.turn_action(level, player_position=(5, 2), occupied={(5, 2)})
    third = sentry.turn_action(level, player_position=(5, 2), occupied={(5, 2)})
    fourth = sentry.turn_action(level, player_position=(5, 2), occupied={(5, 2)})

    assert second.attacked_player is False
    assert sentry.alert_state == "idle"
    assert third.alert_state in {"searching", "idle"}
    assert fourth.alert_state == "idle"


def test_friendly_followers_keep_pace_with_player() -> None:
    level = _make_bordered_level(7, 5)
    level.player_pos = (5, 2)
    level.compute_fov((5, 2), 5)

    follower = DungeonEntity(
        entity_id="servo-skull",
        name="Servo Skull",
        disposition=DungeonDisposition.FRIENDLY,
        movement_ai=DungeonMovementAI.FOLLOW_PLAYER,
        can_talk=False,
        portrait_key="cyber_cherub",
        stats=CombatStats(max_hp=6, hp=6, attack=2, armor=0, movement=5, attack_range=6),
        x=1,
        y=2,
    )

    plan = follower.turn_action(level, player_position=(5, 2), occupied={(5, 2)})

    assert plan.attacked_player is False
    assert plan.moved_to in {(2, 2), (1, 1), (1, 3)}
    assert follower.position == plan.moved_to


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
