"""Pause policy: pure functions over PauseState and MultiplayerConfig.

All functions are pure — no side effects, no GL, no pygame.  They are the
single place where the "can network games pause?" rule is enforced, so no
caller ever needs an explicit `if network:` branch.

Typical game-loop usage:

    # On ENTER key:
    state = state.with_updates(pause=toggle_pause(state.pause, cfg).to_dict())

    # Per-frame:
    if not is_paused(state.pause, GROUP_GAMEPLAY):
        n = sim_clock.update(dt)
        for _ in range(n):
            ...advance gameplay...

    # Audio subsystem:
    if not is_paused(state.pause, GROUP_AUDIO):
        audio.update(dt)

    # UI always runs — check omitted entirely.
"""

from __future__ import annotations

from grimoire2d.models.pause import PauseState, GROUP_GAMEPLAY
from grimoire2d.models.multiplayer import (
    MultiplayerConfig,
    TOPOLOGY_NETWORK_HOST,
    TOPOLOGY_NETWORK_CLIENT,
)

_NETWORK_TOPOLOGIES = frozenset({TOPOLOGY_NETWORK_HOST, TOPOLOGY_NETWORK_CLIENT})


def can_pause(config: MultiplayerConfig) -> bool:
    """Return True when the current topology permits pausing.

    Network games (host or client) return False: pausing one machine while
    the other continues would desynchronise the simulation.
    Local topologies (shared_screen, split_screen) return True.
    """
    return config.topology not in _NETWORK_TOPOLOGIES


def request_pause(pause_state: PauseState, config: MultiplayerConfig) -> PauseState:
    """Pause the gameplay group if the topology permits it.

    Returns the unchanged state when called on a network game — the caller
    does not need to know about the network policy.
    """
    if not can_pause(config):
        return pause_state
    return pause_state.with_group(GROUP_GAMEPLAY, True)


def request_unpause(pause_state: PauseState) -> PauseState:
    """Resume the gameplay group unconditionally."""
    return pause_state.with_group(GROUP_GAMEPLAY, False)


def toggle_pause(pause_state: PauseState, config: MultiplayerConfig) -> PauseState:
    """Toggle the gameplay group between paused and running.

    If gameplay is currently paused, unpauses it.
    If running and the topology permits pausing, pauses it.
    If running and topology does not permit pausing, returns unchanged.
    """
    if pause_state.is_paused(GROUP_GAMEPLAY):
        return request_unpause(pause_state)
    return request_pause(pause_state, config)


def is_paused(pause_state: PauseState, group: str) -> bool:
    """Return whether `group` is currently paused.

    Thin wrapper over PauseState.is_paused(); provided here so callers can
    import everything pause-related from one module.
    """
    return pause_state.is_paused(group)
