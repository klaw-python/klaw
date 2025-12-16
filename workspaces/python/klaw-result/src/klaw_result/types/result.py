"""Result type: Ok[T] | Err[E] for explicit error handling."""

# Placeholder - implementation in Task 2.0

__all__ = ["Err", "Ok", "Result"]


class Ok[T]:
    """Placeholder for Ok type."""


class Err[E]:
    """Placeholder for Err type."""


type Result[T, E = Exception] = Ok[T] | Err[E]
