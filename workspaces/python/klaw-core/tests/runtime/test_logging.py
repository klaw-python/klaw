"""Tests for runtime logging configuration and hooks."""

from __future__ import annotations

from typing import Any

import pytest
from klaw_core.runtime._logging import (
    add_log_hook,
    clear_log_hooks,
    configure_logging,
    get_logger,
    remove_log_hook,
)


@pytest.fixture(autouse=True)
def cleanup_hooks() -> None:
    """Clear log hooks before and after each test."""
    clear_log_hooks()
    yield
    clear_log_hooks()


class TestLogHooks:
    """Tests for logging hooks functionality."""

    def test_hook_receives_log_events(self) -> None:
        """Registered hooks receive log entry dicts."""
        received: list[dict[str, Any]] = []

        def capture_hook(event_dict: dict[str, Any]) -> None:
            received.append(event_dict)

        configure_logging(level='DEBUG', json_output=True)
        add_log_hook(capture_hook)

        logger = get_logger('test')
        logger.info('Test message', extra_field='extra_value')

        assert len(received) >= 1
        # Find our log entry
        test_entries = [e for e in received if e.get('event') == 'Test message']
        assert len(test_entries) == 1
        assert test_entries[0]['extra_field'] == 'extra_value'

    def test_multiple_hooks_all_called(self) -> None:
        """Multiple registered hooks are all called."""
        calls: list[str] = []

        def hook1(event_dict: dict[str, Any]) -> None:
            calls.append('hook1')

        def hook2(event_dict: dict[str, Any]) -> None:
            calls.append('hook2')

        configure_logging(level='DEBUG', json_output=True)
        add_log_hook(hook1)
        add_log_hook(hook2)

        logger = get_logger('test')
        logger.info('Test')

        assert 'hook1' in calls
        assert 'hook2' in calls

    def test_remove_hook(self) -> None:
        """remove_log_hook() stops hook from being called."""
        calls: list[str] = []

        def hook(event_dict: dict[str, Any]) -> None:
            calls.append('called')

        configure_logging(level='DEBUG', json_output=True)
        add_log_hook(hook)

        logger = get_logger('test')
        logger.info('First')
        assert len(calls) == 1

        remove_log_hook(hook)
        logger.info('Second')
        assert len(calls) == 1  # No new calls

    def test_clear_hooks(self) -> None:
        """clear_log_hooks() removes all hooks."""
        calls: list[str] = []

        def hook1(event_dict: dict[str, Any]) -> None:
            calls.append('hook1')

        def hook2(event_dict: dict[str, Any]) -> None:
            calls.append('hook2')

        configure_logging(level='DEBUG', json_output=True)
        add_log_hook(hook1)
        add_log_hook(hook2)

        logger = get_logger('test')
        logger.info('First')
        assert len(calls) == 2

        clear_log_hooks()
        logger.info('Second')
        assert len(calls) == 2  # No new calls

    def test_hook_exception_does_not_break_logging(self) -> None:
        """Exceptions in hooks don't prevent logging or other hooks."""
        calls: list[str] = []

        def bad_hook(event_dict: dict[str, Any]) -> None:
            raise RuntimeError('Hook failed')

        def good_hook(event_dict: dict[str, Any]) -> None:
            calls.append('good')

        configure_logging(level='DEBUG', json_output=True)
        add_log_hook(bad_hook)
        add_log_hook(good_hook)

        logger = get_logger('test')
        # Should not raise
        logger.info('Test')

        # Good hook should still be called
        assert 'good' in calls

    def test_hook_receives_copy_of_event_dict(self) -> None:
        """Hooks receive a copy, not the original event dict."""
        received: list[dict[str, Any]] = []

        def mutating_hook(event_dict: dict[str, Any]) -> None:
            event_dict['mutated'] = True
            received.append(event_dict)

        configure_logging(level='DEBUG', json_output=True)
        add_log_hook(mutating_hook)

        logger = get_logger('test')
        logger.info('Test')

        # Hook received the dict and mutated it
        assert len(received) == 1
        assert received[0].get('mutated') is True
