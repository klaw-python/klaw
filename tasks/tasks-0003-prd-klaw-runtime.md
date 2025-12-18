# Tasks: klaw-runtime

Generated from: `0003-prd-klaw-runtime.md`

## Relevant Files

### Source Files (to create)

- `src/klaw_core/runtime/__init__.py` - Main re-exports: init(), Executor, Backend, channels, actors, etc.
- `src/klaw_core/runtime/_config.py` - RuntimeConfig, psutil detection, environment auto-detection
- `src/klaw_core/runtime/_logging.py` - Structlog configuration, context injection, log hooks
- `src/klaw_core/runtime/executor.py` - Executor class, TaskHandle, gather
- `src/klaw_core/runtime/_backends/__init__.py` - Backend protocol
- `src/klaw_core/runtime/_backends/local.py` - LocalBackend using anyio + aiologic
- `src/klaw_core/runtime/_backends/ray.py` - RayBackend wrapping Ray (optional)
- `src/klaw_core/runtime/channels.py` - channel, oneshot, broadcast, watch, select, Sender, Receiver
- `src/klaw_core/runtime/actor.py` - Actor protocol, ActorRef, spawn_actor, ActorPool
- `src/klaw_core/runtime/supervisor.py` - Supervisor, supervision strategies, health hooks
- `src/klaw_core/runtime/cancel.py` - cancel_scope, CancelScope
- `src/klaw_core/runtime/timeout.py` - timeout() function
- `src/klaw_core/runtime/retry.py` - retry() using tenacity
- `src/klaw_core/runtime/context.py` - Context, context(), current_context()
- `src/klaw_core/runtime/errors.py` - ChannelClosed, Timeout, Cancelled, ActorStopped, ActorNotFound, etc.
- `src/klaw_core/runtime/checkpoint.py` - Checkpointer protocol, LocalCheckpointer (diskcache)
- `src/klaw_core/runtime/workflow.py` - Workflow context manager, checkpointed steps
- `src/klaw_core/runtime/result.py` - AsyncResult (moved from async\_/)
- `src/klaw_core/runtime/itertools.py` - async*collect, async_race_ok, etc. (moved from async*/)
- `src/klaw_core/runtime/_runtime.py` - Runtime unified wrapper class

### Test Files (to create)

- `tests/runtime/test_config.py` - Tests for runtime.init(), auto-detection, Backend enum
- `tests/runtime/test_executor.py` - Tests for Executor, TaskHandle, map, imap, submit
- `tests/runtime/test_backends.py` - Tests for LocalBackend, RayBackend (mocked or real)
- `tests/runtime/test_channels.py` - Tests for channel, oneshot, broadcast, watch, select
- `tests/runtime/test_actor.py` - Tests for Actor, ActorRef, ActorPool
- `tests/runtime/test_supervisor.py` - Tests for Supervisor, restart policies, health hooks
- `tests/runtime/test_cancel.py` - Tests for cancel_scope, cancellation
- `tests/runtime/test_timeout.py` - Tests for timeout()
- `tests/runtime/test_retry.py` - Tests for retry()
- `tests/runtime/test_context.py` - Tests for Context, context propagation
- `tests/runtime/test_checkpoint.py` - Tests for Checkpointer, Workflow
- `tests/runtime/test_runtime.py` - Tests for unified Runtime wrapper
- `tests/runtime/test_migration.py` - Tests verifying async\_/ migration works

### Files to Modify

- `src/klaw_core/__init__.py` - Add runtime re-exports, remove async\_ imports
- `pyproject.toml` - Add new dependencies (psutil, tenacity, structlog, diskcache, ray optional)

### Files to Delete

- `src/klaw_core/async_/__init__.py`
- `src/klaw_core/async_/result.py`
- `src/klaw_core/async_/itertools.py`
- `src/klaw_core/async_/cache.py`

### Notes

- Tests use `pytest` with `pytest-asyncio` (asyncio_mode = "auto")
- Run tests: `uv run pytest workspaces/python/klaw-core/tests/`
- Run specific test: `uv run pytest workspaces/python/klaw-core/tests/runtime/test_channels.py`
- Type check: `uv run mypy workspaces/python/klaw-core/src/`
- Use Hypothesis for property-based testing, Mimesis for fake data
- No mocks—test real execution behavior

## Tasks

- [x] 1.0 Project Setup & Dependencies
  - [x] 1.1 Update `pyproject.toml` to add required dependencies: `psutil>=5.9`, `tenacity>=8.2`, `structlog>=24.0`, `diskcache>=5.6`
  - [x] 1.2 Add Ray dependency (required): `ray>=2.52.1` to main dependencies
  - [x] 1.3 Add `mimesis>=18.0.0` to dev dependencies for testing
  - [x] 1.4 Create `src/klaw_core/runtime/` directory structure with `__init__.py`
  - [x] 1.5 Create `tests/runtime/` directory with `__init__.py` and `conftest.py`
  - [x] 1.6 Run `uv sync` to install new dependencies and verify no conflicts

