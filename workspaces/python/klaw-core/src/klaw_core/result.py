"""Rust-like Result/Option for modern Python 3.13+.

This module provides type-safe error handling and optional values inspired by Rust's
Result<T, E> and Option<T> types. It enables functional programming patterns with
composability through methods like map, and_then, and or_else.

Example:
    ```python
    from klaw_core.result import Ok, Err, safe

    @safe
    def divide(a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Division by zero")
        return a / b

    result = divide(10, 2)
    print(result)  # Ok(5.0)

    result = divide(10, 0)
    print(result)  # Err(ValueError('Division by zero'))
    ```

    ```python
    from klaw_core.result import Some, Nothing, map_opt

    maybe = Some(42).map_opt(lambda x: x * 2)
    print(maybe)  # Some(84)

    nothing = Nothing
    mapped = nothing.map_opt(lambda x: x * 2)
    print(mapped)  # Nothing
    ```
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import wraps
from typing import (
    Any,
    ParamSpec,
    TypeGuard,
    overload,
)

# ---------------------------------------------------------------------
# Result[T, E] — Rust-style Ok / Err
# ---------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Ok[T]:
    """Represents a successful computation containing a value of type T.

    This is the "success" variant of a Result[T, E], containing the actual
    result value.

    Attributes:
        value: The successful result value.
    """

    value: T
    __match_args__ = ('value',)

    def is_ok(self) -> bool:
        """Return True, indicating this is a successful result.

        Returns:
            bool: Always True for Ok instances.
        """
        return True

    def is_err(self) -> bool:
        """Return False, indicating this is not an error result.

        Returns:
            bool: Always False for Ok instances.
        """
        return False

    def is_ok_and(self, pred: Callable[[T], bool]) -> bool:
        """Test if the value satisfies a predicate.

        Args:
            pred: A callable that takes the value and returns a boolean.

        Returns:
            bool: True if the predicate returns True for the value, False otherwise.
        """
        return pred(self.value)

    def is_err_and(self, pred: Callable[[BaseException], bool]) -> bool:
        """Test if the error satisfies a predicate (always False for Ok).

        Args:
            pred: A callable that takes an exception and returns a boolean.

        Returns:
            bool: Always False for Ok instances.
        """
        return False

    def map[U](self, f: Callable[[T], U]) -> Ok[U] | Err[BaseException]:
        """Transform the value using a function.

        Args:
            f: A callable that takes the value and returns a new value of type U.

        Returns:
            Ok[U] | Err[BaseException]: A new Ok containing the transformed value.
        """
        return Ok(f(self.value))

    def map_err[F: BaseException](self, f: Callable[[BaseException], F]) -> Ok[T] | Err[F]:
        """Transform the error (no-op for Ok).

        Args:
            f: A callable that takes an exception and returns a new exception.

        Returns:
            Ok[T] | Err[F]: Returns self unchanged.
        """
        return self  # type: ignore[return-value]

    def map_or[U](self, default: U, f: Callable[[T], U]) -> U:
        """Apply function to value or return default (always applies function for Ok).

        Args:
            default: Default value to return if Err (unused for Ok).
            f: Function to apply to the value.

        Returns:
            U: The result of applying f to the value.
        """
        return f(self.value)

    def map_or_else[U](self, default: Callable[[], U], f: Callable[[T], U]) -> U:
        """Apply function to value or compute default (always applies function for Ok).

        Args:
            default: Callable to compute default if Err (unused for Ok).
            f: Function to apply to the value.

        Returns:
            U: The result of applying f to the value.
        """
        return f(self.value)

    def inspect(self, f: Callable[[T], Any]) -> Ok[T] | Err[BaseException]:
        """Call a function with the value for side effects.

        Args:
            f: A callable that takes the value and performs side effects.

        Returns:
            Ok[T] | Err[BaseException]: Returns self unchanged.
        """
        f(self.value)
        return self

    def inspect_err(self, f: Callable[[BaseException], Any]) -> Ok[T] | Err[BaseException]:
        """Call a function with the error for side effects (no-op for Ok).

        Args:
            f: A callable that takes an exception and performs side effects.

        Returns:
            Ok[T] | Err[BaseException]: Returns self unchanged.
        """
        return self

    def and_then[U](self, f: Callable[[T], Ok[U] | Err[BaseException]]) -> Ok[U] | Err[BaseException]:
        """Chain a computation that may fail.

        Args:
            f: A callable that takes the value and returns a Result.

        Returns:
            Ok[U] | Err[BaseException]: The result of applying f to the value.
        """
        return f(self.value)

    def or_else[F: BaseException](self, f: Callable[[BaseException], Ok[T] | Err[F]]) -> Ok[T] | Err[BaseException | F]:
        """Handle error case (no-op for Ok).

        Args:
            f: A callable that takes an exception and returns a Result.

        Returns:
            Ok[T] | Err[BaseException | F]: Returns self unchanged.
        """
        return self

    def and_[U](self, other: Ok[U] | Err[BaseException]) -> Ok[U] | Err[BaseException]:
        """Logical AND with another Result.

        Args:
            other: Another Result to combine with.

        Returns:
            Ok[U] | Err[BaseException]: Returns the other Result.
        """
        return other

    def or_(self, other: Ok[T] | Err[BaseException]) -> Ok[T] | Err[BaseException]:
        """Logical OR with another Result.

        Args:
            other: Another Result to combine with.

        Returns:
            Ok[T] | Err[BaseException]: Returns self.
        """
        return self

    def contains(self, x: T) -> bool:
        """Check if the Result contains a specific value.

        Args:
            x: The value to check for.

        Returns:
            bool: True if the value matches, False otherwise.
        """
        return self.value == x

    def contains_err(self, e: BaseException | type[BaseException] | tuple[type[BaseException], ...]) -> bool:
        """Check if the Result contains a specific error (always False for Ok).

        Args:
            e: The error or error type(s) to check for.

        Returns:
            bool: Always False for Ok instances.
        """
        return False

    def unwrap(self) -> T:
        """Unwrap the value.

        Returns:
            T: The contained value.

        Raises:
            This method does not raise for Ok instances.
        """
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Unwrap the value or return a default.

        Args:
            default: The default value (unused for Ok).

        Returns:
            T: The contained value.
        """
        return self.value

    def unwrap_or_else(self, f: Callable[[BaseException], T]) -> T:
        """Unwrap the value or compute a default from an error (unused for Ok).

        Args:
            f: A callable to compute the default (unused for Ok).

        Returns:
            T: The contained value.
        """
        return self.value

    def unwrap_err(self) -> BaseException:
        """Unwrap the error (panics for Ok).

        Returns:
            BaseException: Never returns for Ok instances.

        Raises:
            AssertionError: Always raised for Ok instances.
        """
        raise AssertionError(f'called unwrap_err() on Ok({self.value!r})')

    def expect(self, msg: str) -> T:
        """Unwrap the value with a custom error message.

        Args:
            msg: Custom error message (unused for Ok).

        Returns:
            T: The contained value.
        """
        return self.value

    def expect_err(self, msg: str) -> BaseException:
        """Unwrap the error with a custom message (panics for Ok).

        Args:
            msg: Custom error message.

        Returns:
            BaseException: Never returns for Ok instances.

        Raises:
            AssertionError: Always raised for Ok instances.
        """
        raise AssertionError(f'{msg}: expected Err, got Ok({self.value!r})')

    def ok(self) -> T | None:
        """Convert to an optional value.

        Returns:
            T | None: The contained value.
        """
        return self.value

    def err(self) -> BaseException | None:
        """Convert to an optional error.

        Returns:
            BaseException | None: None for Ok instances.
        """
        return None

    def iter(self) -> Iterator[T]:
        """Iterate over the value.

        Yields:
            T: The contained value.
        """
        yield self.value

    def into_ok(self) -> T:
        """Convert to the value (alias for unwrap).

        Returns:
            T: The contained value.
        """
        return self.value

    def into_err(self) -> BaseException:
        """Convert to the error (panics for Ok).

        Returns:
            BaseException: Never returns for Ok instances.

        Raises:
            AssertionError: Always raised for Ok instances.
        """
        raise AssertionError(f'called into_err() on Ok({self.value!r})')

    def __repr__(self) -> str:
        """Return a string representation of the Ok instance."""
        return f'Ok({self.value!r})'


