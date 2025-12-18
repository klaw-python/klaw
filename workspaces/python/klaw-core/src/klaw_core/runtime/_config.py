"""Runtime configuration: Backend enum, RuntimeConfig, and initialization."""

from __future__ import annotations

import logging
import os
import pathlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import psutil

from klaw_core.runtime._logging import configure_logging

__all__ = [
    'Backend',
    'RuntimeConfig',
    'get_config',
    'init',
]


class Backend(Enum):
    """Execution backend for runtime operations."""

    LOCAL = 'local'
    RAY = 'ray'


@dataclass(frozen=True)
class RuntimeConfig:
    """Configuration for the klaw runtime.

    Attributes:
        backend: Execution backend (LOCAL or RAY).
        concurrency: Maximum number of concurrent tasks (auto-detected if None).
        log_level: Logging level (e.g., "DEBUG", "INFO"). None = silent.
        checkpoint_path: Path for checkpoint storage.
        backend_kwargs: Additional backend-specific configuration.
    """

    backend: Backend = Backend.LOCAL
    concurrency: int = 4
    log_level: str | None = None
    checkpoint_path: str | None = None
    backend_kwargs: dict[str, Any] = field(default_factory=dict)


# Global runtime configuration (set by init())
_config: RuntimeConfig | None = None


def _detect_backend() -> Backend:
    """Detect appropriate backend from environment.

    Priority:
    1. KLAW_BACKEND environment variable ("local" or "ray")
    2. Ray cluster detection (if ray.is_initialized())
    3. Default to LOCAL
    """
    env_backend = os.environ.get('KLAW_BACKEND', '').lower()
    if env_backend == 'ray':
        return Backend.RAY
    if env_backend == 'local':
        return Backend.LOCAL
    if env_backend and env_backend not in ('local', 'ray'):
        logging.warning("Unknown KLAW_BACKEND value '%s', defaulting to local", env_backend)

    # Try to detect Ray cluster
    try:
        import ray

        if ray.is_initialized():
            return Backend.RAY
    except ImportError:
        pass

    return Backend.LOCAL


def _detect_concurrency(backend: Backend | None = None) -> int:
    """Detect optimal concurrency from system resources.

    For Ray backend, uses ray.cluster_resources() to get total cluster CPUs.
    For local backend, uses physical CPU cores with awareness of:
    - Container CPU limits (cgroups)
    - Available memory constraints
    - Minimum of 1, maximum of 256
    """
    # If Ray backend and Ray is initialized, use Ray's resource detection
    if backend == Backend.RAY:
        ray_cpus = _detect_ray_concurrency()
        if ray_cpus is not None:
            return ray_cpus

    # Fall back to local detection
    return _detect_local_concurrency()


def _detect_ray_concurrency() -> int | None:
    """Detect concurrency from Ray cluster resources.

    Uses ray.cluster_resources() for total cluster CPUs,
    or ray.available_resources() for currently available CPUs.

    Returns:
        Number of CPUs in the Ray cluster, or None if Ray not available.
    """
    try:
        import ray

        if not ray.is_initialized():
            return None

        # Get total cluster resources (all nodes)
        cluster_resources = ray.cluster_resources()
        total_cpus = cluster_resources.get('CPU', 0)

        if total_cpus > 0:
            return max(1, min(256, int(total_cpus)))

        # Fallback to available resources
        available = ray.available_resources()
        available_cpus = available.get('CPU', 0)
        if available_cpus > 0:
            return max(1, min(256, int(available_cpus)))

    except Exception:
        pass

    return None


