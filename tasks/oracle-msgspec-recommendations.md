# klaw-core msgspec Recommendations

> **Goal:** Battery-included, scale-ready, future-proofed orchestrator foundation

______________________________________________________________________

## Executive Summary

| Priority     | Category        | Items                                                             |
| ------------ | --------------- | ----------------------------------------------------------------- |
| **Critical** | Wire Protocol   | Tagged envelopes, versioned schemas, MessagePack canonical format |
| **Critical** | Performance     | Encoder/decoder pools, `array_like=True`, buffer reuse            |
| **High**     | Typing          | Variance on protocols, generic actors, ParamSpec decorators       |
| **High**     | Validation      | Constraint types, cached converters, strict boundaries            |
| **Medium**   | Future-Proofing | Schema registry, view structs, migration patterns                 |

______________________________________________________________________

## 1. Wire Protocol Foundation

### 1.1 Canonical Channel Envelope (Critical)

Create `klaw_core/runtime/channels/wire.py`:

```python
"""Canonical wire protocol for all channel communication.

All messages crossing process/network boundaries MUST use these types.
MessagePack is the canonical encoding format.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Annotated, Generic, TypeVar

import msgspec

T = TypeVar('T')

# Schema version for forward/backward compatibility
WIRE_SCHEMA_VERSION: int = 1


class MessageKind(IntEnum):
    """Wire message discriminator - use int for compact encoding."""

    DATA = 1
    CONTROL = 2
    HEARTBEAT = 3
    ACK = 4
    ERROR = 5


class WireHeader(msgspec.Struct, array_like=True, frozen=True, gc=False):
    """Fixed header for all wire messages.

    Layout: [version, kind, channel_id, seq, ts]
    """

    version: int = WIRE_SCHEMA_VERSION
    kind: MessageKind = MessageKind.DATA
    channel_id: str = ''
    seq: int = 0
    ts: int = 0  # Unix timestamp millis


class DataMessage(msgspec.Struct, Generic[T], tag=1, array_like=True, frozen=True, gc=False):
    """Data plane message carrying user payload."""

    header: WireHeader
    payload: T


class ControlMessage(msgspec.Struct, tag=2, array_like=True, frozen=True, gc=False):
    """Control plane message for channel lifecycle."""

    header: WireHeader
    action: str  # "create", "close", "resize", "pause", "resume"
    metadata: msgspec.Raw = msgspec.Raw(b'')  # Deferred decoding


class Heartbeat(msgspec.Struct, tag=3, array_like=True, frozen=True, gc=False):
    """Liveness probe - minimal payload."""

    header: WireHeader
    sender_id: str = ''


class Ack(msgspec.Struct, tag=4, array_like=True, frozen=True, gc=False):
    """Acknowledgment for reliable delivery."""

    header: WireHeader
    acked_seq: int = 0
    status: str = 'ok'


class WireError(msgspec.Struct, tag=5, array_like=True, frozen=True, gc=False):
    """Error response on wire."""

    header: WireHeader
    code: str = ''
    message: str = ''
    details: msgspec.Raw = msgspec.Raw(b'')


# The canonical envelope - all wire traffic
WireEnvelope = DataMessage[msgspec.Raw] | ControlMessage | Heartbeat | Ack | WireError
```

**Why:**

- `array_like=True` → ~2x decode speedup, compact wire format
- `tag=N` (int) → faster than string tags, cross-language friendly
- `msgspec.Raw` → zero-copy payload, decode only when needed
- `WireHeader` → consistent routing/tracing across all message types
- `version` field → schema evolution without breaking changes

**Ref:** Guide §6.2, §6.3, §4.1

______________________________________________________________________

### 1.2 Encoder/Decoder Pool (Critical)

Create `klaw_core/runtime/channels/codec.py`:

