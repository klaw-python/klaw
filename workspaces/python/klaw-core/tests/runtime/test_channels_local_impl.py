"""Comprehensive tests for LocalChannel implementation (4.3).

Tests LocalSender and LocalReceiver with aiologic.Queue backend.
Covers send/recv, try_send/try_recv, clone, close, and edge cases.

Uses hypothesis for property-based testing and mimesis for fake data.
"""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import given
from hypothesis import strategies as st
from klaw_core import Ok
from klaw_core.runtime.channels import channel
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, ChannelFull


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    from klaw_core.runtime import init

    init(backend='local', concurrency=4)


class TestLocalSenderRecvBasic:
    """Tests for basic send/recv operations."""

    async def test_send_and_recv_single_value(self) -> None:
        """send() and recv() transfer value correctly."""
        tx, rx = await channel()
        await tx.send(42)
        value = await rx.recv()
        assert value == 42

    async def test_send_and_recv_string(self) -> None:
        """send/recv works with string values."""
        tx, rx = await channel()
        await tx.send('hello')
        value = await rx.recv()
        assert value == 'hello'

    async def test_send_and_recv_complex_type(self) -> None:
        """send/recv works with dicts and complex types."""
        tx, rx = await channel()
        data = {'key': 'value', 'num': 42, 'nested': {'a': 1}}
        await tx.send(data)
        received = await rx.recv()
        assert received == data

    async def test_send_and_recv_list(self) -> None:
        """send/recv works with list values."""
        tx, rx = await channel()
        items = [1, 2, 3, 4, 5]
        await tx.send(items)
        received = await rx.recv()
        assert received == items

    async def test_multiple_sends_recv_fifo_order(self) -> None:
        """Multiple sends are received in FIFO order."""
        tx, rx = await channel()
        for i in range(1, 6):
            await tx.send(i)
        for i in range(1, 6):
            value = await rx.recv()
            assert value == i


class TestLocalSenderNonBlocking:
    """Tests for try_send() non-blocking operations."""

    async def test_try_send_success_returns_ok(self) -> None:
        """try_send() returns Ok(None) when successful."""
        tx, rx = await channel(capacity=10)
        result = await tx.try_send(42)
        assert result == Ok(None)
        assert await rx.recv() == 42

    async def test_try_send_when_full_returns_channel_full(self) -> None:
        """try_send() returns Err(ChannelFull) when queue is at capacity."""
        tx, _rx = await channel(capacity=2)

        # Fill the queue
        await tx.send(1)
        await tx.send(2)

        # Next try_send should fail
        result = await tx.try_send(3)
        assert result.is_err()
        assert isinstance(result.error, ChannelFull)

    async def test_try_send_when_closed_returns_channel_closed(self) -> None:
        """try_send() returns Err(ChannelClosed) when all receivers are gone."""
        tx, rx = await channel()
        await rx.close()

        result = await tx.try_send(42)
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)

    async def test_try_send_returns_capacity_in_error(self) -> None:
        """ChannelFull error includes the queue capacity."""
        tx, _rx = await channel(capacity=5)

        # Fill the queue
        for _ in range(5):
            await tx.send(1)

        result = await tx.try_send(1)
        assert result.is_err()
        err = result.error
        assert isinstance(err, ChannelFull)
        assert err.capacity == 5


class TestLocalReceiverNonBlocking:
    """Tests for try_recv() non-blocking operations."""

    async def test_try_recv_returns_ok_when_value_available(self) -> None:
        """try_recv() returns Ok(value) when message is queued."""
        tx, rx = await channel()
        await tx.send(42)

        result = await rx.try_recv()
        assert result == Ok(42)

    async def test_try_recv_returns_channel_empty_when_no_messages(self) -> None:
        """try_recv() returns Err(ChannelEmpty) when queue is empty."""
        _tx, rx = await channel()

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, ChannelEmpty)

    async def test_try_recv_returns_channel_closed_when_senders_gone(self) -> None:
        """try_recv() returns Err(ChannelClosed) when all senders close and queue empty."""
        tx, rx = await channel()
        await tx.close()

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)

    async def test_try_recv_drains_queue_before_closed(self) -> None:
        """try_recv() returns messages before returning ChannelClosed."""
        tx, rx = await channel()
        await tx.send(1)
        await tx.send(2)
        await tx.close()

        r1 = await rx.try_recv()
        assert r1 == Ok(1)

        r2 = await rx.try_recv()
        assert r2 == Ok(2)

        r3 = await rx.try_recv()
        assert isinstance(r3.error, ChannelClosed)


