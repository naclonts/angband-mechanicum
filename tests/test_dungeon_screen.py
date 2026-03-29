"""Tests for the dungeon screen shell and rendering helpers."""

from __future__ import annotations

from rich.text import Text
import pytest

from angband_mechanicum.app import AngbandMechanicumApp
from angband_mechanicum.app import DungeonSession
from angband_mechanicum.engine.combat_engine import CombatStats
from angband_mechanicum.engine.dungeon_entities import (
    DungeonDisposition,
    DungeonEntity,
    DungeonEntityRoster,
    DungeonMovementAI,
)
from angband_mechanicum.engine.dungeon_gen import GeneratedFloor
from angband_mechanicum.engine.dungeon_level import DungeonLevel, DungeonTerrain, FogState
from angband_mechanicum.engine.game_engine import GameEngine
from angband_mechanicum.engine.story_starts import StoryStart
from angband_mechanicum.screens.game_screen import GameScreen
import angband_mechanicum.screens.dungeon_screen as dungeon_screen_module
from angband_mechanicum.screens.dungeon_screen import (
    DungeonInteractionKind,
    DungeonMapState,
    DungeonScreen,
)
from angband_mechanicum.widgets.dungeon_map import (
    DungeonMapEntity,
    DungeonMessageLog,
    DungeonStatusPane,
    DungeonTransitionPane,
    _resolve_viewport_window,
    render_dungeon_map,
    render_dungeon_status,
)


def _make_level() -> DungeonLevel:
    level = DungeonLevel(
        level_id="test-floor",
        name="Test Floor",
        depth=1,
        environment="forge",
        width=7,
        height=5,
    )
    for y in range(level.height):
        for x in range(level.width):
            if x in (0, level.width - 1) or y in (0, level.height - 1):
                level.set_terrain(x, y, DungeonTerrain.WALL)
            else:
                level.set_terrain(x, y, DungeonTerrain.FLOOR)
    level.set_terrain(5, 2, DungeonTerrain.WALL)
    level.player_pos = (2, 2)
    level.compute_fov((2, 2), 1)
    return level


def _make_floor_with_contacts() -> GeneratedFloor:
    level = _make_level()
    roster = DungeonEntityRoster()
    entity = DungeonEntity(
        entity_id="forge-priest",
        name="Forge Priest",
        disposition=DungeonDisposition.FRIENDLY,
        movement_ai=DungeonMovementAI.STATIONARY,
        can_talk=True,
        portrait_key="mechanicus_adept",
        stats=CombatStats(
            max_hp=6,
            hp=6,
            attack=2,
            armor=1,
            movement=3,
            attack_range=1,
        ),
        description="A live contact pulled from the generated roster.",
    )
    roster.add(entity)
    entity.place(level, 3, 2)
    return GeneratedFloor(
        level=level,
        rooms=[],
        environment="forge",
        entry_room_index=0,
        exit_room_index=0,
        entity_roster=roster,
    )


class TestDungeonMapRendering:
    def test_render_includes_player_and_visible_terrain(self) -> None:
        level = _make_level()
        rendered = render_dungeon_map(level, (2, 2))
        Text.from_markup(rendered)
        assert "[bold #00ff41]@[/bold #00ff41]" in rendered
        assert "#6e4b1e" in rendered

    def test_render_pads_lines_to_viewport_width(self) -> None:
        level = _make_level()
        rendered = render_dungeon_map(level, (2, 2), viewport_size=(18, 7))
        plain_lines = Text.from_markup(rendered).plain.splitlines()
        assert max(len(line) for line in plain_lines) == 18

    def test_render_hides_unseen_tiles(self) -> None:
        level = _make_level()
        level.reset_visible()
        level.set_visible(2, 2)
        rendered = render_dungeon_map(level, (2, 2))
        assert rendered.count(" ") > 0

    def test_render_shows_look_cursor(self) -> None:
        level = _make_level()
        rendered = render_dungeon_map(level, (2, 2), cursor_pos=(3, 2))
        assert "◉" in rendered

    def test_status_panel_reports_fov_and_tile(self) -> None:
        level = _make_level()
        status = render_dungeon_status(level, (2, 2), message_count=3)
        assert "LEVEL: Test Floor" in status
        assert "FOV:" in status
        assert "TILE:  floor" in status


