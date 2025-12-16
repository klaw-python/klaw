"""Tests for Result type (Ok and Err)."""

import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from klaw_result import Err, Nothing, Ok, Propagate, Result, Some, collect


class TestOkCreation:
    """Tests for Ok instantiation and basic properties."""

    def test_ok_creation(self):
        """Ok wraps a value."""
        ok = Ok(42)
        assert ok.value == 42

    def test_ok_with_none(self):
        """Ok can wrap None."""
        ok = Ok(None)
        assert ok.value is None

    def test_ok_with_complex_value(self):
        """Ok can wrap complex values."""
        data = {"key": [1, 2, 3]}
        ok = Ok(data)
        assert ok.value == data

    def test_ok_is_frozen(self):
        """Ok instances are immutable."""
        ok = Ok(42)
        with pytest.raises(AttributeError):
            ok.value = 100  # type: ignore[misc]


class TestErrCreation:
    """Tests for Err instantiation and basic properties."""

    def test_err_creation(self):
        """Err wraps an error value."""
        err = Err("error message")
        assert err.error == "error message"

    def test_err_with_exception(self):
        """Err can wrap exception objects."""
        exc = ValueError("something went wrong")
        err = Err(exc)
        assert err.error is exc

    def test_err_is_frozen(self):
        """Err instances are immutable."""
        err = Err("error")
        with pytest.raises(AttributeError):
            err.error = "new error"  # type: ignore[misc]


class TestResultEquality:
    """Tests for Result equality and hashing."""

    def test_ok_equality(self):
        """Ok instances with same value are equal."""
        assert Ok(42) == Ok(42)
        assert Ok("hello") == Ok("hello")

    def test_ok_inequality(self):
        """Ok instances with different values are not equal."""
        assert Ok(42) != Ok(43)
        assert Ok("hello") != Ok("world")

    def test_err_equality(self):
        """Err instances with same error are equal."""
        assert Err("error") == Err("error")

    def test_err_inequality(self):
        """Err instances with different errors are not equal."""
        assert Err("error1") != Err("error2")

    def test_ok_not_equal_to_err(self):
        """Ok is never equal to Err."""
        assert Ok(42) != Err(42)

    def test_ok_hashable(self):
        """Ok instances are hashable."""
        ok = Ok(42)
        assert hash(ok) == hash(Ok(42))
        assert {ok: "value"}[Ok(42)] == "value"

    def test_err_hashable(self):
        """Err instances are hashable."""
        err = Err("error")
        assert hash(err) == hash(Err("error"))
        assert {err: "value"}[Err("error")] == "value"


class TestResultQuerying:
    """Tests for is_ok() and is_err() methods."""

    def test_ok_is_ok(self):
        """Ok.is_ok() returns True."""
        assert Ok(42).is_ok() is True

    def test_ok_is_err(self):
        """Ok.is_err() returns False."""
        assert Ok(42).is_err() is False

    def test_err_is_ok(self):
        """Err.is_ok() returns False."""
        assert Err("error").is_ok() is False

    def test_err_is_err(self):
        """Err.is_err() returns True."""
        assert Err("error").is_err() is True


