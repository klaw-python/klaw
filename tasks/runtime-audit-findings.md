# Runtime Module Audit Findings

**Date:** 2024-12-18
**Scope:** `workspaces/python/klaw-core/src/klaw_core/runtime/`
**Status:** Task 4.0 (Channels) in progress, Tasks 1-3 complete

## Executive Summary

Comprehensive review of the klaw-core runtime module identified **8 issues** across 6 files. The core architecture is sound, but there are critical correctness issues around cancellation races and timeout handling that must be fixed before production use.

### Issue Severity Distribution

| Severity | Count | Description |
|----------|-------|-------------|
| 🔴 HIGH | 3 | Correctness bugs, race conditions |
| 🟡 MEDIUM | 3 | API inconsistencies, dead code |
| 🟢 LOW | 2 | Polish, unused features |

---

## Findings by Priority

### 🔴 HIGH-1: TaskHandle Cancellation Races

**File:** `runtime/executor.py`
**Lines:** TaskHandle class (~L50-150)

**Problem:**
`TaskHandle.cancel()` can race with `_complete()` / `_fail()` from backends:
- Cancel called before backend attaches CancelScope → task still runs and overwrites cancelled state
- No guard preventing `_complete`/`_fail` from overwriting previous terminal state
- First terminal event should "win" but currently last one does

**Impact:** Cancelled tasks may report success; successful tasks may report cancelled.

**Fix:**

```python
# In executor.py - TaskHandle class

class TaskHandle(Generic[T]):
    __slots__ = (
        "_result",
        "_exception",
        "_exit_reason",
        "_completed",  # Add this field
        "_event",
        "_cancel_scope",
        "_on_cancel",  # Add this for Ray integration
    )

    def __init__(self) -> None:
        self._result: T | None = None
        self._exception: BaseException | None = None
        self._exit_reason: ExitReason = ExitReason.PENDING
        self._completed: bool = False  # Terminal state flag
        self._event: anyio.Event = anyio.Event()
        self._cancel_scope: anyio.CancelScope | None = None
        self._on_cancel: Callable[[str | None], None] | None = None

    def _complete(self, result: T, exit_reason: ExitReason = ExitReason.SUCCESS) -> None:
        """Mark task as complete with a result, unless already completed/cancelled."""
        if self._completed:
            return  # First terminal state wins
        self._result = result
        self._exit_reason = exit_reason
        self._completed = True
        self._event.set()

    def _fail(self, exc: BaseException, exit_reason: ExitReason = ExitReason.ERROR) -> None:
        """Mark task as failed with an exception, unless already completed/cancelled."""
        if self._completed:
            return  # First terminal state wins
        self._exception = exc
        self._exit_reason = exit_reason
        self._completed = True
        self._event.set()

    def _set_on_cancel(self, cb: Callable[[str | None], None]) -> None:
        """Set callback for cancellation (used by RayBackend)."""
        self._on_cancel = cb

    def cancel(self, reason: str | None = None) -> None:
        """Cancel the task. First terminal state wins."""
        if self._completed:
            return
        # Call backend-specific cancel hook (e.g., ray.cancel)
        if self._on_cancel is not None:
            try:
                self._on_cancel(reason)
            except Exception:
                pass  # Best effort
        # Cancel via scope if available
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()
        # Set terminal state
        self._exit_reason = ExitReason.CANCELLED
        self._exception = CancelledError(reason or "Task cancelled")
        self._completed = True
        self._event.set()
```

---

### 🔴 HIGH-2: CancelScope Created Too Late in LocalBackend

**File:** `runtime/_backends/local.py`
**Lines:** `run()` method and `_execute()` inner function

**Problem:**
CancelScope is created inside `_execute()` which runs asynchronously after `run()` returns. If user calls `handle.cancel()` immediately after `run()`, `_cancel_scope` is still `None` and cancel is a no-op.

**Impact:** Early cancellation requests are silently ignored.

**Fix:**

