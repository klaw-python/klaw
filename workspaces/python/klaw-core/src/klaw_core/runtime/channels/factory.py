"""Channel factory functions: channel, oneshot, broadcast, watch, select."""

from __future__ import annotations

import math
import random
from typing import Any

import anyio

from klaw_core.result import Ok


class _RandomProvider:
    """Lazy-loading random provider with klaw_random fallback to stdlib."""

    __slots__ = ('_provider',)

    def __init__(self) -> None:
        self._provider: Any = None

    def rand_range(self, start: int, stop: int) -> int:
        """Generate random int in [start, stop) using klaw_random or stdlib fallback."""
        if self._provider is None:
            try:
                import klaw_random as kr

                self._provider = kr
            except ImportError:
                self._provider = False
        if self._provider:
            return self._provider.rand_range_u64(start, stop)
        return random.randrange(start, stop)  # noqa: S311


_random_provider = _RandomProvider()


def _rand_range(start: int, stop: int) -> int:
    """Generate random int in [start, stop) using klaw_random or stdlib fallback."""
    return _random_provider.rand_range(start, stop)


from klaw_core.runtime.channels.broadcast import (
    BroadcastReceiver,
    BroadcastSender,
    create_broadcast,
)
from klaw_core.runtime.channels.local import LocalReceiver, LocalSender
from klaw_core.runtime.channels.oneshot import (
    OneshotReceiver,
    OneshotSender,
    create_oneshot,
)
from klaw_core.runtime.channels.protocols import Receiver, Sender
from klaw_core.runtime.channels.watch import (
    WatchReceiver,
    WatchSender,
    create_watch,
)
from klaw_core.runtime.errors import NoReceivers

__all__ = ['broadcast', 'channel', 'oneshot', 'select', 'watch']


async def channel[T](
    capacity: int = 10000, distributed: bool = False, unbounded: bool = False
) -> tuple[Sender[T], Receiver[T]]:
    """Create a multi-producer multi-consumer channel.

    Returns a pair of (Sender, Receiver) that can be cloned for distributed use.

    Args:
        capacity: Max messages in buffer before senders block (default 10,000).
                 Ignored if unbounded=True.
        distributed: If True, use DistributedChannel for inter-process/network use.
                    Requires msgspec serializable types.
        unbounded: If True, buffer has no size limit (memory usage unbounded).

    Returns:
        Tuple of (Sender[T], Receiver[T]).

    Example:
        ```python
        tx, rx = await channel(capacity=100)
        await tx.send(42)
        value = await rx.recv()
        ```
    """
    if distributed:
        raise NotImplementedError('Distributed channels (distributed=True) not yet implemented')

    if unbounded:
        buffer_size: int | float = math.inf
    else:
        buffer_size = capacity

    send_stream, recv_stream = anyio.create_memory_object_stream[T](max_buffer_size=buffer_size)

    tx: Sender[T] = LocalSender(send_stream)
    rx: Receiver[T] = LocalReceiver(recv_stream)

    return tx, rx


async def oneshot[T]() -> tuple[OneshotSender[T], OneshotReceiver[T]]:
    """Create a single-value, single-use channel.

    The sender can only send one message. After sending, subsequent
    send() calls raise AlreadySentError. The receiver can only consume
    the value once.

    Unlike regular channels, oneshot does not support cloning.

    Returns:
        Tuple of (OneshotSender[T], OneshotReceiver[T]) for one-shot communication.

    Example:
        ```python
        tx, rx = await oneshot[int]()
        await tx.send(42)
        value = await rx.recv()
        assert value == 42
        ```
    """
    return create_oneshot()


async def broadcast[T](capacity: int = 16) -> tuple[BroadcastSender[T], BroadcastReceiver[T]]:
    """Create a broadcast channel where all receivers get every message.

    Unlike MPMC channels, each receiver sees all messages sent.
    New receivers miss historical messages (only see new ones).
    When receivers fall behind, they receive a LaggedError indicating
    how many messages were skipped.

    Args:
        capacity: Number of messages to buffer (default 16).
                 Older messages are dropped when capacity is reached.
                 Capacity is rounded up to the nearest power of 2.

    Returns:
        Tuple of (BroadcastSender[T], BroadcastReceiver[T]).

    Example:
        ```python
        tx, rx1 = await broadcast[int]()
        rx2 = tx.subscribe()  # New receiver from sender
        await tx.send(1)
        await tx.send(2)
        v1a = await rx1.recv()  # 1
        v1b = await rx1.recv()  # 2
        v2a = await rx2.recv()  # 1
        v2b = await rx2.recv()  # 2
        ```
    """
    return create_broadcast(capacity)


