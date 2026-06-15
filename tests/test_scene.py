"""Tests for models.scene — Scene data model and status constants."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.scene import (
    Scene,
    SCENE_STATUS_LOADING,
    SCENE_STATUS_ACTIVE,
    SCENE_STATUS_PAUSED,
    SCENE_STATUS_CLOSING,
    SCENE_STATUS_CLOSED,
)


class TestSceneDefaults(unittest.TestCase):

    def test_requires_scene_id_and_name(self):
        s = Scene(scene_id="s1", name="Main")
        self.assertEqual(s.scene_id, "s1")
        self.assertEqual(s.name, "Main")

    def test_default_status_active(self):
        s = Scene(scene_id="s1", name="Main")
        self.assertEqual(s.status, SCENE_STATUS_ACTIVE)

    def test_default_actor_ids_empty(self):
        s = Scene(scene_id="s1", name="Main")
        self.assertEqual(s.actor_ids, frozenset())

    def test_actor_count_zero_by_default(self):
        s = Scene(scene_id="s1", name="Main")
        self.assertEqual(s.actor_count, 0)

    def test_is_active_true_when_active(self):
        s = Scene(scene_id="s1", name="Main", status=SCENE_STATUS_ACTIVE)
        self.assertTrue(s.is_active())

    def test_is_active_false_when_paused(self):
        s = Scene(scene_id="s1", name="Main", status=SCENE_STATUS_PAUSED)
        self.assertFalse(s.is_active())


class TestSceneStatusConstants(unittest.TestCase):

    def test_all_five_statuses_exist(self):
        statuses = {
            SCENE_STATUS_LOADING, SCENE_STATUS_ACTIVE, SCENE_STATUS_PAUSED,
            SCENE_STATUS_CLOSING, SCENE_STATUS_CLOSED,
        }
        self.assertEqual(len(statuses), 5)

    def test_invalid_status_raises_value_error(self):
        with self.assertRaises(ValueError):
            Scene(scene_id="x", name="Bad", status="nonexistent")

    def test_all_valid_statuses_accepted(self):
        for st in (SCENE_STATUS_LOADING, SCENE_STATUS_ACTIVE, SCENE_STATUS_PAUSED,
                   SCENE_STATUS_CLOSING, SCENE_STATUS_CLOSED):
            s = Scene(scene_id="x", name="N", status=st)
            self.assertEqual(s.status, st)


class TestSceneActorIds(unittest.TestCase):

    def test_actor_count_reflects_ids(self):
        s = Scene(scene_id="s1", name="N", actor_ids=frozenset({"a1", "a2", "a3"}))
        self.assertEqual(s.actor_count, 3)

    def test_actor_ids_is_frozenset(self):
        s = Scene(scene_id="s1", name="N", actor_ids=frozenset({"a1"}))
        self.assertIsInstance(s.actor_ids, frozenset)


class TestSceneImmutability(unittest.TestCase):

    def test_frozen_cannot_set_attribute(self):
        s = Scene(scene_id="s1", name="N")
        with self.assertRaises(AttributeError):
            s.name = "Other"  # type: ignore[misc]

    def test_with_updates_returns_new_instance(self):
        s = Scene(scene_id="s1", name="N", status=SCENE_STATUS_ACTIVE)
        s2 = s.with_updates(status=SCENE_STATUS_CLOSING)
        self.assertEqual(s.status, SCENE_STATUS_ACTIVE)
        self.assertEqual(s2.status, SCENE_STATUS_CLOSING)


class TestSceneSerialization(unittest.TestCase):

    def test_to_dict_contains_required_keys(self):
        s = Scene(scene_id="s1", name="Gameplay",
                  actor_ids=frozenset({"a1", "a2"}))
        d = s.to_dict()
        self.assertEqual(d["scene_id"], "s1")
        self.assertEqual(d["name"], "Gameplay")
        self.assertEqual(d["status"], SCENE_STATUS_ACTIVE)
        self.assertIsInstance(d["actor_ids"], list)
        self.assertEqual(sorted(d["actor_ids"]), ["a1", "a2"])

    def test_actor_ids_serialized_sorted(self):
        s = Scene(scene_id="s1", name="N", actor_ids=frozenset({"z", "a", "m"}))
        d = s.to_dict()
        self.assertEqual(d["actor_ids"], ["a", "m", "z"])

    def test_roundtrip(self):
        s = Scene(
            scene_id="gameplay",
            name="Gameplay",
            status=SCENE_STATUS_PAUSED,
            actor_ids=frozenset({"hero", "enemy_1"}),
        )
        restored = Scene.from_dict(s.to_dict())
        self.assertEqual(restored.scene_id, s.scene_id)
        self.assertEqual(restored.name, s.name)
        self.assertEqual(restored.status, s.status)
        self.assertEqual(restored.actor_ids, s.actor_ids)

    def test_from_dict_missing_keys_uses_defaults(self):
        s = Scene.from_dict({"scene_id": "x", "name": "N"})
        self.assertEqual(s.status, SCENE_STATUS_ACTIVE)
        self.assertEqual(s.actor_ids, frozenset())


if __name__ == "__main__":
    unittest.main()
