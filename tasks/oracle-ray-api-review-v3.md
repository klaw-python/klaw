# Oracle Ray API Review v3: Future-Proof Scalable Implementation

Complete implementation guide with all advanced features (except RDT).

______________________________________________________________________

## TL;DR

Build a single async **RayChannelActor** per channel with:

- **Ref-counted lifecycle** with true distributed close semantics
- **Named actors** with `get_if_exists=True` and `lifetime="detached"`
- **Node-aware receiver registration** for locality optimization
- **Batch operations** for high throughput
- **ReferenceChannel** wrappers for large payloads
- **Checkpoint hooks** for fault tolerance
- **Backpressure diagnostics** with queue depth and per-node stats
- **Supervisor pattern** for lifecycle management
- **Reader pool patterns** for load balancing

**Effort:** L–XL (1–3 days)

______________________________________________________________________

## Architecture Overview

```
                           Ray Cluster
┌───────────────────────────────────────────────────────────────────────┐
│                            Named Channels                             │
│                                                                       │
│            (one async actor per logical channel name)                 │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │                    RayChannelActor (async)                    │   │
│   │  - asyncio.Queue[item] (or ObjectRef for ReferenceChannel)    │   │
│   │  - ref counts: sender_count, receiver_count                   │   │
│   │  - flags: senders_closed, receivers_closed                    │   │
│   │  - stats: queue_size, high_watermark, total_sent/recv         │   │
│   │  - node-aware registry: reader_id → {node_id, stats...}       │   │
│   │  - checkpoint hooks: get_checkpoint_state/apply_checkpoint    │   │
│   │  - batch APIs: put_batch/get_batch                            │   │
│   │  - backpressure: capacity, size, per-node reader counts       │   │
│   └─────────────────────┬─────────────────────────────────────────┘   │
│                         │                                             │
│        ┌────────────────┴────────────────┐                            │
│        ▼                                 ▼                            │
│  Producers (many)                  Consumers / Reader Pools           │
│  - RaySender                       - RayReceiver                      │
│  - RayReferenceSender (large)      - RayReferenceReceiver (large)     │
│                                                                       │
│ Supervisor / Orchestration layer:                                     │
│   - ChannelSupervisor actor (owns many channels, does checkpointing)  │
│   - ReaderPool patterns (ActorPool-style) using Receivers             │
└───────────────────────────────────────────────────────────────────────┘
```

______________________________________________________________________

## Module Structure

```
klaw_core/runtime/channels/
├── __init__.py
├── protocols.py              # Sender/Receiver protocols
├── local.py                  # LocalSender/LocalReceiver
├── oneshot.py                # OneshotSender/OneshotReceiver
├── broadcast.py              # BroadcastSender/BroadcastReceiver
├── watch.py                  # WatchSender/WatchReceiver
├── ray_channel.py            # RayChannelActor, RaySender, RayReceiver
├── reference_channel.py      # RayReferenceSender/RayReferenceReceiver
├── supervisor.py             # ChannelSupervisor
├── pools.py                  # ReaderPool patterns
├── factory.py                # channel(), get_channel(), delete_channel()
└── errors.py                 # ChannelClosed, ChannelFull, etc.
```

______________________________________________________________________

## Ray API Verification (Ray 2.x)

### Named Actors / Get-or-Create

```python
actor = RayChannelActor.options(
    name=f'channel_{name}',
    namespace=namespace,
    lifetime='detached',
    get_if_exists=True,  # Atomic get-or-create
).remote(capacity=capacity, unbounded=unbounded)
```

- ✅ `get_if_exists=True` is the documented pattern
- ✅ `lifetime="detached"` persists beyond driver
- ✅ Must explicitly `ray.kill()` to clean up

### Node-Awareness

```python
import ray

node_id = ray.get_runtime_context().get_node_id()
```

- ✅ Current, correct API for node ID

### Actor Concurrency

- ✅ Async actors default to `max_concurrency=1000`
- ✅ Appropriate for channels (many small RPCs)

### Named Actor Listing

```python
ray.util.list_named_actors(all_namespaces=True)
```

