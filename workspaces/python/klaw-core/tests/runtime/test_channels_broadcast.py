"""Tests for broadcast channel implementation (4.10).

Tests BroadcastSender and BroadcastReceiver with fan-out semantics.
Covers send/recv, lagging, late subscribe, close, clone, and async iteration.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from klaw_core import Ok
from klaw_core.runtime.channels import broadcast
from klaw_core.runtime.errors import ChannelClosed, ChannelEmpty, Lagged


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    from klaw_core.runtime import init

    init(backend='local', concurrency=4)


class TestBroadcastFanOut:
    """Tests for fan-out semantics: all receivers get all messages."""

    async def test_single_receiver_gets_all_messages(self) -> None:
        """Single receiver receives all sent messages."""
        tx, rx = await broadcast(capacity=16)

        await tx.send(1)
        await tx.send(2)
        await tx.send(3)

        assert await rx.recv() == 1
        assert await rx.recv() == 2
        assert await rx.recv() == 3

    async def test_two_receivers_both_get_all_messages(self) -> None:
        """Two receivers each get all messages independently."""
        tx, rx1 = await broadcast(capacity=16)
        rx2 = tx.subscribe()

        await tx.send(10)
        await tx.send(20)

        assert await rx1.recv() == 10
        assert await rx1.recv() == 20

        assert await rx2.recv() == 10
        assert await rx2.recv() == 20

    async def test_multiple_receivers_all_get_same_messages(self) -> None:
        """Multiple receivers all get the same messages."""
        tx, rx1 = await broadcast(capacity=16)
        rx2 = tx.subscribe()
        rx3 = tx.subscribe()

        await tx.send('hello')
        await tx.send('world')

        for rx in [rx1, rx2, rx3]:
            assert await rx.recv() == 'hello'
            assert await rx.recv() == 'world'

    async def test_receivers_can_read_at_different_speeds(self) -> None:
        """Receivers can consume messages at different rates."""
        tx, rx_fast = await broadcast(capacity=16)
        rx_slow = tx.subscribe()

        await tx.send(1)
        await tx.send(2)
        await tx.send(3)

        assert await rx_fast.recv() == 1
        assert await rx_fast.recv() == 2
        assert await rx_fast.recv() == 3

        assert await rx_slow.recv() == 1

        await tx.send(4)

        assert await rx_slow.recv() == 2
        assert await rx_fast.recv() == 4

    async def test_send_returns_receiver_count(self) -> None:
        """send() returns the number of active receivers."""
        tx, _rx1 = await broadcast(capacity=16)

        count1 = await tx.send(1)
        assert count1 == 1

        _rx2 = tx.subscribe()
        count2 = await tx.send(2)
        assert count2 == 2

        _rx3 = tx.subscribe()
        count3 = await tx.send(3)
        assert count3 == 3


class TestBroadcastLagging:
    """Tests for lagging detection and cursor advancement."""

    async def test_lagging_raises_error_with_skipped_count(self) -> None:
        """Receiver that falls behind gets LaggedError with skip count."""
        from klaw_core.runtime.errors import LaggedError

        tx, rx = await broadcast(capacity=4)

        for i in range(10):
            await tx.send(i)

        with pytest.raises(LaggedError) as exc_info:
            await rx.recv()

        assert exc_info.value.skipped > 0

    async def test_lagging_advances_cursor_to_oldest(self) -> None:
        """After lagging, cursor advances to oldest available message."""
        from klaw_core.runtime.errors import LaggedError

        tx, rx = await broadcast(capacity=4)

        for i in range(8):
            await tx.send(i)

        try:
            await rx.recv()
        except LaggedError:
            pass

        value = await rx.recv()
        assert value >= 4

    async def test_try_recv_returns_lagged_error(self) -> None:
        """try_recv() returns Err(Lagged) when behind."""
        tx, rx = await broadcast(capacity=4)

        for i in range(10):
            await tx.send(i)

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, Lagged)

    async def test_async_iteration_skips_lagged_messages(self) -> None:
        """Async iteration automatically skips lagged messages."""
        tx, rx = await broadcast(capacity=4)

        for i in range(10):
            await tx.send(i)

        await tx.close()

        values = [v async for v in rx]
        assert len(values) <= 4
        assert all(v >= 6 for v in values)


class TestBroadcastLateSubscribe:
    """Tests for late subscription behavior."""

    async def test_late_subscriber_gets_no_backlog(self) -> None:
        """Subscriber created after send() doesn't get old messages."""
        tx, _rx1 = await broadcast(capacity=16)

        await tx.send(1)
        await tx.send(2)

        rx2 = tx.subscribe()

        await tx.send(3)

        result = await rx2.try_recv()
        assert result == Ok(3)

    async def test_resubscribe_starts_fresh(self) -> None:
        """resubscribe() creates receiver at current tail."""
        tx, rx1 = await broadcast(capacity=16)

        await tx.send(1)
        await tx.send(2)

        rx2 = rx1.resubscribe()

        await tx.send(3)

        assert await rx1.recv() == 1
        assert await rx2.recv() == 3


