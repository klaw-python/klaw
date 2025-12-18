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
    # Result types
    'Err',
    'Ok',
    'Result',
    'collect',
    # Option types
    'Nothing',
    'NothingType',
    'Option',
    'Some',
    # Propagation
    'Propagate',
    # Decorators
    'do',
    'do_async',
    'pipe',
    'pipe_async',
    'result',
    'safe',
    'safe_async',
    # Composition
    'Deref',
    'DerefOk',
    'DerefSome',
    'pipe_fn',
    # Typeclass
    'typeclass',
    # Lambda helpers
    'fn',
    # Assertions
    'assert_result',
    'safe_assert',
    # Async
    'AsyncResult',
    'async_collect',
    'async_lru_safe',
]
