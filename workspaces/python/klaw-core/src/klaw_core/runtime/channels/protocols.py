"""Channel protocols: Sender and Receiver abstract interfaces.

Uses PEP 695 type parameter syntax (Python 3.12+) for automatic variance inference.
Type checkers will infer:
- Sender[T] as contravariant (T appears in input positions)
- Receiver[T] as covariant (T appears in output positions)
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, Self

from klaw_core.result import Result
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = ['Receiver', 'ReferenceReceiver', 'ReferenceSender', 'Sender']


class Sender[T](Protocol):
    """Protocol for sending values into a channel.

    Sender is the transmit half of a channel. Multiple senders can exist
    (via `clone()`), enabling multi-producer patterns. When all senders
    are dropped, the channel signals `ChannelClosed` to receivers.

    Type Parameters:
        T: The type of values sent through the channel.
            Variance is inferred by type checkers as contravariant
            (T appears only in input positions).
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
    async def try_send(self, value: T) -> Result[None, ChannelFull | ChannelClosed]:
        """Send a value without blocking.

        Returns `Ok(None)` if queued, or `Err(ChannelFull | ChannelClosed)`.

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
    def clone(self) -> Self:
        """Clone this sender for multi-producer use.

        Returns a new sender that shares the same underlying channel.
        Each clone increments the sender count; dropping all clones
        signals channel closure to receivers.

        This is a synchronous operation: it only increments a reference
        counter and returns immediately (no I/O or waiting involved).

        Returns:
            A new Sender pointing to the same channel.

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


class Receiver[T](Protocol):
    """Protocol for receiving values from a channel.

    Receiver is the receive half of a channel. Multiple receivers can exist
    (via `clone()`), enabling multi-consumer patterns. When all senders
    are dropped, `recv()` returns `Err(ChannelClosed)` after draining.

    Type Parameters:
        T: The type of values received from the channel.
            Variance is inferred by type checkers as covariant
            (T appears only in output positions).
    """

    @abstractmethod
    async def recv(self) -> T:
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
    async def try_recv(self) -> Result[T, ChannelEmpty | ChannelClosed]:
        """Receive the next value without blocking.

        Returns `Ok(value)` if available, or `Err(ChannelEmpty | ChannelClosed)`.

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
    def clone(self) -> Self:
        """Clone this receiver for multi-consumer use.

        Returns a new receiver that shares the same underlying channel.
        Each clone increments the receiver count. All clones receive
        the same messages (MPMC semantics).

        This is a synchronous operation: it only increments a reference
        counter and returns immediately (no I/O or waiting involved).

        Returns:
            A new Receiver pointing to the same channel.

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
    def __aiter__(self) -> AsyncIterator[T]:
        """Iterate over messages as they arrive.

        Enables `async for` syntax. Iteration ends when channel closes
        and queue is drained.

        Returns:
            AsyncIterator yielding T values.

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
    async def __anext__(self) -> T:
        """Get next message for `async for` iteration.

        Called internally by async iteration. Raises `StopAsyncIteration`
        when channel closes and queue is empty.

        Returns:
            The next value from the channel.

        Raises:
            StopAsyncIteration: When iteration ends.
        """
        ...


class ReferenceSender[T](Sender[T], Protocol):
    """Protocol for senders that support batch operations and pass references.

    Type Parameters:
        T: The type of values sent (contravariant, inherited from Sender).
    """

    @abstractmethod
    async def send_batch(self, values: list[T]) -> None:
        """Send multiple values atomically.

        Args:
            values: List of values to send.

        Raises:
            ChannelClosedError: If all receivers have been dropped.
        """
        ...


class ReferenceReceiver[T](Receiver[T], Protocol):
    """Protocol for receivers that support batch operations and receive references.

    Type Parameters:
        T: The type of values received (covariant, inherited from Receiver).
    """

    @abstractmethod
    async def recv_batch(self, max_items: int, timeout: float | None = None) -> list[T]:
        """Receive multiple values in a batch.

        Args:
            max_items: Maximum number of items to receive.
            timeout: Optional timeout in seconds.

        Returns:
            List of received values (may be fewer than max_items).

        Raises:
            ChannelClosedError: If all senders have been dropped and queue is empty.
        """
        ...
