"""Pure functions for creating, querying, updating, and closing scenes and actors.

All functions accept a SceneGraph and return a new SceneGraph (immutable update
pattern — same as PauseState, EngineConfig, etc.).  No side effects, no GL,
no I/O, fully testable without a display.

Scene lifecycle
---------------
  create_scene     → insert a new Scene in LOADING or ACTIVE status
  close_scene      → transition a scene to CLOSING status
  set_active_scene → set active_scene_id on the graph
  query_scenes     → filter scenes by status or other criteria
  get_scene        → look up one scene by ID (returns None if missing)

Actor lifecycle
---------------
  spawn_actor      → create an Actor and attach it to a scene
  destroy_actor    → remove an Actor from the graph and all scenes
  set_actor_active → toggle the active flag without destroying
  query_actors     → filter actors by scene, tags, and active flag
  get_actor        → look up one actor by ID (returns None if missing)

Component helpers
-----------------
  update_component → replace or add one component slot on an actor
  get_component    → read one component slot (returns None if absent)
  remove_component → delete one component slot from an actor
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from grimoire2d.models.actor import Actor
from grimoire2d.models.scene import Scene, SCENE_STATUS_ACTIVE, SCENE_STATUS_CLOSING
from grimoire2d.models.scene_graph import SceneGraph


# ---------------------------------------------------------------------------
# Scene operations
# ---------------------------------------------------------------------------

def create_scene(
    graph: SceneGraph,
    name: str,
    *,
    scene_id: str | None = None,
    status: str = SCENE_STATUS_ACTIVE,
) -> tuple[SceneGraph, str]:
    """Insert a new scene and return (updated_graph, scene_id)."""
    sid = scene_id or str(uuid.uuid4())
    scene = Scene(scene_id=sid, name=name, status=status)
    return replace(graph, scenes={**graph.scenes, sid: scene}), sid


def close_scene(graph: SceneGraph, scene_id: str) -> SceneGraph:
    """Transition a scene to CLOSING status.  No-op if scene not found."""
    if scene_id not in graph.scenes:
        return graph
    new_scene = replace(graph.scenes[scene_id], status=SCENE_STATUS_CLOSING)
    return replace(graph, scenes={**graph.scenes, scene_id: new_scene})


def set_active_scene(graph: SceneGraph, scene_id: str) -> SceneGraph:
    """Set active_scene_id.  Raises KeyError if scene_id not in graph."""
    if scene_id not in graph.scenes:
        raise KeyError(f"Scene {scene_id!r} not found in graph")
    return replace(graph, active_scene_id=scene_id)


def query_scenes(
    graph: SceneGraph,
    *,
    status: str | None = None,
) -> list[Scene]:
    """Return scenes optionally filtered by status."""
    scenes = list(graph.scenes.values())
    if status is not None:
        scenes = [s for s in scenes if s.status == status]
    return scenes


def get_scene(graph: SceneGraph, scene_id: str) -> Scene | None:
    """Return the Scene for scene_id, or None if absent."""
    return graph.scenes.get(scene_id)


# ---------------------------------------------------------------------------
# Actor operations
# ---------------------------------------------------------------------------

def spawn_actor(
    graph: SceneGraph,
    scene_id: str,
    *,
    tags: frozenset[str] | set[str] = frozenset(),
    components: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> tuple[SceneGraph, str]:
    """Create an Actor, attach it to a scene, and return (updated_graph, actor_id).

    Raises KeyError if scene_id is not present in the graph.
    """
    if scene_id not in graph.scenes:
        raise KeyError(f"Scene {scene_id!r} not found in graph")
    aid = actor_id or str(uuid.uuid4())
    actor = Actor(
        actor_id=aid,
        tags=frozenset(tags),
        components=dict(components or {}),
    )
    new_actors = {**graph.actors, aid: actor}
    scene = graph.scenes[scene_id]
    new_scene = replace(scene, actor_ids=scene.actor_ids | {aid})
    return replace(graph, scenes={**graph.scenes, scene_id: new_scene}, actors=new_actors), aid


def destroy_actor(graph: SceneGraph, actor_id: str) -> SceneGraph:
    """Remove an Actor from the graph and all scene membership sets.  No-op if absent."""
    if actor_id not in graph.actors:
        return graph
    new_scenes = {
        sid: replace(s, actor_ids=s.actor_ids - {actor_id})
        if actor_id in s.actor_ids else s
        for sid, s in graph.scenes.items()
    }
    new_actors = {k: v for k, v in graph.actors.items() if k != actor_id}
    return replace(graph, scenes=new_scenes, actors=new_actors)


def set_actor_active(graph: SceneGraph, actor_id: str, active: bool) -> SceneGraph:
    """Toggle an actor's active flag.  No-op if actor_id not found."""
    if actor_id not in graph.actors:
        return graph
    new_actor = replace(graph.actors[actor_id], active=active)
    return replace(graph, actors={**graph.actors, actor_id: new_actor})


def query_actors(
    graph: SceneGraph,
    *,
    scene_id: str | None = None,
    tags: frozenset[str] | set[str] | None = None,
    active_only: bool = True,
) -> list[Actor]:
    """Return actors matching optional scene scope, tag filter, and active flag.

    scene_id=None  → search all actors in the graph
    tags=None      → no tag filter (match all)
    active_only    → exclude actors with active=False when True (default)
    """
    if scene_id is not None:
        scene = graph.scenes.get(scene_id)
        if scene is None:
            return []
        actors = [graph.actors[aid] for aid in scene.actor_ids if aid in graph.actors]
    else:
        actors = list(graph.actors.values())

    if active_only:
        actors = [a for a in actors if a.active]

    if tags is not None:
        tag_set = frozenset(tags)
        actors = [a for a in actors if tag_set.issubset(a.tags)]

    return actors


def get_actor(graph: SceneGraph, actor_id: str) -> Actor | None:
    """Return the Actor for actor_id, or None if absent."""
    return graph.actors.get(actor_id)


# ---------------------------------------------------------------------------
# Component helpers
# ---------------------------------------------------------------------------

def update_component(
    graph: SceneGraph,
    actor_id: str,
    name: str,
    component: Any,
) -> SceneGraph:
    """Replace or add one component slot on an actor.  No-op if actor absent."""
    if actor_id not in graph.actors:
        return graph
    actor = graph.actors[actor_id]
    new_actor = replace(actor, components={**actor.components, name: component})
    return replace(graph, actors={**graph.actors, actor_id: new_actor})


def get_component(
    graph: SceneGraph,
    actor_id: str,
    name: str,
) -> Any | None:
    """Return component `name` from actor, or None if actor or slot is absent."""
    actor = graph.actors.get(actor_id)
    if actor is None:
        return None
    return actor.components.get(name)


def remove_component(
    graph: SceneGraph,
    actor_id: str,
    name: str,
) -> SceneGraph:
    """Remove component slot `name` from an actor.  No-op if actor or slot absent."""
    if actor_id not in graph.actors:
        return graph
    actor = graph.actors[actor_id]
    new_components = {k: v for k, v in actor.components.items() if k != name}
    new_actor = replace(actor, components=new_components)
    return replace(graph, actors={**graph.actors, actor_id: new_actor})