```python
"""High-performance codec pool for wire encoding/decoding.

Single source of truth for all serialization in klaw-core.
Thread-safe, process-local instances.
"""

from __future__ import annotations

import threading
from typing import TypeVar

import msgspec

from klaw_core.runtime.channels.wire import (
    ControlMessage,
    DataMessage,
    WireEnvelope,
    WireError,
)

T = TypeVar('T')


class CodecPool:
    """Per-process codec pool with thread-local encoders.

    Usage:
        pool = get_codec_pool()
        encoded = pool.encode(msg)
        decoded = pool.decode(buf)
    """

    __slots__ = ('_local', '_envelope_decoder', '_lock')

    def __init__(self) -> None:
        self._local = threading.local()
        self._envelope_decoder = msgspec.msgpack.Decoder(WireEnvelope)
        self._lock = threading.Lock()

    @property
    def _encoder(self) -> msgspec.msgpack.Encoder:
        """Thread-local encoder instance."""
        if not hasattr(self._local, 'encoder'):
            self._local.encoder = msgspec.msgpack.Encoder()
        return self._local.encoder

    def encode(self, msg: WireEnvelope) -> bytes:
        """Encode envelope to MessagePack bytes."""
        return self._encoder.encode(msg)

    def encode_into(self, msg: WireEnvelope, buf: bytearray, offset: int = 0) -> int:
        """Encode into pre-allocated buffer. Returns bytes written."""
        return self._encoder.encode_into(msg, buf, offset)

    def decode(self, buf: bytes | bytearray | memoryview) -> WireEnvelope:
        """Decode MessagePack bytes to envelope."""
        return self._envelope_decoder.decode(buf)

    def decode_payload[T](self, raw: msgspec.Raw, payload_type: type[T]) -> T:
        """Decode a Raw payload to concrete type."""
        decoder = msgspec.msgpack.Decoder(payload_type)
        return decoder.decode(raw)


# Module-level singleton
_codec_pool: CodecPool | None = None
_pool_lock = threading.Lock()


def get_codec_pool() -> CodecPool:
    """Get the process-global codec pool."""
    global _codec_pool
    if _codec_pool is None:
        with _pool_lock:
            if _codec_pool is None:
                _codec_pool = CodecPool()
    return _codec_pool


# Convenience functions
def encode(msg: WireEnvelope) -> bytes:
    """Encode wire envelope."""
    return get_codec_pool().encode(msg)


def decode(buf: bytes | bytearray | memoryview) -> WireEnvelope:
    """Decode wire envelope."""
    return get_codec_pool().decode(buf)
```

**Why:**

- Thread-local encoders avoid contention
- Single decoder for envelope (type already captured in tag)
- `encode_into` for zero-allocation hot paths
- Lazy init for fast startup

**Ref:** Guide §3.1, §6.1

______________________________________________________________________

### 1.3 Buffer Pool for High-Throughput (Critical)

Add to `codec.py`:

```python
class BufferPool:
    """Reusable buffer pool for zero-allocation encoding.

    For extreme throughput paths (>100k msg/sec).
    """

    __slots__ = ('_pool', '_lock', '_buffer_size', '_max_pool')

    def __init__(self, buffer_size: int = 4096, max_pool: int = 64) -> None:
        self._pool: list[bytearray] = []
        self._lock = threading.Lock()
        self._buffer_size = buffer_size
        self._max_pool = max_pool

    def acquire(self) -> bytearray:
        """Get a buffer from pool or create new."""
        with self._lock:
            if self._pool:
                buf = self._pool.pop()
                buf.clear()
                return buf
        return bytearray(self._buffer_size)

    def release(self, buf: bytearray) -> None:
        """Return buffer to pool."""
        with self._lock:
            if len(self._pool) < self._max_pool:
                self._pool.append(buf)

    def encode_with_buffer(self, msg: WireEnvelope, codec: CodecPool) -> tuple[memoryview, bytearray]:
        """Encode using pooled buffer. Caller must release buffer."""
        buf = self.acquire()
        try:
            length = codec.encode_into(msg, buf, offset=4)
            # Prepend length for framing
            buf[:4] = length.to_bytes(4, 'big')
            return memoryview(buf)[: 4 + length], buf
        except Exception:
            self.release(buf)
            raise


# Global buffer pool for hot paths
_buffer_pool: BufferPool | None = None


def get_buffer_pool() -> BufferPool:
    """Get process-global buffer pool."""
    global _buffer_pool
    if _buffer_pool is None:
        with _pool_lock:
            if _buffer_pool is None:
                _buffer_pool = BufferPool()
    return _buffer_pool
```

**Ref:** Guide §3.6

______________________________________________________________________

## 2. Constraint Types (High)

Create `klaw_core/runtime/types.py`:

