"""Window settings as a pure data model extension.

Supports the common windowing modes and runtime changes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .base import DataModel, register_extension


@dataclass(frozen=True, slots=True)
class WindowSettings(DataModel):
    """Configuration for the game window.

    mode: one of "fullscreen_exclusive", "fullscreen_borderless", "windowed"
    width, height: desired resolution (0 means use system's current)
    maximized: for windowed mode, whether to start maximized (for dev builds)
    """

    mode: str = "windowed"
    width: int = 0
    height: int = 0
    maximized: bool = False
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "width": self.width,
            "height": self.height,
            "maximized": self.maximized,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WindowSettings:
        return cls(
            mode=data.get("mode", "windowed"),
            width=data.get("width", 0),
            height=data.get("height", 0),
            maximized=data.get("maximized", False),
            version=data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> WindowSettings:
        return replace(self, **changes)


register_extension("window", WindowSettings)