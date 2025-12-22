"""Codec pool infrastructure for wire protocol encoding/decoding.

This module provides thread-safe, high-performance encoding and decoding
of wire protocol messages using msgspec's MessagePack format.

Key components:
    - CodecPool: Thread-local encoder reuse with shared decoder
    - get_codec_pool(): Module-level singleton access
    - encode/decode: Convenience functions for quick usage

Thread Safety:
    - Encoders are NOT thread-safe → use thread-local instances
    - Decoders ARE thread-safe (reentrant) → can share
    - CodecPool handles this automatically

Usage:
    >>> from klaw_core.runtime.channels.codec import get_codec_pool, encode, decode
    >>> from klaw_core.runtime.channels.wire import DataMessage, WireHeader
    >>> import msgspec
    >>>
    >>> # Via pool (recommended for repeated use)
    >>> pool = get_codec_pool()
    >>> header = WireHeader(channel_id="ch-1", seq=1)
    >>> msg = DataMessage(header=header, payload=msgspec.Raw(b'"hello"'))
    >>> encoded = pool.encode(msg)
    >>> decoded = pool.decode(encoded)
    >>>
    >>> # Via convenience functions
    >>> encoded = encode(msg)
    >>> decoded = decode(encoded)

See Also:
    - wire.py: Wire protocol message types
    - PRD §1.2: Encoder/Decoder Pool specification
"""

from __future__ import annotations

import threading
from typing import TypeVar

import msgspec

from klaw_core.runtime.channels.wire import WireEnvelope

__all__ = [
    'BufferPool',
    'CodecPool',
    'decode',
    'encode',
    'get_buffer_pool',
    'get_codec_pool',
]

T = TypeVar('T')


