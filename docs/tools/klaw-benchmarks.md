# Klaw Benchmarks

Performance benchmarking tools for Klaw projects.

## Installation

```bash
uv add klaw-benchmarks
```

## Features

- Automated performance testing
- Memory usage profiling
- CPU usage analysis
- Comparative benchmarking
- Custom benchmark suites

## Usage

```bash
# Run all benchmarks
klaw-benchmarks run

# Run specific benchmark suite
klaw-benchmarks run --suite async_performance

# Compare with previous results
klaw-benchmarks compare --baseline main
```

## Creating Benchmarks

```python
from klaw_benchmarks import Benchmark, BenchmarkSuite

suite = BenchmarkSuite('my_suite')


@suite.benchmark
async def test_async_operation():
    # Your benchmark code here
    pass


if __name__ == '__main__':
    suite.run()
```

## Configuration

Configure benchmarks via `benchmarks.toml`:

```toml
[benchmarks]
iterations = 1000
warmup_iterations = 100
timeout = 30
```
