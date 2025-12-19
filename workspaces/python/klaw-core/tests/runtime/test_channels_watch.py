"""Tests for watch channel implementation (4.11).

Tests WatchSender and WatchReceiver with latest-value observation semantics.
Covers borrow, borrow_and_update, changed, close, clone, and async iteration.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from klaw_core import Ok
from klaw_core.runtime.channels import watch
from klaw_core.runtime.errors import ChannelClosed


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    from klaw_core.runtime import init

    init(backend='local', concurrency=4)


class TestWatchBasic:
    """Tests for basic watch channel operations."""

    async def test_initial_value_available_via_borrow(self) -> None:
        """Initial value is immediately available via borrow()."""
        _tx, rx = await watch(initial=42)

        assert rx.borrow() == 42

    async def test_send_updates_value(self) -> None:
        """send() updates the watched value."""
        tx, rx = await watch(initial=0)

        await tx.send(100)

        assert rx.borrow() == 100

    async def test_borrow_does_not_mark_as_seen(self) -> None:
        """borrow() does not affect has_changed() status."""
        tx, rx = await watch(initial=0)

        await tx.send(1)
        assert rx.has_changed() is True

        _ = rx.borrow()
        assert rx.has_changed() is True

    async def test_borrow_and_update_marks_as_seen(self) -> None:
        """borrow_and_update() marks the current version as seen."""
        tx, rx = await watch(initial=0)

        await tx.send(1)
        assert rx.has_changed() is True

        _ = rx.borrow_and_update()
        assert rx.has_changed() is False

    async def test_send_returns_receiver_count(self) -> None:
        """send() returns the number of active receivers."""
        tx, _rx1 = await watch(initial=0)

        count1 = await tx.send(1)
        assert count1 == 1

        _rx2 = tx.subscribe()
        count2 = await tx.send(2)
        assert count2 == 2


class TestWatchChanged:
    """Tests for changed() semantics."""

    async def test_changed_returns_immediately_if_new_value(self) -> None:
        """changed() returns immediately if value changed since last seen."""
        tx, rx = await watch(initial=0)

        await tx.send(1)

        await rx.changed()
        assert rx.borrow() == 1

    async def test_changed_updates_seen_version(self) -> None:
        """changed() marks the new version as seen."""
        tx, rx = await watch(initial=0)

        await tx.send(1)
        await rx.changed()

        assert rx.has_changed() is False

    async def test_changed_waits_for_new_value(self) -> None:
        """changed() blocks until a new value is sent."""
        import anyio

        tx, rx = await watch(initial=0)

        _ = rx.borrow_and_update()

        result = []

        async def sender():
            await anyio.sleep(0.01)
            await tx.send(42)

        async def receiver():
            await rx.changed()
            result.append(rx.borrow())

        async with anyio.create_task_group() as tg:
            tg.start_soon(receiver)
            tg.start_soon(sender)

        assert result == [42]

    async def test_multiple_sends_coalesce(self) -> None:
        """Multiple sends between changed() calls are coalesced."""
        tx, rx = await watch(initial=0)

        await tx.send(1)
        await tx.send(2)
        await tx.send(3)

        await rx.changed()
        assert rx.borrow() == 3
        assert rx.has_changed() is False


class TestWatchMultipleReceivers:
    """Tests for multiple receiver behavior."""

    async def test_all_receivers_see_latest_value(self) -> None:
        """All receivers can observe the latest value."""
        tx, rx1 = await watch(initial=0)
        rx2 = tx.subscribe()

        await tx.send(42)

        assert rx1.borrow() == 42
        assert rx2.borrow() == 42

    async def test_receivers_track_seen_independently(self) -> None:
        """Each receiver tracks its own seen version."""
        tx, rx1 = await watch(initial=0)
        rx2 = tx.subscribe()

        await tx.send(1)

        _ = rx1.borrow_and_update()
        assert rx1.has_changed() is False
        assert rx2.has_changed() is True

    async def test_subscribe_starts_at_current_version(self) -> None:
        """New subscribers start with current version as seen."""
        tx, _rx1 = await watch(initial=0)

        await tx.send(1)

        rx2 = tx.subscribe()
        assert rx2.has_changed() is False
        assert rx2.borrow() == 1

    async def test_resubscribe_starts_fresh(self) -> None:
        """resubscribe() creates receiver at current version."""
        tx, rx1 = await watch(initial=0)

        await tx.send(1)
        await rx1.changed()

        rx2 = rx1.resubscribe()

        await tx.send(2)

        assert rx1.has_changed() is True
        assert rx2.has_changed() is True


class TestWatchClose:
    """Tests for close propagation."""

    async def test_close_sender_signals_receivers(self) -> None:
        """Closing sender causes changed() to raise ChannelClosed."""
        from klaw_core.runtime.errors import ChannelClosedError

        tx, rx = await watch(initial=0)

        _ = rx.borrow_and_update()
        await tx.close()

        with pytest.raises(ChannelClosedError):
            await rx.changed()

    async def test_changed_succeeds_if_new_value_before_close(self) -> None:
        """changed() succeeds if there's a new value even after close."""
        tx, rx = await watch(initial=0)

        await tx.send(42)
        await tx.close()

        await rx.changed()
        assert rx.borrow() == 42

    async def test_borrow_works_after_close(self) -> None:
        """borrow() still works after channel is closed."""
        tx, rx = await watch(initial=42)

        await tx.close()

        assert rx.borrow() == 42

    async def test_close_is_idempotent(self) -> None:
        """Calling close() multiple times is safe."""
        tx, _rx = await watch(initial=0)

        await tx.close()
        await tx.close()

    async def test_all_cloned_senders_must_close(self) -> None:
        """Channel stays open until all sender clones close."""
        from klaw_core.runtime.errors import ChannelClosedError

        tx1, rx = await watch(initial=0)
        tx2 = tx1.clone()

        await tx1.close()

        await tx2.send(42)
        assert rx.borrow() == 42

        await tx2.close()

        _ = rx.borrow_and_update()
        with pytest.raises(ChannelClosedError):
            await rx.changed()