- ✅ Not deprecated (as of Ray 2.5x)

______________________________________________________________________

## Core Implementation

### Types and Stats

```python
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from queue import Empty, Full
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar

import ray

T = TypeVar('T')


@dataclass
class ReaderInfo:
    """Per-reader tracking information."""

    reader_id: str
    node_id: str
    registered_at: float
    last_seen_at: float
    total_received: int = 0


@dataclass
class ChannelStats:
    """Comprehensive channel statistics for monitoring and backpressure."""

    sender_count: int
    receiver_count: int
    queue_size: int
    capacity: Optional[int]
    senders_closed: bool
    receivers_closed: bool
    created_at: float
    high_watermark: int
    total_sent: int
    total_received: int
    per_node_receivers: Dict[str, int]


@dataclass
class ChannelCheckpoint:
    """Lightweight checkpoint metadata for fault tolerance."""

    created_at: float
    total_sent: int
    total_received: int
    senders_closed: bool
    receivers_closed: bool
```

### RayChannelActor

```python
@ray.remote(
    max_restarts=4,  # Basic fault tolerance
    max_task_retries=-1,  # Retry on transient failures
)
class RayChannelActor:
    """Control plane for a distributed channel with ref-counted lifecycle.

    All methods return status codes instead of raising domain exceptions:
    - 'ok'     : operation succeeded
    - 'full'   : queue at capacity
    - 'empty'  : queue empty
    - 'closed' : channel closed
    """

    def __init__(self, capacity: int, unbounded: bool = False) -> None:
        self._maxsize = 0 if unbounded else capacity
        self._capacity = None if unbounded else capacity
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxsize)

        # Ref counts
        self._sender_count: int = 0
        self._receiver_count: int = 0
        self._senders_closed: bool = False
        self._receivers_closed: bool = False

        # Node-aware reader tracking
        self._readers: Dict[str, ReaderInfo] = {}
        self._node_to_readers: Dict[str, set[str]] = {}

        # Stats
        self._created_at: float = time.time()
        self._total_sent: int = 0
        self._total_received: int = 0
        self._high_watermark: int = 0

    # ─────────────────────────────────────────────────────────────────
    # Registration (ref-counted close)
    # ─────────────────────────────────────────────────────────────────

    def register_sender(self) -> str:
        if self._senders_closed:
            return 'closed'
        self._sender_count += 1
        return 'ok'

    def deregister_sender(self) -> str:
        if self._sender_count > 0:
            self._sender_count -= 1
        if self._sender_count == 0:
            self._senders_closed = True
        return 'ok'

    def register_receiver(self, reader_id: str, node_id: str) -> str:
        if self._receivers_closed:
            return 'closed'
        now = time.time()
        self._receiver_count += 1

        info = ReaderInfo(
            reader_id=reader_id,
            node_id=node_id,
            registered_at=now,
            last_seen_at=now,
        )
        self._readers[reader_id] = info
        self._node_to_readers.setdefault(node_id, set()).add(reader_id)
        return 'ok'

    def deregister_receiver(self, reader_id: str) -> str:
        if reader_id in self._readers:
            node_id = self._readers[reader_id].node_id
            del self._readers[reader_id]
            node_set = self._node_to_readers.get(node_id)
            if node_set is not None:
                node_set.discard(reader_id)
                if not node_set:
                    self._node_to_readers.pop(node_id, None)

        if self._receiver_count > 0:
            self._receiver_count -= 1
        if self._receiver_count == 0:
            self._receivers_closed = True
        return 'ok'

    # ─────────────────────────────────────────────────────────────────
    # Data plane (single-item)
    # ─────────────────────────────────────────────────────────────────

    async def put(self, item: Any, timeout: Optional[float] = None) -> str:
        """Returns 'ok' | 'full' | 'closed'."""
        if self._receivers_closed:
            return 'closed'

        try:
            await asyncio.wait_for(self._queue.put(item), timeout)
        except asyncio.TimeoutError:
            return 'full'

        self._total_sent += 1
        qsize = self._queue.qsize()
        if qsize > self._high_watermark:
            self._high_watermark = qsize
        return 'ok'

    def put_nowait(self, item: Any) -> str:
        if self._receivers_closed:
            return 'closed'
        try:
            self._queue.put_nowait(item)
        except Full:
            return 'full'
        self._total_sent += 1
        qsize = self._queue.qsize()
        if qsize > self._high_watermark:
            self._high_watermark = qsize
        return 'ok'

    async def get(
        self,
        *,
        timeout: Optional[float] = None,
        reader_id: Optional[str] = None,
    ) -> Tuple[str, Any | None]:
        """Returns ('ok', v) | ('empty', None) | ('closed', None)."""
        if self._senders_closed and self._queue.empty():
            return ('closed', None)

        try:
            item = await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            if self._senders_closed:
                return ('closed', None)
            return ('empty', None)

        self._total_received += 1
        if reader_id is not None and reader_id in self._readers:
            info = self._readers[reader_id]
            info.last_seen_at = time.time()
            info.total_received += 1

        return ('ok', item)

    def get_nowait(self, reader_id: Optional[str] = None) -> Tuple[str, Any | None]:
        if self._senders_closed and self._queue.empty():
            return ('closed', None)

        try:
            item = self._queue.get_nowait()
        except Empty:
            if self._senders_closed:
                return ('closed', None)
            return ('empty', None)

        self._total_received += 1
        if reader_id is not None and reader_id in self._readers:
            info = self._readers[reader_id]
            info.last_seen_at = time.time()
            info.total_received += 1

        return ('ok', item)

    # ─────────────────────────────────────────────────────────────────
    # Batch operations
    # ─────────────────────────────────────────────────────────────────

    def put_nowait_batch(self, items: List[Any]) -> str:
        """Atomic batch put: either all items or none."""
        if self._receivers_closed:
            return 'closed'
        if not items:
            return 'ok'

        n = len(items)
        if self._capacity is not None and self._queue.qsize() + n > self._capacity:
            return 'full'

        for item in items:
            self._queue.put_nowait(item)
        self._total_sent += n
        qsize = self._queue.qsize()
        if qsize > self._high_watermark:
            self._high_watermark = qsize
        return 'ok'

    async def put_batch(self, items: List[Any], timeout: Optional[float] = None) -> str:
        """Batch with timeout; best-effort."""
        if self._receivers_closed:
            return 'closed'
        if not items:
            return 'ok'

        if self._capacity is not None and self._queue.qsize() + len(items) > self._capacity:
            return 'full'

        try:
            for item in items:
                await asyncio.wait_for(self._queue.put(item), timeout)
        except asyncio.TimeoutError:
            return 'full'

        self._total_sent += len(items)
        qsize = self._queue.qsize()
        if qsize > self._high_watermark:
            self._high_watermark = qsize
        return 'ok'

    async def get_batch(
        self,
        max_items: int,
        *,
        timeout: Optional[float] = None,
        reader_id: Optional[str] = None,
    ) -> Tuple[str, List[Any]]:
        """Fetch up to max_items. Status: 'ok' | 'empty' | 'closed'."""
        if max_items <= 0:
            return ('empty', [])

        status, first = await self.get(timeout=timeout, reader_id=reader_id)
        if status != 'ok':
            return (status, [])

        items = [first]
        while len(items) < max_items:
            s, v = self.get_nowait(reader_id=reader_id)
            if s != 'ok':
                break
            items.append(v)
        return ('ok', items)

    # ─────────────────────────────────────────────────────────────────
    # Introspection & checkpointing
    # ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> ChannelStats:
        per_node_receivers = {node_id: len(readers) for node_id, readers in self._node_to_readers.items()}
        return ChannelStats(
            sender_count=self._sender_count,
            receiver_count=self._receiver_count,
            queue_size=self._queue.qsize(),
            capacity=self._capacity,
            senders_closed=self._senders_closed,
            receivers_closed=self._receivers_closed,
            created_at=self._created_at,
            high_watermark=self._high_watermark,
            total_sent=self._total_sent,
            total_received=self._total_received,
            per_node_receivers=per_node_receivers,
        )

    def get_capacity(self) -> Optional[int]:
        return self._capacity

    def is_closed(self) -> bool:
        return self._senders_closed and self._receivers_closed and self._queue.empty()

    def get_checkpoint_state(self) -> ChannelCheckpoint:
        """Lightweight checkpoint for supervisors."""
        return ChannelCheckpoint(
            created_at=self._created_at,
            total_sent=self._total_sent,
            total_received=self._total_received,
            senders_closed=self._senders_closed,
            receivers_closed=self._receivers_closed,
        )

    def apply_checkpoint_state(self, state: ChannelCheckpoint) -> str:
        """For supervised recovery; does NOT restore queue contents."""
        self._created_at = state.created_at
        self._total_sent = state.total_sent
        self._total_received = state.total_received
        self._senders_closed = state.senders_closed
        self._receivers_closed = state.receivers_closed
        return 'ok'

    def get_reader_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get per-reader statistics for load balancing."""
        return {
            rid: {
                'node_id': info.node_id,
                'registered_at': info.registered_at,
                'last_seen_at': info.last_seen_at,
                'total_received': info.total_received,
            }
            for rid, info in self._readers.items()
        }
```