class TestDungeonScreenBindings:
    def test_diagonal_movement_bindings_include_vi_and_numpad_aliases(self) -> None:
        keys = {binding.key for binding in DungeonScreen.BINDINGS}
        expected = {
            "y",
            "u",
            "b",
            "n",
            "7",
            "9",
            "1",
            "3",
            "home",
            "pageup",
            "end",
            "pagedown",
        }
        assert expected <= keys

    def test_help_text_lists_each_diagonal_direction(self) -> None:
        hotkeys = dict(DungeonScreen.HOTKEYS)
        assert hotkeys["Y / U / B / N"] == "Vi diagonals"
        assert hotkeys["7 / Home"] == "Move northwest"
        assert hotkeys["9 / PgUp"] == "Move northeast"
        assert hotkeys["1 / End"] == "Move southwest"
        assert hotkeys["3 / PgDn"] == "Move southeast"
        assert hotkeys["Tab"] == "Cycle focus between dungeon panels"

    def test_non_map_panels_are_focusable(self) -> None:
        assert DungeonMessageLog.can_focus is True
        assert DungeonStatusPane.can_focus is True
        assert DungeonTransitionPane.can_focus is True


class TestDungeonMapCamera:
    def test_viewport_window_follows_player_near_edges(self) -> None:
        level = DungeonLevel(
            level_id="camera-test",
            name="Camera Test",
            depth=1,
            environment="forge",
            width=20,
            height=20,
        )
        left, top, visible_cols, visible_rows = _resolve_viewport_window(
            level,
            (18, 18),
            (12, 8),
        )

        assert (left, top) == (12, 15)
        assert (visible_cols, visible_rows) == (8, 5)

    def test_render_crops_to_follow_player_window(self) -> None:
        level = DungeonLevel(
            level_id="camera-test",
            name="Camera Test",
            depth=1,
            environment="forge",
            width=20,
            height=20,
        )
        for y in range(level.height):
            for x in range(level.width):
                level.set_terrain(x, y, DungeonTerrain.FLOOR)
        level.set_terrain(1, 1, DungeonTerrain.TERMINAL)
        level.set_terrain(17, 18, DungeonTerrain.SHRINE)
        level.player_pos = (18, 18)
        level.compute_fov((18, 18), 5)

        rendered = render_dungeon_map(
            level,
            (18, 18),
            viewport_size=(12, 8),
        )

        assert "[bold #00ff41]@[/bold #00ff41]" in rendered
        assert "†" in rendered
        assert "¤" not in rendered
        assert rendered.splitlines()[1] == "  ╔════════╗"


