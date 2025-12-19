"""Channel statistics dataclasses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import msgspec

__all__ = ['ChannelCheckpoint', 'ChannelStats']


class ChannelStats(msgspec.Struct, frozen=True, gc=False):
    """Statistics snapshot for a channel."""

    sender_count: int
    receiver_count: int
    queue_size: int
    capacity: int | None
    senders_closed: bool
    receivers_closed: bool
    created_at: datetime
    high_watermark: int
    total_sent: int
    total_received: int
    backend_extras: dict[str, Any] | None = None


class ChannelCheckpoint(msgspec.Struct, frozen=True, gc=False):
    """Checkpoint state for channel recovery."""

    created_at: datetime
    total_sent: int
    total_received: int
    senders_closed: bool
    receivers_closed: bool