```python
# In _backends/local.py - LocalBackend class

async def run(
    self,
    fn: Callable[..., T] | Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> TaskHandle[T]:
    """Run a function as a managed task."""
    handle: TaskHandle[T] = TaskHandle()
    tg = await self._ensure_task_group()
    self._task_handles.append(handle)
    self._task_count.up()

    # Create CancelScope BEFORE scheduling so cancel() works immediately
    scope = anyio.CancelScope()
    handle._set_cancel_scope(scope)

    async def _execute() -> None:
        try:
            with scope:
                # Check if already cancelled before starting work
                if scope.cancel_called:
                    handle._fail(
                        CancelledError("Task cancelled before start"),
                        ExitReason.CANCELLED,
                    )
                    return

                try:
                    if inspect.iscoroutinefunction(fn):
                        result = await fn(*args, **kwargs)
                    else:
                        result = await anyio.to_thread.run_sync(
                            lambda: fn(*args, **kwargs),
                            limiter=self._limiter,
                        )

                    # Only complete if not cancelled during execution
                    if not scope.cancel_called:
                        handle._complete(result)
                    else:
                        handle._fail(
                            CancelledError("Task cancelled"),
                            ExitReason.CANCELLED,
                        )

                except Exception as e:
                    if scope.cancel_called:
                        handle._fail(
                            CancelledError("Task cancelled"),
                            ExitReason.CANCELLED,
                        )
                    else:
                        handle._fail(e, ExitReason.ERROR)
        finally:
            self._task_count.down()

    tg.start_soon(_execute)
    return handle
```

---

### 🔴 HIGH-3: Wrong TimeoutError Exception Type

**File:** `runtime/_backends/local.py`
**Lines:** `_wait_for_tasks()` and `shutdown()` methods

**Problem:**
Code catches `TimeoutError` (builtins) but `anyio.fail_after()` raises `anyio.TimeoutError` which is a different exception class.

**Impact:** Timeouts are not caught, causing unhandled exceptions.

**Fix:**

```python
# At top of _backends/local.py, update imports:

import anyio
from anyio import CancelScope, CapacityLimiter, TaskGroup
from anyio import get_cancelled_exc_class

# Add explicit import for anyio's TimeoutError
try:
    from anyio import TimeoutError as AnyioTimeoutError
except ImportError:
    # Fallback for older anyio versions
    AnyioTimeoutError = TimeoutError

# In _wait_for_tasks method:
async def _wait_for_tasks(self, timeout: float | None = None) -> None:
    """Wait for all tasks to complete with optional timeout."""
    if timeout is not None:
        try:
            with anyio.fail_after(timeout):
                await self._task_count.wait_for_zero()
        except AnyioTimeoutError:
            # Timeout waiting for tasks
            raise TimeoutError(f"Timed out waiting for tasks after {timeout}s") from None
    else:
        await self._task_count.wait_for_zero()

# In shutdown method:
async def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:
    """Shutdown the backend."""
    if not self._started:
        return

    if wait:
        try:
            await self._wait_for_tasks(timeout)
        except AnyioTimeoutError:
            # Timeout during graceful shutdown, force cancel
            await self._cancel_all_tasks()

    # ... rest of shutdown
```

---

### 🟡 MEDIUM-1: Dead Hook Processor in Logging

**File:** `runtime/_logging.py`
**Lines:** `_create_hook_processor()` function

**Problem:**
`_create_hook_processor()` is defined but never added to the structlog processor chain. The `add_log_hook()`, `remove_log_hook()`, and `clear_log_hooks()` functions have no effect.

**Impact:** Logging hooks feature is completely non-functional.

**Fix:**

```python
# In _logging.py - update _get_shared_processors():

def _get_shared_processors() -> list[Any]:
    """Get processors shared between structlog and stdlib logging."""
    import structlog

    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
        _create_hook_processor(),  # ADD THIS LINE - wire hooks into pipeline
    ]
```

---

### 🟡 MEDIUM-2: Protocol Methods Return `Any` Instead of `Result`

**File:** `runtime/channels.py`
**Lines:** `Sender` and `Receiver` protocol definitions

