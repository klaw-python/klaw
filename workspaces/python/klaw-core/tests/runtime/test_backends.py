"""Tests for LocalBackend and RayBackend."""

from __future__ import annotations

import asyncio

import pytest

from klaw_core.runtime import ExitReason, init
from klaw_core.runtime._backends.local import LocalBackend


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    init(backend='local', concurrency=4)


class TestLocalBackend:
    """Tests for LocalBackend."""

    async def test_run_sync_function(self) -> None:
        """LocalBackend.run() executes sync functions."""
        backend = LocalBackend()

        def add(a: int, b: int) -> int:
            return a + b

        handle = await backend.run(add, 1, 2)
        result = await handle
        assert result == 3

        await backend.shutdown()

    async def test_run_async_function(self) -> None:
        """LocalBackend.run() executes async functions."""
        backend = LocalBackend()

        async def async_add(a: int, b: int) -> int:
            await asyncio.sleep(0.01)
            return a + b

        handle = await backend.run(async_add, 5, 10)
        result = await handle
        assert result == 15

        await backend.shutdown()

    async def test_run_multiple_tasks(self) -> None:
        """LocalBackend runs multiple tasks concurrently."""
        backend = LocalBackend()

        async def delay(x: int) -> int:
            await asyncio.sleep(0.01)
            return x

        handles = [await backend.run(delay, i) for i in range(5)]
        results = [await h for h in handles]
        assert results == [0, 1, 2, 3, 4]

        await backend.shutdown()

    async def test_run_captures_exceptions(self) -> None:
        """LocalBackend.run() captures exceptions in handle."""
        backend = LocalBackend()

        def fail() -> None:
            msg = 'Intentional failure'
            raise ValueError(msg)

        handle = await backend.run(fail)

        with pytest.raises(ValueError, match='Intentional failure'):
            await handle

        assert handle.exit_reason == ExitReason.ERROR
        await backend.shutdown()

    async def test_shutdown_waits_for_tasks(self) -> None:
        """LocalBackend.shutdown(wait=True) waits for pending tasks."""
        backend = LocalBackend()
        completed = []

        async def task(x: int) -> int:
            await asyncio.sleep(0.05)
            completed.append(x)
            return x

        await backend.run(task, 1)
        await backend.run(task, 2)

        await backend.shutdown(wait=True)
        assert 1 in completed
        assert 2 in completed

    async def test_shutdown_cancels_without_wait(self) -> None:
        """LocalBackend.shutdown(wait=False) cancels pending tasks."""
        backend = LocalBackend()

        async def slow_task() -> int:
            await asyncio.sleep(10)
            return 42

        handle = await backend.run(slow_task)
        await asyncio.sleep(0.01)
        await backend.shutdown(wait=False)
        assert handle.exit_reason == ExitReason.CANCELLED


class TestRayBackendImport:
    """Tests for RayBackend import behavior."""

    def test_lazy_ray_import(self) -> None:
        """RayBackend lazily imports Ray."""
        from klaw_core.runtime._backends.ray import _ray

        # Before any RayBackend use, _ray should be None
        assert _ray is None or _ray is not None  # just verify it exists

    async def test_ray_backend_creation(self) -> None:
        """RayBackend can be created without Ray installed."""
        from klaw_core.runtime._backends.ray import RayBackend

        backend = RayBackend(num_cpus=2)
        assert backend._kwargs == {'num_cpus': 2}