- [x] 2.0 Runtime Core: Configuration & Initialization
  - [x] 2.1 Create `runtime/errors.py` with dual struct+exception error types: `ChannelClosed`, `ChannelFull`, `ChannelEmpty`, `Timeout`, `Cancelled`, `BackendError`, `ActorStopped`, `ActorNotFound`
  - [x] 2.2 Create `runtime/_config.py` with `RuntimeConfig` dataclass and `Backend` enum (LOCAL, RAY)
  - [x] 2.3 Implement `_detect_backend()` using environment variables (`KLAW_BACKEND`) and Ray cluster detection
  - [x] 2.4 Implement `_detect_concurrency()` using psutil (physical cores, available memory, container detection)
  - [x] 2.5 Implement `init(backend, concurrency, log_level, checkpoint_path, **backend_kwargs)` function
  - [x] 2.6 Implement `get_config()` to retrieve current global config
  - [x] 2.7 Write tests for `runtime.init()`, auto-detection, and environment variable handling

- [x] 3.0 Executor & Backends
  - [x] 3.1 Create `runtime/_backends/__init__.py` with `ExecutorBackend` protocol
  - [x] 3.2 Implement `runtime/_backends/local.py` `LocalBackend` using anyio task groups and aiologic
  - [x] 3.3 Implement `LocalBackend.run()` for CPU-bound work using `anyio.to_thread.run_sync()`
  - [x] 3.4 Implement `runtime/executor.py` `TaskHandle` class with `cancel()`, `is_running()`, `exit_reason`, `__await__`
  - [x] 3.5 Implement `Executor` class as async context manager with `map()`, `imap()`, `submit()`, `gather()`
  - [x] 3.6 Implement per-task backend kwargs override (merge with global config)
  - [x] 3.7 Create `runtime/_backends/ray.py` `RayBackend` with lazy Ray import and passthrough kwargs
  - [x] 3.8 Implement Ray backend `run()` using `ray.remote()` and async `ray.get()`
  - [x] 3.9 Write tests for Executor with LocalBackend (map, imap, submit, gather)
  - [x] 3.10 Write tests for TaskHandle (cancel, is_running, exit_reason)
  - [x] 3.11 Write tests for RayBackend (can be skipped if Ray not installed)

- [ ] 4.0 Channels (mpmc, oneshot, broadcast, watch, select)
  - [x] 4.1 Create `runtime/channels.py` with `Sender[T]` and `Receiver[T]` protocols
  - [x] 4.2 Implement `channel(capacity, distributed, unbounded)` returning `tuple[Sender, Receiver]`
  - [x] 4.3 Implement `LocalChannel` using `anyio.MemoryObjectStream` with capacity limiting (default 10,000)
        **Note:** Changed from aiologic.Queue to anyio - provides MPMC with ref-counted clones, native cancellation
  - [x] 4.4 Implement `Sender.send()` (async, raises ChannelClosed), `try_send()` (returns Result)
  - [x] 4.5 Implement `Receiver.recv()` (async, raises ChannelClosed), `try_recv()` (returns Result)
  - [x] 4.6 Implement `Sender.clone()`, `Receiver.clone()` for mpmc
  - [x] 4.7 Implement `Receiver.__aiter__` for `async for item in rx` pattern
  - [x] 4.8 Implement `Sender.close()` and closed state propagation
  - [ ] 4.9 Implement `oneshot[T]()` for single-value, single-use channels
  - [ ] 4.10 Implement `broadcast[T](capacity)` where all receivers get every message
  - [ ] 4.11 Implement `watch[T](initial)` for latest-value observation with `borrow()` and `changed()`
  - [ ] 4.12 Implement `select(*receivers, timeout)` for multiplexing multiple receivers
  - [ ] 4.13 Implement `RayChannel` wrapping `ray.util.queue.Queue` for `distributed=True`
        **Note:** Changed from custom msgspec IPC to Ray - cross-platform, already a dependency, handles serialization
  - [ ] 4.14 Implement RayChannel Sender/Receiver adapters matching local channel API
  - [ ] 4.15 Write Hypothesis property tests: no data loss, FIFO order, capacity respected
  - [ ] 4.16 Write tests for oneshot, broadcast, watch, select
  - [ ] 4.17 Write tests for distributed channels (RayChannel)

