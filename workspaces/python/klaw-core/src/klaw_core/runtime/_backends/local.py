"""LocalBackend: Local execution using anyio task groups and thread pools."""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import aiologic
import anyio
from anyio.abc import TaskGroup

from klaw_core.runtime._backends import ExitReason
from klaw_core.runtime.errors import CancelledError
from klaw_core.runtime.executor import TaskHandle

__all__ = ['LocalBackend']

T = TypeVar('T')


class LocalBackend:
    """Local execution backend using anyio.

    Creates and manages a persistent task group across multiple task submissions.
    Uses CountdownEvent to track task completion for synchronization during shutdown.

    The task group context manager is entered lazily on first run() call and
    properly exited during shutdown().

    Attributes:
        _task_group: The anyio task group for managing tasks.
        _task_group_cm: The async context manager for the task group.
        _task_count: CountdownEvent tracking active task completion.
        _max_workers: Maximum concurrent workers (for thread pool).
        _limiter: Capacity limiter for thread pool.
    """

    __slots__ = ('_limiter', '_max_workers', '_task_count', '_task_group', '_task_group_cm', '_task_handles')

    def __init__(self, max_workers: int | None = None, **_kwargs: Any) -> None:
        """Create a LocalBackend.

        Args:
            max_workers: Maximum concurrent workers for CPU-bound tasks.
            **_kwargs: Additional configuration (ignored for compatibility).
        """
        self._task_group: TaskGroup | None = None
        self._task_group_cm: Any = None
        self._task_handles: list[TaskHandle[Any]] = []
        # CountdownEvent starts in "set" state (no pending tasks)
        self._task_count: aiologic.CountdownEvent = aiologic.CountdownEvent()
        self._max_workers = max_workers
        self._limiter: anyio.CapacityLimiter | None = anyio.CapacityLimiter(max_workers) if max_workers else None

    async def _ensure_task_group(self) -> TaskGroup:
        """Ensure task group is created and entered.

        Creates the task group context manager on first call and enters it,
        keeping it alive for subsequent run() calls.
        """
        if self._task_group is not None:
            return self._task_group

        # Create the task group context manager
        self._task_group_cm = anyio.create_task_group()
        # Properly enter the async context manager
        self._task_group = await self._task_group_cm.__aenter__()
        return self._task_group

    async def run(
        self,
        fn: Callable[..., T] | Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> TaskHandle[T]:
        """Execute a function and return a TaskHandle.

        For async functions: runs directly in the task group.
        For sync functions: runs in thread pool via anyio.to_thread.run_sync().

        Args:
            fn: Sync or async callable.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            TaskHandle for the running task.
        """
        handle: TaskHandle[T] = TaskHandle()
        tg = await self._ensure_task_group()

        # Track this handle for later cancellation if needed
        self._task_handles.append(handle)

        # Increment task counter before spawning
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
                            CancelledError('Task cancelled before start'),
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
                                CancelledError('Task cancelled'),
                                ExitReason.CANCELLED,
                            )
                    except Exception as e:
                        if scope.cancel_called:
                            handle._fail(
                                CancelledError('Task cancelled'),
                                ExitReason.CANCELLED,
                            )
                        else:
                            handle._fail(e, ExitReason.ERROR)
            finally:
                # Signal task completion
                self._task_count.down()

        tg.start_soon(_execute)
        return handle

    async def shutdown(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """Shutdown the backend.

        Waits for tasks to complete if requested, cancels remaining tasks,
        then properly exits the task group context manager.

        Args:
            wait: If True, wait for pending tasks to complete.
            timeout: Maximum time to wait for shutdown.
        """
        if self._task_group is None:
            return

        try:
            if wait:
                await self._wait_for_tasks(timeout)
            else:
                # Cancel all tasks immediately
                await self._cancel_all_tasks()
                # Give tasks a moment to process cancellation
                with contextlib.suppress(Exception):
                    with anyio.fail_after(0.5):
                        await self._task_count
        finally:
            # Cancel the task group scope to interrupt remaining tasks
            with contextlib.suppress(Exception):
                self._task_group.cancel_scope.cancel()

        # Exit the task group context manager
        if self._task_group_cm is not None:
            try:
                with anyio.fail_after(1.0):
                    await self._task_group_cm.__aexit__(None, None, None)
            except TimeoutError:
                # Context exit timeout - resources may leak but we must continue
                pass
            except Exception:
                # Suppress any other exceptions during cleanup
                pass

        self._task_group = None
        self._task_group_cm = None

    async def _wait_for_tasks(self, timeout: float | None) -> None:
        """Wait for all pending tasks to complete.

        Uses countdown event to wait for all tracked tasks to finish.
        """
        if self._task_count.value == 0:
            return

        try:
            if timeout is not None:
                with anyio.fail_after(timeout):
                    await self._task_count
            else:
                await self._task_count
        except TimeoutError:
            # Timeout - cancel remaining tasks
            await self._cancel_all_tasks()
            # Give a brief window for cancellation to propagate
            with contextlib.suppress(TimeoutError):
                with anyio.fail_after(0.5):
                    await self._task_count

    async def _cancel_all_tasks(self) -> None:
        """Cancel all running tasks.

        Iterates through tracked task handles and cancels those still running.
        """
        for handle in self._task_handles:
            if handle.is_running():
                handle.cancel()
