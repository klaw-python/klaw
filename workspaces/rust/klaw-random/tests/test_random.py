"""Tests for klaw_random module."""

import pytest
from klaw_random import (
    Rand,
    # Python random API compatible functions
    choice,
    choices,
    gauss,
    rand_f32,
    rand_f64,
    rand_range_u64,
    rand_u32,
    rand_u64,
    randint,
    random,
    sample,
    shuffle,
    uniform,
)


class TestFunctionalAPI:
    """Test the functional API."""

    def test_rand_u32(self):
        """Test rand_u32 generates valid u32."""
        val = rand_u32()
        assert isinstance(val, int)
        assert 0 <= val < 2**32

    def test_rand_u64(self):
        """Test rand_u64 generates valid u64."""
        val = rand_u64()
        assert isinstance(val, int)
        assert 0 <= val < 2**64

    def test_rand_f32(self):
        """Test rand_f32 generates valid f32."""
        val = rand_f32()
        assert isinstance(val, float)
        assert 0.0 <= val < 1.0

    def test_rand_f64(self):
        """Test rand_f64 generates valid f64."""
        val = rand_f64()
        assert isinstance(val, float)
        assert 0.0 <= val < 1.0

    def test_rand_range_u64(self):
        """Test rand_range_u64 generates values in range."""
        for _ in range(100):
            val = rand_range_u64(10, 20)
            assert isinstance(val, int)
            assert 10 <= val < 20

    def test_rand_range_u64_large_range(self):
        """Test rand_range_u64 with large range."""
        val = rand_range_u64(0, 1000000)
        assert 0 <= val < 1000000

    def test_rand_range_u64_single_value(self):
        """Test rand_range_u64 with range size 1."""
        val = rand_range_u64(5, 6)
        assert val == 5


class TestStatefulAPI:
    """Test the stateful Rand class API."""

    def test_rand_creation(self):
        """Test creating a Rand instance."""
        rng = Rand()
        assert rng is not None

    def test_gen_u32(self):
        """Test gen_u32 generates valid u32."""
        rng = Rand()
        val = rng.gen_u32()
        assert isinstance(val, int)
        assert 0 <= val < 2**32

    def test_gen_u64(self):
        """Test gen_u64 generates valid u64."""
        rng = Rand()
        val = rng.gen_u64()
        assert isinstance(val, int)
        assert 0 <= val < 2**64

    def test_gen_f32(self):
        """Test gen_f32 generates valid f32."""
        rng = Rand()
        val = rng.gen_f32()
        assert isinstance(val, float)
        assert 0.0 <= val < 1.0

    def test_gen_f64(self):
        """Test gen_f64 generates valid f64."""
        rng = Rand()
        val = rng.gen_f64()
        assert isinstance(val, float)
        assert 0.0 <= val < 1.0

    def test_gen_range(self):
        """Test gen_range generates values in range."""
        rng = Rand()
        for _ in range(100):
            val = rng.gen_range(10, 20)
            assert isinstance(val, int)
            assert 10 <= val < 20

    def test_gen_multiple_u64(self):
        """Test gen_multiple_u64 generates list of u64."""
        rng = Rand()
        vals = rng.gen_multiple_u64(10)
        assert len(vals) == 10
        assert all(isinstance(v, int) for v in vals)
        assert all(0 <= v < 2**64 for v in vals)

    def test_gen_multiple_f64(self):
        """Test gen_multiple_f64 generates list of f64."""
        rng = Rand()
        vals = rng.gen_multiple_f64(10)
        assert len(vals) == 10
        assert all(isinstance(v, float) for v in vals)
        assert all(0.0 <= v < 1.0 for v in vals)

    def test_multiple_instances_independent(self):
        """Test that multiple Rand instances are independent."""
        rng1 = Rand()
        rng2 = Rand()

        # Generate from both
        vals1 = rng1.gen_multiple_u64(5)
        vals2 = rng2.gen_multiple_u64(5)

        # Should be different sequences (with overwhelming probability)
        assert vals1 != vals2

    def test_stateful_sequence(self):
        """Test that stateful RNG maintains state across calls."""
        rng = Rand()

        # Generate sequence
        val1 = rng.gen_u64()
        val2 = rng.gen_u64()
        val3 = rng.gen_u64()

        # Each should be different
        assert val1 != val2
        assert val2 != val3
        assert val1 != val3


