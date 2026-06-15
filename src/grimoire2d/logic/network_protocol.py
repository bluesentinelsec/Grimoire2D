"""Wire protocol for serialising InputFrames and state snapshots over TCP.

Format: 4-byte little-endian unsigned length prefix + UTF-8 JSON payload.
No external dependencies; json and struct are stdlib.

The length prefix gives the receiver an exact byte count before it reads
the payload, enabling correct framing over a stream socket (TCP delivers
bytes, not messages).

Public API:

  encode_frame(frame)      → bytes   (prefix + payload)
  decode_frame(payload)    → InputFrame  (payload only, no prefix)
  encode_state(state_dict) → bytes   (prefix + payload)
  decode_state(payload)    → dict    (payload only, no prefix)
  read_length(header)      → int     (parse the 4-byte prefix)
  LENGTH_PREFIX_SIZE       → int = 4

TcpTransport uses these functions internally; games do not call them directly
unless implementing a custom transport.
"""

from __future__ import annotations

import json
import struct
from typing import Any

from grimoire2d.models.input_frame import InputFrame

_FMT        = "<I"                      # unsigned 32-bit little-endian
_HDR_SIZE   = struct.calcsize(_FMT)     # always 4

LENGTH_PREFIX_SIZE: int = _HDR_SIZE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pack(payload: bytes) -> bytes:
    """Prepend a 4-byte length header to a payload."""
    return struct.pack(_FMT, len(payload)) + payload


# ---------------------------------------------------------------------------
# InputFrame codec
# ---------------------------------------------------------------------------

def encode_frame(frame: InputFrame) -> bytes:
    """Serialise an InputFrame to length-prefixed JSON bytes."""
    payload = json.dumps(frame.to_dict(), separators=(",", ":")).encode("utf-8")
    return _pack(payload)


def decode_frame(payload: bytes) -> InputFrame:
    """Deserialise an InputFrame from a raw JSON payload (no length prefix)."""
    return InputFrame.from_dict(json.loads(payload.decode("utf-8")))


# ---------------------------------------------------------------------------
# State snapshot codec
# ---------------------------------------------------------------------------

def encode_state(state_dict: dict[str, Any]) -> bytes:
    """Serialise an arbitrary state dict to length-prefixed JSON bytes."""
    payload = json.dumps(state_dict, separators=(",", ":")).encode("utf-8")
    return _pack(payload)


def decode_state(payload: bytes) -> dict[str, Any]:
    """Deserialise a state dict from a raw JSON payload (no length prefix)."""
    return json.loads(payload.decode("utf-8"))


# ---------------------------------------------------------------------------
# Framing helper
# ---------------------------------------------------------------------------

def read_length(header: bytes) -> int:
    """Parse the 4-byte length prefix and return the payload byte count.

    Raises ValueError if header is shorter than LENGTH_PREFIX_SIZE.
    """
    if len(header) < _HDR_SIZE:
        raise ValueError(
            f"Header too short: expected {_HDR_SIZE} bytes, got {len(header)}"
        )
    (length,) = struct.unpack(_FMT, header[:_HDR_SIZE])
    return length
