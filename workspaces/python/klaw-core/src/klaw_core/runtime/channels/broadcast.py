"""Broadcast channel implementation: multi-producer, multi-consumer fan-out."""

from __future__ import annotations

import anyio

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, Lagged

__all__ = ['BroadcastReceiver', 'BroadcastSender']


class _Slot[T]:
    """Slot in the ring buffer holding a value and its position."""

    __slots__ = ('pos', 'val')

    def __init__(self) -> None:
        self.pos: int = 0
        self.val: T | None = None


class _BroadcastState[T]:
    """Shared mutable state for broadcast sender/receiver pairs.

    Uses a ring buffer with per-slot position tracking to detect lagging.
    Each receiver maintains its own cursor; when a slot's position has
    advanced beyond what a receiver expects, the receiver has lagged.
    """

    __slots__ = ('buffer', 'capacity', 'closed', 'lock', 'mask', 'pos', 'rx_count', 'tx_count', 'waiters')

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError('Broadcast channel capacity must be at least 1')
        if capacity & (capacity - 1) != 0:
            power = 1
            while power < capacity:
                power *= 2
            capacity = power

        self.capacity: int = capacity
        self.mask: int = capacity - 1
        self.buffer: list[_Slot[T]] = [_Slot() for _ in range(capacity)]
        self.pos: int = 0
        self.tx_count: int = 1
        self.rx_count: int = 1
        self.closed: bool = False
        self.waiters: list[anyio.Event] = []
        self.lock: anyio.Lock = anyio.Lock()

    def oldest_pos(self) -> int:
        """Return the oldest position still in the buffer."""
        if self.pos <= self.capacity:
            return 0
        return self.pos - self.capacity


class BroadcastSender[T]:
    """Broadcast channel sender - sends to all receivers.

    Supports cloning for multi-producer use. Use subscribe() to create
    new receivers that start from the current position.
    """

    def __init__(self, state: _BroadcastState[T]) -> None:
        self._state = state

    async def send(self, value: T) -> int:
        """Send a value to all receivers.

        Writes to the ring buffer and wakes all waiting receivers.
        Never blocks (broadcast channels overwrite old values when full).

        Args:
            value: The value to broadcast.

        Returns:
            Number of active receivers at time of send.

        Raises:
            ChannelClosedError: If all receivers have been dropped.
        """
        state = self._state

        async with state.lock:
            if state.rx_count == 0:
                raise ChannelClosed().to_exception()

            pos = state.pos
            idx = pos & state.mask

            slot = state.buffer[idx]
            slot.pos = pos
            slot.val = value

            state.pos = pos + 1

            waiters = state.waiters
            state.waiters = []
            rx_count = state.rx_count

        for event in waiters:
            event.set()

        return rx_count

    async def try_send(self, value: T) -> Result[int, ChannelClosed]:
        """Try to send a value without raising exceptions.

        Returns:
            Ok(rx_count) if sent successfully.
            Err(ChannelClosed) if no receivers exist.
        """
        state = self._state

        async with state.lock:
            if state.rx_count == 0:
                return Err(ChannelClosed())

            pos = state.pos
            idx = pos & state.mask

            slot = state.buffer[idx]
            slot.pos = pos
            slot.val = value

            state.pos = pos + 1

            waiters = state.waiters
            state.waiters = []
            rx_count = state.rx_count

        for event in waiters:
            event.set()

        return Ok(rx_count)

    async def close(self) -> None:
        """Close this sender.

        Decrements the sender reference count. When all senders are closed,
        receivers will see ChannelClosed after draining any remaining messages.
        """
        state = self._state

        async with state.lock:
            if state.tx_count > 0:
                state.tx_count -= 1

            if state.tx_count == 0:
                state.closed = True
                waiters = state.waiters
                state.waiters = []
            else:
                waiters = []

        for event in waiters:
            event.set()

    def clone(self) -> BroadcastSender[T]:
        """Clone this sender for multi-producer use.

        Creates a new sender sharing the same channel. Each clone can be
        closed separately; the channel only closes when all clones close.

        Returns:
            A new BroadcastSender[T] pointing to the same channel.
        """
        self._state.tx_count += 1
        return BroadcastSender(self._state)

    def subscribe(self) -> BroadcastReceiver[T]:
        """Create a new receiver starting from the current position.

        The new receiver will only receive messages sent after this call.
        It will not receive any backlog of messages.

        Returns:
            A new BroadcastReceiver[T] starting at the current tail.
        """
        state = self._state
        state.rx_count += 1
        return BroadcastReceiver(state, state.pos)


