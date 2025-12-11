from __future__ import annotations

import inspect as _inspect
import operator as _op
from typing import (
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    ParamSpec,
    Self,
    TypeIs,
    Never,
    overload,
    get_origin,
    get_args,
)

import msgspec
import msgspec.inspect as _insp
import wrapt

# ---------------------------------------------------------------------
# Common typing / helpers
# ---------------------------------------------------------------------
ErrorLike = BaseException | str
P = ParamSpec("P")

# Default combiners for __add__/__iadd__ on Result/Option (both sides successful).
_RESULT_COMBINE: Callable[[object, object], object] = _op.add
_OPTION_COMBINE: Callable[[object, object], object] = _op.add


def set_result_combiner(f: Callable[[object, object], object]) -> None:
    """Set the combiner used by Result.__add__/__iadd__ when both sides are Ok."""
    global _RESULT_COMBINE
    _RESULT_COMBINE = f


def set_option_combiner(f: Callable[[object, object], object]) -> None:
    """Set the combiner used by Option.__add__/__iadd__ when both sides are Some."""
    global _OPTION_COMBINE
    _OPTION_COMBINE = f


# ---------------------------------------------------------------------
# Result[T, E] — base + variants
# ---------------------------------------------------------------------
class Result[+T, -E: ErrorLike = Exception]:
    """Discriminated union: Ok[T, E] | Err[T, E]."""

    # forbid truthiness to avoid 'if r:' footguns
    def __bool__(self) -> Never:
        raise TypeError("Result has no truth value; use .is_ok() / .is_err().")

    # Rust-like iteration: Ok(v) yields one, Err(_) yields none
    def __iter__(self) -> Iterator[T]:
        if self.is_ok():
            yield self.unwrap()

    # predicates (narrowing)
    def is_ok(self) -> TypeIs["Ok[T, E]"]: ...
    def is_err(self) -> TypeIs["Err[T, E]"]: ...
    def is_ok_and(self, pred: Callable[[T], bool]) -> bool: ...
    def is_err_and(self, pred: Callable[[E], bool]) -> bool: ...

    # unwraps
    def unwrap(self) -> T: ...
    def unwrap_err(self) -> E: ...
    def expect(self, msg: str) -> T: ...
    def expect_err(self, msg: str) -> E: ...
    def unwrap_or(self, default: T) -> T: ...
    def unwrap_or_else(self, f: Callable[[E], T]) -> T: ...
    def unwrap_or_default(
        self,
        default_factory: Optional[Callable[[], T]] = None,
        /,
        *,
        default_type: Optional[type[T]] = None,
    ) -> T: ...
    def unwrap_unchecked(self) -> T: ...

    # transforms
    def map[U](self, f: Callable[[T], U]) -> Result[U, E]: ...
    def and_then[U](self, f: Callable[[T], Result[U, E]]) -> Result[U, E]: ...
    def map_err[F: ErrorLike](self, f: Callable[[E], F]) -> Result[T, F]: ...
    def or_else[F: ErrorLike](self, f: Callable[[E], Result[T, F]]) -> Result[T, F]: ...
    def inspect(self, f: Callable[[T], object]) -> Self: ...
    def inspect_err(self, f: Callable[[E], object]) -> Self: ...
    def pipe[U](self, f: Callable[[T], U]) -> Result[U, E]: ...
    # Rust parity helpers
    def and_[U](self, other: "Result[U, E]") -> "Result[U, E]": ...
    def or_(self, other: "Result[T, E]") -> "Result[T, E]": ...
    def map_or[U](self, default: U, f: Callable[[T], U]) -> U: ...
    def map_or_else[U](self, default_fn: Callable[[E], U], f: Callable[[T], U]) -> U: ...
    def contains(self, x: T) -> bool: ...
    def contains_err(self, e: E) -> bool: ...

    # --- Operator sugar ---
    # pair successes; otherwise the first error short-circuits
    def __and__[U](self, other: "Result[U, E]") -> "Result[tuple[T, U], E]": ...
    def __rand__[U](self, other: "Result[U, E]") -> "Result[tuple[U, T], E]": ...
    # fallback to first success
    def __or__(self, other: "Result[T, E]") -> "Result[T, E]": ...
    def __ror__(self, other: "Result[T, E]") -> "Result[T, E]": ...
    # exclusive success: exactly one Ok (fail fast: left Err wins if both Err)
    def __xor__[U](self, other: "Result[U, E]") -> "Result[T | U, E | ValueError]": ...
    def __rxor__[U](self, other: "Result[U, E]") -> "Result[U | T, E | ValueError]": ...
    # monoidal combine via global combiner (both Ok)
    def __add__(self, other: "Result[T, E]") -> "Result[T, E]": ...
    def __radd__(self, other: "Result[T, E]") -> "Result[T, E]": ...
    # in-place variants (immutability-friendly: return new values)
    def __iadd__(self, other: "Result[T, E]") -> "Result[T, E]": ...
    def __iand__[U](self, other: "Result[U, E]") -> "Result[tuple[T, U], E]": ...
    def __ior__(self, other: "Result[T, E]") -> "Result[T, E]": ...
    def __ixor__[U](self, other: "Result[U, E]") -> "Result[T | U, E | ValueError]": ...

    # conversions
    def into_option(self) -> "Option[T]":
        return Some(self.unwrap()) if self.is_ok() else NOTHING

    def into_err(self) -> Optional[E]:
        return self.unwrap_err() if self.is_err() else None

    def ok(self) -> "Option[T]":
        return self.into_option()

    def err(self) -> "Option[E]":
        e = self.into_err()
        return Some(e) if e is not None else NOTHING

    def iter_ok(self) -> Iterator[T]:
        return iter(self)

    def iter_err(self) -> Iterator[E]:
        if self.is_err():
            yield self.unwrap_err()


