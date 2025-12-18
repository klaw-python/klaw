# PRD: klaw-core-migration

## 1. Introduction/Overview

This PRD describes the consolidation of `klaw-result` into `klaw-core`, establishing `klaw-core` as the foundational package for the Klaw ecosystem. Currently, `klaw-result` contains the production-ready msgspec-based Result/Option implementation, while `klaw-core` exists only as scaffolding for mkdocs documentation setup.

This migration will:
- Rename/move `klaw-result` to become `klaw-core`
- Establish the module structure for future runtime and flight modules
- Fix documentation generation to exclude private modules
- Update all dependent packages to import from `klaw-core`

**Problem Statement:**
- `klaw-result` is the real implementation but has a narrow name
- `klaw-core` is placeholder scaffolding
- Documentation currently exposes `_internal`, `_sync`, etc. in API docs
- No clear foundation package for building runtime/orchestrator layers

## 2. Goals

1. **Consolidation**: Merge `klaw-result` into `klaw-core` as the single foundational package
2. **Clean API**: Establish proper `__all__` exports and `_` prefixed private modules
3. **Documentation**: Fix mkdocs to only generate docs for public API
4. **Future-ready**: Define module structure that accommodates runtime and flight modules
5. **Ecosystem update**: Update all dependent packages to import from `klaw-core`

## 3. User Stories

1. **As a Klaw user**, I want to import Result types from `klaw-core` so that I have one clear foundational package.

2. **As a library consumer**, I want flat imports (`from klaw_core import Ok, Err`) so that my import statements are concise.

3. **As a documentation reader**, I want to see only public API in the docs so that I'm not confused by internal implementation details.

4. **As a Klaw maintainer**, I want a clear module structure so that I can add runtime and flight modules without restructuring.

5. **As a developer**, I want optional extras (`klaw-core[dbase]`) so that I can install only what I need.

## 4. Functional Requirements

### 4.1 Package Migration

1. **FR-001**: Move all source code from `klaw-result/src/klaw_result/` to `klaw-core/src/klaw_core/`
2. **FR-002**: Move all tests from `klaw-result/tests/` to `klaw-core/tests/`
3. **FR-003**: Merge `pyproject.toml` configurations, preserving all dependencies
4. **FR-004**: Delete `klaw-result` workspace after migration is complete
5. **FR-005**: Update `uv.lock` to reflect the new package structure

### 4.2 Module Structure

6. **FR-006**: Implement the following directory structure:

```
klaw_core/
├── __init__.py          # Flat re-exports for public API
├── py.typed             # PEP 561 marker
├── result.py            # Ok, Err, Result, collect
├── option.py            # Some, Nothing, NothingType, Option
├── propagate.py         # Propagate exception
├── decorators/          # @safe, @result, @do, @pipe
│   ├── __init__.py
│   ├── safe.py
│   ├── result.py
│   ├── do.py
│   └── pipe.py
├── async_/              # AsyncResult, async utilities
│   ├── __init__.py
│   ├── result.py
│   └── utils.py
├── fn/                  # Lambda helpers
│   ├── __init__.py
│   └── placeholder.py
├── typeclass/           # @typeclass
│   ├── __init__.py
│   └── core.py
├── compose/             # Deref, pipe composition
│   ├── __init__.py
│   └── deref.py
├── assertions/          # safe_assert, assert_result
│   ├── __init__.py
│   └── safe.py
├── _internal/           # Private utilities (NOT in docs)
│   ├── __init__.py
│   └── sync.py
├── runtime/             # STUB: Future async runtime primitives
│   └── __init__.py      # Empty, placeholder
└── flight/              # STUB: Future Arrow Flight integration
    └── __init__.py      # Empty, placeholder
```

7. **FR-007**: All private modules must be prefixed with `_` (e.g., `_internal/`)
8. **FR-008**: Each public submodule must have `__all__` defined in its `__init__.py`

### 4.3 Public API (Flat Re-exports)

9. **FR-009**: The root `__init__.py` must re-export all public symbols:

```python
from klaw_core import (
    # Types
    Ok, Err, Result,
    Some, Nothing, NothingType, Option,
    Propagate,
    collect,
    # Decorators
    safe, safe_async,
    result,
    do, do_async,
    pipe, pipe_async,
    # Async
    AsyncResult, async_collect, async_lru_safe,
    # Composition
    Deref, DerefOk, DerefSome,
    pipe as pipe_fn,
    # Typeclass
    typeclass,
    # Lambda helpers
    fn,
    # Assertions
    safe_assert, assert_result,
)
```

10. **FR-010**: Submodule imports must also work:

```python
from klaw_core.decorators import safe
from klaw_core.async_ import AsyncResult
from klaw_core.typeclass import typeclass
```

### 4.4 Dependencies

11. **FR-011**: Core dependencies (required):
    - `msgspec` — Struct implementation, serialization
    - `wrapt` — Decorator introspection
    - `pyarrow` — Arrow Flight (core, not optional)

