# klaw-random Implementation

## Overview

`klaw-random` is a Rust-powered Python module providing blazingly fast pseudo-random number generation using the FRand algorithm. It follows the same patterns as `klaw-dbase`, using PyO3 and maturin for Rust-Python interoperability.

## Architecture

### Rust Layer (`src/`)

- **lib.rs**: Module entry point and PyO3 module definition
- **py.rs**: PyO3 bindings exposing:
  - `PyRand` class: Stateful RNG instance
  - Free functions: Single-value generation without state

### Python Layer (`klaw_random/`)

- **__init__.py**: Public API re-exports
- **\_random_rs.pyi**: Type stubs for IDE support
- **py.typed**: PEP 561 marker for type checking

## Key Design Decisions

1. **Dual API**:

   - Stateful `Rand` class for sequence generation
   - Free functions (`rand_u64`, `rand_f32`, etc.) for single values

1. **FRand Integration**:

   - Uses FRand 0.10 for 6-7x performance over standard RNG
   - Simple, non-cryptographic PRNG optimized for speed

1. **Type Safety**:

   - PEP 561 compliant with `.pyi` stub files
   - Full type hints for IDE support

1. **Testing**:

   - 17 unit tests covering both APIs
   - Range validation and independence testing
   - Fast CI/CD turnaround with maturin

## Performance

Compared to standard libraries:

- **ThreadRng**: 6.1x faster (u64), 5.6x faster (f64)
- **SmallRng**: 1.6x faster (u64), 1.5x faster (f64)
- **fastrand**: ~1x comparable speed

## Build & Test

```bash
# Build with maturin
uv run maturin develop

# Run tests
uv run pytest tests/ -v
```

## Future Enhancements

- [ ] Seeding support for reproducible sequences
- [ ] NumPy array support for vectorized generation
- [ ] Additional distributions (normal, exponential, etc.)
- [ ] WASM support via wasm-pack
