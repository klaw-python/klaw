# Oracle Recommendations: RayChannel Implementation

Based on review of the Ray API research and existing klaw-runtime protocols.

______________________________________________________________________

## TL;DR

Implement a **`RayChannelActor`** control plane that manages ref-counted sender/receiver registration, enabling true distributed close semantics matching LocalChannel behavior. This adds complexity but is necessary for production use cases where channels are passed widely across workers/nodes.

**Effort:** L (1–2 days) for full ref-counted semantics + named channel support.

______________________________________________________________________

## 1. Why the Advanced Path

The simple approach (closing any sender/receiver shuts down the whole queue) breaks when:

- Channels are passed to multiple Ray tasks/actors
- Senders/receivers are cloned and distributed across nodes
- You can't enforce "don't close early" discipline across distributed code
- Late-joining workers need to connect to existing channels

**Your use case demands:**

- True ref-counted close semantics (channel closes only when ALL senders/receivers close)
- Named channels for cross-process discovery
- Consistent behavior between LocalChannel and RayChannel

______________________________________________________________________

## 2. Architecture: RayChannelActor Control Plane

```
┌─────────────────────────────────────────────────────────────┐
│                    RayChannelActor                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - queue: Queue                                      │   │
│  │  - sender_count: int                                 │   │
│  │  - receiver_count: int                               │   │
│  │  - closed: bool                                      │   │
│  │  - name: str | None                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Methods:                                                   │
│  - register_sender() -> sender_id                          │
│  - deregister_sender(sender_id)                            │
│  - register_receiver() -> receiver_id                      │
│  - deregister_receiver(receiver_id)                        │
│  - put(item) / put_nowait(item)                            │
│  - get() / get_nowait()                                    │
│  - is_closed() -> bool                                     │
│  - get_stats() -> ChannelStats                             │
└─────────────────────────────────────────────────────────────┘
           │                              │
           ▼                              ▼
    ┌──────────────┐              ┌──────────────┐
    │  RaySender   │              │ RayReceiver  │
    │  - actor_ref │              │  - actor_ref │
    │  - sender_id │              │  - recv_id   │
    │  - capacity  │              │  - capacity  │
    └──────────────┘              └──────────────┘
```

______________________________________________________________________

## 3. Implementation Plan

### 3.1 RayChannelActor (Ray Actor)

```python
@ray.remote
class RayChannelActor:
    """Control plane for distributed channel with ref-counted lifecycle."""

    def __init__(self, capacity: int, unbounded: bool = False) -> None:
        self._maxsize = 0 if unbounded else capacity
        self._capacity = None if unbounded else capacity
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxsize)

        self._sender_count: int = 0
        self._receiver_count: int = 0
        self._senders_closed: bool = False  # All senders deregistered
        self._receivers_closed: bool = False  # All receivers deregistered
        self._next_id: int = 0

    def register_sender(self) -> int:
        """Register a new sender, returns sender_id."""
        if self._senders_closed:
            raise ChannelClosed().to_exception()
        self._sender_count += 1
        self._next_id += 1
        return self._next_id

    def deregister_sender(self, sender_id: int) -> None:
        """Deregister sender. When count hits 0, signal receivers."""
        self._sender_count = max(0, self._sender_count - 1)
        if self._sender_count == 0:
            self._senders_closed = True
            # Signal EOF to waiting receivers (put sentinel or use Event)

    def register_receiver(self) -> int:
        """Register a new receiver, returns receiver_id."""
        if self._receivers_closed:
            raise ChannelClosed().to_exception()
        self._receiver_count += 1
        self._next_id += 1
        return self._next_id

    def deregister_receiver(self, receiver_id: int) -> None:
        """Deregister receiver. When count hits 0, signal senders."""
        self._receiver_count = max(0, self._receiver_count - 1)
        if self._receiver_count == 0:
            self._receivers_closed = True

    async def put(self, item: Any, timeout: float | None = None) -> None:
        """Put item into queue. Raises ChannelClosed if receivers gone."""
        if self._receivers_closed:
            raise ChannelClosed().to_exception()
        try:
            await asyncio.wait_for(self._queue.put(item), timeout)
        except asyncio.TimeoutError:
            raise Full()

    def put_nowait(self, item: Any) -> None:
        """Non-blocking put. Raises Full or ChannelClosed."""
        if self._receivers_closed:
            raise ChannelClosed().to_exception()
        self._queue.put_nowait(item)  # Raises Full if at capacity

    async def get(self, timeout: float | None = None) -> Any:
        """Get item from queue. Raises ChannelClosed if senders gone and empty."""
        if self._senders_closed and self._queue.empty():
            raise ChannelClosed().to_exception()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            if self._senders_closed:
                raise ChannelClosed().to_exception()
            raise Empty()

    def get_nowait(self) -> Any:
        """Non-blocking get. Raises Empty or ChannelClosed."""
        if self._senders_closed and self._queue.empty():
            raise ChannelClosed().to_exception()
        return self._queue.get_nowait()  # Raises Empty if nothing

    def is_closed(self) -> bool:
        return self._senders_closed and self._receivers_closed

    def get_capacity(self) -> int | None:
        return self._capacity

    def qsize(self) -> int:
        return self._queue.qsize()
```

