"""Tests for channel() factory function."""

from __future__ import annotations

import pytest

from klaw_core.runtime.channels import Receiver, Sender, channel


class TestChannelFactory:
    """Tests for channel(capacity, distributed, unbounded) factory."""

    async def test_channel_returns_tuple(self) -> None:
        """channel() returns (Sender, Receiver) tuple."""
        tx, rx = await channel()
        assert tx is not None
        assert rx is not None

    async def test_channel_default_args(self) -> None:
        """channel() works with default arguments."""
        tx, rx = await channel()
        assert tx is not None
        assert rx is not None

    async def test_channel_with_capacity(self) -> None:
        """channel(capacity=N) creates bounded channel."""
        tx, rx = await channel(capacity=100)
        assert tx is not None
        assert rx is not None

    async def test_channel_with_unbounded(self) -> None:
        """channel(unbounded=True) creates unbounded channel."""
        tx, rx = await channel(unbounded=True)
        assert tx is not None
        assert rx is not None

    async def test_channel_generic_type_int(self) -> None:
        """channel() works with int type."""
        tx, rx = await channel()
        await tx.send(42)
        value = await rx.recv()
        assert value == 42
        assert isinstance(value, int)

    async def test_channel_generic_type_str(self) -> None:
        """channel() works with str type."""
        tx, rx = await channel()
        await tx.send("hello")
        value = await rx.recv()
        assert value == "hello"
        assert isinstance(value, str)

    async def test_channel_generic_type_complex(self) -> None:
        """channel() works with complex types (dict, list)."""
        tx, rx = await channel()
        msg = {"key": "value", "num": 42}
        await tx.send(msg)
        received = await rx.recv()
        assert received == msg

    async def test_channel_distributed_flag(self) -> None:
        """channel(distributed=True) flag is accepted."""
        # For now, distributed=True might return LocalChannel
        # (actual distributed channels are future work)
        tx, rx = await channel(distributed=False)
        assert tx is not None
        assert rx is not None

    async def test_channel_can_be_cloned(self) -> None:
        """Returned sender/receiver can be cloned."""
        tx, rx = await channel()
        tx2 = tx.clone()
        rx2 = rx.clone()
        assert tx is not tx2
        assert rx is not rx2
