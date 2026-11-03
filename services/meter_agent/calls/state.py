"""What the call mode remembers between polls: how far it has read, and the calls still open."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .assemble import OpenCall


@dataclass(slots=True)
class CallState:
    acc_id: int = 0
    missed_id: int = 0
    open_calls: dict[str, OpenCall] = field(default_factory=dict)


class StateStore:
    """One JSON file, owner-only, replaced atomically. A damaged file is set aside and the agent
    starts from zero: calls already posted are posted again under the same Call-ID, which
    overwrites them."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._dir.chmod(0o700)
        self._file = self._dir / "call-state.json"

    def load(self) -> CallState:
        if not self._file.exists():
            return CallState()
        try:
            data = json.loads(self._file.read_text())
            open_calls = {key: OpenCall(**value) for key, value in dict(data["open_calls"]).items()}
            return CallState(int(data["acc_id"]), int(data["missed_id"]), open_calls)
        except (OSError, ValueError, KeyError, TypeError):
            os.replace(self._file, self._dir / "call-state.damaged")
            return CallState()

    def save(self, state: CallState) -> None:
        payload = {
            "acc_id": state.acc_id,
            "missed_id": state.missed_id,
            "open_calls": {
                key: {
                    "call_id": c.call_id,
                    "from_msisdn": c.from_msisdn,
                    "to_msisdn": c.to_msisdn,
                    "started_at": c.started_at,
                    "answered_at": c.answered_at,
                }
                for key, c in state.open_calls.items()
            },
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
