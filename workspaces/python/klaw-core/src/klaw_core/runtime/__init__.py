"""
klaw_core.runtime: Unified async/multiprocess runtime module.

Provides ergonomic APIs for concurrent and parallel execution with full Result[T, E]
integration, backend-agnostic execution (local + Ray), structured concurrency,
channels, and context propagation.

This module consolidates async utilities and provides a single concurrency foundation
for the Klaw ecosystem.
"""

from klaw_core.runtime._backends import ExecutorBackend, ExitReason
from klaw_core.runtime._config import Backend, RuntimeConfig, get_config, init
from klaw_core.runtime.channels import Receiver, Sender, broadcast, channel, oneshot, select, watch
from klaw_core.runtime.errors import (
    ActorNotFound,
    ActorNotFoundError,
    ActorStopped,
    ActorStoppedError,
    BackendError,
    BackendException,
    Cancelled,
    CancelledError,
    ChannelClosed,
    ChannelClosedError,
    ChannelEmpty,
    ChannelEmptyError,
    ChannelFull,
    ChannelFullError,
    Timeout,
    TimeoutError,
)
from klaw_core.runtime.executor import Executor, TaskHandle

__all__ = [
    # Config
    "Backend",
    "RuntimeConfig",
    "init",
    "get_config",
    # Executor
    "Executor",
    "TaskHandle",
    "ExecutorBackend",
    "ExitReason",
    # Channels
    "Sender",
    "Receiver",
    "channel",
    "oneshot",
    "broadcast",
    "watch",
    "select",
    # Errors - struct variants
    "ChannelClosed",
    "ChannelFull",
    "ChannelEmpty",
    "Timeout",
    "Cancelled",
    "BackendError",
    "ActorStopped",
    "ActorNotFound",
    # Errors - exception variants
    "ChannelClosedError",
    "ChannelFullError",
    "ChannelEmptyError",
    "TimeoutError",
    "CancelledError",
    "BackendException",
    "ActorStoppedError",
    "ActorNotFoundError",
]
