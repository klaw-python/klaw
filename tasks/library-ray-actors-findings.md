# Ray Distributed Channels & Actors API Research

Generated for task 4.13: Implementing `RayChannel` for distributed channels.

______________________________________________________________________

## 1. Ray Queue API (`ray.util.queue.Queue`)

### Constructor

```python
from ray.util.queue import Queue

queue = Queue(
    maxsize: int = 0,  # 0 = unbounded queue
    actor_options: Optional[Dict] = None  # e.g., {"num_cpus": 1}
)
```

### Synchronous Methods

| Method                                    | Description                               |
| ----------------------------------------- | ----------------------------------------- |
| `put(item, block=True, timeout=None)`     | Add item, blocks if full                  |
| `put_nowait(item)`                        | Non-blocking put, raises `Full` if full   |
| `put_nowait_batch(items)`                 | Batch add items (more efficient)          |
| `get(block=True, timeout=None)`           | Remove and return item, blocks if empty   |
| `get_nowait()`                            | Non-blocking get, raises `Empty` if empty |
| `get_nowait_batch(num_items)`             | Batch get items as list                   |
| `qsize()` / `size()`                      | Current queue size                        |
| `empty()`                                 | True if queue is empty                    |
| `full()`                                  | True if queue is full                     |
| `shutdown(force=False, grace_period_s=5)` | Terminate underlying QueueActor           |

### Async Methods

| Method                                            | Description          |
| ------------------------------------------------- | -------------------- |
| `await put_async(item, block=True, timeout=None)` | Async version of put |
| `await get_async(block=True, timeout=None)`       | Async version of get |

### Internal Implementation

The Queue wraps a Ray actor (`_QueueActor`) using `asyncio.Queue` internally:

```python
class _QueueActor:
    def __init__(self, maxsize):
        self.maxsize = maxsize
        self.queue = asyncio.Queue(self.maxsize)

    async def put(self, item, timeout=None):
        try:
            await asyncio.wait_for(self.queue.put(item), timeout)
        except asyncio.TimeoutError:
            raise Full

    async def get(self, timeout=None):
        try:
            return await asyncio.wait_for(self.queue.get(), timeout)
        except asyncio.TimeoutError:
            raise Empty
```

### Exceptions

```python
from ray.util.queue import Empty, Full

# Both inherit from standard library
# ray.util.queue.Empty -> queue.Empty
# ray.util.queue.Full -> queue.Full
```

______________________________________________________________________

## 2. Ray Actor API (`@ray.remote`)

### Basic Actor Definition

```python
@ray.remote
class MyActor:
    def __init__(self, value: int):
        self.value = value

    def get_value(self) -> int:
        return self.value

    async def async_method(self):
        await asyncio.sleep(1)
        return self.value


# Create actor instance
actor = MyActor.remote(10)
result = ray.get(actor.get_value.remote())
```

### Decorator Options

```python
@ray.remote(
    num_cpus=1,
    num_gpus=0,
    memory=1000000,
    max_restarts=3,
    max_task_retries=0,
    max_concurrency=1,
    lifetime='detached',  # or None (default)
    name='my_actor',
    namespace='my_namespace',
    get_if_exists=False,
)
class MyActor:
    pass
```

### Dynamic Options via `.options()`

```python
ActorWithOptions = MyActor.options(num_cpus=2, name='custom_actor', namespace='custom_ns')
actor = ActorWithOptions.remote()
```

### Named Actor Retrieval

```python
# Create named actor
actor = MyActor.options(name='counter', namespace='app').remote()

# Retrieve by name (any process)
retrieved_actor = ray.get_actor('counter', namespace='app')

# List all named actors
all_actors = ray.util.list_named_actors(all_namespaces=True)
# Returns: [{"name": "counter", "namespace": "app"}, ...]
```

### Actor Termination

```python
ray.kill(actor, no_restart=True)
```

______________________________________________________________________

## 3. Object Store (`ray.get()` and `ray.put()`)

### `ray.put()`

```python
obj_ref = ray.put(value, _owner=None)
# Returns ObjectRef that can be passed to other tasks/actors
```

### `ray.get()`

```python
# Single object
result = ray.get(ref)

# Multiple objects (preserves order)
results = ray.get([ref1, ref2, ref3])

# With timeout
try:
    result = ray.get(ref, timeout=5.0)
except ray.exceptions.GetTimeoutError:
    print('Timeout!')
```

### Async Alternative

```python
# In async context, use await instead of ray.get()
result = await ref
results = await asyncio.gather(*refs)
```

______________________________________________________________________

## 4. Serialization

Ray uses **CloudPickle** for all object serialization:

```python
import ray.cloudpickle as pickle
```

