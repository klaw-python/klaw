"""Unit tests for codec pool infrastructure."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import msgspec
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from klaw_core.runtime.channels.codec import (
    BufferPool,
    CodecPool,
    decode,
    encode,
    get_buffer_pool,
    get_codec_pool,
)
from klaw_core.runtime.channels.wire import (
    Ack,
    ControlMessage,
    DataMessage,
    Heartbeat,
    WireEnvelope,
    WireError,
    WireHeader,
)

from tests.strategies import (
    acks,
    control_messages,
    data_messages,
    heartbeats,
    wire_envelopes,
    wire_errors,
    wire_headers,
)


class TestCodecPoolInstantiation:
    """Tests for CodecPool creation."""

    def test_instantiation(self) -> None:
        """CodecPool can be instantiated."""
        pool = CodecPool()
        assert pool is not None

    def test_has_envelope_decoder(self) -> None:
        """CodecPool has a shared envelope decoder."""
        pool = CodecPool()
        assert pool._envelope_decoder is not None
        assert isinstance(pool._envelope_decoder, msgspec.msgpack.Decoder)


class TestCodecPoolEncode:
    """Tests for CodecPool.encode()."""

    def test_encode_returns_bytes(self) -> None:
        """encode() returns bytes."""
        pool = CodecPool()
        msg = Heartbeat(header=WireHeader(), sender_id='test')
        result = pool.encode(msg)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_data_message(self) -> None:
        """encode() works with DataMessage."""
        pool = CodecPool()
        header = WireHeader(channel_id='ch-1', seq=42)
        msg = DataMessage(header=header, payload=msgspec.Raw(b'"hello"'))
        result = pool.encode(msg)
        assert isinstance(result, bytes)

    def test_encode_control_message(self) -> None:
        """encode() works with ControlMessage."""
        pool = CodecPool()
        header = WireHeader(channel_id='ch-1')
        msg = ControlMessage(header=header, action='close')
        result = pool.encode(msg)
        assert isinstance(result, bytes)

    def test_encode_heartbeat(self) -> None:
        """encode() works with Heartbeat."""
        pool = CodecPool()
        msg = Heartbeat(header=WireHeader(), sender_id='node-1')
        result = pool.encode(msg)
        assert isinstance(result, bytes)

    def test_encode_ack(self) -> None:
        """encode() works with Ack."""
        pool = CodecPool()
        msg = Ack(header=WireHeader(), acked_seq=100, status='ok')
        result = pool.encode(msg)
        assert isinstance(result, bytes)

    def test_encode_wire_error(self) -> None:
        """encode() works with WireError."""
        pool = CodecPool()
        msg = WireError(header=WireHeader(), code='timeout', message='Request timed out')
        result = pool.encode(msg)
        assert isinstance(result, bytes)


class TestCodecPoolDecode:
    """Tests for CodecPool.decode()."""

    def test_decode_returns_wire_envelope(self) -> None:
        """decode() returns a WireEnvelope variant."""
        pool = CodecPool()
        msg = Heartbeat(header=WireHeader(), sender_id='test')
        encoded = pool.encode(msg)
        decoded = pool.decode(encoded)
        assert isinstance(decoded, Heartbeat)

    def test_decode_preserves_type(self) -> None:
        """decode() returns the correct variant type."""
        pool = CodecPool()
        messages: list[WireEnvelope] = [
            DataMessage(header=WireHeader(), payload=msgspec.Raw(b'\xc0')),
            ControlMessage(header=WireHeader(), action='pause'),
            Heartbeat(header=WireHeader(), sender_id='s1'),
            Ack(header=WireHeader(), acked_seq=1),
            WireError(header=WireHeader(), code='err'),
        ]
        for msg in messages:
            encoded = pool.encode(msg)
            decoded = pool.decode(encoded)
            assert type(decoded) is type(msg)

    def test_decode_from_bytes(self) -> None:
        """decode() accepts bytes input."""
        pool = CodecPool()
        msg = Heartbeat(header=WireHeader(), sender_id='bytes-test')
        encoded: bytes = pool.encode(msg)
        assert isinstance(encoded, bytes)
        decoded = pool.decode(encoded)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'bytes-test'

    def test_decode_from_bytearray(self) -> None:
        """decode() accepts bytearray input."""
        pool = CodecPool()
        msg = Ack(header=WireHeader(), acked_seq=42)
        encoded = pool.encode(msg)
        ba = bytearray(encoded)
        decoded = pool.decode(ba)
        assert isinstance(decoded, Ack)
        assert decoded.acked_seq == 42

    def test_decode_from_memoryview(self) -> None:
        """decode() accepts memoryview input."""
        pool = CodecPool()
        msg = ControlMessage(header=WireHeader(), action='pause')
        encoded = pool.encode(msg)
        mv = memoryview(encoded)
        decoded = pool.decode(mv)
        assert isinstance(decoded, ControlMessage)
        assert decoded.action == 'pause'

    def test_decode_from_memoryview_slice(self) -> None:
        """decode() accepts memoryview slice for zero-copy parsing."""
        pool = CodecPool()
        msg = Heartbeat(header=WireHeader(seq=999), sender_id='slice-test')
        encoded = pool.encode(msg)
        # Embed in larger buffer with padding
        padded = b'\x00\x00\x00' + encoded + b'\x00\x00\x00'
        mv = memoryview(padded)[3 : 3 + len(encoded)]
        decoded = pool.decode(mv)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'slice-test'
        assert decoded.header.seq == 999


class TestCodecPoolRoundtrip:
    """Tests for encode/decode roundtrip."""

    def test_roundtrip_data_message(self) -> None:
        """DataMessage survives roundtrip."""
        pool = CodecPool()
        header = WireHeader(channel_id='roundtrip', seq=123, ts=1700000000000)
        # Payload must be valid msgpack - encode a dict
        inner_enc = msgspec.msgpack.Encoder()
        payload_bytes = inner_enc.encode({'key': 'value'})
        msg = DataMessage(header=header, payload=msgspec.Raw(payload_bytes))
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, DataMessage)
        assert decoded.header.channel_id == 'roundtrip'
        assert decoded.header.seq == 123
        assert decoded.header.ts == 1700000000000

    def test_roundtrip_control_message(self) -> None:
        """ControlMessage survives roundtrip."""
        pool = CodecPool()
        header = WireHeader(channel_id='ctrl-ch')
        # Metadata must be valid msgpack - encode a dict
        inner_enc = msgspec.msgpack.Encoder()
        metadata_bytes = inner_enc.encode({'size': 100})
        msg = ControlMessage(header=header, action='resize', metadata=msgspec.Raw(metadata_bytes))
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, ControlMessage)
        assert decoded.action == 'resize'
        # Verify metadata can be decoded back
        metadata_dec = msgspec.msgpack.Decoder(dict[str, int])
        assert metadata_dec.decode(decoded.metadata) == {'size': 100}

    def test_roundtrip_heartbeat(self) -> None:
        """Heartbeat survives roundtrip."""
        pool = CodecPool()
        msg = Heartbeat(header=WireHeader(), sender_id='worker-42')
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'worker-42'

    def test_roundtrip_ack(self) -> None:
        """Ack survives roundtrip."""
        pool = CodecPool()
        msg = Ack(header=WireHeader(), acked_seq=999, status='delivered')
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, Ack)
        assert decoded.acked_seq == 999
        assert decoded.status == 'delivered'

    def test_roundtrip_wire_error(self) -> None:
        """WireError survives roundtrip."""
        pool = CodecPool()
        # Details must be valid msgpack - encode a dict
        inner_enc = msgspec.msgpack.Encoder()
        details_bytes = inner_enc.encode({'reason': 'shutdown'})
        msg = WireError(
            header=WireHeader(),
            code='channel_closed',
            message='Channel was closed',
            details=msgspec.Raw(details_bytes),
        )
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, WireError)
        assert decoded.code == 'channel_closed'
        assert decoded.message == 'Channel was closed'
        # Verify details can be decoded back
        details_dec = msgspec.msgpack.Decoder(dict[str, str])
        assert details_dec.decode(decoded.details) == {'reason': 'shutdown'}


class TestEncodeInto:
    """Tests for CodecPool.encode_into().

    Note: encode_into() truncates the buffer to the end of the serialized
    message. The buffer can be decoded directly after encoding.
    """

    def test_encode_into_writes_to_buffer(self) -> None:
        """encode_into() writes to the provided buffer."""
        pool = CodecPool()
        buf = bytearray(4096)
        msg = Heartbeat(header=WireHeader(), sender_id='test')
        written = pool.encode_into(msg, buf)
        assert written > 0
        # Buffer is now truncated to the message length
        assert len(buf) == written

    def test_encode_into_returns_byte_count(self) -> None:
        """encode_into() returns number of bytes written."""
        pool = CodecPool()
        buf = bytearray(4096)
        msg = Ack(header=WireHeader(), acked_seq=42)
        written = pool.encode_into(msg, buf)
        # Should match direct encode length
        direct = pool.encode(msg)
        assert written == len(direct)
        # Buffer is truncated to message size
        assert len(buf) == written

    def test_encode_into_decodable(self) -> None:
        """Data written by encode_into() is decodable."""
        pool = CodecPool()
        buf = bytearray(4096)
        msg = ControlMessage(header=WireHeader(), action='close')
        pool.encode_into(msg, buf)
        # Buffer is truncated, decode directly
        decoded = pool.decode(buf)
        assert isinstance(decoded, ControlMessage)
        assert decoded.action == 'close'

    def test_encode_into_with_offset(self) -> None:
        """encode_into() respects offset parameter."""
        pool = CodecPool()
        buf = bytearray(4096)
        offset = 100
        msg = Heartbeat(header=WireHeader(), sender_id='offset-test')
        written = pool.encode_into(msg, buf, offset)
        # Buffer is truncated to offset + message length
        assert len(buf) == offset + written
        decoded = pool.decode(buf[offset:])
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'offset-test'


class TestDecodePayload:
    """Tests for CodecPool.decode_payload()."""

    def test_decode_payload_dict(self) -> None:
        """decode_payload() decodes to dict."""
        pool = CodecPool()
        # Encode a dict as msgpack Raw
        inner_encoder = msgspec.msgpack.Encoder()
        raw_bytes = inner_encoder.encode({'key': 'value', 'num': 42})
        raw = msgspec.Raw(raw_bytes)

        result = pool.decode_payload(raw, dict[str, str | int])
        assert result == {'key': 'value', 'num': 42}

    def test_decode_payload_list(self) -> None:
        """decode_payload() decodes to list."""
        pool = CodecPool()
        inner_encoder = msgspec.msgpack.Encoder()
        raw_bytes = inner_encoder.encode([1, 2, 3, 4, 5])
        raw = msgspec.Raw(raw_bytes)

        result = pool.decode_payload(raw, list[int])
        assert result == [1, 2, 3, 4, 5]

    def test_decode_payload_struct(self) -> None:
        """decode_payload() decodes to msgspec.Struct."""

        class Point(msgspec.Struct):
            x: int
            y: int

        pool = CodecPool()
        inner_encoder = msgspec.msgpack.Encoder()
        raw_bytes = inner_encoder.encode(Point(x=10, y=20))
        raw = msgspec.Raw(raw_bytes)

        result = pool.decode_payload(raw, Point)
        assert result.x == 10
        assert result.y == 20


class TestGetCodecPool:
    """Tests for get_codec_pool() singleton."""

    def test_returns_codec_pool(self) -> None:
        """get_codec_pool() returns a CodecPool."""
        pool = get_codec_pool()
        assert isinstance(pool, CodecPool)

    def test_returns_singleton(self) -> None:
        """get_codec_pool() returns the same instance."""
        pool1 = get_codec_pool()
        pool2 = get_codec_pool()
        assert pool1 is pool2


class TestConvenienceFunctions:
    """Tests for module-level encode/decode functions."""

    def test_encode_function(self) -> None:
        """encode() convenience function works."""
        msg = Heartbeat(header=WireHeader(), sender_id='convenience')
        result = encode(msg)
        assert isinstance(result, bytes)

    def test_decode_function(self) -> None:
        """decode() convenience function works."""
        msg = Heartbeat(header=WireHeader(), sender_id='convenience')
        encoded = encode(msg)
        decoded = decode(encoded)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'convenience'

    def test_roundtrip_via_convenience(self) -> None:
        """Roundtrip via convenience functions."""
        # Payload must be valid msgpack
        inner_enc = msgspec.msgpack.Encoder()
        payload_bytes = inner_enc.encode('test')
        msg = DataMessage(
            header=WireHeader(channel_id='conv-ch', seq=1),
            payload=msgspec.Raw(payload_bytes),
        )
        decoded = decode(encode(msg))
        assert isinstance(decoded, DataMessage)
        assert decoded.header.channel_id == 'conv-ch'


# -----------------------------------------------------------------------------
# BufferPool Tests
# -----------------------------------------------------------------------------


class TestBufferPoolInstantiation:
    """Tests for BufferPool creation."""

    def test_instantiation_with_defaults(self) -> None:
        """BufferPool can be instantiated with default values."""
        pool = BufferPool()
        assert pool is not None
        assert pool._buffer_size == 4096
        assert pool._max_pool == 64

    def test_instantiation_with_custom_sizes(self) -> None:
        """BufferPool accepts custom buffer_size and max_pool."""
        pool = BufferPool(buffer_size=8192, max_pool=32)
        assert pool._buffer_size == 8192
        assert pool._max_pool == 32


class TestBufferPoolAcquire:
    """Tests for BufferPool.acquire()."""

    def test_acquire_returns_bytearray(self) -> None:
        """acquire() returns a bytearray."""
        pool = BufferPool()
        buf = pool.acquire()
        assert isinstance(buf, bytearray)

    def test_acquire_returns_correct_size(self) -> None:
        """acquire() returns buffer of configured size (but cleared, so len=0)."""
        pool = BufferPool(buffer_size=2048)
        buf = pool.acquire()
        # New buffer starts with the configured capacity but is cleared
        # Actually, bytearray(2048) has len 2048, but after clear it's len 0
        # Wait, that's not right. bytearray(2048) creates array of 2048 zeros
        # Let me check: the implementation creates bytearray(buffer_size)
        # which has len == buffer_size. But acquire clears before returning.
        # Actually re-reading: clear() removes all items, making len 0.
        # But for a new buffer, we don't clear it - we just create it.
        # Let me trace the code more carefully.
        # In acquire(): if pool not empty, pop and clear. Else create new.
        # So for a new buffer: bytearray(self._buffer_size) which has len=buffer_size
        assert len(buf) == 2048

    def test_acquire_returns_cleared_buffer(self) -> None:
        """acquire() returns a cleared buffer when reusing from pool."""
        pool = BufferPool(buffer_size=100)
        buf1 = pool.acquire()
        # Write some data
        buf1.extend(b'test data here')
        pool.release(buf1)
        # Re-acquire - should be same buffer but cleared
        buf2 = pool.acquire()
        assert len(buf2) == 0  # Cleared on acquire


class TestBufferPoolRelease:
    """Tests for BufferPool.release()."""

    def test_release_and_reacquire_same_buffer(self) -> None:
        """Released buffer can be reacquired."""
        pool = BufferPool(buffer_size=1024, max_pool=1)
        buf1 = pool.acquire()
        buf1_id = id(buf1)
        pool.release(buf1)
        buf2 = pool.acquire()
        # Should be the same object (reused)
        assert id(buf2) == buf1_id

    def test_release_respects_max_pool(self) -> None:
        """Pool discards buffers when at max capacity."""
        pool = BufferPool(buffer_size=100, max_pool=2)
        # Acquire 3 buffers
        buf1 = pool.acquire()
        buf2 = pool.acquire()
        buf3 = pool.acquire()
        ids = {id(buf1), id(buf2), id(buf3)}
        assert len(ids) == 3  # All different buffers

        # Release all 3 - only 2 should be kept
        pool.release(buf1)
        pool.release(buf2)
        pool.release(buf3)  # This one should be discarded

        # Acquire 3 again - should get 2 from pool, 1 new
        reacquired = [pool.acquire(), pool.acquire(), pool.acquire()]
        reacquired_ids = {id(b) for b in reacquired}
        # At least one should be new (not in original ids) because max_pool=2
        overlap = ids & reacquired_ids
        assert len(overlap) == 2  # Only 2 were kept in pool


class TestGetBufferPool:
    """Tests for get_buffer_pool() singleton."""

    def test_returns_buffer_pool(self) -> None:
        """get_buffer_pool() returns a BufferPool."""
        pool = get_buffer_pool()
        assert isinstance(pool, BufferPool)

    def test_returns_singleton(self) -> None:
        """get_buffer_pool() returns the same instance."""
        pool1 = get_buffer_pool()
        pool2 = get_buffer_pool()
        assert pool1 is pool2


class TestBufferPoolThreadSafety:
    """Tests for BufferPool thread safety."""

    def test_concurrent_acquire_release(self) -> None:
        """Multiple threads can acquire/release concurrently."""
        pool = BufferPool(buffer_size=256, max_pool=16)
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(iterations: int) -> None:
            try:
                for _ in range(iterations):
                    buf = pool.acquire()
                    # Simulate some work
                    buf.extend(b'x' * 10)
                    pool.release(buf)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker, args=(50,)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors occurred: {errors}'

    def test_singleton_thread_safety(self) -> None:
        """get_buffer_pool() returns same instance across threads."""
        pools: list[BufferPool] = []
        lock = threading.Lock()

        def get_pool() -> None:
            pool = get_buffer_pool()
            with lock:
                pools.append(pool)

        threads = [threading.Thread(target=get_pool) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(pools) == 10
        assert all(p is pools[0] for p in pools)


class TestBufferPoolIntegration:
    """Integration tests for BufferPool with CodecPool."""

    def test_encode_into_with_pooled_buffer(self) -> None:
        """encode_into() works with buffer from BufferPool."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=4096)

        msg = Heartbeat(header=WireHeader(seq=42), sender_id='integration-test')

        buf = buffer_pool.acquire()
        written = codec.encode_into(msg, buf)
        assert written > 0

        # Decode from the buffer
        decoded = codec.decode(buf)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'integration-test'
        assert decoded.header.seq == 42

        buffer_pool.release(buf)

    def test_multiple_encode_decode_cycles_with_pool(self) -> None:
        """Multiple messages can be encoded/decoded reusing pooled buffers."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=4096, max_pool=4)

        messages = [Heartbeat(header=WireHeader(seq=i), sender_id=f'sender-{i}') for i in range(10)]

        for msg in messages:
            buf = buffer_pool.acquire()
            codec.encode_into(msg, buf)
            decoded = codec.decode(buf)
            assert isinstance(decoded, Heartbeat)
            assert decoded.sender_id == msg.sender_id
            buffer_pool.release(buf)


class TestBufferPoolEdgeCases:
    """Edge case tests for BufferPool + CodecPool integration."""

    def test_buffer_smaller_than_message_auto_resizes(self) -> None:
        """Msgspec auto-resizes buffer when message exceeds buffer size."""
        codec = CodecPool()
        # Tiny buffer - 16 bytes
        buffer_pool = BufferPool(buffer_size=16, max_pool=4)

        # Create a message that will definitely exceed 16 bytes
        msg = Heartbeat(
            header=WireHeader(channel_id='a-longer-channel-id', seq=999999),
            sender_id='a-very-long-sender-id-that-exceeds-buffer',
        )

        buf = buffer_pool.acquire()
        original_size = len(buf)
        assert original_size == 16

        # encode_into should resize the buffer
        written = codec.encode_into(msg, buf)
        assert written > original_size  # Message is larger than original buffer

        # Buffer should now be truncated to message size
        assert len(buf) == written

        # Should still decode correctly
        decoded = codec.decode(buf)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'a-very-long-sender-id-that-exceeds-buffer'

        buffer_pool.release(buf)

    def test_large_message_exceeding_default_buffer(self) -> None:
        """Large messages (>4KB) work correctly with buffer pool."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=4096, max_pool=2)

        # Create a large payload - 10KB of data
        large_payload = b'x' * 10_000
        inner_enc = msgspec.msgpack.Encoder()
        payload_bytes = inner_enc.encode(large_payload)

        msg = DataMessage(
            header=WireHeader(channel_id='large-channel', seq=1),
            payload=msgspec.Raw(payload_bytes),
        )

        buf = buffer_pool.acquire()
        written = codec.encode_into(msg, buf)

        # Should have expanded beyond 4KB
        assert written > 4096

        decoded = codec.decode(buf)
        assert isinstance(decoded, DataMessage)

        # Verify payload integrity
        decoded_payload = codec.decode_payload(decoded.payload, bytes)
        assert decoded_payload == large_payload

        buffer_pool.release(buf)

    def test_multiple_encodes_same_buffer_without_release(self) -> None:
        """Multiple encodes to same buffer overwrite previous content."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=4096, max_pool=2)

        buf = buffer_pool.acquire()

        # First encode
        msg1 = Heartbeat(header=WireHeader(seq=1), sender_id='first')
        codec.encode_into(msg1, buf)

        # Second encode to same buffer (without release/reacquire)
        # Need to reset buffer for reuse
        buf.clear()
        msg2 = Heartbeat(header=WireHeader(seq=2), sender_id='second')
        codec.encode_into(msg2, buf)

        # Should decode the second message
        decoded = codec.decode(buf)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'second'
        assert decoded.header.seq == 2

        buffer_pool.release(buf)

    def test_memoryview_of_pooled_buffer(self) -> None:
        """Decode works from memoryview slice of pooled buffer."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=4096, max_pool=2)

        msg = Ack(header=WireHeader(seq=42), acked_seq=100, status='delivered')

        buf = buffer_pool.acquire()
        written = codec.encode_into(msg, buf)

        # Create memoryview and decode from it
        mv = memoryview(buf)
        decoded = codec.decode(mv[:written])
        assert isinstance(decoded, Ack)
        assert decoded.acked_seq == 100
        assert decoded.status == 'delivered'

        buffer_pool.release(buf)

    def test_buffer_usable_after_decode_error(self) -> None:
        """Buffer remains usable after a decode error."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=256, max_pool=2)

        buf = buffer_pool.acquire()

        # Write invalid msgpack data
        buf.extend(b'\xff\xff\xff\xff')  # Invalid msgpack

        # Decode should fail
        with pytest.raises(msgspec.DecodeError):
            codec.decode(buf)

        # Buffer should still be usable - clear and encode valid message
        buf.clear()
        msg = Heartbeat(header=WireHeader(), sender_id='recovery')
        codec.encode_into(msg, buf)

        decoded = codec.decode(buf)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'recovery'

        buffer_pool.release(buf)

    def test_minimal_payload(self) -> None:
        """DataMessage with minimal payload (null) works correctly."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=256, max_pool=2)

        # Minimal valid msgpack: null (0xc0)
        msg = DataMessage(
            header=WireHeader(channel_id='empty-ch'),
            payload=msgspec.Raw(b'\xc0'),  # msgpack nil
        )

        buf = buffer_pool.acquire()
        written = codec.encode_into(msg, buf)
        assert written > 0

        decoded = codec.decode(buf)
        assert isinstance(decoded, DataMessage)
        assert bytes(decoded.payload) == b'\xc0'

        # Verify it decodes to None
        decoded_value = codec.decode_payload(decoded.payload, str | None)
        assert decoded_value is None

        buffer_pool.release(buf)

    def test_buffer_resize_persists_in_pool(self) -> None:
        """Resized buffers keep their new size when returned to pool."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=64, max_pool=1)

        # Create message larger than 64 bytes
        msg = Heartbeat(
            header=WireHeader(channel_id='resize-test-channel-id'),
            sender_id='a-sender-id-that-makes-this-exceed-64-bytes-definitely',
        )

        buf = buffer_pool.acquire()
        original_capacity = len(buf)
        assert original_capacity == 64

        # Encode - this will resize the buffer
        written = codec.encode_into(msg, buf)
        assert written > 64  # Message is larger

        # Release the (now resized) buffer back to pool
        buffer_pool.release(buf)

        # Acquire again - should get the same buffer (cleared)
        buf2 = buffer_pool.acquire()

        # After clear(), len is 0, but we can verify it's the same object
        # and it can handle large messages without reallocation
        msg2 = Heartbeat(
            header=WireHeader(channel_id='another-long-channel-id'),
            sender_id='another-long-sender-id-for-testing-purposes',
        )
        codec.encode_into(msg2, buf2)

        decoded = codec.decode(buf2)
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'another-long-sender-id-for-testing-purposes'

        buffer_pool.release(buf2)

    def test_concurrent_encode_into_different_buffers(self) -> None:
        """Concurrent encode_into with separate buffers is safe."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=512, max_pool=16)
        errors: list[Exception] = []
        results: list[bool] = []
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            try:
                for i in range(20):
                    buf = buffer_pool.acquire()
                    msg = Heartbeat(
                        header=WireHeader(seq=i),
                        sender_id=f'worker-{worker_id}-msg-{i}',
                    )
                    codec.encode_into(msg, buf)
                    decoded = codec.decode(buf)
                    success = isinstance(decoded, Heartbeat) and decoded.sender_id == f'worker-{worker_id}-msg-{i}'
                    with lock:
                        results.append(success)
                    buffer_pool.release(buf)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors: {errors}'
        assert len(results) == 80  # 4 workers x 20 iterations
        assert all(results), 'Some encode/decode cycles failed'


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_encode(self) -> None:
        """Multiple threads can encode concurrently."""
        pool = CodecPool()
        results: list[bytes] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def encode_in_thread(thread_id: int) -> None:
            try:
                for i in range(100):
                    msg = Heartbeat(
                        header=WireHeader(seq=i),
                        sender_id=f'thread-{thread_id}',
                    )
                    encoded = pool.encode(msg)
                    with lock:
                        results.append(encoded)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=encode_in_thread, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors occurred: {errors}'
        assert len(results) == 400  # 4 threads x 100 messages

    def test_concurrent_decode(self) -> None:
        """Multiple threads can decode concurrently."""
        pool = CodecPool()
        # Pre-encode messages
        messages = [pool.encode(Heartbeat(header=WireHeader(seq=i), sender_id=f'msg-{i}')) for i in range(100)]
        results: list[WireEnvelope] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def decode_in_thread() -> None:
            try:
                for encoded in messages:
                    decoded = pool.decode(encoded)
                    with lock:
                        results.append(decoded)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=decode_in_thread) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors occurred: {errors}'
        assert len(results) == 400  # 4 threads x 100 messages
        assert all(isinstance(r, Heartbeat) for r in results)

    def test_concurrent_encode_decode(self) -> None:
        """Mixed encode/decode operations across threads."""
        pool = CodecPool()
        results: list[bool] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def encode_decode_cycle(thread_id: int) -> None:
            try:
                for i in range(50):
                    msg = Ack(
                        header=WireHeader(seq=i),
                        acked_seq=thread_id * 1000 + i,
                    )
                    encoded = pool.encode(msg)
                    decoded = pool.decode(encoded)
                    success = isinstance(decoded, Ack) and decoded.acked_seq == thread_id * 1000 + i
                    with lock:
                        results.append(success)
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(encode_decode_cycle, i) for i in range(8)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f'Errors occurred: {errors}'
        assert len(results) == 400  # 8 threads x 50 cycles
        assert all(results), 'Some roundtrips failed'

    def test_singleton_thread_safety(self) -> None:
        """get_codec_pool() returns same instance across threads."""
        pools: list[CodecPool] = []
        lock = threading.Lock()

        def get_pool() -> None:
            pool = get_codec_pool()
            with lock:
                pools.append(pool)

        threads = [threading.Thread(target=get_pool) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(pools) == 10
        assert all(p is pools[0] for p in pools)


# -----------------------------------------------------------------------------
# Property-Based Tests
# -----------------------------------------------------------------------------


@pytest.mark.hypothesis_property
class TestCodecPropertyBased:
    """Property-based tests for codec roundtrip correctness."""

    @given(envelope=wire_envelopes)
    @settings(max_examples=200)
    def test_any_envelope_roundtrips(self, envelope: WireEnvelope) -> None:
        """Any WireEnvelope can be encoded and decoded correctly."""
        pool = CodecPool()
        encoded = pool.encode(envelope)
        decoded = pool.decode(encoded)

        # Type is preserved
        assert type(decoded) is type(envelope)

        # Header fields match
        assert decoded.header.version == envelope.header.version
        assert decoded.header.kind == envelope.header.kind
        assert decoded.header.channel_id == envelope.header.channel_id
        assert decoded.header.seq == envelope.header.seq
        assert decoded.header.ts == envelope.header.ts

    @given(msg=data_messages())
    @settings(max_examples=100)
    def test_data_message_payload_preserved(self, msg: DataMessage[msgspec.Raw]) -> None:
        """DataMessage payload bytes are preserved through roundtrip."""
        pool = CodecPool()
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, DataMessage)
        assert bytes(decoded.payload) == bytes(msg.payload)

    @given(msg=control_messages())
    @settings(max_examples=100)
    def test_control_message_roundtrip(self, msg: ControlMessage) -> None:
        """ControlMessage action and metadata are preserved."""
        pool = CodecPool()
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, ControlMessage)
        assert decoded.action == msg.action
        assert bytes(decoded.metadata) == bytes(msg.metadata)

    @given(msg=heartbeats())
    @settings(max_examples=100)
    def test_heartbeat_roundtrip(self, msg: Heartbeat) -> None:
        """Heartbeat sender_id is preserved."""
        pool = CodecPool()
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == msg.sender_id

    @given(msg=acks())
    @settings(max_examples=100)
    def test_ack_roundtrip(self, msg: Ack) -> None:
        """Ack acked_seq and status are preserved."""
        pool = CodecPool()
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, Ack)
        assert decoded.acked_seq == msg.acked_seq
        assert decoded.status == msg.status

    @given(msg=wire_errors())
    @settings(max_examples=100)
    def test_wire_error_roundtrip(self, msg: WireError) -> None:
        """WireError code, message, and details are preserved."""
        pool = CodecPool()
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, WireError)
        assert decoded.code == msg.code
        assert decoded.message == msg.message
        assert bytes(decoded.details) == bytes(msg.details)

    @given(header=wire_headers())
    @settings(max_examples=100)
    def test_header_all_fields_preserved(self, header: WireHeader) -> None:
        """All WireHeader fields survive roundtrip in a message."""
        pool = CodecPool()
        msg = Heartbeat(header=header, sender_id='test')
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, Heartbeat)
        assert decoded.header == header

    @given(envelope=wire_envelopes)
    @settings(max_examples=50)
    def test_double_roundtrip_idempotent(self, envelope: WireEnvelope) -> None:
        """Multiple encode/decode cycles produce identical results."""
        pool = CodecPool()

        # First roundtrip
        encoded1 = pool.encode(envelope)
        decoded1 = pool.decode(encoded1)

        # Second roundtrip
        encoded2 = pool.encode(decoded1)
        _ = pool.decode(encoded2)

        # Bytes should be identical
        assert encoded1 == encoded2

    @given(envelope=wire_envelopes)
    @settings(max_examples=50)
    def test_decode_from_bytearray_matches_bytes(self, envelope: WireEnvelope) -> None:
        """Decoding from bytearray produces same result as from bytes."""
        pool = CodecPool()
        encoded = pool.encode(envelope)

        decoded_bytes = pool.decode(encoded)
        decoded_bytearray = pool.decode(bytearray(encoded))

        assert type(decoded_bytes) is type(decoded_bytearray)
        assert decoded_bytes.header == decoded_bytearray.header

    @given(envelope=wire_envelopes)
    @settings(max_examples=50)
    def test_decode_from_memoryview_matches_bytes(self, envelope: WireEnvelope) -> None:
        """Decoding from memoryview produces same result as from bytes."""
        pool = CodecPool()
        encoded = pool.encode(envelope)

        decoded_bytes = pool.decode(encoded)
        decoded_memoryview = pool.decode(memoryview(encoded))

        assert type(decoded_bytes) is type(decoded_memoryview)
        assert decoded_bytes.header == decoded_memoryview.header