**Problem:**
Protocol methods `try_send()` and `try_recv()` are typed to return `Any`, but docstrings and implementations return `Result` types. This defeats type checking.

**Impact:** No type safety for non-blocking channel operations.

**Fix:**

```python
# In channels.py - update protocol definitions:

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull

class Sender(Protocol[T]):
    """Protocol for sending values into a channel."""

    @abstractmethod
    async def send(self, value: T) -> None:
        """Send a value, blocking if channel is at capacity."""
        ...

    @abstractmethod
    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        """Send a value without blocking.

        Returns `Ok(None)` if queued, or `Err(ChannelFull | ChannelClosed)`.
        """
        ...

    @abstractmethod
    def clone(self) -> Sender[T]:
        """Clone this sender for multi-producer use."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close this sender half of the channel."""
        ...


class Receiver(Protocol[T_co]):
    """Protocol for receiving values from a channel."""

    @abstractmethod
    async def recv(self) -> T_co:
        """Receive the next value, blocking if channel is empty."""
        ...

    @abstractmethod
    async def try_recv(self) -> Result[T_co, ChannelEmpty | ChannelClosed]:
        """Receive the next value without blocking.

        Returns `Ok(value)` if available, or `Err(ChannelEmpty | ChannelClosed)`.
        """
        ...

    @abstractmethod
    def clone(self) -> Receiver[T_co]:
        """Clone this receiver for multi-consumer use."""
        ...

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[T_co]:
        """Iterate over messages as they arrive."""
        ...

    @abstractmethod
    async def __anext__(self) -> T_co:
        """Get next message for async for iteration."""
        ...
```

---

### 🟡 MEDIUM-3: Incorrect MPMC Documentation

**File:** `runtime/channels.py`
**Lines:** Module docstring, `Receiver.clone()` docstring

**Problem:**
Documentation says "All clones receive the same messages (MPMC semantics)" which describes **broadcast** semantics. MPMC (multi-producer multi-consumer) means each message goes to exactly **one** receiver (competing consumers).

**Impact:** Users will misunderstand channel behavior.

**Fix:**

```python
# In channels.py - update module docstring:

"""Channels: multi-producer multi-consumer, oneshot, broadcast, watch, select.

Provides ergonomic channel types for passing data between concurrent tasks:
- `channel[T]()`: Multi-producer multi-consumer queue (each message delivered to ONE receiver)
- `oneshot[T]()`: Single-value, single-use channel
- `broadcast[T]()`: All receivers get every message (fan-out)
- `watch[T](initial)`: Latest-value observation with `.borrow()` and `.changed()`
- `select(*receivers)`: Multiplex multiple receivers

Note: `channel()` uses MPMC queue semantics where messages are distributed across
receivers. For broadcast semantics where ALL receivers see EVERY message, use
`broadcast()` instead.

...
"""

# Update Receiver.clone() docstring:

def clone(self) -> Receiver[T_co]:
    """Clone this receiver for multi-consumer use.

    Returns a new receiver that shares the same underlying channel.
    Each clone competes for messages - each message is delivered to
    exactly ONE receiver (true MPMC queue semantics).

    For broadcast semantics where all receivers see all messages,
    use `broadcast()` instead.

    This is a synchronous operation: it only increments a reference
    counter and returns immediately (no I/O or waiting involved).

    Returns:
        A new Receiver[T] pointing to the same channel.

    Example:
        ```python
        tx, rx1 = await channel[int]()
        rx2 = rx1.clone()  # Synchronous, returns immediately
        await tx.send(42)
        # Only ONE of rx1 or rx2 will receive 42, not both
        v = await rx1.recv()  # Gets 42
        # rx2.recv() would block waiting for next message
        ```
    """
    ...
```

---

### 🟢 LOW-1: RuntimeConfig.concurrency Unused

**File:** `runtime/executor.py`
**Lines:** `Executor.__init__()` method

**Problem:**
`RuntimeConfig.concurrency` is computed via psutil (physical cores, memory) but never used when creating LocalBackend. The auto-detected concurrency value is wasted.

