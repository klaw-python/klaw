# PRD: klaw-runtime

## 1. Introduction/Overview

This PRD describes the implementation of `klaw_core.runtime`, a unified async/multiprocess runtime module for the Klaw ecosystem. The runtime provides an ergonomic API for concurrent and parallel execution with full `Result[T, E]` integration, backend-agnostic execution (local + Ray), structured concurrency, channels, and context propagation.

**Problem Statement:**

- Python's async ecosystem is fragmented (asyncio, trio, multiprocessing, Ray, etc.)
- Users must manually bridge sync/async and handle Result types across boundaries
- No unified API for "run this code concurrently" that scales from local to cluster
- Existing `klaw_core.async_` module is standalone and doesn't integrate with a runtime concept

**Solution:**

- Consolidate `async_/` into `runtime/` as the single concurrency foundation
- Provide `Executor` abstraction with pluggable backends (local via anyio/aiologic, Ray for distributed)
- Auto-detect environment and configure sensibly via `runtime.init()`
- Integrate channels, context propagation, timeout/retry, and structured logging

## 2. Goals

1. **Unified API**: Single async-first API that works locally and on Ray clusters
1. **Result Integration**: All operations return `Result[T, E]`, exceptions are captured
1. **Ergonomic**: `async with` and `async for` patterns throughout
1. **Backend Agnostic**: Same code runs on local processes or Ray—switch via config
1. **Observable**: Structured logging with structlog, context propagation for tracing
1. **Testable**: Real execution tests with Hypothesis and Mimesis, no mocks

## 3. User Stories

1. **As a data engineer**, I want to run CPU-bound tasks in parallel so that I can process large datasets efficiently.

1. **As a backend developer**, I want async producer/consumer channels so that I can build streaming pipelines.

1. **As an ML engineer**, I want the same code to run locally and on a Ray cluster so that I can develop locally and scale to production.

1. **As a developer**, I want context (request_id, trace_id) to propagate through spawned tasks so that I can trace requests across concurrent operations.

1. **As a library user**, I want `runtime.init()` to auto-detect my environment so that I don't need boilerplate configuration.

1. **As a developer**, I want structured logging so that I can integrate with my existing observability stack.

## 4. Functional Requirements

### 4.1 Initialization & Configuration

1. **FR-001**: Provide `runtime.init()` to configure global defaults
1. **FR-002**: Auto-detect environment (CPU count, memory, Ray cluster presence) using psutil
1. **FR-003**: Support environment variables: `KLAW_BACKEND`, `KLAW_CONCURRENCY`, `KLAW_LOG_LEVEL`
1. **FR-004**: Provide `Backend` enum with values: `LOCAL`, `RAY`
1. **FR-005**: Configure structlog with sensible defaults; silent by default, configurable via `log_level` parameter

### 4.2 Executor

6. **FR-006**: Provide `Executor` class as async context manager (`async with Executor() as ex:`)
1. **FR-007**: Executor inherits global config from `runtime.init()`, allows per-instance overrides
1. **FR-008**: Implement `ex.map(func, items, **kwargs)` returning `Result[list[U], E]`
1. **FR-009**: Implement `ex.imap(func, items)` returning `AsyncIterator[Result[U, E]]`
1. **FR-010**: Implement `ex.submit(func, *args, **kwargs)` returning `TaskHandle[T, E]`
1. **FR-011**: Implement `ex.gather(*awaitables)` for concurrent execution
1. **FR-012**: Support per-task backend kwargs override (e.g., `num_cpus`, `num_gpus` for Ray)

### 4.3 TaskHandle

13. **FR-013**: `TaskHandle` is awaitable, returns `Result[T, E | Cancelled]`
01. **FR-014**: Implement `handle.cancel(reason=None)` for explicit cancellation
01. **FR-015**: Implement `handle.is_running()` to check task status

### 4.4 Backends

16. **FR-016**: Implement `LocalBackend` using anyio + aiologic for async, `anyio.to_thread.run_sync()` for CPU-bound
01. **FR-017**: Implement `RayBackend` as optional (requires `ray` extra)
01. **FR-018**: Ray backend passes through kwargs (`num_cpus`, `num_gpus`, `resources`, `runtime_env`)
01. **FR-019**: Local backend ignores Ray-specific kwargs silently

### 4.5 Channels