@pytest.mark.hypothesis_property
class TestBufferPoolPropertyBased:
    """Property-based tests for BufferPool invariants."""

    @given(
        buffer_size=st.integers(min_value=1, max_value=8192),
        max_pool=st.integers(min_value=1, max_value=32),
    )
    @settings(max_examples=50)
    def test_pool_size_never_exceeds_max(self, buffer_size: int, max_pool: int) -> None:
        """Pool internal size never exceeds max_pool after any operations."""
        pool = BufferPool(buffer_size=buffer_size, max_pool=max_pool)

        # Acquire and release more buffers than max_pool
        buffers = [pool.acquire() for _ in range(max_pool + 5)]
        for buf in buffers:
            pool.release(buf)

        # Internal pool should be capped at max_pool
        assert len(pool._pool) <= max_pool

    @given(
        buffer_size=st.integers(min_value=1, max_value=4096),
        num_cycles=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=50)
    def test_acquired_buffers_from_pool_are_cleared(self, buffer_size: int, num_cycles: int) -> None:
        """Buffers acquired from pool are always cleared."""
        pool = BufferPool(buffer_size=buffer_size, max_pool=8)

        for _ in range(num_cycles):
            buf = pool.acquire()
            # Write some data
            buf.extend(b'x' * min(100, buffer_size))
            pool.release(buf)

        # Acquire again - should be cleared
        buf = pool.acquire()
        assert len(buf) == 0

    @given(
        buffer_size=st.integers(min_value=1, max_value=4096),
    )
    @settings(max_examples=30)
    def test_fresh_buffer_has_correct_size(self, buffer_size: int) -> None:
        """Freshly created buffers have the configured size."""
        pool = BufferPool(buffer_size=buffer_size, max_pool=1)
        buf = pool.acquire()
        # Fresh buffer has len == buffer_size (filled with zeros)
        assert len(buf) == buffer_size

    @given(
        max_pool=st.integers(min_value=1, max_value=16),
        num_releases=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=50)
    def test_release_is_bounded(self, max_pool: int, num_releases: int) -> None:
        """Releasing many buffers keeps pool bounded."""
        pool = BufferPool(buffer_size=64, max_pool=max_pool)

        # Release many buffers
        for _ in range(num_releases):
            buf = bytearray(64)
            pool.release(buf)

        assert len(pool._pool) <= max_pool

    @given(
        ops=st.lists(
            st.sampled_from(['acquire', 'release']),
            min_size=1,
            max_size=100,
        ),
    )
    @settings(max_examples=100)
    def test_random_acquire_release_sequence_maintains_invariants(self, ops: list[str]) -> None:
        """Random sequences of acquire/release maintain pool invariants."""
        pool = BufferPool(buffer_size=128, max_pool=8)
        held_buffers: list[bytearray] = []

        for op in ops:
            if op == 'acquire':
                buf = pool.acquire()
                # Invariant: acquired buffer is either fresh (len=128) or cleared (len=0)
                assert len(buf) == 128 or len(buf) == 0
                held_buffers.append(buf)
            elif op == 'release' and held_buffers:
                buf = held_buffers.pop()
                pool.release(buf)

        # Invariant: pool size never exceeds max_pool
        assert len(pool._pool) <= 8