### 3.2 RaySender

```python
class RaySender[T]:
    """Distributed sender with ref-counted registration."""

    def __init__(
        self,
        actor: ray.actor.ActorHandle,  # RayChannelActor
        capacity: int | None,
        sender_id: int | None = None,  # None = needs registration
    ) -> None:
        self._actor = actor
        self._capacity = capacity
        self._sender_id = sender_id
        self._closed = False

    async def _ensure_registered(self) -> None:
        """Lazy registration on first use."""
        if self._sender_id is None:
            self._sender_id = await self._actor.register_sender.remote()

    async def send(self, value: T) -> None:
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()
        try:
            await self._actor.put.remote(value)
        except ray.exceptions.RayError as e:
            raise ChannelClosed().to_exception() from e

    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        if self._closed:
            return Err(ChannelClosed())
        await self._ensure_registered()
        try:
            await self._actor.put_nowait.remote(value)
            return Ok(None)
        except Full:
            return Err(ChannelFull(self._capacity or 0))
        except ray.exceptions.RayError:
            return Err(ChannelClosed())

    def clone(self) -> RaySender[T]:
        """Clone returns new sender sharing same actor, unregistered."""
        return RaySender(self._actor, self._capacity, sender_id=None)

    async def close(self) -> None:
        """Deregister this sender from the channel."""
        if self._closed:
            return
        self._closed = True
        if self._sender_id is not None:
            try:
                await self._actor.deregister_sender.remote(self._sender_id)
            except ray.exceptions.RayError:
                pass  # Actor already dead
```

### 3.3 RayReceiver

```python
class RayReceiver[T]:
    """Distributed receiver with ref-counted registration."""

    def __init__(
        self,
        actor: ray.actor.ActorHandle,
        capacity: int | None,
        receiver_id: int | None = None,
    ) -> None:
        self._actor = actor
        self._capacity = capacity
        self._receiver_id = receiver_id
        self._closed = False

    async def _ensure_registered(self) -> None:
        if self._receiver_id is None:
            self._receiver_id = await self._actor.register_receiver.remote()

    async def recv(self) -> T:
        if self._closed:
            raise ChannelClosed().to_exception()
        await self._ensure_registered()
        try:
            return await self._actor.get.remote()
        except ray.exceptions.RayError as e:
            raise ChannelClosed().to_exception() from e

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        if self._closed:
            return Err(ChannelClosed())
        await self._ensure_registered()
        try:
            value = await self._actor.get_nowait.remote()
            return Ok(value)
        except Empty:
            return Err(ChannelEmpty())
        except ray.exceptions.RayError:
            return Err(ChannelClosed())

    def clone(self) -> RayReceiver[T]:
        return RayReceiver(self._actor, self._capacity, receiver_id=None)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._receiver_id is not None:
            try:
                await self._actor.deregister_receiver.remote(self._receiver_id)
            except ray.exceptions.RayError:
                pass

    def __aiter__(self) -> RayReceiver[T]:
        return self

    async def __anext__(self) -> T:
        try:
            return await self.recv()
        except Exception:  # ChannelClosedError
            raise StopAsyncIteration from None
```

### 3.4 Factory with Named Channel Support