**Impact:** Users don't benefit from intelligent concurrency detection.

**Fix:**

```python
# In executor.py - update Executor.__init__():

def __init__(
    self,
    backend: Backend | None = None,
    max_workers: int | None = None,
    **backend_kwargs: Any,
) -> None:
    """Initialize executor with optional backend configuration."""
    config = get_config()

    if backend is None:
        self._backend_type = config.backend
    else:
        self._backend_type = backend

    # Merge backend kwargs, using config.concurrency as default for max_workers
    merged_kwargs = {**config.backend_kwargs, **backend_kwargs}

    # Apply auto-detected concurrency if not explicitly set
    if self._backend_type == Backend.LOCAL:
        if max_workers is not None:
            merged_kwargs["max_workers"] = max_workers
        elif "max_workers" not in merged_kwargs:
            # Use auto-detected concurrency from config
            merged_kwargs["max_workers"] = config.concurrency

    self._backend_kwargs = merged_kwargs
    self._backend: ExecutorBackend | None = None
    self._handles: list[TaskHandle[Any]] = []
    self._started: bool = False
```

---

### 🟢 LOW-2: RayBackend Cancellation Not Wired

**File:** `runtime/_backends/ray.py`
**Lines:** `run()` method

**Problem:**
When user calls `handle.cancel()`, it only sets local state. The Ray task continues running because `ray.cancel()` is never called on the ObjectRef.

**Impact:** Cancelled Ray tasks waste compute resources.

**Fix:**

```python
# In _backends/ray.py - update run() method:

async def run(
    self,
    fn: Callable[..., T] | Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> TaskHandle[T]:
    """Run a function as a Ray remote task."""
    import ray

    handle: TaskHandle[T] = TaskHandle()

    # Create Ray remote function with configured options
    remote_fn = ray.remote(**self._ray_options)(fn)
    object_ref = remote_fn.remote(*args, **kwargs)

    # Store ref for tracking
    self._object_refs[handle] = object_ref
    self._task_handles.append(handle)

    # Wire cancellation to Ray
    def _on_cancel(reason: str | None) -> None:
        try:
            ray.cancel(object_ref, force=False)  # Graceful cancel
        except Exception:
            pass  # Best effort - task may have already completed

    handle._set_on_cancel(_on_cancel)

    # Start background task to wait for result
    async def _wait_for_result() -> None:
        try:
            result = await asyncio.to_thread(ray.get, object_ref)
            handle._complete(result)
        except ray.exceptions.TaskCancelledError:
            handle._fail(
                CancelledError("Ray task cancelled"),
                ExitReason.CANCELLED,
            )
        except ray.exceptions.RayTaskError as e:
            handle._fail(e, ExitReason.ERROR)
        except Exception as e:
            handle._fail(e, ExitReason.ERROR)

    asyncio.create_task(_wait_for_result())
    return handle
```

---

## Additional Recommendations

### 1. LocalSender Capacity Tracking

**File:** `runtime/channels.py`

Currently `LocalSender.try_send()` reads capacity from `self._stream.statistics().max_buffer_size` which couples to anyio internals.

**Fix:** Store capacity explicitly:

```python
class LocalSender(Generic[T]):
    __slots__ = ("_stream", "_capacity")

    def __init__(self, stream: MemoryObjectSendStream[T], capacity: int | float) -> None:
        self._stream = stream
        self._capacity = capacity

    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        try:
            self._stream.send_nowait(value)
            return Ok(None)
        except anyio.WouldBlock:
            # Use stored capacity, not stream internals
            cap = int(self._capacity) if self._capacity != math.inf else 0
            return Err(ChannelFull(cap))
        except anyio.BrokenResourceError:
            return Err(ChannelClosed())
        except anyio.ClosedResourceError:
            return Err(ChannelClosed())

# Update channel() factory:
async def channel(
    capacity: int = 10000, distributed: bool = False, unbounded: bool = False
) -> tuple[Sender[T], Receiver[T]]:
    ...
    tx: Sender[T] = LocalSender(send_stream, buffer_size)  # Pass buffer_size
    rx: Receiver[T] = LocalReceiver(recv_stream)
    return tx, rx
```

