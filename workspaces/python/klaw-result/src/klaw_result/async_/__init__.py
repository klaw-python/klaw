"""Async utilities: AsyncResult and async-aware functions."""

from klaw_result.async_.cache import async_lru_safe
from klaw_result.async_.itertools import async_collect
from klaw_result.async_.result import AsyncResult

__all__ = [
    "AsyncResult",
    "async_collect",
    "async_lru_safe",
]
