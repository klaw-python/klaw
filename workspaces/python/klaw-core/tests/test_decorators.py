"""Tests for decorators: @safe, @pipe, @result, @do."""

import pytest
from klaw_core import (
    Err,
    Ok,
    do,
    do_async,
    pipe,
    pipe_async,
    result,
    safe,
    safe_async,
)


class TestSafeDecorator:
    """Tests for @safe decorator."""

    def test_safe_returns_ok_on_success(self):
        """@safe wraps successful return in Ok."""

        @safe
        def divide(a: int, b: int) -> float:
            return a / b

        result = divide(10, 2)
        assert result == Ok(5.0)

    def test_safe_returns_err_on_exception(self):
        """@safe catches exception and returns Err."""

        @safe
        def divide(a: int, b: int) -> float:
            return a / b

        result = divide(10, 0)
        assert isinstance(result, Err)
        assert isinstance(result.error, ZeroDivisionError)

    def test_safe_with_exceptions_param(self):
        """@safe(exceptions=...) catches only specified exceptions."""

        @safe(exceptions=(ValueError,))
        def risky(x: int) -> int:
            if x < 0:
                raise ValueError('negative')
            if x == 0:
                raise TypeError('zero')
            return x

        assert risky(5) == Ok(5)
        assert isinstance(risky(-1), Err)
        assert isinstance(risky(-1).error, ValueError)

        with pytest.raises(TypeError):
            risky(0)

    def test_safe_preserves_function_name(self):
        """@safe preserves function metadata."""

        @safe
        def my_function():
            pass

        assert my_function.__name__ == 'my_function'

    def test_safe_with_kwargs(self):
        """@safe works with keyword arguments."""

        @safe
        def greet(name: str, greeting: str = 'Hello') -> str:
            return f'{greeting}, {name}!'

        assert greet('World') == Ok('Hello, World!')
        assert greet(name='Python', greeting='Hi') == Ok('Hi, Python!')


class TestSafeAsyncDecorator:
    """Tests for @safe_async decorator."""

    async def test_safe_async_returns_ok_on_success(self):
        """@safe_async wraps successful return in Ok."""

        @safe_async
        async def fetch(x: int) -> int:
            return x * 2

        result = await fetch(5)
        assert result == Ok(10)

    async def test_safe_async_returns_err_on_exception(self):
        """@safe_async catches exception and returns Err."""

        @safe_async
        async def fail() -> int:
            raise ValueError('async error')

        result = await fail()
        assert isinstance(result, Err)
        assert isinstance(result.error, ValueError)

    async def test_safe_async_with_exceptions_param(self):
        """@safe_async(exceptions=...) catches only specified exceptions."""

        @safe_async(exceptions=(ValueError,))
        async def risky(x: int) -> int:
            if x < 0:
                raise ValueError('negative')
            return x

        assert await risky(5) == Ok(5)
        result = await risky(-1)
        assert isinstance(result, Err)


class TestPipeDecorator:
    """Tests for @pipe decorator."""

    def test_pipe_wraps_in_ok(self):
        """@pipe wraps return value in Ok."""

        @pipe
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == Ok(5)

    def test_pipe_with_none(self):
        """@pipe wraps None in Ok."""

        @pipe
        def return_none() -> None:
            return None

        assert return_none() == Ok(None)

    def test_pipe_preserves_function_name(self):
        """@pipe preserves function metadata."""

        @pipe
        def my_function():
            pass

        assert my_function.__name__ == 'my_function'


class TestPipeAsyncDecorator:
    """Tests for @pipe_async decorator."""

    async def test_pipe_async_wraps_in_ok(self):
        """@pipe_async wraps return value in Ok."""

        @pipe_async
        async def fetch(x: int) -> int:
            return x * 2

        assert await fetch(5) == Ok(10)