### 2. Clean Up Task Handle Lists

Both `LocalBackend` and `RayBackend` append to `_task_handles` and never shrink them, causing memory growth.

**Fix:** Clear in `shutdown()`:

```python
# In LocalBackend.shutdown():
async def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:
    ...
    # After all cleanup
    self._task_handles.clear()
    self._started = False

# In RayBackend.shutdown():
async def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:
    ...
    self._task_handles.clear()
    self._object_refs.clear()
    self._started = False
```

### 3. Executor.submit backend_kwargs Documentation

The `submit()` docstring mentions `backend_kwargs` override but the implementation drops it unused.

**Fix:** Either implement or remove from docs:

```python
# Option A: Remove from docs (simpler)
async def submit(
    self,
    fn: Callable[..., T] | Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> TaskHandle[T]:
    """Submit a function for execution.

    Args:
        fn: The function to execute (sync or async).
        *args: Positional arguments passed to fn.
        **kwargs: Keyword arguments passed to fn.

    Returns:
        TaskHandle for tracking and awaiting the result.
    """
    self._ensure_started()
    assert self._backend is not None
    handle = await self._backend.run(fn, *args, **kwargs)
    self._handles.append(handle)
    return handle
```

---

## Task Checklist

### Phase 1: Critical Fixes (Do First)

- [ ] **HIGH-1:** Fix TaskHandle cancellation races
  - [ ] Add `_completed` flag to TaskHandle
  - [ ] Guard `_complete()` and `_fail()` with early return if completed
  - [ ] Add `_on_cancel` callback mechanism
  - [ ] Update `cancel()` to check completed state first
  - [ ] Write tests: cancel-before-start, cancel-during, cancel-after

- [ ] **HIGH-2:** Fix LocalBackend CancelScope timing
  - [ ] Create CancelScope in `run()` before scheduling
  - [ ] Pass scope to `_execute()` inner function
  - [ ] Check `scope.cancel_called` before starting work
  - [ ] Write test: immediate cancel after run() returns

- [ ] **HIGH-3:** Fix TimeoutError import
  - [ ] Import `anyio.TimeoutError` or use `anyio.get_cancelled_exc_class()`
  - [ ] Update `_wait_for_tasks()` exception handler
  - [ ] Update `shutdown()` exception handler
  - [ ] Write test: verify timeout behavior works

### Phase 2: API Consistency

- [ ] **MEDIUM-1:** Wire logging hooks
  - [ ] Add `_create_hook_processor()` to `_get_shared_processors()`
  - [ ] Write test: verify hook receives log events

- [ ] **MEDIUM-2:** Fix protocol return types
  - [ ] Change `Sender.try_send` return type to `Result[None, ChannelFull | ChannelClosed]`
  - [ ] Change `Receiver.try_recv` return type to `Result[T_co, ChannelEmpty | ChannelClosed]`
  - [ ] Run mypy to verify no regressions

- [ ] **MEDIUM-3:** Fix MPMC documentation
  - [ ] Update module docstring
  - [ ] Update `Receiver.clone()` docstring
  - [ ] Update example in clone docstring

### Phase 3: Polish

- [ ] **LOW-1:** Use RuntimeConfig.concurrency
  - [ ] Update Executor.__init__ to use config.concurrency as default max_workers
  - [ ] Preserve explicit max_workers override behavior

- [ ] **LOW-2:** Wire Ray cancellation
  - [ ] Add `_on_cancel` callback in RayBackend.run()
  - [ ] Call `ray.cancel(object_ref)` in callback
  - [ ] Handle `ray.exceptions.TaskCancelledError` in result waiter

### Phase 4: Additional Cleanup

- [ ] Fix LocalSender capacity tracking (store explicitly)
- [ ] Clear task handle lists in shutdown()
- [ ] Fix or remove backend_kwargs from submit() docs

