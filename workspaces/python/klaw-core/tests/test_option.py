"""Tests for Option type (Some and Nothing)."""

import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st
from klaw_core import Err, Nothing, NothingType, Ok, Option, Propagate, Some


class TestSomeCreation:
    """Tests for Some instantiation and basic properties."""

    def test_some_creation(self):
        """Some wraps a value."""
        some = Some(42)
        assert some.value == 42

    def test_some_with_none(self):
        """Some can wrap None (Some(None) is not Nothing)."""
        some = Some(None)
        assert some.value is None
        assert some is not Nothing

    def test_some_with_complex_value(self):
        """Some can wrap complex values."""
        data = {'key': [1, 2, 3]}
        some = Some(data)
        assert some.value == data

    def test_some_is_frozen(self):
        """Some instances are immutable."""
        some = Some(42)
        with pytest.raises(AttributeError):
            some.value = 100  # type: ignore[misc]


class TestNothingCreation:
    """Tests for Nothing singleton."""

    def test_nothing_is_singleton(self):
        """Nothing is a singleton."""
        assert Nothing is Nothing
        assert isinstance(Nothing, NothingType)

    def test_nothing_type_instances_equal(self):
        """Multiple NothingType instances are equal."""
        n1 = NothingType()
        n2 = NothingType()
        assert n1 == n2

    def test_nothing_is_frozen(self):
        """Nothing is immutable."""
        with pytest.raises(AttributeError):
            Nothing.value = 42  # type: ignore[attr-defined]


class TestOptionEquality:
    """Tests for Option equality and hashing."""

    def test_some_equality(self):
        """Some instances with same value are equal."""
        assert Some(42) == Some(42)
        assert Some('hello') == Some('hello')

    def test_some_inequality(self):
        """Some instances with different values are not equal."""
        assert Some(42) != Some(43)
        assert Some('hello') != Some('world')

    def test_nothing_equality(self):
        """Nothing equals itself and other NothingType instances."""
        assert Nothing == Nothing
        assert Nothing == NothingType()

    def test_some_not_equal_to_nothing(self):
        """Some is never equal to Nothing."""
        assert Some(42) != Nothing
        assert Some(None) != Nothing

    def test_some_hashable(self):
        """Some instances are hashable."""
        some = Some(42)
        assert hash(some) == hash(Some(42))
        assert {some: 'value'}[Some(42)] == 'value'

    def test_nothing_hashable(self):
        """Nothing is hashable."""
        assert hash(Nothing) == hash(NothingType())
        assert {Nothing: 'value'}[Nothing] == 'value'


class TestOptionQuerying:
    """Tests for is_some() and is_none() methods."""

    def test_some_is_some(self):
        """Some.is_some() returns True."""
        assert Some(42).is_some() is True

    def test_some_is_none(self):
        """Some.is_none() returns False."""
        assert Some(42).is_none() is False

    def test_nothing_is_some(self):
        """Nothing.is_some() returns False."""
        assert Nothing.is_some() is False

    def test_nothing_is_none(self):
        """Nothing.is_none() returns True."""
        assert Nothing.is_none() is True


class TestOptionUnwrap:
    """Tests for unwrap, unwrap_or, unwrap_or_else, expect."""

    def test_some_unwrap(self):
        """Some.unwrap() returns the value."""
        assert Some(42).unwrap() == 42

    def test_nothing_unwrap_raises(self):
        """Nothing.unwrap() raises RuntimeError."""
        with pytest.raises(RuntimeError, match='Called unwrap on Nothing'):
            Nothing.unwrap()

    def test_some_unwrap_or(self):
        """Some.unwrap_or() returns the value, ignoring default."""
        assert Some(42).unwrap_or(0) == 42

    def test_nothing_unwrap_or(self):
        """Nothing.unwrap_or() returns the default."""
        assert Nothing.unwrap_or(0) == 0

    def test_some_unwrap_or_else(self):
        """Some.unwrap_or_else() returns the value, not calling the function."""
        called = False

        def factory():
            nonlocal called
            called = True
            return 0

        assert Some(42).unwrap_or_else(factory) == 42
        assert called is False

    def test_nothing_unwrap_or_else(self):
        """Nothing.unwrap_or_else() calls the function."""
        assert Nothing.unwrap_or_else(lambda: 0) == 0

    def test_some_expect(self):
        """Some.expect() returns the value."""
        assert Some(42).expect('should not fail') == 42

    def test_nothing_expect_raises(self):
        """Nothing.expect() raises with custom message."""
        with pytest.raises(RuntimeError, match='custom message'):
            Nothing.expect('custom message')


