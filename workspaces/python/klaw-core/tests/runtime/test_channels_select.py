"""Tests for select() multiplexing function.

Tests basic functionality, timeout, biased selection, edge cases,
cancellation safety, and property-based tests.
"""

from __future__ import annotations

import asyncio

import anyio
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from klaw_core.runtime.channels import channel, select
from klaw_core.runtime.errors import ChannelClosedError, NoReceiversError


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    from klaw_core.runtime import init

    init(backend='local', concurrency=4)


class TestSelectBasic:
    """Tests for basic select() functionality."""

    async def test_select_single_receiver_with_buffered_value(self) -> None:
        """select() returns immediately when receiver has buffered value."""
        tx, rx = await channel()
        await tx.send(42)

        idx, value = await select(rx)

        assert idx == 0
        assert value == 42

    async def test_select_returns_tuple_of_index_and_value(self) -> None:
        """select() returns (index, value) tuple."""
        tx, rx = await channel()
        await tx.send('hello')

        result = await select(rx)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == 0
        assert result[1] == 'hello'

    async def test_select_multiple_receivers_one_ready(self) -> None:
        """select() returns ready receiver's index when one has data."""
        _tx1, rx1 = await channel()
        tx2, rx2 = await channel()
        _tx3, rx3 = await channel()

        await tx2.send('from_rx2')

        idx, value = await select(rx1, rx2, rx3)

        assert idx == 1
        assert value == 'from_rx2'

    async def test_select_multiple_receivers_first_ready(self) -> None:
        """select() with biased=True returns first ready receiver."""
        tx1, rx1 = await channel()
        tx2, rx2 = await channel()

        await tx1.send('first')
        await tx2.send('second')

        idx, value = await select(rx1, rx2, biased=True)

        assert idx == 0
        assert value == 'first'

    async def test_select_complex_types(self) -> None:
        """select() works with complex value types."""
        tx, rx = await channel()
        data = {'key': 'value', 'nested': [1, 2, 3]}
        await tx.send(data)

        idx, value = await select(rx)

        assert idx == 0
        assert value == data


class TestSelectSlowPath:
    """Tests for slow-path concurrent waiting."""

    async def test_select_waits_for_value(self) -> None:
        """select() waits when no receiver has immediate value."""
        tx, rx = await channel()

        async def send_later():
            await asyncio.sleep(0.01)
            await tx.send(42)

        asyncio.create_task(send_later())

        idx, value = await select(rx)

        assert idx == 0
        assert value == 42

    async def test_select_returns_first_to_complete(self) -> None:
        """select() returns whichever receiver gets value first."""
        _tx1, rx1 = await channel()
        tx2, rx2 = await channel()

        async def send_to_rx2():
            await asyncio.sleep(0.01)
            await tx2.send('from_rx2')

        asyncio.create_task(send_to_rx2())

        idx, value = await select(rx1, rx2)

        assert idx == 1
        assert value == 'from_rx2'

    async def test_select_cancels_losing_tasks(self) -> None:
        """select() cancels other recv tasks when one wins."""
        tx1, rx1 = await channel()
        tx2, rx2 = await channel()

        async def send_to_rx1():
            await asyncio.sleep(0.01)
            await tx1.send('winner')

        asyncio.create_task(send_to_rx1())

        idx, value = await select(rx1, rx2)

        assert idx == 0
        assert value == 'winner'

        await tx2.send('for_rx2')
        result = await rx2.try_recv()
        assert result.is_ok()
        assert result.value == 'for_rx2'


class TestSelectTimeout:
    """Tests for timeout parameter."""

    async def test_select_with_timeout_returns_before_expiry(self) -> None:
        """select() returns value if received before timeout."""
        tx, rx = await channel()
        await tx.send(42)

        idx, value = await select(rx, timeout=1.0)

        assert idx == 0
        assert value == 42

    async def test_select_timeout_raises_timeout_error(self) -> None:
        """select() raises TimeoutError when timeout expires."""
        _tx, rx = await channel()

        with pytest.raises(TimeoutError):
            await select(rx, timeout=0.01)

    async def test_select_timeout_cancels_pending_tasks(self) -> None:
        """select() cancels pending recv tasks on timeout."""
        tx, rx = await channel()

        with pytest.raises(TimeoutError):
            await select(rx, timeout=0.01)

        await tx.send(42)
        result = await rx.try_recv()
        assert result.is_ok()
        assert result.value == 42


class TestSelectBiased:
    """Tests for biased parameter."""

    async def test_select_biased_true_prefers_lower_index(self) -> None:
        """select(biased=True) prefers lower indices when multiple ready."""
        tx1, rx1 = await channel()
        tx2, rx2 = await channel()
        tx3, rx3 = await channel()

        await tx1.send('first')
        await tx2.send('second')
        await tx3.send('third')

        idx, value = await select(rx1, rx2, rx3, biased=True)

        assert idx == 0
        assert value == 'first'

    async def test_select_biased_true_consistent(self) -> None:
        """select(biased=True) consistently picks lowest ready index."""
        for _ in range(10):
            tx1, rx1 = await channel()
            tx2, rx2 = await channel()

            await tx1.send('a')
            await tx2.send('b')

            idx, _ = await select(rx1, rx2, biased=True)
            assert idx == 0

    async def test_select_biased_false_is_fair(self) -> None:
        """select(biased=False) distributes across ready receivers."""
        indices = []

        for _ in range(50):
            tx1, rx1 = await channel()
            tx2, rx2 = await channel()

            await tx1.send('a')
            await tx2.send('b')

            idx, _ = await select(rx1, rx2, biased=False)
            indices.append(idx)

        assert 0 in indices
        assert 1 in indices


