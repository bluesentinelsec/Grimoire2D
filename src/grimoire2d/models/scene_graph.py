"""SceneGraph data model — top-level container for scenes and actors.

SceneGraph is the shared runtime bus that connects the scene system to the
actor system.  It is intentionally flat:

  scenes  dict[scene_id → Scene]  — scene metadata + actor membership
  actors  dict[actor_id → Actor]  — all actor data, cross-scene

This separation means actors can be queried globally (across scenes) or
scoped to a single scene via scene_ops.query_actors(scene_id=...).

SceneGraph is NOT an EngineConfig extension — it is mutable runtime state,
not static configuration.  Games compose it into their own GameState:

    @dataclass
    class MyGameState:
        graph: SceneGraph = field(default_factory=SceneGraph)
        ...

All mutation is done through pure functions in logic.scene_ops; the
SceneGraph itself is immutable (frozen dataclass).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import DataModel
from .actor import Actor
from .scene import Scene


@dataclass(frozen=True, slots=True)
class SceneGraph(DataModel):
    """Flat, immutable container for all scenes and actors.

    Use scene_ops functions to derive new SceneGraph instances when state
    must change.  Never mutate the dicts in-place.
    """

    scenes:          dict[str, Scene] = field(default_factory=dict)
    actors:          dict[str, Actor] = field(default_factory=dict)
    active_scene_id: str | None       = None
    version:         int              = 1

    @property
    def scene_count(self) -> int:
        return len(self.scenes)

    @property
    def actor_count(self) -> int:
        return len(self.actors)

    def get_active_scene(self) -> Scene | None:
        if self.active_scene_id is None:
            return None
        return self.scenes.get(self.active_scene_id)

    # ------------------------------------------------------------------
    # DataModel protocol
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenes":          {sid: s.to_dict() for sid, s in self.scenes.items()},
            "actors":          {aid: a.to_dict() for aid, a in self.actors.items()},
            "active_scene_id": self.active_scene_id,
            "version":         self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneGraph:
        raw_scenes = data.get("scenes", {})
        raw_actors = data.get("actors", {})
        return cls(
            scenes=          {sid: Scene.from_dict(sd) for sid, sd in raw_scenes.items()},
            actors=          {aid: Actor.from_dict(ad) for aid, ad in raw_actors.items()},
            active_scene_id= data.get("active_scene_id"),
            version=         data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> SceneGraph:
        return replace(self, **changes)