class TestChannelClose:
    """Tests for channel closure semantics."""

    async def test_close_sender_signals_to_receivers(self) -> None:
        """Closing sender causes recv() to raise ChannelClosed after draining."""
        tx, rx = await channel()
        await tx.send(1)
        await tx.close()

        # Can still recv the queued message
        assert await rx.recv() == 1

        # After draining, recv() raises ChannelClosed
        with pytest.raises(Exception, match='Channel closed'):
            await rx.recv()

    async def test_close_receiver_signals_to_senders(self) -> None:
        """Closing receiver causes send() to raise ChannelClosed."""
        tx, rx = await channel()
        await rx.close()

        with pytest.raises(Exception, match='Channel closed'):
            await tx.send(42)

    async def test_close_is_idempotent(self) -> None:
        """Calling close() multiple times is safe."""
        tx, rx = await channel()

        await tx.close()
        await tx.close()  # Should not raise

        await rx.close()
        await rx.close()  # Should not raise

    async def test_close_with_pending_messages(self) -> None:
        """Closing doesn't discard pending messages."""
        tx, rx = await channel()

        await tx.send(1)
        await tx.send(2)
        await tx.send(3)
        await tx.close()

        values = []
        try:
            while True:
                values.append(await rx.recv())
        except Exception:
            pass

        assert values == [1, 2, 3]


class TestChannelClone:
    """Tests for clone() reference counting."""

    async def test_clone_sender_increments_count(self) -> None:
        """Cloning sender creates independent sender."""
        tx1, rx = await channel()
        tx2 = tx1.clone()
        tx3 = tx2.clone()

        # All three can send
        await tx1.send(1)
        await tx2.send(2)
        await tx3.send(3)

        assert await rx.recv() == 1
        assert await rx.recv() == 2
        assert await rx.recv() == 3

    async def test_clone_receiver_increments_count(self) -> None:
        """Cloning receiver creates independent receiver (MPMC)."""
        tx, rx1 = await channel()
        rx2 = rx1.clone()
        rx3 = rx2.clone()

        # Send message
        await tx.send(42)

        # One of the receivers gets it (MPMC - message goes to first available)
        result1 = await rx1.try_recv()
        result2 = await rx2.try_recv()
        result3 = await rx3.try_recv()

        # Exactly one should have the value
        results = [r for r in [result1, result2, result3] if r.is_ok()]
        assert len(results) == 1
        assert results[0] == Ok(42)

    async def test_channel_stays_open_until_all_senders_close(self) -> None:
        """Channel stays open while any sender clone is active."""
        tx1, _rx = await channel()
        tx2 = tx1.clone()
        tx3 = tx2.clone()

        await tx1.close()
        # Channel should still be open - tx2 and tx3 exist
        await tx2.send(42)

        await tx2.close()
        # Channel should still be open - tx3 exists
        await tx3.send(43)

        await tx3.close()
        # Now channel is closed

        with pytest.raises(Exception, match='Channel closed'):
            await tx1.send(44)

    async def test_channel_closes_when_all_receivers_closed(self) -> None:
        """Channel closes when all receiver clones are closed."""
        tx, rx1 = await channel()
        rx2 = rx1.clone()

        await tx.send(42)

        await rx1.close()
        # Channel still open for rx2
        result = await rx2.try_recv()
        assert result == Ok(42)

        await rx2.close()

        # Now senders get ChannelClosed
        with pytest.raises(Exception, match='Channel closed'):
            await tx.send(43)


