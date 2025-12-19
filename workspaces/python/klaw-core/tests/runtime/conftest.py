"""Pytest configuration for runtime tests."""

from __future__ import annotations

import os
import platform
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from python_on_whales import Container, DockerClient, Network


class RayMode(StrEnum):
    """Ray initialization modes for testing."""

    LOCAL = 'local'  # local_mode=True, in-process, fast
    STANDALONE = 'standalone'  # Real Ray processes, local cluster
    CLUSTER = 'cluster'  # Connect to existing cluster (address from env)


RAY_RUNTIME_ENV_EXCLUDES = [
    '.git',
    '.venv',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.hypothesis',
    '*.dbc',
    'node_modules',
    'target',
    'dist',
    'build',
    'site',
    'docs-build',
    '.benchmarks',
    '.cache',
]


@pytest.fixture(params=[RayMode.LOCAL])
def ray_env(request: pytest.FixtureRequest) -> Generator[RayMode]:
    """Initialize Ray with configurable mode.

    Default: LOCAL mode for fast unit tests.
    Override with @pytest.mark.parametrize("ray_env", [...], indirect=True)
    or set KLAW_RAY_TEST_MODE env var.

    Modes:
        LOCAL: local_mode=True, runs actor code in-process (fastest, easiest to debug)
        STANDALONE: Real Ray processes on local machine (more realistic)
        CLUSTER: Connect to existing cluster via KLAW_RAY_CLUSTER_ADDRESS env var

    Example:
        ```python
        @pytest.mark.ray
        def test_something(self, ray_env):
            # Ray is initialized, use it
            pass

        # Run against multiple modes:
        @pytest.mark.ray
        @pytest.mark.parametrize("ray_env", [RayMode.LOCAL, RayMode.STANDALONE], indirect=True)
        def test_cross_mode(self, ray_env):
            pass
        ```
    """
    import ray

    mode_override = os.environ.get('KLAW_RAY_TEST_MODE')
    mode = RayMode(mode_override) if mode_override else request.param

    if mode == RayMode.LOCAL:
        ray.init(local_mode=True, ignore_reinit_error=True)
    elif mode == RayMode.STANDALONE:
        ray.init(
            num_cpus=2,
            ignore_reinit_error=True,
            include_dashboard=False,
            runtime_env={'excludes': RAY_RUNTIME_ENV_EXCLUDES},
        )
    elif mode == RayMode.CLUSTER:
        address = os.environ.get('KLAW_RAY_CLUSTER_ADDRESS', 'auto')
        ray.init(address=address, ignore_reinit_error=True)

    yield mode
    ray.shutdown()


@pytest.fixture
def ray_local() -> Generator[None]:
    """Ray in local mode (fast, in-process). Simple fixture without parameterization."""
    import ray

    ray.init(local_mode=True, ignore_reinit_error=True)
    yield
    ray.shutdown()


@pytest.fixture
def ray_with_cpus_4() -> Generator[None]:
    """Ray initialized with exactly 4 CPUs for concurrency tests."""
    import ray

    # Opt-in to future Ray behavior for GPU env var handling
    os.environ['RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO'] = '0'
    ray.init(
        num_cpus=4,
        ignore_reinit_error=True,
        include_dashboard=False,
        runtime_env={'excludes': RAY_RUNTIME_ENV_EXCLUDES},
    )
    yield
    ray.shutdown()


