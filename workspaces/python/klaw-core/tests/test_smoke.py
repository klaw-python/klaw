"""Smoke tests to verify package structure and imports work."""


def test_import_types():
    """Test that core types can be imported."""
    from klaw_core import Err, Nothing, Ok, Option, Propagate, Result, Some

    assert Ok is not None
    assert Err is not None
    assert Some is not None
    assert Nothing is not None
    assert Propagate is not None
    assert Result is not None
    assert Option is not None


def test_import_decorators():
    """Test that decorators can be imported."""
    from klaw_core import do, do_async, pipe, pipe_async, result, safe, safe_async

    assert safe is not None
    assert safe_async is not None
    assert pipe is not None
    assert pipe_async is not None
    assert result is not None
    assert do is not None
    assert do_async is not None


def test_import_composition():
    """Test that composition utilities can be imported."""
    from klaw_core import Deref, pipe_fn

    assert Deref is not None
    assert pipe_fn is not None


def test_import_typeclass():
    """Test that typeclass can be imported."""
    from klaw_core import typeclass

    assert typeclass is not None


def test_import_fn():
    """Test that fn placeholder can be imported."""
    from klaw_core import fn

    assert fn is not None


def test_import_assertions():
    """Test that assertion utilities can be imported."""
    from klaw_core import assert_result, safe_assert

    assert safe_assert is not None
    assert assert_result is not None


def test_import_async():
    """Test that async utilities can be imported."""
    from klaw_core import AsyncResult, async_collect, async_lru_safe

    assert AsyncResult is not None
    assert async_collect is not None
    assert async_lru_safe is not None


def test_submodule_imports():
    """Test that submodule imports work."""
    from klaw_core import Err, Nothing, Ok, Option, Result, Some  # noqa: F401
    from klaw_core.assertions import assert_result, safe_assert  # noqa: F401
    from klaw_core.async_ import (  # noqa: F401
        AsyncResult,
        async_collect,
        async_lru_safe,
    )
    from klaw_core.compose import Deref, pipe  # noqa: F401
    from klaw_core.decorators import do, pipe, result, safe  # noqa: F401
    from klaw_core.fn import fn  # noqa: F401
    from klaw_core.typeclass import typeclass  # noqa: F401

    assert True  # If we get here, all imports worked