@dataclass(slots=True, frozen=True)
class Err[E: BaseException]:
    """Represents a failed computation containing an error of type E.

    This is the "error" variant of a Result[T, E], containing the exception
    that occurred during the computation.

    Attributes:
        error: The exception that occurred.
    """

    error: E
    __match_args__ = ('error',)

    def is_ok(self) -> bool:
        """Return False, indicating this is not a successful result.

        Returns:
            bool: Always False for Err instances.
        """
        return False

    def is_err(self) -> bool:
        """Return True, indicating this is an error result.

        Returns:
            bool: Always True for Err instances.
        """
        return True

    def is_ok_and(self, pred: Callable[[Any], bool]) -> bool:
        """Test if the value satisfies a predicate (always False for Err).

        Args:
            pred: A callable that takes a value and returns a boolean.

        Returns:
            bool: Always False for Err instances.
        """
        return False

    def is_err_and(self, pred: Callable[[E], bool]) -> bool:
        """Test if the error satisfies a predicate.

        Args:
            pred: A callable that takes the error and returns a boolean.

        Returns:
            bool: True if the predicate returns True for the error, False otherwise.
        """
        return pred(self.error)

    def map[U](self, f: Callable[[Any], U]) -> Ok[U] | Err[E]:
        """Transform the value (no-op for Err).

        Args:
            f: A callable that takes a value and returns a new value.

        Returns:
            Ok[U] | Err[E]: Returns self unchanged.
        """
        return self  # type: ignore[return-value]

    def map_err[F: BaseException](self, f: Callable[[E], F]) -> Ok[Any] | Err[F]:
        """Transform the error using a function.

        Args:
            f: A callable that takes the error and returns a new exception.

        Returns:
            Ok[Any] | Err[F]: A new Err containing the transformed error.
        """
        return Err(f(self.error))

    def map_or[U](self, default: U, f: Callable[[Any], U]) -> U:
        """Apply function to value or return default (always returns default for Err).

        Args:
            default: Default value to return.
            f: Function to apply to the value (unused for Err).

        Returns:
            U: The default value.
        """
        return default

    def map_or_else[U](self, default: Callable[[], U], f: Callable[[Any], U]) -> U:
        """Apply function to value or compute default (always computes default for Err).

        Args:
            default: Callable to compute the default.
            f: Function to apply to the value (unused for Err).

        Returns:
            U: The result of calling default().
        """
        return default()

    def inspect(self, f: Callable[[Any], Any]) -> Ok[Any] | Err[E]:
        """Call a function with the value for side effects (no-op for Err).

        Args:
            f: A callable that takes a value and performs side effects.

        Returns:
            Ok[Any] | Err[E]: Returns self unchanged.
        """
        return self  # type: ignore[return-value]

    def inspect_err(self, f: Callable[[E], Any]) -> Ok[Any] | Err[E]:
        """Call a function with the error for side effects.

        Args:
            f: A callable that takes the error and performs side effects.

        Returns:
            Ok[Any] | Err[E]: Returns self unchanged.
        """
        f(self.error)
        return self  # type: ignore[return-value]

    def and_then[U](self, f: Callable[[Any], Ok[U] | Err[E]]) -> Ok[U] | Err[E]:
        """Chain a computation that may fail (no-op for Err).

        Args:
            f: A callable that takes a value and returns a Result.

        Returns:
            Ok[U] | Err[E]: Returns self unchanged.
        """
        return self  # type: ignore[return-value]

    def or_else[F: BaseException](self, f: Callable[[E], Ok[Any] | Err[F]]) -> Ok[Any] | Err[F]:
        """Handle error case by applying a function to the error.

        Args:
            f: A callable that takes the error and returns a Result.

        Returns:
            Ok[Any] | Err[F]: The result of applying f to the error.
        """
        return f(self.error)

    def and_[U](self, other: Ok[U] | Err[E]) -> Ok[U] | Err[E]:
        """Logical AND with another Result (always returns self for Err).

        Args:
            other: Another Result to combine with.

        Returns:
            Ok[U] | Err[E]: Returns self unchanged.
        """
        return self  # type: ignore[return-value]

    def or_(self, other: Ok[Any] | Err[E]) -> Ok[Any] | Err[E]:
        """Logical OR with another Result.

        Args:
            other: Another Result to combine with.

        Returns:
            Ok[Any] | Err[E]: Returns the other Result.
        """
        return other

    def contains(self, x: Any) -> bool:
        """Check if the Result contains a specific value (always False for Err).

        Args:
            x: The value to check for.

        Returns:
            bool: Always False for Err instances.
        """
        return False

    def contains_err(self, e: E | type[E] | tuple[type[E], ...]) -> bool:
        """Check if the Result contains a specific error.

        Args:
            e: The error, error type, or tuple of error types to check for.

        Returns:
            bool: True if the error matches, False otherwise.
        """
        if isinstance(e, tuple):
            return isinstance(self.error, e)
        if isinstance(e, type):
            return isinstance(self.error, e)  # type: ignore[arg-type]
        return self.error == e

    def unwrap(self) -> Any:
        """Unwrap the value (raises the error for Err).

        Returns:
            Any: Never returns for Err instances.

        Raises:
            E: Always raises the contained error.
        """
        raise self.error

    def unwrap_or(self, default: Any) -> Any:
        """Unwrap the value or return a default.

        Args:
            default: The default value to return.

        Returns:
            Any: The default value.
        """
        return default

    def unwrap_or_else(self, f: Callable[[E], Any]) -> Any:
        """Unwrap the value or compute a default from the error.

        Args:
            f: A callable that takes the error and returns a default value.

        Returns:
            Any: The result of applying f to the error.
        """
        return f(self.error)

    def unwrap_err(self) -> E:
        """Unwrap the error.

        Returns:
            E: The contained error.
        """
        return self.error

    def expect(self, msg: str) -> Any:
        """Unwrap the value with a custom error message (raises a new exception for Err).

        Args:
            msg: Custom error message.

        Returns:
            Any: Never returns for Err instances.

        Raises:
            Exception: A new exception with the custom message and original error as cause.
        """
        raise type(self.error)(f'{msg}: {self.error}') from self.error

    def expect_err(self, msg: str) -> E:
        """Unwrap the error with a custom message.

        Args:
            msg: Custom error message (unused for Err).

        Returns:
            E: The contained error.
        """
        return self.error

    def ok(self) -> Any | None:
        """Convert to an optional value.

        Returns:
            Any | None: None for Err instances.
        """
        return None

    def err(self) -> E | None:
        """Convert to an optional error.

        Returns:
            E | None: The contained error.
        """
        return self.error

    def iter(self) -> Iterator[Any]:
        """Iterate over the value (empty iterator for Err).

        Yields:
            Any: Nothing for Err instances.
        """
        if False:
            yield None  # pragma: no cover

    def into_ok(self) -> Any:
        """Convert to the value (raises the error for Err).

        Returns:
            Any: Never returns for Err instances.

        Raises:
            E: Always raises the contained error.
        """
        raise self.error

    def into_err(self) -> E:
        """Convert to the error (alias for unwrap_err).

        Returns:
            E: The contained error.
        """
        return self.error

    def __repr__(self) -> str:
        """Return a string representation of the Err instance."""
        return f'Err({self.error!r})'


