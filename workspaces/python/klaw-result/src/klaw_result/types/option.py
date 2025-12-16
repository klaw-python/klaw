"""Option type: Some[T] | Nothing for optional values."""

# Placeholder - implementation in Task 2.0

__all__ = ["Nothing", "Option", "Some"]


class Some[T]:
    """Placeholder for Some type."""


class _Nothing:
    """Placeholder for Nothing singleton."""


Nothing = _Nothing()

type Option[T] = Some[T] | _Nothing
