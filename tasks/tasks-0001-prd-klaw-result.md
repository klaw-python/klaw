# Tasks: klaw-result

## Relevant Files

### Package Structure

- `workspaces/python/klaw-result/pyproject.toml` - Package configuration with dependencies (msgspec, wrapt, aioitertools, async-lru, aiologic)
- `workspaces/python/klaw-result/src/klaw_result/__init__.py` - Public API re-exports
- `workspaces/python/klaw-result/src/klaw_result/py.typed` - PEP 561 marker file
- `workspaces/python/klaw-result/README.md` - Package documentation

### Core Types

- `workspaces/python/klaw-result/src/klaw_result/types/result.py` - Result, Ok, Err implementation
- `workspaces/python/klaw-result/src/klaw_result/types/option.py` - Option, Some, Nothing implementation
- `workspaces/python/klaw-result/src/klaw_result/types/__init__.py` - Types submodule exports
- `workspaces/python/klaw-result/src/klaw_result/types/propagate.py` - Propagate exception for .bail()

### Decorators

- `workspaces/python/klaw-result/src/klaw_result/decorators/safe.py` - @safe and @safe_async decorators
- `workspaces/python/klaw-result/src/klaw_result/decorators/pipe.py` - @pipe and @pipe_async decorators
- `workspaces/python/klaw-result/src/klaw_result/decorators/result.py` - @result decorator for propagation
- `workspaces/python/klaw-result/src/klaw_result/decorators/do.py` - @do and @do_async do-notation decorators
- `workspaces/python/klaw-result/src/klaw_result/decorators/__init__.py` - Decorators submodule exports

### Composition

- `workspaces/python/klaw-result/src/klaw_result/compose/pipe.py` - pipe() function and | operator support
- `workspaces/python/klaw-result/src/klaw_result/compose/deref.py` - Deref-style forwarding mixin
- `workspaces/python/klaw-result/src/klaw_result/compose/__init__.py` - Compose submodule exports

### Typeclasses

- `workspaces/python/klaw-result/src/klaw_result/typeclass/core.py` - @typeclass decorator and dispatch
- `workspaces/python/klaw-result/src/klaw_result/typeclass/__init__.py` - Typeclass submodule exports

### Lambda Helpers

- `workspaces/python/klaw-result/src/klaw_result/fn/placeholder.py` - fn placeholder implementation
- `workspaces/python/klaw-result/src/klaw_result/fn/__init__.py` - Fn submodule exports

### Assertions

- `workspaces/python/klaw-result/src/klaw_result/assertions/safe.py` - safe_assert and assert_result
- `workspaces/python/klaw-result/src/klaw_result/assertions/__init__.py` - Assertions submodule exports

### Async

- `workspaces/python/klaw-result/src/klaw_result/async_/result.py` - AsyncResult type
- `workspaces/python/klaw-result/src/klaw_result/async_/itertools.py` - aioitertools integration
- `workspaces/python/klaw-result/src/klaw_result/async_/cache.py` - async-lru Result variant
- `workspaces/python/klaw-result/src/klaw_result/async_/__init__.py` - Async submodule exports

### Internal

- `workspaces/python/klaw-result/src/klaw_result/_internal/sync.py` - aiologic thread-safe operations

### Tests

- `workspaces/python/klaw-result/tests/test_result.py` - Result type tests
- `workspaces/python/klaw-result/tests/test_option.py` - Option type tests
- `workspaces/python/klaw-result/tests/test_decorators.py` - Decorator tests
- `workspaces/python/klaw-result/tests/test_compose.py` - Composition tests
- `workspaces/python/klaw-result/tests/test_typeclass.py` - Typeclass tests
- `workspaces/python/klaw-result/tests/test_fn.py` - Lambda helper tests
- `workspaces/python/klaw-result/tests/test_assertions.py` - Assertion utility tests
- `workspaces/python/klaw-result/tests/test_async.py` - Async variant tests
- `workspaces/python/klaw-result/tests/conftest.py` - Pytest fixtures
- `workspaces/python/klaw-result/tests/strategies.py` - Hypothesis strategies

### Benchmarks

- `workspaces/python/klaw-result/benchmarks/bench_result.py` - Result benchmarks vs returns library
- `workspaces/python/klaw-result/benchmarks/bench_option.py` - Option benchmarks
- `workspaces/python/klaw-result/benchmarks/conftest.py` - Benchmark fixtures

### Notes

- Unit tests are in `tests/` subdirectory
- Use `uv run pytest workspaces/python/klaw-result/tests/` to run tests
- Use `uv run mypy workspaces/python/klaw-result/` for type checking
- Use `uv run ruff check workspaces/python/klaw-result/` for linting
- Use `uv run pytest workspaces/python/klaw-result/benchmarks/ --benchmark-only` for benchmarks
- All types use `msgspec.Struct` with `frozen=True` for immutability
- Use Python 3.13 PEP 695 generic syntax (`class Result[T, E]:`)

## Tasks