20. **FR-020**: Implement `channel[T](capacity=None, distributed=False)` returning `tuple[Sender[T], Receiver[T]]`; default capacity is 10,000 (no true unbounded); use `unbounded=True` to opt into unlimited
01. **FR-021**: Implement `oneshot[T]()` for single-value, single-use channels
01. **FR-022**: Implement `broadcast[T](capacity=None)` for one-to-many (all receivers get every message)
01. **FR-023**: Implement `watch[T](initial)` for latest-value observation
01. **FR-024**: Implement `select(*receivers, timeout=None)` for multiplexing
01. **FR-025**: `Sender` supports `send()` (async, raises on closed), `try_send()` (returns Result), `clone()`, `close()`
01. **FR-026**: `Receiver` supports `recv()` (async, raises on closed), `try_recv()` (returns Result), `clone()`, `__aiter__`
01. **FR-027**: Local channels use `aiologic.Queue`
01. **FR-028**: Distributed channels use msgspec serialization with tagged union framing
01. **FR-029**: Distributed channels enforce backpressure—sender blocks when capacity reached; use `try_send()` for non-blocking with `Result`

### 4.6 Cancellation

30. **FR-030**: Implement `cancel_scope(timeout=None)` as async context manager
01. **FR-031**: Support both scope-based (structured) and handle-based (explicit) cancellation
01. **FR-032**: Cancelled tasks return `Err(Cancelled(reason))`

### 4.7 Timeout & Retry

33. **FR-033**: Implement `timeout(awaitable, seconds)` returning `Result[T, E | Timeout]`
01. **FR-034**: Implement `retry(func, *args, attempts=3, backoff=1.0, retry_on=None)` using tenacity
01. **FR-035**: Retry on `Err` by default, configurable via `retry_on` predicate

### 4.8 Context Propagation

36. **FR-036**: Implement `Context` dataclass with `request_id`, `trace_id`, `span_id`, `extra`
01. **FR-037**: Implement `context(**values)` as async context manager
01. **FR-038**: Implement `current_context()` to retrieve current context
01. **FR-039**: Executor automatically propagates context to spawned tasks via `contextvars`

### 4.9 Structured Logging

40. **FR-040**: Integrate structlog with auto-injection of context (request_id, trace_id)
01. **FR-041**: Log runtime events (task start/end, channel operations, errors) at appropriate levels
01. **FR-042**: Silent by default; configurable via `runtime.init(log_level="info")`
01. **FR-043**: Expose hooks for user customization of logging configuration

### 4.10 Unified Runtime

44. **FR-044**: Implement `Runtime` class as unified wrapper (optional, for convenience)
01. **FR-045**: `Runtime.executor()` returns managed Executor
01. **FR-046**: `Runtime.channel()`, `Runtime.oneshot()`, etc. return channels registered for auto-cleanup
01. **FR-047**: `Runtime.spawn()` spawns tasks managed by runtime
01. **FR-048**: `Runtime.wait()` waits for all spawned tasks
01. **FR-049**: `Runtime.shutdown(wait=True, timeout=30.0)` supports both graceful (wait then cancel) and immediate (`wait=False`) shutdown

### 4.11 Actors & Supervision

50. **FR-050**: Implement `Actor[Msg, Reply]` protocol with `async def handle(self, msg: Msg) -> Reply`
01. **FR-051**: Implement `spawn_actor(actor, capacity=100)` returning `ActorRef[Msg, Reply]`
01. **FR-052**: `ActorRef.send(msg)` for fire-and-forget, `ActorRef.ask(msg)` for request/response returning `Result`
01. **FR-053**: Backend-aware implementation:
    - `Backend.LOCAL`: Channel-based actors with aiologic mailbox
    - `Backend.RAY`: Wraps Ray remote actors (`@ray.remote` classes)
01. **FR-054**: Same `ActorRef` API regardless of backend—user code unchanged between local and Ray
01. **FR-055**: `TaskHandle.exit_reason` property returns `Ok(value) | Err(e) | Cancelled` after completion
01. **FR-056**: `spawn()` and `spawn_actor()` accept `on_exit` callback for lifecycle hooks
01. **FR-057**: Implement restart policies: `restart="never"` (default), `restart="on_failure"`, `restart="always"`
01. **FR-058**: `restart="on_failure"` restarts on `Err`, with configurable `max_restarts` and `restart_delay`
01. **FR-059**: Actors can spawn child actors; parent cancellation cascades to children (linked)

#### Supervision Trees

