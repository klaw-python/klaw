"""@result decorator for catching Propagate exceptions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import wrapt

from klaw_core.propagate import Propagate
from klaw_core.result import Err, Ok

__all__ = ['result']

P = ParamSpec('P')
T = TypeVar('T')
E = TypeVar('E')


def result(
    func: Callable[P, Ok[T] | Err[E]] | Callable[P, Awaitable[Ok[T] | Err[E]]],
) -> Callable[P, Ok[T] | Err[E]] | Callable[P, Awaitable[Ok[T] | Err[E]]]:
    """Decorator that catches Propagate exceptions for .bail() support.

    When a function decorated with @result calls .bail() on an Err,
    the Propagate exception is caught and the Err is returned.
    This enables Rust-like ? operator semantics.

    Automatically detects async functions and handles them appropriately.

    Args:
        func: The function to wrap. Must return a Result type.

    Returns:
        A wrapped function that catches Propagate and returns the contained Err.

    Example:
        ```python
        @result
        def process(x: int) -> Result[int, str]:
            value = get_value(x).bail()  # Returns Err early if get_value fails
            return Ok(value * 2)

        @result
        async def async_process(x: int) -> Result[int, str]:
            value = (await fetch(x)).bail()
            return Ok(value * 2)
        ```
    """
    if asyncio.iscoroutinefunction(func):

        @wrapt.decorator
        async def async_wrapper(
            wrapped: Callable[P, Awaitable[Ok[T] | Err[E]]],
            instance: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Ok[T] | Err[E]:
            try:
                return await wrapped(*args, **kwargs)
            except Propagate as p:
                return p.value  # type: ignore[return-value]

        return async_wrapper(func)  # type: ignore[return-value]

    @wrapt.decorator
    def sync_wrapper(
        wrapped: Callable[P, Ok[T] | Err[E]],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Ok[T] | Err[E]:
        try:
            return wrapped(*args, **kwargs)
        except Propagate as p:
            return p.value  # type: ignore[return-value]

    return sync_wrapper(func)  # type: ignore[return-value]
