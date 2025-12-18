"""Tests for verifying import styles work correctly."""


class TestFlatImports:
    """Verify flat imports from klaw_core work."""

    def test_result_types(self) -> None:
        """Test importing Result types from root."""
        from klaw_core import Err, Ok, Result, collect

        assert Ok(42).unwrap() == 42
        assert Err('error').is_err()
        result: Result[int, str] = Ok(1)
        assert result.is_ok()
        assert collect([Ok(1), Ok(2)]).unwrap() == [1, 2]

    def test_option_types(self) -> None:
        """Test importing Option types from root."""
        from klaw_core import Nothing, NothingType, Option, Some

        assert Some(42).unwrap() == 42
        assert Nothing.is_none()
        option: Option[int] = Some(1)
        assert option.is_some()
        assert isinstance(Nothing, NothingType)

    def test_propagate(self) -> None:
        """Test importing Propagate from root."""
        from klaw_core import Propagate

        assert Propagate is not None

    def test_decorators(self) -> None:
        """Test importing decorators from root."""
        from klaw_core import do, do_async, pipe, pipe_async, result, safe, safe_async

        assert callable(safe)
        assert callable(safe_async)
        assert callable(pipe)
        assert callable(pipe_async)
        assert callable(result)
        assert callable(do)
        assert callable(do_async)

    def test_composition(self) -> None:
        """Test importing composition utilities from root."""
        from klaw_core import Deref, DerefOk, DerefSome, pipe_fn

        assert Deref is not None
        assert DerefOk is not None
        assert DerefSome is not None
        assert callable(pipe_fn)

    def test_typeclass(self) -> None:
        """Test importing typeclass from root."""
        from klaw_core import typeclass

        assert callable(typeclass)

    def test_fn(self) -> None:
        """Test importing fn from root."""
        from klaw_core import fn

        assert fn is not None
        assert (fn + 1)(5) == 6

    def test_assertions(self) -> None:
        """Test importing assertions from root."""
        from klaw_core import assert_result, safe_assert

        assert callable(safe_assert)
        assert callable(assert_result)

    def test_async(self) -> None:
        """Test importing async utilities from root."""
        from klaw_core import AsyncResult, async_collect, async_lru_safe

        assert AsyncResult is not None
        assert callable(async_collect)
        assert callable(async_lru_safe)


class TestSubmoduleImports:
    """Verify submodule imports work."""

    def test_result_module(self) -> None:
        """Test importing from klaw_core.result."""
        from klaw_core.result import Err, Ok

        assert Ok(1).is_ok()
        assert Err('e').is_err()

    def test_option_module(self) -> None:
        """Test importing from klaw_core.option."""
        from klaw_core.option import Nothing, Some

        assert Some(1).is_some()
        assert Nothing.is_none()

    def test_propagate_module(self) -> None:
        """Test importing from klaw_core.propagate."""
        from klaw_core.propagate import Propagate

        assert Propagate is not None

    def test_decorators_module(self) -> None:
        """Test importing from klaw_core.decorators."""
        from klaw_core.decorators import safe

        assert callable(safe)

    def test_async_module(self) -> None:
        """Test importing from klaw_core.async_."""
        from klaw_core.async_ import AsyncResult

        assert AsyncResult is not None

    def test_fn_module(self) -> None:
        """Test importing from klaw_core.fn."""
        from klaw_core.fn import Expr, Lambda, Stream, fn

        assert fn is not None
        assert Expr is not None
        assert Lambda is not None
        assert Stream is not None

    def test_typeclass_module(self) -> None:
        """Test importing from klaw_core.typeclass."""
        from klaw_core.typeclass import NoInstanceError, TypeClass, typeclass

        assert callable(typeclass)
        assert TypeClass is not None
        assert NoInstanceError is not None

    def test_compose_module(self) -> None:
        """Test importing from klaw_core.compose."""
        from klaw_core.compose import Deref, pipe

        assert Deref is not None
        assert callable(pipe)

    def test_assertions_module(self) -> None:
        """Test importing from klaw_core.assertions."""
        from klaw_core.assertions import assert_result, safe_assert

        assert callable(safe_assert)
        assert callable(assert_result)


class TestImportConsistency:
    """Verify flat and submodule imports return the same objects."""

    def test_ok_is_same(self) -> None:
        """Ok from root and submodule should be identical."""
        from klaw_core import Ok as FlatOk
        from klaw_core.result import Ok as SubOk

        assert FlatOk is SubOk

    def test_some_is_same(self) -> None:
        """Some from root and submodule should be identical."""
        from klaw_core import Some as FlatSome
        from klaw_core.option import Some as SubSome

        assert FlatSome is SubSome

    def test_safe_is_same(self) -> None:
        """Safe from root and submodule should be identical."""
        from klaw_core import safe as flat_safe
        from klaw_core.decorators import safe as sub_safe

        assert flat_safe is sub_safe

    def test_fn_is_same(self) -> None:
        """Fn from root and submodule should be identical."""
        from klaw_core import fn as flat_fn
        from klaw_core.fn import fn as sub_fn

        assert flat_fn is sub_fn
