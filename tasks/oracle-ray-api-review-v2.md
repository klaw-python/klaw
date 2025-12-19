# Oracle Ray API Review v2: Corrections & Advanced Path

Based on deeper review of Ray API behavior against our implementation plan.

______________________________________________________________________

## Critical Finding: Exception Semantics

**The original plan has an incorrect assumption.**

Exceptions raised inside a Ray actor (`Full`, `Empty`, `ChannelClosed`) **do not** surface directly to the caller. Ray wraps all actor-side exceptions into `RayTaskError`.

```python
# WRONG: This won't work
try:
    await actor.put_nowait.remote(value)
except Full:  # ❌ Never caught - wrapped in RayTaskError
    return Err(ChannelFull(...))

# CORRECT: Use status return values
status = await actor.put_nowait.remote(value)
if status == 'full':
    return Err(ChannelFull(...))
```

______________________________________________________________________

## Corrections to Original Plan

### 1. Status Return Values (Not Exceptions)

Actor methods must return status codes instead of raising domain exceptions:

```python
@ray.remote
class RayChannelActor:
    # For send operations
    async def put(self, item: Any, timeout: float | None = None) -> str:
        """Returns: 'ok' | 'full' | 'closed'"""
        if self._receivers_closed:
            return 'closed'
        try:
            await asyncio.wait_for(self._queue.put(item), timeout)
            return 'ok'
        except asyncio.TimeoutError:
            return 'full'

    def put_nowait(self, item: Any) -> str:
        """Returns: 'ok' | 'full' | 'closed'"""
        if self._receivers_closed:
            return 'closed'
        try:
            self._queue.put_nowait(item)
            return 'ok'
        except Full:
            return 'full'

    # For receive operations
    async def get(self, timeout: float | None = None) -> tuple[str, Any | None]:
        """Returns: ('ok', value) | ('empty', None) | ('closed', None)"""
        if self._senders_closed and self._queue.empty():
            return ('closed', None)
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout)
            return ('ok', item)
        except asyncio.TimeoutError:
            if self._senders_closed:
                return ('closed', None)
            return ('empty', None)

    def get_nowait(self) -> tuple[str, Any | None]:
        """Returns: ('ok', value) | ('empty', None) | ('closed', None)"""
        if self._senders_closed and self._queue.empty():
            return ('closed', None)
        try:
            return ('ok', self._queue.get_nowait())
        except Empty:
            return ('empty', None)
```

### 2. Use `get_if_exists=True` for Named Actors

Avoids race conditions when multiple processes create the same channel:

```python
# WRONG: Race condition between get_actor and .remote()
try:
    actor = ray.get_actor(f"channel_{name}", namespace=namespace)
except ValueError:
    actor = RayChannelActor.options(name=f"channel_{name}", ...).remote(...)

# CORRECT: Atomic get-or-create
actor = RayChannelActor.options(
    name=f"channel_{name}",
    namespace=namespace,
    lifetime="detached",
    get_if_exists=True,  # ← Returns existing if present
).remote(capacity=capacity, unbounded=unbounded)
```

### 3. Registration IDs Are Optional

Counter-based registration is simpler and sufficient:

```python
def register_sender(self) -> None:
    """Increment sender count."""
    if self._senders_closed:
        return 'closed'
    self._sender_count += 1
    return 'ok'


def deregister_sender(self) -> None:
    """Decrement sender count."""
    self._sender_count = max(0, self._sender_count - 1)
    if self._sender_count == 0:
        self._senders_closed = True
```

The local `_closed` flag on each sender/receiver prevents double-deregistration.

### 4. Actor Concurrency

- Async actors default to `max_concurrency=1000`
- `asyncio.Queue` is safe for concurrent access within the actor's event loop
- No need to set `max_concurrency` manually unless throttling is desired

### 5. Error Handling on Client Side

Only catch `RayError` for transport/actor failures:

```python
async def send(self, value: T) -> None:
    if self._closed:
        raise ChannelClosed().to_exception()
    await self._ensure_registered()

    try:
        status = await self._actor.put.remote(value)
    except ray.exceptions.RayError as e:
        # Actor died, network error, etc.
        raise ChannelClosed().to_exception() from e

    match status:
        case 'ok':
            return
        case 'full':
            raise ChannelFull(self._capacity or 0).to_exception()
        case 'closed':
            raise ChannelClosed().to_exception()
```

______________________________________________________________________

