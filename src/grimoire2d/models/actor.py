"""Actor data model.

An Actor is an addressable entity within a Scene.  It carries:

  actor_id    unique string identifier (UUID or deterministic game-assigned)
  tags        frozenset of string labels for loose coupling and query
  components  dict mapping slot name → DataModel (any registered component)
  active      False to logically remove the actor from queries without destroying it

Actors never reference each other directly; coupling is expressed by sharing
tags and resolved at runtime through scene_ops.query_actors().
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import DataModel, _component_registry


@dataclass(frozen=True, slots=True)
class Actor(DataModel):
    """Addressable entity within a Scene.

    `components` maps slot name → DataModel value.  Use scene_ops helpers
    (update_component, get_component, remove_component) to derive new Actors
    rather than mutating the dict directly.
    """

    actor_id:   str
    tags:       frozenset[str]  = field(default_factory=frozenset)
    components: dict[str, Any]  = field(default_factory=dict)
    active:     bool            = True
    version:    int             = 1

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def has_tags(self, tags: frozenset[str] | set[str]) -> bool:
        return frozenset(tags).issubset(self.tags)

    # ------------------------------------------------------------------
    # DataModel protocol
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        serialized: dict[str, Any] = {}
        for name, comp in self.components.items():
            serialized[name] = comp.to_dict() if hasattr(comp, "to_dict") else comp
        return {
            "actor_id":   self.actor_id,
            "tags":       sorted(self.tags),
            "components": serialized,
            "active":     self.active,
            "version":    self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Actor:
        raw = data.get("components", {})
        components: dict[str, Any] = {}
        for name, cdata in raw.items():
            if name in _component_registry and isinstance(cdata, dict):
                components[name] = _component_registry[name].from_dict(cdata)
            else:
                components[name] = cdata
        return cls(
            actor_id=   data.get("actor_id", ""),
            tags=       frozenset(data.get("tags", [])),
            components= components,
            active=     data.get("active", True),
            version=    data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> Actor:
        return replace(self, **changes)
