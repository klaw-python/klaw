"""Tests for wire protocol message types."""

from __future__ import annotations

import msgspec
import pytest
from klaw_core.runtime.channels.wire import (
    WIRE_SCHEMA_VERSION,
    Ack,
    ControlMessage,
    DataMessage,
    Heartbeat,
    MessageKind,
    WireEnvelope,
    WireError,
    WireHeader,
)


class TestMessageKind:
    """Test MessageKind enum."""

    def test_message_kind_values(self) -> None:
        """MessageKind has correct integer values."""
        assert MessageKind.DATA == 1
        assert MessageKind.CONTROL == 2
        assert MessageKind.HEARTBEAT == 3
        assert MessageKind.ACK == 4
        assert MessageKind.ERROR == 5

    def test_message_kind_is_int_enum(self) -> None:
        """MessageKind values are integers for compact encoding."""
        assert isinstance(MessageKind.DATA, int)
        assert isinstance(MessageKind.CONTROL, int)


class TestWireHeader:
    """Test WireHeader struct."""

    def test_wire_header_default_values(self) -> None:
        """WireHeader has correct default values."""
        header = WireHeader()
        assert header.version == WIRE_SCHEMA_VERSION
        assert header.kind == MessageKind.DATA
        assert header.channel_id == ''  # noqa: PLC1901
        assert header.seq == 0
        assert header.ts == 0

    def test_wire_header_custom_values(self) -> None:
        """WireHeader accepts custom values."""
        header = WireHeader(
            version=2,
            kind=MessageKind.CONTROL,
            channel_id='my-channel',
            seq=42,
            ts=1703001234567,
        )
        assert header.version == 2
        assert header.kind == MessageKind.CONTROL
        assert header.channel_id == 'my-channel'
        assert header.seq == 42
        assert header.ts == 1703001234567

    def test_wire_header_is_frozen(self) -> None:
        """WireHeader is immutable (frozen=True)."""
        header = WireHeader()
        with pytest.raises(AttributeError):
            header.seq = 10  # type: ignore[misc]

    def test_wire_header_is_hashable(self) -> None:
        """WireHeader is hashable (frozen structs are hashable)."""
        header = WireHeader(channel_id='test', seq=1)
        assert hash(header) is not None
        # Can be used in sets
        header_set = {header, WireHeader(channel_id='test', seq=1)}
        assert len(header_set) == 1


class TestDataMessage:
    """Test DataMessage struct."""

    def test_data_message_creation(self) -> None:
        """DataMessage can be created with header and payload."""
        header = WireHeader(channel_id='chan-1', seq=1)
        payload = msgspec.Raw(b'{"key": "value"}')
        msg = DataMessage(header=header, payload=payload)

        assert msg.header == header
        assert msg.payload == payload

    def test_data_message_field_access(self) -> None:
        """DataMessage fields are accessible."""
        header = WireHeader(kind=MessageKind.DATA)
        msg = DataMessage(header=header, payload=msgspec.Raw(b'test'))

        assert msg.header.kind == MessageKind.DATA
        assert bytes(msg.payload) == b'test'

    def test_data_message_is_frozen(self) -> None:
        """DataMessage is immutable."""
        msg = DataMessage(header=WireHeader(), payload=msgspec.Raw(b''))
        with pytest.raises(AttributeError):
            msg.payload = msgspec.Raw(b'new')  # type: ignore[misc]


class TestControlMessage:
    """Test ControlMessage struct."""

    def test_control_message_creation(self) -> None:
        """ControlMessage can be created with action."""
        header = WireHeader(kind=MessageKind.CONTROL)
        msg = ControlMessage(header=header, action='create')

        assert msg.header == header
        assert msg.action == 'create'
        # Default metadata is msgpack null (b"\xc0")
        assert bytes(msg.metadata) == b'\xc0'

    def test_control_message_all_actions(self) -> None:
        """ControlMessage accepts all valid action types."""
        actions = ['create', 'close', 'resize', 'pause', 'resume']
        for action in actions:
            msg = ControlMessage(header=WireHeader(), action=action)
            assert msg.action == action

    def test_control_message_with_metadata(self) -> None:
        """ControlMessage can include metadata."""
        metadata = msgspec.Raw(b'{"new_capacity": 100}')
        msg = ControlMessage(
            header=WireHeader(),
            action='resize',
            metadata=metadata,
        )
        assert bytes(msg.metadata) == b'{"new_capacity": 100}'

    def test_control_message_is_frozen(self) -> None:
        """ControlMessage is immutable."""
        msg = ControlMessage(header=WireHeader(), action='close')
        with pytest.raises(AttributeError):
            msg.action = 'pause'  # type: ignore[misc]