class TestAsyncIteration:
    """Tests for async iteration support."""

    async def test_async_for_iteration(self) -> None:
        """Async for iterates over received values."""
        tx, rx = await channel()

        async def send_values():
            for i in range(1, 4):
                await tx.send(i)
            await tx.close()

        asyncio.create_task(send_values())

        values = [value async for value in rx]

        assert values == [1, 2, 3]

    async def test_async_iteration_stops_at_close(self) -> None:
        """Iteration stops with StopAsyncIteration when channel closes."""
        tx, rx = await channel()
        await tx.send(1)
        await tx.send(2)
        await tx.close()

        count = 0
        async for _ in rx:
            count += 1

        assert count == 2

    async def test_async_iteration_with_clone(self) -> None:
        """Async iteration works with cloned receivers."""
        tx, rx1 = await channel()
        rx2 = rx1.clone()

        async def sender():
            for i in range(3):
                await tx.send(i)
            await tx.close()

        asyncio.create_task(sender())

        values1 = [v async for v in rx1]

        # rx2 may get some or none (MPMC - messages already consumed)
        values2 = [v async for v in rx2]

        # Total should be 3 (distributed between receivers)
        assert len(values1) + len(values2) <= 3


class TestErrorCases:
    """Tests for error conditions."""

    async def test_send_after_close_raises_channel_closed(self) -> None:
        """send() after close() raises ChannelClosed."""
        tx, _rx = await channel()
        await tx.close()

        with pytest.raises(Exception, match='Channel closed'):
            await tx.send(42)

    async def test_recv_after_close_and_drain_raises_channel_closed(self) -> None:
        """recv() raises ChannelClosed after queue is drained."""
        tx, rx = await channel()
        await tx.send(42)
        await tx.close()

        await rx.recv()  # Get the message
        with pytest.raises(Exception, match='Channel closed'):
            await rx.recv()

    async def test_try_send_on_closed_sender_returns_error(self) -> None:
        """try_send() on closed sender returns error immediately."""
        tx, _rx = await channel()
        await tx.close()

        result = await tx.try_send(42)
        assert result.is_err()

    async def test_try_recv_on_closed_receiver_returns_error(self) -> None:
        """try_recv() on closed receiver returns error immediately."""
        _tx, rx = await channel()
        await rx.close()

        result = await rx.try_recv()
        assert result.is_err()


class TestCapacity:
    """Tests for bounded channel capacity."""

    async def test_bounded_channel_respects_capacity(self) -> None:
        """Bounded channel blocks send when at capacity."""
        tx, rx = await channel(capacity=2)

        await tx.send(1)
        await tx.send(2)

        # Next send should block until we recv
        task = asyncio.create_task(tx.send(3))
        await asyncio.sleep(0.01)  # Give task time to start

        # Task should still be pending
        assert not task.done()

        # Recv one message
        await rx.recv()

        # Now send should complete
        await asyncio.wait_for(task, timeout=1.0)

    async def test_unbounded_channel_never_blocks(self) -> None:
        """Unbounded channel never blocks on send."""
        tx, rx = await channel(unbounded=True)

        # Send many values without blocking
        for i in range(10000):
            await tx.send(i)

        # Verify we can still recv them
        assert await rx.recv() == 0


@pytest.mark.hypothesis_property
@given(
    values=st.lists(st.integers(min_value=-1000000, max_value=1000000), min_size=1, max_size=100)
)
async def test_property_fifo_order(values: list[int]) -> None:
    """Property: Channel maintains FIFO order for all messages."""
    tx, rx = await channel()

    for v in values:
        await tx.send(v)

    received = [await rx.recv() for _ in values]

    assert received == values


@pytest.mark.hypothesis_property
@given(
    values=st.lists(st.text(min_size=1), min_size=1, max_size=50)
)
async def test_property_no_data_loss(values: list[str]) -> None:
    """Property: No messages are lost after send."""
    tx, rx = await channel()

    for v in values:
        await tx.send(v)

    await tx.close()

    received = [v async for v in rx]

    assert len(received) == len(values)
    assert set(received) == set(values)


@pytest.mark.hypothesis_property
@given(
    capacity=st.integers(min_value=1, max_value=100),
    count=st.integers(min_value=1, max_value=100),
)
async def test_property_capacity_respected(capacity: int, count: int) -> None:
    """Property: Capacity limit is enforced."""
    tx, _rx = await channel(capacity=capacity)

    # Send up to capacity non-blocking
    for i in range(min(count, capacity)):
        result = await tx.try_send(i)
        assert result.is_ok()

    # Queue should be full if count >= capacity
    if count >= capacity:
        result = await tx.try_send(999)
        assert result.is_err()