class TestBroadcastClose:
    """Tests for close propagation."""

    async def test_close_sender_signals_receivers(self) -> None:
        """Closing sender causes recv() to raise ChannelClosed."""
        from klaw_core.runtime.errors import ChannelClosedError

        tx, rx = await broadcast(capacity=16)

        await tx.send(1)
        await tx.close()

        assert await rx.recv() == 1

        with pytest.raises(ChannelClosedError):
            await rx.recv()

    async def test_try_recv_returns_closed_when_empty_and_closed(self) -> None:
        """try_recv() returns Err(ChannelClosed) when closed and empty."""
        tx, rx = await broadcast(capacity=16)

        await tx.close()

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)

    async def test_try_recv_returns_empty_when_open(self) -> None:
        """try_recv() returns Err(ChannelEmpty) when open but empty."""
        _tx, rx = await broadcast(capacity=16)

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, ChannelEmpty)

    async def test_close_is_idempotent(self) -> None:
        """Calling close() multiple times is safe."""
        tx, _rx = await broadcast(capacity=16)

        await tx.close()
        await tx.close()

    async def test_all_cloned_senders_must_close(self) -> None:
        """Channel stays open until all sender clones close."""
        tx1, rx = await broadcast(capacity=16)
        tx2 = tx1.clone()

        await tx1.close()

        await tx2.send(42)
        assert await rx.recv() == 42

        await tx2.close()

        result = await rx.try_recv()
        assert isinstance(result.error, ChannelClosed)


class TestBroadcastSenderClone:
    """Tests for sender cloning and multi-producer."""

    async def test_clone_creates_independent_sender(self) -> None:
        """Cloned senders can both send messages."""
        tx1, rx = await broadcast(capacity=16)
        tx2 = tx1.clone()

        await tx1.send(1)
        await tx2.send(2)

        assert await rx.recv() == 1
        assert await rx.recv() == 2

    async def test_try_send_returns_ok(self) -> None:
        """try_send() returns Ok(rx_count) on success."""
        tx, _rx = await broadcast(capacity=16)

        result = await tx.try_send(42)
        assert result == Ok(1)

    async def test_try_send_returns_closed_when_no_receivers(self) -> None:
        """try_send() returns Err(ChannelClosed) when no receivers."""
        tx, rx = await broadcast(capacity=16)

        rx._state.rx_count = 0

        result = await tx.try_send(42)
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)


# --- Hypothesis Property Tests ---


@pytest.mark.hypothesis_property
@given(values=st.lists(st.integers(min_value=-1000, max_value=1000), min_size=1, max_size=50))
async def test_property_all_receivers_get_all_messages(values: list[int]) -> None:
    """Property: Every receiver gets every message sent after subscription."""
    tx, rx1 = await broadcast(capacity=64)
    rx2 = tx.subscribe()

    for v in values:
        await tx.send(v)

    received1 = [await rx1.recv() for _ in values]
    received2 = [await rx2.recv() for _ in values]

    assert received1 == values
    assert received2 == values


@pytest.mark.hypothesis_property
@given(values=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=30))
async def test_property_fifo_order_preserved(values: list[str]) -> None:
    """Property: Messages are received in FIFO order."""
    tx, rx = await broadcast(capacity=64)

    for v in values:
        await tx.send(v)

    received = [await rx.recv() for _ in values]
    assert received == values


@pytest.mark.hypothesis_property
@given(
    capacity_power=st.integers(min_value=1, max_value=4),
    overflow=st.integers(min_value=1, max_value=32),
)
async def test_property_lagging_detected_when_overflowed(capacity_power: int, overflow: int) -> None:
    """Property: Lagging is detected when buffer overflows."""
    from klaw_core.runtime.errors import LaggedError

    capacity = 2**capacity_power
    tx, rx = await broadcast(capacity=capacity)

    total = capacity + overflow
    for i in range(total):
        await tx.send(i)

    try:
        await rx.recv()
        lagged = False
    except LaggedError:
        lagged = True

    assert lagged, f'Expected lagging with capacity={capacity}, sent={total}'


@pytest.mark.hypothesis_property
@given(
    pre_values=st.lists(st.integers(), min_size=0, max_size=10),
    post_values=st.lists(st.integers(), min_size=1, max_size=10),
)
async def test_property_late_subscriber_only_gets_new_messages(pre_values: list[int], post_values: list[int]) -> None:
    """Property: Late subscribers only receive messages sent after subscription."""
    tx, _rx1 = await broadcast(capacity=64)

    for v in pre_values:
        await tx.send(v)

    rx2 = tx.subscribe()

    for v in post_values:
        await tx.send(v)

    received = [await rx2.recv() for _ in post_values]
    assert received == post_values