59a. **FR-059a**: Implement `Supervisor` for managing groups of child actors
59b. **FR-059b**: Implement supervision strategies:
\- `one_for_one`: restart only the failed child (default)
\- `one_for_all`: restart all children if any one fails
\- `rest_for_one`: restart failed child and all children started after it
59c. **FR-059c**: `Supervisor` accepts `max_restarts` and `restart_window` (e.g., 3 restarts in 5 seconds → shutdown)
59d. **FR-059d**: Supervisors can supervise other supervisors (nested trees)
59e. **FR-059e**: `Supervisor.start_child(actor)` and `Supervisor.stop_child(ref)` for dynamic child management

#### Actor Pools

59f. **FR-059f**: Implement `ActorPool[Msg, Reply]` for load-balanced dispatch across multiple identical actors
59g. **FR-059g**: `actor_pool(actor_class, size=N)` creates pool of N actors
59h. **FR-059h**: `pool.send(msg)` dispatches to next available actor (round-robin or least-loaded)
59i. **FR-059i**: `pool.map(func, items)` distributes work across pool, returns `Result[list[U], E]`
59j. **FR-059j**: `pool.broadcast(msg)` sends to all actors in pool
59k. **FR-059k**: Pool auto-replaces failed actors based on restart policy

#### Scheduling (Ray Backend)

59l. **FR-059l**: Resource requirements (`num_cpus`, `num_gpus`, `memory`) passed through to Ray
59m. **FR-059m**: Node affinity (`scheduling_strategy`, `node_id`) passed through to Ray
59n. **FR-059n**: Placement groups passed through via `placement_group` and `bundle_index` kwargs

#### Named Actors & Registry

59o. **FR-059o**: `spawn_actor(actor, name="foo")` registers actor by name
59p. **FR-059p**: `rt.get_actor(name)` retrieves actor by name, returns `Result[ActorRef, ActorNotFound]`
59q. **FR-059q**: `rt.whereis(name)` returns `Option[ActorRef]` (non-throwing lookup)
59r. **FR-059r**: `rt.register(name, ref)` manually registers existing actor
59s. **FR-059s**: `rt.unregister(name)` removes actor from registry
59t. **FR-059t**: Local backend: in-process dict registry
59u. **FR-059u**: Ray backend: uses Ray's named actor registry (`ray.get_actor(name)`)

#### Distributed Fault Tolerance (Ray Backend)

59v. **FR-059v**: Passthrough Ray fault tolerance options: `max_restarts`, `max_task_retries`, `lifetime`
59w. **FR-059w**: `max_restarts`: number of times Ray restarts actor on failure
59x. **FR-059x**: `max_task_retries`: number of times to retry failed actor method calls
59y. **FR-059y**: `lifetime="detached"`: actor survives driver exit; `lifetime="default"`: actor dies with driver

#### Health Monitoring Hooks

59z. **FR-059z**: `Supervisor.on_restart(callback)`: called when child actor restarts
59aa. **FR-059aa**: `Supervisor.on_failure(callback)`: called when child actor fails (before restart)
59ab. **FR-059ab**: `Supervisor.on_max_restarts(callback)`: called when actor exhausts restart limit
59ac. **FR-059ac**: Callbacks receive `(ref: ActorRef, error: Exception | None, attempt: int)`
59ad. **FR-059ad**: Hooks integrate with structlog for automatic structured logging

60. **FR-060**: Implement `ActorRef.stop()` for graceful shutdown (drain mailbox then exit)
01. **FR-061**: Ray actors serialize messages with msgspec; local actors pass by reference

### 4.12 Error Types

62. **FR-062**: All error types are dual: `msgspec.Struct` + `Exception` (can be used in Result or raised)
01. **FR-063**: Implement: `ChannelClosed`, `ChannelFull`, `ChannelEmpty`, `Timeout`, `Cancelled`, `BackendError`, `ActorStopped`, `ActorNotFound`

### 4.13 Persistence & Checkpointing

68. **FR-068**: Implement `Checkpointer` protocol for pluggable persistence
01. **FR-069**: Local backend: use `diskcache` for persistence (default: `~/.klaw/checkpoints/`)
01. **FR-070**: Ray backend: passthrough to Ray's checkpointing and Ray Workflows
01. **FR-071**: `spawn_actor(actor, checkpoint=True, checkpoint_interval=60)` enables actor state checkpointing
01. **FR-072**: Actor state auto-restored on restart from last checkpoint
01. **FR-073**: Implement `Workflow` context manager for checkpointed step execution
01. **FR-074**: `wf.step(name, func, *args)` executes and checkpoints step result
01. **FR-075**: Workflow resumes from last completed step on restart
01. **FR-076**: Checkpoint storage configurable via `runtime.init(checkpoint_path="...")`
01. **FR-077**: State serialized via msgspec for fast, compact storage

