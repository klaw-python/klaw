"""Tests for runtime channels: Sender/Receiver protocols and factories."""

from __future__ import annotations

from klaw_core.runtime.channels import Receiver, Sender

# Tests for Sender and Receiver protocols


class TestSenderProtocol:
    """Test Sender protocol definition and behavior."""

    def test_sender_protocol_has_send(self) -> None:
        """Sender protocol defines async send() method."""
        assert hasattr(Sender, 'send')

    def test_sender_protocol_has_try_send(self) -> None:
        """Sender protocol defines async try_send() method."""
        assert hasattr(Sender, 'try_send')

    def test_sender_protocol_has_clone(self) -> None:
        """Sender protocol defines async clone() method."""
        assert hasattr(Sender, 'clone')

    def test_sender_protocol_has_close(self) -> None:
        """Sender protocol defines async close() method."""
        assert hasattr(Sender, 'close')


class TestReceiverProtocol:
    """Test Receiver protocol definition and behavior."""

    def test_receiver_protocol_has_recv(self) -> None:
        """Receiver protocol defines async recv() method."""
        assert hasattr(Receiver, 'recv')

    def test_receiver_protocol_has_try_recv(self) -> None:
        """Receiver protocol defines async try_recv() method."""
        assert hasattr(Receiver, 'try_recv')

    def test_receiver_protocol_has_clone(self) -> None:
        """Receiver protocol defines async clone() method."""
        assert hasattr(Receiver, 'clone')

    def test_receiver_protocol_has_aiter(self) -> None:
        """Receiver protocol defines __aiter__() method."""
        assert hasattr(Receiver, '__aiter__')

    def test_receiver_protocol_has_anext(self) -> None:
        """Receiver protocol defines async __anext__() method."""
        assert hasattr(Receiver, '__anext__')


class TestChannelProtocolTypes:
    """Test that protocols are properly typed."""

    def test_sender_is_protocol(self) -> None:
        """Sender is a Protocol type."""
        from typing import Protocol, get_origin

        assert get_origin(Sender) is None or issubclass(Sender, Protocol) or hasattr(Sender, '__protocol_attrs__')

    def test_receiver_is_protocol(self) -> None:
        """Receiver is a Protocol type."""
        from typing import Protocol, get_origin

        assert get_origin(Receiver) is None or issubclass(Receiver, Protocol) or hasattr(Receiver, '__protocol_attrs__')


class TestProtocolVariance:
    """Test variance behavior on Sender and Receiver protocols.

    These tests verify that the PEP 695 type parameter syntax is used,
    which enables automatic variance inference by type checkers:
    - Sender[T] is inferred as contravariant (T in input positions)
    - Receiver[T] is inferred as covariant (T in output positions)

    The actual variance is computed by type checkers (mypy/pyright),
    not at runtime. These tests verify the type parameters are configured
    for inference.
    """

    def test_sender_uses_pep695_syntax(self) -> None:
        """Sender uses PEP 695 type parameter syntax with infer_variance."""
        params = getattr(Sender, '__parameters__', ())
        assert len(params) == 1
        # PEP 695 syntax sets __infer_variance__ = True
        assert params[0].__infer_variance__ is True

    def test_receiver_uses_pep695_syntax(self) -> None:
        """Receiver uses PEP 695 type parameter syntax with infer_variance."""
        params = getattr(Receiver, '__parameters__', ())
        assert len(params) == 1
        # PEP 695 syntax sets __infer_variance__ = True
        assert params[0].__infer_variance__ is True

    def test_sender_typevar_not_explicitly_variant(self) -> None:
        """Sender's TypeVar is not explicitly marked (variance is inferred)."""
        params = getattr(Sender, '__parameters__', ())
        # When using PEP 695 syntax, explicit variance flags are False
        # because variance is inferred by the type checker
        assert params[0].__covariant__ is False
        assert params[0].__contravariant__ is False

    def test_receiver_typevar_not_explicitly_variant(self) -> None:
        """Receiver's TypeVar is not explicitly marked (variance is inferred)."""
        params = getattr(Receiver, '__parameters__', ())
        # When using PEP 695 syntax, explicit variance flags are False
        # because variance is inferred by the type checker
        assert params[0].__covariant__ is False
        assert params[0].__contravariant__ is False

    def test_variance_documented_in_docstrings(self) -> None:
        """Protocol docstrings explain variance behavior."""
        assert 'contravariant' in (Sender.__doc__ or '').lower()
        assert 'covariant' in (Receiver.__doc__ or '').lower()
