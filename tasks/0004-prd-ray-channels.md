# PRD: Ray Channels

## 1. Introduction/Overview

Ray Channels provides distributed channel primitives for klaw, enabling communication between tasks and actors across a Ray cluster. This feature extends the existing local channel system with a Ray-backed implementation that supports multi-node, multi-process communication while maintaining the same channel semantics (MPMC, Oneshot, Broadcast, Watch).

**Problem solved:** Local channels are limited to single-process communication. As klaw workloads scale to distributed environments, users need channels that work seamlessly across Ray workers, nodes, and jobs without changing their code significantly.

## 2. Goals

1. **Distributed communication**: Enable send/recv across Ray workers, nodes, and jobs
1. **API consistency**: Maintain the same `Sender`/`Receiver` protocol interface as local channels
1. **Full channel semantics**: Support all channel types (MPMC, Oneshot, Broadcast, Watch) with Ray backend
1. **Flexible lifecycle**: Support both anonymous (ephemeral) and named (persistent/detached) channels
1. **Large payload efficiency**: Provide reference channels for efficient transfer of large objects via Ray's object store
1. **Operational visibility**: Expose channel stats, backpressure metrics, and node-aware receiver tracking
1. **Lifecycle management**: Provide supervisor pattern for managing multiple channels and checkpointing

## 3. User Stories

### Core Usage

- **US-1**: As a developer, I want to create a distributed channel so that my producer tasks on one node can send messages to consumer tasks on other nodes.
- **US-2**: As a developer, I want to use the same `async for item in receiver` pattern with Ray channels as I do with local channels so that I don't need to learn a new API.
- **US-3**: As a developer, I want to clone senders/receivers so that multiple producers or consumers can share a channel with proper ref-counting.

### Named Channels

- **US-4**: As a developer, I want to create a named channel that persists beyond my driver script so that separate Ray jobs can communicate through it.
- **US-5**: As a developer, I want to retrieve an existing named channel by name so that I can attach new producers/consumers to it.

### Large Payloads

- **US-6**: As a developer, I want to send large numpy arrays or tensors through channels efficiently without repeated serialization.

### Observability

- **US-7**: As an operator, I want to query channel stats (queue size, high watermark, per-node receivers) to monitor system health and detect backpressure.

### Lifecycle Management

- **US-8**: As a developer, I want a supervisor to manage multiple channels, create checkpoints, and restore state for fault tolerance.

### Load Balancing

- **US-9**: As a developer, I want to create a pool of reader actors that consume from a channel for parallel processing with dynamic scaling.

## 4. Functional Requirements

### 4.1 Module Structure

1. All Ray-specific code MUST be isolated in `klaw_core/runtime/channels/ray/` submodule
1. The `ray/` submodule MUST be the only place that imports `ray`
1. Top-level `channels/` MUST remain backend-agnostic (protocols, stats, errors)

### 4.2 RayChannelActor

4. The system MUST provide a `RayChannelActor` Ray actor class that holds the channel buffer
1. `RayChannelActor` MUST use `asyncio.Queue` internally for message buffering
1. `RayChannelActor` MUST support bounded capacity (blocking when full) and unbounded mode
1. `RayChannelActor` MUST track sender and receiver ref-counts for distributed close semantics
1. `RayChannelActor` MUST track per-reader stats including `node_id`, `registered_at`, `last_seen_at`, `total_received`
1. `RayChannelActor` MUST provide `get_stats()` returning `ChannelStats` with queue size, capacity, high watermark, totals, and per-node receiver counts
1. `RayChannelActor` MUST provide `get_checkpoint_state()` and `apply_checkpoint_state()` for fault tolerance
1. `RayChannelActor` MUST use `@ray.remote(max_restarts=4, max_task_retries=-1)` for basic fault tolerance
1. Actor methods MUST return status codes (`"ok"`, `"full"`, `"empty"`, `"closed"`) instead of raising exceptions

### 4.3 RaySender / RayReceiver

13. `RaySender[T]` MUST implement the `Sender[T]` protocol
01. `RayReceiver[T]` MUST implement the `Receiver[T]` protocol
01. Both MUST support lazy registration (register on first use)
01. Both MUST translate actor status codes to appropriate exceptions/results
01. `RaySender` MUST support `send()`, `try_send()`, `send_batch()`, `clone()`, `close()`
01. `RayReceiver` MUST support `recv()`, `try_recv()`, `recv_batch()`, `clone()`, `close()`, `__aiter__`, `__anext__`
01. `RayReceiver` MUST track its `reader_id` and `node_id` for per-reader stats

### 4.4 Reference Channels

20. The system MUST provide `RayReferenceSender[T]` that wraps values with `ray.put()` before sending
01. The system MUST provide `RayReferenceReceiver[T]` that calls `ray.get()` on received `ObjectRef`s
01. Reference channels MUST support batch operations for efficiency

### 4.5 Factory Functions

23. The system MUST provide `ray_channel()` for direct Ray channel creation
01. The system MUST provide `get_ray_channel(name)` to retrieve existing named channels
01. The system MUST provide `delete_ray_channel(name)` to clean up named channels
01. The system MUST provide `list_ray_channels()` to enumerate channels in a namespace
01. The top-level `channel()` factory MUST accept `backend="ray"` or `distributed=True` parameter
01. Named channels MUST use `lifetime="detached"` and `get_if_exists=True` actor options

### 4.6 Supervisor

29. The system MUST provide `ChannelSupervisor` actor for managing multiple channels
01. `ChannelSupervisor` MUST support `create_channel()`, `delete_channel()`, `list_channels()`
01. `ChannelSupervisor` MUST support `get_checkpoint()` and `restore_from_checkpoint()` per channel

