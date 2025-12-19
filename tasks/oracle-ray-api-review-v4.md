# Oracle Ray API Review v4: Modular Architecture

Reorganized architecture with Ray logic isolated in `channels/ray/` submodule.

______________________________________________________________________

## TL;DR

- Move all Ray-specific logic into `channels/ray/`
- Keep top-level `channels/` backend-agnostic with protocols, stats, and factories
- Ray is an optional dependency (imported only when `backend="ray"`)
- New `ReferenceSender`/`ReferenceReceiver` protocols for large payloads

**Effort:** L–M (0.5–1.5 days)

______________________________________________________________________

## Module Structure

```
klaw_core/runtime/channels/
├── __init__.py              # Public exports (protocols, factories)
├── protocols.py             # Sender, Receiver, ReferenceSender, ReferenceReceiver
├── stats.py                 # ChannelStats, ChannelCheckpoint (backend-agnostic)
├── errors.py                # ChannelClosed, ChannelFull, ChannelEmpty
├── local.py                 # LocalSender/LocalReceiver
├── oneshot.py               # OneshotSender/OneshotReceiver
├── broadcast.py             # BroadcastSender/BroadcastReceiver
├── watch.py                 # WatchSender/WatchReceiver
├── select.py                # select() function
├── factory.py               # Backend-agnostic channel(), get_channel(), etc.
│
└── ray/                     # RAY-SPECIFIC (only place that imports ray)
    ├── __init__.py          # Ray public surface
    ├── actor.py             # RayChannelActor, ReaderInfo
    ├── core.py              # RaySender, RayReceiver
    ├── reference.py         # RayReferenceSender, RayReferenceReceiver
    ├── supervisor.py        # ChannelSupervisor
    ├── pools.py             # ChannelReader, ReaderPoolController
    └── factory.py           # ray_channel(), get_ray_channel(), etc.
```

### Key Constraints

- **Only `channels/ray/` imports `ray`**
- **`channels/factory.py` does lazy import** when Ray backend requested
- **Ray code imports from main module** for protocols/types only

______________________________________________________________________

## Backend-Agnostic Protocols

### protocols.py

```python
from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, TypeVar, List

from klaw_core.result import Result
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = [
    'Sender',
    'Receiver',
    'ReferenceSender',
    'ReferenceReceiver',
]

T = TypeVar('T')


class Sender(Protocol[T]):
    """Protocol for sending values into a channel."""

    @abstractmethod
    async def send(self, value: T) -> None:
        """Send a value, blocking if at capacity."""
        ...

    @abstractmethod
    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        """Non-blocking send."""
        ...

    @abstractmethod
    def clone(self) -> Sender[T]:
        """Clone for multi-producer use."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close this sender."""
        ...


class Receiver(Protocol[T]):
    """Protocol for receiving values from a channel."""

    @abstractmethod
    async def recv(self) -> T:
        """Receive next value, blocking if empty."""
        ...

    @abstractmethod
    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        """Non-blocking receive."""
        ...

    @abstractmethod
    def clone(self) -> Receiver[T]:
        """Clone for multi-consumer use."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close this receiver."""
        ...

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[T]:
        """Async iteration support."""
        ...

    @abstractmethod
    async def __anext__(self) -> T:
        """Next value for async for loop."""
        ...


class ReferenceSender(Sender[T], Protocol[T]):
    """Sender that uses backend-specific references for large payloads.

    Semantics same as Sender[T], but implementations may store
    backend-native references (Ray ObjectRefs, Redis keys, etc.)
    """

    @abstractmethod
    async def send_batch(self, values: List[T]) -> None:
        """Batch send for efficiency."""
        ...


class ReferenceReceiver(Receiver[T], Protocol[T]):
    """Receiver counterpart for ReferenceSender."""

    @abstractmethod
    async def recv_batch(self, max_items: int) -> List[T]:
        """Batch receive for efficiency."""
        ...
```

______________________________________________________________________

## Backend-Agnostic Stats

### stats.py

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class ChannelStats:
    """Backend-agnostic channel statistics.

    Backends attach additional info via backend_extras.
    """

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
    backend_extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ChannelCheckpoint:
    """Lightweight checkpoint metadata for fault tolerance."""

    created_at: float
    total_sent: int
    total_received: int
    senders_closed: bool
    receivers_closed: bool
```

______________________________________________________________________

## Ray Submodule

### ray/actor.py

```python
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from queue import Empty, Full
from typing import Any, Dict, List, Optional, Set, Tuple, TypeVar

import ray

from klaw_core.runtime.channels.stats import ChannelStats, ChannelCheckpoint