Custom serializers can be registered:

```python
from ray.util.serialization import register_serializer

register_serializer(MyClass, serializer=lambda obj: {'data': obj.data}, deserializer=lambda d: MyClass(d['data']))
```

______________________________________________________________________

## 5. Exception Types

```python
from ray.exceptions import (
    RayError,  # Base class
    RayTaskError,  # Task execution failed
    RayActorError,  # Actor-specific errors
    TaskCancelledError,
    ObjectStoreFullError,
    ObjectLostError,
    OwnerDiedError,
    GetTimeoutError,
)

from ray.util.queue import Empty, Full
```

______________________________________________________________________

## 6. Async Support in Ray

### Async Actor Methods

```python
@ray.remote
class AsyncActor:
    async def process(self, data):
        await asyncio.sleep(1)
        return data * 2


# Async actors default to max_concurrency=1000
```

### Blocking Warning

```python
# BAD: Blocks event loop
async def bad():
    result = ray.get(actor.method.remote())


# GOOD: Use await
async def good():
    result = await actor.method.remote()
```

______________________________________________________________________

## 7. Design Pattern for klaw RayChannel

### Recommended Implementation

```python
from ray.util.queue import Queue, Empty, Full


class RaySender[T]:
    """Distributed sender wrapping Ray Queue."""

    def __init__(self, queue: Queue) -> None:
        self._queue = queue

    async def send(self, value: T) -> None:
        """Async blocking send."""
        await self._queue.put_async(value, block=True)

    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        """Non-blocking send."""
        try:
            self._queue.put_nowait(value)
            return Ok(None)
        except Full:
            return Err(ChannelFull(self._queue.maxsize))

    def clone(self) -> 'RaySender[T]':
        """Clone returns same queue reference."""
        return RaySender(self._queue)

    async def close(self) -> None:
        """Shutdown underlying queue actor."""
        self._queue.shutdown(force=False, grace_period_s=5)


class RayReceiver[T]:
    """Distributed receiver wrapping Ray Queue."""

    def __init__(self, queue: Queue) -> None:
        self._queue = queue

    async def recv(self) -> T:
        """Async blocking receive."""
        return await self._queue.get_async(block=True)

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        """Non-blocking receive."""
        try:
            return Ok(self._queue.get_nowait())
        except Empty:
            return Err(ChannelEmpty())

    def clone(self) -> 'RayReceiver[T]':
        """Clone returns same queue reference."""
        return RayReceiver(self._queue)

    async def close(self) -> None:
        """Shutdown underlying queue actor."""
        self._queue.shutdown(force=False, grace_period_s=5)
```

### Factory Function

```python
async def channel(
    capacity: int = 10000, distributed: bool = False, unbounded: bool = False
) -> tuple[Sender[T], Receiver[T]]:
    if distributed:
        maxsize = 0 if unbounded else capacity
        queue = Queue(maxsize=maxsize)
        return RaySender(queue), RayReceiver(queue)
    # ... local implementation
```

______________________________________________________________________

## 8. Key Considerations

| Aspect            | Notes                                               |
| ----------------- | --------------------------------------------------- |
| **Capacity**      | `maxsize=0` means unbounded in Ray Queue            |
| **Exceptions**    | Use `ray.util.queue.Empty/Full`, not stdlib         |
| **Async**         | Always use `put_async`/`get_async` in async context |
| **Cloning**       | Safe - just shares queue reference                  |
| **Shutdown**      | Call `shutdown()` for graceful cleanup              |
| **Cross-node**    | Works automatically via Ray object store            |
| **Serialization** | CloudPickle handles most types automatically        |

______________________________________________________________________

## 9. Differences from Local Channel

| Feature          | LocalChannel             | RayChannel           |
| ---------------- | ------------------------ | -------------------- |
| Backend          | anyio.MemoryObjectStream | ray.util.queue.Queue |
| Scope            | Single process           | Cross-process/node   |
| Serialization    | None (in-memory refs)    | CloudPickle          |
| Latency          | ~μs                      | ~ms (network hop)    |
| Capacity default | 10,000                   | 0 (unbounded)        |
| Close semantics  | Ref-counted              | Actor shutdown       |

______________________________________________________________________

## 10. Open Questions for Implementation

1. **Named channels**: Should we support `channel(name="foo")` for retrieval across processes?
1. **Lifecycle**: Who owns the Queue actor? Detached vs fate-shared?
1. **Error mapping**: Map Ray exceptions to klaw errors (Empty→ChannelEmpty, etc.)
1. **Batch operations**: Expose `send_batch`/`recv_batch` for efficiency?
1. **Backpressure**: Ray Queue `put_async(block=True)` blocks indefinitely - add timeout?
