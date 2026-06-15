"""Tests for models.actor — Actor data model."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.actor import Actor
from grimoire2d.models.components import TransformComponent, VelocityComponent


class TestActorDefaults(unittest.TestCase):

    def test_requires_actor_id(self):
        a = Actor(actor_id="hero")
        self.assertEqual(a.actor_id, "hero")

    def test_default_tags_empty(self):
        a = Actor(actor_id="x")
        self.assertEqual(a.tags, frozenset())

    def test_default_components_empty(self):
        a = Actor(actor_id="x")
        self.assertEqual(a.components, {})

    def test_default_active_true(self):
        a = Actor(actor_id="x")
        self.assertTrue(a.active)

    def test_default_version(self):
        a = Actor(actor_id="x")
        self.assertEqual(a.version, 1)


class TestActorTagHelpers(unittest.TestCase):

    def test_has_tag_present(self):
        a = Actor(actor_id="x", tags=frozenset({"enemy", "dynamic"}))
        self.assertTrue(a.has_tag("enemy"))

    def test_has_tag_absent(self):
        a = Actor(actor_id="x", tags=frozenset({"enemy"}))
        self.assertFalse(a.has_tag("player"))

    def test_has_tags_subset(self):
        a = Actor(actor_id="x", tags=frozenset({"enemy", "dynamic", "visible"}))
        self.assertTrue(a.has_tags({"enemy", "dynamic"}))

    def test_has_tags_superset_required_fails(self):
        a = Actor(actor_id="x", tags=frozenset({"enemy"}))
        self.assertFalse(a.has_tags({"enemy", "boss"}))

    def test_has_tags_empty_set_always_true(self):
        a = Actor(actor_id="x", tags=frozenset())
        self.assertTrue(a.has_tags(set()))


class TestActorImmutability(unittest.TestCase):

    def test_frozen_cannot_set_attribute(self):
        a = Actor(actor_id="x")
        with self.assertRaises(AttributeError):
            a.active = False  # type: ignore[misc]

    def test_with_updates_returns_new_instance(self):
        a = Actor(actor_id="x", active=True)
        a2 = a.with_updates(active=False)
        self.assertTrue(a.active)
        self.assertFalse(a2.active)

    def test_with_updates_does_not_mutate_original(self):
        tags = frozenset({"enemy"})
        a = Actor(actor_id="x", tags=tags)
        a.with_updates(tags=frozenset({"player"}))
        self.assertEqual(a.tags, tags)


class TestActorSerialization(unittest.TestCase):

    def test_to_dict_contains_required_keys(self):
        a = Actor(actor_id="hero", tags=frozenset({"player"}))
        d = a.to_dict()
        self.assertEqual(d["actor_id"], "hero")
        self.assertIn("player", d["tags"])
        self.assertIn("components", d)
        self.assertIn("active", d)

    def test_tags_serialized_as_sorted_list(self):
        a = Actor(actor_id="x", tags=frozenset({"z_tag", "a_tag"}))
        d = a.to_dict()
        self.assertEqual(d["tags"], ["a_tag", "z_tag"])

    def test_roundtrip_no_components(self):
        a = Actor(actor_id="hero", tags=frozenset({"player"}), active=True)
        restored = Actor.from_dict(a.to_dict())
        self.assertEqual(restored.actor_id, a.actor_id)
        self.assertEqual(restored.tags, a.tags)
        self.assertEqual(restored.active, a.active)

    def test_roundtrip_with_registered_component(self):
        tf = TransformComponent(x=10.0, y=20.0, angle=1.5)
        a = Actor(actor_id="hero", components={"transform": tf})
        restored = Actor.from_dict(a.to_dict())
        self.assertIsInstance(restored.components["transform"], TransformComponent)
        self.assertAlmostEqual(restored.components["transform"].x, 10.0)
        self.assertAlmostEqual(restored.components["transform"].angle, 1.5)

    def test_roundtrip_with_velocity_component(self):
        vel = VelocityComponent(vx=3.0, vy=-1.5)
        a = Actor(actor_id="ball", components={"velocity": vel})
        restored = Actor.from_dict(a.to_dict())
        self.assertIsInstance(restored.components["velocity"], VelocityComponent)
        self.assertAlmostEqual(restored.components["velocity"].vx, 3.0)

    def test_from_dict_unknown_component_stays_as_dict(self):
        data = {
            "actor_id": "x",
            "tags": [],
            "components": {"unknown_comp": {"foo": 42}},
            "active": True,
            "version": 1,
        }
        a = Actor.from_dict(data)
        self.assertIsInstance(a.components["unknown_comp"], dict)

    def test_from_dict_missing_keys_uses_defaults(self):
        a = Actor.from_dict({})
        self.assertEqual(a.actor_id, "")
        self.assertEqual(a.tags, frozenset())
        self.assertTrue(a.active)

    def test_components_serialized_via_to_dict(self):
        tf = TransformComponent(x=5.0, y=7.0)
        a = Actor(actor_id="x", components={"transform": tf})
        d = a.to_dict()
        self.assertIsInstance(d["components"]["transform"], dict)
        self.assertAlmostEqual(d["components"]["transform"]["x"], 5.0)


if __name__ == "__main__":
    unittest.main()