T = TypeVar('T')


@dataclass
class ReaderInfo:
    """Per-reader tracking information for Ray backend."""

    reader_id: str
    node_id: str
    registered_at: float
    last_seen_at: float
    total_received: int = 0


@ray.remote(
    max_restarts=4,
    max_task_retries=-1,
)
class RayChannelActor:
    """Control plane for distributed channel with ref-counted lifecycle.

    All methods return status codes:
    - 'ok'     : success
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
        self._node_to_readers: Dict[str, Set[str]] = {}

        # Stats
        self._created_at: float = time.time()
        self._total_sent: int = 0
        self._total_received: int = 0
        self._high_watermark: int = 0

    # ─────────────────────────────────────────────────────────────────
    # Registration
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
            readers = self._node_to_readers.get(node_id)
            if readers is not None:
                readers.discard(reader_id)
                if not readers:
                    del self._node_to_readers[node_id]
        if self._receiver_count > 0:
            self._receiver_count -= 1
        if self._receiver_count == 0:
            self._receivers_closed = True
        return 'ok'

    # ─────────────────────────────────────────────────────────────────
    # Data plane (single-item)
    # ─────────────────────────────────────────────────────────────────

    async def put(self, item: Any, timeout: Optional[float] = None) -> str:
        if self._receivers_closed:
            return 'closed'
        try:
            await asyncio.wait_for(self._queue.put(item), timeout)
        except asyncio.TimeoutError:
            return 'full'
        self._total_sent += 1
        self._update_watermark()
        return 'ok'

    def put_nowait(self, item: Any) -> str:
        if self._receivers_closed:
            return 'closed'
        try:
            self._queue.put_nowait(item)
        except Full:
            return 'full'
        self._total_sent += 1
        self._update_watermark()
        return 'ok'

    async def get(
        self,
        timeout: Optional[float] = None,
        reader_id: Optional[str] = None,
    ) -> Tuple[str, Any]:
        if self._senders_closed and self._queue.empty():
            return ('closed', None)
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            if self._senders_closed:
                return ('closed', None)
            return ('empty', None)
        self._total_received += 1
        self._update_reader_stats(reader_id)
        return ('ok', item)

    def get_nowait(self, reader_id: Optional[str] = None) -> Tuple[str, Any]:
        if self._senders_closed and self._queue.empty():
            return ('closed', None)
        try:
            item = self._queue.get_nowait()
        except Empty:
            if self._senders_closed:
                return ('closed', None)
            return ('empty', None)
        self._total_received += 1
        self._update_reader_stats(reader_id)
        return ('ok', item)

    # ─────────────────────────────────────────────────────────────────
    # Batch operations
    # ─────────────────────────────────────────────────────────────────

    def put_nowait_batch(self, items: List[Any]) -> str:
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
        self._update_watermark()
        return 'ok'

    async def put_batch(self, items: List[Any], timeout: Optional[float] = None) -> str:
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
        self._update_watermark()
        return 'ok'

    async def get_batch(
        self,
        max_items: int,
        timeout: Optional[float] = None,
        reader_id: Optional[str] = None,
    ) -> Tuple[str, List[Any]]:
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
        per_node = {n: len(r) for n, r in self._node_to_readers.items()}
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
            backend_extras={'per_node_receivers': per_node},
        )

    def get_checkpoint_state(self) -> ChannelCheckpoint:
        return ChannelCheckpoint(
            created_at=self._created_at,
            total_sent=self._total_sent,
            total_received=self._total_received,
            senders_closed=self._senders_closed,
            receivers_closed=self._receivers_closed,
        )

    def apply_checkpoint_state(self, state: ChannelCheckpoint) -> str:
        self._created_at = state.created_at
        self._total_sent = state.total_sent
        self._total_received = state.total_received
        self._senders_closed = state.senders_closed
        self._receivers_closed = state.receivers_closed
        return 'ok'

    def get_capacity(self) -> Optional[int]:
        return self._capacity

    def is_closed(self) -> bool:
        return self._senders_closed and self._receivers_closed and self._queue.empty()

    def get_reader_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            rid: {
                'node_id': info.node_id,
                'registered_at': info.registered_at,
                'last_seen_at': info.last_seen_at,
                'total_received': info.total_received,
            }
            for rid, info in self._readers.items()
        }

    # ─────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────

    def _update_watermark(self) -> None:
        qsize = self._queue.qsize()
        if qsize > self._high_watermark:
            self._high_watermark = qsize

    def _update_reader_stats(self, reader_id: Optional[str]) -> None:
        if reader_id and reader_id in self._readers:
            info = self._readers[reader_id]
            info.last_seen_at = time.time()
            info.total_received += 1
```

### ray/core.py

```python
from __future__ import annotations

import logging
import uuid
from typing import Generic, List, Optional, TypeVar

import ray

from klaw_core.result import Result, Ok, Err
from klaw_core.runtime.channels.protocols import Sender, Receiver
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull

from .actor import RayChannelActor

logger = logging.getLogger(__name__)
T = TypeVar('T')


class RaySender(Generic[T]):
    """Ray-backed distributed Sender implementation."""

    __slots__ = ('_actor', '_capacity', '_registered', '_closed')

    def __init__(self, actor: ray.actor.ActorHandle, capacity: Optional[int]) -> None:
        self._actor = actor
        self._capacity = capacity
        self._registered = False
        self._closed = False

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


class RayReceiver(Generic[T]):
    """Ray-backed distributed Receiver implementation."""

    __slots__ = ('_actor', '_capacity', '_registered', '_closed', '_reader_id', '_node_id')

    def __init__(self, actor: ray.actor.ActorHandle, capacity: Optional[int]) -> None:
        self._actor = actor
        self._capacity = capacity
        self._registered = False
        self._closed = False
        self._reader_id: str = uuid.uuid4().hex
        self._node_id: Optional[str] = None

    def _get_node_id(self) -> str:
        if self._node_id is None:
            self._node_id = ray.get_runtime_context().get_node_id()
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

    async def recv(self, timeout: Optional[float] = None) -> T:
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

    async def recv_batch(self, max_items: int, timeout: Optional[float] = None) -> List[T]:
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

### ray/reference.py

```python
from __future__ import annotations

from typing import Generic, List, TypeVar

import ray

from klaw_core.result import Result, Ok
from klaw_core.runtime.channels.protocols import ReferenceSender, ReferenceReceiver
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull

from .core import RaySender, RayReceiver

T = TypeVar('T')


class RayReferenceSender(Generic[T]):
    """Reference-based sender using Ray's object store."""

    def __init__(self, inner: RaySender[ray.ObjectRef]) -> None:
        self._inner = inner

    async def send(self, value: T) -> None:
        ref = ray.put(value)
        await self._inner.send(ref)

    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        ref = ray.put(value)
        return await self._inner.try_send(ref)

    async def send_batch(self, values: List[T]) -> None:
        refs = [ray.put(v) for v in values]
        await self._inner.send_batch(refs)

    async def close(self) -> None:
        await self._inner.close()

    def clone(self) -> RayReferenceSender[T]:
        return RayReferenceSender(self._inner.clone())


