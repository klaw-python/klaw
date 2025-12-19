"""@pipe and @pipe_async decorators for wrapping return values in Ok."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import wrapt

from klaw_core.result import Ok

__all__ = ['pipe', 'pipe_async']

P = ParamSpec('P')
T = TypeVar('T')


def pipe[**P, T](func: Callable[P, T]) -> Callable[P, Ok[T]]:
    """Decorator that wraps the return value in Ok.

    Useful for functions that never fail, to make them compatible
    with Result-based pipelines.

    Args:
        func: The function to wrap.

    Returns:
        A wrapped function that returns Ok[T] instead of T.

    Example:
        ```python
        @pipe
        def add(a: int, b: int) -> int:
            return a + b
        add(2, 3)
        # Ok(value=5)
        ```
    """

    @wrapt.decorator
    def wrapper(
        wrapped: Callable[P, T],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Ok[T]:
        return Ok(wrapped(*args, **kwargs))

    return wrapper(func)  # type: ignore[return-value]


def pipe_async[**P, T](
    func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[Ok[T]]]:
    """Async decorator that wraps the return value in Ok.

    Useful for async functions that never fail, to make them compatible
    with Result-based pipelines.

    Args:
        func: The async function to wrap.

    Returns:
        A wrapped async function that returns Ok[T] instead of T.

    Example:
        ```python
        @pipe_async
        async def fetch_data() -> str:
            return "data"
        await fetch_data()
        # Ok(value='data')
        ```
    """

    @wrapt.decorator
    async def wrapper(
        wrapped: Callable[P, Awaitable[T]],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Ok[T]:
        result = await wrapped(*args, **kwargs)
        return Ok(result)

    return wrapper(func)  # type: ignore[return-value]