```python
"""Constrained types for validation at decode boundaries.

These types are validated by msgspec during decode from external sources
(config files, API requests, wire messages). Internal struct creation
does NOT validate - rely on static typing there.
"""

from typing import Annotated

import msgspec

# --- Numeric constraints ---

PositiveInt = Annotated[int, msgspec.Meta(gt=0, description='Integer > 0')]
NonNegativeInt = Annotated[int, msgspec.Meta(ge=0, description='Integer >= 0')]
PositiveFloat = Annotated[float, msgspec.Meta(gt=0.0, description='Float > 0')]
Percentage = Annotated[float, msgspec.Meta(ge=0.0, le=100.0, description='0-100%')]
Ratio = Annotated[float, msgspec.Meta(ge=0.0, le=1.0, description='0.0-1.0')]

# --- Capacity/size constraints ---

ChannelCapacity = Annotated[int, msgspec.Meta(ge=1, le=10_000_000, description='Channel buffer size')]
BatchSize = Annotated[int, msgspec.Meta(ge=1, le=100_000, description='Batch operation size')]
TimeoutSeconds = Annotated[float, msgspec.Meta(gt=0.0, le=86400.0, description='Timeout 0-24h')]
ConcurrencyLimit = Annotated[int, msgspec.Meta(ge=1, le=10_000, description='Max concurrent ops')]

# --- String constraints ---

Identifier = Annotated[
    str,
    msgspec.Meta(min_length=1, max_length=256, pattern=r'^[a-zA-Z_][a-zA-Z0-9_\-\.]*$', description='Valid identifier'),
]

ChannelName = Annotated[
    str,
    msgspec.Meta(
        min_length=1,
        max_length=512,
        pattern=r'^[a-zA-Z_][a-zA-Z0-9_\-\./]*$',
        description='Channel name with optional namespace',
    ),
]

NodeId = Annotated[str, msgspec.Meta(min_length=1, max_length=128, description='Node/worker identifier')]

# --- Version constraints ---

SchemaVersion = Annotated[int, msgspec.Meta(ge=1, le=1000, description='Wire schema version')]
```

**Usage in structs:**

```python
from klaw_core.runtime.types import ChannelCapacity, TimeoutSeconds, Identifier


class ChannelConfig(msgspec.Struct, frozen=True, gc=False, omit_defaults=True):
    name: Identifier
    capacity: ChannelCapacity = 10000
    timeout: TimeoutSeconds = 30.0
```

**Ref:** Guide §4.2

______________________________________________________________________

## 3. Typed Protocols with Variance (High)

Update `protocols.py`:

```python
"""Channel protocols with proper variance for composability."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, TypeVar

from klaw_core.result import Result
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = ['Receiver', 'Sender', 'ReferenceReceiver', 'ReferenceSender']

# Variance declarations
T_co = TypeVar('T_co', covariant=True)  # Receiver produces T
T_contra = TypeVar('T_contra', contravariant=True)  # Sender consumes T


class Sender(Protocol[T_contra]):
    """Protocol for sending values into a channel.

    Contravariant: Sender[Animal] can be used where Sender[Dog] is expected.
    """

    @abstractmethod
    async def send(self, value: T_contra) -> None:
        """Send a value, blocking if at capacity."""
        ...

    @abstractmethod
    async def try_send(self, value: T_contra) -> Result[None, ChannelFull | ChannelClosed]:
        """Send without blocking."""
        ...

    @abstractmethod
    def clone(self) -> Sender[T_contra]:
        """Clone for multi-producer use."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close this sender."""
        ...


class Receiver(Protocol[T_co]):
    """Protocol for receiving values from a channel.

    Covariant: Receiver[Dog] can be used where Receiver[Animal] is expected.
    """

    @abstractmethod
    async def recv(self) -> T_co:
        """Receive next value, blocking if empty."""
        ...

    @abstractmethod
    async def try_recv(self) -> Result[T_co, ChannelEmpty | ChannelClosed]:
        """Receive without blocking."""
        ...

    @abstractmethod
    def clone(self) -> Receiver[T_co]:
        """Clone for multi-consumer use."""
        ...

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[T_co]:
        """Async iteration."""
        ...

    @abstractmethod
    async def __anext__(self) -> T_co:
        """Next for async iteration."""
        ...
```

**Ref:** Guide §2.1

______________________________________________________________________

## 4. Generic Ray Actor (High)

Update `actor.py`:

