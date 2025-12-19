"""Watch channel implementation: single latest-value observation."""

from __future__ import annotations

import anyio

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import ChannelClosed

__all__ = ['WatchReceiver', 'WatchSender']


class _WatchState[T]:
    """Shared mutable state for watch sender/receiver pairs.

    Holds a single value with version tracking for change detection.
    Each receiver maintains its own seen version; changed() waits
    until the version advances beyond what the receiver has seen.
    """

    __slots__ = ('closed', 'lock', 'rx_count', 'tx_count', 'value', 'version', 'waiters')

    def __init__(self, initial: T) -> None:
        self.value: T = initial
        self.version: int = 0
        self.tx_count: int = 1
        self.rx_count: int = 1
        self.closed: bool = False
        self.waiters: list[anyio.Event] = []
        self.lock: anyio.Lock = anyio.Lock()


class WatchSender[T]:
    """Watch channel sender - sets the latest value for all receivers.

    Supports cloning for multi-producer use. Use subscribe() to create
    new receivers that start from the current version.
    """

    def __init__(self, state: _WatchState[T]) -> None:
        self._state = state

    async def send(self, value: T) -> int:
        """Set the watched value and notify all receivers.

        Overwrites the current value and increments the version.
        All receivers waiting on changed() will be woken.

        Args:
            value: The new value to store.

        Returns:
            Number of active receivers at time of send.

        Raises:
            ChannelClosedError: If no receivers exist.
        """
        state = self._state

        async with state.lock:
            if state.rx_count == 0:
                raise ChannelClosed().to_exception()

            state.value = value
            state.version += 1

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

            state.value = value
            state.version += 1

            waiters = state.waiters
            state.waiters = []
            rx_count = state.rx_count

        for event in waiters:
            event.set()

        return Ok(rx_count)

    async def close(self) -> None:
        """Close this sender.

        Decrements the sender reference count. When all senders are closed,
        receivers will see ChannelClosed on their next changed() call.
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

    def clone(self) -> WatchSender[T]:
        """Clone this sender for multi-producer use.

        Creates a new sender sharing the same channel. Each clone can be
        closed separately; the channel only closes when all clones close.

        Returns:
            A new WatchSender[T] pointing to the same channel.
        """
        self._state.tx_count += 1
        return WatchSender(self._state)

    def subscribe(self) -> WatchReceiver[T]:
        """Create a new receiver starting from the current version.

        The new receiver has already 'seen' the current value; changed()
        will only complete after a new send().

        Returns:
            A new WatchReceiver[T] starting at the current version.
        """
        state = self._state
        state.rx_count += 1
        return WatchReceiver(state, state.version)


class WatchReceiver[T]:
    """Watch channel receiver - observes the latest value.

    Each receiver tracks its own seen version. Use borrow() to read
    the current value, borrow_and_update() to read and mark as seen,
    or changed() to wait for new values.
    """

    def __init__(self, state: _WatchState[T], seen_version: int) -> None:
        self._state = state
        self._seen: int = seen_version

    def borrow(self) -> T:
        """Borrow the current value without marking it as seen.

        Returns the current value directly. Does not affect whether
        changed() will return immediately or wait.

        Note: Returns a direct reference to the stored object.
        Treat the value as immutable or copy if isolation is needed.

        Returns:
            The current watched value.
        """
        return self._state.value

    def borrow_and_update(self) -> T:
        """Borrow the current value and mark it as seen.

        Returns the current value and updates the seen version so that
        subsequent changed() calls will wait for newer values.

        Returns:
            The current watched value.
        """
        state = self._state
        self._seen = state.version
        return state.value

    async def changed(self) -> None:
        """Wait until the watched value changes.

        Returns immediately if the value has changed since last observation.
        Otherwise blocks until a new value is sent or the channel closes.

        After returning, the new version is marked as seen.

        Raises:
            ChannelClosedError: If all senders closed and no new value
                is available beyond what this receiver has already seen.
        """
        state = self._state

        while True:
            async with state.lock:
                if self._seen != state.version:
                    self._seen = state.version
                    return

                if state.closed:
                    raise ChannelClosed().to_exception()

                event = anyio.Event()
                state.waiters.append(event)

            await event.wait()

    async def try_changed(self) -> Result[None, ChannelClosed]:
        """Check if the value has changed without blocking.

        Returns:
            Ok(None) if a new value is available (marks it as seen).
            Err(ChannelClosed) if closed and no new value available.

        Note: Returns Err(ChannelClosed) if no change yet and not closed.
        Use borrow() to read the current value regardless.
        """
        state = self._state

        async with state.lock:
            if self._seen != state.version:
                self._seen = state.version
                return Ok(None)

            if state.closed:
                return Err(ChannelClosed())

            return Err(ChannelClosed())

    def has_changed(self) -> bool:
        """Check if the value has changed since last observation.

        Non-blocking check that does not mark the value as seen.

        Returns:
            True if a new value is available, False otherwise.
        """
        return self._seen != self._state.version

    def resubscribe(self) -> WatchReceiver[T]:
        """Create a new receiver starting from the current version.

        The new receiver has already 'seen' the current value; changed()
        will only complete after a new send().

        Returns:
            A new WatchReceiver[T] starting at the current version.
        """
        state = self._state
        state.rx_count += 1
        return WatchReceiver(state, state.version)

    def __aiter__(self) -> WatchReceiver[T]:
        """Start async iteration.

        Enables `async for value in rx:` syntax. Iteration ends when
        all senders close. Each iteration yields the value after a change.

        Returns:
            Self as async iterator.
        """
        return self

    async def __anext__(self) -> T:
        """Get next changed value for async for loop.

        Waits for the next change and returns the new value.

        Returns:
            The new value after a change.

        Raises:
            StopAsyncIteration: When all senders close.
        """
        try:
            await self.changed()
            return self.borrow()
        except Exception:
            raise StopAsyncIteration from None


def create_watch[T](initial: T) -> tuple[WatchSender[T], WatchReceiver[T]]:
    """Create a watch sender/receiver pair (sync helper for factory)."""
    state: _WatchState[T] = _WatchState(initial)
    return WatchSender(state), WatchReceiver(state, state.version)