class TestDungeonMapState:
    def test_move_player_updates_position_and_fov(self) -> None:
        level = _make_level()
        state = DungeonMapState(level=level, player_pos=(2, 2), fov_radius=1)
        assert state.move_player(1, 0) is True
        assert state.player_pos == (3, 2)
        assert level.get_tile(3, 2).fog == FogState.VISIBLE
        assert state.move_player(1, 0) is True
        assert state.player_pos == (4, 2)
        assert level.get_tile(2, 2).fog == FogState.EXPLORED
        assert len(state.messages) >= 2

    def test_blocked_move_adds_message(self) -> None:
        level = _make_level()
        state = DungeonMapState(level=level, player_pos=(2, 2), fov_radius=1)
        assert state.move_player(1, 0) is True
        assert state.move_player(1, 0) is True
        assert state.move_player(1, 0) is False
        assert state.messages[-1].startswith("Wall")

    def test_wait_recomputes_visibility_and_logs(self) -> None:
        level = _make_level()
        state = DungeonMapState(level=level, player_pos=(2, 2), fov_radius=1)
        state.wait()
        assert state.messages[-1] == "You hold position and scan the chamber."
        assert level.get_tile(2, 2).fog == FogState.VISIBLE

    def test_build_examine_context_includes_entity_and_surroundings(self) -> None:
        level = _make_level()
        statue = DungeonMapEntity(
            entity_id="statue-1",
            name="Machine Statue",
            x=3,
            y=2,
            disposition="neutral",
            can_talk=False,
            description="An ancient brass icon of the Omnissiah.",
            scene_art="STATUE",
        )
        state = DungeonMapState(level=level, player_pos=(2, 2), entities=[statue])

        context = state.build_examine_context((3, 2))

        assert context["target_kind"] == "character"
        assert context["target_entity_name"] == "Machine Statue"
        assert context["target_visible"] is True
        assert context["surroundings"]["west"] == "floor"
        assert context["distance_from_player"] == 1

    def test_state_round_trips_through_dict(self) -> None:
        level = _make_level()
        entity = DungeonMapEntity(
            entity_id="alpha-7",
            name="Alpha-7",
            x=3,
            y=2,
            symbol="A",
            fg="#123456",
            disposition="friendly",
            can_talk=True,
            entity_type="character",
            hp=5,
            max_hp=8,
            attack=3,
            armor=1,
            description="Skitarii companion",
            scene_art="SCENE",
            history_entity_id="skitarius-alpha-7",
        )
        state = DungeonMapState(
            level=level,
            player_pos=(2, 2),
            fov_radius=2,
            player_attack=6,
            entities=[entity],
            messages=["First contact"],
        )
        restored = DungeonMapState.from_dict(state.to_dict())
        assert restored.player_pos == (2, 2)
        assert restored.fov_radius == 2
        assert restored.player_attack == 6
        assert restored.messages == ["First contact"]
        assert restored.level.name == "Test Floor"
        assert restored.entities[0].history_entity_id == "skitarius-alpha-7"

    def test_hostile_bump_attacks_and_clears_tile(self) -> None:
        level = _make_level()
        hostile = DungeonMapEntity(
            entity_id="rogue-servitor",
            name="Rogue Servitor",
            x=3,
            y=2,
            disposition="hostile",
            hp=3,
            max_hp=3,
            attack=2,
            armor=0,
        )
        state = DungeonMapState(level=level, player_pos=(2, 2), entities=[hostile])

        result = state.attempt_step(1, 0)

        assert result.kind == DungeonInteractionKind.ATTACK
        assert result.attack_damage == 4
        assert result.target_defeated is True
        assert state.player_pos == (3, 2)
        assert state.entity_at((3, 2)) is None
        assert "destroyed" in state.messages[-1]

    def test_friendly_bump_prompts_conversation(self) -> None:
        level = _make_level()
        ally = DungeonMapEntity(
            entity_id="alpha-7",
            name="Alpha-7",
            x=3,
            y=2,
            disposition="friendly",
            can_talk=True,
            history_entity_id="skitarius-alpha-7",
            description="Skitarii companion",
        )
        state = DungeonMapState(level=level, player_pos=(2, 2), entities=[ally])

        result = state.attempt_step(1, 0)

        assert result.kind == DungeonInteractionKind.CONVERSATION
        assert result.speaking_npc_id == "skitarius-alpha-7"
        assert result.interaction_context["interaction_entity_name"] == "Alpha-7"
        assert state.player_pos == (2, 2)
        assert state.messages[-1] == "You address Alpha-7."

    def test_object_bump_prompts_text_view(self) -> None:
        level = _make_level()
        terminal = DungeonMapEntity(
            entity_id="terminal-1",
            name="Cogitator Terminal",
            x=3,
            y=2,
            disposition="neutral",
            entity_type="object",
            description="A humming machine shrine of data.",
            scene_art="TERMINAL",
        )
        state = DungeonMapState(level=level, player_pos=(2, 2), entities=[terminal])

        result = state.attempt_step(1, 0)

        assert result.kind == DungeonInteractionKind.OBJECT
        assert result.scene_art == "TERMINAL"
        assert result.interaction_context["interaction_entity_type"] == "object"
        assert state.messages[-1] == "You inspect Cogitator Terminal."

    def test_neutral_bump_only_logs_local_description(self) -> None:
        level = _make_level()
        statue = DungeonMapEntity(
            entity_id="statue-1",
            name="Machine Statue",
            x=3,
            y=2,
            disposition="neutral",
            can_talk=False,
            description="An ancient brass icon of the Omnissiah.",
        )
        state = DungeonMapState(level=level, player_pos=(2, 2), entities=[statue])

        result = state.attempt_step(1, 0)

        assert result.kind == DungeonInteractionKind.NEUTRAL
        assert "leave it undisturbed" in state.messages[-1]
        assert state.player_pos == (2, 2)

    def test_step_onto_transition_tile_returns_transition_result(self) -> None:
        level = _make_level()
        level.set_terrain(3, 2, DungeonTerrain.STAIRS_DOWN)
        level.stairs_down = [(3, 2)]
        state = DungeonMapState(level=level, player_pos=(2, 2), fov_radius=1)

        result = state.attempt_step(1, 0)

        assert result.kind == DungeonInteractionKind.TRANSITION
        assert result.moved_to == (3, 2)
        assert "carry you deeper" in result.message