class TestResultDecorator:
    """Tests for @result decorator."""

    def test_result_passes_through_ok(self):
        """@result passes through Ok unchanged."""

        @result
        def compute(x: int) -> Ok[int] | Err[str]:
            return Ok(x * 2)

        assert compute(5) == Ok(10)

    def test_result_passes_through_err(self):
        """@result passes through Err unchanged."""

        @result
        def compute(x: int) -> Ok[int] | Err[str]:
            return Err('failed')

        assert compute(5) == Err('failed')

    def test_result_catches_propagate_from_bail(self):
        """@result catches Propagate from .bail() and returns Err."""

        @result
        def compute(x: int) -> Ok[int] | Err[str]:
            if x < 0:
                Err('negative').bail()
            return Ok(x * 2)

        assert compute(5) == Ok(10)
        assert compute(-1) == Err('negative')

    def test_result_chains_bail(self):
        """@result enables chaining with .bail()."""

        def get_value(x: int) -> Ok[int] | Err[str]:
            if x < 0:
                return Err('negative')
            return Ok(x)

        @result
        def double_if_positive(x: int) -> Ok[int] | Err[str]:
            value = get_value(x).bail()
            return Ok(value * 2)

        assert double_if_positive(5) == Ok(10)
        assert double_if_positive(-1) == Err('negative')


class TestResultDecoratorAsync:
    """Tests for @result decorator with async functions."""

    async def test_result_async_passes_through_ok(self):
        """@result passes through Ok unchanged for async."""

        @result
        async def compute(x: int) -> Ok[int] | Err[str]:
            return Ok(x * 2)

        assert await compute(5) == Ok(10)

    async def test_result_async_catches_propagate(self):
        """@result catches Propagate from .bail() in async functions."""

        async def async_get_value(x: int) -> Ok[int] | Err[str]:
            if x < 0:
                return Err('negative')
            return Ok(x)

        @result
        async def double_if_positive(x: int) -> Ok[int] | Err[str]:
            value = (await async_get_value(x)).bail()
            return Ok(value * 2)

        assert await double_if_positive(5) == Ok(10)
        assert await double_if_positive(-1) == Err('negative')


class TestDoDecorator:
    """Tests for @do decorator (do-notation)."""

    def test_do_extracts_ok_values(self):
        """@do extracts values from Ok and returns final Ok."""

        @do
        def compute():
            x = yield Ok(5)
            y = yield Ok(3)
            return x + y

        assert compute() == Ok(8)

    def test_do_short_circuits_on_err(self):
        """@do short-circuits on first Err."""

        @do
        def compute():
            x = yield Ok(5)
            y = yield Err('failed')
            return x + y  # Never reached

        assert compute() == Err('failed')

    def test_do_with_function_calls(self):
        """@do works with function calls that return Results."""

        def get_x() -> Ok[int] | Err[str]:
            return Ok(10)

        def get_y() -> Ok[int] | Err[str]:
            return Ok(20)

        @do
        def compute():
            x = yield get_x()
            y = yield get_y()
            return x + y

        assert compute() == Ok(30)

    def test_do_with_failing_function(self):
        """@do short-circuits when function returns Err."""

        def get_x() -> Ok[int] | Err[str]:
            return Ok(10)

        def get_y() -> Ok[int] | Err[str]:
            return Err('y failed')

        @do
        def compute():
            x = yield get_x()
            y = yield get_y()
            return x + y

        assert compute() == Err('y failed')


class TestDoAsyncDecorator:
    """Tests for @do_async decorator (async do-notation)."""

    async def test_do_async_extracts_ok_values(self):
        """@do_async extracts values from Ok."""

        @do_async
        async def compute():
            x = yield Ok(5)
            y = yield Ok(3)
            yield Ok(x + y)

        assert await compute() == Ok(8)

    async def test_do_async_short_circuits_on_err(self):
        """@do_async short-circuits on first Err."""

        @do_async
        async def compute():
            x = yield Ok(5)
            y = yield Err('failed')
            yield Ok(x + y)

        assert await compute() == Err('failed')

    async def test_do_async_with_await(self):
        """@do_async works with awaited Results."""

        async def fetch_x() -> Ok[int] | Err[str]:
            return Ok(10)

        async def fetch_y() -> Ok[int] | Err[str]:
            return Ok(20)

        @do_async
        async def compute():
            x = yield await fetch_x()
            y = yield await fetch_y()
            yield Ok(x + y)

        assert await compute() == Ok(30)


class TestDecoratorComposition:
    """Tests for composing multiple decorators."""

    def test_safe_with_result(self):
        """@safe can be composed with @result."""

        @safe
        def risky_divide(a: int, b: int) -> float:
            return a / b

        @result
        def compute(a: int, b: int) -> Ok[float] | Err[Exception]:
            value = risky_divide(a, b).bail()
            return Ok(value * 2)

        assert compute(10, 2) == Ok(10.0)
        res = compute(10, 0)
        assert isinstance(res, Err)
        assert isinstance(res.error, ZeroDivisionError)