- [ ] 5.0 Cancellation, Timeout & Retry
  - [ ] 5.1 Create `runtime/cancel.py` with `CancelScope` class wrapping anyio cancel scope
  - [ ] 5.2 Implement `cancel_scope(timeout)` as async context manager
  - [ ] 5.3 Implement `CancelScope.cancel()` for explicit cancellation
  - [ ] 5.4 Ensure cancelled tasks return `Err(Cancelled(reason))`
  - [ ] 5.5 Create `runtime/timeout.py` with `timeout(awaitable, seconds)` returning `Result[T, E | Timeout]`
  - [ ] 5.6 Create `runtime/retry.py` with `retry()` using tenacity under the hood
  - [ ] 5.7 Implement retry on `Err` by default with configurable `retry_on` predicate
  - [ ] 5.8 Implement `attempts`, `backoff`, `max_delay` parameters
  - [ ] 5.9 Write tests for cancel_scope (timeout, explicit cancel)
  - [ ] 5.10 Write tests for timeout() with Hypothesis for timing bounds
  - [ ] 5.11 Write tests for retry() with various retry policies

- [ ] 6.0 Context Propagation & Structured Logging
  - [ ] 6.1 Create `runtime/context.py` with `Context` dataclass (request_id, trace_id, span_id, extra)
  - [ ] 6.2 Implement `context(**values)` as async context manager using contextvars
  - [ ] 6.3 Implement `current_context()` to retrieve current context
  - [ ] 6.4 Ensure Executor propagates context to spawned tasks (capture and restore)
  - [ ] 6.5 Create `runtime/_logging.py` with structlog configuration
  - [ ] 6.6 Implement auto-injection of context (request_id, trace_id) into log entries
  - [ ] 6.7 Implement log level configuration via `runtime.init(log_level=...)`, silent by default
  - [ ] 6.8 Implement logging hooks for user customization
  - [ ] 6.9 Write tests for context propagation through executor tasks
  - [ ] 6.10 Write tests for structlog integration and context injection

- [ ] 7.0 Actors, Supervision & Pools
  - [ ] 7.1 Create `runtime/actor.py` with `Actor[Msg, Reply]` protocol and `handle()` method
  - [ ] 7.2 Implement `ActorRef[Msg, Reply]` with `send()` (fire-and-forget) and `ask()` (request/response)
  - [ ] 7.3 Implement `spawn_actor(actor, name, capacity, restart, ...)` returning `ActorRef`
  - [ ] 7.4 Implement local actor using channel as mailbox with message loop
  - [ ] 7.5 Implement `ActorRef.stop()` for graceful shutdown (drain mailbox then exit)
  - [ ] 7.6 Create `runtime/supervisor.py` with `Supervisor` class
  - [ ] 7.7 Implement supervision strategies: `one_for_one`, `one_for_all`, `rest_for_one`
  - [ ] 7.8 Implement `max_restarts` and `restart_window` for rate limiting restarts
  - [ ] 7.9 Implement `Supervisor.start_child()` and `Supervisor.stop_child()` for dynamic management
  - [ ] 7.10 Implement nested supervisors (supervisors can supervise other supervisors)
  - [ ] 7.11 Implement restart policies on actors: `restart="never"`, `"on_failure"`, `"always"`
  - [ ] 7.12 Implement `ActorPool[Msg, Reply]` for load-balanced dispatch
  - [ ] 7.13 Implement `actor_pool(actor_class, size)` factory
  - [ ] 7.14 Implement `pool.send()` (round-robin/least-loaded), `pool.map()`, `pool.broadcast()`
  - [ ] 7.15 Implement pool auto-replace failed actors based on restart policy
  - [ ] 7.16 Implement Ray backend actor using `@ray.remote` class wrapper
  - [ ] 7.17 Ensure same `ActorRef` API for both local and Ray backends
  - [ ] 7.18 Write tests for Actor, ActorRef (send, ask, stop)
  - [ ] 7.19 Write tests for Supervisor with all strategies
  - [ ] 7.20 Write tests for ActorPool (send, map, broadcast, auto-replace)

- [ ] 8.0 Named Actors, Registry & Fault Tolerance
  - [ ] 8.1 Implement named actor registration: `spawn_actor(actor, name="foo")`
  - [ ] 8.2 Implement `rt.get_actor(name)` returning `Result[ActorRef, ActorNotFound]`
  - [ ] 8.3 Implement `rt.whereis(name)` returning `Option[ActorRef]`
  - [ ] 8.4 Implement `rt.register(name, ref)` and `rt.unregister(name)`
  - [ ] 8.5 Local backend: in-process dict registry
  - [ ] 8.6 Ray backend: wrap `ray.get_actor(name)` for registry
  - [ ] 8.7 Implement Ray fault tolerance passthrough: `max_restarts`, `max_task_retries`, `lifetime`
  - [ ] 8.8 Implement health monitoring hooks: `on_restart`, `on_failure`, `on_max_restarts`
  - [ ] 8.9 Implement callback signature: `(ref: ActorRef, error: Exception | None, attempt: int)`
  - [ ] 8.10 Integrate health hooks with structlog for automatic structured logging
  - [ ] 8.11 Write tests for named actors and registry lookup
  - [ ] 8.12 Write tests for health monitoring hooks

