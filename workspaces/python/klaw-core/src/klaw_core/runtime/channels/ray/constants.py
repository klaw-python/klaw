"""Ray channel constants."""

from __future__ import annotations

import os
from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar

import msgspec

T = TypeVar('T')

DEFAULT_RAY_NAMESPACE = os.environ.get('KLAW_RAY_NAMESPACE', 'klaw')


class ChannelType(StrEnum):
    """Channel type identifiers."""

    MPMC = 'mpmc'
    BROADCAST = 'broadcast'
    WATCH = 'watch'
    ONESHOT = 'oneshot'


class ReaderInfo(msgspec.Struct, frozen=True, gc=False):
    """Per-reader tracking information."""

    reader_id: str
    node_id: str
    registered_at: datetime
    last_seen_at: datetime
    total_received: int


class SingleResult(msgspec.Struct, Generic[T], frozen=True, gc=False):
    """Typed, immutable response for single-value operations."""

    status: str
    value: T | None = None


class BatchResult(msgspec.Struct, Generic[T], frozen=True, gc=False):
    """Typed, immutable response for batch operations."""

    status: str
    items: tuple[T, ...] = ()


class ChannelMetadata(msgspec.Struct, frozen=True, gc=False):
    """Channel metadata for type dispatch."""

    channel_type: ChannelType
    capacity: int | None
    unbounded: bool
    value_type: str | None = None
