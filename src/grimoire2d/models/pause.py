"""PauseState data model and standard update-group name constants.

PauseState maps update-group names to a boolean paused flag.  A group that
is absent from the dict is treated as *not* paused (running).

Standard groups — games may add their own:

  GROUP_GAMEPLAY  all game entities, physics, AI, simulation clock
  GROUP_AUDIO     music and sound effects
  GROUP_UI        menus, HUD animations, visual indicators
  GROUP_INPUT     keyboard / gamepad — almost never paused

Typical local-game pause:
  pause_state.with_group(GROUP_GAMEPLAY, True)
  → gameplay freezes; audio, UI, and input keep running.

Games choose which groups to pause per-actor.  An actor that should
*ignore* pause simply does not check is_paused(), or checks a group
that the game never pauses.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import DataModel, register_extension

# ---------------------------------------------------------------------------
# Standard group name constants
# ---------------------------------------------------------------------------

GROUP_GAMEPLAY: str = "gameplay"
GROUP_AUDIO:    str = "audio"
GROUP_UI:       str = "ui"
GROUP_INPUT:    str = "input"


# ---------------------------------------------------------------------------
# PauseState
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PauseState(DataModel):
    """Maps update-group names to their paused flag.

    All mutating operations return a new PauseState (immutable value object).
    The engine enforces no policy here — that lives in logic.pause_logic.
    """

    groups:  dict[str, bool] = field(default_factory=dict)
    version: int = 1

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def is_paused(self, group: str) -> bool:
        """Return True if `group` is currently paused."""
        return self.groups.get(group, False)

    def any_paused(self) -> bool:
        """Return True if at least one group is paused."""
        return any(self.groups.values())

    # ------------------------------------------------------------------ #
    # Mutations (return new instance)
    # ------------------------------------------------------------------ #

    def with_group(self, group: str, paused: bool) -> PauseState:
        """Return a new PauseState with one group's flag changed."""
        new_groups = dict(self.groups)
        new_groups[group] = paused
        return replace(self, groups=new_groups)

    # ------------------------------------------------------------------ #
    # DataModel protocol
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return {"groups": dict(self.groups), "version": self.version}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PauseState:
        return cls(
            groups=  dict(data.get("groups", {})),
            version= data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> PauseState:
        return replace(self, **changes)

    # ------------------------------------------------------------------ #
    # Factory
    # ------------------------------------------------------------------ #

    @classmethod
    def running(cls) -> PauseState:
        """All groups running (unpaused). The default state."""
        return cls()


register_extension("pause", PauseState)