```python
"""Ray channel actor with generic typing and cached validation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

import msgspec
import ray

from klaw_core.runtime.channels.ray.constants import BatchResult, ReaderInfo, SingleResult
from klaw_core.runtime.types import ChannelCapacity

T = TypeVar('T')


class _ChannelActorState(msgspec.Struct):
    """Mutable internal state - GC tracked for safety."""

    capacity: int | None
    unbounded: bool
    value_type: Any = None
    sender_count: int = 0
    receiver_count: int = 0
    senders_closed: bool = False
    receivers_closed: bool = False
    created_at: datetime = msgspec.UNSET
    high_watermark: int = 0
    total_sent: int = 0
    total_received: int = 0

    def __post_init__(self) -> None:
        if self.created_at is msgspec.UNSET:
            self.created_at = datetime.now(timezone.utc)


class _TypeValidator:
    """Cached type validator using msgspec.convert."""

    __slots__ = ('_value_type', '_convert_fn')

    def __init__(self, value_type: type[Any] | None) -> None:
        self._value_type = value_type
        if value_type is not None:
            # Pre-compile the converter
            self._convert_fn = lambda item: msgspec.convert(item, type=value_type)
        else:
            self._convert_fn = None

    def validate(self, item: Any) -> bool:
        """Validate item against type. Returns True if valid or no type set."""
        if self._convert_fn is None:
            return True
        try:
            self._convert_fn(item)
            return True
        except (msgspec.ValidationError, TypeError):
            return False


@ray.remote(max_restarts=4, max_task_retries=-1, max_concurrency=1000)
class RayChannelActor(Generic[T]):
    """Generic Ray channel actor with type-safe operations.

    Type parameter T is for documentation and client-side typing.
    Runtime validation uses value_type if provided.
    """

    def __init__(
        self,
        capacity: ChannelCapacity | None = None,
        unbounded: bool = False,
        value_type: type[T] | None = None,
    ) -> None:
        self._state = _ChannelActorState(
            capacity=capacity if not unbounded else None,
            unbounded=unbounded,
            value_type=value_type,
        )
        self._validator = _TypeValidator(value_type)

        queue_size = 0 if unbounded or capacity is None else capacity
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=queue_size)
        self._readers: dict[str, ReaderInfo] = {}

    async def put(self, item: T, timeout: float | None = None) -> str:
        """Put item with optional timeout. Returns status code."""
        if self._state.senders_closed or self._state.receivers_closed:
            return 'closed'
        if not self._validator.validate(item):
            return 'type_error'

        try:
            if timeout is not None:
                await asyncio.wait_for(self._queue.put(item), timeout=timeout)
            else:
                await self._queue.put(item)

            self._state.total_sent += 1
            self._update_watermark()
            return 'ok'
        except asyncio.TimeoutError:
            return 'full'

    async def get(self, timeout: float | None = None, reader_id: str | None = None) -> SingleResult[T]:
        """Get item with optional timeout. Returns SingleResult."""
        if self._state.senders_closed and self._queue.empty():
            return SingleResult(status='closed')

        try:
            if timeout is not None:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                item = await self._queue.get()

            self._state.total_received += 1
            self._update_reader_stats(reader_id)
            return SingleResult(status='ok', value=item)
        except asyncio.TimeoutError:
            return SingleResult(status='empty')

    async def get_batch(
        self,
        max_items: int,
        timeout: float | None = None,
        reader_id: str | None = None,
    ) -> BatchResult[T]:
        """Get up to max_items. Returns BatchResult."""
        if self._state.senders_closed and self._queue.empty():
            return BatchResult(status='closed')

        collected: list[T] = []
        deadline = None
        if timeout is not None:
            import time

            deadline = time.monotonic() + timeout

        while len(collected) < max_items:
            if self._queue.empty():
                if collected:
                    break
                # Wait for at least one item
                remaining = None
                if deadline is not None:
                    import time

                    remaining = max(0, deadline - time.monotonic())
                try:
                    if remaining is not None:
                        item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                    else:
                        item = await self._queue.get()
                    collected.append(item)
                except asyncio.TimeoutError:
                    break
            else:
                try:
                    collected.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

        if collected:
            self._state.total_received += len(collected)
            self._update_reader_stats(reader_id, count=len(collected))
            return BatchResult(status='ok', items=tuple(collected))
        return BatchResult(status='empty')

    def _update_watermark(self) -> None:
        current = self._queue.qsize()
        if current > self._state.high_watermark:
            self._state.high_watermark = current

    def _update_reader_stats(self, reader_id: str | None, count: int = 1) -> None:
        if reader_id and reader_id in self._readers:
            old = self._readers[reader_id]
            self._readers[reader_id] = ReaderInfo(
                reader_id=old.reader_id,
                node_id=old.node_id,
                registered_at=old.registered_at,
                last_seen_at=datetime.now(timezone.utc),
                total_received=old.total_received + count,
            )

    # ... rest of methods unchanged ...
```