### RaySender

```python
import logging

logger = logging.getLogger(__name__)


class RaySender(Generic[T]):
    """Distributed sender with ref-counted registration."""

    __slots__ = ('_actor', '_capacity', '_closed', '_registered')

    def __init__(self, actor: ray.actor.ActorHandle, capacity: Optional[int]) -> None:
        self._actor = actor
        self._capacity = capacity
        self._closed = False
        self._registered = False

    async def _ensure_registered(self) -> None:
        if self._registered:
            return
        try:
            status = await self._actor.register_sender.remote()
        except ray.exceptions.RayError as e:
            logger.warning('Ray error registering sender: %s', e)
            self._closed = True
            raise ChannelClosed().to_exception() from e

        if status == 'closed':
            self._closed = True
            raise ChannelClosed().to_exception()
        self._registered = True

    async def send(self, value: T) -> None:
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()

        try:
            status = await self._actor.put.remote(value)
        except ray.exceptions.RayError as e:
            logger.warning('Ray error in send: %s', e)
            self._closed = True
            raise ChannelClosed().to_exception() from e

        if status == 'ok':
            return
        if status == 'full':
            raise ChannelFull(self._capacity or 0).to_exception()
        if status == 'closed':
            self._closed = True
            raise ChannelClosed().to_exception()

    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        if self._closed:
            return Err(ChannelClosed())
        await self._ensure_registered()

        try:
            status = await self._actor.put_nowait.remote(value)
        except ray.exceptions.RayError:
            return Err(ChannelClosed())

        if status == 'ok':
            return Ok(None)
        if status == 'full':
            return Err(ChannelFull(self._capacity or 0))
        return Err(ChannelClosed())

    async def send_batch(self, values: List[T]) -> None:
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()

        try:
            status = await self._actor.put_batch.remote(values)
        except ray.exceptions.RayError as e:
            logger.warning('Ray error in send_batch: %s', e)
            self._closed = True
            raise ChannelClosed().to_exception() from e

        if status == 'ok':
            return
        if status == 'full':
            raise ChannelFull(self._capacity or 0).to_exception()
        if status == 'closed':
            self._closed = True
            raise ChannelClosed().to_exception()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._registered:
            return
        try:
            await self._actor.deregister_sender.remote()
        except ray.exceptions.RayError:
            pass

    def clone(self) -> RaySender[T]:
        return RaySender(self._actor, self._capacity)
```