```python
async def channel(
    capacity: int = 10000,
    distributed: bool = False,
    unbounded: bool = False,
    name: str | None = None,
    namespace: str = 'klaw',
) -> tuple[Sender[T], Receiver[T]]:
    if not distributed:
        # Existing LocalChannel path
        ...

    # Distributed path with RayChannelActor
    if name is not None:
        # Try to get existing named channel
        try:
            actor = ray.get_actor(f'channel_{name}', namespace=namespace)
        except ValueError:
            # Doesn't exist, create it
            actor = RayChannelActor.options(
                name=f'channel_{name}',
                namespace=namespace,
                lifetime='detached',
            ).remote(capacity=capacity, unbounded=unbounded)
    else:
        # Anonymous channel
        actor = RayChannelActor.remote(capacity=capacity, unbounded=unbounded)

    cap = None if unbounded else capacity
    tx = RaySender(actor, cap)
    rx = RayReceiver(actor, cap)

    # Pre-register the initial sender/receiver
    await tx._ensure_registered()
    await rx._ensure_registered()

    return tx, rx
```

______________________________________________________________________

## 4. Named Channel Retrieval

```python
async def get_channel(
    name: str,
    namespace: str = 'klaw',
) -> tuple[Sender[T], Receiver[T]] | None:
    """Retrieve an existing named channel."""
    try:
        actor = ray.get_actor(f'channel_{name}', namespace=namespace)
        cap = await actor.get_capacity.remote()
        tx = RaySender(actor, cap)
        rx = RayReceiver(actor, cap)
        await tx._ensure_registered()
        await rx._ensure_registered()
        return tx, rx
    except ValueError:
        return None
```

______________________________________________________________________

## 5. Key Design Decisions

| Decision           | Choice                                    | Rationale                                          |
| ------------------ | ----------------------------------------- | -------------------------------------------------- |
| **Ref-counting**   | Per-sender/receiver IDs                   | Enables true distributed close semantics           |
| **Registration**   | Lazy on first send/recv                   | `clone()` stays synchronous                        |
| **Named channels** | Optional `name` param                     | Cross-process discovery                            |
| **Lifetime**       | Detached for named, default for anonymous | Named channels persist; anonymous die with creator |
| **Queue backend**  | `asyncio.Queue` in actor                  | Matches Ray's internal Queue implementation        |
| **Error mapping**  | All RayError → ChannelClosed              | Simple, consistent story                           |

______________________________________________________________________

## 6. Edge Cases & Gotchas

1. **Registration race**: Multiple clones registering simultaneously is safe (atomic counter in actor)

1. **Actor death**: If RayChannelActor dies, all operations raise ChannelClosed

1. **Lazy registration cost**: First `send()`/`recv()` has extra RTT for registration; acceptable tradeoff for sync `clone()`

1. **Named channel cleanup**: Detached actors persist until explicitly killed; consider adding `channel_delete(name)` helper

1. **Serialization**: Values must be CloudPickle-serializable; non-serializable objects fail at runtime

1. **Unbounded memory**: `unbounded=True` + fast producer = potential OOM in cluster

______________________________________________________________________

## 7. Test Strategy

1. **Unit tests** (single process, Ray local mode):

   - send/recv roundtrip
   - try_send/try_recv with capacity
   - clone creates independent sender/receiver
   - close one clone doesn't affect others
   - close ALL senders → receivers get ChannelClosed
   - close ALL receivers → senders get ChannelClosed
   - async iteration

1. **Named channel tests**:

   - Create named channel, retrieve by name
   - Multiple retrievals return same channel
   - Named channel persists after creator exits (detached)

1. **Distributed tests** (multi-process):

   - Pass sender to Ray task, send from task
   - Pass receiver to Ray task, recv in task
   - Cross-node communication

______________________________________________________________________

## 8. File Structure

```
src/klaw_core/runtime/channels/
├── __init__.py
├── protocols.py      # Sender/Receiver protocols
├── local.py          # LocalSender/LocalReceiver
├── oneshot.py        # OneshotSender/OneshotReceiver
├── broadcast.py      # BroadcastSender/BroadcastReceiver
├── watch.py          # WatchSender/WatchReceiver
├── ray_channel.py    # RayChannelActor, RaySender, RayReceiver  ← NEW
└── factory.py        # channel(), oneshot(), broadcast(), watch(), select()
```

______________________________________________________________________

## 9. Implementation Order

1. **RayChannelActor** - the control plane actor
1. **RaySender** - with lazy registration
1. **RayReceiver** - with lazy registration + async iteration
1. **Factory wiring** - `distributed=True` path
1. **Named channels** - optional `name` parameter
1. **Tests** - mirror LocalChannel tests with Ray-specific expectations
