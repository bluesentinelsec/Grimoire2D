"""Tests for logic.input_router — InputSource implementations and route_inputs."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.logic.input_router import (
    LocalInputSource,
    StaticInputSource,
    SequencedInputSource,
    route_inputs,
)
from grimoire2d.models.input_frame import InputFrame


class TestLocalInputSource(unittest.TestCase):

    def _make_source(self, pressed: frozenset[str]) -> LocalInputSource:
        bindings = {
            "move_left":  ["a", "left"],
            "move_right": ["d", "right"],
            "fire":       ["space"],
        }
        return LocalInputSource(
            player_id="P1",
            bindings=bindings,
            key_getter=lambda: pressed,
        )

    def test_player_id(self):
        src = self._make_source(frozenset())
        self.assertEqual(src.player_id, "P1")

    def test_no_keys_pressed(self):
        src = self._make_source(frozenset())
        frame = src.poll(tick=0)
        self.assertIsInstance(frame, InputFrame)
        self.assertEqual(frame.actions, frozenset())

    def test_single_action_primary_key(self):
        src = self._make_source(frozenset(["a"]))
        frame = src.poll(tick=1)
        self.assertIn("move_left", frame.actions)
        self.assertNotIn("fire", frame.actions)

    def test_single_action_alternate_key(self):
        src = self._make_source(frozenset(["left"]))
        frame = src.poll(tick=2)
        self.assertIn("move_left", frame.actions)

    def test_multiple_actions_simultaneously(self):
        src = self._make_source(frozenset(["a", "space"]))
        frame = src.poll(tick=3)
        self.assertIn("move_left", frame.actions)
        self.assertIn("fire", frame.actions)
        self.assertNotIn("move_right", frame.actions)

    def test_frame_tick_matches_argument(self):
        src = self._make_source(frozenset())
        frame = src.poll(tick=99)
        self.assertEqual(frame.tick, 99)

    def test_frame_player_id_matches(self):
        src = self._make_source(frozenset(["space"]))
        frame = src.poll(tick=0)
        self.assertEqual(frame.player_id, "P1")


class TestStaticInputSource(unittest.TestCase):

    def test_returns_fixed_actions_every_tick(self):
        src = StaticInputSource("P2", frozenset(["jump"]))
        for tick in range(5):
            frame = src.poll(tick)
            self.assertEqual(frame.actions, frozenset(["jump"]))
            self.assertEqual(frame.tick, tick)

    def test_empty_default_actions(self):
        src = StaticInputSource("P1")
        frame = src.poll(0)
        self.assertEqual(frame.actions, frozenset())

    def test_player_id(self):
        src = StaticInputSource("CPU")
        self.assertEqual(src.player_id, "CPU")


class TestSequencedInputSource(unittest.TestCase):

    def _frames(self) -> list[InputFrame]:
        return [
            InputFrame(player_id="P1", tick=i,
                       actions=frozenset([f"action_{i}"]))
            for i in range(3)
        ]

    def test_plays_back_in_order(self):
        seq = SequencedInputSource("P1", self._frames())
        for i in range(3):
            frame = seq.poll(i)
            self.assertIn(f"action_{i}", frame.actions)

    def test_returns_empty_when_exhausted(self):
        seq = SequencedInputSource("P1", self._frames())
        for _ in range(3):
            seq.poll(0)
        frame = seq.poll(99)
        self.assertEqual(frame.actions, frozenset())
        self.assertEqual(frame.player_id, "P1")

    def test_player_id_matches(self):
        seq = SequencedInputSource("P2", [])
        self.assertEqual(seq.player_id, "P2")


class TestRouteInputs(unittest.TestCase):

    def test_collects_frames_from_all_sources(self):
        sources = [
            StaticInputSource("P1", frozenset(["move_left"])),
            StaticInputSource("P2", frozenset(["fire"])),
        ]
        frames = route_inputs(sources, tick=5)
        self.assertEqual(len(frames), 2)
        pids = {f.player_id for f in frames}
        self.assertEqual(pids, {"P1", "P2"})

    def test_skips_sources_returning_none(self):
        class NullSource:
            player_id = "P3"
            def poll(self, tick):
                return None

        sources = [
            StaticInputSource("P1", frozenset()),
            NullSource(),
        ]
        frames = route_inputs(sources, tick=0)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].player_id, "P1")

    def test_empty_sources_returns_empty_list(self):
        self.assertEqual(route_inputs([], tick=0), [])

    def test_tick_propagated_to_frames(self):
        sources = [StaticInputSource("P1", frozenset())]
        frames = route_inputs(sources, tick=42)
        self.assertEqual(frames[0].tick, 42)

    def test_determinism_same_input_same_output(self):
        actions = frozenset(["jump", "fire"])
        sources = [StaticInputSource("P1", actions)]
        f1 = route_inputs(sources, tick=1)
        f2 = route_inputs(sources, tick=1)
        self.assertEqual(f1[0].actions, f2[0].actions)


if __name__ == "__main__":
    unittest.main()
