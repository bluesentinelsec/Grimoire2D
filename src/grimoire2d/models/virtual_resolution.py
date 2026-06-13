"""Virtual resolution data model.

This is the authoritative, data-driven resolution that the game world,
art, logic, cameras, and UI coordinates are authored against.

Default is 1280x720 (a solid 16:9 baseline that integer-scales well to
many common display resolutions). It is fully runtime mutable via the
normal EngineConfig/AppState with_updates path so options screens,
dev tools, or even gameplay can change the virtual resolution without
restarting.

The presentation + scaling logic use this + the current physical window
size to compute letterboxed viewports and the orthographic projection.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .base import DataModel, register_extension


@dataclass(frozen=True, slots=True)
class VirtualResolution(DataModel):
    """The fixed virtual (design) resolution for the game.

    width, height: the game coordinate space in "pixels". All drawing,
        camera positions, layout, etc. are expressed in this space.
        The actual OS window can be any size; the renderer letterboxes
        and scales to fit while preserving aspect.

    integer_scaling: when True (default), only whole integer scales are
        used. This produces crisp pixels (no filtering) at the cost of
        potentially larger letterbox bars. When False a fractional scale
        is allowed to make the virtual area exactly fill one axis.

    This model is deliberately small and focused. All extension of
    display behavior happens via new registered models or composition
    at the AppState / game state level.
    """

    width: int = 1280
    height: int = 720
    integer_scaling: bool = True
    version: int = 1

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("virtual resolution width and height must be positive")
        if self.version < 1:
            raise ValueError("version must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "integer_scaling": self.integer_scaling,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VirtualResolution:
        return cls(
            width=data.get("width", 1280),
            height=data.get("height", 720),
            integer_scaling=data.get("integer_scaling", True),
            version=data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> VirtualResolution:
        return replace(self, **changes)


register_extension("virtual_resolution", VirtualResolution)
