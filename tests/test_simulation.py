"""Tests for logic.simulation — SimulationClock and advance_tick pattern."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.logic.simulation import SimulationClock
from grimoire2d.logic.input_router import StaticInputSource, route_inputs
from grimoire2d.models.input_frame import InputFrame


class TestSimulationClock(unittest.TestCase):

    def test_initial_state(self):
        clock = SimulationClock(tick_rate=60)
        self.assertEqual(clock.tick, 0)
        self.assertAlmostEqual(clock.tick_dt, 1.0 / 60, places=6)

    def test_single_tick_at_exact_boundary(self):
        clock = SimulationClock(tick_rate=60)
        n = clock.update(1.0 / 60)
        self.assertEqual(n, 1)
        self.assertEqual(clock.tick, 1)

    def test_no_tick_below_threshold(self):
        clock = SimulationClock(tick_rate=60)
        n = clock.update(0.001)
        self.assertEqual(n, 0)
        self.assertEqual(clock.tick, 0)

    def test_multiple_ticks_from_large_dt(self):
        clock = SimulationClock(tick_rate=60)
        n = clock.update(3.0 / 60)
        self.assertEqual(n, 3)
        self.assertEqual(clock.tick, 3)

    def test_capped_at_max_ticks_per_frame(self):
        clock = SimulationClock(tick_rate=60, max_ticks_per_frame=4)
        n = clock.update(10.0)
        self.assertLessEqual(n, 4)

    def test_accumulates_across_frames(self):
        clock = SimulationClock(tick_rate=60)
        total = 0
        for _ in range(60):
            total += clock.update(1.0 / 60)
        self.assertEqual(total, 60)
        self.assertEqual(clock.tick, 60)

    def test_fractional_accumulation(self):
        clock = SimulationClock(tick_rate=60)
        # Two half-ticks should yield exactly one tick
        clock.update(0.5 / 60)
        n = clock.update(0.5 / 60)
        self.assertEqual(n, 1)
        self.assertEqual(clock.tick, 1)

    def test_reset(self):
        clock = SimulationClock(tick_rate=60)
        clock.update(1.0)
        clock.reset()
        self.assertEqual(clock.tick, 0)
        n = clock.update(0.001)
        self.assertEqual(n, 0)

    def test_alpha_interpolation_factor(self):
        clock = SimulationClock(tick_rate=60)
        clock.update(0.5 / 60)
        self.assertGreater(clock.alpha, 0.0)
        self.assertLess(clock.alpha, 1.0)

    def test_alpha_zero_after_exact_tick(self):
        clock = SimulationClock(tick_rate=60)
        clock.update(1.0 / 60)
        self.assertAlmostEqual(clock.alpha, 0.0, places=5)


class TestAdvanceTickPattern(unittest.TestCase):
    """Demonstrates how a game wires SimulationClock + route_inputs + advance_tick.

    advance_tick is a game-supplied pure function; the engine does not define it.
    These tests show the wiring is correct using a trivial game state.
    """

    def _make_game_state(self):
        return {"score": 0, "moves": []}

    def _advance_tick(self, state: dict, frames: list[InputFrame]) -> dict:
        new_moves = list(state["moves"])
        new_score = state["score"]
        for frame in frames:
            if frame.has_action("score"):
                new_score += 1
            new_moves.append(frame.actions)
        return {"score": new_score, "moves": new_moves}

    def test_single_tick_single_player(self):
        clock = SimulationClock(tick_rate=60)
        source = StaticInputSource("P1", frozenset(["score"]))
        state = self._make_game_state()

        n = clock.update(1.0 / 60)
        for _ in range(n):
            frames = route_inputs([source], clock.tick)
            state = self._advance_tick(state, frames)

        self.assertEqual(state["score"], 1)

    def test_many_ticks_accumulate_state(self):
        clock = SimulationClock(tick_rate=60)
        source = StaticInputSource("P1", frozenset(["score"]))
        state = self._make_game_state()

        for _ in range(60):
            n = clock.update(1.0 / 60)
            for _ in range(n):
                frames = route_inputs([source], clock.tick)
                state = self._advance_tick(state, frames)

        self.assertEqual(state["score"], 60)

    def test_two_players_different_actions(self):
        clock = SimulationClock(tick_rate=60)
        p1 = StaticInputSource("P1", frozenset(["score"]))
        p2 = StaticInputSource("P2", frozenset())
        state = self._make_game_state()

        n = clock.update(1.0 / 60)
        for _ in range(n):
            frames = route_inputs([p1, p2], clock.tick)
            state = self._advance_tick(state, frames)

        self.assertEqual(state["score"], 1)

    def test_determinism_same_inputs_same_state(self):
        def run(actions):
            clock = SimulationClock(tick_rate=60)
            source = StaticInputSource("P1", frozenset(actions))
            state = self._make_game_state()
            for _ in range(10):
                n = clock.update(1.0 / 60)
                for _ in range(n):
                    frames = route_inputs([source], clock.tick)
                    state = self._advance_tick(state, frames)
            return state

        result_a = run(["score"])
        result_b = run(["score"])
        self.assertEqual(result_a, result_b)

    def test_no_input_no_state_change(self):
        clock = SimulationClock(tick_rate=60)
        source = StaticInputSource("P1", frozenset())
        state = self._make_game_state()

        for _ in range(5):
            n = clock.update(1.0 / 60)
            for _ in range(n):
                frames = route_inputs([source], clock.tick)
                state = self._advance_tick(state, frames)

        self.assertEqual(state["score"], 0)


if __name__ == "__main__":
    unittest.main()
