# Tasks: klaw-core-migration

## Relevant Files

### Source Files (to delete in klaw-core)
- `workspaces/python/klaw-core/src/klaw_core/__init__.py` - Placeholder init (delete and replace)
- `workspaces/python/klaw-core/src/klaw_core/_core.py` - Placeholder module (delete)
- `workspaces/python/klaw-core/src/klaw_core/_another_module.py` - Placeholder module (delete)
- `workspaces/python/klaw-core/src/klaw_core/result.py` - Dataclass-based Result (delete)
- `workspaces/python/klaw-core/src/klaw_core/result_other.py` - Alternative Result impl (delete)

### Source Files (to migrate from klaw-result)
- `workspaces/python/klaw-result/src/klaw_result/` - All source code to migrate
- `workspaces/python/klaw-result/tests/` - All tests to migrate
- `workspaces/python/klaw-result/pyproject.toml` - Config to adapt for klaw-core
- `workspaces/python/klaw-result/README.md` - Documentation to migrate

### Configuration Files (to update)
- `workspaces/python/klaw-core/pyproject.toml` - Overwrite with klaw-result config
- `mkdocs.yml` - Update paths and watch directories
- `docs/scripts/gen_ref_pages.py` - Update workspace references

### New Files (to create)
- `workspaces/python/klaw-core/src/klaw_core/runtime/__init__.py` - Stub for future runtime
- `workspaces/python/klaw-core/src/klaw_core/flight/__init__.py` - Stub for future Arrow Flight

### Test Files
- `workspaces/python/klaw-core/tests/test_result.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_option.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_decorators.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_async.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_fn.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_typeclass.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_compose.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_assertions.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_smoke.py` - Migrated from klaw-result
- `workspaces/python/klaw-core/tests/test_imports.py` - NEW: Verify flat and submodule imports

### Notes

- Use `uv run pytest workspaces/python/klaw-core/tests/` to run tests after migration
- Use `uv run mypy workspaces/python/klaw-core/src/` for type checking
- Use `mkdocs build` to verify documentation builds correctly
- All imports must change from `klaw_result` to `klaw_core`

## Tasks

- [x] 1.0 Delete existing klaw-core placeholder contents
  - [x] 1.1 Delete `workspaces/python/klaw-core/src/klaw_core/_core.py`
  - [x] 1.2 Delete `workspaces/python/klaw-core/src/klaw_core/_another_module.py`
  - [x] 1.3 Delete `workspaces/python/klaw-core/src/klaw_core/result.py`
  - [x] 1.4 Delete `workspaces/python/klaw-core/src/klaw_core/result_other.py`
  - [x] 1.5 Delete `workspaces/python/klaw-core/src/klaw_core/__init__.py` (will be replaced)

- [x] 2.0 Migrate klaw-result source code to klaw-core with new module structure
  - [x] 2.1 Copy `klaw-result/src/klaw_result/types/result.py` → `klaw-core/src/klaw_core/result.py` (flatten)
  - [x] 2.2 Copy `klaw-result/src/klaw_result/types/option.py` → `klaw-core/src/klaw_core/option.py` (flatten)
  - [x] 2.3 Copy `klaw-result/src/klaw_result/types/propagate.py` → `klaw-core/src/klaw_core/propagate.py` (flatten)
  - [x] 2.4 Copy `klaw-result/src/klaw_result/decorators/` → `klaw-core/src/klaw_core/decorators/`
  - [x] 2.5 Copy `klaw-result/src/klaw_result/async_/` → `klaw-core/src/klaw_core/async_/`
  - [x] 2.6 Copy `klaw-result/src/klaw_result/fn/` → `klaw-core/src/klaw_core/fn/`
  - [x] 2.7 Copy `klaw-result/src/klaw_result/typeclass/` → `klaw-core/src/klaw_core/typeclass/`
  - [x] 2.8 Copy `klaw-result/src/klaw_result/compose/` → `klaw-core/src/klaw_core/compose/`
  - [x] 2.9 Copy `klaw-result/src/klaw_result/assertions/` → `klaw-core/src/klaw_core/assertions/`
  - [x] 2.10 Copy `klaw-result/src/klaw_result/_internal/` → `klaw-core/src/klaw_core/_internal/`
  - [x] 2.11 Copy `klaw-result/src/klaw_result/py.typed` → `klaw-core/src/klaw_core/py.typed`
  - [x] 2.12 Update all internal imports from `klaw_result` to `klaw_core` in migrated files
  - [x] 2.13 Create new `klaw-core/src/klaw_core/__init__.py` with flat re-exports
  - [x] 2.14 Ensure all submodule `__init__.py` files have proper `__all__` exports
  - [x] 2.15 Update `klaw-core/src/klaw_core/types/__init__.py` to re-export from flattened modules (if keeping types/ structure) OR delete types/ directory if fully flattened

