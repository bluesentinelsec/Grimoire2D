"""Built-in Actor component types: Transform and Velocity.

Components are plain DataModel value objects stored by name in Actor.components.
Games define additional components by implementing DataModel and calling
register_component() at module level.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .base import DataModel, register_component


@dataclass(frozen=True, slots=True)
class TransformComponent(DataModel):
    """2-D position, orientation, and scale for an actor."""

    x:       float = 0.0
    y:       float = 0.0
    angle:   float = 0.0   # radians; positive = counter-clockwise
    scale_x: float = 1.0
    scale_y: float = 1.0
    version: int   = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x, "y": self.y,
            "angle": self.angle,
            "scale_x": self.scale_x, "scale_y": self.scale_y,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransformComponent:
        return cls(
            x=       data.get("x",       0.0),
            y=       data.get("y",       0.0),
            angle=   data.get("angle",   0.0),
            scale_x= data.get("scale_x", 1.0),
            scale_y= data.get("scale_y", 1.0),
            version= data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> TransformComponent:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class VelocityComponent(DataModel):
    """Linear and angular velocity for an actor."""

    vx:      float = 0.0
    vy:      float = 0.0
    angular: float = 0.0   # radians per tick
    version: int   = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "vx": self.vx, "vy": self.vy,
            "angular": self.angular,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VelocityComponent:
        return cls(
            vx=      data.get("vx",      0.0),
            vy=      data.get("vy",      0.0),
            angular= data.get("angular", 0.0),
            version= data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> VelocityComponent:
        return replace(self, **changes)


register_component("transform", TransformComponent)
register_component("velocity",  VelocityComponent)
