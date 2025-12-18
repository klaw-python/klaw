"""Pytest configuration for runtime tests."""

from __future__ import annotations

import os

import pytest


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