@pytest.fixture
def ray_with_cpus_8() -> Generator[None]:
    """Ray initialized with exactly 8 CPUs for concurrency tests."""
    import ray

    # Opt-in to future Ray behavior for GPU env var handling
    os.environ['RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO'] = '0'
    ray.init(
        num_cpus=8,
        ignore_reinit_error=True,
        include_dashboard=False,
        runtime_env={'excludes': RAY_RUNTIME_ENV_EXCLUDES},
    )
    yield
    ray.shutdown()


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend for async tests."""
    return 'asyncio'


def get_worker_suffix() -> str:
    """Return unique suffix based on pytest-xdist worker ID."""
    worker = os.environ.get('PYTEST_XDIST_WORKER', '')
    if worker.startswith('gw'):
        return f'_{worker}'
    return ''


@pytest.fixture
def unique_name() -> str:
    """Return unique suffix for container names.

    Ensures containers in parallel workers don't conflict.

    Example:
        ```python
        def test_something(self, unique_name):
            container_name = f"test_container{unique_name}"
        ```
    """
    return get_worker_suffix()


def _get_klaw_core_path() -> str:
    """Get absolute path to klaw-core for volume mounting."""
    # conftest.py is in klaw-core/tests/runtime/
    # .parent = tests/runtime/, .parent.parent = tests/, .parent.parent.parent = klaw-core/
    return str(Path(__file__).parent.parent.parent.absolute())


# =============================================================================
# Container Runner (Simple single-container tests)
# =============================================================================


@dataclass
class ContainerRunner:
    """Helper for running klaw code inside Docker containers.

    Simplifies the common pattern of:
    - Installing dependencies
    - Mounting klaw-core source
    - Running Python scripts
    - Handling container cleanup

    Example:
        ```python
        @pytest.mark.containers
        def test_something(self, container_runner: ContainerRunner):
            output = container_runner.run(
                '''
    from klaw_core.runtime import init
    config = init()
    print(f'backend={config.backend.value}')
    print('PASS')
    ''',
                cpus=2.0,
                memory='512m',
            )
            assert 'PASS' in output
        ```
    """

    _docker: DockerClient = field(repr=False)
    _unique_suffix: str
    _klaw_core_path: str = field(default_factory=_get_klaw_core_path)
    _base_image: str = 'python:3.13-slim'
    _extra_deps: list[str] = field(default_factory=list)

    def run(
        self,
        script: str,
        *,
        cpus: float | None = None,
        memory: str | None = None,
        envs: dict[str, str] | None = None,
        name_suffix: str = '',
        async_script: bool = False,
    ) -> str:
        """Run a Python script inside a container with klaw-core mounted.

        Args:
            script: Python code to execute (klaw imports available)
            cpus: CPU limit (e.g., 2.0)
            memory: Memory limit (e.g., '512m')
            envs: Environment variables
            name_suffix: Suffix for container name
            async_script: If True, wraps script in asyncio.run()

        Returns:
            Output from script execution
        """
        deps = [
            'msgspec',
            'psutil',
            'structlog',
            'async-lru',
            'aioitertools',
            'wrapt',
            'aiologic',
            'anyio',
            'tenacity',
            'diskcache',
            *self._extra_deps,
        ]
        deps_str = ' '.join(deps)

        if async_script:
            wrapped_script = f"""
import asyncio
from klaw_core.runtime import init, get_config, Executor, Backend

async def main():
{_indent(script, 4)}

asyncio.run(main())
"""
        else:
            wrapped_script = script

        full_script = f"""
pip install -q {deps_str} > /dev/null 2>&1
python -c "
import sys
sys.path.insert(0, '/app/src')