**Ref:** Guide §2.4, §3.9

______________________________________________________________________

## 5. Schema Registry for Evolution (Medium)

Create `klaw_core/runtime/schema.py`:

```python
"""Schema registry for wire format evolution.

Enables:
- Version negotiation between workers
- Backward/forward compatible changes
- Schema documentation and validation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import msgspec


@dataclass(frozen=True, slots=True)
class SchemaInfo:
    """Metadata about a registered schema."""

    name: str
    version: int
    struct_type: type
    json_schema: dict[str, Any]


class SchemaRegistry:
    """Registry of versioned wire schemas.

    Usage:
        registry = SchemaRegistry()
        registry.register(DataMessage, version=1)
        registry.register(DataMessageV2, version=2)

        # Get schema for version
        schema = registry.get("DataMessage", version=1)
    """

    __slots__ = ('_schemas',)

    def __init__(self) -> None:
        self._schemas: dict[tuple[str, int], SchemaInfo] = {}

    def register(
        self,
        struct_type: type,
        *,
        version: int,
        name: str | None = None,
    ) -> None:
        """Register a schema version."""
        schema_name = name or struct_type.__name__
        json_schema = msgspec.json.schema(struct_type)

        info = SchemaInfo(
            name=schema_name,
            version=version,
            struct_type=struct_type,
            json_schema=json_schema,
        )
        self._schemas[(schema_name, version)] = info

    def get(self, name: str, version: int) -> SchemaInfo | None:
        """Get schema info by name and version."""
        return self._schemas.get((name, version))

    def latest(self, name: str) -> SchemaInfo | None:
        """Get latest version of a schema."""
        matching = [info for (n, _), info in self._schemas.items() if n == name]
        if not matching:
            return None
        return max(matching, key=lambda i: i.version)

    def export_all(self) -> dict[str, Any]:
        """Export all schemas as JSON Schema."""
        return {f'{info.name}@v{info.version}': info.json_schema for info in self._schemas.values()}


# Global registry
_registry = SchemaRegistry()


def get_schema_registry() -> SchemaRegistry:
    """Get the global schema registry."""
    return _registry


def register_schema(struct_type: type, *, version: int, name: str | None = None) -> type:
    """Decorator to register a schema."""
    get_schema_registry().register(struct_type, version=version, name=name)
    return struct_type
```

**Usage:**

```python
@register_schema(version=1)
class TaskEvent(msgspec.Struct, frozen=True, gc=False):
    id: str
    run_id: str
    status: str
    payload: msgspec.Raw


@register_schema(version=2, name='TaskEvent')
class TaskEventV2(msgspec.Struct, frozen=True, gc=False):
    id: str
    run_id: str
    status: str
    payload: msgspec.Raw
    # New in v2
    attempt: int = 0
    parent_id: str | None = None
```

______________________________________________________________________

## 6. View Structs for Streaming (Medium)

Create `klaw_core/runtime/views.py`:

```python
"""View structs for efficient partial decoding.

Use when you need only a subset of fields from large messages.
Particularly useful for:
- Control plane routing (need channel_id, not payload)
- Metrics/monitoring (need timestamps, counts)
- Index building (need IDs only)
"""

from __future__ import annotations

import msgspec

from klaw_core.runtime.channels.wire import MessageKind


class EnvelopeView(msgspec.Struct, array_like=True):
    """Minimal view for routing - only header fields."""

    version: int
    kind: MessageKind
    channel_id: str
    seq: int
    ts: int


class TaskEventView(msgspec.Struct):
    """View for task listing/filtering - no payload."""

    id: str
    run_id: str
    status: str


class RunSummaryView(msgspec.Struct):
    """View for run list pages."""

    id: str
    name: str
    status: str
    created_at: int
    updated_at: int


# Pre-built decoders for views
_envelope_view_decoder = msgspec.msgpack.Decoder(EnvelopeView)
_task_event_view_decoder = msgspec.msgpack.Decoder(TaskEventView)


def decode_envelope_view(buf: bytes) -> EnvelopeView:
    """Fast decode for routing decisions."""
    return _envelope_view_decoder.decode(buf)


def decode_task_view(buf: bytes) -> TaskEventView:
    """Fast decode for task listings."""
    return _task_event_view_decoder.decode(buf)
```

