"""Tests for models.input_frame — InputFrame and InputBuffer."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.input_frame import InputFrame, InputBuffer


class TestInputFrame(unittest.TestCase):

    def test_defaults(self):
        f = InputFrame()
        self.assertEqual(f.player_id, "")
        self.assertEqual(f.tick, 0)
        self.assertEqual(f.actions, frozenset())

    def test_has_action_true_and_false(self):
        f = InputFrame(player_id="P1", tick=5, actions=frozenset(["move_left", "fire"]))
        self.assertTrue(f.has_action("move_left"))
        self.assertTrue(f.has_action("fire"))
        self.assertFalse(f.has_action("jump"))

    def test_roundtrip_serialization(self):
        f = InputFrame(player_id="P2", tick=42, actions=frozenset(["jump", "fire"]))
        restored = InputFrame.from_dict(f.to_dict())
        self.assertEqual(restored, f)

    def test_with_updates_actions_coerced_to_frozenset(self):
        f = InputFrame(player_id="P1", tick=0)
        f2 = f.with_updates(actions=["move_right"])
        self.assertIsInstance(f2.actions, frozenset)
        self.assertIn("move_right", f2.actions)

    def test_empty_factory(self):
        f = InputFrame.empty("P3", 10)
        self.assertEqual(f.player_id, "P3")
        self.assertEqual(f.tick, 10)
        self.assertEqual(len(f.actions), 0)

    def test_from_dict_missing_keys(self):
        f = InputFrame.from_dict({})
        self.assertEqual(f.player_id, "")
        self.assertEqual(f.tick, 0)

    def test_actions_sorted_in_dict(self):
        f = InputFrame(actions=frozenset(["z_last", "a_first"]))
        d = f.to_dict()
        self.assertEqual(d["actions"], sorted(["z_last", "a_first"]))


class TestInputBuffer(unittest.TestCase):

    def test_empty_factory(self):
        buf = InputBuffer.empty()
        self.assertEqual(buf.frames_for("P1"), ())
        self.assertEqual(buf.confirmed_tick, 0)

    def test_push_single_frame(self):
        buf = InputBuffer.empty()
        f = InputFrame(player_id="P1", tick=1, actions=frozenset(["fire"]))
        buf = buf.push(f)
        self.assertEqual(len(buf.frames_for("P1")), 1)
        self.assertEqual(buf.frames_for("P1")[0], f)

    def test_push_multiple_players(self):
        buf = InputBuffer.empty()
        f1 = InputFrame(player_id="P1", tick=1)
        f2 = InputFrame(player_id="P2", tick=1)
        buf = buf.push(f1).push(f2)
        self.assertEqual(len(buf.frames_for("P1")), 1)
        self.assertEqual(len(buf.frames_for("P2")), 1)

    def test_push_preserves_order(self):
        buf = InputBuffer.empty()
        frames = [InputFrame(player_id="P1", tick=i) for i in range(5)]
        for f in frames:
            buf = buf.push(f)
        stored = buf.frames_for("P1")
        self.assertEqual([f.tick for f in stored], list(range(5)))

    def test_drain_up_to_returns_correct_frames(self):
        buf = InputBuffer.empty()
        for tick in range(10):
            buf = buf.push(InputFrame(player_id="P1", tick=tick))
        ready, new_buf = buf.drain_up_to(4)
        ready_ticks = sorted(f.tick for f in ready)
        self.assertEqual(ready_ticks, [0, 1, 2, 3, 4])
        remaining = new_buf.frames_for("P1")
        self.assertEqual([f.tick for f in remaining], [5, 6, 7, 8, 9])

    def test_drain_updates_confirmed_tick(self):
        buf = InputBuffer.empty()
        buf = buf.push(InputFrame(player_id="P1", tick=3))
        _, new_buf = buf.drain_up_to(3)
        self.assertEqual(new_buf.confirmed_tick, 3)

    def test_roundtrip_serialization(self):
        buf = InputBuffer.empty()
        buf = buf.push(InputFrame(player_id="P1", tick=1, actions=frozenset(["jump"])))
        buf = buf.push(InputFrame(player_id="P2", tick=1))
        restored = InputBuffer.from_dict(buf.to_dict())
        self.assertEqual(restored.frames_for("P1")[0].actions, frozenset(["jump"]))
        self.assertEqual(len(restored.frames_for("P2")), 1)

    def test_immutability(self):
        buf = InputBuffer.empty()
        buf2 = buf.push(InputFrame(player_id="P1", tick=0))
        self.assertEqual(buf.frames_for("P1"), ())  # original unchanged
        self.assertEqual(len(buf2.frames_for("P1")), 1)


if __name__ == "__main__":
    unittest.main()