{wrapped_script}
"
"""
        container_name = f'klaw_test{name_suffix}{self._unique_suffix}'

        run_kwargs: dict = {
            'name': container_name,
            'remove': True,
            'volumes': [(self._klaw_core_path, '/app', 'ro')],
        }
        if cpus is not None:
            run_kwargs['cpus'] = cpus
        if memory is not None:
            run_kwargs['memory'] = memory
        if envs is not None:
            run_kwargs['envs'] = envs

        try:
            result = self._docker.run(
                self._base_image,
                ['sh', '-c', full_script],
                **run_kwargs,
            )
            return str(result) if result else ''
        except Exception as e:
            import pytest

            pytest.skip(f'Docker not available: {e}')
            return ''  # unreachable but satisfies type checker


def _indent(text: str, spaces: int) -> str:
    """Indent each line of text by the given number of spaces."""
    prefix = ' ' * spaces
    return '\n'.join(prefix + line if line.strip() else line for line in text.split('\n'))


@pytest.fixture
def container_runner(unique_name: str) -> ContainerRunner:
    """Provide a ContainerRunner for simple container tests.

    Example:
        ```python
        @pytest.mark.containers
        def test_cpu_detection(self, container_runner: ContainerRunner):
            output = container_runner.run(
                '''
    from klaw_core.runtime._config import _detect_container_cpu_limit
    limit = _detect_container_cpu_limit()
    print(f'limit={limit}')
    assert limit == 2
    print('PASS')
    ''',
                cpus=2.0,
            )
            assert 'PASS' in output
        ```
    """
    from python_on_whales import DockerClient

    return ContainerRunner(
        _docker=DockerClient(),
        _unique_suffix=unique_name,
    )


def _get_ray_image() -> str:
    """Get Ray Docker image for current platform."""
    arch = platform.machine()
    if arch in {'arm64', 'aarch64'}:
        return 'rayproject/ray:2.9.0-aarch64'
    return 'rayproject/ray:2.9.0'


def _wait_for_ray_head(docker: DockerClient, head_name: str, max_attempts: int = 30) -> bool:
    """Wait for Ray head node to be ready."""
    for _ in range(max_attempts):
        try:
            result = docker.execute(head_name, ['ray', 'status'])
            if isinstance(result, str) and ('Active' in result or 'CPU' in result):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# =============================================================================
# Approach 1: Context Manager-based Ray Cluster (Simple, Automatic Cleanup)
# =============================================================================


@dataclass
class RayClusterFixture:
    """Fixture for running code against a Ray cluster in Docker.

    Uses python-on-whales context managers for automatic cleanup.
    Provides helpers to run Python scripts against the cluster.

    Example:
        ```python
        @pytest.mark.containers
        def test_ray_remote(self, ray_cluster: RayClusterFixture):
            output = ray_cluster.run_script('''
    @ray.remote
    def double(x):
    return x * 2
    result = ray.get(double.remote(21))
    assert result == 42
    print("PASS")
    ''')
            assert 'PASS' in output
        ```
    """

    address: str
    head_name: str
    network_name: str
    ray_image: str
    unique_suffix: str
    _docker: DockerClient = field(repr=False)
    _head: Container = field(repr=False)
    _network: Network = field(repr=False)
    _workers: list[Container] = field(default_factory=list, repr=False)
    _exit_stack: ExitStack = field(default_factory=ExitStack, repr=False)

    def run_script(
        self,
        script: str,
        *,
        client_name: str | None = None,
        timeout: int = 60,
    ) -> str:
        """Run a Python script against the Ray cluster.

        The script runs in a container connected to the cluster network.
        `ray` is already imported and initialized with the cluster address.

        Args:
            script: Python code to execute (ray.init/shutdown handled automatically)
            client_name: Optional name for the client container
            timeout: Timeout in seconds

        Returns:
            Output from the script execution
        """
        full_script = f"""
import ray
ray.init(address="{self.address}")

{script}

