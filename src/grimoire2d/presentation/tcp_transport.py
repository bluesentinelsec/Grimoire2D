"""TCP socket transport implementing the InputSource protocol.

TcpTransport wraps a connected socket and behaves exactly like a
LocalInputSource from the perspective of route_inputs(): calling poll()
returns an InputFrame (or None if no complete packet arrived this tick).

InMemoryTransport is a test double backed by two queues that needs no sockets.
Use InMemoryTransport.make_pair() to create two wired transports that simulate
a full bidirectional network session inside a single process — no ports, no
OS resources, no timing sensitivity.

Both classes satisfy the InputSource protocol:
    @property player_id: str
    def poll(tick: int) -> InputFrame | None

Neither class depends on pygame; both can be used in unit tests and in CI.
"""

from __future__ import annotations

import queue
import socket
from typing import Optional

from grimoire2d.models.input_frame import InputFrame
from grimoire2d.logic.network_protocol import (
    encode_frame,
    decode_frame,
    read_length,
    LENGTH_PREFIX_SIZE,
)


# ---------------------------------------------------------------------------
# TcpTransport
# ---------------------------------------------------------------------------

class TcpTransport:
    """Non-blocking TCP transport that implements the InputSource protocol.

    The socket must already be connected before construction.
    Internally maintains a receive buffer so partial reads across poll()
    calls are handled correctly.
    """

    def __init__(self, player_id: str, sock: socket.socket) -> None:
        self._player_id  = player_id
        self._sock       = sock
        self._sock.setblocking(False)
        self._recv_buf   = bytearray()

    @property
    def player_id(self) -> str:
        return self._player_id

    # ------------------------------------------------------------------ #
    # Send
    # ------------------------------------------------------------------ #

    def send_frame(self, frame: InputFrame) -> None:
        """Blocking send of one InputFrame to the remote peer."""
        self._sock.sendall(encode_frame(frame))

    # ------------------------------------------------------------------ #
    # Receive (InputSource.poll)
    # ------------------------------------------------------------------ #

    def poll(self, tick: int) -> Optional[InputFrame]:
        """Non-blocking read of the next available InputFrame.

        Returns None if no complete message is in the buffer yet.
        Raises ConnectionError if the remote peer closed the connection.
        """
        try:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("Remote peer closed the connection")
            self._recv_buf.extend(chunk)
        except BlockingIOError:
            pass  # no data available right now; try next poll()

        # Need at least the length prefix
        if len(self._recv_buf) < LENGTH_PREFIX_SIZE:
            return None

        payload_len = read_length(bytes(self._recv_buf[:LENGTH_PREFIX_SIZE]))
        total = LENGTH_PREFIX_SIZE + payload_len

        if len(self._recv_buf) < total:
            return None  # partial payload; wait for more data

        payload = bytes(self._recv_buf[LENGTH_PREFIX_SIZE:total])
        del self._recv_buf[:total]
        return decode_frame(payload)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        self._sock.close()


# ---------------------------------------------------------------------------
# InMemoryTransport
# ---------------------------------------------------------------------------

class InMemoryTransport:
    """In-process test double: two queue.Queue objects replace the socket.

    Create a matched pair:
        host_side, client_side = InMemoryTransport.make_pair("P1", "P2")

    Frames sent from host_side appear at client_side.poll() and vice versa.
    Useful for integration-testing the full network session flow in CI without
    any actual network stack or port allocation.
    """

    def __init__(
        self,
        player_id: str,
        inbox:  queue.Queue,
        outbox: queue.Queue,
    ) -> None:
        self._player_id = player_id
        self._inbox     = inbox
        self._outbox    = outbox

    @classmethod
    def make_pair(
        cls,
        pid_a: str,
        pid_b: str,
    ) -> tuple[InMemoryTransport, InMemoryTransport]:
        """Return two transports whose send/recv are wired together."""
        q_ab: queue.Queue = queue.Queue()
        q_ba: queue.Queue = queue.Queue()
        a = cls(pid_a, inbox=q_ba, outbox=q_ab)
        b = cls(pid_b, inbox=q_ab, outbox=q_ba)
        return a, b

    @property
    def player_id(self) -> str:
        return self._player_id

    def send_frame(self, frame: InputFrame) -> None:
        """Put a frame into the outbox (immediately available to the peer)."""
        self._outbox.put(frame)

    def poll(self, tick: int) -> Optional[InputFrame]:
        """Non-blocking read from the inbox. Returns None if empty."""
        try:
            return self._inbox.get_nowait()
        except queue.Empty:
            return None