- [x] 3.0 Overwrite pyproject.toml with klaw-result's config
  - [x] 3.1 Copy klaw-result's pyproject.toml to klaw-core
  - [x] 3.2 Update `name` from `klaw-result` to `klaw-core`
  - [x] 3.3 Update `description` to reflect klaw-core's role as foundational package
  - [x] 3.4 Update `[tool.hatch.build.targets.wheel]` packages to `["src/klaw_core"]`
  - [x] 3.5 Update `[tool.mutmut]` paths to use `klaw_core`
  - [x] 3.6 Add `pyarrow` to core dependencies (per PRD FR-011)
  - [x] 3.7 Add `klaw-core-ext` as core dependency (per PRD FR-014)
  - [x] 3.8 Add placeholder `[project.optional-dependencies]` structure for future extras (`dbase`, `polars`, `all`)
  - [x] 3.9 Copy README.md from klaw-result and update for klaw-core naming

- [x] 4.0 Migrate tests and update imports
  - [x] 4.1 Copy all test files from `klaw-result/tests/` to `klaw-core/tests/`
  - [x] 4.2 Copy `conftest.py` and `strategies.py` from klaw-result tests
  - [x] 4.3 Update all imports in test files from `klaw_result` to `klaw_core`
  - [x] 4.4 Create `test_imports.py` to verify flat imports work: `from klaw_core import Ok, Err, Result, safe`
  - [x] 4.5 Add tests to `test_imports.py` to verify submodule imports work: `from klaw_core.decorators import safe`
  - [x] 4.6 Run tests to verify migration: `uv run pytest workspaces/python/klaw-core/tests/ -v` (585 passed)

- [ ] 5.0 Update documentation configuration
  - [ ] 5.1 Update `mkdocs.yml` paths to remove `klaw-result` reference (line 193)
  - [ ] 5.2 Update `mkdocs.yml` watch directories to remove klaw-result (currently not in watch, but verify)
  - [ ] 5.3 Update `docs/scripts/gen_ref_pages.py` line 15: change `klaw-result` to `klaw-core`
  - [ ] 5.4 Add `filters: ["!^_"]` to mkdocstrings options if not already present (to hide `_internal`, etc.)
  - [ ] 5.5 Verify mkdocs build works: `mkdocs build`
  - [ ] 5.6 Verify API docs show `klaw_core` and NOT `_internal` or other private modules

- [ ] 6.0 Add stub modules for future runtime and flight
  - [ ] 6.1 Create `klaw-core/src/klaw_core/runtime/__init__.py` with placeholder docstring
  - [ ] 6.2 Create `klaw-core/src/klaw_core/flight/__init__.py` with placeholder docstring
  - [ ] 6.3 Ensure stub modules have `__all__: list[str] = []`
  - [ ] 6.4 Add docstrings referencing future PRDs (e.g., "See PRD: 0003-prd-klaw-runtime.md")

- [ ] 7.0 Verify migration
  - [ ] 7.1 Run all tests: `uv run pytest workspaces/python/klaw-core/tests/ -v`
  - [ ] 7.2 Run type checking: `uv run mypy workspaces/python/klaw-core/src/klaw_core/`
  - [ ] 7.3 Run linting: `uv run ruff check workspaces/python/klaw-core/src/`
  - [ ] 7.4 Build docs: `mkdocs build`
  - [ ] 7.5 Verify flat imports work in Python REPL: `from klaw_core import Ok, Err, Result`
  - [ ] 7.6 Verify submodule imports work: `from klaw_core.decorators import safe`
  - [ ] 7.7 Update `uv.lock` if needed: `uv lock`

- [ ] 8.0 Delete klaw-result workspace
  - [ ] 8.1 Remove `workspaces/python/klaw-result/` directory entirely
  - [ ] 8.2 Update any workspace configuration files that reference klaw-result (if any)
  - [ ] 8.3 Run `uv lock` to update lockfile without klaw-result
  - [ ] 8.4 Final verification: all tests still pass, docs still build
