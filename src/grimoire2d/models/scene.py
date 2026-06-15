"""Scene data model and lifecycle status constants.

A Scene is a named collection of actor IDs with a lifecycle status.
Scenes never own Actor data directly — the SceneGraph's `actors` dict
is the single source of truth for Actor state; Scenes hold only the
set of IDs that belong to them.

Lifecycle
---------
  LOADING   scene is being set up (assets loading, actors spawning)
  ACTIVE    scene is running normally
  PAUSED    scene is suspended but still in memory
  CLOSING   scene has been requested to close; cleanup in progress
  CLOSED    scene has completed teardown (safe to remove from graph)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import DataModel

# ---------------------------------------------------------------------------
# Lifecycle status constants
# ---------------------------------------------------------------------------

SCENE_STATUS_LOADING: str = "loading"
SCENE_STATUS_ACTIVE:  str = "active"
SCENE_STATUS_PAUSED:  str = "paused"
SCENE_STATUS_CLOSING: str = "closing"
SCENE_STATUS_CLOSED:  str = "closed"

VALID_SCENE_STATUSES: frozenset[str] = frozenset({
    SCENE_STATUS_LOADING,
    SCENE_STATUS_ACTIVE,
    SCENE_STATUS_PAUSED,
    SCENE_STATUS_CLOSING,
    SCENE_STATUS_CLOSED,
})


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Scene(DataModel):
    """Named collection of actor IDs with a lifecycle status.

    scene_id and name must be provided; all other fields have defaults.
    """

    scene_id:  str
    name:      str
    status:    str            = SCENE_STATUS_ACTIVE
    actor_ids: frozenset[str] = field(default_factory=frozenset)
    version:   int            = 1

    def __post_init__(self) -> None:
        if self.status not in VALID_SCENE_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(VALID_SCENE_STATUSES)!r}, "
                f"got {self.status!r}"
            )

    @property
    def actor_count(self) -> int:
        return len(self.actor_ids)

    def is_active(self) -> bool:
        return self.status == SCENE_STATUS_ACTIVE

    # ------------------------------------------------------------------
    # DataModel protocol
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id":  self.scene_id,
            "name":      self.name,
            "status":    self.status,
            "actor_ids": sorted(self.actor_ids),
            "version":   self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        return cls(
            scene_id=  data.get("scene_id",  ""),
            name=      data.get("name",      ""),
            status=    data.get("status",    SCENE_STATUS_ACTIVE),
            actor_ids= frozenset(data.get("actor_ids", [])),
            version=   data.get("version",   1),
        )

    def with_updates(self, **changes: Any) -> Scene:
        return replace(self, **changes)
