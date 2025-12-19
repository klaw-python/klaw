"""Fast pseudo-random number generator with Python bindings.

This module provides a blazingly fast PRNG powered by FRand, a Rust-based
pseudo-random number generator that is 5-7x faster than standard libraries.

Classes:
    Rand: Stateful RNG instance for generating sequences of random numbers.

Functions:
    rand_u32(): Generate a random u32.
    rand_u64(): Generate a random u64.
    rand_f32(): Generate a random f32 in [0.0, 1.0).
    rand_f64(): Generate a random f64 in [0.0, 1.0).
    rand_range_u64(start, end): Generate a random integer in [start, end).

    # Python random API compatible functions:
    random(): Return a random float in [0.0, 1.0).
    randint(a, b): Return a random integer N such that a <= N <= b.
    uniform(a, b): Return a random float N such that a <= N <= b.
    choice(seq): Return a random element from the non-empty sequence.
    shuffle(x): Shuffle list x in place.
    sample(population, k): Return a k-length list of unique elements.
    choices(population, k): Return a k-length list with replacement.
    gauss(mu, sigma): Return a random float from a Gaussian distribution.
"""

from ._random_rs import (
    PyRand as Rand,
)
from ._random_rs import (
    # Python random API compatible functions
    choice,
    choices,
    gauss,
    # Original API
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

__all__ = [
    'Rand',
    'choice',
    'choices',
    'gauss',
    'rand_f32',
    'rand_f64',
    'rand_range_u64',
    'rand_u32',
    'rand_u64',
    'randint',
    'random',
    'sample',
    'shuffle',
    'uniform',
]