### RayReceiver

```python
class RayReceiver(Generic[T]):
    """Distributed receiver with ref-counted registration and node tracking."""

    __slots__ = ('_actor', '_capacity', '_closed', '_registered', '_reader_id', '_node_id')

    def __init__(self, actor: ray.actor.ActorHandle, capacity: Optional[int]) -> None:
        self._actor = actor
        self._capacity = capacity
        self._closed = False
        self._registered = False
        self._reader_id: str = uuid.uuid4().hex
        self._node_id: Optional[str] = None

    def _get_node_id(self) -> str:
        if self._node_id is None:
            ctx = ray.get_runtime_context()
            self._node_id = ctx.get_node_id()
        return self._node_id

    async def _ensure_registered(self) -> None:
        if self._registered:
            return
        node_id = self._get_node_id()
        try:
            status = await self._actor.register_receiver.remote(self._reader_id, node_id)
        except ray.exceptions.RayError as e:
            logger.warning('Ray error registering receiver: %s', e)
            self._closed = True
            raise ChannelClosed().to_exception() from e

        if status == 'closed':
            self._closed = True
            raise ChannelClosed().to_exception()
        self._registered = True

    async def recv(self, *, timeout: Optional[float] = None) -> T:
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()

        try:
            status, value = await self._actor.get.remote(
                timeout=timeout,
                reader_id=self._reader_id,
            )
        except ray.exceptions.RayError as e:
            logger.warning('Ray error in recv: %s', e)
            self._closed = True
            raise ChannelClosed().to_exception() from e

        if status == 'ok':
            return value
        if status == 'empty':
            raise ChannelEmpty().to_exception()
        if status == 'closed':
            self._closed = True
            raise ChannelClosed().to_exception()
        raise RuntimeError(f'Unexpected status: {status}')

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        if self._closed:
            return Err(ChannelClosed())
        await self._ensure_registered()

        try:
            status, value = await self._actor.get_nowait.remote(reader_id=self._reader_id)
        except ray.exceptions.RayError:
            return Err(ChannelClosed())

        if status == 'ok':
            return Ok(value)
        if status == 'empty':
            return Err(ChannelEmpty())
        return Err(ChannelClosed())

    async def recv_batch(self, max_items: int, *, timeout: Optional[float] = None) -> List[T]:
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()

        try:
            status, values = await self._actor.get_batch.remote(
                max_items,
                timeout=timeout,
                reader_id=self._reader_id,
            )
        except ray.exceptions.RayError as e:
            logger.warning('Ray error in recv_batch: %s', e)
            self._closed = True
            raise ChannelClosed().to_exception() from e

        if status == 'ok':
            return values
        if status == 'empty':
            return []
        if status == 'closed':
            self._closed = True
            raise ChannelClosed().to_exception()
        raise RuntimeError(f'Unexpected status: {status}')

    def __aiter__(self) -> RayReceiver[T]:
        return self

    async def __anext__(self) -> T:
        try:
            return await self.recv()
        except Exception:
            raise StopAsyncIteration from None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._registered:
            return
        try:
            await self._actor.deregister_receiver.remote(self._reader_id)
        except ray.exceptions.RayError:
            pass

    def clone(self) -> RayReceiver[T]:
        return RayReceiver(self._actor, self._capacity)
```