- [x] 1.0 Project Setup & Package Structure

  - [x] 1.1 Create `workspaces/python/klaw-result/` directory structure with `src/klaw_result/` layout
  - [x] 1.2 Create `pyproject.toml` with dependencies: msgspec, wrapt, aioitertools, async-lru, aiologic
  - [x] 1.3 Create `.python-version` file with `3.13`
  - [x] 1.4 Create `py.typed` marker file for PEP 561 compliance
  - [x] 1.5 Create submodule directories: `types/`, `decorators/`, `compose/`, `typeclass/`, `fn/`, `assertions/`, `async_/`, `_internal/`
  - [x] 1.6 Create `__init__.py` files with flat re-exports for all submodules
  - [x] 1.7 Create `tests/` and `benchmarks/` directories with `conftest.py`
  - [x] 1.8 Add dev dependencies: pytest, pytest-asyncio, hypothesis, pytest-benchmark, mutmut, returns (for comparison)
  - [x] 1.9 Update root `pyproject.toml` workspace members to include `klaw-result`

- [x] 2.0 Core Types Implementation

  - [x] 2.1 Create `Propagate` exception class in `types/propagate.py` for `.bail()` mechanism
  - [x] 2.2 Implement `Ok[T]` as `msgspec.Struct` with `frozen=True`, `__match_args__`
  - [x] 2.3 Implement `Err[E]` as `msgspec.Struct` with `frozen=True`, `__match_args__`
  - [x] 2.4 Define `Result[T, E]` type alias as `Ok[T] | Err[E]` with PEP 696 default `E=Exception`
  - [x] 2.5 Implement querying methods: `is_ok() -> TypeIs[Ok[T]]`, `is_err() -> TypeIs[Err[E]]`
  - [x] 2.6 Implement extracting methods: `unwrap()`, `unwrap_or()`, `unwrap_or_else()`, `expect()`
  - [x] 2.7 Implement transforming methods: `map()`, `map_err()`, `and_then()`, `or_else()`
  - [x] 2.8 Implement converting methods: `ok() -> Option[T]`, `err() -> Option[E]`, `transpose()`
  - [x] 2.9 Implement combining methods: `and_()`, `or_()`, `zip()`, `flatten()`
  - [x] 2.10 Implement `collect(Iterable[Result[T, E]]) -> Result[list[T], E]` class method
  - [x] 2.11 Implement `.bail()` and `.unwrap_or_return()` methods that raise `Propagate`
  - [x] 2.12 Implement `Some[T]` as `msgspec.Struct` with `frozen=True`, `__match_args__`
  - [x] 2.13 Implement `Nothing` as singleton (frozen Struct or sentinel)
  - [x] 2.14 Define `Option[T]` type alias as `Some[T] | Nothing`
  - [x] 2.15 Implement Option querying: `is_some() -> TypeIs[Some[T]]`, `is_none() -> TypeIs[Nothing]`
  - [x] 2.16 Implement Option extracting, transforming methods (mirror Result API)
  - [x] 2.17 Implement Option converting: `ok_or()`, `ok_or_else()` returning Result
  - [x] 2.18 Implement Option `.bail()` and `.unwrap_or_return()` methods
  - [x] 2.19 Add `__repr__`, `__eq__`, `__hash__` via msgspec.Struct defaults
  - [x] 2.20 Export all types from `types/__init__.py`

- [x] 3.0 Decorators & Propagation

  - [x] 3.1 Implement `@safe` decorator using `wrapt.decorator` — catches exceptions, returns `Err(exception)`
  - [x] 3.2 Implement `@safe_async` decorator for async functions
  - [x] 3.3 Implement `@pipe` decorator — wraps return value in `Ok()`
  - [x] 3.4 Implement `@pipe_async` decorator for async functions
  - [x] 3.5 Implement `@result` decorator — catches `Propagate` exception, returns contained `Err`
  - [x] 3.6 Implement `@result` for async functions (same decorator, detect async)
  - [x] 3.7 Implement `@do` decorator — generator-based do-notation with `yield` for Result extraction
  - [x] 3.8 Implement `@do_async` decorator — async generator do-notation
  - [x] 3.9 Ensure all decorators preserve function signatures and type hints via `wrapt`
  - [x] 3.10 Add context manager support to Result/Option for `with result.ctx as value:` unwrapping
  - [x] 3.11 Export all decorators from `decorators/__init__.py`

- [x] 4.0 Composition & Operators

  - [x] 4.1 Implement `__or__` (`|`) operator on Result for chaining: `Ok(x) | f` calls `f(x)` and wraps
  - [x] 4.2 Implement `__or__` on Option for same behavior
  - [x] 4.3 Implement `pipe(value, *fns)` function — applies functions in sequence, auto-wrapping
  - [x] 4.4 Detect if piped function already returns Result/Option to avoid double-wrapping
  - [x] 4.5 Create `Deref` mixin/protocol for `__getattr__` forwarding to wrapped value
  - [x] 4.6 Implement auto-wrapping of forwarded method return values
  - [x] 4.7 Detect if forwarded method returns Result/Option to avoid double-wrapping
  - [x] 4.8 Make deref forwarding opt-in (separate `DerefResult`/`DerefOption` classes or `.deref` property)
  - [x] 4.9 Export composition utilities from `compose/__init__.py`

