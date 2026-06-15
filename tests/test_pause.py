"""Tests for models.pause and logic.pause_logic."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.pause import (
    PauseState,
    GROUP_GAMEPLAY,
    GROUP_AUDIO,
    GROUP_UI,
    GROUP_INPUT,
)
from grimoire2d.models.multiplayer import MultiplayerConfig
from grimoire2d.logic.pause_logic import (
    can_pause,
    request_pause,
    request_unpause,
    toggle_pause,
    is_paused,
)


# ---------------------------------------------------------------------------
# PauseState model
# ---------------------------------------------------------------------------

class TestPauseState(unittest.TestCase):

    def test_running_factory_all_unpaused(self):
        ps = PauseState.running()
        for group in (GROUP_GAMEPLAY, GROUP_AUDIO, GROUP_UI, GROUP_INPUT):
            self.assertFalse(ps.is_paused(group))

    def test_unknown_group_is_not_paused(self):
        ps = PauseState.running()
        self.assertFalse(ps.is_paused("nonexistent_group"))

    def test_with_group_pauses_one_group(self):
        ps = PauseState.running().with_group(GROUP_GAMEPLAY, True)
        self.assertTrue(ps.is_paused(GROUP_GAMEPLAY))
        self.assertFalse(ps.is_paused(GROUP_AUDIO))
        self.assertFalse(ps.is_paused(GROUP_UI))

    def test_with_group_unpauses(self):
        ps = PauseState.running().with_group(GROUP_GAMEPLAY, True)
        ps = ps.with_group(GROUP_GAMEPLAY, False)
        self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))

    def test_multiple_independent_groups(self):
        ps = (PauseState.running()
              .with_group(GROUP_GAMEPLAY, True)
              .with_group(GROUP_AUDIO, True))
        self.assertTrue(ps.is_paused(GROUP_GAMEPLAY))
        self.assertTrue(ps.is_paused(GROUP_AUDIO))
        self.assertFalse(ps.is_paused(GROUP_UI))
        self.assertFalse(ps.is_paused(GROUP_INPUT))

    def test_game_defined_group(self):
        ps = PauseState.running().with_group("particles", True)
        self.assertTrue(ps.is_paused("particles"))
        self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))

    def test_any_paused_false_when_all_running(self):
        self.assertFalse(PauseState.running().any_paused())

    def test_any_paused_true_when_one_group_paused(self):
        ps = PauseState.running().with_group(GROUP_GAMEPLAY, True)
        self.assertTrue(ps.any_paused())

    def test_immutability(self):
        ps = PauseState.running()
        ps2 = ps.with_group(GROUP_GAMEPLAY, True)
        self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))  # original unchanged
        self.assertTrue(ps2.is_paused(GROUP_GAMEPLAY))

    def test_roundtrip_serialization_all_running(self):
        ps = PauseState.running()
        restored = PauseState.from_dict(ps.to_dict())
        self.assertEqual(restored, ps)

    def test_roundtrip_serialization_some_paused(self):
        ps = (PauseState.running()
              .with_group(GROUP_GAMEPLAY, True)
              .with_group("custom", True))
        restored = PauseState.from_dict(ps.to_dict())
        self.assertTrue(restored.is_paused(GROUP_GAMEPLAY))
        self.assertTrue(restored.is_paused("custom"))
        self.assertFalse(restored.is_paused(GROUP_AUDIO))

    def test_from_dict_missing_keys_defaults_to_running(self):
        ps = PauseState.from_dict({})
        self.assertFalse(ps.any_paused())

    def test_registered_as_engine_config_extension(self):
        from grimoire2d.models import EngineConfig
        engine = EngineConfig.default()
        self.assertIn("pause", engine.extensions)
        self.assertIsInstance(engine.extensions["pause"], PauseState)


# ---------------------------------------------------------------------------
# can_pause
# ---------------------------------------------------------------------------

class TestCanPause(unittest.TestCase):

    def test_single_player_can_pause(self):
        self.assertTrue(can_pause(MultiplayerConfig.single_player()))

    def test_local_shared_screen_can_pause(self):
        self.assertTrue(can_pause(MultiplayerConfig.local_two_player_shared()))

    def test_local_split_screen_can_pause(self):
        self.assertTrue(can_pause(MultiplayerConfig.local_two_player_split()))

    def test_network_host_cannot_pause(self):
        self.assertFalse(can_pause(MultiplayerConfig.network_host()))

    def test_network_client_cannot_pause(self):
        self.assertFalse(can_pause(MultiplayerConfig.network_client("127.0.0.1")))


# ---------------------------------------------------------------------------
# request_pause / request_unpause
# ---------------------------------------------------------------------------

class TestRequestPause(unittest.TestCase):

    def test_pauses_gameplay_for_local_game(self):
        cfg = MultiplayerConfig.single_player()
        ps = request_pause(PauseState.running(), cfg)
        self.assertTrue(ps.is_paused(GROUP_GAMEPLAY))

    def test_does_not_pause_audio_or_ui(self):
        cfg = MultiplayerConfig.single_player()
        ps = request_pause(PauseState.running(), cfg)
        self.assertFalse(ps.is_paused(GROUP_AUDIO))
        self.assertFalse(ps.is_paused(GROUP_UI))
        self.assertFalse(ps.is_paused(GROUP_INPUT))

    def test_network_host_pause_is_noop(self):
        cfg = MultiplayerConfig.network_host()
        ps = PauseState.running()
        result = request_pause(ps, cfg)
        self.assertFalse(result.is_paused(GROUP_GAMEPLAY))
        self.assertEqual(result, ps)

    def test_network_client_pause_is_noop(self):
        cfg = MultiplayerConfig.network_client("10.0.0.1")
        ps = PauseState.running()
        result = request_pause(ps, cfg)
        self.assertEqual(result, ps)

    def test_request_unpause_clears_gameplay(self):
        cfg = MultiplayerConfig.single_player()
        ps = request_pause(PauseState.running(), cfg)
        ps = request_unpause(ps)
        self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))

    def test_unpause_on_running_state_is_safe(self):
        ps = request_unpause(PauseState.running())
        self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))


# ---------------------------------------------------------------------------
# toggle_pause
# ---------------------------------------------------------------------------

class TestTogglePause(unittest.TestCase):

    def test_toggle_pauses_when_running(self):
        cfg = MultiplayerConfig.single_player()
        ps = toggle_pause(PauseState.running(), cfg)
        self.assertTrue(ps.is_paused(GROUP_GAMEPLAY))

    def test_toggle_unpauses_when_paused(self):
        cfg = MultiplayerConfig.single_player()
        ps = PauseState.running().with_group(GROUP_GAMEPLAY, True)
        ps = toggle_pause(ps, cfg)
        self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))

    def test_double_toggle_returns_to_running(self):
        cfg = MultiplayerConfig.single_player()
        ps = PauseState.running()
        ps = toggle_pause(ps, cfg)
        ps = toggle_pause(ps, cfg)
        self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))

    def test_network_toggle_is_always_noop(self):
        cfg = MultiplayerConfig.network_host()
        ps = PauseState.running()
        for _ in range(5):
            ps = toggle_pause(ps, cfg)
            self.assertFalse(ps.is_paused(GROUP_GAMEPLAY))


# ---------------------------------------------------------------------------
# is_paused convenience wrapper
# ---------------------------------------------------------------------------

class TestIsPaused(unittest.TestCase):

    def test_delegates_to_pause_state(self):
        ps = PauseState.running().with_group(GROUP_GAMEPLAY, True)
        self.assertTrue(is_paused(ps, GROUP_GAMEPLAY))
        self.assertFalse(is_paused(ps, GROUP_AUDIO))

    def test_unpaused_state(self):
        ps = PauseState.running()
        self.assertFalse(is_paused(ps, GROUP_GAMEPLAY))


# ---------------------------------------------------------------------------
# Integration: simulation respects pause group
# ---------------------------------------------------------------------------

class TestSimulationRespectsPause(unittest.TestCase):
    """Shows the intended game-loop pattern: gameplay only advances when
    the gameplay group is running."""

    def _advance(self, state: dict, paused: bool) -> dict:
        if not paused:
            state = {**state, "tick": state["tick"] + 1}
        return state

    def test_tick_advances_when_unpaused(self):
        cfg = MultiplayerConfig.single_player()
        ps = PauseState.running()
        state = {"tick": 0}
        for _ in range(10):
            state = self._advance(state, is_paused(ps, GROUP_GAMEPLAY))
        self.assertEqual(state["tick"], 10)

    def test_tick_freezes_when_paused(self):
        cfg = MultiplayerConfig.single_player()
        ps = request_pause(PauseState.running(), cfg)
        state = {"tick": 0}
        for _ in range(10):
            state = self._advance(state, is_paused(ps, GROUP_GAMEPLAY))
        self.assertEqual(state["tick"], 0)

    def test_tick_resumes_after_unpause(self):
        cfg = MultiplayerConfig.single_player()
        ps = PauseState.running()
        state = {"tick": 0}

        # 5 ticks running
        for _ in range(5):
            state = self._advance(state, is_paused(ps, GROUP_GAMEPLAY))

        # pause for 5 ticks
        ps = request_pause(ps, cfg)
        for _ in range(5):
            state = self._advance(state, is_paused(ps, GROUP_GAMEPLAY))

        # unpause and run 5 more
        ps = request_unpause(ps)
        for _ in range(5):
            state = self._advance(state, is_paused(ps, GROUP_GAMEPLAY))

        self.assertEqual(state["tick"], 10)


if __name__ == "__main__":
    unittest.main()
