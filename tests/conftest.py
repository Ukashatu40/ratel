from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from common.logging import JsonFormatter
from tests.synthetic import find_sentinels


class _SessionLogFormatter(logging.Formatter):
    """The production JSON format, but deliberately NOT a JsonFormatter instance.

    configure_logging() removes every root handler whose formatter is a JsonFormatter. If this one
    were, the first create_app() in the suite would detach the session log and the guard below
    would go blind (tests/tooling/test_session_log.py watches for that).
    """

    _json = JsonFormatter()

    def format(self, record: logging.LogRecord) -> str:
        return self._json.format(record)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """Write the session log in the production format, fields included.

    Pytest's default log file line holds only the message, so a secret logged as a field value
    (`log_event(..., note=value)`) would never reach the file and the guard below would not see it.
    """
    plugin = config.pluginmanager.get_plugin("logging-plugin")
    handler = getattr(plugin, "log_file_handler", None)
    if handler is not None:
        handler.setFormatter(_SessionLogFormatter())


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run if a Ki, OPc or API-key sentinel reached the captured test log."""
    log_file = Path(session.config.rootpath) / ".pytest_cache" / "ratel-test.log"
    if not log_file.exists():
        return
    leaked = find_sentinels(log_file.read_text(errors="replace"))
    if leaked:
        sys.stderr.write(f"\nSECURITY: sentinel found in test log {log_file}: {leaked}\n")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
