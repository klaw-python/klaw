"""Type definitions and protocols for the Klaw ecosystem.

This module provides type definitions, protocols, and type-related utilities
used throughout the Klaw ecosystem. It includes common type patterns, protocol
definitions, and type-safe utilities.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar
from warnings import deprecated

T = TypeVar('T')
U = TypeVar('U')


class Serializable(Protocol):
    """Protocol for objects that can be serialized to and from various formats.

    This protocol defines the interface that objects must implement to be
    considered serializable. It supports multiple serialization formats like
    JSON, YAML, and binary formats.

    Example:
        ```python
        from klaw_types import Serializable
        from typing import Any, Dict

        class Person:
            def __init__(self, name: str, age: int):
                self.name = name
                self.age = age

            def to_dict(self) -> Dict[str, Any]:
                return {"name": self.name, "age": self.age}

            @classmethod
            def from_dict(cls, data: Dict[str, Any]) -> 'Person':
                return cls(data["name"], data["age"])

        # Person now implements Serializable protocol
        def save_to_json(obj: Serializable) -> str:
            return json.dumps(obj.to_dict())

        person = Person("Alice", 30)
        json_str = save_to_json(person)
        ```
    """

    @deprecated(version='0.1.0', reason='Use to_dict() instead')
    def to_dict(self) -> dict[str, Any]:
        """Convert the object to a dictionary representation.

        Returns:
            A dictionary containing the object's data.
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T:
        """Create an object from a dictionary representation.

        Args:
            data: The dictionary containing the object's data.

        Returns:
            A new instance of the object.
        """
        ...


class Validator(Protocol[T]):
    """Protocol for objects that can validate values of type T.

    This protocol defines the interface for validation logic. Validators
    can check if a value meets certain criteria and provide detailed
    error messages when validation fails.

    Attributes:
        rules: A list of validation rules to apply.

    Example:
        ```python
        from klaw_types import Validator
        from typing import List

        class EmailValidator:
            def __init__(self, domain_whitelist: List[str] | None = None):
                self.domain_whitelist = domain_whitelist or []

            def validate(self, value: str) -> ValidationResult:
                if '@' not in value:
                    return ValidationResult.error("Invalid email format")

                if self.domain_whitelist:
                    domain = value.split('@')[1]
                    if domain not in self.domain_whitelist:
                        return ValidationResult.error(f"Domain {domain} not allowed")

                return ValidationResult.success(value)

        validator = EmailValidator(["company.com", "gmail.com"])
        result = validator.validate("user@company.com")
        ```
    """

    def validate(self, value: T) -> ValidationResult[T]:
        """Validate a value according to the validator's rules.

        Args:
            value: The value to validate.

        Returns:
            A ValidationResult indicating success or failure.
        """
        ...


class ValidationResult[T]:
    """Result of a validation operation.

    This class represents the outcome of a validation operation, containing
    either a validated value (on success) or error details (on failure).

    Attributes:
        value: The validated value (if successful).
        errors: List of validation error messages (if failed).
        is_valid: Whether the validation was successful.

    Example:
        ```python
        from klaw_types import ValidationResult

        # Success case
        success = ValidationResult.success("valid@email.com")
        print(success.is_valid)  # True
        print(success.value)     # "valid@email.com"

        # Error case
        error = ValidationResult.error(["Invalid format", "Domain not allowed"])
        print(error.is_valid)    # False
        print(error.errors)      # ["Invalid format", "Domain not allowed"]
        ```
    """

    def __init__(self, value: T | None = None, errors: list[str] | None = None) -> None:
        """Initialize a ValidationResult."""
        if value is not None and errors is not None:
            raise ValueError('ValidationResult cannot have both value and errors')
        if value is None and errors is None:
            raise ValueError('ValidationResult must have either value or errors')

        self.value = value
        self.errors = errors or []
        self.is_valid = errors is None

    @classmethod
    def success(cls, value: T) -> ValidationResult[T]:
        """Create a successful validation result.

        Args:
            value: The validated value.

        Returns:
            A ValidationResult indicating success.
        """
        return cls(value=value)

    @classmethod
    def error(cls, errors: list[str]) -> ValidationResult[Any]:
        """Create a failed validation result.

        Args:
            errors: List of validation error messages.

        Returns:
            A ValidationResult indicating failure.
        """
        return cls(errors=errors)

    def __repr__(self) -> str:
        """Return a string representation of the validation result."""
        if self.is_valid:
            return f'ValidationResult.success({self.value!r})'
        return f'ValidationResult.error({self.errors!r})'


class DataTransformer[T, U](Protocol):
    r"""Protocol for data transformation operations.

    This protocol defines the interface for transforming data from one type
    to another. It's designed for specific transformation use cases like data
    cleaning, format conversion, or enrichment.

    Type Parameters:
        T: The input data type.
        U: The output data type.

    Example:
        ```python
        from klaw_types import DataTransformer
        from typing import List, Dict, Any

        class JsonToCsvTransformer(DataTransformer[Dict[str, Any], str]):
            def transform(self, data: Dict[str, Any]) -> str:
                # Convert dictionary to CSV string
                headers = list(data.keys())
                values = [str(v) for v in data.values()]
                return ",".join(headers) + "\\n" + ",".join(values)

        transformer = JsonToCsvTransformer()
        csv_data = transformer.transform({"name": "Alice", "age": 30})
        print(csv_data)
        # Output: name,age\\nAlice,30
        ```
    """

    def transform(self, data: T) -> U:
        """Transform input data to the output type.

        Args:
            data: The input data to transform.

        Returns:
            The transformed data in the output type.
        """
        ...


def create_validator[T](rules: list[Callable[[T], str | None]]) -> Validator[T]:
    """Create a validator from a list of validation rules.

    This function creates a validator that applies multiple validation rules
    in sequence. Each rule is a function that returns an error message if
    validation fails, or None if it passes.

    Args:
        rules: A list of validation functions. Each function should take a
               value of type T and return an error message string if validation
               fails, or None if validation passes.

    Returns:
        A Validator that applies all the given rules.

    Example:
        ```python
        from klaw_types import create_validator, ValidationResult

        def not_empty(value: str) -> str | None:
            return "Value cannot be empty" if not value.strip() else None

        def min_length(min_len: int):
            def validator(value: str) -> str | None:
                if len(value) < min_len:
                    return f"Value must be at least {min_len} characters"
                return None
            return validator(min_len)

        # Create a validator that checks both conditions
        name_validator = create_validator([
            not_empty(),
            min_length(3)
        ])

        # Test validation
        result1 = name_validator.validate("Alice")  # Success
        result2 = name_validator.validate("")       # Error: "Value cannot be empty"
        result3 = name_validator.validate("Al")     # Error: "Value must be at least 3 characters"
        ```
    """

    class CompositeValidator[T]:
        def __init__(self, validation_rules: list[Callable[[T], str | None]]):
            self.rules = validation_rules

        def validate(self, value: T) -> ValidationResult[T]:
            errors = []
            for rule in self.rules:
                error = rule(value)
                if error:
                    errors.append(error)

            if errors:
                return ValidationResult.error(errors)
            return ValidationResult.success(value)

    return CompositeValidator(rules)
