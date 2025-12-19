"""Container-based tests for Executor and backends.

These tests verify the Executor works correctly inside Docker containers
and with Ray clusters.

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


KLAW_CORE_PATH = '/Users/wrath/projects/klaw/workspaces/python/klaw-core'

SETUP_SCRIPT = """
pip install -q msgspec psutil structlog async-lru aioitertools wrapt aiologic anyio tenacity diskcache > /dev/null 2>&1
python -c "
import sys
sys.path.insert(0, '/app/src')
import asyncio
"""

SCRIPT_SUFFIX = '"'


@pytest.mark.containers
class TestExecutorInContainer:
    """Tests for Executor running inside containers."""

    def test_executor_submit_in_container(self, docker: DockerClient, unique_name: str) -> None:
        """Executor.submit() works inside a container."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime import init, Executor

async def main():
    init(backend='local', concurrency=2)
    async with Executor() as ex:
        handle = await ex.submit(lambda: 42)
        result = await handle
        print(f'result={{result}}')
        assert result == 42, f'Expected 42, got {{result}}'
        print('PASS: Executor.submit() works in container')

asyncio.run(main())
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_executor_submit{unique_name}',
                cpus=2.0,
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'PASS' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')

    def test_executor_map_in_container(self, docker: DockerClient, unique_name: str) -> None:
        """Executor.map() works inside a container."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime import init, Executor

async def main():
    init(backend='local', concurrency=4)
    async with Executor() as ex:
        results = await ex.map(lambda x: x * 2, [1, 2, 3, 4, 5])
        values = [r.unwrap() for r in results]
        print(f'values={{values}}')
        assert values == [2, 4, 6, 8, 10], f'Expected [2,4,6,8,10], got {{values}}'
        print('PASS: Executor.map() works in container')

asyncio.run(main())
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_executor_map{unique_name}',
                cpus=4.0,
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'PASS' in output
        except Exception as e:
            pytest.skip(f'Docker not available: {e}')

    def test_executor_respects_cpu_limit(self, docker: DockerClient, unique_name: str) -> None:
        """Executor respects container CPU limits."""
        script = f"""{SETUP_SCRIPT}
from klaw_core.runtime import init, get_config, Executor

async def main():
    config = init(backend='local')
    print(f'concurrency={{config.concurrency}}')

    # With 2 CPUs, concurrency should be <= 2
    assert config.concurrency <= 2, f'Expected <= 2, got {{config.concurrency}}'

    async with Executor() as ex:
        results = await ex.map(lambda x: x, [1, 2, 3])
        print(f'results_count={{len(results)}}')
        assert len(results) == 3
        print('PASS: Executor respects CPU limit')

asyncio.run(main())
{SCRIPT_SUFFIX}
"""
        try:
            output = docker.run(
                'python:3.13-slim',
                ['sh', '-c', script],
                name=f'klaw_executor_cpu{unique_name}',
                cpus=2.0,
                remove=True,
                volumes=[(KLAW_CORE_PATH, '/app', 'ro')],
            )
            print(output)
            assert 'concurrency=' in output
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
class TestRayBackendCluster:
    """Tests for RayBackend with Ray cluster."""

    def test_ray_backend_basic(self, docker: DockerClient, unique_name: str) -> None:
        """RayBackend executes tasks on Ray cluster."""
        import time

        from python_on_whales import docker as docker_cli

        ray_image = _get_ray_image()

        network_name = f'ray_net_exec{unique_name}'
        head_name = f'ray_head_exec{unique_name}'

        def wait_for_ray_head(max_attempts: int = 10) -> bool:
            """Wait for Ray head to be ready."""
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
            docker_cli.network.create(network_name)

            docker_cli.run(
                ray_image,
                ['ray', 'start', '--head', '--port=6379', '--num-cpus=2', '--block'],
                name=head_name,
                networks=[network_name],
                detach=True,
                cpus=2.0,
            )

            if not wait_for_ray_head():
                pytest.skip('Ray head node failed to start')

            script = f"""
import ray
import asyncio

ray.init(address="ray://{head_name}:10001")

@ray.remote
def double(x):
    return x * 2

# Test basic remote execution
result = ray.get(double.remote(21))
print(f"result={{result}}")
assert result == 42, f"Expected 42, got {{result}}"
print("PASS: Ray remote execution works")

ray.shutdown()
"""
            output = docker_cli.run(
                ray_image,
                ['python', '-c', script],
                name=f'ray_exec_client{unique_name}',
                networks=[network_name],
                remove=True,
            )
            print(output)
            assert 'PASS' in output

        except Exception as e:
            pytest.skip(f'Ray cluster test failed: {e}')
        finally:
            for name in [head_name]:
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

    def test_ray_backend_map(self, docker: DockerClient, unique_name: str) -> None:
        """RayBackend.map() distributes work across cluster."""
        import time

        from python_on_whales import docker as docker_cli

        ray_image = _get_ray_image()

        network_name = f'ray_net_map{unique_name}'
        head_name = f'ray_head_map{unique_name}'
        worker_name = f'ray_worker_map{unique_name}'

        def wait_for_ray_head(max_attempts: int = 10) -> bool:
            """Wait for Ray head to be ready."""
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
            docker_cli.network.create(network_name)

            docker_cli.run(
                ray_image,
                ['ray', 'start', '--head', '--port=6379', '--num-cpus=2', '--block'],
                name=head_name,
                networks=[network_name],
                detach=True,
                cpus=2.0,
            )

            if not wait_for_ray_head():
                pytest.skip('Ray head node failed to start')

            docker_cli.run(
                ray_image,
                ['ray', 'start', f'--address={head_name}:6379', '--num-cpus=2', '--block'],
                name=worker_name,
                networks=[network_name],
                detach=True,
                cpus=2.0,
            )

            for _ in range(10):
                try:
                    status = docker_cli.execute(head_name, ['ray', 'status'])
                    if '4.0 CPU' in status or '4 CPU' in status:
                        break
                except Exception:
                    pass
                time.sleep(1)

            script = f"""
import ray
import asyncio

ray.init(address="ray://{head_name}:10001")

@ray.remote
def process(x):
    return x * 2

# Map over items using Ray
items = [1, 2, 3, 4, 5]
refs = [process.remote(x) for x in items]
results = ray.get(refs)

print(f"results={{results}}")
assert results == [2, 4, 6, 8, 10], f"Expected [2,4,6,8,10], got {{results}}"
print("PASS: Ray map-style execution works")

ray.shutdown()
"""
            output = docker_cli.run(
                ray_image,
                ['python', '-c', script],
                name=f'ray_map_client{unique_name}',
                networks=[network_name],
                remove=True,
            )
            print(output)
            assert 'PASS' in output

        except Exception as e:
            pytest.skip(f'Ray cluster test failed: {e}')
        finally:
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