class CodecPool:
    """Thread-safe pool for wire protocol encoding and decoding.

    Uses thread-local storage for encoders (not thread-safe) and a shared
    decoder (thread-safe/reentrant). This avoids encoder creation overhead
    in hot paths while maintaining thread safety.

    Example:
        >>> pool = CodecPool()
        >>> header = WireHeader(channel_id="test")
        >>> msg = DataMessage(header=header, payload=msgspec.Raw(b"{}"))
        >>> encoded = pool.encode(msg)
        >>> decoded = pool.decode(encoded)
        >>> assert isinstance(decoded, DataMessage)

    Attributes:
        _local: Thread-local storage for per-thread encoders.
        _envelope_decoder: Shared decoder for WireEnvelope (thread-safe).
    """

    __slots__ = ('_envelope_decoder', '_local')

    def __init__(self) -> None:
        """Initialize the codec pool with thread-local encoder storage."""
        self._local = threading.local()
        self._envelope_decoder: msgspec.msgpack.Decoder[WireEnvelope] = msgspec.msgpack.Decoder(WireEnvelope)

    @property
    def _encoder(self) -> msgspec.msgpack.Encoder:
        """Get or create the thread-local encoder.

        Returns:
            The msgpack encoder for this thread.
        """
        encoder = getattr(self._local, 'encoder', None)
        if encoder is None:
            encoder = msgspec.msgpack.Encoder()
            self._local.encoder = encoder
        return encoder

    def encode(self, msg: WireEnvelope) -> bytes:
        """Encode a wire envelope to MessagePack bytes.

        Args:
            msg: The wire envelope to encode.

        Returns:
            MessagePack-encoded bytes.

        Example:
            >>> pool = CodecPool()
            >>> msg = Heartbeat(header=WireHeader(), sender_id="node-1")
            >>> data = pool.encode(msg)
            >>> isinstance(data, bytes)
            True
        """
        return self._encoder.encode(msg)

    def encode_into(self, msg: WireEnvelope, buf: bytearray, offset: int = 0) -> int:
        """Encode a wire envelope directly into a pre-allocated buffer.

        This method enables zero-allocation encoding by writing directly
        to a reusable buffer (e.g., from BufferPool).

        Note: The buffer is truncated to the end of the serialized message.
        The returned value is the new length of the buffer (from offset).

        Args:
            msg: The wire envelope to encode.
            buf: Target buffer to write into (will be truncated).
            offset: Starting position in the buffer.

        Returns:
            Number of bytes written (new buffer length minus offset).

        Example:
            >>> pool = CodecPool()
            >>> buf = bytearray(4096)
            >>> msg = Ack(header=WireHeader(), acked_seq=42)
            >>> written = pool.encode_into(msg, buf)
            >>> decoded = pool.decode(buf)  # buf is now truncated
        """
        self._encoder.encode_into(msg, buf, offset)
        return len(buf) - offset

    def decode(self, buf: bytes | bytearray | memoryview) -> WireEnvelope:
        """Decode MessagePack bytes to a wire envelope.

        Uses the shared decoder which is thread-safe.

        Args:
            buf: MessagePack-encoded bytes.

        Returns:
            The decoded WireEnvelope variant.

        Raises:
            msgspec.DecodeError: If the buffer is malformed.
            msgspec.ValidationError: If the data doesn't match WireEnvelope.

        Example:
            >>> pool = CodecPool()
            >>> msg = Heartbeat(header=WireHeader(), sender_id="node-1")
            >>> decoded = pool.decode(pool.encode(msg))
            >>> isinstance(decoded, Heartbeat)
            True
        """
        return self._envelope_decoder.decode(buf)

    def decode_payload(self, raw: msgspec.Raw, payload_type: type[T]) -> T:
        """Decode a raw payload to a specific type.

        When a DataMessage is decoded, its payload is `msgspec.Raw` to
        defer type resolution. Use this method to decode the payload to
        the actual expected type.

        Args:
            raw: The raw payload from DataMessage.payload.
            payload_type: The expected type of the payload.

        Returns:
            The decoded payload of type T.

        Raises:
            msgspec.DecodeError: If the raw bytes are malformed.
            msgspec.ValidationError: If the data doesn't match payload_type.

        Example:
            >>> pool = CodecPool()
            >>> # Assume we received a DataMessage with JSON payload
            >>> match decoded:
            ...     case DataMessage(payload=raw):
            ...         actual = pool.decode_payload(raw, dict[str, int])
        """
        decoder: msgspec.msgpack.Decoder[T] = msgspec.msgpack.Decoder(payload_type)
        return decoder.decode(raw)


class BufferPool:
    """Thread-safe pool of reusable bytearray buffers for zero-allocation encoding.

    Provides buffer reuse to avoid allocation overhead in high-throughput
    scenarios. Use with `CodecPool.encode_into()` to write directly to
    pre-allocated buffers without creating new byte objects.

    The pool maintains a fixed maximum number of buffers. When the pool is
    exhausted, `acquire()` creates a new buffer. When the pool is full,
    `release()` discards the buffer.

    Thread Safety:
        All operations are protected by a lock for safe concurrent access.

    Example:
        >>> pool = BufferPool(buffer_size=4096, max_pool=32)
        >>> buf = pool.acquire()
        >>> # Use buf with encode_into()...
        >>> codec.encode_into(msg, buf)
        >>> # Process the encoded data...
        >>> pool.release(buf)  # Return to pool for reuse

    Attributes:
        _pool: List of available buffers.
        _lock: Threading lock for safe concurrent access.
        _buffer_size: Size of new buffers created by acquire().
        _max_pool: Maximum number of buffers to keep in the pool.
    """

    __slots__ = ('_buffer_size', '_lock', '_max_pool', '_pool')

    def __init__(self, buffer_size: int = 4096, max_pool: int = 64) -> None:
        """Initialize the buffer pool.

        Args:
            buffer_size: Size in bytes of each buffer. Default 4096 (4KB).
            max_pool: Maximum buffers to retain. Default 64.
        """
        self._pool: list[bytearray] = []
        self._lock = threading.Lock()
        self._buffer_size = buffer_size
        self._max_pool = max_pool

    def acquire(self) -> bytearray:
        """Acquire a buffer from the pool or create a new one.

        If a buffer is available in the pool, it is returned after being
        cleared. Otherwise, a new buffer of `_buffer_size` is created.

        Returns:
            A cleared bytearray ready for use.

        Example:
            >>> pool = BufferPool()
            >>> buf = pool.acquire()
            >>> len(buf)
            0
        """
        with self._lock:
            if self._pool:
                buf = self._pool.pop()
                buf.clear()
                return buf
        return bytearray(self._buffer_size)

    def release(self, buf: bytearray) -> None:
        """Return a buffer to the pool for reuse.

        If the pool is at capacity (`_max_pool`), the buffer is discarded.
        The buffer is NOT cleared here; clearing happens on acquire().

        Args:
            buf: The buffer to return to the pool.

        Example:
            >>> pool = BufferPool(max_pool=2)
            >>> buf1 = pool.acquire()
            >>> buf2 = pool.acquire()
            >>> pool.release(buf1)
            >>> pool.release(buf2)
            >>> buf3 = bytearray(100)
            >>> pool.release(buf3)  # Discarded if pool is full
        """
        with self._lock:
            if len(self._pool) < self._max_pool:
                self._pool.append(buf)