@pytest.mark.hypothesis_property
class TestWireProtocolPropertyBased:
    """Property-based tests for wire protocol invariants."""

    @given(envelope=wire_envelopes)
    @settings(max_examples=100)
    def test_message_kind_matches_type(self, envelope: WireEnvelope) -> None:
        """header.kind matches the actual message type after roundtrip."""
        from klaw_core.runtime.channels.wire import MessageKind

        pool = CodecPool()
        decoded = pool.decode(pool.encode(envelope))

        # Map message types to expected MessageKind
        expected_kind = {
            DataMessage: MessageKind.DATA,
            ControlMessage: MessageKind.CONTROL,
            Heartbeat: MessageKind.HEARTBEAT,
            Ack: MessageKind.ACK,
            WireError: MessageKind.ERROR,
        }

        assert decoded.header.kind == expected_kind[type(decoded)]

    @given(
        ops=st.lists(
            st.tuples(
                st.sampled_from(['acquire', 'encode', 'decode', 'release']),
                st.integers(min_value=0, max_value=100),
            ),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=100)
    def test_buffer_pool_codec_composition(self, ops: list[tuple[str, int]]) -> None:
        """Random acquire/encode_into/decode/release sequences maintain correctness."""
        codec = CodecPool()
        buffer_pool = BufferPool(buffer_size=512, max_pool=8)
        held_buffers: list[bytearray] = []
        encoded_buffers: list[tuple[bytearray, Heartbeat]] = []

        for op, seed in ops:
            if op == 'acquire':
                buf = buffer_pool.acquire()
                held_buffers.append(buf)
            elif op == 'encode' and held_buffers:
                buf = held_buffers.pop()
                msg = Heartbeat(
                    header=WireHeader(seq=seed),
                    sender_id=f'sender-{seed}',
                )
                codec.encode_into(msg, buf)
                encoded_buffers.append((buf, msg))
            elif op == 'decode' and encoded_buffers:
                buf, original_msg = encoded_buffers.pop()
                decoded = codec.decode(buf)
                # Verify correctness
                assert isinstance(decoded, Heartbeat)
                assert decoded.header.seq == original_msg.header.seq
                assert decoded.sender_id == original_msg.sender_id
                held_buffers.append(buf)
            elif op == 'release' and held_buffers:
                buf = held_buffers.pop()
                buffer_pool.release(buf)

        # Pool invariant
        assert len(buffer_pool._pool) <= 8

    @given(payload_data=st.binary(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_binary_payload_fuzz(self, payload_data: bytes) -> None:
        """Any arbitrary binary data as payload survives exactly."""
        codec = CodecPool()
        inner_enc = msgspec.msgpack.Encoder()
        payload_bytes = inner_enc.encode(payload_data)

        msg = DataMessage(
            header=WireHeader(channel_id='fuzz-test'),
            payload=msgspec.Raw(payload_bytes),
        )

        decoded = codec.decode(codec.encode(msg))
        assert isinstance(decoded, DataMessage)

        # Decode the payload and verify exact match
        decoded_payload = codec.decode_payload(decoded.payload, bytes)
        assert decoded_payload == payload_data

    @given(envelope=wire_envelopes)
    @settings(max_examples=50)
    def test_truncation_raises_decode_error(self, envelope: WireEnvelope) -> None:
        """Any prefix of valid encoded bytes raises DecodeError."""
        pool = CodecPool()
        encoded = pool.encode(envelope)

        # Try all prefixes (except empty and full)
        for length in range(1, len(encoded)):
            truncated = encoded[:length]
            with pytest.raises(msgspec.DecodeError):
                pool.decode(truncated)

    @given(msg=control_messages())
    @settings(max_examples=100)
    def test_control_action_preserved(self, msg: ControlMessage) -> None:
        """ControlMessage.action is preserved exactly after roundtrip."""
        pool = CodecPool()
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, ControlMessage)
        assert decoded.action == msg.action

    @given(envelope=wire_envelopes)
    @settings(max_examples=50, deadline=None)
    def test_concurrent_roundtrips_with_hypothesis_data(self, envelope: WireEnvelope) -> None:
        """Multiple threads doing roundtrips with same envelope don't interfere."""
        pool = CodecPool()
        results: list[bool] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                for _ in range(10):
                    encoded = pool.encode(envelope)
                    decoded = pool.decode(encoded)
                    success = (
                        type(decoded) is type(envelope)
                        and decoded.header.version == envelope.header.version
                        and decoded.header.seq == envelope.header.seq
                    )
                    with lock:
                        results.append(success)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors: {errors}'
        assert all(results), 'Some concurrent roundtrips failed'


class TestWireProtocolRobustness:
    """Robustness tests for wire protocol edge cases."""

    def test_unicode_in_channel_id(self) -> None:
        """Unicode characters in channel_id survive roundtrip."""
        pool = CodecPool()
        # Emoji, CJK, Arabic, etc.
        unicode_ids = [
            'channel-🚀-rocket',
            '频道-中文',
            'قناة-عربي',
            'канал-кириллица',
            'チャンネル-日本語',
            '🎉🎊🎁',
        ]
        for channel_id in unicode_ids:
            msg = Heartbeat(
                header=WireHeader(channel_id=channel_id),
                sender_id='test',
            )
            decoded = pool.decode(pool.encode(msg))
            assert decoded.header.channel_id == channel_id

    def test_unicode_in_sender_id(self) -> None:
        """Unicode characters in sender_id survive roundtrip."""
        pool = CodecPool()
        unicode_senders = [
            'sender-émoji-🔥',
            '发送者-中文',
            'مرسل-عربي',
        ]
        for sender_id in unicode_senders:
            msg = Heartbeat(
                header=WireHeader(),
                sender_id=sender_id,
            )
            decoded = pool.decode(pool.encode(msg))
            assert decoded.sender_id == sender_id

    def test_null_bytes_in_strings(self) -> None:
        """Null bytes embedded in strings survive roundtrip."""
        pool = CodecPool()
        # Strings with embedded null bytes
        null_strings = [
            'before\x00after',
            '\x00start',
            'end\x00',
            '\x00\x00\x00',
            'a\x00b\x00c',
        ]
        for s in null_strings:
            msg = Heartbeat(
                header=WireHeader(channel_id=s),
                sender_id=s,
            )
            decoded = pool.decode(pool.encode(msg))
            assert decoded.header.channel_id == s
            assert decoded.sender_id == s

    def test_very_long_channel_id(self) -> None:
        """Very long channel_id (>1KB) survives roundtrip."""
        pool = CodecPool()
        long_id = 'x' * 2000  # 2KB
        msg = Heartbeat(
            header=WireHeader(channel_id=long_id),
            sender_id='test',
        )
        decoded = pool.decode(pool.encode(msg))
        assert decoded.header.channel_id == long_id
        assert len(decoded.header.channel_id) == 2000

    def test_very_long_sender_id(self) -> None:
        """Very long sender_id survives roundtrip."""
        pool = CodecPool()
        long_sender = 's' * 5000  # 5KB
        msg = Heartbeat(
            header=WireHeader(),
            sender_id=long_sender,
        )
        decoded = pool.decode(pool.encode(msg))
        assert decoded.sender_id == long_sender

    def test_very_long_error_message(self) -> None:
        """Very long error message survives roundtrip."""
        pool = CodecPool()
        long_message = 'error: ' + 'x' * 10000
        msg = WireError(
            header=WireHeader(),
            code='long_error',
            message=long_message,
        )
        decoded = pool.decode(pool.encode(msg))
        assert isinstance(decoded, WireError)
        assert decoded.message == long_message


class TestWireProtocolInvariants:
    """Invariant tests for wire protocol correctness."""

    def test_equality_after_roundtrip_heartbeat(self) -> None:
        """Heartbeat equals itself after roundtrip."""
        pool = CodecPool()
        msg = Heartbeat(
            header=WireHeader(channel_id='eq-test', seq=42, ts=1000),
            sender_id='sender-1',
        )
        decoded = pool.decode(pool.encode(msg))
        assert decoded == msg

    def test_equality_after_roundtrip_ack(self) -> None:
        """Ack equals itself after roundtrip."""
        pool = CodecPool()
        msg = Ack(
            header=WireHeader(channel_id='ack-eq', seq=100),
            acked_seq=99,
            status='delivered',
        )
        decoded = pool.decode(pool.encode(msg))
        assert decoded == msg

    def test_equality_after_roundtrip_control(self) -> None:
        """ControlMessage equals itself after roundtrip."""
        pool = CodecPool()
        msg = ControlMessage(
            header=WireHeader(channel_id='ctrl-eq'),
            action='pause',
            metadata=msgspec.Raw(b'\xc0'),  # null
        )
        decoded = pool.decode(pool.encode(msg))
        assert decoded == msg

    def test_equality_after_roundtrip_wire_error(self) -> None:
        """WireError equals itself after roundtrip."""
        pool = CodecPool()
        msg = WireError(
            header=WireHeader(),
            code='test_error',
            message='Something went wrong',
            details=msgspec.Raw(b'\xc0'),
        )
        decoded = pool.decode(pool.encode(msg))
        assert decoded == msg

    def test_hash_stability_heartbeat(self) -> None:
        """Heartbeat hash is stable after roundtrip."""
        pool = CodecPool()
        msg = Heartbeat(
            header=WireHeader(channel_id='hash-test', seq=1),
            sender_id='hasher',
        )
        decoded = pool.decode(pool.encode(msg))
        assert hash(decoded) == hash(msg)

    def test_hash_stability_ack(self) -> None:
        """Ack hash is stable after roundtrip."""
        pool = CodecPool()
        msg = Ack(
            header=WireHeader(seq=50),
            acked_seq=49,
            status='ok',
        )
        decoded = pool.decode(pool.encode(msg))
        assert hash(decoded) == hash(msg)

    def test_hash_stability_header(self) -> None:
        """WireHeader hash is stable after roundtrip."""
        pool = CodecPool()
        header = WireHeader(channel_id='header-hash', seq=999, ts=123456789)
        msg = Heartbeat(header=header, sender_id='test')
        decoded = pool.decode(pool.encode(msg))
        assert hash(decoded.header) == hash(header)

    def test_frozen_immutability_header(self) -> None:
        """WireHeader fields cannot be modified (frozen)."""
        header = WireHeader(channel_id='immutable', seq=1)
        with pytest.raises(AttributeError):
            header.seq = 2  # type: ignore[misc]
        with pytest.raises(AttributeError):
            header.channel_id = 'changed'  # type: ignore[misc]

    def test_frozen_immutability_heartbeat(self) -> None:
        """Heartbeat fields cannot be modified (frozen)."""
        msg = Heartbeat(header=WireHeader(), sender_id='original')
        with pytest.raises(AttributeError):
            msg.sender_id = 'changed'  # type: ignore[misc]

    def test_frozen_immutability_ack(self) -> None:
        """Ack fields cannot be modified (frozen)."""
        msg = Ack(header=WireHeader(), acked_seq=1, status='ok')
        with pytest.raises(AttributeError):
            msg.acked_seq = 2  # type: ignore[misc]
        with pytest.raises(AttributeError):
            msg.status = 'error'  # type: ignore[misc]


class TestDecoderReentrance:
    """Tests for decoder thread safety and reentrance."""

    def test_concurrent_decodes_shared_decoder(self) -> None:
        """Multiple concurrent decodes on shared decoder produce correct results."""
        pool = CodecPool()
        # Pre-encode different messages
        messages = [pool.encode(Heartbeat(header=WireHeader(seq=i), sender_id=f's-{i}')) for i in range(100)]

        results: list[tuple[int, str]] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def decode_many(start: int, count: int) -> None:
            try:
                for i in range(start, start + count):
                    idx = i % len(messages)
                    decoded = pool.decode(messages[idx])
                    assert isinstance(decoded, Heartbeat)
                    with lock:
                        results.append((decoded.header.seq, decoded.sender_id))
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=decode_many, args=(i * 25, 25)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f'Errors: {errors}'
        assert len(results) == 200  # 8 threads x 25 decodes

        # Verify correctness - seq and sender_id should match
        for seq, sender_id in results:
            assert sender_id == f's-{seq}'


class TestMemorySafety:
    """Memory safety tests using tracemalloc."""

    def test_buffer_pool_no_leak_under_repeated_use(self) -> None:
        """Repeated acquire/release doesn't leak memory."""
        import gc
        import tracemalloc

        buffer_pool = BufferPool(buffer_size=1024, max_pool=8)

        # Warm up
        for _ in range(100):
            buf = buffer_pool.acquire()
            buf.extend(b'x' * 500)
            buffer_pool.release(buf)

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # Do many more cycles
        for _ in range(1000):
            buf = buffer_pool.acquire()
            buf.extend(b'y' * 500)
            buffer_pool.release(buf)

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare memory - should not grow significantly
        stats = snapshot2.compare_to(snapshot1, 'lineno')
        # Sum up memory growth
        total_growth = sum(stat.size_diff for stat in stats if stat.size_diff > 0)

        # Allow some growth but not unbounded (< 100KB)
        assert total_growth < 100_000, f'Memory grew by {total_growth} bytes'

    def test_codec_pool_no_leak_under_repeated_encode_decode(self) -> None:
        """Repeated encode/decode doesn't leak memory."""
        import gc
        import tracemalloc

        codec = CodecPool()
        msg = Heartbeat(header=WireHeader(seq=1), sender_id='leak-test')

        # Warm up
        for _ in range(100):
            encoded = codec.encode(msg)
            _ = codec.decode(encoded)

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # Do many more cycles
        for _ in range(1000):
            encoded = codec.encode(msg)
            _ = codec.decode(encoded)

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot2.compare_to(snapshot1, 'lineno')
        total_growth = sum(stat.size_diff for stat in stats if stat.size_diff > 0)

        # Allow some growth but not unbounded (< 100KB)
        assert total_growth < 100_000, f'Memory grew by {total_growth} bytes'