**Ref:** Guide §4.6

______________________________________________________________________

## 7. Configuration System (Medium)

Update config approach in `klaw_core/runtime/_config.py`:

```python
"""Configuration system using msgspec structs.

- TOML for human-authored config files
- Strict validation at load time
- Environment variable overrides
- Defaults omitted in serialization
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import msgspec

from klaw_core.runtime.types import (
    ChannelCapacity,
    ConcurrencyLimit,
    Identifier,
    TimeoutSeconds,
)


class RayConfig(msgspec.Struct, omit_defaults=True, forbid_unknown_fields=True):
    """Ray backend configuration."""

    namespace: Identifier = 'klaw'
    address: str | None = None  # None = auto-detect
    max_restarts: int = 4
    max_task_retries: int = -1
    max_concurrency: ConcurrencyLimit = 1000


class ChannelDefaults(msgspec.Struct, omit_defaults=True, forbid_unknown_fields=True):
    """Default channel settings."""

    capacity: ChannelCapacity = 10000
    unbounded: bool = False
    timeout: TimeoutSeconds = 30.0


class ExecutorConfig(msgspec.Struct, omit_defaults=True, forbid_unknown_fields=True):
    """Executor settings."""

    max_workers: ConcurrencyLimit = 64
    shutdown_timeout: TimeoutSeconds = 30.0


class TelemetryConfig(msgspec.Struct, omit_defaults=True, forbid_unknown_fields=True):
    """Observability settings."""

    enabled: bool = True
    metrics_port: Annotated[int, msgspec.Meta(ge=1024, le=65535)] = 9090
    trace_sample_rate: Annotated[float, msgspec.Meta(ge=0.0, le=1.0)] = 0.1


class KlawConfig(msgspec.Struct, omit_defaults=True, forbid_unknown_fields=True):
    """Root configuration."""

    ray: RayConfig = msgspec.field(default_factory=RayConfig)
    channels: ChannelDefaults = msgspec.field(default_factory=ChannelDefaults)
    executor: ExecutorConfig = msgspec.field(default_factory=ExecutorConfig)
    telemetry: TelemetryConfig = msgspec.field(default_factory=TelemetryConfig)


def load_config(path: str | Path | None = None) -> KlawConfig:
    """Load config from TOML file with env overrides.

    Args:
        path: Config file path. If None, uses KLAW_CONFIG env var or defaults.

    Returns:
        Validated KlawConfig instance.
    """
    if path is None:
        path = os.environ.get('KLAW_CONFIG', 'klaw.toml')

    path = Path(path)

    if path.exists():
        with open(path, 'rb') as f:
            config = msgspec.toml.decode(f.read(), type=KlawConfig, strict=False)
    else:
        config = KlawConfig()

    # Apply environment overrides
    config = _apply_env_overrides(config)

    return config


def _apply_env_overrides(config: KlawConfig) -> KlawConfig:
    """Apply KLAW_* environment variable overrides."""
    # Example: KLAW_RAY_NAMESPACE=prod overrides ray.namespace
    if ns := os.environ.get('KLAW_RAY_NAMESPACE'):
        config = msgspec.structs.replace(config, ray=msgspec.structs.replace(config.ray, namespace=ns))
    if addr := os.environ.get('KLAW_RAY_ADDRESS'):
        config = msgspec.structs.replace(config, ray=msgspec.structs.replace(config.ray, address=addr))
    # Add more as needed...
    return config


def save_config(config: KlawConfig, path: str | Path) -> None:
    """Save config to TOML file."""
    with open(path, 'wb') as f:
        f.write(msgspec.toml.encode(config))
```

**Ref:** Guide §5.4, §7

______________________________________________________________________

## 8. ParamSpec Decorators (High)

Update decorators to preserve signatures:

