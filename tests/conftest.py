from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.synthetic import find_sentinels


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run if a Ki/OPc sentinel reached the captured test log."""
    log_file = Path(session.config.rootpath) / ".pytest_cache" / "ratel-test.log"
    if not log_file.exists():
        return
    leaked = find_sentinels(log_file.read_text(errors="replace"))
    if leaked:
        sys.stderr.write(f"\nSECURITY: Ki/OPc sentinel found in test log {log_file}: {leaked}\n")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
