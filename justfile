# Klaw Development Tasks
# Run with `just <recipe-name>`

# Documentation tasks
docs-install:
    uv sync --project docs-build

docs-serve:
    uv run --project docs-build mkdocs serve --dev-addr 127.0.0.1:8000 || \
    uv run --project docs-build mkdocs serve --dev-addr 127.0.0.1:8001 || \
    uv run --project docs-build mkdocs serve --dev-addr 127.0.0.1:8002 || \
    uv run --project docs-build mkdocs serve --dev-addr 127.0.0.1:8003

docs-build:
    uv run --project docs-build mkdocs build

docs-clean:
    rm -rf site/

docs-deploy:
    uv run --project docs-build mkdocs gh-deploy --clean --force

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