# -----------------------------------------------------------------------------
# Module-Level Singleton
# -----------------------------------------------------------------------------

_codec_pool: CodecPool | None = None
_codec_pool_lock = threading.Lock()


def get_codec_pool() -> CodecPool:
    """Get the global codec pool singleton.

    Uses double-checked locking for thread-safe lazy initialization.

    Returns:
        The shared CodecPool instance.

    Example:
        >>> pool = get_codec_pool()
        >>> same_pool = get_codec_pool()
        >>> pool is same_pool
        True
    """
    global _codec_pool  # noqa: PLW0603
    if _codec_pool is None:
        with _codec_pool_lock:
            if _codec_pool is None:
                _codec_pool = CodecPool()
    return _codec_pool


_buffer_pool: BufferPool | None = None
_buffer_pool_lock = threading.Lock()


def get_buffer_pool() -> BufferPool:
    """Get the global buffer pool singleton.

    Uses double-checked locking for thread-safe lazy initialization.

    Returns:
        The shared BufferPool instance.

    Example:
        >>> pool = get_buffer_pool()
        >>> same_pool = get_buffer_pool()
        >>> pool is same_pool
        True
    """
    global _buffer_pool  # noqa: PLW0603
    if _buffer_pool is None:
        with _buffer_pool_lock:
            if _buffer_pool is None:
                _buffer_pool = BufferPool()
    return _buffer_pool


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


def encode(msg: WireEnvelope) -> bytes:
    """Encode a wire envelope to MessagePack bytes.

    Convenience function that uses the global codec pool.

    Args:
        msg: The wire envelope to encode.

    Returns:
        MessagePack-encoded bytes.

    Example:
        >>> from klaw_core.runtime.channels.wire import Heartbeat, WireHeader
        >>> msg = Heartbeat(header=WireHeader(), sender_id="node-1")
        >>> data = encode(msg)
        >>> isinstance(data, bytes)
        True
    """
    return get_codec_pool().encode(msg)


def decode(buf: bytes | bytearray | memoryview) -> WireEnvelope:
    """Decode MessagePack bytes to a wire envelope.

    Convenience function that uses the global codec pool.

    Args:
        buf: MessagePack-encoded bytes.

    Returns:
        The decoded WireEnvelope variant.

    Example:
        >>> from klaw_core.runtime.channels.wire import Heartbeat, WireHeader
        >>> msg = Heartbeat(header=WireHeader(), sender_id="node-1")
        >>> decoded = decode(encode(msg))
        >>> isinstance(decoded, Heartbeat)
        True
    """
    return get_codec_pool().decode(buf)
