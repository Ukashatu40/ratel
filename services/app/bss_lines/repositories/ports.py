"""The storage interface for bss_lines.

Services depend on this protocol, not on SQLAlchemy. Tests use a fake that
matches this shape. The real implementation is in sql.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.bss_lines.models.lines import Line


class LinesRepository(Protocol):
    def get(self, line_id: int) -> Line | None:
        """Load a line by its id to change it. None if not found.

        The line is locked until the transaction ends, so two changes to one line take turns.
        """
        ...

    def find_by_identifier(
        self,
        *,
        line_id: int | None = None,
        msisdn: str | None = None,
        iccid: str | None = None,
        imsi: str | None = None,
    ) -> Line | None:
        """Load a line by exactly one of line_id, msisdn, iccid or imsi."""
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


class PaidPlanCheck(Protocol):
    """Whether a line has data it has paid for. Answered by BSS: money, which owns allowances."""

    def has_paid_allowance(self, line_id: int, now: datetime) -> bool:
        """True if the line has an allowance with data left that has not yet expired.

        An allowance that starts later counts: the customer has paid and it is on its way.
        """
        ...
