"""safe_assert and assert_result utilities.

Provides assertion utilities that work correctly with Result types:
- safe_assert: Always runs, even with python -O
- assert_result: Returns Result[None, E] based on condition
"""

from __future__ import annotations

from collections.abc import Callable
from typing import overload

from klaw_core.result import Err, Ok, Result

__all__ = ['assert_result', 'safe_assert']


def safe_assert(condition: bool, message: str = '') -> None:
    """Assert that works even in optimized mode (-O flag).

    Unlike the built-in assert, this always executes regardless of __debug__.
    Use this when assertions are part of your program logic, not just debugging.

    Args:
        condition: The condition to check.
        message: Optional error message if assertion fails.

    Raises:
        AssertionError: If condition is False.

    Example:
        ```python
        safe_assert(1 + 1 == 2)  # passes
        safe_assert(False, "This always fails")  # raises AssertionError
        ```
    """
    if not condition:
        raise AssertionError(message)


@overload
def assert_result[E](condition: bool, error: E) -> Result[None, E]: ...


@overload
def assert_result[E](condition: bool, error: Callable[[], E], *, lazy: bool = True) -> Result[None, E]: ...


def assert_result[E](
    condition: bool,
    error: E | Callable[[], E],
    *,
    lazy: bool = False,
) -> Result[None, E]:
    """Return Ok(None) if condition is True, else Err(error).

    This is useful for validation pipelines where you want to short-circuit
    on the first failed condition using Result's and_then or the @result decorator.

    Args:
        condition: The condition to check.
        error: The error value, or a callable that produces it (if lazy=True).
        lazy: If True, treat error as a callable and only invoke it on failure.

    Returns:
        Ok(None) if condition is True, Err(error) if False.

    Example:
        ```python
        assert_result(True, "error")
        # Ok(value=None)

        assert_result(False, "validation failed")
        # Err(error='validation failed')

        assert_result(False, lambda: ValueError("lazy error"), lazy=True)
        # Err(error=ValueError('lazy error'))

        # Use with and_then for validation chains:
        from klaw_core import Ok, result

        @result
        def validate_user(name: str, age: int):
            assert_result(len(name) > 0, "name required").bail()
            assert_result(age >= 0, "age must be non-negative").bail()
            return Ok({"name": name, "age": age})

        validate_user("Alice", 30)
        # Ok(value={'name': 'Alice', 'age': 30})

        validate_user("", 30)
        # Err(error='name required')
        ```
    """
    if condition:
        return Ok(None)

    if lazy and callable(error):
        return Err(error())  # type: ignore[return-value]
    return Err(error)  # type: ignore[arg-type]
