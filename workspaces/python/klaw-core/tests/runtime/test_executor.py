"""Tests for Executor with LocalBackend (map, imap, submit, gather)."""

from __future__ import annotations

import asyncio

import pytest

from klaw_core import Err, Ok
from klaw_core.runtime import Executor, ExitReason, TaskHandle, init


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    init(backend='local', concurrency=4)


class TestExecutorSubmit:
    """Tests for Executor.submit()."""

    async def test_submit_sync_function(self) -> None:
        """submit() executes sync functions correctly."""

        def add(a: int, b: int) -> int:
            return a + b

        async with Executor() as ex:
            handle = await ex.submit(add, 1, 2)
            result = await handle
            assert result == 3

    async def test_submit_async_function(self) -> None:
        """submit() executes async functions correctly."""

        async def async_add(a: int, b: int) -> int:
            await asyncio.sleep(0.01)
            return a + b

        async with Executor() as ex:
            handle = await ex.submit(async_add, 5, 10)
            result = await handle
            assert result == 15

    async def test_submit_with_kwargs(self) -> None:
        """submit() passes kwargs to function."""

        def greet(name: str, greeting: str = 'Hello') -> str:
            return f'{greeting}, {name}!'

        async with Executor() as ex:
            handle = await ex.submit(greet, 'World', greeting='Hi')
            result = await handle
            assert result == 'Hi, World!'

    async def test_submit_returns_task_handle(self) -> None:
        """submit() returns a TaskHandle."""

        async with Executor() as ex:
            handle = await ex.submit(lambda: 42)
            assert isinstance(handle, TaskHandle)


class TestExecutorMap:
    """Tests for Executor.map()."""

    async def test_map_sync_function(self) -> None:
        """map() applies sync function to all items."""

        def double(x: int) -> int:
            return x * 2

        async with Executor() as ex:
            results = await ex.map(double, [1, 2, 3, 4, 5])
            assert len(results) == 5
            assert all(r.is_ok() for r in results)
            values = [r.unwrap() for r in results]
            assert values == [2, 4, 6, 8, 10]

    async def test_map_async_function(self) -> None:
        """map() applies async function to all items."""

        async def async_double(x: int) -> int:
            await asyncio.sleep(0.001)
            return x * 2

        async with Executor() as ex:
            results = await ex.map(async_double, [1, 2, 3])
            values = [r.unwrap() for r in results]
            assert values == [2, 4, 6]

    async def test_map_preserves_order(self) -> None:
        """map() returns results in input order."""

        async def delay_by_value(x: int) -> int:
            await asyncio.sleep(0.01 * (5 - x))
            return x

        async with Executor() as ex:
            results = await ex.map(delay_by_value, [1, 2, 3, 4, 5])
            values = [r.unwrap() for r in results]
            assert values == [1, 2, 3, 4, 5]

    async def test_map_handles_errors(self) -> None:
        """map() captures exceptions as Err results."""

        def maybe_fail(x: int) -> int:
            if x == 3:
                msg = 'Failed on 3'
                raise ValueError(msg)
            return x

        async with Executor() as ex:
            results = await ex.map(maybe_fail, [1, 2, 3, 4, 5])
            assert results[0] == Ok(1)
            assert results[1] == Ok(2)
            assert results[2].is_err()
            assert results[3] == Ok(4)
            assert results[4] == Ok(5)

    async def test_map_empty_iterable(self) -> None:
        """map() with empty iterable returns empty list."""

        async with Executor() as ex:
            results = await ex.map(lambda x: x, [])
            assert results == []


class TestExecutorImap:
    """Tests for Executor.imap()."""

    async def test_imap_yields_results(self) -> None:
        """imap() yields results as async iterator."""

        def double(x: int) -> int:
            return x * 2

        async with Executor() as ex:
            results = []
            async for result in ex.imap(double, [1, 2, 3]):
                results.append(result)
            assert len(results) == 3
            values = sorted([r.unwrap() for r in results])
            assert values == [2, 4, 6]

    async def test_imap_handles_errors(self) -> None:
        """imap() captures exceptions as Err results."""

        def maybe_fail(x: int) -> int:
            if x == 2:
                msg = 'Failed'
                raise ValueError(msg)
            return x

        async with Executor() as ex:
            results = []
            async for result in ex.imap(maybe_fail, [1, 2, 3]):
                results.append(result)
            ok_count = sum(1 for r in results if r.is_ok())
            err_count = sum(1 for r in results if r.is_err())
            assert ok_count == 2
            assert err_count == 1


class TestExecutorGather:
    """Tests for Executor.gather()."""

    async def test_gather_multiple_handles(self) -> None:
        """gather() waits for multiple handles."""

        async with Executor() as ex:
            h1 = await ex.submit(lambda: 1)
            h2 = await ex.submit(lambda: 2)
            h3 = await ex.submit(lambda: 3)
            results = await ex.gather(h1, h2, h3)
            assert len(results) == 3
            values = [r.unwrap() for r in results]
            assert values == [1, 2, 3]

    async def test_gather_preserves_order(self) -> None:
        """gather() returns results in handle order."""

        async def delay(x: int) -> int:
            await asyncio.sleep(0.01 * (4 - x))
            return x

        async with Executor() as ex:
            h1 = await ex.submit(delay, 1)
            h2 = await ex.submit(delay, 2)
            h3 = await ex.submit(delay, 3)
            results = await ex.gather(h1, h2, h3)
            values = [r.unwrap() for r in results]
            assert values == [1, 2, 3]

    async def test_gather_empty(self) -> None:
        """gather() with no handles returns empty list."""

        async with Executor() as ex:
            results = await ex.gather()
            assert results == []


class TestExecutorContextManager:
    """Tests for Executor as async context manager."""

    async def test_requires_context_manager(self) -> None:
        """Executor methods require context manager."""
        ex = Executor()
        with pytest.raises(RuntimeError, match='async context manager'):
            await ex.submit(lambda: 42)

    async def test_context_manager_cleanup(self) -> None:
        """Executor cleans up on context exit."""

        async with Executor() as ex:
            handle = await ex.submit(lambda: 42)
            await handle

        assert not ex._started
