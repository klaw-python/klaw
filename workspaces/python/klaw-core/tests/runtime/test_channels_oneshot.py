"""Tests for oneshot channel implementation (4.9).

Tests OneshotSender and OneshotReceiver: single-value, single-use semantics.
"""

from __future__ import annotations

import asyncio

import pytest
from klaw_core import Ok
from klaw_core.runtime.channels import oneshot
from klaw_core.runtime.errors import AlreadySent, ChannelClosed, ChannelEmpty


@pytest.fixture(autouse=True)
def setup_runtime() -> None:
    """Initialize runtime before each test."""
    from klaw_core.runtime import init

    init(backend='local', concurrency=4)


class TestOneshotBasic:
    """Tests for basic oneshot send/recv."""

    async def test_send_and_recv_single_value(self) -> None:
        """send() and recv() transfer value correctly."""
        tx, rx = await oneshot()
        await tx.send(42)
        value = await rx.recv()
        assert value == 42

    async def test_send_and_recv_string(self) -> None:
        """send/recv works with string values."""
        tx, rx = await oneshot()
        await tx.send('hello')
        value = await rx.recv()
        assert value == 'hello'

    async def test_send_and_recv_complex_type(self) -> None:
        """send/recv works with dicts and complex types."""
        tx, rx = await oneshot()
        data = {'key': 'value', 'num': 42}
        await tx.send(data)
        received = await rx.recv()
        assert received == data

    async def test_recv_blocks_until_send(self) -> None:
        """recv() blocks until send() is called."""
        tx, rx = await oneshot()

        async def delayed_send():
            await asyncio.sleep(0.01)
            await tx.send(42)

        asyncio.create_task(delayed_send())
        value = await rx.recv()
        assert value == 42


class TestOneshotSenderErrors:
    """Tests for sender error conditions."""

    async def test_send_twice_raises_already_sent(self) -> None:
        """Second send() raises AlreadySentError."""
        tx, _rx = await oneshot()
        await tx.send(1)

        with pytest.raises(Exception, match='already sent'):
            await tx.send(2)

    async def test_send_after_close_raises_channel_closed(self) -> None:
        """send() after close() raises ChannelClosedError."""
        tx, _rx = await oneshot()
        await tx.close()

        with pytest.raises(Exception, match='Channel closed'):
            await tx.send(42)

    async def test_try_send_success_returns_ok(self) -> None:
        """try_send() returns Ok(None) on success."""
        tx, rx = await oneshot()
        result = await tx.try_send(42)
        assert result == Ok(None)
        assert await rx.recv() == 42

    async def test_try_send_twice_returns_already_sent(self) -> None:
        """Second try_send() returns Err(AlreadySent)."""
        tx, _rx = await oneshot()
        await tx.try_send(1)

        result = await tx.try_send(2)
        assert result.is_err()
        assert isinstance(result.error, AlreadySent)

    async def test_try_send_after_close_returns_channel_closed(self) -> None:
        """try_send() after close() returns Err(ChannelClosed)."""
        tx, _rx = await oneshot()
        await tx.close()

        result = await tx.try_send(42)
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)

    async def test_clone_raises_not_implemented(self) -> None:
        """clone() raises NotImplementedError."""
        tx, _rx = await oneshot()

        with pytest.raises(NotImplementedError, match='do not support cloning'):
            tx.clone()


class TestOneshotReceiverErrors:
    """Tests for receiver error conditions."""

    async def test_recv_twice_raises_channel_closed(self) -> None:
        """Second recv() raises ChannelClosedError."""
        tx, rx = await oneshot()
        await tx.send(42)
        await rx.recv()

        with pytest.raises(Exception, match='already consumed'):
            await rx.recv()

    async def test_recv_after_sender_close_raises_channel_closed(self) -> None:
        """recv() after sender.close() raises ChannelClosedError."""
        tx, rx = await oneshot()
        await tx.close()

        with pytest.raises(Exception, match='Channel closed'):
            await rx.recv()

    async def test_try_recv_no_value_returns_channel_empty(self) -> None:
        """try_recv() before send returns Err(ChannelEmpty)."""
        _tx, rx = await oneshot()

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, ChannelEmpty)

    async def test_try_recv_success_returns_ok(self) -> None:
        """try_recv() returns Ok(value) when value available."""
        tx, rx = await oneshot()
        await tx.send(42)

        result = await rx.try_recv()
        assert result == Ok(42)

    async def test_try_recv_twice_returns_channel_closed(self) -> None:
        """Second try_recv() returns Err(ChannelClosed)."""
        tx, rx = await oneshot()
        await tx.send(42)
        await rx.try_recv()

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)

    async def test_try_recv_after_close_returns_channel_closed(self) -> None:
        """try_recv() after sender.close() returns Err(ChannelClosed)."""
        tx, rx = await oneshot()
        await tx.close()

        result = await rx.try_recv()
        assert result.is_err()
        assert isinstance(result.error, ChannelClosed)

    async def test_clone_raises_not_implemented(self) -> None:
        """clone() raises NotImplementedError."""
        _tx, rx = await oneshot()

        with pytest.raises(NotImplementedError, match='do not support cloning'):
            rx.clone()


class TestOneshotAsyncIteration:
    """Tests for async iteration support."""

    async def test_async_for_yields_single_value(self) -> None:
        """Async for yields the single value then stops."""
        tx, rx = await oneshot()
        await tx.send(42)

        values = [v async for v in rx]
        assert values == [42]

    async def test_async_for_stops_on_close(self) -> None:
        """Async for stops immediately if channel closed."""
        tx, rx = await oneshot()
        await tx.close()

        values = [v async for v in rx]
        assert values == []

    async def test_async_for_with_delayed_send(self) -> None:
        """Async for waits for value then stops."""
        tx, rx = await oneshot()

        async def delayed_send():
            await asyncio.sleep(0.01)
            await tx.send(99)

        asyncio.create_task(delayed_send())

        values = [v async for v in rx]
        assert values == [99]


class TestOneshotClose:
    """Tests for close semantics."""

    async def test_close_unblocks_waiting_receiver(self) -> None:
        """close() unblocks a receiver waiting on recv()."""
        tx, rx = await oneshot()

        async def close_later():
            await asyncio.sleep(0.01)
            await tx.close()

        asyncio.create_task(close_later())

        with pytest.raises(Exception, match='Channel closed'):
            await rx.recv()

    async def test_close_is_idempotent(self) -> None:
        """Multiple close() calls are safe."""
        tx, _rx = await oneshot()
        await tx.close()
        await tx.close()  # Should not raise
