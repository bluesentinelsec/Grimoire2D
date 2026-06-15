"""Tests for models.player — PlayerIdentity and PlayerRoster."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.player import (
    PlayerIdentity,
    PlayerRoster,
    ROLE_LOCAL,
    ROLE_REMOTE,
    ROLE_AI,
    ROLE_REPLAY,
)


class TestPlayerIdentity(unittest.TestCase):

    def test_defaults(self):
        p = PlayerIdentity()
        self.assertEqual(p.player_id, "P1")
        self.assertEqual(p.role, ROLE_LOCAL)
        self.assertEqual(p.display_name, "")

    def test_valid_roles(self):
        for role in (ROLE_LOCAL, ROLE_REMOTE, ROLE_AI, ROLE_REPLAY):
            p = PlayerIdentity(player_id="P1", role=role)
            self.assertEqual(p.role, role)

    def test_invalid_role_raises(self):
        with self.assertRaises(ValueError):
            PlayerIdentity(player_id="P1", role="spectator")

    def test_empty_player_id_raises(self):
        with self.assertRaises(ValueError):
            PlayerIdentity(player_id="")

    def test_roundtrip_serialization(self):
        p = PlayerIdentity(player_id="P2", role=ROLE_REMOTE, display_name="Alice")
        restored = PlayerIdentity.from_dict(p.to_dict())
        self.assertEqual(restored, p)

    def test_with_updates_immutable(self):
        p = PlayerIdentity(player_id="P1")
        p2 = p.with_updates(display_name="Bob")
        self.assertEqual(p2.display_name, "Bob")
        self.assertEqual(p.display_name, "")  # original unchanged

    def test_from_dict_missing_keys_uses_defaults(self):
        p = PlayerIdentity.from_dict({})
        self.assertEqual(p.player_id, "P1")
        self.assertEqual(p.role, ROLE_LOCAL)


class TestPlayerRoster(unittest.TestCase):

    def test_single_player_factory(self):
        r = PlayerRoster.single_player()
        self.assertEqual(len(r.slots), 1)
        self.assertEqual(r.slots[0].player_id, "P1")
        self.assertEqual(r.slots[0].role, ROLE_LOCAL)

    def test_local_two_player_factory(self):
        r = PlayerRoster.local_two_player()
        self.assertEqual(len(r.slots), 2)
        ids = r.player_ids()
        self.assertIn("P1", ids)
        self.assertIn("P2", ids)

    def test_get_existing_player(self):
        r = PlayerRoster.local_two_player()
        p = r.get("P2")
        self.assertIsNotNone(p)
        self.assertEqual(p.player_id, "P2")

    def test_get_missing_player_returns_none(self):
        r = PlayerRoster.single_player()
        self.assertIsNone(r.get("P99"))

    def test_duplicate_ids_raises(self):
        with self.assertRaises(ValueError):
            PlayerRoster(slots=(
                PlayerIdentity(player_id="P1"),
                PlayerIdentity(player_id="P1"),
            ))

    def test_roundtrip_serialization(self):
        r = PlayerRoster.local_two_player()
        restored = PlayerRoster.from_dict(r.to_dict())
        self.assertEqual(restored, r)

    def test_empty_roster(self):
        r = PlayerRoster()
        self.assertEqual(r.player_ids(), ())

    def test_from_dict_missing_keys(self):
        r = PlayerRoster.from_dict({})
        self.assertEqual(len(r.slots), 0)


if __name__ == "__main__":
    unittest.main()