______________________________________________________________________

## ReferenceChannel for Large Payloads

```python
# reference_channel.py


class RayReferenceSender(Generic[T]):
    """Wraps RaySender[ObjectRef] to avoid repeated serialization.

    Uses ray.put() on producer side. Ownership: producer's worker owns
    the ObjectRef; if it dies, object may be lost.
    """

    def __init__(self, inner: RaySender[ray.ObjectRef]) -> None:
        self._inner = inner

    async def send(self, value: T) -> None:
        ref = ray.put(value)
        await self._inner.send(ref)

    async def send_batch(self, values: List[T]) -> None:
        refs = [ray.put(v) for v in values]
        await self._inner.send_batch(refs)

    async def close(self) -> None:
        await self._inner.close()

    def clone(self) -> RayReferenceSender[T]:
        return RayReferenceSender(self._inner.clone())


class RayReferenceReceiver(Generic[T]):
    """Receiver counterpart for ReferenceChannel."""

    def __init__(self, inner: RayReceiver[ray.ObjectRef]) -> None:
        self._inner = inner

    async def recv(self) -> T:
        ref = await self._inner.recv()
        return ray.get(ref)

    async def recv_batch(self, max_items: int) -> List[T]:
        refs = await self._inner.recv_batch(max_items)
        return ray.get(refs)  # Efficient batch get

    async def close(self) -> None:
        await self._inner.close()

    def clone(self) -> RayReferenceReceiver[T]:
        return RayReferenceReceiver(self._inner.clone())
```

