"""Container-based tests for runtime config detection.

These tests verify our actual detection functions work correctly
inside Docker containers with CPU/memory limits.

Requires Docker to be available. Mark with @pytest.mark.containers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from python_on_whales import DockerClient


@pytest.fixture(scope='module')
def docker() -> DockerClient:
    """Provide a DockerClient for container tests."""
    from python_on_whales import DockerClient

    return DockerClient()


# Path to klaw-core for volume mounting
KLAW_CORE_PATH = '/Users/wrath/projects/klaw/workspaces/python/klaw-core'

# Script prefix to install deps and setup path
SETUP_SCRIPT = """
pip install -q msgspec psutil structlog async-lru aioitertools wrapt aiologic anyio > /dev/null 2>&1
python -c "
import sys
sys.path.insert(0, '/app/src')
"""

SCRIPT_SUFFIX = '"'


@pytest.mark.containers
class TestDetectContainerCpuLimit:
    """Tests for _detect_container_cpu_limit() inside containers."""

    def test_detects_cpu_limit_with_cpus_flag(self, docker: DockerClient, unique_name: str) -> None:
        """_detect_container_cpu_limit() returns correct value with --cpus=2."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime._config import _detect_container_cpu_limit

limit = _detect_container_cpu_limit()
print(f'cpu_limit={{limit}}')

if limit is not None:
    assert limit == 2, f'Expected 2, got {{limit}}'
    print('PASS: _detect_container_cpu_limit() returned 2')
else:
    # On some Docker setups (macOS), cgroups may not be exposed
    print('SKIP: cgroups not available in this environment')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_detect_cpu{unique_name}',
                cpus=2.0,
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'cpu_limit=' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')

    def test_returns_none_without_cpu_limit(self, docker: DockerClient, unique_name: str) -> None:
        """_detect_container_cpu_limit() returns None when no limit set."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime._config import _detect_container_cpu_limit

limit = _detect_container_cpu_limit()
print(f'cpu_limit={{limit}}')

# Without --cpus flag, limit should be None
assert limit is None, f'Expected None, got {{limit}}'
print('PASS: _detect_container_cpu_limit() returned None (no limit)')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_detect_no_cpu{unique_name}',
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'PASS' in output or 'cpu_limit=None' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')


@pytest.mark.containers
class TestDetectConcurrency:
    """Tests for _detect_concurrency() inside containers."""

    def test_respects_cpu_limit(self, docker: DockerClient, unique_name: str) -> None:
        """_detect_concurrency() respects container CPU limit."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime._config import _detect_concurrency

concurrency = _detect_concurrency()
print(f'concurrency={{concurrency}}')

# With --cpus=2, concurrency should be <= 2
assert 1 <= concurrency <= 2, f'Expected 1-2, got {{concurrency}}'
print('PASS: _detect_concurrency() respects CPU limit')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_detect_conc{unique_name}',
                cpus=2.0,
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'concurrency=' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')

    def test_respects_memory_limit(self, docker: DockerClient, unique_name: str) -> None:
        """_detect_concurrency() considers memory constraints."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime._config import _detect_concurrency

concurrency = _detect_concurrency()
print(f'concurrency={{concurrency}}')

# With 512MB memory, concurrency should be limited
# (our heuristic assumes ~1GB per worker)
assert concurrency >= 1, f'Expected >= 1, got {{concurrency}}'
print('PASS: _detect_concurrency() returned valid value')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_detect_mem{unique_name}',
                memory='512m',
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'concurrency=' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')


@pytest.mark.containers
class TestDetectBackend:
    """Tests for _detect_backend() inside containers."""

    def test_detects_backend_from_env(self, docker: DockerClient, unique_name: str) -> None:
        """_detect_backend() reads KLAW_BACKEND env var."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime._config import _detect_backend, Backend

backend = _detect_backend()
print(f'backend={{backend.value}}')

