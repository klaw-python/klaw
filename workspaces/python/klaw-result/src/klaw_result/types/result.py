"""Result type: Ok[T] | Err[E] for explicit error handling."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, NoReturn, TypeIs

import msgspec

from klaw_result.types.propagate import Propagate

if TYPE_CHECKING:
    from klaw_result.types.option import Option

__all__ = ["Err", "Ok", "Result"]


class Ok[T](msgspec.Struct, frozen=True, gc=False):
    """Success variant of Result containing a value of type T.

    Ok represents the successful outcome of an operation. It wraps a value
    that can be extracted, transformed, or propagated through a chain of
    Result-returning operations.

    Examples:
        >>> ok = Ok(42)
        >>> ok.unwrap()
        42
        >>> ok.map(lambda x: x * 2)
        Ok(value=84)
    """

    value: T

    def is_ok(self) -> TypeIs[Ok[T]]:
        """Return True if the result is Ok.

        This method provides type narrowing - after checking is_ok(),
        the type checker knows the result is Ok[T].
        """
        return True

    def is_err(self) -> TypeIs[Err[object]]:
        """Return False since this is Ok.

        This method provides type narrowing - after checking is_err(),
        the type checker knows the result is Err[E].
        """
        return False

    def unwrap(self) -> T:
        """Return the contained Ok value.

        Since this is Ok, this always succeeds.
        """
        return self.value

    def unwrap_or(self, default: T) -> T:  # noqa: ARG002
        """Return the contained Ok value, ignoring the default."""
        return self.value

    def unwrap_or_else(self, f: Callable[[], T]) -> T:  # noqa: ARG002
        """Return the contained Ok value, ignoring the fallback function."""
        return self.value

    def expect(self, _msg: str) -> T:
        """Return the contained Ok value, ignoring the message."""
        return self.value

    def map[U](self, f: Callable[[T], U]) -> Ok[U]:
        """Apply a function to the contained value.

        Args:
            f: Function to apply to the Ok value.

        Returns:
            Ok containing the result of applying f to the value.
        """
        return Ok(f(self.value))

    def map_err[F](self, _f: Callable[[object], F]) -> Ok[T]:
        """Return self unchanged since this is Ok."""
        return self

    def and_then[U, E](self, f: Callable[[T], Ok[U] | Err[E]]) -> Ok[U] | Err[E]:
        """Apply a function that returns a Result to the contained value.

        Also known as flatmap or bind.

        Args:
            f: Function that takes T and returns Result[U, E].

        Returns:
            The Result returned by f.
        """
        return f(self.value)

    def or_else[F](self, _f: Callable[[object], Ok[T] | Err[F]]) -> Ok[T]:
        """Return self unchanged since this is Ok."""
        return self

    def ok(self) -> Option[T]:
        """Convert to Option, returning Some(value)."""
        from klaw_result.types.option import Some

        return Some(self.value)

    def err(self) -> Option[object]:
        """Convert to Option, returning Nothing since this is Ok."""
        from klaw_result.types.option import Nothing

        return Nothing

    def and_[U, E](self, other: Ok[U] | Err[E]) -> Ok[U] | Err[E]:
        """Return other if self is Ok, else return self (Err).

        Since this is Ok, returns other.
        """
        return other

    def or_[F](self, _other: Ok[T] | Err[F]) -> Ok[T]:
        """Return self if Ok, else return other.

        Since this is Ok, returns self.
        """
        return self

    def zip[U, E](self, other: Ok[U] | Err[E]) -> Ok[tuple[T, U]] | Err[E]:
        """Combine two Ok values into a tuple.

        If both are Ok, returns Ok((self.value, other.value)).
        If either is Err, returns the first Err.
        """
        if isinstance(other, Ok):
            return Ok((self.value, other.value))
        return other

    def flatten[U, E](self: Ok[Ok[U] | Err[E]]) -> Ok[U] | Err[E]:
        """Flatten a nested Result.

        Converts Result[Result[T, E], E] into Result[T, E].
        """
        return self.value  # type: ignore[return-value]

    def bail(self) -> T:
        """Return the contained value (no-op for Ok).

        This is the equivalent of Rust's ? operator. For Ok, it just
        returns the value. For Err, it would raise Propagate.
        """
        return self.value

    def unwrap_or_return(self) -> T:
        """Alias for bail(). Return the contained value."""
        return self.value

    def __or__[U, E](self, f: Callable[[T], U]) -> Ok[U] | Err[E]:
        """Pipe operator for chaining: Ok(x) | f calls f(x) and wraps in Ok."""
        result = f(self.value)
        if isinstance(result, Ok | Err):
            return result
        return Ok(result)


class Err[E](msgspec.Struct, frozen=True, gc=False):
    """Error variant of Result containing an error of type E.

    Err represents the failure outcome of an operation. It wraps an error
    value that can be transformed, recovered from, or propagated.

    Examples:
        >>> err = Err("something went wrong")
        >>> err.is_err()
        True
        >>> err.unwrap_or(0)
        0
    """

    error: E

    def is_ok(self) -> TypeIs[Ok[object]]:
        """Return False since this is Err."""
        return False

    def is_err(self) -> TypeIs[Err[E]]:
        """Return True if the result is Err.

        This method provides type narrowing - after checking is_err(),
        the type checker knows the result is Err[E].
        """
        return True

    def unwrap(self) -> NoReturn:
        """Raise an exception since this is Err.

        Raises:
            RuntimeError: Always, since Err has no Ok value to unwrap.
        """
        raise RuntimeError(f"Called unwrap on Err: {self.error!r}")

    def unwrap_or[T](self, default: T) -> T:
        """Return the default value since this is Err."""
        return default

    def unwrap_or_else[T](self, f: Callable[[], T]) -> T:
        """Compute and return a default value since this is Err."""
        return f()

    def expect(self, msg: str) -> NoReturn:
        """Raise an exception with a custom message.

        Args:
            msg: Custom error message.

        Raises:
            RuntimeError: Always, with the custom message.
        """
        raise RuntimeError(f"{msg}: {self.error!r}")

    def map[T, U](self, _f: Callable[[T], U]) -> Err[E]:
        """Return self unchanged since this is Err."""
        return self

    def map_err[F](self, f: Callable[[E], F]) -> Err[F]:
        """Apply a function to the contained error.

        Args:
            f: Function to apply to the error value.

        Returns:
            Err containing the transformed error.
        """
        return Err(f(self.error))

    def and_then[T, U](self, _f: Callable[[T], Ok[U] | Err[E]]) -> Err[E]:
        """Return self unchanged since this is Err."""
        return self

    def or_else[T, F](self, f: Callable[[E], Ok[T] | Err[F]]) -> Ok[T] | Err[F]:
        """Apply a recovery function to the error.

        Args:
            f: Function that takes the error and returns a new Result.

        Returns:
            The Result returned by f.
        """
        return f(self.error)

    def ok(self) -> Option[object]:
        """Convert to Option, returning Nothing since this is Err."""
        from klaw_result.types.option import Nothing

        return Nothing

    def err(self) -> Option[E]:
        """Convert to Option, returning Some(error)."""
        from klaw_result.types.option import Some

        return Some(self.error)

    def and_[T, U](self, _other: Ok[U] | Err[E]) -> Err[E]:
        """Return self since this is Err."""
        return self

    def or_[T, F](self, other: Ok[T] | Err[F]) -> Ok[T] | Err[F]:
        """Return other since this is Err."""
        return other

    def zip[T, U](self, _other: Ok[U] | Err[E]) -> Err[E]:
        """Return self since this is Err."""
        return self

    def flatten(self) -> Err[E]:
        """Return self since this is Err (nothing to flatten)."""
        return self

    def bail(self) -> NoReturn:
        """Raise Propagate to propagate this error up the call stack.

        This is the equivalent of Rust's ? operator. When used inside
        a function decorated with @result, the error will be caught
        and returned.

        Raises:
            Propagate: Always, containing this Err.
        """
        raise Propagate(self)

    def unwrap_or_return(self) -> NoReturn:
        """Alias for bail(). Raise Propagate to propagate this error."""
        raise Propagate(self)

    def __or__[T, U](self, _f: Callable[[T], U]) -> Err[E]:
        """Pipe operator returns self unchanged for Err."""
        return self


type Result[T, E = Exception] = Ok[T] | Err[E]


def collect[T, E](results: Iterable[Ok[T] | Err[E]]) -> Ok[list[T]] | Err[E]:
    """Collect an iterable of Results into a Result of list.

    Short-circuits on the first Err encountered.

    Args:
        results: An iterable of Result values.

    Returns:
        Ok(list[T]) if all results are Ok, otherwise the first Err.

    Examples:
        >>> collect([Ok(1), Ok(2), Ok(3)])
        Ok(value=[1, 2, 3])
        >>> collect([Ok(1), Err("fail"), Ok(3)])
        Err(error='fail')
    """
    values: list[T] = []
    for result in results:
        if isinstance(result, Err):
            return result
        values.append(result.value)
    return Ok(values)