class Ok(msgspec.Struct, Result[T, E], frozen=True):
    value: T

    # tagged-union encoding
    def __msgspec_encode__(self) -> dict[str, T]:
        return {"Ok": self.value}

    # predicates
    def is_ok(self) -> TypeIs["Ok[T, E]"]: return True
    def is_err(self) -> TypeIs["Err[T, E]"]: return False
    def is_ok_and(self, pred: Callable[[T], bool]) -> bool: return pred(self.value)
    def is_err_and(self, pred: Callable[[E], bool]) -> bool: return False

    # unwraps
    def unwrap(self) -> T: return self.value
    def unwrap_err(self) -> Never: raise RuntimeError("unwrap_err() on Ok")
    def expect(self, msg: str) -> T: return self.value
    def expect_err(self, msg: str) -> Never: raise RuntimeError(msg)
    def unwrap_or(self, default: T) -> T: return self.value
    def unwrap_or_else(self, f: Callable[[E], T]) -> T: return self.value
    def unwrap_or_default(
        self,
        default_factory: Optional[Callable[[], T]] = None,
        /,
        *,
        default_type: Optional[type[T]] = None,
    ) -> T:
        return self.value
    def unwrap_unchecked(self) -> T: return self.value  # safe here

    # transforms
    def map[U](self, f: Callable[[T], U]) -> Ok[U, E]: return Ok(f(self.value))
    def and_then[U](self, f: Callable[[T], Result[U, E]]) -> Result[U, E]: return f(self.value)
    def map_err[F: ErrorLike](self, f: Callable[[E], F]) -> Ok[T, F]: return Ok(self.value)
    def or_else[F: ErrorLike](self, f: Callable[[E], Result[T, F]]) -> Ok[T, F]: return Ok(self.value)
    def inspect(self, f: Callable[[T], object]) -> Self: f(self.value); return self
    def inspect_err(self, f: Callable[[E], object]) -> Self: return self
    def pipe[U](self, f: Callable[[T], U]) -> Ok[U, E]: return Ok(f(self.value))

    # Rust parity helpers
    def and_[U](self, other: Result[U, E]) -> Result[U, E]: return other
    def or_(self, other: Result[T, E]) -> Result[T, E]: return self
    def map_or[U](self, default: U, f: Callable[[T], U]) -> U: return f(self.value)
    def map_or_else[U](self, default_fn: Callable[[E], U], f: Callable[[T], U]) -> U: return f(self.value)
    def contains(self, x: T) -> bool: return self.value == x
    def contains_err(self, e: E) -> bool: return False

    # --- Operator sugar ---
    def __and__[U](self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        return other.map(lambda u: (self.value, u))
    def __rand__[U](self, other: Result[U, E]) -> Result[tuple[U, T], E]:
        return other.map(lambda u: (u, self.value))
    def __or__(self, other: Result[T, E]) -> Result[T, E]:
        return self
    def __ror__(self, other: Result[T, E]) -> Result[T, E]:
        return other if other.is_ok() else self
    # xor: exactly one Ok (other must be Err)
    def __xor__[U](self, other: Result[U, E]) -> Result[T | U, E | ValueError]:
        if other.is_err():
            return self
        return Err(ValueError("exclusive success violated: both Ok"))
    def __rxor__[U](self, other: Result[U, E]) -> Result[U | T, E | ValueError]:
        if other.is_err():
            return self
        return Err(ValueError("exclusive success violated: both Ok"))
    # + / iadd: combine Ok values via global combiner; propagate Err otherwise
    def __add__(self, other: Result[T, E]) -> Result[T, E]:
        if other.is_err():
            return other
        try:
            return Ok(_RESULT_COMBINE(self.value, other.unwrap()))
        except BaseException as e:
            return Err(e)  # type: ignore[call-arg]
    def __radd__(self, other: Result[T, E]) -> Result[T, E]:
        if other.is_err():
            return other
        try:
            return Ok(_RESULT_COMBINE(other.unwrap(), self.value))
        except BaseException as e:
            return Err(e)  # type: ignore[call-arg]
    def __iadd__(self, other: Result[T, E]) -> Result[T, E]:
        return self.__add__(other)
    # in-place mirrors for &, |, ^
    def __iand__[U](self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        return self.__and__(other)
    def __ior__(self, other: Result[T, E]) -> Result[T, E]:
        return self.__or__(other)
    def __ixor__[U](self, other: Result[U, E]) -> Result[T | U, E | ValueError]:
        return self.__xor__(other)


class Err(msgspec.Struct, Result[T, E], frozen=True):
    error: E

    # tagged-union encoding
    def __msgspec_encode__(self) -> dict[str, E]:
        return {"Err": self.error}

    # predicates
    def is_ok(self) -> TypeIs["Ok[T, E]"]: return False
    def is_err(self) -> TypeIs["Err[T, E]"]: return True
    def is_ok_and(self, pred: Callable[[T], bool]) -> bool: return False
    def is_err_and(self, pred: Callable[[E], bool]) -> bool: return pred(self.error)

    # unwraps
    def unwrap(self) -> Never: raise RuntimeError(f"unwrap() on Err: {self.error!r}")
    def unwrap_err(self) -> E: return self.error
    def expect(self, msg: str) -> Never: raise RuntimeError(f"{msg}: {self.error!r}")
    def expect_err(self, msg: str) -> E: return self.error
    def unwrap_or(self, default: T) -> T: return default
    def unwrap_or_else(self, f: Callable[[E], T]) -> T: return f(self.error)
    def unwrap_or_default(
        self,
        default_factory: Optional[Callable[[], T]] = None,
        /,
        *,
        default_type: Optional[type[T]] = None,
    ) -> T:
        if default_factory is not None:
            return default_factory()
        if default_type is not None:
            try:
                return default_type()
            except Exception as e:
                raise TypeError(f"default_type {default_type!r} is not default-constructible") from e
        raise TypeError(
            "unwrap_or_default() on Err has no default; pass default_factory, or default_type=Type, "
            "or use unwrap_or(default)"
        )
    def unwrap_unchecked(self) -> Never: raise AttributeError("unwrap_unchecked() on Err")

    # transforms
    def map[U](self, f: Callable[[T], U]) -> Err[U, E]: return Err(self.error)
    def and_then[U](self, f: Callable[[T], Result[U, E]]) -> Err[U, E]: return Err(self.error)
    def map_err[F: ErrorLike](self, f: Callable[[E], F]) -> Err[T, F]: return Err(f(self.error))
    def or_else[F: ErrorLike](self, f: Callable[[E], Result[T, F]]) -> Result[T, F]: return f(self.error)
    def inspect(self, f: Callable[[T], object]) -> Self: return self
    def inspect_err(self, f: Callable[[E], object]) -> Self: f(self.error); return self
    def pipe[U](self, f: Callable[[T], U]) -> Err[U, E]: return Err(self.error)

    # Rust parity helpers
    def and_[U](self, other: Result[U, E]) -> Result[U, E]: return self
    def or_(self, other: Result[T, E]) -> Result[T, E]: return other
    def map_or[U](self, default: U, f: Callable[[T], U]) -> U: return default
    def map_or_else[U](self, default_fn: Callable[[E], U], f: Callable[[T], U]) -> U: return default_fn(self.error)
    def contains(self, x: T) -> bool: return False
    def contains_err(self, e: E) -> bool: return self.error == e

    # --- Operator sugar ---
    def __and__[U](self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        return self
    def __rand__[U](self, other: Result[U, E]) -> Result[tuple[U, T], E]:
        return other if other.is_err() else self
    def __or__(self, other: Result[T, E]) -> Result[T, E]:
        return other
    def __ror__(self, other: Result[T, E]) -> Result[T, E]:
        return other if other.is_ok() else self
    # xor: fail fast on left error; one Ok wins
    def __xor__[U](self, other: Result[U, E]) -> Result[T | U, E | ValueError]:
        return other if other.is_ok() else self  # both Err -> self (left)
    def __rxor__[U](self, other: Result[U, E]) -> Result[U | T, E | ValueError]:
        return other if other.is_ok() else other  # both Err -> other (left of rxor)
    # + / iadd: propagate error
    def __add__(self, other: Result[T, E]) -> Result[T, E]:
        return self
    def __radd__(self, other: Result[T, E]) -> Result[T, E]:
        return other
    def __iadd__(self, other: Result[T, E]) -> Result[T, E]:
        return self
    # in-place mirrors for &, |, ^
    def __iand__[U](self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        return self.__and__(other)
    def __ior__(self, other: Result[T, E]) -> Result[T, E]:
        return self.__or__(other)
    def __ixor__[U](self, other: Result[U, E]) -> Result[T | U, E | ValueError]:
        return self.__xor__(other)


# constructors & helpers
def ok[T](value: T) -> Ok[T, Exception]: return Ok(value)
def err[E: ErrorLike](error: E) -> Err[Never, E]: return Err(error)


def try_catch[T, E: ErrorLike](
    fn: Callable[P, T], /, *args: P.args,
    map_err: Callable[[BaseException], E] = lambda e: e,
    **kwargs: P.kwargs,
) -> Result[T, E]:
    try:
        return Ok(fn(*args, **kwargs))
    except BaseException as e:
        return Err(map_err(e))


async def atry_catch[T, E: ErrorLike](
    fn: Callable[P, Awaitable[T]], /, *args: P.args,
    map_err: Callable[[BaseException], E] = lambda e: e,
    **kwargs: P.kwargs,
) -> Result[T, E]:
    try:
        return Ok(await fn(*args, **kwargs))
    except BaseException as e:
        return Err(map_err(e))


def sequence[T, E: ErrorLike](results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    acc: list[T] = []
    for r in results:
        if r.is_err():
            return Err(r.unwrap_err())
        acc.append(r.unwrap())
    return Ok(acc)


def traverse[U, T, E: ErrorLike](items: Iterable[U], f: Callable[[U], Result[T, E]]) -> Result[list[T], E]:
    return sequence(f(x) for x in items)


def zip_ok[A, B, E: ErrorLike](a: Result[A, E], b: Result[B, E]) -> Result[tuple[A, B], E]:
    return a.and_then(lambda va: b.map(lambda vb: (va, vb)))


def zip3[A, B, C, E: ErrorLike](
    r1: Result[A, E], r2: Result[B, E], r3: Result[C, E]
) -> Result[tuple[A, B, C], E]:
    if r1.is_err(): return Err(r1.unwrap_err())
    if r2.is_err(): return Err(r2.unwrap_err())
    if r3.is_err(): return Err(r3.unwrap_err())
    return Ok((r1.unwrap(), r2.unwrap(), r3.unwrap()))


def zip4[A, B, C, D, E: ErrorLike](
    r1: Result[A, E], r2: Result[B, E], r3: Result[C, E], r4: Result[D, E]
) -> Result[tuple[A, B, C, D], E]:
    if r1.is_err(): return Err(r1.unwrap_err())
    if r2.is_err(): return Err(r2.unwrap_err())
    if r3.is_err(): return Err(r3.unwrap_err())
    if r4.is_err(): return Err(r4.unwrap_err())
    return Ok((r1.unwrap(), r2.unwrap(), r3.unwrap(), r4.unwrap()))


# ---------------------------------------------------------------------
# Option[T] — base + variants
# ---------------------------------------------------------------------
class Option[+T]:
    """Discriminated union: Some[T] | Nothing."""

    def __bool__(self) -> Never:
        raise TypeError("Option has no truth value; use .is_some() / .is_nothing().")

    def __iter__(self) -> Iterator[T]:
        if self.is_some():
            yield self.unwrap()

    # predicates
    def is_some(self) -> TypeIs["Some[T]"]: ...
    def is_nothing(self) -> TypeIs["Nothing"]: ...

    # unwraps
    def unwrap(self) -> T: ...
    def expect(self, msg: str) -> T: ...
    def unwrap_or(self, default: T) -> T: ...
    def unwrap_or_else(self, f: Callable[[], T]) -> T: ...
    def unwrap_or_default(
        self,
        default_factory: Optional[Callable[[], T]] = None,
        /,
        *,
        default_type: Optional[type[T]] = None,
    ) -> T: ...
    def unwrap_unchecked(self) -> T: ...

    # combinators
    def map[U](self, f: Callable[[T], U]) -> Option[U]: ...
    def and_then[U](self, f: Callable[[T], Option[U]]) -> Option[U]: ...
    def filter(self, pred: Callable[[T], bool]) -> Option[T]: ...
    def or_(self, other: Option[T]) -> Option[T]: ...
    def or_else(self, f: Callable[[], Option[T]]) -> Option[T]: ...
    def zip[U](self, other: Option[U]) -> Option[tuple[T, U]]: ...

    # --- Operator sugar (Option) ---
    def __and__[U](self, other: "Option[U]") -> "Option[tuple[T, U]]": ...
    def __rand__[U](self, other: "Option[U]") -> "Option[tuple[U, T]]": ...
    def __or__(self, other: "Option[T]") -> "Option[T]": ...
    def __ror__(self, other: "Option[T]") -> "Option[T]": ...
    # exclusive presence: exactly one Some
    def __xor__[U](self, other: "Option[U]") -> "Option[T | U]": ...
    def __rxor__[U](self, other: "Option[U]") -> "Option[U | T]": ...
    # monoidal combine for Some via global combiner
    def __add__(self, other: "Option[T]") -> "Option[T]": ...
    def __radd__(self, other: "Option[T]") -> "Option[T]": ...
    # in-place variants (return new values)
    def __iadd__(self, other: "Option[T]") -> "Option[T]": ...
    def __iand__[U](self, other: "Option[U]") -> "Option[tuple[T, U]]": ...
    def __ior__(self, other: "Option[T]") -> "Option[T]": ...
    def __ixor__[U](self, other: "Option[U]") -> "Option[T | U]": ...

    # interop
    def into_optional(self) -> Optional[T]: ...
    def ok_or[E: ErrorLike](self, error: E) -> Result[T, E]: ...
    def ok_or_else[E: ErrorLike](self, f: Callable[[], E]) -> Result[T, E]: ...
    def to_result[E: ErrorLike](self, error: E) -> Result[T, E]: return self.ok_or(error)


class Some(msgspec.Struct, Option[T], frozen=True):
    value: T

    def __msgspec_encode__(self) -> dict[str, T]:
        return {"Some": self.value}

    def is_some(self) -> TypeIs["Some[T]"]: return True
    def is_nothing(self) -> TypeIs["Nothing"]: return False

    def unwrap(self) -> T: return self.value
    def expect(self, msg: str) -> T: return self.value
    def unwrap_or(self, default: T) -> T: return self.value
    def unwrap_or_else(self, f: Callable[[], T]) -> T: return self.value
    def unwrap_or_default(
        self,
        default_factory: Optional[Callable[[], T]] = None,
        /,
        *,
        default_type: Optional[type[T]] = None,
    ) -> T:
        return self.value
    def unwrap_unchecked(self) -> T: return self.value

    def map[U](self, f: Callable[[T], U]) -> Some[U]: return Some(f(self.value))
    def and_then[U](self, f: Callable[[T], Option[U]]) -> Option[U]: return f(self.value)
    def filter(self, pred: Callable[[T], bool]) -> Option[T]: return self if pred(self.value) else NOTHING
    def or_(self, other: Option[T]) -> Option[T]: return self
    def or_else(self, f: Callable[[], Option[T]]) -> Option[T]: return self
    def zip[U](self, other: Option[U]) -> Option[tuple[T, U]]:
        return other.map(lambda u: (self.value, u))

    # --- Operator sugar (Option) ---
    def __and__[U](self, other: Option[U]) -> Option[tuple[T, U]]:
        return other.map(lambda u: (self.value, u))
    def __rand__[U](self, other: Option[U]) -> Option[tuple[U, T]]:
        return other.map(lambda u: (u, self.value))
    def __or__(self, other: Option[T]) -> Option[T]:
        return self
    def __ror__(self, other: Option[T]) -> Option[T]:
        return other if other.is_some() else self
    # xor: exactly one Some
    def __xor__[U](self, other: Option[U]) -> Option[T | U]:
        return self if other.is_nothing() else NOTHING
    def __rxor__[U](self, other: Option[U]) -> Option[U | T]:
        return self if other.is_nothing() else NOTHING
    # + / iadd: combine Some values via global combiner
    def __add__(self, other: Option[T]) -> Option[T]:
        if other.is_nothing():
            return self
        try:
            return Some(_OPTION_COMBINE(self.value, other.unwrap()))
        except BaseException:
            return NOTHING
    def __radd__(self, other: Option[T]) -> Option[T]:
        if other.is_nothing():
            return self
        try:
            return Some(_OPTION_COMBINE(other.unwrap(), self.value))
        except BaseException:
            return NOTHING
    def __iadd__(self, other: Option[T]) -> Option[T]:
        return self.__add__(other)
    # in-place mirrors for &, |, ^
    def __iand__[U](self, other: Option[U]) -> Option[tuple[T, U]]:
        return self.__and__(other)
    def __ior__(self, other: Option[T]) -> Option[T]:
        return self.__or__(other)
    def __ixor__[U](self, other: Option[U]) -> Option[T | U]:
        return self.__xor__(other)

    # interop
    def into_optional(self) -> Optional[T]: return self.value
    def ok_or[E: ErrorLike](self, error: E) -> Result[T, E]: return Ok(self.value)
    def ok_or_else[E: ErrorLike](self, f: Callable[[], E]) -> Result[T, E]: return Ok(self.value)


class Nothing(msgspec.Struct, Option[Never], frozen=True):
    def __msgspec_encode__(self) -> dict[str, None]:
        return {"Nothing": None}

    def is_some(self) -> TypeIs["Some[Never]"]: return False
    def is_nothing(self) -> TypeIs["Nothing"]: return True

    def unwrap(self) -> Never: raise RuntimeError("unwrap() on Nothing")
    def expect(self, msg: str) -> Never: raise RuntimeError(msg)
    def unwrap_or[T](self, default: T) -> T: return default
    def unwrap_or_else[T](self, f: Callable[[], T]) -> T: return f()
    def unwrap_or_default[
        T
    ](
        self,
        default_factory: Optional[Callable[[], T]] = None,
        /,
        *,
        default_type: Optional[type[T]] = None,
    ) -> T:
        if default_factory is not None:
            return default_factory()
        if default_type is not None:
            try:
                return default_type()
            except Exception as e:
                raise TypeError(f"default_type {default_type!r} is not default-constructible") from e
        raise TypeError(
            "unwrap_or_default() on Nothing has no default; pass default_factory, or default_type=Type, "
            "or use unwrap_or(default)"
        )
    def unwrap_unchecked(self) -> Never: raise AttributeError("unwrap_unchecked() on Nothing")

    def map[U](self, f: Callable[[Never], U]) -> "Nothing": return self
    def and_then[U](self, f: Callable[[Never], Option[U]]) -> "Nothing": return self
    def filter(self, pred: Callable[[Never], bool]) -> "Nothing": return self
    def or_[T](self, other: Option[T]) -> Option[T]: return other
    def or_else[T](self, f: Callable[[], Option[T]]) -> Option[T]: return f()
    def zip[U](self, other: Option[U]) -> "Nothing": return self

    # --- Operator sugar (Option) ---
    def __and__[U](self, other: Option[U]) -> "Nothing":
        return self
    def __rand__[U](self, other: Option[U]) -> "Nothing":
        return other if other.is_nothing() else self
    def __or__(self, other: Option[T]) -> Option[T]:
        return other
    def __ror__(self, other: Option[T]) -> Option[T]:
        return other if other.is_some() else self
    # xor / + / iadd identities
    def __xor__[U](self, other: Option[U]) -> Option[U]:
        return other
    def __rxor__[U](self, other: Option[U]) -> Option[U]:
        return other
    def __add__(self, other: Option[T]) -> Option[T]:
        return other
    def __radd__(self, other: Option[T]) -> Option[T]:
        return other
    def __iadd__(self, other: Option[T]) -> Option[T]:
        return other
    # in-place mirrors for &, |, ^
    def __iand__[U](self, other: Option[U]) -> "Nothing":
        return self.__and__(other)
    def __ior__(self, other: Option[T]) -> Option[T]:
        return self.__or__(other)
    def __ixor__[U](self, other: Option[U]) -> Option[U]:
        return self.__xor__(other)

    # interop
    def into_optional(self) -> None: return None
    def ok_or[E: ErrorLike](self, error: E) -> Result[Never, E]: return Err(error)
    def ok_or_else[E: ErrorLike](self, f: Callable[[], E]) -> Result[Never, E]: return Err(f())


# public singleton
NOTHING = Nothing()


def some[T](value: T) -> Some[T]: return Some(value)
def nothing() -> Nothing: return NOTHING
def option_from_optional[T](value: Optional[T]) -> Option[T]:
    return Some(value) if value is not None else NOTHING


# ---------------------------------------------------------------------
# wrapt-powered decorators (+ optional signature adapters)
# ---------------------------------------------------------------------
def with_signature(proto: Callable[..., object]):
    """Create a wrapt signature adapter (optional nicety for IDEs/Docs).

    Example:
        def proto(x: int) -> Result[int, str]: ...
        @wrap_result[str, int](adapter=with_signature(proto))
        def f(x: int) -> int: ...
    """
    return wrapt.adapter_factory(proto)  # type: ignore[no-any-return]


def wrap_result[E: ErrorLike, T](
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    map_err: Callable[[BaseException], E] = lambda e: e,
    adapter=None,  # optional wrapt.adapter_factory(...) for advertised signature
) -> Callable[[Callable[P, T]], Callable[P, Result[T, E]]]:
    @wrapt.decorator(adapter=adapter)
    def _wrapper(wrapped, instance, args, kwargs):
        try:
            return Ok(wrapped(*args, **kwargs))
        except exceptions as e:
            return Err(map_err(e))
    return _wrapper  # type: ignore[return-value]


def awrap_result[E: ErrorLike, T](
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    map_err: Callable[[BaseException], E] = lambda e: e,
    adapter=None,  # optional adapter for async signatures
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Result[T, E]]]]:
    @wrapt.decorator(adapter=adapter)
    async def _wrapper(wrapped, instance, args, kwargs):
        try:
            return Ok(await wrapped(*args, **kwargs))
        except exceptions as e:
            return Err(map_err(e))
    return _wrapper  # type: ignore[return-value]


@overload
def wrap_result_auto[E: ErrorLike, T](
    *,
    exceptions: tuple[type[BaseException], ...] = ...,
    map_err: Callable[[BaseException], E] = ...,
    adapter=None,
    adapter_async=None,
) -> Callable[[Callable[P, T]], Callable[P, Result[T, E]]]: ...
@overload
def wrap_result_auto[E: ErrorLike, T](
    *,
    exceptions: tuple[type[BaseException], ...] = ...,
    map_err: Callable[[BaseException], E] = ...,
    adapter=None,
    adapter_async=None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Result[T, E]]]]: ...
def wrap_result_auto[E: ErrorLike, T](
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    map_err: Callable[[BaseException], E] = lambda e: e,
    adapter=None,
    adapter_async=None,
):
    """Decorator that auto-picks sync/async wrapper; optional adapters for each."""
    def _decorator(fn):
        if _inspect.iscoroutinefunction(fn):
            return awrap_result[E, T](exceptions=exceptions, map_err=map_err, adapter=adapter_async)(fn)
        return wrap_result[E, T](exceptions=exceptions, map_err=map_err, adapter=adapter)(fn)
    return _decorator


def wrap_option[T](
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    adapter=None,
) -> Callable[[Callable[P, T]], Callable[P, Option[T]]]:
    @wrapt.decorator(adapter=adapter)
    def _wrapper(wrapped, instance, args, kwargs):
        try:
            return Some(wrapped(*args, **kwargs))
        except exceptions:
            return NOTHING
    return _wrapper  # type: ignore[return-value]


def awrap_option[T](
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    adapter=None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Option[T]]]]:
    @wrapt.decorator(adapter=adapter)
    async def _wrapper(wrapped, instance, args, kwargs):
        try:
            return Some(await wrapped(*args, **kwargs))
        except exceptions:
            return NOTHING
    return _wrapper  # type: ignore[return-value]


