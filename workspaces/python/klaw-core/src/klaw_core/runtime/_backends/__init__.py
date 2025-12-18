"""Backend protocol and implementations for the runtime module."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from klaw_core.runtime.executor import TaskHandle

__all__ = [
    'ExecutorBackend',
    'ExitReason',
]


class ExitReason(Enum):
    """Reason a task exited."""

    SUCCESS = 'success'
    CANCELLED = 'cancelled'
    ERROR = 'error'


@runtime_checkable
class ExecutorBackend(Protocol):
    """Protocol for execution backends.

    Backends are responsible for running callables (sync or async)
    and returning TaskHandle instances for management.

    Implementations:
        - LocalBackend: Uses anyio task groups + thread pool for CPU work
        - RayBackend: Delegates to Ray remote actors/tasks
    """

    async def run[T](
        self,
        fn: Callable[..., T] | Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> TaskHandle[T]:
        """Execute a function and return a TaskHandle.

        Args:
            fn: Sync or async callable to execute.
            *args: Positional arguments for fn.
            **kwargs: Keyword arguments for fn.

        Returns:
            TaskHandle for the running task.
        """
        ...

    async def shutdown(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """Shutdown the backend gracefully.

        Args:
            wait: If True, wait for pending tasks to complete.
            timeout: Maximum time to wait for shutdown.
        """
        ...
