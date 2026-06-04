"""Pure data model for engine configuration (Category A per proposal 0001).

This is a simple value object with no behavior or side effects.
Serialization is provided for future VFS/persistence use (currently in-memory only).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Runtime engine configuration data model.

    Fields are chosen to support the minimal game loop milestone
    (window title/size, timing, vsync, clear color for presentation).

    Use .with_updates(...) to create a new instance with changes
    (supports the "runtime mutable" story without mutation in place).
    """

    title: str = "Grimoire2D"
    width: int = 800
    height: int = 600
    target_fps: int = 60
    vsync: bool = True
    clear_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    version: int = 1

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.target_fps <= 0:
            raise ValueError("target_fps must be positive")
        if len(self.clear_color) != 4 or not all(0 <= c <= 255 for c in self.clear_color):
            raise ValueError("clear_color must be a 4-tuple of ints 0-255")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (for VFS/persistence boundary)."""
        return {
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "target_fps": self.target_fps,
            "vsync": self.vsync,
            "clear_color": self.clear_color,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngineConfig:
        """Deserialize from a plain dict.

        Unknown keys are ignored (forward compatible).
        """
        return cls(
            title=data.get("title", "Grimoire2D"),
            width=data.get("width", 800),
            height=data.get("height", 600),
            target_fps=data.get("target_fps", 60),
            vsync=data.get("vsync", True),
            clear_color=data.get("clear_color", (0, 0, 0, 255)),
            version=data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> EngineConfig:
        """Return a new EngineConfig with the given fields updated.

        This provides a clear, immutable "mutation" story for runtime config changes.
        """
        return replace(self, **changes)


# Note: future VFS integration will load/save via to_dict/from_dict
# (see proposal 0001 and 0002). Currently only in-memory dicts are supported.