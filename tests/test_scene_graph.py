"""Tests for models.scene_graph — SceneGraph data model."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.actor import Actor
from grimoire2d.models.components import TransformComponent
from grimoire2d.models.scene import Scene, SCENE_STATUS_ACTIVE
from grimoire2d.models.scene_graph import SceneGraph


def _make_scene(sid: str, name: str = "Test") -> Scene:
    return Scene(scene_id=sid, name=name)


def _make_actor(aid: str, **kwargs) -> Actor:
    return Actor(actor_id=aid, **kwargs)


class TestSceneGraphDefaults(unittest.TestCase):

    def test_empty_by_default(self):
        g = SceneGraph()
        self.assertEqual(g.scenes, {})
        self.assertEqual(g.actors, {})
        self.assertIsNone(g.active_scene_id)

    def test_scene_count_zero(self):
        self.assertEqual(SceneGraph().scene_count, 0)

    def test_actor_count_zero(self):
        self.assertEqual(SceneGraph().actor_count, 0)

    def test_get_active_scene_none_when_no_active(self):
        g = SceneGraph(scenes={"s1": _make_scene("s1")})
        self.assertIsNone(g.get_active_scene())

    def test_get_active_scene_returns_scene(self):
        s = _make_scene("s1")
        g = SceneGraph(scenes={"s1": s}, active_scene_id="s1")
        self.assertEqual(g.get_active_scene(), s)

    def test_get_active_scene_missing_id_returns_none(self):
        g = SceneGraph(active_scene_id="ghost")
        self.assertIsNone(g.get_active_scene())


class TestSceneGraphImmutability(unittest.TestCase):

    def test_frozen(self):
        g = SceneGraph()
        with self.assertRaises(AttributeError):
            g.active_scene_id = "s1"  # type: ignore[misc]

    def test_with_updates_returns_new_instance(self):
        g = SceneGraph()
        g2 = g.with_updates(active_scene_id="s1")
        self.assertIsNone(g.active_scene_id)
        self.assertEqual(g2.active_scene_id, "s1")


class TestSceneGraphSerialization(unittest.TestCase):

    def test_to_dict_keys(self):
        g = SceneGraph()
        d = g.to_dict()
        self.assertIn("scenes", d)
        self.assertIn("actors", d)
        self.assertIn("active_scene_id", d)

    def test_roundtrip_empty(self):
        g = SceneGraph()
        restored = SceneGraph.from_dict(g.to_dict())
        self.assertEqual(restored.scenes, {})
        self.assertEqual(restored.actors, {})
        self.assertIsNone(restored.active_scene_id)

    def test_roundtrip_with_scenes_and_actors(self):
        tf = TransformComponent(x=5.0, y=10.0)
        actor = Actor(actor_id="hero", tags=frozenset({"player"}),
                      components={"transform": tf})
        scene = Scene(scene_id="level1", name="Level 1",
                      actor_ids=frozenset({"hero"}))
        g = SceneGraph(
            scenes={"level1": scene},
            actors={"hero": actor},
            active_scene_id="level1",
        )
        restored = SceneGraph.from_dict(g.to_dict())
        self.assertIn("level1", restored.scenes)
        self.assertIn("hero", restored.actors)
        self.assertEqual(restored.active_scene_id, "level1")
        self.assertIsInstance(restored.actors["hero"].components["transform"],
                              TransformComponent)

    def test_from_dict_missing_keys_uses_defaults(self):
        g = SceneGraph.from_dict({})
        self.assertEqual(g.scenes, {})
        self.assertIsNone(g.active_scene_id)

    def test_scene_membership_preserved(self):
        scene = Scene(scene_id="s1", name="N", actor_ids=frozenset({"a1", "a2"}))
        g = SceneGraph(scenes={"s1": scene})
        restored = SceneGraph.from_dict(g.to_dict())
        self.assertEqual(restored.scenes["s1"].actor_ids, frozenset({"a1", "a2"}))


if __name__ == "__main__":
    unittest.main()
