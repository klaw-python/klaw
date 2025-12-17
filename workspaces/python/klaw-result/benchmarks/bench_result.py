"""Benchmarks comparing klaw-result vs returns library.

Run with: uv run pytest benchmarks/ --benchmark-only -v
"""

# klaw-result imports
from klaw_result import Err as KErr
from klaw_result import Ok as KOk
from klaw_result import collect as k_collect
from klaw_result import safe as k_safe

# returns library imports
from returns.result import Failure, Success
from returns.result import safe as r_safe


# =============================================================================
# Creation benchmarks
# =============================================================================


class TestCreation:
    """Benchmark Result/Ok/Err creation."""

    def test_klaw_ok_creation(self, benchmark):
        """Benchmark klaw Ok creation."""
        benchmark(KOk, 42)

    def test_returns_success_creation(self, benchmark):
        """Benchmark returns Success creation."""
        benchmark(Success, 42)

    def test_klaw_err_creation(self, benchmark):
        """Benchmark klaw Err creation."""
        benchmark(KErr, "error")

    def test_returns_failure_creation(self, benchmark):
        """Benchmark returns Failure creation."""
        benchmark(Failure, "error")


# =============================================================================
# Method call benchmarks
# =============================================================================


class TestMethodCalls:
    """Benchmark common method calls."""

    def test_klaw_map(self, benchmark):
        """Benchmark klaw map."""
        ok = KOk(5)
        benchmark(ok.map, lambda x: x * 2)

    def test_returns_map(self, benchmark):
        """Benchmark returns map."""
        ok = Success(5)
        benchmark(ok.map, lambda x: x * 2)

    def test_klaw_and_then(self, benchmark):
        """Benchmark klaw and_then."""
        ok = KOk(5)
        benchmark(ok.and_then, lambda x: KOk(x * 2))

    def test_returns_bind(self, benchmark):
        """Benchmark returns bind."""
        ok = Success(5)
        benchmark(ok.bind, lambda x: Success(x * 2))

    def test_klaw_unwrap_or(self, benchmark):
        """Benchmark klaw unwrap_or."""
        ok = KOk(5)
        benchmark(ok.unwrap_or, 0)

    def test_returns_value_or(self, benchmark):
        """Benchmark returns value_or."""
        ok = Success(5)
        benchmark(ok.value_or, 0)

    def test_klaw_is_ok(self, benchmark):
        """Benchmark klaw is_ok."""
        ok = KOk(5)
        benchmark(ok.is_ok)

    def test_returns_is_success(self, benchmark):
        """Benchmark returns is_success (via isinstance)."""
        ok = Success(5)
        benchmark(lambda: isinstance(ok, Success))


# =============================================================================
# Chaining benchmarks
# =============================================================================


class TestChaining:
    """Benchmark chained operations."""

    def test_klaw_chain_3(self, benchmark):
        """Benchmark klaw 3-step chain."""

        def chain():
            return (
                KOk(5)
                .map(lambda x: x + 1)
                .map(lambda x: x * 2)
                .and_then(lambda x: KOk(x - 1))
            )

        benchmark(chain)

    def test_returns_chain_3(self, benchmark):
        """Benchmark returns 3-step chain."""

        def chain():
            return (
                Success(5)
                .map(lambda x: x + 1)
                .map(lambda x: x * 2)
                .bind(lambda x: Success(x - 1))
            )

        benchmark(chain)

    def test_klaw_chain_10(self, benchmark):
        """Benchmark klaw 10-step chain."""

        def chain():
            r = KOk(0)
            for i in range(10):
                r = r.map(lambda x, i=i: x + i)
            return r

        benchmark(chain)

    def test_returns_chain_10(self, benchmark):
        """Benchmark returns 10-step chain."""

        def chain():
            r = Success(0)
            for i in range(10):
                r = r.map(lambda x, i=i: x + i)
            return r

        benchmark(chain)


# =============================================================================
# Safe decorator benchmarks
# =============================================================================


class TestSafeDecorator:
    """Benchmark @safe decorator."""

    def test_klaw_safe_success(self, benchmark):
        """Benchmark klaw @safe on success path."""

        @k_safe
        def divide(a: int, b: int) -> float:
            return a / b

        benchmark(divide, 10, 2)

    def test_returns_safe_success(self, benchmark):
        """Benchmark returns @safe on success path."""

        @r_safe
        def divide(a: int, b: int) -> float:
            return a / b

        benchmark(divide, 10, 2)

    def test_klaw_safe_failure(self, benchmark):
        """Benchmark klaw @safe on failure path."""

        @k_safe
        def divide(a: int, b: int) -> float:
            return a / b

        benchmark(divide, 10, 0)

    def test_returns_safe_failure(self, benchmark):
        """Benchmark returns @safe on failure path."""

        @r_safe
        def divide(a: int, b: int) -> float:
            return a / b

        benchmark(divide, 10, 0)


# =============================================================================
# Collect benchmarks
# =============================================================================


class TestCollect:
    """Benchmark collecting results."""

    def test_klaw_collect_10(self, benchmark):
        """Benchmark klaw collect with 10 items."""
        items = [KOk(i) for i in range(10)]
        benchmark(k_collect, items)

    def test_klaw_collect_100(self, benchmark):
        """Benchmark klaw collect with 100 items."""
        items = [KOk(i) for i in range(100)]
        benchmark(k_collect, items)

    def test_klaw_collect_with_err(self, benchmark):
        """Benchmark klaw collect with early error."""
        items = [KOk(i) if i != 5 else KErr("fail") for i in range(100)]
        benchmark(k_collect, items)


# =============================================================================
# Pattern matching benchmarks
# =============================================================================


class TestPatternMatching:
    """Benchmark pattern matching."""

    def test_klaw_match_ok(self, benchmark):
        """Benchmark klaw pattern matching on Ok."""
        ok = KOk(42)

        def match_it():
            match ok:
                case KOk(v):
                    return v
                case KErr(e):
                    return e

        benchmark(match_it)

    def test_returns_match_success(self, benchmark):
        """Benchmark returns pattern matching on Success."""
        ok = Success(42)

        def match_it():
            match ok:
                case Success(v):
                    return v
                case Failure(e):
                    return e

        benchmark(match_it)

    def test_klaw_is_ok_branch(self, benchmark):
        """Benchmark klaw is_ok() branching."""
        ok = KOk(42)

        def branch():
            if ok.is_ok():
                return ok.unwrap()
            return None

        benchmark(branch)


# =============================================================================
# Memory benchmarks (using tracemalloc would be better, but this gives idea)
# =============================================================================


class TestMemory:
    """Rough memory comparison via object creation."""

    def test_klaw_create_1000(self, benchmark):
        """Create 1000 klaw Ok objects."""

        def create():
            return [KOk(i) for i in range(1000)]

        benchmark(create)

    def test_returns_create_1000(self, benchmark):
        """Create 1000 returns Success objects."""

        def create():
            return [Success(i) for i in range(1000)]

        benchmark(create)