class TestTransitionHelpers:
    def test_app_builds_dungeon_session_from_story_start(self) -> None:
        app = AngbandMechanicumApp()
        story = StoryStart(
            id="test-story",
            title="The Silent Forge",
            description="A forge goes silent.",
            location="Forge-Cathedral Alpha",
            intro_narrative="The forge awaits.",
            scene_art="ART",
        )
        session = app.build_dungeon_session(story)

        assert session.story_id == "test-story"
        assert session.location == "Forge-Cathedral Alpha"
        assert session.intro_narrative == "The forge awaits."
        assert session.state.level.name == "Forge-Cathedral Alpha"
        assert session.state.messages == ["The forge awaits."]
        assert session.state.player_pos is not None

    def test_game_screen_can_build_dungeon_transition_state(self) -> None:
        screen = GameScreen()
        payload = screen.build_dungeon_transition_state(
            ["Conversation ended."],
            scene_art="SCENE",
            info_update={"LOCATION": "Vault"},
        )

        assert payload["narrative_log"] == ["Conversation ended."]
        assert payload["current_scene_art"] == "SCENE"
        assert payload["info_update"] == {"LOCATION": "Vault"}

    def test_game_screen_accepts_conversation_focus(self) -> None:
        screen = GameScreen(speaking_npc_id="skitarius-alpha-7")
        assert screen._speaking_npc_id == "skitarius-alpha-7"

    def test_dungeon_screen_uses_floor_contacts_when_floor_is_provided(self) -> None:
        floor = _make_floor_with_contacts()
        screen = DungeonScreen(floor=floor)

        assert [entity.entity_id for entity in screen.state.entities] == ["forge-priest"]
        assert (screen.state.entities[0].x, screen.state.entities[0].y) == (3, 2)


class TestDungeonLookMode:
    def test_look_mode_stays_modal_across_cursor_moves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        level = _make_level()
        screen = DungeonScreen(level=level, player_pos=(2, 2))
        monkeypatch.setattr(screen, "_refresh_all", lambda: None)

        screen.action_look()
        screen.action_move_east()
        screen.action_move_east()

        assert screen._look_mode is True
        assert screen._look_cursor_pos == (4, 2)
        assert screen.state.player_pos == (2, 2)

    def test_confirm_exits_look_mode_explicitly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        level = _make_level()
        screen = DungeonScreen(level=level, player_pos=(2, 2))
        monkeypatch.setattr(screen, "_refresh_all", lambda: None)
        monkeypatch.setattr(screen, "_run_examine", lambda position: None)

        screen.action_look()
        screen.action_move_east()
        screen.action_confirm_look()

        assert screen._look_mode is False
        assert screen._look_cursor_pos is None

