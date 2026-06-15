"""Tests for logic.network_protocol and presentation.tcp_transport.InMemoryTransport."""

import sys
import struct
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.logic.network_protocol import (
    encode_frame,
    decode_frame,
    encode_state,
    decode_state,
    read_length,
    LENGTH_PREFIX_SIZE,
)
from grimoire2d.models.input_frame import InputFrame
from grimoire2d.presentation.tcp_transport import InMemoryTransport


class TestLengthPrefix(unittest.TestCase):

    def test_prefix_size_is_4(self):
        self.assertEqual(LENGTH_PREFIX_SIZE, 4)

    def test_read_length_parses_correctly(self):
        n = 1234
        header = struct.pack("<I", n)
        self.assertEqual(read_length(header), n)

    def test_read_length_too_short_raises(self):
        with self.assertRaises(ValueError):
            read_length(b"\x00\x01")

    def test_prefix_matches_actual_payload(self):
        f = InputFrame(player_id="P1", tick=5, actions=frozenset(["fire"]))
        data = encode_frame(f)
        claimed_len = read_length(data[:LENGTH_PREFIX_SIZE])
        actual_payload_len = len(data) - LENGTH_PREFIX_SIZE
        self.assertEqual(claimed_len, actual_payload_len)


class TestFrameCodec(unittest.TestCase):

    def _roundtrip(self, frame: InputFrame) -> InputFrame:
        encoded = encode_frame(frame)
        payload = encoded[LENGTH_PREFIX_SIZE:]
        return decode_frame(payload)

    def test_empty_frame_roundtrip(self):
        f = InputFrame.empty("P1", 0)
        self.assertEqual(self._roundtrip(f), f)

    def test_frame_with_actions_roundtrip(self):
        f = InputFrame(player_id="P2", tick=42,
                       actions=frozenset(["jump", "move_right", "fire"]))
        restored = self._roundtrip(f)
        self.assertEqual(restored.player_id, "P2")
        self.assertEqual(restored.tick, 42)
        self.assertEqual(restored.actions, frozenset(["jump", "move_right", "fire"]))

    def test_unicode_player_id(self):
        f = InputFrame(player_id="Ångström", tick=1)
        self.assertEqual(self._roundtrip(f).player_id, "Ångström")

    def test_many_actions_roundtrip(self):
        actions = frozenset(f"action_{i}" for i in range(50))
        f = InputFrame(player_id="P1", tick=0, actions=actions)
        self.assertEqual(self._roundtrip(f).actions, actions)

    def test_large_tick_roundtrip(self):
        f = InputFrame(player_id="P1", tick=2**20)
        self.assertEqual(self._roundtrip(f).tick, 2**20)


class TestStateCodec(unittest.TestCase):

    def _roundtrip(self, d: dict) -> dict:
        encoded = encode_state(d)
        payload = encoded[LENGTH_PREFIX_SIZE:]
        return decode_state(payload)

    def test_empty_dict(self):
        self.assertEqual(self._roundtrip({}), {})

    def test_nested_dict(self):
        state = {"tick": 10, "players": {"P1": {"score": 5}}, "active": True}
        self.assertEqual(self._roundtrip(state), state)

    def test_list_values(self):
        state = {"actions": ["jump", "fire"]}
        restored = self._roundtrip(state)
        self.assertEqual(restored["actions"], ["jump", "fire"])


class TestInMemoryTransport(unittest.TestCase):

    def test_make_pair_creates_two_transports(self):
        a, b = InMemoryTransport.make_pair("P1", "P2")
        self.assertEqual(a.player_id, "P1")
        self.assertEqual(b.player_id, "P2")

    def test_send_from_a_received_by_b(self):
        a, b = InMemoryTransport.make_pair("P1", "P2")
        frame = InputFrame(player_id="P1", tick=3, actions=frozenset(["fire"]))
        a.send_frame(frame)
        received = b.poll(tick=3)
        self.assertIsNotNone(received)
        self.assertEqual(received.player_id, "P1")
        self.assertEqual(received.actions, frozenset(["fire"]))

    def test_send_from_b_received_by_a(self):
        a, b = InMemoryTransport.make_pair("P1", "P2")
        frame = InputFrame(player_id="P2", tick=1, actions=frozenset(["jump"]))
        b.send_frame(frame)
        received = a.poll(tick=1)
        self.assertIsNotNone(received)
        self.assertEqual(received.player_id, "P2")

    def test_poll_returns_none_when_empty(self):
        a, b = InMemoryTransport.make_pair("P1", "P2")
        self.assertIsNone(a.poll(0))
        self.assertIsNone(b.poll(0))

    def test_fifo_ordering(self):
        a, b = InMemoryTransport.make_pair("P1", "P2")
        for tick in range(5):
            a.send_frame(InputFrame(player_id="P1", tick=tick))
        received_ticks = [b.poll(0).tick for _ in range(5)]
        self.assertEqual(received_ticks, list(range(5)))

    def test_transport_as_input_source_in_route_inputs(self):
        """InMemoryTransport satisfies the InputSource protocol for route_inputs."""
        from grimoire2d.logic.input_router import route_inputs
        a, b = InMemoryTransport.make_pair("P1", "P2")
        frame = InputFrame(player_id="P1", tick=7, actions=frozenset(["score"]))
        a.send_frame(frame)
        frames = route_inputs([b], tick=7)
        self.assertEqual(len(frames), 1)
        self.assertTrue(frames[0].has_action("score"))

    def test_independent_channels(self):
        """Each direction has its own independent queue."""
        a, b = InMemoryTransport.make_pair("P1", "P2")
        a.send_frame(InputFrame(player_id="P1", tick=0, actions=frozenset(["A"])))
        b.send_frame(InputFrame(player_id="P2", tick=0, actions=frozenset(["B"])))
        from_a = b.poll(0)
        from_b = a.poll(0)
        self.assertIn("A", from_a.actions)
        self.assertIn("B", from_b.actions)


if __name__ == "__main__":
    unittest.main()
