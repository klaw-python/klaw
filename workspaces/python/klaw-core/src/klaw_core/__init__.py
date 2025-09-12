"""Klaw Core - Foundation utilities and types for the Klaw ecosystem.

This package provides the core functionality and types that form the foundation
of the Klaw ecosystem. It includes basic utilities, type definitions, and
common patterns used across all Klaw packages.
"""

from __future__ import annotations

import klaw_core._another_module as another_module
import klaw_core._core as core

__all__ = [
    'another_module',
    'core',
]


def hello() -> str:
    """Return a greeting from klaw-core.

    This is a simple example function that demonstrates the basic
    functionality of the klaw-core package.

    Returns:
        A greeting string from klaw-core.

    Example:
        ```python
        from klaw_core import hello

        result = hello()
        print(result)  # Hello from klaw-core!
        ```
    """
    return 'Hello from klaw-core!'
