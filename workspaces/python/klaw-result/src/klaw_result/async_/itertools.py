"""Async iteration utilities for Result types.

Provides Result-aware async iteration functions that integrate with
aioitertools for efficient async processing of Result streams.

Examples:
    >>> async def fetch_items(ids: list[int]) -> list[Result[Item, Error]]:
    ...     tasks = [fetch_item(id) for id in ids]
    ...     return await async_collect(tasks)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable

from klaw_result.types.result import Err, Ok, Result

__all__ = [
    "async_collect",
    "async_collect_concurrent",
    "async_map",
    "async_filter_ok",
    "async_partition",
]


async def async_collect[T, E](
    awaitables: Iterable[Awaitable[Result[T, E]]],
) -> Result[list[T], E]:
    """Collect awaitables of Results into a Result of list.

    Runs all awaitables concurrently using asyncio.gather, then
    collects the results. Short-circuits to return the first Err
    encountered (in order of the original iterable).

    Args:
        awaitables: An iterable of awaitables that produce Result values.

    Returns:
        Ok(list[T]) if all results are Ok, otherwise the first Err.

    Examples:
        >>> async def get_value(n: int) -> Result[int, str]:
        ...     return Ok(n * 2)
        >>>
        >>> async def example():
        ...     results = await async_collect([get_value(1), get_value(2)])
        ...     assert results == Ok([2, 4])
        >>>
        >>> asyncio.run(example())
    """
    results = await asyncio.gather(*awaitables)
    values: list[T] = []
    for result in results:
        if isinstance(result, Err):
            return result
        values.append(result.value)
    return Ok(values)


async def async_collect_concurrent[T, E](
    awaitables: Iterable[Awaitable[Result[T, E]]],
    *,
    limit: int | None = None,
) -> Result[list[T], E]:
    """Collect awaitables with optional concurrency limit.

    Like async_collect but allows limiting the number of concurrent
    operations using a semaphore.

    Args:
        awaitables: An iterable of awaitables that produce Result values.
        limit: Maximum number of concurrent operations. None means unlimited.

    Returns:
        Ok(list[T]) if all results are Ok, otherwise the first Err.

    Examples:
        >>> async def fetch(id: int) -> Result[dict, str]:
        ...     await asyncio.sleep(0.01)
        ...     return Ok({"id": id})
        >>>
        >>> async def example():
        ...     tasks = [fetch(i) for i in range(10)]
        ...     result = await async_collect_concurrent(tasks, limit=3)
        ...     assert result.is_ok()
    """
    if limit is None:
        return await async_collect(awaitables)

    semaphore = asyncio.Semaphore(limit)
    awaitable_list = list(awaitables)

    async def limited(aw: Awaitable[Result[T, E]]) -> Result[T, E]:
        async with semaphore:
            return await aw

    results = await asyncio.gather(*[limited(aw) for aw in awaitable_list])
    values: list[T] = []
    for result in results:
        if isinstance(result, Err):
            return result
        values.append(result.value)
    return Ok(values)


async def async_map[T, U, E](
    func: Callable[[T], Awaitable[Result[U, E]]],
    items: Iterable[T],
    *,
    limit: int | None = None,
) -> Result[list[U], E]:
    """Apply an async function to each item and collect results.

    Args:
        func: Async function that takes T and returns Result[U, E].
        items: Items to process.
        limit: Maximum number of concurrent operations.

    Returns:
        Ok(list[U]) if all results are Ok, otherwise the first Err.

    Examples:
        >>> async def process(n: int) -> Result[int, str]:
        ...     return Ok(n * 2)
        >>>
        >>> async def example():
        ...     result = await async_map(process, [1, 2, 3])
        ...     assert result == Ok([2, 4, 6])
    """
    awaitables = [func(item) for item in items]
    return await async_collect_concurrent(awaitables, limit=limit)


async def async_filter_ok[T, E](
    awaitables: Iterable[Awaitable[Result[T, E]]],
) -> list[T]:
    """Collect only the Ok values, discarding Errs.

    Runs all awaitables concurrently and returns only the successful values.
    Errors are silently ignored.

    Args:
        awaitables: An iterable of awaitables that produce Result values.

    Returns:
        List of Ok values.

    Examples:
        >>> async def maybe_value(n: int) -> Result[int, str]:
        ...     return Ok(n) if n > 0 else Err("negative")
        >>>
        >>> async def example():
        ...     tasks = [maybe_value(n) for n in [-1, 2, -3, 4]]
        ...     values = await async_filter_ok(tasks)
        ...     assert values == [2, 4]
    """
    results = await asyncio.gather(*awaitables)
    return [r.value for r in results if isinstance(r, Ok)]


async def async_partition[T, E](
    awaitables: Iterable[Awaitable[Result[T, E]]],
) -> tuple[list[T], list[E]]:
    """Partition results into Ok values and Err values.

    Runs all awaitables concurrently and separates the results.

    Args:
        awaitables: An iterable of awaitables that produce Result values.

    Returns:
        Tuple of (ok_values, err_values).

    Examples:
        >>> async def check(n: int) -> Result[int, str]:
        ...     return Ok(n) if n > 0 else Err(f"{n} is negative")
        >>>
        >>> async def example():
        ...     tasks = [check(n) for n in [-1, 2, -3, 4]]
        ...     oks, errs = await async_partition(tasks)
        ...     assert oks == [2, 4]
        ...     assert errs == ["-1 is negative", "-3 is negative"]
    """
    results = await asyncio.gather(*awaitables)
    oks: list[T] = []
    errs: list[E] = []
    for r in results:
        if isinstance(r, Ok):
            oks.append(r.value)
        else:
            errs.append(r.error)
    return oks, errs


async def async_first_ok[T, E](
    awaitables: Iterable[Awaitable[Result[T, E]]],
) -> Result[T, list[E]]:
    """Return the first Ok result, or all errors if all fail.

    Runs awaitables sequentially and returns as soon as one succeeds.
    If all fail, returns Err with a list of all errors.

    Args:
        awaitables: An iterable of awaitables that produce Result values.

    Returns:
        First Ok result, or Err with all errors.

    Examples:
        >>> async def try_source(n: int) -> Result[str, str]:
        ...     return Ok(f"source{n}") if n == 2 else Err(f"failed{n}")
        >>>
        >>> async def example():
        ...     tasks = [try_source(n) for n in [1, 2, 3]]
        ...     result = await async_first_ok(tasks)
        ...     assert result == Ok("source2")
    """
    errors: list[E] = []
    for aw in awaitables:
        result = await aw
        if isinstance(result, Ok):
            return result
        errors.append(result.error)
    return Err(errors)


async def async_iter_ok[T, E](
    async_iterable: AsyncIterable[Result[T, E]],
) -> AsyncIterable[T]:
    """Yield only Ok values from an async iterable.

    Args:
        async_iterable: An async iterable of Result values.

    Yields:
        Values from Ok results.

    Examples:
        >>> async def generate():
        ...     yield Ok(1)
        ...     yield Err("skip")
        ...     yield Ok(2)
        >>>
        >>> async def example():
        ...     values = [v async for v in async_iter_ok(generate())]
        ...     assert values == [1, 2]
    """
    async for result in async_iterable:
        if isinstance(result, Ok):
            yield result.value
