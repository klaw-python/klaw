"""@safe and @safe_async decorators for catching exceptions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, overload

import wrapt

from klaw_core.result import Err, Ok

__all__ = ['safe', 'safe_async']

P = ParamSpec('P')
T = TypeVar('T')
E = TypeVar('E', bound=BaseException)


@overload
def safe[**P, T](
    func: Callable[P, T],
) -> Callable[P, Ok[T] | Err[Exception]]: ...


@overload
def safe[E: BaseException](
    *,
    exceptions: tuple[type[E], ...],
) -> Callable[[Callable[P, T]], Callable[P, Ok[T] | Err[E]]]: ...


@overload
def safe[E: BaseException](
    func: None = None,
    *,
    exceptions: tuple[type[E], ...] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, Ok[T] | Err[E]]]: ...


def safe[**P, T](
    func: Callable[P, T] | None = None,
    *,
    exceptions: tuple[type[Any], ...] | None = None,
) -> Any:
    """Decorator that catches exceptions and returns Err.

    Wraps a function so that it returns Ok(value) on success and
    Err(exception) if an exception is raised.

    Can be used with or without arguments:
        @safe
        def risky(): ...

        @safe(exceptions=(ValueError, TypeError))
        def specific(): ...

    Args:
        func: The function to wrap (when used without parentheses).
        exceptions: Tuple of exception types to catch. Defaults to (Exception,).

    Returns:
        A wrapped function that returns Result[T, E] instead of T.

    Example:
        ```python
        @safe
        def divide(a: int, b: int) -> float:
            return a / b
        divide(10, 2)
        # Ok(value=5.0)
        divide(10, 0)
        # Err(error=ZeroDivisionError('division by zero'))
        ```
    """
    catch = exceptions if exceptions is not None else (Exception,)

    @wrapt.decorator
    def wrapper(
        wrapped: Callable[P, T],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Ok[T] | Err[Any]:
        try:
            result = wrapped(*args, **kwargs)
            return Ok(result)
        except catch as e:
            return Err(e)

    if func is not None:
        return wrapper(func)
    return wrapper


@overload
def safe_async[**P, T](
    func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[Ok[T] | Err[Exception]]]: ...


@overload
def safe_async[E: BaseException](
    *,
    exceptions: tuple[type[E], ...],
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Ok[T] | Err[E]]]]: ...


@overload
def safe_async[E: BaseException](
    func: None = None,
    *,
    exceptions: tuple[type[E], ...] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Ok[T] | Err[E]]]]: ...


def safe_async[**P, T](
    func: Callable[P, Awaitable[T]] | None = None,
    *,
    exceptions: tuple[type[Any], ...] | None = None,
) -> Any:
    """Async decorator that catches exceptions and returns Err.

    Wraps an async function so that it returns Ok(value) on success and
    Err(exception) if an exception is raised.

    Can be used with or without arguments:
        @safe_async
        async def risky(): ...

        @safe_async(exceptions=(ValueError, TypeError))
        async def specific(): ...

    Args:
        func: The async function to wrap (when used without parentheses).
        exceptions: Tuple of exception types to catch. Defaults to (Exception,).

    Returns:
        A wrapped async function that returns Result[T, E] instead of T.

    Example:
        ```python
        @safe_async
        async def fetch(url: str) -> str:
            # may raise
            return await http_get(url)
        ```
    """
    catch = exceptions if exceptions is not None else (Exception,)

    @wrapt.decorator
    async def wrapper(
        wrapped: Callable[P, Awaitable[T]],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Ok[T] | Err[Any]:
        try:
            result = await wrapped(*args, **kwargs)
            return Ok(result)
        except catch as e:
            return Err(e)

    if func is not None:
        return wrapper(func)
    return wrapper