def patch_resultize(
    module,
    name: str,
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    map_err: Callable[[BaseException], ErrorLike] = lambda e: e,
    enabled: bool | Callable[[], bool] = True,
):
    """Safely monkey-patch module.name so it returns Result[...] instead of raising.

    Uses wrapt.wrap_function_wrapper; 'enabled' can be a bool or a callable.
    """
    def _wrapper(wrapped, instance, args, kwargs):
        if callable(enabled) and not enabled():
            return wrapped(*args, **kwargs)  # pass-through
        if enabled is False:
            return wrapped(*args, **kwargs)
        try:
            return Ok(wrapped(*args, **kwargs))
        except exceptions as e:
            return Err(map_err(e))
    wrapt.wrap_function_wrapper(module, name, _wrapper, enabled=True)


# ---------------------------------------------------------------------
# Tagged-union decoding support (dec_hook)
# ---------------------------------------------------------------------
def _convert_inner(expected_type, value):
    return msgspec.convert(value, type=expected_type) if expected_type is not None else value


def _tagged_union_dec_hook(expected_type, obj):
    """Decode {"Ok": v} / {"Err": e} / {"Some": v} / {"Nothing": None} into our ADTs."""
    origin = get_origin(expected_type) or expected_type
    args = get_args(expected_type)

    # Result[T, E]
    if isinstance(origin, type) and issubclass(origin, Result):
        if not isinstance(obj, dict) or len(obj) != 1:
            return obj
        (tag, payload), = obj.items()
        T_type = args[0] if args else None
        E_type = args[1] if len(args) > 1 else None
        if tag == "Ok":
            return Ok(_convert_inner(T_type, payload))
        if tag == "Err":
            return Err(_convert_inner(E_type, payload))
        return obj

    # Option[T]
    if isinstance(origin, type) and issubclass(origin, Option):
        if not isinstance(obj, dict) or len(obj) != 1:
            return obj
        (tag, payload), = obj.items()
        T_type = args[0] if args else None
        if tag == "Some":
            return Some(_convert_inner(T_type, payload))
        if tag == "Nothing":
            return NOTHING
        return obj

    return obj  # other types untouched


