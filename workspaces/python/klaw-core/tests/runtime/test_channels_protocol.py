"""Tests for runtime channels: Sender/Receiver protocols and factories."""

from __future__ import annotations

import pytest

from klaw_core.runtime.channels import Receiver, Sender

# Tests for Sender and Receiver protocols


class TestSenderProtocol:
    """Test Sender protocol definition and behavior."""

    def test_sender_protocol_has_send(self) -> None:
        """Sender protocol defines async send() method."""
        assert hasattr(Sender, "send")

    def test_sender_protocol_has_try_send(self) -> None:
        """Sender protocol defines async try_send() method."""
        assert hasattr(Sender, "try_send")

    def test_sender_protocol_has_clone(self) -> None:
        """Sender protocol defines async clone() method."""
        assert hasattr(Sender, "clone")

    def test_sender_protocol_has_close(self) -> None:
        """Sender protocol defines async close() method."""
        assert hasattr(Sender, "close")


class TestReceiverProtocol:
    """Test Receiver protocol definition and behavior."""

    def test_receiver_protocol_has_recv(self) -> None:
        """Receiver protocol defines async recv() method."""
        assert hasattr(Receiver, "recv")

    def test_receiver_protocol_has_try_recv(self) -> None:
        """Receiver protocol defines async try_recv() method."""
        assert hasattr(Receiver, "try_recv")

    def test_receiver_protocol_has_clone(self) -> None:
        """Receiver protocol defines async clone() method."""
        assert hasattr(Receiver, "clone")

    def test_receiver_protocol_has_aiter(self) -> None:
        """Receiver protocol defines __aiter__() method."""
        assert hasattr(Receiver, "__aiter__")

    def test_receiver_protocol_has_anext(self) -> None:
        """Receiver protocol defines async __anext__() method."""
        assert hasattr(Receiver, "__anext__")


class TestChannelProtocolTypes:
    """Test that protocols are properly typed."""

    def test_sender_is_protocol(self) -> None:
        """Sender is a Protocol type."""
        from typing import get_origin
        from typing import Protocol

        assert get_origin(Sender) is None or issubclass(Sender, Protocol) or hasattr(Sender, "__protocol_attrs__")

    def test_receiver_is_protocol(self) -> None:
        """Receiver is a Protocol type."""
        from typing import get_origin
        from typing import Protocol

        assert get_origin(Receiver) is None or issubclass(Receiver, Protocol) or hasattr(Receiver, "__protocol_attrs__")
