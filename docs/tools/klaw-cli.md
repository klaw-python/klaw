# Klaw CLI

The Klaw Command Line Interface provides a set of commands for working with Klaw projects.

## Installation

```bash
uv add klaw-cli
```

## Usage

```bash
klaw --help
```

## Available Commands

- `klaw init` - Initialize a new Klaw project
- `klaw build` - Build the project
- `klaw test` - Run tests
- `klaw docs` - Generate documentation
- `klaw lint` - Run linters and formatters

## Configuration

The CLI can be configured via:

- Command line arguments
- Configuration files (`.klaw.toml`, `pyproject.toml`)
- Environment variables

## Examples

```bash
# Initialize a new project
klaw init my-project

# Build with verbose output
klaw build --verbose

# Run tests with coverage
klaw test --coverage
```
