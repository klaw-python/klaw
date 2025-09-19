"""Core utilities and foundational types for the Klaw ecosystem.

This module provides the fundamental building blocks that other Klaw packages
depend on. It includes basic utilities, type definitions, and common patterns
used throughout the ecosystem.
"""

from __future__ import annotations

from typing import Any, Self, TypeVar

T = TypeVar('T')
"""Generic type variable for type annotations.
    Note:
        This type variable is used to annotate functions that can return a value of
        any type, such as functions that return a result or a list of values.
        It is used to ensure that the return type of a function is consistent
        across the codebase.

"""


E = TypeVar('E')
"""Generic type variable for exception types.
    Note:
        This type variable is used to annotate functions that can raise exceptions.
        It is used to ensure that the exception type of a function is consistent
        across the codebase.
"""


class KlawError(Exception):
    """Base exception class for Klaw-related errors.

    This is the root exception that all Klaw-specific exceptions should inherit from.
    It provides a consistent error handling interface across the ecosystem.

    Attributes:
        message (str): A human-readable description of the error.
        code (str | None): An optional error code for programmatic error handling.

    Example:
        ```python
        from klaw_core import KlawError

        try:
            # Some operation that might fail
            pass
        except KlawError as e:
            print(f"Klaw error occurred: {e}")
        ```
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        """Initialize a KlawError.

        Args:
            message (str): A human-readable description of the error.
            code (str | None): An optional error code for programmatic error handling.

        Returns:
            None
        """
        super().__init__(message)
        self.message: str = message
        self.code: str | None = code

    def __str__(self) -> str:
        """Return a string representation of the error."""
        if self.code:
            return f'[{self.code}] {self.message}'
        return self.message


def safe_get[T](data: dict[str, Any], key: str, default: T | None = None) -> T | Any:
    """Safely retrieve a value from a dictionary.

    This function provides a type-safe way to access dictionary values with
    optional default values. It's designed to work well with static type checkers,
    encoding behavioral contracts as described in modern generics patterns.

    Args:
        data (dict[str, Any]): The dictionary to retrieve the value from.
        key (str): The key to look up in the dictionary.
        default (T | None): The default value to return if the key is not found.

    Returns:
        The value associated with the key, or the default value if the key
        is not present in the dictionary.

    Raises:
        KeyError: If the key is not found and no default is provided.

    Example:
        ```python
        from klaw_core import safe_get

        data = {"name": "Alice", "age": 30}

        # Safe access with default
        name = safe_get(data, "name", "Unknown")
        city = safe_get(data, "city", "Unknown")

        # Will raise KeyError if key doesn't exist and no default
        try:
            missing = safe_get(data, "missing_key")
        except KeyError:
            print("Key not found")
        ```
    """
    if key in data:
        return data[key]
    if default is not None:
        return default
    raise KeyError(f"Key '{key}' not found in data")


def validate_type[T](value: Any, expected_type: type[T]) -> T:
    """Validate that a value is of the expected type.

    This function performs runtime type checking and raises a descriptive
    error if the validation fails. It's particularly useful for validating
    function arguments and return values, ensuring type contracts are enforced.

    Args:
        value (Any): The value to validate.
        expected_type (type[T]): The expected type of the value.

    Returns:
        The validated value (unchanged if validation passes).

    Raises:
        TypeError: If the value is not of the expected type.

    Example:
        ```python
        from klaw_core import validate_type

        def process_number(n: int) -> int:
            validated_n = validate_type(n, int)
            return validated_n * 2

        result = process_number(5)  # Works fine
        # result = process_number("5")  # Raises TypeError
        ```
    """
    if not isinstance(value, expected_type):
        raise TypeError(f'Expected value of type {expected_type.__name__}, got {type(value).__name__}: {value!r}')
    return value


class Result[T, E]:
    """A container for operations that may succeed or fail.

    This class represents the result of an operation that can either succeed
    with a value or fail with an error. It's inspired by functional programming
    patterns and provides a type-safe way to handle operations that might fail,
    as outlined in modern generics approaches. It uses two type variables to
    track success and error types separately.

    Attributes:
        _value (T | None): The success value (if operation succeeded).
        _error (E | None): The error value (if operation failed).

    Example:
        ```python
        from klaw_core import Result

        def divide(a: float, b: float) -> Result[float, str]:
            if b == 0:
                return Result(error="Division by zero")
            return Result(value=a / b)

        result = divide(10, 2)
        if result.ok():
            print(f"Result: {result.unwrap()}")
        else:
            print(f"Error: {result.unwrap_err()}")

        # Error case
        error_result = divide(10, 0)
        print(f"Error: {error_result.unwrap_err()}")
        ```

    ??? note "A few notes about Result"
        This class is inspired by functional programming patterns and provides a type-safe way to handle operations that might fail,
        as outlined in modern generics approaches. It uses two type variables to track success and error types separately.

    ??? abstract
        Some other notes about this class

    ??? info "Useful things"
        - This is a useful thing

    ??? tip "Useful tips"
        - This is a useful tip

    ??? success "Success"
        - This is a success

    ??? question "Question"
        - This is a question

    ??? warning "Warning"
        - This is a warning

    ??? failure "Failure"
        - This is a failure

    ??? danger "Danger"
        - This is a danger

    ??? bug "Bug"
        - This is a bug

    ??? quote "Quote"
        - This is a quote
    """

    def __init__(self, value: T | None = None, error: E | None = None) -> None:
        """Initialize a Result. Use Result.success() or Result.error() instead."""
        if (value is not None) and (error is not None):
            raise ValueError('Result cannot have both a value and an error')
        if (value is None) and (error is None):
            raise ValueError('Result must have either a value or an error')

        self._value = value
        self._error = error

    @classmethod
    def success(cls, value: T) -> Self:
        """Create a successful result with a value.

        Args:
            value: The success value.

        Returns:
            A Result representing a successful operation.
        """
        return cls(value=value)

    @classmethod
    def error(cls, error: E) -> Result[T, E]:
        """Create a failed result with an error.

        Args:
            error: A description of what went wrong.

        Returns:
            A Result representing a failed operation.
        """
        return cls(error=error)

    def ok(self) -> bool:
        """Check if the result represents a successful operation."""
        return self._error is None

    def err(self) -> bool:
        """Check if the result represents a failed operation."""
        return self._value is None

    def unwrap(self) -> T:
        """Get the success value. Raises an exception if the result is an error."""
        if self._value is not None:
            return self._value
        raise RuntimeError(f'Tried to unwrap Result error: {self._error}')

    def unwrap_err(self) -> E:
        """Get the error value. Raises an exception if the result is a success."""
        if self._error is not None:
            return self._error
        raise RuntimeError(f'Expected error, found value: {self._value}')

    # Legacy properties for backward compatibility (removed conflicting 'error' property)
    @property
    def is_success(self) -> bool:
        """Check if the result represents a successful operation (legacy alias for ok())."""
        return self.ok()

    @property
    def value(self) -> T:
        """Get the success value (legacy alias for unwrap())."""
        return self.unwrap()

    def __repr__(self) -> str:
        """Return a string representation of the result."""
        if self.ok():
            return f'Result.success({self._value!r})'
        return f'Result.error({self._error!r})'
