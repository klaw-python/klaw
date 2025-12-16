"""Deref mixin for forwarding attribute access to wrapped values.

Provides transparent delegation to the inner value while wrapping
results in Ok/Some to maintain Result/Option semantics.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from klaw_result.types.option import NothingType, Some
from klaw_result.types.result import Err, Ok

__all__ = ["Deref", "DerefOk", "DerefSome"]


def _is_result_or_option(value: object) -> bool:
    """Check if a value is already a Result or Option type."""
    return isinstance(value, Ok | Err | Some | NothingType)


class Deref:
    """Mixin that forwards attribute access to a wrapped value.

    This mixin provides Rust-like Deref behavior where accessing an
    attribute on a wrapper type transparently delegates to the inner value.
    Method calls on the inner value have their results wrapped in Ok/Some.

    Subclasses must define a `_deref_value` property that returns the
    inner value to delegate to.

    This is designed to be used with Result/Option wrapper types.
    """

    @property
    def _deref_value(self) -> Any:
        """Return the inner value to delegate attribute access to.

        Subclasses must implement this property.
        """
        raise NotImplementedError("Subclasses must implement _deref_value")

    @property
    def _deref_wrapper(self) -> type:
        """Return the wrapper type to use for results (Ok or Some).

        Subclasses must implement this property.
        """
        raise NotImplementedError("Subclasses must implement _deref_wrapper")

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the inner value.

        If the attribute is callable, returns a wrapper that calls the
        method and wraps the result in Ok/Some (unless it's already
        a Result/Option).
        """
        inner = self._deref_value
        attr = getattr(inner, name)

        if callable(attr):
            return _MethodWrapper(attr, self._deref_wrapper)
        return attr


class _MethodWrapper:
    """Wrapper for method calls that auto-wraps results."""

    __slots__ = ("_method", "_wrapper")

    def __init__(self, method: Callable[..., Any], wrapper: type) -> None:
        self._method = method
        self._wrapper = wrapper

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = self._method(*args, **kwargs)
        if _is_result_or_option(result):
            return result
        return self._wrapper(result)

    def __repr__(self) -> str:
        return f"<wrapped {self._method!r}>"


class DerefOk[T](Deref):
    """An Ok variant that forwards attribute access to its value.

    This provides transparent method chaining where you can call methods
    on the wrapped value and get Ok-wrapped results back.

    Examples:
        >>> d = DerefOk("hello")
        >>> d.upper()
        Ok(value='HELLO')
        >>> d.split("e")
        Ok(value=['h', 'llo'])
    """

    __slots__ = ("_value",)

    def __init__(self, value: T) -> None:
        self._value = value

    @property
    def _deref_value(self) -> T:
        return self._value

    @property
    def _deref_wrapper(self) -> type:
        return Ok

    @property
    def value(self) -> T:
        """The wrapped value."""
        return self._value

    def unwrap(self) -> T:
        """Return the wrapped value."""
        return self._value

    def is_ok(self) -> bool:
        """Return True (this is always Ok)."""
        return True

    def is_err(self) -> bool:
        """Return False (this is never Err)."""
        return False

    def to_ok(self) -> Ok[T]:
        """Convert to a regular Ok."""
        return Ok(self._value)

    def __repr__(self) -> str:
        return f"DerefOk(value={self._value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DerefOk):
            return self._value == other._value
        if isinstance(other, Ok):
            return self._value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("DerefOk", self._value))


class DerefSome[T](Deref):
    """A Some variant that forwards attribute access to its value.

    This provides transparent method chaining where you can call methods
    on the wrapped value and get Some-wrapped results back.

    Examples:
        >>> d = DerefSome("hello")
        >>> d.upper()
        Some(value='HELLO')
        >>> d.split("e")
        Some(value=['h', 'llo'])
    """

    __slots__ = ("_value",)

    def __init__(self, value: T) -> None:
        self._value = value

    @property
    def _deref_value(self) -> T:
        return self._value

    @property
    def _deref_wrapper(self) -> type:
        return Some

    @property
    def value(self) -> T:
        """The wrapped value."""
        return self._value

    def unwrap(self) -> T:
        """Return the wrapped value."""
        return self._value

    def is_some(self) -> bool:
        """Return True (this is always Some)."""
        return True

    def is_none(self) -> bool:
        """Return False (this is never Nothing)."""
        return False

    def to_some(self) -> Some[T]:
        """Convert to a regular Some."""
        return Some(self._value)

    def __repr__(self) -> str:
        return f"DerefSome(value={self._value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DerefSome):
            return self._value == other._value
        if isinstance(other, Some):
            return self._value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("DerefSome", self._value))
