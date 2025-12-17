"""Async utilities: AsyncResult and async-aware functions.

This module provides async-aware Result operations:
- AsyncResult: Wrapper for composing async Result operations
- async_collect: Collect awaitables of Results into Result of list
- async_lru_safe: Cached async functions with exception handling

Examples:
    >>> from klaw_result.async_ import AsyncResult, async_collect
    >>>
    >>> async def fetch(id: int) -> Result[dict, str]:
    ...     return Ok({"id": id})
    >>>
    >>> async def main():
    ...     # Use AsyncResult for chaining
    ...     result = await AsyncResult(fetch(1)).amap(lambda d: d["id"])
    ...
    ...     # Collect multiple async results
    ...     results = await async_collect([fetch(1), fetch(2), fetch(3)])
"""

from klaw_result.async_.cache import async_lru_safe
from klaw_result.async_.itertools import (
    async_collect,
    async_collect_concurrent,
    async_filter_ok,
    async_first_ok,
    async_iter_ok,
    async_map,
    async_partition,
    async_race_ok,
)
from klaw_result.async_.result import AsyncResult

__all__ = [
    "AsyncResult",
    "async_collect",
    "async_collect_concurrent",
    "async_filter_ok",
    "async_first_ok",
    "async_iter_ok",
    "async_lru_safe",
    "async_map",
    "async_partition",
    "async_race_ok",
]
