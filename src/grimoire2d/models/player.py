"""Player identity and roster data models.

A PlayerIdentity describes one slot in the session: who the player is and
where their input originates. The engine supports four roles:

  "local"  — keyboard or gamepad connected to this machine
  "remote" — input arrives over the network (TcpTransport)
  "ai"     — input produced by game logic (StaticInputSource or custom)
  "replay" — input played back from a recorded InputBuffer
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import DataModel

ROLE_LOCAL  = "local"
ROLE_REMOTE = "remote"
ROLE_AI     = "ai"
ROLE_REPLAY = "replay"
VALID_ROLES: frozenset[str] = frozenset({ROLE_LOCAL, ROLE_REMOTE, ROLE_AI, ROLE_REPLAY})


@dataclass(frozen=True, slots=True)
class PlayerIdentity(DataModel):
    """Identifies one player slot: who they are and how their input is sourced."""

    player_id:    str = "P1"
    role:         str = ROLE_LOCAL
    display_name: str = ""
    version:      int = 1

    def __post_init__(self) -> None:
        if not self.player_id:
            raise ValueError("player_id must be non-empty")
        if self.role not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)!r}, got {self.role!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id":    self.player_id,
            "role":         self.role,
            "display_name": self.display_name,
            "version":      self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayerIdentity:
        return cls(
            player_id=    data.get("player_id",    "P1"),
            role=         data.get("role",         ROLE_LOCAL),
            display_name= data.get("display_name", ""),
            version=      data.get("version",      1),
        )

    def with_updates(self, **changes: Any) -> PlayerIdentity:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class PlayerRoster(DataModel):
    """Ordered sequence of player slots for a session.

    All player_ids in the roster must be unique. The order determines
    default input bindings (slot 0 → P1 keys, slot 1 → P2 keys, etc.).
    """

    slots:   tuple[PlayerIdentity, ...] = field(default_factory=tuple)
    version: int = 1

    def __post_init__(self) -> None:
        ids = [p.player_id for p in self.slots]
        if len(ids) != len(set(ids)):
            raise ValueError("PlayerRoster contains duplicate player_ids")

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def get(self, player_id: str) -> PlayerIdentity | None:
        """Return the slot with the given player_id, or None."""
        for p in self.slots:
            if p.player_id == player_id:
                return p
        return None

    def player_ids(self) -> tuple[str, ...]:
        return tuple(p.player_id for p in self.slots)

    # ------------------------------------------------------------------ #
    # DataModel protocol
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return {
            "slots":   [s.to_dict() for s in self.slots],
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayerRoster:
        return cls(
            slots=   tuple(PlayerIdentity.from_dict(s) for s in data.get("slots", [])),
            version= data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> PlayerRoster:
        return replace(self, **changes)

    # ------------------------------------------------------------------ #
    # Factories
    # ------------------------------------------------------------------ #

    @classmethod
    def single_player(cls, player_id: str = "P1") -> PlayerRoster:
        return cls(slots=(PlayerIdentity(player_id=player_id, role=ROLE_LOCAL),))

    @classmethod
    def local_two_player(cls) -> PlayerRoster:
        return cls(slots=(
            PlayerIdentity(player_id="P1", role=ROLE_LOCAL),
            PlayerIdentity(player_id="P2", role=ROLE_LOCAL),
        ))