---

## Test Commands

```bash
# Run all runtime tests
uv run pytest workspaces/python/klaw-core/tests/runtime/ -v

# Run specific test files
uv run pytest workspaces/python/klaw-core/tests/runtime/test_executor.py -v
uv run pytest workspaces/python/klaw-core/tests/runtime/test_channels*.py -v
uv run pytest workspaces/python/klaw-core/tests/runtime/test_task_handle.py -v

# Type checking
uv run mypy workspaces/python/klaw-core/src/klaw_core/runtime/

# Linting
uv run ruff check workspaces/python/klaw-core/src/klaw_core/runtime/
```

---

## Architecture Decisions

### Decision 1: anyio vs aiologic for Local Channels

**Decision:** Keep `anyio.MemoryObjectStream` for LocalChannel implementation.

**Rationale:**
- PRD specified `aiologic.Queue` but anyio provides better semantics for our use case
- Built-in MPMC with reference-counted clones
- Native cancellation and closure handling via `EndOfStream`/`BrokenResourceError`
- Simpler to maintain, no custom reference counting needed
- aiologic better suited for greenlet/thread interop which we don't need

**Action:** ✅ Updated PRD task 4.3 description to reflect this decision.

---

### Decision 2: Ray vs Custom IPC for Distributed Channels

**Decision:** Use `ray.util.queue.Queue` for `distributed=True` channels instead of custom msgspec+sockets.

**Analysis of alternatives:**

| Option | Cross-Platform | Complexity | Performance | Maintenance |
|--------|---------------|------------|-------------|-------------|
| **Ray Queue** | ✅ Yes | 🟢 Low | 🟡 Medium | 🟢 Low |
| Unix sockets + msgspec | ❌ Unix only | 🟡 Medium | 🟢 High | 🟡 Medium |
| gRPC + msgspec | ✅ Yes | 🟡 Medium | 🟢 High | 🟡 Medium |
| Arrow Flight | ✅ Yes | 🔴 High | 🟡 Batch-only | 🔴 High |
| multiprocessing.Queue | ✅ Yes | 🟢 Low | 🟡 Medium | 🟢 Low |

**Rationale:**
1. **Ray is already a required dependency** - no new dependencies added
2. **Cross-platform** - Windows, Linux, macOS all supported
3. **Proven distributed queue** - `ray.util.queue.Queue` handles serialization, backpressure, and cross-process/machine communication
4. **Same code local and cluster** - matches PRD goal "switch via config"
5. **No custom IPC protocol** - eliminates maintenance burden of socket management, framing, error handling
6. **Fault tolerance built-in** - Ray handles actor failures, restarts

**Trade-offs:**
- Distributed channels require Ray runtime (acceptable since Ray is already required for distributed execution)
- Higher latency than raw sockets (acceptable for most use cases)
- Serialization via cloudpickle, not msgspec (acceptable, msgspec can still be used for payload if needed)

**Implementation approach:**
```python
# Local channel (in-process) - already implemented
distributed=False → anyio.MemoryObjectStream wrapped in LocalSender/LocalReceiver

# Distributed channel (cross-process/network) - to implement
distributed=True → ray.util.queue.Queue wrapped in RaySender/RayReceiver
```

**Action:** ✅ Updated PRD tasks 4.13-4.14 to use RayChannel wrapper instead of custom msgspec IPC.

---

### Impact on Task List

**Removed complexity:**
- ❌ No custom serialization protocol with msgspec tagged unions
- ❌ No Unix socket or named pipe management
- ❌ No cross-platform IPC abstraction layer
- ❌ No custom backpressure implementation

**Simplified tasks:**
- 4.13: `RayChannel` wrapper around `ray.util.queue.Queue` (~2h instead of ~8h)
- 4.14: `RaySender`/`RayReceiver` adapters matching local API (~1h instead of ~4h)
- 4.17: Tests for Ray channel wrapper (~1h instead of ~3h)

**Estimated savings:** ~11 hours of implementation + ongoing maintenance burden
