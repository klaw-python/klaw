"""AsyncResult type for async-aware Result operations.

AsyncResult wraps an Awaitable[Result[T, E]] and provides async-aware
transformation methods that compose cleanly in async contexts.

Example:
    ```python
    async def fetch_user(id: int) -> Result[User, Error]:
        ...

    # Chain async operations
    result = await (
        AsyncResult(fetch_user(1))
        .aand_then(validate_user)
        .amap(format_response)
    )
    ```
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine, Generator
from typing import TYPE_CHECKING, Any

import anyio

from klaw_core.result import Err, Ok, Result

if TYPE_CHECKING:
    from klaw_core.option import Option

__all__ = ['AsyncResult']


class AsyncResult[T, E]:
    """Async-aware Result wrapper for composing async Result operations.

    AsyncResult holds an Awaitable[Result[T, E]] and provides methods
    for transforming and chaining async operations that produce Results.

    Unlike regular Result, AsyncResult methods return new AsyncResult
    instances, allowing you to build up a chain of async operations
    that only execute when awaited.

    Note:
        AsyncResult is single-shot when wrapping a coroutine object.
        Coroutines can only be awaited once; awaiting the same AsyncResult
        multiple times will raise RuntimeError. Use from_ok/from_err/from_result
        for reusable values, or wrap a Task/Future for multi-await scenarios.

    Note:
        Some methods like `azip()` use asyncio.gather internally and are
        asyncio-specific. The core transformation methods (amap, aand_then, etc.)
        are backend-agnostic.

    Attributes:
        _awaitable: The underlying awaitable that produces a Result.

    Example:
        ```python
        async def get_data() -> Result[int, str]:
            return Ok(42)

        async def main():
            # Wrap and transform
            result = await AsyncResult(get_data()).amap(lambda x: x * 2)
            assert result == Ok(84)

        asyncio.run(main())
        ```
    """

    __slots__ = ('_awaitable',)

    def __init__(self, awaitable: Awaitable[Result[T, E]]) -> None:
        """Create an AsyncResult from an awaitable.

        Args:
            awaitable: An awaitable that produces a Result[T, E].
        """
        self._awaitable = awaitable

    def __await__(self) -> Generator[Any, Any, Result[T, E]]:
        """Support await syntax to get the underlying Result.

        Returns:
            The Result[T, E] produced by the awaitable.

        Example:
            ```python
            async def example():
                result = await AsyncResult.from_ok(42)
                assert result == Ok(42)
            ```
        """
        return self._awaitable.__await__()

    @classmethod
    def from_ok(cls, value: T) -> AsyncResult[T, E]:
        """Create an AsyncResult containing Ok(value).

        Args:
            value: The success value.

        Returns:
            AsyncResult wrapping a coroutine that returns Ok(value).
        """

        async def _ok() -> Result[T, E]:
            return Ok(value)

        return cls(_ok())

    @classmethod
    def from_err(cls, error: E) -> AsyncResult[T, E]:
        """Create an AsyncResult containing Err(error).

        Args:
            error: The error value.

        Returns:
            AsyncResult wrapping a coroutine that returns Err(error).
        """

        async def _err() -> Result[T, E]:
            return Err(error)

        return cls(_err())

    @classmethod
    def from_result(cls, result: Result[T, E]) -> AsyncResult[T, E]:
        """Create an AsyncResult from a synchronous Result.

        Args:
            result: A Result[T, E] value.

        Returns:
            AsyncResult wrapping a coroutine that returns the result.
        """

        async def _result() -> Result[T, E]:
            return result

        return cls(_result())

    def amap[U](self, f: Callable[[T], U]) -> AsyncResult[U, E]:
        """Apply a sync function to the Ok value.

        If the underlying Result is Ok, applies f to the value.
        If Err, returns the Err unchanged.

        Args:
            f: Sync function to apply to the Ok value.

        Returns:
            New AsyncResult with the transformed value.

        Example:
            ```python
            async def example():
                result = await AsyncResult.from_ok(5).amap(lambda x: x * 2)
                assert result == Ok(10)
            ```
        """

        async def _mapped() -> Result[U, E]:
            result = await self._awaitable
            if isinstance(result, Ok):
                return Ok(f(result.value))
            return result

        return AsyncResult(_mapped())

    def amap_async[U](
        self, f: Callable[[T], Awaitable[U]]
    ) -> AsyncResult[U, E]:
        """Apply an async function to the Ok value.

        If the underlying Result is Ok, awaits f(value).
        If Err, returns the Err unchanged.

        Args:
            f: Async function to apply to the Ok value.

        Returns:
            New AsyncResult with the transformed value.

        Example:
            ```python
            async def double(x: int) -> int:
                return x * 2

            async def example():
                result = await AsyncResult.from_ok(5).amap_async(double)
                assert result == Ok(10)
            ```
        """

        async def _mapped() -> Result[U, E]:
            result = await self._awaitable
            if isinstance(result, Ok):
                return Ok(await f(result.value))
            return result

        return AsyncResult(_mapped())

    def amap_err[F](self, f: Callable[[E], F]) -> AsyncResult[T, F]:
        """Apply a sync function to the Err value.

        If the underlying Result is Err, applies f to the error.
        If Ok, returns the Ok unchanged.

        Args:
            f: Sync function to apply to the Err value.

        Returns:
            New AsyncResult with the transformed error.
        """

        async def _mapped() -> Result[T, F]:
            result = await self._awaitable
            if isinstance(result, Err):
                return Err(f(result.error))
            return result  # type: ignore[return-value]

        return AsyncResult(_mapped())

    def amap_err_async[F](
        self, f: Callable[[E], Awaitable[F]]
    ) -> AsyncResult[T, F]:
        """Apply an async function to the Err value.

        Args:
            f: Async function to apply to the Err value.

        Returns:
            New AsyncResult with the transformed error.
        """

        async def _mapped() -> Result[T, F]:
            result = await self._awaitable
            if isinstance(result, Err):
                return Err(await f(result.error))
            return result  # type: ignore[return-value]

        return AsyncResult(_mapped())

    def aand_then[U](
        self, f: Callable[[T], Result[U, E]]
    ) -> AsyncResult[U, E]:
        """Chain with a sync function that returns a Result.

        If Ok, calls f(value) and returns its result.
        If Err, returns the Err unchanged.

        Args:
            f: Sync function that takes T and returns Result[U, E].

        Returns:
            New AsyncResult with the chained result.

        Example:
            ```python
            def validate(x: int) -> Result[int, str]:
                return Ok(x) if x > 0 else Err("not positive")

            async def example():
                result = await AsyncResult.from_ok(5).aand_then(validate)
                assert result == Ok(5)
            ```
        """

        async def _chained() -> Result[U, E]:
            result = await self._awaitable
            if isinstance(result, Ok):
                return f(result.value)
            return result  # type: ignore[return-value]

        return AsyncResult(_chained())

    def aand_then_async[U](
        self, f: Callable[[T], Awaitable[Result[U, E]]]
    ) -> AsyncResult[U, E]:
        """Chain with an async function that returns a Result.

        If Ok, awaits f(value) and returns its result.
        If Err, returns the Err unchanged.

        Args:
            f: Async function that takes T and returns Result[U, E].

        Returns:
            New AsyncResult with the chained result.

        Example:
            ```python
            async def fetch_details(id: int) -> Result[dict, str]:
                return Ok({"id": id, "name": "test"})

            async def example():
                result = await AsyncResult.from_ok(1).aand_then_async(fetch_details)
                assert result.is_ok()
            ```
        """

        async def _chained() -> Result[U, E]:
            result = await self._awaitable
            if isinstance(result, Ok):
                return await f(result.value)
            return result  # type: ignore[return-value]

        return AsyncResult(_chained())

    def aor_else[F](
        self, f: Callable[[E], Result[T, F]]
    ) -> AsyncResult[T, F]:
        """Recover from an Err with a sync function.

        If Err, calls f(error) and returns its result.
        If Ok, returns the Ok unchanged.

        Args:
            f: Sync function that takes E and returns Result[T, F].

        Returns:
            New AsyncResult with the recovery result.
        """

        async def _recovered() -> Result[T, F]:
            result = await self._awaitable
            if isinstance(result, Err):
                return f(result.error)
            return result  # type: ignore[return-value]

        return AsyncResult(_recovered())

    def aor_else_async[F](
        self, f: Callable[[E], Awaitable[Result[T, F]]]
    ) -> AsyncResult[T, F]:
        """Recover from an Err with an async function.

        If Err, awaits f(error) and returns its result.
        If Ok, returns the Ok unchanged.

        Args:
            f: Async function that takes E and returns Result[T, F].

        Returns:
            New AsyncResult with the recovery result.
        """

        async def _recovered() -> Result[T, F]:
            result = await self._awaitable
            if isinstance(result, Err):
                return await f(result.error)
            return result  # type: ignore[return-value]

        return AsyncResult(_recovered())

    def aunwrap_or(self, default: T) -> Coroutine[Any, Any, T]:
        """Unwrap with a default value.

        Returns:
            Coroutine that produces the Ok value or the default.
        """

        async def _unwrap() -> T:
            result = await self._awaitable
            if isinstance(result, Ok):
                return result.value
            return default

        return _unwrap()

    def aunwrap_or_else(self, f: Callable[[E], T]) -> Coroutine[Any, Any, T]:
        """Unwrap with a function to compute the default from the error.

        Returns:
            Coroutine that produces the Ok value or f(error).
        """

        async def _unwrap() -> T:
            result = await self._awaitable
            if isinstance(result, Ok):
                return result.value
            return f(result.error)

        return _unwrap()

    def aok(self) -> Coroutine[Any, Any, Option[T]]:
        """Convert to Option, returning Some(value) for Ok.

        Returns:
            Coroutine that produces Some(value) or Nothing.
        """
        from klaw_core.option import Nothing, Some

        async def _ok() -> Option[T]:
            result = await self._awaitable
            if isinstance(result, Ok):
                return Some(result.value)
            return Nothing

        return _ok()

    def aerr(self) -> Coroutine[Any, Any, Option[E]]:
        """Convert to Option, returning Some(error) for Err.

        Returns:
            Coroutine that produces Some(error) or Nothing.
        """
        from klaw_core.option import Nothing, Some

        async def _err() -> Option[E]:
            result = await self._awaitable
            if isinstance(result, Err):
                return Some(result.error)
            return Nothing

        return _err()

    def azip[U](self, other: AsyncResult[U, E]) -> AsyncResult[tuple[T, U], E]:
        """Combine two AsyncResults into a tuple.

        Runs both awaitables concurrently. If both are Ok, returns
        Ok((self.value, other.value)). If either is Err, returns the
        first Err (by position: self first, then other).

        Args:
            other: Another AsyncResult to combine with.

        Returns:
            AsyncResult containing the tuple or first error.
        """

        async def _zipped() -> Result[tuple[T, U], E]:
            result1: Result[T, E] | None = None
            result2: Result[U, E] | None = None

            async with anyio.create_task_group() as tg:

                async def run_self() -> None:
                    nonlocal result1
                    result1 = await self._awaitable

                async def run_other() -> None:
                    nonlocal result2
                    result2 = await other._awaitable

                tg.start_soon(run_self)
                tg.start_soon(run_other)

            assert result1 is not None
            assert result2 is not None

            if isinstance(result1, Err):
                return result1
            if isinstance(result2, Err):
                return result2
            return Ok((result1.value, result2.value))

        return AsyncResult(_zipped())

    def __repr__(self) -> str:
        return f'AsyncResult({self._awaitable!r})'