class TestOptionMap:
    """Tests for map method."""

    def test_some_map(self):
        """Some.map() transforms the value."""
        result = Some(5).map(lambda x: x * 2)
        assert result == Some(10)

    def test_some_map_chain(self):
        """Some.map() can be chained."""
        result = Some(5).map(lambda x: x * 2).map(str)
        assert result == Some('10')

    def test_nothing_map(self):
        """Nothing.map() returns Nothing."""
        result = Nothing.map(lambda x: x * 2)
        assert result is Nothing


class TestOptionAndThen:
    """Tests for and_then (flatmap/bind) and or_else methods."""

    def test_some_and_then_returns_some(self):
        """Some.and_then() with function returning Some."""
        result = Some(5).and_then(lambda x: Some(x * 2))
        assert result == Some(10)

    def test_some_and_then_returns_nothing(self):
        """Some.and_then() with function returning Nothing."""
        result = Some(5).and_then(lambda x: Nothing)
        assert result is Nothing

    def test_nothing_and_then(self):
        """Nothing.and_then() returns Nothing."""
        result = Nothing.and_then(lambda x: Some(x * 2))
        assert result is Nothing

    def test_some_or_else(self):
        """Some.or_else() returns self unchanged."""
        result = Some(42).or_else(lambda: Some(0))
        assert result == Some(42)

    def test_nothing_or_else_returns_some(self):
        """Nothing.or_else() with recovery function returning Some."""
        result = Nothing.or_else(lambda: Some(0))
        assert result == Some(0)

    def test_nothing_or_else_returns_nothing(self):
        """Nothing.or_else() with function returning Nothing."""
        result = Nothing.or_else(lambda: Nothing)
        assert result is Nothing


class TestOptionFilter:
    """Tests for filter method."""

    def test_some_filter_passes(self):
        """Some.filter() returns Some when predicate is True."""
        result = Some(5).filter(lambda x: x > 0)
        assert result == Some(5)

    def test_some_filter_fails(self):
        """Some.filter() returns Nothing when predicate is False."""
        result = Some(5).filter(lambda x: x < 0)
        assert result is Nothing

    def test_nothing_filter(self):
        """Nothing.filter() returns Nothing."""
        result = Nothing.filter(lambda x: True)
        assert result is Nothing


class TestOptionConversion:
    """Tests for ok_or(), ok_or_else() conversion to Result."""

    def test_some_ok_or(self):
        """Some.ok_or() returns Ok(value)."""
        result = Some(42).ok_or('error')
        assert result == Ok(42)

    def test_nothing_ok_or(self):
        """Nothing.ok_or() returns Err(error)."""
        result = Nothing.ok_or('error')
        assert result == Err('error')

    def test_some_ok_or_else(self):
        """Some.ok_or_else() returns Ok(value), not calling factory."""
        called = False

        def factory():
            nonlocal called
            called = True
            return 'error'

        result = Some(42).ok_or_else(factory)
        assert result == Ok(42)
        assert called is False

    def test_nothing_ok_or_else(self):
        """Nothing.ok_or_else() calls factory and returns Err."""
        result = Nothing.ok_or_else(lambda: 'computed error')
        assert result == Err('computed error')


class TestOptionCombining:
    """Tests for and_, or_, zip, flatten."""

    def test_some_and(self):
        """Some.and_() returns other."""
        result = Some(1).and_(Some(2))
        assert result == Some(2)

    def test_some_and_nothing(self):
        """Some.and_() with Nothing returns Nothing."""
        result = Some(1).and_(Nothing)
        assert result is Nothing

    def test_nothing_and(self):
        """Nothing.and_() returns Nothing."""
        result = Nothing.and_(Some(2))
        assert result is Nothing

    def test_some_or(self):
        """Some.or_() returns self."""
        result = Some(1).or_(Some(2))
        assert result == Some(1)

    def test_nothing_or_some(self):
        """Nothing.or_() returns other Some."""
        result = Nothing.or_(Some(2))
        assert result == Some(2)

    def test_nothing_or_nothing(self):
        """Nothing.or_() with Nothing returns Nothing."""
        result = Nothing.or_(Nothing)
        assert result is Nothing

    def test_some_zip_some(self):
        """Some.zip() with Some returns Some of tuple."""
        result = Some(1).zip(Some(2))
        assert result == Some((1, 2))

    def test_some_zip_nothing(self):
        """Some.zip() with Nothing returns Nothing."""
        result = Some(1).zip(Nothing)
        assert result is Nothing

    def test_nothing_zip(self):
        """Nothing.zip() returns Nothing."""
        result = Nothing.zip(Some(2))
        assert result is Nothing

    def test_some_flatten(self):
        """Some containing Some flattens to inner Some."""
        nested: Some[Some[int]] = Some(Some(42))
        result = nested.flatten()
        assert result == Some(42)

    def test_some_flatten_nothing(self):
        """Some containing Nothing flattens to Nothing."""
        nested: Some[NothingType] = Some(Nothing)
        result = nested.flatten()
        assert result is Nothing

    def test_nothing_flatten(self):
        """Nothing.flatten() returns Nothing."""
        result = Nothing.flatten()
        assert result is Nothing


