"""klaw-result: Type-safe Result and Option types for Python 3.13+.

Flat imports (preferred):
    from klaw_result import Result, Ok, Err, Option, Some, Nothing
    from klaw_result import safe, pipe, result, do, fn, typeclass

Submodule imports (for organization):
    from klaw_result.types import Result, Option
    from klaw_result.decorators import safe, pipe
    from klaw_result.fn import fn
"""

# Types
from klaw_result.types import (
    Err,
    Nothing,
    Ok,
    Option,
    Propagate,
    Result,
    Some,
)

# Decorators
from klaw_result.decorators import (
    do,
    do_async,
    pipe,
    pipe_async,
    result,
    safe,
    safe_async,
)

# Composition
from klaw_result.compose import Deref
from klaw_result.compose import pipe as pipe_fn

# Typeclass
from klaw_result.typeclass import typeclass

# Lambda helpers
from klaw_result.fn import fn

# Assertions
from klaw_result.assertions import assert_result, safe_assert

# Async
from klaw_result.async_ import AsyncResult, async_collect, async_lru_safe

__all__ = [
    "AsyncResult",
    "Deref",
    "Err",
    "Nothing",
    "Ok",
    "Option",
    "Propagate",
    "Result",
    "Some",
    "assert_result",
    "async_collect",
    "async_lru_safe",
    "do",
    "do_async",
    "fn",
    "pipe",
    "pipe_async",
    "pipe_fn",
    "result",
    "safe",
    "safe_assert",
    "safe_async",
    "typeclass",
]
