"""Tests for typeclass decorator and dispatch."""

import math

import pytest
from klaw_core.typeclass import NoInstanceError, TypeClass, typeclass


class TestTypeclassBasic:
    """Tests for basic typeclass functionality."""

    def test_typeclass_decorator(self):
        """@typeclass creates a TypeClass instance."""

        @typeclass
        def show(value) -> str: ...

        assert isinstance(show, TypeClass)

    def test_typeclass_preserves_name(self):
        """@typeclass preserves function name."""

        @typeclass
        def my_func(value) -> str: ...

        assert my_func.__name__ == 'my_func'

    def test_typeclass_preserves_doc(self):
        """@typeclass preserves docstring."""

        @typeclass
        def show(value) -> str:
            """Convert to string."""

        assert show.__doc__ == 'Convert to string.'

    def test_typeclass_repr(self):
        """TypeClass has readable repr."""

        @typeclass
        def show(value) -> str: ...

        assert repr(show) == '<typeclass show with 0 instances>'


class TestTypeclassInstances:
    """Tests for registering and dispatching instances."""

    def test_instance_registration(self):
        """@instance registers a type-specific implementation."""

        @typeclass
        def show(value) -> str: ...

        @show.instance(int)
        def show_int(value: int) -> str:
            return f'Int({value})'

        assert show(42) == 'Int(42)'

    def test_multiple_instances(self):
        """Multiple instances can be registered."""

        @typeclass
        def show(value) -> str: ...

        @show.instance(int)
        def show_int(value: int) -> str:
            return f'Int({value})'

        @show.instance(str)
        def show_str(value: str) -> str:
            return f'Str({value!r})'

        assert show(42) == 'Int(42)'
        assert show('hello') == "Str('hello')"

    def test_instance_with_extra_args(self):
        """Instances can accept extra arguments."""

        @typeclass
        def format_value(value, prefix: str = '') -> str: ...

        @format_value.instance(int)
        def format_int(value: int, prefix: str = '') -> str:
            return f'{prefix}{value}'

        assert format_value(42) == '42'
        assert format_value(42, prefix='num: ') == 'num: 42'

    def test_instance_with_kwargs(self):
        """Instances can accept keyword arguments."""

        @typeclass
        def serialize(value, **options) -> str: ...

        @serialize.instance(dict)
        def serialize_dict(value: dict, indent: int = 0) -> str:
            return f'Dict({value}, indent={indent})'

        assert serialize({'a': 1}) == "Dict({'a': 1}, indent=0)"
        assert serialize({'a': 1}, indent=2) == "Dict({'a': 1}, indent=2)"


class TestTypeclassDispatch:
    """Tests for type dispatch behavior."""

    def test_dispatch_by_exact_type(self):
        """Dispatch uses exact type match first."""

        @typeclass
        def process(value) -> str: ...

        @process.instance(bool)
        def process_bool(value: bool) -> str:
            return f'Bool({value})'

        @process.instance(int)
        def process_int(value: int) -> str:
            return f'Int({value})'

        # bool is subclass of int, but exact match should win
        assert process(True) == 'Bool(True)'
        assert process(42) == 'Int(42)'

    def test_dispatch_by_inheritance(self):
        """Dispatch falls back to base class instance."""

        class Animal:
            pass

        class Dog(Animal):
            pass

        @typeclass
        def speak(value) -> str: ...

        @speak.instance(Animal)
        def speak_animal(value: Animal) -> str:
            return 'Some animal sound'

        assert speak(Dog()) == 'Some animal sound'

    def test_dispatch_mro_order(self):
        """Dispatch follows MRO for inheritance."""

        class A:
            pass

        class B(A):
            pass

        class C(B):
            pass

        @typeclass
        def identify(value) -> str: ...

        @identify.instance(A)
        def identify_a(value: A) -> str:
            return 'A'

        @identify.instance(B)
        def identify_b(value: B) -> str:
            return 'B'

        # C should match B (closer in MRO) before A
        assert identify(C()) == 'B'
        assert identify(B()) == 'B'
        assert identify(A()) == 'A'


class TestTypeclassDefault:
    """Tests for default implementations."""

    def test_default_implementation(self):
        """Typeclass with body serves as default."""

        @typeclass
        def stringify(value) -> str:
            return f'Default({value!r})'

        assert stringify(42) == 'Default(42)'
        assert stringify('hello') == "Default('hello')"

    def test_default_with_instances(self):
        """Default is used when no instance matches."""

        @typeclass
        def stringify(value) -> str:
            return f'Default({value!r})'

        @stringify.instance(int)
        def stringify_int(value: int) -> str:
            return f'Int({value})'

        assert stringify(42) == 'Int(42)'
        assert stringify('hello') == "Default('hello')"

    def test_no_instance_no_default_raises(self):
        """NoInstanceError raised when no match and no default."""

        @typeclass
        def process(value) -> str: ...

        with pytest.raises(NoInstanceError) as exc_info:
            process(42)

        assert exc_info.value.typeclass_name == 'process'
        assert exc_info.value.value_type is int