ray.shutdown()
"""
        name = client_name or f'ray_client{self.unique_suffix}'
        return self._docker.run(
            self.ray_image,
            ['python', '-c', full_script],
            name=name,
            networks=[self.network_name],
            remove=True,
        )

    def add_worker(self, *, num_cpus: int = 2, name_suffix: str = '') -> Container:
        """Add a worker node to the cluster.

        Args:
            num_cpus: Number of CPUs for the worker
            name_suffix: Optional suffix for worker name

        Returns:
            The created worker container
        """
        worker_name = f'ray_worker{name_suffix}{self.unique_suffix}'
        worker = self._docker.run(
            self.ray_image,
            [
                'ray',
                'start',
                f'--address={self.head_name}:6379',
                f'--num-cpus={num_cpus}',
                '--block',
            ],
            name=worker_name,
            networks=[self.network_name],
            detach=True,
            cpus=float(num_cpus),
        )
        self._workers.append(worker)
        return worker

    def wait_for_cpus(self, expected_cpus: int, max_attempts: int = 30) -> bool:
        """Wait for the cluster to have the expected number of CPUs.

        Args:
            expected_cpus: Expected total CPU count
            max_attempts: Maximum number of polling attempts

        Returns:
            True if expected CPUs found, False otherwise
        """
        for _ in range(max_attempts):
            try:
                result = self._docker.execute(self.head_name, ['ray', 'status'])
                status = str(result) if result else ''
                if f'{expected_cpus}.0 CPU' in status or f'{expected_cpus} CPU' in status:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def get_cluster_status(self) -> str:
        """Get the current Ray cluster status."""
        result = self._docker.execute(self.head_name, ['ray', 'status'])
        return str(result) if result else ''

    def cleanup(self) -> None:
        """Explicitly cleanup workers (network and head handled by context managers)."""
        for worker in self._workers:
            try:
                worker.stop(time=5)
                worker.remove(force=True)
            except Exception:
                pass
        self._workers.clear()


@contextmanager
def _ray_cluster_context(unique_suffix: str) -> Generator[RayClusterFixture]:
    """Context manager for Ray cluster with automatic cleanup."""
    from python_on_whales import DockerClient

    docker = DockerClient()
    ray_image = _get_ray_image()
    network_name = f'ray_net{unique_suffix}'
    head_name = f'ray_head{unique_suffix}'

    with docker.network.create(network_name) as network:
        with docker.run(
            ray_image,
            ['ray', 'start', '--head', '--port=6379', '--num-cpus=2', '--block'],
            name=head_name,
            networks=[network_name],
            detach=True,
            cpus=2.0,
        ) as head:
            if not _wait_for_ray_head(docker, head_name):
                pytest.skip('Ray head node failed to start')

            fixture = RayClusterFixture(
                address=f'ray://{head_name}:10001',
                head_name=head_name,
                network_name=network_name,
                ray_image=ray_image,
                unique_suffix=unique_suffix,
                _docker=docker,
                _head=head,
                _network=network,
            )

            try:
                yield fixture
            finally:
                fixture.cleanup()


@pytest.fixture
def ray_cluster(unique_name: str) -> Generator[RayClusterFixture]:
    """Spin up a Ray cluster in Docker using context managers.

    Creates a Ray head node and network with automatic cleanup.
    Workers can be added via `add_worker()`.

    Example:
        ```python
        @pytest.mark.containers
        def test_ray_cluster(self, ray_cluster: RayClusterFixture):
            ray_cluster.add_worker(num_cpus=2)
            ray_cluster.wait_for_cpus(4)  # head(2) + worker(2)

            output = ray_cluster.run_script('''
    result = ray.cluster_resources().get("CPU", 0)
    print(f"cpus={int(result)}")
    assert result >= 4
    print("PASS")
    ''')
            assert 'PASS' in output
        ```
    """
    try:
        with _ray_cluster_context(unique_name) as fixture:
            yield fixture
    except Exception as e:
        pytest.skip(f'Ray cluster setup failed: {e}')


# =============================================================================
# Approach 2: Docker Compose-based Ray Cluster (Multi-container orchestration)
# =============================================================================


@dataclass
class RayComposeCluster:
    """Ray cluster managed via Docker Compose.

    Uses docker-compose.ray.yml for declarative cluster definition.
    Supports scaling workers and waiting for healthchecks.

    Example:
        ```python
        @pytest.mark.containers
        def test_ray_compose(self, ray_compose_cluster: RayComposeCluster):
            ray_compose_cluster.scale_workers(3)
            output = ray_compose_cluster.run_script('print(ray.cluster_resources())')
        ```
    """

    project_name: str
    compose_file: Path
    ray_image: str
    _docker: DockerClient = field(repr=False)

    @property
    def head_address(self) -> str:
        """Ray client address for connecting to the cluster."""
        return 'ray://ray-head:10001'

    def scale_workers(self, count: int, wait: bool = True) -> None:
        """Scale the number of worker replicas.

        Args:
            count: Number of worker replicas
            wait: Wait for scaling to complete
        """
        self._docker.compose.up(
            services=['ray-worker'],
            detach=True,
            scales={'ray-worker': count},
            wait=wait,
        )

    def run_script(
        self,
        script: str,
        *,
        timeout: int = 60,
    ) -> str:
        """Run a Python script against the Ray cluster.

        Args:
            script: Python code to execute
            timeout: Timeout in seconds

        Returns:
            Output from the script execution
        """
        full_script = f"""
