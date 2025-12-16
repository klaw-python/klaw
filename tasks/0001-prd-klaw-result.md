# PRD: klaw-result

## 1. Introduction/Overview

`klaw-result` is a type-safe, performant library for explicit error handling in Python, inspired by Rust's `Result` and `Option` types. It addresses the shortcomings of the existing `returns` library by leveraging Python 3.13's new typing features (PEP 695 generics, PEP 696 TypeVar defaults, TypeIs) and using `msgspec.Struct` for performance.

The library provides a Rust-like API for error handling without exceptions, enabling railway-oriented programming, functional composition, and explicit control flow. It includes sync and async variants, typeclasses, lambda helpers, and ergonomic decorators for seamless integration into Python codebases.

**Problem Statement:**

- The `returns` library is too complex with too many abstractions
- Poor typing that doesn't leverage modern Python 3.13 features
- Performance issues
- API doesn't feel Pythonic enough

## 2. Goals

1. **Rust-compatible API**: Provide `Result[T, E]` and `Option[T]` with familiar methods (`map`, `and_then`, `unwrap`, etc.)
1. **Type Safety**: Full type coverage with mypy/pyright, leveraging Python 3.13's `TypeIs` for proper type narrowing
1. **Performance**: Use `msgspec.Struct` for fast instantiation, comparison, and serialization (5-60x faster than dataclasses)
1. **Ergonomics**: Multiple ways to handle errors — decorators, context managers, do-notation, pipe operators
1. **Async Support**: Full async variants compatible with asyncio/uvloop
1. **Extensibility**: Typeclasses for ad-hoc polymorphism, lambda helpers for composition

## 3. User Stories

1. **As a Python developer**, I want to use `Result[T, E]` to handle errors explicitly so that I can avoid unexpected exceptions in my code.

1. **As a team lead**, I want to enforce explicit error handling patterns so that our codebase is more predictable and maintainable.

1. **As a library author**, I want type-safe Result types so that my API consumers know exactly what errors can occur.

1. **As a developer working with async code**, I want async-compatible Result types so that I can use the same patterns in sync and async contexts.

1. **As a functional programming enthusiast**, I want to chain operations with `map`, `and_then`, and pipe operators so that I can write declarative code.

## 4. Functional Requirements

### 4.1 Core Types

1. **FR-001**: The system must provide `Result[T, E]` as a tagged union of `Ok[T]` and `Err[E]`
1. **FR-002**: The system must provide `Option[T]` as a tagged union of `Some[T]` and `Nothing`
1. **FR-003**: All types must be implemented using `msgspec.Struct` for performance
1. **FR-004**: All types must support Python's `match` statement via `__match_args__`
1. **FR-005**: Types must be immutable (frozen)

### 4.2 Result Methods (Rust-compatible)

**Querying:**
6\. **FR-006**: `is_ok() -> TypeIs[Ok[T]]` — returns True if Ok, with type narrowing
7\. **FR-007**: `is_err() -> TypeIs[Err[E]]` — returns True if Err, with type narrowing

**Extracting:**
8\. **FR-008**: `unwrap() -> T` — returns value or raises on Err
9\. **FR-009**: `unwrap_or(default: T) -> T` — returns value or default
10\. **FR-010**: `unwrap_or_else(f: Callable[[], T]) -> T` — returns value or computes default
11\. **FR-011**: `expect(msg: str) -> T` — returns value or raises with custom message

**Transforming:**
12\. **FR-012**: `map(f: Callable[[T], U]) -> Result[U, E]` — transform Ok value
13\. **FR-013**: `map_err(f: Callable[[E], F]) -> Result[T, F]` — transform Err value
14\. **FR-014**: `and_then(f: Callable[[T], Result[U, E]]) -> Result[U, E]` — flatmap/bind
15\. **FR-015**: `or_else(f: Callable[[E], Result[T, F]]) -> Result[T, F]` — recover from error

**Converting:**
16\. **FR-016**: `ok() -> Option[T]` — convert to Option, discarding error
17\. **FR-017**: `err() -> Option[E]` — convert to Option of error
18\. **FR-018**: `transpose()` — convert `Result[Option[T], E]` to `Option[Result[T, E]]`

