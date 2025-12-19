# klaw-random

A fast pseudo-random number generator with Python bindings, powered by [FRand](https://github.com/engusmaze/frand).

## Performance

FRand is 5-7x faster than standard random libraries:

| Library         |   u64    |   f64    |   u128   |
| :-------------- | :------: | :------: | :------: |
| rand::ThreadRng |   1.0x   |   1.0x   |   1.0x   |
| rand::SmallRng  |   3.7x   |   3.8x   |   2.2x   |
| fastrand::Rng   |   5.8x   |   2.3x   |   6.8x   |
| **frand::Rand** | **6.1x** | **5.6x** | **7.2x** |

## Installation

```bash
pip install klaw-random
```

## Usage

### Functional API

```python
from klaw_random import rand_u64, rand_f64, rand_range_u64

# Single random values
print(rand_u64())  # Random u64
print(rand_f64())  # Random f64 in [0.0, 1.0)
print(rand_range_u64(1, 100))  # Random int in [1, 100)
```

### Stateful API

```python
from klaw_random import Rand

rng = Rand()

# Generate individual values
print(rng.gen_u64())
print(rng.gen_f64())
print(rng.gen_range(1, 100))

# Generate multiple values
print(rng.gen_multiple_u64(10))
print(rng.gen_multiple_f64(10))
```

## API Reference

### Functions

- `rand_u32() -> int` - Random u32
- `rand_u64() -> int` - Random u64
- `rand_f32() -> float` - Random f32 in \[0.0, 1.0)
- `rand_f64() -> float` - Random f64 in \[0.0, 1.0)
- `rand_range_u64(start: int, end: int) -> int` - Random int in \[start, end)

### Rand Class

Stateful RNG instance with methods:

- `gen_u32() -> int`
- `gen_u64() -> int`
- `gen_f32() -> float`
- `gen_f64() -> float`
- `gen_range(start: int, end: int) -> int`
- `gen_multiple_u64(count: int) -> list[int]`
- `gen_multiple_f64(count: int) -> list[float]`

## Development

### Building

```bash
maturin develop
```

### Testing

```bash
pytest
```

### Benchmarking

```bash
pip install -e .[dev]
pytest --benchmark
```