**Usage:**

```python
# Create channel storing ObjectRefs
tx_raw, rx_raw = await channel[ray.ObjectRef](
    capacity=1000,
    distributed=True,
    name='large_payloads',
)

ref_tx = RayReferenceSender(tx_raw)
ref_rx = RayReferenceReceiver(rx_raw)

await ref_tx.send(huge_numpy_array)
value = await ref_rx.recv()
```

______________________________________________________________________

## Supervisor Pattern

```python
# supervisor.py

from dataclasses import asdict


@ray.remote
class ChannelSupervisor:
    """Owns and monitors multiple channels; manages checkpointing."""

    def __init__(self) -> None:
        self._channels: Dict[str, ray.actor.ActorHandle] = {}
        self._checkpoints: Dict[str, ChannelCheckpoint] = {}

    async def create_channel(
        self,
        name: str,
        capacity: int = 10000,
        unbounded: bool = False,
    ) -> str:
        if name in self._channels:
            return 'exists'
        actor = RayChannelActor.options(
            name=f'channel_{name}',
            lifetime='detached',
            get_if_exists=True,
        ).remote(capacity=capacity, unbounded=unbounded)
        self._channels[name] = actor
        return 'ok'

    async def get_checkpoint(self, name: str) -> Optional[dict]:
        actor = self._channels.get(name)
        if actor is None:
            return None
        state: ChannelCheckpoint = await actor.get_checkpoint_state.remote()
        self._checkpoints[name] = state
        return asdict(state)

    async def restore_from_checkpoint(self, name: str, state_dict: dict) -> str:
        actor = self._channels.get(name)
        if actor is None:
            return 'missing'
        state = ChannelCheckpoint(**state_dict)
        await actor.apply_checkpoint_state.remote(state)
        self._checkpoints[name] = state
        return 'ok'

    async def delete_channel(self, name: str) -> str:
        actor = self._channels.pop(name, None)
        if actor is None:
            return 'missing'
        ray.kill(actor, no_restart=True)
        return 'ok'

    def list_channels(self) -> List[str]:
        return list(self._channels.keys())
```

______________________________________________________________________

## Reader Pool Pattern

```python
# pools.py


@ray.remote
class ChannelReader:
    """Worker that consumes from a channel."""

    def __init__(self, channel_name: str, namespace: str = 'klaw') -> None:
        self._channel_name = channel_name
        self._namespace = namespace
        self._rx: Optional[RayReceiver] = None

    async def start(self) -> None:
        result = await get_channel(self._channel_name, namespace=self._namespace)
        if result is None:
            raise ValueError(f'Channel {self._channel_name} not found')
        _, self._rx = result
        async for item in self._rx:
            await self.process(item)

    async def process(self, item: Any) -> None:
        # Override in subclass
        pass


@ray.remote
class ReaderPoolController:
    """Manages a pool of readers for load balancing."""

    def __init__(self, channel_name: str, initial_size: int) -> None:
        self._channel_name = channel_name
        self._readers: List[ray.actor.ActorHandle] = []
        for _ in range(initial_size):
            self._spawn_reader()

    def _spawn_reader(self) -> None:
        r = ChannelReader.options(max_concurrency=1).remote(self._channel_name)
        self._readers.append(r)
        r.start.remote()

    async def scale(self, delta: int) -> None:
        if delta > 0:
            for _ in range(delta):
                self._spawn_reader()
        elif delta < 0:
            for _ in range(min(-delta, len(self._readers))):
                r = self._readers.pop()
                ray.kill(r, no_restart=True)

    def num_readers(self) -> int:
        return len(self._readers)
```

______________________________________________________________________

## Factory Functions

