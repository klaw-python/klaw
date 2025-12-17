"""aiologic integration for thread-safe operations.

Provides thread-safe primitives for Result types that work correctly
in both sync and async contexts using aiologic.

aiologic provides synchronization primitives that work across
asyncio, threading, and multiprocessing contexts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import aiologic

from klaw_result.types.result import Err, Ok, Result

__all__ = ["OnceCell", "Lazy", "ResultOnce"]

T = TypeVar("T")


class OnceCell[T]:
    """A cell that can be written to exactly once.

    Thread-safe and async-safe using aiologic.Lock. Once a value is set,
    it cannot be changed.

    The `get()` method is non-blocking and returns None if the value hasn't
    been set. Use `get_or_init()` or `get_or_init_async()` for blocking/awaiting
    initialization with concurrent access safety.

    Note:
        Storing None is allowed, but `get()` cannot distinguish "unset" from
        "set to None". Use `is_set()` to check if the cell has been initialized.

    Examples:
        >>> cell: OnceCell[int] = OnceCell()
        >>> cell.get()  # Non-blocking, returns None if unset
        None
        >>> cell.set(42)
        True
        >>> cell.get()
        42
        >>> cell.set(100)  # Returns False, value unchanged
        False
    """

    __slots__ = ("_lock", "_value", "_is_set")

    def __init__(self) -> None:
        self._lock = aiologic.Lock()
        self._value: T | None = None
        self._is_set = False

    def get(self) -> T | None:
        """Get the value if set, otherwise None."""
        return self._value if self._is_set else None

    def get_or_init(self, init: Callable[[], T]) -> T:
        """Get the value, or initialize it with the given function.

        Thread-safe: only one thread will call init().

        Args:
            init: Function to call to initialize the value.

        Returns:
            The stored or newly initialized value.
        """
        if self._is_set:
            return self._value  # type: ignore[return-value]

        with self._lock:
            if not self._is_set:
                self._value = init()
                self._is_set = True
            return self._value  # type: ignore[return-value]

    async def get_or_init_async(self, init: Callable[[], T]) -> T:
        """Async version of get_or_init.

        Args:
            init: Function to call to initialize the value.

        Returns:
            The stored or newly initialized value.
        """
        if self._is_set:
            return self._value  # type: ignore[return-value]

        async with self._lock:
            if not self._is_set:
                self._value = init()
                self._is_set = True
            return self._value  # type: ignore[return-value]

    def set(self, value: T) -> bool:
        """Set the value if not already set.

        Args:
            value: The value to store.

        Returns:
            True if the value was set, False if already set.
        """
        if self._is_set:
            return False

        with self._lock:
            if self._is_set:
                return False
            self._value = value
            self._is_set = True
            return True

    def is_set(self) -> bool:
        """Check if the value has been set."""
        return self._is_set


class Lazy[T]:
    """A lazily initialized value.

    The initialization function is called at most once, on first access.
    Thread-safe and async-safe.

    Examples:
        >>> def expensive():
        ...     print("Computing...")
        ...     return 42
        >>>
        >>> lazy = Lazy(expensive)
        >>> lazy.get()  # Prints "Computing..."
        42
        >>> lazy.get()  # No print, returns cached value
        42
    """

    __slots__ = ("_cell", "_init")

    def __init__(self, init: Callable[[], T]) -> None:
        """Create a Lazy value.

        Args:
            init: Function to call on first access.
        """
        self._cell: OnceCell[T] = OnceCell()
        self._init = init

    def get(self) -> T:
        """Get the value, initializing if necessary."""
        return self._cell.get_or_init(self._init)

    async def get_async(self) -> T:
        """Async version of get."""
        return await self._cell.get_or_init_async(self._init)

    def is_initialized(self) -> bool:
        """Check if the value has been initialized."""
        return self._cell.is_set()


class ResultOnce[T, E]:
    """A Result that is computed exactly once with retry on failure.

    Similar to Lazy but for fallible initialization that returns Result.
    If initialization fails (returns Err), subsequent calls will retry.
    Thread-safe and async-safe using aiologic.Lock.

    Note:
        The initializer must be a synchronous function. The `get_async()`
        method provides async-safe concurrent access but does NOT await
        the initializer - it only ensures thread-safe access to the cached
        result.

    Examples:
        >>> def fetch_config() -> Result[Config, Error]:
        ...     # Synchronous initialization
        ...     return Ok(Config(...))
        >>>
        >>> config_once: ResultOnce[Config, Error] = ResultOnce(fetch_config)
        >>> result = config_once.get()  # Sync access
        >>> result = await config_once.get_async()  # Async-safe access
    """

    __slots__ = ("_lock", "_result", "_init")

    def __init__(self, init: Callable[[], Result[T, E]]) -> None:
        """Create a ResultOnce.

        Args:
            init: Function that returns Result[T, E].
        """
        self._lock = aiologic.Lock()
        self._result: Result[T, E] | None = None
        self._init = init

    def get(self) -> Result[T, E]:
        """Get the result, computing if necessary.

        If the previous computation returned Err, retries.
        """
        if self._result is not None and isinstance(self._result, Ok):
            return self._result

        with self._lock:
            if self._result is None or isinstance(self._result, Err):
                self._result = self._init()
            return self._result

    async def get_async(self) -> Result[T, E]:
        """Async version of get."""
        if self._result is not None and isinstance(self._result, Ok):
            return self._result

        async with self._lock:
            if self._result is None or isinstance(self._result, Err):
                self._result = self._init()
            return self._result

    def is_ok(self) -> bool:
        """Check if successfully initialized."""
        return self._result is not None and isinstance(self._result, Ok)

    def reset(self) -> None:
        """Reset to allow re-initialization."""
        with self._lock:
            self._result = None
