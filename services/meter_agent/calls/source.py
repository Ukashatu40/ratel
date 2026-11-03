"""Getting rows from the voice VM's MySQL without a SQL driver in the agent.

The agent runs a fixed command (`deploy/voice/ratel-call-export.sh`, behind a one-line sudo rule)
that prints tab-separated rows. The command takes three whole numbers and nothing else, so nothing
the agent reads can change what it asks for.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Protocol

from .rows import CallRow


class CallSourceError(Exception):
    """The export could not run or printed something unreadable. Carries no row data."""


class CallSource(Protocol):
    def fetch(
        self, after_acc: int, after_missed: int, settle_seconds: int
    ) -> tuple[list[CallRow], int]:
        """Rows newer than the two ids and `settle_seconds` old, and how many lines were skipped."""
        ...


_FIELDS = 10


def parse_rows(output: str) -> tuple[list[CallRow], int]:
    rows: list[CallRow] = []
    skipped = 0
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != _FIELDS or parts[0] not in ("acc", "missed"):
            skipped += 1
            continue
        try:
            rows.append(
                CallRow(
                    table=parts[0],
                    row_id=int(parts[1]),
                    method=parts[2],
                    sip_code=int(parts[3]),
                    call_id=parts[4],
                    from_tag=parts[5],
                    from_user=parts[6],
                    to_user=parts[7],
                    time=int(float(parts[8])),
                    start_ts=int(float(parts[9])),
                )
            )
        except ValueError:
            skipped += 1
    return rows, skipped


class CommandCallSource:
    def __init__(self, command: str, timeout_seconds: float = 30.0) -> None:
        self._command = shlex.split(command)
        self._timeout = timeout_seconds

    def fetch(
        self, after_acc: int, after_missed: int, settle_seconds: int
    ) -> tuple[list[CallRow], int]:
        args = [
            *self._command,
            "--after-acc", str(int(after_acc)),
            "--after-missed", str(int(after_missed)),
            "--settle", str(int(settle_seconds)),
        ]  # fmt: skip
        try:
            result = subprocess.run(  # noqa: S603  (a fixed command and whole numbers)
                args, capture_output=True, text=True, timeout=self._timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CallSourceError(type(exc).__name__) from None
        if result.returncode != 0:
            # The command's own message could carry a database error; the status is enough.
            raise CallSourceError(f"exit {result.returncode}")
        return parse_rows(result.stdout)