class TestWatchSenderClone:
    """Tests for sender cloning and multi-producer."""

    async def test_clone_creates_independent_sender(self) -> None:
        """Cloned senders can both send values."""
        tx1, rx = await watch(initial=0)
        tx2 = tx1.clone()

        await tx1.send(1)
        assert rx.borrow() == 1

        await tx2.send(2)
        assert rx.borrow() == 2

    async def test_try_send_returns_ok(self) -> None:
        """try_send() returns Ok(rx_count) on success."""
        tx, _rx = await watch(initial=0)

        result = await tx.try_send(42)
        assert result == Ok(1)

    async def test_try_send_returns_closed_when_no_receivers(self) -> None:
        """try_send() returns Err(ChannelClosed) when no receivers."""
        tx, rx = await watch(initial=0)

        rx._state.rx_count = 0

        result = await tx.try_send(42)
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)


class TestWatchAsyncIteration:
    """Tests for async iteration support."""

    async def test_async_for_iteration(self) -> None:
        """Async for iterates over changed values."""
        import anyio

        tx, rx = await watch(initial=0)

        async def sender():
            for i in range(1, 4):
                await tx.send(i)
                await anyio.sleep(0.01)
            await tx.close()

        values: list[int] = []

        async def receiver():
            values.extend([value async for value in rx])

        async with anyio.create_task_group() as tg:
            tg.start_soon(sender)
            tg.start_soon(receiver)

        assert len(values) >= 1
        assert 3 in values

    async def test_iteration_stops_on_close(self) -> None:
        """Iteration stops with StopAsyncIteration when channel closes."""
        tx, rx = await watch(initial=0)

        await tx.send(1)
        await tx.close()

        values = [v async for v in rx]
        assert values == [1]


# --- Hypothesis Property Tests ---


@pytest.mark.hypothesis_property
@given(values=st.lists(st.integers(min_value=-1000, max_value=1000), min_size=1, max_size=50))
async def test_property_last_value_always_available(values: list[int]) -> None:
    """Property: The last sent value is always available via borrow()."""
    tx, rx = await watch(initial=0)

    for v in values:
        await tx.send(v)

    assert rx.borrow() == values[-1]


@pytest.mark.hypothesis_property
@given(values=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=30))
async def test_property_all_receivers_see_same_value(values: list[str]) -> None:
    """Property: All receivers see the same latest value."""
    tx, rx1 = await watch(initial='')
    rx2 = tx.subscribe()
    rx3 = tx.subscribe()

    for v in values:
        await tx.send(v)

    expected = values[-1]
    assert rx1.borrow() == expected
    assert rx2.borrow() == expected
    assert rx3.borrow() == expected


@pytest.mark.hypothesis_property
@given(
    initial=st.integers(),
    updates=st.lists(st.integers(), min_size=0, max_size=20),
)
async def test_property_version_increments_monotonically(initial: int, updates: list[int]) -> None:
    """Property: Version increments with each send."""
    tx, rx = await watch(initial=initial)

    versions_seen = [rx._state.version]

    for v in updates:
        await tx.send(v)
        versions_seen.append(rx._state.version)

    for i in range(1, len(versions_seen)):
        assert versions_seen[i] == versions_seen[i - 1] + 1


@pytest.mark.hypothesis_property
@given(
    initial=st.integers(),
    value=st.integers(),
)
async def test_property_changed_detects_any_update(initial: int, value: int) -> None:
    """Property: changed() detects updates regardless of value."""
    tx, rx = await watch(initial=initial)

    _ = rx.borrow_and_update()
    assert rx.has_changed() is False

    await tx.send(value)
    assert rx.has_changed() is True

    await rx.changed()
    assert rx.has_changed() is False