class TestHeartbeat:
    """Test Heartbeat struct."""

    def test_heartbeat_creation(self) -> None:
        """Heartbeat can be created."""
        header = WireHeader(kind=MessageKind.HEARTBEAT)
        msg = Heartbeat(header=header, sender_id='node-1')

        assert msg.header == header
        assert msg.sender_id == 'node-1'

    def test_heartbeat_default_sender_id(self) -> None:
        """Heartbeat has empty default sender_id."""
        msg = Heartbeat(header=WireHeader())
        assert msg.sender_id == ''  # noqa: PLC1901

    def test_heartbeat_is_frozen(self) -> None:
        """Heartbeat is immutable."""
        msg = Heartbeat(header=WireHeader())
        with pytest.raises(AttributeError):
            msg.sender_id = 'new-id'  # type: ignore[misc]


class TestAck:
    """Test Ack struct."""

    def test_ack_creation(self) -> None:
        """Ack can be created."""
        header = WireHeader(kind=MessageKind.ACK)
        msg = Ack(header=header, acked_seq=42, status='ok')

        assert msg.header == header
        assert msg.acked_seq == 42
        assert msg.status == 'ok'

    def test_ack_default_values(self) -> None:
        """Ack has correct defaults."""
        msg = Ack(header=WireHeader())
        assert msg.acked_seq == 0
        assert msg.status == 'ok'

    def test_ack_is_frozen(self) -> None:
        """Ack is immutable."""
        msg = Ack(header=WireHeader())
        with pytest.raises(AttributeError):
            msg.status = 'error'  # type: ignore[misc]


class TestWireError:
    """Test WireError struct."""

    def test_wire_error_creation(self) -> None:
        """WireError can be created."""
        header = WireHeader(kind=MessageKind.ERROR)
        msg = WireError(
            header=header,
            code='channel_closed',
            message='The channel has been closed',
        )

        assert msg.header == header
        assert msg.code == 'channel_closed'
        assert msg.message == 'The channel has been closed'
        # Default details is msgpack null (b"\xc0")
        assert bytes(msg.details) == b'\xc0'

    def test_wire_error_with_details(self) -> None:
        """WireError can include structured details."""
        details = msgspec.Raw(b'{"reason": "timeout"}')
        msg = WireError(
            header=WireHeader(),
            code='timeout',
            message='Operation timed out',
            details=details,
        )
        assert bytes(msg.details) == b'{"reason": "timeout"}'

    def test_wire_error_default_values(self) -> None:
        """WireError has correct defaults."""
        msg = WireError(header=WireHeader())
        assert msg.code == ''  # noqa: PLC1901
        assert msg.message == ''  # noqa: PLC1901
        # Default details is msgpack null (b"\xc0")
        assert bytes(msg.details) == b'\xc0'

    def test_wire_error_is_frozen(self) -> None:
        """WireError is immutable."""
        msg = WireError(header=WireHeader())
        with pytest.raises(AttributeError):
            msg.code = 'new_code'  # type: ignore[misc]


class TestWireEnvelope:
    """Test WireEnvelope type alias."""

    def test_wire_envelope_accepts_data_message(self) -> None:
        """WireEnvelope accepts DataMessage."""
        msg: WireEnvelope = DataMessage(
            header=WireHeader(),
            payload=msgspec.Raw(b'test'),
        )
        assert isinstance(msg, DataMessage)

    def test_wire_envelope_accepts_control_message(self) -> None:
        """WireEnvelope accepts ControlMessage."""
        msg: WireEnvelope = ControlMessage(header=WireHeader(), action='close')
        assert isinstance(msg, ControlMessage)

    def test_wire_envelope_accepts_heartbeat(self) -> None:
        """WireEnvelope accepts Heartbeat."""
        msg: WireEnvelope = Heartbeat(header=WireHeader())
        assert isinstance(msg, Heartbeat)

    def test_wire_envelope_accepts_ack(self) -> None:
        """WireEnvelope accepts Ack."""
        msg: WireEnvelope = Ack(header=WireHeader())
        assert isinstance(msg, Ack)

    def test_wire_envelope_accepts_wire_error(self) -> None:
        """WireEnvelope accepts WireError."""
        msg: WireEnvelope = WireError(header=WireHeader())
        assert isinstance(msg, WireError)


class TestWireSchemaVersion:
    """Test WIRE_SCHEMA_VERSION constant."""

    def test_wire_schema_version_is_one(self) -> None:
        """Initial schema version is 1."""
        assert WIRE_SCHEMA_VERSION == 1

    def test_wire_schema_version_is_int(self) -> None:
        """Schema version is an integer."""
        assert isinstance(WIRE_SCHEMA_VERSION, int)