class RayReferenceReceiver(Generic[T]):
    """Reference-based receiver using Ray's object store."""

    def __init__(self, inner: RayReceiver[ray.ObjectRef]) -> None:
        self._inner = inner

    async def recv(self) -> T:
        ref = await self._inner.recv()
        return ray.get(ref)

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        result = await self._inner.try_recv()
        if result.is_ok():
            ref = result.unwrap()
            return Ok(ray.get(ref))
        return result

    async def recv_batch(self, max_items: int) -> List[T]:
        refs = await self._inner.recv_batch(max_items)
        return ray.get(refs)

    def __aiter__(self) -> RayReferenceReceiver[T]:
        return self

    async def __anext__(self) -> T:
        return await self.recv()

    async def close(self) -> None:
        await self._inner.close()

    def clone(self) -> RayReferenceReceiver[T]:
        return RayReferenceReceiver(self._inner.clone())
```

### ray/supervisor.py

```python
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Optional

import ray

from klaw_core.runtime.channels.stats import ChannelCheckpoint
from .actor import RayChannelActor


@ray.remote
class ChannelSupervisor:
    """Owns and monitors multiple Ray channels; manages checkpointing."""

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

### ray/pools.py

```python
from __future__ import annotations

from typing import Any, List, Optional

import ray

from .core import RayReceiver
from .factory import get_ray_channel


@ray.remote
class ChannelReader:
    """Worker that consumes from a Ray channel."""

    def __init__(self, channel_name: str, namespace: str = 'klaw') -> None:
        self._channel_name = channel_name
        self._namespace = namespace
        self._rx: Optional[RayReceiver[Any]] = None

    async def start(self) -> None:
        result = await get_ray_channel(self._channel_name, namespace=self._namespace)
        if result is None:
            raise ValueError(f'Channel {self._channel_name} not found')
        _, self._rx = result
        async for item in self._rx:
            await self.process(item)

    async def process(self, item: Any) -> None:
        pass  # Override in subclass


@ray.remote
class ReaderPoolController:
    """Manages a pool of ChannelReader instances for load balancing."""

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

### ray/factory.py

```python
from __future__ import annotations

