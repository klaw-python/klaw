"""async-lru integration for cached async Result functions.

Provides decorators that combine async-lru caching with safe
exception handling for Result-returning async functions.

Example:
    ```python
    @async_lru_safe(maxsize=128)
    async def fetch_user(id: int) -> dict:
        response = await http_client.get(f"/users/{id}")
        return response.json()

    # First call fetches, second call uses cache
    result1 = await fetch_user(1)  # Result[dict, Exception]
    result2 = await fetch_user(1)  # Cached Result
    ```
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar, overload

from async_lru import alru_cache

from klaw_core.result import Err, Ok, Result

__all__ = ['async_lru_safe']

P = ParamSpec('P')
T = TypeVar('T')


@overload
def async_lru_safe(
    fn: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[Result[T, Exception]]]: ...


@overload
def async_lru_safe(
    *,
    maxsize: int | None = 128,
    ttl: float | None = None,
) -> Callable[
    [Callable[P, Awaitable[T]]],
    Callable[P, Awaitable[Result[T, Exception]]],
]: ...


def async_lru_safe(
    fn: Callable[P, Awaitable[T]] | None = None,
    *,
    maxsize: int | None = 128,
    ttl: float | None = None,
) -> (
    Callable[P, Awaitable[Result[T, Exception]]]
    | Callable[
        [Callable[P, Awaitable[T]]],
        Callable[P, Awaitable[Result[T, Exception]]],
    ]
):
    """Decorator combining async-lru caching with safe exception handling.

    Wraps an async function to:
    1. Catch any exceptions and return Err(exception)
    2. Return successful results as Ok(value)
    3. Cache results using async-lru

    Can be used with or without arguments:
        @async_lru_safe
        async def fetch(id: int) -> Data: ...

        @async_lru_safe(maxsize=256, ttl=60.0)
        async def fetch(id: int) -> Data: ...

    Args:
        fn: The async function to wrap (when used without parens).
        maxsize: Maximum cache size. None means unlimited.
        ttl: Time-to-live in seconds. None means no expiration.

    Returns:
        Decorated function that returns Result[T, Exception].

    Example:
        ```python
        @async_lru_safe
        async def get_data(key: str) -> dict:
            return {"key": key}

        async def example():
            result = await get_data("test")
            assert result == Ok({"key": "test"})

        @async_lru_safe(maxsize=100, ttl=300.0)
        async def cached_fetch(url: str) -> bytes:
            async with aiohttp.get(url) as resp:
                return await resp.read()
        ```
    """

    def decorator(
        func: Callable[P, Awaitable[T]],
    ) -> Callable[P, Awaitable[Result[T, Exception]]]:
        @alru_cache(maxsize=maxsize, ttl=ttl)
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Result[T, Exception]:
            try:
                value = await func(*args, **kwargs)
                return Ok(value)
            except Exception as e:
                return Err(e)

        return wrapper  # type: ignore[return-value]

    if fn is not None:
        return decorator(fn)

    return decorator