import ray
ray.init(address='{self.head_address}')

{script}

ray.shutdown()
"""
        result = self._docker.compose.run(
            'ray-head',
            command=['python', '-c', full_script],
            remove=True,
        )
        return str(result) if result else ''

    def get_services(self) -> list:
        """Get all running services in the cluster."""
        return list(self._docker.compose.ps())

    def logs(self, service: str | None = None, follow: bool = False) -> str:
        """Get logs from services.

        Args:
            service: Specific service name, or None for all
            follow: Stream logs continuously

        Returns:
            Log output
        """
        services = [service] if service else []
        result = self._docker.compose.logs(services=services, follow=follow)
        return str(result) if result else ''


@pytest.fixture
def ray_compose_cluster(unique_name: str) -> Generator[RayComposeCluster]:
    """Spin up a Ray cluster using Docker Compose.

    Uses docker-compose.ray.yml for declarative cluster setup.
    Supports worker scaling and healthcheck-based readiness.

    Example:
        ```python
        @pytest.mark.containers
        def test_compose_cluster(self, ray_compose_cluster: RayComposeCluster):
            ray_compose_cluster.scale_workers(2)
            services = ray_compose_cluster.get_services()
            assert len(services) >= 2
        ```
    """
    from python_on_whales import DockerClient

    compose_file = Path(__file__).parent / 'docker-compose.ray.yml'
    if not compose_file.exists():
        pytest.skip(f'Compose file not found: {compose_file}')

    project_name = f'ray_test{unique_name}'.replace('_', '')
    ray_image = _get_ray_image()

    os.environ['RAY_IMAGE'] = ray_image

    docker = DockerClient(
        compose_files=[compose_file],
        compose_project_name=project_name,
        compose_env_file=None,
    )

    try:
        docker.compose.up(
            detach=True,
            wait=True,
        )

        yield RayComposeCluster(
            project_name=project_name,
            compose_file=compose_file,
            ray_image=ray_image,
            _docker=docker,
        )

    except Exception as e:
        pytest.skip(f'Compose cluster setup failed: {e}')

    finally:
        try:
            docker.compose.down(volumes=True, remove_orphans=True)
        except Exception:
            pass


# =============================================================================
# Approach 3: Docker Swarm + Stack (Realistic distributed testing)
# =============================================================================


@dataclass
class RaySwarmCluster:
    """Ray cluster deployed as a Docker Swarm stack.

    Uses overlay networks for true distributed service discovery.
    Provides production-like orchestration with service scaling.

    Example:
        ```python
        @pytest.mark.containers
        @pytest.mark.swarm
        def test_swarm_cluster(self, ray_swarm_cluster: RaySwarmCluster):
            ray_swarm_cluster.scale_workers(3)
            tasks = ray_swarm_cluster.get_tasks()
            assert len([t for t in tasks if 'worker' in t.service_id]) == 3
        ```
    """

    stack_name: str
    compose_file: Path
    ray_image: str
    _docker: DockerClient = field(repr=False)

    @property
    def head_address(self) -> str:
        """Ray client address for connecting to the cluster."""
        return 'ray://ray-head:10001'

    def scale_workers(self, count: int) -> None:
        """Scale worker service replicas.

        Args:
            count: Number of worker replicas
        """
        service_name = f'{self.stack_name}_ray-worker'
        self._docker.service.scale({service_name: count})

    def get_services(self) -> list:
        """Get all services in the stack."""
        return self._docker.stack.services(self.stack_name)

    def get_tasks(self) -> list:
        """Get all tasks (containers) running in the stack."""
        return self._docker.stack.ps(self.stack_name)

    def wait_for_convergence(self, timeout: int = 60) -> bool:
        """Wait for all services to reach desired state.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if converged, False if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            tasks = self.get_tasks()
            all_running = all(t.desired_state == 'running' and t.status.state == 'running' for t in tasks)
            if all_running and len(tasks) > 0:
                return True
            time.sleep(2)
        return False

    def run_script(self, script: str) -> str:
        """Run a Python script against the cluster.

        Note: In Swarm mode, scripts run inside the existing head container.

        Args:
            script: Python code to execute

        Returns:
            Output from script execution
        """
        full_script = f"""
import ray
ray.init(address='{self.head_address}')
{script}
ray.shutdown()
"""
        tasks = self.get_tasks()
        head_task = next((t for t in tasks if 'head' in str(t.service_id)), None)
        if not head_task or not head_task.status.container_status:
            raise RuntimeError('Head container not found')

        container_id = head_task.status.container_status.container_id
        result = self._docker.execute(container_id, ['python', '-c', full_script])
        return str(result) if result else ''

    def get_node_distribution(self) -> dict[str, int]:
        """Get count of tasks per node.

        Returns:
            Dict mapping node_id to task count
        """
        distribution: dict[str, int] = {}
        for task in self.get_tasks():
            node_id = task.node_id or 'unknown'
            distribution[node_id] = distribution.get(node_id, 0) + 1
        return distribution


