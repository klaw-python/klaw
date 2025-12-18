"""Runtime error types: dual struct+exception for Result and raise-based code."""

from __future__ import annotations

import msgspec

__all__ = [
    'ActorNotFound',
    'ActorNotFoundError',
    'ActorStopped',
    'ActorStoppedError',
    'BackendError',
    'BackendException',
    'Cancelled',
    'CancelledError',
    'ChannelClosed',
    'ChannelClosedError',
    'ChannelEmpty',
    'ChannelEmptyError',
    'ChannelFull',
    'ChannelFullError',
    'Timeout',
    'TimeoutError',
]


# --- Channel Errors ---


class ChannelClosed(msgspec.Struct, frozen=True, gc=False):
    """Channel has been closed - struct variant for Result[T, ChannelClosed]."""

    reason: str | None = None

    def to_exception(self) -> ChannelClosedError:
        """Convert to exception for raise-based code."""
        return ChannelClosedError(self.reason)


class ChannelClosedError(Exception):
    """Channel has been closed - exception variant."""

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason
        super().__init__(reason or 'Channel closed')

    def to_struct(self) -> ChannelClosed:
        """Convert to struct for Result-based code."""
        return ChannelClosed(self.reason)


class ChannelFull(msgspec.Struct, frozen=True, gc=False):
    """Channel is at capacity - struct variant for Result[T, ChannelFull]."""

    capacity: int

    def to_exception(self) -> ChannelFullError:
        """Convert to exception for raise-based code."""
        return ChannelFullError(self.capacity)


class ChannelFullError(Exception):
    """Channel is at capacity - exception variant."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        super().__init__(f'Channel full (capacity={capacity})')

    def to_struct(self) -> ChannelFull:
        """Convert to struct for Result-based code."""
        return ChannelFull(self.capacity)


class ChannelEmpty(msgspec.Struct, frozen=True, gc=False):
    """Channel has no messages - struct variant for Result[T, ChannelEmpty]."""

    def to_exception(self) -> ChannelEmptyError:
        """Convert to exception for raise-based code."""
        return ChannelEmptyError()


class ChannelEmptyError(Exception):
    """Channel has no messages - exception variant."""

    def __init__(self) -> None:
        super().__init__('Channel empty')

    def to_struct(self) -> ChannelEmpty:
        """Convert to struct for Result-based code."""
        return ChannelEmpty()


# --- Timeout/Cancellation Errors ---


class Timeout(msgspec.Struct, frozen=True, gc=False):
    """Operation timed out - struct variant for Result[T, Timeout]."""

    seconds: float
    operation: str | None = None

    def to_exception(self) -> TimeoutError:
        """Convert to exception for raise-based code."""
        return TimeoutError(self.seconds, self.operation)


class TimeoutError(Exception):  # noqa: A001 - intentionally shadows builtin
    """Operation timed out - exception variant."""

    def __init__(self, seconds: float, operation: str | None = None) -> None:
        self.seconds = seconds
        self.operation = operation
        msg = f'Timeout after {seconds}s'
        if operation:
            msg = f'{operation}: {msg}'
        super().__init__(msg)

    def to_struct(self) -> Timeout:
        """Convert to struct for Result-based code."""
        return Timeout(self.seconds, self.operation)


class Cancelled(msgspec.Struct, frozen=True, gc=False):
    """Operation was cancelled - struct variant for Result[T, Cancelled]."""

    reason: str | None = None

    def to_exception(self) -> CancelledError:
        """Convert to exception for raise-based code."""
        return CancelledError(self.reason)


class CancelledError(Exception):
    """Operation was cancelled - exception variant."""

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason
        super().__init__(reason or 'Operation cancelled')

    def to_struct(self) -> Cancelled:
        """Convert to struct for Result-based code."""
        return Cancelled(self.reason)


# --- Backend Errors ---


class BackendError(msgspec.Struct, frozen=True, gc=False):
    """Backend operation failed - struct variant for Result[T, BackendError]."""

    message: str
    backend: str

    def to_exception(self) -> BackendException:
        """Convert to exception for raise-based code."""
        return BackendException(self.message, self.backend)


class BackendException(Exception):
    """Backend operation failed - exception variant."""

    def __init__(self, message: str, backend: str) -> None:
        self.message = message
        self.backend = backend
        super().__init__(f'[{backend}] {message}')

    def to_struct(self) -> BackendError:
        """Convert to struct for Result-based code."""
        return BackendError(self.message, self.backend)


# --- Actor Errors ---


class ActorStopped(msgspec.Struct, frozen=True, gc=False):
    """Actor has stopped - struct variant for Result[T, ActorStopped]."""

    actor_name: str | None = None
    reason: str | None = None

    def to_exception(self) -> ActorStoppedError:
        """Convert to exception for raise-based code."""
        return ActorStoppedError(self.actor_name, self.reason)


class ActorStoppedError(Exception):
    """Actor has stopped - exception variant."""

    def __init__(self, actor_name: str | None = None, reason: str | None = None) -> None:
        self.actor_name = actor_name
        self.reason = reason
        msg = 'Actor stopped'
        if actor_name:
            msg = f"Actor '{actor_name}' stopped"
        if reason:
            msg = f'{msg}: {reason}'
        super().__init__(msg)

    def to_struct(self) -> ActorStopped:
        """Convert to struct for Result-based code."""
        return ActorStopped(self.actor_name, self.reason)


class ActorNotFound(msgspec.Struct, frozen=True, gc=False):
    """Named actor not found in registry - struct variant."""

    name: str

    def to_exception(self) -> ActorNotFoundError:
        """Convert to exception for raise-based code."""
        return ActorNotFoundError(self.name)


class ActorNotFoundError(Exception):
    """Named actor not found in registry - exception variant."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Actor not found: '{name}'")

    def to_struct(self) -> ActorNotFound:
        """Convert to struct for Result-based code."""
        return ActorNotFound(self.name)