# Public alias (now Ok/Err exist, so this works cleanly)
type Result[T, E: BaseException] = Ok[T] | Err[E]


# ---------------------------------------------------------------------
# TypeGuards & free-function parity
# ---------------------------------------------------------------------


def result_as_ref[T, E: BaseException](r: Result[T, E]) -> Result[T, E]:
    """Rust: Result::as_ref — here: identity (same object)."""
    return r


def result_as_mut[T, E: BaseException](r: Result[T, E]) -> Result[T, E]:
    """Rust: Result::as_mut — here: identity (same object)."""
    return r


def result_transpose[T, E: BaseException](r: Result[Maybe[T], E]) -> Maybe[Result[T, E]]:
    # Ok(Some(v)) -> Some(Ok(v))
    # Ok(Nothing) -> Nothing
    # Err(e)      -> Some(Err(e))  (matches Rust)
    if isinstance(r, Ok):
        inner = r.value
        return Some(Ok(inner.value)) if is_some(inner) else Nothing
    return Some(Err(r.error))


def result_flatten[T, E: BaseException](r: Result[Result[T, E], E]) -> Result[T, E]:
    # Ok(Ok(v)) -> Ok(v)
    # Ok(Err(e))-> Err(e)
    # Err(e)    -> Err(e)
    if isinstance(r, Ok):
        return r.value
    return r


