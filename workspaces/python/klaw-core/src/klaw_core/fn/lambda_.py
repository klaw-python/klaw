"""Typed Lambda placeholder using msgspec.Struct.

This module provides a fully-typed lambda placeholder that enables
concise function creation with full static type inference.

??? info "Use however you want"
    ```python
    # Operator syntax (chainable)
    fn + 1          → Expr that computes x + 1
    fn * 2 + 1      → Expr that computes x * 2 + 1
    fn["key"]       → Expr that computes x["key"]

    # Method syntax (returns Callable directly)
    fn.upper()      → Callable[[str], str]
    fn.mul(2)       → Callable[[int], int]
    ```

Example:
    ```python
    from klaw_core.fn import fn
    (fn + 1)(5)  # 6
    (fn * 2)(5)  # 10
    fn.upper()("hello")  # 'HELLO'
    ```
"""

from __future__ import annotations

import functools
import itertools
import operator
from collections.abc import Callable, Iterable, Mapping, MutableSequence
from typing import TYPE_CHECKING, Any, TypeVar

import msgspec

if TYPE_CHECKING:
    from klaw_core.option import Option
    from klaw_core.result import Ok, Result

__all__ = ['Expr', 'Lambda', 'Stream', 'fn']

T = TypeVar('T')
T1 = TypeVar('T1')
T2 = TypeVar('T2')
K = TypeVar('K')
V = TypeVar('V')


class _InputRef:
    """Sentinel marker indicating 'use the original input value'."""

    __slots__ = ()

    def __repr__(self) -> str:
        return '<input>'


_INPUT = _InputRef()


class Expr(msgspec.Struct, frozen=True, gc=False):
    """Chainable expression that stores operations.

    Each operation is a tuple of (op_name, arg).
    The expression is callable and applies all operations in sequence.

    Supports self-referential expressions (fn used multiple times):
        - (fn * fn)(5) results in 5 * 5 = 25
        - ((fn - 10) / fn)(20) results in (20 - 10) / 20 = 0.5

    Example:
        ```python
        expr = Expr(ops=(("add", 1), ("mul", 2)))
        expr(5)  # (5 + 1) * 2 = 12
        ```
    """

    ops: tuple[tuple[str, Any], ...] = ()

    def _chain(self, op: str, arg: Any = None) -> Expr:
        """Create a new Expr with an additional operation."""
        if isinstance(arg, Expr):
            arg = _INPUT
        return Expr(ops=(*self.ops, (op, arg)))

    def __call__(self, value: Any) -> Any:
        """Apply all operations to the value."""
        result = value
        for op, arg in self.ops:
            if isinstance(arg, _InputRef):
                arg = value
            result = _apply_op(result, op, arg)
        return result

    # =========================================================================
    # Arithmetic operators
    # =========================================================================

    def __add__(self, other: Any) -> Expr:
        return self._chain('add', other)

    def __radd__(self, other: Any) -> Expr:
        return self._chain('radd', other)

    def __sub__(self, other: Any) -> Expr:
        return self._chain('sub', other)

    def __rsub__(self, other: Any) -> Expr:
        return self._chain('rsub', other)

    def __mul__(self, other: Any) -> Expr:
        return self._chain('mul', other)

    def __rmul__(self, other: Any) -> Expr:
        return self._chain('rmul', other)

    def __truediv__(self, other: Any) -> Expr:
        return self._chain('truediv', other)

    def __rtruediv__(self, other: Any) -> Expr:
        return self._chain('rtruediv', other)

    def __floordiv__(self, other: Any) -> Expr:
        return self._chain('floordiv', other)

    def __rfloordiv__(self, other: Any) -> Expr:
        return self._chain('rfloordiv', other)

    def __mod__(self, other: Any) -> Expr:
        return self._chain('mod', other)

    def __rmod__(self, other: Any) -> Expr:
        return self._chain('rmod', other)

    def __pow__(self, other: Any) -> Expr:
        return self._chain('pow', other)

    def __rpow__(self, other: Any) -> Expr:
        return self._chain('rpow', other)

    # =========================================================================
    # Bitwise operators
    # =========================================================================

    def __and__(self, other: Any) -> Expr:
        return self._chain('and', other)

    def __rand__(self, other: Any) -> Expr:
        return self._chain('rand', other)

    def __or__(self, other: Any) -> Expr:
        return self._chain('or', other)

    def __ror__(self, other: Any) -> Expr:
        return self._chain('ror', other)

    def __xor__(self, other: Any) -> Expr:
        return self._chain('xor', other)

    def __rxor__(self, other: Any) -> Expr:
        return self._chain('rxor', other)

    def __lshift__(self, other: Any) -> Expr:
        return self._chain('lshift', other)

    def __rlshift__(self, other: Any) -> Expr:
        return self._chain('rlshift', other)

    def __rshift__(self, other: Any) -> Expr:
        return self._chain('rshift', other)

    def __rrshift__(self, other: Any) -> Expr:
        return self._chain('rrshift', other)

    # =========================================================================
    # Unary operators
    # =========================================================================

    def __neg__(self) -> Expr:
        return self._chain('neg')

    def __pos__(self) -> Expr:
        return self._chain('pos')

    def __invert__(self) -> Expr:
        return self._chain('invert')

    def __abs__(self) -> Expr:
        return self._chain('abs')

    # =========================================================================
    # Comparison operators
    # =========================================================================

    def __lt__(self, other: Any) -> Expr:
        return self._chain('lt', other)

    def __le__(self, other: Any) -> Expr:
        return self._chain('le', other)

    def __gt__(self, other: Any) -> Expr:
        return self._chain('gt', other)

    def __ge__(self, other: Any) -> Expr:
        return self._chain('ge', other)

    def __eq__(self, other: object) -> Expr:  # type: ignore[override]
        return self._chain('eq', other)

    def __ne__(self, other: object) -> Expr:  # type: ignore[override]
        return self._chain('ne', other)

    # =========================================================================
    # Item access
    # =========================================================================

    def __getitem__(self, key: Any) -> Expr:
        return self._chain('getitem', key)

    def over(self, iterable: Iterable[Any]) -> Stream:
        """Apply this expression over an iterable, returning a Stream.

        Example:
            ```python
            (fn * 2).over([1, 2, 3]).to_list()  # [2, 4, 6]
            (fn * 2).over([1, 2, 3]).filter(fn > 3).to_list()  # [4, 6]
            ```
        """
        return Stream(_iter=map(self, iterable))

    # =========================================================================
    # Option/Result integration
    # =========================================================================

    def try_call(self, value: Any) -> Result[Any, Exception]:
        """Apply expression, wrapping result in Ok or catching exceptions as Err.

        Example:
            ```python
            (fn / 2).try_call(10)  # Ok(value=5.0)
            (fn / 0).try_call(10)  # Err(error=ZeroDivisionError(...))
            ```
        """
        from klaw_core.result import Err, Ok

        try:
            return Ok(self(value))
        except Exception as e:
            return Err(e)

    def some(self, value: Any) -> Option[Any]:
        """Apply expression and wrap result in Some.

        Example:
            ```python
            (fn * 2).some(5)  # Some(value=10)
            ```
        """
        from klaw_core.option import Some

        return Some(self(value))

    def some_if(self, predicate: Callable[[Any], bool]) -> Callable[[Any], Option[Any]]:
        """Return Some(result) if predicate(result) is True, else Nothing.

        Example:
            ```python
            positive = (fn * 2).some_if(fn > 0)
            positive(5)  # Some(value=10)
            positive(-5)  # Nothing
            ```
        """
        from klaw_core.option import Nothing, Some

        def apply(value: Any) -> Option[Any]:
            result = self(value)
            if predicate(result):
                return Some(result)
            return Nothing

        return apply

    def ok(self, value: Any) -> Ok[Any]:
        """Apply expression and wrap result in Ok.

        Example:
            ```python
            (fn * 2).ok(5)  # Ok(value=10)
            ```
        """
        from klaw_core.result import Ok

        return Ok(self(value))

    def __repr__(self) -> str:
        if not self.ops:
            return 'fn'
        ops_str = ' -> '.join(f'{op}({arg!r})' if arg is not None else op for op, arg in self.ops)
        return f'fn[{ops_str}]'


