"""Channels: multi-producer multi-consumer, oneshot, broadcast, watch, select.

Provides ergonomic channel types for passing data between concurrent tasks:
- `channel[T]()`: Multi-producer multi-consumer MPMC channel
- `oneshot[T]()`: Single-value, single-use channel
- `broadcast[T]()`: All receivers get every message
- `watch[T](initial)`: Latest-value observation with `.borrow()` and `.changed()`
- `select(*receivers)`: Multiplex multiple receivers

All channels support async/await operations and can be cloned for distributed use.

Built on anyio.create_memory_object_stream() which provides:
- Thread-safe and task-safe send/receive
- Automatic closure signaling (EndOfStream exception when all senders close)
- Reference-counted clones (stream only closes when all clones are closed)
- Async iteration support
- MPMC semantics (each message delivered to one receiver)

## Cancellation & Timeouts

Channels integrate with anyio/trio cancellation semantics:
- Send/recv operations can be cancelled via anyio.CancelScope()
- Timeouts should be enforced by the caller using anyio.fail_after() or anyio.move_on_after()
- Cancellation during send/recv will raise anyio.get_cancelled_exc_class()

Example with timeout:
    ```python
    with anyio.fail_after(5):
        value = await rx.recv()  # Raises TimeoutError if takes >5s
    ```
"""

from klaw_core.runtime.channels.broadcast import BroadcastReceiver, BroadcastSender
from klaw_core.runtime.channels.factory import (
    broadcast,
    channel,
    oneshot,
    select,
    watch,
)
from klaw_core.runtime.channels.local import LocalReceiver, LocalSender
from klaw_core.runtime.channels.oneshot import OneshotReceiver, OneshotSender
from klaw_core.runtime.channels.protocols import Receiver, Sender
from klaw_core.runtime.channels.watch import WatchReceiver, WatchSender

__all__ = [
    'BroadcastReceiver',
    'BroadcastSender',
    'LocalReceiver',
    'LocalSender',
    'OneshotReceiver',
    'OneshotSender',
    'Receiver',
    'Sender',
    'WatchReceiver',
    'WatchSender',
    'broadcast',
    'channel',
    'oneshot',
    'select',
    'watch',
]