class TestOptionBail:
    """Tests for bail() and unwrap_or_return() methods."""

    def test_some_bail(self):
        """Some.bail() returns the value."""
        assert Some(42).bail() == 42

    def test_nothing_bail_raises_propagate(self):
        """Nothing.bail() raises Propagate."""
        with pytest.raises(Propagate) as exc_info:
            Nothing.bail()
        assert exc_info.value.value is Nothing

    def test_some_unwrap_or_return(self):
        """Some.unwrap_or_return() returns the value."""
        assert Some(42).unwrap_or_return() == 42

    def test_nothing_unwrap_or_return_raises_propagate(self):
        """Nothing.unwrap_or_return() raises Propagate."""
        with pytest.raises(Propagate) as exc_info:
            Nothing.unwrap_or_return()
        assert exc_info.value.value is Nothing


class TestOptionPipeOperator:
    """Tests for the | (pipe) operator."""

    def test_some_pipe_function(self):
        """Some | f applies f and wraps result in Some."""
        result = Some(5) | (lambda x: x * 2)
        assert result == Some(10)

    def test_some_pipe_chain(self):
        """Pipe operator can be chained."""
        result = Some(5) | (lambda x: x * 2) | str
        assert result == Some('10')

    def test_nothing_pipe(self):
        """Nothing | f returns Nothing unchanged."""
        result = Nothing | (lambda x: x * 2)
        assert result is Nothing


class TestOptionPatternMatching:
    """Tests for pattern matching support."""

    def test_match_some(self):
        """Pattern matching on Some extracts value."""
        option: Option[int] = Some(42)
        match option:
            case Some(value):
                assert value == 42
            case NothingType():
                pytest.fail('Should not match Nothing')

    def test_match_nothing(self):
        """Pattern matching on Nothing."""
        option: Option[int] = Nothing
        match option:
            case Some(_):
                pytest.fail('Should not match Some')
            case NothingType():
                pass  # Success


class TestOptionRepr:
    """Tests for __repr__ (provided by msgspec.Struct)."""

    def test_some_repr(self):
        """Some has readable repr."""
        assert repr(Some(42)) == 'Some(value=42)'

    def test_nothing_repr(self):
        """Nothing has readable repr."""
        assert repr(Nothing) == 'NothingType()'


class TestOptionCopy:
    """Tests for copy behavior."""

    def test_some_copy(self):
        """Some can be copied."""
        some = Some(42)
        copied = copy.copy(some)
        assert copied == some
        assert copied is not some

    def test_nothing_copy(self):
        """Nothing can be copied (returns equivalent instance)."""
        copied = copy.copy(Nothing)
        assert copied == Nothing


class TestOptionContextManager:
    """Tests for context manager support."""

    def test_some_context_manager(self):
        """Some works as context manager, yielding value."""
        with Some(42) as value:
            assert value == 42

    def test_nothing_context_manager_raises(self):
        """Nothing context manager raises Propagate."""
        with pytest.raises(Propagate) as exc_info, Nothing as _value:
            pass  # Never reached
        assert exc_info.value.value is Nothing


class TestOptionMonadLaws:
    """Property-based tests for monad laws."""

    @given(st.integers())
    def test_left_identity(self, value: int):
        """Left identity: Some(a).and_then(f) == f(a)."""

        def f(x: int) -> Some[int] | NothingType:
            return Some(x * 2)

        assert Some(value).and_then(f) == f(value)

    @given(st.integers())
    def test_right_identity(self, value: int):
        """Right identity: m.and_then(Some) == m."""
        m = Some(value)
        assert m.and_then(Some) == m

    @given(st.integers())
    def test_associativity(self, value: int):
        """Associativity: m.and_then(f).and_then(g) == m.and_then(x => f(x).and_then(g))."""

        def f(x: int) -> Some[int] | NothingType:
            return Some(x + 1)

        def g(x: int) -> Some[str] | NothingType:
            return Some(str(x))

        m = Some(value)
        left = m.and_then(f).and_then(g)
        right = m.and_then(lambda x: f(x).and_then(g))
        assert left == right


class TestOptionFunctorLaws:
    """Property-based tests for functor laws."""

    @given(st.integers())
    def test_identity(self, value: int):
        """Identity: m.map(id) == m."""
        m = Some(value)
        assert m.map(lambda x: x) == m

    @given(st.integers())
    def test_composition(self, value: int):
        """Composition: m.map(f).map(g) == m.map(g . f)."""

        def f(x: int) -> int:
            return x + 1

        def g(x: int) -> str:
            return str(x)

        m = Some(value)
        assert m.map(f).map(g) == m.map(lambda x: g(f(x)))