# Ready-to-use decoders (JSON/msgpack share the hook)
TAGGED_DECODER = msgspec.Decoder(dec_hook=_tagged_union_dec_hook)

# Encoders don't need hooks because we implement __msgspec_encode__ on variants.
TAGGED_JSON = msgspec.json  # convenience alias


# ---------------------------------------------------------------------
# Introspection / "schema" helpers
# ---------------------------------------------------------------------
def type_info(tp) -> msgspec.inspect.Type:
    """Return msgspec's rich Type info (useful for docs/validation)."""
    return msgspec.inspect.type_info(tp)


def preview_schema(tp) -> str:
    """Human-friendly preview of the structural shape."""
    info = msgspec.inspect.type_info(tp)
    return repr(info)


# ---------------------------------------------------------------------
# Cross-type utilities with Rust parity
# ---------------------------------------------------------------------
def transpose_option[T, E: ErrorLike](r: Result[Option[T], E]) -> Option[Result[T, E]]:
    """Rust: Result<Option<T>, E> -> Option<Result[T, E]]"""
    if r.is_err():
        return NOTHING
    inner = r.unwrap()
    return inner.map(lambda v: Ok(v))


def flatten_result[T, E1: ErrorLike, E2: ErrorLike](
    r: Result[Result[T, E2], E1]
) -> Result[T, E1 | E2]:
    """Collapse one Result layer: Ok(Ok(T)) -> Ok(T); Ok(Err(e2)) -> Err(e2); Err(e1) -> Err(e1)"""
    if r.is_err():
        return Err(r.unwrap_err())
    return r.unwrap()


