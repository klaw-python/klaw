"""Benchmarks for Option type.

Run with: uv run pytest benchmarks/ --benchmark-only -v
"""

from klaw_result import Nothing, Some


# =============================================================================
# Creation benchmarks
# =============================================================================


class TestOptionCreation:
    """Benchmark Option creation."""

    def test_some_creation(self, benchmark):
        """Benchmark Some creation."""
        benchmark(Some, 42)

    def test_nothing_access(self, benchmark):
        """Benchmark Nothing singleton access."""

        def get_nothing():
            return Nothing

        benchmark(get_nothing)


# =============================================================================
# Method call benchmarks
# =============================================================================


class TestOptionMethods:
    """Benchmark Option method calls."""

    def test_some_map(self, benchmark):
        """Benchmark Some.map."""
        some = Some(5)
        benchmark(some.map, lambda x: x * 2)

    def test_nothing_map(self, benchmark):
        """Benchmark Nothing.map."""
        benchmark(Nothing.map, lambda x: x * 2)

    def test_some_and_then(self, benchmark):
        """Benchmark Some.and_then."""
        some = Some(5)
        benchmark(some.and_then, lambda x: Some(x * 2))

    def test_some_unwrap_or(self, benchmark):
        """Benchmark Some.unwrap_or."""
        some = Some(5)
        benchmark(some.unwrap_or, 0)

    def test_nothing_unwrap_or(self, benchmark):
        """Benchmark Nothing.unwrap_or."""
        benchmark(Nothing.unwrap_or, 0)

    def test_some_is_some(self, benchmark):
        """Benchmark Some.is_some."""
        some = Some(5)
        benchmark(some.is_some)

    def test_nothing_is_none(self, benchmark):
        """Benchmark Nothing.is_none."""
        benchmark(Nothing.is_none)


# =============================================================================
# Chaining benchmarks
# =============================================================================


class TestOptionChaining:
    """Benchmark chained Option operations."""

    def test_some_chain_3(self, benchmark):
        """Benchmark 3-step chain on Some."""

        def chain():
            return (
                Some(5)
                .map(lambda x: x + 1)
                .map(lambda x: x * 2)
                .and_then(lambda x: Some(x - 1))
            )

        benchmark(chain)

    def test_nothing_chain_3(self, benchmark):
        """Benchmark 3-step chain on Nothing (should short-circuit)."""

        def chain():
            return (
                Nothing.map(lambda x: x + 1)
                .map(lambda x: x * 2)
                .and_then(lambda x: Some(x - 1))
            )

        benchmark(chain)

    def test_filter_chain(self, benchmark):
        """Benchmark chain with filter."""

        def chain():
            return Some(10).filter(lambda x: x > 5).map(lambda x: x * 2)

        benchmark(chain)


# =============================================================================
# Conversion benchmarks
# =============================================================================


class TestOptionConversion:
    """Benchmark Option conversions."""

    def test_some_ok_or(self, benchmark):
        """Benchmark Some.ok_or."""
        some = Some(42)
        benchmark(some.ok_or, "error")

    def test_nothing_ok_or(self, benchmark):
        """Benchmark Nothing.ok_or."""
        benchmark(Nothing.ok_or, "error")

    def test_some_zip(self, benchmark):
        """Benchmark Some.zip."""
        some1 = Some(1)
        some2 = Some(2)
        benchmark(some1.zip, some2)


# =============================================================================
# Pattern matching benchmarks
# =============================================================================


class TestOptionPatternMatching:
    """Benchmark pattern matching on Option."""

    def test_match_some(self, benchmark):
        """Benchmark pattern matching on Some."""
        some = Some(42)

        def match_it():
            match some:
                case Some(v):
                    return v
                case _:
                    return None

        benchmark(match_it)

    def test_match_nothing(self, benchmark):
        """Benchmark pattern matching on Nothing."""

        def match_it():
            match Nothing:
                case Some(v):
                    return v
                case _:
                    return None

        benchmark(match_it)


# =============================================================================
# Memory benchmarks
# =============================================================================


class TestOptionMemory:
    """Rough memory comparison."""

    def test_create_1000_some(self, benchmark):
        """Create 1000 Some objects."""

        def create():
            return [Some(i) for i in range(1000)]

        benchmark(create)
