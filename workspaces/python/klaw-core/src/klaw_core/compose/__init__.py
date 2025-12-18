"""Composition utilities: pipe() function and Deref mixin."""

from klaw_core.compose.deref import Deref, DerefOk, DerefSome
from klaw_core.compose.pipe import pipe

__all__ = [
    'Deref',
    'DerefOk',
    'DerefSome',
    'pipe',
]
