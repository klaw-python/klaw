"""@do and @do_async decorators for generator-based do-notation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Generator
from typing import Any, ParamSpec, TypeVar

import wrapt

from klaw_core.option import NothingType, Some
from klaw_core.result import Err, Ok

__all__ = ['do', 'do_async']

P = ParamSpec('P')
T = TypeVar('T')
E = TypeVar('E')


def do(
    func: Callable[P, Generator[Ok[Any] | Err[E] | Some[Any] | NothingType, Any, T]],
) -> Callable[P, Ok[T] | Err[E]]:
    """Decorator for generator-based do-notation with Result.

    Enables Haskell-style do-notation using generators. Yield Result values
    to extract their Ok values; if an Err is yielded, it short-circuits and
    returns that Err immediately.

    The generator should yield Result values and return the final value
    to be wrapped in Ok.

    Args:
        func: A generator function that yields Results and returns T.

    Returns:
        A function that returns Result[T, E].

    Example:
        ```python
        @do
        def compute() -> Generator[Result[int, str], int, int]:
            x = yield get_x()  # Returns Err early if get_x() is Err
            y = yield get_y()  # Returns Err early if get_y() is Err
            return x + y
        compute()
        # Ok(value=...)  # or Err(...) if any step failed
        ```
    """

    @wrapt.decorator
    def wrapper(
        wrapped: Callable[
            P, Generator[Ok[Any] | Err[E] | Some[Any] | NothingType, Any, T]
        ],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Ok[T] | Err[E]:
        gen = wrapped(*args, **kwargs)
        try:
            result = next(gen)
            while True:
                if isinstance(result, Err):
                    return result
                if isinstance(result, NothingType):
                    return Err(None)  # type: ignore[arg-type]
                if isinstance(result, Ok) or isinstance(result, Some):
                    value = result.value
                else:
                    value = result
                result = gen.send(value)
        except StopIteration as e:
            return Ok(e.value)

    return wrapper(func)  # type: ignore[return-value]


def do_async(
    func: Callable[P, AsyncGenerator[Ok[Any] | Err[E] | Some[Any] | NothingType, Any]],
) -> Callable[P, Any]:
    """Async decorator for generator-based do-notation with Result.

    Enables Haskell-style do-notation using async generators. Yield Result
    values to extract their Ok values; if an Err is yielded, it short-circuits
    and returns that Err immediately.

    Note: Async generators cannot have a return value in Python, so the last
    yielded Ok value is used as the final result.

    Args:
        func: An async generator function that yields Results.

    Returns:
        An async function that returns Result[T, E].

    Example:
        ```python
        @do_async
        async def compute():
            x = yield await fetch_x()  # Returns Err early if fetch_x() is Err
            y = yield await fetch_y()  # Returns Err early if fetch_y() is Err
            yield Ok(x + y)  # Final result
        ```
    """

    @wrapt.decorator
    async def wrapper(
        wrapped: Callable[
            P, AsyncGenerator[Ok[Any] | Err[E] | Some[Any] | NothingType, Any]
        ],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Ok[T] | Err[E]:
        gen = wrapped(*args, **kwargs)
        last_ok: Ok[Any] | None = None
        try:
            result = await gen.asend(None)
            while True:
                if isinstance(result, Err):
                    return result
                if isinstance(result, NothingType):
                    return Err(None)  # type: ignore[arg-type]
                if isinstance(result, Ok):
                    last_ok = result
                    value = result.value
                elif isinstance(result, Some):
                    value = result.value
                else:
                    value = result
                result = await gen.asend(value)
        except StopAsyncIteration:
            if last_ok is not None:
                return last_ok
            return Ok(None)  # type: ignore[arg-type]

    return wrapper(func)
