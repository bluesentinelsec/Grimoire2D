"""Base protocol for all data models (common and game-specific).

This is the contract that enables the composition approach:
- Engine provides small, reusable common models (EngineConfig, LoadState, etc.).
- Games define their own pure models following the exact same shape.
- Games compose them (e.g. MyWorldState(engine=..., player=..., ...)).
- The rest of the engine (persistence, VFS, hot reload, DataContext) can treat them uniformly
  without knowing the concrete types.

All models should be pure value objects (no behavior, no side effects).
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, Self, runtime_checkable


@runtime_checkable
class DataModel(Protocol):
    """Protocol that all data models (engine-provided and game-specific) must satisfy.

    This is intentionally minimal and structural so that ordinary @dataclass
    definitions (with or without frozen/slots) satisfy it automatically.

    Recommended implementation pattern:
        @dataclass(frozen=True, slots=True)
        class MyModel:
            version: int = 1
            # ... other fields ...

            def to_dict(self) -> dict[str, Any]: ...
            @classmethod
            def from_dict(cls, data: dict[str, Any]) -> Self: ...
            def with_updates(self, **changes: Any) -> Self: ...
    """

    version: int

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation suitable for serialization."""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Reconstruct from a plain dict.

        Should support forward compatibility (ignore unknown keys) and
        supply defaults for missing known keys.
        """
        ...

    def with_updates(self, **changes: Any) -> Self:
        """Return a new instance with the given fields changed.

        This is the preferred way to express "runtime mutation" for configs
        while keeping models immutable.
        """
        ...


# --- Extension registry (enables purely net-new additions) ---
_settings_registry: dict[str, type[DataModel]] = {}


def register_extension(name: str, model_cls: type[DataModel]) -> None:
    """Register a new settings / data model category.

    Call this at the bottom of the model's own file after defining the class.
    This is the mechanism that keeps EngineConfig (and similar containers)
    closed for modification while remaining open for extension.
    """
    _settings_registry[name] = model_cls


# --- Component registry (enables Actor component deserialization) ---
_component_registry: dict[str, type[DataModel]] = {}


def register_component(name: str, component_cls: type[DataModel]) -> None:
    """Register an Actor component type for deserialization by slot name.

    Call this at the bottom of a component's module after defining the class.
    On Actor.from_dict(), known names are reconstructed as typed DataModels;
    unknown names fall back to raw dicts.
    """
    _component_registry[name] = component_cls