```python
"""Type-preserving decorators using ParamSpec."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import wrapt

from klaw_core.propagate import Propagate
from klaw_core.result import Err, Ok, Result

P = ParamSpec('P')
T = TypeVar('T')
E = TypeVar('E')


def result(
    func: Callable[P, Result[T, E]] | Callable[P, Awaitable[Result[T, E]]],
) -> Callable[P, Result[T, E]] | Callable[P, Awaitable[Result[T, E]]]:
    """Decorator that catches Propagate for .bail() support.

    Preserves function signature for IDE/type-checker support.
    """
    if asyncio.iscoroutinefunction(func):

        @wrapt.decorator
        async def async_wrapper(
            wrapped: Callable[P, Awaitable[Result[T, E]]],
            instance: object,
            args: tuple[object, ...],
            kwargs: dict[str, object],
        ) -> Result[T, E]:
            try:
                return await wrapped(*args, **kwargs)  # type: ignore
            except Propagate as p:
                return p.value

        return async_wrapper(func)

    @wrapt.decorator
    def sync_wrapper(
        wrapped: Callable[P, Result[T, E]],
        instance: object,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> Result[T, E]:
        try:
            return wrapped(*args, **kwargs)  # type: ignore
        except Propagate as p:
            return p.value

    return sync_wrapper(func)
```

**Ref:** Guide §2.3

______________________________________________________________________

## 9. Implementation Checklist

### Critical (Do First)

- [ ] Create `wire.py` with versioned `WireEnvelope` types
- [ ] Create `codec.py` with `CodecPool` and `BufferPool`
- [ ] Add `array_like=True` to all wire-crossing structs
- [ ] Create `types.py` with constrained type aliases

### High (Do Next)

- [ ] Update `protocols.py` with variance annotations
- [ ] Make `RayChannelActor` generic with cached validator
- [ ] Update decorators with `ParamSpec`
- [ ] Add docstrings noting Result/Option are in-process only

### Medium (Polish)

- [ ] Create `schema.py` registry for evolution
- [ ] Create `views.py` for partial decoding
- [ ] Update config system with validation
- [ ] Add round-trip tests for error struct/exception pairs

### Low (When Needed)

- [ ] Flip `_ChannelActorState` to `gc=True`
- [ ] Add `Generic[T]` for older tool compat
- [ ] Add `omit_defaults=True` to more structs

______________________________________________________________________

## 10. Testing Strategy

```python
"""Test patterns for msgspec types."""

import msgspec
import pytest

from klaw_core.runtime.channels.wire import (
    DataMessage,
    WireEnvelope,
    WireHeader,
)
from klaw_core.runtime.channels.codec import get_codec_pool


class TestWireRoundTrip:
    """Verify encode/decode preserves all data."""

    def test_data_message_roundtrip(self) -> None:
        pool = get_codec_pool()

        msg = DataMessage(
            header=WireHeader(channel_id='test', seq=1, ts=1234567890),
            payload=msgspec.Raw(b'{"key": "value"}'),
        )

        encoded = pool.encode(msg)
        decoded = pool.decode(encoded)

        assert isinstance(decoded, DataMessage)
        assert decoded.header.channel_id == 'test'
        assert decoded.header.seq == 1

    def test_envelope_tagged_dispatch(self) -> None:
        """Verify tagged union decodes to correct type."""
        from klaw_core.runtime.channels.wire import Heartbeat

        pool = get_codec_pool()

        hb = Heartbeat(
            header=WireHeader(kind=3, channel_id='test'),
            sender_id='worker-1',
        )

        decoded = pool.decode(pool.encode(hb))
        assert isinstance(decoded, Heartbeat)
        assert decoded.sender_id == 'worker-1'


class TestConstraintValidation:
    """Verify constraints are enforced at decode."""

    def test_positive_int_constraint(self) -> None:
        from klaw_core.runtime.types import PositiveInt

        class Config(msgspec.Struct):
            count: PositiveInt

        # Valid
        msgspec.json.decode(b'{"count": 1}', type=Config)

        # Invalid
        with pytest.raises(msgspec.ValidationError):
            msgspec.json.decode(b'{"count": 0}', type=Config)

        with pytest.raises(msgspec.ValidationError):
            msgspec.json.decode(b'{"count": -1}', type=Config)
```

______________________________________________________________________

## References

| Section         | Guide Reference  |
| --------------- | ---------------- |
| Wire Protocol   | §6.2, §6.3, §4.1 |
| Encoder/Decoder | §3.1, §6.1       |
| Buffer Reuse    | §3.6             |
| Constraints     | §4.2, §7         |
| Variance        | §2.1             |
| Generics        | §2.4             |
| View Structs    | §4.6             |
| Config          | §5.4, §7         |
| Performance     | §3.4, §3.5       |
