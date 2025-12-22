"""Hypothesis strategies for property-based testing of klaw-core types."""

import msgspec
from hypothesis import strategies as st
from klaw_core.runtime.channels.wire import (
    Ack,
    ControlMessage,
    DataMessage,
    Heartbeat,
    MessageKind,
    WireEnvelope,
    WireError,
    WireHeader,
)

# -----------------------------------------------------------------------------
# Basic value strategies
# -----------------------------------------------------------------------------

integers = st.integers()
texts = st.text(min_size=0, max_size=100)
booleans = st.booleans()

# Exception strategies
exceptions = st.sampled_from([
    ValueError('test'),
    TypeError('test'),
    RuntimeError('test'),
])

# -----------------------------------------------------------------------------
# Wire Protocol Strategies
# -----------------------------------------------------------------------------

# MessageKind enum
message_kinds = st.sampled_from(list(MessageKind))

# Channel IDs - simple identifiers
channel_ids = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789-_'),
    min_size=0,
    max_size=64,
)

# Sender IDs for heartbeats
sender_ids = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789-_'),
    min_size=0,
    max_size=32,
)

# Action strings for control messages
control_actions = st.sampled_from(['create', 'close', 'resize', 'pause', 'resume'])

# Status strings for acks
ack_statuses = st.sampled_from(['ok', 'error', 'timeout', 'rejected'])

# Error codes
error_codes = st.sampled_from([
    '',
    'channel_closed',
    'timeout',
    'invalid_message',
    'capacity_exceeded',
])

# Sequence numbers (non-negative)
seq_numbers = st.integers(min_value=0, max_value=2**63 - 1)

# Timestamps (Unix millis, non-negative)
timestamps = st.integers(min_value=0, max_value=2**63 - 1)

# Schema versions
schema_versions = st.integers(min_value=1, max_value=100)


def _msgpack_raw_from_value(value: object) -> msgspec.Raw:
    """Convert a Python value to msgspec.Raw (msgpack encoded)."""
    enc = msgspec.msgpack.Encoder()
    return msgspec.Raw(enc.encode(value))


# Raw payloads - valid msgpack bytes
# We generate Python values then encode them
raw_payloads = st.one_of(
    st.none().map(_msgpack_raw_from_value),
    st.integers(min_value=-1000, max_value=1000).map(_msgpack_raw_from_value),
    st.text(max_size=50).map(_msgpack_raw_from_value),
    st.booleans().map(_msgpack_raw_from_value),
    st.lists(st.integers(min_value=-100, max_value=100), max_size=10).map(_msgpack_raw_from_value),
    st.dictionaries(
        st.text(min_size=1, max_size=10),
        st.integers(min_value=-100, max_value=100),
        max_size=5,
    ).map(_msgpack_raw_from_value),
)


@st.composite
def wire_headers(
    draw: st.DrawFn,
    kind: MessageKind | None = None,
) -> WireHeader:
    """Generate WireHeader instances.

    Args:
        draw: Hypothesis draw function.
        kind: If provided, use this specific MessageKind. Otherwise random.
    """
    return WireHeader(
        version=draw(schema_versions),
        kind=kind if kind is not None else draw(message_kinds),
        channel_id=draw(channel_ids),
        seq=draw(seq_numbers),
        ts=draw(timestamps),
    )


@st.composite
def data_messages(draw: st.DrawFn) -> DataMessage[msgspec.Raw]:
    """Generate DataMessage instances with Raw payloads."""
    return DataMessage(
        header=draw(wire_headers(kind=MessageKind.DATA)),
        payload=draw(raw_payloads),
    )


@st.composite
def control_messages(draw: st.DrawFn) -> ControlMessage:
    """Generate ControlMessage instances."""
    return ControlMessage(
        header=draw(wire_headers(kind=MessageKind.CONTROL)),
        action=draw(control_actions),
        metadata=draw(raw_payloads),
    )


@st.composite
def heartbeats(draw: st.DrawFn) -> Heartbeat:
    """Generate Heartbeat instances."""
    return Heartbeat(
        header=draw(wire_headers(kind=MessageKind.HEARTBEAT)),
        sender_id=draw(sender_ids),
    )


@st.composite
def acks(draw: st.DrawFn) -> Ack:
    """Generate Ack instances."""
    return Ack(
        header=draw(wire_headers(kind=MessageKind.ACK)),
        acked_seq=draw(seq_numbers),
        status=draw(ack_statuses),
    )


@st.composite
def wire_errors(draw: st.DrawFn) -> WireError:
    """Generate WireError instances."""
    return WireError(
        header=draw(wire_headers(kind=MessageKind.ERROR)),
        code=draw(error_codes),
        message=draw(st.text(max_size=100)),
        details=draw(raw_payloads),
    )


# Combined strategy for any WireEnvelope variant
wire_envelopes: st.SearchStrategy[WireEnvelope] = st.one_of(
    data_messages(),
    control_messages(),
    heartbeats(),
    acks(),
    wire_errors(),
)