def _detect_local_concurrency() -> int:
    """Detect concurrency from local system resources.

    Uses physical CPU cores with awareness of:
    - Container CPU limits (cgroups)
    - Available memory constraints
    """
    try:
        # Physical cores preferred over logical for CPU-bound work
        physical_cores = psutil.cpu_count(logical=False)
        if physical_cores is None:
            physical_cores = psutil.cpu_count(logical=True) or 4

        # Check for container CPU limits (cgroups v1 and v2)
        container_limit = _detect_container_cpu_limit()
        if container_limit is not None:
            physical_cores = min(physical_cores, container_limit)

        # Memory-based limiting: assume ~1GB per worker minimum
        try:
            available_memory_gb = psutil.virtual_memory().available / (1024**3)
            memory_limit = max(1, int(available_memory_gb))
            physical_cores = min(physical_cores, memory_limit)
        except Exception:
            pass

        return max(1, min(256, physical_cores))
    except Exception:
        return 4  # Safe default


def _detect_container_cpu_limit() -> int | None:
    """Detect CPU limit in containerized environments."""
    # cgroups v2
    try:
        with pathlib.Path('/sys/fs/cgroup/cpu.max').open() as f:
            content = f.read().strip()
            if content != 'max':
                quota, period = content.split()
                if quota != 'max':
                    return max(1, int(int(quota) / int(period)))
    except (FileNotFoundError, ValueError, PermissionError):
        pass

    # cgroups v1
    try:
        with pathlib.Path('/sys/fs/cgroup/cpu/cpu.cfs_quota_us').open() as quota_f:
            quota_v1 = int(quota_f.read().strip())
        with pathlib.Path('/sys/fs/cgroup/cpu/cpu.cfs_period_us').open() as period_f:
            period_v1 = int(period_f.read().strip())
        if quota_v1 > 0:
            return max(1, quota_v1 // period_v1)
    except (FileNotFoundError, ValueError, PermissionError):
        pass

    return None


def init(
    backend: Backend | str | None = None,
    concurrency: int | None = None,
    log_level: str | None = None,
    checkpoint_path: str | None = None,
    **backend_kwargs: Any,
) -> RuntimeConfig:
    """Initialize the klaw runtime with specified configuration.

    Args:
        backend: Execution backend. Auto-detected if None.
            Can be Backend enum or string ("local", "ray").
        concurrency: Max concurrent tasks. Auto-detected if None.
        log_level: Logging level ("DEBUG", "INFO", etc.). None = silent.
        checkpoint_path: Path for checkpoint storage.
        **backend_kwargs: Backend-specific configuration passed through.

    Returns:
        The RuntimeConfig that was set.

    Example:
        ```python
        from klaw_core.runtime import init, Backend

        # Auto-detect everything
        init()

        # Explicit configuration
        init(backend=Backend.RAY, concurrency=8, log_level="INFO")

        # With backend kwargs for Ray
        init(backend="ray", num_cpus=4, num_gpus=1)
        ```
    """
    global _config  # noqa: PLW0603

    # Resolve backend
    if backend is None:
        resolved_backend = _detect_backend()
    elif isinstance(backend, str):
        resolved_backend = Backend(backend.lower())
    else:
        resolved_backend = backend

    # Resolve concurrency (pass backend for Ray-aware detection)
    if concurrency is None:
        resolved_concurrency = _detect_concurrency(resolved_backend)
    else:
        resolved_concurrency = max(1, min(256, concurrency))

    _config = RuntimeConfig(
        backend=resolved_backend,
        concurrency=resolved_concurrency,
        log_level=log_level,
        checkpoint_path=checkpoint_path,
        backend_kwargs=backend_kwargs,
    )

    # Configure logging if level specified
    if log_level is not None:
        configure_logging(log_level)

    return _config


def get_config() -> RuntimeConfig:
    """Get the current runtime configuration.

    Returns:
        The current RuntimeConfig.

    Raises:
        RuntimeError: If init() has not been called.

    Example:
        ```python
        from klaw_core.runtime import init, get_config

        init(concurrency=8)
        config = get_config()
        print(config.concurrency)  # 8
        ```
    """
    if _config is None:
        msg = 'Runtime not initialized. Call runtime.init() first.'
        raise RuntimeError(msg)
    return _config