## Advanced Path: Full Implementation

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       RayChannelActor                               │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  State:                                                        │ │
│  │  - queue: asyncio.Queue[Any]                                   │ │
│  │  - sender_count: int                                           │ │
│  │  - receiver_count: int                                         │ │
│  │  - senders_closed: bool                                        │ │
│  │  - receivers_closed: bool                                      │ │
│  │  - capacity: int | None                                        │ │
│  │  - created_at: float                                           │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Registration (status returns):                                     │
│  - register_sender() -> str                                        │
│  - deregister_sender() -> str                                      │
│  - register_receiver() -> str                                      │
│  - deregister_receiver() -> str                                    │
│                                                                     │
│  Data (status returns):                                            │
│  - put(item, timeout) -> str                                       │
│  - put_nowait(item) -> str                                         │
│  - get(timeout) -> tuple[str, Any | None]                          │
│  - get_nowait() -> tuple[str, Any | None]                          │
│                                                                     │
│  Introspection:                                                    │
│  - get_stats() -> ChannelStats                                     │
│  - is_closed() -> bool                                             │
│  - get_capacity() -> int | None                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Complete RayChannelActor Implementation

```python
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from queue import Empty, Full
from typing import Any

import ray


@dataclass
class ChannelStats:
    """Statistics for a distributed channel."""

    sender_count: int
    receiver_count: int
    queue_size: int
    capacity: int | None
    senders_closed: bool
    receivers_closed: bool
    created_at: float


@ray.remote
class RayChannelActor:
    """Control plane for distributed channel with ref-counted lifecycle.

    All methods return status codes instead of raising exceptions,
    because Ray wraps actor exceptions in RayTaskError.

    Status codes:
    - "ok": Operation succeeded
    - "full": Queue at capacity (put operations)
    - "empty": Queue empty (get operations)
    - "closed": Channel is closed
    """

    def __init__(self, capacity: int, unbounded: bool = False) -> None:
        self._maxsize = 0 if unbounded else capacity
        self._capacity = None if unbounded else capacity
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxsize)

        self._sender_count: int = 0
        self._receiver_count: int = 0
        self._senders_closed: bool = False
        self._receivers_closed: bool = False
        self._created_at: float = time.time()

    # --- Registration ---

    def register_sender(self) -> str:
        """Register a sender. Returns 'ok' or 'closed'."""
        if self._senders_closed:
            return 'closed'
        self._sender_count += 1
        return 'ok'

    def deregister_sender(self) -> str:
        """Deregister a sender. Returns 'ok'."""
        self._sender_count = max(0, self._sender_count - 1)
        if self._sender_count == 0:
            self._senders_closed = True
        return 'ok'

    def register_receiver(self) -> str:
        """Register a receiver. Returns 'ok' or 'closed'."""
        if self._receivers_closed:
            return 'closed'
        self._receiver_count += 1
        return 'ok'

    def deregister_receiver(self) -> str:
        """Deregister a receiver. Returns 'ok'."""
        self._receiver_count = max(0, self._receiver_count - 1)
        if self._receiver_count == 0:
            self._receivers_closed = True
        return 'ok'

    # --- Send Operations ---

    async def put(self, item: Any, timeout: float | None = None) -> str:
        """Blocking put. Returns 'ok', 'full', or 'closed'."""
        if self._receivers_closed:
            return 'closed'
        try:
            if timeout is None:
                await self._queue.put(item)
            else:
                await asyncio.wait_for(self._queue.put(item), timeout)
            return 'ok'
        except asyncio.TimeoutError:
            return 'full'

    def put_nowait(self, item: Any) -> str:
        """Non-blocking put. Returns 'ok', 'full', or 'closed'."""
        if self._receivers_closed:
            return 'closed'
        try:
            self._queue.put_nowait(item)
            return 'ok'
        except Full:
            return 'full'

    # --- Receive Operations ---

    async def get(self, timeout: float | None = None) -> tuple[str, Any | None]:
        """Blocking get. Returns ('ok', value), ('empty', None), or ('closed', None)."""
        # Check if closed and drained
        if self._senders_closed and self._queue.empty():
            return ('closed', None)

        try:
            if timeout is None:
                # For blocking without timeout, we need to periodically check closed state
                while True:
                    try:
                        item = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                        return ('ok', item)
                    except asyncio.TimeoutError:
                        if self._senders_closed and self._queue.empty():
                            return ('closed', None)
                        continue
            else:
                item = await asyncio.wait_for(self._queue.get(), timeout)
                return ('ok', item)
        except asyncio.TimeoutError:
            if self._senders_closed:
                return ('closed', None)
            return ('empty', None)

    def get_nowait(self) -> tuple[str, Any | None]:
        """Non-blocking get. Returns ('ok', value), ('empty', None), or ('closed', None)."""
        if self._senders_closed and self._queue.empty():
            return ('closed', None)
        try:
            item = self._queue.get_nowait()
            return ('ok', item)
        except Empty:
            return ('empty', None)

    # --- Introspection ---

    def get_stats(self) -> ChannelStats:
        """Get channel statistics."""
        return ChannelStats(
            sender_count=self._sender_count,
            receiver_count=self._receiver_count,
            queue_size=self._queue.qsize(),
            capacity=self._capacity,
            senders_closed=self._senders_closed,
            receivers_closed=self._receivers_closed,
            created_at=self._created_at,
        )

    def is_closed(self) -> bool:
        """Check if channel is fully closed."""
        return self._senders_closed and self._receivers_closed

    def get_capacity(self) -> int | None:
        """Get channel capacity (None if unbounded)."""
        return self._capacity

    def qsize(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
```