- [x] 5.0 Typeclasses

  - [x] 5.1 Design typeclass interface: `@typeclass` decorator that returns a dispatchable function
  - [x] 5.2 Implement `.instance(Type)` decorator for registering type-specific implementations
  - [x] 5.3 Implement type-safe dispatch based on first argument's type
  - [x] 5.4 Support generic types in dispatch (e.g., `list[int]` vs `list[str]`)
  - [x] 5.5 Ensure full type inference without mypy plugin (use overloads, TypeVar, Protocol)
  - [x] 5.6 Add runtime error for missing instance implementations
  - [x] 5.7 Export typeclass utilities from `typeclass/__init__.py`

- [ ] 6.0 Lambda Helpers (`fn`)

  - [x] 6.1 Create `FnPlaceholder` class with operator overloads (`__add__`, `__sub__`, `__mul__`, etc.)
  - [x] 6.2 Implement `__getitem__` for `fn['key']` dict/list access
  - [x] 6.3 Implement `__getattr__` for `fn.method()` method calls (returns callable placeholder)
  - [x] 6.4 Implement `__call__` to produce the actual lambda function
  - [x] 6.5 Create `fn` singleton instance of `FnPlaceholder`
  - [x] 6.6 Add type stubs/overloads for common operations to enable type inference
  - [x] 6.7 Test with mypy/pyright to verify type inference works without plugin
  - [x] 6.8 Export `fn` from `fn/__init__.py`

- [ ] 7.0 Assertion Utilities

  - [ ] 7.1 Implement `safe_assert(condition, message)` — raises `AssertionError` even in `-O` mode
  - [ ] 7.2 Implement `assert_result(condition, error) -> Result[None, E]` — returns `Ok(None)` or `Err(error)`
  - [ ] 7.3 Add overloads for `assert_result` with callable error factory
  - [ ] 7.4 Export assertion utilities from `assertions/__init__.py`

- [ ] 8.0 Async Variants

  - [ ] 8.1 Design `AsyncResult[T, E]` — wrapper that holds `Awaitable[Result[T, E]]`
  - [ ] 8.2 Implement async methods: `amap()`, `amap_err()`, `aand_then()`, `aor_else()`
  - [ ] 8.3 Implement `await` support via `__await__` to get underlying `Result`
  - [ ] 8.4 Ensure compatibility with asyncio, uvloop, and other asyncio-compatible loops
  - [ ] 8.5 Create `async_collect()` for `Iterable[Awaitable[Result[T, E]]]`
  - [ ] 8.6 Wrap/re-export relevant `aioitertools` functions with Result-aware versions
  - [ ] 8.7 Create `@async_lru_safe` decorator combining `async-lru` with `@safe_async`
  - [ ] 8.8 Integrate `aiologic` for thread-safe internal operations in `_internal/sync.py`
  - [ ] 8.9 Export async utilities from `async_/__init__.py`

- [ ] 9.0 Testing & Quality

  - [ ] 9.1 Create `conftest.py` with common fixtures (sample Ok/Err/Some/Nothing instances)
  - [ ] 9.2 Create `strategies.py` with Hypothesis strategies for Result and Option
  - [ ] 9.3 Write unit tests for all Result methods (test_result.py)
  - [ ] 9.4 Write unit tests for all Option methods (test_option.py)
  - [ ] 9.5 Write unit tests for all decorators (test_decorators.py)
  - [ ] 9.6 Write unit tests for pipe operator and composition (test_compose.py)
  - [ ] 9.7 Write unit tests for typeclasses (test_typeclass.py)
  - [ ] 9.8 Write unit tests for fn placeholder (test_fn.py)
  - [ ] 9.9 Write unit tests for assertion utilities (test_assertions.py)
  - [ ] 9.10 Write async tests with pytest-asyncio (test_async.py)
  - [ ] 9.11 Add property-based tests with Hypothesis for all core operations
  - [ ] 9.12 Set up mutation testing with mutmut
  - [ ] 9.13 Create benchmark suite comparing against `returns` library
  - [ ] 9.14 Benchmark Result/Option creation, method calls, chaining
  - [ ] 9.15 Verify 100% type coverage with mypy strict mode
  - [ ] 9.16 Verify pyright compatibility

- [ ] 10.0 Documentation

  - [ ] 10.1 Write comprehensive docstrings for all public APIs
  - [ ] 10.2 Create `README.md` with quick start guide and examples
  - [ ] 10.3 Add usage examples for each major feature (Result, Option, decorators, pipe, etc.)
  - [ ] 10.4 Document pattern matching usage with Python `match` statement
  - [ ] 10.5 Document async usage patterns
  - [ ] 10.6 Add migration guide from `returns` library
  - [ ] 10.7 Set up mkdocs integration for API reference (if needed)