def option_as_ref[T](m: Maybe[T]) -> Maybe[T]:
    """Rust: Option::as_ref — here: identity (same object)."""
    return m


def option_as_mut[T](m: Maybe[T]) -> Maybe[T]:
    """Rust: Option::as_mut — here: identity (same object)."""
    return m


def inspect_opt[T](m: Maybe[T], f: Callable[[T], Any]) -> Maybe[T]:
    if is_some(m):
        f(m.value)
    return m


def map_or_opt[T, U](m: Maybe[T], default: U, f: Callable[[T], U]) -> U:
    return f(m.value) if is_some(m) else default


def map_or_else_opt[T, U](m: Maybe[T], default_fn: Callable[[], U], f: Callable[[T], U]) -> U:
    return f(m.value) if is_some(m) else default_fn()


def and_opt[T, U](m: Maybe[T], other: Maybe[U]) -> Maybe[U]:
    # Some(_) & Some(u) -> Some(u)
    # Some(_) & Nothing -> Nothing
    # Nothing & _       -> Nothing
    return other if is_some(m) else Nothing


def xor_opt[T](a: Maybe[T], b: Maybe[T]) -> Maybe[T]:
    # Exactly one Some wins
    return a if is_some(a) and is_nothing(b) else (b if is_some(b) and is_nothing(a) else Nothing)


def option_transpose[T, E: BaseException](m: Maybe[Result[T, E]]) -> Result[Maybe[T], E]:
    # Some(Ok(v)) -> Ok(Some(v))
    # Some(Err(e))-> Err(e)
    # Nothing     -> Ok(Nothing)
    if is_nothing(m):
        return Ok(Nothing)
    r = m.value
    return r if isinstance(r, Err) else Ok(Some(r.value))


def option_flatten[T](m: Maybe[Maybe[T]]) -> Maybe[T]:
    return m.value if is_some(m) else Nothing


def unwrap_or_default_opt[T](m: Maybe[T], default_factory: Callable[[], T]) -> T:
    return m.value if is_some(m) else default_factory()


def is_ok[T, E: BaseException](r: Result[T, E]) -> TypeGuard[Ok[T]]:
    """Check if a Result is Ok.

    Args:
        r: The Result to check.

    Returns:
        bool: True if the Result is Ok, False if Err.
    """
    return isinstance(r, Ok)


def is_err[T, E: BaseException](r: Result[T, E]) -> TypeGuard[Err[E]]:
    """Check if a Result is Err.

    Args:
        r: The Result to check.

    Returns:
        bool: True if the Result is Err, False if Ok.
    """
    return isinstance(r, Err)


def rmap[T, U, E: BaseException](r: Result[T, E], f: Callable[[T], U]) -> Result[U, E]:
    """Transform the value of a Result if Ok. Alias for map, since map is a keyword.

    Args:
        r: The Result to transform.
        f: Function to apply to the value if Ok.

    Returns:
        Result[U, E]: A new Result with the transformed value if Ok, otherwise the original Err.
    """
    return r.map(f)


