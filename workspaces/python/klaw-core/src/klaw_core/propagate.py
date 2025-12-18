"""Propagate exception for .bail() mechanism."""

from typing import Any


class Propagate(Exception):  # noqa: N818
    """Exception raised by .bail() to propagate Err/Nothing up the call stack.

    This is caught by the @result decorator to return the contained error.
    The name intentionally doesn't end with "Error" to match Rust's naming
    and to distinguish it from actual errors.
    """

    __slots__ = ('_value',)

    def __init__(self, value: Any) -> None:
        """Initialize Propagate with the error value to propagate.

        Args:
            value: The Err or Nothing value being propagated.
        """
        self._value = value
        super().__init__(f'Propagate({value!r})')

    @property
    def value(self) -> Any:
        """The error value being propagated."""
        return self._value
