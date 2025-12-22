# Sunray Integration Plan for RayChannelActor

## Overview

Integrate [sunray](https://github.com/zen-xu/sunray) into `RayChannelActor` to provide typed Ray actor handles with IDE autocompletion and proper type inference.

**Status**: Sunray v0.13.0 confirmed working on Python 3.13
**Effort**: Small-Medium (1-3 hours including tests)
**Breaking Changes**: Yes, but nothing is published yet

______________________________________________________________________

## Goals

1. Convert `RayChannelActor` to use sunray's `ActorMixin` and `@remote_method`
1. Get typed actor handles: `Actor[RayChannelActor[int]]`
1. Enable IDE autocompletion via `.methods.put.remote()` pattern
1. Keep PEP 695 type parameter syntax (`class RayChannelActor[T]:`)
1. Preserve runtime type validation via `_TypeValidator[T]`

______________________________________________________________________

## Design Decisions

| Aspect           | Decision                        | Rationale                                                   |
| ---------------- | ------------------------------- | ----------------------------------------------------------- |
| Actor base       | `sunray.ActorMixin`             | Provides typed `Actor[T]` wrapper                           |
| Method decorator | `@sunray.remote_method`         | Enables `.methods` access pattern                           |
| Generics         | Keep PEP 695 `class Foo[T]:`    | Already used in protocols, Python 3.13 target               |
| Ray options      | Pass to `ActorMixin` base class | `max_restarts=4, max_task_retries=-1, max_concurrency=1000` |
| Type validation  | Keep `_TypeValidator[T]`        | msgspec-based runtime validation                            |

______________________________________________________________________

## API Changes

### Instantiation

```python
# Before (Ray native)
actor = RayChannelActor.remote(capacity=10, value_type=int)

# After (sunray)
actor = RayChannelActor.new_actor().remote(capacity=10, value_type=int)
# Type: sunray.Actor[RayChannelActor[int]]
```

### Method Calls

```python
# Before (Ray native)
status = ray.get(actor.put_nowait.remote(42))
result = ray.get(actor.get_nowait.remote())

# After (sunray)
status = ray.get(actor.methods.put_nowait.remote(42))
result = ray.get(actor.methods.get_nowait.remote())
```

### Actor Options

```python
# Before (Ray native)
actor = RayChannelActor.options(num_cpus=2).remote(...)

# After (sunray)
actor = RayChannelActor.new_actor().options(num_cpus=2).remote(...)
```

______________________________________________________________________

## Tasks

### Task 1: Convert RayChannelActor to ActorMixin

**File**: `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/actor.py`

**Changes**:

1. Remove `@ray.remote(...)` decorator
1. Add `sunray.ActorMixin` as base class with Ray options
1. Decorate all public methods with `@sunray.remote_method`
1. Keep `_TypeValidator[T]` and internal methods unchanged

**Full Implementation**:

```python
"""Ray channel actor implementation."""

from __future__ import annotations

import asyncio
from functools import partial
from datetime import UTC, datetime
from typing import Any

import msgspec
import sunray

from klaw_core.runtime.channels.ray.constants import BatchResult, ReaderInfo, SingleResult


class _TypeValidator[T]:
    """Validates values against a type using msgspec.convert with lazy caching.

    The converter function is created lazily on first validation call,
    avoiding overhead when validation is not needed (value_type=None).

    Type Parameters:
        T: The type to validate against.
    """

    __slots__ = ('_type', '_convert_fn')

    def __init__(self, value_type: type[T] | None) -> None:
        """Initialize the validator.

        Args:
            value_type: The type to validate against, or None to accept all values.
        """
        self._type = value_type
        self._convert_fn: Any | None = None

    def validate(self, item: Any) -> bool:
        """Validate an item against the expected type.

        Args:
            item: The value to validate.

        Returns:
            True if valid (or no type constraint), False if validation fails.
        """
        if self._type is None:
            return True

        if self._convert_fn is None:
            self._convert_fn = partial(msgspec.convert, type=self._type)

        try:
            self._convert_fn(item)
        except (msgspec.ValidationError, TypeError):
            return False
        return True


class _ChannelActorState(msgspec.Struct, gc=False):
    """Mutable internal state for RayChannelActor."""

    capacity: int | None
    unbounded: bool
    value_type: type | None = None
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
            self.created_at = datetime.now(UTC)


class RayChannelActor[T](
    sunray.ActorMixin,
    max_restarts=4,
    max_task_retries=-1,
    max_concurrency=1000,
):
    """Ray actor that holds the channel buffer.

    Integrated with sunray's ActorMixin for typed actor handles.

    Usage:
        actor = RayChannelActor.new_actor().remote(capacity=10, value_type=int)
        status = ray.get(actor.methods.put_nowait.remote(42))
        result = ray.get(actor.methods.get_nowait.remote())

    Actor methods return status codes instead of raising exceptions:
    - "ok": Operation succeeded
    - "full": Channel at capacity (for put operations)
    - "empty": No messages available (for get operations)
    - "closed": Channel has been closed
    - "type_error": Value failed runtime type validation
    """

    def __init__(
        self,
        capacity: int | None = None,
        unbounded: bool = False,
        value_type: type[T] | None = None,
    ) -> None:
        """Initialize the channel actor.

        Args:
            capacity: Maximum queue size. None means unbounded.
            unbounded: If True, queue has no capacity limit.
            value_type: Optional type for runtime validation (e.g., int, list[str]).
        """
        self._state = _ChannelActorState(
            capacity=capacity if not unbounded else None,
            unbounded=unbounded,
            value_type=value_type,
        )
        self._validator = _TypeValidator(value_type)

        queue_size = 0 if unbounded or capacity is None else capacity
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=queue_size)

        self._readers: dict[str, ReaderInfo] = {}

    @sunray.remote_method
    def register_sender(self) -> str:
        """Register a new sender. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        self._state.sender_count += 1
        return 'ok'

    @sunray.remote_method
    def deregister_sender(self) -> str:
        """Deregister a sender. Returns status code."""
        if self._state.sender_count > 0:
            self._state.sender_count -= 1
        if self._state.sender_count == 0:
            self._state.senders_closed = True
        return 'ok'

    @sunray.remote_method
    def register_receiver(self, reader_id: str, node_id: str) -> str:
        """Register a new receiver with node tracking. Returns status code."""
        if self._state.receivers_closed:
            return 'closed'

        now = datetime.now(UTC)
        self._readers[reader_id] = ReaderInfo(
            reader_id=reader_id,
            node_id=node_id,
            registered_at=now,
            last_seen_at=now,
            total_received=0,
        )
        self._state.receiver_count += 1
        return 'ok'

    @sunray.remote_method
    def deregister_receiver(self, reader_id: str) -> str:
        """Deregister a receiver. Returns status code."""
        if reader_id in self._readers:
            del self._readers[reader_id]
            if self._state.receiver_count > 0:
                self._state.receiver_count -= 1
        if self._state.receiver_count == 0:
            self._state.receivers_closed = True
        return 'ok'

    @sunray.remote_method
    async def put(self, item: T, timeout: float | None = None) -> str:
        """Put an item into the queue. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        if self._state.receivers_closed:
            return 'closed'
        if not self._validator.validate(item):
            return 'type_error'

        try:
            if timeout is not None:
                await asyncio.wait_for(self._queue.put(item), timeout=timeout)
            else:
                await self._queue.put(item)

            self._state.total_sent += 1
            current_size = self._queue.qsize()
            self._state.high_watermark = max(self._state.high_watermark, current_size)
            return 'ok'
        except TimeoutError:
            return 'full'

    @sunray.remote_method
    def put_nowait(self, item: T) -> str:
        """Put an item without blocking. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        if self._state.receivers_closed:
            return 'closed'
        if not self._validator.validate(item):
            return 'type_error'

        try:
            self._queue.put_nowait(item)
            self._state.total_sent += 1
            current_size = self._queue.qsize()
            self._state.high_watermark = max(self._state.high_watermark, current_size)
            return 'ok'
        except asyncio.QueueFull:
            return 'full'

    @sunray.remote_method
    async def get(
        self,
        timeout: float | None = None,
        reader_id: str | None = None,
    ) -> SingleResult[T]:
        """Get an item from the queue. Returns SingleResult."""
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
        except TimeoutError:
            return SingleResult(status='empty')

    @sunray.remote_method
    def get_nowait(self, reader_id: str | None = None) -> SingleResult[T]:
        """Get an item without blocking. Returns SingleResult."""
        if self._state.senders_closed and self._queue.empty():
            return SingleResult(status='closed')

        try:
            item = self._queue.get_nowait()
            self._state.total_received += 1
            self._update_reader_stats(reader_id)
            return SingleResult(status='ok', value=item)
        except asyncio.QueueEmpty:
            return SingleResult(status='empty')

    @sunray.remote_method
    async def put_batch(
        self,
        items: tuple[T, ...],
        timeout: float | None = None,
    ) -> str:
        """Put multiple items atomically. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        if self._state.receivers_closed:
            return 'closed'
        for item in items:
            if not self._validator.validate(item):
                return 'type_error'

        try:
            for item in items:
                if timeout is not None:
                    await asyncio.wait_for(self._queue.put(item), timeout=timeout)
                else:
                    await self._queue.put(item)

            self._state.total_sent += len(items)
            current_size = self._queue.qsize()
            self._state.high_watermark = max(self._state.high_watermark, current_size)
            return 'ok'
        except TimeoutError:
            return 'full'

    @sunray.remote_method
    async def get_batch(
        self,
        max_items: int,
        timeout: float | None = None,
        reader_id: str | None = None,
    ) -> BatchResult[T]:
        """Get multiple items from the queue. Returns BatchResult."""
        if self._state.senders_closed and self._queue.empty():
            return BatchResult(status='closed')

        collected: list[T] = []
        try:
            for _ in range(max_items):
                if self._queue.empty():
                    break
                if timeout is not None:
                    item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                else:
                    item = await self._queue.get()
                collected.append(item)

            if collected:
                self._state.total_received += len(collected)
                if reader_id and reader_id in self._readers:
                    old = self._readers[reader_id]
                    self._readers[reader_id] = ReaderInfo(
                        reader_id=old.reader_id,
                        node_id=old.node_id,
                        registered_at=old.registered_at,
                        last_seen_at=datetime.now(UTC),
                        total_received=old.total_received + len(collected),
                    )
                return BatchResult(status='ok', items=tuple(collected))
            return BatchResult(status='empty')
        except TimeoutError:
            if collected:
                self._state.total_received += len(collected)
                return BatchResult(status='ok', items=tuple(collected))
            return BatchResult(status='empty')

    def _update_reader_stats(self, reader_id: str | None) -> None:
        """Update reader stats with new immutable ReaderInfo instance."""
        if reader_id and reader_id in self._readers:
            old = self._readers[reader_id]
            self._readers[reader_id] = ReaderInfo(
                reader_id=old.reader_id,
                node_id=old.node_id,
                registered_at=old.registered_at,
                last_seen_at=datetime.now(UTC),
                total_received=old.total_received + 1,
            )
```

______________________________________________________________________

### Task 2: Update Package Exports (Optional)

**File**: `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/__init__.py`

```python
"""Ray-backed distributed channel implementations."""

from __future__ import annotations

from klaw_core.runtime.channels.ray.actor import RayChannelActor
from klaw_core.runtime.channels.ray.constants import BatchResult, ReaderInfo, SingleResult

__all__ = ['RayChannelActor', 'BatchResult', 'ReaderInfo', 'SingleResult']
```

______________________________________________________________________

### Task 3: Update All Call Sites

Search for any code that uses `RayChannelActor` and update:

```bash
rg "RayChannelActor" --type py
```

**Pattern replacements**:

| Before                                     | After                                                  |
| ------------------------------------------ | ------------------------------------------------------ |
| `RayChannelActor.remote(...)`              | `RayChannelActor.new_actor().remote(...)`              |
| `RayChannelActor.options(...).remote(...)` | `RayChannelActor.new_actor().options(...).remote(...)` |
| `actor.method_name.remote(...)`            | `actor.methods.method_name.remote(...)`                |

______________________________________________________________________

### Task 4: Create/Update Tests

**File**: `workspaces/python/klaw-core/tests/runtime/channels/ray/test_actor.py`

```python
"""Tests for RayChannelActor with sunray integration."""

from __future__ import annotations

import pytest
import ray
import sunray

from klaw_core.runtime.channels.ray.actor import RayChannelActor


@pytest.fixture
def ray_initialized():
    """Initialize Ray for testing."""
    from klaw_core.runtime._backends.ray import RayBackend

    backend = RayBackend()
    backend._ensure_ray_init()
    yield
    ray.shutdown()


class TestRayChannelActorSunray:
    """Test RayChannelActor with sunray integration."""

    def test_actor_creation(self, ray_initialized):
        """Test creating actor with new_actor()."""
        actor = RayChannelActor.new_actor().remote(capacity=10, value_type=int)
        assert actor is not None
        # Verify it's a sunray Actor wrapper
        assert isinstance(actor, sunray.Actor)

    def test_put_and_get(self, ray_initialized):
        """Test basic put/get operations via .methods."""
        actor = RayChannelActor.new_actor().remote(capacity=10, value_type=int)

        # Put via .methods
        status = ray.get(actor.methods.put_nowait.remote(42))
        assert status == 'ok'

        # Get via .methods
        result = ray.get(actor.methods.get_nowait.remote())
        assert result.status == 'ok'
        assert result.value == 42

    def test_type_validation(self, ray_initialized):
        """Test runtime type validation still works."""
        actor = RayChannelActor.new_actor().remote(capacity=10, value_type=int)

        # Valid type
        status = ray.get(actor.methods.put_nowait.remote(42))
        assert status == 'ok'

        # Invalid type
        status = ray.get(actor.methods.put_nowait.remote('not an int'))
        assert status == 'type_error'

    def test_sender_receiver_registration(self, ray_initialized):
        """Test sender/receiver registration via .methods."""
        actor = RayChannelActor.new_actor().remote(capacity=10)

        # Register sender
        status = ray.get(actor.methods.register_sender.remote())
        assert status == 'ok'

        # Register receiver
        status = ray.get(actor.methods.register_receiver.remote('reader-1', 'node-1'))
        assert status == 'ok'

        # Deregister
        status = ray.get(actor.methods.deregister_sender.remote())
        assert status == 'ok'

    def test_batch_operations(self, ray_initialized):
        """Test batch put/get via .methods."""
        actor = RayChannelActor.new_actor().remote(unbounded=True, value_type=int)

        # Batch put
        items = (1, 2, 3, 4, 5)
        status = ray.get(actor.methods.put_batch.remote(items))
        assert status == 'ok'

        # Batch get
        result = ray.get(actor.methods.get_batch.remote(max_items=3))
        assert result.status == 'ok'
        assert len(result.items) == 3
        assert result.items == (1, 2, 3)

    def test_channel_closure(self, ray_initialized):
        """Test channel closure behavior."""
        actor = RayChannelActor.new_actor().remote(capacity=10)

        # Register and deregister sender to close
        ray.get(actor.methods.register_sender.remote())
        ray.get(actor.methods.deregister_sender.remote())

        # Should be closed now
        status = ray.get(actor.methods.put_nowait.remote(42))
        assert status == 'closed'

    def test_actor_options(self, ray_initialized):
        """Test actor options via new_actor().options()."""
        actor = (
            RayChannelActor.new_actor()
            .options(
                num_cpus=0,  # Use 0 for testing
                name='test-channel-actor',
            )
            .remote(capacity=10)
        )

        status = ray.get(actor.methods.put_nowait.remote(42))
        assert status == 'ok'

    def test_unbounded_queue(self, ray_initialized):
        """Test unbounded queue mode."""
        actor = RayChannelActor.new_actor().remote(unbounded=True)

        # Should accept many items
        for i in range(100):
            status = ray.get(actor.methods.put_nowait.remote(i))
            assert status == 'ok'

    def test_async_methods(self, ray_initialized):
        """Test async put/get methods."""
        actor = RayChannelActor.new_actor().remote(capacity=10, value_type=int)

        # Async put
        status = ray.get(actor.methods.put.remote(42, timeout=1.0))
        assert status == 'ok'

        # Async get
        result = ray.get(actor.methods.get.remote(timeout=1.0))
        assert result.status == 'ok'
        assert result.value == 42
```

______________________________________________________________________

### Task 5: Verify Type Checking

Run mypy/pyright to verify types work correctly:

```bash
uv run mypy src/klaw_core/runtime/channels/ray/actor.py
uv run pyright src/klaw_core/runtime/channels/ray/actor.py
```

**Expected**: No type errors. IDE should show autocompletion for `actor.methods.*`.

______________________________________________________________________

## Risks and Mitigations

| Risk                                  | Impact | Mitigation                                                      |
| ------------------------------------- | ------ | --------------------------------------------------------------- |
| PEP 695 + sunray incompatibility      | High   | Tested: works on Python 3.13                                    |
| sunray not officially supporting 3.13 | Medium | sunray has no 3.13-specific code; classifiers are just metadata |
| Ray version mismatch in workers       | Low    | Already handled by our `DEFAULT_RUNTIME_ENV_EXCLUDES`           |
| Breaking existing code                | None   | Nothing published yet                                           |

______________________________________________________________________

## Testing Strategy

1. **Unit tests**: Test actor creation, method calls, type validation
1. **Integration tests**: Test with real Ray cluster (standalone mode)
1. **Type checking**: Verify mypy/pyright pass
1. **IDE verification**: Check autocompletion works in VS Code

______________________________________________________________________

## Files Changed Summary

| File                                             | Change Type         |
| ------------------------------------------------ | ------------------- |
| `src/klaw_core/runtime/channels/ray/actor.py`    | Modified            |
| `src/klaw_core/runtime/channels/ray/__init__.py` | Modified (optional) |
| `tests/runtime/channels/ray/test_actor.py`       | Created/Modified    |

______________________________________________________________________

## Verification Commands

```bash
# Run tests
uv run pytest tests/runtime/channels/ray/test_actor.py -v

# Type check
uv run mypy src/klaw_core/runtime/channels/ray/

# Quick smoke test
uv run python -c "
from klaw_core.runtime.channels.ray.actor import RayChannelActor
from klaw_core.runtime._backends.ray import RayBackend
import ray

RayBackend()._ensure_ray_init()
actor = RayChannelActor.new_actor().remote(capacity=10, value_type=int)
print('put:', ray.get(actor.methods.put_nowait.remote(42)))
print('get:', ray.get(actor.methods.get_nowait.remote()))
ray.shutdown()
print('✓ Sunray integration works!')
"
```

______________________________________________________________________

## Next Steps After Completion

1. Update any higher-level channel implementations that use `RayChannelActor`
1. Add type aliases for common actor types if needed
1. Consider adding helper functions for common patterns
1. Update documentation with new API patterns
