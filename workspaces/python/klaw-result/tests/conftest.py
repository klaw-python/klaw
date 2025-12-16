"""Pytest configuration and shared fixtures for klaw-result tests."""

import pytest


@pytest.fixture
def sample_ok():
    """Sample Ok value for testing."""
    from klaw_result import Ok

    return Ok(42)


@pytest.fixture
def sample_err():
    """Sample Err value for testing."""
    from klaw_result import Err

    return Err(ValueError("test error"))


@pytest.fixture
def sample_some():
    """Sample Some value for testing."""
    from klaw_result import Some

    return Some("hello")


@pytest.fixture
def sample_nothing():
    """Sample Nothing value for testing."""
    from klaw_result import Nothing

    return Nothing
