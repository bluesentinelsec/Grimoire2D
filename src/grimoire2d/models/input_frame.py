"""InputFrame and InputBuffer data models.

InputFrame is the atom of game input: one player's logical actions at one tick.
Actions are game-defined strings ("move_left", "fire", "jump") rather than raw
key codes, so the simulation layer never depends on hardware details.

InputBuffer queues frames per player and supports drain_up_to() for
fixed-timestep consumption and jitter-buffer / rollback patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import DataModel


@dataclass(frozen=True, slots=True)
class InputFrame(DataModel):
    """One player's logical actions at a single simulation tick.

    player_id: which player this frame belongs to
    tick:      the simulation tick this frame applies to
    actions:   frozenset of active logical action names this tick
    """

    player_id: str = ""
    tick:      int = 0
    actions:   frozenset[str] = frozenset()
    version:   int = 1

    def has_action(self, action: str) -> bool:
        """Return True if the named action is active this frame."""
        return action in self.actions

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "tick":      self.tick,
            "actions":   sorted(self.actions),
            "version":   self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InputFrame:
        return cls(
            player_id= data.get("player_id", ""),
            tick=      data.get("tick",      0),
            actions=   frozenset(data.get("actions", [])),
            version=   data.get("version",   1),
        )

    def with_updates(self, **changes: Any) -> InputFrame:
        if "actions" in changes:
            changes["actions"] = frozenset(changes["actions"])
        return replace(self, **changes)

    @classmethod
    def empty(cls, player_id: str, tick: int) -> InputFrame:
        """Convenience constructor for a no-op frame."""
        return cls(player_id=player_id, tick=tick)


# ---------------------------------------------------------------------------
# InputBuffer
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class InputBuffer(DataModel):
    """Per-player queue of InputFrames.

    Frames are stored as an ordered tuple of (player_id, frames_tuple) pairs.
    This structure is immutable: all mutations return a new InputBuffer.

    Typical use:
        buf = InputBuffer.empty()
        buf = buf.push(frame_from_network)
        ready, buf = buf.drain_up_to(current_tick)
    """

    # Tuple of (player_id, frames) pairs — kept as a plain tuple so
    # the whole model stays frozen and serializable.
    entries:        tuple[tuple[str, tuple[InputFrame, ...]], ...] = field(
                        default_factory=tuple
                    )
    confirmed_tick: int = 0
    version:        int = 1

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def frames_for(self, player_id: str) -> tuple[InputFrame, ...]:
        """Return the queued frames for one player (empty tuple if none)."""
        for pid, frames in self.entries:
            if pid == player_id:
                return frames
        return ()

    # ------------------------------------------------------------------ #
    # Mutations (return new instances)
    # ------------------------------------------------------------------ #

    def _set_frames_for(self, player_id: str,
                        frames: tuple[InputFrame, ...]) -> InputBuffer:
        new_entries = [(pid, f) for pid, f in self.entries if pid != player_id]
        new_entries.append((player_id, frames))
        return replace(self, entries=tuple(new_entries))

    def push(self, frame: InputFrame) -> InputBuffer:
        """Append one frame to the queue for its player."""
        existing = self.frames_for(frame.player_id)
        return self._set_frames_for(frame.player_id, existing + (frame,))

    def drain_up_to(self, tick: int) -> tuple[list[InputFrame], InputBuffer]:
        """Consume all frames at or before `tick`.

        Returns (ready_frames, new_buffer).  The new buffer's confirmed_tick
        is updated to `tick`.
        """
        ready: list[InputFrame] = []
        new_entries = []
        for pid, frames in self.entries:
            keep: list[InputFrame] = []
            for f in frames:
                if f.tick <= tick:
                    ready.append(f)
                else:
                    keep.append(f)
            new_entries.append((pid, tuple(keep)))
        return ready, replace(self,
                              entries=tuple(new_entries),
                              confirmed_tick=tick)

    # ------------------------------------------------------------------ #
    # DataModel protocol
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [
                {"player_id": pid,
                 "frames":    [f.to_dict() for f in frames]}
                for pid, frames in self.entries
            ],
            "confirmed_tick": self.confirmed_tick,
            "version":        self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InputBuffer:
        entries = tuple(
            (e["player_id"],
             tuple(InputFrame.from_dict(f) for f in e.get("frames", [])))
            for e in data.get("entries", [])
        )
        return cls(
            entries=        entries,
            confirmed_tick= data.get("confirmed_tick", 0),
            version=        data.get("version", 1),
        )

    def with_updates(self, **changes: Any) -> InputBuffer:
        return replace(self, **changes)

    @classmethod
    def empty(cls) -> InputBuffer:
        return cls()