### 4.14 Migration

64. **FR-064**: Delete `klaw_core/async_/` directory
01. **FR-065**: Move `AsyncResult` to `klaw_core/runtime/result.py`
01. **FR-066**: Move async itertools to `klaw_core/runtime/itertools.py`
01. **FR-067**: Re-export moved items from `klaw_core/__init__.py` for flat imports

## 5. Non-Goals (Out of Scope)

1. **NG-001**: Custom failure detection protocols (heartbeats, membership) — uses Ray's built-in detection with passthrough options
1. **NG-002**: Additional backends (Dask, Joblib, Modal) — only Local and Ray supported; no plans for other backends
1. **NG-003**: Custom storage backends for persistence — only diskcache (local) and Ray (distributed) supported
1. **NG-004**: Distributed tracing integration (OpenTelemetry) — future work, hooks provided
1. **NG-005**: GUI or dashboard for monitoring — out of scope
1. **NG-006**: Custom actor scheduler — uses Ray's built-in placement; resources/affinity/placement groups are passthrough only

## 6. Design Considerations

### 6.1 Backend Strategy

**Local default, Ray opt-in.** Same code works on both:

| Environment           | Backend         | Use Case                    |
| --------------------- | --------------- | --------------------------- |
| Dev (quick iteration) | Local (default) | Fast startup, no overhead   |
| Dev (testing Ray)     | Ray (local)     | Verify Ray behavior locally |
| CI/tests              | Local or Ray    | Depending on test type      |
| Production            | Ray (cluster)   | Auto-detect or explicit     |

```python
# Quick dev iteration (instant startup, no processes)
runtime.init()

# Test Ray locally (starts local Ray cluster)
runtime.init(backend='ray')

# Production (auto-detect cluster or explicit)
runtime.init(backend='auto')  # detects Ray cluster
```

**Implementation parity**: Both backends implement the full API. Code written against local backend works unchanged on Ray.

### 6.2 Module Structure

```
klaw_core/
├── runtime/
│   ├── __init__.py       # init(), Executor, Backend, all re-exports
│   ├── _config.py        # RuntimeConfig, psutil detection
│   ├── _logging.py       # structlog configuration
│   ├── _backends/
│   │   ├── __init__.py
│   │   ├── local.py      # anyio + aiologic
│   │   └── ray.py        # optional Ray backend
│   ├── executor.py       # Executor, TaskHandle
│   ├── result.py         # AsyncResult (from async_/)
│   ├── itertools.py      # async_collect, etc. (from async_/)
│   ├── channels.py       # channel, oneshot, broadcast, watch, select
│   ├── actor.py          # Actor protocol, ActorRef, spawn_actor, ActorPool
│   ├── supervisor.py     # Supervisor, supervision strategies
│   ├── cancel.py         # cancel_scope, CancelScope
│   ├── timeout.py        # timeout()
│   ├── retry.py          # retry() using tenacity
│   ├── context.py        # Context, context(), current_context()
│   ├── errors.py         # ChannelClosed, Timeout, Cancelled, ActorStopped, etc.
│   ├── checkpoint.py     # Checkpointer protocol, LocalCheckpointer (diskcache)
│   ├── workflow.py       # Workflow context manager, checkpointed steps
│   └── _runtime.py       # Runtime unified wrapper
└── ...
```

### 6.3 Async Protocol Support

All components support `async with` and `async for`:

```python
async with Executor() as ex:
    async for result in ex.imap(process, items):
        ...

async with cancel_scope(timeout=5.0):
    async for item in rx:
        ...
```

### 6.4 Actor Usage