def collect_dict[K, V, E: ErrorLike](items: dict[K, Result[V, E]]) -> Result[dict[K, V], E]:
    """Collect dict of results into a dict of values, short-circuiting on first Err."""
    out: dict[K, V] = {}
    for k, r in items.items():
        if r.is_err():
            return Err(r.unwrap_err())
        out[k] = r.unwrap()
    return Ok(out)


def collect_mapping[K, V, E: ErrorLike](items: Mapping[K, Result[V, E]]) -> Result[dict[K, V], E]:
    """Like collect_dict but accepts any Mapping."""
    out: dict[K, V] = {}
    for k, r in items.items():
        if r.is_err():
            return Err(r.unwrap_err())
        out[k] = r.unwrap()
    return Ok(out)


def try_for_each[T, E: ErrorLike](items: Iterable[T], f: Callable[[T], Result[object, E]]) -> Result[None, E]:
    """Apply f to each item, stopping early on Err."""
    for x in items:
        r = f(x)
        if r.is_err():
            return Err(r.unwrap_err())
    return Ok(None)


# ---------------------------------------------------------------------
# Runtime Struct helpers
# ---------------------------------------------------------------------
def make_struct(name: str, fields: list[tuple[str, object]], *, frozen: bool = True) -> type[msgspec.Struct]:
    """
    Create a msgspec.Struct at runtime.

    Example:
        DbCfg = make_struct("DbCfg", [("host", str), ("port", int), ("ssl", bool)])
        inst = DbCfg(host="localhost", port=5432, ssl=True)
    """
    return msgspec.defstruct(name, fields, frozen=frozen)


