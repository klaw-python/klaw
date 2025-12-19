"""Oneshot channel implementation: single-value, single-use."""

from __future__ import annotations

import anyio

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import AlreadySent, ChannelClosed, ChannelEmpty

__all__ = ['OneshotReceiver', 'OneshotSender']


class _OneshotState[T]:
    """Shared mutable state for oneshot sender/receiver pair."""

    __slots__ = ('closed', 'event', 'sent', 'value')

    def __init__(self) -> None:
        self.event: anyio.Event = anyio.Event()
        self.value: T | None = None
        self.sent: bool = False
        self.closed: bool = False


class OneshotSender[T]:
    """Oneshot channel sender - single value, single use.

    Can only send one value. After sending, subsequent send() calls
    raise AlreadySentError. Does not support cloning.
    """

    def __init__(self, state: _OneshotState[T]) -> None:
        self._state = state

    async def send(self, value: T) -> None:
        """Send a value through the oneshot channel.

        Can only be called once. Subsequent calls raise AlreadySentError.

        Args:
            value: The value to send.

        Raises:
            AlreadySentError: If send() was already called.
            ChannelClosedError: If the channel was closed before sending.
        """
        if self._state.closed:
            raise ChannelClosed().to_exception()
        if self._state.sent:
            raise AlreadySent().to_exception()

        self._state.value = value
        self._state.sent = True
        self._state.event.set()

    async def try_send(self, value: T) -> Result[None, AlreadySent | ChannelClosed]:
        """Try to send a value without raising exceptions.

        Returns:
            Ok(None) if sent successfully.
            Err(AlreadySent) if already sent.
            Err(ChannelClosed) if channel was closed.
        """
        if self._state.closed:
            return Err(ChannelClosed())
        if self._state.sent:
            return Err(AlreadySent())

        self._state.value = value
        self._state.sent = True
        self._state.event.set()
        return Ok(None)

    def clone(self) -> OneshotSender[T]:
        """Oneshot channels do not support cloning.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError('Oneshot channels do not support cloning')

    async def close(self) -> None:
        """Close the sender without sending a value.

        Unblocks any waiting receivers with ChannelClosed.
        """
        self._state.closed = True
        self._state.event.set()


class OneshotReceiver[T]:
    """Oneshot channel receiver - receives single value once.

    Can only receive one value. After receiving, subsequent recv() calls
    raise ChannelClosedError. Does not support cloning.
    """

    def __init__(self, state: _OneshotState[T]) -> None:
        self._state = state
        self._consumed: bool = False

    async def recv(self) -> T:
        """Receive the value from the oneshot channel.

        Blocks until a value is sent or the channel is closed.
        Can only be called once successfully.

        Returns:
            The sent value.

        Raises:
            ChannelClosedError: If channel closed without sending, or already consumed.
        """
        if self._consumed:
            raise ChannelClosed(reason='already consumed').to_exception()

        await self._state.event.wait()

        if self._state.closed and not self._state.sent:
            raise ChannelClosed().to_exception()

        self._consumed = True
        return self._state.value  # type: ignore[return-value]

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        """Try to receive without blocking.

        Returns:
            Ok(value) if value is available.
            Err(ChannelEmpty) if no value sent yet.
            Err(ChannelClosed) if closed or already consumed.
        """
        if self._consumed:
            return Err(ChannelClosed(reason='already consumed'))

        if not self._state.event.is_set():
            return Err(ChannelEmpty())

        if self._state.closed and not self._state.sent:
            return Err(ChannelClosed())

        self._consumed = True
        return Ok(self._state.value)  # type: ignore[arg-type]

    def clone(self) -> OneshotReceiver[T]:
        """Oneshot channels do not support cloning.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError('Oneshot channels do not support cloning')

    def __aiter__(self) -> OneshotReceiver[T]:
        """Start async iteration (yields at most one value)."""
        return self

    async def __anext__(self) -> T:
        """Get value for async for loop.

        Yields the single value then stops iteration.

        Raises:
            StopAsyncIteration: After yielding the value or if closed.
        """
        if self._consumed:
            raise StopAsyncIteration

        try:
            return await self.recv()
        except Exception:
            raise StopAsyncIteration from None


def create_oneshot[T]() -> tuple[OneshotSender[T], OneshotReceiver[T]]:
    """Create a oneshot sender/receiver pair (sync helper for factory)."""
    state: _OneshotState[T] = _OneshotState()
    return OneshotSender(state), OneshotReceiver(state)