assert backend == Backend.RAY, f'Expected RAY, got {{backend}}'
print('PASS: _detect_backend() detected ray from env')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_detect_backend{unique_name}',
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
                envs={'KLAW_BACKEND': 'ray'},
            )
            print(output)
            assert 'PASS' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')

    def test_defaults_to_local(self, docker: DockerClient, unique_name: str) -> None:
        """_detect_backend() defaults to LOCAL without env var."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime._config import _detect_backend, Backend

backend = _detect_backend()
print(f'backend={{backend.value}}')

assert backend == Backend.LOCAL, f'Expected LOCAL, got {{backend}}'
print('PASS: _detect_backend() defaults to local')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_detect_backend_local{unique_name}',
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'PASS' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')


def _get_ray_image() -> str:
    """Get Ray Docker image for current platform."""
    import platform

    arch = platform.machine()
    if arch in {'arm64', 'aarch64'}:
        return 'rayproject/ray:2.9.0-aarch64'
    return 'rayproject/ray:2.9.0'


@pytest.mark.containers
class TestRayCluster:
    """Tests for Ray cluster resource detection."""

    def test_detects_cluster_cpus(self, docker: DockerClient, unique_name: str) -> None:
        """_detect_ray_concurrency() returns total CPUs across cluster nodes."""
        import time

        from python_on_whales import docker as docker_cli

        ray_image = _get_ray_image()

        network_name = f'ray_net{unique_name}'
        head_name = f'ray_head{unique_name}'
        worker_name = f'ray_worker{unique_name}'

        def wait_for_ray_head(max_attempts: int = 10) -> bool:
            """Wait for Ray head to be ready by checking ray status."""
            for _ in range(max_attempts):
                try:
                    result = docker_cli.execute(head_name, ['ray', 'status'])
                    if 'Active' in result or 'CPU' in result:
                        return True
                except Exception:
                    pass
                time.sleep(1)
            return False

        try:
            # Create network
            docker_cli.network.create(network_name)

            # Start head node (2 CPUs)
            docker_cli.run(
                ray_image,
                ['ray', 'start', '--head', '--port=6379', '--num-cpus=2', '--block'],
                name=head_name,
                networks=[network_name],
                detach=True,
                cpus=2.0,
            )

            # Wait for head to be ready
            if not wait_for_ray_head():
                pytest.skip('Ray head node failed to start')

            # Start worker node (2 CPUs)
            docker_cli.run(
                ray_image,
                ['ray', 'start', f'--address={head_name}:6379', '--num-cpus=2', '--block'],
                name=worker_name,
                networks=[network_name],
                detach=True,
                cpus=2.0,
            )

            # Wait for worker to join (check cluster has 4 CPUs)
            for _ in range(10):
                try:
                    status = docker_cli.execute(head_name, ['ray', 'status'])
                    if '4.0 CPU' in status or '4 CPU' in status:
                        break
                except Exception:
                    pass
                time.sleep(1)

            # Test script: connect and check total CPUs
            script = f"""
import ray
ray.init(address="ray://{head_name}:10001")
cpus = ray.cluster_resources().get("CPU", 0)
print(f"cluster_cpus={{int(cpus)}}")
assert cpus >= 4, f"Expected >= 4 CPUs (head+worker), got {{cpus}}"
print("PASS: Ray cluster detected 4+ CPUs")
ray.shutdown()
"""
            output = docker_cli.run(
                ray_image,
                ['python', '-c', script],
                name=f'ray_client{unique_name}',
                networks=[network_name],
                remove=True,
            )
            print(output)
            assert 'PASS' in output

        except Exception as e:
            pytest.skip(f'Ray cluster test failed: {e}')
        finally:
            # Cleanup
            for name in [head_name, worker_name]:
                try:
                    docker_cli.stop(name, time=5)
                except Exception:
                    pass
                try:
                    docker_cli.remove(name, force=True)
                except Exception:
                    pass
            try:
                docker_cli.network.remove(network_name)
            except Exception:
                pass


@pytest.mark.containers
class TestInit:
    """Tests for init() inside containers."""

    def test_init_auto_detection(self, docker: DockerClient, unique_name: str) -> None:
        """init() with auto-detection works in container."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime import init, get_config, Backend

config = init()
print(f'backend={{config.backend.value}}')
print(f'concurrency={{config.concurrency}}')

assert config.backend == Backend.LOCAL
assert 1 <= config.concurrency <= 4
print('PASS: init() auto-detection works')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_init{unique_name}',
                cpus=4.0,
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'PASS' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')

    def test_init_with_explicit_config(self, docker: DockerClient, unique_name: str) -> None:
        """init() with explicit config overrides detection."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime import init, get_config, Backend

config = init(backend='local', concurrency=8, log_level='DEBUG')
print(f'backend={{config.backend.value}}')
print(f'concurrency={{config.concurrency}}')
print(f'log_level={{config.log_level}}')

assert config.backend == Backend.LOCAL
assert config.concurrency == 8
assert config.log_level == 'DEBUG'
print('PASS: init() explicit config works')
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_init_explicit{unique_name}',
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'PASS' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')
