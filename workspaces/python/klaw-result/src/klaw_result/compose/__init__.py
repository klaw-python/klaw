"""Composition utilities: pipe() function and Deref mixin."""

from klaw_result.compose.deref import Deref, DerefOk, DerefSome
from klaw_result.compose.pipe import pipe

__all__ = [
    "Deref",
    "DerefOk",
    "DerefSome",
    "pipe",
]