async def watch[T](initial: T) -> tuple[WatchSender[T], WatchReceiver[T]]:
    """Create a watch channel that always holds the latest value.

    Receivers can `.borrow()` the current value or `.changed()` to
    wait for updates. Only the most recent value is stored; intermediate
    values are collapsed.

    Unlike broadcast channels, watch channels:
    - Always have a value (initialized at creation)
    - Only store the latest value (no buffer)
    - Use version tracking for change detection (no lagging)

    Args:
        initial: Initial value to store and return to new receivers.

    Returns:
        Tuple of (WatchSender[T], WatchReceiver[T]) for latest-value observation.

    Example:
        ```python
        tx, rx = await watch(initial=0)
        await tx.send(42)
        await rx.changed()  # waits for next update
        value = rx.borrow()  # 42
        ```
    """
    return create_watch(initial)


async def select(
    *receivers: Receiver[Any],
    timeout: float | None = None,
    biased: bool = False,
) -> tuple[int, Any]:
    """Multiplex multiple receivers, returning the first available message.

    Polls all receivers and returns a tuple of (index, value) for the first
    receiver that has a message available. If no messages are immediately
    available, concurrently waits on all receivers until one produces a value.

    The index identifies which receiver produced the value, enabling callers
    to branch on the source. This is similar to Tokio's `select!` macro.

    Args:
        *receivers: Variable number of Receiver objects to multiplex.
        timeout: Max seconds to wait (None = no timeout). If timeout expires
            before any receiver produces a value, raises TimeoutError.
        biased: If False (default), receivers are polled in random order for
            fairness. If True, receivers are polled in argument order (index 0
            first), giving priority to earlier receivers.

    Returns:
        Tuple of (index, value) where index is the position of the receiver
        that produced the value in the arguments list (0-indexed).

    Raises:
        NoReceiversError: If no receivers are provided.
        ChannelClosedError: If the selected receiver's channel is closed.
        TimeoutError: If timeout expires with no messages available.

    Example:
        ```python
        tx1, rx1 = await channel[int]()
        tx2, rx2 = await channel[str]()

        await tx1.send(42)

        idx, value = await select(rx1, rx2)
        if idx == 0:
            print(f"Got int from rx1: {value}")
        elif idx == 1:
            print(f"Got str from rx2: {value}")
        ```

    Note:
        Fairness is best-effort. The `biased` parameter only affects the
        polling order when checking for immediately available messages.
        When waiting concurrently, the event loop determines which receiver
        completes first.
    """
    if not receivers:
        raise NoReceivers().to_exception()

    if timeout is not None:
        with anyio.fail_after(timeout):
            return await _select_impl(receivers, biased)
    else:
        return await _select_impl(receivers, biased)


async def _select_impl(receivers: tuple[Receiver[Any], ...], biased: bool) -> tuple[int, Any]:
    """Core select implementation without timeout handling."""
    n = len(receivers)
    start = 0 if biased else _rand_range(0, n)

    for offset in range(n):
        idx = (start + offset) % n
        result = await receivers[idx].try_recv()
        if isinstance(result, Ok):
            return (idx, result.value)

    # Fast-path found no ready receivers, fall through to slow-path
    return await _select_slow_path(receivers)


async def _select_slow_path(receivers: tuple[Receiver[Any], ...]) -> tuple[int, Any]:
    """Slow-path: concurrently wait on all receivers, return first to complete.

    Spawns one task per receiver. First task to get a value (or error) wins.
    All other tasks are cancelled.
    """
    winner_idx: int | None = None
    winner_value: Any = None
    winner_exc: BaseException | None = None
    winner_event = anyio.Event()

    async def recv_task(idx: int, rx: Receiver[Any]) -> None:
        nonlocal winner_idx, winner_value, winner_exc

        try:
            value = await rx.recv()
        except BaseException as exc:
            if winner_idx is None:
                winner_idx = idx
                winner_exc = exc
                winner_event.set()
        else:
            if winner_idx is None:
                winner_idx = idx
                winner_value = value
                winner_event.set()

    async with anyio.create_task_group() as tg:
        for idx, rx in enumerate(receivers):
            tg.start_soon(recv_task, idx, rx)

        await winner_event.wait()
        tg.cancel_scope.cancel()

    if winner_exc is not None:
        raise winner_exc

    assert winner_idx is not None
    return (winner_idx, winner_value)
