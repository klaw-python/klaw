# Ray Design Patterns, Anti-Patterns & Advanced Topics

Research from Ray documentation for klaw-runtime distributed channels.

______________________________________________________________________

## 1. Design Patterns & Best Practices

### 1.1 Core Architecture Principles

**Actors as Stateful Workers**

- Each actor runs in its own isolated Python process
- Instance variables persist across method calls
- Actor methods execute on the same process, preserving locality

**Remote Objects & Object Store**

- Objects stored in Ray's distributed CPU-based object store (Plasma)
- Each node has one object store server managing shared memory
- Objects are **immutable** once stored
- Small objects (\<100KB) are **inlined** in task arguments (zero-copy optimization)

**Actor Task Execution Order**

- Single-threaded actors: tasks from same submitter execute in submission order
- Tasks from **different submitters** may execute out-of-order
- Async/threaded actors don't guarantee execution order

______________________________________________________________________

### 1.2 Actor Concurrency Models

| Model               | `max_concurrency` | Use Case                                     |
| ------------------- | ----------------- | -------------------------------------------- |
| **Single-Threaded** | 1 (default)       | Sequential consistency, safe state mutations |
| **Async Actors**    | 1000 (default)    | I/O-bound, network-heavy workloads           |
| **Threaded Actors** | 1 (default)       | Libraries that release GIL (NumPy, PyTorch)  |

**For Channels:** Use async actors with tuned `max_concurrency` for queue workers.

______________________________________________________________________

### 1.3 Memory & Object Store Management

**Object Store Defaults**

- Allocation: 30% of available node memory
- Storage: `/dev/shm` on Linux, `/tmp` on macOS
- Spilling: Automatic disk spillover when store fills
- Eviction: LRU when references are released

**Reference Types Keeping Objects Pinned**

1. Local ObjectRef variables
1. Deserialized copies from `ray.get()`
1. Pending task arguments
1. ObjectRefs serialized inside other objects
1. Actor instance variables holding ObjectRefs

______________________________________________________________________

## 2. Critical Anti-Patterns

| Anti-Pattern                              | Issue                               | Solution                              |
| ----------------------------------------- | ----------------------------------- | ------------------------------------- |
| **Passing same large arg multiple times** | Duplicates in object store          | Use `ray.put()` once, pass ObjectRef  |
| **`ray.get()` inside task**               | Blocks task, can deadlock           | Pass ObjectRefs as task arguments     |
| **`ray.get()` in loop**                   | Sequential instead of parallel      | Spawn all tasks, batch `ray.get()`    |
| **Returning `ray.put()` ObjectRefs**      | Ownership issues, disables inlining | Return values directly                |
| **Closure capturing large objects**       | Serialization bloat                 | Use `ray.put()`, pass ObjectRefs      |
| **Fetching too many objects**             | OOM                                 | Fetch in batches                      |
| **`ray.get()` in submission order**       | Stragglers block all                | Use `ray.wait()` for completion order |
| **Over-parallelizing**                    | Task overhead exceeds speedup       | Batch operations                      |

______________________________________________________________________

## 3. Actor Lifecycle & Fault Tolerance

### 3.1 Object Ownership Model

The worker that creates an ObjectRef is the **owner**:

- If owner dies, object is **lost** (cannot be reconstructed)
- ObjectRef must not outlive its owner
- Driver is typically owner (safe, long-lived)

**Best Practices for Durability**

1. Return values directly from tasks (makes caller the owner)
1. Avoid storing ObjectRefs in actor state long-term
1. Use supervisor pattern for automatic retry

### 3.2 Supervisor Pattern

```python
@ray.remote
class ChannelSupervisor:
    def __init__(self, num_workers):
        self.workers = [Worker.remote() for _ in range(num_workers)]
        # Channels owned by supervisor (safe ownership)
        self.input_queue = asyncio.Queue()
```

**Advantages:**

- Supervisor owns channels (safe ownership model)
- Automatic cleanup when supervisor dies
- Centralized lifecycle management

______________________________________________________________________

## 4. Ray Direct Transport (RDT)

### 4.1 What It Is

RDT bypasses the object store for tensor transfers:

**Normal flow:** GPU → CPU → object store → CPU → GPU (slow)
**RDT flow:** GPU → GPU direct (fast)