class TestResultUnwrap:
    """Tests for unwrap, unwrap_or, unwrap_or_else, expect."""

    def test_ok_unwrap(self):
        """Ok.unwrap() returns the value."""
        assert Ok(42).unwrap() == 42

    def test_err_unwrap_raises(self):
        """Err.unwrap() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Called unwrap on Err"):
            Err("error").unwrap()

    def test_ok_unwrap_or(self):
        """Ok.unwrap_or() returns the value, ignoring default."""
        assert Ok(42).unwrap_or(0) == 42

    def test_err_unwrap_or(self):
        """Err.unwrap_or() returns the default."""
        assert Err("error").unwrap_or(0) == 0

    def test_ok_unwrap_or_else(self):
        """Ok.unwrap_or_else() returns the value, not calling the function."""
        called = False

        def factory():
            nonlocal called
            called = True
            return 0

        assert Ok(42).unwrap_or_else(factory) == 42
        assert called is False

    def test_err_unwrap_or_else(self):
        """Err.unwrap_or_else() calls the function."""
        assert Err("error").unwrap_or_else(lambda: 0) == 0

    def test_ok_expect(self):
        """Ok.expect() returns the value."""
        assert Ok(42).expect("should not fail") == 42

    def test_err_expect_raises(self):
        """Err.expect() raises with custom message."""
        with pytest.raises(RuntimeError, match="custom message"):
            Err("error").expect("custom message")


class TestResultMap:
    """Tests for map and map_err methods."""

    def test_ok_map(self):
        """Ok.map() transforms the value."""
        result = Ok(5).map(lambda x: x * 2)
        assert result == Ok(10)

    def test_ok_map_chain(self):
        """Ok.map() can be chained."""
        result = Ok(5).map(lambda x: x * 2).map(str)
        assert result == Ok("10")

    def test_err_map(self):
        """Err.map() returns self unchanged."""
        err: Result[int, str] = Err("error")
        result = err.map(lambda x: x * 2)
        assert result == Err("error")

    def test_ok_map_err(self):
        """Ok.map_err() returns self unchanged."""
        result = Ok(42).map_err(str.upper)
        assert result == Ok(42)

    def test_err_map_err(self):
        """Err.map_err() transforms the error."""
        result = Err("error").map_err(str.upper)
        assert result == Err("ERROR")


class TestResultAndThen:
    """Tests for and_then (flatmap/bind) and or_else methods."""

    def test_ok_and_then_returns_ok(self):
        """Ok.and_then() with function returning Ok."""
        result = Ok(5).and_then(lambda x: Ok(x * 2))
        assert result == Ok(10)

    def test_ok_and_then_returns_err(self):
        """Ok.and_then() with function returning Err."""
        result = Ok(5).and_then(lambda x: Err(f"failed with {x}"))
        assert result == Err("failed with 5")

    def test_err_and_then(self):
        """Err.and_then() returns self unchanged."""
        err: Result[int, str] = Err("error")
        result = err.and_then(lambda x: Ok(x * 2))
        assert result == Err("error")

    def test_ok_or_else(self):
        """Ok.or_else() returns self unchanged."""
        result = Ok(42).or_else(lambda e: Ok(0))
        assert result == Ok(42)

    def test_err_or_else_returns_ok(self):
        """Err.or_else() with recovery function returning Ok."""
        result = Err("error").or_else(lambda e: Ok(0))
        assert result == Ok(0)

    def test_err_or_else_returns_err(self):
        """Err.or_else() with function returning new Err."""
        result = Err("error").or_else(lambda e: Err(f"wrapped: {e}"))
        assert result == Err("wrapped: error")


class TestResultConversion:
    """Tests for ok(), err() conversion to Option."""

    def test_ok_to_option(self):
        """Ok.ok() returns Some(value)."""
        result = Ok(42).ok()
        assert result == Some(42)

    def test_err_to_option(self):
        """Err.ok() returns Nothing."""
        result = Err("error").ok()
        assert result is Nothing

    def test_ok_err_to_option(self):
        """Ok.err() returns Nothing."""
        result = Ok(42).err()
        assert result is Nothing

    def test_err_err_to_option(self):
        """Err.err() returns Some(error)."""
        result = Err("error").err()
        assert result == Some("error")


class TestResultCombining:
    """Tests for and_, or_, zip, flatten."""

    def test_ok_and(self):
        """Ok.and_() returns other."""
        result = Ok(1).and_(Ok(2))
        assert result == Ok(2)

    def test_ok_and_err(self):
        """Ok.and_() with Err returns the Err."""
        result = Ok(1).and_(Err("error"))
        assert result == Err("error")

    def test_err_and(self):
        """Err.and_() returns self."""
        result = Err("error").and_(Ok(2))
        assert result == Err("error")

    def test_ok_or(self):
        """Ok.or_() returns self."""
        result = Ok(1).or_(Ok(2))
        assert result == Ok(1)

    def test_err_or_ok(self):
        """Err.or_() returns other Ok."""
        result = Err("error").or_(Ok(2))
        assert result == Ok(2)

    def test_err_or_err(self):
        """Err.or_() with Err returns other Err."""
        result = Err("error1").or_(Err("error2"))
        assert result == Err("error2")

    def test_ok_zip_ok(self):
        """Ok.zip() with Ok returns Ok of tuple."""
        result = Ok(1).zip(Ok(2))
        assert result == Ok((1, 2))

    def test_ok_zip_err(self):
        """Ok.zip() with Err returns the Err."""
        result = Ok(1).zip(Err("error"))
        assert result == Err("error")

    def test_err_zip(self):
        """Err.zip() returns self."""
        result = Err("error").zip(Ok(2))
        assert result == Err("error")

    def test_ok_flatten(self):
        """Ok containing Ok flattens to Ok."""
        nested: Ok[Ok[int]] = Ok(Ok(42))
        result = nested.flatten()
        assert result == Ok(42)

    def test_ok_flatten_err(self):
        """Ok containing Err flattens to Err."""
        nested: Ok[Err[str]] = Ok(Err("error"))
        result = nested.flatten()
        assert result == Err("error")

    def test_err_flatten(self):
        """Err.flatten() returns self."""
        result = Err("error").flatten()
        assert result == Err("error")


class TestResultCollect:
    """Tests for collect() function."""

    def test_collect_all_ok(self):
        """collect() with all Ok returns Ok of list."""
        results: list[Ok[int] | Err[str]] = [Ok(1), Ok(2), Ok(3)]
        result = collect(results)
        assert result == Ok([1, 2, 3])

    def test_collect_with_err(self):
        """collect() short-circuits on first Err."""
        results: list[Ok[int] | Err[str]] = [Ok(1), Err("error"), Ok(3)]
        result = collect(results)
        assert result == Err("error")

    def test_collect_empty(self):
        """collect() with empty iterable returns Ok([])."""
        result = collect([])
        assert result == Ok([])

    def test_collect_first_err(self):
        """collect() returns the first Err encountered."""
        results: list[Ok[int] | Err[str]] = [Err("first"), Err("second")]
        result = collect(results)
        assert result == Err("first")


class TestResultBail:
    """Tests for bail() and unwrap_or_return() methods."""

    def test_ok_bail(self):
        """Ok.bail() returns the value."""
        assert Ok(42).bail() == 42

    def test_err_bail_raises_propagate(self):
        """Err.bail() raises Propagate."""
        err = Err("error")
        with pytest.raises(Propagate) as exc_info:
            err.bail()
        assert exc_info.value.value is err

    def test_ok_unwrap_or_return(self):
        """Ok.unwrap_or_return() returns the value."""
        assert Ok(42).unwrap_or_return() == 42

    def test_err_unwrap_or_return_raises_propagate(self):
        """Err.unwrap_or_return() raises Propagate."""
        err = Err("error")
        with pytest.raises(Propagate) as exc_info:
            err.unwrap_or_return()
        assert exc_info.value.value is err


class TestResultPipeOperator:
    """Tests for the | (pipe) operator."""

    def test_ok_pipe_function(self):
        """Ok | f applies f and wraps result in Ok."""
        result = Ok(5) | (lambda x: x * 2)
        assert result == Ok(10)

    def test_ok_pipe_chain(self):
        """Pipe operator can be chained."""
        result = Ok(5) | (lambda x: x * 2) | str
        assert result == Ok("10")

    def test_ok_pipe_returns_result(self):
        """Pipe with function returning Result doesn't double-wrap."""
        result = Ok(5) | (lambda x: Ok(x * 2))
        assert result == Ok(10)

    def test_err_pipe(self):
        """Err | f returns self unchanged."""
        result = Err("error") | (lambda x: x * 2)
        assert result == Err("error")