import logging
from typing import List, Optional, Tuple, TypeVar

import ray

from .actor import RayChannelActor
from .core import RaySender, RayReceiver

logger = logging.getLogger(__name__)
T = TypeVar('T')


async def ray_channel(
    capacity: int = 10000,
    *,
    unbounded: bool = False,
    name: Optional[str] = None,
    namespace: str = 'klaw',
) -> Tuple[RaySender[T], RayReceiver[T]]:
    """Create a Ray-backed distributed channel."""
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


async def get_ray_channel(
    name: str,
    *,
    namespace: str = 'klaw',
) -> Optional[Tuple[RaySender[T], RayReceiver[T]]]:
    """Retrieve an existing named Ray channel."""
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


def delete_ray_channel(name: str, *, namespace: str = 'klaw') -> bool:
    """Delete a named Ray channel."""
    try:
        actor = ray.get_actor(f'channel_{name}', namespace=namespace)
    except ValueError:
        return False
    ray.kill(actor, no_restart=True)
    return True


def list_ray_channels(*, namespace: str = 'klaw') -> List[str]:
    """List all named Ray channels in namespace."""
    all_actors = ray.util.list_named_actors(all_namespaces=True)
    prefix = 'channel_'
    return [
        info['name'][len(prefix) :]
        for info in all_actors
        if info['namespace'] == namespace and info['name'].startswith(prefix)
    ]
```

### ray/__init__.py

```python
from .core import RaySender, RayReceiver
from .reference import RayReferenceSender, RayReferenceReceiver
from .factory import (
    ray_channel,
    get_ray_channel,
    delete_ray_channel,
    list_ray_channels,
)
from .supervisor import ChannelSupervisor
from .pools import ChannelReader, ReaderPoolController

__all__ = [
    'RaySender',
    'RayReceiver',
    'RayReferenceSender',
    'RayReferenceReceiver',
    'ray_channel',
    'get_ray_channel',
    'delete_ray_channel',
    'list_ray_channels',
    'ChannelSupervisor',
    'ChannelReader',
    'ReaderPoolController',
]
```

______________________________________________________________________

## Backend-Agnostic Factory

### factory.py

```python
from __future__ import annotations

from typing import Literal, Optional, Tuple, TypeVar, List

from klaw_core.runtime.channels.protocols import Sender, Receiver

T = TypeVar('T')
Backend = Literal['local', 'ray']


async def channel(
    capacity: int = 10000,
    *,
    distributed: Optional[bool] = None,
    backend: Optional[Backend] = None,
    unbounded: bool = False,
    name: Optional[str] = None,
    namespace: str = 'klaw',
) -> Tuple[Sender[T], Receiver[T]]:
    """Create a channel with pluggable backend.

    Args:
        capacity: Maximum in-flight messages.
        distributed: Backwards-compat; True implies backend="ray".
        backend: Explicit backend choice ("local" | "ray").
        unbounded: If True, ignore capacity.
        name: Optional channel name (Ray only).
        namespace: Backend-specific namespace.
    """
    if backend is None:
        backend = 'ray' if distributed else 'local'

    if backend == 'local':
        from . import local

        return await local.channel(capacity=capacity, unbounded=unbounded)

    if backend == 'ray':
        try:
            from .ray.factory import ray_channel
        except ModuleNotFoundError as exc:
            raise RuntimeError("Ray backend requested but 'ray' is not installed.") from exc

        return await ray_channel(
            capacity=capacity,
            unbounded=unbounded,
            name=name,
            namespace=namespace,
        )

    raise ValueError(f'Unknown backend: {backend!r}')


async def get_channel(
    name: str,
    *,
    backend: Backend = 'ray',
    namespace: str = 'klaw',
) -> Optional[Tuple[Sender[T], Receiver[T]]]:
    """Retrieve an existing named channel."""
    if backend != 'ray':
        raise NotImplementedError("get_channel() only implemented for backend='ray'")

    try:
        from .ray.factory import get_ray_channel
    except ModuleNotFoundError as exc:
        raise RuntimeError('Ray not installed.') from exc

    return await get_ray_channel(name, namespace=namespace)


def delete_channel(name: str, *, backend: Backend = 'ray', namespace: str = 'klaw') -> bool:
    """Delete a named channel."""
    if backend != 'ray':
        raise NotImplementedError("delete_channel() only implemented for backend='ray'")

    try:
        from .ray.factory import delete_ray_channel
    except ModuleNotFoundError as exc:
        raise RuntimeError('Ray not installed.') from exc

    return delete_ray_channel(name, namespace=namespace)


