"""Binary framing shared with the Flutter app (flutter lib/protocol.dart).

Every message is: 1 byte type, 4 bytes big-endian payload length, payload.
"""

from __future__ import annotations

import json
import struct

PROTOCOL_VERSION = 1
TYPE_FRAME = 1  # desktop -> phone: JPEG bytes of the captured region
TYPE_JSON = 2  # phone -> desktop: UTF-8 JSON object

_HEADER = struct.Struct(">BI")
_MAX_PAYLOAD = 32 * 1024 * 1024


def pack(message_type: int, payload: bytes) -> bytes:
    return _HEADER.pack(message_type, len(payload)) + payload


def pack_frame(jpeg: bytes) -> bytes:
    return pack(TYPE_FRAME, jpeg)


def pack_json(message: dict) -> bytes:
    return pack(TYPE_JSON, json.dumps(message, separators=(",", ":")).encode("utf-8"))


class Reader:
    """Incrementally splits a byte stream into (type, payload) messages."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self._buffer += data
        messages: list[tuple[int, bytes]] = []
        while len(self._buffer) >= _HEADER.size:
            message_type, length = _HEADER.unpack_from(self._buffer, 0)
            if length > _MAX_PAYLOAD:
                raise ValueError(f"message too large: {length} bytes")
            end = _HEADER.size + length
            if len(self._buffer) < end:
                break
            messages.append((message_type, bytes(self._buffer[_HEADER.size : end])))
            del self._buffer[:end]
        return messages