class TestResultPatternMatching:
    """Tests for pattern matching support."""

    def test_match_ok(self):
        """Pattern matching on Ok extracts value."""
        result: Result[int, str] = Ok(42)
        match result:
            case Ok(value):
                assert value == 42
            case Err(_):
                pytest.fail("Should not match Err")

    def test_match_err(self):
        """Pattern matching on Err extracts error."""
        result: Result[int, str] = Err("error")
        match result:
            case Ok(_):
                pytest.fail("Should not match Ok")
            case Err(error):
                assert error == "error"


class TestResultRepr:
    """Tests for __repr__ (provided by msgspec.Struct)."""

    def test_ok_repr(self):
        """Ok has readable repr."""
        assert repr(Ok(42)) == "Ok(value=42)"

    def test_err_repr(self):
        """Err has readable repr."""
        assert repr(Err("error")) == "Err(error='error')"


class TestResultCopy:
    """Tests for copy behavior."""

    def test_ok_copy(self):
        """Ok can be copied."""
        ok = Ok(42)
        copied = copy.copy(ok)
        assert copied == ok
        assert copied is not ok

    def test_err_copy(self):
        """Err can be copied."""
        err = Err("error")
        copied = copy.copy(err)
        assert copied == err
        assert copied is not err


class TestResultContextManager:
    """Tests for context manager support."""

    def test_ok_context_manager(self):
        """Ok works as context manager, yielding value."""
        with Ok(42) as value:
            assert value == 42

    def test_err_context_manager_raises(self):
        """Err context manager raises Propagate."""
        with pytest.raises(Propagate) as exc_info:
            with Err("error") as _value:
                pass  # Never reached
        assert exc_info.value.value == Err("error")


class TestResultMonadLaws:
    """Property-based tests for monad laws."""

    @given(st.integers())
    def test_left_identity(self, value: int):
        """Left identity: Ok(a).and_then(f) == f(a)."""

        def f(x: int) -> Ok[int] | Err[str]:
            return Ok(x * 2)

        assert Ok(value).and_then(f) == f(value)

    @given(st.integers())
    def test_right_identity(self, value: int):
        """Right identity: m.and_then(Ok) == m."""
        m = Ok(value)
        assert m.and_then(Ok) == m

    @given(st.integers())
    def test_associativity(self, value: int):
        """Associativity: m.and_then(f).and_then(g) == m.and_then(x => f(x).and_then(g))."""

        def f(x: int) -> Ok[int] | Err[str]:
            return Ok(x + 1)

        def g(x: int) -> Ok[str] | Err[str]:
            return Ok(str(x))

        m = Ok(value)
        left = m.and_then(f).and_then(g)
        right = m.and_then(lambda x: f(x).and_then(g))
        assert left == right


class TestResultFunctorLaws:
    """Property-based tests for functor laws."""

    @given(st.integers())
    def test_identity(self, value: int):
        """Identity: m.map(id) == m."""
        m = Ok(value)
        assert m.map(lambda x: x) == m

    @given(st.integers())
    def test_composition(self, value: int):
        """Composition: m.map(f).map(g) == m.map(g . f)."""

        def f(x: int) -> int:
            return x + 1

        def g(x: int) -> str:
            return str(x)

        m = Ok(value)
        assert m.map(f).map(g) == m.map(lambda x: g(f(x)))