class TestAmbientDiscoveries:
    def test_prefers_visible_character_over_terrain(self) -> None:
        level = _make_level()
        npc = DungeonMapEntity(
            entity_id="relay-priest",
            name="Relay Priest",
            x=3,
            y=2,
            disposition="friendly",
            can_talk=True,
            description="A hooded attendant watching the aisles.",
        )
        screen = DungeonScreen(level=level, player_pos=(2, 2), entities=[npc])

        context = screen._find_ambient_discovery_context()

        assert context is not None
        assert context["target_kind"] == "character"
        assert context["target_label"] == "Relay Priest"

    def test_maybe_trigger_ambient_discovery_updates_panel_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        level = _make_level()
        shrine = DungeonMapEntity(
            entity_id="data-shrine",
            name="Data Shrine",
            x=3,
            y=2,
            disposition="neutral",
            entity_type="object",
            description="A cogitator altar flickering with faint binaric runes.",
        )
        screen = DungeonScreen(level=level, player_pos=(2, 2), entities=[shrine])
        screen._ambient_action_index = 3
        monkeypatch.setattr(screen, "_refresh_all", lambda: None)

        seen_contexts: list[dict[str, object]] = []

        def fake_run(context: dict[str, object]) -> None:
            try:
                seen_contexts.append(context)
                screen._set_ambient_discovery(
                    f"⛨ AMBIENT: {str(context.get('target_label', 'Discovery')).upper()}",
                    ["A brief machine-spirit whisper settles over the panel."],
                )
            finally:
                screen._ambient_discovery_busy = False

        monkeypatch.setattr(screen, "_run_ambient_discovery", fake_run)

        screen._maybe_trigger_ambient_discovery()
        first_title = screen._ambient_discovery_title
        first_lines = list(screen._ambient_discovery_lines)

        screen._maybe_trigger_ambient_discovery()

        assert len(seen_contexts) == 1
        assert first_title == "⛨ AMBIENT: DATA SHRINE"
        assert first_lines == ["A brief machine-spirit whisper settles over the panel."]
    def test_terrain_type_dedupe_suppresses_second_column(self) -> None:
        """Two columns at different positions should not both trigger ambient."""
        level = _make_level()
        level.set_terrain(3, 2, DungeonTerrain.COLUMN)
        level.set_terrain(4, 2, DungeonTerrain.COLUMN)
        level.compute_fov((2, 2), 8)

        screen = DungeonScreen(level=level, player_pos=(2, 2))

        first = screen._find_ambient_discovery_context()
        assert first is not None
        assert first["terrain"] == "column"

        # Simulate having announced the first column.
        screen._ambient_seen_keys.add(str(first["ambient_key"]))
        subject = screen._ambient_subject_key(first)
        screen._ambient_seen_terrain_types.add(subject)
        screen._ambient_last_subject = subject

        # The second column at a different position should be suppressed.
        second = screen._find_ambient_discovery_context()
        assert second is None

    def test_back_to_back_same_subject_suppressed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After announcing a shrine, the same terrain type is suppressed next turn."""
        level = _make_level()
        level.set_terrain(3, 1, DungeonTerrain.SHRINE)
        level.set_terrain(4, 1, DungeonTerrain.SHRINE)
        level.compute_fov((2, 2), 8)

        screen = DungeonScreen(level=level, player_pos=(2, 2))
        monkeypatch.setattr(screen, "_refresh_all", lambda: None)

        first = screen._find_ambient_discovery_context()
        assert first is not None
        assert first["terrain"] == "shrine"

        # Mark the first as seen and set it as the last subject.
        screen._ambient_seen_keys.add(str(first["ambient_key"]))
        subject = screen._ambient_subject_key(first)
        screen._ambient_seen_terrain_types.add(subject)
        screen._ambient_last_subject = subject

        # Back-to-back: same terrain type → suppressed
        second = screen._find_ambient_discovery_context()
        assert second is None

    def test_entity_bypasses_terrain_type_dedupe(self) -> None:
        """Characters/objects should still appear even if a terrain type was deduped."""
        level = _make_level()
        level.set_terrain(3, 1, DungeonTerrain.COLUMN)
        level.compute_fov((2, 2), 8)

        npc = DungeonMapEntity(
            entity_id="enginseer-1",
            name="Enginseer Primus",
            x=3,
            y=2,
            disposition="friendly",
            can_talk=True,
            description="A senior tech-adept.",
        )
        screen = DungeonScreen(level=level, player_pos=(2, 2), entities=[npc])

        # Pretend we already announced a column terrain.
        screen._ambient_seen_terrain_types.add("terrain:column")
        screen._ambient_last_subject = "terrain:column"

        # The NPC should still come through despite terrain dedupe.
        context = screen._find_ambient_discovery_context()
        assert context is not None
        assert context["target_kind"] == "character"
        assert context["target_label"] == "Enginseer Primus"

    def test_doubled_cooldown_prevents_rapid_triggers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With cooldown=6, triggers at action_index < 6 after last trigger are blocked."""
        level = _make_level()
        level.set_terrain(3, 1, DungeonTerrain.TERMINAL)
        level.set_terrain(4, 1, DungeonTerrain.SHRINE)
        level.compute_fov((2, 2), 8)

        screen = DungeonScreen(level=level, player_pos=(2, 2))
        monkeypatch.setattr(screen, "_refresh_all", lambda: None)

        triggered: list[dict[str, object]] = []

        def fake_run(context: dict[str, object]) -> None:
            triggered.append(context)
            screen._ambient_discovery_busy = False

        monkeypatch.setattr(screen, "_run_ambient_discovery", fake_run)

        # Simulate: last trigger was at action_index=0, current=5 → gap of 5 < 6 → skip
        screen._ambient_last_trigger_index = 0
        screen._ambient_action_index = 5
        screen._maybe_trigger_ambient_discovery()
        assert len(triggered) == 0

        # Now advance to 6 → gap is exactly 6 → fires
        screen._ambient_action_index = 6
        screen._maybe_trigger_ambient_discovery()
        assert len(triggered) == 1

    def test_cooldown_value_is_six(self) -> None:
        """Verify the cooldown constant is 6 (double the original 3)."""
        assert DungeonScreen.AMBIENT_DISCOVERY_COOLDOWN == 6

    def test_look_examine_still_works_after_dedupe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit look/examine should not be affected by ambient dedupe state."""
        level = _make_level()
        level.set_terrain(3, 2, DungeonTerrain.COLUMN)
        level.compute_fov((2, 2), 8)

        screen = DungeonScreen(level=level, player_pos=(2, 2))
        monkeypatch.setattr(screen, "_refresh_all", lambda: None)

        # Poison the dedupe state for columns.
        screen._ambient_seen_terrain_types.add("terrain:column")
        screen._ambient_last_subject = "terrain:column"

        # Ambient should be suppressed.
        assert screen._find_ambient_discovery_context() is None

        # But explicit look/examine context should still build fine.
        context = screen._state.build_examine_context((3, 2))
        assert context["terrain"] == "column"
        assert context["target_visible"] is True

        # And look mode mechanics are unaffected.
        screen.action_look()
        assert screen._look_mode is True
        screen.action_move_east()
        assert screen._look_cursor_pos == (3, 2)

        # Confirm would trigger _run_examine, which is the explicit path.
        examine_called: list[tuple[int, int]] = []
        monkeypatch.setattr(screen, "_run_examine", lambda pos: examine_called.append(pos))
        screen.action_confirm_look()
        assert examine_called == [(3, 2)]
        assert screen._look_mode is False


class _FakeEngine:
    def __init__(self) -> None:
        self.turn_count = 7

    def to_dict(self) -> dict[str, object]:
        return {"turn_count": self.turn_count}


class _FakeSaveManager:
    def __init__(self) -> None:
        self.saved: list[tuple[str, dict[str, object]]] = []

    def save(self, slot_id: str, state: dict[str, object]) -> None:
        self.saved.append((slot_id, state))


def _build_autosave_screen(
    level: DungeonLevel,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[DungeonScreen, _FakeSaveManager, AngbandMechanicumApp]:
    save_manager = _FakeSaveManager()
    monkeypatch.setattr(dungeon_screen_module, "SaveManager", lambda: save_manager)
    screen = DungeonScreen(level=level, player_pos=(2, 2))
    app = AngbandMechanicumApp()
    app.game_engine = _FakeEngine()  # type: ignore[assignment]
    app.save_slot = "slot-1"
    app.dungeon_session = DungeonSession(state=screen.state)
    object.__setattr__(screen, "_parent", app)
    monkeypatch.setattr(screen, "_refresh_all", lambda: None)
    return screen, save_manager, app


class TestDungeonAutosave:
    def test_movement_autosaves_current_dungeon_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        level = _make_level()
        screen, save_manager, _app = _build_autosave_screen(level, monkeypatch)

        screen._step(1, 0)

        assert len(save_manager.saved) == 1
        slot_id, payload = save_manager.saved[0]
        assert slot_id == "slot-1"
        assert payload["mode"] == "dungeon"
        assert payload["dungeon_session"]["state"]["player_pos"] == [3, 2]

    def test_blocked_move_does_not_autosave(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        level = _make_level()
        screen, save_manager, _app = _build_autosave_screen(level, monkeypatch)

        screen._step(3, 0)

        assert save_manager.saved == []

    def test_wait_autosaves_after_rescan(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        level = _make_level()
        screen, save_manager, _app = _build_autosave_screen(level, monkeypatch)

        screen.action_wait()

        assert len(save_manager.saved) == 1
        assert save_manager.saved[0][1]["dungeon_session"]["state"]["messages"][-1] == (
            "You hold position and scan the chamber."
        )

    def test_transition_autosaves_after_travel_trigger(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        level = _make_level()
        level.set_terrain(3, 2, DungeonTerrain.STAIRS_DOWN)
        level.stairs_down = [(3, 2)]
        screen, save_manager, app = _build_autosave_screen(level, monkeypatch)
        transition_calls: list[bool] = []
        app.travel_dungeon_transition = lambda: transition_calls.append(True)  # type: ignore[assignment]

        screen._step(1, 0)

        assert transition_calls == [True]
        assert len(save_manager.saved) == 1
        assert save_manager.saved[0][1]["dungeon_session"]["state"]["player_pos"] == [3, 2]


class TestDungeonPanelFocus:
    @pytest.mark.asyncio
    async def test_tab_cycles_panels_and_log_scrolls(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-fake")
        app = AngbandMechanicumApp()
        story = StoryStart(
            id="focus-test",
            title="The Silent Forge",
            description="A forge goes silent.",
            location="Forge-Cathedral Alpha",
            intro_narrative="The forge awaits.",
            scene_art="ART",
        )
        session = app.build_dungeon_session(story)
        session.state.messages = [f"Log entry {i}" for i in range(40)]
        app.dungeon_session = session

        async with app.run_test(size=(120, 40)) as pilot:
            app.open_dungeon_view()
            await pilot.pause()

            assert app.screen.focused is not None
            assert app.screen.focused.id == "dungeon-map"

            await pilot.press("tab")
            await pilot.pause()
            assert app.screen.focused is not None
            assert app.screen.focused.id == "dungeon-log"

            log_pane = app.screen.query_one("#dungeon-log", DungeonMessageLog)
            log_pane.scroll_home()
            await pilot.press("pagedown")
            await pilot.pause()
            assert log_pane.scroll_y > 0

            await pilot.press("tab")
            await pilot.pause()
            assert app.screen.focused is not None
            assert app.screen.focused.id == "dungeon-status"

            await pilot.press("tab")
            await pilot.pause()
            assert app.screen.focused is not None
            assert app.screen.focused.id == "dungeon-inspect"

            await pilot.press("tab")
            await pilot.pause()
            assert app.screen.focused is not None
            assert app.screen.focused.id == "dungeon-map"


class TestDungeonExamineIntegration:
    @pytest.mark.asyncio
    async def test_game_engine_examine_prompt_includes_target_context(self, engine_with_mock_client: GameEngine) -> None:
        engine = engine_with_mock_client
        from tests.conftest import _make_api_response

        engine._client.messages.create.return_value = _make_api_response(
            '{"narrative_text": "A terminal hums.", "scene_art": "ART", "info_update": null, "entities": [], "combat_trigger": false, "speaking_npc": null}'
        )

        context = {
            "target_label": "Cogitator Terminal",
            "target_kind": "object",
            "terrain": "terminal",
            "target_position": [3, 2],
        }

        response = await engine.examine_dungeon_target(context)

        assert response.narrative_text == "A terminal hums."
        assert engine.turn_count == 0
        assert engine._conversation_history == []
        prompt = engine._client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Cogitator Terminal" in prompt
