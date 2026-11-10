"""The previous counter reading of every address, kept on disk (W2-14).

The agent counts by subtracting the previous reading from the current one. Held only in memory,
that reading is lost at every restart, and the traffic since the last tick with it. Here it is
written after each tick, owner-only and replaced atomically, so a restart carries on where the
last tick stopped.

No network access. A file that cannot be read is set aside, never trusted: the agent then starts
from a baseline, which loses at most one interval, never invents bytes.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from common.logging import log_event

from ..domain.records import Reading
from .spool import _make_private

log = logging.getLogger("ratel.meter.readings")

# A released address is not given to another line for 24 hours (PRODUCT_RULES.md, data path). A
# reading older than that could be charged to the wrong line, so it is not resumed from: the
# agent takes a fresh baseline instead. An hour of margin.
MAX_AGE_SECONDS = 23 * 3600

_FILE = "readings.json"


class ReadingStore:
    def __init__(
        self, directory: str | os.PathLike[str], max_age_seconds: int = MAX_AGE_SECONDS
    ) -> None:
        self._dir = Path(directory)
        _make_private(self._dir)
        self._file = self._dir / _FILE
        self._max_age = max_age_seconds

    def load(self, now: int) -> dict[str, Reading]:
        """The readings saved by the last run that are still safe to count from."""
        if not self._file.exists():
            return {}
        try:
            data = json.loads(self._file.read_text())
            saved = data["readings"]
            if not isinstance(saved, dict):
                raise TypeError("readings must be an object")
            readings = {
                ue_ip: Reading(ue_ip, _count(up), _count(down), _count(read_at))
                for ue_ip, (up, down, read_at) in saved.items()
            }
        except (OSError, ValueError, KeyError, TypeError):
            os.replace(self._file, self._dir / "readings.damaged")
            log_event(log, logging.WARNING, "meter.readings.damaged")
            return {}
        fresh = {ip: r for ip, r in readings.items() if now - r.read_at < self._max_age}
        if len(fresh) < len(readings):
            dropped = len(readings) - len(fresh)
            log_event(log, logging.WARNING, "meter.readings.expired", count=dropped)
        return fresh

    def save(self, readings: Mapping[str, Reading]) -> None:
        payload = {
            "readings": {
                ue_ip: [r.bytes_up_total, r.bytes_down_total, r.read_at]
                for ue_ip, r in readings.items()
            }
        }
        fd, tmp = tempfile.mkstemp(dir=self._dir, prefix=".tmp-")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._file)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise


def _count(value: object) -> int:
    """A whole non-negative number from the file, or an error that sets the file aside."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("not a whole non-negative number")
    return value
