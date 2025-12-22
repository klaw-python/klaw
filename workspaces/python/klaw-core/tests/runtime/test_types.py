"""Unit tests for constrained type aliases."""

from __future__ import annotations

import msgspec
import pytest
from klaw_core.runtime.types import (
    ChannelCapacity,
    ConcurrencyLimit,
    Identifier,
    Namespace,
    NonNegativeInt,
    PositiveInt,
    TimeoutSeconds,
)


class PositiveIntConfig(msgspec.Struct):
    """Helper struct for testing PositiveInt."""

    value: PositiveInt


class NonNegativeIntConfig(msgspec.Struct):
    """Helper struct for testing NonNegativeInt."""

    value: NonNegativeInt


class ChannelCapacityConfig(msgspec.Struct):
    """Helper struct for testing ChannelCapacity."""

    value: ChannelCapacity


class TimeoutSecondsConfig(msgspec.Struct):
    """Helper struct for testing TimeoutSeconds."""

    value: TimeoutSeconds


class ConcurrencyLimitConfig(msgspec.Struct):
    """Helper struct for testing ConcurrencyLimit."""

    value: ConcurrencyLimit


class IdentifierConfig(msgspec.Struct):
    """Helper struct for testing Identifier."""

    value: Identifier


class NamespaceConfig(msgspec.Struct):
    """Helper struct for testing Namespace."""

    value: Namespace


class TestPositiveInt:
    """Tests for PositiveInt constraint (gt=0)."""

    @pytest.mark.parametrize('value', [1, 100, 1_000_000])
    def test_accepts_positive_values(self, value: int) -> None:
        result = msgspec.json.decode(
            f'{{"value": {value}}}'.encode(),
            type=PositiveIntConfig,
        )
        assert result.value == value

    @pytest.mark.parametrize('value', [0, -1, -100])
    def test_rejects_non_positive_values(self, value: int) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                f'{{"value": {value}}}'.encode(),
                type=PositiveIntConfig,
            )
        assert 'value' in str(exc_info.value).lower()


class TestNonNegativeInt:
    """Tests for NonNegativeInt constraint (ge=0)."""

    @pytest.mark.parametrize('value', [0, 1, 100, 1_000_000])
    def test_accepts_non_negative_values(self, value: int) -> None:
        result = msgspec.json.decode(
            f'{{"value": {value}}}'.encode(),
            type=NonNegativeIntConfig,
        )
        assert result.value == value

    @pytest.mark.parametrize('value', [-1, -100])
    def test_rejects_negative_values(self, value: int) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                f'{{"value": {value}}}'.encode(),
                type=NonNegativeIntConfig,
            )
        assert 'value' in str(exc_info.value).lower()


class TestChannelCapacity:
    """Tests for ChannelCapacity constraint (ge=1, le=1_000_000)."""

    @pytest.mark.parametrize('value', [1, 500_000, 1_000_000])
    def test_accepts_valid_capacity(self, value: int) -> None:
        result = msgspec.json.decode(
            f'{{"value": {value}}}'.encode(),
            type=ChannelCapacityConfig,
        )
        assert result.value == value

    @pytest.mark.parametrize('value', [0, -1, 1_000_001, 10_000_000])
    def test_rejects_invalid_capacity(self, value: int) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                f'{{"value": {value}}}'.encode(),
                type=ChannelCapacityConfig,
            )
        assert 'value' in str(exc_info.value).lower()


class TestTimeoutSeconds:
    """Tests for TimeoutSeconds constraint (ge=0.0, le=86400.0)."""

    @pytest.mark.parametrize('value', [0.0, 30.0, 3600.0, 86400.0])
    def test_accepts_valid_timeout(self, value: float) -> None:
        result = msgspec.json.decode(
            f'{{"value": {value}}}'.encode(),
            type=TimeoutSecondsConfig,
        )
        assert result.value == value

    @pytest.mark.parametrize('value', [-1.0, -0.001, 86400.1, 100000.0])
    def test_rejects_invalid_timeout(self, value: float) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                f'{{"value": {value}}}'.encode(),
                type=TimeoutSecondsConfig,
            )
        assert 'value' in str(exc_info.value).lower()


