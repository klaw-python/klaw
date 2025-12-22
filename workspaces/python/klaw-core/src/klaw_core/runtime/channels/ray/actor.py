"""Ray channel actor implementation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial
from typing import Any

import msgspec
import ray

from klaw_core.runtime.channels.ray.constants import BatchResult, ReaderInfo, SingleResult


class _TypeValidator[T]:
    """Validates values against a type using msgspec.convert with lazy caching.

    The converter function is created lazily on first validation call,
    avoiding overhead when validation is not needed (value_type=None).

    Type Parameters:
        T: The type to validate against.
    """

    __slots__ = ('_convert_fn', '_type')

    def __init__(self, value_type: type[T] | None) -> None:
        """Initialize the validator.

        Args:
            value_type: The type to validate against, or None to accept all values.
        """
        self._type = value_type
        self._convert_fn: Any | None = None

    def validate(self, item: Any) -> bool:
        """Validate an item against the expected type.

        Args:
            item: The value to validate.

        Returns:
            True if valid (or no type constraint), False if validation fails.
        """
        if self._type is None:
            return True

        if self._convert_fn is None:
            self._convert_fn = partial(msgspec.convert, type=self._type)

        try:
            self._convert_fn(item)
        except (msgspec.ValidationError, TypeError):
            return False
        return True


class _ChannelActorState(msgspec.Struct, gc=False):
    """Mutable internal state for RayChannelActor."""

    capacity: int | None
    unbounded: bool
    value_type: type | None = None
    sender_count: int = 0
    receiver_count: int = 0
    senders_closed: bool = False
    receivers_closed: bool = False
    created_at: datetime = msgspec.UNSET
    high_watermark: int = 0
    total_sent: int = 0
    total_received: int = 0

    def __post_init__(self) -> None:
        if self.created_at is msgspec.UNSET:
            self.created_at = datetime.now(UTC)


@ray.remote(max_restarts=4, max_task_retries=-1, max_concurrency=1000)
class RayChannelActor[T]:
    """Ray actor that holds the channel buffer.

    Actor methods return status codes instead of raising exceptions:
    - "ok": Operation succeeded
    - "full": Channel at capacity (for put operations)
    - "empty": No messages available (for get operations)
    - "closed": Channel has been closed
    - "type_error": Value failed runtime type validation
    """

    def __init__(
        self,
        capacity: int | None = None,
        unbounded: bool = False,
        value_type: type[T] | None = None,
    ) -> None:
        """Initialize the channel actor.

        Args:
            capacity: Maximum queue size. None means unbounded.
            unbounded: If True, queue has no capacity limit.
            value_type: Optional type for runtime validation (e.g., int, list[str]).
        """
        self._state = _ChannelActorState(
            capacity=capacity if not unbounded else None,
            unbounded=unbounded,
            value_type=value_type,
        )
        self._validator = _TypeValidator(value_type)

        queue_size = 0 if unbounded or capacity is None else capacity
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=queue_size)

        self._readers: dict[str, ReaderInfo] = {}

    def register_sender(self) -> str:
        """Register a new sender. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        self._state.sender_count += 1
        return 'ok'

    def deregister_sender(self) -> str:
        """Deregister a sender. Returns status code."""
        if self._state.sender_count > 0:
            self._state.sender_count -= 1
        if self._state.sender_count == 0:
            self._state.senders_closed = True
        return 'ok'

    def register_receiver(self, reader_id: str, node_id: str) -> str:
        """Register a new receiver with node tracking. Returns status code."""
        if self._state.receivers_closed:
            return 'closed'

        now = datetime.now(UTC)
        self._readers[reader_id] = ReaderInfo(
            reader_id=reader_id,
            node_id=node_id,
            registered_at=now,
            last_seen_at=now,
            total_received=0,
        )
        self._state.receiver_count += 1
        return 'ok'

    def deregister_receiver(self, reader_id: str) -> str:
        """Deregister a receiver. Returns status code."""
        if reader_id in self._readers:
            del self._readers[reader_id]
            if self._state.receiver_count > 0:
                self._state.receiver_count -= 1
        if self._state.receiver_count == 0:
            self._state.receivers_closed = True
        return 'ok'

    async def put(self, item: T, timeout: float | None = None) -> str:
        """Put an item into the queue. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        if self._state.receivers_closed:
            return 'closed'
        if not self._validator.validate(item):
            return 'type_error'

        try:
            if timeout is not None:
                await asyncio.wait_for(self._queue.put(item), timeout=timeout)
            else:
                await self._queue.put(item)

            self._state.total_sent += 1
            current_size = self._queue.qsize()
            self._state.high_watermark = max(self._state.high_watermark, current_size)
            return 'ok'  # noqa: TRY300
        except TimeoutError:
            return 'full'

    def put_nowait(self, item: T) -> str:
        """Put an item without blocking. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        if self._state.receivers_closed:
            return 'closed'
        if not self._validator.validate(item):
            return 'type_error'

        try:
            self._queue.put_nowait(item)
            self._state.total_sent += 1
            current_size = self._queue.qsize()
            self._state.high_watermark = max(self._state.high_watermark, current_size)
            return 'ok'  # noqa: TRY300
        except asyncio.QueueFull:
            return 'full'

    async def get(self, timeout: float | None = None, reader_id: str | None = None) -> SingleResult[T]:
        """Get an item from the queue. Returns SingleResult."""
        if self._state.senders_closed and self._queue.empty():
            return SingleResult(status='closed')

        try:
            if timeout is not None:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                item = await self._queue.get()

            self._state.total_received += 1
            self._update_reader_stats(reader_id)
            return SingleResult(status='ok', value=item)
        except TimeoutError:
            return SingleResult(status='empty')

    def get_nowait(self, reader_id: str | None = None) -> SingleResult[T]:
        """Get an item without blocking. Returns SingleResult."""
        if self._state.senders_closed and self._queue.empty():
            return SingleResult(status='closed')

        try:
            item = self._queue.get_nowait()
            self._state.total_received += 1
            self._update_reader_stats(reader_id)
            return SingleResult(status='ok', value=item)
        except asyncio.QueueEmpty:
            return SingleResult(status='empty')

    async def put_batch(self, items: tuple[T, ...], timeout: float | None = None) -> str:
        """Put multiple items atomically. Returns status code."""
        if self._state.senders_closed:
            return 'closed'
        if self._state.receivers_closed:
            return 'closed'
        for item in items:
            if not self._validator.validate(item):
                return 'type_error'

        try:
            for item in items:
                if timeout is not None:
                    await asyncio.wait_for(self._queue.put(item), timeout=timeout)
                else:
                    await self._queue.put(item)

            self._state.total_sent += len(items)
            current_size = self._queue.qsize()
            self._state.high_watermark = max(self._state.high_watermark, current_size)
            return 'ok'  # noqa: TRY300
        except TimeoutError:
            return 'full'

    async def get_batch(
        self, max_items: int, timeout: float | None = None, reader_id: str | None = None
    ) -> BatchResult[T]:
        """Get multiple items from the queue. Returns BatchResult."""
        if self._state.senders_closed and self._queue.empty():
            return BatchResult(status='closed')

        collected: list[T] = []
        try:
            for _ in range(max_items):
                if self._queue.empty():
                    break
                if timeout is not None:
                    item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                else:
                    item = await self._queue.get()
                collected.append(item)

            if collected:
                self._state.total_received += len(collected)
                if reader_id and reader_id in self._readers:
                    old = self._readers[reader_id]
                    self._readers[reader_id] = ReaderInfo(
                        reader_id=old.reader_id,
                        node_id=old.node_id,
                        registered_at=old.registered_at,
                        last_seen_at=datetime.now(UTC),
                        total_received=old.total_received + len(collected),
                    )
                return BatchResult(status='ok', items=tuple(collected))
            return BatchResult(status='empty')
        except TimeoutError:
            if collected:
                self._state.total_received += len(collected)
                return BatchResult(status='ok', items=tuple(collected))
            return BatchResult(status='empty')

    def _update_reader_stats(self, reader_id: str | None) -> None:
        """Update reader stats with new immutable ReaderInfo instance."""
        if reader_id and reader_id in self._readers:
            old = self._readers[reader_id]
            self._readers[reader_id] = ReaderInfo(
                reader_id=old.reader_id,
                node_id=old.node_id,
                registered_at=old.registered_at,
                last_seen_at=datetime.now(UTC),
                total_received=old.total_received + 1,
            )
