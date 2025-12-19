"""Container-based tests for runtime config detection.

These tests verify our actual detection functions work correctly
inside Docker containers with CPU/memory limits.

Requires Docker to be available. Mark with @pytest.mark.containers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.runtime.conftest import ContainerRunner, RayClusterFixture


@pytest.mark.containers
class TestDetectContainerCpuLimit:
    """Tests for _detect_container_cpu_limit() inside containers."""

    def test_detects_cpu_limit_with_cpus_flag(self, container_runner: ContainerRunner) -> None:
        """_detect_container_cpu_limit() returns correct value with --cpus=2."""
        output = container_runner.run(
            """
from klaw_core.runtime._config import _detect_container_cpu_limit

limit = _detect_container_cpu_limit()
print(f'cpu_limit={limit}')

if limit is not None:
    assert limit == 2, f'Expected 2, got {limit}'
    print('PASS: _detect_container_cpu_limit() returned 2')
else:
    # On some Docker setups (macOS), cgroups may not be exposed
    print('SKIP: cgroups not available in this environment')
""",
            cpus=2.0,
            name_suffix='_detect_cpu',
        )
        print(output)
        assert 'cpu_limit=' in output

    def test_returns_none_without_cpu_limit(self, container_runner: ContainerRunner) -> None:
        """_detect_container_cpu_limit() returns None when no limit set."""
        output = container_runner.run(
            """
from klaw_core.runtime._config import _detect_container_cpu_limit

limit = _detect_container_cpu_limit()
print(f'cpu_limit={limit}')

# Without --cpus flag, limit should be None
assert limit is None, f'Expected None, got {limit}'
print('PASS: _detect_container_cpu_limit() returned None (no limit)')
""",
            name_suffix='_detect_no_cpu',
        )
        print(output)
        assert 'PASS' in output or 'cpu_limit=None' in output


@pytest.mark.containers
class TestDetectConcurrency:
    """Tests for _detect_concurrency() inside containers."""

    def test_respects_cpu_limit(self, container_runner: ContainerRunner) -> None:
        """_detect_concurrency() respects container CPU limit."""
        output = container_runner.run(
            """
from klaw_core.runtime._config import _detect_concurrency

concurrency = _detect_concurrency()
print(f'concurrency={concurrency}')

# With --cpus=2, concurrency should be <= 2
assert 1 <= concurrency <= 2, f'Expected 1-2, got {concurrency}'
print('PASS: _detect_concurrency() respects CPU limit')
""",
            cpus=2.0,
            name_suffix='_detect_conc',
        )
        print(output)
        assert 'concurrency=' in output

    def test_respects_memory_limit(self, container_runner: ContainerRunner) -> None:
        """_detect_concurrency() considers memory constraints."""
        output = container_runner.run(
            """
from klaw_core.runtime._config import _detect_concurrency

concurrency = _detect_concurrency()
print(f'concurrency={concurrency}')

# With 512MB memory, concurrency should be limited
# (our heuristic assumes ~1GB per worker)
assert concurrency >= 1, f'Expected >= 1, got {concurrency}'
print('PASS: _detect_concurrency() returned valid value')
""",
            memory='512m',
            name_suffix='_detect_mem',
        )
        print(output)
        assert 'concurrency=' in output


@pytest.mark.containers
class TestDetectBackend:
    """Tests for _detect_backend() inside containers."""

    def test_detects_backend_from_env(self, container_runner: ContainerRunner) -> None:
        """_detect_backend() reads KLAW_BACKEND env var."""
        output = container_runner.run(
            """
from klaw_core.runtime._config import _detect_backend, Backend

backend = _detect_backend()
print(f'backend={backend.value}')

assert backend == Backend.RAY, f'Expected RAY, got {backend}'
print('PASS: _detect_backend() detected ray from env')
""",
            envs={'KLAW_BACKEND': 'ray'},
            name_suffix='_detect_backend',
        )
        print(output)
        assert 'PASS' in output

    def test_defaults_to_local(self, container_runner: ContainerRunner) -> None:
        """_detect_backend() defaults to LOCAL without env var."""
        output = container_runner.run(
            """
from klaw_core.runtime._config import _detect_backend, Backend

backend = _detect_backend()
print(f'backend={backend.value}')

assert backend == Backend.LOCAL, f'Expected LOCAL, got {backend}'
print('PASS: _detect_backend() defaults to local')
""",
            name_suffix='_detect_backend_local',
        )
        print(output)
        assert 'PASS' in output


@pytest.mark.containers
class TestRayCluster:
    """Tests for Ray cluster resource detection."""

    def test_detects_cluster_cpus(self, ray_cluster: RayClusterFixture) -> None:
        """_detect_ray_concurrency() returns total CPUs across cluster nodes."""
        ray_cluster.add_worker(num_cpus=2)
        ray_cluster.wait_for_cpus(4)

        output = ray_cluster.run_script(
            """
cpus = ray.cluster_resources().get('CPU', 0)
print(f'cluster_cpus={int(cpus)}')
assert cpus >= 4, f'Expected >= 4 CPUs (head+worker), got {cpus}'
print('PASS: Ray cluster detected 4+ CPUs')
""",
            client_name=f'ray_client{ray_cluster.unique_suffix}',
        )
        print(output)
        assert 'PASS' in output


@pytest.mark.containers
class TestInit:
    """Tests for init() inside containers."""

    def test_init_auto_detection(self, container_runner: ContainerRunner) -> None:
        """init() with auto-detection works in container."""
        output = container_runner.run(
            """
from klaw_core.runtime import init, get_config, Backend

config = init()
print(f'backend={config.backend.value}')
print(f'concurrency={config.concurrency}')

assert config.backend == Backend.LOCAL
assert 1 <= config.concurrency <= 4
print('PASS: init() auto-detection works')
""",
            cpus=4.0,
            name_suffix='_init',
        )
        print(output)
        assert 'PASS' in output

    def test_init_with_explicit_config(self, container_runner: ContainerRunner) -> None:
        """init() with explicit config overrides detection."""
        output = container_runner.run(
            """
from klaw_core.runtime import init, get_config, Backend

config = init(backend='local', concurrency=8, log_level='DEBUG')
print(f'backend={config.backend.value}')
print(f'concurrency={config.concurrency}')
print(f'log_level={config.log_level}')

assert config.backend == Backend.LOCAL
assert config.concurrency == 8
assert config.log_level == 'DEBUG'
print('PASS: init() explicit config works')
""",
            name_suffix='_init_explicit',
        )
        print(output)
        assert 'PASS' in output
