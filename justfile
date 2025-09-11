# Klaw Development Tasks
# Run with `just <recipe-name>`

# Documentation tasks
docs-install:
    uv sync --group docs

docs-serve:
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:8000 || \
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:8001 || \
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:8002 || \
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:8003

docs-build:
    uv run --group docs mkdocs build

docs-clean:
    rm -rf site/

docs-deploy:
    uv run --group docs mkdocs gh-deploy --clean --force

# Development tasks
lint:
    uv run ruff check .

format:
    uv run ruff format .

type-check:
    uv run mypy .

test:
    uv run pytest

# Combined tasks
check: lint type-check test

# Workspace management
sync:
    uv sync

# Clean all caches
clean-all: docs-clean
    rm -rf .ruff_cache .mypy_cache .pytest_cache
    find . -name "__pycache__" -type d -exec rm -rf {} +
    find . -name "*.pyc" -delete

# Setup development environment
setup: sync docs-install
    @echo "Development environment setup complete!"
    @echo "Run 'just docs-serve' to start the documentation server"