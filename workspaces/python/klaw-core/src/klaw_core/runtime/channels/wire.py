"""Wire protocol message types for klaw-core channels.

This module defines the canonical envelope format for messages crossing
process or network boundaries (e.g., Ray actor calls, distributed channels).

The wire protocol uses msgspec's tagged unions for efficient polymorphic
dispatch and MessagePack encoding with `array_like=True` for compact
representation.

Schema versioning is built-in via `WIRE_SCHEMA_VERSION` in `WireHeader`,
enabling forward-compatible evolution.

Usage:
    >>> from klaw_core.runtime.channels.wire import (
    ...     DataMessage, WireHeader, WireEnvelope
    ... )
    >>> from klaw_core.runtime.channels.codec import get_codec_pool
    >>> import msgspec
    >>>
    >>> header = WireHeader(channel_id="my-channel", seq=1)
    >>> msg = DataMessage(header=header, payload=msgspec.Raw(b'{"key": "value"}'))
    >>> pool = get_codec_pool()
    >>> encoded = pool.encode(msg)
    >>> decoded = pool.decode(encoded)

See Also:
    - codec.py: Encoder/decoder pools for wire messages
    - schema.py: Schema registry for version evolution
"""

from __future__ import annotations

from enum import IntEnum
from typing import Generic, TypeVar

import msgspec

__all__ = [
    'WIRE_SCHEMA_VERSION',
    'Ack',
    'ControlMessage',
    'DataMessage',
    'Heartbeat',
    'MessageKind',
    'WireEnvelope',
    'WireError',
    'WireHeader',
]

T = TypeVar('T')

# -----------------------------------------------------------------------------
# Schema Version
# -----------------------------------------------------------------------------

WIRE_SCHEMA_VERSION: int = 1
"""Current wire protocol schema version.

Increment this when making breaking changes to message structure.
The version is embedded in every WireHeader, enabling receivers to
route messages to the appropriate decoder.

Version history:
    1 - Initial wire protocol with DataMessage, ControlMessage,
        Heartbeat, Ack, and WireError.
"""


# -----------------------------------------------------------------------------
# Message Kind Discriminator
# -----------------------------------------------------------------------------


class MessageKind(IntEnum):
    """Discriminator for wire message types.

    Uses IntEnum (not StrEnum) for compact MessagePack encoding—each
    variant encodes as a single byte rather than a variable-length string.

    These values are used in WireHeader.kind to indicate the message
    category before full decoding.
    """

    DATA = 1
    """User data payload (DataMessage)."""

    CONTROL = 2
    """Control plane command (ControlMessage)."""

    HEARTBEAT = 3
    """Liveness probe (Heartbeat)."""

    ACK = 4
    """Delivery acknowledgment (Ack)."""

    ERROR = 5
    """Error response (WireError)."""


# -----------------------------------------------------------------------------
# Wire Header
# -----------------------------------------------------------------------------


class WireHeader(msgspec.Struct, array_like=True, frozen=True, gc=False):
    """Common header for all wire messages.

    Encoded as a positional array for compact representation:
        [version, kind, channel_id, seq, ts]

    Attributes:
        version: Schema version for forward compatibility.
        kind: Message category discriminator.
        channel_id: Target channel identifier.
        seq: Sequence number for ordering/deduplication.
        ts: Unix timestamp in milliseconds.
    """

    version: int = WIRE_SCHEMA_VERSION
    kind: MessageKind = MessageKind.DATA
    channel_id: str = ''
    seq: int = 0
    ts: int = 0


# -----------------------------------------------------------------------------
# Message Types (Tagged Union Variants)
# -----------------------------------------------------------------------------


class DataMessage(msgspec.Struct, Generic[T], tag=1, array_like=True, frozen=True, gc=False):
    """Data plane message carrying a user payload.

    The payload is typically encoded as `msgspec.Raw` in the envelope,
    allowing deferred decoding to the actual type when needed.

    Attributes:
        header: Common wire header.
        payload: The user data of type T.
    """

    header: WireHeader
    payload: T


class ControlMessage(msgspec.Struct, tag=2, array_like=True, frozen=True, gc=False):
    """Control plane message for channel lifecycle operations.

    Used for out-of-band commands that manage channel state rather than
    carrying user data.

    Attributes:
        header: Common wire header.
        action: The control action to perform.
            Valid values: "create", "close", "resize", "pause", "resume".
        metadata: Optional action-specific metadata as raw bytes.
    """

    header: WireHeader
    action: str
    metadata: msgspec.Raw = msgspec.Raw(b'\xc0')


class Heartbeat(msgspec.Struct, tag=3, array_like=True, frozen=True, gc=False):
    """Liveness probe for connection health monitoring.

    Sent periodically to detect dead connections and trigger failover.
    The receiver should respond with an Ack.

    Attributes:
        header: Common wire header.
        sender_id: Identifier of the heartbeat sender.
    """

    header: WireHeader
    sender_id: str = ''


class Ack(msgspec.Struct, tag=4, array_like=True, frozen=True, gc=False):
    """Acknowledgment for reliable delivery confirmation.

    Sent in response to messages that require confirmation, such as
    heartbeats or critical data messages.

    Attributes:
        header: Common wire header.
        acked_seq: Sequence number of the acknowledged message.
        status: Acknowledgment status ("ok", "error", etc.).
    """

    header: WireHeader
    acked_seq: int = 0
    status: str = 'ok'


class WireError(msgspec.Struct, tag=5, array_like=True, frozen=True, gc=False):
    """Error response for failed operations.

    Returned when a request cannot be fulfilled. The code field enables
    programmatic error handling, while message provides human-readable
    context.

    Attributes:
        header: Common wire header.
        code: Machine-readable error code (e.g., "channel_closed", "timeout").
        message: Human-readable error description.
        details: Optional structured error details as raw bytes.
    """

    header: WireHeader
    code: str = ''
    message: str = ''
    details: msgspec.Raw = msgspec.Raw(b'\xc0')


# -----------------------------------------------------------------------------
# Wire Envelope (Tagged Union)
# -----------------------------------------------------------------------------

WireEnvelope = DataMessage[msgspec.Raw] | ControlMessage | Heartbeat | Ack | WireError
"""Canonical envelope for all wire protocol messages.

This is the primary type for encoding/decoding messages crossing process
or network boundaries. The tagged union enables efficient dispatch:

    from klaw_core.runtime.channels.codec import get_codec_pool

    pool = get_codec_pool()
    decoded = pool.decode(raw_bytes)

    match decoded:
        case DataMessage(header=h, payload=p):
            # Decode raw payload to actual type
            actual = pool.decode_payload(p, MyType)
        case ControlMessage(header=h, action=a):
            handle_control(a)
        case Heartbeat():
            send_ack()
        case Ack():
            mark_delivered()
        case WireError(code=c, message=m):
            handle_error(c, m)

Note: DataMessage uses `msgspec.Raw` for deferred payload decoding,
allowing the envelope to be decoded without knowing the payload type.
See `codec.py` for encoding/decoding utilities.
"""
