"""@typeclass decorator and dispatch mechanism.

Provides Haskell-style typeclasses for Python with runtime dispatch
and static type inference via overloads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar, get_args, get_origin

import wrapt

__all__ = ['NoInstanceError', 'TypeClass', 'typeclass']

F = TypeVar('F', bound=Callable[..., Any])


class NoInstanceError(TypeError):
    """Raised when no typeclass instance is registered for a type."""

    def __init__(self, typeclass_name: str, value_type: type) -> None:
        self.typeclass_name = typeclass_name
        self.value_type = value_type
        super().__init__(
            f"No instance of '{typeclass_name}' for type '{value_type.__name__}'"
        )


class TypeClass(wrapt.ObjectProxy, Generic[F]):
    """A typeclass with registered type instances.

    A typeclass defines a polymorphic function that dispatches to
    type-specific implementations based on the first argument's type.

    Attributes:
        _self_name: The name of the typeclass function.
        _self_default: The default/fallback function implementation.
        _self_instances: Dictionary mapping types to their instance implementations.
        _self_generic_instances: Dictionary mapping generic types to their implementations.

    Example:
        ```python
        @typeclass
        def show(value) -> str:
            '''Convert a value to a string representation.'''
            ...

        @show.instance(int)
        def show_int(value: int) -> str:
            return f"Int({value})"

        @show.instance(str)
        def show_str(value: str) -> str:
            return f"Str({value!r})"

        show(42)
        # 'Int(42)'
        show("hello")
        # "Str('hello')"
        ```
    """

    def __init__(self, default_fn: F) -> None:
        """Initialize a typeclass with a default/fallback function.

        Args:
            default_fn: The decorated function, used as default or for signature.
        """
        super().__init__(default_fn)
        self._self_name = default_fn.__name__
        self._self_default: F | None = default_fn if _has_implementation(default_fn) else None
        self._self_instances: dict[type, Callable[..., Any]] = {}
        self._self_generic_instances: dict[type, Callable[..., Any]] = {}

    def instance(self, type_: type) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an instance implementation for a specific type.

        Args:
            type_: The type to register the instance for.

        Returns:
            A decorator that registers the implementation.

        Example:
            ```python
            @show.instance(list)
            def show_list(value: list) -> str:
                return f"List({value})"
            ```
        """
        origin = get_origin(type_)

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if origin is not None:
                # Generic type like list[int] - store under origin with args check
                self._self_generic_instances[type_] = fn
            else:
                self._self_instances[type_] = fn
            return fn

        return decorator

    def _find_instance(self, value: Any) -> Callable[..., Any] | None:
        """Find the best matching instance for a value."""
        value_type = type(value)

        # Exact type match
        if value_type in self._self_instances:
            return self._self_instances[value_type]

        # Check generic instances (e.g., list[int])
        for generic_type, fn in self._self_generic_instances.items():
            if self._matches_generic(value, generic_type):
                return fn

        # Check origin of generic types (e.g., list for list[int])
        for registered_type, fn in self._self_instances.items():
            origin = get_origin(registered_type)
            if origin is not None and isinstance(value, origin):
                return fn

        # MRO lookup for inheritance
        for base in value_type.__mro__[1:]:
            if base in self._self_instances:
                return self._self_instances[base]

        return None

    def _matches_generic(self, value: Any, generic_type: type) -> bool:
        """Check if a value matches a generic type like list[int]."""
        origin = get_origin(generic_type)
        args = get_args(generic_type)

        if origin is None:
            return isinstance(value, generic_type)

        if not isinstance(value, origin):
            return False

        if not args:
            return True

        # For sequences, check element types
        if origin in (list, tuple, set, frozenset):
            if not value:
                return True  # Empty collection matches any element type
            element_type = args[0]
            return all(isinstance(elem, element_type) for elem in value)

        # For dicts, check key and value types
        if origin is dict:
            if not value:
                return True
            key_type, val_type = args if len(args) == 2 else (args[0], Any)
            return all(
                isinstance(k, key_type) and isinstance(v, val_type)
                for k, v in value.items()
            )

        return True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Dispatch to the appropriate instance based on first argument."""
        if not args:
            if self._self_default is not None:
                return self._self_default(**kwargs)
            raise TypeError(f'{self._self_name}() requires at least one argument')

        first_arg = args[0]
        instance_fn = self._find_instance(first_arg)

        if instance_fn is not None:
            return instance_fn(*args, **kwargs)

        if self._self_default is not None:
            return self._self_default(*args, **kwargs)

        raise NoInstanceError(self._self_name, type(first_arg))

    def __repr__(self) -> str:
        types_registered = list(self._self_instances.keys()) + list(self._self_generic_instances.keys())
        return f'<typeclass {self._self_name} with {len(types_registered)} instances>'


def _has_implementation(fn: Callable[..., Any]) -> bool:
    """Check if a function has an actual implementation (not just ...).

    Returns True if the function does something other than just `...` or `pass`.
    """
    if not callable(fn):
        return False

    # Get the code object
    code = getattr(fn, '__code__', None)
    if code is None:
        return True  # Built-in or C extension, assume it has implementation

    # Check for stub implementations (just `...` or `pass` or `return None`)
    # In Python 3.13, these all compile to the same bytecode that just returns None
    # with co_consts = (None,)
    # Real implementations have more constants or different bytecode
    if code.co_consts == (None,) and len(code.co_code) <= 4:
        return False

    return True


def typeclass(fn: F) -> TypeClass[F]:
    """Decorator to create a typeclass from a function signature.

    The decorated function serves as the default implementation (if it has a body)
    or just defines the signature (if the body is `...`).

    Args:
        fn: The function defining the typeclass signature.

    Returns:
        A TypeClass instance that can dispatch to registered instances.

    Example:
        ```python
        @typeclass
        def serialize(value) -> str:
            '''Serialize a value to string.'''
            ...

        @serialize.instance(int)
        def serialize_int(value: int) -> str:
            return str(value)

        serialize(42)
        # '42'
        ```
    """
    return TypeClass(fn)
