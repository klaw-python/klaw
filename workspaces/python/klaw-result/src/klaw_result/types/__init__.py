"""Core types: Result, Ok, Err, Option, Some, Nothing."""

from klaw_result.types.option import Nothing, Option, Some
from klaw_result.types.propagate import Propagate
from klaw_result.types.result import Err, Ok, Result

__all__ = [
    "Err",
    "Nothing",
    "Ok",
    "Option",
    "Propagate",
    "Result",
    "Some",
]
