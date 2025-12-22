"""Constrained type aliases for decode-time validation.

This module provides type aliases with constraints that are validated
automatically by msgspec during decoding. Using these types in your
structs ensures invalid values are rejected at deserialization time
with clear error messages.

Key benefits:
    - Catch misconfigurations at load time, not runtime
    - Self-documenting valid ranges in type signatures
    - Zero runtime overhead for valid data (validation during decode)

Usage:
    >>> import msgspec
    >>> from klaw_core.runtime.types import ChannelCapacity, TimeoutSeconds
    >>>
    >>> class ChannelConfig(msgspec.Struct):
    ...     capacity: ChannelCapacity  # Must be 1-1,000,000
    ...     timeout: TimeoutSeconds    # Must be 0-86400
    >>>
    >>> # Valid
    >>> config = msgspec.json.decode(
    ...     b'{"capacity": 100, "timeout": 30.0}',
    ...     type=ChannelConfig
    ... )
    >>>
    >>> # Invalid - raises ValidationError
    >>> msgspec.json.decode(
    ...     b'{"capacity": 0, "timeout": 30.0}',
    ...     type=ChannelConfig
    ... )
    # ValidationError: Expected `int` >= 1 - at `$.capacity`

See Also:
    - https://jcristharif.com/msgspec/constraints.html
    - PRD §FR-1.3: Constrained Types specification
"""

from __future__ import annotations

from typing import Annotated

import msgspec

__all__ = [
    'ChannelCapacity',
    'ConcurrencyLimit',
    'Identifier',
    'Namespace',
    'NonNegativeInt',
    'PositiveInt',
    'TimeoutSeconds',
]

# -----------------------------------------------------------------------------
# Numeric Constraints
# -----------------------------------------------------------------------------

PositiveInt = Annotated[int, msgspec.Meta(gt=0)]
"""Integer greater than zero.

Valid: 1, 100, 1_000_000
Invalid: 0, -1, -100
"""

NonNegativeInt = Annotated[int, msgspec.Meta(ge=0)]
"""Integer greater than or equal to zero.

Valid: 0, 1, 100, 1_000_000
Invalid: -1, -100
"""

ChannelCapacity = Annotated[int, msgspec.Meta(ge=1, le=1_000_000)]
"""Channel buffer capacity constraint.

Valid range: 1 to 1,000,000 (inclusive)

This prevents misconfiguration of channel sizes that could cause
memory issues (too large) or deadlocks (zero/negative).
"""

TimeoutSeconds = Annotated[float, msgspec.Meta(ge=0.0, le=86400.0)]
"""Timeout duration in seconds.

Valid range: 0.0 to 86400.0 (24 hours, inclusive)

Zero means no timeout (immediate). The upper bound prevents
accidental infinite waits from typos (e.g., milliseconds vs seconds).
"""

ConcurrencyLimit = Annotated[int, msgspec.Meta(ge=1, le=10_000)]
"""Maximum concurrent operations constraint.

Valid range: 1 to 10,000 (inclusive)

This prevents misconfiguration that could exhaust system resources
(too high) or serialize all operations (zero).
"""

# -----------------------------------------------------------------------------
# String Constraints
# -----------------------------------------------------------------------------

Identifier = Annotated[
    str,
    msgspec.Meta(
        min_length=1,
        max_length=255,
        pattern=r'^[a-zA-Z_][a-zA-Z0-9_-]*$',
    ),
]
"""General-purpose identifier for channels, tasks, etc.

Constraints:
    - Length: 1 to 255 characters
    - Pattern: Must start with letter or underscore, followed by
      letters, digits, underscores, or hyphens

Valid: "foo", "foo_bar", "Foo-123", "_private"
Invalid: "", "123foo", "foo bar", "foo.bar"
"""

Namespace = Annotated[
    str,
    msgspec.Meta(
        min_length=1,
        max_length=63,
        pattern=r'^[a-z][a-z0-9-]*$',
    ),
]
"""Kubernetes-style namespace identifier.

Constraints:
    - Length: 1 to 63 characters (DNS label limit)
    - Pattern: Must start with lowercase letter, followed by
      lowercase letters, digits, or hyphens

Valid: "klaw", "my-namespace", "prod01"
Invalid: "", "MyNamespace", "123ns", "ns_with_underscore"
"""