class Stream(msgspec.Struct, frozen=True, gc=False):
    """Fluent iterator wrapper for chaining operations.

    Stream wraps an iterable and provides fluent methods for
    map, filter, reduce, and other iterator operations.

    Example:
        ```python
        Stream([1, 2, 3]).map(fn * 2).filter(fn > 3).to_list()  # [4, 6]
        Stream([1, 2, 3]).map(fn * 2).sum()  # 12
        ```
    """

    _iter: Iterable[Any]

    def map(self, func: Callable[[Any], Any]) -> Stream:
        """Apply function to each element."""
        return Stream(_iter=map(func, self._iter))

    def filter(self, func: Callable[[Any], bool] | None = None) -> Stream:
        """Keep elements where func returns True."""
        return Stream(_iter=filter(func, self._iter))

    def reduce(self, func: Callable[[Any, Any], Any], initial: Any = None) -> Any:
        """Reduce iterable to single value."""
        if initial is None:
            return functools.reduce(func, self._iter)
        return functools.reduce(func, self._iter, initial)

    def take(self, n: int) -> Stream:
        """Take first n elements."""
        return Stream(_iter=itertools.islice(self._iter, n))

    def skip(self, n: int) -> Stream:
        """Skip first n elements."""
        return Stream(_iter=itertools.islice(self._iter, n, None))

    def take_while(self, func: Callable[[Any], bool]) -> Stream:
        """Take elements while predicate is True."""
        return Stream(_iter=itertools.takewhile(func, self._iter))

    def drop_while(self, func: Callable[[Any], bool]) -> Stream:
        """Drop elements while predicate is True."""
        return Stream(_iter=itertools.dropwhile(func, self._iter))

    def chain(self, *others: Iterable[Any]) -> Stream:
        """Chain with other iterables."""
        return Stream(_iter=itertools.chain(self._iter, *others))

    def zip(self, *others: Iterable[Any]) -> Stream:
        """Zip with other iterables."""
        return Stream(_iter=zip(self._iter, *others, strict=False))

    def enumerate(self, start: int = 0) -> Stream:
        """Enumerate elements."""
        return Stream(_iter=enumerate(self._iter, start))

    def flatten(self) -> Stream:
        """Flatten one level of nesting."""
        return Stream(_iter=itertools.chain.from_iterable(self._iter))

    def unique(self) -> Stream:
        """Remove duplicates (preserves order)."""

        def _unique(it: Iterable[Any]) -> Iterable[Any]:
            seen: set[Any] = set()
            for x in it:
                if x not in seen:
                    seen.add(x)
                    yield x

        return Stream(_iter=_unique(self._iter))

    def sorted(self, *, key: Callable[[Any], Any] | None = None, reverse: bool = False) -> Stream:
        """Sort elements."""
        return Stream(_iter=sorted(self._iter, key=key, reverse=reverse))

    def reversed(self) -> Stream:
        """Reverse elements (consumes iterator)."""
        return Stream(_iter=reversed(list(self._iter)))

    def group_by(self, key: Callable[[Any], Any]) -> Stream:
        """Group consecutive elements by key."""
        return Stream(_iter=itertools.groupby(self._iter, key))

    def batch(self, n: int) -> Stream:
        """Split into batches of size n."""

        def _batch(it: Iterable[Any], size: int) -> Iterable[tuple[Any, ...]]:
            it = iter(it)
            while chunk := tuple(itertools.islice(it, size)):
                yield chunk

        return Stream(_iter=_batch(self._iter, n))

    def starmap(self, func: Callable[..., Any]) -> Stream:
        """Apply function to unpacked elements."""
        return Stream(_iter=itertools.starmap(func, self._iter))

    # =========================================================================
    # Terminal operations (consume the stream)
    # =========================================================================

    def to_list(self) -> list[Any]:
        """Collect into list."""
        return list(self._iter)

    def to_tuple(self) -> tuple[Any, ...]:
        """Collect into tuple."""
        return tuple(self._iter)

    def to_set(self) -> set[Any]:
        """Collect into set."""
        return set(self._iter)

    def to_dict(self) -> dict[Any, Any]:
        """Collect into dict (assumes key-value pairs)."""
        return dict(self._iter)

    def to_dicts(self, *keys: str) -> list[dict[str, Any]]:
        """Convert each item to a dict.

        If keys are provided, extracts only those keys/attributes.
        Otherwise uses vars(), _asdict(), or dict() on each item.

        Example:
            ```python
            from dataclasses import dataclass
            @dataclass
            class User:
                name: str
                age: int
            Stream([User('Alice', 30)]).to_dicts()
            # [{'name': 'Alice', 'age': 30}]
            Stream([{'a': 1, 'b': 2}]).to_dicts('a')
            # [{'a': 1}]
            ```
        """
        result: list[dict[str, Any]] = []
        for item in self._iter:
            if keys:
                d = {}
                for k in keys:
                    if hasattr(item, k):
                        d[k] = getattr(item, k)
                    elif isinstance(item, dict) and k in item:
                        d[k] = item[k]
                result.append(d)
            elif hasattr(item, '_asdict'):
                result.append(item._asdict())
            elif hasattr(item, '__dict__'):
                result.append(vars(item))
            elif isinstance(item, dict):
                result.append(dict(item))
            else:
                result.append({'value': item})
        return result

    def collect(self, factory: Callable[[Iterable[Any]], T] = list) -> T:  # type: ignore[assignment]
        """Collect into container using factory."""
        return factory(self._iter)

    def sum(self) -> Any:
        """Sum all elements."""
        return sum(self._iter)

    def min(self) -> Any:
        """Get minimum element."""
        return min(self._iter)

    def max(self) -> Any:
        """Get maximum element."""
        return max(self._iter)

    def count(self) -> int:
        """Count elements."""
        return sum(1 for _ in self._iter)

    def first(self) -> Any | None:
        """Get first element or None."""
        for x in self._iter:
            return x
        return None

    def last(self) -> Any | None:
        """Get last element or None."""
        result = None
        for x in self._iter:
            result = x
        return result

    def nth(self, n: int) -> Any | None:
        """Get nth element or None."""
        for x in itertools.islice(self._iter, n, n + 1):
            return x
        return None

    def all(self) -> bool:
        """Check if all elements are truthy."""
        return all(self._iter)

    def any(self) -> bool:
        """Check if any element is truthy."""
        return any(self._iter)

    def find(self, func: Callable[[Any], bool]) -> Any | None:
        """Find first element matching predicate."""
        for x in self._iter:
            if func(x):
                return x
        return None

    def for_each(self, func: Callable[[Any], Any]) -> None:
        """Apply function to each element for side effects."""
        for x in self._iter:
            func(x)

    def join(self, sep: str = '') -> str:
        """Join string elements."""
        return sep.join(self._iter)

    def __iter__(self) -> Any:
        """Allow direct iteration."""
        return iter(self._iter)

    def __repr__(self) -> str:
        return f'Stream({self._iter!r})'

    # =========================================================================
    # Option/Result integration
    # =========================================================================

    def first_some(self) -> Option[Any]:
        """Get first element as Some, or Nothing if empty.

        Examples:
            >>> Stream([1, 2, 3]).first_some()
            Some(value=1)
            >>> Stream([]).first_some()
            Nothing
        """
        from klaw_core.option import Nothing, Some

        for x in self._iter:
            return Some(x)
        return Nothing

    def last_some(self) -> Option[Any]:
        """Get last element as Some, or Nothing if empty.

        Examples:
            >>> Stream([1, 2, 3]).last_some()
            Some(value=3)
            >>> Stream([]).last_some()
            Nothing
        """
        from klaw_core.option import Nothing, Some

        result: Option[Any] = Nothing
        for x in self._iter:
            result = Some(x)
        return result

    def find_some(self, func: Callable[[Any], bool]) -> Option[Any]:
        """Find first matching element as Some, or Nothing.

        Examples:
            >>> Stream([1, 2, 3, 4]).find_some(fn > 2)
            Some(value=3)
            >>> Stream([1, 2]).find_some(fn > 5)
            Nothing
        """
        from klaw_core.option import Nothing, Some

        for x in self._iter:
            if func(x):
                return Some(x)
        return Nothing

    def nth_some(self, n: int) -> Option[Any]:
        """Get nth element as Some, or Nothing.

        Examples:
            >>> Stream([1, 2, 3]).nth_some(1)
            Some(value=2)
            >>> Stream([1, 2]).nth_some(10)
            Nothing
        """
        from klaw_core.option import Nothing, Some

        for x in itertools.islice(self._iter, n, n + 1):
            return Some(x)
        return Nothing

    def filter_some(self) -> Stream:
        """Filter out Nothing values and unwrap Some values.

        Examples:
            >>> from klaw_core import Some, Nothing
            >>> Stream([Some(1), Nothing, Some(2)]).filter_some().to_list()
            [1, 2]
        """
        from klaw_core.option import Some

        def _unwrap_some(it: Iterable[Any]) -> Iterable[Any]:
            for x in it:
                if isinstance(x, Some):
                    yield x.value

        return Stream(_iter=_unwrap_some(self._iter))

    def filter_ok(self) -> Stream:
        """Filter out Err values and unwrap Ok values.

        Examples:
            >>> from klaw_core import Ok, Err
            >>> Stream([Ok(1), Err("fail"), Ok(2)]).filter_ok().to_list()
            [1, 2]
        """
        from klaw_core.result import Ok

        def _unwrap_ok(it: Iterable[Any]) -> Iterable[Any]:
            for x in it:
                if isinstance(x, Ok):
                    yield x.value

        return Stream(_iter=_unwrap_ok(self._iter))

    def collect_results(self) -> Result[list[Any], Any]:
        """Collect Results into Ok(list) or return first Err.

        Examples:
            >>> from klaw_core import Ok, Err
            >>> Stream([Ok(1), Ok(2), Ok(3)]).collect_results()
            Ok(value=[1, 2, 3])
            >>> Stream([Ok(1), Err("fail"), Ok(3)]).collect_results()
            Err(error='fail')
        """
        from klaw_core.result import Err, Ok

        values: list[Any] = []
        for x in self._iter:
            if isinstance(x, Err):
                return x
            if isinstance(x, Ok):
                values.append(x.value)
            else:
                values.append(x)
        return Ok(values)

    def collect_options(self) -> Option[list[Any]]:
        """Collect Options into Some(list) or return Nothing if any Nothing.

        Examples:
            >>> from klaw_core import Some, Nothing
            >>> Stream([Some(1), Some(2)]).collect_options()
            Some(value=[1, 2])
            >>> Stream([Some(1), Nothing]).collect_options()
            Nothing
        """
        from klaw_core.option import Nothing, NothingType, Some

        values: list[Any] = []
        for x in self._iter:
            if isinstance(x, NothingType):
                return Nothing
            if isinstance(x, Some):
                values.append(x.value)
            else:
                values.append(x)
        return Some(values)

    def try_reduce(self, func: Callable[[Any, Any], Any], initial: Any = None) -> Result[Any, Exception]:
        """Reduce with exception handling, returning Result.

        Examples:
            >>> Stream([1, 2, 3]).try_reduce(lambda a, b: a + b)
            Ok(value=6)
            >>> Stream([]).try_reduce(lambda a, b: a + b)
            Err(error=TypeError(...))
        """
        from klaw_core.result import Err, Ok

        try:
            if initial is None:
                return Ok(functools.reduce(func, self._iter))
            return Ok(functools.reduce(func, self._iter, initial))
        except Exception as e:
            return Err(e)