### 4.2 Supported Transports

| Transport | Backend            | Use Case      | Requirement                    |
| --------- | ------------------ | ------------- | ------------------------------ |
| **Gloo**  | PyTorch collective | CPU tensors   | No GPU required                |
| **NCCL**  | NVIDIA collective  | GPU tensors   | NVIDIA GPUs + collective group |
| **NIXL**  | NVIDIA RDMA        | CPU↔GPU mixed | NVIDIA GPUs, NIXL installed    |

### 4.3 Usage

```python
@ray.remote
class Sender:
    @ray.method(tensor_transport='nccl')
    def send_tensor(self, tensor):
        return tensor  # Direct GPU-GPU transfer
```

### 4.4 Critical Limitations

🚨 **Object Mutability Problem**

RDT objects are **mutable** — Ray holds a reference, not a copy:

```python
@ray.remote
class Sender:
    @ray.method(tensor_transport='gloo')
    def create_tensor(self):
        self.tensor = torch.zeros(1000)
        return self.tensor  # Reference, not copy!

    def modify_tensor(self):
        self.tensor += 1  # 🔴 RACE CONDITION!
```

**Solution:** Use `ray.experimental.wait_tensor_freed(tensor_ref)` before modifying.

**Other Limitations:**

- Torch tensors only (not arbitrary objects)
- Ray actors only (not tasks)
- Not compatible with asyncio
- Gloo/NCCL: Cannot use `ray.put()`, cannot pass across process boundaries

### 4.5 RDT for Channels

**Use Case:** GPU-accelerated tensor passing between workers

**Consideration:** Collective group setup overhead may not be worth it for simple channels. Use shared memory for coordination, GPU data transferred out-of-band.

______________________________________________________________________

## 5. Ray Experimental Channels

### 5.1 Channel Types

| Type                              | Description                                      |
| --------------------------------- | ------------------------------------------------ |
| **SharedMemoryType**              | Uses object store, auto-resize, multi-node       |
| **CachedChannel**                 | Caches data, avoids serialization for same-actor |
| **TorchTensorAcceleratorChannel** | GPU tensor specialization                        |

### 5.2 Key Characteristics

- **Minimum buffer:** 1000 bytes
- **Automatic resize:** On overflow
- **No buffering:** Writer blocks until all readers consume
- **Reader registration required:** `ensure_registered_as_reader()`

### 5.3 Multi-Node Support

- Each node has independent reader buffer
- Readers on same node share one buffer
- Remote readers receive updates via RPC

### 5.4 Design Implications

**Strengths:**

- ✅ Built-in multi-node support
- ✅ Automatic buffer management
- ✅ GPU tensor specialization

**Weaknesses:**

- ❌ Blocking semantics (not queue-like)
- ❌ Requires explicit registration
- ❌ Still experimental, limited docs
- ⚠️ Designed for compiled DAGs, not general queues

______________________________________________________________________

## 6. Performance Tuning

### 6.1 Batching Pattern

Task overhead (scheduling, RPC, serialization) can exceed work time:

```python
# ❌ Fine-grained (slow)
for item in items:
    task.remote(item)

# ✅ Batched (fast)
for batch in batches:
    task.remote(batch)
```

**Rule:** Task duration should be 1+ second to justify overhead.

### 6.2 Backpressure

```python
pending = []
for item in stream():
    pending.append(task.remote(item))
    if len(pending) > max_pending:
        ray.wait(pending, num_returns=1)
        pending.pop(0)
```

### 6.3 Pipelining

Overlap computation and communication:

```python
# ❌ Sequential
while True:
    work = ray.get(queue.pop.remote())  # Block
    process(work)

# ✅ Pipelined
work = ray.get(queue.pop.remote())
while True:
    next_ref = queue.pop.remote()  # Fire RPC
    process(work)  # Use CPU while RPC in flight
    work = ray.get(next_ref)
```

### 6.4 Completion Order

```python
# ❌ Submission order (stragglers block)
for ref in refs:
    result = ray.get(ref)

# ✅ Completion order
pending = set(refs)
while pending:
    ready, pending = ray.wait(list(pending), num_returns=1)
    result = ray.get(ready[0])
```

______________________________________________________________________

## 7. Serialization Best Practices

**Default Path:**

