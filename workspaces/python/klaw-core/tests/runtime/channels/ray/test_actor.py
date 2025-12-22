"""Tests for RayChannelActor and _TypeValidator."""

from __future__ import annotations

import math

import pytest
from klaw_core.runtime.channels.ray.actor import _TypeValidator


class TestTypeValidator:
    """Tests for _TypeValidator helper class."""

    def test_none_type_accepts_all(self) -> None:
        """Validator with None type accepts any value."""
        validator = _TypeValidator(None)
        assert validator.validate(42) is True
        assert validator.validate('hello') is True
        assert validator.validate([1, 2, 3]) is True
        assert validator.validate({'key': 'value'}) is True
        assert validator.validate(None) is True

    def test_int_type_accepts_int(self) -> None:
        """Validator with int type accepts integers."""
        validator = _TypeValidator(int)
        assert validator.validate(42) is True
        assert validator.validate(0) is True
        assert validator.validate(-100) is True

    def test_int_type_rejects_non_int(self) -> None:
        """Validator with int type rejects non-integers."""
        validator = _TypeValidator(int)
        assert validator.validate('hello') is False
        assert validator.validate(math.pi) is False
        assert validator.validate([1, 2]) is False

    def test_str_type_accepts_str(self) -> None:
        """Validator with str type accepts strings."""
        validator = _TypeValidator(str)
        assert validator.validate('hello') is True
        assert validator.validate('') is True

    def test_str_type_rejects_non_str(self) -> None:
        """Validator with str type rejects non-strings."""
        validator = _TypeValidator(str)
        assert validator.validate(42) is False
        assert validator.validate(['a', 'b']) is False

    def test_list_str_type(self) -> None:
        """Validator with list[str] type validates correctly."""
        validator = _TypeValidator(list[str])
        assert validator.validate(['a', 'b', 'c']) is True
        assert validator.validate([]) is True
        assert validator.validate([1, 2, 3]) is False
        assert validator.validate('not a list') is False

    def test_converter_is_cached(self) -> None:
        """Converter function is created lazily and cached."""
        validator = _TypeValidator(int)
        assert validator._convert_fn is None

        validator.validate(42)
        first_fn = validator._convert_fn
        assert first_fn is not None

        validator.validate(100)
        assert validator._convert_fn is first_fn


@pytest.mark.ray
class TestRayChannelActor:
    """Tests for RayChannelActor with Ray container fixtures."""

    def test_actor_instantiation(self, ray_env: None) -> None:
        """Actor can be instantiated with Ray."""
        from klaw_core.runtime.channels.ray.actor import RayChannelActor

        actor = RayChannelActor.remote(capacity=10)
        assert actor is not None

    def test_actor_with_typed_value(self, ray_env: None) -> None:
        """Actor can be instantiated with value_type."""
        import ray
        from klaw_core.runtime.channels.ray.actor import RayChannelActor

        actor = RayChannelActor.remote(capacity=10, value_type=int)
        status = ray.get(actor.put_nowait.remote(42))
        assert status == 'ok'

    def test_actor_rejects_wrong_type(self, ray_env: None) -> None:
        """Actor rejects values that don't match value_type."""
        import ray
        from klaw_core.runtime.channels.ray.actor import RayChannelActor

        actor = RayChannelActor.remote(capacity=10, value_type=int)
        status = ray.get(actor.put_nowait.remote('not an int'))
        assert status == 'type_error'

    def test_actor_put_get_roundtrip(self, ray_env: None) -> None:
        """Actor can put and get values."""
        import ray
        from klaw_core.runtime.channels.ray.actor import RayChannelActor

        actor = RayChannelActor.remote(capacity=10, value_type=int)

        ray.get(actor.register_sender.remote())
        ray.get(actor.register_receiver.remote('reader-1', 'node-1'))

        status = ray.get(actor.put_nowait.remote(42))
        assert status == 'ok'

        result = ray.get(actor.get_nowait.remote())
        assert result.status == 'ok'
        assert result.value == 42

    def test_actor_unbounded(self, ray_env: None) -> None:
        """Actor works in unbounded mode."""
        import ray
        from klaw_core.runtime.channels.ray.actor import RayChannelActor

        actor = RayChannelActor.remote(unbounded=True)
        ray.get(actor.register_sender.remote())

        for i in range(100):
            status = ray.get(actor.put_nowait.remote(i))
            assert status == 'ok'
