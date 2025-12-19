"""Local channel implementation using anyio memory object streams."""

from __future__ import annotations

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull

__all__ = ['LocalReceiver', 'LocalSender']


class LocalSender[T]:
    """Local channel sender using anyio memory object streams.

    Thread-safe and task-safe via anyio.MemoryObjectSendStream.
    Automatically signals closure when all sender clones are closed.
    """

    def __init__(self, stream: MemoryObjectSendStream[T]) -> None:
        """Initialize sender wrapping an anyio send stream.

        Args:
            stream: anyio.MemoryObjectSendStream to send to.
        """
        self._stream = stream

    async def send(self, value: T) -> None:
        """Send a value, blocking if channel is at capacity.

        Awaits until value is queued or channel closes. Integrates with
        anyio/trio cancellation: cancellation during send will raise
        the appropriate cancellation exception.

        Args:
            value: The value to send.

        Raises:
            ChannelClosedError: If all receivers have been dropped.
            anyio.get_cancelled_exc_class(): If cancelled during wait.

        Example:
            ```python
            tx, rx = await channel[int]()
            await tx.send(42)
            ```
        """
        try:
            await self._stream.send(value)
        except anyio.BrokenResourceError:
            raise ChannelClosed().to_exception() from None
        except anyio.ClosedResourceError:
            raise ChannelClosed().to_exception() from None

    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        """Send a value without blocking.

        Returns immediately: Ok(None) if sent, or Err if queue full or closed.

        Returns:
            Result[None, ChannelFull | ChannelClosed]

        Example:
            ```python
            tx, rx = await channel[int]()
            match await tx.try_send(42):
                case Ok(_): print("sent")
                case Err(ChannelFull(cap)): print(f"queue full, capacity={cap}")
                case Err(ChannelClosed()): print("channel closed")
            ```
        """
        try:
            self._stream.send_nowait(value)
            return Ok(None)
        except anyio.WouldBlock:
            stats = self._stream.statistics()
            return Err(ChannelFull(int(stats.max_buffer_size)))
        except anyio.BrokenResourceError:
            return Err(ChannelClosed())
        except anyio.ClosedResourceError:
            return Err(ChannelClosed())

    def clone(self) -> LocalSender[T]:
        """Clone this sender for multi-producer use.

        Creates a new sender sharing the same stream. Each clone can be
        closed separately; the channel only closes when all clones close.

        Non-async: cloning is atomic and doesn't require suspension.

        Returns:
            A new LocalSender[T] pointing to the same stream.

        Example:
            ```python
            tx1, rx = await channel[int]()
            tx2 = tx1.clone()
            await tx1.send(1)
            await tx2.send(2)
            # rx receives messages from both senders
            ```
        """
        return LocalSender(self._stream.clone())

    async def close(self) -> None:
        """Close this sender half of the channel.

        Signals to receivers that this sender will send no more messages.
        When all senders close, receivers will see EndOfStream.
        """
        await self._stream.aclose()


class LocalReceiver[T]:
    """Local channel receiver using anyio memory object streams.

    Thread-safe and task-safe via anyio.MemoryObjectReceiveStream.
    Supports async iteration and both blocking/non-blocking receive.
    """

    def __init__(self, stream: MemoryObjectReceiveStream[T]) -> None:
        """Initialize receiver wrapping an anyio receive stream.

        Args:
            stream: anyio.MemoryObjectReceiveStream to receive from.
        """
        self._stream = stream

    async def recv(self) -> T:
        """Receive the next value, blocking if channel is empty.

        Awaits until a message arrives or all senders close. Integrates
        with anyio/trio cancellation.

        Returns:
            The next value from the channel.

        Raises:
            ChannelClosedError: If all senders closed and queue is empty.
            anyio.get_cancelled_exc_class(): If cancelled during wait.

        Example:
            ```python
            tx, rx = await channel[int]()
            await tx.send(42)
            value = await rx.recv()
            assert value == 42
            ```
        """
        try:
            return await self._stream.receive()
        except anyio.EndOfStream:
            raise ChannelClosed().to_exception() from None
        except anyio.ClosedResourceError:
            raise ChannelClosed().to_exception() from None

    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        """Receive without blocking.

        Returns immediately: Ok(value) if available, or Err if empty/closed.

        Returns:
            Result[T, ChannelEmpty | ChannelClosed]

        Example:
            ```python
            tx, rx = await channel[int]()
            match await rx.try_recv():
                case Ok(value): print(f"got {value}")
                case Err(ChannelEmpty()): print("no messages")
                case Err(ChannelClosed()): print("channel closed")
            ```
        """
        try:
            return Ok(self._stream.receive_nowait())
        except anyio.WouldBlock:
            return Err(ChannelEmpty())
        except anyio.EndOfStream:
            return Err(ChannelClosed())
        except anyio.ClosedResourceError:
            return Err(ChannelClosed())

    def clone(self) -> LocalReceiver[T]:
        """Clone this receiver for multi-consumer use.

        Creates a new receiver sharing the same stream. Each clone can be
        closed separately; the channel only closes when all clones close.

        Non-async: cloning is atomic and doesn't require suspension.

        Returns:
            A new LocalReceiver[T] pointing to the same stream.

        Example:
            ```python
            tx, rx1 = await channel[int]()
            rx2 = rx1.clone()
            await tx.send(42)
            v1 = await rx1.recv()  # 42 (MPMC - one receiver gets it)
            # rx2 may or may not get it depending on timing
            ```
        """
        return LocalReceiver(self._stream.clone())

    async def close(self) -> None:
        """Close this receiver half of the channel.

        Signals that this receiver will no longer consume messages.
        When all receivers close, senders will get BrokenResourceError
        on their next send attempt.
        """
        await self._stream.aclose()

    def __aiter__(self) -> LocalReceiver[T]:
        """Start async iteration.

        Enables `async for value in rx:` syntax. Iteration ends when
        all senders close (yields StopAsyncIteration).

        Returns:
            Self as async iterator.
        """
        return self

    async def __anext__(self) -> T:
        """Get next value for async for loop.

        Called internally by async iteration. Converts EndOfStream
        to StopAsyncIteration to signal end of iteration.

        Returns:
            The next value from the channel.

        Raises:
            StopAsyncIteration: When all senders close.
        """
        try:
            return await self._stream.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None