- [ ] 9.0 Persistence & Checkpointing
  - [ ] 9.1 Create `runtime/checkpoint.py` with `Checkpointer` protocol
  - [ ] 9.2 Implement `LocalCheckpointer` using diskcache (default path: `~/.klaw/checkpoints/`)
  - [ ] 9.3 Implement state serialization using msgspec for fast, compact storage
  - [ ] 9.4 Implement actor checkpointing: `spawn_actor(actor, checkpoint=True, checkpoint_interval=60)`
  - [ ] 9.5 Implement actor state auto-restore on restart from last checkpoint
  - [ ] 9.6 Create `runtime/workflow.py` with `Workflow` async context manager
  - [ ] 9.7 Implement `wf.step(name, func, *args)` for checkpointed step execution
  - [ ] 9.8 Implement workflow resume from last completed step on restart
  - [ ] 9.9 Implement checkpoint storage configuration via `runtime.init(checkpoint_path="...")`
  - [ ] 9.10 Implement Ray backend passthrough to Ray Workflows and Ray checkpointing
  - [ ] 9.11 Write tests for LocalCheckpointer save/load roundtrip
  - [ ] 9.12 Write tests for actor checkpointing and restore
  - [ ] 9.13 Write tests for Workflow step checkpointing and resume

- [ ] 10.0 Migration: Move async\_/ to runtime/
  - [ ] 10.1 Copy `async_/result.py` to `runtime/result.py`, update imports
  - [ ] 10.2 Copy `async_/itertools.py` to `runtime/itertools.py`, update to use runtime config for concurrency
  - [ ] 10.3 Copy `async_/cache.py` contents (async_lru_safe) to appropriate location
  - [ ] 10.4 Update `runtime/__init__.py` to re-export AsyncResult, async_collect, async_race_ok, etc.
  - [ ] 10.5 Update `klaw_core/__init__.py` to import from `runtime` instead of `async_`
  - [ ] 10.6 Delete `async_/` directory entirely
  - [ ] 10.7 Update `tests/test_async.py` imports to use new paths (or keep if re-exports work)
  - [ ] 10.8 Run all existing tests to verify migration didn't break anything
  - [ ] 10.9 Run mypy to verify type checking passes

- [ ] 11.0 Unified Runtime Wrapper
  - [ ] 11.1 Create `runtime/_runtime.py` with `Runtime` class as async context manager
  - [ ] 11.2 Implement `Runtime.executor()` returning managed Executor
  - [ ] 11.3 Implement `Runtime.channel()`, `Runtime.oneshot()`, etc. for auto-cleanup registration
  - [ ] 11.4 Implement `Runtime.spawn()` and `Runtime.spawn_actor()` for managed task/actor spawning
  - [ ] 11.5 Implement `Runtime.wait()` to wait for all spawned tasks
  - [ ] 11.6 Implement `Runtime.shutdown(wait=True, timeout=30.0)` with graceful and immediate modes
  - [ ] 11.7 Implement graceful shutdown: close channels, wait for tasks, then cancel
  - [ ] 11.8 Add Runtime re-exports to `runtime/__init__.py`
  - [ ] 11.9 Write tests for Runtime lifecycle (spawn, wait, shutdown)
  - [ ] 11.10 Write tests for graceful vs immediate shutdown

- [ ] 12.0 Documentation & Final Integration
  - [ ] 12.1 Update `klaw_core/__init__.py` with complete runtime re-exports for flat imports
  - [ ] 12.2 Add docstrings to all public APIs following existing conventions
  - [ ] 12.3 Create usage examples in docstrings for key APIs (Executor, channels, actors)
  - [ ] 12.4 Run full test suite: `uv run pytest workspaces/python/klaw-core/tests/`
  - [ ] 12.5 Run mypy strict mode: `uv run mypy workspaces/python/klaw-core/src/`
  - [ ] 12.6 Run ruff linting: `uv run ruff check workspaces/python/klaw-core/src/`
  - [ ] 12.7 Verify all success metrics from PRD are met
  - [ ] 12.8 Update README.md with runtime module overview and quick start