**Combining:**
19\. **FR-019**: `and_(other: Result[U, E]) -> Result[U, E]` — return other if Ok
20\. **FR-020**: `or_(other: Result[T, F]) -> Result[T, F]` — return self if Ok, else other
21\. **FR-021**: `zip(other: Result[U, E]) -> Result[tuple[T, U], E]` — combine two Results
22\. **FR-022**: `flatten() -> Result[T, E]` — unwrap nested Result
23\. **FR-023**: `collect(results: Iterable[Result[T, E]]) -> Result[list[T], E]` — collect Results, short-circuit on first Err

### 4.3 Option Methods (Rust-compatible)

24. **FR-024**: `is_some() -> TypeIs[Some[T]]` — with type narrowing
01. **FR-025**: `is_none() -> TypeIs[Nothing]` — with type narrowing
01. **FR-026**: All extracting methods (`unwrap`, `unwrap_or`, etc.)
01. **FR-027**: All transforming methods (`map`, `and_then`, etc.)
01. **FR-028**: `ok_or(err: E) -> Result[T, E]` — convert to Result
01. **FR-029**: `ok_or_else(f: Callable[[], E]) -> Result[T, E]` — convert with computed error

### 4.4 Propagation (? operator equivalents)

30. **FR-030**: `.bail()` method — raises `Propagate` exception if Err/Nothing (short form)
01. **FR-031**: `.unwrap_or_return()` method — alias for `.bail()` (explicit form)
01. **FR-032**: `@result` decorator — catches `Propagate` and returns Err
01. **FR-033**: Context manager support for unwrapping within a block

### 4.5 Decorators

34. **FR-034**: `@safe` — catches exceptions and returns `Err(exception)`
01. **FR-035**: `@pipe` — wraps return value in `Ok`
01. **FR-036**: `@result` — catches `Propagate` exceptions for `.bail()` support
01. **FR-037**: `@do` — enables generator-based do-notation with `yield`

### 4.6 Async Variants

38. **FR-038**: `AsyncResult[T, E]` — async-aware Result type
01. **FR-039**: Async methods: `map_async()`, `and_then_async()`, etc.
01. **FR-040**: `@safe_async` — async version of `@safe`
01. **FR-041**: `@pipe_async` — async version of `@pipe`
01. **FR-042**: `@do_async` — async do-notation with `async for`
01. **FR-043**: Must work with asyncio, uvloop, and other asyncio-compatible event loops

### 4.7 Pipe Operator and Composition

44. **FR-044**: `|` operator on Result for chaining: `Ok(x) | f | g`
01. **FR-045**: `pipe(value, *fns)` function for composition

### 4.8 Deref-style Forwarding

46. **FR-046**: Optional `__getattr__` forwarding to wrapped value
01. **FR-047**: Auto-wrapping of return values in Result/Option (detect if already Result)
01. **FR-048**: Hybrid approach — explicit opt-in for forwarding

### 4.9 Typeclasses

49. **FR-049**: `@typeclass` decorator for defining typeclasses
01. **FR-050**: `.instance(Type)` for registering implementations
01. **FR-051**: Type-safe dispatch with custom implementation (not singledispatch)

### 4.10 Lambda Helpers (`fn`)

52. **FR-052**: `fn` placeholder for typed shorthand lambdas
01. **FR-053**: Support for `fn + 1`, `fn['key']`, `fn.method()` patterns
01. **FR-054**: Full type inference with pure Python typing (no mypy plugin)

### 4.11 Assertion Utilities

55. **FR-055**: `safe_assert(condition, message)` — assert that works in optimized mode
01. **FR-056**: `assert_result(condition, error) -> Result[None, E]` — returns Err on failure

### 4.12 Async Utilities Integration

57. **FR-057**: Re-export/wrap `aioitertools` for async iteration over Results
01. **FR-058**: Provide `@async_lru` variant that returns Result (cache + safe)
01. **FR-059**: Use `aiologic` internally for thread-safe operations