def map_err[T, E: BaseException, F: BaseException](r: Result[T, E], f: Callable[[E], F]) -> Result[T, F]:
    """Transform the error of a Result if Err.

    Args:
        r: The Result to transform.
        f: Function to apply to the error if Err.

    Returns:
        Result[T, F]: A new Result with the transformed error if Err, otherwise the original Ok.
    """
    return r.map_err(f)


def and_then[T, U, E: BaseException](r: Result[T, E], f: Callable[[T], Result[U, E]]) -> Result[U, E]:
    """Chain a computation that may fail.

    Args:
        r: The Result to chain from.
        f: Function that takes the value and returns a new Result.

    Returns:
        Result[U, E]: The result of applying f if Ok, otherwise the original Err.
    """
    return r.and_then(f)


def or_else[T, E: BaseException, F: BaseException](r: Result[T, E], f: Callable[[E], Result[T, F]]) -> Result[T, E | F]:
    """Handle the error case of a Result.

    Args:
        r: The Result to handle.
        f: Function that takes the error and returns a new Result.

    Returns:
        Result[T, E | F]: The original Ok if Ok, otherwise the result of applying f to the error.
    """
    return r.or_else(f)


def and_[T, U, E: BaseException](r: Result[T, E], other: Result[U, E]) -> Result[U, E]:
    """Logical AND with another Result.

    Args:
        r: The first Result.
        other: The second Result.

    Returns:
        Result[U, E]: other if r is Ok, otherwise r.
    """
    return r.and_(other)


def or_[T, E: BaseException](r: Result[T, E], other: Result[T, E]) -> Result[T, E]:
    """Logical OR with another Result.

    Args:
        r: The first Result.
        other: The second Result.

    Returns:
        Result[T, E]: r if r is Ok, otherwise other.
    """
    return r.or_(other)


def inspect[T, E: BaseException](r: Result[T, E], f: Callable[[T], Any]) -> Result[T, E]:
    """Call a function with the value for side effects if Ok.

    Args:
        r: The Result to inspect.
        f: Function to call with the value if Ok.

    Returns:
        Result[T, E]: The original Result unchanged.
    """
    return r.inspect(f)


def inspect_err[T, E: BaseException](r: Result[T, E], f: Callable[[E], Any]) -> Result[T, E]:
    """Call a function with the error for side effects if Err.

    Args:
        r: The Result to inspect.
        f: Function to call with the error if Err.

    Returns:
        Result[T, E]: The original Result unchanged.
    """
    return r.inspect_err(f)


