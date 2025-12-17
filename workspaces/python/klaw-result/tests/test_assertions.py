"""Tests for assertion utilities."""

import subprocess
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

from klaw_result import Err, Ok, assert_result, result, safe_assert


class TestSafeAssert:
    """Tests for safe_assert function."""

    def test_passes_on_true(self):
        """safe_assert does not raise when condition is True."""
        safe_assert(True)
        safe_assert(1 == 1)
        safe_assert(bool([1, 2, 3]))

    def test_raises_on_false(self):
        """safe_assert raises AssertionError when condition is False."""
        with pytest.raises(AssertionError):
            safe_assert(False)

    def test_raises_with_message(self):
        """safe_assert includes message in AssertionError."""
        with pytest.raises(AssertionError, match="custom message"):
            safe_assert(False, "custom message")

    def test_empty_message_on_false(self):
        """safe_assert raises with empty message by default."""
        with pytest.raises(AssertionError, match="^$"):
            safe_assert(False)

    def test_works_in_optimized_mode(self):
        """safe_assert works even with python -O."""
        code = """
from klaw_result import safe_assert
try:
    safe_assert(False, "should fail")
    print("NO_ERROR")
except AssertionError as e:
    print(f"ASSERTION_ERROR:{e}")
"""
        result = subprocess.run(
            [sys.executable, "-O", "-c", code],
            capture_output=True,
            text=True,
        )
        assert "ASSERTION_ERROR:should fail" in result.stdout

    @given(st.booleans())
    def test_consistent_with_bool(self, condition: bool):
        """safe_assert raises iff condition is False."""
        if condition:
            safe_assert(condition)
        else:
            with pytest.raises(AssertionError):
                safe_assert(condition)


class TestAssertResult:
    """Tests for assert_result function."""

    def test_returns_ok_on_true(self):
        """assert_result returns Ok(None) when condition is True."""
        result = assert_result(True, "error")
        assert result == Ok(None)

    def test_returns_err_on_false(self):
        """assert_result returns Err(error) when condition is False."""
        result = assert_result(False, "validation failed")
        assert result == Err("validation failed")

    def test_with_exception_error(self):
        """assert_result works with exception as error."""
        result = assert_result(False, ValueError("bad value"))
        assert isinstance(result, Err)
        assert isinstance(result.error, ValueError)
        assert str(result.error) == "bad value"

    def test_with_custom_error_type(self):
        """assert_result works with custom error types."""

        class ValidationError:
            def __init__(self, field: str, msg: str):
                self.field = field
                self.msg = msg

        result = assert_result(False, ValidationError("age", "must be positive"))
        assert isinstance(result, Err)
        assert result.error.field == "age"
        assert result.error.msg == "must be positive"

    def test_lazy_error_not_called_on_true(self):
        """Lazy error factory is not called when condition is True."""
        called = []

        def make_error():
            called.append(True)
            return "error"

        result = assert_result(True, make_error, lazy=True)
        assert result == Ok(None)
        assert called == []

    def test_lazy_error_called_on_false(self):
        """Lazy error factory is called when condition is False."""
        called = []

        def make_error():
            called.append(True)
            return "lazy error"

        result = assert_result(False, make_error, lazy=True)
        assert result == Err("lazy error")
        assert called == [True]

    def test_lazy_with_lambda(self):
        """Lazy mode works with lambda."""
        result = assert_result(False, lambda: ValueError("computed"), lazy=True)
        assert isinstance(result, Err)
        assert isinstance(result.error, ValueError)

    def test_non_lazy_callable_stored_as_is(self):
        """Without lazy=True, callable is stored as the error value."""

        def my_func():
            return "never called"

        result = assert_result(False, my_func)
        assert isinstance(result, Err)
        assert result.error is my_func

    def test_with_result_decorator(self):
        """assert_result works with @result decorator for validation chains."""

        @result
        def validate(value: int):
            assert_result(value > 0, "must be positive").bail()
            assert_result(value < 100, "must be under 100").bail()
            return Ok(value * 2)

        assert validate(50) == Ok(100)
        assert validate(-5) == Err("must be positive")
        assert validate(150) == Err("must be under 100")

    def test_chained_with_and_then(self):
        """assert_result chains with and_then for sequential validation."""

        def validate_positive(n: int):
            return assert_result(n > 0, "not positive").and_then(lambda _: Ok(n))

        def validate_even(n: int):
            return assert_result(n % 2 == 0, "not even").and_then(lambda _: Ok(n))

        result = Ok(4).and_then(validate_positive).and_then(validate_even)
        assert result == Ok(4)

        result = Ok(-1).and_then(validate_positive).and_then(validate_even)
        assert result == Err("not positive")

        result = Ok(3).and_then(validate_positive).and_then(validate_even)
        assert result == Err("not even")

    @given(st.booleans(), st.text())
    def test_result_matches_condition(self, condition: bool, error: str):
        """assert_result returns Ok iff condition is True."""
        result = assert_result(condition, error)
        if condition:
            assert result == Ok(None)
        else:
            assert result == Err(error)


class TestAssertResultIntegration:
    """Integration tests for assertion utilities with Result types."""

    def test_form_validation_pattern(self):
        """Demonstrates form validation pattern with assert_result."""

        def validate_username(username: str):
            return (
                assert_result(len(username) >= 3, "username too short")
                .and_then(
                    lambda _: assert_result(len(username) <= 20, "username too long")
                )
                .and_then(
                    lambda _: assert_result(
                        username.isalnum(), "username must be alphanumeric"
                    )
                )
                .and_then(lambda _: Ok(username))
            )

        assert validate_username("alice") == Ok("alice")
        assert validate_username("ab") == Err("username too short")
        assert validate_username("a" * 30) == Err("username too long")
        assert validate_username("alice!") == Err("username must be alphanumeric")

    def test_with_bail_pattern(self):
        """Demonstrates bail() pattern with assert_result."""

        @result
        def process_order(quantity: int, price: float):
            assert_result(quantity > 0, "quantity must be positive").bail()
            assert_result(price > 0, "price must be positive").bail()
            assert_result(quantity * price <= 10000, "order too large").bail()
            return Ok({"quantity": quantity, "total": quantity * price})

        assert process_order(5, 10.0) == Ok({"quantity": 5, "total": 50.0})
        assert process_order(0, 10.0) == Err("quantity must be positive")
        assert process_order(5, -10.0) == Err("price must be positive")
        assert process_order(1000, 100.0) == Err("order too large")

    def test_lazy_error_with_expensive_message(self):
        """Lazy errors avoid expensive error message construction."""
        call_count = 0

        def expensive_error():
            nonlocal call_count
            call_count += 1
            return f"Error computed {call_count} time(s)"

        assert_result(True, expensive_error, lazy=True)
        assert_result(True, expensive_error, lazy=True)
        assert call_count == 0

        result = assert_result(False, expensive_error, lazy=True)
        assert call_count == 1
        assert result == Err("Error computed 1 time(s)")

    def test_collect_validation_errors(self):
        """Collect all validation results."""
        from klaw_result import collect

        validations = [
            assert_result(True, "error1"),
            assert_result(True, "error2"),
            assert_result(True, "error3"),
        ]
        result = collect(validations)
        assert result == Ok([None, None, None])

        validations = [
            assert_result(True, "error1"),
            assert_result(False, "error2"),
            assert_result(True, "error3"),
        ]
        result = collect(validations)
        assert result == Err("error2")