```python
# factory.py


async def channel(
    capacity: int = 10000,
    *,
    distributed: bool = False,
    unbounded: bool = False,
    name: Optional[str] = None,
    namespace: str = 'klaw',
) -> Tuple[RaySender[T], RayReceiver[T]]:
    if not distributed:
        # LocalChannel path
        return await local_channel(capacity=capacity, unbounded=unbounded)

    if unbounded:
        logger.warning('Creating unbounded Ray channel; may cause OOM if consumers are slow.')

    if name is not None:
        actor = RayChannelActor.options(
            name=f'channel_{name}',
            namespace=namespace,
            lifetime='detached',
            get_if_exists=True,
        ).remote(capacity=capacity, unbounded=unbounded)
    else:
        actor = RayChannelActor.remote(capacity=capacity, unbounded=unbounded)

    cap = None if unbounded else capacity
    tx: RaySender[T] = RaySender(actor, cap)
    rx: RayReceiver[T] = RayReceiver(actor, cap)

    await tx._ensure_registered()
    await rx._ensure_registered()
    return tx, rx


async def get_channel(
    name: str,
    *,
    namespace: str = 'klaw',
) -> Optional[Tuple[RaySender[T], RayReceiver[T]]]:
    try:
        actor = ray.get_actor(f'channel_{name}', namespace=namespace)
    except ValueError:
        return None

    try:
        cap = await actor.get_capacity.remote()
    except ray.exceptions.RayError:
        return None

    tx: RaySender[T] = RaySender(actor, cap)
    rx: RayReceiver[T] = RayReceiver(actor, cap)
    await tx._ensure_registered()
    await rx._ensure_registered()
    return tx, rx


def delete_channel(name: str, *, namespace: str = 'klaw') -> bool:
    try:
        actor = ray.get_actor(f'channel_{name}', namespace=namespace)
    except ValueError:
        return False
    ray.kill(actor, no_restart=True)
    return True


def list_channels(*, namespace: str = 'klaw') -> List[str]:
    all_actors = ray.util.list_named_actors(all_namespaces=True)
    prefix = 'channel_'
    return [
        info['name'][len(prefix) :]
        for info in all_actors
        if info['namespace'] == namespace and info['name'].startswith(prefix)
    ]
```

______________________________________________________________________

## Test Strategy

### Unit Tests (Local Mode)

```python
@pytest.fixture
def ray_init():
    ray.init(local_mode=True)
    yield
    ray.shutdown()
```

1. **Basic send/recv** — ordering, close semantics
1. **Clone semantics** — independent lifecycle, ref counting
1. **All senders/receivers closed** — proper channel closure
1. **Batch operations** — atomicity, capacity enforcement
1. **Named channel retrieval** — get_channel returns working handles
1. **Stats + backpressure** — queue_size, high_watermark
1. **Node-aware registration** — per_node_receivers counts

### Distributed Tests

1. **Cross-process communication** — remote sender, local receiver
1. **Many producers / many consumers** — all messages consumed exactly once
1. **Named channel across jobs** — different drivers attach to same channel
1. **Fault tolerance** — kill actor, verify restart behavior
1. **ReferenceChannel** — large payloads, memory efficiency

### Reader Pool Tests

1. **Spawn pool** — verify all readers process items
1. **Scale up/down** — dynamic pool sizing
1. **Load distribution** — no reader starvation

______________________________________________________________________

## Performance Considerations

### Batch Operations

- Use `put_batch`/`get_batch` for high throughput
- Aim for 1s+ method duration to amortize overhead

### Backpressure

- Use `capacity` and `queue_size` from stats
- Implement admission control in upstream stages
- Poll `get_stats()` periodically, not per-message

### Large Payloads

- Use ReferenceChannel for payloads >100KB
- Object lifetime bound to `ray.put` owner

### Node-Aware Optimization

- Use `per_node_receivers` for observability
- Future: per-node channels with global router

### Fault Tolerance

- `max_restarts=4` + `max_task_retries=-1` for resilience
- Checkpoint hooks for application-level recovery

______________________________________________________________________

## Future Considerations (When Needed)

1. **Sharded channels** — multiple actors per logical channel with consistent hashing
1. **RDT** — when stable, for GPU-heavy workloads
1. **Per-node buffering** — integrate with Ray experimental channels
1. **Exactly-once delivery** — persistent logs across failures
