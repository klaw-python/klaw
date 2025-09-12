"""Data validation utilities for the Klaw ecosystem.

This module provides validation functions and classes to ensure data integrity
and type safety across Klaw applications. It includes runtime type checking,
schema validation, and common validation patterns.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from klaw_core._core import KlawError

T = TypeVar('T')
"""Generic type variable for validated values."""

V = TypeVar('V')
"""Generic type variable for validator functions."""


class ValidationError(KlawError):
    """Exception raised when data validation fails.

    This exception provides detailed information about validation failures,
    including the field that failed validation and the expected vs actual values.

    Attributes:
        field (str): The name of the field that failed validation.
        expected (str): A description of the expected value.
        actual (Any): The actual value that was provided.

    Example:
        ```python
        from klaw_core.another_module import ValidationError

        try:
            validate_string("age", 25)
        except ValidationError as e:
            print(f"Validation failed for {e.field}: expected {e.expected}, got {e.actual}")
        ```
    """

    def __init__(self, field: str, expected: str, actual: Any) -> None:
        """Initialize a ValidationError.

        Args:
            field (str): The name of the field that failed validation.
            expected (str): A description of the expected value.
            actual (Any): The actual value that was provided.
        """
        message = f"Validation failed for field '{field}': expected {expected}, got {actual!r}"
        super().__init__(message, code='VALIDATION_ERROR')
        self.field: str = field
        self.expected: str = expected
        self.actual: Any = actual


def validate_string(field: str, value: Any, min_length: int = 0, max_length: int | None = None) -> str:
    """Validate that a value is a string with optional length constraints.

    Args:
        field (str): The name of the field being validated.
        value (Any): The value to validate.
        min_length (int): Minimum allowed length (default: 0).
        max_length (int | None): Maximum allowed length (default: None for no limit).

    Returns:
        str: The validated string value.

    Raises:
        ValidationError: If validation fails.

    Example:
        ```python
        from klaw_core.another_module import validate_string

        name = validate_string("name", "Alice", min_length=1, max_length=50)
        ```
    """
    if not isinstance(value, str):
        raise ValidationError(field, 'string', value)

    if len(value) < min_length:
        raise ValidationError(field, f'string with minimum length {min_length}', value)

    if max_length is not None and len(value) > max_length:
        raise ValidationError(field, f'string with maximum length {max_length}', value)

    return value


def validate_number(field: str, value: Any, min_value: float | None = None, max_value: float | None = None) -> float:
    """Validate that a value is a number with optional range constraints.

    Args:
        field (str): The name of the field being validated.
        value (Any): The value to validate.
        min_value (float | None): Minimum allowed value (default: None).
        max_value (float | None): Maximum allowed value (default: None).

    Returns:
        float: The validated numeric value.

    Raises:
        ValidationError: If validation fails.

    Example:
        ```python
        from klaw_core.another_module import validate_number

        age = validate_number("age", 25, min_value=0, max_value=120)
        ```
    """
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        raise ValidationError(field, 'number', value)

    if min_value is not None and num_value < min_value:
        raise ValidationError(field, f'number >= {min_value}', value)

    if max_value is not None and num_value > max_value:
        raise ValidationError(field, f'number <= {max_value}', value)

    return num_value


class Validator[T]:
    """A configurable validator for data validation.

    This class allows building complex validation rules through method chaining
    and provides a fluent interface for data validation.

    Attributes:
        _field (str): The name of the field being validated.
        _validators (list[Callable[[Any], T]]): List of validation functions.

    Example:
        ```python
        from klaw_core.another_module import Validator

        validator = (Validator("email")
                    .is_string()
                    .min_length(5)
                    .max_length(100))

        try:
            result = validator.validate("user@example.com")
        except ValidationError:
            print("Validation failed")
        ```
    """

    def __init__(self, field: str) -> None:
        """Initialize a Validator.

        Args:
            field (str): The name of the field to validate.
        """
        self._field: str = field
        self._validators: list[Callable[[Any], T]] = []

    def is_string(self) -> Validator[str]:
        """Add a string type validation rule."""
        self._validators.append(lambda v: validate_string(self._field, v))
        return self  # type: ignore

    def min_length(self, length: int) -> Validator[str]:
        """Add a minimum length validation rule for strings."""
        self._validators.append(lambda v: validate_string(self._field, v, min_length=length))
        return self  # type: ignore

    def max_length(self, length: int) -> Validator[str]:
        """Add a maximum length validation rule for strings."""
        self._validators.append(lambda v: validate_string(self._field, v, max_length=length))
        return self  # type: ignore

    def is_number(self) -> Validator[float]:
        """Add a number type validation rule."""
        self._validators.append(lambda v: validate_number(self._field, v))
        return self  # type: ignore

    def min_value(self, value: float) -> Validator[float]:
        """Add a minimum value validation rule for numbers."""
        self._validators.append(lambda v: validate_number(self._field, v, min_value=value))
        return self  # type: ignore

    def max_value(self, value: float) -> Validator[float]:
        """Add a maximum value validation rule for numbers."""
        self._validators.append(lambda v: validate_number(self._field, v, max_value=value))
        return self  # type: ignore

    def validate(self, value: Any) -> T:
        """Validate a value against all configured rules.

        Args:
            value (Any): The value to validate.

        Returns:
            T: The validated value.

        Raises:
            ValidationError: If any validation rule fails.
        """
        result = value
        for validator in self._validators:
            result = validator(result)
        return result


__all__ = [
    'ValidationError',
    'Validator',
    'validate_number',
    'validate_string',
]
