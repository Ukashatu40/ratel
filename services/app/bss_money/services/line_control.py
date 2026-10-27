"""The rating job's changes to a line, made through BSS: lines' state machine.

BSS: money never calls RatelLink or sets a line's state itself (docs/DEPENDENCIES.md): it asks
BSS: lines, which validates the move, calls RatelLink and writes the audit entry. Each change gets
a fresh transaction, because the lifecycle commits.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from app.bss_lines.repositories.ports import LinesRepository
from app.bss_lines.services.lifecycle import (
    RatelLinkClientProto,
    expire_line,
    mark_out_of_data,
    restore_line,
)

LinesScope = Callable[[], AbstractContextManager[LinesRepository]]
"""Opens a session and yields the lines repository on it; closes the session on exit."""


class LifecycleLineControl:
    def __init__(self, lines_scope: LinesScope, client: RatelLinkClientProto) -> None:
        self._lines_scope = lines_scope
        self._client = client

    def mark_out_of_data(self, line_id: int, idempotency_key: str) -> None:
        with self._lines_scope() as lines:
            mark_out_of_data(lines, self._client, line_id, idempotency_key=idempotency_key)

    def expire(self, line_id: int, idempotency_key: str) -> None:
        with self._lines_scope() as lines:
            expire_line(lines, self._client, line_id, idempotency_key=idempotency_key)

    def restore(self, line_id: int, idempotency_key: str) -> None:
        with self._lines_scope() as lines:
            restore_line(lines, self._client, line_id, idempotency_key=idempotency_key)
