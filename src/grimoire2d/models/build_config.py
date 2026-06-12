"""Build configuration as a pure data model extension.

Used to distinguish dev vs release builds for initial window behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .base import DataModel, register_extension


@dataclass(frozen=True, slots=True)
class BuildConfig(DataModel):
    """Build type configuration.

    mode: "dev" or "release"
    """

    mode: str = "dev"
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BuildConfig:
        return cls(
            mode=data.get("mode", "dev"),
            version=data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> BuildConfig:
        return replace(self, **changes)


register_extension("build", BuildConfig)