def list_channels(*, backend: Backend = 'ray', namespace: str = 'klaw') -> List[str]:
    """List named channels."""
    if backend != 'ray':
        raise NotImplementedError("list_channels() only implemented for backend='ray'")

    try:
        from .ray.factory import list_ray_channels
    except ModuleNotFoundError as exc:
        raise RuntimeError('Ray not installed.') from exc

    return list_ray_channels(namespace=namespace)
```

______________________________________________________________________

## Main Package __init__.py

```python
"""Channels: multi-producer multi-consumer, oneshot, broadcast, watch, select."""

from klaw_core.runtime.channels.factory import (
    channel,
    get_channel,
    delete_channel,
    list_channels,
)
from klaw_core.runtime.channels.local import LocalReceiver, LocalSender
from klaw_core.runtime.channels.oneshot import OneshotReceiver, OneshotSender
from klaw_core.runtime.channels.broadcast import BroadcastReceiver, BroadcastSender
from klaw_core.runtime.channels.watch import WatchReceiver, WatchSender
from klaw_core.runtime.channels.protocols import (
    Receiver,
    Sender,
    ReferenceSender,
    ReferenceReceiver,
)
from klaw_core.runtime.channels.stats import ChannelStats, ChannelCheckpoint

__all__ = [
    # Factories
    'channel',
    'get_channel',
    'delete_channel',
    'list_channels',
    # Protocols
    'Sender',
    'Receiver',
    'ReferenceSender',
    'ReferenceReceiver',
    # Stats
    'ChannelStats',
    'ChannelCheckpoint',
    # Local implementations
    'LocalSender',
    'LocalReceiver',
    'OneshotSender',
    'OneshotReceiver',
    'BroadcastSender',
    'BroadcastReceiver',
    'WatchSender',
    'WatchReceiver',
]
```

**Note:** Ray types (`RaySender`, `RayReceiver`, etc.) are NOT exported from the main package. Users who need Ray-specific APIs import from `klaw_core.runtime.channels.ray`.

______________________________________________________________________

## Import Flow

```
                   ┌──────────────────────────────┐
                   │    User Code                 │
                   └──────────────┬───────────────┘
                                  │
                   ┌──────────────▼───────────────┐
                   │    channels/__init__.py      │
                   │    (no ray import)           │
                   └──────────────┬───────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
┌─────────▼─────────┐   ┌────────▼────────┐   ┌──────────▼──────────┐
│ channels/local.py │   │ channels/       │   │ channels/ray/       │
│ (no ray)          │   │ factory.py      │   │ (imports ray)       │
└───────────────────┘   │ (lazy import)   │   └─────────────────────┘
                        └─────────────────┘
```

______________________________________________________________________

## Test Strategy

### Unit Tests (no Ray)

- Test protocols, stats, local channels without Ray installed
- `pytest -m "not ray"`

### Ray Tests

- Mark with `@pytest.mark.ray`
- Use `ray.init(local_mode=True)` fixture

### Test Files

```
tests/runtime/channels/
├── test_protocols.py          # Protocol compliance
├── test_stats.py              # Stats dataclasses
├── test_local.py              # LocalSender/Receiver
├── test_factory.py            # Factory backend dispatch
└── ray/
    ├── test_actor.py          # RayChannelActor
    ├── test_core.py           # RaySender/Receiver
    ├── test_reference.py      # RayReferenceSender/Receiver
    ├── test_supervisor.py     # ChannelSupervisor
    ├── test_pools.py          # ReaderPoolController
    └── test_distributed.py    # Cross-process tests
```

______________________________________________________________________

## Summary

| Component           | Location                     | Imports Ray? |
| ------------------- | ---------------------------- | ------------ |
| Protocols           | `channels/protocols.py`      | No           |
| Stats               | `channels/stats.py`          | No           |
| Local impl          | `channels/local.py`          | No           |
| Factory             | `channels/factory.py`        | Lazy         |
| Ray actor           | `channels/ray/actor.py`      | Yes          |
| Ray sender/receiver | `channels/ray/core.py`       | Yes          |
| Ray reference       | `channels/ray/reference.py`  | Yes          |
| Ray supervisor      | `channels/ray/supervisor.py` | Yes          |
| Ray pools           | `channels/ray/pools.py`      | Yes          |
| Ray factory         | `channels/ray/factory.py`    | Yes          |

**Key benefits:**

- Ray is optional dependency
- Clean separation of concerns
- Future backends can follow same pattern
- No import cycles