class TestTypeclassGenericTypes:
    """Tests for generic type dispatch."""

    def test_list_instance(self):
        """Instance for list type."""

        @typeclass
        def show(value) -> str: ...

        @show.instance(list)
        def show_list(value: list) -> str:
            return f'List({value})'

        assert show([1, 2, 3]) == 'List([1, 2, 3])'

    def test_generic_list_int(self):
        """Instance for list[int] specifically."""

        @typeclass
        def process(value) -> str: ...

        @process.instance(list[int])
        def process_int_list(value: list[int]) -> str:
            return f'IntList({value})'

        @process.instance(list[str])
        def process_str_list(value: list[str]) -> str:
            return f'StrList({value})'

        assert process([1, 2, 3]) == 'IntList([1, 2, 3])'
        assert process(['a', 'b']) == "StrList(['a', 'b'])"

    def test_generic_empty_list(self):
        """Empty list matches first registered generic."""

        @typeclass
        def process(value) -> str: ...

        @process.instance(list[int])
        def process_int_list(value: list[int]) -> str:
            return f'IntList({value})'

        # Empty list matches because we can't determine element type
        assert process([]) == 'IntList([])'

    def test_dict_instance(self):
        """Instance for dict type."""

        @typeclass
        def show(value) -> str: ...

        @show.instance(dict)
        def show_dict(value: dict) -> str:
            return f'Dict({value})'

        assert show({'a': 1}) == "Dict({'a': 1})"

    def test_generic_dict(self):
        """Instance for dict[str, int] specifically."""

        @typeclass
        def process(value) -> str: ...

        @process.instance(dict[str, int])
        def process_str_int_dict(value: dict[str, int]) -> str:
            return f'StrIntDict({value})'

        assert process({'a': 1, 'b': 2}) == "StrIntDict({'a': 1, 'b': 2})"


class TestTypeclassNoInstanceError:
    """Tests for NoInstanceError."""

    def test_error_message(self):
        """NoInstanceError has informative message."""

        @typeclass
        def process(value) -> str: ...

        with pytest.raises(NoInstanceError) as exc_info:
            process(math.pi)

        assert 'process' in str(exc_info.value)
        assert 'float' in str(exc_info.value)

    def test_error_attributes(self):
        """NoInstanceError has typeclass_name and value_type."""

        @typeclass
        def my_typeclass(value) -> str: ...

        try:
            my_typeclass(complex(1, 2))
        except NoInstanceError as e:
            assert e.typeclass_name == 'my_typeclass'
            assert e.value_type is complex


class TestTypeclassRepr:
    """Tests for TypeClass representation."""

    def test_repr_empty(self):
        """Repr shows 0 instances when empty."""

        @typeclass
        def show(value) -> str: ...

        assert '0 instances' in repr(show)

    def test_repr_with_instances(self):
        """Repr shows instance count."""

        @typeclass
        def show(value) -> str: ...

        @show.instance(int)
        def show_int(value: int) -> str:
            return str(value)

        @show.instance(str)
        def show_str(value: str) -> str:
            return value

        assert '2 instances' in repr(show)


class TestTypeclassRealWorld:
    """Real-world usage patterns."""

    def test_json_serializable(self):
        """Typeclass for JSON-like serialization."""

        @typeclass
        def to_json(value) -> str: ...

        @to_json.instance(str)
        def str_to_json(value: str) -> str:
            return f'"{value}"'

        @to_json.instance(int)
        def int_to_json(value: int) -> str:
            return str(value)

        @to_json.instance(bool)
        def bool_to_json(value: bool) -> str:
            return 'true' if value else 'false'

        @to_json.instance(list)
        def list_to_json(value: list) -> str:
            items = ', '.join(to_json(item) for item in value)
            return f'[{items}]'

        assert to_json('hello') == '"hello"'
        assert to_json(42) == '42'
        assert to_json(True) == 'true'
        assert to_json([1, 2, 'three']) == '[1, 2, "three"]'

    def test_eq_typeclass(self):
        """Typeclass for custom equality."""

        @typeclass
        def eq(a, b) -> bool:
            return a == b

        @eq.instance(float)
        def float_eq(a: float, b: float) -> bool:
            return abs(a - b) < 1e-9

        assert eq(1, 1) is True
        assert eq('a', 'a') is True
        assert eq(1.0, 1.0 + 1e-10) is True  # Float tolerance
        assert eq(1.0, 1.1) is False


class TestTypeclassEdgeCases:
    """Edge case tests."""

    def test_none_value(self):
        """Typeclass handles None values."""

        @typeclass
        def show(value) -> str: ...

        @show.instance(type(None))
        def show_none(value: None) -> str:
            return 'Nothing'

        assert show(None) == 'Nothing'

    def test_instance_returns_original_function(self):
        """@instance decorator returns the original function."""

        @typeclass
        def show(value) -> str: ...

        @show.instance(int)
        def show_int(value: int) -> str:
            return str(value)

        # The decorated function is still callable on its own
        assert show_int(42) == '42'

    def test_callable_type(self):
        """Instance for callable types."""

        @typeclass
        def describe(value) -> str: ...

        def my_func():
            pass

        @describe.instance(type(my_func))
        def describe_func(value) -> str:
            return f'Function: {value.__name__}'

        assert describe(my_func) == 'Function: my_func'

    def test_no_args_with_default(self):
        """Calling with no args uses default if it handles it."""

        @typeclass
        def get_value() -> int:
            return 42

        assert get_value() == 42

    def test_no_args_without_default_raises(self):
        """Calling with no args and no default raises TypeError."""

        @typeclass
        def process(value) -> str: ...

        with pytest.raises(TypeError, match='requires at least one argument'):
            process()
