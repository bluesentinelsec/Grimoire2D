"""Multiplayer session configuration and viewport assignment models.

MultiplayerConfig is the single source of truth for how a session is arranged:
how many players, where input comes from, and how the screen is divided.

Single-player is the degenerate case:
    MultiplayerConfig.single_player()
    → one slot, role="local", topology="shared_screen"

The simulation and viewport-layout logic work identically regardless of
topology — only MultiplayerConfig changes between scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import DataModel, register_extension
from .player import PlayerIdentity, ROLE_LOCAL, ROLE_REMOTE

# ---------------------------------------------------------------------------
# Topology constants
# ---------------------------------------------------------------------------

TOPOLOGY_SHARED_SCREEN   = "shared_screen"
TOPOLOGY_SPLIT_SCREEN    = "split_screen"
TOPOLOGY_NETWORK_HOST    = "network_host"
TOPOLOGY_NETWORK_CLIENT  = "network_client"

VALID_TOPOLOGIES: frozenset[str] = frozenset({
    TOPOLOGY_SHARED_SCREEN,
    TOPOLOGY_SPLIT_SCREEN,
    TOPOLOGY_NETWORK_HOST,
    TOPOLOGY_NETWORK_CLIENT,
})


# ---------------------------------------------------------------------------
# ViewportAssignment
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ViewportAssignment(DataModel):
    """Pixel rectangle on screen assigned to one player's view.

    Coordinates are in physical (drawable) pixels from the top-left origin.
    player_id="*" is the shared-screen sentinel: all players see this one view.
    """

    player_id: str   = "*"
    x:         float = 0.0
    y:         float = 0.0
    w:         float = 1280.0
    h:         float = 720.0
    version:   int   = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ViewportAssignment:
        return cls(
            player_id= data.get("player_id", "*"),
            x=         data.get("x",         0.0),
            y=         data.get("y",         0.0),
            w=         data.get("w",         1280.0),
            h=         data.get("h",         720.0),
            version=   data.get("version",   1),
        )

    def with_updates(self, **changes: Any) -> ViewportAssignment:
        return replace(self, **changes)


# ---------------------------------------------------------------------------
# SimulationState
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SimulationState(DataModel):
    """Authoritative tick counter.

    tick is the number of fixed-rate simulation steps completed.
    The game loop advances tick via SimulationClock; this model persists it.

    Pause state is held in models.pause.PauseState (the single source of
    truth for all group-aware pause behaviour).
    """

    tick:    int = 0
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"tick": self.tick, "version": self.version}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationState:
        return cls(
            tick=    data.get("tick",    0),
            version= data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> SimulationState:
        return replace(self, **changes)


# ---------------------------------------------------------------------------
# MultiplayerConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MultiplayerConfig(DataModel):
    """Top-level description of the session's player arrangement.

    player_slots: ordered list of PlayerIdentity objects (one per player).
    topology:     how the screen and network are structured.
    host / port:  used when topology is network_host or network_client.
    tick_rate:    fixed-rate simulation frequency in Hz (default 60).

    Factory methods cover the four common configurations.
    """

    player_slots: tuple[PlayerIdentity, ...] = field(
        default_factory=lambda: (PlayerIdentity(player_id="P1"),)
    )
    topology:  str = TOPOLOGY_SHARED_SCREEN
    host:      str = ""
    port:      int = 7777
    tick_rate: int = 60
    version:   int = 1

    def __post_init__(self) -> None:
        if self.topology not in VALID_TOPOLOGIES:
            raise ValueError(
                f"topology must be one of {sorted(VALID_TOPOLOGIES)!r}, "
                f"got {self.topology!r}"
            )
        if self.tick_rate <= 0:
            raise ValueError(f"tick_rate must be positive, got {self.tick_rate}")

    # ------------------------------------------------------------------ #
    # Convenience queries
    # ------------------------------------------------------------------ #

    @property
    def player_count(self) -> int:
        return len(self.player_slots)

    def player_ids(self) -> tuple[str, ...]:
        return tuple(p.player_id for p in self.player_slots)

    def is_network(self) -> bool:
        return self.topology in (TOPOLOGY_NETWORK_HOST, TOPOLOGY_NETWORK_CLIENT)

    # ------------------------------------------------------------------ #
    # DataModel protocol
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_slots": [p.to_dict() for p in self.player_slots],
            "topology":     self.topology,
            "host":         self.host,
            "port":         self.port,
            "tick_rate":    self.tick_rate,
            "version":      self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MultiplayerConfig:
        raw_slots = data.get("player_slots",
                             [{"player_id": "P1", "role": "local",
                               "display_name": "", "version": 1}])
        return cls(
            player_slots= tuple(PlayerIdentity.from_dict(s) for s in raw_slots),
            topology=     data.get("topology",  TOPOLOGY_SHARED_SCREEN),
            host=         data.get("host",      ""),
            port=         data.get("port",      7777),
            tick_rate=    data.get("tick_rate", 60),
            version=      data.get("version",   1),
        )

    def with_updates(self, **changes: Any) -> MultiplayerConfig:
        return replace(self, **changes)

    # ------------------------------------------------------------------ #
    # Factories
    # ------------------------------------------------------------------ #

    @classmethod
    def single_player(cls) -> MultiplayerConfig:
        """One local player, shared (full) screen."""
        return cls()

    @classmethod
    def local_two_player_shared(cls) -> MultiplayerConfig:
        """Two local players sharing the same full-screen view (e.g. Pong)."""
        return cls(
            player_slots=(
                PlayerIdentity(player_id="P1", role=ROLE_LOCAL),
                PlayerIdentity(player_id="P2", role=ROLE_LOCAL),
            ),
            topology=TOPOLOGY_SHARED_SCREEN,
        )

    @classmethod
    def local_two_player_split(cls) -> MultiplayerConfig:
        """Two local players each with their own half-screen viewport."""
        return cls(
            player_slots=(
                PlayerIdentity(player_id="P1", role=ROLE_LOCAL),
                PlayerIdentity(player_id="P2", role=ROLE_LOCAL),
            ),
            topology=TOPOLOGY_SPLIT_SCREEN,
        )

    @classmethod
    def network_host(cls, host: str = "0.0.0.0", port: int = 7777) -> MultiplayerConfig:
        """Host side: local P1, remote P2."""
        return cls(
            player_slots=(
                PlayerIdentity(player_id="P1", role=ROLE_LOCAL),
                PlayerIdentity(player_id="P2", role=ROLE_REMOTE),
            ),
            topology=TOPOLOGY_NETWORK_HOST,
            host=host,
            port=port,
        )

    @classmethod
    def network_client(cls, host: str, port: int = 7777) -> MultiplayerConfig:
        """Client side: remote P1 (host), local P2."""
        return cls(
            player_slots=(
                PlayerIdentity(player_id="P1", role=ROLE_REMOTE),
                PlayerIdentity(player_id="P2", role=ROLE_LOCAL),
            ),
            topology=TOPOLOGY_NETWORK_CLIENT,
            host=host,
            port=port,
        )


register_extension("multiplayer", MultiplayerConfig)
