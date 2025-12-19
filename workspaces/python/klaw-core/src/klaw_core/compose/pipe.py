"""pipe() function for composing functions over Result/Option values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, overload

from klaw_core.option import NothingType, Some
from klaw_core.result import Err, Ok

__all__ = ['pipe']

T = TypeVar('T')
T1 = TypeVar('T1')
T2 = TypeVar('T2')
T3 = TypeVar('T3')
T4 = TypeVar('T4')
T5 = TypeVar('T5')
T6 = TypeVar('T6')
T7 = TypeVar('T7')
T8 = TypeVar('T8')


def _is_result_or_option(value: object) -> bool:
    """Check if a value is already a Result or Option type."""
    return isinstance(value, Ok | Err | Some | NothingType)


def _wrap_value[T](value: T) -> Ok[T] | T:
    """Wrap a value in Ok if it's not already a Result/Option."""
    if _is_result_or_option(value):
        return value  # type: ignore[return-value]
    return Ok(value)


def _apply_fn[T, U](value: T, fn: Callable[[T], U]) -> Ok[U] | Err[Any] | Some[U] | NothingType:
    """Apply a function to a value and wrap the result appropriately.

    If value is Err or Nothing, returns it unchanged (short-circuit).
    If value is Ok or Some, applies fn to the unwrapped value.
    If fn returns a Result/Option, returns it directly (no double-wrapping).
    Otherwise, wraps the result in the same container type as input.
    """
    if isinstance(value, Err):
        return value
    if isinstance(value, NothingType):
        return value

    if isinstance(value, Ok):
        result = fn(value.value)
        if _is_result_or_option(result):
            return result  # type: ignore[return-value]
        return Ok(result)

    if isinstance(value, Some):
        result = fn(value.value)
        if _is_result_or_option(result):
            return result  # type: ignore[return-value]
        return Some(result)

    # Plain value - apply fn and wrap in Ok
    result = fn(value)
    if _is_result_or_option(result):
        return result  # type: ignore[return-value]
    return Ok(result)


# Overloads for type inference (up to 8 functions)
@overload
def pipe[T](value: T) -> Ok[T]: ...
@overload
def pipe(value: T, fn1: Callable[[T], T1], /) -> Ok[T1] | Err[Any]: ...
@overload
def pipe(value: T, fn1: Callable[[T], T1], fn2: Callable[[T1], T2], /) -> Ok[T2] | Err[Any]: ...
@overload
def pipe(
    value: T, fn1: Callable[[T], T1], fn2: Callable[[T1], T2], fn3: Callable[[T2], T3], /
) -> Ok[T3] | Err[Any]: ...
@overload
def pipe(
    value: T,
    fn1: Callable[[T], T1],
    fn2: Callable[[T1], T2],
    fn3: Callable[[T2], T3],
    fn4: Callable[[T3], T4],
    /,
) -> Ok[T4] | Err[Any]: ...
@overload
def pipe(
    value: T,
    fn1: Callable[[T], T1],
    fn2: Callable[[T1], T2],
    fn3: Callable[[T2], T3],
    fn4: Callable[[T3], T4],
    fn5: Callable[[T4], T5],
    /,
) -> Ok[T5] | Err[Any]: ...
@overload
def pipe(
    value: T,
    fn1: Callable[[T], T1],
    fn2: Callable[[T1], T2],
    fn3: Callable[[T2], T3],
    fn4: Callable[[T3], T4],
    fn5: Callable[[T4], T5],
    fn6: Callable[[T5], T6],
    /,
) -> Ok[T6] | Err[Any]: ...
@overload
def pipe(
    value: T,
    fn1: Callable[[T], T1],
    fn2: Callable[[T1], T2],
    fn3: Callable[[T2], T3],
    fn4: Callable[[T3], T4],
    fn5: Callable[[T4], T5],
    fn6: Callable[[T5], T6],
    fn7: Callable[[T6], T7],
    /,
) -> Ok[T7] | Err[Any]: ...
@overload
def pipe(
    value: T,
    fn1: Callable[[T], T1],
    fn2: Callable[[T1], T2],
    fn3: Callable[[T2], T3],
    fn4: Callable[[T3], T4],
    fn5: Callable[[T4], T5],
    fn6: Callable[[T5], T6],
    fn7: Callable[[T6], T7],
    fn8: Callable[[T7], T8],
    /,
) -> Ok[T8] | Err[Any]: ...


def pipe(value: Any, *fns: Callable[..., Any]) -> Any:
    """Compose functions in sequence, threading a value through them.

    The initial value is wrapped in Ok() if not already a Result/Option.
    Each function is applied to the unwrapped value from the previous step.
    Short-circuits on Err or Nothing.
    If a function returns a Result/Option, it's used directly (no double-wrapping).

    Args:
        value: The initial value to thread through the functions.
        *fns: Functions to apply in sequence.

    Returns:
        The final Result/Option after applying all functions.

    Example:
        ```python
        pipe(5, lambda x: x + 1, lambda x: x * 2)
        # Ok(value=12)

        pipe(Ok(5), lambda x: x + 1, str)
        # Ok(value='6')

        pipe(5, lambda x: Err("fail"), lambda x: x + 1)
        # Err(error='fail')

        pipe(Some(3), lambda x: x * 2)
        # Some(value=6)
        ```
    """
    if not fns:
        return _wrap_value(value)

    current: Any = value
    for fn in fns:
        current = _apply_fn(current, fn)
        # Short-circuit on Err or Nothing
        if isinstance(current, Err | NothingType):
            return current

    return current