### Complete RaySender Implementation

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import ray
from ray.actor import ActorHandle

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import ChannelClosed, ChannelFull

if TYPE_CHECKING:
    from klaw_core.runtime.channels.protocols import Sender


class RaySender[T]:
    """Distributed sender with ref-counted registration.

    Uses status-return pattern for Ray actor communication.
    Registration is lazy (on first send) to keep clone() synchronous.
    """

    __slots__ = ('_actor', '_capacity', '_registered', '_closed')

    def __init__(
        self,
        actor: ActorHandle,
        capacity: int | None,
        registered: bool = False,
    ) -> None:
        self._actor = actor
        self._capacity = capacity
        self._registered = registered
        self._closed = False

    async def _ensure_registered(self) -> None:
        """Lazy registration on first use."""
        if self._registered:
            return
        try:
            status = await self._actor.register_sender.remote()
            if status == 'closed':
                raise ChannelClosed().to_exception()
            self._registered = True
        except ray.exceptions.RayError as e:
            raise ChannelClosed().to_exception() from e

    async def send(self, value: T) -> None:
        """Send a value, blocking if channel is at capacity.

        Raises:
            ChannelClosedError: If channel is closed or actor died.
        """
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()

        try:
            status = await self._actor.put.remote(value)
        except ray.exceptions.RayError as e:
            raise ChannelClosed().to_exception() from e

        match status:
            case 'ok':
                return
            case 'full':
                # Shouldn't happen with blocking put (no timeout)
                raise ChannelFull(self._capacity or 0).to_exception()
            case 'closed':
                raise ChannelClosed().to_exception()

    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        """Non-blocking send.

        Returns:
            Ok(None) if sent, Err(ChannelFull) if at capacity, Err(ChannelClosed) if closed.
        """
        if self._closed:
            return Err(ChannelClosed())
        await self._ensure_registered()

        try:
            status = await self._actor.put_nowait.remote(value)
        except ray.exceptions.RayError:
            return Err(ChannelClosed())

        match status:
            case 'ok':
                return Ok(None)
            case 'full':
                return Err(ChannelFull(self._capacity or 0))
            case 'closed':
                return Err(ChannelClosed())

        return Err(ChannelClosed())  # Unreachable but satisfies type checker

    def clone(self) -> RaySender[T]:
        """Clone this sender for multi-producer use.

        Returns a new sender sharing the same actor. The clone is
        unregistered and will register on first send.
        """
        return RaySender(self._actor, self._capacity, registered=False)

    async def close(self) -> None:
        """Close this sender, deregistering from the channel.

        When all senders close, receivers will see ChannelClosed.
        """
        if self._closed:
            return
        self._closed = True

        if self._registered:
            try:
                await self._actor.deregister_sender.remote()
            except ray.exceptions.RayError:
                pass  # Actor already dead
