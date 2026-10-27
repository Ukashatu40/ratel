"""The storage interface for bss_lines.

Services depend on this protocol, not on SQLAlchemy. Tests use a fake that
matches this shape. The real implementation is in sql.py.
"""

from __future__ import annotations

from typing import Protocol

from app.bss_lines.models.lines import Line


class LinesRepository(Protocol):
    def get(self, line_id: int) -> Line | None:
        """Load a line by its id. None if not found."""
        ...

    def save(self, line: Line) -> None:
        """Persist the line's current state (set by the state machine)."""
        ...

    def retire_sim(self, iccid: str) -> None:
        """Mark the SIM with this ICCID retired. Used when a line is terminated."""
        ...

    def add_audit(
        self,
        *,
        line_id: int,
        from_state: str,
        to_state: str,
        actor: str,
        reason: str,
    ) -> None:
        """Append an audit entry for a state change."""
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...
