"""Executor: High-level task execution with backend abstraction."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from types import TracebackType
from typing import TYPE_CHECKING, Any, TypeVar

# TypeVars for generic methods (not classes using Python 3.12 generic syntax)
T = TypeVar('T')
U = TypeVar('U')

import aiologic
import anyio

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime._backends import ExitReason
from klaw_core.runtime._config import Backend, get_config
from klaw_core.runtime.errors import Cancelled, CancelledError

if TYPE_CHECKING:
    from klaw_core.runtime._backends import ExecutorBackend

__all__ = [
    'Executor',
    'TaskHandle',
]


class TaskHandle[T]:
    """Handle to a running or completed task.

    Provides methods to cancel, check status, and await the result.

    Attributes:
        _result: The cached result once completed.
        _event: Event signaling completion.
        _exit_reason: Why the task exited.
        _cancel_scope: Anyio cancel scope for this task.
    """

    __slots__ = (
        '_cancel_scope',
        '_completed',
        '_event',
        '_exception',
        '_exit_reason',
        '_result',
    )

    def __init__(self) -> None:
        self._result: T | None = None
        self._exception: BaseException | None = None
        self._event: aiologic.Event = aiologic.Event()
        self._exit_reason: ExitReason | None = None
        self._cancel_scope: anyio.CancelScope | None = None
        self._completed = False

    def _set_cancel_scope(self, scope: anyio.CancelScope) -> None:
        """Set the cancel scope for this task."""
        self._cancel_scope = scope

    def _complete(self, result: T, exit_reason: ExitReason = ExitReason.SUCCESS) -> None:
        """Mark task as complete with a result."""
        self._result = result
        self._exit_reason = exit_reason
        self._completed = True
        self._event.set()

    def _fail(self, exc: BaseException, exit_reason: ExitReason = ExitReason.ERROR) -> None:
        """Mark task as failed with an exception."""
        self._exception = exc
        self._exit_reason = exit_reason
        self._completed = True
        self._event.set()

    def cancel(self, reason: str | None = None) -> None:
        """Cancel the task.

        Args:
            reason: Optional reason for cancellation.
        """
        if self._cancel_scope is not None and not self._completed:
            self._cancel_scope.cancel()
            self._exit_reason = ExitReason.CANCELLED
            self._exception = CancelledError(reason)
            self._completed = True
            self._event.set()

    def is_running(self) -> bool:
        """Check if the task is still running.

        Returns:
            True if task is running, False if completed or cancelled.
        """
        return not self._completed

    @property
    def exit_reason(self) -> ExitReason | None:
        """Get the exit reason if task completed.

        Returns:
            ExitReason or None if still running.
        """
        return self._exit_reason

    async def wait(self) -> T:
        """Wait for task completion and return the result.

        Returns:
            The task result.

        Raises:
            Exception: If the task failed with an exception.
            CancelledError: If the task was cancelled.
        """
        # Wait for completion signal (aiologic.Event supports both async and green contexts)
        await self._event
        if self._exception is not None:
            raise self._exception
        return self._result  # type: ignore[return-value]

    def result(self) -> Result[T, Cancelled | Exception]:
        """Get the result as a Result type (non-blocking).

        Returns:
            Ok(value) if successful, Err(Cancelled|Exception) if failed.

        Raises:
            RuntimeError: If task is not yet complete.
        """
        if not self._completed:
            msg = 'Task not yet complete. Use await or wait() first.'
            raise RuntimeError(msg)
        if self._exception is not None:
            if isinstance(self._exception, CancelledError):
                return Err(self._exception.to_struct())
            if isinstance(self._exception, Exception):
                return Err(self._exception)
            return Err(Exception(str(self._exception)))
        return Ok(self._result)  # type: ignore[arg-type]

    def __await__(self) -> Any:
        """Support await syntax."""
        return self.wait().__await__()


class Executor:
    """High-level task executor with backend abstraction.

    Provides map, imap, submit, and gather operations for concurrent
    execution with full Result integration.

    Example:
        ```python
        from klaw_core.runtime import init
        from klaw_core.runtime.executor import Executor

        async def main():
            init()
            async with Executor() as ex:
                results = await ex.map(process, items)
        ```
    """

    __slots__ = ('_backend', '_backend_kwargs', '_backend_type', '_handles', '_started')

    def __init__(
        self,
        backend: Backend | str | None = None,
        **backend_kwargs: Any,
    ) -> None:
        """Create an executor.

        Args:
            backend: Backend to use. Auto-detected if None.
            **backend_kwargs: Backend-specific configuration.
        """
        self._backend: ExecutorBackend | None = None
        self._backend_kwargs = backend_kwargs
        self._handles: list[TaskHandle[Any]] = []
        self._started = False

        if backend is None:
            config = get_config()
            self._backend_type = config.backend
            merged_kwargs = {**config.backend_kwargs, **backend_kwargs}
            self._backend_kwargs = merged_kwargs
        elif isinstance(backend, str):
            self._backend_type = Backend(backend.lower())
        else:
            self._backend_type = backend

    async def __aenter__(self) -> Executor:
        """Enter the executor context."""
        self._backend = await self._create_backend()
        self._started = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the executor context, waiting for pending tasks."""
        if self._backend is not None:
            await self._backend.shutdown(wait=True)
        self._started = False

    async def _create_backend(self) -> ExecutorBackend:
        """Create the backend based on configuration."""
        if self._backend_type == Backend.RAY:
            from klaw_core.runtime._backends.ray import RayBackend

            return RayBackend(**self._backend_kwargs)

        from klaw_core.runtime._backends.local import LocalBackend

        return LocalBackend(**self._backend_kwargs)

    def _ensure_started(self) -> None:
        """Ensure executor is in context manager."""
        if not self._started or self._backend is None:
            msg = 'Executor must be used as async context manager: async with Executor() as ex:'
            raise RuntimeError(msg)

    async def submit(
        self,
        fn: Callable[..., T] | Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> TaskHandle[T]:
        """Submit a single task for execution.

        Args:
            fn: Sync or async callable.
            *args: Positional arguments.
            **kwargs: Keyword arguments (can include backend_kwargs to override).

        Returns:
            TaskHandle for the submitted task.
        """
        self._ensure_started()
        assert self._backend is not None

        backend_kwargs = kwargs.pop('backend_kwargs', {})
        _ = backend_kwargs

        handle = await self._backend.run(fn, *args, **kwargs)
        self._handles.append(handle)
        return handle

    async def map(
        self,
        fn: Callable[[T], U] | Callable[[T], Awaitable[U]],
        items: Iterable[T],
        **kwargs: Any,
    ) -> list[Result[U, Exception]]:
        """Apply fn to each item concurrently, returning all results.

        Args:
            fn: Function to apply to each item.
            items: Items to process.
            **kwargs: Additional arguments for each fn call.

        Returns:
            List of Results in same order as items.
        """
        self._ensure_started()

        handles: list[TaskHandle[U]] = []
        for item in items:
            handle = await self.submit(fn, item, **kwargs)
            handles.append(handle)

        results: list[Result[U, Exception]] = []
        for handle in handles:
            try:
                value = await handle
                results.append(Ok(value))
            except Exception as e:
                results.append(Err(e))
        return results

    async def imap(
        self,
        fn: Callable[[T], U] | Callable[[T], Awaitable[U]],
        items: Iterable[T],
        **kwargs: Any,
    ) -> AsyncIterator[Result[U, Exception]]:
        """Apply fn to each item, yielding results as they complete.

        Unlike map(), yields results in completion order, not input order.

        Args:
            fn: Function to apply.
            items: Items to process.
            **kwargs: Additional arguments.

        Yields:
            Results as tasks complete.
        """
        self._ensure_started()

        handles: list[TaskHandle[U]] = []
        for item in items:
            handle = await self.submit(fn, item, **kwargs)
            handles.append(handle)

        pending = set(handles)

        while pending:
            for handle in list(pending):
                if not handle.is_running():
                    pending.discard(handle)
                    if handle._exception is not None:
                        yield Err(handle._exception)  # type: ignore[arg-type]
                    else:
                        yield Ok(handle._result)  # type: ignore[arg-type]
                    break
            else:
                await anyio.sleep(0.001)

    async def gather(
        self,
        *handles: TaskHandle[T],
    ) -> list[Result[T, Exception]]:
        """Wait for multiple handles and return results.

        Args:
            *handles: TaskHandles to wait for.

        Returns:
            List of Results in same order as handles.
        """
        results: list[Result[T, Exception]] = []
        for handle in handles:
            try:
                value = await handle
                results.append(Ok(value))
            except Exception as e:
                results.append(Err(e))
        return results