@pytest.fixture
def ray_swarm_cluster(unique_name: str) -> Generator[RaySwarmCluster]:
    """Deploy a Ray cluster as a Docker Swarm stack.

    Requires Docker Swarm to be initialized. Uses overlay networks
    for proper distributed service discovery.

    Example:
        ```python
        @pytest.mark.containers
        @pytest.mark.swarm
        def test_swarm_scaling(self, ray_swarm_cluster: RaySwarmCluster):
            ray_swarm_cluster.scale_workers(2)
            ray_swarm_cluster.wait_for_convergence()
            tasks = ray_swarm_cluster.get_tasks()
            worker_tasks = [t for t in tasks if 'worker' in str(t.service_id)]
            assert len(worker_tasks) == 2
        ```
    """
    from python_on_whales import DockerClient

    docker = DockerClient()
    compose_file = Path(__file__).parent / 'docker-compose.ray.yml'
    if not compose_file.exists():
        pytest.skip(f'Compose file not found: {compose_file}')

    stack_name = f'raytest{unique_name}'.replace('_', '')
    ray_image = _get_ray_image()

    swarm_initialized = False
    try:
        info = docker.system.info()
        swarm_info = info.swarm
        if swarm_info is None or swarm_info.local_node_state == 'inactive':
            docker.swarm.init(advertise_address='127.0.0.1')
            swarm_initialized = True
    except Exception as e:
        pytest.skip(f'Docker Swarm not available: {e}')

    os.environ['RAY_IMAGE'] = ray_image

    try:
        docker.stack.deploy(
            stack_name,
            compose_files=[compose_file],
        )

        cluster = RaySwarmCluster(
            stack_name=stack_name,
            compose_file=compose_file,
            ray_image=ray_image,
            _docker=docker,
        )

        if not cluster.wait_for_convergence(timeout=60):
            pytest.skip('Swarm stack failed to converge')

        yield cluster

    except Exception as e:
        pytest.skip(f'Swarm cluster setup failed: {e}')

    finally:
        try:
            docker.stack.remove(stack_name)
            time.sleep(2)
        except Exception:
            pass

        if swarm_initialized:
            try:
                docker.swarm.leave(force=True)
            except Exception:
                pass


# =============================================================================
# Approach 4: Docker Contexts (Multi-host testing)
# =============================================================================


@dataclass
class DockerContextConfig:
    """Configuration for a Docker context endpoint."""

    name: str
    host: str
    description: str = ''
    tls_verify: bool = False
    cert_path: str | None = None


