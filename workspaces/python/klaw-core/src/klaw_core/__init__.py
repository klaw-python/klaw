"""klaw-core: Foundation package for the Klaw ecosystem.

Type-safe Result and Option types for Python 3.13+, with async support,
decorators, and functional composition utilities.

Flat imports (preferred):
    from klaw_core import Result, Ok, Err, Option, Some, Nothing
    from klaw_core import safe, pipe, result, do, fn, typeclass

Submodule imports (for organization):
    from klaw_core.result import Ok, Err, Result
    from klaw_core.option import Some, Nothing, Option
    from klaw_core.decorators import safe, pipe
    from klaw_core.fn import fn
"""

# Types (flattened from types/)
# Assertions
from klaw_core.assertions import assert_result, safe_assert

# Async
from klaw_core.async_ import AsyncResult, async_collect, async_lru_safe

# Composition
from klaw_core.compose import Deref, DerefOk, DerefSome
from klaw_core.compose import pipe as pipe_fn

# Decorators
from klaw_core.decorators import (
    do,
    do_async,
    pipe,
    pipe_async,
    result,
    safe,
    safe_async,
)

# Lambda helpers
from klaw_core.fn import fn
from klaw_core.option import (
    Nothing,
    NothingType,
    Option,
    Some,
)
from klaw_core.propagate import Propagate
from klaw_core.result import (
    Err,
    Ok,
    Result,
    collect,
)

# Typeclass
from klaw_core.typeclass import typeclass

__all__ = [
    # Async
    'AsyncResult',
    # Composition
    'Deref',
    'DerefOk',
    'DerefSome',
    # Result types
    'Err',
    # Option types
    'Nothing',
    'NothingType',
    'Ok',
    'Option',
    # Propagation
    'Propagate',
    'Result',
    'Some',
    # Assertions
    'assert_result',
    'async_collect',
    'async_lru_safe',
    'collect',
    # Decorators
    'do',
    'do_async',
    # Lambda helpers
    'fn',
    'pipe',
    'pipe_async',
    'pipe_fn',
    'result',
    'safe',
    'safe_assert',
    'safe_async',
    # Typeclass
    'typeclass',
]
