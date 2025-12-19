# Real-World Ray Actor Patterns for Distributed Channels

Research from Ray ecosystem projects and community examples.

______________________________________________________________________

## 1. Ray's Native Queue Implementation

**Source:** [`ray.util.queue.Queue`](https://github.com/ray-project/ray/blob/master/python/ray/util/queue.py)

### Architecture

- Single `_QueueActor` wrapping `asyncio.Queue`
- Async methods for non-blocking operations
- Batch operations to reduce serialization overhead

### Key Code Pattern

```python
class _QueueActor:
    def __init__(self, maxsize):
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

    def put_nowait_batch(self, items):
        # Check space upfront for batch atomicity
        if self.maxsize > 0 and len(items) + self.qsize() > self.maxsize:
            raise Full(...)
        for item in items:
            self.queue.put_nowait(item)
```

### Takeaways

- Single source of truth in one actor
- Async/await for non-blocking backpressure
- Batch operations for efficiency
- Support both sync and async access patterns

______________________________________________________________________

## 2. Actor Pooling & Load Balancing

**Source:** [`ray.util.ActorPool`](https://github.com/ray-project/ray/blob/master/python/ray/util/actor_pool.py)

### Architecture

- Idle actor tracking with `_idle_actors` list
- `_future_to_actor` mapping for O(1) lookup
- Pending work queue for backpressure

### Key Code Pattern

```python
class ActorPool:
    def __init__(self, actors: list):
        self._idle_actors = list(actors)
        self._future_to_actor = {}
        self._pending_submits = []

    def submit(self, fn, value):
        if self._idle_actors:
            actor = self._idle_actors.pop()
            future = fn(actor, value)
            self._future_to_actor[future] = (index, actor)
        else:
            self._pending_submits.append((fn, value))

    def _return_actor(self, actor):
        self._idle_actors.append(actor)
        if self._pending_submits:
            self.submit(*self._pending_submits.pop(0))
```

### Autoscaling Interface

```python
@dataclass(frozen=True)
class ActorPoolScalingRequest:
    delta: int
    force: bool = False
    reason: Optional[str] = None


class AutoscalingActorPool(ABC):
    def num_tasks_in_flight(self) -> int: ...
    def num_free_task_slots(self) -> int: ...
    def scale(self, req: ActorPoolScalingRequest): ...
```

### Takeaways

- Track idle actors for instant dispatch
- Buffer pending work when no actors available
- Separate ordered vs unordered results
- Track utilization for scaling decisions

______________________________________________________________________

## 3. Fault-Tolerant Actor Communication

**Source:** [actor_restart.py](https://github.com/ray-project/ray/blob/master/doc/source/ray-core/doc_code/actor_restart.py)

### Automatic Restart Pattern

```python
@ray.remote(max_restarts=4, max_task_retries=-1)
class RobustActor:
    def __init__(self):
        self.counter = 0

    def execute(self):
        # Ray restarts actor up to 4 times
        # Failed tasks retried transparently
        pass
```

### Manual Checkpointing Pattern

```python
class ChannelController:
    def execute_with_fault_tolerance(self):
        while True:
            try:
                ray.get(worker.process_item.remote(item))
                # Checkpoint on success
                self.worker_state = ray.get(worker.checkpoint.remote())
                break
            except ray.exceptions.RayActorError:
                # Recovery: restart and restore
                self.worker = Worker.remote()
                ray.get(self.worker.restore.remote(self.worker_state))
```

### Takeaways

- Use `max_task_retries=-1` for queue actors (no message loss)
- Checkpoint channel state at critical points
- Implement recovery protocol for actor death

______________________________________________________________________

## 4. Async Actor Patterns

**Source:** [pattern_async_actor.py](https://github.com/ray-project/ray/blob/master/doc/source/ray-core/doc_code/pattern_async_actor.py)

### Concurrent Method Execution

```python
@ray.remote
class AsyncTaskExecutor:
    def __init__(self, task_store):
        self.task_store = task_store

    async def run(self):
        while True:
            # Use await to yield control
            task = await self.task_store.get_next_task.remote()
            self._execute_task(task)

    def get_num_executed_tasks(self):
        # Runs concurrently with run() because run() is async
        return self.num_executed_tasks
```

### Pipelining Pattern

```python
@ray.remote
class PipelinedWorker:
    def run(self):
        # Prefetch next while processing current
        self.work_item_ref = self.work_queue.get_work_item.remote()

        while True:
            work_item = ray.get(self.work_item_ref)
            if work_item is None:
                break

            # Fetch next while processing
            self.work_item_ref = self.work_queue.get_work_item.remote()
            self.process(work_item)
```

### Takeaways

- Actor thread doesn't block while awaiting
- Other methods can execute concurrently
- Overlap fetch and process for throughput

______________________________________________________________________

## 5. Ray Experimental Channels

**Source:** [`ray.experimental.channel`](https://github.com/ray-project/ray/tree/master/python/ray/experimental/channel)

### Communicator Pattern (Multi-Actor Sync)

```python
@ray.remote(num_cpus=0)
class CPUCommBarrier:
    def __init__(self, num_actors: int):
        self.condition = asyncio.Condition()
        self.collective_data = defaultdict(list)
        self.num_actors_seen = defaultdict(int)

    async def wait_collective(self, op_id: int, data, op: ReduceOp):
        async with self.condition:
            self.collective_data[op_id].append(data)
            self.num_actors_seen[op_id] += 1

            if self.num_actors_seen[op_id] == self.num_actors:
                # All ready, apply op
                data = self._apply_op(op, self.collective_data[op_id])
                self.condition.notify_all()
            else:
                await self.condition.wait_for(lambda: self.num_actors_seen[op_id] == self.num_actors)

            return data
```

### Ref Counting Pattern

```python
ReaderRefInfo = namedtuple('ReaderRefInfo', ['reader_ref', 'ref_owner_actor_id', 'num_reader_actors'])


class _ResizeChannel:
    """Sentinel value for metadata communication."""

    def __init__(self, node_id_to_reader_ref_info: Dict[str, ReaderRefInfo]):
        self._node_id_to_reader_ref_info = node_id_to_reader_ref_info
```

### Node-Aware Reader Tracking

```python
class Channel(ChannelInterface):
    def __init__(self, writer, reader_and_node_list, typ=None):
        # Track readers per node for locality
        self._node_id_to_readers = defaultdict(list)
        for reader, node_id in reader_and_node_list:
            self._node_id_to_readers[node_id].append(reader)

        # One ref per node for efficiency
        self._node_id_to_reader_ref_info = {}
```

### Takeaways

- Track `(reader_id, node_id)` pairs for cleanup
- Use sentinel values for metadata communication
- Separate local vs remote reader handling

______________________________________________________________________

## 6. Request Routing (Ray Serve)

**Source:** [request_router.py](https://github.com/ray-project/ray/blob/master/python/ray/serve/_private/request_router/request_router.py)

### Locality-Aware Routing

```python
class LocalityMixin:
    def __init__(self):
        self._colocated_replica_ids = defaultdict(set)
        self._replica_id_set = set()

    def apply_locality_routing(self, pending_request=None):
        """Route: local node → local AZ → anywhere."""
        if self._prefer_local_node_routing:
            return self._colocated_replica_ids[LocalityScope.NODE]
        elif self._prefer_local_az_routing:
            return self._colocated_replica_ids[LocalityScope.AVAILABILITY_ZONE]
        else:
            return self._replica_id_set
```

### Queue Length Tracking

```python
class ReplicaQueueLengthCache:
    """Track queue depths to balance load."""

    pass


class RequestRouter(LocalityMixin, FIFOMixin, MultiplexMixin):
    def route_request(self, pending_request):
        # Choose based on:
        # 1. Locality (same node > same AZ > any)
        # 2. Queue depth (least loaded)
        # 3. Retry backoff (exponential + jitter)
        pass
```

### Takeaways

- Track queue depth per reader for load balancing
- Implement locality-aware routing
- Exponential backoff with jitter for retries

______________________________________________________________________

## 7. Efficient Queue Implementation (Ray Data)

**Source:** [fifo_bundle_queue.py](https://github.com/ray-project/ray/blob/master/python/ray/data/_internal/execution/bundle_queue/fifo_bundle_queue.py)

### Linked List for O(1) Removal

```python
class FIFOBundleQueue(BundleQueue):
    def __init__(self):
        self._head = None
        self._tail = None
        self._bundle_to_nodes = defaultdict(deque)
        self._nbytes = 0
        self._num_blocks = 0

    def remove(self, bundle):
        node = self._bundle_to_nodes[bundle].popleft()

        # Update links
        if self._head is self._tail:
            self._head = self._tail = None
        elif node is self._head:
            self._head = node.next
        elif node is self._tail:
            self._tail = node.prev
        else:
            node.prev.next = node.next
            node.next.prev = node.prev

        # Update metadata
        self._nbytes -= bundle.size_bytes()
        self._num_blocks -= len(bundle)
```

### Memory-Aware Interface

```python
class BundleQueue(ABC):
    def estimate_size_bytes(self) -> int:
        """Total size of objects in queue."""

    def num_blocks(self) -> int:
        """Number of blocks in queue."""
```

### Takeaways

- Linked list for O(1) removal
- Track metadata (bytes, blocks) for backpressure
- Support `peek_next()` for inspection
- Implement `remove()` for cancellation

______________________________________________________________________

## 8. LangChain + Ray Integration

**Source:** [langchain-ray](https://github.com/ray-project/langchain-ray)

### Sharded Processing Pattern

```python
@ray.remote(num_gpus=1)
def process_shard(shard):
    embeddings = LocalHuggingFaceEmbeddings()
    return FAISS.from_documents(shard, embeddings)


# Shard and process in parallel
shards = np.array_split(chunks, db_shards)
futures = [process_shard.remote(shards[i]) for i in range(db_shards)]
results = ray.get(futures)

# Merge results
db = results[0]
for result in results[1:]:
    db.merge_from(result)
```

### Actor-Based Streaming

```python
class Embed:
    def __init__(self):
        self.transformer = SentenceTransformer(model_name, device='cuda')

    def __call__(self, text_batch):
        embeddings = self.transformer.encode(text_batch, batch_size=100)
        return list(zip(text_batch, embeddings))


# Use with ActorPoolStrategy
ds = ds.map_batches(
    Embed,
    batch_size=100,
    compute=ray.data.ActorPoolStrategy(min_size=20, max_size=20),
    num_gpus=1,
)
```

### Takeaways

- Support both stateless tasks and stateful actors
- Batch operations for GPU efficiency
- ActorPoolStrategy for automatic load balancing

______________________________________________________________________

## 9. Recommended Architecture for klaw-runtime

```
┌─────────────────────────────────────────────────────┐
│ Distributed Channel                                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ┌─────────────────────────────────────────────┐    │
│ │ Producer Actors                             │    │
│ │ - Write to channel                          │    │
│ │ - Track backpressure via utilization        │    │
│ └─────────────┬───────────────────────────────┘    │
│               │                                     │
│               ▼                                     │
│ ┌─────────────────────────────────────────────┐    │
│ │ Channel Coordinator Actor (async)           │    │
│ │ - asyncio.Queue internally                  │    │
│ │ - Ref counting for cleanup                  │    │
│ │ - Node-aware reader tracking                │    │
│ │ - Checkpointing for recovery                │    │
│ └─────────────┬───────────────────────────────┘    │
│               │                                     │
│    ┌──────────┴───────────┐                        │
│    ▼                      ▼                        │
│ ┌──────────┐        ┌──────────┐                   │
│ │ Local    │        │ Remote   │                   │
│ │ Readers  │        │ Readers  │                   │
│ │ (Same    │        │ (Other   │                   │
│ │ Node)    │        │ Nodes)   │                   │
│ └──────────┘        └──────────┘                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

______________________________________________________________________

## 10. Summary: Patterns to Adopt

| Pattern                 | Source                | Use Case                         |
| ----------------------- | --------------------- | -------------------------------- |
| **Async Queue Actor**   | `ray.util.queue`      | Channel coordinator              |
| **ActorPool**           | `ray.util.ActorPool`  | Producer/consumer load balancing |
| **Auto Restart**        | actor_restart.py      | Channel recovery                 |
| **Pipelining**          | pattern_pipelining.py | Overlap fetch + process          |
| **Node-Aware Tracking** | experimental.channel  | Locality optimization            |
| **Locality Routing**    | request_router.py     | Reader selection                 |
| **Linked List Queue**   | fifo_bundle_queue.py  | O(1) removal                     |
| **Batch Operations**    | embedding_ray.py      | GPU efficiency                   |
| **Ref Counting**        | ReaderRefInfo         | Multi-reader cleanup             |
| **Sentinel Values**     | \_ResizeChannel       | Metadata communication           |

______________________________________________________________________

## 11. Key Implementation Features

1. **Async Actor Core** — Use `asyncio.Queue` with timeout support
1. **Ref Counting** — Track `(reader_id, node_id)` pairs
1. **Locality Optimization** — Separate local vs remote readers
1. **Fault Tolerance** — Checkpointing + auto restart
1. **Backpressure** — Queue depth tracking
1. **Batching** — `put_batch()`/`get_batch()` for efficiency
1. **Load Balancing** — ActorPool pattern for reader distribution
1. **Monitoring** — Metrics on depth, utilization, latency