class TestSelectEdgeCases:
    """Tests for edge cases and error conditions."""

    async def test_select_no_receivers_raises_error(self) -> None:
        """select() with no receivers raises NoReceiversError."""
        with pytest.raises(NoReceiversError):
            await select()

    async def test_select_all_closed_raises_channel_closed(self) -> None:
        """select() raises ChannelClosedError when all receivers are closed."""
        tx1, rx1 = await channel()
        tx2, rx2 = await channel()

        await tx1.close()
        await tx2.close()

        with pytest.raises(ChannelClosedError):
            await select(rx1, rx2)

    async def test_select_one_closed_one_open_returns_open(self) -> None:
        """select() returns from open receiver when one is closed."""
        tx1, rx1 = await channel()
        tx2, rx2 = await channel()

        await tx1.close()
        await tx2.send('from_open')

        idx, value = await select(rx1, rx2)

        assert idx == 1
        assert value == 'from_open'

    async def test_select_mixed_types(self) -> None:
        """select() works with receivers of different value types."""
        _tx_int, rx_int = await channel()
        tx_str, rx_str = await channel()

        await tx_str.send('hello')

        idx, value = await select(rx_int, rx_str)

        assert idx == 1
        assert value == 'hello'
        assert isinstance(value, str)


class TestSelectCancellation:
    """Tests for cancellation safety."""

    async def test_select_can_be_cancelled(self) -> None:
        """select() can be cancelled without leaking tasks."""
        _tx, rx = await channel()

        async def run_select():
            await select(rx)

        task = asyncio.create_task(run_select())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_select_cancellation_in_slow_path_does_not_consume(self) -> None:
        """Cancelled select() in slow-path does not consume messages sent after."""
        tx, rx = await channel()

        async def run_select():
            with anyio.move_on_after(0.01):
                await select(rx)

        await run_select()

        await tx.send(42)
        result = await rx.try_recv()
        assert result.is_ok()
        assert result.value == 42

    async def test_select_no_leaked_tasks_after_completion(self) -> None:
        """select() does not leak tasks after normal completion."""
        tx1, rx1 = await channel()
        tx2, rx2 = await channel()

        await tx1.send(42)

        await select(rx1, rx2)

        await tx2.send('after')
        result = await rx2.try_recv()
        assert result.is_ok()


# --- Property-based tests ---


@pytest.mark.hypothesis_property
@given(
    num_receivers=st.integers(min_value=1, max_value=10),
    ready_index=st.integers(min_value=0, max_value=9),
)
@settings(max_examples=50)
async def test_property_index_always_valid(num_receivers: int, ready_index: int) -> None:
    """Property: Returned index is always in [0, len(receivers))."""
    ready_index %= num_receivers

    receivers = []
    senders = []
    for _ in range(num_receivers):
        tx, rx = await channel()
        senders.append(tx)
        receivers.append(rx)

    await senders[ready_index].send(42)

    idx, value = await select(*receivers)

    assert 0 <= idx < num_receivers
    assert idx == ready_index
    assert value == 42


@pytest.mark.hypothesis_property
@given(values=st.lists(st.integers(min_value=-1000, max_value=1000), min_size=1, max_size=20))
@settings(max_examples=30)
async def test_property_no_data_loss(values: list[int]) -> None:
    """Property: Value returned by select matches exactly one sent value."""
    tx, rx = await channel()

    for v in values:
        await tx.send(v)

    idx, value = await select(rx)

    assert idx == 0
    assert value == values[0]

    remaining = [await rx.recv() for _ in range(len(values) - 1)]
    assert remaining == values[1:]


@pytest.mark.hypothesis_property
@given(
    num_receivers=st.integers(min_value=2, max_value=5),
    iterations=st.integers(min_value=20, max_value=50),
)
@settings(max_examples=10)
async def test_property_biased_always_picks_lowest(num_receivers: int, iterations: int) -> None:
    """Property: biased=True always picks lowest ready index."""
    for _ in range(iterations):
        receivers = []
        senders = []
        for _ in range(num_receivers):
            tx, rx = await channel()
            senders.append(tx)
            receivers.append(rx)

        for tx in senders:
            await tx.send('ready')

        idx, _ = await select(*receivers, biased=True)

        assert idx == 0


@pytest.mark.hypothesis_property
@given(
    iterations=st.integers(min_value=30, max_value=100),
)
@settings(max_examples=5)
async def test_property_unbiased_is_fair(iterations: int) -> None:
    """Property: biased=False distributes across indices over many runs."""
    indices_seen: set[int] = set()

    for _ in range(iterations):
        tx1, rx1 = await channel()
        tx2, rx2 = await channel()
        tx3, rx3 = await channel()

        await tx1.send('a')
        await tx2.send('b')
        await tx3.send('c')

        idx, _ = await select(rx1, rx2, rx3, biased=False)
        indices_seen.add(idx)

    assert len(indices_seen) >= 2


@pytest.mark.hypothesis_property
@given(
    value=st.one_of(
        st.integers(),
        st.text(min_size=1, max_size=50),
        st.lists(st.integers(), min_size=1, max_size=10),
    )
)
@settings(max_examples=30)
async def test_property_value_preserved(value: int | str | list[int]) -> None:
    """Property: Value returned by select is identical to value sent."""
    tx, rx = await channel()
    await tx.send(value)

    idx, received = await select(rx)

    assert idx == 0
    assert received == value