```

### Complete RayReceiver Implementation

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import ray
from ray.actor import ActorHandle

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from klaw_core.runtime.channels.protocols import Receiver


class RayReceiver[T]:
    """Distributed receiver with ref-counted registration.

    Uses status-return pattern for Ray actor communication.
    Registration is lazy (on first recv) to keep clone() synchronous.
    """

    __slots__ = ('_actor', '_capacity', '_registered', '_closed')

    def __init__(
        self,
        actor: ActorHandle,
        capacity: int | None,
        registered: bool = False,
    ) -> None:
        self._actor = actor
        self._capacity = capacity
        self._registered = registered
        self._closed = False

    async def _ensure_registered(self) -> None:
        """Lazy registration on first use."""
        if self._registered:
            return
        try:
            status = await self._actor.register_receiver.remote()
            if status == 'closed':
                raise ChannelClosed().to_exception()
            self._registered = True
        except ray.exceptions.RayError as e:
            raise ChannelClosed().to_exception() from e

    async def recv(self) -> T:
        """Receive the next value, blocking if channel is empty.

        Returns:
            The next value from the channel.

        Raises:
            ChannelClosedError: If all senders closed and queue is empty.
        """
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()

        try:
            status, value = await self._actor.get.remote()
        except ray.exceptions.RayError as e:
            raise ChannelClosed().to_exception() from e

        match status:
            case 'ok':
                return value
            case 'empty':
                # Shouldn't happen with blocking get (no timeout)
                raise ChannelEmpty().to_exception()
            case 'closed':
                raise ChannelClosed().to_exception()

        raise ChannelClosed().to_exception()  # Unreachable

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        """Non-blocking receive.

        Returns:
            Ok(value) if available, Err(ChannelEmpty) if empty, Err(ChannelClosed) if closed.
        """
        if self._closed:
            return Err(ChannelClosed())
        await self._ensure_registered()

        try:
            status, value = await self._actor.get_nowait.remote()
        except ray.exceptions.RayError:
            return Err(ChannelClosed())

        match status:
            case 'ok':
                return Ok(value)
            case 'empty':
                return Err(ChannelEmpty())
            case 'closed':
                return Err(ChannelClosed())

        return Err(ChannelClosed())  # Unreachable

    def clone(self) -> RayReceiver[T]:
        """Clone this receiver for multi-consumer use.

        Returns a new receiver sharing the same actor. The clone is
        unregistered and will register on first recv.
        """
        return RayReceiver(self._actor, self._capacity, registered=False)

    async def close(self) -> None:
        """Close this receiver, deregistering from the channel.

        When all receivers close, senders will see ChannelClosed.
        """
        if self._closed:
            return
        self._closed = True

        if self._registered:
            try:
                await self._actor.deregister_receiver.remote()
            except ray.exceptions.RayError:
                pass  # Actor already dead

    def __aiter__(self) -> RayReceiver[T]:
        """Start async iteration."""
        return self

    async def __anext__(self) -> T:
        """Get next value for async for loop."""
        try:
            return await self.recv()
        except Exception:  # ChannelClosedError
            raise StopAsyncIteration from None
```

### Factory Functions

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import ray

from klaw_core.runtime.channels.ray_channel import (
    RayChannelActor,
    RayReceiver,
    RaySender,
)

if TYPE_CHECKING:
    from klaw_core.runtime.channels.protocols import Receiver, Sender


async def channel(
    capacity: int = 10000,
    distributed: bool = False,
    unbounded: bool = False,
    name: str | None = None,
    namespace: str = 'klaw',
) -> tuple[Sender[T], Receiver[T]]:
    """Create a channel.

    Args:
        capacity: Max messages before senders block (default 10,000).
        distributed: If True, use RayChannel for cross-process/node communication.
        unbounded: If True, channel has no capacity limit.
        name: Optional name for cross-process retrieval (distributed only).
        namespace: Ray namespace for named channels (default "klaw").

    Returns:
        Tuple of (Sender[T], Receiver[T]).
    """
    if not distributed:
        # Existing LocalChannel path
        ...

    # Distributed path with RayChannelActor
    if name is not None:
        # Atomic get-or-create with get_if_exists
        actor = RayChannelActor.options(
            name=f'channel_{name}',
            namespace=namespace,
            lifetime='detached',
            get_if_exists=True,
        ).remote(capacity=capacity, unbounded=unbounded)
    else:
        # Anonymous channel (dies with creator)
        actor = RayChannelActor.remote(capacity=capacity, unbounded=unbounded)

    cap = None if unbounded else capacity
    tx: Sender[T] = RaySender(actor, cap)
    rx: Receiver[T] = RayReceiver(actor, cap)

    # Pre-register the initial sender/receiver
    await tx._ensure_registered()
    await rx._ensure_registered()

    return tx, rx


async def get_channel(
    name: str,
    namespace: str = 'klaw',
) -> tuple[Sender[T], Receiver[T]] | None:
    """Retrieve an existing named channel.

    Args:
        name: The channel name.
        namespace: Ray namespace (default "klaw").

    Returns:
        Tuple of (Sender[T], Receiver[T]) or None if not found.
    """
    try:
        actor = ray.get_actor(f'channel_{name}', namespace=namespace)
    except ValueError:
        return None

    try:
        cap = await actor.get_capacity.remote()
    except ray.exceptions.RayError:
        return None  # Actor dead or broken

    tx: Sender[T] = RaySender(actor, cap)
    rx: Receiver[T] = RayReceiver(actor, cap)

    await tx._ensure_registered()
    await rx._ensure_registered()

    return tx, rx