class BroadcastReceiver[T]:
    """Broadcast channel receiver - receives all messages sent after subscription.

    Each receiver has its own cursor and receives every message independently.
    Does not support clone(); use resubscribe() to create a new receiver
    starting from the current tail position.
    """

    def __init__(self, state: _BroadcastState[T], next_pos: int) -> None:
        self._state = state
        self._next: int = next_pos

    async def recv(self) -> T:
        """Receive the next broadcast message.

        Blocks until a message is available. Each receiver independently
        receives all messages sent after its subscription.

        Returns:
            The next value from the broadcast channel.

        Raises:
            ChannelClosedError: If all senders closed and no messages remain.
            LaggedError: If this receiver fell behind and messages were lost.
                The receiver's cursor is advanced to the oldest available message.
        """
        state = self._state

        while True:
            async with state.lock:
                if self._next < state.pos:
                    idx = self._next & state.mask
                    slot = state.buffer[idx]

                    if slot.pos != self._next:
                        skipped = state.oldest_pos() - self._next
                        self._next = state.oldest_pos()
                        raise Lagged(skipped).to_exception()

                    value = slot.val
                    self._next += 1
                    return value  # type: ignore[return-value]

                if state.closed:
                    raise ChannelClosed().to_exception()

                event = anyio.Event()
                state.waiters.append(event)

            await event.wait()

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed | Lagged]:
        """Try to receive without blocking.

        Returns immediately with the result.

        Returns:
            Ok(value) if a message is available.
            Err(ChannelEmpty) if no messages are available.
            Err(ChannelClosed) if all senders closed and no messages remain.
            Err(Lagged(n)) if this receiver fell behind; cursor is advanced.
        """
        state = self._state

        async with state.lock:
            if self._next >= state.pos:
                if state.closed:
                    return Err(ChannelClosed())
                return Err(ChannelEmpty())

            idx = self._next & state.mask
            slot = state.buffer[idx]

            if slot.pos != self._next:
                skipped = state.oldest_pos() - self._next
                self._next = state.oldest_pos()
                return Err(Lagged(skipped))

            value = slot.val
            self._next += 1
            return Ok(value)  # type: ignore[arg-type]

    def resubscribe(self) -> BroadcastReceiver[T]:
        """Create a new receiver starting from the current tail position.

        The new receiver will only receive messages sent after this call.
        Useful for recovering from lagging by starting fresh.

        Returns:
            A new BroadcastReceiver[T] starting at the current tail.
        """
        state = self._state
        state.rx_count += 1
        return BroadcastReceiver(state, state.pos)

    def __aiter__(self) -> BroadcastReceiver[T]:
        """Start async iteration.

        Enables `async for value in rx:` syntax. Iteration ends when
        all senders close. Lagged messages are skipped during iteration.

        Returns:
            Self as async iterator.
        """
        return self

    async def __anext__(self) -> T:
        """Get next value for async for loop.

        Skips lagged messages automatically during iteration.

        Returns:
            The next value from the broadcast channel.

        Raises:
            StopAsyncIteration: When all senders close.
        """
        from klaw_core.runtime.errors import LaggedError

        while True:
            try:
                return await self.recv()
            except LaggedError:
                continue
            except Exception:
                raise StopAsyncIteration from None


def create_broadcast[T](capacity: int = 16) -> tuple[BroadcastSender[T], BroadcastReceiver[T]]:
    """Create a broadcast sender/receiver pair (sync helper for factory)."""
    state: _BroadcastState[T] = _BroadcastState(capacity)
    return BroadcastSender(state), BroadcastReceiver(state, state.pos)
