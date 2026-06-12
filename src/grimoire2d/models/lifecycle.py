"""Lifecycle state as a pure data model.

This model captures whether the application should continue running.
It is the data that will drive the (future) game loop termination.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional

from .base import DataModel, register_extension


@dataclass(frozen=True, slots=True)
class LifecycleState(DataModel):
    """Pure data representing the application's lifecycle state.

    - is_running: whether the main loop should continue.
    - should_quit: signal that the app wants to exit.
    - quit_reason: optional reason (e.g. "escape_pressed", "window_closed").

    This model is designed to be updated by business logic (rules)
    and observed by the presentation layer.
    """

    is_running: bool = True
    should_quit: bool = False
    quit_reason: Optional[str] = None
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_running": self.is_running,
            "should_quit": self.should_quit,
            "quit_reason": self.quit_reason,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LifecycleState:
        return cls(
            is_running=data.get("is_running", True),
            should_quit=data.get("should_quit", False),
            quit_reason=data.get("quit_reason"),
            version=data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> LifecycleState:
        return replace(self, **changes)


register_extension("lifecycle", LifecycleState)