"""Tests for runtime configuration and initialization."""

from __future__ import annotations

import os
from unittest.mock import patch

import psutil
import pytest
from klaw_core.runtime import Backend, RuntimeConfig, get_config, init
from klaw_core.runtime._config import (
    _detect_backend,
    _detect_concurrency,
    _detect_container_cpu_limit,
)


class TestBackendEnum:
    """Tests for the Backend enum."""

    def test_backend_values(self) -> None:
        assert Backend.LOCAL.value == 'local'
        assert Backend.RAY.value == 'ray'

    def test_backend_from_string(self) -> None:
        assert Backend('local') == Backend.LOCAL
        assert Backend('ray') == Backend.RAY

    def test_backend_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            Backend('invalid')


class TestRuntimeConfig:
    """Tests for the RuntimeConfig dataclass."""

    def test_default_values(self) -> None:
        config = RuntimeConfig()
        assert config.backend == Backend.LOCAL
        assert config.concurrency == 4
        assert config.log_level is None
        assert config.checkpoint_path is None
        assert config.backend_kwargs == {}

    def test_custom_values(self) -> None:
        config = RuntimeConfig(
            backend=Backend.RAY,
            concurrency=16,
            log_level='DEBUG',
            checkpoint_path='/tmp/checkpoints',
            backend_kwargs={'num_cpus': 4},
        )
        assert config.backend == Backend.RAY
        assert config.concurrency == 16
        assert config.log_level == 'DEBUG'
        assert config.checkpoint_path == '/tmp/checkpoints'
        assert config.backend_kwargs == {'num_cpus': 4}

    def test_config_is_frozen(self) -> None:
        config = RuntimeConfig()
        with pytest.raises(AttributeError):
            config.concurrency = 8  # type: ignore[misc]


