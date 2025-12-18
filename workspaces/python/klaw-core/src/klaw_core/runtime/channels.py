"""Channels: multi-producer multi-consumer, oneshot, broadcast, watch, select.

Provides ergonomic channel types for passing data between concurrent tasks:
- `channel[T]()`: Multi-producer multi-consumer MPMC channel
- `oneshot[T]()`: Single-value, single-use channel
- `broadcast[T]()`: All receivers get every message
- `watch[T](initial)`: Latest-value observation with `.borrow()` and `.changed()`
- `select(*receivers)`: Multiplex multiple receivers

All channels support async/await operations and can be cloned for distributed use.

Built on anyio.create_memory_object_stream() which provides:
- Thread-safe and task-safe send/receive
- Automatic closure signaling (EndOfStream exception when all senders close)
- Reference-counted clones (stream only closes when all clones are closed)
- Async iteration support
- MPMC semantics (each message delivered to one receiver)

## Cancellation & Timeouts

Channels integrate with anyio/trio cancellation semantics:
- Send/recv operations can be cancelled via anyio.CancelScope()
- Timeouts should be enforced by the caller using anyio.fail_after() or anyio.move_on_after()
- Cancellation during send/recv will raise anyio.get_cancelled_exc_class()

Example with timeout:
    ```python
    with anyio.fail_after(5):
        value = await rx.recv()  # Raises TimeoutError if takes >5s
    ```
"""

from __future__ import annotations

import math
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from klaw_core.result import Err, Ok, Result
from klaw_core.runtime.errors import ChannelClosed, ChannelClosedError, ChannelEmpty, ChannelFull

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = [
    "Sender",
    "Receiver",
    "channel",
    "oneshot",
    "broadcast",
    "watch",
    "select",
]

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


# --- Sender Protocol ---


class Sender(Protocol[T]):
    """Protocol for sending values into a channel.

    Sender is the transmit half of a channel. Multiple senders can exist
    (via `clone()`), enabling multi-producer patterns. When all senders
    are dropped, the channel signals `ChannelClosed` to receivers.

    Type Parameters:
        T: The type of values sent through the channel.
    """

    @abstractmethod
    async def send(self, value: T) -> None:
        """Send a value, blocking if channel is at capacity.

        Awaits until the value is queued. If the channel is closed
        (all receivers dropped), raises `ChannelClosedError`.

        Args:
            value: The value to send.

        Raises:
            ChannelClosedError: If all receivers have been dropped.

        Example:
            ```python
            tx, rx = await channel[int]()
            await tx.send(42)
            ```
        """
        ...

    @abstractmethod
    async def try_send(self, value: T) -> Any:
        """Send a value without blocking.

        Returns `Ok(None)` if queued, or `Err(ChannelFull | ChannelClosed)`.

        Returns:
            Result[None, ChannelFull | ChannelClosed]

        Example:
            ```python
            result = await tx.try_send(42)
            match result:
                case Ok(_): print("sent")
                case Err(ChannelFull(_)): print("full")
                case Err(ChannelClosed(_)): print("closed")
            ```
        """
        ...

    @abstractmethod
    def clone(self) -> Sender[T]:
        """Clone this sender for multi-producer use.

        Returns a new sender that shares the same underlying channel.
        Each clone increments the sender count; dropping all clones
        signals channel closure to receivers.

        This is a synchronous operation: it only increments a reference
        counter and returns immediately (no I/O or waiting involved).

        Returns:
            A new Sender[T] pointing to the same channel.

        Example:
            ```python
            tx1, rx = await channel[int]()
            tx2 = tx1.clone()  # Synchronous, returns immediately
            await tx1.send(1)
            await tx2.send(2)
            ```
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close this sender half of the channel.

        Signals to receivers that no more messages will arrive from
        this sender. If this is the last active sender, receivers
        will see `ChannelClosed` after draining the queue.

        Example:
            ```python
            await tx.close()
            ```
        """
        ...


# --- Receiver Protocol ---


class Receiver(Protocol[T_co]):
    """Protocol for receiving values from a channel.

    Receiver is the receive half of a channel. Multiple receivers can exist
    (via `clone()`), enabling multi-consumer patterns. When all senders
    are dropped, `recv()` returns `Err(ChannelClosed)` after draining.

    Type Parameters:
        T_co: The type of values received (covariant).
    """

    @abstractmethod
    async def recv(self) -> T_co:
        """Receive the next value, blocking if channel is empty.

        Awaits until a value is available or all senders close.
        After the channel closes, subsequent calls raise `ChannelClosedError`.

        Returns:
            The next value from the channel.

        Raises:
            ChannelClosedError: If all senders have been dropped and queue is empty.

        Example:
            ```python
            tx, rx = await channel[int]()
            await tx.send(42)
            value = await rx.recv()
            assert value == 42
            ```
        """
        ...

    @abstractmethod
    async def try_recv(self) -> Any:
        """Receive the next value without blocking.

        Returns `Ok(value)` if available, or `Err(ChannelEmpty | ChannelClosed)`.

        Returns:
            Result[T, ChannelEmpty | ChannelClosed]

        Example:
            ```python
            result = await rx.try_recv()
            match result:
                case Ok(value): print(f"got {value}")
                case Err(ChannelEmpty()): print("no messages")
                case Err(ChannelClosed()): print("closed")
            ```
        """
        ...

    @abstractmethod
    def clone(self) -> Receiver[T_co]:
        """Clone this receiver for multi-consumer use.

        Returns a new receiver that shares the same underlying channel.
        Each clone increments the receiver count. All clones receive
        the same messages (MPMC semantics).

        This is a synchronous operation: it only increments a reference
        counter and returns immediately (no I/O or waiting involved).

        Returns:
            A new Receiver[T] pointing to the same channel.

        Example:
            ```python
            tx, rx1 = await channel[int]()
            rx2 = rx1.clone()  # Synchronous, returns immediately
            await tx.send(42)
            v1 = await rx1.recv()  # 42 (or empty if rx2 took it)
            v2 = await rx2.recv()  # 42 (or empty if rx1 took it - MPMC)
            ```
        """
        ...

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[T_co]:
        """Iterate over messages as they arrive.

        Enables `async for` syntax. Iteration ends when channel closes
        and queue is drained.

        Returns:
            AsyncIterator yielding T_co values.

        Example:
            ```python
            tx, rx = await channel[int]()
            async def send_msgs():
                for i in range(3):
                    await tx.send(i)
                await tx.close()
            
            async for value in rx:
                print(value)
            # prints: 0, 1, 2
            ```
        """
        ...

    @abstractmethod
    async def __anext__(self) -> T_co:
        """Get next message for `async for` iteration.

        Called internally by async iteration. Raises `StopAsyncIteration`
        when channel closes and queue is empty.

        Returns:
            The next value from the channel.

        Raises:
            StopAsyncIteration: When iteration ends.
        """
        ...