```python
from klaw_core.runtime import Actor, ActorRef


class Worker(Actor[Request, Result[Response, Error]]):
    async def handle(self, msg: Request) -> Result[Response, Error]:
        return Ok(Response(data=msg.id))


async with Runtime() as rt:
    # Spawn with restart policy
    ref: ActorRef[Request, Result[Response, Error]] = await rt.spawn_actor(
        Worker(),
        restart='on_failure',
        max_restarts=3,
    )

    # Fire-and-forget
    await ref.send(Request(id=1))

    # Request/response
    result = await ref.ask(Request(id=2))

    # Graceful shutdown
    await ref.stop()

# Actor Pools
pool = await rt.actor_pool(Worker, size=10)
results = await pool.map(process, items)  # distributes across pool
await pool.broadcast(ConfigUpdate(...))  # sends to all

# Supervision Trees
async with Supervisor(strategy='one_for_all', max_restarts=3) as sup:
    await sup.start_child(Worker())
    await sup.start_child(Worker())
    # If one fails, both restart

# Named Actors & Registry
cache = await rt.spawn_actor(CacheWorker(), name='cache')

# Lookup by name anywhere
cache_ref = await rt.get_actor('cache')  # Result[ActorRef, ActorNotFound]
cache_opt = await rt.whereis('cache')  # Option[ActorRef]

# Fault Tolerance (Ray backend)
ref = await rt.spawn_actor(
    Worker(),
    max_restarts=3,  # Ray restarts on failure
    max_task_retries=2,  # Retry failed method calls
    lifetime='detached',  # Survive driver exit
)

# Health Monitoring Hooks
async with Supervisor(strategy='one_for_one') as sup:
    sup.on_restart(lambda ref, err, n: log.warn(f'{ref} restarted ({n})'))
    sup.on_failure(lambda ref, err, n: log.error(f'{ref} failed: {err}'))
    sup.on_max_restarts(lambda ref, err, n: alert.critical(f'{ref} exhausted'))

# Persistence & Checkpointing
ref = await rt.spawn_actor(
    StatefulWorker(),
    checkpoint=True,
    checkpoint_interval=60,
)
# Local: diskcache; Ray: Ray checkpointing

# Workflow with checkpointed steps
async with Workflow(name='pipeline') as wf:
    data = await wf.step('fetch', fetch_data, url)
    result = await wf.step('process', process, data)
    # On restart, resumes from last completed step
```

### 6.5 Dual Error Types

Errors work both as Result values and exceptions:

```python
# As Result
result: Result[T, ChannelClosed] = tx.try_send(value)

# As exception
try:
    await rx.recv()
except ChannelClosed:
    ...
```

## 7. Technical Considerations

### 7.1 Dependencies

**Required:**

```toml
dependencies = [
    "anyio>=4.12.0",
    "aiologic>=0.4",
    "psutil>=5.9",
    "tenacity>=8.2",
    "structlog>=24.0",
    "msgspec>=0.18",
    "diskcache>=5.6",
    # existing: wrapt, pyarrow
]
```

**Optional:**

```toml
[project.optional-dependencies]
ray = ["ray>=2.52"]
test = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "hypothesis>=6.100",
    "mimesis>=19.0.0",
    "anyio[trio]>=4.12.0",
]
```

### 7.2 Python Version

- **Minimum**: Python 3.13 only
- **Features used**: PEP 695 generics, pattern matching, `type` statement

### 7.3 Backend Detection

```python
def _detect_backend() -> Backend:
    if env := os.environ.get('KLAW_BACKEND'):
        return Backend(env.lower())
    if _in_ray_cluster():
        return Backend.RAY
    return Backend.LOCAL
```

### 7.4 Context Propagation

Uses `contextvars` for automatic propagation across await boundaries. Executor captures and restores context in spawned tasks.

## 8. Success Metrics

1. **SM-001**: All existing `async_/` tests pass after migration to `runtime/`
1. **SM-002**: Benchmarks show no regression vs raw anyio (within 5%)
1. **SM-003**: Same code runs locally and on Ray cluster without modification
1. **SM-004**: Context (request_id) propagates correctly through spawned tasks
1. **SM-005**: All channel types pass Hypothesis property-based tests
1. **SM-006**: mypy/pyright pass in strict mode
1. **SM-007**: `runtime.init()` correctly auto-detects environment

## 9. Testing Strategy

### 9.1 Property-Based Testing (Hypothesis)

- Channel data integrity (no loss, FIFO order)
- Capacity limits respected
- Timeout bounds honored
- Context propagation preserved

### 9.2 Realistic Data (Mimesis)

- Test with realistic payloads (users, events, etc.)
- Verify serialization roundtrip for distributed channels

### 9.3 No Mocks

- All tests use real execution
- Test actual concurrency behavior
- Verify real timeouts and cancellation

## 10. Design Decisions (Resolved)

1. **DD-001**: `Runtime.shutdown(wait=True, timeout=30.0)` supports both modes—graceful (wait then cancel) and immediate (`wait=False`)

1. **DD-002**: Distributed channels enforce backpressure—sender blocks when capacity reached; use `try_send()` for non-blocking

1. **DD-003**: No true unbounded channels—default capacity is 10,000; use `unbounded=True` to explicitly opt into unlimited (at user's risk)