class TestConcurrencyLimit:
    """Tests for ConcurrencyLimit constraint (ge=1, le=10_000)."""

    @pytest.mark.parametrize('value', [1, 100, 10_000])
    def test_accepts_valid_concurrency(self, value: int) -> None:
        result = msgspec.json.decode(
            f'{{"value": {value}}}'.encode(),
            type=ConcurrencyLimitConfig,
        )
        assert result.value == value

    @pytest.mark.parametrize('value', [0, -1, 10_001, 100_000])
    def test_rejects_invalid_concurrency(self, value: int) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                f'{{"value": {value}}}'.encode(),
                type=ConcurrencyLimitConfig,
            )
        assert 'value' in str(exc_info.value).lower()


class TestIdentifier:
    """Tests for Identifier constraint (pattern + length)."""

    @pytest.mark.parametrize('value', ['foo', 'foo_bar', 'Foo-123', '_private', 'a'])
    def test_accepts_valid_identifiers(self, value: str) -> None:
        result = msgspec.json.decode(
            f'{{"value": "{value}"}}'.encode(),
            type=IdentifierConfig,
        )
        assert result.value == value

    @pytest.mark.parametrize(
        'value',
        [
            '',  # empty
            '123foo',  # starts with digit
            'foo bar',  # contains space
            'foo.bar',  # contains dot
        ],
    )
    def test_rejects_invalid_identifiers(self, value: str) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                f'{{"value": "{value}"}}'.encode(),
                type=IdentifierConfig,
            )
        assert 'value' in str(exc_info.value).lower()

    def test_rejects_too_long_identifier(self) -> None:
        long_value = 'a' * 256
        with pytest.raises(msgspec.ValidationError):
            msgspec.json.decode(
                f'{{"value": "{long_value}"}}'.encode(),
                type=IdentifierConfig,
            )

    def test_accepts_max_length_identifier(self) -> None:
        max_value = 'a' * 255
        result = msgspec.json.decode(
            f'{{"value": "{max_value}"}}'.encode(),
            type=IdentifierConfig,
        )
        assert result.value == max_value


class TestNamespace:
    """Tests for Namespace constraint (K8s-style, pattern + length)."""

    @pytest.mark.parametrize('value', ['klaw', 'my-namespace', 'prod01', 'a'])
    def test_accepts_valid_namespaces(self, value: str) -> None:
        result = msgspec.json.decode(
            f'{{"value": "{value}"}}'.encode(),
            type=NamespaceConfig,
        )
        assert result.value == value

    @pytest.mark.parametrize(
        'value',
        [
            '',  # empty
            'MyNamespace',  # uppercase
            '123ns',  # starts with digit
            'ns_with_underscore',  # contains underscore
            '-starts-with-dash',  # starts with dash
        ],
    )
    def test_rejects_invalid_namespaces(self, value: str) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                f'{{"value": "{value}"}}'.encode(),
                type=NamespaceConfig,
            )
        assert 'value' in str(exc_info.value).lower()

    def test_rejects_too_long_namespace(self) -> None:
        long_value = 'a' * 64
        with pytest.raises(msgspec.ValidationError):
            msgspec.json.decode(
                f'{{"value": "{long_value}"}}'.encode(),
                type=NamespaceConfig,
            )

    def test_accepts_max_length_namespace(self) -> None:
        max_value = 'a' * 63
        result = msgspec.json.decode(
            f'{{"value": "{max_value}"}}'.encode(),
            type=NamespaceConfig,
        )
        assert result.value == max_value


class TestErrorMessages:
    """Tests for error message clarity."""

    def test_error_includes_field_path(self) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                b'{"value": 0}',
                type=PositiveIntConfig,
            )
        error_msg = str(exc_info.value)
        assert '$.value' in error_msg or 'value' in error_msg.lower()

    def test_error_indicates_constraint_violation(self) -> None:
        with pytest.raises(msgspec.ValidationError) as exc_info:
            msgspec.json.decode(
                b'{"value": -1}',
                type=ChannelCapacityConfig,
            )
        error_msg = str(exc_info.value)
        assert '>=' in error_msg or 'greater' in error_msg.lower() or 'int' in error_msg.lower()
