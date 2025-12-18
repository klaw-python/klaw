"""Structured logging configuration for the klaw runtime.

Supports both local (structlog) and Ray backends with consistent JSON output.
Ray provides built-in structured logging with context injection (job_id, worker_id,
actor_id, task_id, etc.) which we leverage when running on the Ray backend.

Uses structlog's ProcessorFormatter to unify structlog and stdlib logging output,
ensuring third-party libraries also emit structured logs.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    'add_log_hook',
    'clear_log_hooks',
    'configure_logging',
    'configure_ray_logging',
    'get_logger',
    'get_ray_logging_config',
    'remove_log_hook',
]


def _get_shared_processors() -> list[Any]:
    """Get processors shared between structlog and stdlib foreign logs."""
    import structlog

    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.stdlib.ExtraAdder(),
        _create_hook_processor(),  # Wire hooks into the pipeline
    ]


def _get_structlog_processors() -> list[Any]:
    """Get the full processor chain for structlog loggers."""
    import structlog

    return [
        *_get_shared_processors(),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]


def _get_renderer(json_output: bool = True) -> Any:
    """Get the appropriate renderer based on output format."""
    import structlog

    if json_output:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())


def configure_logging(
    level: str = 'INFO',
    *,
    json_output: bool = True,
) -> None:
    """Configure structlog with ProcessorFormatter for unified output.

    This configuration ensures both structlog loggers and standard library
    loggers (from third-party packages) emit consistent structured logs.

    Args:
        level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").
        json_output: If True, emit JSON logs. If False, use colored console output.
    """
    import structlog

    # Configure structlog
    structlog.configure(
        processors=_get_structlog_processors(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging with ProcessorFormatter
    # This ensures third-party logs also get structured output
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_get_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _get_renderer(json_output),
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str | None = None) -> Any:
    """Get a structlog logger.

    Args:
        name: Logger name. If None, uses the caller's module name.

    Returns:
        A structlog BoundLogger.
    """
    import structlog

    return structlog.get_logger(name)


def get_ray_logging_config(level: str = 'INFO') -> Any:
    """Get Ray LoggingConfig for structured JSON logging.

    Ray's LoggingConfig automatically injects context fields:
    - job_id, worker_id, node_id
    - actor_id, actor_name (for actors)
    - task_id, task_name, task_function_name (for tasks)

    Args:
        level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").

    Returns:
        ray.LoggingConfig configured for JSON output.

    Raises:
        ImportError: If ray is not installed.
    """
    import ray

    return ray.LoggingConfig(encoding='JSON', log_level=level.upper())


def configure_ray_logging(level: str = 'INFO') -> Any:
    """Configure Ray logging with structured JSON output.

    This returns a LoggingConfig that should be passed to ray.init():

        config = configure_ray_logging("INFO")
        ray.init(logging_config=config)

    Args:
        level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").

    Returns:
        ray.LoggingConfig for use with ray.init().
    """
    return get_ray_logging_config(level)


# --- Logging Hooks ---

_log_hooks: list[Callable[[dict[str, Any]], None]] = []


def add_log_hook(hook: Callable[[dict[str, Any]], None]) -> None:
    """Register a hook to be called for each log entry.

    Hooks receive a dict with log entry fields and can be used for
    custom processing, metrics, alerting, etc.

    Args:
        hook: Callable that receives log entry dict.
    """
    _log_hooks.append(hook)


def remove_log_hook(hook: Callable[[dict[str, Any]], None]) -> None:
    """Remove a previously registered log hook.

    Args:
        hook: The hook to remove.
    """
    if hook in _log_hooks:
        _log_hooks.remove(hook)


def clear_log_hooks() -> None:
    """Remove all registered log hooks."""
    _log_hooks.clear()


def _create_hook_processor() -> Callable[[Any, str, dict[str, Any]], dict[str, Any]]:
    """Create a processor that invokes log hooks."""

    def hook_processor(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        for hook in _log_hooks:
            try:
                hook(event_dict.copy())
            except Exception:
                pass  # Don't let hook failures break logging
        return event_dict

    return hook_processor