class TestPythonRandomAPIFunctional:
    """Test Python random API compatible module-level functions."""

    def test_random(self):
        """Test random() returns float in [0.0, 1.0)."""
        for _ in range(100):
            val = random()
            assert isinstance(val, float)
            assert 0.0 <= val < 1.0

    def test_randint(self):
        """Test randint(a, b) returns integer in [a, b]."""
        for _ in range(100):
            val = randint(1, 10)
            assert isinstance(val, int)
            assert 1 <= val <= 10

    def test_randint_same_value(self):
        """Test randint with a == b."""
        val = randint(5, 5)
        assert val == 5

    def test_randint_negative(self):
        """Test randint with negative values."""
        for _ in range(100):
            val = randint(-10, -1)
            assert -10 <= val <= -1

    def test_randint_invalid_range(self):
        """Test randint raises error for invalid range."""
        with pytest.raises(ValueError):
            randint(10, 5)

    def test_uniform(self):
        """Test uniform(a, b) returns float in [a, b]."""
        for _ in range(100):
            val = uniform(5.0, 10.0)
            assert isinstance(val, float)
            assert 5.0 <= val <= 10.0

    def test_uniform_reversed(self):
        """Test uniform with a > b (still works, just reversed range)."""
        val = uniform(10.0, 5.0)
        assert isinstance(val, float)

    def test_choice(self):
        """Test choice returns element from sequence."""
        seq = [1, 2, 3, 4, 5]
        for _ in range(100):
            val = choice(seq)
            assert val in seq

    def test_choice_tuple(self):
        """Test choice works with tuple."""
        seq = ('a', 'b', 'c')
        val = choice(seq)
        assert val in seq

    def test_choice_string(self):
        """Test choice works with string."""
        seq = 'abcdef'
        val = choice(seq)
        assert val in seq

    def test_choice_empty(self):
        """Test choice raises error for empty sequence."""
        with pytest.raises(IndexError):
            choice([])

    def test_shuffle(self):
        """Test shuffle modifies list in place."""
        original = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        lst = original.copy()
        shuffle(lst)
        # Should contain same elements
        assert sorted(lst) == sorted(original)
        # Should be different order (with overwhelming probability for 10 elements)
        assert lst != original

    def test_shuffle_empty(self):
        """Test shuffle with empty list."""
        lst = []
        shuffle(lst)
        assert lst == []

    def test_shuffle_single(self):
        """Test shuffle with single element."""
        lst = [1]
        shuffle(lst)
        assert lst == [1]

    def test_sample(self):
        """Test sample returns k unique elements."""
        population = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        for _ in range(10):
            result = sample(population, 5)
            assert len(result) == 5
            # All unique
            assert len(set(result)) == 5
            # All from population
            assert all(x in population for x in result)

    def test_sample_full(self):
        """Test sample with k == len(population)."""
        population = [1, 2, 3, 4, 5]
        result = sample(population, 5)
        assert sorted(result) == sorted(population)

    def test_sample_zero(self):
        """Test sample with k == 0."""
        result = sample([1, 2, 3], 0)
        assert result == []

    def test_sample_too_large(self):
        """Test sample raises error when k > len(population)."""
        with pytest.raises(ValueError):
            sample([1, 2, 3], 5)

    def test_choices(self):
        """Test choices returns k elements with replacement."""
        population = [1, 2, 3]
        result = choices(population, k=10)
        assert len(result) == 10
        assert all(x in population for x in result)

    def test_choices_default(self):
        """Test choices with default k=1."""
        population = [1, 2, 3]
        result = choices(population)
        assert len(result) == 1
        assert result[0] in population

    def test_choices_empty(self):
        """Test choices raises error for empty population."""
        with pytest.raises(ValueError):
            choices([])

    def test_gauss(self):
        """Test gauss returns values from Gaussian distribution."""
        # Generate many values and check statistical properties
        values = [gauss(0.0, 1.0) for _ in range(1000)]
        mean = sum(values) / len(values)
        # Mean should be close to 0 (within reasonable bounds)
        assert -0.5 < mean < 0.5

    def test_gauss_custom_params(self):
        """Test gauss with custom mu and sigma."""
        values = [gauss(100.0, 10.0) for _ in range(1000)]
        mean = sum(values) / len(values)
        # Mean should be close to 100
        assert 95.0 < mean < 105.0


class TestPythonRandomAPIStateful:
    """Test Python random API compatible methods on Rand class."""

    def test_seed(self):
        """Test seed produces reproducible sequences."""
        rng1 = Rand()
        rng1.seed(12345)
        vals1 = [rng1.random() for _ in range(5)]

        rng2 = Rand()
        rng2.seed(12345)
        vals2 = [rng2.random() for _ in range(5)]

        assert vals1 == vals2

    def test_seed_none(self):
        """Test seed with None reseeds randomly."""
        rng = Rand()
        rng.seed(None)
        val = rng.random()
        assert 0.0 <= val < 1.0

    def test_random(self):
        """Test random() returns float in [0.0, 1.0)."""
        rng = Rand()
        for _ in range(100):
            val = rng.random()
            assert isinstance(val, float)
            assert 0.0 <= val < 1.0

    def test_randint(self):
        """Test randint(a, b) returns integer in [a, b]."""
        rng = Rand()
        for _ in range(100):
            val = rng.randint(1, 10)
            assert isinstance(val, int)
            assert 1 <= val <= 10

    def test_uniform(self):
        """Test uniform(a, b) returns float in [a, b]."""
        rng = Rand()
        for _ in range(100):
            val = rng.uniform(5.0, 10.0)
            assert isinstance(val, float)
            assert 5.0 <= val <= 10.0

    def test_choice(self):
        """Test choice returns element from sequence."""
        rng = Rand()
        seq = [1, 2, 3, 4, 5]
        for _ in range(100):
            val = rng.choice(seq)
            assert val in seq

    def test_shuffle(self):
        """Test shuffle modifies list in place."""
        rng = Rand()
        original = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        lst = original.copy()
        rng.shuffle(lst)
        assert sorted(lst) == sorted(original)

    def test_sample(self):
        """Test sample returns k unique elements."""
        rng = Rand()
        population = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = rng.sample(population, 5)
        assert len(result) == 5
        assert len(set(result)) == 5

    def test_choices(self):
        """Test choices returns k elements with replacement."""
        rng = Rand()
        population = [1, 2, 3]
        result = rng.choices(population, k=10)
        assert len(result) == 10

    def test_gauss(self):
        """Test gauss returns values from Gaussian distribution."""
        rng = Rand()
        values = [rng.gauss(0.0, 1.0) for _ in range(1000)]
        mean = sum(values) / len(values)
        assert -0.5 < mean < 0.5
