# klaw-result

Type-safe, performant Result and Option types for Python 3.13+, inspired by Rust.

## Installation

```bash
pip install klaw-result
```

## Quick Start

```python
from klaw_result import Result, Ok, Err, Option, Some, Nothing


# Explicit error handling with Result
def divide(a: int, b: int) -> Result[float, str]:
    if b == 0:
        return Err('division by zero')
    return Ok(a / b)


# Pattern matching
match divide(10, 2):
    case Ok(value):
        print(f'Result: {value}')
    case Err(error):
        print(f'Error: {error}')

# Chaining with map and and_then
result = Ok(10).map(lambda x: x * 2).and_then(lambda x: Ok(x + 1) if x < 100 else Err('too large'))


# Optional values with Option
def find_user(id: int) -> Option[str]:
    users = {1: 'Alice', 2: 'Bob'}
    return Some(users[id]) if id in users else Nothing


# Using .bail() for early returns (like Rust's ? operator)
from klaw_result import result as result_decorator


@result_decorator
def process() -> Result[int, str]:
    x = divide(10, 2).bail()  # Returns Err early if division fails
    return Ok(int(x * 2))
```

## Features

- **Result[T, E]**: Explicit error handling with `Ok` and `Err` variants
- **Option[T]**: Optional values with `Some` and `Nothing` variants
- **Type-safe**: Full mypy/pyright support with `TypeIs` for type narrowing
- **Performant**: Built on `msgspec.Struct` (5-60x faster than dataclasses)
- **Ergonomic**: Decorators (`@safe`, `@pipe`, `@result`), pipe operators, do-notation
- **Async-ready**: Full async support with `AsyncResult` and async decorators

## Requirements

- Python 3.13+

## License

MIT
