"""Composed root application state.

AppState is the primary data model a minimal "game" or application
will work with. It demonstrates the composition approach:

- It aggregates common engine models (EngineConfig, LifecycleState, InputState).
- Game-specific data models are added by the game developer via composition
  (preferred) or by subclassing / adding an `extra` bag.

This is the "game is just data" root for the high-level milestone
(open a window until escape is pressed). Future logic will update
the lifecycle and input components; presentation will read config
and lifecycle to decide what to render and when to stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict

from .base import DataModel
from .config import EngineConfig
from .input import InputState
from .lifecycle import LifecycleState


@dataclass(frozen=True, slots=True)
class AppState(DataModel):
    """Top-level composed state for a minimal application / game.

    engine:     Core engine and window configuration.
    lifecycle:  Whether the app should keep running.
    input:      Current input snapshot (for ESC detection etc.).

    Games extend this by composition:

        @dataclass(frozen=True, slots=True)
        class MyGameState(AppState):
            player: PlayerState
            world: WorldData
            ...

    Or for simple cases, use the `extra` field for arbitrary game data
    (still serializable as dict).

    All components follow the DataModel contract, so the whole
    AppState can be serialized, updated immutably, and hot-reloaded.
    """

    engine: EngineConfig = field(default_factory=EngineConfig.default)
    lifecycle: LifecycleState = field(default_factory=LifecycleState)
    input: InputState = field(default_factory=InputState)
    extra: Dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = {
            "engine": self.engine.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "input": self.input.to_dict(),
            "version": self.version,
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppState:
        return cls(
            engine=EngineConfig.from_dict(data.get("engine", {})),
            lifecycle=LifecycleState.from_dict(data.get("lifecycle", {})),
            input=InputState.from_dict(data.get("input", {})),
            extra=data.get("extra", {}),
            version=data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> AppState:
        # Support nested updates for sub-models
        if "engine" in changes:
            changes["engine"] = self.engine.with_updates(**changes["engine"])
        if "lifecycle" in changes:
            changes["lifecycle"] = self.lifecycle.with_updates(**changes["lifecycle"])
        if "input" in changes:
            changes["input"] = self.input.with_updates(**changes["input"])
        return replace(self, **changes)

    @classmethod
    def default(cls) -> AppState:
        """Convenience constructor with sensible defaults for a minimal app."""
        return cls(
            engine=EngineConfig.default(),
            lifecycle=LifecycleState(),
            input=InputState(),
        )


# Note: AppState itself is not registered as an "extension" because it is
# a composition root. Games will typically define their own top-level state
# that includes AppState (or its components) plus game-specific models.