12. **FR-012**: Integration dependencies (required):
    - `aioitertools` — Async iteration
    - `async-lru` — Cached async functions
    - `aiologic` — Thread-safe operations

13. **FR-013**: Optional extras structure (for future use):
    - `[dbase]` — klaw-dbase (not implemented in this PRD)
    - `[polars]` — klaw-polars (not implemented in this PRD)
    - `[all]` — All optional extras

14. **FR-014**: Rust extension `klaw-core-ext` remains a separate package; `klaw-core` depends on it as a core dependency

### 4.5 Documentation

15. **FR-015**: Update `mkdocs.yml` to reference `klaw_core` instead of `klaw_result`

16. **FR-016**: Configure mkdocstrings to filter private modules:

```yaml
plugins:
  - mkdocstrings:
      handlers:
        python:
          options:
            show_if_no_docstring: false
            members_order: source
            filters:
              - "!^_"  # Hide anything starting with _
```

17. **FR-017**: Documentation must build successfully with `mkdocs build`
18. **FR-018**: API docs must NOT include `_internal`, `_sync`, or any `_`-prefixed modules

### 4.6 Dependent Package Updates

19. **FR-019**: Update `klaw-polars` to import from `klaw_core`
20. **FR-020**: Update `klaw-types` to import from `klaw_core` (if applicable)
21. **FR-021**: Update `klaw-testing` to import from `klaw_core` (if applicable)
22. **FR-022**: Update `klaw-plugins` to import from `klaw_core` (if applicable)
23. **FR-023**: Update any examples in `klaw-examples` to use `klaw_core`

### 4.7 Testing

24. **FR-024**: All existing `klaw-result` tests must pass after migration
25. **FR-025**: Import tests must verify both flat and submodule import styles work
26. **FR-026**: Type checking must pass with mypy/pyright in strict mode

## 5. Non-Goals (Out of Scope)

1. **NG-001**: Implementing runtime primitives (channels, tasks, supervision) — separate PRD
2. **NG-002**: Implementing Arrow Flight integration — separate PRD
3. **NG-003**: Adding new functionality to Result/Option types
4. **NG-004**: Publishing to PyPI (internal only for now)
5. **NG-005**: Implementing `[dbase]`, `[polars]`, or other extras — future work
6. **NG-006**: Backwards compatibility shim in `klaw-result` (package will be deleted)

## 6. Design Considerations

### 6.1 Import Style

Users should prefer flat imports for common types:

```python
# Preferred
from klaw_core import Ok, Err, Result, safe

# Also works (for organization)
from klaw_core.decorators import safe, result
from klaw_core.async_ import AsyncResult
```

### 6.2 Private Module Convention

All internal/private modules use `_` prefix:
- `_internal/` — shared utilities
- `_sync.py` — aiologic wrappers

This ensures:
- Clear distinction between public and private API
- Autodoc tools skip `_`-prefixed modules by default
- IDE autocomplete doesn't suggest private modules

### 6.3 Stub Modules

The `runtime/` and `flight/` directories will contain only `__init__.py` with:

```python
"""klaw-core runtime primitives.

This module is a placeholder for future implementation.
See PRD: 0003-prd-klaw-runtime.md
"""

__all__: list[str] = []
```

## 7. Technical Considerations

### 7.1 Python Version

- **Minimum**: Python 3.13 only
- **Features used**: PEP 695 generics, PEP 696 TypeVar defaults, PEP 742 TypeIs

### 7.2 Build System

- **Tool**: uv (workspace management)
- **Config**: pyproject.toml with uv workspace configuration

### 7.3 Type Checking

- Must pass mypy in strict mode
- Must pass pyright in strict mode
- `py.typed` marker required for PEP 561 compliance

### 7.4 Rust Extension

`klaw-core-ext` provides optional performance primitives via PyO3. It remains a separate workspace package but is listed as a dependency of `klaw-core`.

## 8. Success Metrics

1. **SM-001**: All 12 test files from `klaw-result` pass in `klaw-core`
2. **SM-002**: `mkdocs build` succeeds without warnings
3. **SM-003**: API documentation shows only public modules (no `_internal`, etc.)
4. **SM-004**: `from klaw_core import Ok, Err, Result, safe` works
5. **SM-005**: `from klaw_core.decorators import safe` works
6. **SM-006**: mypy/pyright pass in strict mode
7. **SM-007**: All dependent packages (`klaw-polars`, etc.) import successfully
8. **SM-008**: `klaw-result` workspace directory is deleted

## 9. Design Decisions (Resolved)

1. **DD-001**: Delete `klaw-result` completely after migration (not published, no shim needed)

2. **DD-002**: Delete all existing `klaw-core` contents (`result.py`, `result_other.py`, `_core.py`, `_another_module.py`) — they are placeholder/dataclass duplicates

3. **DD-003**: Include empty `runtime/` and `flight/` stubs with docstrings pointing to future PRDs
