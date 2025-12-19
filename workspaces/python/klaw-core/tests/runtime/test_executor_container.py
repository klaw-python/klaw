"""Container-based tests for Executor and backends.

These tests verify the Executor works correctly inside Docker containers
and with Ray clusters.

Requires Docker to be available. Mark with @pytest.mark.containers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.runtime.conftest import ContainerRunner, RayClusterFixture


@pytest.mark.containers
class TestExecutorInContainer:
    """Tests for Executor running inside containers."""

    def test_executor_submit_in_container(self, container_runner: ContainerRunner) -> None:
        """Executor.submit() works inside a container."""
        output = container_runner.run(
            """
init(backend='local', concurrency=2)
async with Executor() as ex:
    handle = await ex.submit(lambda: 42)
    result = await handle
    print(f'result={result}')
    assert result == 42, f'Expected 42, got {result}'
    print('PASS: Executor.submit() works in container')
""",
            cpus=2.0,
            name_suffix='_executor_submit',
            async_script=True,
        )
        print(output)
        assert 'PASS' in output

    def test_executor_map_in_container(self, container_runner: ContainerRunner) -> None:
        """Executor.map() works inside a container."""
        output = container_runner.run(
            """
init(backend='local', concurrency=4)
async with Executor() as ex:
    results = await ex.map(lambda x: x * 2, [1, 2, 3, 4, 5])
    values = [r.unwrap() for r in results]
    print(f'values={values}')
    assert values == [2, 4, 6, 8, 10], f'Expected [2,4,6,8,10], got {values}'
    print('PASS: Executor.map() works in container')
""",
            cpus=4.0,
            name_suffix='_executor_map',
            async_script=True,
        )
        print(output)
        assert 'PASS' in output

    def test_executor_respects_cpu_limit(self, container_runner: ContainerRunner) -> None:
        """Executor respects container CPU limits."""
        output = container_runner.run(
            """
config = init(backend='local')
print(f'concurrency={config.concurrency}')

# With 2 CPUs, concurrency should be <= 2
assert config.concurrency <= 2, f'Expected <= 2, got {config.concurrency}'

async with Executor() as ex:
    results = await ex.map(lambda x: x, [1, 2, 3])
    print(f'results_count={len(results)}')
    assert len(results) == 3
    print('PASS: Executor respects CPU limit')
""",
            cpus=2.0,
            name_suffix='_executor_cpu',
            async_script=True,
        )
        print(output)
        assert 'concurrency=' in output


@pytest.mark.containers
class TestRayBackendCluster:
    """Tests for RayBackend with Ray cluster."""

    def test_ray_backend_basic(self, ray_cluster: RayClusterFixture) -> None:
        """RayBackend executes tasks on Ray cluster."""
        output = ray_cluster.run_script(
            """
@ray.remote
def double(x):
    return x * 2

result = ray.get(double.remote(21))
print(f'result={result}')
assert result == 42, f'Expected 42, got {result}'
print('PASS: Ray remote execution works')
""",
            client_name=f'ray_exec_client{ray_cluster.unique_suffix}',
        )
        print(output)
        assert 'PASS' in output

    def test_ray_backend_map(self, ray_cluster: RayClusterFixture) -> None:
        """RayBackend.map() distributes work across cluster."""
        ray_cluster.add_worker(num_cpus=2, name_suffix='_map')
        ray_cluster.wait_for_cpus(4)

        output = ray_cluster.run_script(
            """
@ray.remote
def process(x):
    return x * 2

items = [1, 2, 3, 4, 5]
refs = [process.remote(x) for x in items]
results = ray.get(refs)

print(f'results={results}')
assert results == [2, 4, 6, 8, 10], f'Expected [2,4,6,8,10], got {results}'
print('PASS: Ray map-style execution works')
""",
            client_name=f'ray_map_client{ray_cluster.unique_suffix}',
        )
        print(output)
        assert 'PASS' in output