def _apply_op(value: Any, op: str, arg: Any) -> Any:
    """Apply a single operation to a value."""
    match op:
        # Arithmetic
        case 'add':
            return value + arg
        case 'radd':
            return arg + value
        case 'sub':
            return value - arg
        case 'rsub':
            return arg - value
        case 'mul':
            return value * arg
        case 'rmul':
            return arg * value
        case 'truediv':
            return value / arg
        case 'rtruediv':
            return arg / value
        case 'floordiv':
            return value // arg
        case 'rfloordiv':
            return arg // value
        case 'mod':
            return value % arg
        case 'rmod':
            return arg % value
        case 'pow':
            return value**arg
        case 'rpow':
            return arg**value

        # Bitwise
        case 'and':
            return value & arg
        case 'rand':
            return arg & value
        case 'or':
            return value | arg
        case 'ror':
            return arg | value
        case 'xor':
            return value ^ arg
        case 'rxor':
            return arg ^ value
        case 'lshift':
            return value << arg
        case 'rlshift':
            return arg << value
        case 'rshift':
            return value >> arg
        case 'rrshift':
            return arg >> value

        # Unary
        case 'neg':
            return -value
        case 'pos':
            return +value
        case 'invert':
            return ~value
        case 'abs':
            return abs(value)

        # Comparison
        case 'lt':
            return value < arg
        case 'le':
            return value <= arg
        case 'gt':
            return value > arg
        case 'ge':
            return value >= arg
        case 'eq':
            return value == arg
        case 'ne':
            return value != arg

        # Access
        case 'getitem':
            return value[arg]

        case 'getattr':
            return getattr(value, arg)

        case 'method':
            method_name, args, kwargs = arg
            return getattr(value, method_name)(*args, **kwargs)

        case _:
            raise ValueError(f'Unknown operation: {op}')