1. Arguments serialized via `cloudpickle`
1. Large objects (>1MB) go to object store
1. Small objects (\<100KB) inlined in RPC (zero-copy)

**Optimization Strategies:**

1. Avoid large function closures
1. Use `ray.put()` for large shared args
1. Return small objects directly (enables inlining)
1. Custom serializers for domain objects

______________________________________________________________________

## 8. Anti-Patterns for Channel Implementation

| Pattern                                | Problem                      | Fix                          |
| -------------------------------------- | ---------------------------- | ---------------------------- |
| **Unbounded channel buffer**           | OOM if reader slow           | Implement queue size limits  |
| **Channels with untracked ObjectRefs** | References die with owner    | Supervisor owns channels     |
| **Long-lived pending ObjectRefs**      | Pins memory, blocks eviction | Process promptly             |
| **Async actors without yields**        | Blocks other tasks           | Use `await asyncio.sleep(0)` |
| **Channels in closures**               | Serialization bloat          | Pass as explicit argument    |
| **Fine-grained writes**                | RPC overhead dominates       | Batch writes                 |

______________________________________________________________________

## 9. Recommended Architecture for klaw-runtime

### 9.1 Supervisor Pattern for Channels

```python
@ray.remote
class ChannelSupervisor:
    def __init__(self, num_workers):
        self.workers = [Worker.remote(self) for _ in range(num_workers)]
        self.input_channel = RayChannel(...)
        self.output_channel = RayChannel(...)

    def submit_work(self, data):
        self.input_channel.write(data)

    def get_result(self):
        return self.output_channel.read()
```

### 9.2 Backpressure in Pipelines

```python
@ray.remote
class AsyncQueueActor:
    def __init__(self, max_pending=100):
        self.pending = []
        self.max_pending = max_pending

    async def enqueue(self, item):
        while len(self.pending) >= self.max_pending:
            await asyncio.sleep(0.01)
        self.pending.append(item)
```

### 9.3 Serialization-Aware Design

```python
class ReferenceChannel:
    def write(self, value):
        ref = ray.put(value)  # Serialize once
        self.channel.write(ref)

    def read(self):
        ref = self.channel.read()
        return ray.get(ref)
```

______________________________________________________________________

## 10. Key Takeaways for klaw-runtime

### Design Principles

- ✅ Async actors for I/O-bound channels
- ✅ Supervisor pattern for safe ownership
- ✅ Implement backpressure
- ✅ Batch operations

### Object Store Awareness

- ✅ Small messages (\<100KB) inlined
- ✅ Large messages use object store
- ✅ Avoid keeping ObjectRefs alive too long

### Serialization

- ✅ Return values directly (enables inlining)
- ✅ Use `ray.put()` for large shared objects
- ✅ Avoid closure-capturing large objects

### GPU Efficiency

- ✅ RDT beneficial for large GPU tensors
- ✅ Watch for RDT mutability bugs
- ✅ Fallback to shared memory for simplicity

### Fault Tolerance

- ✅ Return values directly (driver becomes owner)
- ✅ Avoid ObjectRefs in worker state
- ✅ Use supervisor for failure isolation

### Performance

- ✅ Batch to reduce overhead
- ✅ Backpressure with `ray.wait()`
- ✅ Process in completion order

______________________________________________________________________

## 11. References

**Core Architecture**

- [Actors Guide](https://docs.ray.io/en/latest/ray-core/actors.html)
- [Objects & Object Store](https://docs.ray.io/en/latest/ray-core/objects.html)
- [Memory Management](https://docs.ray.io/en/latest/ray-core/scheduling/memory-management.html)

**Patterns**

- [Design Patterns Index](https://docs.ray.io/en/latest/ray-core/patterns/index.html)
- [Limit Pending Tasks](https://docs.ray.io/en/latest/ray-core/patterns/limit-pending-tasks.html)
- [Pipelining](https://docs.ray.io/en/latest/ray-core/patterns/pipelining.html)

**Advanced**

- [Async API](https://docs.ray.io/en/latest/ray-core/actors/async_api.html)
- [Ray Direct Transport](https://docs.ray.io/en/latest/ray-core/direct-transport.html)
- [Fault Tolerance](https://docs.ray.io/en/latest/ray-core/fault-tolerance.html)
