"""Option type: Some[T] | Nothing for optional values."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, NoReturn, TypeIs

import msgspec

from klaw_result.types.propagate import Propagate

if TYPE_CHECKING:
    from klaw_result.types.result import Err, Ok

__all__ = ["Nothing", "NothingType", "Option", "Some"]


class Some[T](msgspec.Struct, frozen=True, gc=False):
    """Some variant of Option containing a value of type T.

    Some represents the presence of a value. It wraps a value that can be
    extracted, transformed, or propagated through a chain of Option-returning
    operations.

    Examples:
        >>> some = Some(42)
        >>> some.unwrap()
        42
        >>> some.map(lambda x: x * 2)
        Some(value=84)
        >>> with some as value:
        ...     print(value)
        42
    """

    value: T

    def __enter__(self) -> T:
        """Context manager entry - returns the contained value."""
        return self.value

    def __exit__(self, *_: object) -> None:
        """Context manager exit - no cleanup needed."""
        pass

    def is_some(self) -> TypeIs[Some[T]]:
        """Return True if the option is Some.

        This method provides type narrowing - after checking is_some(),
        the type checker knows the option is Some[T].
        """
        return True

    def is_none(self) -> TypeIs[NothingType]:
        """Return False since this is Some."""
        return False

    def unwrap(self) -> T:
        """Return the contained Some value.

        Since this is Some, this always succeeds.
        """
        return self.value

    def unwrap_or(self, default: T) -> T:  # noqa: ARG002
        """Return the contained Some value, ignoring the default."""
        return self.value

    def unwrap_or_else(self, f: Callable[[], T]) -> T:  # noqa: ARG002
        """Return the contained Some value, ignoring the fallback function."""
        return self.value

    def expect(self, _msg: str) -> T:
        """Return the contained Some value, ignoring the message."""
        return self.value

    def map[U](self, f: Callable[[T], U]) -> Some[U]:
        """Apply a function to the contained value.

        Args:
            f: Function to apply to the Some value.

        Returns:
            Some containing the result of applying f to the value.
        """
        return Some(f(self.value))

    def and_then[U](
        self, f: Callable[[T], Some[U] | NothingType]
    ) -> Some[U] | NothingType:
        """Apply a function that returns an Option to the contained value.

        Also known as flatmap or bind.

        Args:
            f: Function that takes T and returns Option[U].

        Returns:
            The Option returned by f.
        """
        return f(self.value)

    def or_else(self, _f: Callable[[], Some[T] | NothingType]) -> Some[T]:
        """Return self unchanged since this is Some."""
        return self

    def filter(self, predicate: Callable[[T], bool]) -> Some[T] | NothingType:
        """Return Some if the predicate is satisfied, else Nothing.

        Args:
            predicate: Function that returns True to keep the value.

        Returns:
            Some(value) if predicate(value) is True, else Nothing.
        """
        if predicate(self.value):
            return self
        return Nothing

    def ok_or[E](self, _err: E) -> Ok[T]:
        """Convert to Result, returning Ok(value).

        Args:
            _err: Ignored error value.

        Returns:
            Ok containing the value.
        """
        from klaw_result.types.result import Ok

        return Ok(self.value)

    def ok_or_else[E](self, _f: Callable[[], E]) -> Ok[T]:
        """Convert to Result, returning Ok(value).

        Args:
            _f: Ignored error factory function.

        Returns:
            Ok containing the value.
        """
        from klaw_result.types.result import Ok

        return Ok(self.value)

    def and_[U](self, other: Some[U] | NothingType) -> Some[U] | NothingType:
        """Return other if self is Some, else return Nothing.

        Since this is Some, returns other.
        """
        return other

    def or_(self, _other: Some[T] | NothingType) -> Some[T]:
        """Return self if Some, else return other.

        Since this is Some, returns self.
        """
        return self

    def zip[U](self, other: Some[U] | NothingType) -> Some[tuple[T, U]] | NothingType:
        """Combine two Some values into a tuple.

        If both are Some, returns Some((self.value, other.value)).
        If either is Nothing, returns Nothing.
        """
        if isinstance(other, Some):
            return Some((self.value, other.value))
        return Nothing

    def flatten[U](self: Some[Some[U] | NothingType]) -> Some[U] | NothingType:
        """Flatten a nested Option.

        Converts Option[Option[T]] into Option[T].
        """
        return self.value  # type: ignore[return-value]

    def bail(self) -> T:
        """Return the contained value (no-op for Some).

        This is the equivalent of Rust's ? operator. For Some, it just
        returns the value. For Nothing, it would raise Propagate.
        """
        return self.value

    def unwrap_or_return(self) -> T:
        """Alias for bail(). Return the contained value."""
        return self.value

    def __or__[U](self, f: Callable[[T], U]) -> Some[U] | NothingType:
        """Pipe operator for chaining: Some(x) | f calls f(x) and wraps in Some."""
        result = f(self.value)
        if isinstance(result, Some | NothingType):
            return result
        return Some(result)


class NothingType(msgspec.Struct, frozen=True, gc=False):
    """Nothing variant of Option representing absence of a value.

    Nothing represents the absence of a value. Operations on Nothing
    typically return Nothing or a default value.

    This is a singleton - use the `Nothing` constant instead of
    instantiating directly.

    Examples:
        >>> Nothing.is_none()
        True
        >>> Nothing.unwrap_or(0)
        0
    """

    def __enter__(self) -> NoReturn:
        """Context manager entry - raises Propagate for Nothing."""
        raise Propagate(self)

    def __exit__(self, *_: object) -> None:
        """Context manager exit - never called since __enter__ raises."""
        pass

    def is_some(self) -> TypeIs[Some[object]]:
        """Return False since this is Nothing."""
        return False

    def is_none(self) -> TypeIs[NothingType]:
        """Return True if the option is Nothing.

        This method provides type narrowing - after checking is_none(),
        the type checker knows the option is Nothing.
        """
        return True

    def unwrap(self) -> NoReturn:
        """Raise an exception since this is Nothing.

        Raises:
            RuntimeError: Always, since Nothing has no value to unwrap.
        """
        raise RuntimeError("Called unwrap on Nothing")

    def unwrap_or[T](self, default: T) -> T:
        """Return the default value since this is Nothing."""
        return default

    def unwrap_or_else[T](self, f: Callable[[], T]) -> T:
        """Compute and return a default value since this is Nothing."""
        return f()

    def expect(self, msg: str) -> NoReturn:
        """Raise an exception with a custom message.

        Args:
            msg: Custom error message.

        Raises:
            RuntimeError: Always, with the custom message.
        """
        raise RuntimeError(msg)

    def map[T, U](self, _f: Callable[[T], U]) -> NothingType:
        """Return Nothing since there's no value to map."""
        return self

    def and_then[T, U](self, _f: Callable[[T], Some[U] | NothingType]) -> NothingType:
        """Return Nothing since there's no value to bind."""
        return self

    def or_else[T](
        self, f: Callable[[], Some[T] | NothingType]
    ) -> Some[T] | NothingType:
        """Apply a recovery function since this is Nothing.

        Args:
            f: Function that returns a new Option.

        Returns:
            The Option returned by f.
        """
        return f()

    def filter[T](self, _predicate: Callable[[T], bool]) -> NothingType:  # noqa: ARG002
        """Return Nothing since there's no value to filter."""
        return self

    def ok_or[E](self, err: E) -> Err[E]:
        """Convert to Result, returning Err(err).

        Args:
            err: The error value to wrap.

        Returns:
            Err containing the error.
        """
        from klaw_result.types.result import Err

        return Err(err)

    def ok_or_else[E](self, f: Callable[[], E]) -> Err[E]:
        """Convert to Result, computing the error.

        Args:
            f: Function that produces the error value.

        Returns:
            Err containing the computed error.
        """
        from klaw_result.types.result import Err

        return Err(f())

    def and_[T](self, _other: Some[T] | NothingType) -> NothingType:
        """Return Nothing since self is Nothing."""
        return self

    def or_[T](self, other: Some[T] | NothingType) -> Some[T] | NothingType:
        """Return other since self is Nothing."""
        return other

    def zip[T, U](self, _other: Some[U] | NothingType) -> NothingType:
        """Return Nothing since self is Nothing."""
        return self

    def flatten(self) -> NothingType:
        """Return Nothing since there's nothing to flatten."""
        return self

    def bail(self) -> NoReturn:
        """Raise Propagate to propagate Nothing up the call stack.

        This is the equivalent of Rust's ? operator. When used inside
        a function decorated with @result, Nothing will be caught
        and returned.

        Raises:
            Propagate: Always, containing Nothing.
        """
        raise Propagate(self)

    def unwrap_or_return(self) -> NoReturn:
        """Alias for bail(). Raise Propagate to propagate Nothing."""
        raise Propagate(self)

    def __or__[T, U](self, _f: Callable[[T], U]) -> NothingType:
        """Pipe operator returns Nothing unchanged."""
        return self


Nothing: NothingType = NothingType()
"""Singleton instance representing the absence of a value."""


type Option[T] = Some[T] | NothingType
