"""Tests for TaskHandle (cancel, is_running, exit_reason)."""

from __future__ import annotations

import asyncio

import pytest

from klaw_core.runtime import Executor, ExitReason, init
from klaw_core.runtime.errors import Cancelled


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    init(backend='local', concurrency=4)


class TestTaskHandleBasics:
    """Basic TaskHandle tests."""

    async def test_is_running_before_completion(self) -> None:
        """is_running() returns True while task is running."""

        async def slow_task() -> int:
            await asyncio.sleep(0.5)
            return 42

        async with Executor() as ex:
            handle = await ex.submit(slow_task)
            assert handle.is_running()
            handle.cancel()

    async def test_is_running_after_completion(self) -> None:
        """is_running() returns False after task completes."""

        async with Executor() as ex:
            handle = await ex.submit(lambda: 42)
            await handle
            assert not handle.is_running()

    async def test_exit_reason_success(self) -> None:
        """exit_reason is SUCCESS for successful tasks."""

        async with Executor() as ex:
            handle = await ex.submit(lambda: 42)
            await handle
            assert handle.exit_reason == ExitReason.SUCCESS

    async def test_exit_reason_error(self) -> None:
        """exit_reason is ERROR for failed tasks."""

        def fail() -> None:
            msg = 'Intentional failure'
            raise ValueError(msg)

        async with Executor() as ex:
            handle = await ex.submit(fail)
            with pytest.raises(ValueError):
                await handle
            assert handle.exit_reason == ExitReason.ERROR

    async def test_await_returns_result(self) -> None:
        """Awaiting handle returns the task result."""

        async with Executor() as ex:
            handle = await ex.submit(lambda: 'hello')
            result = await handle
            assert result == 'hello'

    async def test_await_raises_exception(self) -> None:
        """Awaiting failed handle raises the exception."""

        def fail() -> None:
            msg = 'Test error'
            raise ValueError(msg)

        async with Executor() as ex:
            handle = await ex.submit(fail)
            with pytest.raises(ValueError, match='Test error'):
                await handle


class TestTaskHandleCancel:
    """Tests for TaskHandle.cancel()."""

    async def test_cancel_running_task(self) -> None:
        """cancel() cancels a running task."""

        async def slow_task() -> int:
            await asyncio.sleep(10)
            return 42

        async with Executor() as ex:
            handle = await ex.submit(slow_task)
            await asyncio.sleep(0.01)
            handle.cancel('User requested')
            assert handle.exit_reason == ExitReason.CANCELLED

    async def test_cancel_sets_exit_reason(self) -> None:
        """cancel() sets exit_reason to CANCELLED."""

        async def slow_task() -> int:
            await asyncio.sleep(10)
            return 42

        async with Executor() as ex:
            handle = await ex.submit(slow_task)
            await asyncio.sleep(0.01)
            handle.cancel()
            assert handle.exit_reason == ExitReason.CANCELLED

    async def test_cancel_completed_task_is_noop(self) -> None:
        """cancel() on completed task does nothing."""

        async with Executor() as ex:
            handle = await ex.submit(lambda: 42)
            await handle
            original_reason = handle.exit_reason
            handle.cancel()
            assert handle.exit_reason == original_reason


class TestTaskHandleResult:
    """Tests for TaskHandle.result()."""

    async def test_result_returns_ok_on_success(self) -> None:
        """result() returns Ok for successful task."""

        async with Executor() as ex:
            handle = await ex.submit(lambda: 42)
            await handle
            r = handle.result()
            assert r.is_ok()
            assert r.unwrap() == 42

    async def test_result_returns_err_on_failure(self) -> None:
        """result() returns Err for failed task."""

        def fail() -> None:
            msg = 'Error'
            raise ValueError(msg)

        async with Executor() as ex:
            handle = await ex.submit(fail)
            with pytest.raises(ValueError):
                await handle
            r = handle.result()
            assert r.is_err()
            assert isinstance(r.error, ValueError)

    async def test_result_returns_cancelled_on_cancel(self) -> None:
        """result() returns Err(Cancelled) for cancelled task."""

        async def slow_task() -> int:
            await asyncio.sleep(10)
            return 42

        async with Executor() as ex:
            handle = await ex.submit(slow_task)
            await asyncio.sleep(0.01)
            handle.cancel('Test cancel')
            r = handle.result()
            assert r.is_err()
            err = r.error
            assert isinstance(err, Cancelled)

    async def test_result_raises_if_not_complete(self) -> None:
        """result() raises RuntimeError if task not complete."""

        async def slow_task() -> int:
            await asyncio.sleep(10)
            return 42

        async with Executor() as ex:
            handle = await ex.submit(slow_task)
            with pytest.raises(RuntimeError, match='not yet complete'):
                handle.result()
            handle.cancel()