# --- LocalChannel Implementation ---


class LocalSender(Generic[T]):
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
            # Receivers have been closed
            raise ChannelClosed().to_exception() from None
        except anyio.ClosedResourceError:
            # This sender was already closed
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
            # Buffer is full
            stats = self._stream.statistics()
            return Err(ChannelFull(int(stats.max_buffer_size)))
        except anyio.BrokenResourceError:
            # Receivers have been closed
            return Err(ChannelClosed())
        except anyio.ClosedResourceError:
            # This sender was already closed
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


class LocalReceiver(Generic[T]):
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
            # All senders have closed
            raise ChannelClosed().to_exception() from None
        except anyio.ClosedResourceError:
            # This receiver was already closed
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
            # No items in buffer and no senders waiting
            return Err(ChannelEmpty())
        except anyio.EndOfStream:
            # All senders have closed and buffer is empty
            return Err(ChannelClosed())
        except anyio.ClosedResourceError:
            # This receiver was already closed
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


# --- Factory Functions ---


async def channel(
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
        raise NotImplementedError(
            "Distributed channels (distributed=True) not yet implemented"
        )

    # Determine buffer size (anyio requires int or math.inf)
    if unbounded:
        buffer_size: int | float = math.inf
    else:
        buffer_size = capacity

    # Create the underlying memory object stream
    send_stream, recv_stream = anyio.create_memory_object_stream[T](
        max_buffer_size=buffer_size
    )

    # Create sender and receiver wrappers
    tx: Sender[T] = LocalSender(send_stream)
    rx: Receiver[T] = LocalReceiver(recv_stream)

    return tx, rx


async def oneshot[T]() -> tuple[Sender[T], Receiver[T]]:
    """Create a single-value, single-use channel.

    The sender can only send one message. After sending, the channel
    automatically closes. Receivers must consume once.

    Returns:
        Tuple of (Sender[T], Receiver[T]) for one-shot communication.

    Example:
        ```python
        tx, rx = await oneshot[int]()
        await tx.send(42)
        value = await rx.recv()
        ```
    """
    raise NotImplementedError("oneshot() factory not yet implemented")


async def broadcast[T](capacity: int = 10000) -> tuple[Sender[T], Receiver[T]]:
    """Create a broadcast channel where all receivers get every message.

    Unlike MPMC channels, each receiver sees all messages sent.
    New receivers miss historical messages (only see new ones).

    Args:
        capacity: Number of messages to buffer (default 10,000).
                 Older messages are dropped when capacity is reached.

    Returns:
        Tuple of (Sender[T], Receiver[T]) for broadcast communication.

    Example:
        ```python
        tx, rx1 = await broadcast[int]()
        rx2 = await rx1.clone()
        await tx.send(1)
        await tx.send(2)
        v1a = await rx1.recv()  # 1
        v1b = await rx1.recv()  # 2
        v2a = await rx2.recv()  # 1
        v2b = await rx2.recv()  # 2
        ```
    """
    raise NotImplementedError("broadcast() factory not yet implemented")


async def watch[T](initial: T) -> tuple[Sender[T], Receiver[T]]:
    """Create a watch channel that always holds the latest value.

    Receivers can `.borrow()` the current value or `.changed()` to
    wait for updates. Only the most recent message is stored.

    Args:
        initial: Initial value to store and return to new receivers.

    Returns:
        Tuple of (Sender[T], Receiver[T]) for latest-value observation.

    Example:
        ```python
        tx, rx = await watch[int](initial=0)
        await tx.send(42)
        value = await rx.changed()  # waits for next update
        # value == 42
        ```
    """
    raise NotImplementedError("watch() factory not yet implemented")


async def select(*receivers: Receiver[Any], timeout: float | None = None) -> Any:
    """Multiplex multiple receivers, returning the first available message.

    Awaits on all receivers and returns the first message to arrive.
    If timeout expires, raises Timeout.

    Args:
        *receivers: Variable number of Receiver objects to multiplex.
        timeout: Max seconds to wait (None = no timeout).

    Returns:
        The message from whichever receiver got data first.

    Raises:
        TimeoutError: If timeout expires with no messages.

    Example:
        ```python
        tx1, rx1 = await channel[int]()
        tx2, rx2 = await channel[str]()
        msg = await select(rx1, rx2)
        # Returns first message from either rx1 or rx2
        ```
    """
    raise NotImplementedError("select() function not yet implemented")