def sequence[T, E: BaseException](rs: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Collect values from an iterable of Results, short-circuiting on first Err.

    Args:
        rs: An iterable of Result instances.

    Returns:
        Result[list[T], E]: Ok with list of values if all Ok, otherwise first Err encountered.
    """
    out: list[T] = []
    for r in rs:
        if isinstance(r, Ok):
            out.append(r.value)
        else:
            return r
    return Ok(out)


def traverse[U, T, E: BaseException](xs: Iterable[U], f: Callable[[U], Result[T, E]]) -> Result[list[T], E]:
    """Map a function over an iterable and collect the results, short-circuiting on first Err.

    Args:
        xs: An iterable of values to map over.
        f: Function that takes a value and returns a Result.

    Returns:
        Result[list[T], E]: Ok with list of mapped values if all succeed, otherwise first Err.
    """
    return sequence(f(x) for x in xs)


def partition_results[T, E: BaseException](rs: Iterable[Result[T, E]]) -> tuple[list[T], list[E]]:
    """Separate an iterable of Results into successes and failures.

    Args:
        rs: An iterable of Result instances.

    Returns:
        tuple[list[T], list[E]]: A tuple of (successful_values, errors).
    """
    oks: list[T] = []
    errs: list[E] = []
    for r in rs:
        if isinstance(r, Ok):
            oks.append(r.value)
        else:
            errs.append(r.error)
    return oks, errs


# Decorators (keep original signature via ParamSpec)
P = ParamSpec('P')


@overload
def safe[T](fn: Callable[P, T], /) -> Callable[P, Result[T, Exception]]: ...
@overload
def safe[T, F: BaseException](
    fn: Callable[P, T], /, *, exceptions: tuple[type[F], ...]
) -> Callable[P, Result[T, F]]: ...
def safe[T](
    fn: Callable[P, T], /, *, exceptions: tuple[type[BaseException], ...] = ()
) -> Callable[P, Result[T, BaseException]]:
    """Wrap a synchronous function to capture exceptions as Err.

    This decorator converts any exceptions raised by the wrapped function
    into Err instances, allowing for functional error handling.

    Args:
        fn: The function to wrap.
        exceptions: Optional tuple of exception types to catch. If empty, catches all BaseException.

    Returns:
        Callable[P, Result[T, BaseException]]: A wrapped function that returns Result[T, BaseException].

    Example:
        ```python
        @safe
        def divide(a: float, b: float) -> float:
            if b == 0:
                raise ValueError("Division by zero")
            return a / b

        result = divide(10, 0)
        # result is Err(ValueError('Division by zero'))
        ```
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Result[T, BaseException]:
        try:
            return Ok(fn(*args, **kwargs))
        except BaseException as e:
            if not exceptions or isinstance(e, exceptions):
                return Err(e)
            return Err(e)

    return wrapper


@overload
def async_safe[T](fn: Callable[P, Awaitable[T]], /) -> Callable[P, Awaitable[Result[T, Exception]]]: ...
@overload
def async_safe[T, F: BaseException](
    fn: Callable[P, Awaitable[T]], /, *, exceptions: tuple[type[F], ...]
) -> Callable[P, Awaitable[Result[T, F]]]: ...
def async_safe[T](
    fn: Callable[P, Awaitable[T]], /, *, exceptions: tuple[type[BaseException], ...] = ()
) -> Callable[P, Awaitable[Result[T, BaseException]]]:
    """Wrap an asynchronous function to capture exceptions as Err.

    This decorator converts any exceptions raised by the wrapped async function
    into Err instances, allowing for functional error handling in async code.

    Args:
        fn: The async function to wrap.
        exceptions: Optional tuple of exception types to catch. If empty, catches all BaseException.

    Returns:
        Callable[P, Awaitable[Result[T, BaseException]]]: A wrapped async function that returns Awaitable[Result[T, BaseException]].

    Example:
        ```python
        @async_safe
        async def async_divide(a: float, b: float) -> float:
            await asyncio.sleep(0.1)  # Simulate async work
            if b == 0:
                raise ValueError("Division by zero")
            return a / b

        result = await async_divide(10, 0)
        # result is Err(ValueError('Division by zero'))
        ```
    """

    @wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Result[T, BaseException]:
        try:
            return Ok(await fn(*args, **kwargs))
        except BaseException as e:
            if not exceptions or isinstance(e, exceptions):
                return Err(e)
            return Err(e)

    return wrapper


async def gather_results[T, E: BaseException](coros: Iterable[Awaitable[Result[T, E]]]) -> Result[list[T], E]:
    """Await multiple async Results, short-circuiting on the first Err.

    This function is useful for running multiple async operations that may fail
    and collecting their results, stopping at the first failure encountered.

    Args:
        coros: An iterable of awaitables that return Result[T, E].

    Returns:
        Result[list[T], E]: Ok with list of all successful values if all succeed,
        otherwise the first Err encountered.

    Example:
        ```python
        import asyncio

        async def task(n: int) -> Result[int, ValueError]:
            if n < 0:
                return Err(ValueError("Negative number"))
            return Ok(n * 2)

        results = await gather_results([task(1), task(2), task(-1)])
        # results is Err(ValueError('Negative number'))
        ```
    """
    out: list[T] = []
    for c in coros:
        r = await c
        if isinstance(r, Ok):
            out.append(r.value)
        else:
            return r
    return Ok(out)


def unwrap[T, E: BaseException](r: Result[T, E]) -> T:
    """Unwrap a Result, returning the value if Ok or raising the error if Err.

    Args:
        r: The Result to unwrap.

    Returns:
        T: The contained value.

    Raises:
        E: The contained error if Err.
    """
    return r.unwrap()


def unwrap_err[T, E: BaseException](r: Result[T, E]) -> E:
    """Unwrap a Result, returning the error if Err or raising AssertionError if Ok.

    Args:
        r: The Result to unwrap.

    Returns:
        E: The contained error.

    Raises:
        AssertionError: If the Result is Ok.
    """
    return r.unwrap_err()


def unwrap_or[T, E: BaseException](r: Result[T, E], default: T) -> T:
    """Unwrap a Result or return a default value.

    Args:
        r: The Result to unwrap.
        default: The default value to return if Err.

    Returns:
        T: The contained value if Ok, otherwise the default.
    """
    return r.unwrap_or(default)


def unwrap_or_else[T, E: BaseException](r: Result[T, E], f: Callable[[E], T]) -> T:
    """Unwrap a Result or compute a default value from the error.

    Args:
        r: The Result to unwrap.
        f: A callable that takes the error and returns a default value.

    Returns:
        T: The contained value if Ok, otherwise the result of f(error).
    """
    return r.unwrap_or_else(f)


def expect[T, E: BaseException](r: Result[T, E], msg: str) -> T:
    """Unwrap a Result with a custom error message.

    Args:
        r: The Result to unwrap.
        msg: Custom error message to use if Err.

    Returns:
        T: The contained value.

    Raises:
        Exception: A new exception with the custom message if Err.
    """
    return r.expect(msg)


def expect_err[T, E: BaseException](r: Result[T, E], msg: str) -> E:
    """Unwrap a Result's error with a custom assertion message.

    Args:
        r: The Result to unwrap.
        msg: Custom assertion message (unused for Err).

    Returns:
        E: The contained error.

    Raises:
        AssertionError: If the Result is Ok.
    """
    return r.expect_err(msg)


# ---------------------------------------------------------------------
# Option / Maybe[T] — Rust-style Some / Nothing
# ---------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Some[T]:
    """Represents a present value of type T.

    This is the "present" variant of a Maybe[T], containing the actual value.

    Attributes:
        value: The present value.
    """

    value: T
    __match_args__ = ('value',)


@dataclass(slots=True, frozen=True)
class _Nothing:
    """Represents the absence of a value.

    This is the "absent" variant of a Maybe[T], indicating no value is present.
    This class is typically accessed through the Nothing singleton.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return 'Nothing'


Nothing: _Nothing = _Nothing()
"""Singleton instance representing the absence of a value."""
type Maybe[T] = Some[T] | _Nothing


def is_some[T](m: Maybe[T]) -> TypeGuard[Some[T]]:
    """Check if a Maybe contains a value.

    Args:
        m: The Maybe to check.

    Returns:
        bool: True if the Maybe contains a value, False if Nothing.
    """
    return isinstance(m, Some)


def is_nothing[T](m: Maybe[T]) -> TypeGuard[_Nothing]:
    """Check if a Maybe is Nothing (contains no value).

    Args:
        m: The Maybe to check.

    Returns:
        bool: True if the Maybe is Nothing, False if it contains a value.
    """
    return m is Nothing


def some[T](x: T) -> Maybe[T]:
    """Wrap a value in Some.

    Args:
        x: The value to wrap.

    Returns:
        Maybe[T]: A Some containing the value.
    """
    return Some(x)


def from_nullable[T](x: T | None) -> Maybe[T]:
    """Convert a nullable value to Maybe.

    Args:
        x: The value that may be None.

    Returns:
        Maybe[T]: Some(x) if x is not None, otherwise Nothing.
    """
    return Some(x) if x is not None else Nothing


def map_opt[T, U](m: Maybe[T], f: Callable[[T], U]) -> Maybe[U]:
    """Transform the value inside a Maybe if present.

    Args:
        m: The Maybe to transform.
        f: Function to apply to the value if present.

    Returns:
        Maybe[U]: Some with the transformed value if m was Some, otherwise Nothing.
    """
    return Some(f(m.value)) if is_some(m) else Nothing


def and_then_opt[T, U](m: Maybe[T], f: Callable[[T], Maybe[U]]) -> Maybe[U]:
    """Chain a computation that may return Nothing.

    Args:
        m: The Maybe to chain from.
        f: Function that takes the value and returns a Maybe.

    Returns:
        Maybe[U]: The result of applying f if m was Some, otherwise Nothing.
    """
    return f(m.value) if is_some(m) else Nothing


def filter_opt[T](m: Maybe[T], pred: Callable[[T], bool]) -> Maybe[T]:
    """Filter a Maybe based on a predicate.

    Args:
        m: The Maybe to filter.
        pred: Predicate function to test the value.

    Returns:
        Maybe[T]: m if it contains a value that satisfies pred, otherwise Nothing.
    """
    return m if is_some(m) and pred(m.value) else Nothing


def or_opt[T](m: Maybe[T], other: Maybe[T]) -> Maybe[T]:
    """Return m if it has a value, otherwise return other.

    Args:
        m: The primary Maybe.
        other: The fallback Maybe.

    Returns:
        Maybe[T]: m if it has a value, otherwise other.
    """
    return m if is_some(m) else other


def or_else_opt[T](m: Maybe[T], f: Callable[[], Maybe[T]]) -> Maybe[T]:
    """Return m if it has a value, otherwise call f and return its result.

    Args:
        m: The primary Maybe.
        f: Function to call if m is Nothing.

    Returns:
        Maybe[T]: m if it has a value, otherwise the result of f().
    """
    return m if is_some(m) else f()


def zip_opt[T, U](m1: Maybe[T], m2: Maybe[U]) -> Maybe[tuple[T, U]]:
    """Combine two Maybes into a Maybe of tuples if both have values.

    Args:
        m1: The first Maybe.
        m2: The second Maybe.

    Returns:
        Maybe[tuple[T, U]]: Some with tuple of values if both are Some, otherwise Nothing.
    """
    return Some((m1.value, m2.value)) if is_some(m1) and is_some(m2) else Nothing


def zip_with_opt[T, U, V](m1: Maybe[T], m2: Maybe[U], f: Callable[[T, U], V]) -> Maybe[V]:
    """Combine two Maybes with a function if both have values.

    Args:
        m1: The first Maybe.
        m2: The second Maybe.
        f: Function to combine the values.

    Returns:
        Maybe[V]: Some with the result of f if both are Some, otherwise Nothing.
    """
    return Some(f(m1.value, m2.value)) if is_some(m1) and is_some(m2) else Nothing


def unwrap_opt[T](m: Maybe[T]) -> T:
    """Unwrap a Maybe, returning the value if Some or raising ValueError if Nothing.

    Args:
        m: The Maybe to unwrap.

    Returns:
        T: The contained value.

    Raises:
        ValueError: If the Maybe is Nothing.
    """
    if is_some(m):
        return m.value
    raise ValueError('called unwrap() on Nothing')


def expect_opt[T](m: Maybe[T], msg: str) -> T:
    """Unwrap a Maybe with a custom error message.

    Args:
        m: The Maybe to unwrap.
        msg: Custom error message to use if Nothing.

    Returns:
        T: The contained value.

    Raises:
        ValueError: If the Maybe is Nothing.
    """
    if is_some(m):
        return m.value
    raise ValueError(msg)


def unwrap_or_opt[T](m: Maybe[T], default: T) -> T:
    """Unwrap a Maybe or return a default value.

    Args:
        m: The Maybe to unwrap.
        default: The default value to return if Nothing.

    Returns:
        T: The contained value if Some, otherwise the default.
    """
    return m.value if is_some(m) else default


def unwrap_or_else_opt[T](m: Maybe[T], f: Callable[[], T]) -> T:
    """Unwrap a Maybe or compute a default value.

    Args:
        m: The Maybe to unwrap.
        f: Function to compute the default if Nothing.

    Returns:
        T: The contained value if Some, otherwise the result of f().
    """
    return m.value if is_some(m) else f()


@overload
def ok_or[T, E: BaseException](m: Maybe[T], err: E) -> Result[T, E]: ...
@overload
def ok_or[T, E: BaseException](m: Maybe[T], err: Callable[[], E]) -> Result[T, E]: ...
def ok_or[T, E: BaseException](m: Maybe[T], err) -> Result[T, E]:
    """Convert a Maybe to a Result, providing an error for Nothing.

    Args:
        m: The Maybe to convert.
        err: The error to use if Nothing, either a value or a callable that returns an error.

    Returns:
        Result[T, E]: Ok with the value if Some, otherwise Err with the provided error.
    """
    if is_some(m):
        return Ok(m.value)
    e = err() if callable(err) else err
    return Err(e)


def ok_or_else[T, E: BaseException](m: Maybe[T], f: Callable[[], E]) -> Result[T, E]:
    """Convert a Maybe to a Result, computing an error for Nothing.

    Args:
        m: The Maybe to convert.
        f: Callable that returns an error if Nothing.

    Returns:
        Result[T, E]: Ok with the value if Some, otherwise Err with the result of f().
    """
    return Ok(m.value) if is_some(m) else Err(f())


def to_result[T, E: BaseException](m: Maybe[T], err: E) -> Result[T, E]:
    """Convert a Maybe to a Result (alias for ok_or with a value error).

    Args:
        m: The Maybe to convert.
        err: The error to use if Nothing.

    Returns:
        Result[T, E]: Ok with the value if Some, otherwise Err with err.
    """
    return ok_or(m, err)


def from_result[T, E: BaseException](r: Result[T, E]) -> Maybe[T]:
    """Convert a Result to a Maybe.

    Args:
        r: The Result to convert.

    Returns:
        Maybe[T]: Some with the value if Ok, otherwise Nothing.
    """
    return Some(r.value) if isinstance(r, Ok) else Nothing


def sequence_opt[T](xs: Iterable[Maybe[T]]) -> Maybe[list[T]]:
    """Collect values from an iterable of Maybes, short-circuiting on Nothing.

    Args:
        xs: An iterable of Maybe instances.

    Returns:
        Maybe[list[T]]: Some with list of values if all are Some, otherwise Nothing.
    """
    out: list[T] = []
    for m in xs:
        if is_some(m):
            out.append(m.value)
        else:
            return Nothing
    return Some(out)


def traverse_opt[U, T](xs: Iterable[U], f: Callable[[U], Maybe[T]]) -> Maybe[list[T]]:
    """Map a function over an iterable and collect the results, short-circuiting on Nothing.

    Args:
        xs: An iterable of values to map over.
        f: Function that takes a value and returns a Maybe.

    Returns:
        Maybe[list[T]]: Some with list of mapped values if all succeed, otherwise Nothing.
    """
    return sequence_opt(f(x) for x in xs)


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

__all__ = [
    'Err',
    'Maybe',
    'Nothing',
    # Result
    'Ok',
    'Result',
    # Option
    'Some',
    'and_',
    'and_then',
    'and_then_opt',
    'async_safe',
    'expect',
    'expect_err',
    'expect_opt',
    'filter_opt',
    'from_nullable',
    'from_result',
    'gather_results',
    'inspect',
    'inspect_err',
    'is_err',
    'is_nothing',
    'is_ok',
    'is_some',
    'map',
    'map_err',
    'map_opt',
    'ok_or',
    'ok_or_else',
    'or_',
    'or_else',
    'or_else_opt',
    'or_opt',
    'partition_results',
    'safe',
    'sequence',
    'sequence_opt',
    'some',
    'to_result',
    'traverse',
    'traverse_opt',
    'unwrap',
    'unwrap_err',
    'unwrap_opt',
    'unwrap_or',
    'unwrap_or_else',
    'unwrap_or_else_opt',
    'unwrap_or_opt',
    'zip_opt',
    'zip_with_opt',
]
