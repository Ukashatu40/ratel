"""The session log is what the Ki/OPc/API-key guard in tests/conftest.py searches. These tests keep
that guard from going blind: it must hold structured fields, and application code that
reconfigures logging must not detach it."""

import logging

import pytest

from common.logging import configure_logging, log_event
from ratel_link.config import Settings
from ratel_link.main import create_app


def _session_log_handler(config: pytest.Config) -> logging.Handler:
    plugin = config.pluginmanager.get_plugin("logging-plugin")
    handler = getattr(plugin, "log_file_handler", None)
    assert handler is not None, "pytest has no log file configured (log_file in pyproject.toml)"
    return handler  # type: ignore[no-any-return]


def test_the_session_log_is_attached_during_a_test(pytestconfig: pytest.Config) -> None:
    assert _session_log_handler(pytestconfig) in logging.getLogger().handlers


def test_creating_the_app_does_not_detach_the_session_log(pytestconfig: pytest.Config) -> None:
    handler = _session_log_handler(pytestconfig)
    create_app(Settings())  # calls configure_logging
    configure_logging("INFO")
    assert handler in logging.getLogger().handlers


def test_the_session_log_holds_fields_not_just_the_message(pytestconfig: pytest.Config) -> None:
    handler = _session_log_handler(pytestconfig)
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "x", (), None)
    record.__dict__.update({"event": "probe.event", "some_field": "visible-in-session-log"})
    assert handler.formatter is not None
    assert "visible-in-session-log" in handler.formatter.format(record)


def test_the_session_log_file_receives_lines_after_create_app(
    pytestconfig: pytest.Config,
) -> None:
    create_app(Settings())
    log_event(logging.getLogger("ratel.test"), logging.WARNING, "session.log.canary", n=1)
    handler = _session_log_handler(pytestconfig)
    handler.flush()
    log_file = pytestconfig.rootpath / ".pytest_cache" / "ratel-test.log"
    assert "session.log.canary" in log_file.read_text()
