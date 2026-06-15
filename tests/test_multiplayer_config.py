"""Tests for models.multiplayer — MultiplayerConfig, ViewportAssignment, SimulationState."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.multiplayer import (
    MultiplayerConfig,
    ViewportAssignment,
    SimulationState,
    TOPOLOGY_SHARED_SCREEN,
    TOPOLOGY_SPLIT_SCREEN,
    TOPOLOGY_NETWORK_HOST,
    TOPOLOGY_NETWORK_CLIENT,
)
from grimoire2d.models.player import PlayerIdentity, ROLE_LOCAL, ROLE_REMOTE


class TestViewportAssignment(unittest.TestCase):

    def test_defaults(self):
        va = ViewportAssignment()
        self.assertEqual(va.player_id, "*")
        self.assertEqual(va.x, 0.0)
        self.assertEqual(va.y, 0.0)

    def test_roundtrip_serialization(self):
        va = ViewportAssignment(player_id="P1", x=640.0, y=0.0, w=640.0, h=720.0)
        restored = ViewportAssignment.from_dict(va.to_dict())
        self.assertEqual(restored, va)


class TestSimulationState(unittest.TestCase):

    def test_defaults(self):
        s = SimulationState()
        self.assertEqual(s.tick, 0)

    def test_with_updates(self):
        s = SimulationState().with_updates(tick=10)
        self.assertEqual(s.tick, 10)

    def test_roundtrip_serialization(self):
        s = SimulationState(tick=42)
        restored = SimulationState.from_dict(s.to_dict())
        self.assertEqual(restored, s)


class TestMultiplayerConfig(unittest.TestCase):

    def test_single_player_factory(self):
        cfg = MultiplayerConfig.single_player()
        self.assertEqual(cfg.player_count, 1)
        self.assertEqual(cfg.topology, TOPOLOGY_SHARED_SCREEN)
        self.assertEqual(cfg.player_slots[0].role, ROLE_LOCAL)

    def test_local_two_player_shared(self):
        cfg = MultiplayerConfig.local_two_player_shared()
        self.assertEqual(cfg.player_count, 2)
        self.assertEqual(cfg.topology, TOPOLOGY_SHARED_SCREEN)
        self.assertTrue(all(p.role == ROLE_LOCAL for p in cfg.player_slots))

    def test_local_two_player_split(self):
        cfg = MultiplayerConfig.local_two_player_split()
        self.assertEqual(cfg.topology, TOPOLOGY_SPLIT_SCREEN)
        self.assertEqual(cfg.player_count, 2)

    def test_network_host_factory(self):
        cfg = MultiplayerConfig.network_host(host="0.0.0.0", port=9000)
        self.assertEqual(cfg.topology, TOPOLOGY_NETWORK_HOST)
        self.assertEqual(cfg.host, "0.0.0.0")
        self.assertEqual(cfg.port, 9000)
        roles = [p.role for p in cfg.player_slots]
        self.assertIn(ROLE_LOCAL, roles)
        self.assertIn(ROLE_REMOTE, roles)

    def test_network_client_factory(self):
        cfg = MultiplayerConfig.network_client(host="192.168.1.5", port=7777)
        self.assertEqual(cfg.topology, TOPOLOGY_NETWORK_CLIENT)
        self.assertEqual(cfg.host, "192.168.1.5")

    def test_invalid_topology_raises(self):
        with self.assertRaises(ValueError):
            MultiplayerConfig(topology="lan_party")

    def test_invalid_tick_rate_raises(self):
        with self.assertRaises(ValueError):
            MultiplayerConfig(tick_rate=0)
        with self.assertRaises(ValueError):
            MultiplayerConfig(tick_rate=-1)

    def test_player_ids(self):
        cfg = MultiplayerConfig.local_two_player_shared()
        ids = cfg.player_ids()
        self.assertIn("P1", ids)
        self.assertIn("P2", ids)

    def test_is_network(self):
        self.assertFalse(MultiplayerConfig.single_player().is_network())
        self.assertFalse(MultiplayerConfig.local_two_player_split().is_network())
        self.assertTrue(MultiplayerConfig.network_host().is_network())
        self.assertTrue(MultiplayerConfig.network_client("127.0.0.1").is_network())

    def test_roundtrip_serialization_single(self):
        cfg = MultiplayerConfig.single_player()
        restored = MultiplayerConfig.from_dict(cfg.to_dict())
        self.assertEqual(restored, cfg)

    def test_roundtrip_serialization_network(self):
        cfg = MultiplayerConfig.network_host(port=8080)
        restored = MultiplayerConfig.from_dict(cfg.to_dict())
        self.assertEqual(restored, cfg)

    def test_from_dict_missing_keys_uses_defaults(self):
        cfg = MultiplayerConfig.from_dict({})
        self.assertEqual(cfg.topology, TOPOLOGY_SHARED_SCREEN)
        self.assertEqual(cfg.tick_rate, 60)

    def test_registered_as_extension(self):
        from grimoire2d.models import EngineConfig
        engine = EngineConfig.default()
        self.assertIn("multiplayer", engine.extensions)
        self.assertIsInstance(engine.extensions["multiplayer"], MultiplayerConfig)

    def test_with_updates_immutable(self):
        cfg = MultiplayerConfig.single_player()
        cfg2 = cfg.with_updates(tick_rate=30)
        self.assertEqual(cfg2.tick_rate, 30)
        self.assertEqual(cfg.tick_rate, 60)


if __name__ == "__main__":
    unittest.main()
