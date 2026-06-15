"""Input routing: normalises all input sources into InputFrame objects.

The InputSource protocol is the key seam. Every concrete source—keyboard,
gamepad, TCP socket, AI, replay file—implements the same two-method interface.
The simulation never inspects the source; it only receives a list[InputFrame].

Concrete sources provided here:

  LocalInputSource    reads keyboard state via a caller-supplied key_getter
                      (injectable for testing without pygame)
  StaticInputSource   always returns the same actions — AI stub / test double
  SequencedInputSource plays back a predetermined list — replay / test double

The TcpTransport in presentation.tcp_transport also implements InputSource
and can be passed directly to route_inputs().
"""

from __future__ import annotations

from typing import Callable, Protocol, Sequence

from grimoire2d.models.input_frame import InputFrame


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class InputSource(Protocol):
    """Contract for any entity that can produce InputFrames.

    poll() is called exactly once per simulation tick. It returns an InputFrame
    when input is available, or None when the source has nothing to report
    (e.g. a network source still waiting for the packet for this tick).
    """

    @property
    def player_id(self) -> str: ...

    def poll(self, tick: int) -> InputFrame | None: ...


# ---------------------------------------------------------------------------
# LocalInputSource
# ---------------------------------------------------------------------------

class LocalInputSource:
    """Maps live keyboard state to logical actions via a configurable binding table.

    bindings: maps action name → list of key name strings
        e.g. {"move_left": ["a", "left"], "fire": ["space", "z"]}

    key_getter: callable that returns the current set of pressed key name strings.
        In production: lambda: {pygame.key.name(k) for k, v in enumerate(pygame.key.get_pressed()) if v}
        In tests: lambda: frozenset(["a", "space"])

    An action is active when ANY of its bound keys is currently pressed.
    """

    def __init__(
        self,
        player_id: str,
        bindings: dict[str, list[str]],
        key_getter: Callable[[], frozenset[str]],
    ) -> None:
        self._player_id = player_id
        self._bindings  = bindings
        self._key_getter = key_getter

    @property
    def player_id(self) -> str:
        return self._player_id

    def poll(self, tick: int) -> InputFrame:
        pressed = self._key_getter()
        active: set[str] = set()
        for action, keys in self._bindings.items():
            if any(k in pressed for k in keys):
                active.add(action)
        return InputFrame(
            player_id=self._player_id,
            tick=tick,
            actions=frozenset(active),
        )


# ---------------------------------------------------------------------------
# StaticInputSource
# ---------------------------------------------------------------------------

class StaticInputSource:
    """Always returns a fixed action set. Useful for AI stubs and tests."""

    def __init__(
        self,
        player_id: str,
        actions: frozenset[str] = frozenset(),
    ) -> None:
        self._player_id = player_id
        self._actions   = actions

    @property
    def player_id(self) -> str:
        return self._player_id

    def poll(self, tick: int) -> InputFrame:
        return InputFrame(
            player_id=self._player_id,
            tick=tick,
            actions=self._actions,
        )


# ---------------------------------------------------------------------------
# SequencedInputSource
# ---------------------------------------------------------------------------

class SequencedInputSource:
    """Plays back a predetermined sequence of InputFrames in order.

    Once exhausted, returns empty frames. This is the primary tool for
    deterministic simulation tests and replay systems: record a session's
    InputFrames, feed them back via this source, and the simulation must
    reproduce the exact same game state.
    """

    def __init__(self, player_id: str, sequence: list[InputFrame]) -> None:
        self._player_id = player_id
        self._sequence  = list(sequence)
        self._index     = 0

    @property
    def player_id(self) -> str:
        return self._player_id

    def poll(self, tick: int) -> InputFrame:
        if self._index < len(self._sequence):
            frame = self._sequence[self._index]
            self._index += 1
            return frame
        return InputFrame.empty(self._player_id, tick)


# ---------------------------------------------------------------------------
# route_inputs
# ---------------------------------------------------------------------------

def route_inputs(
    sources: Sequence[InputSource],
    tick: int,
) -> list[InputFrame]:
    """Poll every source once and collect the resulting frames.

    Sources that return None (network sources waiting for a packet) are
    silently skipped; the simulation receives only the frames that arrived.
    The returned list contains at most one frame per source.
    """
    frames: list[InputFrame] = []
    for source in sources:
        frame = source.poll(tick)
        if frame is not None:
            frames.append(frame)
    return frames
