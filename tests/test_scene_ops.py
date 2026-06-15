"""Tests for logic.scene_ops — all 13 pure scene/actor CRUD functions."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grimoire2d.models.components import TransformComponent
from grimoire2d.models.scene import (
    SCENE_STATUS_ACTIVE,
    SCENE_STATUS_CLOSING,
    SCENE_STATUS_LOADING,
)
from grimoire2d.models.scene_graph import SceneGraph
from grimoire2d.logic.scene_ops import (
    create_scene,
    close_scene,
    set_active_scene,
    query_scenes,
    get_scene,
    spawn_actor,
    destroy_actor,
    set_actor_active,
    query_actors,
    get_actor,
    update_component,
    get_component,
    remove_component,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _graph_with_scene(sid: str = "s1", name: str = "Main") -> tuple[SceneGraph, str]:
    return create_scene(SceneGraph(), name, scene_id=sid)


def _graph_with_actor(
    sid: str = "s1", aid: str = "a1",
    tags: frozenset[str] = frozenset(),
) -> tuple[SceneGraph, str, str]:
    g, _ = _graph_with_scene(sid)
    g, actual_aid = spawn_actor(g, sid, tags=tags, actor_id=aid)
    return g, sid, actual_aid


# ---------------------------------------------------------------------------
# create_scene
# ---------------------------------------------------------------------------

class TestCreateScene(unittest.TestCase):

    def test_returns_graph_and_id(self):
        g, sid = create_scene(SceneGraph(), "Main", scene_id="main")
        self.assertEqual(sid, "main")
        self.assertIn("main", g.scenes)

    def test_scene_has_correct_name(self):
        g, sid = create_scene(SceneGraph(), "Level 1", scene_id="l1")
        self.assertEqual(g.scenes["l1"].name, "Level 1")

    def test_auto_generated_id_when_none(self):
        g, sid = create_scene(SceneGraph(), "Auto")
        self.assertIn(sid, g.scenes)
        self.assertEqual(len(sid), 36)  # UUID4 length

    def test_default_status_active(self):
        g, sid = create_scene(SceneGraph(), "X", scene_id="x")
        self.assertEqual(g.scenes["x"].status, SCENE_STATUS_ACTIVE)

    def test_custom_status(self):
        g, sid = create_scene(SceneGraph(), "X", scene_id="x",
                              status=SCENE_STATUS_LOADING)
        self.assertEqual(g.scenes["x"].status, SCENE_STATUS_LOADING)

    def test_multiple_scenes(self):
        g = SceneGraph()
        g, _ = create_scene(g, "A", scene_id="a")
        g, _ = create_scene(g, "B", scene_id="b")
        self.assertEqual(len(g.scenes), 2)

    def test_original_graph_unchanged(self):
        original = SceneGraph()
        create_scene(original, "X")
        self.assertEqual(original.scene_count, 0)


# ---------------------------------------------------------------------------
# close_scene
# ---------------------------------------------------------------------------

class TestCloseScene(unittest.TestCase):

    def test_transitions_to_closing(self):
        g, sid = _graph_with_scene()
        g2 = close_scene(g, sid)
        self.assertEqual(g2.scenes[sid].status, SCENE_STATUS_CLOSING)

    def test_original_unchanged(self):
        g, sid = _graph_with_scene()
        close_scene(g, sid)
        self.assertEqual(g.scenes[sid].status, SCENE_STATUS_ACTIVE)

    def test_noop_if_scene_missing(self):
        g = SceneGraph()
        g2 = close_scene(g, "ghost")
        self.assertEqual(g2, g)


# ---------------------------------------------------------------------------
# set_active_scene
# ---------------------------------------------------------------------------

class TestSetActiveScene(unittest.TestCase):

    def test_sets_active_scene_id(self):
        g, sid = _graph_with_scene("main")
        g2 = set_active_scene(g, "main")
        self.assertEqual(g2.active_scene_id, "main")

    def test_raises_if_missing(self):
        with self.assertRaises(KeyError):
            set_active_scene(SceneGraph(), "ghost")


# ---------------------------------------------------------------------------
# query_scenes
# ---------------------------------------------------------------------------

class TestQueryScenes(unittest.TestCase):

    def test_returns_all_without_filter(self):
        g, _ = _graph_with_scene("a")
        g, _ = create_scene(g, "B", scene_id="b")
        self.assertEqual(len(query_scenes(g)), 2)

    def test_filter_by_status(self):
        g, _ = _graph_with_scene("a")
        g, sid_b = create_scene(g, "B", scene_id="b")
        g = close_scene(g, sid_b)
        active = query_scenes(g, status=SCENE_STATUS_ACTIVE)
        closing = query_scenes(g, status=SCENE_STATUS_CLOSING)
        self.assertEqual(len(active), 1)
        self.assertEqual(len(closing), 1)

    def test_empty_graph_returns_empty(self):
        self.assertEqual(query_scenes(SceneGraph()), [])


# ---------------------------------------------------------------------------
# get_scene
# ---------------------------------------------------------------------------

class TestGetScene(unittest.TestCase):

    def test_returns_scene(self):
        g, sid = _graph_with_scene("s1", "Main")
        s = get_scene(g, "s1")
        self.assertIsNotNone(s)
        self.assertEqual(s.name, "Main")

    def test_returns_none_if_missing(self):
        self.assertIsNone(get_scene(SceneGraph(), "ghost"))


# ---------------------------------------------------------------------------
# spawn_actor
# ---------------------------------------------------------------------------

class TestSpawnActor(unittest.TestCase):

    def test_returns_graph_and_id(self):
        g, sid = _graph_with_scene()
        g2, aid = spawn_actor(g, sid, actor_id="hero")
        self.assertEqual(aid, "hero")
        self.assertIn("hero", g2.actors)

    def test_actor_added_to_scene_membership(self):
        g, sid = _graph_with_scene()
        g2, aid = spawn_actor(g, sid, actor_id="hero")
        self.assertIn("hero", g2.scenes[sid].actor_ids)

    def test_tags_assigned(self):
        g, sid = _graph_with_scene()
        g2, aid = spawn_actor(g, sid, tags={"player", "dynamic"}, actor_id="hero")
        self.assertEqual(g2.actors["hero"].tags, frozenset({"player", "dynamic"}))

    def test_components_assigned(self):
        g, sid = _graph_with_scene()
        tf = TransformComponent(x=10.0)
        g2, aid = spawn_actor(g, sid, components={"transform": tf}, actor_id="h")
        self.assertEqual(g2.actors["h"].components["transform"].x, 10.0)

    def test_auto_uuid_when_no_actor_id(self):
        g, sid = _graph_with_scene()
        g2, aid = spawn_actor(g, sid)
        self.assertEqual(len(aid), 36)

    def test_raises_if_scene_missing(self):
        with self.assertRaises(KeyError):
            spawn_actor(SceneGraph(), "ghost", actor_id="x")

    def test_original_graph_unchanged(self):
        g, sid = _graph_with_scene()
        spawn_actor(g, sid, actor_id="hero")
        self.assertNotIn("hero", g.actors)


# ---------------------------------------------------------------------------
# destroy_actor
# ---------------------------------------------------------------------------

class TestDestroyActor(unittest.TestCase):

    def test_removes_actor_from_actors(self):
        g, sid, aid = _graph_with_actor()
        g2 = destroy_actor(g, aid)
        self.assertNotIn(aid, g2.actors)

    def test_removes_actor_from_scene_membership(self):
        g, sid, aid = _graph_with_actor()
        g2 = destroy_actor(g, aid)
        self.assertNotIn(aid, g2.scenes[sid].actor_ids)

    def test_noop_if_actor_missing(self):
        g, _ = _graph_with_scene()
        g2 = destroy_actor(g, "ghost")
        self.assertEqual(g2, g)

    def test_other_actors_unaffected(self):
        g, sid = _graph_with_scene()
        g, _ = spawn_actor(g, sid, actor_id="a1")
        g, _ = spawn_actor(g, sid, actor_id="a2")
        g2 = destroy_actor(g, "a1")
        self.assertIn("a2", g2.actors)
        self.assertIn("a2", g2.scenes[sid].actor_ids)


# ---------------------------------------------------------------------------
# set_actor_active
# ---------------------------------------------------------------------------

class TestSetActorActive(unittest.TestCase):

    def test_deactivate(self):
        g, sid, aid = _graph_with_actor()
        g2 = set_actor_active(g, aid, False)
        self.assertFalse(g2.actors[aid].active)

    def test_reactivate(self):
        g, sid, aid = _graph_with_actor()
        g2 = set_actor_active(g, aid, False)
        g3 = set_actor_active(g2, aid, True)
        self.assertTrue(g3.actors[aid].active)

    def test_noop_if_actor_missing(self):
        g = SceneGraph()
        g2 = set_actor_active(g, "ghost", False)
        self.assertEqual(g2, g)


# ---------------------------------------------------------------------------
# query_actors
# ---------------------------------------------------------------------------

class TestQueryActors(unittest.TestCase):

    def _populated(self):
        g = SceneGraph()
        g, sid = create_scene(g, "Main", scene_id="main")
        g, _ = spawn_actor(g, sid, tags={"player"}, actor_id="hero")
        g, _ = spawn_actor(g, sid, tags={"enemy"}, actor_id="goblin_1")
        g, _ = spawn_actor(g, sid, tags={"enemy", "boss"}, actor_id="goblin_boss")
        return g, sid

    def test_returns_all_active_by_default(self):
        g, sid = self._populated()
        actors = query_actors(g)
        self.assertEqual(len(actors), 3)

    def test_filter_by_scene_id(self):
        g, sid = self._populated()
        g, sid2 = create_scene(g, "Other", scene_id="other")
        g, _ = spawn_actor(g, sid2, tags={"npc"}, actor_id="townsperson")
        actors = query_actors(g, scene_id=sid)
        self.assertEqual(len(actors), 3)

    def test_filter_by_tag(self):
        g, sid = self._populated()
        enemies = query_actors(g, tags={"enemy"})
        self.assertEqual(len(enemies), 2)

    def test_filter_by_multiple_tags(self):
        g, sid = self._populated()
        bosses = query_actors(g, tags={"enemy", "boss"})
        self.assertEqual(len(bosses), 1)
        self.assertEqual(bosses[0].actor_id, "goblin_boss")

    def test_active_only_excludes_inactive(self):
        g, sid = self._populated()
        g = set_actor_active(g, "goblin_1", False)
        actors = query_actors(g, active_only=True)
        self.assertEqual(len(actors), 2)

    def test_active_only_false_includes_inactive(self):
        g, sid = self._populated()
        g = set_actor_active(g, "goblin_1", False)
        actors = query_actors(g, active_only=False)
        self.assertEqual(len(actors), 3)

    def test_missing_scene_returns_empty(self):
        g = SceneGraph()
        self.assertEqual(query_actors(g, scene_id="ghost"), [])

    def test_combined_scene_and_tag_filter(self):
        g, sid = self._populated()
        g, sid2 = create_scene(g, "Other", scene_id="other")
        g, _ = spawn_actor(g, sid2, tags={"enemy"}, actor_id="remote_enemy")
        result = query_actors(g, scene_id=sid, tags={"enemy"})
        self.assertEqual(len(result), 2)
        ids = {a.actor_id for a in result}
        self.assertNotIn("remote_enemy", ids)


# ---------------------------------------------------------------------------
# get_actor
# ---------------------------------------------------------------------------

class TestGetActor(unittest.TestCase):

    def test_returns_actor(self):
        g, sid, aid = _graph_with_actor(aid="hero")
        a = get_actor(g, "hero")
        self.assertIsNotNone(a)
        self.assertEqual(a.actor_id, "hero")

    def test_returns_none_if_missing(self):
        self.assertIsNone(get_actor(SceneGraph(), "ghost"))


# ---------------------------------------------------------------------------
# update_component
# ---------------------------------------------------------------------------

class TestUpdateComponent(unittest.TestCase):

    def test_adds_new_component(self):
        g, sid, aid = _graph_with_actor()
        tf = TransformComponent(x=5.0)
        g2 = update_component(g, aid, "transform", tf)
        self.assertAlmostEqual(g2.actors[aid].components["transform"].x, 5.0)

    def test_replaces_existing_component(self):
        tf1 = TransformComponent(x=5.0)
        tf2 = TransformComponent(x=99.0)
        g, sid = _graph_with_scene()
        g, aid = spawn_actor(g, sid, components={"transform": tf1}, actor_id="a")
        g2 = update_component(g, aid, "transform", tf2)
        self.assertAlmostEqual(g2.actors[aid].components["transform"].x, 99.0)

    def test_original_actor_unchanged(self):
        g, sid, aid = _graph_with_actor()
        tf = TransformComponent(x=5.0)
        update_component(g, aid, "transform", tf)
        self.assertNotIn("transform", g.actors[aid].components)

    def test_noop_if_actor_missing(self):
        g = SceneGraph()
        g2 = update_component(g, "ghost", "transform", TransformComponent())
        self.assertEqual(g2, g)


# ---------------------------------------------------------------------------
# get_component
# ---------------------------------------------------------------------------

class TestGetComponent(unittest.TestCase):

    def test_returns_component(self):
        tf = TransformComponent(x=7.0)
        g, sid = _graph_with_scene()
        g, aid = spawn_actor(g, sid, components={"transform": tf}, actor_id="a")
        comp = get_component(g, aid, "transform")
        self.assertIsNotNone(comp)
        self.assertAlmostEqual(comp.x, 7.0)

    def test_returns_none_if_slot_missing(self):
        g, sid, aid = _graph_with_actor()
        self.assertIsNone(get_component(g, aid, "nonexistent"))

    def test_returns_none_if_actor_missing(self):
        self.assertIsNone(get_component(SceneGraph(), "ghost", "transform"))


# ---------------------------------------------------------------------------
# remove_component
# ---------------------------------------------------------------------------

class TestRemoveComponent(unittest.TestCase):

    def test_removes_existing_component(self):
        tf = TransformComponent()
        g, sid = _graph_with_scene()
        g, aid = spawn_actor(g, sid, components={"transform": tf}, actor_id="a")
        g2 = remove_component(g, aid, "transform")
        self.assertNotIn("transform", g2.actors[aid].components)

    def test_other_components_unaffected(self):
        from grimoire2d.models.components import VelocityComponent
        tf = TransformComponent()
        vel = VelocityComponent(vx=1.0)
        g, sid = _graph_with_scene()
        g, aid = spawn_actor(g, sid, components={"transform": tf, "velocity": vel}, actor_id="a")
        g2 = remove_component(g, aid, "transform")
        self.assertIn("velocity", g2.actors[aid].components)

    def test_noop_if_slot_missing(self):
        g, sid, aid = _graph_with_actor()
        g2 = remove_component(g, aid, "nonexistent")
        self.assertEqual(g2.actors[aid].components, g.actors[aid].components)

    def test_noop_if_actor_missing(self):
        g = SceneGraph()
        g2 = remove_component(g, "ghost", "transform")
        self.assertEqual(g2, g)


# ---------------------------------------------------------------------------
# Integration: full scene lifecycle
# ---------------------------------------------------------------------------

class TestFullSceneLifecycle(unittest.TestCase):

    def test_create_populate_query_destroy(self):
        g = SceneGraph()

        # Create two scenes
        g, splash_id = create_scene(g, "Splash", scene_id="splash")
        g, game_id = create_scene(g, "Gameplay", scene_id="game")
        g = set_active_scene(g, game_id)

        # Spawn actors in gameplay
        g, pid = spawn_actor(g, game_id, tags={"player"}, actor_id="hero")
        g, eid1 = spawn_actor(g, game_id, tags={"enemy"}, actor_id="e1")
        g, eid2 = spawn_actor(g, game_id, tags={"enemy"}, actor_id="e2")

        # Add transforms
        g = update_component(g, pid, "transform", TransformComponent(x=100, y=200))

        # Queries
        players = query_actors(g, scene_id=game_id, tags={"player"})
        enemies = query_actors(g, scene_id=game_id, tags={"enemy"})
        self.assertEqual(len(players), 1)
        self.assertEqual(len(enemies), 2)

        # Verify transform
        t = get_component(g, pid, "transform")
        self.assertAlmostEqual(t.x, 100)
        self.assertAlmostEqual(t.y, 200)

        # Destroy one enemy
        g = destroy_actor(g, eid1)
        enemies_after = query_actors(g, scene_id=game_id, tags={"enemy"})
        self.assertEqual(len(enemies_after), 1)

        # Close splash
        g = close_scene(g, splash_id)
        self.assertEqual(g.scenes[splash_id].status, SCENE_STATUS_CLOSING)

        # Active scene still correct
        self.assertEqual(g.active_scene_id, game_id)


if __name__ == "__main__":
    unittest.main()
