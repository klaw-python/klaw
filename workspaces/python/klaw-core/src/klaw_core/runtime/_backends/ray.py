"""RayBackend: Distributed execution using Ray."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

# Suppress Ray's FutureWarning about accelerator env var override
os.environ.setdefault('RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO', '0')

from klaw_core.runtime._backends import ExitReason
from klaw_core.runtime.errors import BackendException, CancelledError
from klaw_core.runtime.executor import TaskHandle

__all__ = ['RayBackend']

T = TypeVar('T')

_ray: Any = None

DEFAULT_RUNTIME_ENV_EXCLUDES = [
    # Version control & IDE
    '.git',
    '.vscode',
    '.idea',
    '.kilocode',
    # Python environments & caches
    '.venv',
    'venv',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.hypothesis',
    '__pycache__',
    '*.pyc',
    '*.pyo',
    '.tox',
    '.nox',
    '.eggs',
    '*.egg-info',
    '.coverage',
    'htmlcov',
    # Rust artifacts (monorepo with Rust workspaces)
    'target',
    'workspaces/rust',
    '*.rs',
    'Cargo.lock',
    'Cargo.toml',
    # Build artifacts
    'dist',
    'build',
    # Documentation
    'site',
    'docs',
    'docs-build',
    # Tests (not needed in Ray workers)
    'tests',
    '**/tests',
    '*_test.py',
    'test_*.py',
    'conftest.py',
    # Benchmarks & references
    '.benchmarks',
    '.cache',
    '.reference',
    # Other large/unnecessary files
    '*.dbc',
    'node_modules',
    '.DS_Store',
    '.env',
    '*.log',
    '*.lock',
    'uv.lock',
    # Tasks/PRD files
    'tasks',
]


def _get_ray() -> Any:
    """Lazy import of Ray."""
    global _ray  # noqa: PLW0603
    if _ray is None:
        try:
            import ray as ray_module

            _ray = ray_module
        except ImportError as e:
            msg = "Ray is not installed. Install with: pip install 'ray[default]'"
            raise BackendException(msg, 'ray') from e
    return _ray


class RayBackend:
    """Ray execution backend for distributed computing.

    Uses ray.remote() for task execution with async ray.get() for results.

    Attributes:
        _handles: List of active task handles.
        _object_refs: Mapping of handles to Ray ObjectRefs.
        _kwargs: Backend-specific kwargs passed to Ray.
    """

    __slots__ = ('_background_tasks', '_handles', '_initialized', '_kwargs', '_object_refs')

    def __init__(self, **kwargs: Any) -> None:
        """Create a RayBackend.

        Args:
            **kwargs: Ray-specific configuration (num_cpus, num_gpus, etc.).
                     Passed through to ray.init() or ray.remote().
        """
        self._handles: list[TaskHandle[Any]] = []
        self._object_refs: dict[TaskHandle[Any], Any] = {}
        self._kwargs = kwargs
        self._initialized = False
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _ensure_ray_init(self) -> None:
        """Ensure Ray is initialized."""
        ray = _get_ray()
        if not ray.is_initialized():
            init_kwargs = {
                k: v
                for k, v in self._kwargs.items()
                if k in {'address', 'namespace', 'runtime_env', 'num_cpus', 'num_gpus'}
            }
            # Merge default excludes into runtime_env
            runtime_env = init_kwargs.get('runtime_env', {})
            if isinstance(runtime_env, dict):
                existing_excludes = runtime_env.get('excludes', [])
                merged_excludes = list(set(DEFAULT_RUNTIME_ENV_EXCLUDES + existing_excludes))
                runtime_env = {**runtime_env, 'excludes': merged_excludes}
                init_kwargs['runtime_env'] = runtime_env
            ray.init(**init_kwargs, ignore_reinit_error=True)
        self._initialized = True

    async def run(
        self,
        fn: Callable[..., T] | Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> TaskHandle[T]:
        """Execute a function using Ray remote.

        Args:
            fn: Sync or async callable.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            TaskHandle for the running task.
        """
        self._ensure_ray_init()
        ray = _get_ray()

        handle: TaskHandle[T] = TaskHandle()

        remote_kwargs = {k: v for k, v in self._kwargs.items() if k in {'num_cpus', 'num_gpus', 'memory'}}

        if inspect.iscoroutinefunction(fn):

            @ray.remote(**remote_kwargs)
            async def _async_wrapper(*a: Any, **kw: Any) -> T:
                return await fn(*a, **kw)  # type: ignore[misc]

            object_ref = _async_wrapper.remote(*args, **kwargs)
        else:

            @ray.remote(**remote_kwargs)
            def _sync_wrapper(*a: Any, **kw: Any) -> T:
                return fn(*a, **kw)  # type: ignore[return-value]

            object_ref = _sync_wrapper.remote(*args, **kwargs)

        self._handles.append(handle)
        self._object_refs[handle] = object_ref

        async def _wait_for_result() -> None:
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: ray.get(object_ref))
                handle._complete(result)
            except ray.exceptions.TaskCancelledError:
                handle._fail(CancelledError('Ray task cancelled'), ExitReason.CANCELLED)
            except Exception as e:
                handle._fail(e, ExitReason.ERROR)

        task = asyncio.create_task(_wait_for_result())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        return handle

    async def shutdown(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """Shutdown the Ray backend.

        Args:
            wait: If True, wait for pending tasks to complete.
            timeout: Maximum time to wait for shutdown.
        """
        ray = _get_ray()

        if wait:
            await self._wait_for_handles(timeout)
        else:
            self._cancel_pending(ray)

        self._handles.clear()
        self._object_refs.clear()

    async def _wait_for_handles(self, timeout: float | None) -> None:
        """Wait for all handles to complete."""
        for handle in self._handles:
            if handle.is_running():
                with contextlib.suppress(Exception):
                    if timeout is not None:
                        await asyncio.wait_for(handle.wait(), timeout=timeout)
                    else:
                        await handle.wait()

    def _cancel_pending(self, ray: Any) -> None:
        """Cancel all pending tasks."""
        for handle, obj_ref in self._object_refs.items():
            if handle.is_running():
                with contextlib.suppress(Exception):
                    ray.cancel(obj_ref)
                handle.cancel('Shutdown requested')
