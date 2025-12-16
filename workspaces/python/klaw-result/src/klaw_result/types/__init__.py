"""Core types: Result, Ok, Err, Option, Some, Nothing."""

from klaw_result.types.option import Nothing, NothingType, Option, Some
from klaw_result.types.propagate import Propagate
from klaw_result.types.result import Err, Ok, Result, collect

__all__ = [
    "Err",
    "Nothing",
    "NothingType",
    "Ok",
    "Option",
    "Propagate",
    "Result",
    "Some",
    "collect",
]
