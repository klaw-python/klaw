"""Async iteration utilities for Result types.

Provides Result-aware async iteration functions with proper concurrency
control using aiologic for thread-safe operations.

Example:
    ```python
    async def fetch_items(ids: list[int]) -> list[Result[Item, Error]]:
        tasks = [fetch_item(id) for id in ids]
        return await async_collect(tasks)
    ```
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable, Iterable

import aiologic
import anyio

from klaw_core.result import Err, Ok, Result

__all__ = [
    'async_collect',
    'async_collect_concurrent',
    'async_filter_ok',
    'async_first_ok',
    'async_iter_ok',
    'async_map',
    'async_partition',
    'async_race_ok',
]


async def async_collect[T, E](
    awaitables: Iterable[Awaitable[Result[T, E]]],
) -> Result[list[T], E]:
    """Collect awaitables of Results into a Result of list.

    Runs all awaitables concurrently and waits for all to complete.
    Then returns Ok(list[T]) if all succeeded, or the first Err
    encountered (by original order).

    Note:
        This does NOT short-circuit/cancel on first error. All awaitables
        run to completion before checking results. Use async_race_ok if
        you need early termination on success.

    Args:
        awaitables: An iterable of awaitables that produce Result values.

    Returns:
        Ok(list[T]) if all results are Ok, otherwise the first Err (by order).

    Example:
        ```python
        async def get_value(n: int) -> Result[int, str]:
            return Ok(n * 2)

        async def example():
            results = await async_collect([get_value(1), get_value(2)])
            assert results == Ok([2, 4])
        ```
    """
    awaitable_list = list(awaitables)
    results: list[Result[T, E] | None] = [None] * len(awaitable_list)

    async with anyio.create_task_group() as tg:

        async def run_one(i: int, aw: Awaitable[Result[T, E]]) -> None:
            results[i] = await aw

        for i, aw in enumerate(awaitable_list):
            tg.start_soon(run_one, i, aw)

    values: list[T] = []
    for result in results:
        assert result is not None
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
    operations using aiologic.CapacityLimiter for thread-safe limiting.

    Note:
        The awaitables iterable is eagerly materialized into a list before
        processing. If the iterable has side effects on iteration, those
        effects happen immediately.

    Args:
        awaitables: An iterable of awaitables that produce Result values.
        limit: Maximum number of concurrent operations. None means unlimited.

    Returns:
        Ok(list[T]) if all results are Ok, otherwise the first Err (by order).

    Example:
        ```python
        async def fetch(id: int) -> Result[dict, str]:
            await asyncio.sleep(0.01)
            return Ok({"id": id})

        async def example():
            tasks = [fetch(i) for i in range(10)]
            result = await async_collect_concurrent(tasks, limit=3)
            assert result.is_ok()
        ```
    """
    if limit is None:
        return await async_collect(awaitables)

    limiter = aiologic.CapacityLimiter(limit)
    awaitable_list = list(awaitables)
    results: list[Result[T, E] | None] = [None] * len(awaitable_list)

    async with anyio.create_task_group() as tg:

        async def run_one(i: int, aw: Awaitable[Result[T, E]]) -> None:
            async with limiter:
                results[i] = await aw

        for i, aw in enumerate(awaitable_list):
            tg.start_soon(run_one, i, aw)

    values: list[T] = []
    for result in results:
        assert result is not None
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

    Example:
        ```python
        async def process(n: int) -> Result[int, str]:
            return Ok(n * 2)

        async def example():
            result = await async_map(process, [1, 2, 3])
            assert result == Ok([2, 4, 6])
        ```
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

    Example:
        ```python
        async def maybe_value(n: int) -> Result[int, str]:
            return Ok(n) if n > 0 else Err("negative")

        async def example():
            tasks = [maybe_value(n) for n in [-1, 2, -3, 4]]
            values = await async_filter_ok(tasks)
            assert values == [2, 4]
        ```
    """
    awaitable_list = list(awaitables)
    results: list[Result[T, E] | None] = [None] * len(awaitable_list)

    async with anyio.create_task_group() as tg:

        async def run_one(i: int, aw: Awaitable[Result[T, E]]) -> None:
            results[i] = await aw

        for i, aw in enumerate(awaitable_list):
            tg.start_soon(run_one, i, aw)

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

    Example:
        ```python
        async def check(n: int) -> Result[int, str]:
            return Ok(n) if n > 0 else Err(f"{n} is negative")

        async def example():
            tasks = [check(n) for n in [-1, 2, -3, 4]]
            oks, errs = await async_partition(tasks)
            assert oks == [2, 4]
            assert errs == ["-1 is negative", "-3 is negative"]
        ```
    """
    awaitable_list = list(awaitables)
    results: list[Result[T, E] | None] = [None] * len(awaitable_list)

    async with anyio.create_task_group() as tg:

        async def run_one(i: int, aw: Awaitable[Result[T, E]]) -> None:
            results[i] = await aw

        for i, aw in enumerate(awaitable_list):
            tg.start_soon(run_one, i, aw)

    oks: list[T] = []
    errs: list[E] = []
    for r in results:
        assert r is not None
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

    Note: Any remaining awaitables after finding an Ok are properly
    cancelled/closed to avoid "coroutine was never awaited" warnings.

    Args:
        awaitables: An iterable of awaitables that produce Result values.

    Returns:
        First Ok result, or Err with all errors.

    Example:
        ```python
        async def try_source(n: int) -> Result[str, str]:
            return Ok(f"source{n}") if n == 2 else Err(f"failed{n}")

        async def example():
            tasks = [try_source(n) for n in [1, 2, 3]]
            result = await async_first_ok(tasks)
            assert result == Ok("source2")
        ```
    """
    awaitable_list = list(awaitables)
    errors: list[E] = []

    for i, aw in enumerate(awaitable_list):
        result = await aw
        if isinstance(result, Ok):
            # Clean up remaining unawaited coroutines
            for remaining in awaitable_list[i + 1 :]:
                if hasattr(remaining, 'close'):
                    remaining.close()  # type: ignore[union-attr]
            return result
        errors.append(result.error)
    return Err(errors)


async def async_race_ok[T, E](
    awaitables: Iterable[Awaitable[Result[T, E]]],
) -> Result[T, list[E]]:
    """Race awaitables concurrently, return first Ok or all errors.

    Unlike async_first_ok which runs sequentially, this runs all
    awaitables concurrently and returns as soon as any succeeds.
    Remaining tasks are cancelled.

    Uses aiologic.Event for thread-safe signaling and anyio for
    backend-agnostic task orchestration.

    Args:
        awaitables: An iterable of awaitables that produce Result values.

    Returns:
        First Ok result (by completion time), or Err with all errors.

    Example:
        ```python
        async def slow_source(n: int, delay: float) -> Result[str, str]:
            await anyio.sleep(delay)
            return Ok(f"source{n}") if n == 2 else Err(f"fail{n}")

        async def example():
            # Source 2 succeeds fastest
            tasks = [slow_source(1, 0.1), slow_source(2, 0.01), slow_source(3, 0.1)]
            result = await async_race_ok(tasks)
            assert result == Ok("source2")
        ```
    """
    awaitable_list = list(awaitables)
    if not awaitable_list:
        return Err([])

    # Use aiologic primitives for thread-safe, free-threaded compatible operation
    success_event = aiologic.Event()
    state_lock = aiologic.Lock()
    first_ok: Result[T, list[E]] | None = None
    errors: list[E] = []
    error_count = 0
    total = len(awaitable_list)

    # Backend-agnostic cancellation exception
    cancelled_exc = anyio.get_cancelled_exc_class()

    async def run_one(aw: Awaitable[Result[T, E]]) -> None:
        nonlocal first_ok, error_count
        try:
            result = await aw
            async with state_lock:
                if isinstance(result, Ok):
                    if first_ok is None:
                        first_ok = result  # type: ignore[assignment]
                        success_event.set()
                else:
                    errors.append(result.error)
                    error_count += 1
                    if error_count == total:
                        success_event.set()
        except cancelled_exc:
            pass

    async with anyio.create_task_group() as tg:

        async def monitor() -> None:
            await success_event
            tg.cancel_scope.cancel()

        for aw in awaitable_list:
            tg.start_soon(run_one, aw)
        tg.start_soon(monitor)

    if first_ok is not None:
        return first_ok
    return Err(errors)


async def async_iter_ok[T, E](
    async_iterable: AsyncIterable[Result[T, E]],
) -> AsyncIterable[T]:
    """Yield only Ok values from an async iterable.

    Args:
        async_iterable: An async iterable of Result values.

    Yields:
        Values from Ok results.

    Example:
        ```python
        async def generate():
            yield Ok(1)
            yield Err("skip")
            yield Ok(2)

        async def example():
            values = [v async for v in async_iter_ok(generate())]
            assert values == [1, 2]
        ```
    """
    async for result in async_iterable:
        if isinstance(result, Ok):
            yield result.value
