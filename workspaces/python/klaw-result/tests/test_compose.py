"""Tests for composition utilities: pipe() and Deref."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from klaw_result import (
    DerefOk,
    DerefSome,
    Err,
    Nothing,
    Ok,
    Some,
)
from klaw_result.compose import pipe


class TestPipeBasic:
    """Tests for basic pipe() functionality."""

    def test_pipe_no_functions(self):
        """pipe(value) wraps value in Ok."""
        result = pipe(5)
        assert result == Ok(5)

    def test_pipe_no_functions_with_ok(self):
        """pipe(Ok(value)) returns the Ok unchanged."""
        result = pipe(Ok(5))
        assert result == Ok(5)

    def test_pipe_single_function(self):
        """pipe(value, fn) applies fn and wraps in Ok."""
        result = pipe(5, lambda x: x + 1)
        assert result == Ok(6)

    def test_pipe_multiple_functions(self):
        """pipe(value, fn1, fn2, ...) chains functions."""
        result = pipe(5, lambda x: x + 1, lambda x: x * 2, str)
        assert result == Ok("12")

    def test_pipe_with_ok_input(self):
        """pipe(Ok(value), ...) unwraps and applies functions."""
        result = pipe(Ok(5), lambda x: x + 1, lambda x: x * 2)
        assert result == Ok(12)

    def test_pipe_with_some_input(self):
        """pipe(Some(value), ...) unwraps and applies functions."""
        result = pipe(Some(5), lambda x: x + 1, lambda x: x * 2)
        assert result == Some(12)


class TestPipeShortCircuit:
    """Tests for pipe() short-circuit behavior."""

    def test_pipe_short_circuits_on_err(self):
        """pipe() stops and returns Err when a function returns Err."""
        called = False

        def should_not_run(x: int) -> int:
            nonlocal called
            called = True
            return x + 1

        result = pipe(5, lambda x: Err("failed"), should_not_run)
        assert result == Err("failed")
        assert called is False

    def test_pipe_short_circuits_on_nothing(self):
        """pipe() stops and returns Nothing when a function returns Nothing."""
        called = False

        def should_not_run(x: int) -> int:
            nonlocal called
            called = True
            return x + 1

        result = pipe(5, lambda x: Nothing, should_not_run)
        assert result is Nothing
        assert called is False

    def test_pipe_with_err_input(self):
        """pipe(Err(...), ...) returns Err immediately."""
        called = False

        def should_not_run(x: int) -> int:
            nonlocal called
            called = True
            return x + 1

        result = pipe(Err("already failed"), should_not_run)
        assert result == Err("already failed")
        assert called is False

    def test_pipe_with_nothing_input(self):
        """pipe(Nothing, ...) returns Nothing immediately."""
        called = False

        def should_not_run(x: int) -> int:
            nonlocal called
            called = True
            return x + 1

        result = pipe(Nothing, should_not_run)
        assert result is Nothing
        assert called is False


class TestPipeNoDoubleWrap:
    """Tests for avoiding double-wrapping in pipe()."""

    def test_pipe_fn_returns_ok(self):
        """Function returning Ok is not double-wrapped."""
        result = pipe(5, lambda x: Ok(x + 1))
        assert result == Ok(6)

    def test_pipe_fn_returns_err(self):
        """Function returning Err is not double-wrapped."""
        result = pipe(5, lambda x: Err("fail"))
        assert result == Err("fail")

    def test_pipe_fn_returns_some(self):
        """Function returning Some is not double-wrapped."""
        result = pipe(5, lambda x: Some(x + 1))
        assert result == Some(6)

    def test_pipe_fn_returns_nothing(self):
        """Function returning Nothing is not double-wrapped."""
        result = pipe(5, lambda x: Nothing)
        assert result is Nothing

    def test_pipe_chain_with_mixed_returns(self):
        """Chaining functions with mixed return types."""
        result = pipe(
            5,
            lambda x: Ok(x + 1),  # Returns Ok(6)
            lambda x: x * 2,  # Returns 12, wrapped to Ok(12)
            lambda x: Some(str(x)),  # Returns Some("12")
        )
        assert result == Some("12")


class TestPipeRealWorld:
    """Real-world usage patterns for pipe()."""

    def test_pipe_data_transformation(self):
        """Transform data through a pipeline."""

        def parse_int(s: str) -> Ok[int] | Err[str]:
            try:
                return Ok(int(s))
            except ValueError:
                return Err(f"Invalid int: {s}")

        def validate_positive(n: int) -> Ok[int] | Err[str]:
            if n > 0:
                return Ok(n)
            return Err("Must be positive")

        def double(n: int) -> int:
            return n * 2

        result = pipe("42", parse_int, validate_positive, double)
        assert result == Ok(84)

        result = pipe("abc", parse_int, validate_positive, double)
        assert result == Err("Invalid int: abc")

        result = pipe("-5", parse_int, validate_positive, double)
        assert result == Err("Must be positive")

    def test_pipe_optional_chain(self):
        """Chain optional operations."""

        def find_user(user_id: int) -> Some[dict] | type[Nothing]:
            if user_id == 1:
                return Some({"id": 1, "name": "Alice", "email": "alice@example.com"})
            return Nothing

        def get_email(user: dict) -> Some[str] | type[Nothing]:
            email = user.get("email")
            if email:
                return Some(email)
            return Nothing

        result = pipe(1, find_user, get_email)
        assert result == Some("alice@example.com")

        result = pipe(999, find_user, get_email)
        assert result is Nothing


class TestPipePropertyBased:
    """Property-based tests for pipe()."""

    @given(st.integers())
    def test_pipe_identity(self, value: int):
        """pipe(value, id) == Ok(value)."""
        result = pipe(value, lambda x: x)
        assert result == Ok(value)

    @given(st.integers())
    def test_pipe_associativity(self, value: int):
        """Composing functions in pipe is associative."""

        def f(x: int) -> int:
            return x + 1

        def g(x: int) -> int:
            return x * 2

        def h(x: int) -> int:
            return x - 3

        # All at once
        r1 = pipe(value, f, g, h)
        # Step by step
        r2 = pipe(value, f)
        r2 = pipe(r2, g)
        r2 = pipe(r2, h)

        assert r1 == r2


class TestDerefOkBasic:
    """Tests for DerefOk basic functionality."""

    def test_deref_ok_creation(self):
        """DerefOk wraps a value."""
        d = DerefOk(42)
        assert d.value == 42

    def test_deref_ok_unwrap(self):
        """DerefOk.unwrap() returns the value."""
        d = DerefOk(42)
        assert d.unwrap() == 42

    def test_deref_ok_is_ok(self):
        """DerefOk.is_ok() returns True."""
        d = DerefOk(42)
        assert d.is_ok() is True

    def test_deref_ok_is_err(self):
        """DerefOk.is_err() returns False."""
        d = DerefOk(42)
        assert d.is_err() is False

    def test_deref_ok_to_ok(self):
        """DerefOk.to_ok() returns Ok."""
        d = DerefOk(42)
        assert d.to_ok() == Ok(42)

    def test_deref_ok_repr(self):
        """DerefOk has readable repr."""
        d = DerefOk(42)
        assert repr(d) == "DerefOk(value=42)"

    def test_deref_ok_equality(self):
        """DerefOk equality works."""
        assert DerefOk(42) == DerefOk(42)
        assert DerefOk(42) != DerefOk(43)

    def test_deref_ok_equals_ok(self):
        """DerefOk equals equivalent Ok."""
        assert DerefOk(42) == Ok(42)

    def test_deref_ok_hashable(self):
        """DerefOk is hashable."""
        d = DerefOk(42)
        assert hash(d) == hash(DerefOk(42))


class TestDerefOkForwarding:
    """Tests for DerefOk attribute forwarding."""

    def test_deref_ok_forwards_method(self):
        """DerefOk forwards method calls to inner value."""
        d = DerefOk("hello")
        result = d.upper()
        assert result == Ok("HELLO")

    def test_deref_ok_forwards_method_with_args(self):
        """DerefOk forwards method calls with arguments."""
        d = DerefOk("hello world")
        result = d.split(" ")
        assert result == Ok(["hello", "world"])

    def test_deref_ok_forwards_method_chain(self):
        """Methods can be called in sequence (not chained on result)."""
        d = DerefOk("hello")
        result1 = d.upper()
        result2 = d.replace("l", "L")
        assert result1 == Ok("HELLO")
        assert result2 == Ok("heLLo")

    def test_deref_ok_method_returns_result(self):
        """Method returning Result is not double-wrapped."""

        class MyStr(str):
            def checked_upper(self) -> Ok[str]:
                return Ok(self.upper())

        d = DerefOk(MyStr("hello"))
        result = d.checked_upper()
        assert result == Ok("HELLO")

    def test_deref_ok_access_property(self):
        """DerefOk can access properties of inner value."""

        class Point:
            def __init__(self, x: int, y: int):
                self.x = x
                self.y = y

        d = DerefOk(Point(3, 4))
        assert d.x == 3
        assert d.y == 4


class TestDerefSomeBasic:
    """Tests for DerefSome basic functionality."""

    def test_deref_some_creation(self):
        """DerefSome wraps a value."""
        d = DerefSome(42)
        assert d.value == 42

    def test_deref_some_unwrap(self):
        """DerefSome.unwrap() returns the value."""
        d = DerefSome(42)
        assert d.unwrap() == 42

    def test_deref_some_is_some(self):
        """DerefSome.is_some() returns True."""
        d = DerefSome(42)
        assert d.is_some() is True

    def test_deref_some_is_none(self):
        """DerefSome.is_none() returns False."""
        d = DerefSome(42)
        assert d.is_none() is False

    def test_deref_some_to_some(self):
        """DerefSome.to_some() returns Some."""
        d = DerefSome(42)
        assert d.to_some() == Some(42)

    def test_deref_some_repr(self):
        """DerefSome has readable repr."""
        d = DerefSome(42)
        assert repr(d) == "DerefSome(value=42)"

    def test_deref_some_equality(self):
        """DerefSome equality works."""
        assert DerefSome(42) == DerefSome(42)
        assert DerefSome(42) != DerefSome(43)

    def test_deref_some_equals_some(self):
        """DerefSome equals equivalent Some."""
        assert DerefSome(42) == Some(42)

    def test_deref_some_hashable(self):
        """DerefSome is hashable."""
        d = DerefSome(42)
        assert hash(d) == hash(DerefSome(42))


class TestDerefSomeForwarding:
    """Tests for DerefSome attribute forwarding."""

    def test_deref_some_forwards_method(self):
        """DerefSome forwards method calls to inner value."""
        d = DerefSome("hello")
        result = d.upper()
        assert result == Some("HELLO")

    def test_deref_some_forwards_method_with_args(self):
        """DerefSome forwards method calls with arguments."""
        d = DerefSome("hello world")
        result = d.split(" ")
        assert result == Some(["hello", "world"])

    def test_deref_some_method_returns_option(self):
        """Method returning Option is not double-wrapped."""

        class MyStr(str):
            def checked_upper(self) -> Some[str]:
                return Some(self.upper())

        d = DerefSome(MyStr("hello"))
        result = d.checked_upper()
        assert result == Some("HELLO")


class TestDerefMixinProtocol:
    """Tests for custom Deref implementations."""

    def test_custom_deref_not_implemented(self):
        """Base Deref raises NotImplementedError."""
        from klaw_result.compose.deref import Deref

        class BadDeref(Deref):
            pass

        d = BadDeref()
        with pytest.raises(NotImplementedError):
            _ = d._deref_value

        with pytest.raises(NotImplementedError):
            _ = d._deref_wrapper


class TestDerefWithList:
    """Tests for Deref with list values."""

    def test_deref_ok_list_methods(self):
        """DerefOk works with list methods."""
        d = DerefOk([1, 2, 3])
        result = d.copy()
        assert result == Ok([1, 2, 3])

    def test_deref_some_list_index(self):
        """DerefSome works with list __getitem__ via method."""
        d = DerefSome([1, 2, 3])
        # Access length
        assert len(d.value) == 3


class TestDerefWithDict:
    """Tests for Deref with dict values."""

    def test_deref_ok_dict_methods(self):
        """DerefOk works with dict methods."""
        d = DerefOk({"a": 1, "b": 2})
        result = d.keys()
        # dict_keys is wrapped in Ok
        assert isinstance(result, Ok)

    def test_deref_ok_dict_get(self):
        """DerefOk.get() works on dict."""
        d = DerefOk({"a": 1, "b": 2})
        result = d.get("a")
        assert result == Ok(1)

        result = d.get("z", 0)
        assert result == Ok(0)