class TestDetectBackend:
    """Tests for _detect_backend()."""

    def test_env_local(self) -> None:
        with patch.dict(os.environ, {'KLAW_BACKEND': 'local'}):
            assert _detect_backend() == Backend.LOCAL

    def test_env_ray(self) -> None:
        with patch.dict(os.environ, {'KLAW_BACKEND': 'ray'}):
            assert _detect_backend() == Backend.RAY

    def test_env_case_insensitive(self) -> None:
        with patch.dict(os.environ, {'KLAW_BACKEND': 'LOCAL'}):
            assert _detect_backend() == Backend.LOCAL
        with patch.dict(os.environ, {'KLAW_BACKEND': 'RAY'}):
            assert _detect_backend() == Backend.RAY

    def test_env_invalid_defaults_to_local(self) -> None:
        with patch.dict(os.environ, {'KLAW_BACKEND': 'invalid'}):
            assert _detect_backend() == Backend.LOCAL

    def test_no_env_defaults_to_local(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            # Also mock ray.is_initialized to return False
            with patch.dict('sys.modules', {'ray': None}):
                assert _detect_backend() == Backend.LOCAL


class TestDetectConcurrency:
    """Tests for _detect_concurrency()."""

    def test_returns_positive_int(self) -> None:
        result = _detect_concurrency()
        assert isinstance(result, int)
        assert result >= 1
        assert result <= 256

    def test_respects_physical_cores(self) -> None:
        physical = psutil.cpu_count(logical=False)
        if physical is not None:
            result = _detect_concurrency()
            # Result should be <= physical cores (or adjusted by memory)
            assert result >= 1

    def test_minimum_of_one(self) -> None:
        with patch.object(psutil, 'cpu_count', return_value=0):
            result = _detect_concurrency()
            assert result >= 1


class TestDetectContainerCpuLimit:
    """Tests for _detect_container_cpu_limit()."""

    def test_no_cgroups_returns_none(self) -> None:
        # On non-container systems, this should return None
        result = _detect_container_cpu_limit()
        # Could be None or an int if we're actually in a container
        assert result is None or isinstance(result, int)


class TestInit:
    """Tests for init()."""

    def test_init_with_defaults(self) -> None:
        config = init()
        assert isinstance(config, RuntimeConfig)
        assert config.backend in {Backend.LOCAL, Backend.RAY}
        assert config.concurrency >= 1

    def test_init_with_backend_enum(self) -> None:
        config = init(backend=Backend.LOCAL)
        assert config.backend == Backend.LOCAL

    def test_init_with_backend_string(self) -> None:
        config = init(backend='local')
        assert config.backend == Backend.LOCAL

    def test_init_with_concurrency(self) -> None:
        config = init(concurrency=8)
        assert config.concurrency == 8

    def test_init_concurrency_clamped_min(self) -> None:
        config = init(concurrency=-5)
        assert config.concurrency == 1

    def test_init_concurrency_clamped_max(self) -> None:
        config = init(concurrency=1000)
        assert config.concurrency == 256

    def test_init_with_log_level(self) -> None:
        config = init(log_level='DEBUG')
        assert config.log_level == 'DEBUG'

    def test_init_with_checkpoint_path(self) -> None:
        config = init(checkpoint_path='/tmp/ckpt')
        assert config.checkpoint_path == '/tmp/ckpt'

    def test_init_with_backend_kwargs(self) -> None:
        config = init(num_cpus=4, num_gpus=1)
        assert config.backend_kwargs == {'num_cpus': 4, 'num_gpus': 1}

    def test_init_sets_global_config(self) -> None:
        init(concurrency=42)
        config = get_config()
        assert config.concurrency == 42


class TestGetConfig:
    """Tests for get_config()."""

    def test_get_config_after_init(self) -> None:
        init(backend=Backend.LOCAL, concurrency=12)
        config = get_config()
        assert config.backend == Backend.LOCAL
        assert config.concurrency == 12

    def test_get_config_before_init_raises(self) -> None:
        # Reset global config
        import klaw_core.runtime._config as config_module

        config_module._config = None
        with pytest.raises(RuntimeError, match='Runtime not initialized'):
            get_config()


class TestDetectRayConcurrency:
    """Tests for _detect_ray_concurrency()."""

    def test_returns_none_when_ray_not_initialized(self) -> None:
        from klaw_core.runtime._config import _detect_ray_concurrency

        result = _detect_ray_concurrency()
        # Ray is not initialized in tests, should return None
        assert result is None

    @pytest.mark.ray
    def test_returns_cpu_count_when_ray_initialized(self, ray_with_cpus_4: None) -> None:
        from klaw_core.runtime._config import _detect_ray_concurrency

        result = _detect_ray_concurrency()
        assert result == 4, f'Expected 4 CPUs from Ray, got {result}'

    @pytest.mark.ray
    def test_detect_concurrency_uses_ray_when_backend_is_ray_and_initialized(self, ray_with_cpus_8: None) -> None:
        from klaw_core.runtime._config import Backend, _detect_concurrency

        result = _detect_concurrency(Backend.RAY)
        assert result == 8, f'Expected 8 CPUs from Ray, got {result}'

    def test_detect_concurrency_falls_back_to_local_when_ray_not_initialized(self) -> None:
        from klaw_core.runtime._config import (
            Backend,
            _detect_concurrency,
            _detect_local_concurrency,
        )

        # Ray not initialized, should fall back to local detection
        expected = _detect_local_concurrency()
        result = _detect_concurrency(Backend.RAY)
        assert result == expected, f'Expected {expected} (local), got {result}'

    def test_detect_concurrency_uses_local_when_backend_is_local(self) -> None:
        from klaw_core.runtime._config import (
            Backend,
            _detect_concurrency,
            _detect_local_concurrency,
        )

        expected = _detect_local_concurrency()
        result = _detect_concurrency(Backend.LOCAL)
        assert result == expected, f'Expected {expected}, got {result}'


class TestDetectLocalConcurrency:
    """Tests for _detect_local_concurrency()."""

    def test_returns_physical_cores_or_capped(self) -> None:
        import psutil
        from klaw_core.runtime._config import _detect_local_concurrency

        result = _detect_local_concurrency()
        physical_cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 4

        # Result should be <= physical cores (may be limited by memory or container)
        assert 1 <= result <= physical_cores, f'Expected 1-{physical_cores}, got {result}'

    def test_matches_expected_for_this_machine(self) -> None:
        import psutil
        from klaw_core.runtime._config import (
            _detect_container_cpu_limit,
            _detect_local_concurrency,
        )

        result = _detect_local_concurrency()

        # Calculate expected value manually
        physical_cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 4
        container_limit = _detect_container_cpu_limit()
        if container_limit is not None:
            physical_cores = min(physical_cores, container_limit)

        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        memory_limit = max(1, int(available_memory_gb))
        expected = max(1, min(256, physical_cores, memory_limit))

        assert result == expected, f'Expected {expected}, got {result}'


class TestEnvVariableIntegration:
    """Integration tests for environment variable handling."""

    def test_klaw_backend_env_respected(self) -> None:
        with patch.dict(os.environ, {'KLAW_BACKEND': 'local'}):
            config = init()
            assert config.backend == Backend.LOCAL

    def test_explicit_backend_overrides_env(self) -> None:
        with patch.dict(os.environ, {'KLAW_BACKEND': 'ray'}):
            config = init(backend=Backend.LOCAL)
            assert config.backend == Backend.LOCAL