@dataclass
class MultiHostRayCluster:
    """Ray cluster spanning multiple Docker hosts via contexts.

    Enables testing across multiple Docker daemons (local, remote, SSH).

    Example:
        ```python
        @pytest.mark.containers
        @pytest.mark.multihost
        def test_multihost(self, multihost_ray_cluster: MultiHostRayCluster):
            multihost_ray_cluster.add_worker_on_host("worker-host")
            # Tests distributed behavior across hosts
        ```
    """

    contexts: dict[str, DockerClient] = field(default_factory=dict)
    head_context: str = ''
    head_address: str = ''
    ray_image: str = ''
    _primary_docker: DockerClient = field(default=None, repr=False)  # type: ignore[assignment]

    def add_context(self, config: DockerContextConfig) -> None:
        """Add a Docker context for a remote host.

        Args:
            config: Context configuration with host details
        """
        from python_on_whales import DockerClient

        self._primary_docker.context.create(
            config.name,
            docker={'host': config.host},
            description=config.description,
        )
        self.contexts[config.name] = DockerClient(context=config.name)

    def add_worker_on_host(
        self,
        context_name: str,
        *,
        num_cpus: int = 2,
        worker_name: str | None = None,
    ) -> Container:
        """Add a Ray worker on a specific host.

        Args:
            context_name: Name of the Docker context/host
            num_cpus: CPUs for the worker
            worker_name: Optional worker container name

        Returns:
            The created worker container
        """
        if context_name not in self.contexts:
            raise ValueError(f'Unknown context: {context_name}')

        docker = self.contexts[context_name]
        name = worker_name or f'ray_worker_{context_name}'

        return docker.run(
            self.ray_image,
            [
                'ray',
                'start',
                f'--address={self.head_address}',
                f'--num-cpus={num_cpus}',
                '--block',
            ],
            name=name,
            detach=True,
            cpus=float(num_cpus),
        )

    def list_contexts(self) -> list[str]:
        """List all available Docker contexts."""
        return list(self.contexts.keys())

    def cleanup_context(self, context_name: str) -> None:
        """Remove a Docker context.

        Args:
            context_name: Name of context to remove
        """
        if context_name in self.contexts:
            del self.contexts[context_name]
            try:
                self._primary_docker.context.remove(context_name)
            except Exception:
                pass


@pytest.fixture
def multihost_ray_cluster(unique_name: str) -> Generator[MultiHostRayCluster]:
    """Create a Ray cluster that can span multiple Docker hosts.

    Requires KLAW_DOCKER_HOSTS env var with comma-separated host URIs.
    Format: "ssh://user@host1,tcp://host2:2375"

    Example:
        ```python
        @pytest.mark.containers
        @pytest.mark.multihost
        def test_cross_host(self, multihost_ray_cluster: MultiHostRayCluster):
            # Add workers on different hosts
            for ctx in multihost_ray_cluster.list_contexts():
                multihost_ray_cluster.add_worker_on_host(ctx)
        ```
    """
    from python_on_whales import DockerClient

    hosts_env = os.environ.get('KLAW_DOCKER_HOSTS', '')
    if not hosts_env:
        pytest.skip('KLAW_DOCKER_HOSTS not set for multi-host testing')

    docker = DockerClient()
    ray_image = _get_ray_image()
    network_name = f'ray_multihost{unique_name}'
    head_name = f'ray_head_multihost{unique_name}'
    created_contexts: list[str] = []

    try:
        with docker.network.create(network_name):
            with docker.run(
                ray_image,
                ['ray', 'start', '--head', '--port=6379', '--num-cpus=2', '--block'],
                name=head_name,
                networks=[network_name],
                detach=True,
                cpus=2.0,
            ):
                if not _wait_for_ray_head(docker, head_name):
                    pytest.skip('Ray head node failed to start')

                cluster = MultiHostRayCluster(
                    head_context='default',
                    head_address=f'{head_name}:6379',
                    ray_image=ray_image,
                    _primary_docker=docker,
                )

                hosts = [h.strip() for h in hosts_env.split(',') if h.strip()]
                for i, host in enumerate(hosts):
                    ctx_name = f'remote_{i}{unique_name}'
                    cluster.add_context(
                        DockerContextConfig(
                            name=ctx_name,
                            host=host,
                            description=f'Remote Docker host {i}',
                        )
                    )
                    created_contexts.append(ctx_name)

                yield cluster

    except Exception as e:
        pytest.skip(f'Multi-host cluster setup failed: {e}')

    finally:
        for ctx_name in created_contexts:
            try:
                docker.context.remove(ctx_name)
            except Exception:
                pass