### 4.7 Reader Pools

32. The system MUST provide `ChannelReader` actor base class for consuming from channels
01. The system MUST provide `ReaderPoolController` for managing a pool of `ChannelReader` actors
01. `ReaderPoolController` MUST support `scale(delta)` for dynamic pool sizing

### 4.8 All Channel Types

35. MPMC channels MUST work with Ray backend (multiple producers, multiple consumers, each message consumed once)
01. Oneshot channels MUST work with Ray backend (single send, single receive)
01. Broadcast channels MUST work with Ray backend (all receivers get all messages)
01. Watch channels MUST work with Ray backend (receivers get latest value)

### 4.9 Backend-Agnostic Components

39. `ChannelStats` dataclass MUST include `backend_extras: Mapping[str, Any]` for Ray-specific fields
01. `ChannelCheckpoint` dataclass MUST be backend-agnostic
01. `Sender`, `Receiver`, `ReferenceSender`, `ReferenceReceiver` protocols MUST be backend-agnostic

## 5. Non-Goals (Out of Scope)

1. **Ray Data integration (RDT)**: No integration with Ray Data or Ray Direct Transport
1. **Ray Compiled Graphs**: No use of `experimental_compile()` or accelerated DAGs
1. **GPU tensor optimizations**: No NCCL-backed GPU-to-GPU tensor transfers
1. **Experimental Ray channels**: No use of `ray.experimental.channel.*`
1. **Automatic sharding**: No automatic partitioning of channels across nodes (manual sharding only)
1. **Exactly-once delivery**: No persistent log-based delivery guarantees across failures

## 6. Design Considerations

### Module Layout

```
klaw_core/runtime/channels/
├── __init__.py              # Public exports
├── protocols.py             # Sender, Receiver, ReferenceSender, ReferenceReceiver
├── stats.py                 # ChannelStats, ChannelCheckpoint
├── errors.py                # ChannelClosed, ChannelFull, ChannelEmpty
├── local.py                 # LocalSender/LocalReceiver
├── oneshot.py               # OneshotSender/OneshotReceiver
├── broadcast.py             # BroadcastSender/BroadcastReceiver
├── watch.py                 # WatchSender/WatchReceiver
├── select.py                # select() function
├── factory.py               # Backend-agnostic channel(), get_channel(), etc.
└── ray/                     # RAY-SPECIFIC
    ├── __init__.py
    ├── actor.py             # RayChannelActor, ReaderInfo
    ├── core.py              # RaySender, RayReceiver
    ├── reference.py         # RayReferenceSender, RayReferenceReceiver
    ├── supervisor.py        # ChannelSupervisor
    ├── pools.py             # ChannelReader, ReaderPoolController
    └── factory.py           # ray_channel(), get_ray_channel(), etc.
```

### Ray Actor Configuration

- Named actors: `name=f"channel_{name}"`, `namespace=namespace`, `lifetime="detached"`, `get_if_exists=True`
- Fault tolerance: `max_restarts=4`, `max_task_retries=-1`
- Async actors default to `max_concurrency=1000`

## 7. Technical Considerations

### Ray Version

- Target Ray 2.x (2.5+)
- Verified APIs: `get_if_exists`, `lifetime="detached"`, `ray.get_runtime_context().get_node_id()`, `ray.util.list_named_actors()`

### Dependencies

- Ray is a required dependency
- No additional Ray extras required (no `ray[adag]`)

### Performance

- Use batch operations (`put_batch`/`get_batch`) for high throughput
- Use reference channels for payloads >100KB
- Actor methods should be non-blocking (use `await` for queue operations)
- Consider `num_cpus=0` for channel actors to avoid oversubscribing

### Serialization

- Standard Ray serialization (cloudpickle + specialized numpy/torch serializers)
- Reference channels avoid repeated serialization for large objects

## 8. Success Metrics

1. **Protocol compliance**: All Ray channel implementations pass existing `Sender`/`Receiver` protocol tests
1. **Cross-process communication**: Demonstrated send/recv between separate Ray workers
1. **Cross-node communication**: Demonstrated send/recv between different cluster nodes
1. **Named channel persistence**: Demonstrated channel access from separate driver scripts
1. **Performance baseline**: Benchmarks documenting overhead vs local channels (target: \<2ms per message for small payloads)
1. **Reference channel efficiency**: Demonstrated memory savings for large payload transfers

## 9. Design Decisions (Resolved)

1. **Namespace default**: Use `"klaw"` as the default Ray namespace via a `DEFAULT_RAY_NAMESPACE` constant. Allow override via parameter and optionally via `KLAW_RAY_NAMESPACE` env var.

1. **Channel type detection**: Store `channel_type` metadata in the actor (e.g., `"mpmc"`, `"broadcast"`, `"watch"`, `"oneshot"`). Expose via `get_metadata()` method. `get_ray_channel()` calls this to reconstruct the correct sender/receiver wrapper.

1. **Supervisor singleton**: Per-namespace singleton via `get_channel_supervisor(namespace=...)` helper. Not a hard global — each Ray namespace gets its own supervisor. This provides convenience + isolation + testability.

1. **Broadcast/Watch with Ray**: Implement Ray-specific actors (`RayBroadcastActor`, `RayWatchActor`) with appropriate semantics. Do NOT layer these over MPMC — their fan-out and latest-value semantics are fundamentally different.

1. **Error handling**: Introduce `ChannelBackendError` as a subclass of `ChannelClosed`. All `ray.exceptions.RayError` failures map to this error. This is distinct (for detection/retry logic) but compatible (existing `ChannelClosed` handlers still work). Include diagnostic fields: `backend`, `cause`, `actor_name`, `namespace`.