## 5. Non-Goals (Out of Scope)

1. **NG-001**: IO container (like `returns` library) — focus on Result/Option only
1. **NG-002**: Future/FutureResult containers — use native async/await instead
1. **NG-003**: RequiresContext (dependency injection) — separate concern
1. **NG-004**: Support for Python < 3.13
1. **NG-005**: Trio/anyio support in v0.1 (asyncio only, but compatible with uvloop)
1. **NG-006**: mypy plugin (rely on native Python 3.13 typing features)

## 6. Design Considerations

### 6.1 Package Structure

```
klaw_result/
├── __init__.py          # Flat re-exports
├── types/
│   ├── result.py        # Result, Ok, Err
│   └── option.py        # Option, Some, Nothing
├── decorators/
│   ├── safe.py          # @safe, @safe_async
│   ├── pipe.py          # @pipe, @pipe_async
│   ├── result.py        # @result
│   └── do.py            # @do, @do_async
├── fn/
│   └── placeholder.py   # fn lambda helper
├── typeclass/
│   └── core.py          # @typeclass
├── assertions/
│   └── safe.py          # safe_assert, assert_result
├── async_/
│   ├── result.py        # AsyncResult
│   └── utils.py         # async utilities
└── _internal/
    └── sync.py          # aiologic integration
```

### 6.2 Import Style

```python
# Flat imports (preferred)
from klaw_result import Result, Ok, Err, Option, Some, Nothing
from klaw_result import safe, pipe, result, do, fn, typeclass

# Submodule imports (for organization)
from klaw_result.types import Result, Option
from klaw_result.decorators import safe, pipe
from klaw_result.fn import fn
```

### 6.3 Pattern Matching

```python
match fetch_user(id):
    case Ok(user):
        print(f'Found: {user.name}')
    case Err(NotFound()):
        print('User not found')
    case Err(e):
        print(f'Error: {e}')
```

## 7. Technical Considerations

### 7.1 Dependencies (Hard)

- `msgspec` — Struct implementation, serialization, tagged unions
- `wrapt` — Correct decorator implementation with introspection

### 7.2 Dependencies (Integration)

- `aioitertools` — Re-export for async iteration
- `async-lru` — Base for cached async Result functions
- `aiologic` — Thread-safe internal operations

### 7.3 Python Version

- **Minimum**: Python 3.13 only
- **Features used**: PEP 695 generics, PEP 696 TypeVar defaults, PEP 742 TypeIs

### 7.4 Type Narrowing Example

```python
result: Result[User, Error] = fetch_user(id)

if result.is_ok():
    # Type checker knows: result is Ok[User]
    print(result.unwrap().name)  # Safe, no runtime error possible
else:
    # Type checker knows: result is Err[Error]
    log_error(result.unwrap_err())
```

## 8. Success Metrics

1. **SM-001**: All core types and methods implemented and documented
1. **SM-002**: 100% type coverage — mypy/pyright clean with strict mode
1. **SM-003**: Benchmark shows improvement over `returns` library
1. **SM-004**: Mutation testing coverage (mutmut or similar)
1. **SM-005**: Comprehensive documentation with examples
1. **SM-006**: Property-based tests with Hypothesis for all core operations
1. **SM-007**: Integration tests with real-world usage patterns

## 9. Design Decisions (Resolved)

1. **DD-001**: `fn` lambda helper must achieve type safety with pure Python typing — no mypy plugin required.

1. **DD-002**: Deref-style forwarding must detect if the forwarded method already returns a Result/Option and avoid double-wrapping.

1. **DD-003**: Typeclasses will use a custom implementation (not `@singledispatch`) for better typing support.

1. **DD-004**: `Result.collect()` method will be provided to convert `list[Result[T, E]]` to `Result[list[T], E]`.

## 10. Open Questions

1. **OQ-001**: Package structure may need to be submodules-only due to mkdocs documentation generation limitations — needs investigation.

1. **OQ-002**: Naming for async variants — `amap` vs keeping same names with `async def`? (To be decided during implementation)
