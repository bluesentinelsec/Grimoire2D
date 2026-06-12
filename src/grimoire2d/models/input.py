"""Input state as a pure data model.

This is a snapshot of input relevant to the application loop.
For the initial milestone (window + escape to quit), it focuses on keyboard state.
The design is intentionally extensible for future game-specific input
(e.g. mouse, gamepad, custom actions) without modifying this core model.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, FrozenSet

from .base import DataModel, register_extension


@dataclass(frozen=True, slots=True)
class InputState(DataModel):
    """Pure snapshot of current input state.

    pressed_keys: set of key names that are currently held down
                  (e.g. "escape", "a", "left").
                  Names should be consistent (lowercase, pygame-style names).

    This model is pure data. Business logic will interpret it
    (e.g. set lifecycle.should_quit when "escape" is pressed).
    Presentation will produce updated snapshots each frame.
    """

    pressed_keys: FrozenSet[str] = frozenset()
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "pressed_keys": sorted(self.pressed_keys),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InputState:
        keys = data.get("pressed_keys", [])
        return cls(
            pressed_keys=frozenset(keys),
            version=data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> InputState:
        return replace(self, **changes)

    def is_key_pressed(self, key: str) -> bool:
        """Convenience query (pure, no side effects)."""
        return key.lower() in self.pressed_keys


register_extension("input", InputState)