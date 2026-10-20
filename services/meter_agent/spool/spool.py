"""Disk spool with ordered replay (W2-15).

The spool never opens a network connection. The sender is passed in, so
tests use a fake sender and a temporary directory. See W2-15.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# A sender takes one batch (a JSON-serialisable dict or list) and returns
# True when the API acknowledged it. It may raise; the spool treats any
# exception as "not acknowledged".
Sender = Callable[[object], bool]


@dataclass(frozen=True, slots=True)
class SpoolResult:
    """What happened in one replay pass."""

    delivered: int
    remaining: int
    quarantined: int


def _make_private(directory: Path) -> None:
    """Create the directory if needed and make it readable by its owner only.

    Batches hold IMSIs, which are personal data. The mode is set explicitly
    after creating, because `mkdir` obeys the umask and leaves an existing
    directory as it was. Files made by `mkstemp` are already owner-only.
    """
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)


class Spool:
    """A directory of pending batches, oldest first by filename.

    File names sort lexicographically into chronological order. Callers
    name files by the interval's period_start, zero-padded, so a replay
    always processes the oldest first.
    """

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self._dir = Path(directory)
        _make_private(self._dir)
        self._quarantine = self._dir / "quarantine"
        _make_private(self._quarantine)

    def spool(self, name: str, batch: object) -> Path:
        """Write one batch to disk atomically.

        Write to a temporary file in the same directory, then rename it,
        so a crash never leaves a half-written file that looks complete.
        """
        target = self._dir / name
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, prefix=".tmp-")
        try:
            with os.fdopen(fd, "w") as tmp:
                json.dump(batch, tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            # Never leave a temporary file behind.
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
        return target

    def pending(self) -> list[Path]:
        """Files waiting to be sent, oldest first.

        Temporary files and the quarantine directory are ignored.
        """
        files = [p for p in self._dir.iterdir() if p.is_file() and not p.name.startswith(".tmp-")]
        return sorted(files, key=lambda p: p.name)

    def replay(self, sender: Sender) -> SpoolResult:
        """Send every pending batch, oldest first, and delete on ack.

        A file that cannot be read is moved aside, never deleted, and
        replay continues with the next file. A file the sender does not
        acknowledge is left in place.
        """
        delivered = 0
        quarantined = 0
        for path in self.pending():
            try:
                batch = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                # Corrupt or unreadable: quarantine, keep going.
                os.replace(path, self._quarantine / path.name)
                quarantined += 1
                continue

            try:
                acknowledged = sender(batch)
            except Exception:
                # The sender failed. Leave the file for the next pass.
                acknowledged = False

            if acknowledged:
                path.unlink()
                delivered += 1

        remaining = len(self.pending())
        return SpoolResult(delivered=delivered, remaining=remaining, quarantined=quarantined)