def delete_channel(name: str, namespace: str = 'klaw') -> bool:
    """Delete a named channel.

    Args:
        name: The channel name.
        namespace: Ray namespace (default "klaw").

    Returns:
        True if deleted, False if not found.
    """
    try:
        actor = ray.get_actor(f'channel_{name}', namespace=namespace)
    except ValueError:
        return False

    ray.kill(actor, no_restart=True)
    return True


def list_channels(namespace: str = 'klaw') -> list[str]:
    """List all named channels in a namespace.

    Args:
        namespace: Ray namespace (default "klaw").

    Returns:
        List of channel names.
    """
    all_actors = ray.util.list_named_actors(all_namespaces=True)
    prefix = 'channel_'
    return [
        actor['name'][len(prefix) :]
        for actor in all_actors
        if actor['namespace'] == namespace and actor['name'].startswith(prefix)
    ]
```

______________________________________________________________________

## Risks & Guardrails

### 1. Silent Masking of Bugs

Catching all `RayError` and mapping to `ChannelClosed` can hide serialization bugs.

**Guardrail:** Log the original error before mapping:

```python
except ray.exceptions.RayError as e:
    logger.warning(f"Ray error in channel operation: {e}")
    raise ChannelClosed().to_exception() from e
```

### 2. Leaked Registrations

If a client crashes without calling `close()`, the registration is never decremented.

**Guardrail:** Accept this for now. Named channels persist; anonymous channels die with their creator. Add TTL/heartbeat later if needed.

### 3. Detached Actor Accumulation

Detached named actors survive indefinitely without explicit cleanup.

**Guardrail:** Expose `delete_channel()` and `list_channels()` for admin cleanup. Consider periodic GC based on `created_at` timestamp.

### 4. Blocking Get Spin

The blocking `get()` implementation polls every 0.1s to check closed state.

**Guardrail:** This is acceptable latency for distributed channels. Alternative: use an `asyncio.Event` to signal closure, but adds complexity.

______________________________________________________________________

## Implementation Order

1. **Create `ray_channel.py`** with `RayChannelActor`, `RaySender`, `RayReceiver`
1. **Update `factory.py`** to wire `distributed=True` to Ray implementation
1. **Add `get_channel()`, `delete_channel()`, `list_channels()`** helpers
1. **Write tests** mirroring LocalChannel tests with Ray-specific expectations
1. **Add integration tests** for cross-process communication

______________________________________________________________________

## Test Strategy

### Unit Tests (Ray local mode)

```python
@pytest.fixture
def ray_init():
    ray.init(local_mode=True)
    yield
    ray.shutdown()


async def test_ray_channel_send_recv(ray_init):
    tx, rx = await channel(distributed=True)
    await tx.send(42)
    value = await rx.recv()
    assert value == 42
    await tx.close()
    await rx.close()


async def test_ray_channel_clone_independent(ray_init):
    tx1, rx = await channel(distributed=True)
    tx2 = tx1.clone()

    await tx1.close()
    # tx2 should still work
    await tx2.send(42)
    assert await rx.recv() == 42

    await tx2.close()
    await rx.close()


async def test_ray_channel_all_senders_closed(ray_init):
    tx, rx = await channel(distributed=True)
    await tx.send(1)
    await tx.close()

    # Can still drain
    assert await rx.recv() == 1

    # Now closed
    with pytest.raises(Exception, match='Channel closed'):
        await rx.recv()


async def test_named_channel_retrieval(ray_init):
    tx1, rx1 = await channel(distributed=True, name='test')
    result = await get_channel('test')
    assert result is not None
    tx2, rx2 = result

    await tx2.send(42)
    assert await rx1.recv() == 42

    delete_channel('test')
```

### Distributed Tests (Multi-process)

```python
@ray.remote
def remote_sender(name: str, values: list[int]) -> None:
    import asyncio

    async def run():
        result = await get_channel(name)
        if result is None:
            raise ValueError('Channel not found')
        tx, _ = result
        for v in values:
            await tx.send(v)
        await tx.close()

    asyncio.run(run())


async def test_cross_process_communication():
    tx, rx = await channel(distributed=True, name='cross_proc')

    # Start remote sender
    ray.get(remote_sender.remote('cross_proc', [1, 2, 3]))

    # Receive in main process
    values = []
    async for v in rx:
        values.append(v)
        if len(values) == 3:
            break

    assert values == [1, 2, 3]
    delete_channel('cross_proc')
```
