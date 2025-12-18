"""Typed lambda placeholder for concise function creation.

Supports two styles:

    # Operator syntax (chainable Expr)
    fn + 1          → Expr computing x + 1
    fn * 2 + 1      → Expr computing x * 2 + 1
    fn["key"]       → Expr computing x["key"]

    # Method syntax (returns typed Callable)
    fn.upper()      → Callable[[str], str]
    fn.mul(2)       → Callable[[int], int]
    fn.item("key")  → Callable[[Mapping[K, V]], V]

Example:
    ```python
    from klaw_core import fn
    (fn + 1)(5)  # 6
    (fn * 2)(5)  # 10
    fn.upper()("hello")  # 'HELLO'
    list(map(fn.mul(2), [1, 2, 3]))  # [2, 4, 6]
    ```
"""

from klaw_core.fn.lambda_ import Expr, Lambda, Stream, fn

__all__ = [
    'Expr',
    'Lambda',
    'Stream',
    'fn',
]