def zip_struct[S: msgspec.Struct, E: ErrorLike](
    struct_type: type[S],
    fields: Mapping[str, Result[object, E]],
) -> Result[S, E]:
    """
    Build a Struct instance from a mapping of field -> Result.
    Short-circuits on the first Err.
    """
    tinfo = _insp.type_info(struct_type)
    if not isinstance(tinfo, _insp.StructType):
        return Err(TypeError(f"{struct_type!r} is not a msgspec.Struct"))

    expected: dict[str, object] = {f.name: f.type for f in tinfo.fields}
    unknown = set(fields) - set(expected)
    if unknown:
        return Err(TypeError(f"Unknown fields: {sorted(unknown)}"))
    missing = [n for n in expected if n not in fields]
    if missing:
        return Err(TypeError(f"Missing fields: {missing}"))

    vals: dict[str, object] = {}
    for name, r in fields.items():
        if r.is_err():
            return Err(r.unwrap_err())
        vals[name] = msgspec.convert(r.unwrap(), type=expected[name])

    try:
        return Ok(struct_type(**vals))  # type: ignore[arg-type]
    except Exception as e:
        return Err(e)


# ---------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------
__all__ = [
    "ErrorLike",
    # Result
    "Result", "Ok", "Err", "ok", "err",
    "try_catch", "atry_catch", "sequence", "traverse",
    "zip_ok", "zip3", "zip4",
    "wrap_result", "awrap_result", "wrap_result_auto",
    "with_signature", "patch_resultize",
    "set_result_combiner", "set_option_combiner",
    # Option
    "Option", "Some", "Nothing", "NOTHING",
    "some", "nothing", "option_from_optional",
    "wrap_option", "awrap_option",
    # Codecs / schema
    "TAGGED_DECODER", "TAGGED_JSON", "type_info", "preview_schema",
    # Cross-type
    "transpose_option", "flatten_result",
    "collect_dict", "collect_mapping", "try_for_each",
    # Runtime structs
    "make_struct", "zip_struct",
]