class Lambda(Expr):
    """Typed lambda placeholder combining Expr operators with method factories.

    Lambda extends Expr to provide both:
    - Operator syntax: fn + 1, fn * 2, fn["key"]
    - Method factories: fn.upper(), fn.mul(2), fn.item("key")

    Examples:
        >>> (fn + 1)(5)
        6
        >>> fn.upper()("hello")
        'HELLO'
        >>> fn.item("name")({"name": "Alice"})
        'Alice'
    """

    # =========================================================================
    # String methods
    # =========================================================================

    def upper(self) -> Callable[[str], str]:
        """Create lambda: x.upper()."""
        return operator.methodcaller('upper')

    def lower(self) -> Callable[[str], str]:
        """Create lambda: x.lower()."""
        return operator.methodcaller('lower')

    def strip(self, chars: str | None = None) -> Callable[[str], str]:
        """Create lambda: x.strip(chars)."""
        return operator.methodcaller('strip', chars)

    def lstrip(self, chars: str | None = None) -> Callable[[str], str]:
        """Create lambda: x.lstrip(chars)."""
        return operator.methodcaller('lstrip', chars)

    def rstrip(self, chars: str | None = None) -> Callable[[str], str]:
        """Create lambda: x.rstrip(chars)."""
        return operator.methodcaller('rstrip', chars)

    def split(self, sep: str | None = None, maxsplit: int = -1) -> Callable[[str], list[str]]:
        """Create lambda: x.split(sep, maxsplit)."""
        return operator.methodcaller('split', sep, maxsplit)

    def rsplit(self, sep: str | None = None, maxsplit: int = -1) -> Callable[[str], list[str]]:
        """Create lambda: x.rsplit(sep, maxsplit)."""
        return operator.methodcaller('rsplit', sep, maxsplit)

    def splitlines(self, keepends: bool = False) -> Callable[[str], list[str]]:
        """Create lambda: x.splitlines(keepends)."""
        return operator.methodcaller('splitlines', keepends)

    def join(self, iterable: Iterable[str]) -> Callable[[str], str]:
        """Create lambda: x.join(iterable)."""
        return operator.methodcaller('join', iterable)

    def replace(self, old: str, new: str, count: int = -1) -> Callable[[str], str]:
        """Create lambda: x.replace(old, new, count)."""
        return operator.methodcaller('replace', old, new, count)

    def startswith(
        self, prefix: str | tuple[str, ...], start: int = 0, end: int | None = None
    ) -> Callable[[str], bool]:
        """Create lambda: x.startswith(prefix)."""
        if end is None:
            return operator.methodcaller('startswith', prefix, start)
        return operator.methodcaller('startswith', prefix, start, end)

    def endswith(self, suffix: str | tuple[str, ...], start: int = 0, end: int | None = None) -> Callable[[str], bool]:
        """Create lambda: x.endswith(suffix)."""
        if end is None:
            return operator.methodcaller('endswith', suffix, start)
        return operator.methodcaller('endswith', suffix, start, end)

    def find(self, sub: str, start: int = 0, end: int | None = None) -> Callable[[str], int]:
        """Create lambda: x.find(sub)."""
        if end is None:
            return operator.methodcaller('find', sub, start)
        return operator.methodcaller('find', sub, start, end)

    def rfind(self, sub: str, start: int = 0, end: int | None = None) -> Callable[[str], int]:
        """Create lambda: x.rfind(sub)."""
        if end is None:
            return operator.methodcaller('rfind', sub, start)
        return operator.methodcaller('rfind', sub, start, end)

    def index(self, sub: str, start: int = 0, end: int | None = None) -> Callable[[str], int]:
        """Create lambda: x.index(sub)."""
        if end is None:
            return operator.methodcaller('index', sub, start)
        return operator.methodcaller('index', sub, start, end)

    def count(self, sub: str, start: int = 0, end: int | None = None) -> Callable[[str], int]:
        """Create lambda: x.count(sub)."""
        if end is None:
            return operator.methodcaller('count', sub, start)
        return operator.methodcaller('count', sub, start, end)

    def title(self) -> Callable[[str], str]:
        """Create lambda: x.title()."""
        return operator.methodcaller('title')

    def capitalize(self) -> Callable[[str], str]:
        """Create lambda: x.capitalize()."""
        return operator.methodcaller('capitalize')

    def casefold(self) -> Callable[[str], str]:
        """Create lambda: x.casefold()."""
        return operator.methodcaller('casefold')

    def swapcase(self) -> Callable[[str], str]:
        """Create lambda: x.swapcase()."""
        return operator.methodcaller('swapcase')

    def center(self, width: int, fillchar: str = ' ') -> Callable[[str], str]:
        """Create lambda: x.center(width, fillchar)."""
        return operator.methodcaller('center', width, fillchar)

    def ljust(self, width: int, fillchar: str = ' ') -> Callable[[str], str]:
        """Create lambda: x.ljust(width, fillchar)."""
        return operator.methodcaller('ljust', width, fillchar)

    def rjust(self, width: int, fillchar: str = ' ') -> Callable[[str], str]:
        """Create lambda: x.rjust(width, fillchar)."""
        return operator.methodcaller('rjust', width, fillchar)

    def zfill(self, width: int) -> Callable[[str], str]:
        """Create lambda: x.zfill(width)."""
        return operator.methodcaller('zfill', width)

    def encode(self, encoding: str = 'utf-8', errors: str = 'strict') -> Callable[[str], bytes]:
        """Create lambda: x.encode(encoding, errors)."""
        return operator.methodcaller('encode', encoding, errors)

    def isalpha(self) -> Callable[[str], bool]:
        """Create lambda: x.isalpha()."""
        return operator.methodcaller('isalpha')

    def isalnum(self) -> Callable[[str], bool]:
        """Create lambda: x.isalnum()."""
        return operator.methodcaller('isalnum')

    def isdigit(self) -> Callable[[str], bool]:
        """Create lambda: x.isdigit()."""
        return operator.methodcaller('isdigit')

    def isnumeric(self) -> Callable[[str], bool]:
        """Create lambda: x.isnumeric()."""
        return operator.methodcaller('isnumeric')

    def isdecimal(self) -> Callable[[str], bool]:
        """Create lambda: x.isdecimal()."""
        return operator.methodcaller('isdecimal')

    def isspace(self) -> Callable[[str], bool]:
        """Create lambda: x.isspace()."""
        return operator.methodcaller('isspace')

    def isupper(self) -> Callable[[str], bool]:
        """Create lambda: x.isupper()."""
        return operator.methodcaller('isupper')

    def islower(self) -> Callable[[str], bool]:
        """Create lambda: x.islower()."""
        return operator.methodcaller('islower')

    def istitle(self) -> Callable[[str], bool]:
        """Create lambda: x.istitle()."""
        return operator.methodcaller('istitle')

    def isidentifier(self) -> Callable[[str], bool]:
        """Create lambda: x.isidentifier()."""
        return operator.methodcaller('isidentifier')

    def isprintable(self) -> Callable[[str], bool]:
        """Create lambda: x.isprintable()."""
        return operator.methodcaller('isprintable')

    def isascii(self) -> Callable[[str], bool]:
        """Create lambda: x.isascii()."""
        return operator.methodcaller('isascii')

    def expandtabs(self, tabsize: int = 8) -> Callable[[str], str]:
        """Create lambda: x.expandtabs(tabsize)."""
        return operator.methodcaller('expandtabs', tabsize)

    def partition(self, sep: str) -> Callable[[str], tuple[str, str, str]]:
        """Create lambda: x.partition(sep)."""
        return operator.methodcaller('partition', sep)

    def rpartition(self, sep: str) -> Callable[[str], tuple[str, str, str]]:
        """Create lambda: x.rpartition(sep)."""
        return operator.methodcaller('rpartition', sep)

    def removeprefix(self, prefix: str) -> Callable[[str], str]:
        """Create lambda: x.removeprefix(prefix)."""
        return operator.methodcaller('removeprefix', prefix)

    def removesuffix(self, suffix: str) -> Callable[[str], str]:
        """Create lambda: x.removesuffix(suffix)."""
        return operator.methodcaller('removesuffix', suffix)

    # =========================================================================
    # Dict methods
    # =========================================================================

    def get(self, key: K, default: V | None = None) -> Callable[[Mapping[K, V]], V | None]:
        """Create lambda: x.get(key, default)."""
        return operator.methodcaller('get', key, default)

    def keys(self) -> Callable[[Mapping[K, V]], Any]:
        """Create lambda: x.keys()."""
        return operator.methodcaller('keys')

    def values(self) -> Callable[[Mapping[K, V]], Any]:
        """Create lambda: x.values()."""
        return operator.methodcaller('values')

    def items(self) -> Callable[[Mapping[K, V]], Any]:
        """Create lambda: x.items()."""
        return operator.methodcaller('items')

    def pop(self, key: K, *default: V) -> Callable[[dict[K, V]], V]:
        """Create lambda: x.pop(key, default)."""
        return operator.methodcaller('pop', key, *default)

    def setdefault(self, key: K, default: V) -> Callable[[dict[K, V]], V]:
        """Create lambda: x.setdefault(key, default)."""
        return operator.methodcaller('setdefault', key, default)

    # =========================================================================
    # List/Sequence methods
    # =========================================================================

    def append(self, item: T) -> Callable[[MutableSequence[T]], None]:
        """Create lambda: x.append(item)."""
        return operator.methodcaller('append', item)

    def extend(self, items: Iterable[T]) -> Callable[[MutableSequence[T]], None]:
        """Create lambda: x.extend(items)."""
        return operator.methodcaller('extend', items)

    def insert(self, idx: int, item: T) -> Callable[[MutableSequence[T]], None]:
        """Create lambda: x.insert(index, item)."""
        return operator.methodcaller('insert', idx, item)

    def remove(self, item: T) -> Callable[[MutableSequence[T]], None]:
        """Create lambda: x.remove(item)."""
        return operator.methodcaller('remove', item)

    def reverse(self) -> Callable[[MutableSequence[T]], None]:
        """Create lambda: x.reverse()."""
        return operator.methodcaller('reverse')

    def sort(self, *, key: Callable[[T], Any] | None = None, reverse: bool = False) -> Callable[[list[T]], None]:
        """Create lambda: x.sort(key=key, reverse=reverse)."""
        return operator.methodcaller('sort', key=key, reverse=reverse)

    def copy(self) -> Callable[[list[T]], list[T]]:
        """Create lambda: x.copy()."""
        return operator.methodcaller('copy')

    def clear(self) -> Callable[[MutableSequence[T]], None]:
        """Create lambda: x.clear()."""
        return operator.methodcaller('clear')

    # =========================================================================
    # Numeric methods
    # =========================================================================

    def bit_length(self) -> Callable[[int], int]:
        """Create lambda: x.bit_length()."""
        return operator.methodcaller('bit_length')

    def bit_count(self) -> Callable[[int], int]:
        """Create lambda: x.bit_count()."""
        return operator.methodcaller('bit_count')

    def conjugate(self) -> Callable[[complex], complex]:
        """Create lambda: x.conjugate()."""
        return operator.methodcaller('conjugate')

    def hex(self) -> Callable[[float], str]:
        """Create lambda: x.hex()."""
        return operator.methodcaller('hex')

    def is_integer(self) -> Callable[[float], bool]:
        """Create lambda: x.is_integer()."""
        return operator.methodcaller('is_integer')

    def as_integer_ratio(self) -> Callable[[float], tuple[int, int]]:
        """Create lambda: x.as_integer_ratio()."""
        return operator.methodcaller('as_integer_ratio')

    # =========================================================================
    # Attribute and item access
    # =========================================================================

    def attr(self, name: str) -> Callable[[Any], Any]:
        """Create lambda: getattr(x, name)."""
        return operator.attrgetter(name)

    def item(self, key: K) -> Callable[[Mapping[K, V]], V]:
        """Create lambda: x[key]."""
        return operator.itemgetter(key)

    def method(self, name: str, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
        """Create lambda: x.method(*args, **kwargs)."""
        return operator.methodcaller(name, *args, **kwargs)

    # =========================================================================
    # Arithmetic operators
    # =========================================================================

    def add(self, n: T) -> Callable[[T], T]:
        """Create lambda: x + n."""
        return lambda x: x + n  # type: ignore[operator, return-value]

    def radd(self, n: T) -> Callable[[T], T]:
        """Create lambda: n + x."""
        return lambda x: n + x  # type: ignore[operator, return-value]

    def sub(self, n: T) -> Callable[[T], T]:
        """Create lambda: x - n."""
        return lambda x: x - n  # type: ignore[operator, return-value]

    def rsub(self, n: T) -> Callable[[T], T]:
        """Create lambda: n - x."""
        return lambda x: n - x  # type: ignore[operator, return-value]

    def mul(self, n: T) -> Callable[[T], T]:
        """Create lambda: x * n."""
        return lambda x: x * n  # type: ignore[operator, return-value]

    def rmul(self, n: T) -> Callable[[T], T]:
        """Create lambda: n * x."""
        return lambda x: n * x  # type: ignore[operator, return-value]

    def truediv(self, n: float) -> Callable[[float], float]:
        """Create lambda: x / n."""
        return lambda x: x / n

    def rtruediv(self, n: float) -> Callable[[float], float]:
        """Create lambda: n / x."""
        return lambda x: n / x

    def floordiv(self, n: int) -> Callable[[int], int]:
        """Create lambda: x // n."""
        return lambda x: x // n

    def rfloordiv(self, n: int) -> Callable[[int], int]:
        """Create lambda: n // x."""
        return lambda x: n // x

    def mod(self, n: int) -> Callable[[int], int]:
        """Create lambda: x % n."""
        return lambda x: x % n

    def rmod(self, n: int) -> Callable[[int], int]:
        """Create lambda: n % x."""
        return lambda x: n % x

    def pow(self, n: int) -> Callable[[int], int]:
        """Create lambda: x ** n."""
        return lambda x: x**n

    def rpow(self, n: int) -> Callable[[int], int]:
        """Create lambda: n ** x."""
        return lambda x: n**x

    def neg(self) -> Callable[[T], T]:
        """Create lambda: -x."""
        return operator.neg

    def pos(self) -> Callable[[T], T]:
        """Create lambda: +x."""
        return operator.pos

    def abs_(self) -> Callable[[T], T]:
        """Create lambda: abs(x)."""
        return abs  # type: ignore[return-value]

    def invert(self) -> Callable[[int], int]:
        """Create lambda: ~x."""
        return operator.invert

    # =========================================================================
    # Bitwise operators
    # =========================================================================

    def and_(self, n: int) -> Callable[[int], int]:
        """Create lambda: x & n."""
        return lambda x: x & n

    def rand(self, n: int) -> Callable[[int], int]:
        """Create lambda: n & x."""
        return lambda x: n & x

    def or_(self, n: int) -> Callable[[int], int]:
        """Create lambda: x | n."""
        return lambda x: x | n

    def ror(self, n: int) -> Callable[[int], int]:
        """Create lambda: n | x."""
        return lambda x: n | x

    def xor(self, n: int) -> Callable[[int], int]:
        """Create lambda: x ^ n."""
        return lambda x: x ^ n

    def rxor(self, n: int) -> Callable[[int], int]:
        """Create lambda: n ^ x."""
        return lambda x: n ^ x

    def lshift(self, n: int) -> Callable[[int], int]:
        """Create lambda: x << n."""
        return lambda x: x << n

    def rlshift(self, n: int) -> Callable[[int], int]:
        """Create lambda: n << x."""
        return lambda x: n << x

    def rshift(self, n: int) -> Callable[[int], int]:
        """Create lambda: x >> n."""
        return lambda x: x >> n

    def rrshift(self, n: int) -> Callable[[int], int]:
        """Create lambda: n >> x."""
        return lambda x: n >> x

    # =========================================================================
    # Comparison operators
    # =========================================================================

    def eq(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x == value."""
        return lambda x: x == value

    def ne(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x != value."""
        return lambda x: x != value

    def lt(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x < value."""
        return lambda x: x < value  # type: ignore[operator]

    def le(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x <= value."""
        return lambda x: x <= value  # type: ignore[operator]

    def gt(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x > value."""
        return lambda x: x > value  # type: ignore[operator]

    def ge(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x >= value."""
        return lambda x: x >= value  # type: ignore[operator]

    # =========================================================================
    # Boolean/Logic
    # =========================================================================

    def not_(self) -> Callable[[Any], bool]:
        """Create lambda: not x."""
        return operator.not_

    def truth(self) -> Callable[[Any], bool]:
        """Create lambda: bool(x)."""
        return operator.truth

    def is_(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x is value."""
        return lambda x: x is value

    def is_not(self, value: T) -> Callable[[T], bool]:
        """Create lambda: x is not value."""
        return lambda x: x is not value

    def contains(self, item: T) -> Callable[[Iterable[T]], bool]:
        """Create lambda: item in x."""
        return lambda x: item in x

    def in_(self, container: Iterable[T]) -> Callable[[T], bool]:
        """Create lambda: x in container."""
        return lambda x: x in container

    def not_in(self, container: Iterable[T]) -> Callable[[T], bool]:
        """Create lambda: x not in container."""
        return lambda x: x not in container

    # =========================================================================
    # Type conversions
    # =========================================================================

    def int_(self) -> Callable[[Any], int]:
        """Create lambda: int(x)."""
        return int

    def float_(self) -> Callable[[Any], float]:
        """Create lambda: float(x)."""
        return float

    def str_(self) -> Callable[[Any], str]:
        """Create lambda: str(x)."""
        return str

    def bool_(self) -> Callable[[Any], bool]:
        """Create lambda: bool(x)."""
        return bool

    def list_(self) -> Callable[[Iterable[T]], list[T]]:
        """Create lambda: list(x)."""
        return list

    def tuple_(self) -> Callable[[Iterable[T]], tuple[T, ...]]:
        """Create lambda: tuple(x)."""
        return tuple  # type: ignore[return-value]

    def set_(self) -> Callable[[Iterable[T]], set[T]]:
        """Create lambda: set(x)."""
        return set

    def dict_(self) -> Callable[[Iterable[tuple[K, V]]], dict[K, V]]:
        """Create lambda: dict(x)."""
        return dict  # type: ignore[return-value]

    def bytes_(self, encoding: str = 'utf-8') -> Callable[[str], bytes]:
        """Create lambda: x.encode(encoding)."""
        return operator.methodcaller('encode', encoding)

    # =========================================================================
    # Builtins
    # =========================================================================

    def len_(self) -> Callable[[Any], int]:
        """Create lambda: len(x)."""
        return len

    def repr_(self) -> Callable[[Any], str]:
        """Create lambda: repr(x)."""
        return repr

    def hash_(self) -> Callable[[Any], int]:
        """Create lambda: hash(x)."""
        return hash

    def type_(self) -> Callable[[Any], type]:
        """Create lambda: type(x)."""
        return type

    def id_(self) -> Callable[[Any], int]:
        """Create lambda: id(x)."""
        return id

    def callable_(self) -> Callable[[Any], bool]:
        """Create lambda: callable(x)."""
        return callable

    def sorted_(
        self, *, key: Callable[[T], Any] | None = None, reverse: bool = False
    ) -> Callable[[Iterable[T]], list[T]]:
        """Create lambda: sorted(x, key=key, reverse=reverse)."""
        return lambda x: sorted(x, key=key, reverse=reverse)

    def reversed_(self) -> Callable[[Iterable[T]], Iterable[T]]:
        """Create lambda: reversed(x)."""
        return reversed  # type: ignore[return-value]

    def enumerate_(self, start: int = 0) -> Callable[[Iterable[T]], Iterable[tuple[int, T]]]:
        """Create lambda: enumerate(x, start)."""
        return lambda x: enumerate(x, start)

    def min_(self) -> Callable[[Iterable[T]], T]:
        """Create lambda: min(x)."""
        return min  # type: ignore[return-value]

    def max_(self) -> Callable[[Iterable[T]], T]:
        """Create lambda: max(x)."""
        return max  # type: ignore[return-value]

    def sum_(self) -> Callable[[Iterable[T]], T]:
        """Create lambda: sum(x)."""
        return sum  # type: ignore[return-value]

    def all_(self) -> Callable[[Iterable[Any]], bool]:
        """Create lambda: all(x)."""
        return all

    def any_(self) -> Callable[[Iterable[Any]], bool]:
        """Create lambda: any(x)."""
        return any

    def zip_(self, *iterables: Iterable[Any]) -> Callable[[Iterable[T]], Iterable[tuple[Any, ...]]]:
        """Create lambda: zip(x, *iterables)."""
        return lambda x: zip(x, *iterables, strict=False)

    def map_(self, func: Callable[[T], T2]) -> Callable[[Iterable[T]], Iterable[T2]]:
        """Create lambda: map(func, x)."""
        return lambda x: map(func, x)

    def filter_(self, func: Callable[[T], bool] | None = None) -> Callable[[Iterable[T]], Iterable[T]]:
        """Create lambda: filter(func, x)."""
        return lambda x: filter(func, x)

    # =========================================================================
    # Identity and composition
    # =========================================================================

    def identity(self) -> Callable[[T], T]:
        """Create lambda: x (identity function)."""
        return lambda x: x

    def const(self, value: T) -> Callable[[Any], T]:
        """Create lambda: value (constant function)."""
        return lambda _: value

    def call(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., T]], T]:
        """Create lambda: x(*args, **kwargs)."""
        return lambda x: x(*args, **kwargs)

    # =========================================================================
    # Stream factory methods (fn as entry point for streams)
    # =========================================================================

    def iter(self, iterable: Iterable[T]) -> Stream:
        """Create a Stream from an iterable.

        Example:
            ```python
            fn.iter([1, 2, 3]).map(fn * 2).to_list()  # [2, 4, 6]
            ```
        """
        return Stream(_iter=iterable)

    def enumerate(self, iterable: Iterable[T], start: int = 0) -> Stream:
        """Create an enumerated Stream from an iterable.

        Examples:
            >>> fn.enumerate(['a', 'b', 'c']).to_list()
            [(0, 'a'), (1, 'b'), (2, 'c')]
            >>> fn.enumerate(['a', 'b'], start=1).to_list()
            [(1, 'a'), (2, 'b')]
        """
        return Stream(_iter=enumerate(iterable, start))

    def range(self, *args: int) -> Stream:
        """Create a Stream from range().

        Examples:
            >>> fn.range(5).map(fn * 2).to_list()
            [0, 2, 4, 6, 8]
            >>> fn.range(1, 6).filter(fn % 2 == 0).to_list()
            [2, 4]
        """
        return Stream(_iter=range(*args))

    def iterate(self, func: Callable[[T], T], start: T) -> Stream:
        """Create infinite Stream by repeatedly applying func.

        Examples:
            >>> fn.iterate(fn * 2, 1).take(5).to_list()
            [1, 2, 4, 8, 16]
        """

        def _iterate() -> Iterable[T]:
            value = start
            while True:
                yield value
                value = func(value)

        return Stream(_iter=_iterate())

    def repeat(self, value: T, times: int | None = None) -> Stream:
        """Create Stream that repeats value.

        Examples:
            >>> fn.repeat(42, 3).to_list()
            [42, 42, 42]
        """
        if times is None:
            return Stream(_iter=itertools.repeat(value))
        return Stream(_iter=itertools.repeat(value, times))

    def counter(self, start: int = 0, step: int = 1) -> Stream:
        """Create infinite counting Stream.

        Examples:
            >>> fn.counter(10).take(5).to_list()
            [10, 11, 12, 13, 14]
            >>> fn.counter(0, 2).take(5).to_list()
            [0, 2, 4, 6, 8]
        """
        return Stream(_iter=itertools.count(start, step))

    def cycle(self, iterable: Iterable[T]) -> Stream:
        """Create infinite Stream cycling through iterable.

        Examples:
            >>> fn.cycle([1, 2, 3]).take(7).to_list()
            [1, 2, 3, 1, 2, 3, 1]
        """
        return Stream(_iter=itertools.cycle(iterable))

    def zip(self, *iterables: Iterable[Any]) -> Stream:
        """Zip multiple iterables into a Stream.

        Examples:
            >>> fn.zip([1, 2], ['a', 'b']).to_list()
            [(1, 'a'), (2, 'b')]
        """
        return Stream(_iter=zip(*iterables, strict=False))

    def chain(self, *iterables: Iterable[Any]) -> Stream:
        """Chain multiple iterables into a Stream.

        Examples:
            >>> fn.chain([1, 2], [3, 4]).to_list()
            [1, 2, 3, 4]
        """
        return Stream(_iter=itertools.chain(*iterables))


fn: Lambda = Lambda()
